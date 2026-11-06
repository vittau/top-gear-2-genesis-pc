#!/usr/bin/env python3
"""Top Gear 2 (Genesis) password codec — reversed from the stock ROM.

The ENTER PASSWORD screen stores 16 symbols. Each symbol is a 5-bit value
salted with a fixed key string;

    v[i] = (code[i] - 1 - KEY[i]) & 0x1F

and the 16 values concatenate big-endian into an 80-bit block (symbol 0 is
the most significant 5 bits). That block is then un-permuted bit by bit with
a stock 80-entry table into a 10-byte plaintext record, which unpacks into
the game-state fields listed in FIELDS. FIELDS['sum'] is an 8-bit additive
checksum over every other field.

Everything here was verified against the running game: the ROM's own
prefilled password decodes to a valid record (checksum matches) and is
accepted through the UI, and generated passwords start real races.

    python3 tools/tg2_password.py decode "KUC2 2HQG CJL2 Y4%T"
    python3 tools/tg2_password.py encode --field country=1
    python3 tools/tg2_password.py tables
"""
from __future__ import annotations

import argparse
import json
import sys

# The 32 password symbols in keyboard order (left-to-right, top-to-bottom).
# The keyboard's control keys (arrows, DEL, END) are not part of the alphabet.
ALPHABET = 'BCDFGHJKLNPQSTUYZ123456789[]?\\#%'
assert len(ALPHABET) == 32

# Salt string at ROM $0239B2, applied one byte per symbol.
KEY = b'gnarreKdaehrotoM'
assert len(KEY) == 16

# Bit permutation at ROM $0239C2: plaintext bit i comes from ciphertext bit
# PERM[i], both numbered most-significant-bit first inside the 10-byte block.
PERM = (
    0x44, 0x25, 0x1C, 0x3F, 0x4A, 0x0C, 0x31, 0x37,
    0x05, 0x01, 0x09, 0x0D, 0x34, 0x1A, 0x08, 0x0B,
    0x07, 0x0E, 0x47, 0x02, 0x29, 0x11, 0x17, 0x10,
    0x18, 0x15, 0x4E, 0x00, 0x19, 0x0A, 0x1B, 0x48,
    0x0F, 0x14, 0x1E, 0x12, 0x1F, 0x3E, 0x20, 0x22,
    0x16, 0x24, 0x49, 0x21, 0x03, 0x26, 0x2E, 0x23,
    0x2A, 0x28, 0x4F, 0x2C, 0x35, 0x2F, 0x04, 0x2D,
    0x36, 0x32, 0x40, 0x38, 0x4D, 0x45, 0x3B, 0x4C,
    0x30, 0x3A, 0x3D, 0x33, 0x41, 0x3C, 0x06, 0x46,
    0x2B, 0x4B, 0x43, 0x42, 0x1D, 0x13, 0x39, 0x27,
)

# Field layout of the decoded 10-byte record, from the unpacker at $02371A
# and the packer at $0235C6. (name, bit offset in the plaintext MSB-first
# bit stream, width).  'sum' is the trailing checksum: its low 7 bits are at
# stream bits 0..6 (byte 0 bits 7..1) and bit 7 is byte 9 bit 0 (stream bit
# 79). Stream bits 72..78 are unused.
FIELDS = (
    ('flag',     7, 1),   # $2a
    ('country',  8, 4),   # $28
    ('stage',   12, 2),   # $2c  (validator rejects > 2)
    ('money',   14, 10),  # $2e
    ('field30', 24, 10),  # $30
    ('u32',     34, 2),
    ('u34',     36, 2),
    ('u36',     38, 2),
    ('u38',     40, 2),
    ('u3a',     42, 2),
    ('u3c',     44, 2),
    ('u3e',     46, 2),
    ('u40',     48, 2),
    ('u42',     50, 2),
    ('u44',     52, 2),
    ('u46',     54, 2),
    ('u48',     56, 2),
    ('u4a',     58, 2),
    ('u4c',     60, 2),
    ('u4e',     62, 2),
    ('u50',     64, 2),
    ('u52',     66, 3),
    ('u54',     69, 3),
)
SUM_BITS = 8


def normalise(text: str) -> str:
    """Uppercase and strip the 4x4 display spacing; keep only symbols."""
    out = []
    for ch in text.upper():
        if ch in ALPHABET:
            out.append(ch)
    return ''.join(out)


def chars_to_block(symbols: str) -> int:
    """16 symbols -> 80-bit integer (symbol 0 is the top 5 bits)."""
    if len(symbols) != 16:
        raise ValueError(f'password must have 16 symbols, got {len(symbols)}')
    block = 0
    for i, ch in enumerate(symbols):
        code = ALPHABET.index(ch) + 1
        v = (code - 1 - KEY[i]) & 0x1F
        block = (block << 5) | v
    return block


def block_to_chars(block: int) -> str:
    out = []
    for i in range(16):
        v = (block >> (5 * (15 - i))) & 0x1F
        code = (v + KEY[i]) & 0x1F
        out.append(ALPHABET[code])     # (code + 1 - 1) index
    return ''.join(out)


def _unpermute(block: int) -> bytes:
    out = 0
    for i, src in enumerate(PERM):
        bit = (block >> (79 - src)) & 1
        out |= bit << (79 - i)
    return out.to_bytes(10, 'big')


def _permute(plain: bytes) -> int:
    src = int.from_bytes(plain, 'big')
    out = 0
    for i, dst in enumerate(PERM):
        bit = (src >> (79 - i)) & 1
        out |= bit << (79 - dst)
    return out


def _bits(plain: bytes) -> int:
    return int.from_bytes(plain, 'big')


def decode(symbols: str) -> dict:
    symbols = normalise(symbols)
    block = chars_to_block(symbols)
    plain = _unpermute(block)
    bits = _bits(plain)
    rec = {}
    for name, off, width in FIELDS:
        rec[name] = (bits >> (80 - off - width)) & ((1 << width) - 1)
    rec['sum'] = ((bits >> (80 - 7)) & 0x7F) | (((bits >> (80 - 79 - 1)) & 1) << 7)
    rec['_plain'] = plain.hex()
    rec['_cipher'] = f'{block:020x}'
    rec['valid'] = (sum(rec[name] for name, _, _ in FIELDS)
                    & 0xFF) == rec['sum']
    return rec


def encode(**values) -> dict:
    """Build a password record. Unknown fields default to 0; recomputes sum."""
    rec = {name: 0 for name, _, _ in FIELDS}
    for key, value in values.items():
        if key not in rec:
            raise KeyError(f'unknown field {key!r}; known: {sorted(rec)}')
        rec[key] = int(value)
    rec['sum'] = sum(rec[name] for name, _, _ in FIELDS) & 0xFF
    bits = (rec['sum'] & 0x7F) << (80 - 7)
    bits |= (rec['sum'] >> 7 & 1) << (80 - 79 - 1)
    for name, off, width in FIELDS:
        bits |= (rec[name] & ((1 << width) - 1)) << (80 - off - width)
    plain = bits.to_bytes(10, 'big')
    block = _permute(plain)
    return dict(symbols=block_to_chars(block), block=f'{block:020x}',
                plain=plain.hex(), **rec)


def spaced(symbols: str) -> str:
    return ' '.join(symbols[i:i + 4] for i in range(0, 16, 4))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('decode')
    d.add_argument('password')
    e = sub.add_parser('encode')
    e.add_argument('--field', action='append', default=[],
                   help='name=value, repeatable')
    e.add_argument('--json', action='store_true')
    sub.add_parser('tables')
    a = p.parse_args()
    if a.cmd == 'decode':
        print(json.dumps(decode(a.password), indent=2))
    elif a.cmd == 'encode':
        values = {}
        for item in a.field:
            k, v = item.split('=', 1)
            values[k] = int(v, 0)
        rec = encode(**values)
        if a.json:
            print(json.dumps(rec, indent=2))
        else:
            print(spaced(rec['symbols']))
            print(json.dumps({k: v for k, v in rec.items()
                              if k not in ('symbols',)}, indent=2))
    else:
        print('alphabet:', ALPHABET)
        print('key     :', KEY.decode('ascii'))
        print('perm    :', ' '.join(f'{x:02X}' for x in PERM))
        for name, off, width in FIELDS:
            print(f'{name:8s} bit {off:3d} width {width}')


if __name__ == '__main__':
    main()
