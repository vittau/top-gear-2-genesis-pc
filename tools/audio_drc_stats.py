#!/usr/bin/env python3
"""Summarise the DRC playback-ratio stability of a capture from its frame log.

The runner records one row per presented frame in the always-on statistics ring
(`GENESIS_FRAME_STATS=<path>`). The columns used here are `corr_ppm` - the
ratio correction the audio bridge applied to the source stream, i.e. exactly
how much faster/slower the music was played at that moment - and `fill_us`,
the ring fill.

Playback ratio wobble is what an ear hears as "the music changes speed". This
tool reports it as a distribution and as a slope: a constant offset (the
device crystal) is inaudible, a fast swing is not.

  python3 tools/audio_drc_stats.py build/device/on/frame-stats.csv
  python3 tools/audio_drc_stats.py a.csv b.csv --json out.json
"""
import argparse
import csv
import json
import sys


def load(path):
    frames, corr, fill, conceal, under = [], [], [], [], []
    with open(path, newline='') as f:
        for row in csv.DictReader(f):
            try:
                frames.append(int(row['frame']))
                corr.append(int(row['corr_ppm']))
                fill.append(int(row['fill_us']))
                conceal.append(int(row.get('conceals', 0) or 0))
                under.append(int(row.get('underruns', 0) or 0))
            except (KeyError, ValueError):
                continue
    return {'path': path, 'frame': frames, 'corr': corr, 'fill': fill,
            'conceal': conceal, 'underrun': under}


def pct(values, p):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p * (len(s) - 1))))]


def summarise(d):
    corr = d['corr']
    if len(corr) < 10:
        return {'path': d['path'], 'rows': len(corr)}
    # Per-second slope of the ratio: median |corr[i+50] - corr[i]| gives the
    # fastest typical change the listener hears, in ppm per 1 s.
    step = 50
    slopes = [abs(corr[i + step] - corr[i]) for i in range(0, len(corr) - step, 10)]
    # Signed drift over the whole capture, excluding the first 2 s of priming.
    tail = corr[120:]
    return {
        'path': d['path'],
        'rows': len(corr),
        'seconds': round(len(corr) / 60.0, 1),
        'corr_ppm': {'min': min(corr), 'p05': pct(corr, .05), 'p50': pct(corr, .50),
                     'p95': pct(corr, .95), 'max': max(corr),
                     'span': max(corr) - min(corr)},
        'corr_change_ppm_per_s': {'p50': pct(slopes, .50), 'p95': pct(slopes, .95),
                                  'max': max(slopes) if slopes else 0},
        'corr_tail_p05_p95_ppm': [pct(tail, .05), pct(tail, .95)],
        'fill_ms': {'min': round(min(d['fill']) / 1000.0, 1),
                    'p50': round(pct(d['fill'], .50) / 1000.0, 1),
                    'p95': round(pct(d['fill'], .95) / 1000.0, 1),
                    'max': round(max(d['fill']) / 1000.0, 1)},
        'conceals': d['conceal'][-1] if d['conceal'] else 0,
        'underruns': d['underrun'][-1] if d['underrun'] else 0,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('csv', nargs='+')
    p.add_argument('--json')
    a = p.parse_args()
    out = [summarise(load(path)) for path in a.csv]
    for s in out:
        if 'corr_ppm' not in s:
            print('%s: no usable rows' % s['path'])
            continue
        c = s['corr_ppm']
        print('%s  %.0f s' % (s['path'], s['seconds']))
        print('  ratio correction : %+d ppm (p05 %+d .. p95 %+d, span %d ppm)'
              % (c['p50'], c['p05'], c['p95'], c['span']))
        print('  correction change: p50 %d ppm/s, p95 %d ppm/s, max %d ppm/s'
              % (s['corr_change_ppm_per_s']['p50'], s['corr_change_ppm_per_s']['p95'],
                 s['corr_change_ppm_per_s']['max']))
        f = s['fill_ms']
        print('  ring fill        : min %.0f, p50 %.0f, p95 %.0f, max %.0f ms'
              % (f['min'], f['p50'], f['p95'], f['max']))
        print('  conceals %d, underruns %d' % (s['conceals'], s['underruns']))
    if a.json:
        with open(a.json, 'w') as f:
            json.dump(out, f, indent=2)
            f.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
