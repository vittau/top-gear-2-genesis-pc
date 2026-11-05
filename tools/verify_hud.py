#!/usr/bin/env python3
"""Replay HUD evidence on port 4460 without guest writes or saved states.

Run --record-baseline before rebuilding the renderer, then run normally.
Requires Pillow. Captures, dumps and logs stay under build/hud/.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ('dispatch_misses', 'floor_coverage', 'interior_label_misses', 'floor_unsafe')
FRAMES = (2800, 3300, 4501)
SEQUENCE = tuple(range(4510, 4516))
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--exe', type=Path, default=ROOT/'build/TG2Recomp')
p.add_argument('--out', type=Path, default=ROOT/'build/hud')
p.add_argument('--rom', type=Path, default=Path.home()/'roms/genesis/tg2.bin')
p.add_argument('--port', type=int, default=4460)
p.add_argument('--record-baseline', action='store_true')
p.add_argument('--check-only', action='store_true', help='Validate existing captures without relaunching')
p.add_argument('--runs', help='Comma separated run names, to resume evidence collection')
a = p.parse_args()
a.exe, a.out = a.exe.resolve(), a.out.resolve()
a.out.mkdir(parents=True, exist_ok=True)
(a.exe.parent/'debug.ini').touch()


def command(name, **kw):
    with socket.create_connection(('127.0.0.1', a.port), timeout=5) as s:
        s.sendall((json.dumps(dict(cmd=name, id=1, **kw))+'\n').encode())
        return json.loads(s.makefile().readline())


def timeline(out, short=False):
    actions = {}
    for action in json.loads((ROOT/'game/baseline-route.json').read_text()):
        if 'keys' in action and action['frame'] <= (300 if short else SEQUENCE[-1]):
            actions[action['frame']] = ['RELEASE'] + ([] if action['keys'] == '0' else [
                'HOLD '+{'80': 'START', '2': 'DOWN', '10': 'B'}[action['keys']]])
    for frame in ((60, 300) if short else FRAMES + SEQUENCE):
        actions.setdefault(frame, []).extend([
            f'SCREENSHOT {out}/frame-{frame}.png',
            f'DUMP_VRAM {out}/frame-{frame}.vram', f'DUMP_RAM {out}/frame-{frame}.ram'])
    lines, previous = [], 1
    for frame, events in sorted(actions.items()):
        if frame > previous:
            lines.append(f'WAIT {frame-previous}')
        lines.extend(events)
        previous = frame
    lines += ['WAIT 3', 'EXIT 0']
    path = out/'route.input'
    path.write_text('\n'.join(lines)+'\n')
    return path


def run(name, mode, hud, fps):
    out = a.out/name
    out.mkdir(parents=True, exist_ok=True)
    script = timeline(out, mode == 'off')
    with socket.socket() as check:
        check.bind(('127.0.0.1', a.port))
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_RENDER_DRIVER='software',
               SDL_AUDIODRIVER='dummy', TG2_HUD_MODE=hud, TG2_RACE_60FPS=str(fps))
    env.pop('APPIMAGE', None)
    with (out/'stdout.log').open('w') as stdout, (out/'stderr.log').open('w') as stderr:
        proc = subprocess.Popen([str(a.exe), str(a.rom), '--no-launcher', '--port', str(a.port),
            '--widescreen', mode, '--input-script', str(script), '--max-frames', '304' if mode == 'off' else '4519',
            '--fresh-evidence', '--hash-frames', '60', '--turbo'],
            cwd=a.exe.parent, env=env, stdout=stdout, stderr=stderr)
        deadline, next_frame = time.monotonic()+900, 2750
        try:
            while proc.poll() is None:
                if time.monotonic() > deadline:
                    raise TimeoutError(name)
                try:
                    frame = command('frame_info')['current_frame']
                    if frame >= next_frame:
                        # Read-only name-table/SAT evidence alongside live raster rows.
                        data = dict(frame=frame, video=command('tg2_video', rows=1),
                                    vdp=command('vdp_state'),
                                    names=command('read_vram', addr='C000', size=2048),
                                    sat=command('read_vram', addr='BE00', size=512))
                        (out/f'state-{frame}.json').write_text(json.dumps(data, indent=2)+'\n')
                        next_frame += 500
                except (OSError, KeyError):
                    pass
                time.sleep(.2)
            assert proc.returncode == 0, (name, proc.returncode)
        finally:
            if proc.poll() is None:
                proc.terminate()  # Only the PID started by this probe.
                proc.wait(timeout=10)
            for stem in MANIFESTS:
                shutil.copyfile(a.exe.parent/(stem+'.toml'), out/(stem+'.toml'))
    for stem in MANIFESTS:
        assert re.search(r'# entries:\s+0\b', (out/(stem+'.toml')).read_text()), (name, stem)
    print(name, 'exit=0; manifests=0', flush=True)


def equal_images(first, second):
    x, y = Image.open(first).convert('RGB'), Image.open(second).convert('RGB')
    assert x.size == y.size, (first, second, 'size')
    assert ImageChops.difference(x, y).getbbox() is None, (first, second, 'pixels')


def verify_translation(centered, edges, frame):
    """Check each opaque live HUD texel, including overlapping map markers."""
    vram = (centered/f'frame-{frame}.vram').read_bytes()
    word = lambda addr: int.from_bytes(bytes((vram[addr & 65535], vram[(addr+1) & 65535])), 'big')
    snapshots = [json.loads(path.read_text()) for path in centered.glob('state-*.json')]
    rows = min(snapshots, key=lambda d: abs(d['frame']-frame))['video']['rows']
    source = Image.open(centered/f'frame-{frame}.png').convert('RGB')
    dest = Image.open(edges/f'frame-{frame}.png').convert('RGB')
    origin = (source.width-256)//2
    right = source.width-256-origin
    mask = {}
    for y, (ha, hb, va, vb, ba, bb) in enumerate(rows):
        # Inactive rows retain old diagnostic scroll values. The baseline
        # raster displays the HUD between rows 14 and 93; inspect its live
        # cells only in that interval, and compare the other rows below.
        if y < 14 or y >= 94:
            continue
        for x in range(256):
            px, py = (x-ha) & 511, (y+va) & 511
            attr = word(ba + ((py//8)*64 + px//8)*2)
            tile = attr & 2047
            if not (attr & 0x8000 and 4 <= tile <= 0x84):
                continue
            tx, ty = px & 7, py & 7
            if attr & 0x800:
                tx ^= 7
            if attr & 0x1000:
                ty ^= 7
            byte = vram[tile*32 + ty*4 + tx//2]
            if (byte & 15 if tx & 1 else byte >> 4):
                mask[x,y] = -origin if tile < 0x3D else right
    link = 0
    for _ in range(64):
        entry = 0xBE00 + link*8
        attr, size = word(entry+4), vram[entry+2]
        tile = attr & 2047
        if size == 5 and attr & 0x8000 and tile in (0x106, 0x10E):
            x, y = (word(entry+6) & 1023)-128, (word(entry) & 1023)-128
            for dy in range(16):
                for dx in range(16):
                    sx, sy = (15-dx if attr & 0x800 else dx), (15-dy if attr & 0x1000 else dy)
                    byte = vram[(tile+(sx//8)*2+sy//8)*32+(sy & 7)*4+(sx & 7)//2]
                    if (byte & 15 if sx & 1 else byte >> 4) and 0 <= x+dx < 256 and 0 <= y+dy < 224:
                        mask[x+dx,y+dy] = right
        link = vram[entry+3] & 127
        if not link:
            break
    assert len(mask) > 500, (frame, 'HUD ownership missing')
    for (x,y), delta in mask.items():
        assert source.getpixel((origin+x,y)) == dest.getpixel((origin+x+delta,y)), (edges.name, frame, x,y,'HUD translation')
        # The baseline track's HUD rows have uniform sky in plane B. The
        # center column is uncovered, so it is an independent sky reference.
        assert dest.getpixel((origin+x,y)) == source.getpixel((origin+128,y)), (edges.name,frame,x,y,'HUD ghost')
    return len(mask)


runs = ([(f'before-{r}', r.replace('-', ':'), 'centered', 0) for r in ('16-9', '21-9')]
        if a.record_baseline else [
            ('off-centered', 'off', 'centered', 0), ('off-edges', 'off', 'edges', 0),
            ('centered-16-9', '16:9', 'centered', 0), ('edges-16-9', '16:9', 'edges', 0),
            ('centered-21-9', '21:9', 'centered', 0), ('edges-21-9', '21:9', 'edges', 0),
            ('fps60-centered', '21:9', 'centered', 1), ('fps60-edges', '21:9', 'edges', 1)])
for args in runs:
    if not a.check_only and (not a.runs or args[0] in a.runs.split(',')):
        run(*args)
if a.record_baseline:
    raise SystemExit(0)

summary = {}
translations = {}
summary['manifests'] = {}
for name, _, _, _ in runs:
    for stem in MANIFESTS:
        assert re.search(r'# entries:\s+0\b', (a.out/name/(stem+'.toml')).read_text()), (name, stem)
    summary['manifests'][name] = 'all four empty'
for name in ('off-centered', 'off-edges'):
    text = (a.out/name/'stderr.log').read_text()
    for frame, expected in ((60, '2A0B972960C5E325'), (300, '1131D937D70234FD')):
        assert f'frame={frame} w=320 h=224 hash=0x{expected}' in text, (name, frame)
    summary[name] = dict(exit=0, hashes={'60': '2A0B972960C5E325', '300': '1131D937D70234FD'})
for ratio in ('16-9', '21-9'):
    old, centered = a.out/f'before-{ratio}', a.out/f'centered-{ratio}'
    old_hashes = re.findall(r'\[FBHASH\].*', (old/'stderr.log').read_text())
    assert old_hashes == re.findall(r'\[FBHASH\].*', (centered/'stderr.log').read_text()), ratio
    for frame in FRAMES + SEQUENCE:
        equal_images(old/f'frame-{frame}.png', centered/f'frame-{frame}.png')
    summary[f'centered-{ratio}'] = 'all framebuffer hashes and captured pixels match pre-change build'
for centered_name, edges_name in [('off-centered', 'off-edges'),
        ('centered-16-9', 'edges-16-9'), ('centered-21-9', 'edges-21-9'),
        ('fps60-centered', 'fps60-edges')]:
    centered, edges = a.out/centered_name, a.out/edges_name
    for frame in ((60, 300) if centered_name.startswith('off') else FRAMES + SEQUENCE):
        for suffix in ('ram', 'vram'):
            assert (centered/f'frame-{frame}.{suffix}').read_bytes() == (edges/f'frame-{frame}.{suffix}').read_bytes(), (edges_name, frame, suffix)
        x = Image.open(centered/f'frame-{frame}.png').convert('RGB')
        y = Image.open(edges/f'frame-{frame}.png').convert('RGB')
        if centered_name.startswith('off'):
            equal_images(centered/f'frame-{frame}.png', edges/f'frame-{frame}.png')
        else:
            # HUD is above row 94 on this route; every lower pixel must stay exact.
            assert ImageChops.difference(x.crop((0,94,x.width,x.height)), y.crop((0,94,y.width,y.height))).getbbox() is None, (edges_name, frame, 'world changed')
            assert ImageChops.difference(x.crop((0,0,x.width,14)), y.crop((0,0,y.width,14))).getbbox() is None, (edges_name, frame, 'top raster changed')
            assert ImageChops.difference(x,y).getbbox(), (edges_name, frame, 'HUD did not move')
            translations[f'{edges_name}/{frame}'] = verify_translation(centered, edges, frame)
    if centered_name.startswith('off'):
        summary[edges_name]['comparison'] = 'RAM/VRAM and all pixels identical'
    else:
        summary[edges_name] = 'RAM/VRAM exact; every opaque HUD pixel translated exactly; no ghosts; other rows unchanged at all nine frames'
summary['translated_pixel_counts'] = translations
summary['fps60_consecutive_frames'] = list(SEQUENCE)
for name in ('fps60-centered', 'fps60-edges'):
    assert 'race presentation: 60 fps option on' in (a.out/name/'stderr.log').read_text(), name
    assert len({Image.open(a.out/name/f'frame-{frame}.png').tobytes() for frame in SEQUENCE}) == 6, (name, 'repeated 60 fps picture')
summary['screenshots_sha256'] = {str(p.relative_to(a.out)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(a.out.glob('*/frame-*.png'))}
(a.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k != 'screenshots_sha256'}, indent=2))
