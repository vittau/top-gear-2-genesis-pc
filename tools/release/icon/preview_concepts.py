#!/usr/bin/env python3
"""Compose owner-selection previews from built-in imagegen PNGs (Pillow required).

Run from the repository root. Inputs and previews stay outside git in build/icon/photo.
Generated originals are not deterministic; the downsampling and composition here are.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

OUT = Path('build/icon/photo')
CONCEPTS = (
    ('a', 'SUNSET SPRINT', (0.00, 0.24, 0.83, 1.00)),
    ('b', 'LOW-ANGLE HEAT', (0.12, 0.25, 0.98, 0.98)),
    ('c', 'CREST OF FIRE', (0.02, 0.27, 0.94, 0.99)),
)


def thumbnail(master, size, crop):
    if size <= 32:
        w, h = master.size
        master = master.crop(tuple(round(f * n) for f, n in zip(crop, (w, h, w, h))))
        master = ImageEnhance.Contrast(master).enhance(1.12)
        master = ImageEnhance.Brightness(master).enhance(1.10)
    thumb = ImageOps.fit(master, (size, size), method=Image.Resampling.LANCZOS)
    if size <= 32:
        thumb = thumb.filter(ImageFilter.UnsharpMask(radius=0.5, percent=110, threshold=3))
    return thumb


def main():
    sheet = Image.new('RGB', (1620, 850), '#15121d')
    d = ImageDraw.Draw(sheet)
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font = ImageFont.truetype(font_path, 24)
    label = ImageFont.truetype(font_path, 17)
    for index, (key, name, crop) in enumerate(CONCEPTS):
        master = Image.open(OUT / f'generated-{key}.png').convert('RGB')
        master = ImageOps.fit(master, (1024, 1024), method=Image.Resampling.LANCZOS)
        master.save(OUT / f'{key}-1024.png')
        x = 30 + index * 540
        d.text((x, 22), f'{key.upper()} — {name}', font=font, fill='#fff6e9')
        sheet.paste(master.resize((500, 500), Image.Resampling.LANCZOS), (x, 70))
        for j, size in enumerate((64, 32, 16)):
            thumb = thumbnail(master, size, crop)
            thumb.save(OUT / f'{key}-{size}.png')
            xx = x + j * 165
            sheet.paste(thumb, (xx, 608))
            d.text((xx, 688), f'{size} px', font=label, fill='#d5c9db')
            if size <= 32:
                sheet.paste(thumb.resize((64, 64), Image.Resampling.NEAREST), (xx + 65, 608))
                d.text((xx, 722), 'detail crop', font=label, fill='#ab9eaf')
        d.text((x, 786), '16/32 shown also enlarged with nearest pixels', font=label, fill='#ab9eaf')
    sheet.save(OUT / 'concepts.png')
    print(f'Wrote {OUT}/concepts.png and 12 sized previews')


if __name__ == '__main__':
    main()
