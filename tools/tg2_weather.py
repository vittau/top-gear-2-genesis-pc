#!/usr/bin/env python3
"""List stock-USA precipitation tracks and screen-spelled country passwords.

A password resumes at slot 1 of its country, not directly at a later race.
"""
import argparse
import json
from pathlib import Path
import zlib
import tg2_password as pw
from tg2_qual_coverage import COUNTRIES, NAMES


def races(rom):
    data = Path(rom).read_bytes()
    if zlib.crc32(data) != 0xBD3074D2:
        raise ValueError('expected the Top Gear 2 USA ROM (CRC32 BD3074D2)')
    rows = []
    for index in range(64):
        address = int.from_bytes(data[0x1B8E8 + index*4:0x1B8EC + index*4], 'big')
        flags = data[address + 3]
        country, slot = divmod(index, 4)
        rows.append(dict(index=index, country=country, country_name=COUNTRIES[country],
                         slot=slot+1, track=NAMES[country, slot],
                         descriptor=f'0x{address:06X}', flags=f'0x{flags:02X}',
                         precipitation=('snow' if flags & 0x40 else 'rain') if flags & 0x20 else 'none',
                         password=pw.spaced(pw.max_upgrades(country)['symbols']),
                         password_start_index=country*4))
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, default=Path.home()/'roms/genesis/tg2.bin')
    p.add_argument('--all', action='store_true')
    p.add_argument('--json', action='store_true')
    a = p.parse_args()
    rows = [r for r in races(a.rom) if a.all or r['precipitation'] != 'none']
    if a.json:
        print(json.dumps(rows, indent=2))
        return
    print('Enter via CONTINUE → PASSWORDS; each password starts at country slot 1.')
    print('Later slots require championship progression; the password has no race-slot field.\n')
    print('| Index | Country / track | Slot | Weather | Flags | Max-parts/max-money password |')
    print('|---:|---|---:|---|---|---|')
    for r in rows:
        print(f"| {r['index']} | {r['country_name']} / {r['track']} | {r['slot']} | {r['precipitation']} | `{r['flags']}` | `{r['password']}` |")


if __name__ == '__main__':
    main()
