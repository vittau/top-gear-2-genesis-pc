#!/usr/bin/env python3
"""Reproduce the save-state freeze at the GO! frame, same and cross process.

Loads a country password, drives to the frame where the race clock starts,
saves a native quickstate there, then:

  same   save, run 120 frames, load in the SAME process, hold throttle
  cross  a fresh process boots 600 frames, loads the file, holds throttle

For each phase it captures screenshots at the start and after 400 frames and
reads `$FF18D8` (speed) and `$FF23B8` (race clock), so "the picture is frozen
while the RAM runs" is measured, not assumed.

  python3 tools/tg2_state_freeze.py --port 4610 --out build/qual/qa-state
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


def to_go(r, ui, country=4):
    ui.to_password_screen()
    ui.type_symbols(pw.encode(country=country, u54=1)['symbols'])
    ui.submit()
    start = r.frame()
    taps = 0
    nxt = start
    while r.frame() - start < 3000:
        if r.state_and_frame().clock > 0:
            return True
        if r.frame() >= nxt and taps < 10:
            ui.tap('START', 7, 40)
            taps += 1
            nxt = r.frame() + 200
    return False


def probe(r, phase, out, frames=420):
    shots = []
    r.set_input(KEYS['B'])
    shots.append(str(r.screenshot(f'{phase}-hold-0.png')))
    for i in range(frames // 60):
        r.wait_frame(r.frame() + 60)
        shots.append(str(r.screenshot(f'{phase}-hold-{(i + 1) * 60}.png')))
    r.set_input(0)
    return dict(shots=shots,
                speed=r.ram16(0x18D8), clock=r.ram32(0x23B8),
                lap=r.ram16(0x1994))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=4610)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--country', type=int, default=4)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    state = (a.out / 'go.state').resolve()

    evidence = dict(country=a.country, state=str(state))
    # A: same process: save at GO, run, load, hold.
    r = Runner(port=a.port, out=a.out / 'same', widescreen='16:9',
               max_frames=200000, extra_args=['--turbo'],
               env_extra={'TG2_RACE_60FPS': '1', 'TG2_HIDE_OVERSCAN': '1'},
               video_driver='offscreen')
    ui_args = type('A', (), {})()
    try:
        r.start()
        ui = PasswordUI(r, ui_args)
        evidence['same_reached_go'] = to_go(r, ui, a.country)
        r.wait_frame(r.frame() + 30)
        r.command('save_state', path=str(state))
        evidence['same_before'] = dict(speed=r.ram16(0x18D8), clock=r.ram32(0x23B8))
        r.wait_frame(r.frame() + 120)
        r.command('load_state', path=str(state))
        evidence['same_after_load'] = probe(r, 'same', a.out)
    finally:
        r.stop()

    # B: fresh process: boot, load the same file, hold.
    dir_b = a.out / 'cross'
    dir_b.mkdir(exist_ok=True)
    r2 = Runner(port=a.port, out=dir_b, widescreen='16:9', max_frames=200000,
                extra_args=['--turbo'],
                env_extra={'TG2_RACE_60FPS': '1', 'TG2_HIDE_OVERSCAN': '1'},
                video_driver='offscreen')
    try:
        r2.start()
        r2.wait_frame(600)
        r2.command('load_state', path=str(state))
        evidence['cross_after_load'] = probe(r2, 'cross', a.out)
    finally:
        r2.stop()

    for key in ('same_after_load', 'cross_after_load'):
        e = evidence.get(key, {})
        pics = set(Path(s).read_bytes() for s in e.get('shots', []) if Path(s).exists())
        e['distinct_pictures'] = len(pics)
    (a.out / 'summary.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({k: v for k, v in evidence.items()}, indent=1))


if __name__ == '__main__':
    main()
