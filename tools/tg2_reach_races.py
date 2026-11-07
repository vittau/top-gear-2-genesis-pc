#!/usr/bin/env python3
"""Drive the championship races a password cannot reach, one process per race.

The password loader only ever resumes at a country's first race: the packer
drops the low two bits of the race index (`$023A12..$023A18`, index/4), so it
can name a country but not a slot. The game itself loads the intro panel and
the race scene from `$FF16BE` (descriptor store at `$001E5E`), so setting that
word on the game-setup screen selects slot 2..4 of the country whose password
was just typed. Nothing else is written: the race then runs on the release
defaults with controller input only.

`tools/tg2_progress.py --start-slot N` performs one cell; this driver walks
the missing cells (see docs/tasks/25-state-load-and-coverage.md) and writes
`build/qual/qa-reach/cNN-sN/` per race.

  python3 tools/tg2_reach_races.py --out build/qual/qa-reach
  python3 tools/tg2_reach_races.py --out build/qual/qa-reach --only 3-1,3-2
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

# Races the top-ten gate stopped in the task-22 progression runs (country, slot).
MISSING = [
    (2, 3),                                     # Canada 4
    (3, 1), (3, 2), (3, 3),                     # Egypt 2-4
    (7, 1), (7, 2), (7, 3),                     # India 2-4
    (9, 3),                                     # Italy 4
    (11, 2), (11, 3),                           # Scandinavia 3-4
    (12, 2), (12, 3),                           # South America 3-4
    (13, 2), (13, 3),                           # Spain 3-4
    (14, 1), (14, 2), (14, 3),                  # Switzerland 2-4
    (15, 2), (15, 3),                           # U.S.A. 3-4
]
COUNTRIES = ['Australasia', 'Britain', 'Canada', 'Egypt', 'France', 'Germany',
             'Greece', 'India', 'Ireland', 'Italy', 'Japan', 'Scandinavia',
             'South America', 'Spain', 'Switzerland', 'U.S.A.']


def cell_id(c: int, s: int) -> str:
    return f'c{c:02d}-s{s + 1}'


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--out', type=Path, default=ROOT / 'build/qual/qa-reach')
    p.add_argument('--port', type=int, default=4620)
    p.add_argument('--mode', default='defaults')
    p.add_argument('--only', default='',
                   help='comma list of country-slot (1-based slot), e.g. 3-2,14-4')
    p.add_argument('--seconds', type=int, default=0,
                   help='optional: cap the race window instead of driving to the finish')
    p.add_argument('--no-lock', action='store_true',
                   help='do not wrap each run in the machine-wide heavy lock')
    a = p.parse_args()

    cells = MISSING
    if a.only:
        want = set()
        for item in a.only.split(','):
            c, s = item.strip().split('-')
            want.add((int(c), int(s) - 1))
        cells = [x for x in MISSING if x in want]

    a.out.mkdir(parents=True, exist_ok=True)
    results = []
    for c, s in cells:
        out = a.out / cell_id(c, s)
        cmd = [sys.executable, str(ROOT / 'tools/tg2_progress.py'),
               '--out', str(out), '--port', str(a.port),
               '--country', str(c), '--start-slot', str(s),
               '--races', '1', '--mode', a.mode]
        print(f'=== {COUNTRIES[c]} race {s + 1} (index {c * 4 + s}) -> {out}',
              flush=True)
        if a.no_lock:
            rc = subprocess.call(cmd, cwd=str(ROOT))
        else:
            rc = subprocess.call(
                ['flock', str(Path.home() / '.cache/tg2-heavy.lock')] + cmd,
                cwd=str(ROOT))
        summary = {}
        if (out / 'summary.json').exists():
            summary = json.loads((out / 'summary.json').read_text())
        races = summary.get('races') or [{}]
        r0 = races[0]
        results.append(dict(
            country=c, country_name=COUNTRIES[c], slot=s + 1,
            index=c * 4 + s, rc=rc, result=summary.get('result'),
            requested_index=summary.get('requested_index'),
            index_at_race=r0.get('index'), descriptor=r0.get('descriptor'),
            finish_frame=r0.get('finish_frame'),
            timeout=bool(r0.get('timeout')),
            manifests=summary.get('manifests')))
        (a.out / 'batch.json').write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps(results[-1]), flush=True)
    failed = [r for r in results if r['rc'] != 0 or not r['finish_frame']]
    print(f'{len(results) - len(failed)}/{len(results)} races reached the finish')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
