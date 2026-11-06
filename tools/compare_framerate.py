#!/usr/bin/env python3
"""Compare private deterministic race captures; emit reviewable scalar evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import wave

FIELDS = {'race_vint': (0x238C, 2), 'pictures_built': (0x23B4, 2),
          'position': (0x18CA, 4), 'view_position': (0x18D2, 4),
          'speed': (0x18D8, 2), 'integration_speed': (0x198C, 2),
          'lap_index': (0x1994, 2), 'clock_16_16': (0x23B8, 4)}


def read_fields(path):
    data = path.read_bytes()
    assert len(data) == 65536, path
    return {k: int.from_bytes(data[a:a+n], 'big') for k, (a, n) in FIELDS.items()}


def capture(path, start, count):
    summary = json.loads((path / 'summary.json').read_text())
    assert summary['exit'] == 0
    assert summary['cold_boot'] == {'60': '2A0B972960C5E325', '300': '1131D937D70234FD'}
    ram = [(path / f'ram-{f}.ram').read_bytes() for f in range(start, start + count + 1)]
    scalar = [read_fields(path / f'ram-{f}.ram') for f in range(start, start + count + 1)]
    summary['counter_deltas'] = {k: dict(Counter((y[k] - x[k]) % (1 << (FIELDS[k][1] * 8))
                                                for x, y in zip(scalar, scalar[1:])))
                                 for k in ['race_vint', 'pictures_built', 'clock_16_16']}
    for name, off, length in [('sprites', 0xBE00, 0x280), ('hscroll', 0xB800, 0x380)]:
        values = [(path / f'vram-{f}.vram').read_bytes()[off:off+length]
                  for f in range(start, start + count + 1)]
        summary[name + '_changed'] = sum(a != b for a, b in zip(values, values[1:]))
    summary['primary_raster_swaps'] = sum(a[0x231E:0x2322] != b[0x231E:0x2322]
                                        for a, b in zip(ram, ram[1:]))
    for name in ['dispatch_misses', 'floor_coverage', 'interior_label_misses', 'floor_unsafe']:
        text = (path / (name + '.toml')).read_text()
        match = re.search(r'# entries:\s+(\d+)', text)
        summary[name] = int(match[1]) if match else None
    summary['png_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(path.glob('frame-*.png'))}
    audio = path / 'audio.wav'
    if audio.exists():
        with wave.open(str(audio), 'rb') as w:
            summary['audio'] = dict(frames=w.getnframes(), rate=w.getframerate(),
                                    channels=w.getnchannels(), width=w.getsampwidth())
        summary['audio']['sha256'] = hashlib.file_digest(audio.open('rb'), 'sha256').hexdigest()
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('off', type=Path)
    p.add_argument('on', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    first = json.loads((a.off / 'summary.json').read_text())
    start, count = first['start'], first['frames']
    result = {'off': capture(a.off, start, count), 'on': capture(a.on, start, count)}
    rows = []
    mismatches = Counter()
    for f in sorted({3300, 4500, 5200, *range(start, start + count + 1)}):
        off = read_fields(a.off / f'ram-{f}.ram')
        on = read_fields(a.on / f'ram-{f}.ram')
        for key in FIELDS:
            if off[key] != on[key]:
                mismatches[key] += 1
        rows.append({'frame': f, 'off': off, 'on': on})
    result['mismatched_samples'] = dict(mismatches)
    result['samples'] = rows
    a.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'samples'}, indent=2))


if __name__ == '__main__':
    main()
