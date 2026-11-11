#!/usr/bin/env python3
"""Contact sheets and measured art sizes for the S4 actor ladders.

Reads one `check_highres.py lod` directory (actors.csv definitions plus the
snap.vram/snap.cram/snap.ram art snapshot) and the ROM by path, draws every
model of every object record the run used, and prints each model's opaque
extent next to the size the projection scale predicts for its depth band.
Everything it writes stays in the given (ignored) build directory.
Usage: actor_sheet.py build/highres-check/lod/auckland [--rom PATH]
"""
from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path

from PIL import Image


class Memory:
    def __init__(self, rom: bytes, ram: bytes):
        self.rom, self.ram = rom, ram

    def u16(self, a):
        a &= 0xFFFFFF
        if a + 1 < len(self.rom) and a < 0x100000:
            return struct.unpack_from('>H', self.rom, a)[0]
        if a >= 0xFF0000:
            return struct.unpack_from('>H', self.ram, a & 0xFFFF)[0] if (a & 0xFFFF) < 0xFFFF else 0
        return 0

    def s16(self, a):
        v = self.u16(a)
        return v - 65536 if v >= 32768 else v

    def u32(self, a):
        return (self.u16(a) << 16) | self.u16(a + 2)


def palette(cram: bytes):
    out = []
    for i in range(64):
        v = struct.unpack_from('>H', cram, i * 2)[0]
        out.append((((v >> 1) & 7) * 36, ((v >> 5) & 7) * 36, ((v >> 9) & 7) * 36))
    return out


def model_pixels(mem: Memory, vram: bytes, record: int, model: int):
    """Opaque pixels of one model relative to its anchor (x centre, y bottom):
    {(x, y): cram index}; later headers/pieces are drawn under earlier ones
    exactly like the backward SAT builder (first written wins)."""
    art, table, rattr = mem.u32(record), mem.u32(record + 4), mem.u16(record + 8)
    h = mem.u32(table + model * 4)
    pixels, pieces = {}, 0
    if not h:
        return pixels, pieces
    order = []
    for _ in range(16):
        setoff, halfw, height, hattr = mem.u16(h), mem.s16(h + 2), mem.s16(h + 4), mem.u16(h + 6)
        lst = art + 8 + setoff
        count, p = mem.u16(lst), (mem.u32(lst + 2) + art) & 0xFFFFFF
        attr = hattr | rattr
        x0 = halfw if attr & 0x800 else -halfw
        if count > 128:
            break
        for i in range(count):
            q = p + i * 8
            sz, pa = mem.u16(q + 2) >> 8, mem.u16(q + 4)
            pw, ph = (((sz >> 2) & 3) + 1) * 8, ((sz & 3) + 1) * 8
            px = x0 + (-mem.s16(q + 6) - pw if attr & 0x800 else mem.s16(q + 6))
            py = -height + mem.s16(q)
            order.append((px, py, pw, ph, ((attr ^ (pa & 0x1800)) + (pa & 2047)) & 0xFFFF))
        if mem.u16(h + 8) == 0x8888:
            break
        h += 10
    pieces = len(order)
    # The emitter allocates SAT slots backwards, so a later piece is in front.
    for px, py, pw, ph, attr in reversed(order):
        for dy in range(ph):
            sy = ph - 1 - dy if attr & 0x1000 else dy
            for dx in range(pw):
                if (px + dx, py + dy) in pixels:
                    continue
                sx = pw - 1 - dx if attr & 0x800 else dx
                tile = ((attr & 2047) + (sx // 8) * (ph // 8) + sy // 8) & 2047
                b = vram[(tile * 32 + (sy & 7) * 4 + (sx & 7) // 2) & 0xFFFF]
                c = b & 15 if sx & 1 else b >> 4
                if c:
                    pixels[(px + dx, py + dy)] = ((attr >> 9) & 48) | c
    return pixels, pieces


def extent(pixels):
    if not pixels:
        return None
    xs = [x for x, _ in pixels]
    ys = [y for _, y in pixels]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('dir', type=Path)
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--zoom', type=int, default=2)
    p.add_argument('--all', action='store_true', help='include special kinds that stay native')
    args = p.parse_args()
    mem = Memory(args.rom.read_bytes(), (args.dir / 'snap.ram').read_bytes())
    vram = (args.dir / 'snap.vram').read_bytes()
    pal = palette((args.dir / 'snap.cram').read_bytes())
    used, tables = {}, {}
    with (args.dir / 'actors.csv').open() as f:
        for line in f:
            if line.startswith('O,'):
                v = line.split(',', 9)
                if v[4] != '000000' and (args.all or (v[5] != '0' and v[3] != 'FFFE')):
                    used.setdefault(int(v[4], 16), {}).setdefault(int(v[7]), [0, v[2]])[0] += 1
            elif line.startswith('T,'):
                v = line.rstrip().split(',')
                tables[int(v[2])] = [int(x) for x in v[4:]]
    # The projection scale per depth index, straight from the game's table.
    scale_ptr = mem.u32(0xFF221E)
    scale = [mem.u16(scale_ptr + 2 * i) for i in range(128)]
    result = {'scale_table': f'{scale_ptr:06X}', 'scale': scale[:100], 'records': {}}
    print(f'scale table @{scale_ptr:06X}: {scale[:24]} ...')
    for which, name in ((0, 'scenery'), (1, 'cars')):
        t = tables.get(which)
        if not t:
            continue
        bands = {}
        for depth, level in enumerate(t):
            if level >= 0 and depth < 127:
                b = bands.setdefault(level, [depth, depth])
                b[1] = depth
        mids = {lv: math.sqrt(scale[a] * scale[min(b + 1, 127)]) for lv, (a, b) in bands.items()}
        result[name] = {'bands': bands, 'design_scale': mids}
        print(f'{name} bands (level: depth range, geometric-centre scale): ' +
              ' '.join(f'{lv}:{a}-{b}@{mids[lv]:.0f}' for lv, (a, b) in sorted(bands.items())))
    sheets = []
    for record in sorted(used):
        car = record >= 0xFF8E94
        mids = result['cars' if car else 'scenery']['design_scale']
        models = sorted(used[record])
        kind = used[record][models[0]][1]
        rows, entry = [], {}
        for m in range(0, max(models) + 1):
            px, pieces = model_pixels(mem, vram, record, m)
            e = extent(px)
            if e is None:
                continue
            rows.append((m, px, e))
            # Level of this model: scenery model == level; cars use the remap rows.
            level = m if not car else (0 if m < 5 else 1 if m < 8 else 2 if m < 11 else 3 if m < 14 else m - 10)
            entry[m] = dict(extent=e, width=e[2] - e[0], height=-e[1], below=e[3], pieces=pieces,
                            level=level, uses=used[record].get(m, [0])[0])
        if not rows:
            continue
        base = rows[0]
        h0, s0 = -base[2][1], mids.get(0)
        print(f'record {record:06X} kind {kind}{" car" if car else ""}:')
        for m, px, e in rows:
            d = entry[m]
            mid = mids.get(d['level'])
            pred = h0 * mid / s0 if mid and s0 else None
            d['design_scale'] = mid
            d['predicted_height'] = pred
            print(f"  model {m:2d} level {d['level']:2d} uses {d['uses']:5d} pieces {d['pieces']:2d} "
                  f"art {d['width']:3d}x{d['height']:3d} (x {e[0]}..{e[2]}, below {e[3]}) "
                  + (f"design scale {mid:6.0f} predicted h {pred:6.1f} ratio {d['height'] / pred:.2f}" if pred else ''))
        result['records'][f'{record:06X}'] = dict(kind=kind, car=car, models=entry)
        width = sum(e[2] - e[0] + 4 for _, _, e in rows) + 4
        height = max(e[3] - e[1] for _, _, e in rows) + 8
        img = Image.new('RGB', (width, height), (255, 0, 255))
        x = 4
        for m, px, e in rows:
            for (ax, ay), c in px.items():
                img.putpixel((x + ax - e[0], height - 4 - (e[3] - ay)), pal[c])
            x += e[2] - e[0] + 4
        sheets.append((record, img))
    if sheets:
        W = max(i.width for _, i in sheets)
        H = sum(i.height + 2 for _, i in sheets)
        sheet = Image.new('RGB', (W, H), (255, 0, 255))
        y = 0
        for record, img in sheets:
            sheet.paste(img, (0, y))
            y += img.height + 2
        sheet = sheet.resize((W * args.zoom, H * args.zoom), Image.NEAREST)
        sheet.save(args.dir / 'actor-sheet.png')
        print('sheet:', args.dir / 'actor-sheet.png', sheet.size)
    (args.dir / 'actor-sheet.json').write_text(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
