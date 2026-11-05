#!/usr/bin/env python3
"""Gate a staged release payload: no ROM, no generated C, no debug output.

Adapted from RocketKnightAdventuresRecomp/tools/verify_release.py. This is the
independent check that runs after staging (and again in the job that downloads
the uploaded artifact), so a packaging mistake cannot silently publish game
data or build products.

Fails when the payload contains:
  * any file whose SHA-256 equals the private ROM's,
  * a .bin/.md/.gen/.smd/.smc file larger than 512 KiB (ROM-like data),
  * a generated/ directory, or a GenesisRecomp (recompiler) binary,
  * save states, RAM/VRAM dumps, settings, ROM bookkeeping or logs,
  * absolute symlinks or symlinks escaping the payload.

Usage:
    verify_artifact.py --dir DIR [--require FILE ...] [--max-total-mb N]
"""
import argparse
import hashlib
import os
import sys

DEFAULT_ROM_SHA256 = "b41909d53090e28c1d1e50941dad01676dd3d19caf26c75f66aac6a3ad689ba6"
ROM_LIKE_EXTENSIONS = {".bin", ".md", ".gen", ".smd", ".smc"}
ROM_LIKE_MAX_BYTES = 512 * 1024
FORBIDDEN_NAMES = {
    "settings.ini",
    "rom.cfg",
    "debug.ini",
    "genesis-netplay-room.txt",
}
FORBIDDEN_PREFIXES = ("dispatch_misses", "floor_coverage", "interior_label_misses", "floor_unsafe")
FORBIDDEN_SUFFIXES = (
    ".srm", ".ram", ".vram", ".log", ".pdb", ".map", ".sav", ".wav",
    ".state", ".rzs", ".replay", ".unresolved_jumptables.log",
)
RECOMPILER_NAMES = {"genesisrecomp", "genesisrecomp.exe"}


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True)
    parser.add_argument("--rom-sha256", default=DEFAULT_ROM_SHA256)
    parser.add_argument("--require", action="append", default=[],
                        help="payload-relative file or directory that must exist")
    parser.add_argument("--max-total-mb", type=int, default=256)
    args = parser.parse_args()

    root = os.path.realpath(args.dir)
    if not os.path.isdir(root):
        raise SystemExit(f"verify: not a directory: {args.dir}")

    problems = []
    total = 0
    files = 0
    for current, directories, names in os.walk(root):
        relative_dir = os.path.relpath(current, root)
        if relative_dir != ".":
            if os.path.basename(current) == "generated":
                problems.append(f"generated C directory present: {relative_dir}")
        for name in sorted(names):
            path = os.path.join(current, name)
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            if os.path.islink(path):
                target = os.path.realpath(path)
                if os.path.isabs(os.readlink(path)) or not target.startswith(root + os.sep):
                    problems.append(f"symlink escapes payload: {relative}")
                    continue
            if not os.path.isfile(path):
                continue
            files += 1
            size = os.path.getsize(path)
            total += size
            lowered = name.lower()
            stem = os.path.splitext(lowered)[0]
            if lowered in RECOMPILER_NAMES:
                problems.append(f"recompiler binary present: {relative}")
            if lowered in FORBIDDEN_NAMES or stem in FORBIDDEN_NAMES:
                problems.append(f"runtime/debug file present: {relative}")
            if stem.startswith(FORBIDDEN_PREFIXES):
                problems.append(f"runtime diagnostic present: {relative}")
            if lowered.endswith(FORBIDDEN_SUFFIXES):
                problems.append(f"forbidden file type: {relative}")
            extension = os.path.splitext(lowered)[1]
            if extension in ROM_LIKE_EXTENSIONS and size > ROM_LIKE_MAX_BYTES:
                problems.append(f"ROM-like file over 512 KiB: {relative} ({size} bytes)")
            if size > 0 and sha256_file(path) == args.rom_sha256:
                problems.append(f"private ROM present: {relative}")

    for required in args.require:
        if not os.path.exists(os.path.join(root, required)):
            problems.append(f"required payload entry missing: {required}")

    if total > args.max_total_mb * 1024 * 1024:
        problems.append(f"payload is {total} bytes, over {args.max_total_mb} MiB")

    print(f"verify: {files} files, {total} bytes under {root}")
    if problems:
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        raise SystemExit(1)
    print("verify: PASS (no ROM, generated C, recompiler or debug output)")


if __name__ == "__main__":
    main()
