#!/usr/bin/env python3
"""Replay the baseline controller route with exact frame captures in each aspect.

Requires Pillow. All ROM-derived captures remain in the ignored output directory.
No guest state writes, pause/step, or savestates; uses only controller input,
read-only dumps, and the free-running TCP presentation configuration.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ('dispatch_misses.toml', 'floor_coverage.toml',
             'interior_label_misses.toml', 'floor_unsafe.toml')
FRAMES = (600, 1350, 2800, 3300, 4501)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--exe', type=Path, default=ROOT/'build/TG2Recomp')
p.add_argument('--rom', type=Path, default=Path.home()/'roms/genesis/tg2.bin')
p.add_argument('--out', type=Path, default=ROOT/'build/ws')
p.add_argument('--port', type=int, default=4400)
p.add_argument('--modes', default='off,16:9,21:9')
a = p.parse_args()
a.exe, a.out = a.exe.resolve(), a.out.resolve()
a.out.mkdir(parents=True, exist_ok=True)
(a.exe.parent/'debug.ini').touch()

def command(cmd, **args):
    with socket.create_connection(('127.0.0.1', a.port), timeout=5) as s:
        s.sendall((json.dumps(dict(cmd=cmd, id=1, **args))+'\n').encode())
        return json.loads(s.makefile().readline())

def timeline(out):
    actions = {f: [] for f in FRAMES}
    for action in json.loads((ROOT/'game/baseline-route.json').read_text()):
        if 'keys' in action:
            lines = ['RELEASE']
            if action['keys'] != '0':
                lines += ['HOLD '+{'80':'START', '2':'DOWN', '10':'B'}[action['keys']]]
            actions.setdefault(action['frame'], []).extend(lines)
    for frame in FRAMES:
        actions[frame] += [f'SCREENSHOT {out}/frame-{frame}.png',
                           f'DUMP_RAM {out}/frame-{frame}.ram',
                           f'DUMP_VRAM {out}/frame-{frame}.vram']
    # Extra captures can establish a sprite crossing the old viewport boundary.
    for frame in range(3360, 4441, 120):
        actions.setdefault(frame, []).append(f'SCREENSHOT {out}/frame-{frame}.png')
    lines, previous = [], 1
    for frame, event in sorted(actions.items()):
        if frame > previous:
            lines.append(f'WAIT {frame-previous}')
        lines.extend(event)
        previous = frame
    lines += [f'WAIT {5600-previous}', 'EXIT 0']
    path = out/'route.input'
    path.write_text('\n'.join(lines)+'\n')
    return path

summary = {}
for mode in a.modes.split(','):
    out = a.out/mode.replace(':', '-')
    out.mkdir(parents=True, exist_ok=True)
    script = timeline(out)
    with socket.socket() as check:
        check.bind(('127.0.0.1', a.port))
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_RENDER_DRIVER='software',
               SDL_AUDIODRIVER='dummy')
    argv = [str(a.exe), str(a.rom), '--no-launcher', '--port', str(a.port),
            '--widescreen', mode, '--input-script', str(script), '--max-frames', '5601',
            '--hash-frames', '60', '--fresh-evidence', '--turbo']
    diagnostics = []
    with (out/'stdout.log').open('w') as stdout, (out/'stderr.log').open('w') as stderr:
        proc = subprocess.Popen(argv, cwd=a.exe.parent, env=env, stdout=stdout, stderr=stderr)
        deadline = time.monotonic()+240
        next_frame = 2800
        try:
            while proc.poll() is None:
                if time.monotonic()>deadline:
                    raise TimeoutError(f'{mode} runtime deadline exceeded')
                try:
                    frame = command('frame_info')['current_frame']
                    if frame >= next_frame:
                        data = command('tg2_video')
                        diagnostics.append(dict(frame=frame, video=data))
                        (out/'video.json').write_text(json.dumps(diagnostics, indent=2)+'\n')
                        next_frame += 120
                except (ConnectionRefusedError, ConnectionResetError, OSError):
                    pass
                time.sleep(.05)
            if proc.returncode:
                raise RuntimeError(f'{mode} exited {proc.returncode}')
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)
            for name in MANIFESTS:
                shutil.copyfile(a.exe.parent/name, out/name)
    for name in MANIFESTS:
        text = (out/name).read_text()
        if not re.search(r'# entries:\s+0\b', text):
            raise AssertionError(f'{mode}: nonempty {name}')
    summary[mode] = dict(exit=proc.returncode, frames=5600, manifests='all empty')
    if mode == 'off':
        text = (out/'stderr.log').read_text()
        for frame, expected in [(60, '2A0B972960C5E325'), (300, '1131D937D70234FD')]:
            assert f'frame={frame} w=320 h=224 hash=0x{expected}' in text
        summary[mode]['hashes'] = {'60':'2A0B972960C5E325', '300':'1131D937D70234FD'}
    if mode != 'off' and (a.out/'off/frame-2800.ram').exists():
        from PIL import Image, ImageChops
        for frame in FRAMES:
            for suffix in ('ram', 'vram'):
                assert (out/f'frame-{frame}.{suffix}').read_bytes() == (a.out/'off'/f'frame-{frame}.{suffix}').read_bytes(), (mode, frame, suffix)
            native = Image.open(a.out/'off'/f'frame-{frame}.png').convert('RGB')
            wide = Image.open(out/f'frame-{frame}.png').convert('RGB')
            origin = (wide.width-native.width)//2
            assert ImageChops.difference(native, wide.crop((origin, 0, origin+native.width, native.height))).getbbox() is None, (mode, frame, 'native center')
        summary[mode]['canonical_state_and_center'] = 'identical at all 5 capture frames'
    (a.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({mode:summary[mode]}), flush=True)
