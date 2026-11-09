#!/usr/bin/env python3
"""Prove the presented geometry on any panel aspect, without a real device.

Runs the native build headless (SDL dummy driver) and uses the dev-only
`video_configure` command to make the window exactly as large as a 16:10 Deck
panel (1280x800), a 16:9 TV (1280x720) and a 4:3 monitor (1024x768). For each
output size and presentation mode it records:

  * the geometry the game computed: `[VIDEO] display/window/output/picture`
    lines from stderr (the adaptive renderer follows SDL_GetRendererOutputSize);
  * the size of the presented window capture (SDL output, bars included);
  * the size of the game picture capture (the framebuffer the game composed);
  * the non-black bounding box inside the presented capture, as a rough
    placement check. Advisory only: this capture is requested from the TCP
    thread, so under the dummy driver it can catch a half-presented buffer.
    The engine's own output/picture aspect pair is the authoritative number.

`--race` boots a 1P race first (the same controller-only route the release
smoke uses), so the numbers are the cropped 200-line race picture a player
sees, not the 224-line title screen.

  python3 tools/tg2_aspect_probe.py --port 4450 --out build/aspect

Needs no third-party modules: the engine writes stored-deflate RGB PNGs.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import struct
import subprocess
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Same route as tools/tg2_release_smoke.py: title -> main menu -> 1P GAME row
# -> setup -> intro -> race.
RACE_ROUTE = """\
WAIT 1300
PRESS START 8
WAIT 960
PRESS DOWN 8
WAIT 1000
PRESS DOWN 8
WAIT 1055
PRESS DOWN 8
WAIT 1110
PRESS DOWN 8
WAIT 1165
WAIT 1300
PRESS START 8
WAIT 1650
PRESS START 7
WAIT 900
"""


def read_png(path: Path):
    """Decode the engine's PNG (8-bit RGB, filter 0, stored deflate)."""
    data = path.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', path
    pos, width, height, idat = 8, 0, 0, b''
    while pos < len(data):
        (length,) = struct.unpack('>I', data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if kind == b'IHDR':
            width, height = struct.unpack('>II', body[:8])
            bit, color, _, _, interlace = body[8:13]
            assert (bit, color, interlace) == (8, 2, 0), (bit, color, interlace)
        elif kind == b'IDAT':
            idat += body
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = width * 3
    rows = []
    for y in range(height):
        base = y * (stride + 1)
        assert raw[base] == 0, 'only filter 0 is produced'
        rows.append(raw[base + 1:base + 1 + stride])
    return width, height, rows


def picture_box(path: Path):
    """Non-black bounding box of a decoded capture, as (x, y, w, h)."""
    width, height, rows = read_png(path)
    left, right, top, bottom = width, -1, -1, -1
    for y, row in enumerate(rows):
        for x in range(width):
            if row[x * 3] > 24 or row[x * 3 + 1] > 24 or row[x * 3 + 2] > 24:
                if x < left:
                    left = x
                if x > right:
                    right = x
                if top < 0:
                    top = y
                bottom = y
    if right < 0:
        return (0, 0, 0, 0)
    return (left, top, right - left + 1, bottom - top + 1)


def command(port, cmd, **args):
    with socket.create_connection(('127.0.0.1', port), timeout=5) as s:
        s.sendall((json.dumps(dict(cmd=cmd, id=1, **args)) + '\n').encode())
        return json.loads(s.makefile().readline())


def wait_frames(port, current, count, timeout=120):
    deadline = time.monotonic() + timeout
    target = current + count
    while time.monotonic() < deadline:
        try:
            frame = command(port, 'frame_info')['current_frame']
        except OSError:
            time.sleep(0.05)
            continue
        if frame >= target:
            return frame
        time.sleep(0.02)
    raise TimeoutError(f'{count} frames did not elapse')


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--out', type=Path, default=ROOT / 'build/aspect')
    p.add_argument('--port', type=int, default=4450)
    p.add_argument('--modes', default='fit,16:9')
    p.add_argument('--sizes', default='1280x800,1280x720,1024x768')
    p.add_argument('--race', action='store_true')
    p.add_argument('--timeout', type=int, default=300)
    a = p.parse_args()
    a.exe, a.out = a.exe.resolve(), a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    (a.exe.parent / 'debug.ini').touch()

    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy',
               SDL_RENDER_DRIVER='software')
    env.pop('APPIMAGE', None)
    argv = [str(a.exe), str(a.rom), '--no-launcher', '--port', str(a.port),
            '--widescreen', 'fit', '--turbo', '--fresh-evidence']
    if a.race:
        route = a.out / 'route.input'
        route.write_text(RACE_ROUTE)
        argv += ['--input-script', str(route)]
    else:
        argv += ['--max-frames', '4000']

    sizes = [tuple(int(v) for v in s.split('x')) for s in a.sizes.split(',')]
    modes = a.modes.split(',')
    report = {'exe': str(a.exe), 'race': a.race, 'cases': []}
    log = (a.out / 'stderr.log').open('w')
    proc = subprocess.Popen(argv, cwd=a.exe.parent, env=env,
                            stdout=subprocess.DEVNULL, stderr=log)
    stderr_path = a.out / 'stderr.log'
    deadline = time.monotonic() + a.timeout
    try:
        while True:
            try:
                frame = command(a.port, 'frame_info')['current_frame']
                break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError('exited before the TCP server appeared')
                if time.monotonic() > deadline:
                    raise TimeoutError('TCP server never appeared')
                time.sleep(0.1)
        if a.race:
            # Wait for the crop to prove the race picture is on screen: the
            # runner prints 200 picture lines (224 minus the hidden overscan
            # bands) only while a 1P race is presented.
            while time.monotonic() < deadline:
                text = stderr_path.read_text(errors='replace')
                race_on = False
                for line in text.splitlines():
                    if '[VIDEO] output' not in line:
                        continue
                    m = re.search(r'picture (\d+)x(\d+)', line)
                    if m and m.group(2) == '200':
                        race_on = True
                if race_on:
                    break
                if proc.poll() is not None:
                    raise RuntimeError('exited before the race started')
                frame = command(a.port, 'frame_info')['current_frame']
                time.sleep(0.1)
            else:
                raise TimeoutError('the race picture never appeared')
        for mode in modes:
            for (w, h) in sizes:
                answer = command(a.port, 'video_configure', mode=mode,
                                 window_width=w, window_height=h)
                assert answer.get('ok'), answer
                frame = wait_frames(a.port, frame, 25)
                tag = f'{mode.replace(":", "-")}-{w}x{h}'
                presented = a.out / f'presented-{tag}.png'
                picture = a.out / f'picture-{tag}.png'
                command(a.port, 'screenshot', path=str(presented), presented=1)
                command(a.port, 'screenshot', path=str(picture))
                out_w, out_h, _ = read_png(presented)
                pic_w, pic_h, _ = read_png(picture)
                box = picture_box(presented)
                geometry = ''
                for line in (a.out / 'stderr.log').read_text(errors='replace').splitlines():
                    if line.startswith('[VIDEO] output '):
                        geometry = line
                report['cases'].append(dict(
                    mode=mode, requested=f'{w}x{h}', frame=frame,
                    engine_geometry=geometry,
                    presented_png=f'{out_w}x{out_h}',
                    picture_png=f'{pic_w}x{pic_h}',
                    picture_box_advisory=dict(x=box[0], y=box[1],
                                              w=box[2], h=box[3]),
                    presented=str(presented), picture_capture=str(picture)))
                print(json.dumps(report['cases'][-1]))
    finally:
        try:
            command(a.port, 'quit')
        except OSError:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=20)
        except (subprocess.TimeoutExpired, OSError):
            proc.kill()
        log.close()

    # Geometry lines the runner printed for each case.
    geometry = []
    for line in (a.out / 'stderr.log').read_text(errors='replace').splitlines():
        if line.startswith('[VIDEO] ') and (' display ' in line or ' window ' in line
                                            or ' output ' in line):
            geometry.append(line)
    report['geometry'] = geometry
    (a.out / 'aspect.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'cases': len(report['cases']), 'report': str(a.out / 'aspect.json')}))


if __name__ == '__main__':
    main()
