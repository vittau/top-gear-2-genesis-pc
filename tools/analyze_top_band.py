#!/usr/bin/env python3
"""Identify the native top window band from read-only HUD probe artifacts.

Inputs: build/hud/top-band/{off,centered-16-9,edges-16-9,centered-21-9,edges-21-9}
with the same route files as verify_hud and tg2_video(top=1) snapshots.
The parent build/hud contains the pre-investigation wide captures.
Outputs: JSON evidence and before/after crops, all under the ignored build tree.
"""
from regression import boot_hashes
import argparse
import json
from pathlib import Path
import re
from PIL import Image, ImageChops, ImageDraw

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--out', type=Path, default=Path(__file__).resolve().parents[1]/'build/hud/top-band')
a = p.parse_args()
a.out = a.out.resolve()
NAMES = ('centered-16-9', 'edges-16-9', 'centered-21-9', 'edges-21-9')
FRAMES = (2800, 3300, 4501)
LEVELS = (0,49,87,119,146,174,206,255)
summary = {}


def red_bounds(im):
    points = [(x,y) for y in range(8) for x in range(im.width)
              if (lambda c: c[0]>120 and c[0]>c[1]*1.5 and c[0]>c[2]*1.5)(im.getpixel((x,y)))]
    assert points
    return [min(x for x,y in points), min(y for x,y in points),
            max(x for x,y in points), max(y for x,y in points)]


for name in ('off',) + NAMES:
    for stem in ('dispatch_misses', 'floor_coverage', 'interior_label_misses', 'floor_unsafe'):
        assert re.search(r'# entries:\s+0\b', (a.out/name/(stem+'.toml')).read_text()), (name,stem)
    for frame in FRAMES:
        native = Image.open(a.out/'off'/f'frame-{frame}.png').convert('RGB')
        image = Image.open(a.out/name/f'frame-{frame}.png').convert('RGB')
        margin = (image.width-256)//2
        assert ImageChops.difference(native.crop((0,0,256,8)),image.crop((margin,0,margin+256,8))).getbbox() is None, (name,frame,'native band changed')
        assert red_bounds(native) == [16,0,31,7]
        assert red_bounds(image) == [16+margin,0,31+margin,7]
        if name != 'off':
            before = Image.open(a.out.parent/name/f'frame-{frame}.png').convert('RGB')
            assert ImageChops.difference(before,image).getbbox() is None, (name,frame,'diagnostics changed image')
            for suffix in ('ram', 'vram'):
                assert (a.out.parent/name/f'frame-{frame}.{suffix}').read_bytes() == (a.out/name/f'frame-{frame}.{suffix}').read_bytes(), (name,frame,suffix)
    summary[name] = dict(width=image.width, margin=margin, red_bounds=red_bounds(image), manifests=0)
    if name == 'off':
        log = (a.out/name/'stderr.log').read_text()
        for frame,h in boot_hashes().items():
            assert f'frame={frame} w=320 h=224 hash=0x{h}' in log
        continue
    snapshots = [json.loads(f.read_text()) for f in (a.out/name).glob('state-*.json')]
    state = min(snapshots,key=lambda d: abs(d['frame']-4501))
    vram = (a.out/name/'frame-4501.vram').read_bytes()
    word = lambda addr: int.from_bytes(vram[addr:addr+2],'big')
    samples = []
    for y,row in enumerate(state['video']['top']):
        r,cram = row['reg'],row['cram']
        assert [r[i] for i in (3,17,18)] == [0,0,1], (name,y,'window configuration')
        for x in range(16,32):
            # H32 window: unscrolled 32-cell rows, name table at zero.
            attr = word((y//8*32+x//8)*2)
            assert attr == 0  # Both cells select pattern 0, palette 0.
            byte = vram[(attr&2047)*32+(y&7)*4+(x&7)//2]
            nib = byte&15 if x&1 else byte>>4
            if not nib:
                continue
            color = cram[((attr>>9)&48)|nib]
            rgb = tuple(LEVELS[(color>>shift)&7] for shift in (1,5,9))
            assert image.getpixel((margin+x,y)) == rgb, (name,x,y,'window pixel mismatch')
            samples.append([x,y,nib,color])
    assert len(samples) == 56
    # No displayed sprite intersects this band; exclude a sprite explanation.
    link = 0
    for _ in range(64):
        e = 0xBE00+link*8
        y = (word(e)&1023)-128
        assert not (y<8 and y+((vram[e+2]&3)+1)*8>0), (name,link,'top sprite')
        link = vram[e+3]&127
        if not link:
            break
    summary[name]['window_samples_matched'] = len(samples)
    summary[name]['window_cram'] = {'3': state['video']['top'][0]['cram'][3], '8': state['video']['top'][0]['cram'][8]}
    before = Image.open(a.out.parent/name/'frame-4501.png').convert('RGB')
    sheet = Image.new('RGB',(image.width*3,88),(245,245,245))
    draw = ImageDraw.Draw(sheet)
    draw.text((4,2),f'{name}: before (native origin {margin}, red {16+margin}..{31+margin})',fill='black')
    sheet.paste(before.crop((0,0,image.width,8)).resize((image.width*3,24),Image.Resampling.NEAREST),(0,18))
    draw.text((4,46),'after: identical pixels; read-only diagnostics added',fill='black')
    sheet.paste(image.crop((0,0,image.width,8)).resize((image.width*3,24),Image.Resampling.NEAREST),(0,64))
    sheet.save(a.out/f'before-after-{name}.png')

stock = Image.open(a.out/'off/frame-4501.png').convert('RGB')
stock.crop((0,0,256,8)).resize((1024,32),Image.Resampling.NEAREST).save(a.out/'stock-top.png')
(a.out/'top-band-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
