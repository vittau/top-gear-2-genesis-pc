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
p.add_argument('--sweep', action='store_true', help='Steer after frame 4501 to exercise margin crossings')
a = p.parse_args()
a.exe, a.out = a.exe.resolve(), a.out.resolve()
a.out.mkdir(parents=True, exist_ok=True)
(a.exe.parent/'debug.ini').touch()

def command(cmd, **args):
    with socket.create_connection(('127.0.0.1', a.port), timeout=5) as s:
        s.sendall((json.dumps(dict(cmd=cmd, id=1, **args))+'\n').encode())
        return json.loads(s.makefile().readline())

def stderr_text_tail(out):
    try:
        return (out/'stderr.log').read_text()[-1200:]
    except OSError:
        return '(no stderr log)'

def timeline(out):
    actions = {f: [] for f in FRAMES}
    for action in json.loads((ROOT/'game/baseline-route.json').read_text()):
        if 'keys' in action:
            lines = ['RELEASE']
            if action['keys'] != '0':
                lines += ['HOLD '+{'80':'START', '2':'DOWN', '10':'B'}[action['keys']]]
            actions.setdefault(action['frame'], []).extend(lines)
    if a.sweep:
        actions[4600] = ['RELEASE', 'HOLD B', 'HOLD RIGHT']
        actions[4900] = ['RELEASE', 'HOLD B', 'HOLD LEFT']
        for frame in range(4600, 5501, 20):
            actions.setdefault(frame, []).append(f'SCREENSHOT {out}/sweep-{frame}.png')
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
    # A launched native build that inherits a host $APPIMAGE would anchor its
    # debug.ini lookup (and the required TCP server) to the AppImage directory.
    env.pop('APPIMAGE', None)
    argv = [str(a.exe), str(a.rom), '--no-launcher', '--port', str(a.port),
            '--widescreen', mode, '--input-script', str(script), '--max-frames', '5601',
            '--hash-frames', '60', '--fresh-evidence', '--turbo']
    diagnostics = []
    margin_shots = []
    resize_actions = []
    if mode == '21:9' and not a.sweep:
        for frame, dw, dh, expected in [(4600,1600,900,398), (4700,1234,567,488),
                                        (4800,1000,1000,320), (4900,3840,720,1195)]:
            resize_actions += [(frame, 'configure', (dw,dh)), (frame+20, 'capture', expected)]
        resize_actions += [(5000,'off',None), (5020,'capture',256), (5100,'restore',None)]
    with (out/'stdout.log').open('w') as stdout, (out/'stderr.log').open('w') as stderr:
        proc = subprocess.Popen(argv, cwd=a.exe.parent, env=env, stdout=stdout, stderr=stderr)
        # The debug.ini TCP server is required for every frame capture; fail
        # loudly when it never appears instead of timing out silently.
        ready = time.monotonic()+20
        while True:
            try:
                command('frame_info')
                break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError(f'{mode} exited early:\n'+stderr_text_tail(out))
                if time.monotonic()>ready:
                    raise RuntimeError(f'{mode} TCP server never became reachable:\n'+stderr_text_tail(out))
                time.sleep(.1)
        deadline = time.monotonic()+600
        next_frame = 2800
        try:
            while proc.poll() is None:
                if time.monotonic()>deadline:
                    raise TimeoutError(f'{mode} runtime deadline exceeded')
                try:
                    frame = command('frame_info')['current_frame']
                    while resize_actions and frame >= resize_actions[0][0]:
                        at, operation, value = resize_actions.pop(0)
                        if operation == 'configure':
                            response = command('video_configure', mode='fit', window_width=value[0], window_height=value[1])
                        elif operation == 'off':
                            response = command('video_configure', mode='off')
                        elif operation == 'restore':
                            response = command('video_configure', mode=mode)
                        else:
                            from PIL import Image
                            path = out/f'adaptive-{value}.png'
                            response = command('screenshot', path=str(path))
                            assert Image.open(path).width == value, (at, value, Image.open(path).size)
                        assert response.get('ok'), response
                    if frame >= next_frame:
                        data = command('tg2_video')
                        diagnostics.append(dict(frame=frame, video=data))
                        (out/'video.json').write_text(json.dumps(diagnostics, indent=2)+'\n')
                        if data.get('sprite_margin_pixels', 0) and len(margin_shots)<12:
                            path=out/f'margin-{frame}.png'
                            command('screenshot', path=str(path))
                            margin_shots.append(str(path))
                        next_frame += 12
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
    if mode == '21:9' and not a.sweep:
        assert not resize_actions, resize_actions
        summary[mode]['adaptive_widths_and_disable'] = [398,488,320,1195,256]
    if mode != 'off':
        assert any(d['video'].get('sat_matches', 0)>0 for d in diagnostics), 'captured mappings never matched native SAT pieces'
        assert margin_shots, 'no captured sprite pixel ever reached the added margins'
        summary[mode]['margin_screenshots'] = margin_shots
        summary[mode]['max_sprite_margin_pixels'] = max(
            d['video'].get('sprite_margin_pixels', 0) for d in diagnostics)
        summary[mode]['max_margin_pieces'] = max(
            d['video'].get('margin_pieces', 0) for d in diagnostics)
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
