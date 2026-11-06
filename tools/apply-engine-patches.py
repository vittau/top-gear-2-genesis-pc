#!/usr/bin/env python3
"""Portable twin of tools/apply-engine-patches.sh (used on Windows).

Applies every patches/segagenesisrecomp/*.patch to the engine submodule (or to
external/m68k-recomp-core for core-* patches) without committing anything, and
without touching the upstream submodule pin. Re-running is a no-op: a patch
that already applies in reverse is considered applied.

Usage: apply-engine-patches.py [--repo DIR] [--check]
"""
import argparse
import os
import subprocess
import sys


def git(directory, *args):
    return subprocess.run(["git", "-C", directory, *args],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    parser.add_argument("--check", action="store_true",
                        help="only report whether every patch applies")
    args = parser.parse_args()

    patches_dir = os.path.join(args.repo, "patches", "segagenesisrecomp")
    engine = os.path.join(args.repo, "segagenesisrecomp")
    if not os.path.isdir(engine):
        raise SystemExit("apply-engine-patches: engine submodule is not initialized")
    patches = sorted(
        os.path.join(patches_dir, name)
        for name in os.listdir(patches_dir) if name.endswith(".patch")
    )

    for patch in patches:
        target = engine
        if os.path.basename(patch).startswith("core-"):
            target = os.path.join(engine, "external", "m68k-recomp-core")
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


if __name__ == "__main__":
    main()
