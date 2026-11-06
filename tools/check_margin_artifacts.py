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
    totals = dict(rows=0, frames=0, black_violations=0, examples=[])
    frames = set()
    with Path(path).open() as source:
        for record in csv.DictReader(source):
            row = {key: int(value) for key, value in record.items()}
            frames.add(row['frame'])
            totals['rows'] += 1
            if row['margin'] & 0xffffff == 0 and row['native'] & 0xffffff:
                totals['black_violations'] += 1
                if len(totals['examples']) < 20:
                    totals['examples'].append(row)
    totals['frames'] = len(frames)
    totals['passed'] = totals['rows'] > 0 and not totals['black_violations']
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
