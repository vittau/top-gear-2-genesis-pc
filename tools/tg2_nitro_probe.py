#!/usr/bin/env python3
"""Nitro measurement: same throttle, button released / held / released.

Loads a track through the password screen, reaches racing speed, then samples
speed and the nitro tank in three 2 s windows: baseline (throttle only),
nitro (throttle + C) and recovery (throttle only). Writes a JSON series and
screenshots for each phase.

  python3 tools/tg2_nitro_probe.py --port 4490 --out build/qual/nitro/c00
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, KEYS  # noqa: E402
import tg2_password as pw  # noqa: E402
from tg2_password_ui import PasswordUI  # noqa: E402
import tg2_coverage as cov  # noqa: E402

TANK = cov.TANK


class Args:
    kp = 1.0
    kd = 4.0
    kc = 0.0
    deadband = 9.0
    target_lat = 0.0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4490)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--country', type=int, default=0)
    p.add_argument('--mode', choices=sorted(cov.MODES), default='off')
    p.add_argument('--warmup', type=int, default=900)
    p.add_argument('--window', type=int, default=120)
    a = p.parse_args()
    mode = cov.MODES[a.mode]
    r = Runner(port=a.port, out=a.out, widescreen=mode['widescreen'],
               max_frames=120000, env_extra=dict(mode['env']),
               extra_args=['--turbo'], video_driver='offscreen')
    phases = []

    def sample(seconds, extra_keys, label):
        rows = []
        start = r.frame()
        while r.frame() - start < seconds:
            st = r.step(KEYS['B'] | extra_keys)
            tank = r.ram16(TANK)
            rows.append(dict(frame=st.frame, speed=st.speed, tank=tank,
                             boost=r.ram16(0x18CA + 0x38),
                             accel=r.ram16(0x18CA + 0x34)))
        shot = r.screenshot(f'{label}.png')
        speeds = [x['speed'] for x in rows]
        phases.append(dict(label=label, keys=f'{KEYS["B"] | extra_keys:02X}',
                           frames=[rows[0]['frame'], rows[-1]['frame']],
                           speed_start=speeds[0], speed_end=speeds[-1],
                           speed_max=max(speeds), speed_min=min(speeds),
                           tank_start=rows[0]['tank'], tank_end=rows[-1]['tank'],
                           boost_values=sorted({x['boost'] for x in rows}),
                           screenshot=str(shot)))

    try:
        r.start()
        c = cov.Coverage(r, Args())
        c.ui.to_password_screen()
        c.ui.type_symbols(pw.encode(country=a.country)['symbols'])
        c.ui.submit()
        st = c.press_until_race()
        if st is None:
            raise RuntimeError('race never started')
        print('race started', st.frame, flush=True)
        sample(a.warmup, 0, 'warmup')            # reach racing speed
        sample(a.window, 0, 'baseline')          # throttle only
        sample(a.window, KEYS['C'], 'nitro')     # throttle + C
        sample(a.window, 0, 'recovery')          # throttle only again
        result = dict(country=a.country, mode=a.mode, phases=phases,
                      nitro_button='C (raw pad bit 5 -> remapped bit 4)',
                      tank_address='$FF18CA+$2D4')
        (a.out / 'nitro.json').write_text(json.dumps(result, indent=2) + '\n')
        for ph in phases:
            print(ph['label'], 'speed', ph['speed_start'], '->', ph['speed_max'], 'boost', ph['boost_values'],
                  "tank", ph["tank_start"], "->", ph["tank_end"])
    finally:
        print('exit', r.stop())


if __name__ == '__main__':
    main()
