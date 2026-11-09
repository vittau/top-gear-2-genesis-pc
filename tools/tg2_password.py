#!/usr/bin/env python3
"""Top Gear 2 (Genesis) password codec — reversed from the stock ROM.

The ENTER PASSWORD screen stores 16 symbols. Each symbol is a 5-bit value
salted with a fixed key string;

    v[i] = (code[i] - 1 - KEY[i]) & 0x1F

and the 16 values concatenate big-endian into an 80-bit block (symbol 0 is
the most significant 5 bits). That block is then un-permuted bit by bit with
a stock 80-entry table into a 10-byte plaintext record, which unpacks into
the game-state fields listed in FIELDS. The checksum is a 15-bit additive
checksum over every other field.

Everything here was verified against the running game: the ROM's own
prefilled password decodes to a valid record (checksum matches) and is
accepted through the UI, and generated passwords start real races.

    python3 tools/tg2_password.py decode "KVC2 2HQG CJL2 Y4%T"
    python3 tools/tg2_password.py encode --field country=1
    python3 tools/tg2_password.py tables
"""
from __future__ import annotations

import argparse
import json
import sys

# The 32 password symbols in keyboard order (left-to-right, top-to-bottom).
# The keyboard's control keys (arrows, DEL, END) are not part of the alphabet.
ALPHABET = 'BCDFGHJKLNPQSTVYZ123456789[]?\\#%'
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
# bit stream, width). 'sum' has 15 bits: low 7 at stream bits 0..6
# (byte 0 bits 7..1), high 8 in byte 9 (stream bits 72..79).
FIELDS = (
    ('flag',     7, 1),   # $2a
    ('country',  8, 4),   # $28
    ('stage',   12, 2),   # $2c  (validator rejects > 2)
    ('money',   14, 10),  # $2e
    ('field30', 24, 10),  # $30: player 2 money
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
SUM_BITS = 15


def normalise(text: str) -> str:
    """Screen symbols, ignoring spacing; accept historical U as an alias for V."""
    out = []
    for ch in text.upper():
        if ch.isspace():
            continue
        if ch == 'U':                 # old tool spelling of screen code 15
            ch = 'V'
        if ch not in ALPHABET:
            raise ValueError(f'{ch!r} is not a password-screen symbol')
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


def decode(symbols: str, picker_country: int = -1) -> dict:
    symbols = normalise(symbols)
    block = chars_to_block(symbols)
    plain = _unpermute(block)
    bits = _bits(plain)
    rec = {}
    for name, off, width in FIELDS:
        rec[name] = (bits >> (80 - off - width)) & ((1 << width) - 1)
    rec['sum'] = ((bits >> 73) & 0x7F) | ((bits & 0xFF) << 7)
    rec['_plain'] = plain.hex()
    rec['_cipher'] = f'{block:020x}'
    rec['_field_sum'] = sum(rec[name] for name, _, _ in FIELDS)
    rec['_errors'] = []
    if rec['_field_sum'] != rec['sum']:
        rec['_errors'].append('checksum mismatch')
    if rec['stage'] > 2:
        rec['_errors'].append('difficulty exceeds 2')
    if picker_country > rec['country']:
        rec['_errors'].append(f'country {rec["country"]} is below picker requirement {picker_country}')
    rec['valid'] = not rec['_errors']
    return rec


def encode(**values) -> dict:
    """Build a password record. Unknown fields default to 0; recomputes sum."""
    rec = {name: 0 for name, _, _ in FIELDS}
    for key, value in values.items():
        if key not in rec:
            raise KeyError(f'unknown field {key!r}; known: {sorted(rec)}')
        rec[key] = int(value)
    for name, _, width in FIELDS:
        if not 0 <= rec[name] < (1 << width):
            raise ValueError(f'{name} must be in 0..{(1 << width) - 1}')
    if rec['stage'] > 2:
        raise ValueError('stage/difficulty must be 0..2')
    rec['sum'] = sum(rec[name] for name, _, _ in FIELDS)
    bits = (rec['sum'] & 0x7F) << (80 - 7)
    bits |= rec['sum'] >> 7
    for name, off, width in FIELDS:
        bits |= (rec[name] & ((1 << width) - 1)) << (80 - off - width)
    plain = bits.to_bytes(10, 'big')
    block = _permute(plain)
    return dict(symbols=block_to_chars(block), block=f'{block:020x}',
                plain=plain.hex(), **rec)


def max_upgrades(country: int, stage: int = 0, two_players: bool = False) -> dict:
    """Both cars: eight level-3 parts, 1023k each, stock red/blue colours."""
    values = dict(country=country, stage=stage, flag=int(two_players),
                  money=1023, field30=1023, u52=0, u54=1)
    values.update({f'u{offset:x}': 3 for offset in range(0x32, 0x52, 2)})
    return encode(**values)


def work_record(work: bytes) -> dict:
    """Decode a 0x56-byte validator work area (A0, on either menu route)."""
    if len(work) != 0x56:
        raise ValueError('work record must contain 0x56 bytes')
    def word(offset):
        return int.from_bytes(work[offset:offset + 2], 'big')
    fields = {}
    offsets = {'sum': 0x26, 'country': 0x28, 'flag': 0x2a,
               'stage': 0x2c, 'money': 0x2e, 'field30': 0x30}
    for name, _, _ in FIELDS:
        offset = offsets[name] if name in offsets else int(name[1:], 16)
        fields[name] = word(offset)
    fields['sum'] = word(0x26)
    codes = list(work[:16])
    return dict(codes=codes,
                symbols=''.join(ALPHABET[c - 1] if 1 <= c <= 32 else '_' for c in codes),
                cipher=work[0x10:0x1a].hex(), plain=work[0x1a:0x24].hex(),
                picker_country=int.from_bytes(work[0x24:0x26], 'big', signed=True),
                fields=fields, field_sum=sum(fields[n] for n, _, _ in FIELDS))


def spaced(symbols: str) -> str:
    return ' '.join(symbols[i:i + 4] for i in range(0, 16, 4))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('decode')
    d.add_argument('password')
    d.add_argument('--picker-country', type=int, default=-1,
                   help='country required by COUNTRY SELECT; default PASSWORDS route (-1)')
    e = sub.add_parser('encode')
    e.add_argument('--field', action='append', default=[],
                   help='name=value, repeatable')
    e.add_argument('--json', action='store_true')
    m = sub.add_parser('max', help='all parts at level 3 and both balances at maximum')
    m.add_argument('--country', type=int, required=True)
    m.add_argument('--stage', type=int, choices=(0, 1, 2), default=0)
    m.add_argument('--two-players', action='store_true')
    m.add_argument('--json', action='store_true')
    sub.add_parser('tables')
    a = p.parse_args()
    if a.cmd == 'decode':
        print(json.dumps(decode(a.password, a.picker_country), indent=2))
    elif a.cmd in ('encode', 'max'):
        values = {}
        for item in getattr(a, 'field', []):
            k, v = item.split('=', 1)
            values[k] = int(v, 0)
        rec = max_upgrades(a.country, a.stage, a.two_players) if a.cmd == 'max' else encode(**values)
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
