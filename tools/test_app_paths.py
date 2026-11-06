#!/usr/bin/env python3
"""Compile/run the macOS bundle path helpers without macOS.

The string part of runner/app_paths.h is platform independent; compiling it
with GENESIS_APP_PATHS_TEST checks the bundle-root/parent rules on any host, so
the CI Linux runner can prove the layout the macOS job relies on.

Usage: python3 tools/test_app_paths.py
"""
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SOURCE = r'''
#include "app_paths.h"

static int check(const char *exe_dir, int expect_bundle, const char *expect_parent)
{
    char root[1024];
    char parent[1024];
    int is_bundle = genesis_macos_bundle_root(exe_dir, root, sizeof root);
    if (is_bundle != expect_bundle) {
        fprintf(stderr, "bundle(%s): got %d expected %d\n", exe_dir, is_bundle, expect_bundle);
        return 1;
    }
    if (!expect_bundle) return 0;
    if (!genesis_macos_bundle_parent(exe_dir, parent, sizeof parent)) {
        fprintf(stderr, "parent(%s): no parent\n", exe_dir);
        return 1;
    }
    if (strcmp(parent, expect_parent) != 0) {
        fprintf(stderr, "parent(%s): got '%s' expected '%s'\n", exe_dir, parent, expect_parent);
        return 1;
    }
    return 0;
}

int main(void)
{
    int failures = 0;
    failures += check("/Applications/TG2Recomp.app/Contents/MacOS/", 1, "/Applications/");
    failures += check("/Applications/TG2Recomp.app/Contents/MacOS", 1, "/Applications/");
    failures += check("/home/u/Games/TG2Recomp.app/Contents/MacOS/", 1, "/home/u/Games/");
    failures += check("/X.app/Contents/MacOS/", 1, "/");
    failures += check("TG2Recomp.app/Contents/MacOS/", 1, "./");
    failures += check("/home/u/Games/", 0, NULL);
    failures += check("/home/u/Games/Contents/MacOS/", 0, NULL);
    failures += check("/home/u/Games/Other.app/Contents/Resources/", 0, NULL);
    if (failures) return 1;
    puts("app paths: 8 cases passed");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix="tg2-app-paths-") as tmp:
        directory = Path(tmp)
        source = directory / "check.c"
        source.write_text(SOURCE)
        executable = directory / "check"
        subprocess.run(
            [os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-DGENESIS_APP_PATHS_TEST",
             "-I", str(ROOT / "segagenesisrecomp/runner"),
             str(source), "-o", str(executable)],
            check=True,
        )
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout.strip())


if __name__ == "__main__":
    main()
