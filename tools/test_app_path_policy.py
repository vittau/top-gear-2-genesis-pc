#!/usr/bin/env python3
"""Run actual runner path selection with mocked platform/filesystem APIs.

All three platform branches compile/run on the host. This is path-policy
coverage, not a substitute for running packaged applications on each OS.
--runner can select an archived directory containing main.c and app_paths.h.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


PREAMBLE = r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#undef __APPLE__
#undef _WIN32
static const char *image, *appimage, *appdir;
static int writable;
static char s_exe_dir[1024], s_data_dir[1024];
static int s_rom_library;
static struct { const char *data_directory_name; } g_game_spec = {"TG2Recomp"};
static char *test_getenv(const char *key) {
 if (!strcmp(key,"HOME")) return "/Users/player";
 if (!strcmp(key,"APPIMAGE")) return (char *)appimage;
 if (!strcmp(key,"APPDIR")) return (char *)appdir;
 return NULL;
}
static ssize_t test_readlink(const char *p,char *out,size_t cap) {
 (void)p; size_t n=strlen(image); if(n>cap)n=cap; memcpy(out,image,n); return n;
}
static int test_ns_path(char *out,uint32_t *cap) {
 snprintf(out,*cap,"%s",image);return 0;
}
static char *test_realpath(const char *in,char *out) {strcpy(out,in);return out;}
static int test_access(const char *p,int mode) {(void)p;(void)mode;return writable?0:-1;}
static int test_mkdir(const char *p,int mode) {(void)p;(void)mode;return 0;}
static unsigned test_module(void *h,char *out,unsigned cap) {
 (void)h;snprintf(out,cap,"%s",image);return (unsigned)strlen(out);
}
#define getenv test_getenv
#define readlink test_readlink
#define _NSGetExecutablePath test_ns_path
#define realpath test_realpath
#define access test_access
#define mkdir test_mkdir
#define GetModuleFileNameA test_module
'''
DRIVER = r'''
int main(int argc,char **argv) {
 if(argc!=6)return 2;
 image=argv[1];appimage=argv[3];appdir=argv[4];writable=atoi(argv[5]);
 init_exe_dir(argv[2]);
#ifdef __APPLE__
 macos_bundle_paths();
#endif
 printf("%s|%s|%d\n",s_exe_dir,*s_data_dir?s_data_dir:s_exe_dir,s_rom_library);
 return 0;
}
'''
CASES = [
    ('mac-installed', 'apple', '/Applications/TG2Recomp.app/Contents/MacOS/TG2Recomp', '', '', '', 1,
     '/Applications/|/Users/player/Library/Application Support/TG2Recomp/|1'),
    ('mac-portable', 'apple', '/Games/TG2Recomp.app/Contents/MacOS/TG2Recomp', '', '', '', 1,
     '/Games/|/Games/|0'),
    ('mac-readonly', 'apple', '/Games/TG2Recomp.app/Contents/MacOS/TG2Recomp', '', '', '', 0,
     '/Games/|/Users/player/Library/Application Support/TG2Recomp/|1'),
    ('mac-loose', 'apple', '/Games/TG2Recomp', './TG2Recomp', '', '', 1, '/Games/|/Games/|0'),
    ('linux-loose', 'linux', '/games/TG2Recomp', './TG2Recomp', '', '', 1, '/games/|/games/|0'),
    ('linux-appimage', 'linux', '/tmp/.mount/usr/bin/TG2Recomp', '', '/games/TG2Recomp.AppImage', '/tmp/.mount', 1,
     '/games/|/games/|0'),
    ('linux-inherited-appimage', 'linux', '/games/TG2Recomp', '', '/other/Orca.AppImage', '/tmp/.other', 1,
     '/games/|/games/|0'),
    ('linux-argv-fallback', 'linux', '', '/fallback/TG2Recomp', '', '', 1, '/fallback/|/fallback/|0'),
    ('windows-loose', 'windows', r'C:\Games\TG2Recomp.exe', '', '', '', 1, 'C:\\Games\\|C:\\Games\\|0'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', type=Path, default=ROOT / 'segagenesisrecomp/runner')
    args = parser.parse_args()
    source = (args.runner / 'main.c').read_text()
    init = function(source, 'static void init_exe_dir(')
    mac = function(source, 'static void macos_bundle_paths(')
    outputs = {}
    with tempfile.TemporaryDirectory(prefix='genesis-path-policy-') as tmp:
        directory = Path(tmp)
        (directory / 'mach-o').mkdir()
        (directory / 'mach-o/dyld.h').write_text('/* Platform API mocked by the test. */\n')
        (directory / 'app_paths.h').write_bytes((args.runner / 'app_paths.h').read_bytes())
        for platform, define in [('apple', '__APPLE__'), ('linux', None), ('windows', '_WIN32')]:
            cfile = directory / (platform + '.c')
            cfile.write_text(PREAMBLE + (f'\n#define {define} 1\n' if define else '') +
                             '#define GENESIS_APP_PATHS_TEST 1\n#include "app_paths.h"\n' + init +
                             ('\n' + mac if platform == 'apple' else '') + DRIVER)
            exe = directory / platform
            subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-Wno-unused-function', '-Wno-unused-variable', '-Wno-unused-parameter',
                            '-I', str(directory), str(cfile), '-o', str(exe)], check=True)
            for name, target, image, argv0, appimage, appdir, writable, expected in CASES:
                if target != platform:
                    continue
                out = subprocess.check_output([str(exe), image, argv0, appimage, appdir, str(writable)],
                                              text=True, stderr=subprocess.DEVNULL).strip()
                assert out == expected, (name, out, expected)
                outputs[name] = out
    print(json.dumps(outputs, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
