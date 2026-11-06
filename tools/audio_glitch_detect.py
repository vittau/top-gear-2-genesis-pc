#!/usr/bin/env python3
"""Measure what a real audio device actually played: pops, dropouts, tempo.

Input is a device-side capture (the sink monitor WAV written by
tools/audio_device_capture.py) plus, optionally, the offline deterministic WAV
of the same route to measure local tempo/drift.

Three independent detectors, all reported as counts per minute:

  dropout_zero      run of >= 2 ms of exact digital silence inside music
  dropout_repeat    run of >= 2 ms of identical samples (DC hold) inside music
  dropout_envelope  3-60 ms envelope collapse (>20 dB below the local median)
  pop               sample-to-sample step > 8x the local derivative envelope
  tempo             local device/reference ratio in ppm, per 15 s window

Everything is computed from the file, so a build can be compared without any
in-process telemetry. --selftest injects known artifacts into a clean capture
and reports what was found, which is how the detector itself is qualified.

  python3 tools/audio_glitch_detect.py --device build/x/device.wav \
      --reference build/audio15/offline.wav --out build/x/glitch.json
"""
import argparse
import json
import wave
from pathlib import Path

import numpy as np

DEV_RATE = 48000.0
MUSIC_GATE = 120.0      # local RMS (s16 units) considered "music is playing"
ZERO_RUN_MS = 2.0
POP_FRAC = 0.7          # step must be this fraction of the local peak
POP_FLOOR = 1200.0      # absolute step (s16 units) below which nothing is a pop
POP_ISO_MS = 10.0       # isolated in time: no other step within this window
ENV_DROP_DB = 20.0


def read_wav(path):
    with wave.open(str(path)) as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        raise SystemExit('%s: expected 16-bit PCM, got %d bytes/sample' % (path, sw))
    a = np.frombuffer(raw, dtype='<i2')
    if ch > 1:
        a = a.reshape(-1, ch)
        mono = a.astype(np.float32).mean(axis=1)
    else:
        mono = a.astype(np.float32)
    return mono, sr, ch


def moving_rms(x, win):
    win = max(1, int(win))
    c = np.concatenate(([0.0], np.cumsum(x * x)))
    out = np.empty(len(x), dtype=np.float32)
    half = win // 2
    for start in range(0, len(x), 65536):
        idx = np.arange(start, min(len(x), start + 65536))
        lo = np.clip(idx - half, 0, len(x))
        hi = np.clip(idx + half + 1, 0, len(x))
        out[idx] = np.sqrt((c[hi] - c[lo]) / np.maximum(1, hi - lo))
    return out


def runs(mask):
    """(start, length) of True runs."""
    if not mask.any():
        return []
    d = np.diff(np.concatenate(([0], mask.view(np.int8), [0])))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return list(zip(starts.tolist(), (ends - starts).tolist()))


def local_peak(x, win):
    """Local |x| maximum over +-win, blockwise (20 ms support)."""
    blk = 48
    ax = np.abs(x)
    nb = len(ax) // blk
    if nb == 0:
        return np.abs(x)
    v = ax[:nb * blk].reshape(nb, blk).max(axis=1)
    k = max(1, int(win) // blk + 1)
    near = np.empty(nb, dtype=np.float32)
    for i in range(nb):
        near[i] = v[max(0, i - k):min(nb, i + k + 1)].max()
    out = np.repeat(near, blk)
    return np.concatenate([out, np.full(len(ax) - len(out),
                                        out[-1] if len(out) else 0.0)])


def runs(mask):
    """(start, length) of True runs."""
    if not mask.any():
        return []
    d = np.diff(np.concatenate(([0], mask.view(np.int8), [0])))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return list(zip(starts.tolist(), (ends - starts).tolist()))


def local_derivative_envelope(d, win):
    """Local derivative envelope: 99.5th percentile of |d| per 10 ms block.

    The envelope for a block is the maximum of its *neighbouring* blocks (not
    itself), so a step that is the artifact under test cannot raise its own
    threshold - a plain per-block percentile is defeated by one outlier in 480
    samples. A legitimate transient (a drum attack) is broadband across
    neighbouring blocks and still suppresses the flag."""
    blk = max(1, int(0.010 * DEV_RATE))
    nblk = (len(d) + blk - 1) // blk
    vals = np.empty(nblk, dtype=np.float32)
    for b in range(0, nblk, 4096):
        for i in range(b, min(nblk, b + 4096)):
            seg = d[i * blk:(i + 1) * blk]
            vals[i] = np.percentile(seg, 99.5) if len(seg) else 0.0
    near = np.empty(nblk, dtype=np.float32)
    for i in range(nblk):
        near[i] = max(vals[j] for j in (i - 2, i - 1, i + 1, i + 2)
                      if 0 <= j < nblk)
    return np.repeat(near, blk)[:len(d)]


def runs(mask):
    """(start, length) of True runs."""
    if not mask.any():
        return []
    d = np.diff(np.concatenate(([0], mask.view(np.int8), [0])))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return list(zip(starts.tolist(), (ends - starts).tolist()))


def local_derivative_envelope(d, win):
    """Local derivative envelope: 99.5th percentile of |d| per 10 ms block,
    expanded to the block +/- one block (piecewise constant, ~20 ms support).

    Slow legitimate waveforms (a sustained bass note, a drum attack) set their
    own envelope this way, so only a step that is far above its neighbours is
    flagged as a discontinuity."""
    blk = max(1, int(0.010 * DEV_RATE))
    nblk = (len(d) + blk - 1) // blk
    vals = np.empty(nblk, dtype=np.float32)
    for b in range(0, nblk, 4096):
        for i in range(b, min(nblk, b + 4096)):
            seg = d[i * blk:(i + 1) * blk]
            vals[i] = np.percentile(seg, 99.5) if len(seg) else 0.0
    vals = np.maximum(vals, np.roll(vals, 1))
    vals = np.maximum(vals, np.roll(vals, -1))
    return np.repeat(vals, blk)[:len(d)]


def detect(mono, sr, gate=MUSIC_GATE):
    dt_ms = 1000.0 / sr
    out = {}
    rms50 = moving_rms(mono, 0.05 * sr)
    music = rms50 > gate

    # --- 1. digital silence (fade-to-silence / real underrun) -------------
    quiet = np.abs(mono) <= 1.0
    min_run = int(round(ZERO_RUN_MS / dt_ms))
    zero_runs = [(s, l) for s, l in runs(quiet) if l >= min_run]
    zero_ev = []
    for s, l in zero_runs:
        before = rms50[max(0, s - int(0.05 * sr)):s]
        after = rms50[min(len(rms50), s + l):min(len(rms50), s + l + int(0.05 * sr))]
        if len(before) and len(after) and before.mean() > gate and after.mean() > gate:
            zero_ev.append((s / sr, l * dt_ms))

    # --- 2. identical-sample runs (DC hold) -------------------------------
    same = np.zeros(len(mono), dtype=bool)
    same[1:] = mono[1:] == mono[:-1]
    hold_runs = [(s, l) for s, l in runs(same) if l >= min_run]
    hold_ev = []
    for s, l in hold_runs:
        seg = rms50[max(0, s - int(0.05 * sr)):max(1, s)]
        if len(seg) and seg.mean() > gate and abs(mono[s]) > 8:
            hold_ev.append((s / sr, l * dt_ms))

    # --- 3. envelope collapse (fade to silence and back) -------------------
    rms5 = moving_rms(mono, 0.005 * sr)
    med_win = int(0.2 * sr)
    med = np.empty_like(rms5)
    block = 32768
    for start in range(0, len(rms5), block):
        lo = max(0, start - med_win)
        hi = min(len(rms5), start + block + med_win)
        med[start:start + block] = np.median(rms5[lo:hi])
    collapse = (rms5 < med * 10 ** (-ENV_DROP_DB / 20.0)) & (med > gate)
    collapse_ev = []
    for s, l in runs(collapse):
        if l * dt_ms > 60.0:
            continue                      # a real stop/start, not a glitch
        collapse_ev.append((s / sr, l * dt_ms))

    # --- 4. discontinuous steps (pops) -------------------------------------
    # This music is full of genuine sample-to-sample edges (PSG square waves,
    # FM percussion), so "far above the local derivative envelope" cannot work:
    # the music's own edges ARE the envelope. What distinguishes a pipeline
    # discontinuity is that it is *isolated* - one step of a large fraction of
    # the local peak, with no comparable step for 10 ms either side. A square
    # wave repeats its edges every half period, so it never qualifies.
    d = np.abs(np.diff(mono, prepend=mono[0]))
    pk = local_peak(mono, 0.020 * sr)
    step = (d > POP_FRAC * pk) & (d > POP_FLOOR) & music
    iso = max(2, int(POP_ISO_MS / 1000.0 * sr))
    pop_ev = []
    for s0, l in runs(step):
        if step[max(0, s0 - iso):max(0, s0 - 2)].any():
            continue
        if step[s0 + l + 2:s0 + l + iso].any():
            continue
        peak = float(d[s0:s0 + l].max())
        pop_ev.append((s0 / sr, peak, float(pk[s0] / max(1.0, peak))))
    out['dropout_zero'] = zero_ev
    out['dropout_repeat'] = hold_ev
    out['dropout_envelope'] = collapse_ev
    out['pops'] = pop_ev
    out['music_seconds'] = float(music.sum() * dt_ms / 1000.0)
    out['seconds'] = len(mono) / sr
    out['rms'] = float(np.sqrt((mono.astype(np.float64) ** 2).mean()))
    out['peak'] = float(np.abs(mono).max())
    return out


# ---------------------------------------------------------------------------
# tempo / drift against the offline reference
# ---------------------------------------------------------------------------
ENV_RATE = 200.0


def envelope_at(x, sr, rate=ENV_RATE):
    """Amplitude envelope at `rate` Hz: rectify, low-pass, resample."""
    dec = sr / rate
    # sum of |x| over each output bin's span is a cheap, phase-free envelope
    n_out = int(len(x) / dec)
    idx = (np.arange(n_out + 1) * dec).astype(np.int64)
    c = np.concatenate(([0.0], np.cumsum(np.abs(x).astype(np.float64))))
    env = (c[idx[1:]] - c[idx[:-1]]) / np.maximum(1, np.diff(idx))
    # smooth to ~20 Hz so the envelope is tempo-comparable, not timbre
    k = max(1, int(round(rate / 20.0)))
    ker = np.ones(k) / k
    return np.convolve(env, ker, mode='same')


def window_corr(a, b, lag):
    """Normalized correlation of window `a` against `b[lag:lag+len(a)]`."""
    seg = b[lag:lag + len(a)]
    if len(seg) < len(a):
        return -2.0
    x = a - a.mean()
    y = seg - seg.mean()
    den = np.sqrt(float((x * x).sum()) * float((y * y).sum()))
    if den <= 1e-12:
        return -2.0
    return float((x * y).sum() / den)


# Tempo/drift is measured on the waveform itself, not on the amplitude
# envelope: a chiptune beat gives an envelope that is periodic at ~0.5 s, so an
# envelope correlation has many near-equal peaks and cannot resolve a tempo
# error. 4 kHz keeps note onsets and waveform phase sharp enough for a
# sub-millisecond lag while staying cheap.
LAG_RATE = 4000.0


def decimate_to(x, sr_in, rate=LAG_RATE):
    step = max(1, int(round(sr_in / rate)))
    n = len(x) // step
    if n < 1:
        return np.zeros(0, dtype=np.float32)
    return x[:n * step].reshape(n, step).mean(axis=1)


def corr_candidates(a, b, max_lag):
    """FFT correlation of a against b; returns (lags, values) over +-max_lag."""
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    fa = np.fft.rfft(a, n)
    fb = np.fft.rfft(b, n)
    cc = np.fft.irfft(fa * np.conj(fb), n)
    pos = cc[:max_lag + 1]
    neg = cc[-max_lag:][::-1]      # lags -1, -2, ... -> keep ascending
    vals = np.concatenate([neg[::-1], pos])
    lags = np.arange(-max_lag, max_lag + 1)
    return lags, vals


def onset_signal(env):
    """Onset strength at ENV_RATE: positive jumps of the amplitude envelope."""
    d = np.diff(env, prepend=env[0])
    d[d < 0] = 0.0
    k = int(ENV_RATE * 0.02)
    if k > 1:
        d = np.convolve(d, np.ones(k) / k, mode='same')
    return d


def tempo_track(dev, ref, win_s=30.0, hop_s=15.0, ppm_range=4000, ppm_step=100,
                max_lag_s=0.30):
    """Local device/reference tempo ratio in ppm, and the lag at each window.

    The amplitude envelope is warped by the candidate ratio and correlated
    against the device stream; a wrong ratio misaligns the far end of a 30 s
    window by >=150 ms, so the score picks the true ratio. A 30 s window is
    long enough that +-1000 ppm (one beat in 30 s) is resolved, and short
    enough that the ratio can be followed over the run."""
    de = onset_signal(envelope_at(dev, DEV_RATE))
    re_ = onset_signal(envelope_at(ref, 223721.0))
    win = int(win_s * ENV_RATE)
    hop = int(hop_s * ENV_RATE)
    ml = int(max_lag_s * ENV_RATE)
    n = min(len(de), len(re_))
    # coarse start alignment at zero warp (first 60 s)
    probe = de[:min(n, int(60 * ENV_RATE))]
    best, lag0 = -2.0, 0
    for lag in range(-ml, ml + 1, 2):
        a = probe
        b = re_[:len(a)]
        if lag > 0:
            a, b = probe[lag:], re_[:len(probe) - lag]
        elif lag < 0:
            a, b = probe[:-lag], re_[-lag:len(probe)]
        c = window_corr(a[:len(b)], b, 0) if len(b) > ENV_RATE else -2
        if c > best:
            best, lag0 = c, lag
    rows = []
    for start in range(0, max(1, n - win), hop):
        seg = de[start:start + win]
        if seg.mean() < 1e-6:
            continue
        best = (-2.0, 0, 0.0)
        for ppm in range(-ppm_range, ppm_range + 1, ppm_step):
            r = 1.0 + ppm * 1e-6
            for lag in range(lag0 - ml, lag0 + ml + 1, 5):
                base = start + lag
                if base < 0:
                    continue
                idx = base + np.arange(win) * r
                if idx[-1] >= len(re_) - 1:
                    continue
                warped = np.interp(idx, np.arange(len(re_)), re_)
                c = window_corr(seg, warped, 0)
                if c > best[0]:
                    best = (c, ppm, lag)
        # refine ratio around the winner
        if best[0] > 0:
            for ppm in range(best[1] - ppm_step, best[1] + ppm_step + 1, 20):
                r = 1.0 + ppm * 1e-6
                for lag in range(best[2] - 6, best[2] + 7):
                    base = start + lag
                    if base < 0:
                        continue
                    idx = base + np.arange(win) * r
                    if idx[-1] >= len(re_) - 1:
                        continue
                    warped = np.interp(idx, np.arange(len(re_)), re_)
                    c = window_corr(seg, warped, 0)
                    if c > best[0]:
                        best = (c, ppm, lag)
        rows.append((start / ENV_RATE, best[1], best[2] / ENV_RATE, best[0]))
    return rows


def summarize(res, ppm=None, times=None):
    minutes = max(1e-9, res['music_seconds'] / 60.0)
    out = {
        'seconds': round(res['seconds'], 2),
        'music_seconds': round(res['music_seconds'], 2),
        'rms': round(res['rms'], 1),
        'peak': res['peak'],
        'dropout_zero': len(res['dropout_zero']),
        'dropout_repeat': len(res['dropout_repeat']),
        'dropout_envelope': len(res['dropout_envelope']),
        'pops': len(res['pops']),
        'dropout_zero_per_min': round(len(res['dropout_zero']) / minutes, 2),
        'dropout_repeat_per_min': round(len(res['dropout_repeat']) / minutes, 2),
        'dropout_envelope_per_min': round(len(res['dropout_envelope']) / minutes, 2),
        'pops_per_min': round(len(res['pops']) / minutes, 2),
        'events': {
            'zero': [round(t, 3) for t, _ in res['dropout_zero'][:40]],
            'repeat': [round(t, 3) for t, _ in res['dropout_repeat'][:40]],
            'envelope': [round(t, 3) for t, _ in res['dropout_envelope'][:40]],
            'pops': [round(t, 3) for t, _, _ in res['pops'][:40]],
        },
    }
    if ppm:
        vals = [p for _, p in ppm]
        out['tempo_ppm'] = {'median': int(np.median(vals)), 'min': int(min(vals)),
                            'max': int(max(vals)), 'windows': len(vals),
                            'series': [[round(t, 1), p] for t, p in ppm]}
    return out


def selftest(path, out_dir):
    mono, sr, ch = read_wav(path)
    base = detect(mono, sr)
    rng = np.random.default_rng(7)
    n = len(mono)
    lo, hi = int(5 * sr), n - int(5 * sr)
    inj = mono.copy()
    pops = rng.integers(lo, hi, 12)
    for p in pops:                       # instantaneous step, then back
        inj[p:p + 1] += 9000
        inj[p + 1:p + 2] -= 9000
    drops = rng.integers(lo, hi - int(0.05 * sr), 6)
    for p in drops:                      # 20 ms fade to digital silence
        L = int(0.020 * sr)
        ramp = np.linspace(1, 0, L // 2)
        inj[p:p + L // 2] *= ramp
        inj[p + L // 2:p + L] = 0.0
    inj[inj > 32767] = 32767
    inj[inj < -32768] = -32768
    got = detect(inj, sr)
    drops_ms = [(t, ms) for t, ms in got['dropout_zero']]

    def near(ev, want, tol=0.05):
        return sum(1 for w in want if any(abs(e[0] - w / sr) < tol for e in ev))

    report = {
        'clean_count': {k: len(base[k]) for k in
                        ('dropout_zero', 'dropout_repeat', 'dropout_envelope', 'pops')},
        'injected_pops': len(pops),
        'found_pops_near_injected': near(got['pops'], pops),
        'injected_dropouts': len(drops),
        'found_zero_near_injected': near(drops_ms, drops),
        'found_envelope_near_injected': near(got['dropout_envelope'], drops),
        'total_after': {k: len(got[k]) for k in
                        ('dropout_zero', 'dropout_repeat', 'dropout_envelope', 'pops')},
    }
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / 'selftest.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    ok = (report['found_pops_near_injected'] >= 0.8 * len(pops) and
          report['found_zero_near_injected'] >= 0.8 * len(drops) and
          report['clean_count']['pops'] <= 2)
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--device', type=Path, required=True)
    p.add_argument('--reference', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--selftest', action='store_true')
    p.add_argument('--gate', type=float, default=MUSIC_GATE)
    a = p.parse_args()
    if a.selftest:
        return selftest(a.device, a.out or a.device.parent)
    mono, sr, ch = read_wav(a.device)
    res = detect(mono, sr, a.gate)
    ppm = times = None
    lag_info = None
    if a.reference:
        mono_r, sr_r, _ = read_wav(a.reference)
        rows = tempo_track(mono, mono_r)
        ppm = [(t, p) for t, p, _, c in rows if c >= 0.5]
        lag_info = {
            'lag_s_first': round(rows[0][2], 3) if rows else None,
            'lag_s_last': round(rows[-1][2], 3) if rows else None,
            'lag_s_min': round(min(r[2] for r in rows), 3) if rows else None,
            'lag_s_max': round(max(r[2] for r in rows), 3) if rows else None,
            'drift_ms_total': round(1000.0 * (rows[-1][2] - rows[0][2]), 1)
                              if rows else None,
            'score_min': round(min(r[3] for r in rows), 3) if rows else None,
            'series': [[round(t, 1), round(l, 4), round(c, 3)]
                       for t, _, l, c in rows],
        }
    summary = summarize(res, ppm, times)
    summary['device'] = str(a.device)
    summary['reference'] = str(a.reference) if a.reference else None
    summary['lag'] = lag_info
    text = json.dumps(summary, indent=2)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text + '\n')
        print(json.dumps({k: summary[k] for k in summary
                          if k not in ('events', 'tempo_ppm')}, indent=2))
        if ppm:
            print('tempo ppm: median %d range %d..%d over %d windows' %
                  (summary['tempo_ppm']['median'], summary['tempo_ppm']['min'],
                   summary['tempo_ppm']['max'], len(ppm)))
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
