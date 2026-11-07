#!/usr/bin/env python3
"""Render the release-qualification coverage table from the run evidence.

Reads the country progression runs (`tools/tg2_progress.py`, one directory per
country) plus the ROM race table, and prints the country x race markdown table
that `docs/VALIDATION.md` carries. No game process is launched.

  python3 tools/tg2_qual_coverage.py --root build/qual/qa-prog
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import manifest_counts  # noqa: E402

COUNTRIES = ['Australasia', 'Britain', 'Canada', 'Egypt', 'France', 'Germany',
             'Greece', 'India', 'Ireland', 'Italy', 'Japan', 'Scandinavia',
             'South America', 'Spain', 'Switzerland', 'U.S.A.']

# Track names read off the intro panel of each race (country, slot). The ROM
# stores them in the game's own font, not ASCII; the panel is the only place
# the full name appears.
NAMES = {
    (0, 0): 'Auckland', (0, 1): 'Ayers Rock', (0, 2): 'Canterbury Plains', (0, 3): 'Sydney',
    (1, 0): 'Loch Ness', (1, 1): 'London', (1, 2): 'Sheffield', (1, 3): 'Stonehenge',
    (2, 0): 'Banff', (2, 1): 'Niagara', (2, 2): 'Toronto',
    (3, 0): 'Abu Simbel',
    (4, 0): 'Bordeaux', (4, 1): 'Monaco', (4, 2): 'Nice', (4, 3): 'Paris',
    (5, 0): 'Bavaria', (5, 1): 'Cologne', (5, 2): 'Frankfurt', (5, 3): 'Munich',
    (6, 0): 'Athens', (6, 1): 'Meteora', (6, 2): 'Mykanos', (6, 3): 'Santorini',
    (7, 0): 'Amber Port',
    (8, 0): 'Dublin', (8, 1): 'Galway', (8, 2): 'Killarney', (8, 3): 'Limerick',
    (9, 0): 'Florence', (9, 1): 'Pisa', (9, 2): 'Rome',
    (10, 0): 'Hiroshima', (10, 1): 'Kyoto', (10, 2): 'Tokyo', (10, 3): 'Yokohama',
    (11, 0): 'Copenhagen', (11, 1): 'Helsinki',
    (12, 0): 'Chile', (12, 1): 'Mexico',
    (13, 0): 'Andalusia', (13, 1): 'Barcelona',
    (14, 0): 'Geneva',
    (15, 0): 'Las Vegas', (15, 1): 'Los Angeles',
}

ROM = Path.home() / 'roms/genesis/tg2.bin'
TABLE = 0x1B8E8


def race_table(rom: Path):
    if not rom.exists():
        return {}
    data = rom.read_bytes()
    out = {}
    for index in range(64):
        a = int.from_bytes(data[TABLE + index * 4:TABLE + index * 4 + 4], 'big')
        rec = data[a:a + 0xAE]
        out[index] = dict(descriptor=f'0x{a:06x}',
                          length=f'{chr(rec[8])}.{chr(rec[9])}',
                          laps=rec[7], weather=rec[10])
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('build/qual/qa-prog'))
    p.add_argument('--rom', type=Path, default=ROM)
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    table = race_table(a.rom)
    rows = []
    for c in range(16):
        out = a.root / f'c{c:02d}'
        summary = {}
        if (out / 'summary.json').exists():
            summary = json.loads((out / 'summary.json').read_text())
        races = {r['round']: r for r in summary.get('races', [])}
        for slot in range(4):
            index = c * 4 + slot
            info = table.get(index, {})
            race = races.get(slot + 1, {})
            laps = [x['seconds'] for x in race.get('lap_times', [])]
            rows.append(dict(
                country=c, slot=slot, index=index,
                name=NAMES.get((c, slot), '–'),
                length=info.get('length', '?'), laps_total=info.get('laps', '?'),
                weather=info.get('weather'),
                descriptor=info.get('descriptor', '?'),
                result=('passed' if race.get('finish_frame') else
                        ('NOT REACHED (failed to qualify)' if not summary
                         else 'NOT REACHED (failed to qualify)')),
                race_laps=[round(x) for x in race.get('lap_boundaries', []) and
                           [b['lap'] for b in race['lap_boundaries']]],
                lap_seconds=laps,
                manifests=manifest_counts(out),
                evidence=str(out)))
    header = ('| Country | Race | Track | Length | Laps | Descriptor | Result | '
              'Splits | Manifests | Evidence |\n'
              '|---|---:|---|---:|---:|---|---|---|---|---|\n')
    body = []
    for r in rows:
        m = r['manifests'] or {}
        mcount = '/'.join(str(m.get(k, '?')) for k in
                          ('dispatch_misses.toml', 'floor_coverage.toml',
                           'interior_label_misses.toml', 'floor_unsafe.toml'))
        laps = len(r['lap_seconds'])
        body.append(f"| {COUNTRIES[r['country']]} | {r['slot'] + 1} | {r['name']} | "
                    f"{r['length']} mi | {r['laps_total']} | {r['descriptor']} | "
                    f"{r['result']} | {laps} | {mcount} | `{r['evidence']}` |")
    text = header + '\n'.join(body) + '\n'
    if a.out:
        a.out.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
