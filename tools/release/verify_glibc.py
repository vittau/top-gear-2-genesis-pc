#!/usr/bin/env python3
"""Prove a Linux release binary needs no glibc newer than a given version.

Prints the highest GLIBC_* symbol version the dynamic loader requirements
reference (and the highest GLIBCXX_* if libstdc++ stayed dynamic), then fails
if it is above the limit. SteamOS 3.x ships glibc 2.35 or newer, so release
Linux builds are qualified against 2.35.

Usage:
    verify_glibc.py --binary PATH [--max 2.35] [--show-ldd]
"""
import argparse
import re
import subprocess
import sys

VERSION = re.compile(r"(GLIBC|GLIBCXX|CXXABI)_(\d+)\.(\d+)(?:\.(\d+))?")


def version_tuple(match):
    return tuple(int(match.group(index)) for index in (2, 3) if match.group(index))


def printable(version):
    return ".".join(str(part) for part in version)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--max", default="2.35")
    parser.add_argument("--show-ldd", action="store_true")
    args = parser.parse_args()

    limit = tuple(int(part) for part in args.max.split("."))
    output = subprocess.run(
        ["objdump", "-T", args.binary],
        check=True, stdout=subprocess.PIPE, text=True,
    ).stdout

    found = {}
    for match in VERSION.finditer(output):
        family = match.group(1)
        version = version_tuple(match)
        if family not in found or version > found[family]:
            found[family] = version

    if not found:
        raise SystemExit("verify-glibc: no GLIBC symbol versions found; not an ELF binary?")

    for family in sorted(found):
        print(f"verify-glibc: highest {family} symbol version: {printable(found[family])}")

    glibc = found.get("GLIBC")
    if glibc is None:
        raise SystemExit("verify-glibc: binary has no GLIBC symbol requirements")
    if glibc > limit:
        raise SystemExit(
            f"verify-glibc: FAIL requires GLIBC {printable(glibc)}, limit is {args.max}"
        )

    if args.show_ldd:
        ldd = subprocess.run(["ldd", args.binary], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
        print(ldd.stdout.rstrip())
        missing = [line.strip() for line in ldd.stdout.splitlines() if "not found" in line]
        if missing:
            raise SystemExit(
                "verify-glibc: FAIL missing shared libraries: " + "; ".join(missing)
            )

    print(f"verify-glibc: PASS obeys glibc <= {args.max} (needs {printable(glibc)})")


if __name__ == "__main__":
    main()
