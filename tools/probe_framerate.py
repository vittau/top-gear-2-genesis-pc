#!/usr/bin/env python3
"""Deterministic baseline-route race cadence capture, one owned PID on port 4410.

Produces private RAM/VRAM/PNG evidence only below the selected build directory.
The runner's input script executes at exact wall frames, avoiding TCP input jitter.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--road-audit', action='store_true',
                   help='check every synthesized baseline road row against its real neighbours')
    p.add_argument('--strip-start', type=int, action='append', default=[],
                   help='12-frame road strip at this wall frame (audit defaults: start and 4500)')
    p.add_argument('--out', type=Path, default=ROOT / 'build/fps/stock')
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--60fps', dest='fps60', action='store_true')
    p.add_argument('--widescreen', default='off')
    p.add_argument('--hud', choices=['centered', 'edges'], default='centered')
    p.add_argument('--turbo', action='store_true')
    p.add_argument('--extra', nargs='*', default=[])
    p.add_argument('--port', type=int, default=4410)
    p.add_argument('--start', type=int, default=3600)
    p.add_argument('--count', type=int, default=360)
    p.add_argument('--shots', default='', help='comma-separated extra frame screenshots')
    a = p.parse_args()
    if a.road_audit and not a.fps60:
        p.error('--road-audit requires --60fps')
    strips = sorted(set(a.strip_start or ([a.start, 4500] if a.road_audit else [])))
    a.out = a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    a.exe = a.exe.resolve()
    (a.exe.parent / 'debug.ini').touch()
    # Fail on this port only; other worktrees may have their own runtime.
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', a.port)) == 0:
            p.error(f'port {a.port} is occupied')
    actions = {}
    names = ['UP', 'DOWN', 'LEFT', 'RIGHT', 'B', 'C', 'A', 'START']
    for row in json.loads((ROOT / 'game/baseline-route.json').read_text()):
        if 'keys' in row:
            mask = int(row['keys'], 16)
            actions.setdefault(row['frame'], []).extend(
                ['RELEASE'] + [f'HOLD {name}' for i, name in enumerate(names) if mask & (1 << i)])
    for frame in range(a.start, a.start + a.count + 1):
        actions.setdefault(frame, []).extend([
            f'DUMP_RAM {a.out}/ram-{frame}.ram',
            f'DUMP_VRAM {a.out}/vram-{frame}.vram'])
    for frame in [3300, 4500, 5200]:
        actions.setdefault(frame, []).append(f'DUMP_RAM {a.out}/ram-{frame}.ram')
    for frame in range(a.start, a.start + 6):
        actions.setdefault(frame, []).append(f'SCREENSHOT {a.out}/frame-{frame}.png')
    shot_frames = {int(x) for x in a.shots.split(',') if x.strip()}
    shot_frames.update(f for start in strips for f in range(start, start + 12))
    for frame in sorted(shot_frames):
        actions.setdefault(frame, []).append(f'SCREENSHOT {a.out}/shot-{frame}.png')
    script = []
    # input_script_tick first runs at wall frame 1.
    previous = 1
    for frame, lines in sorted(actions.items()):
        script.extend([f'WAIT {frame - previous}', *lines])
        previous = frame
    script_path = a.out / 'route.input'
    script_path.write_text('\n'.join(script) + '\n')
    env = dict(os.environ, SDL_VIDEODRIVER='offscreen' if a.turbo else 'dummy',
               SDL_RENDER_DRIVER='software', SDL_AUDIODRIVER='dummy',
               TG2_RACE_60FPS='1' if a.fps60 else '0', TG2_HUD_MODE=a.hud)
    # A host $APPIMAGE would anchor debug.ini/saves/evidence to the AppImage
    # directory and move the TCP server away from this build.
    env.pop('APPIMAGE', None)
    if a.road_audit:
        audit = a.out / 'audit'
        audit.mkdir(exist_ok=True)
        for stale in audit.glob('frame-*.road'):
            stale.unlink()
        env['TG2_ROAD_AUDIT_DIR'] = str(audit)
    args = [str(a.exe), str(Path.home() / 'roms/genesis/tg2.bin'), '--no-launcher',
            '--port', str(a.port), '--widescreen', a.widescreen, '--max-frames', str(max(5600, previous + 2)),
            '--hash-frames', '1', '--fresh-evidence', '--input-script', str(script_path),
            '--wav', str(a.out / 'audio.wav'), *a.extra]
    if a.turbo:
        args.append('--turbo')
    with (a.out / 'stdout.log').open('w') as out, (a.out / 'stderr.log').open('w') as err:
        proc = subprocess.Popen(args, cwd=a.exe.parent, env=env, stdout=out, stderr=err)
        try:
            code = proc.wait(timeout=240)
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)
    for name in ['dispatch_misses.toml', 'floor_coverage.toml', 'interior_label_misses.toml', 'floor_unsafe.toml']:
        src = a.exe.parent / name
        if src.exists():
            (a.out / name).write_bytes(src.read_bytes())
    for frame in range(a.start, a.start + 6):
        shot, canonical = a.out / f'shot-{frame}.png', a.out / f'frame-{frame}.png'
        if shot.exists():
            canonical.write_bytes(shot.read_bytes())
    audit_result = None
    if code == 0 and a.road_audit:
        cmd = [sys.executable, str(ROOT / 'tools/check_road_artifacts.py'), str(a.out)]
        for start in strips:
            cmd += ['--strip-start', str(start)]
        with (a.out / 'road-check.log').open('w') as log:
            check = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
        if check.returncode:
            code = check.returncode
        report = a.out / 'road-artifacts.json'
        if report.exists():
            audit_result = json.loads(report.read_text())
    hashes = {int(f): h for f, h in re.findall(r'\[FBHASH\] frame=(\d+).*?hash=0x([A-F0-9]+)', (a.out / 'stderr.log').read_text())}
    if code == 0 and (max(5600, previous + 2) not in hashes or
                      any(f not in hashes for f in range(a.start, a.start + a.count + 1))):
        raise RuntimeError('runtime ended without the complete measurement window')
    changes = [f for f in range(a.start + 1, a.start + a.count + 1) if hashes.get(f) != hashes.get(f - 1)]
    summary = dict(exit=code, command=args, race_headroom=env.get('TG2_RACE_HEADROOM', '0'),
                   cold_boot={f: hashes.get(f) for f in [60, 300]},
                   start=a.start, frames=a.count, changed_pictures=len(changes),
                   pictures_per_60_frames=len(changes) * 60 / a.count,
                   intervals=dict(Counter(b - c for c, b in zip(changes, changes[1:]))),
                   changes=changes, road_artifacts=audit_result)
    (a.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    raise SystemExit(code)


if __name__ == '__main__':
    main()
