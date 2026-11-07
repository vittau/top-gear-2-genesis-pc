#!/usr/bin/env python3
"""Compose icon variants from the approved, generated 1024px Crest of Fire master.

Pillow is needed only to regenerate artwork, never to build/run/package the game.
  python3 tools/release/make_icon.py --all
  python3 tools/release/make_icon.py --size 64 --out build/icon/64.png
The checked-in tg2recomp.png is the source: generation is documented in icon/PROMPTS.md.
"""
import argparse
from io import BytesIO
from pathlib import Path
import struct
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / 'tools/release/tg2recomp.png'
CROP = (0.02, 0.27, 0.94, 0.99)  # approved same-car front/headlights detail
SIZES = (16, 24, 32, 48, 64, 256)


def render(master, size):
    if size <= 32:
        w, h = master.size
        master = master.crop(tuple(round(f*n) for f, n in zip(CROP, (w, h, w, h))))
        master = ImageEnhance.Contrast(master).enhance(1.12)
        master = ImageEnhance.Brightness(master).enhance(1.10)
    icon = ImageOps.fit(master, (size, size), method=Image.Resampling.LANCZOS)
    if size <= 32:
        icon = icon.filter(ImageFilter.UnsharpMask(radius=0.5, percent=110, threshold=3))
    return icon.convert('RGBA')


def dib(icon):
    """32-bit bottom-up BGRA DIB plus opaque AND mask, supported by Win32/SDL."""
    size = icon.width
    header = struct.pack('<IiiHHIIiiII', 40, size, size*2, 1, 32, 0, size*size*4, 0, 0, 0, 0)
    pixels = icon.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes('raw', 'BGRA')
    mask = bytes(((size+31)//32)*4*size)
    return header + pixels + mask


def write_ico(master, path):
    payloads = []
    for size in SIZES:
        icon = render(master, size)
        if size == 256:
            out = BytesIO(); icon.save(out, format='PNG'); payloads.append(out.getvalue())
        else:
            payloads.append(dib(icon))
    offset = 6 + 16*len(SIZES)
    entries = []
    for size, payload in zip(SIZES, payloads):
        entries.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(payload), offset))
        offset += len(payload)
    path.write_bytes(struct.pack('<HHH', 0, 1, len(SIZES)) + b''.join(entries) + b''.join(payloads))


def social_preview(master, path, font_path):
    # The art remains a square, with plain project text beside it; no copied wordmark.
    im = Image.new('RGB', (1280, 640), '#1b1527')
    im.paste(master.resize((640, 640), Image.Resampling.LANCZOS), (640, 0))
    d = ImageDraw.Draw(im)
    heading = ImageFont.truetype(font_path, 76)
    body = ImageFont.truetype(font_path, 26)
    d.rectangle((64, 113, 164, 121), fill='#ffbc54')
    d.text((60, 171), 'TG2Recomp', font=heading, fill='#fff3e1')
    d.text((64, 294), 'Native PC recompilation', font=body, fill='#e3d6e8')
    d.text((64, 338), 'Widescreen • 60 fps', font=body, fill='#ffbc54')
    d.text((64, 526), 'Windows / Linux / macOS', font=body, fill='#d3c4da')
    im.save(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=MASTER)
    p.add_argument('--size', type=int, default=1024)
    p.add_argument('--all', action='store_true', help='Regenerate small PNGs, ICO and social preview')
    p.add_argument('--font', default='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    a = p.parse_args()
    master = Image.open(MASTER).convert('RGB')
    if master.size != (1024, 1024):
        p.error('approved master must be 1024x1024')
    if a.all:
        for size in (16, 24, 32):
            render(master, size).save(MASTER.parent / f'icon/tg2recomp-{size}.png')
        write_ico(master, MASTER.with_suffix('.ico'))
        social_preview(master, ROOT / 'docs/images/social-preview.png', a.font)
    elif a.out.resolve() == MASTER.resolve():
        if a.size != 1024:
            p.error('refusing to resize the authoritative master in place; supply --out')
        print('Approved master already present; no overwrite')
    else:
        render(master, a.size).save(a.out)
    print('make_icon: complete')


if __name__ == '__main__':
    main()
