#!/usr/bin/env python3
"""Compare the audio a race quickstate resumed against the uninterrupted race.

The load case's two captures both stop a fixed number of frames after the
save/resume point, so their last frames cover the same guest time. A
quickstate resumes at a guest boundary that need not coincide with the
reference capture's frame flush, so the two tails can differ by a few frames;
the comparison therefore works on 20-frame RMS windows of the *effects* layer,
where the engine sound is continuous, and reports every window's ratio instead
of requiring sample alignment.

Streaming and dependency-free (no FFT, no whole-file load, no NumPy). Used by
tools/regression.py and runnable alone as evidence:

  python3 tools/tg2_state_audio.py ref_chipB.wav load_chipB.wav
"""
from __future__ import annotations

import argparse
import array
import json
import math
import wave


def _read_mono(w, n):
    ch = w.getnchannels()
    raw = w.readframes(n)
    a = array.array('h')
    a.frombytes(raw[:len(raw) - (len(raw) % 2)])
    frames = len(a) // ch
    if ch == 1:
        return [float(v) for v in a]
    return [sum(a[i * ch:(i + 1) * ch]) / ch for i in range(frames)]


def tail_windows(path, count, win):
    """RMS/peak of every full `win`-sample window in the last `count` samples."""
    with wave.open(str(path)) as w:
        rate, total = w.getframerate(), w.getnframes()
        start = max(0, total - count)
        w.setpos(start)
        rms, left, peak, samples = [], total - start, 0, 0
        while left >= win:
            x = _read_mono(w, win)
            if len(x) < win:
                break
            rms.append(math.sqrt(sum(v * v for v in x) / len(x)))
            for v in x:
                if abs(v) > peak:
                    peak = abs(v)
            samples += len(x)
            left -= len(x)
    return dict(rate=rate, rms=rms, peak=peak, samples=samples)


def compare(ref, load, frames=200.0, win_frames=20.0, tol=(0.9, 1.1),
            win_tol=(0.8, 1.25)):
    """Compare the last `frames` of two captures of the same guest time."""
    with wave.open(str(ref)) as w:
        rate = w.getframerate()
        count = int(frames * rate / 60.0)
    win = int(win_frames * rate / 60.0)
    a = tail_windows(ref, count, win)
    b = tail_windows(load, count, win)
    n = min(len(a['rms']), len(b['rms']))
    ratios = [round(b['rms'][i] / a['rms'][i], 3)
              for i in range(n) if a['rms'][i] > 0]
    inside = sum(1 for r in ratios if win_tol[0] <= r <= win_tol[1])
    rms_a = math.sqrt(sum(x * x for x in a['rms'][:n]) / n) if n else 0.0
    rms_b = math.sqrt(sum(x * x for x in b['rms'][:n]) / n) if n else 0.0
    rms_ratio = rms_b / rms_a if rms_a else None
    peak_ratio = b['peak'] / a['peak'] if a['peak'] else None
    ok = bool(rms_ratio is not None and tol[0] <= rms_ratio <= tol[1] and
              peak_ratio is not None and 0.5 <= peak_ratio <= 1.5 and
              len(ratios) >= 4 and inside == len(ratios))
    return dict(ok=ok, frames=frames, win_frames=win_frames, windows=len(ratios),
                rms_ref=round(rms_a, 1), rms_load=round(rms_b, 1),
                rms_ratio=round(rms_ratio, 2) if rms_ratio is not None else None,
                peak_ref=int(a['peak']), peak_load=int(b['peak']),
                peak_ratio=round(peak_ratio, 2) if peak_ratio is not None else None,
                windows_inside=inside,
                window_ratios=ratios)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('ref')
    p.add_argument('load')
    p.add_argument('--frames', type=float, default=200.0)
    p.add_argument('--win-frames', type=float, default=20.0)
    a = p.parse_args()
    result = compare(a.ref, a.load, a.frames, a.win_frames)
    print(json.dumps(result, indent=1))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
