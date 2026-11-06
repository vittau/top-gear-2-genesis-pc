#!/usr/bin/env python3
"""Compare TG2 WAV captures taken on the same deterministic route.

Answers "is the second source actually audible in this capture?", the question
docs/AUDIO.md asks of BOTH: peak/RMS plus 20 ms band-envelope statistics and
envelope correlation against the two single-source captures.

  python3 tools/tg2_audio_compare.py --music m.wav --sfx s.wav --both b.wav
  python3 tools/tg2_audio_compare.py --music m.wav --both b.wav --json out.json

Bands: 50-200, 200-500, 500-1000, 1000-2000, 2000-4000 Hz. Envelopes are the
20 ms RMS of each band. Envelope correlation is Pearson over the whole
capture; the "quiet music" ratio is the mean BOTH/SFX RMS inside the 10 % of
windows where MUSIC is quietest (the AUDIO.md audibility check).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

BANDS = [(50, 200), (200, 500), (500, 1000), (1000, 2000), (2000, 4000)]
WIN = 0.020


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    import wave
    with wave.open(str(path)) as w:
        n, ch, rate = w.getnframes(), w.getnchannels(), w.getframerate()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype='<i2').astype(np.float64)
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, rate


def band_envelopes(x: np.ndarray, rate: int) -> dict[str, np.ndarray]:
    n = int(rate * WIN)
    hop = n
    frames = (len(x) - n) // hop + 1 if len(x) >= n else 0
    spec = np.fft.rfft(x[:frames * hop].reshape(frames, n) * np.hanning(n), axis=1)
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    mag = np.abs(spec) / n
    out = {}
    for lo, hi in BANDS:
        sel = (freqs >= lo) & (freqs < hi)
        env = np.sqrt((mag[:, sel] ** 2).sum(axis=1))
        out[f'{lo}-{hi}'] = env
    return out


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    m = min(len(a), len(b))
    a, b = a[:m], b[:m]
    if m < 4 or a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def describe(path: Path, trim_s: float = 0.0) -> dict:
    x, rate = read_wav(path)
    if trim_s > 0:
        x = x[int(trim_s * rate):]
    env = band_envelopes(x, rate)
    return dict(path=str(path), rate=rate, duration_s=round(len(x) / rate, 3),
                peak=int(np.abs(x).max()), rms=round(float(np.sqrt((x ** 2).mean())), 2),
                band_rms={k: round(float(np.sqrt((v ** 2).mean())), 2)
                          for k, v in env.items()},
                env=env)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--music', type=Path)
    p.add_argument('--sfx', type=Path)
    p.add_argument('--both', type=Path, required=True)
    p.add_argument('--trim', type=float, default=0.0,
                   help='seconds to drop from the start of every capture')
    p.add_argument('--json', type=Path)
    a = p.parse_args()

    caps = {}
    for name in ('music', 'sfx', 'both'):
        path = getattr(a, name)
        if path:
            caps[name] = describe(path, a.trim)

    report = {'captures': {k: {kk: vv for kk, vv in v.items() if kk != 'env'}
                           for k, v in caps.items()}}
    both = caps['both']
    for ref in ('music', 'sfx'):
        if ref not in caps:
            continue
        corr = {}
        for band in both['env']:
            corr[band] = round(pearson(both['env'][band], caps[ref]['env'][band]), 3)
        report[f'corr_both_vs_{ref}'] = corr

    if 'music' in caps and 'sfx' in caps:
        # Captures can differ in length by a few windows; compare the overlap.
        common = min(len(caps[k]['env']['50-200']) for k in ('music', 'sfx', 'both'))
        for k in caps:
            for band in caps[k]['env']:
                caps[k]['env'][band] = caps[k]['env'][band][:common]
        m, s, b = (caps[k]['env'] for k in ('music', 'sfx', 'both'))
        q_band = '50-200'
        mv = m[q_band]
        k = max(1, len(mv) // 10)
        quiet = np.argsort(mv)[:k]
        report['quiet_music_windows'] = {
            'count': int(k), 'band': q_band,
            'music_rms': round(float(np.sqrt((mv[quiet] ** 2).mean())), 2),
            'sfx_rms': round(float(np.sqrt((s[q_band][quiet] ** 2).mean())), 2),
            'both_rms': round(float(np.sqrt((b[q_band][quiet] ** 2).mean())), 2),
            'both_over_music': round(float(np.sqrt((b[q_band][quiet] ** 2).mean()) /
                                           max(np.sqrt((mv[quiet] ** 2).mean()), 1e-9)), 2),
        }
    if 'music' in caps and 'sfx' in caps and 'both' in caps:
        # Where BOTH exceeds both single captures, the two sources are mixing.
        report['bands_both_exceeds_both_singles'] = [
            band for band in BANDS_KEYS(caps['both'])
            if caps['both']['band_rms'][band] > caps['music']['band_rms'][band]
            and caps['both']['band_rms'][band] > caps['sfx']['band_rms'][band]]
    print(json.dumps(report, indent=2))
    if a.json:
        a.json.write_text(json.dumps(report, indent=2) + '\n')


def BANDS_KEYS(cap):
    return list(cap['band_rms'].keys())


if __name__ == '__main__':
    main()
