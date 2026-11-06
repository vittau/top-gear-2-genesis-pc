#!/usr/bin/env python3
"""Assemble the draft-release payload from the three build artifacts.

Input is the layout actions/download-artifact produces: one directory per
artifact name. The script:

  * extracts the Linux tarball and the AppImage (no FUSE needed) and runs
    tools/release/verify_artifact.py on both,
  * verifies the macOS .app zip and the staged Windows folder the same way,
  * zips the Windows folder as TG2Recomp-windows-x64.zip,
  * copies the four user-facing deliverables into the output directory and
    writes SHA256SUMS.

Nothing is published here; the release workflow only calls the GitHub API
after this script succeeds. A dry run stops after printing the listing.

Usage:
    assemble_release.py --artifacts DIR --out DIR --tag v0.1.0
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VERIFY = os.path.join(REPO, "tools", "release", "verify_artifact.py")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(directory, *requires):
    command = [sys.executable, VERIFY, "--dir", directory]
    for item in requires:
        command += ["--require", item]
    subprocess.run(command, check=True)


def artifact(artifacts, name):
    path = os.path.join(artifacts, name)
    if not os.path.isdir(path):
        raise SystemExit(f"assemble: missing artifact directory {path}")
    return path


def find_one(directory, filename):
    path = os.path.join(directory, filename)
    if not os.path.isfile(path):
        raise SystemExit(f"assemble: missing {filename} in {directory}")
    return path


def zip_directory(source, destination, root_name):
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for current, _, names in os.walk(source):
            for name in sorted(names):
                full = os.path.join(current, name)
                relative = os.path.relpath(full, source)
                archive.write(full, os.path.join(root_name, relative))


def check_linux(artifacts, work):
    directory = artifact(artifacts, "TG2Recomp-linux-x86_64")
    tarball = find_one(directory, "TG2Recomp-linux-x86_64.tar.gz")
    appimage = find_one(directory, "TG2Recomp-x86_64.AppImage")

    tarball_root = os.path.join(work, "tarball")
    os.makedirs(tarball_root)
    with tarfile.open(tarball, "r:gz") as archive:
        archive.extractall(tarball_root, filter="data")
    verify(os.path.join(tarball_root, "TG2Recomp-linux-x86_64"),
           "TG2Recomp", "assets", "licenses", "README.txt")

    appimage_root = os.path.join(work, "appimage")
    os.makedirs(appimage_root)
    os.chmod(appimage, 0o755)
    subprocess.run([appimage, "--appimage-extract"], cwd=appimage_root,
                   check=True, stdout=subprocess.DEVNULL)
    verify(os.path.join(appimage_root, "squashfs-root"),
           "usr/bin/TG2Recomp", "usr/bin/assets", "usr/bin/licenses",
           "usr/bin/README.txt")
    return {"TG2Recomp-linux-x86_64.tar.gz": tarball,
            "TG2Recomp-x86_64.AppImage": appimage}


def check_macos(artifacts, out, work):
    directory = artifact(artifacts, "TG2Recomp-macos")
    archive_path = os.path.join(directory, "TG2Recomp-macos.zip")
    if os.path.isfile(archive_path):
        extracted = os.path.join(work, "macos")
        os.makedirs(extracted)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extracted)
        verify(extracted, "README.txt", "TG2Recomp.app/Contents/Info.plist",
               "TG2Recomp.app/Contents/MacOS/TG2Recomp")
        return {"TG2Recomp-macos.zip": archive_path}

    # Fallback for an older artifact layout: zip the staged bundle ourselves.
    staged = os.path.join(directory, "TG2Recomp-macos")
    verify(staged, "README.txt", "TG2Recomp.app/Contents/MacOS/TG2Recomp")
    destination = os.path.join(out, "TG2Recomp-macos.zip")
    zip_directory(staged, destination, ".")
    return {"TG2Recomp-macos.zip": destination}


def check_windows(artifacts, out):
    directory = artifact(artifacts, "TG2Recomp-windows-x64")
    # upload-artifact stores the contents of the uploaded directory, so the
    # executable is either at the artifact root or one folder down.
    root = directory
    if not os.path.isfile(os.path.join(root, "TG2Recomp.exe")):
        root = os.path.join(directory, "TG2Recomp-windows-x64")
    verify(root, "TG2Recomp.exe", "assets", "licenses", "README.txt")
    destination = os.path.join(out, "TG2Recomp-windows-x64.zip")
    zip_directory(root, destination, "TG2Recomp-windows-x64")
    return {"TG2Recomp-windows-x64.zip": destination}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    artifacts = os.path.abspath(args.artifacts)
    out = os.path.abspath(args.out)
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    work = tempfile.mkdtemp(prefix="tg2-release-")
    try:
        payload = {}
        payload.update(check_linux(artifacts, work))
        payload.update(check_windows(artifacts, out))
        payload.update(check_macos(artifacts, out, work))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for name, source in sorted(payload.items()):
        if os.path.abspath(source) != os.path.join(out, name):
            shutil.copy2(source, os.path.join(out, name))

    lines = []
    print(f"release payload for {args.tag} ({out})")
    for name in sorted(payload):
        path = os.path.join(out, name)
        digest = sha256_file(path)
        size = os.path.getsize(path)
        lines.append(f"{digest}  {name}")
        print(f"  {name:<34} {size:>12} bytes  {digest}")
    with open(os.path.join(out, "SHA256SUMS"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"  {'SHA256SUMS':<34} {os.path.getsize(os.path.join(out, 'SHA256SUMS')):>12} bytes")
    print(f"assemble: {len(payload)} deliverables + SHA256SUMS ready")


if __name__ == "__main__":
    main()
