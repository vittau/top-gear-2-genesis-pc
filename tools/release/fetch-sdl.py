#!/usr/bin/env python3
"""Fetch, verify and unpack the pinned SDL2 source used by release builds.

TG2 release payloads link SDL2 statically, so every platform builds the same
pinned SDL2 release from source instead of depending on a host package. The
tarball SHA-256 is checked before extraction; the caller may cache the tarball
out of tree (the cache never contains ROMs, generated C or build output).

Usage:
    fetch-sdl.py [--version 2.28.5] [--dest DIR] [--cache DIR]

Prints the extracted source directory (the tree to pass as TG2_SDL_SOURCE).
"""
import argparse
import hashlib
import os
import sys
import tarfile
import urllib.request

# version -> (sha256 of the official libsdl-org release tarball)
PINNED = {
    "2.28.5": "332cb37d0be20cb9541739c61f79bae5a477427d79ae85e352089afdaf6666e4",
}
URL = "https://github.com/libsdl-org/SDL/releases/download/release-{v}/SDL2-{v}.tar.gz"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, dest):
    last_error = None
    for attempt in range(3):
        try:
            print(f"fetch-sdl: downloading {url} (attempt {attempt + 1})", file=sys.stderr)
            urllib.request.urlretrieve(url, dest)
            return
        except Exception as error:  # noqa: BLE001 - report and retry
            last_error = error
    raise SystemExit(f"fetch-sdl: download failed: {last_error}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="2.28.5")
    parser.add_argument("--dest", required=True, help="directory that receives SDL2-<version>")
    parser.add_argument("--cache", help="directory that keeps the verified tarball")
    args = parser.parse_args()

    if args.version not in PINNED:
        raise SystemExit(
            f"fetch-sdl: SDL2 {args.version} is not pinned; add its sha256 to PINNED first"
        )
    expected = PINNED[args.version]
    source = os.path.join(args.dest, f"SDL2-{args.version}")
    if os.path.isfile(os.path.join(source, "CMakeLists.txt")):
        print(source)
        return

    os.makedirs(args.dest, exist_ok=True)
    cache = args.cache or args.dest
    os.makedirs(cache, exist_ok=True)
    tarball = os.path.join(cache, f"SDL2-{args.version}.tar.gz")

    if not os.path.isfile(tarball) or sha256_file(tarball) != expected:
        temporary = tarball + ".part"
        download(URL.format(v=args.version), temporary)
        actual = sha256_file(temporary)
        if actual != expected:
            os.unlink(temporary)
            raise SystemExit(
                f"fetch-sdl: SHA-256 mismatch for SDL2 {args.version}: "
                f"expected {expected}, got {actual}"
            )
        os.replace(temporary, tarball)

    print(f"fetch-sdl: verified {tarball} ({expected})", file=sys.stderr)
    with tarfile.open(tarball, "r:gz") as archive:
        # Refuse absolute or parent-relative members before writing anything.
        for member in archive.getmembers():
            target = os.path.normpath(os.path.join(args.dest, member.name))
            if not target.startswith(os.path.normpath(args.dest) + os.sep):
                raise SystemExit(f"fetch-sdl: unsafe archive member {member.name}")
        try:
            archive.extractall(args.dest, filter="data")  # Python 3.12+
        except TypeError:
            archive.extractall(args.dest)
    if not os.path.isfile(os.path.join(source, "CMakeLists.txt")):
        raise SystemExit(f"fetch-sdl: extraction produced no SDL2 source tree in {source}")
    print(source)


if __name__ == "__main__":
    main()
