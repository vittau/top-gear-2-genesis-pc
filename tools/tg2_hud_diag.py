#!/usr/bin/env python3
"""HUD Edges diagnostics: per-scanline raster state plus exact-frame captures.

Replays the baseline controller route through the runner's own input script (so
frame timing is exact), polls the game's `tg2_video {"rows":1}` report while the
frames of interest pass, and writes `diag.json` with the per-row plane A/B
scroll state that the HUD relocation depends on, next to a screenshot per
sample frame.

  python3 tools/tg2_hud_diag.py --port 4600 --out build/hud/diag-16-9 \
      --mode 16:9 --frames 3300,3400,3460,3480,3500,3840,3900
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def route_script(route: Path, out: Path, frames: list[int], end: int,
                 dumps: list[int] = ()) -> Path:
    actions: dict[int, list[str]] = {f: [] for f in frames}
    for action in json.loads(route.read_text()):
        if 'keys' not in action:
            continue
        mask = int(action['keys'], 16)
        names = ['UP', 'DOWN', 'LEFT', 'RIGHT', 'B', 'C', 'A', 'START']
        lines = ['RELEASE'] + [f'HOLD {n}' for bit, n in enumerate(names) if mask & (1 << bit)]
        actions.setdefault(action['frame'], []).extend(lines)
    for frame in frames:
        actions.setdefault(frame, []).append(f'SCREENSHOT {out}/frame-{frame}.png')
    for frame in dumps:
        actions.setdefault(frame, []).extend([f'DUMP_RAM {out}/frame-{frame}.ram',
                                              f'DUMP_VRAM {out}/frame-{frame}.vram'])
    lines, previous = [], 1
    for frame, events in sorted(actions.items()):
        if frame > previous:
            lines.append(f'WAIT {frame - previous}')
        lines.extend(events)
        previous = frame
    lines += [f'WAIT {end - previous}', 'EXIT 0']
    path = out / 'route.input'
    path.write_text('\n'.join(lines) + '\n')
    return path


def command(port: int, cmd: str, **args):
    with socket.create_connection(('127.0.0.1', port), timeout=5) as s:
        s.sendall((json.dumps(dict(cmd=cmd, id=1, **args)) + '\n').encode())
        return json.loads(s.makefile().readline())


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4600)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--route', type=Path, default=ROOT / 'game/baseline-route.json')
    p.add_argument('--mode', default='16:9')
    p.add_argument('--frames', default='3480')
    p.add_argument('--end-frame', type=int, default=4200)
    p.add_argument('--hud', default='edges')
    p.add_argument('--dumps', default='', help='extra exact-frame RAM/VRAM dumps')
    p.add_argument('--turbo', action='store_true')
    a = p.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    frames = [int(x) for x in a.frames.split(',') if x.strip()]
    dumps = [int(x) for x in a.dumps.split(',') if x.strip()]
    script = route_script(a.route, out, frames, a.end_frame, dumps)
    (a.exe.parent / 'debug.ini').touch()
    env = dict(os.environ, SDL_VIDEODRIVER='offscreen' if a.turbo else 'dummy',
               SDL_RENDER_DRIVER='software', SDL_AUDIODRIVER='dummy',
               TG2_HUD_MODE=a.hud, TG2_HIDE_OVERSCAN='0', TG2_RACE_60FPS='0')
    env.pop('APPIMAGE', None)
    argv = [str(a.exe), str(a.rom), '--no-launcher', '--port', str(a.port),
            '--widescreen', a.mode, '--input-script', str(script),
            '--max-frames', str(a.end_frame + 1), '--fresh-evidence', '--turbo']
    with (out / 'stdout.log').open('w') as stdout, (out / 'stderr.log').open('w') as stderr:
        proc = subprocess.Popen(argv, cwd=a.exe.parent, env=env, stdout=stdout, stderr=stderr)
        samples = []
        try:
            ready = time.monotonic() + 20
            while True:
                try:
                    command(a.port, 'frame_info')
                    break
                except OSError:
                    if proc.poll() is not None:
                        raise RuntimeError('runner exited during startup')
                    if time.monotonic() > ready:
                        raise TimeoutError('TCP server never came up')
                    time.sleep(.05)
            lo, hi = min(frames) - 200, max(frames) + 120
            while proc.poll() is None:
                try:
                    frame = command(a.port, 'frame_info')['current_frame']
                    if lo <= frame <= hi:
                        video = command(a.port, 'tg2_video', rows=1, top=1)
                        samples.append(dict(frame=frame, video=video))
                except (ConnectionRefusedError, ConnectionResetError, OSError):
                    pass
                time.sleep(.01)
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)
    (out / 'diag.json').write_text(json.dumps(dict(mode=a.mode, hud=a.hud,
                                                   frames=frames, samples=samples), indent=2) + '\n')
    print(json.dumps(dict(samples=len(samples), frames=[s['frame'] for s in samples][:5],
                          out=str(out))))


if __name__ == '__main__':
    main()
