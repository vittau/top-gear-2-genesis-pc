#!/usr/bin/env python3
"""Active-line evidence for the race crop, per country.

Reaches a track through the game's own ENTER PASSWORD screen, captures the
picture through the pre-race panels and the start countdown, while cruising and
(optionally) during a nitro burst and on both pause screens, then reports which
scanlines carry content (`tools/check_active_lines.py`).

Everything is stock presentation: widescreen Off, 60 fps Off, Hide overscan
Off, so each capture is the full 224-line picture.

  python3 tools/tg2_active_lines.py --port 4600 --out build/active/c00 \
      --country 0 --extras nitro,pause
  python3 tools/tg2_active_lines.py --port 4600 --out build/active/c05 \
      --country 5 --seconds 15
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, KEYS  # noqa: E402
import tg2_password as pw  # noqa: E402
from check_active_lines import check  # noqa: E402
from tg2_coverage import Coverage  # noqa: E402


def shot(runner: Runner, out: Path, name: str, shots: list):
    path = runner.screenshot(out / f'{name}.png')
    shots.append(dict(name=name, frame=runner.frame(), path=str(path)))
    return path


def to_race(cov, out, shots, limit=3000):
    """Tap START through the panels, capturing the countdown on the way.

    `Coverage.press_until_race` taps at most ten times every 200 frames, which
    is the proven path through the intro panels and the pre-race shop; the
    captures ride along between taps without adding taps of their own."""
    r = cov.r
    start = r.frame()
    taps = 0
    next_tap = start
    while r.frame() - start < limit:
        st = cov.state()
        if st.clock > 0:
            return st
        if r.frame() >= next_tap and taps < 12:
            cov.ui.tap('START', 7, 40)
            taps += 1
            for _ in range(3):
                r.wait_frame(r.frame() + 55)
                shot(r, out, f'pre-{r.frame():05d}', shots)
            next_tap = r.frame() + 60
        else:
            r.wait_frame(r.frame() + 20)
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4600)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--country', type=int, required=True)
    p.add_argument('--exe', type=Path,
                   default=Path(__file__).resolve().parents[1] / 'build/TG2Recomp')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--seconds', type=float, default=15.0)
    p.add_argument('--extras', default='', help='nitro,pause')
    p.add_argument('--widescreen', default='off',
                   help='presentation to capture; the crop evidence uses off on '
                        'purpose, 16:9/21:9 prove the cropped canvas')
    p.add_argument('--hide-overscan', default='0',
                   help='TG2_HIDE_OVERSCAN for the capture (1 = cropped picture)')
    p.add_argument('--nitro-at', type=int, default=600)
    a = p.parse_args()
    extras = {x.strip() for x in a.extras.split(',') if x.strip()}
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    args = SimpleNamespace(nitro=False, nitro_at=a.nitro_at, nitro_for=120,
                           shot_every=600, kp=1.0, kd=4.0, kc=0.0, deadband=9.0,
                           target_lat=0.0)
    r = Runner(port=a.port, out=out, exe=a.exe, rom=a.rom,
               widescreen=a.widescreen, max_frames=200000,
               env_extra={'TG2_HIDE_OVERSCAN': a.hide_overscan,
                          'TG2_RACE_60FPS': '0'},
               extra_args=['--turbo'])
    shots, result, meta = [], 'error', {}
    try:
        r.start()
        cov = Coverage(r, args)
        cov.ui.to_password_screen()
        cov.ui.type_symbols(pw.encode(country=a.country)['symbols'])
        cov.ui.submit()
        st = to_race(cov, out, shots)
        if st is None:
            result = 'no-race'
        else:
            meta['start_frame'] = st.frame
            shot(r, out, 'race-start', shots)
            frames = int(a.seconds * 60)
            prev_lat = None
            start = r.frame()
            next_shot = start + 90
            nitro_done = False
            pad = KEYS['B']
            while r.frame() - start < frames:
                st = r.step(pad)
                elapsed = st.frame - start
                u = (0.0 - st.lat_units) - 4.0 * (
                    0.0 if prev_lat is None else st.lat_units - prev_lat)
                pad = KEYS['B']
                if u > 9.0:
                    pad |= KEYS['RIGHT']
                elif u < -9.0:
                    pad |= KEYS['LEFT']
                nitro_window = 'nitro' in extras and a.nitro_at <= elapsed < a.nitro_at + 120
                if nitro_window:
                    pad |= KEYS['C']
                    if elapsed % 30 == 0:
                        shot(r, out, f'nitro-{st.frame:05d}', shots)
                prev_lat = st.lat_units
                if st.frame >= next_shot:
                    next_shot = st.frame + 240
                    shot(r, out, f'race-{st.frame:05d}', shots)
            if 'nitro' in extras and not nitro_done:
                shot(r, out, f'nitro-end-{r.frame():05d}', shots)
            r.set_input(0)
            if 'pause' in extras:
                cov.ui.tap('START', 7, 40)
                for index in range(3):
                    shot(r, out, f'pause-{index}', shots)
                    cov.ui.wait(20)
                cov.ui.tap('START', 7, 40)
                cov.ui.wait(40)
                shot(r, out, 'resume', shots)
            result = 'captured'
    finally:
        code = r.stop()
    results = []
    for entry in shots:
        info = check(Path(entry['path']))
        info.update(name=entry['name'], frame=entry['frame'])
        results.append(info)
    summary = dict(country=a.country, result=result, exit_code=code, meta=meta,
                   extras=sorted(extras),
                   password=pw.spaced(pw.encode(country=a.country)['symbols']),
                   pictures=results,
                   failures=[p['name'] for p in results if not p['ok']],
                   manifests=dict(
                       (name, sum(1 for line in (out / name).read_text(errors='replace').splitlines()
                                  if line.strip().startswith('[[')))
                       if (out / name).exists() else None
                       for name in ('dispatch_misses.toml', 'floor_coverage.toml',
                                    'interior_label_misses.toml', 'floor_unsafe.toml')))
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(dict(country=a.country, result=result, pictures=len(results),
                          failures=summary['failures'], manifests=summary['manifests'])))


if __name__ == '__main__':
    main()
