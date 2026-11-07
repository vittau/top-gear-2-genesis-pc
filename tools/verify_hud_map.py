#!/usr/bin/env python3
"""Automated HUD Edges map/marker alignment check.

The track map and its 1ST/1P position markers must move together: both belong
to the right instrument cluster, so in HUD Edges mode every HUD pixel sits at
its native position plus `origin + right` (the centred origin plus the right
margin), and the markers stay on the map outline.

The check captures the same route frames twice — once with widescreen Off (the
stock native picture) and once in a widescreen mode with HUD Edges — and
compares measured bounding boxes rather than eyeballing:

  map     the yellow track outline in the top-right instrument area
  marker  the player marker's orange "1P" label

Both boxes must land at exactly native + (origin + right), and the marker box
must stay inside the map box in the edges picture.

  python3 tools/verify_hud_map.py --port 4600 --out build/hudmap/16-9 \
      --mode 16:9 --step 60 --from 2600 --to 5300
  python3 tools/verify_hud_map.py --pairs build/x/off build/x/16-9-edges
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

# Native instrument area of the right cluster (map, LAP, position). Coordinates
# are native pixels, so the same rectangle finds the cluster in every mode
# after subtracting that mode's origin.
MAP_AREA = (160, 8, 256, 120)
ORANGE = (206, 87, 49)
MANIFESTS = ('dispatch_misses.toml', 'floor_coverage.toml',
             'interior_label_misses.toml', 'floor_unsafe.toml')


def bounds(path: Path, predicate, box):
    from PIL import Image
    image = Image.open(path).convert('RGB')
    pixels = image.load()
    x0, y0, x1, y1 = box
    xs, ys = [], []
    for y in range(max(0, y0), min(y1, image.height)):
        for x in range(max(0, x0), min(x1, image.width)):
            if predicate(pixels[x, y]):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return [min(xs), min(ys), max(xs) + 1, max(ys) + 1]


def is_yellow(p):
    return p[0] > 200 and p[1] > 200 and p[2] < 100


def is_orange(p):
    return all(abs(p[i] - ORANGE[i]) < 16 for i in range(3))


def measure(path: Path, shift: int):
    """Map and marker boxes of one picture, in file coordinates.

    `shift` is where native x=0 sits in the file: 0 for the stock picture, the
    centred origin plus the cluster offset for an Edges picture. Finding the
    cluster at all is part of the check, so the search window moves with it.
    """
    window = (MAP_AREA[0] + shift, MAP_AREA[1], MAP_AREA[2] + shift, MAP_AREA[3])
    return dict(map=bounds(path, is_yellow, window),
                marker=bounds(path, is_orange, window))


def compare(native: Path, edges: Path, origin: int, offset: int):
    n = measure(native, 0)
    e = measure(edges, offset)
    if not n['map'] or not n['marker']:
        # Menus and other non-race screens carry no track map: nothing to check.
        return dict(ok=True, skipped='no instrument map in this frame',
                    native=n, edges=e)
    problems = []
    if not e['map'] or not e['marker']:
        problems.append(f'edges picture has no map/marker at offset {offset}')
    else:
        expected = {k: [v + (offset if i % 2 == 0 else 0) for i, v in enumerate(box)]
                    for k, box in n.items()}
        for key in ('map', 'marker'):
            if e[key] != expected[key]:
                problems.append(f'{key} at {e[key]}, expected {expected[key]} '
                                f'(native {n[key]} + {offset})')
        # The markers must keep their position relative to the map: a cluster
        # that moves while the other stays put changes this displacement.
        rel_native = [n['marker'][i] - n['map'][i] for i in range(4)]
        rel_edges = [e['marker'][i] - e['map'][i] for i in range(4)]
        if rel_native != rel_edges:
            problems.append(f'map/marker split: displacement {rel_edges} in the '
                            f'Edges picture, {rel_native} natively')
        return dict(ok=not problems, problems=problems, native=n, edges=e,
                    expected={k: [v + (offset if i % 2 == 0 else 0)
                                  for i, v in enumerate(box)] for k, box in n.items()})
    return dict(ok=False, problems=problems, native=n, edges=e)


def route_script(route: Path, out: Path, frames: list[int], end: int) -> Path:
    actions: dict[int, list[str]] = {}
    for action in json.loads(route.read_text()):
        if 'keys' not in action:
            continue
        mask = int(action['keys'], 16)
        names = ['UP', 'DOWN', 'LEFT', 'RIGHT', 'B', 'C', 'A', 'START']
        lines = ['RELEASE'] + [f'HOLD {n}' for bit, n in enumerate(names) if mask & (1 << bit)]
        actions.setdefault(action['frame'], []).extend(lines)
    for frame in frames:
        actions.setdefault(frame, []).append(f'SCREENSHOT {out}/frame-{frame}.png')
    lines, previous = [], 1
    for frame, events in sorted(actions.items()):
        if frame > previous:
            lines.append(f'WAIT {frame - previous}')
        lines.extend(events)
        previous = frame
    lines += [f'WAIT {max(0, end - previous)}', 'EXIT 0']
    path = out / 'route.input'
    path.write_text('\n'.join(lines) + '\n')
    return path


def command(port: int, cmd: str, **args):
    with socket.create_connection(('127.0.0.1', port), timeout=5) as s:
        s.sendall((json.dumps(dict(cmd=cmd, id=1, **args)) + '\n').encode())
        return json.loads(s.makefile().readline())


def capture(args, frames, name, mode, hud):
    out = args.out / name
    out.mkdir(parents=True, exist_ok=True)
    script = route_script(args.route, out, frames, args.end)
    (args.exe.parent / 'debug.ini').touch()
    env = dict(os.environ, SDL_VIDEODRIVER='offscreen', SDL_RENDER_DRIVER='software',
               SDL_AUDIODRIVER='dummy', TG2_HIDE_OVERSCAN='0', TG2_RACE_60FPS='0')
    if hud:
        env['TG2_HUD_MODE'] = 'edges'
    env.pop('APPIMAGE', None)
    argv = [str(args.exe), str(args.rom), '--no-launcher', '--port', str(args.port),
            '--widescreen', mode, '--input-script', str(script),
            '--max-frames', str(args.end + 1), '--fresh-evidence', '--turbo']
    with (out / 'stdout.log').open('w') as stdout, (out / 'stderr.log').open('w') as stderr:
        proc = subprocess.Popen(argv, cwd=args.exe.parent, env=env, stdout=stdout, stderr=stderr)
        try:
            ready = time.monotonic() + 30
            while True:
                try:
                    command(args.port, 'frame_info')
                    break
                except OSError:
                    if proc.poll() is not None:
                        raise RuntimeError(f'{name} exited during startup')
                    if time.monotonic() > ready:
                        raise TimeoutError(f'{name}: TCP server never came up')
                    time.sleep(.05)
            while proc.poll() is None:
                time.sleep(.05)
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4600)
    p.add_argument('--out', type=Path, default=ROOT / 'build/hudmap')
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--route', type=Path, default=ROOT / 'game/baseline-route.json')
    p.add_argument('--mode', default='16:9')
    p.add_argument('--step', type=int, default=60)
    p.add_argument('--from', dest='first', type=int, default=2600)
    p.add_argument('--to', dest='last', type=int, default=5300)
    p.add_argument('--end', type=int, default=5340)
    p.add_argument('--pairs', nargs=2, type=Path,
                   help='validate two existing capture directories instead of running')
    p.add_argument('--native-origin', type=int, default=0,
                   help='origin of the native reference picture (0 for Off)')
    a = p.parse_args()
    a.exe, a.out = a.exe.resolve(), a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    frames = list(range(a.first, a.last + 1, a.step))
    if a.pairs:
        native_dir, edges_dir = a.pairs
        from PIL import Image
        origin = (Image.open(next(edges_dir.glob('frame-*.png'))).width - 256) // 2
        width = Image.open(next(edges_dir.glob('frame-*.png'))).width
        right = width - 256 - origin
        offset = origin + right
        results = {}
        for path in sorted(native_dir.glob('frame-*.png')):
            peer = edges_dir / path.name
            if not peer.exists():
                continue
            results[path.stem] = compare(path, peer, origin, offset)
        summary = dict(mode='pairs', origin=origin, offset=offset,
                       frames=len(results),
                       failures=sum(1 for r in results.values() if not r['ok']),
                       skipped=sum(1 for r in results.values() if r.get('skipped')),
                       results=results)
        (a.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps({k: summary[k] for k in ('origin', 'offset', 'frames',
                                                    'failures', 'skipped')}))
        for name, result in results.items():
            if not result['ok']:
                print(name, result['problems'])
        raise SystemExit(0 if summary['failures'] == 0 else 1)
    native_dir = capture(a, frames, 'native', 'off', hud=False)
    edges_dir = capture(a, frames, a.mode.replace(':', '-') + '-edges', a.mode, hud=True)
    from PIL import Image
    sample = Image.open(next(edges_dir.glob('frame-*.png')))
    origin = (sample.width - 256) // 2
    offset = origin + (sample.width - 256 - origin)
    results = {}
    for frame in frames:
        native = native_dir / f'frame-{frame}.png'
        edges = edges_dir / f'frame-{frame}.png'
        if not native.exists() or not edges.exists():
            results[f'frame-{frame}'] = dict(ok=False, problems=['missing capture'])
            continue
        results[f'frame-{frame}'] = compare(native, edges, origin, offset)
    failures = sum(1 for r in results.values() if not r['ok'])
    skipped = sum(1 for r in results.values() if r.get('skipped'))
    summary = dict(mode=a.mode, origin=origin, offset=offset, frames=len(results),
                   failures=failures, skipped=skipped, results=results)
    for name in MANIFESTS:
        for directory in (native_dir, edges_dir):
            path = directory / name
            if path.exists():
                (a.out / f'{directory.name}-{name}').write_text(path.read_text())
    (a.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(dict(mode=a.mode, origin=origin, offset=offset,
                          frames=len(results), failures=failures, skipped=skipped)))
    for name, result in results.items():
        if not result['ok']:
            print(name, result['problems'])
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == '__main__':
    main()
