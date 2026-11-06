#!/usr/bin/env python3
"""Check every race scanline exported by TG2_MARGIN_AUDIT.

The trace is emitted before sprites/HUD can cover a margin defect. Native edge
colours come from the native row producer, including 60 fps synthesis, rather
than from the margin renderer. Captures stay private under build/.
"""
import argparse
import csv
import json
from pathlib import Path


def check(path):
    totals = dict(rows=0, frames=0, black_violations=0, ground_colour_violations=0, examples=[])
    frames, slopes, lines = {}, set(), set()
    with Path(path).open() as source:
        for record in csv.DictReader(source):
            row = {key: int(value) for key, value in record.items()}
            frames[row['frame']] = frames.get(row['frame'], 0) | (1 << (row['line'] * 2 + row['side']))
            slopes.add(row['slope'])
            lines.add(row['line'])
            totals['rows'] += 1
            # Opaque black panorama art and native plane-A effects are not
            # the backdrop gap: require visible scenery at the native edge.
            black = (row['margin'] & 0xffffff == 0 and row['native'] & 0xffffff
                     and row['native_b'] & 0xffffff and not row['margin_bp'])
            ground = (row['native'] & 0xffffff and row['bp'] in (5, 15, 21, 31)
                      and (432 <= row['atlas_y'] < 448
                           or row['margin_bp'] in (5, 15, 21, 31))
                      and row['margin'] != row['native_b'])
            totals['ground_colour_violations'] += int(ground)
            if black:
                totals['black_violations'] += 1
            if (black or ground) and len(totals['examples']) < 20:
                row['source'] = ('road' if row['atlas_y'] < 432 else
                                 'ground/separator' if row['atlas_y'] < 448 else 'panorama')
                totals['examples'].append(row)
    totals['frames'] = len(frames)
    totals['incomplete_frames'] = [f for f, coverage in frames.items()
                                  if coverage != (1 << 448) - 1]
    totals['line_range'] = [min(lines), max(lines)] if lines else []
    totals['slope_range'] = [min(slopes), max(slopes)] if slopes else []
    totals['passed'] = (totals['rows'] > 0 and not totals['incomplete_frames']
                        and not totals['black_violations']
                        and not totals['ground_colour_violations'])
    return totals


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace', type=Path)
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    result = check(a.trace)
    if a.out:
        a.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
