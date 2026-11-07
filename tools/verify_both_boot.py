#!/usr/bin/env python3
"""Regression test: BOTH persisted in settings.ini must not silence the music.

Owner bug on main e0e1f9b: with `[mods.racesound] mode = both` saved from an
earlier session, the title/menu music was a constant DC level. The cause was
patch 0011 releasing the Z80 from BUSREQ while routing was on: the music
mailbox could be read mid-write, the title-track command was lost, and the
driver never started.

This boots a stock ROM three times from a clean runtime directory -- BOTH,
MUSIC and SOUND EFFECTS persisted -- captures the first `--frames` frames and
requires the BOTH mix to correlate >= 0.99 with MUSIC (or SFX; on the title
screen all three modes play the same resident music driver) over the music
window. It also fails if the capture is a constant DC level.

  python3 tools/verify_both_boot.py --exe build/TG2Recomp

Exit code 0 = pass, 1 = regression. Everything lands in `--out`; other than
that the tool only writes inside its temporary runtime directories.
"""
from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / 'build' / 'TG2Recomp'
DEFAULT_ROM = Path.home() / 'roms/genesis/tg2.bin'
MIN_CORR = 0.99


def load(path, fps, win):
    w = wave.open(str(path))
    n, r, ch = w.getnframes(), w.getframerate(), w.getnchannels()
    lo = min(n, int(win[0] * r / fps))
    hi = min(n, int(win[1] * r / fps))
    w.setpos(lo)
    a = array('h')
    a.frombytes(w.readframes(max(0, hi - lo)))
    w.close()
    return a, r, ch


def corr(x, y):
    n = min(len(x), len(y))
    if n == 0:
        return 0.0
    mx = sum(x[:n]) / n
    my = sum(y[:n]) / n
    sxx = syy = sxy = 0.0
    for i in range(n):
        dx = x[i] - mx
        dy = y[i] - my
        sxx += dx * dx
        syy += dy * dy
        sxy += dx * dy
    return sxy / math.sqrt(sxx * syy) if sxx and syy else 0.0


def rms(a):
    return math.sqrt(sum(v * v for v in a) / len(a)) if a else 0.0


def run_mode(exe: Path, rom: Path, mode: str, frames: int, work: Path):
    d = work / mode
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, d / exe.name)
    (d / 'settings.ini').write_text(f'[mods.racesound]\nmode = {mode}\n')
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    wav = d / 'boot.wav'
    proc = subprocess.run(
        [str(d / exe.name), str(rom), '--no-launcher', '--max-frames', str(frames),
         '--turbo', '--wav', str(wav)],
        cwd=d, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (d / 'run.log').write_text(proc.stdout or '')
    if proc.returncode != 0 or not wav.exists():
        raise SystemExit(f'{mode}: run failed (exit {proc.returncode}); see {d}/run.log')
    return wav


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--exe', type=Path, default=DEFAULT_EXE)
    p.add_argument('--rom', type=Path, default=DEFAULT_ROM)
    p.add_argument('--frames', type=int, default=900)
    p.add_argument('--fps', type=float, default=60.0)
    p.add_argument('--window', default='400:900',
                   help='music window in guest frames (default 400:900)')
    p.add_argument('--out', type=Path, default=ROOT / 'build' / 'verify-both-boot')
    a = p.parse_args()
    win = tuple(int(v) for v in a.window.split(':'))
    if len(win) != 2 or win[1] <= win[0]:
        raise SystemExit('--window must be first:last')

    a.out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='tg2-both-boot-'))
    try:
        wavs = {m: run_mode(a.exe, a.rom, m, a.frames, work)
                for m in ('both', 'music', 'sfx')}
        sig = {}
        for m, w in wavs.items():
            sig[m] = load(w, a.fps, win)
            shutil.copy2(w, a.out / f'{m}.wav')

        b, r, ch = sig['both']
        m, _, _ = sig['music']
        s, _, _ = sig['sfx']
        rows = [('both vs music', corr(b, m)),
                ('both vs sfx', corr(b, s)),
                ('music vs sfx', corr(m, s))]
        rb, rm = rms(b), rms(m)
        dc = rb > 100.0 and max(b) - min(b) < 8 if b else True

        print(f'window {win[0]}..{win[1]} frames, {len(b) // ch / r:.2f} s, '
              f'rate {r} Hz:')
        for name, c in rows:
            print(f'  {name:14s} correlation {c:.6f}  ({"PASS" if c >= MIN_CORR else "FAIL"} >= {MIN_CORR})')
        print(f'  RMS both {rb:.1f}  music {rm:.1f}')
        ok = all(c >= MIN_CORR for _, c in rows) and not dc
        if dc:
            print('  FAIL: the BOTH capture is a constant DC level (no music)')
        print('PASS' if ok else 'REGRESSION')
        return 0 if ok else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
