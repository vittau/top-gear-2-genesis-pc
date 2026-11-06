#!/usr/bin/env python3
"""Capture the RACE SOUND page for the stock values and for BOTH.

One run, one build, so the three pages are pixel-comparable:

  * SOUND EFFECTS (stock value 0)
  * MUSIC         (stock value 1)
  * BOTH          (host value, shown as MUSIC to the cartridge)

Each page is written as a 1x PNG plus a 3x nearest-neighbour zoom cropped to
the page box.  Input is controller-only; nothing writes guest memory.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, KEYS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


BOX = (64, 72, 256, 160)


def zoom(src: Path, dst: Path, box=BOX, factor=3):
    from PIL import Image
    im = Image.open(src).convert('RGB')
    im.crop(box).resize(((box[2] - box[0]) * factor, (box[3] - box[1]) * factor),
                        Image.NEAREST).save(dst)


def sheet(items, dst: Path, factor: int = 1):
    """One labelled strip of page crops, left to right."""
    from PIL import Image, ImageDraw
    crops = []
    for label, path in items:
        im = Image.open(path).convert('RGB').crop(BOX)
        if factor != 1:
            im = im.resize(((BOX[2] - BOX[0]) * factor, (BOX[3] - BOX[1]) * factor),
                           Image.NEAREST)
        crops.append((label, im))
    pad, label_h = 6, 12
    w = sum(c.width for _, c in crops) + pad * (len(crops) + 1)
    h = max(c.height for _, c in crops) + label_h + pad * 2
    out = Image.new('RGB', (w, h), (24, 24, 28))
    d = ImageDraw.Draw(out)
    x = pad
    for label, c in crops:
        d.text((x, pad), label, fill=(230, 230, 230))
        out.paste(c, (x, pad + label_h))
        x += c.width + pad
    out.save(dst)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4550)
    p.add_argument('--out', type=Path, default=ROOT / 'build/menu-pages')
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--sheet', action='store_true',
                   help='compose 1x and 3x comparison strips')
    a = p.parse_args()
    a.out = a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)

    r = Runner(port=a.port, out=a.out, exe=a.exe, widescreen='off', max_frames=4000)
    r.start()
    try:
        def shot(name):
            path = a.out / f'{name}.png'
            r.command('screenshot', path=str(path))
            zoom(path, a.out / f'{name}-3x.png')
            print(f'{name:22s} mode={r.ram16(0x240E)} value={r.ram16(0x2560)}',
                  flush=True)

        def settle(n=90):
            r.wait_frame(r.frame() + n)

        r.wait_frame(400)
        r.tap('START', 8)
        settle(200)
        for _ in range(2):
            r.tap('DOWN', 6); settle(40)
        r.tap('START', 8); settle(200)     # SOUND submenu
        r.tap('START', 8); settle(240)     # RACE SOUND value page
        shot('race-sound-effects')
        r.tap('DOWN', 6); settle(120)
        shot('race-sound-music')
        r.tap('DOWN', 6); settle(120)
        shot('race-sound-both')
        r.tap('UP', 6); settle(120)
        shot('race-sound-music-again')
    finally:
        r.stop()

    if a.sheet:
        sheet([('stock: MUSIC', a.out / 'race-sound-music.png'),
               ('stock: SOUND EFFECTS', a.out / 'race-sound-effects.png'),
               ('new: BOTH', a.out / 'race-sound-both.png')],
              a.out / 'sheet-1x.png', 1)
        sheet([('stock: MUSIC', a.out / 'race-sound-music.png'),
               ('stock: SOUND EFFECTS', a.out / 'race-sound-effects.png'),
               ('new: BOTH', a.out / 'race-sound-both.png')],
              a.out / 'sheet-3x.png', 3)
    return 0


if __name__ == '__main__':
    sys.exit(main())
