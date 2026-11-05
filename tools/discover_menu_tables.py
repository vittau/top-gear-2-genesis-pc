#!/usr/bin/env python3
"""Audit TG2 two-level state dispatch leaves; emit only callable addresses."""
import argparse
from pathlib import Path
from capstone import Cs, CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
r = a.rom.read_bytes()
md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
# Proven by raw-ROM producer pairs (MOVEA PC-indexed, then MOVEA An-indexed,
# JMP (a0)) and by the first code instruction after each contiguous table.
tables = [(0x1ED68, 0x1ED98, 0x1EE34), (0x219B6, 0x219DE, 0x21A4A)]
lines = ['# Two-level menu state tables, raw-ROM audited by discover_menu_tables.py.', '[functions]', 'late_extra = [']
seen = set()
for producer, start, end in tables:
    ins = list(md.disasm(r[producer:producer+20], producer))
    assert ins[-1].mnemonic == 'jmp' and ins[-1].op_str == '(a0)'
    lines.append(f'  # Leaf table ${start:06X}..${end:06X}, dispatcher ${producer:06X}.')
    for pc in range(start, end, 4):
        target = int.from_bytes(r[pc:pc+4], 'big')
        assert target % 2 == 0 and 0x200 <= target < len(r)
        first = next(md.disasm(r[target:target+16], target))
        assert first.mnemonic != 'dc.w'
        if target not in seen:
            lines.append(f'  0x{target:06X}, # pointer at ${pc:06X}')
            seen.add(target)
lines.append(']')
a.output.write_text('\n'.join(lines) + '\n')
