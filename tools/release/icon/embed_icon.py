#!/usr/bin/env python3
"""Extract the 32px RGBA DIB from our ICO as a build-local C header (stdlib only)."""
import argparse
from pathlib import Path
import struct


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('ico', type=Path)
    p.add_argument('header', type=Path)
    a = p.parse_args()
    data = a.ico.read_bytes()
    reserved, kind, count = struct.unpack_from('<HHH', data)
    if (reserved, kind) != (0, 1):
        p.error('not an ICO')
    for index in range(count):
        w, h, _, _, planes, bpp, length, offset = struct.unpack_from('<BBBBHHII', data, 6+index*16)
        if (w, h, planes, bpp) != (32, 32, 1, 32):
            continue
        dib = data[offset:offset+length]
        header_size, width, height, planes, depth, compression = struct.unpack_from('<IiiHHI', dib)
        if (header_size, width, height, planes, depth, compression) != (40, 32, 64, 1, 32, 0):
            p.error('expected uncompressed 32px BGRA DIB')
        rgba = bytearray()
        for y in reversed(range(32)):
            for x in range(32):
                b, g, r, alpha = dib[40+(y*32+x)*4:44+(y*32+x)*4]
                rgba.extend((r, g, b, alpha))
        lines = [', '.join(f'0x{v:02x}' for v in rgba[i:i+16]) for i in range(0,len(rgba),16)]
        a.header.parent.mkdir(parents=True, exist_ok=True)
        a.header.write_text('/* Generated from the approved ICO; do not edit. */\n'
            '#pragma once\nstatic const unsigned char tg2_icon_rgba[] = {\n    '
            + ',\n    '.join(lines) + '\n};\n')
        return
    p.error('missing 32px DIB entry')


if __name__ == '__main__':
    main()
