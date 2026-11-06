#!/usr/bin/env python3
"""Race a chosen country from the menu's COUNTRY SELECTION screen.

The main menu has a CONTINUE submenu with PASSWORD and COUNTRY SELECTION. The
latter is a direct track picker, which reaches tracks the championship gate
would otherwise hide. This tool selects country N, records the track intro
(weather/time panel), then races for a few seconds and captures screenshots and
a race trace.

  python3 tools/tg2_country_probe.py --port 4470 --out build/qual/country-1 \
      --country 1 --race-frames 900
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, KEYS  # noqa: E402
from tg2_race_driver import Driver  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4470)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--country', type=int, default=0)
    p.add_argument('--race-frames', type=int, default=900)
    p.add_argument('--widescreen', default='off')
    p.add_argument('--60fps', dest='fps60', action='store_true')
    p.add_argument('--turbo', action='store_true', default=True)
    p.add_argument('--no-turbo', dest='turbo', action='store_false')
    a = p.parse_args()
    a.stage_dumps = False
    a.sp_every = 0
    a.target_lat = 0.0
    a.kp = 1.0
    a.kd = 4.0
    a.kc = 0.0
    a.deadband = 9.0
    a.launch_delay = 0
    env = {'TG2_RACE_60FPS': '1'} if a.fps60 else {}
    extra = ['--turbo'] if a.turbo else []
    r = Runner(port=a.port, out=a.out, widescreen=a.widescreen, max_frames=20000,
               env_extra=env, extra_args=extra,
               video_driver='offscreen' if a.turbo else 'dummy')
    rows = []
    try:
        r.start()
        d = Driver(r, a)
        r.wait_frame(700)
        d.tap('START', 8)                 # title -> menu
        r.wait_frame(1200)
        for i in range(3):                # 1P GAME -> CONTINUE
            d.tap('DOWN', 8)
            r.wait_frame(1350 + i * 100)
        d.tap('START', 8)                 # -> CONTINUE submenu
        r.wait_frame(1800)
        d.tap('DOWN', 8)                  # PASSWORD -> COUNTRY SELECTION
        r.wait_frame(2000)
        d.shot('submenu')
        d.tap('RIGHT', 8)                 # enter the country picker
        r.wait_frame(r.frame() + 200)
        d.tap('START', 8)
        r.wait_frame(2500)
        for i in range(a.country):
            d.tap('DOWN', 8)
            r.wait_frame(r.frame() + 140)
        d.shot(f'country-{a.country}-selected')
        d.tap('START', 8)                 # choose country
        r.wait_frame(r.frame() + 400)
        d.shot(f'country-{a.country}-after-select')
        # Walk whatever confirmation screens appear, shooting each one.
        for i in range(4):
            d.tap('START', 8)
            r.wait_frame(r.frame() + 420)
            d.shot(f'country-{a.country}-screen-{i}')
            st = r.state_and_frame()
            if st.clock > 0:
                break
        d.shot(f'country-{a.country}-race-start')
        pad = KEYS['B']
        prev_lat = None
        for i in range(a.race_frames):
            st = r.step(pad)
            lat = st.lat_units
            pad = d.control_pad(st, prev_lat, a)
            prev_lat = lat
            rows.append(dict(frame=st.frame, clock=st.clock, lap=st.lap,
                             lat=round(lat, 2), speed=st.speed, pos=st.pos,
                             phase=st.phase))
            if i % 120 == 0:
                d.shot(f'country-{a.country}-race-{st.frame}')
        (a.out / 'race.csv').write_text(
            'frame,clock,lap,lat,speed,pos,phase\n' +
            '\n'.join(f"{x['frame']},{x['clock']},{x['lap']},{x['lat']},"
                      f"{x['speed']},{x['pos']},{x['phase']}" for x in rows) + '\n')
        moving = [x for x in rows if x['speed'] > 500]
        summary = dict(country=a.country, race_frames=a.race_frames,
                       clock_start=rows[0]['clock'] if rows else None,
                       clock_end=rows[-1]['clock'] if rows else None,
                       max_speed=max((x['speed'] for x in rows), default=0),
                       moving_frames=len(moving),
                       lap_values=sorted({x['lap'] for x in rows}),
                       shots=d.shots)
        (a.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary, indent=2)[:600])
    finally:
        r.stop()


if __name__ == '__main__':
    main()
