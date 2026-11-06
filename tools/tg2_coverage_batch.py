#!/usr/bin/env python3
"""Run the 16-track coverage matrix (one process per cell).

For every country (0..15) this launches `tools/tg2_coverage.py` once per
presentation mode, sequentially on one TCP port, and appends one JSON line per
cell to <out>/index.jsonl. Nitro is exercised on two countries in each mode so
the boost appears in the matrix without draining the tank on every run.

  python3 tools/tg2_coverage_batch.py --port 4490 --out build/qual/cov \
      --modes off,ws169-edges --seconds 62
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NITRO_COUNTRIES = (0, 8)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4490)
    p.add_argument('--out', type=Path, default=ROOT / 'build/qual/cov')
    p.add_argument('--modes', default='off,ws169-edges')
    p.add_argument('--countries', default=','.join(str(i) for i in range(16)))
    p.add_argument('--seconds', type=float, default=62.0)
    p.add_argument('--shot-every', type=int, default=600)
    p.add_argument('--skip-existing', action='store_true')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    index = a.out / 'index.jsonl'
    modes = [m.strip() for m in a.modes.split(',') if m.strip()]
    countries = [int(c) for c in a.countries.split(',') if c.strip()]
    for mode in modes:
        for country in countries:
            out = a.out / f'c{country:02d}-{mode}'
            if a.skip_existing and (out / 'summary.json').exists():
                print('skip', out, flush=True)
                continue
            cmd = [sys.executable, str(ROOT / 'tools/tg2_coverage.py'),
                   '--port', str(a.port), '--out', str(out),
                   '--country', str(country), '--mode', mode,
                   '--seconds', str(a.seconds), '--shot-every', str(a.shot_every)]
            if country in NITRO_COUNTRIES:
                cmd.append('--nitro')
            print('run', ' '.join(cmd), flush=True)
            proc = subprocess.run(cmd, capture_output=True, text=True)
            line = dict(country=country, mode=mode, out=str(out),
                        returncode=proc.returncode,
                        stdout=proc.stdout.strip().splitlines()[-1:] or [],
                        stderr=proc.stderr.strip().splitlines()[-3:] or [])
            summary_path = out / 'summary.json'
            if summary_path.exists():
                summary = json.loads(summary_path.read_text())
                line['result'] = summary.get('result')
                line['manifests'] = summary.get('manifests')
                line['meta'] = summary.get('meta')
                line['nitro'] = summary.get('nitro')
            with index.open('a') as fh:
                fh.write(json.dumps(line) + '\n')
            print(json.dumps(line)[:400], flush=True)


if __name__ == '__main__':
    main()
