#!/usr/bin/env python3
"""All-track coverage run: password in, 60 s of driving, evidence out.

Boots the stock game, enters a generated password through the game's own
ENTER PASSWORD screen, walks the track-intro screens, drives the loaded
track for a fixed number of wall frames with the closed-loop controller, and
writes the evidence (trace, screenshots, summary, runtime manifests).

  python3 tools/tg2_coverage.py --port 4490 --out build/qual/cov/c00-off \
      --country 0 --mode off
  python3 tools/tg2_coverage.py ... --mode ws169-edges

`--mode` picks the presentation: off / ws169 / ws169-edges (16:9 with
HUD Edges) / ws169-60 (16:9 + HUD Edges + the 60 fps option).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, RaceState, KEYS  # noqa: E402
import tg2_password as pw  # noqa: E402
from tg2_password_ui import PasswordUI  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Player-record nitro tank (byte pair at $FF18CA+$2D4); decrements while the
# nitro button is held (see docs/RAM_MAP.md and docs/PASSWORDS.md).
TANK = 0x18CA + 0x2D4

MODES = {
    'off':          dict(widescreen='off',  env={}),
    'ws169':        dict(widescreen='16:9', env={}),
    'ws169-edges':  dict(widescreen='16:9', env={'TG2_HUD_MODE': 'edges'}),
    'ws169-60':     dict(widescreen='16:9', env={'TG2_HUD_MODE': 'edges',
                                                 'TG2_RACE_60FPS': '1'}),
}


def manifests(out: Path) -> dict:
    counts = {}
    for name in ('dispatch_misses.toml', 'floor_coverage.toml',
                 'interior_label_misses.toml', 'floor_unsafe.toml'):
        path = out / name
        if not path.exists():
            counts[name] = None
            continue
        counts[name] = sum(1 for line in path.read_text(errors='replace').splitlines()
                           if line.strip().startswith('[['))
    return counts


class Coverage:
    def __init__(self, runner: Runner, args):
        self.r = runner
        self.args = args
        self.ui = PasswordUI(runner, args)
        self.trace = []
        self.shots = []

    def shot(self, name):
        path = self.r.screenshot(f'{name}.png')
        self.shots.append(dict(name=name, frame=self.r.frame(), path=str(path)))
        return path

    def state(self) -> RaceState:
        return self.r.state_and_frame()

    # -- race ----------------------------------------------------------
    def press_until_race(self, limit=2400, label='intro'):
        r = self.r
        start = r.frame()
        taps = 0
        next_tap = start
        intro_shots = 0
        while r.frame() - start < limit:
            st = self.state()
            self.trace.append(dict(frame=st.frame, clock=st.clock, lap=st.lap,
                                   speed=st.speed, lat=round(st.lat_units, 3),
                                   phase=st.phase, pad=0))
            if st.clock > 0:
                return st
            if r.frame() >= next_tap and taps < 10:
                if intro_shots < 3:
                    self.shot(f'{label}-{intro_shots}')
                    intro_shots += 1
                self.ui.tap('START', 7, 40)
                taps += 1
                next_tap = r.frame() + 200
        return None

    def drive(self, frames, prev_lat=None):
        r = self.r
        a = self.args
        pad = 0
        start = r.frame()
        last_shot = 0
        nitro = dict(enabled=bool(a.nitro), before=None, after=None,
                     peak_speed=0, peak_frame=None, samples=[])
        prev_speed = None
        while r.frame() - start < frames:
            elapsed = r.frame() - start
            st = r.step(pad)
            lat = st.lat_units
            d = 0.0 if prev_lat is None else lat - prev_lat
            u = a.kp * (a.target_lat - lat) - a.kd * d + a.kc * st.curv
            pad = KEYS['B']
            if u > a.deadband:
                pad |= KEYS['RIGHT']
            elif u < -a.deadband:
                pad |= KEYS['LEFT']
            # Nitro window: hold C (canonical bit 4) with throttle.
            in_window = a.nitro and a.nitro_at <= elapsed < a.nitro_at + a.nitro_for
            if in_window:
                pad |= KEYS['C']
            prev_lat = lat
            if a.nitro:
                if nitro['before'] is None and elapsed >= a.nitro_at - 20:
                    nitro['before'] = dict(frame=st.frame, speed=st.speed,
                                           tank=r.ram16(TANK))
                if in_window:
                    if st.speed > nitro['peak_speed']:
                        nitro['peak_speed'] = st.speed
                        nitro['peak_frame'] = st.frame
                    if elapsed % 20 == 0:
                        nitro['samples'].append(dict(frame=st.frame, speed=st.speed,
                                                     tank=r.ram16(TANK),
                                                     launched=elapsed))
                if nitro['after'] is None and elapsed >= a.nitro_at + a.nitro_for + 2:
                    nitro['after'] = dict(frame=st.frame, speed=st.speed,
                                          tank=r.ram16(TANK),
                                          peak=nitro['peak_speed'])
            self.trace.append(dict(frame=st.frame, clock=st.clock, lap=st.lap,
                                   speed=st.speed, lat=round(lat, 3),
                                   phase=st.phase, pad=pad, curv=st.curv,
                                   pos=st.pos))
            if st.frame - last_shot >= a.shot_every:
                last_shot = st.frame
                self.shot(f'race-{st.frame}')
        if a.nitro:
            self.nitro = nitro
        return prev_lat


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4490)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--country', type=int, required=True)
    p.add_argument('--mode', choices=sorted(MODES), default='off')
    p.add_argument('--seconds', type=float, default=62.0,
                   help='wall seconds of driving after the race clock starts')
    p.add_argument('--shot-every', type=int, default=600)
    p.add_argument('--kp', type=float, default=1.0)
    p.add_argument('--kd', type=float, default=4.0)
    p.add_argument('--kc', type=float, default=0.0)
    p.add_argument('--deadband', type=float, default=9.0)
    p.add_argument('--target-lat', type=float, default=0.0)
    p.add_argument('--realtime', action='store_true',
                   help='60 Hz video loop instead of the uncapped offscreen loop')
    p.add_argument('--nitro', action='store_true',
                   help='hold C (nitro) in a 2 s window and record tank/speed')
    p.add_argument('--nitro-at', type=int, default=1200,
                   help='wall frames after the clock starts to fire nitro')
    p.add_argument('--nitro-for', type=int, default=120,
                   help='frames to hold the nitro button')
    a = p.parse_args()
    mode = MODES[a.mode]
    env = dict(mode['env'])
    r = Runner(port=a.port, out=a.out, widescreen=mode['widescreen'],
               max_frames=200000, env_extra=env,
               extra_args=[] if a.realtime else ['--turbo'],
               video_driver='dummy' if a.realtime else 'offscreen')
    result = 'error'
    meta = {}
    cov = None
    try:
        r.start()
        cov = Coverage(r, a)
        cov.ui.to_password_screen()
        password = pw.encode(country=a.country)
        cov.ui.type_symbols(password['symbols'])
        before = cov.ui.submit()
        cov.ui.shot('setup')
        st = cov.press_until_race()
        if st is None:
            result = 'no-race'
        else:
            meta['start_frame'] = st.frame
            meta['start_clock'] = st.clock
            cov.shot('race-start')
            frames = int(a.seconds * 60)
            cov.drive(frames)
            end = cov.state()
            meta['end_frame'] = end.frame
            meta['end_clock'] = end.clock
            meta['laps_seen'] = sorted({t['lap'] for t in cov.trace})
            meta['max_speed'] = max((t['speed'] for t in cov.trace), default=0)
            moving = [t for t in cov.trace if t['speed'] > 500]
            meta['moving_frames'] = len(moving)
            meta['driven_seconds'] = round((end.frame - st.frame) / 60.0, 2)
            meta['race_seconds'] = round((end.clock - st.clock) / 65536.0 / 50.0, 2)
            cov.shot('race-end')
            result = 'driven'
    except Exception as exc:                     # noqa: BLE001
        result = f'error: {exc}'
        raise
    finally:
        code = r.stop()
        out = a.out
        if cov is not None:
            (out / 'trace.csv').write_text(
                'frame,clock,lap,speed,lat,phase,pad\n' +
                '\n'.join(f"{t['frame']},{t['clock']},{t['lap']},{t['speed']},"
                          f"{t['lat']},{t['phase']},{t.get('pad', 0)}"
                          for t in cov.trace) + '\n')
        summary = dict(country=a.country, mode=a.mode, result=result,
                       password=pw.spaced(pw.encode(country=a.country)['symbols']),
                       fields=pw.encode(country=a.country),
                       shots=(cov.shots if cov else []), meta=meta,
                       exit_code=code, manifests=manifests(out))
        if cov is not None and getattr(cov, 'nitro', None):
            summary['nitro'] = cov.nitro
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(dict(country=a.country, mode=a.mode, result=result,
                              manifests=summary['manifests'], **meta)))


if __name__ == '__main__':
    main()
