#!/usr/bin/env python3
"""Audit the road renderer's three MOVE.L table,D0; PUSH D0; RTS tables."""
from pathlib import Path
import argparse
from capstone import Cs, CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
r = a.rom.read_bytes()
md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
lines = ['# Road renderer RTS jump tables: raw-ROM producer + bounded leaf audit.', '[functions]', 'late_extra = [']
seen = set()
for start, end in ((0x7B08, 0x7B88), (0x7CE4, 0x7D64), (0x7E78, 0x7EF8)):
    assert r[start-8:start].hex() == '203b00062f004e75'
    lines.append(f'  # 32 absolute-long pointers at ${start:06X}..${end:06X}.')
    for pos in range(start, end, 4):
        target = int.from_bytes(r[pos:pos+4], 'big')
        assert end <= target < end + 0x100 and not target % 2
        first = next(md.disasm(r[target:target+16], target))
        assert first.mnemonic != 'dc.w'
        if target not in seen:
            lines.append(f'  0x{target:06X}, # pointer at ${pos:06X}')
            seen.add(target)
lines.append(']')
a.output.write_text('\n'.join(lines) + '\n')
