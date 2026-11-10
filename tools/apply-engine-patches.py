#!/usr/bin/env python3
"""Portable twin of tools/apply-engine-patches.sh (used on Windows).

Applies numbered patches to segagenesisrecomp, core-* to its
external/m68k-recomp-core, and ui-* to recomp-ui, without changing any pin.
A shared shell/Python stamp hashes the stack and engine/UI revisions so a
second application is a no-op even when later patches rewrite earlier hunks.
Reverse checks still support partially applied trees. --check examines the
current tree only; it does not simulate dependent patches on a clean tree.

Usage: apply-engine-patches.py [--repo DIR] [--check]
"""
import argparse
import hashlib
from pathlib import Path
import os
import subprocess


def git(directory, *args):
    return subprocess.run(["git", "-C", directory, *args],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    parser.add_argument("--check", action="store_true",
                        help="check patches against the current tree (not a sequential-stack dry run)")
    args = parser.parse_args()
    args.repo = os.path.abspath(args.repo)

    patches_dir = os.path.join(args.repo, "patches", "segagenesisrecomp")
    engine = os.path.join(args.repo, "segagenesisrecomp")
    if not os.path.isdir(engine):
        raise SystemExit("apply-engine-patches: engine submodule is not initialized")
    patches = sorted(
        os.path.join(patches_dir, name)
        for name in os.listdir(patches_dir) if name.endswith(".patch")
    )

    ui = os.path.join(args.repo, "recomp-ui")
    if not os.path.isdir(ui):
        raise SystemExit("apply-engine-patches: UI submodule is not initialized")
    digest = hashlib.sha256()
    for patch in patches:
        with open(patch, "rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
    def revision(directory):
        return subprocess.check_output(["git", "-C", directory, "rev-parse", "HEAD"],
                                       text=True).strip()
    git_dir = subprocess.check_output(["git", "-C", args.repo, "rev-parse", "--git-dir"],
                                     text=True).strip()
    stamp = Path(git_dir)
    if not stamp.is_absolute():
        stamp = Path(args.repo) / stamp
    stamp /= "tg2-engine-patches.stamp"
    want = f"{digest.hexdigest()} {revision(engine)} {revision(ui)}\n"
    if stamp.exists() and stamp.read_text() == want:
        print("apply-engine-patches: stack already applied (stamp matches)")
        return

    for patch in patches:
        target = engine
        if os.path.basename(patch).startswith("core-"):
            target = os.path.join(engine, "external", "m68k-recomp-core")
        elif os.path.basename(patch).startswith("ui-"):
            target = ui
        if git(target, "apply", "--reverse", "--check", patch).returncode == 0:
            print(f"apply-engine-patches: already applied {os.path.basename(patch)}")
            continue
        if git(target, "apply", "--check", patch).returncode != 0:
            raise SystemExit(f"apply-engine-patches: patch does not apply: {patch}")
        if args.check:
            print(f"apply-engine-patches: would apply {os.path.basename(patch)}")
            continue
        result = git(target, "apply", patch)
        if result.returncode != 0:
            raise SystemExit(f"apply-engine-patches: failed to apply {patch}")
        print(f"apply-engine-patches: applied {os.path.basename(patch)}")

    if not args.check:
        stamp.write_bytes(want.encode("ascii"))


if __name__ == "__main__":
    main()
