#!/usr/bin/env python3
"""Regression: BOTH must not disturb the resident music driver's Z80 image.

The cartridge uploads its 8 KB Z80 music driver (ROM $02589A..$027899) to
$A00000 at boot.  In BOTH mode the 68K SFX engine's sample-command ports
($A0025E..$A00261) are routed to the second Z80 core, and those offsets are
also part of the driver's note -> octave (block) table at Z80 $0227 - entries
$37..$3A, the four semitones G..A# of octave 4.  An unconditional route put
zeros there in every session where BOTH was already live at the upload
(persisted `[mods.racesound] mode = both`, i.e. the owner's settings), and
those four note indices then played four octaves low: "some instruments
sometimes seem to be missing" (docs/AUDIO.md section 5, task 37).

This boots the three RACE SOUND modes from clean runtime directories and
requires, at a fixed frame:

  * BOTH's first-core driver image to match MUSIC's byte for byte outside the
    driver's own work variables, in particular $25E..$261 == ROM $20 x4;
  * the second core's RAM to be empty at boot (nothing was diverted there);
  * the resident image to be the music driver (`F3 31 F0 1F C3 42`).

  python3 tools/verify_both_driver_image.py --exe build/TG2Recomp

Exit code 0 = pass, 1 = regression.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / 'build' / 'TG2Recomp'
DEFAULT_ROM = Path.home() / 'roms/genesis/tg2.bin'
DRIVER_ROM = 0x2589A
DRIVER_LEN = 0x2000
TABLE = 0x227            # note -> octave (block << 3), 8 octaves x 12 semitones
PORT_BYTES = (0x25E, 0x261)
# offsetof(GenesisBus, z80_sfx_ram): z80_ram (0x2000) + z80_bank (4) +
# bank_shift (4) + z80_busreq/z80_reset_off/z80_reset_pending (3).
SFX_RAM_DELTA = 0x200B
STUB = bytes.fromhex('F331F01FC342')      # music driver reset entry


def read_z80(r, addr: int, n: int) -> bytes:
    out = b''
    while n > 0:
        k = min(n, 4096)
        out += bytes.fromhex(r.command('read_z80_ram', addr=addr, len=k)['data'])
        addr += k
        n -= k
    return out


def boot(exe: Path, rom: Path, mode: str, frames: int, work: Path, port: int):
    d = work / mode
    d.mkdir(parents=True, exist_ok=True)
    local = d / exe.name
    shutil.copy2(exe, local)
    (d / 'settings.ini').write_text(f'[mods.racesound]\nmode = {mode}\n')
    from tg2_runner import Runner
    with Runner(port=port, out=d / 'evidence', exe=local, rom=rom,
                max_frames=frames + 300) as r:
        r.wait_frame(frames)
        ram = read_z80(r, 0, DRIVER_LEN)
        r.command('save_state', path=str(d / 'state.bin'))
    blob = (d / 'state.bin').read_bytes()
    pos = blob.find(STUB)
    sfx = b''
    if pos >= 0 and pos + SFX_RAM_DELTA + DRIVER_LEN <= len(blob):
        sfx = blob[pos + SFX_RAM_DELTA:pos + SFX_RAM_DELTA + DRIVER_LEN]
    return ram, sfx, pos


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--exe', type=Path, default=DEFAULT_EXE)
    p.add_argument('--rom', type=Path, default=DEFAULT_ROM)
    p.add_argument('--frames', type=int, default=400)
    p.add_argument('--out', type=Path, default=ROOT / 'build/both-driver-image')
    p.add_argument('--port', type=int, default=4555)
    a = p.parse_args()
    a.out = a.out.resolve()
    if a.out.exists():
        shutil.rmtree(a.out)
    a.out.mkdir(parents=True)

    image = a.rom.read_bytes()[DRIVER_ROM:DRIVER_ROM + DRIVER_LEN]
    fails = []
    results = {}
    for i, mode in enumerate(('both', 'music', 'sfx')):
        ram, sfx, pos = boot(a.exe, a.rom, mode, a.frames, a.out, a.port + i)
        results[mode] = (ram, sfx)
        table = ram[TABLE:TABLE + 0x60]
        print(f'== {mode}: stub={ram[0:6].hex(" ").upper()} '
              f'machine_image_offset={pos if pos >= 0 else "not found"}', flush=True)
        print(f'   $25E..$261 = {ram[0x25E:0x262].hex(" ").upper()} '
              f'(ROM {image[0x25E:0x262].hex(" ").upper()})')
        print(f'   octave table oct4 = '
              f'{table[4 * 12:5 * 12].hex(" ").upper()}')
        print(f'   whole-image diffs vs ROM = '
              f'{sum(1 for i in range(DRIVER_LEN) if ram[i] != image[i])}')
        print(f'   second-core RAM non-zero bytes = {sum(1 for b in sfx if b)}')
        if ram[:6] != STUB:
            fails.append(f'{mode}: resident image is not the music driver')
        if ram[0x25E:0x262] != image[0x25E:0x262]:
            fails.append(f'{mode}: $25E..$261 != ROM '
                         f'({ram[0x25E:0x262].hex()} vs {image[0x25E:0x262].hex()})')
        if table[4 * 12:5 * 12] != image[TABLE + 4 * 12:TABLE + 5 * 12]:
            fails.append(f'{mode}: octave-4 table row differs from ROM')

    both = results['both'][0]
    music = results['music'][0]
    tb = [i for i in range(DRIVER_LEN) if both[i] != music[i]]
    print(f'== BOTH vs MUSIC whole image: {len(tb)} byte(s) differ'
          + (' -> ' + ' '.join(f'{i:03X}' for i in tb[:8]) if tb else ''))
    if any(TABLE <= i < TABLE + 0x60 for i in tb):
        fails.append('BOTH differs from MUSIC inside the driver note/octave table')
    if sum(1 for b in results['both'][1] if b):
        fails.append('BOTH diverted bytes into the second core before a race')

    print()
    if fails:
        for f in fails:
            print('FAIL:', f)
        return 1
    print('PASS: BOTH keeps the music driver image intact and the second core '
          'empty until a race uploads its own image.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
