#!/usr/bin/env python3
"""Apply the pinned engine/core/UI patch stack without losing local edits.

The stamp records stack/pin identities and the resulting trees (tracked diffs
and untracked contents). A matching stamp is a no-op; a missing/stale stamp or
--reset snapshots every dirty target, including untracked files, to refs/keep/
before restoring the pinned commits and applying the complete sorted stack.
--check only validates the stamp/tree; it never resets or applies patches.
--as-commits imports the stack into local branches; --export writes their
committed histories back as contiguous patch files. Neither mode pushes.
The shell entry point delegates here on macOS/Linux; Windows calls this file.
"""
import argparse
import base64
import hashlib
import json
import os
import re
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


def target_label(patch):
    return 'core' if patch.name.startswith('core-') else 'ui' if patch.name.startswith('ui-') else 'engine'


def public_identity(repo):
    identity = dict(os.environ)
    for role in ('AUTHOR', 'COMMITTER'):
        for field in ('NAME', 'EMAIL'):
            identity[f'GIT_{role}_{field}'] = git(
                repo, 'config', f'user.{field.lower()}', text=True).strip()
    return identity


def preserve_targets(targets, identity):
    for label in ('core', 'engine', 'ui'):
        snapshot(targets[label], label, identity)


def restore_pins(targets, pins, branch=None):
    for label, directory in targets.items():
        # Detaching keeps local maintenance branches intact during normal builds.
        git(directory, 'checkout', '--detach', '--force', pins[label])
        git(directory, 'clean', '-fd')
        if branch:
            git(directory, 'checkout', '-B', branch, pins[label])


def commit_patch(directory, patch, mail, identity):
    # Several historical inputs are bare unified diffs, not mbox messages.
    # mailinfo preserves supplied messages; only those without a Subject use
    # the descriptive filename as their initial maintenance-commit subject.
    with tempfile.TemporaryDirectory(prefix='tg2-patch-mail-') as tmp:
        message, diff = Path(tmp) / 'message', Path(tmp) / 'diff'
        info = git(directory, 'mailinfo', str(message), str(diff), input=mail).decode()
        fields = dict(line.split(': ', 1) for line in info.splitlines() if ': ' in line)
        subject = fields.get('Subject') or re.sub(r'^(?:core-|ui-)?[0-9]+-', '', patch.stem).replace('-', ' ').capitalize()
        body = message.read_text() if fields.get('Subject') else ''
        message.write_text(subject + '\n\n' + body)
        env = dict(identity)
        if fields.get('Date'):
            env['GIT_AUTHOR_DATE'] = env['GIT_COMMITTER_DATE'] = fields['Date']
        if fields.get('Author') and fields.get('Email'):
            env['GIT_AUTHOR_NAME'], env['GIT_AUTHOR_EMAIL'] = fields['Author'], fields['Email']
        git(directory, 'apply', '--index', str(patch.resolve()))
        git(directory, 'commit', '-F', str(message), env=env)


def export_commits(repo, targets, pins, branch, metadata):
    try:
        imported = json.loads(metadata.read_text())
    except (OSError, ValueError):
        imported = {}
    cache = imported.get('commits', {}) if imported.get('pins') == pins else {}
    output = {}
    for label, directory in targets.items():
        if git(directory, 'status', '--porcelain', '--untracked-files=all', '--ignore-submodules=all'):
            raise SystemExit(f'apply-engine-patches: commit {label} maintenance edits before --export')
        ref = 'refs/heads/' + branch
        git(directory, 'merge-base', '--is-ancestor', pins[label], ref)
        commits = git(directory, 'rev-list', '--reverse', pins[label] + '..' + ref, text=True).splitlines()
        for number, commit in enumerate(commits, 1):
            parents = git(directory, 'rev-list', '--parents', '-n', '1', commit, text=True).split()
            if len(parents) != 2:
                raise SystemExit('apply-engine-patches: maintenance histories must be linear (no merge commits)')
            mail = git(directory, 'format-patch', '--stdout', '--no-signature', '-1', commit)
            # Preserve legacy mail byte for byte for an unchanged imported
            # commit. New/amended/squashed commits use format-patch verbatim.
            if commit in cache:
                original = base64.b64decode(cache[commit]['mail'])
                mail = original
            subject = git(directory, 'show', '-s', '--format=%s', commit, text=True).strip()
            slug = re.sub(r'[^a-z0-9]+', '-', subject.lower()).strip('-')[:72].rstrip('-') or 'patch'
            prefix = '' if label == 'engine' else label + '-'
            output[f'{prefix}{number:04d}-{slug}.patch'] = mail
    directory = repo / 'patches/segagenesisrecomp'
    with tempfile.TemporaryDirectory(prefix='tg2-export-') as tmp:
        for name, mail in output.items():
            (Path(tmp) / name).write_bytes(mail)
        for name in sorted(output):
            temporary = directory / ('.' + name + '.tmp')
            temporary.write_bytes((Path(tmp) / name).read_bytes())
            temporary.replace(directory / name)
        for stale in directory.glob('*.patch'):
            if stale.name not in output:
                stale.unlink()
    print(f'apply-engine-patches: exported {len(output)} patches from local {branch} branches')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--reset', action='store_true', help='snapshot and rebuild the entire stack')
    mode.add_argument('--check', action='store_true', help='read-only stamp/tree validation')
    mode.add_argument('--as-commits', action='store_true', help='import one commit per patch on local maintenance branches')
    mode.add_argument('--export', action='store_true', help='export local maintenance branches and remove stale patch files')
    parser.add_argument('--branch', default='tg2/patches', help='local maintenance branch name (never pushed)')
    args = parser.parse_args()
    repo = args.repo.resolve()
    engine, ui = repo / 'segagenesisrecomp', repo / 'recomp-ui'
    core = engine / 'external/m68k-recomp-core'
    targets = dict(engine=engine, core=core, ui=ui)
    for label, directory in targets.items():
        if not (directory / '.git').exists():
            raise SystemExit(f'apply-engine-patches: {label} submodule is not initialized')
    pins = dict(engine=pin(repo, 'segagenesisrecomp'), ui=pin(repo, 'recomp-ui'))
    pins['core'] = git(engine, 'ls-tree', pins['engine'], 'external/m68k-recomp-core', text=True).split()[2]
    git(repo, 'check-ref-format', '--branch', args.branch)
    patches = sorted((repo / 'patches/segagenesisrecomp').glob('*.patch'))
    gitdir = Path(git(repo, 'rev-parse', '--absolute-git-dir', text=True).strip())
    metadata = gitdir / 'tg2-engine-patches-maintenance.json'
    if args.export:
        export_commits(repo, targets, pins, args.branch, metadata)
        return
    if args.as_commits:
        # Save mail before any repository mutation; parent pins never change.
        mails = [(p, p.read_bytes()) for p in patches]
        identity = public_identity(repo)
        preserve_targets(targets, identity)
        for label, directory in targets.items():
            existing = git(directory, 'for-each-ref', '--format=%(objectname)', 'refs/heads/' + args.branch, text=True).strip()
            if existing:
                keep = f'refs/keep/tg2-patches-{label}-branch-{time.time_ns()}'
                git(directory, 'update-ref', keep, existing)
                print(f'apply-engine-patches: preserved local {label} branch at {keep}')
        restore_pins(targets, pins, args.branch)
        imported = {}
        for patch, mail in mails:
            label = target_label(patch)
            commit_patch(targets[label], patch, mail, identity)
            imported[revision(targets[label])] = dict(name=patch.name, mail=base64.b64encode(mail).decode())
            print(f'apply-engine-patches: committed {label} {patch.name}')
        metadata.write_text(json.dumps(dict(version=1, pins=pins, branch=args.branch, commits=imported), indent=2) + '\n')
        return
    digest = hashlib.sha256()
    for patch in patches:
        digest.update(patch.name.encode() + b'\0')
        digest.update(patch.read_bytes())
    want = dict(version=2, stack=digest.hexdigest(), pins=pins,
                trees={label: tree_hash(path) for label, path in targets.items()})
    stamp = gitdir / 'tg2-engine-patches.stamp'
    try:
        previous = json.loads(stamp.read_text())
    except (OSError, ValueError):
        previous = None
    if not args.reset and previous == want:
        print('apply-engine-patches: stack already applied (stamp and trees match)')
        return
    if args.check:
        raise SystemExit('apply-engine-patches: stack/tree mismatch; run applicator to snapshot and rebuild')
    # Read the public identity only if a snapshot is needed; clean application
    # still works without any author configuration (Phase A fixture).
    dirty = any(git(path, 'status', '--porcelain', '--untracked-files=all') for path in targets.values())
    identity = public_identity(repo) if dirty else dict(os.environ)
    preserve_targets(targets, identity)
    restore_pins(targets, pins)
    for patch in patches:
        label = target_label(patch)
        git(targets[label], 'apply', str(patch))
        print(f'apply-engine-patches: applied {patch.name}')
    want['trees'] = {label: tree_hash(path) for label, path in targets.items()}
    temporary = stamp.with_suffix('.tmp')
    temporary.write_text(json.dumps(want, sort_keys=True) + '\n')
    temporary.replace(stamp)


if __name__ == '__main__':
    main()
