#!/usr/bin/env python3
"""Compile/run content-discovery checks without a private ROM or GUI."""
from pathlib import Path
import os
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='tg2-rom-detect-') as tmp:
    d = Path(tmp)
    source = d / 'check.c'
    source.write_text('''#include "rom_autodetect.h"
int main(int argc, char **argv) {
    char path[2048];
    if (argc != 2) return 2;
    if (!genesis_find_rom_in_directory(argv[1], 0xCBF43926u, 9, path, sizeof path)) return 1;
    puts(path);
    return 0;
}
''')
    exe = d / 'check'
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
        '-I', str(ROOT / 'segagenesisrecomp/runner'), str(source), '-o', str(exe)], check=True)
    cases = d / 'cases'
    cases.mkdir()
    (cases / 'wrong.bin').write_bytes(b'000000000')
    (cases / 'long.md').write_bytes(b'1234567890')
    (cases / 'directory.gen').mkdir()
    os.mkfifo(cases / 'pipe.bin')
    assert subprocess.run([str(exe), str(cases)], timeout=5).returncode == 1
    for name in ('odd name.without-extension', 'cartridge.md', 'UPPER.GEN', 'tg2.bin'):
        match = cases / name
        match.write_bytes(b'123456789')
        result = subprocess.run([str(exe), str(cases)], capture_output=True, text=True, timeout=5)
        assert result.returncode == 0 and result.stdout.strip() == str(match), result
        match.unlink()
    assert subprocess.run([str(exe), str(d / 'absent')], timeout=5).returncode == 1
print('content discovery: 6 cases passed (extensions, CRC/size, directories, FIFO, absent directory)')
