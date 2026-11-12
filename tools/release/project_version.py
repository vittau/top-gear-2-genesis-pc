#!/usr/bin/env python3
"""Read the release version from the CMake project declaration."""
from pathlib import Path
import re


def project_version():
    cmake = Path(__file__).resolve().parents[2] / 'CMakeLists.txt'
    match = re.search(r'project\(TopGear2Recomp\s+VERSION\s+([0-9]+\.[0-9]+\.[0-9]+)\s', cmake.read_text())
    if not match:
        raise ValueError(f'No TopGear2Recomp project version in {cmake}')
    return match.group(1)


if __name__ == '__main__':
    print(project_version())
