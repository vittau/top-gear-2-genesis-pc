#!/usr/bin/env python3
"""Live option-toggle regression probe (task 30 follow-up).

Each new audio option must be switchable *while the game runs*: title/menu
music, countdown, and mid-race, in MUSIC, SOUND EFFECTS and BOTH. This probe
drives the game through the standard menu route, inserts OPTION directives at
exact frames (the engine's input-script OPTION directive runs the same setter
the in-game menu uses), and compares the capture against an uninterrupted run of
the same route:

  * before the first toggle the two captures must be byte-identical;
  * after an option is switched back and the transition has settled, the two
    captures must be byte-identical again (no lost notes, no stale voices, no
    level offset);
  * while an option is on, only that option's documented effect may show:
    the measured RMS ratio has to stay inside the expected band, and nothing
    may collapse to silence;
  * switch transitions must not add pops (audio_glitch_detect).

  python3 tools/tg2_live_toggle_probe.py --exe build/TG2Recomp --out build/livetoggle

Writes <out>/<mode>-<option>/{ref,toggled}.wav, toggled.input, summary.json and
prints a table. Exit status 1 when any check fails.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

# option id, settings key, value while on, value while off
OPTIONS = [
    ('cleanfm',    'mods.cleanfm.enabled',     1, 0),
    ('dacresample', 'mods.dacresample.enabled', 1, 0),
    ('musicvol',   'mods.musicvol.level',     50, 100),
    ('sfxvol',     'mods.sfxvol.level',       50, 100),
]


def expected_band(mode, oid, window):
    """RMS ratio band the option's own effect may produce in that window.

    `window` is 'menu' (title/menu music, one source) or 'race'. A fader only
    acts on its source, and in BOTH mode the other source keeps its level, so
    the band depends on mode and window; None means "not measured here".
    """
    if window == 'menu':
        if oid == 'musicvol':
            return (0.35, 0.65)
        if oid == 'sfxvol':
            return None                 # no sound effects in the menus
        return (0.85, 1.05) if oid == 'cleanfm' else (0.95, 1.05)
    if oid == 'musicvol':
        return {'music': (0.35, 0.65), 'both': (0.55, 0.90)}.get(mode)
    if oid == 'sfxvol':
        return {'sfx': (0.35, 0.65), 'both': (0.55, 0.95)}.get(mode)
    return (0.85, 1.05) if oid == 'cleanfm' else (0.95, 1.05)
MODES = ('music', 'sfx', 'both')
SETTLE_S = 0.60


def gen_route(mode, out, rom):
    script = out / f'{mode}.base.input'
    exe = ROOT / 'build' / 'TG2Recomp'
    subprocess.run([sys.executable, str(ROOT / 'tools' / 'tg2_both_route.py'),
                    '--mode', mode, '--script-out', str(script), '--script-race',
                    '--exe', str(exe), '--rom', str(rom)],
                   check=True, capture_output=True, text=True)
    return script


def run(exe, rom, script, wav, log, userdir, env_extra=None):
    # Hermetic settings: every run reads the same stock settings.ini, and the
    # option changes it writes (the menu path persists them) never leak into
    # the next run or into the developer's own settings.
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy',
               GENESIS_USER_DIR=str(Path(userdir).resolve()) + '/')
    sid = Path(userdir) / 'settings.ini'
    sid.parent.mkdir(parents=True, exist_ok=True)
    sid.write_text('')     # stock settings for every run
    env.pop('TG2_MUSIC_VOL', None)
    env.pop('TG2_SFX_VOL', None)
    env.pop('TG2_CLEAN_FM', None)
    env.pop('TG2_DAC_RESAMPLE', None)
    env.pop('TG2_RACE_SOUND', None)
    if env_extra:
        env.update(env_extra)
    cmd = [str(exe), str(rom), '--no-launcher', '--widescreen', 'off',
           '--max-frames', '9000', '--turbo', '--wav', str(wav),
           '--input-script', str(script)]
    with open(log, 'w') as lf:
        p = subprocess.run(cmd, env=env, stdout=lf, stderr=subprocess.STDOUT)
    return p.returncode


def dump_markers(log):
    """Frames of the DUMP_RAM directives, in order (the route dumps RAM at the
    race start and every 600 frames after it)."""
    return [int(m.group(1)) for m in
            re.finditer(r'DUMP_RAM requested at frame (\d+)', log.read_text())]


def rewrite_with_options(script, markers, toggles):
    """Insert OPTION directives at absolute frames.

    Static WAITs are split; DUMP_RAM markers resynchronise the clock after the
    route's dynamic WAIT_RAM16. `toggles` is {frame: [(key, value), ...]}.
    """
    lines = script.read_text().splitlines()
    out = []
    cur = 0
    marker_i = 0
    pending = dict(toggles)
    for line in lines:
        s = line.strip()
        if s.startswith('DUMP_RAM'):
            if marker_i < len(markers):
                cur = markers[marker_i]
                marker_i += 1
            out.append(line)
            continue
        if s.startswith('WAIT ') and not s.startswith('WAIT_RAM'):
            n = int(s.split()[1])
            lo, hi = cur, cur + n
            while True:
                frames = sorted(f for f in pending if lo < f <= hi)
                if not frames:
                    break
                f = frames[0]
                out.append(f'WAIT {f - cur}')
                for key, value in pending.pop(f):
                    out.append(f'OPTION {key} {value}')
                cur = f
                lo = cur
            out.append(f'WAIT {hi - cur}')
            cur = hi
            continue
        # A toggle exactly on the current frame, before this directive.
        while cur in pending:
            for key, value in pending.pop(cur):
                out.append(f'OPTION {key} {value}')
        out.append(line)
    for f in sorted(pending):
        raise SystemExit(f'toggle frame {f} is past the end of the script')
    return '\n'.join(out) + '\n'


def per_second(wav):
    w = wave.open(str(wav))
    rate, n = w.getframerate(), w.getnframes()
    sums, cnt, i0 = [], [], 0
    block = 1 << 20
    while i0 < n:
        a = np.frombuffer(w.readframes(min(block, n - i0)), dtype='<i2')
        a = a.reshape(-1, 2).astype(np.float64)
        sec = (i0 + np.arange(a.shape[0])) // rate
        for s in np.unique(sec):
            m = sec == s
            while len(sums) <= s:
                sums.append(0.0); cnt.append(0)
            sums[s] += float((a[m] ** 2).sum()); cnt[s] += int(m.sum() * 2)
        i0 += a.shape[0]
    w.close()
    return [float(np.sqrt(s / c)) if c else 0.0 for s, c in zip(sums, cnt)], rate, n


def diff_seconds(a, b):
    """Per-second counts of differing samples, plus first/last difference."""
    wa, wb = wave.open(str(a)), wave.open(str(b))
    if wa.getnframes() != wb.getnframes():
        return None
    rate = wa.getframerate(); n = wa.getnframes(); i0 = 0
    per = {}; first = last = None
    block = 1 << 20
    while i0 < n:
        want = min(block, n - i0)
        x = np.frombuffer(wa.readframes(want), dtype='<i2').reshape(-1, 2)
        y = np.frombuffer(wb.readframes(want), dtype='<i2').reshape(-1, 2)
        d = (x != y).any(axis=1)
        if d.any():
            idx = np.nonzero(d)[0]
            sec = (i0 + idx) // rate
            for s in np.unique(sec):
                per[int(s)] = per.get(int(s), 0) + int((sec == s).sum())
            if first is None:
                first = float((i0 + idx[0]) / rate)
            last = float((i0 + idx[-1]) / rate)
        i0 += want
    wa.close(); wb.close()
    return {'per_second': per, 'first': first, 'last': last,
            'seconds': sorted(per), 'n_seconds': n / rate}


def pops(wav):
    out = subprocess.run([sys.executable, str(ROOT / 'tools' / 'audio_glitch_detect.py'),
                          '--device', str(wav)], capture_output=True, text=True)
    d = json.loads(out.stdout)
    return {'pops': d['pops'], 'zero': d['dropout_zero'],
            'repeat': d['dropout_repeat']}


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--out', type=Path, default=ROOT / 'build/livetoggle')
    p.add_argument('--modes', default=','.join(MODES))
    p.add_argument('--only', default='', help='comma list of option ids')
    a = p.parse_args()

    a.out.mkdir(parents=True, exist_ok=True)
    modes = [m for m in a.modes.split(',') if m]
    only = [o for o in a.only.split(',') if o]
    options = [o for o in OPTIONS if not only or o[0] in only]

    results = {}
    for mode in modes:
        base = gen_route(mode, a.out, a.rom)
        ref_dir = a.out / f'{mode}-ref'
        ref_dir.mkdir(exist_ok=True)
        ref_wav = ref_dir / 'run.wav'
        log = ref_dir / 'run.log'
        rc = run(a.exe, a.rom, base, ref_wav, log, a.out / 'userdir')
        markers = dump_markers(log)
        if rc != 0 or not markers:
            raise SystemExit(f'{mode}: reference run failed (rc={rc}, markers={markers})')
        race = markers[0]
        ref_rms, rate, nframes = per_second(ref_wav)
        ref_pops = pops(ref_wav)
        print(f'[{mode}] reference ok: {nframes / rate:.1f}s, race starts at frame {race}')

        # menu music (well before the route leaves the menu), countdown, early
        # race, mid race
        points = [900, race - 200, race + 120, race + 900]
        for oid, key, on, off in options:
            toggles = {}
            seq = [on, off, on, off]
            for f, v in zip(points, seq):
                toggles.setdefault(f, []).append((key, v))
            script = a.out / f'{mode}-{oid}.input'
            script.write_text(rewrite_with_options(base, markers, dict(toggles)))
            d = a.out / f'{mode}-{oid}'
            d.mkdir(exist_ok=True)
            wav = d / 'toggled.wav'
            rc = run(a.exe, a.rom, script, wav, d / 'toggled.log', a.out / 'userdir')
            if rc != 0:
                raise SystemExit(f'{mode}/{oid}: run failed rc={rc}')
            t_rms, _, tn = per_second(wav)
            diff = diff_seconds(ref_wav, wav)
            last_off = points[-1]
            settle_frame = last_off + int(SETTLE_S * 60)
            ok = True
            notes = []
            if diff is None:
                ok = False; notes.append('capture length differs')
            else:
                bad_before = [s for s in diff['seconds']
                              if s < points[0] / 60.0 - 0.1]
                if bad_before:
                    ok = False
                    notes.append(f'differs before the first toggle at {bad_before[:6]}s')
                after = [s for s in diff['seconds']
                         if s * 60.0 > settle_frame]
                if after:
                    ok = False
                    notes.append(f'not restored after the last off-toggle: '
                                 f'{len(after)} s differ (first {after[:4]})')
                # on-windows: the option's own effect only, and no silence
                # The menu window stops at 32 s: the route leaves the menus
                # for the race scene around frame 2100, and from there the
                # sound is the race's own (in SOUND EFFECTS its content
                # correlates 0.00 with the music-mode capture of the same span).
                menu_end = min(points[1], 32 * 60)
                for window, (w0, w1) in (('menu', (points[0], menu_end)),
                                         ('race', (points[2], points[3]))):
                    band = expected_band(mode, oid, window)
                    if band is None:
                        continue
                    s0 = int(w0 / 60.0) + 1
                    s1 = int(w1 / 60.0) - 1
                    if s1 <= s0:
                        continue
                    r = [t_rms[s] / ref_rms[s] for s in range(s0, s1)
                         if ref_rms[s] > 600]
                    dead = [s for s in range(s0, s1)
                            if t_rms[s] < 1 and ref_rms[s] > 600]
                    if dead:
                        ok = False; notes.append(f'silent while on ({window}) at {dead[:4]}s')
                    if r:
                        lo, hi = band
                        out_of_band = [x for x in r if not (lo <= x <= hi)]
                        if out_of_band:
                            ok = False
                            notes.append(f'level out of band while on ({window}): '
                                         f'{min(r):.3f}..{max(r):.3f} (want {band})')
            t_pops = pops(wav)
            new_pops = t_pops['pops'] - ref_pops['pops']
            if new_pops > 0:
                ok = False; notes.append(f'{new_pops} extra pops')
            results[f'{mode}/{oid}'] = {
                'ok': ok, 'notes': notes,
                'ratio_median': round(float(np.median(
                    [t_rms[s] / ref_rms[s] for s in range(2, min(len(ref_rms), len(t_rms)))
                     if ref_rms[s] > 50] or [0])), 4),
                'pops': t_pops['pops'], 'ref_pops': ref_pops['pops'],
                'diff_seconds': len(diff['seconds']) if diff else -1,
                'diff_last': diff['last'] if diff else None,
            }
            print(f'  {oid:12s} {"PASS" if ok else "FAIL"} '
                  f'ratio={results[f"{mode}/{oid}"]["ratio_median"]:.3f} '
                  f'diff_s={results[f"{mode}/{oid}"]["diff_seconds"]} '
                  f'pops={t_pops["pops"]} {" ".join(notes)}')

        # --- RACE SOUND changed mid-race: the selection changes at once but its
        # routing/policy layer is adopted at the next race, so the running race
        # must be audio-neutral - byte-identical to the same route without the
        # toggles. (The menu switch to BOTH is the documented route of task 20
        # and is not part of this check.)
        key = 'mods.racesound.mode'
        sel = {'sfx': 0, 'music': 1, 'both': 2}[mode]
        other = 1 if sel == 2 else 2      # the switch to test (and back)
        toggles = {race + 120: [(key, other)], race + 400: [(key, sel)],
                   race + 900: [(key, other)], race + 1500: [(key, sel)]}
        script = a.out / f'{mode}-racesound.input'
        script.write_text(rewrite_with_options(base, markers, dict(toggles)))
        d = a.out / f'{mode}-racesound'
        d.mkdir(exist_ok=True)
        wav = d / 'toggled.wav'
        rc = run(a.exe, a.rom, script, wav, d / 'toggled.log', a.out / 'userdir')
        if rc != 0:
            raise SystemExit(f'{mode}/racesound: run failed rc={rc}')
        diff = diff_seconds(ref_wav, wav)
        t_pops = pops(wav)
        ok = diff is not None and not diff['seconds'] and t_pops['pops'] <= ref_pops['pops']
        notes = [] if ok else [
            ('capture length differs' if diff is None else
             f'{len(diff["seconds"])} s differ (first {diff["seconds"][:4]})'),
            f'pops {t_pops["pops"]} vs {ref_pops["pops"]}']
        results[f'{mode}/racesound'] = {
            'ok': ok, 'notes': [n for n in notes if n],
            'diff_seconds': len(diff['seconds']) if diff else -1,
            'diff_last': diff['last'] if diff else None,
            'pops': t_pops['pops'], 'ref_pops': ref_pops['pops'],
        }
        print(f'  {"racesound":12s} {"PASS" if ok else "FAIL"} '
              f'diff_s={results[f"{mode}/racesound"]["diff_seconds"]} '
              f'pops={t_pops["pops"]} {" ".join(n for n in notes if n)}')

    (a.out / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    bad = [k for k, v in results.items() if not v['ok']]
    print(f'\n{len(results) - len(bad)}/{len(results)} passed'
          + (f'; failed: {", ".join(bad)}' if bad else ''))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
