#!/usr/bin/env python3
"""Apply the pinned engine/core/UI patch stack without losing local edits.

The stamp records stack/pin identities and the resulting trees (tracked diffs
and untracked contents). A matching stamp is a no-op; a missing/stale stamp or
--reset snapshots every dirty target, including untracked files, to refs/keep/
before restoring the pinned commits and applying the complete sorted stack.
--check only validates the stamp/tree; it never resets or applies patches.
The shell entry point delegates here on macOS/Linux; Windows calls this file.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid


def git(directory, *args, **kwargs):
    return subprocess.check_output(['git', '-C', str(directory), *args], **kwargs)


def revision(directory, ref='HEAD'):
    return git(directory, 'rev-parse', ref, text=True).strip()


def pin(directory, path):
    return git(directory, 'ls-tree', 'HEAD', path, text=True).split()[2]


def tree_hash(directory):
    digest = hashlib.sha256()
    digest.update(revision(directory).encode())
    digest.update(git(directory, 'diff', '--binary', 'HEAD', '--'))
    for name in sorted(git(directory, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0')):
        if not name:
            continue
        digest.update(b'\0' + name + b'\0')
        path = directory / os.fsdecode(name)
        digest.update(str(path.lstat().st_mode).encode())
        if path.is_symlink():
            digest.update(os.fsencode(os.readlink(path)))
        else:
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(65536), b''):
                    digest.update(chunk)
    return digest.hexdigest()


def snapshot(directory, label, identity):
    if not git(directory, 'status', '--porcelain', '--untracked-files=all'):
        return
    # An empty, private index includes untracked files without touching the
    # user's index. Snapshot nested core separately before its parent engine.
    with tempfile.TemporaryDirectory(prefix='tg2-patch-index-') as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / 'index'))
        git(directory, 'read-tree', 'HEAD', env=env)
        git(directory, 'add', '-A', env=env)
        tree = git(directory, 'write-tree', env=env, text=True).strip()
        commit = git(directory, 'commit-tree', tree, '-p', 'HEAD',
                     input=b'Snapshot before TG2 patch stack reset\n', env=identity).strip().decode()
    name = f'refs/keep/tg2-patches-{label}-{time.time_ns()}-{uuid.uuid4().hex[:8]}'
    git(directory, 'update-ref', name, commit)
    print(f'apply-engine-patches: preserved {label} edits at {name} ({commit})')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--reset', action='store_true', help='snapshot and rebuild the entire stack')
    parser.add_argument('--check', action='store_true', help='read-only stamp/tree validation')
    args = parser.parse_args()
    if args.check and args.reset:
        parser.error('--check and --reset are mutually exclusive')
    repo = args.repo.resolve()
    engine, ui = repo / 'segagenesisrecomp', repo / 'recomp-ui'
    core = engine / 'external/m68k-recomp-core'
    targets = dict(engine=engine, core=core, ui=ui)
    for label, directory in targets.items():
        if not (directory / '.git').exists():
            raise SystemExit(f'apply-engine-patches: {label} submodule is not initialized')
    pins = dict(engine=pin(repo, 'segagenesisrecomp'), ui=pin(repo, 'recomp-ui'))
    # Resolve core from the pinned engine, even if the checked-out HEAD moved.
    pins['core'] = git(engine, 'ls-tree', pins['engine'], 'external/m68k-recomp-core', text=True).split()[2]
    patches = sorted((repo / 'patches/segagenesisrecomp').glob('*.patch'))
    digest = hashlib.sha256()
    for patch in patches:
        digest.update(patch.name.encode() + b'\0')
        digest.update(patch.read_bytes())
    want = dict(version=2, stack=digest.hexdigest(), pins=pins,
                trees={label: tree_hash(path) for label, path in targets.items()})
    stamp = Path(git(repo, 'rev-parse', '--absolute-git-dir', text=True).strip()) / 'tg2-engine-patches.stamp'
    try:
        previous = json.loads(stamp.read_text())
    except (OSError, ValueError):
        previous = None
    if not args.reset and previous == want:
        print('apply-engine-patches: stack already applied (stamp and trees match)')
        return
    if args.check:
        raise SystemExit('apply-engine-patches: stack/tree mismatch; run applicator to snapshot and rebuild')
    # Use the consuming repository's configured identity for recovery commits;
    # a freshly initialized submodule may otherwise inherit a personal global one.
    identity = dict(os.environ)
    for role in ('AUTHOR', 'COMMITTER'):
        for field in ('NAME', 'EMAIL'):
            identity[f'GIT_{role}_{field}'] = git(repo, 'config', f'user.{field.lower()}', text=True).strip()
    # Preserve all targets before the first destructive operation.
    for label in ('core', 'engine', 'ui'):
        snapshot(targets[label], label, identity)
    for label, directory in targets.items():
        git(directory, 'reset', '--hard', pins[label])
        git(directory, 'clean', '-fd')
    for patch in patches:
        label = 'core' if patch.name.startswith('core-') else 'ui' if patch.name.startswith('ui-') else 'engine'
        git(targets[label], 'apply', str(patch))
        print(f'apply-engine-patches: applied {patch.name}')
    want['trees'] = {label: tree_hash(path) for label, path in targets.items()}
    temporary = stamp.with_suffix('.tmp')
    temporary.write_text(json.dumps(want, sort_keys=True) + '\n')
    temporary.replace(stamp)


if __name__ == '__main__':
    main()
