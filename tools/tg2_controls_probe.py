#!/usr/bin/env python3
"""Probe the in-race controls for nitro / brake behaviour, with screenshots.

Boots to a race, drives with the same PD lane-keeping law as the qualification
driver (so the car stays on the asphalt), and adds one extra button for a fixed
window at a time. Speed is compared between windows, so a real boost or brake
shows up as a speed delta, not as a driving accident. Also drives off the road
for a collision/slow-down capture.

  python3 tools/tg2_controls_probe.py --port 4470 --out build/qual/controls
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
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
    p.add_argument('--widescreen', default='off')
    p.add_argument('--60fps', dest='fps60', action='store_true')
    p.add_argument('--turbo', action='store_true')
    p.add_argument('--launch-delay', type=int, default=0)
    p.add_argument('--window', type=int, default=120)
    a = p.parse_args()
    a.stage_dumps = False
    a.sp_every = 0
    a.target_lat = 0.0
    a.kp = 1.0
    a.kd = 4.0
    a.kc = 0.0
    a.deadband = 9.0
    env = {'TG2_RACE_60FPS': '1'} if a.fps60 else {}
    extra = ['--turbo'] if a.turbo else []
    r = Runner(port=a.port, out=a.out, widescreen=a.widescreen, max_frames=30000,
               env_extra=env, extra_args=extra,
               video_driver='offscreen' if a.turbo else 'dummy')
    rows, phases = [], []
    try:
        r.start()
        d = Driver(r, a)
        d.boot_to_setup()
        st = d.press_start_until_race(label='pre')
        if st is None:
            raise RuntimeError('race never started')
        d.shot('race-start')
        plan = [('baseline-1', 0, a.window),
                ('plus-A', KEYS['A'], a.window),
                ('baseline-2', 0, a.window),
                ('plus-C', KEYS['C'], a.window),
                ('baseline-3', 0, a.window),
                ('offroad-LEFT', KEYS['LEFT'], 150),
                ('recover', 0, 240)]
        pad = KEYS['B']
        prev_lat = None
        for name, extra_key, frames in plan:
            speeds = []
            phases.append(dict(name=name, extra=f'{extra_key:02X}', frames=frames,
                               frame_start=r.frame()))
            for i in range(frames):
                st = r.step(pad)
                lat = st.lat_units
                base = d.control_pad(st, prev_lat, a)
                pad = base | extra_key
                prev_lat = lat
                speeds.append(st.speed)
                rows.append(dict(phase=name, frame=st.frame, clock=st.clock,
                                 lap=st.lap, lat=round(lat, 2), speed=st.speed,
                                 pos=st.pos, race_phase=st.phase,
                                 t2d8=st.t2d8, t2dc=st.t2dc))
                if i % 30 == 0:
                    d.shot(f'{name}-{st.frame}')
            phases[-1]['speed_start'] = speeds[0]
            phases[-1]['speed_end'] = speeds[-1]
            phases[-1]['speed_median'] = statistics.median(speeds)
            phases[-1]['frame_end'] = r.frame()
        d.shot('probe-end')
        (a.out / 'phases.json').write_text(json.dumps(phases, indent=2) + '\n')
        (a.out / 'controls.csv').write_text(
            'phase,frame,clock,lap,lat,speed,pos,race_phase,t2d8,t2dc\n' +
            '\n'.join(f"{x['phase']},{x['frame']},{x['clock']},{x['lap']},"
                      f"{x['lat']},{x['speed']},{x['pos']},{x['race_phase']},"
                      f"{x['t2d8']},{x['t2dc']}" for x in rows) + '\n')
        print(json.dumps(phases, indent=2))
    finally:
        r.stop()


if __name__ == '__main__':
    main()
