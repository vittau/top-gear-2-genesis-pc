#!/usr/bin/env python3
"""Task 39 deterministic motion evidence. Run under the shared heavy lock.

record uses an ignored race checkpoint and controller input only. trace streams
per-presented-frame diagnostics; no ROM-derived assets enter the repository.
compare streams traces one frame at a time, matches record/lateral/depth, and
separates physical growth from unexplained size changes at art boundaries.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
from collections import defaultdict
from pathlib import Path

from tg2_runner import ROOT, Runner, manifest_counts
from check_highres import wait_exit


def record(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    lines = [f'LOAD_STATE {args.state.resolve()}', 'WAIT 40', 'HOLD B']
    if args.pictures:
        pictures = out / 'pictures'
        pictures.mkdir(exist_ok=True)
        for i in range(args.frames):
            lines += ['WAIT 1', f'SCREENSHOT {pictures}/{i:05}.png']
    else:
        lines += [f'WAIT {args.frames}']
    lines += [f'DUMP_RAM {out}/end.ram', 'WAIT 2', 'EXIT 0']
    script = out / 'run.input'
    script.write_text('\n'.join(lines) + '\n')
    r = Runner(out=out, exe=args.exe, port=4494, widescreen='16:9',
               max_frames=args.frames+200, env_extra={
                   'TG2_HIGHRES_SCALE': '4', 'TG2_RACE_60FPS': '1',
                   'TG2_ACTOR_SIZE': args.policy,
                   'TG2_ACTOR_TRACE': str(out / 'actors.csv'),
                   'TG2_ACTOR_LOG': str(out / 'guest.csv'),
                   'TG2_ACTOR_AUDIT': '1'},
               extra_args=['--turbo', '--input-script', str(script)])
    try:
        r.start()
        wait_exit(r, timeout=300)
    finally:
        code = r.stop()
    result = dict(exit=code, manifests=manifest_counts(out), policy=args.policy,
                  frames=args.frames, state=str(args.state), exe=str(args.exe))
    result['ok'] = code == 0 and all(v == 0 for v in result['manifests'].values())
    (out / 'run.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


def frames(path):
    with path.open() as stream:
        for frame, rows in itertools.groupby(csv.DictReader(stream), lambda a: int(a['frame'])):
            yield frame, [{k: float(v) for k, v in row.items()} for row in rows]


def measure(path):
    stats = defaultdict(lambda: dict(pairs=0, boundaries=0, max_jump=0.,
                                    max_boundary_jump=0., max_residual=0.,
                                    max_boundary_residual=0., residual_over_threshold=0,
                                    max_reference_error=0., changing=0, repeated=0, examples=[]))
    previous, old_frame = [], -2
    for frame, actors in frames(path):
        if frame <= 40:
            continue  # checkpoint history warm-up, before the scripted drive
        used = set()
        if frame != old_frame + 1:
            previous = []
        for a in actors:
            if not a['promoted'] or not a['pixels']:
                continue
            best, distance = None, 3.
            for i, p in enumerate(previous):
                if i in used or p['record'] != a['record']:
                    continue
                if not a['car'] and p['lateral'] != a['lateral']:
                    continue
                if 'identity' in a and p.get('identity') != a['identity']:
                    continue
                d = abs(a['depth'] - p['depth'])
                if a['car']:
                    d += abs(a['x'] - p['x']) * .02
                if d < distance:
                    best, distance = i, d
            if best is None:
                continue
            used.add(best)
            p = previous[best]
            if not p['promoted'] or not p['pixels'] or p['size'] <= 0:
                continue
            key = 'car' if a['car'] else f"{int(a['kind']):02X}"
            s = stats[key]
            reference = (2816 * (2218 if a['car'] else 1830)) ** .5
            s['max_reference_error'] = max(s['max_reference_error'],
                                           abs(a['size'] * reference / a['projection'] - 1))
            jump = abs(a['size'] / p['size'] - 1)
            projected = a['projection'] / p['projection']
            residual = abs((a['size'] / p['size']) / projected - 1)
            boundary = a['level'] != p['level']
            s['pairs'] += 1
            s['boundaries'] += boundary
            s['max_jump'] = max(s['max_jump'], jump)
            s['max_residual'] = max(s['max_residual'], residual)
            if boundary:
                s['max_boundary_jump'] = max(s['max_boundary_jump'], jump)
                s['max_boundary_residual'] = max(s['max_boundary_residual'], residual)
            s['residual_over_threshold'] += residual > .001
            s['changing'] += jump > 1e-7
            s['repeated'] += jump <= 1e-7
            if residual > .001 and len(s['examples']) < 3:
                s['examples'].append(dict(frame=frame, depth=a['depth'], jump=jump,
                                          residual=residual, boundary=boundary))
        previous, old_frame = actors, frame
    return stats


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    r = sub.add_parser('record')
    r.add_argument('--state', type=Path, required=True)
    r.add_argument('--out', type=Path, required=True)
    r.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    r.add_argument('--policy', choices=['stepped', 'continuous'], required=True)
    r.add_argument('--frames', type=int, default=900)
    r.add_argument('--pictures', action='store_true')
    a = sub.add_parser('analyze')
    a.add_argument('trace', type=Path, nargs='+')
    a.add_argument('--out', type=Path, required=True)
    a.add_argument('--continuous', action='store_true',
                   help='gate residuals and independent ROM reference to 0.1%%')
    args = p.parse_args()
    if args.action == 'record':
        return record(args)
    result = {str(path): measure(path) for path in args.trace}
    failures = []
    if args.continuous:
        kinds = {kind for run in result.values() for kind in run}
        if not {'car', '94', '99', 'F0'} <= kinds:
            failures.append('missing car/tree/barrel/sign motion samples')
        for path, run in result.items():
            for kind, values in run.items():
                if values['residual_over_threshold'] or values['max_reference_error'] > .001:
                    failures.append(f'{path}: {kind} exceeds 0.1% size/projection tolerance')
        result['gate'] = dict(ok=not failures, failures=failures, threshold=.001)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
