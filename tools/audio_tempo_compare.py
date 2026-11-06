#!/usr/bin/env python3
"""Compare the musical tempo and pitch of two recordings of the same music.

The reference is normally an accurate emulator's render of the cartridge
(see tools/gpgx_render.c); the measurement is the native port's offline tap or
its real-device capture. The tool reports, for the pair:

  * the global tempo ratio (measurement / reference), in % and in BPM;
  * the local tempo ratio in 1 s windows (a sliding 8 s window), plus its
    standard deviation and its largest deviation;
  * the pitch offset in cents (long-term log-spectrum shift).

No resampling of the inputs is done: each file's own sample rate is used to
build a 100 Hz onset/energy envelope on log-spaced bands, and tempo is
estimated by warping the measured envelope over a ratio grid and correlating it
with the reference. Pitch is the maximum of the cross-correlation of the two
long-term average log-spectra over a cents-shift grid.

  python3 tools/audio_tempo_compare.py REF.wav MEAS.wav [--json out.json]
  python3 tools/audio_tempo_compare.py --selftest

--selftest synthesises a melody with known onsets, then builds a tempo-only
variant (events moved in time, same pitches) and a pitch-only variant (same
event times, shifted pitches) and checks that the tool recovers each without
confusing the two. Nothing is written outside --json.
"""
import argparse
import json
import math
import sys
import wave

import numpy as np

ENVELOPE_FPS = 100.0
BAND_LO_HZ = 60.0
BAND_HI_HZ = 7800.0
N_BANDS = 48


# ---------------------------------------------------------------- WAV input
def load_wav(path):
    """(rate, mono float32 in [-1,1]) for a PCM WAV."""
    with wave.open(path, 'rb') as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        width = w.getsampwidth()
        n = w.getnframes()
        raw = w.readframes(n)
    if width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        data = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = (b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16))
        v = np.where(v & 0x800000, v - 0x1000000, v)
        data = v.astype(np.float32) / 8388608.0
    elif width == 4:
        data = np.frombuffer(raw, dtype='<i4').astype(np.float32) / 2147483648.0
    else:
        raise SystemExit('unsupported sample width %d' % width)
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return rate, data


# ------------------------------------------------------- band/onset envelope
def band_edges(rate, nfft_hz):
    """Log-spaced band edges within [BAND_LO_HZ, min(BAND_HI_HZ, 0.45*rate)]."""
    hi = min(BAND_HI_HZ, 0.45 * rate)
    return np.geomspace(BAND_LO_HZ, hi, N_BANDS + 1)


def onset_envelope(data, rate, fps=ENVELOPE_FPS):
    """Log-band energy flux at `fps` frames/s, plus per-band log energies."""
    hop = max(1, int(round(rate / fps)))
    nfft = 1 << int(math.ceil(math.log2(max(8 * hop, 256))))
    win = np.hanning(nfft).astype(np.float32)
    edges = band_edges(rate, rate)
    freqs = np.fft.rfftfreq(nfft, 1.0 / rate)
    masks = [(freqs >= edges[i]) & (freqs < edges[i + 1]) for i in range(N_BANDS)]
    masks = [m for m in masks if m.any()]
    frames = 1 + (len(data) - nfft) // hop
    if frames < 4:
        raise SystemExit('signal too short for an onset envelope')
    energy = np.empty((frames, len(masks)), dtype=np.float32)
    window_starts = np.arange(frames) * hop
    # Chunked so peak memory stays small for 223 kHz captures.
    chunk = 512
    for start in range(0, frames, chunk):
        stop = min(frames, start + chunk)
        idx = window_starts[start:stop, None] + np.arange(nfft)[None, :]
        seg = data[idx] * win
        spec = np.abs(np.fft.rfft(seg, axis=1)) ** 2
        for b, m in enumerate(masks):
            energy[start:stop, b] = spec[:, m].mean(axis=1)
    log_e = np.log10(energy + 1e-10)
    flux = np.diff(log_e, axis=0, prepend=log_e[:1])
    env = np.maximum(flux, 0.0).sum(axis=1)
    return env.astype(np.float64), np.log10(energy + 1e-10)


def beat_bpm(env, fps=ENVELOPE_FPS, lo_bpm=60.0, hi_bpm=200.0):
    """Reference tempo from the envelope's own autocorrelation."""
    x = env - env.mean()
    n = len(x)
    if n < 4 * fps or not np.any(x):
        return float('nan')
    ac = np.correlate(x, x, mode='full')[n - 1:]
    ac /= (ac[0] + 1e-12)
    lo = int(fps * 60.0 / hi_bpm)
    hi = min(len(ac) - 1, int(fps * 60.0 / lo_bpm))
    if hi <= lo:
        return float('nan')
    lag = lo + int(np.argmax(ac[lo:hi]))
    return 60.0 * fps / lag


# ------------------------------------------------------------- tempo search
def _norm(x):
    x = x - x.mean()
    s = np.sqrt((x * x).sum())
    return x / s if s > 0 else x


def _corr_at(warped, ref, lag):
    """Normalised correlation of `warped` against `ref` shifted by `lag` samples."""
    if lag >= 0:
        a = warped[:len(warped) - lag] if lag else warped
        b = ref[lag:]
    else:
        a = warped[-lag:]
        b = ref[:len(ref) + lag]
    n = min(len(a), len(b))
    if n < 16:
        return -1.0, n
    a = _norm(a[:n])
    b = _norm(b[:n])
    return float((a * b).sum()), n


def _best_lag(warped, ref, search):
    """Best lag in [-search, +search] (samples) by direct correlation."""
    best = (-2.0, 0)
    step = max(1, search // 200)
    for lag in range(-search, search + 1, step):
        c, _ = _corr_at(warped, ref, lag)
        if c > best[0]:
            best = (c, lag)
    # refine around the coarse winner
    for lag in range(best[1] - step, best[1] + step + 1):
        c, _ = _corr_at(warped, ref, lag)
        if c > best[0]:
            best = (c, lag)
    return best


def warp(env, ratio, n_out=None):
    """Resample `env` so that its event spacing becomes ratio * original.

    ratio > 1 means the measured performance is faster: its events are closer
    together, so reading it at positions t/ratio... we instead stretch the
    *measured* envelope by `ratio` and compare with the reference timeline.
    """
    n_out = n_out or len(env)
    t = np.arange(n_out, dtype=np.float64) / ratio
    return np.interp(t, np.arange(len(env), dtype=np.float64), env,
                     left=env[0], right=env[-1])


def global_tempo(ref, meas, coarse=0.06, cstep=0.001, fstep=0.0002,
                 lag_search=int(4 * ENVELOPE_FPS)):
    """(ratio, correlation, lag) maximising correlation over tempo candidates."""
    n = min(len(ref), int(len(meas) / (1.0 - coarse)))
    best = (-2.0, 1.0, 0)
    ratios = np.arange(1.0 - coarse, 1.0 + coarse + 1e-9, cstep)
    for r in ratios:
        w = warp(meas, r, n)
        c, lag = _best_lag(w, ref, lag_search)
        if c > best[0]:
            best = (c, r, lag)
    # fine pass, keeping the winning lag search narrow but re-searched
    centre = best[1]
    for r in np.arange(centre - cstep, centre + cstep + 1e-9, fstep):
        w = warp(meas, r, n)
        c, lag = _best_lag(w, ref, lag_search)
        if c > best[0]:
            best = (c, r, lag)
    return best[1], best[0], best[2]


def local_tempo(ref, meas, global_ratio, global_lag, win_s=8.0, step_s=1.0,
                span=0.015, rstep=0.0005):
    """Tempo ratio per 1 s step from sliding `win_s` windows."""
    fps = ENVELOPE_FPS
    win = int(win_s * fps)
    step = int(step_s * fps)
    out = []
    n = min(len(ref), len(meas))
    for start in range(0, n - win, step):
        r_ref = ref[start:start + win]
        # The measured window that corresponds to this reference window under
        # the global warp. Its position follows the ratio; the local search is
        # allowed to move it a little.
        m0 = int((start - global_lag) / global_ratio)
        if m0 < 0 or m0 + win + 4 * fps >= len(meas):
            continue
        best = (-2.0, 1.0, 0)
        for r in np.arange(global_ratio * (1 - span), global_ratio * (1 + span) + 1e-9, rstep):
            m_len = int(win / r * global_ratio)
            seg = meas[m0:m0 + max(m_len, win) + 1]
            if len(seg) < win:
                continue
            w = warp(seg, r / global_ratio, win + int(0.4 * fps))
            c, lag = _best_lag(w, r_ref, int(0.4 * fps))
            if c > best[0]:
                best = (c, r, lag)
        if best[0] > 0.02:
            out.append({'t': start / fps, 'ratio': float(best[1]),
                        'corr': float(best[0])})
    return out


# ------------------------------------------------------------------ pitch
def log_spectrum(data, rate, f_lo=60.0, f_hi=7800.0, cents_step=1.0):
    """Long-term average log spectrum sampled on a cents grid."""
    nfft = 1 << int(math.ceil(math.log2(max(2048, rate // 8))))
    win = np.hanning(nfft).astype(np.float32)
    hop = nfft // 2
    frames = 1 + (len(data) - nfft) // hop
    if frames < 2:
        return None, None
    acc = np.zeros(nfft // 2 + 1, dtype=np.float64)
    chunk = 256
    for start in range(0, frames, chunk):
        stop = min(frames, start + chunk)
        idx = (np.arange(start, stop) * hop)[:, None] + np.arange(nfft)[None, :]
        spec = np.abs(np.fft.rfft(data[idx] * win, axis=1)) ** 2
        acc += spec.sum(axis=0)
    freqs = np.fft.rfftfreq(nfft, 1.0 / rate)
    sel = (freqs >= f_lo) & (freqs <= min(f_hi, 0.45 * rate))
    f = freqs[sel]
    a = np.log10(acc[sel] + 1e-12)
    n_cents = int(1200.0 * math.log2(f[-1] / f[0]) / cents_step)
    grid_cents = np.arange(n_cents) * cents_step
    grid_hz = f[0] * 2.0 ** (grid_cents / 1200.0)
    grid = np.interp(grid_hz, f, a)
    return grid, grid_cents


def pitch_cents(ref_spec, meas_spec, axis_step_cents=1.0, max_cents=120.0, step_cents=0.5):
    """Shift (in cents) that best aligns meas onto ref on the log axis."""
    a = _norm(ref_spec)
    best = (-2.0, 0.0)
    for shift in np.arange(-max_cents, max_cents + 1e-9, step_cents):
        d = int(round(shift / axis_step_cents))
        if d == 0:
            b = meas_spec
        elif d > 0:
            b = np.concatenate([np.zeros(d), meas_spec[:-d]])
        else:
            b = np.concatenate([meas_spec[-d:], np.zeros(-d)])
        c = float((a * _norm(b)).sum())
        if c > best[0]:
            best = (c, float(shift))
    # The search shifts the measurement to align it onto the reference, so a
    # measurement that is sharp by N cents needs a -N cent shift. Report the
    # offset of the measurement, not the correction.
    return -best[1], best[0]


def compare(ref_path, meas_path, ref_span=None, meas_span=None):
    rr, ref = load_wav(ref_path)
    mr, meas = load_wav(meas_path)
    if ref_span:
        ref = ref[int(ref_span[0] * rr):int(ref_span[1] * rr)]
    if meas_span:
        meas = meas[int(meas_span[0] * mr):int(meas_span[1] * mr)]
    renv, _ = onset_envelope(ref, rr)
    menv, _ = onset_envelope(meas, mr)
    ratio, corr, lag = global_tempo(renv, menv)
    loc = local_tempo(renv, menv, ratio, lag)

    bpm = beat_bpm(renv)
    out = {
        'ref': {'path': ref_path, 'rate': rr, 'seconds': len(ref) / rr},
        'meas': {'path': meas_path, 'rate': mr, 'seconds': len(meas) / mr},
        'global': {
            'ratio': ratio,
            'percent': (ratio - 1.0) * 100.0,
            'corr': corr,
            'lag_s': lag / ENVELOPE_FPS,
            'ref_bpm': bpm,
            'meas_bpm': bpm * ratio if not math.isnan(bpm) else float('nan'),
        },
        'local': {},
        'pitch': {},
    }
    if len(loc) >= 3:
        ratios = np.array([e['ratio'] for e in loc])
        corrs = np.array([e['corr'] for e in loc])
        w = np.clip(corrs, 0, None)
        mean = float((ratios * w).sum() / (w.sum() + 1e-12))
        dev = ratios - mean
        out['local'] = {
            'windows': len(loc),
            'mean_ratio': mean,
            'mean_percent': (mean - 1.0) * 100.0,
            'std_percent': float(np.sqrt((dev * dev * w).sum() / (w.sum() + 1e-12)) * 100.0),
            'max_deviation_percent': float(np.abs(dev).max() * 100.0),
            'median_percent': float((np.median(ratios) - 1.0) * 100.0),
            'series': loc,
        }

    # Pitch: compare the music span both files really contain.
    fps = ENVELOPE_FPS
    start = max(0, int(lag / fps)) if lag > 0 else 0
    t_ref0 = max(0.0, -lag / fps)
    span_s = min(len(ref) / rr - t_ref0, (len(meas) / mr - start / fps) / ratio)
    span_s = max(2.0, span_s)
    rs = ref[int(t_ref0 * rr):int((t_ref0 + span_s) * rr)]
    ms = meas[int(start / fps * mr):int((start / fps + span_s * ratio) * mr)]
    rg, rgc = log_spectrum(rs, rr)
    mg, _ = log_spectrum(ms, mr)
    if rg is not None and mg is not None and len(rg) == len(mg):
        cents, pcorr = pitch_cents(rg, mg, axis_step_cents=float(rgc[1] - rgc[0]))
        out['pitch'] = {'cents': cents, 'corr': pcorr, 'span_s': span_s}
    return out


# ---------------------------------------------------------------- selftest
def synth_melody(rate=44100, seconds=30.0, bpm=128.0, pitch_cents=0.0,
                 tempo_ratio=1.0, seed=7):
    """Decaying harmonic notes on a beat grid (tempo/pitch independently set)."""
    n = int(rate * seconds)
    x = np.zeros(n, dtype=np.float64)
    rng = np.random.default_rng(seed)
    scale = [0, 3, 5, 7, 10, 12, 15, 14, 12, 7, 5, 3]
    beat = 60.0 / bpm / tempo_ratio
    t = 0.0
    i = 0
    while t < seconds - 0.4:
        semi = scale[i % len(scale)] + 12 * (i // 24 % 2)
        f0 = 220.0 * 2.0 ** ((semi + pitch_cents / 100.0) / 12.0)
        start = int(t * rate)
        length = min(int(0.35 * rate), n - start)
        if length > 8:
            tt = np.arange(length) / rate
            env = np.exp(-6.0 * tt)
            sig = (np.sin(2 * np.pi * f0 * tt) + 0.5 * np.sin(2 * np.pi * 2 * f0 * tt)
                   + 0.25 * np.sin(2 * np.pi * 3 * f0 * tt))
            x[start:start + length] += 0.3 * env * sig
        if i % 4 == 2:   # a bass note every other half bar keeps the low band alive
            fb = f0 / 2.0
            start = int(t * rate)
            length = min(int(0.45 * rate), n - start)
            if length > 8:
                tt = np.arange(length) / rate
                x[start:start + length] += 0.2 * np.exp(-4.0 * tt) * np.sin(2 * np.pi * fb * tt)
        x[start:start + min(length, n - start)] += 0.002 * rng.standard_normal(
            min(length, n - start))
        t += beat
        i += 1
    peak = np.abs(x).max()
    if peak > 0:
        x *= 0.7 / peak
    return rate, x.astype(np.float32)


def write_wav(path, rate, x):
    pcm = np.clip(x * 32767.0, -32768, 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def selftest(tmpdir):
    import os
    ok = True
    base_rate, base = synth_melody()
    write_wav(os.path.join(tmpdir, 'st-ref.wav'), base_rate, base)
    cases = [
        ('tempo+1.5%', synth_melody(tempo_ratio=1.015), 1.015, 0.0, 0.15),
        ('tempo-1.0%', synth_melody(tempo_ratio=0.99), 0.99, 0.0, 0.15),
        ('tempo+0.1%', synth_melody(tempo_ratio=1.001), 1.001, 0.0, 0.03),
        ('pitch+25c', synth_melody(pitch_cents=25.0), 1.0, 25.0, 22.0),
        ('pitch-40c', synth_melody(pitch_cents=-40.0), 1.0, -40.0, 20.0),
        ('identity', synth_melody(), 1.0, 0.0, 0.02),
    ]
    for name, (rate, x), want_t, want_c, tol in cases:
        path = os.path.join(tmpdir, 'st-case.wav')
        write_wav(path, rate, x)
        res = compare(os.path.join(tmpdir, 'st-ref.wav'), path)
        got_t = (res['global']['ratio'] - 1.0) * 100.0
        got_c = res['pitch'].get('cents', float('nan'))
        tol_t = abs(want_t - 1.0) * 100.0 * 0.5 + 0.03   # 50% of the effect + noise floor
        tol_c = tol + 2.0 if want_c else 3.0
        good = abs(got_t - (want_t - 1.0) * 100.0) <= tol_t and abs(got_c - want_c) <= tol_c
        ok = ok and good
        print('%-12s want tempo %+7.3f%% pitch %+6.1fc  got tempo %+7.3f%% '
              'pitch %+6.1fc  %s' % (name, (want_t - 1) * 100, want_c, got_t, got_c,
                                     'PASS' if good else 'FAIL'))
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('ref', nargs='?')
    p.add_argument('meas', nargs='?')
    p.add_argument('--json')
    p.add_argument('--selftest', action='store_true')
    p.add_argument('--ref-span', help='start,end seconds of the reference')
    p.add_argument('--meas-span', help='start,end seconds of the measurement')
    a = p.parse_args()
    if a.selftest:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            code = selftest(d)
        return code
    if not a.ref or not a.meas:
        p.error('need a reference and a measurement (or --selftest)')
    span = lambda s: [float(v) for v in s.split(',')] if s else None
    res = compare(a.ref, a.meas, span(a.ref_span), span(a.meas_span))
    g = res['global']
    print('reference : %s  (%.1f s @ %d Hz)' % (res['ref']['path'], res['ref']['seconds'],
                                                res['ref']['rate']))
    print('measured  : %s  (%.1f s @ %d Hz)' % (res['meas']['path'], res['meas']['seconds'],
                                                res['meas']['rate']))
    print('global tempo ratio : %.5f  (%+.3f %%)   corr %.3f  lag %.3f s' %
          (g['ratio'], g['percent'], g['corr'], g['lag_s']))
    if not math.isnan(g['ref_bpm']):
        print('reference tempo    : %.2f BPM   measured %.2f BPM' %
              (g['ref_bpm'], g['meas_bpm']))
    loc = res['local']
    if loc:
        print('local tempo        : %d windows, mean %+.3f %%, std %.3f %%, '
              'max deviation %.3f %%' % (loc['windows'], loc['mean_percent'],
                                         loc['std_percent'], loc['max_deviation_percent']))
    pit = res['pitch']
    if pit:
        print('pitch offset       : %+.1f cents (corr %.3f, %.1f s span)' %
              (pit['cents'], pit['corr'], pit['span_s']))
    if a.json:
        with open(a.json, 'w') as f:
            json.dump(res, f, indent=2)
            f.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
