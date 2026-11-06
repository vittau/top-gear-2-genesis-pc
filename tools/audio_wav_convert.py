#!/usr/bin/env python3
"""Streaming WAV rate conversion + trim (no full-file loads).

The port's offline tap writes at the PSG's native rate (223721 Hz stereo, see
docs/AUDIO.md), which is not something to hand to a player or diff against a
44100 Hz reference. This converts to a chosen rate with a box pre-filter (so
nothing aliases into the new band) and linear interpolation, reading and
writing in blocks, so a 150 MB capture never has to fit in memory.

  python3 tools/audio_wav_convert.py IN.wav OUT.wav --rate 44100 --tail 60

`--tail` keeps only the last N seconds: the music span of a capture, whose
first seconds are the boot and the menu route. `--start`/`--end` take an
explicit window, `--mono` averages the channels.
"""
from __future__ import annotations

import argparse
import wave

import numpy as np

BLOCK = 1 << 15


def convert(src, dst, rate, tail=None, start=None, end=None, mono=False,
            prefilter=5, verbose=True):
    w = wave.open(src, 'rb')
    ch, width, in_rate, n = (w.getnchannels(), w.getsampwidth(),
                             w.getframerate(), w.getnframes())
    if width != 2:
        raise SystemExit('%s: only 16-bit PCM is supported' % src)
    t1 = n / in_rate
    t0 = max(0.0, t1 - tail) if tail else 0.0
    if start is not None:
        t0 = start
    if end is not None:
        t1 = end
    first = int(t0 * in_rate)
    last = int(min(t1, n / in_rate) * in_rate)
    step = in_rate / float(rate)
    k = max(1, int(prefilter))

    out = wave.open(dst, 'wb')
    out.setnchannels(1 if mono else ch)
    out.setsampwidth(2)
    out.setframerate(int(round(rate)))

    w.setpos(first)
    carry = np.zeros((k - 1, ch), dtype=np.float64)
    buf = np.zeros((0, ch), dtype=np.float64)   # filtered samples, from base
    base = first                                # input index of buf[0]
    out_pos = float(first)                      # next output position
    produced = 0
    read = first
    while read < last:
        raw = w.readframes(min(BLOCK, last - read))
        if not raw:
            break
        block = np.frombuffer(raw, dtype='<i2').reshape(-1, ch).astype(np.float64)
        read += len(block)
        ext = np.vstack([carry, block])
        cs = np.cumsum(np.vstack([np.zeros((1, ch)), ext]), axis=0)
        filt = (cs[k:] - cs[:-k]) / k
        carry = ext[-(k - 1):].copy() if k > 1 else ext[:0]
        buf = np.vstack([buf, filt])
        # emit every output sample we now have both neighbours for
        while out_pos + 1.0 <= base + len(buf) - 1:
            rel = out_pos - base
            i0 = int(np.floor(rel))
            f = rel - i0
            y = buf[i0] * (1.0 - f) + buf[i0 + 1] * f
            if mono:
                y = np.array([y.mean()])
            np.clip(y, -32768, 32767, out=y)
            out.writeframes(y.astype('<i2').tobytes())
            produced += 1
            out_pos += step
        drop = int(np.floor(out_pos)) - base
        if drop > 0:
            buf = buf[drop:]
            base += drop
    out.close()
    w.close()
    info = dict(in_rate=in_rate, out_rate=rate, seconds=(last - first) / in_rate,
                samples=produced)
    if verbose:
        print('wrote %s: %d Hz, %.2f s, %d samples'
              % (dst, info['out_rate'], info['seconds'], info['samples']))
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--rate', type=int, default=44100)
    ap.add_argument('--tail', type=float)
    ap.add_argument('--start', type=float)
    ap.add_argument('--end', type=float)
    ap.add_argument('--mono', action='store_true')
    a = ap.parse_args()
    convert(a.src, a.dst, a.rate, tail=a.tail, start=a.start, end=a.end,
            mono=a.mono)


if __name__ == '__main__':
    main()
