#!/usr/bin/env python3
"""Check paired exact-frame weather captures; assets stay outside git.

Each directory contains 16-9.png, fit.png, and 21-9.png, captured from
identical controller replays before and after the renderer change.
"""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageChops

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('before', type=Path)
p.add_argument('after', type=Path)
a = p.parse_args()
results = {}
for mode in ('16-9', 'fit', '21-9'):
    before = Image.open(a.before / f'{mode}.png').convert('RGB')
    after = Image.open(a.after / f'{mode}.png').convert('RGB')
    assert before.size == after.size, (mode, before.size, after.size)
    origin = (before.width - 256) // 2
    center = (origin, 0, origin + 256, before.height)
    assert ImageChops.difference(before.crop(center), after.crop(center)).getbbox() is None, (mode, 'native center changed')
    changes = []
    for box in ((0, 0, origin, before.height),
                (origin + 256, 0, before.width, before.height)):
        diff = ImageChops.difference(before.crop(box), after.crop(box))
        count = sum(pixel != (0, 0, 0) for pixel in diff.getdata())
        assert count > 0, (mode, 'dry margin', box)
        # Point features must remain sparse, rather than smearing into walls.
        assert count < diff.width * diff.height // 2, (mode, 'dense margin')
        changes.append(count)
    results[mode] = dict(size=before.size, center='identical', changed_margin_pixels=changes)
print(json.dumps(results, indent=2))
