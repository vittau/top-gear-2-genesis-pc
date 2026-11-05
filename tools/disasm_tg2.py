#!/usr/bin/env python3
"""Raw stock-ROM 68000 disassembly; pip install capstone in a local venv."""
import argparse
from pathlib import Path
from capstone import Cs, CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('address', type=lambda s: int(s, 0))
p.add_argument('--size', type=lambda s: int(s, 0), default=0x100)
p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
a = p.parse_args()
data = a.rom.read_bytes()
md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
for ins in md.disasm(data[a.address:a.address + a.size], a.address):
    print(f'{ins.address:06X}: {ins.bytes.hex():20s} {ins.mnemonic:10s} {ins.op_str}')
