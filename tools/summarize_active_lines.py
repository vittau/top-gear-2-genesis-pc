#!/usr/bin/env python3
"""Aggregate active-line captures into the evidence table.

Reads the `summary.json` files written by `tools/tg2_active_lines.py` (and any
`tools/check_active_lines.py --out` result files) and prints one markdown row
per run: the situations captured, which rows carried picture content and
whether either cropped band was ever non-empty.

  python3 tools/summarize_active_lines.py 'build/crop/active/*/summary.json' \
      --out build/crop/active/summary.md
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

SITUATIONS = ('pre-', 'early-', 'race-start', 'race-', 'nitro-', 'pause-', 'resume')


def classify(name: str) -> str:
    if name.startswith('pause-'):
        return 'pause'
    if name.startswith('nitro'):
        return 'nitro'
    if name.startswith('early-') or name == 'race-start':
        return 'countdown/first seconds'
    if name.startswith('pre-'):
        return 'intro/transition'
    if name.startswith('race-'):
        return 'cruise'
    if name.startswith('resume'):
        return 'resume'
    return 'other'


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('pattern', help='glob for summary.json files')
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    rows = []
    totals = dict(runs=0, pictures=0, failures=0, situations=set())
    for path in sorted(glob.glob(a.pattern)):
        data = json.loads(Path(path).read_text())
        pictures = data.get('pictures', [])
        if not pictures:
            continue
        situations = {}
        for picture in pictures:
            situations.setdefault(classify(picture['name']), []).append(picture)
        first = min(p['first_picture_row'] for p in pictures if p['first_picture_row'] is not None)
        last = max(p['last_picture_row'] for p in pictures if p['last_picture_row'] is not None)
        bad = [p['name'] for p in pictures if not p['ok']]
        window = [p for p in pictures if p['top_window_rows']]
        marks = [p['top_mark_columns'] for p in window if p['top_mark_columns']]
        rows.append(dict(
            run=Path(path).parent.name, country=data.get('country'),
            result=data.get('result'), pictures=len(pictures),
            situations=sorted(situations),
            rows=f'{first}..{last}',
            top_mark_columns=sorted({tuple(m) for m in marks}),
            manifests=data.get('manifests'), failures=bad))
        totals['runs'] += 1
        totals['pictures'] += len(pictures)
        totals['failures'] += len(bad)
        totals['situations'].update(situations)
    lines = ['| run | country | pictures | situations | picture rows | window-mark columns '
             '| band failures |', '|---|---:|---:|---|---|---|---|']
    for row in rows:
        lines.append(
            f"| `{row['run']}` | {row['country']} | {row['pictures']} | "
            f"{', '.join(row['situations'])} | {row['rows']} | "
            f"{', '.join(f'{m[0]}..{m[1]}' for m in row['top_mark_columns']) or '-'} | "
            f"{len(row['failures'])} |")
    text = '\n'.join(lines) + '\n'
    print(text)
    print(json.dumps(dict(runs=totals['runs'], pictures=totals['pictures'],
                          failures=totals['failures'],
                          situations=sorted(totals['situations']))))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text)
    raise SystemExit(0 if totals['failures'] == 0 else 1)


if __name__ == '__main__':
    main()
