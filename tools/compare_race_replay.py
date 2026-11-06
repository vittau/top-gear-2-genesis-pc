#!/usr/bin/env python3
"""Compare exact per-V-int state-trace.csv captures from tg2_replay_route.py."""
import argparse
import csv
import json
from pathlib import Path

NUMERIC = ('clock', 'lap', 'pos', 'lat_raw', 'view', 'speed', 'speed2', 'curv', 'slope', 'builds')
HASHES = ('player_sha256', 'wram_sha256')


def read(path):
    with (path / 'state-trace.csv').open() as f:
        return {int(r['frame']): r for r in csv.DictReader(f)}


def laps(trace):
    previous_clock = 0
    previous_lap = None
    split_clock = 0
    stall = 0
    result = []
    for frame, row in sorted(trace.items()):
        clock, lap = int(row['clock']), int(row['lap'])
        if not clock:
            previous_lap = lap
            continue
        if previous_lap is not None and lap != previous_lap:
            result.append(dict(lap=lap, frame=frame, ticks=clock - split_clock,
                               seconds=round((clock - split_clock) / 65536 / 50, 4)))
            split_clock = clock
        stall = stall + 1 if clock == previous_clock else 0
        if stall == 12 and int(row['speed']) == 0:
            if clock > split_clock:
                result.append(dict(lap=lap + 1, frame=frame, ticks=clock - split_clock,
                                   seconds=round((clock - split_clock) / 65536 / 50, 4)))
            break
        previous_clock, previous_lap = clock, lap
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stock', type=Path)
    p.add_argument('presentation', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    left, right = read(a.stock), read(a.presentation)
    common = sorted(left.keys() & right.keys())
    max_diff = {k: 0 for k in NUMERIC}
    hash_diff = {k: 0 for k in HASHES}
    first = None
    logic_steps = 0
    previous_build = None
    for frame in common:
        x, y = left[frame], right[frame]
        different = False
        for k in NUMERIC:
            delta = abs(int(x[k]) - int(y[k]))
            max_diff[k] = max(max_diff[k], delta)
            different |= delta != 0
        for k in HASHES:
            delta = x[k] != y[k]
            hash_diff[k] += delta
            different |= delta
        if different and first is None:
            first = frame
        if int(x['builds']) != previous_build:
            logic_steps += 1
        previous_build = int(x['builds'])
    missing = dict(stock_only=sorted(left.keys() - right.keys()),
                   presentation_only=sorted(right.keys() - left.keys()))
    result = dict(frames=len(common), first_frame=common[0] if common else None,
                  last_frame=common[-1] if common else None,
                  stock_picture_steps=logic_steps, first_divergent_frame=first,
                  max_abs_diff=max_diff, hash_differing_frames=hash_diff,
                  missing=missing, stock_laps=laps(left), presentation_laps=laps(right))
    result['identical'] = bool(common) and first is None and not any(missing.values())
    a.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['identical'] else 1)


if __name__ == '__main__':
    main()
