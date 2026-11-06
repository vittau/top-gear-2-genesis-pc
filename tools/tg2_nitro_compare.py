#!/usr/bin/env python3
"""Controlled nitro comparison: identical open-loop input, button added at F.

Records a closed-loop route, then replays that exact pad sequence twice from
the race start — once as recorded, once with the nitro button (C) OR-ed into
the pads of a 60-frame window. Both replays are deterministic guest runs, so
the speed difference at the same race clock is caused by the nitro press
alone.

  python3 tools/tg2_nitro_compare.py --port 4490 --out build/qual/nitro/compare
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
    shot_every = 10 ** 9
    nitro = False


def boot_to_race(r, country):
    c = cov.Coverage(r, Args())
    c.ui.to_password_screen()
    c.ui.type_symbols(pw.encode(country=country)['symbols'])
    c.ui.submit()
    st = c.press_until_race()
    if st is None:
        raise RuntimeError('race never started')
    return st.frame


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4490)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--country', type=int, default=0)
    p.add_argument('--record-frames', type=int, default=1500)
    p.add_argument('--window-at', type=int, default=900,
                   help='frames after the race start to press nitro')
    p.add_argument('--window', type=int, default=60)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    route = []          # (offset from race start, pad)

    # -- pass 1: record a closed-loop route ----------------------------
    r = Runner(port=a.port, out=a.out / 'record', max_frames=120000,
               extra_args=['--turbo'], video_driver='offscreen')
    try:
        r.start()
        t0 = boot_to_race(r, a.country)
        prev_lat = None
        for _ in range(a.record_frames):
            st = r.step(route[-1][1] if route else 0)
            lat = st.lat_units
            d = 0.0 if prev_lat is None else lat - prev_lat
            u = 1.0 * (0.0 - lat) - 4.0 * d
            pad = KEYS['B']
            if u > 9.0:
                pad |= KEYS['RIGHT']
            elif u < -9.0:
                pad |= KEYS['LEFT']
            prev_lat = lat
            if not route or route[-1][1] != pad:
                route.append((st.frame - t0, pad))
    finally:
        r.stop()

    def replay(label, inject):
        r = Runner(port=a.port, out=a.out / label, max_frames=120000,
                   extra_args=['--turbo'], video_driver='offscreen')
        rows = []
        try:
            r.start()
            t0 = boot_to_race(r, a.country)
            pad_from = 0
            for i, (off, pad) in enumerate(route):
                target = t0 + off
                while r.frame() < target:
                    r.wait_frame(target)
                next_off = route[i + 1][0] if i + 1 < len(route) else a.record_frames
                used = pad
                if inject and a.window_at <= off < a.window_at + a.window:
                    used = pad | KEYS['C']
                r.set_input(used)
                # sample until the next route entry
                while r.frame() < t0 + next_off:
                    st = r.state_and_frame()
                    rows.append(dict(off=st.frame - t0, speed=st.speed,
                                     tank=r.ram16(TANK), clock=st.clock,
                                     pad=used))
            r.screenshot(f'{label}.png')
        finally:
            code = r.stop()
        return rows, code

    plain, c1 = replay('replay-plain', False)
    boosted, c2 = replay('replay-nitro', True)

    def at(rows, off):
        for row in rows:
            if row['off'] >= off:
                return row
        return None

    marks = [a.window_at - 1, a.window_at + 15, a.window_at + 30,
             a.window_at + 59, a.window_at + 90, a.window_at + 150]
    table = []
    for off in marks:
        p_row = at(plain, off)
        b_row = at(boosted, off)
        table.append(dict(off=off,
                          plain_speed=p_row['speed'] if p_row else None,
                          nitro_speed=b_row['speed'] if b_row else None,
                          plain_tank=p_row['tank'] if p_row else None,
                          nitro_tank=b_row['tank'] if b_row else None,
                          plain_clock=p_row['clock'] if p_row else None,
                          nitro_clock=b_row['clock'] if b_row else None))
    result = dict(country=a.country, window_at=a.window_at, window=a.window,
                  route=len(route), markers=table,
                  plain_exit=c1, nitro_exit=c2,
                  plain_samples=plain, nitro_samples=boosted)
    (a.out / 'nitro-compare.json').write_text(json.dumps(result, indent=1) + '\n')
    for row in table:
        print(row)


if __name__ == '__main__':
    main()
