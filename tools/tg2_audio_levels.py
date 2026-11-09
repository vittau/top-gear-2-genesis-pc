#!/usr/bin/env python3
"""Per-source audio measurements for the port's offline captures.

Everything streams the WAV in blocks, so a 100 MB, 120 s capture never has to
fit in memory (AGENTS.md machine-resource rules).

  rms    FILE                 per-second RMS (and the mean)
  dc     FILE                 whole-file mean sample (the chip's DC offset)
  bands  FILE AT SECS         band energies (dB) of a window, 20 Hz .. 40 kHz
  ratio  FILE REF             per-second RMS ratio against a reference capture
  maxdiff FILE REF            largest absolute sample difference (identity check)

Both captures must come from the same route (tools/tg2_both_route.py
--script-out) so a ratio compares the same music/engine span.
"""
import json
import sys
import wave

import numpy as np
from scipy.signal import welch

CHUNK = 1 << 20


def blocks(path):
    w = wave.open(path)
    n, ch, rate = w.getnframes(), w.getnchannels(), w.getframerate()
    done = 0
    while done < n:
        want = min(CHUNK, n - done)
        a = np.frombuffer(w.readframes(want), dtype='<i2').reshape(-1, ch)
        yield a, rate
        done += want
    w.close()


def per_second(path):
    sums = []
    i0 = 0
    rate = 0
    for a, rate in blocks(path):
        x = a.astype(np.float64)
        sec = (i0 + np.arange(x.shape[0])) // rate
        for s in np.unique(sec):
            m = sec == s
            while len(sums) <= s:
                sums.append([0.0, 0])
            sums[s][0] += float((x[m] ** 2).sum())
            sums[s][1] += int(m.sum() * x.shape[1])
        i0 += x.shape[0]
    return [(float(np.sqrt(v[0] / v[1])), v[1] // 2) for v in sums], rate


def window(path, at_sec, secs):
    rate = wave.open(path).getframerate()
    start, need = int(at_sec * rate), int(secs * rate)
    parts = []
    i0 = 0
    for a, rate in blocks(path):
        i1 = i0 + a.shape[0]
        lo, hi = max(start, i0), min(start + need, i1)
        if hi > lo:
            parts.append(a[lo - i0:hi - i0].astype(np.float64))
        i0 = i1
        if i1 >= start + need:
            break
    return (np.concatenate(parts) if parts else np.zeros((0, 2))), rate


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == 'rms':
        r, rate = per_second(path)
        vals = [x[0] for x in r]
        print(json.dumps({'rate': rate, 'seconds': len(vals),
                          'rms': [round(v, 2) for v in vals],
                          'mean_rms': round(float(np.mean(vals)), 3)}))
    elif cmd == 'dc':
        tot = 0.0
        n = 0
        for a, _ in blocks(path):
            tot += float(a.astype(np.float64).sum())
            n += a.size
        print(json.dumps({'dc_mean': round(tot / n, 4)}))
    elif cmd == 'bands':
        at = float(sys.argv[3]) if len(sys.argv) > 3 else 60.0
        secs = float(sys.argv[4]) if len(sys.argv) > 4 else 4.0
        x, rate = window(path, at, secs)
        mono = x.mean(axis=1)
        mono = mono - mono.mean()
        f, p = welch(mono, fs=rate, nperseg=16384)
        edges = [(20, 200), (200, 1000), (1000, 3300), (3300, 6600),
                 (6600, 12000), (12000, 20000), (20000, 40000)]
        out = {}
        for lo, hi in edges:
            m = (f >= lo) & (f < hi)
            out[f'{lo}-{hi}'] = round(10 * np.log10(float(p[m].sum()) + 1e-12), 2)
        print(json.dumps({'at': at, 'secs': secs, 'band_dB': out}))
    elif cmd == 'ratio':
        a, _ = per_second(path)
        b, _ = per_second(sys.argv[3])
        n = min(len(a), len(b))
        r = [round(a[i][0] / b[i][0], 4) if b[i][0] > 1 else None for i in range(n)]
        rr = [x for x in r if x is not None]
        print(json.dumps({'secs': n,
                          'ratio_median': round(float(np.median(rr)), 4),
                          'ratio_p05': round(float(np.percentile(rr, 5)), 4),
                          'ratio_p95': round(float(np.percentile(rr, 95)), 4),
                          'first_s': r[:8], 'last_s': r[-6:]}))
    elif cmd == 'maxdiff':
        peak = 0
        same_len = True
        for (a, _), (b, _) in zip(blocks(path), blocks(sys.argv[3])):
            if a.shape[0] != b.shape[0]:
                same_len = False
                break
            d = a.astype(np.int32) - b.astype(np.int32)
            peak = max(peak, int(np.abs(d).max()))
        print(json.dumps({'same_length': same_len,
                          'identical': same_len and peak == 0,
                          'peak_abs_diff': peak}))
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
