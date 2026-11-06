#!/usr/bin/env python3
"""Audit widescreen-margin continuity for coverage screenshots.

For a 16:9 frame the native 256-pixel image sits in the centre
(columns 71..326 of 398). This tool checks the two seams where the native
centre meets the generated margin and compares each seam step against the
distribution of ordinary adjacent-column steps in the same frame, then builds
a contact sheet for visual review.

  python3 tools/tg2_margin_audit.py --cov build/qual/cov \
      --out build/qual/margin-audit
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from PIL import Image

NATIVE_W = 256
NATIVE_H = 224


def column_steps(img: Image.Image):
    px = img.convert('RGB').load()
    w, h = img.size
    steps = []
    for x in range(1, w):
        total = 0
        for y in range(h):
            a = px[x - 1, y]
            b = px[x, y]
            total += abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])
        steps.append(total / (h * 3.0))
    return steps


def audit_frame(path: Path) -> dict:
    img = Image.open(path)
    w, h = img.size
    out = dict(path=str(path), size=[w, h])
    if w <= NATIVE_W:
        out['native_only'] = True
        return out
    left = (w - NATIVE_W) // 2
    right = left + NATIVE_W - 1
    steps = column_steps(img)
    # steps[x-1] is the step between column x-1 and x
    seam_left = steps[left - 1]
    seam_right = steps[right]
    interior = [s for i, s in enumerate(steps) if 0 < i < len(steps) - 1
                and not (left - 3 <= i <= left + 2)
                and not (right - 2 <= i <= right + 3)]
    med = statistics.median(interior) if interior else 0.0
    p99 = sorted(interior)[int(len(interior) * 0.99)] if interior else 0.0
    out.update(left=left, right=right, seam_left=round(seam_left, 2),
               seam_right=round(seam_right, 2), median_step=round(med, 2),
               p99_step=round(p99, 2),
               seam_ratio=max(round(seam_left / med, 2) if med else 0,
                              round(seam_right / med, 2) if med else 0))
    # Flag only seams that are far outside the frame's own step distribution.
    out['seam_flag'] = bool(med and (seam_left > max(p99 * 3, med * 8)
                                     or seam_right > max(p99 * 3, med * 8)))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cov', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--per-run', type=int, default=4)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    report = []
    sheets = []
    for run in sorted(a.cov.iterdir()):
        if not run.is_dir():
            continue
        shots = sorted(p for p in run.glob('race-*.png'))
        if not shots:
            continue
        chosen = shots[::max(1, len(shots) // a.per_run)][:a.per_run]
        entries = []
        for shot in chosen:
            entry = audit_frame(shot)
            entry['run'] = run.name
            entries.append(entry)
            report.append(entry)
        # contact sheet of this run's chosen frames
        ims = [Image.open(p) for p in chosen]
        w = max(i.size[0] for i in ims)
        h = sum(i.size[1] for i in ims)
        sheet = Image.new('RGB', (w, h))
        y = 0
        for im in ims:
            sheet.paste(im, (0, y))
            y += im.size[1]
        sheet_path = a.out / f'{run.name}-sheet.png'
        sheet.save(sheet_path)
        sheets.append(dict(run=run.name, sheet=str(sheet_path),
                           frames=[e['path'] for e in entries],
                           flagged=[e['path'] for e in entries if e.get('seam_flag')]))
    (a.out / 'margin-audit.json').write_text(json.dumps(dict(frames=report,
                                                             sheets=sheets),
                                                        indent=2) + '\n')
    bad = [e for e in report if e.get('seam_flag')]
    print(f'{len(report)} frames audited, {len(bad)} seam outliers')
    for e in bad[:20]:
        print(' ', e['run'], Path(e['path']).name, 'ratio', e['seam_ratio'],
              'L', e['seam_left'], 'R', e['seam_right'], 'median', e['median_step'])


if __name__ == '__main__':
    main()
