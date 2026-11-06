#!/usr/bin/env python3
"""Probe the in-race controls for nitro / brake behaviour, with screenshots.

Boots to a race, holds throttle, then probes A and C while logging speed, the
lateral position and the player-record timers that the speed model touches
(`+$34`, `+$36`, `+$38`, `+$2D8`, `+$2DC`). Also drives off the road so a
collision/slow-down is captured.

  python3 tools/tg2_controls_probe.py --port 4470 --out build/qual/controls
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, KEYS  # noqa: E402
from tg2_race_driver import Driver  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STATE_LO = 0x1600
STATE_LEN = 0x0E00


def s16(block, addr):
    o = addr - STATE_LO
    return struct.unpack('>h', block[o:o + 2])[0]


def u32(block, addr):
    o = addr - STATE_LO
    return struct.unpack('>I', block[o:o + 4])[0]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4470)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--widescreen', default='off')
    p.add_argument('--60fps', dest='fps60', action='store_true')
    p.add_argument('--turbo', action='store_true')
    a = p.parse_args()
    env = {'TG2_RACE_60FPS': '1'} if a.fps60 else {}
    extra = ['--turbo'] if a.turbo else []
    r = Runner(port=a.port, out=a.out, widescreen=a.widescreen, max_frames=20000,
               env_extra=env, extra_args=extra,
               video_driver='offscreen' if a.turbo else 'dummy')
    rows = []
    phases = []
    try:
        r.start()
        d = Driver(r, a)
        d.boot_to_setup()
        st = d.press_start_until_race(label='pre')
        if st is None:
            raise RuntimeError('race never started')
        d.shot('race-start')
        plan = [('throttle', KEYS['B'], 420),
                ('throttle+A', KEYS['B'] | KEYS['A'], 150),
                ('throttle', KEYS['B'], 150),
                ('throttle+C', KEYS['B'] | KEYS['C'], 150),
                ('throttle', KEYS['B'], 150),
                ('throttle+LEFT', KEYS['B'] | KEYS['LEFT'], 150),
                ('throttle-recover', KEYS['B'], 240),
                ('throttle+RIGHT', KEYS['B'] | KEYS['RIGHT'], 150)]
        pad = KEYS['B']
        for name, keys, frames in plan:
            phases.append(dict(name=name, keys=f'{keys:02X}', frames=frames,
                               frame_start=r.frame()))
            for i in range(frames):
                st = r.step(keys)
                rows.append(dict(phase=name, frame=st.frame, clock=st.clock,
                                 lap=st.lap, lat=round(st.lat_units, 2),
                                 speed=st.speed, pos=st.pos,
                                 phase_word=st.phase, t34=st.t34, t36=st.t36,
                                 t38=st.t38, t2d8=st.t2d8, t2dc=st.t2dc))
                if i % 25 == 0:
                    d.shot(f'{name}-{st.frame}')
            phases[-1]['frame_end'] = r.frame()
            phases[-1]['speed_end'] = rows[-1]['speed']
        d.shot('probe-end')
        (a.out / 'phases.json').write_text(json.dumps(phases, indent=2) + '\n')
        (a.out / 'controls.csv').write_text(
            'phase,frame,clock,lap,lat,speed,pos,race_phase,t34,t36,t38,t2d8,t2dc\n' +
            '\n'.join(f"{x['phase']},{x['frame']},{x['clock']},{x['lap']},"
                      f"{x['lat']},{x['speed']},{x['pos']},{x['phase_word']},"
                      f"{x['t34']},{x['t36']},{x['t38']},{x['t2d8']},{x['t2dc']}"
                      for x in rows) + '\n')
    finally:
        r.stop()


if __name__ == '__main__':
    main()
