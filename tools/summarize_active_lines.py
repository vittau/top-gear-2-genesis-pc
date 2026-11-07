#!/usr/bin/env python3
"""Aggregate active-line captures into the evidence table.

Reads the `summary.json` files written by `tools/tg2_active_lines.py` and
re-measures every captured picture with `tools/check_active_lines.py`, so the
table always reflects the current classifier. One markdown row per run.

  python3 tools/summarize_active_lines.py 'build/crop/active/*/summary.json' \
      --out build/crop/active/summary.md
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_active_lines import check  # noqa: E402


def situation(name: str) -> str:
    if name.startswith('pause-'):
        return 'pause'
    if name.startswith('nitro'):
        return 'nitro'
    if name in ('race-start',) or name.startswith('early-'):
        return 'race start'
    if name.startswith('pre-'):
        return 'pre-race panels/countdown'
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
    rows, totals = [], dict(runs=0, pictures=0, race_pictures=0, failures=0,
                            situations=set(), first=None, last=None)
    details = []
    for path in sorted(glob.glob(a.pattern)):
        data = json.loads(Path(path).read_text())
        pictures = []
        for entry in data.get('pictures', []):
            target = Path(entry['path'])
            if not target.exists():
                continue
            info = check(target)
            info['name'] = entry['name']
            info['situation'] = situation(entry['name'])
            pictures.append(info)
        race = [p for p in pictures if p['race_like']]
        if not pictures:
            continue
        firsts = [p['first_picture_row'] for p in race if p['first_picture_row'] is not None]
        lasts = [p['last_picture_row'] for p in race if p['last_picture_row'] is not None]
        bad = [p['name'] for p in pictures if not p['ok']]
        marks = sorted({tuple(p['top_mark_columns']) for p in race if p['top_mark_columns']})
        rows.append(dict(run=Path(path).parent.name, country=data.get('country'),
                         pictures=len(pictures), race=len(race),
                         situations=sorted({p['situation'] for p in pictures}),
                         rows=f'{min(firsts)}..{max(lasts)}' if firsts else '-',
                         marks=', '.join(f'{m[0]}..{m[1]}' for m in marks) or '-',
                         failures=bad,
                         manifests=data.get('manifests')))
        totals['runs'] += 1
        totals['pictures'] += len(pictures)
        totals['race_pictures'] += len(race)
        totals['failures'] += len(bad)
        totals['situations'].update(p['situation'] for p in pictures)
        details.append(dict(run=Path(path).parent.name, country=data.get('country'),
                            race_rows=[min(firsts), max(lasts)] if firsts else None,
                            situations=sorted({p['situation'] for p in pictures}),
                            pictures=[dict(name=p['name'], race=p['race_like'],
                                           top=p['top_ok'], bottom=p['bottom_ok'],
                                           first=p['first_picture_row'],
                                           last=p['last_picture_row'])
                                      for p in pictures]))
    lines = ['| run | country | pictures | race pictures | situations | picture rows '
             '| window-mark columns | band failures |',
             '|---|---:|---:|---:|---|---|---|---:|']
    for row in rows:
        lines.append(
            f"| `{row['run']}` | {row['country']} | {row['pictures']} | {row['race']} | "
            f"{', '.join(row['situations'])} | {row['rows']} | {row['marks']} | "
            f"{len(row['failures'])} |")
    text = '\n'.join(lines) + '\n'
    print(text)
    print(json.dumps(dict(runs=totals['runs'], pictures=totals['pictures'],
                          race_pictures=totals['race_pictures'],
                          failures=totals['failures'],
                          situations=sorted(totals['situations']))))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text)
        a.out.with_suffix('.json').write_text(json.dumps(dict(
            table=rows, details=details, totals=dict(
                runs=totals['runs'], pictures=totals['pictures'],
                race_pictures=totals['race_pictures'],
                failures=totals['failures'],
                situations=sorted(totals['situations']))), indent=2) + '\n')
    raise SystemExit(0 if totals['failures'] == 0 else 1)


if __name__ == '__main__':
    main()
