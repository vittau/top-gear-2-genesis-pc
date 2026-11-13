#!/usr/bin/env python3
"""Capture pictures for the README at the owner's presentation settings.

Two modes, both headless (SDL dummy, one process at a time):

* ``capture`` boots the real game through its own password screen, drives the
  race with a closed-loop controller and takes screenshots every
  ``--shot-every`` frames. With ``--state-at`` it also saves quickstates at
  those race-relative frames, so a chosen picture can be reproduced later.
* ``from-state`` loads one of those quickstates in a fresh process, waits
  ``--waits`` presented frames and takes one screenshot. Widescreen mode and
  internal scale can differ from the recording run; the guest state stays the
  same (verified by the printed WRAM hash), which is what makes a matched
  Original / 16:9 / 21:9 or 1x / 4x pair.

The pictures use whatever ``settings.ini`` next to the executable holds
(linear filter, Hide overscan, HUD, 60 fps races). This tool forces the
widescreen mode through the usual ``--widescreen`` switch and the render scale
through the runner's ``TG2_HIGHRES_SCALE`` override (the same value the
settings row writes), then asserts through ``tg2_video`` that every option in
effect is the one the README picture claims.

Everything it writes is ROM-derived and must stay under the ignored build
directory; never commit its output.

  python3 tools/readme_shots.py capture --scene france \
      --out build/readme/france --shot-every 30 --seconds 25 \
      --state-at 900,1200
  python3 tools/readme_shots.py from-state --state build/readme/france/s900.state \
      --out build/readme/france/21x9 --widescreen 21:9
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner  # noqa: E402
from tg2_coverage import Coverage  # noqa: E402
import tg2_password as pw  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# country = password country index, slot = race inside the country (0..3).
# Passwords always resume at slot 0, so a later slot uses the existing
# qualification-only selector (tg2_progress --start-slot, docs/PASSWORDS.md).
# Night is the ROM descriptor's lighting byte 3, the value Athens and Las Vegas
# carry (docs/VALIDATION.md §3); Canterbury Plains has it, Auckland does not.
# Canada's snow scene is Banff (5 laps), the track the old picture showed.
SCENES = {
    'egypt': dict(country=3, slot=0, track='Egypt / Abu Simbel'),
    'france': dict(country=4, slot=0, track='France / Bordeaux'),
    'canada': dict(country=2, slot=0, track='Canada / Banff'),
    'night': dict(country=0, slot=2, track='Australasia / Canterbury Plains (night)'),
}


def wram_hash(r) -> str:
    """Player record + race clock + surroundings: cheap moment identity."""
    return hashlib.sha256(r.ram(0x1600, 0x0E00)).hexdigest()[:16]


def state_info(r):
    info = r.command('tg2_video')
    highres = r.command('tg2_highres')
    return dict(phase=[info.get('phase_num'), info.get('phase_den')],
                from_frame=info.get('from_frame'), to_frame=info.get('to_frame'),
                scale=info.get('highres_scale'), hud_edges=info.get('hud_edges'),
                hide_overscan=info.get('hide_overscan'), race60=info.get('race60'),
                linear_filter=highres.get('native_filter'))


def assert_settings(info, scale):
    problems = []
    if info['scale'] != scale:
        problems.append(f"render scale {info['scale']} != {scale}")
    if info['hud_edges']:
        problems.append('HUD is not Centered')
    if not info['hide_overscan']:
        problems.append('Hide overscan is off')
    if not info['race60']:
        problems.append('60 fps races are off')
    if info['linear_filter']:
        problems.append('Linear filter is on')
    if problems:
        raise SystemExit('settings mismatch: ' + '; '.join(problems))


def enter_race(r, out, country, slot):
    args = SimpleNamespace(country=country, stage=0, mode='off', port=0, out=out,
                           kp=1.0, kd=4.0, kc=0.0, deadband=9.0, target_lat=0.0,
                           nitro=False, nitro_at=10 ** 9, nitro_for=0, shot_every=0)
    cov = Coverage(r, args)
    cov.ui.to_password_screen()
    cov.ui.type_symbols(pw.encode(country=country, stage=0)['symbols'])
    cov.ui.submit()
    if slot:
        # Same setup-only selector as tools/check_highres.py / tg2_progress.py:
        # set the two race selections the game itself stores before the scene
        # loads. Race execution stays stock.
        index = country * 4 + slot
        descriptor = struct.unpack_from('>I', r.rom.read_bytes(),
                                        0x1B8E8 + index * 4)[0]
        r.wait_frame(r.frame() + 200)
        r.write_memory(0xFF16BE, f'{index:04X}')
        r.write_memory(0xFF241C, f'{descriptor:08X}')
        (out / 'track-selector.json').write_text(json.dumps(dict(
            index=index, descriptor=descriptor, setup_only=True)) + '\n')
    return cov.press_until_race(), cov


def capture(a):
    scene = SCENES[a.scene]
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    r = Runner(port=a.port, out=out, exe=a.exe, rom=a.rom, widescreen=a.widescreen,
               max_frames=400000, env_extra={'TG2_HIGHRES_SCALE': str(a.scale)},
               extra_args=['--turbo'], video_driver='dummy')
    shots, states = [], []
    start = end = None
    r.start()
    try:
        state, _cov = enter_race(r, out, scene['country'], scene['slot'])
        if state is None:
            raise SystemExit('never reached a race')
        info = state_info(r)
        assert_settings(info, a.scale)
        start = state.frame
        wanted = sorted(int(x) for x in a.state_at.split(',') if x.strip())
        pad, prev = 0, None
        next_shot = a.skip
        while r.frame() - start < a.seconds * 60:
            rel = r.frame() - start
            st = r.step(pad)
            lat = st.lat_units
            d = 0.0 if prev is None else lat - prev
            u = -lat - 4.0 * d
            pad = 0x10 | (0x08 if u > 9.0 else 0x04 if u < -9.0 else 0)
            prev = lat
            if wanted and rel >= wanted[0]:
                wanted.pop(0)
                state_rel = rel
                state_path = (out / f's{rel:05d}.state').resolve()
                if state_path.exists():
                    state_path.unlink()
                r.command('save_state', path=str(state_path))
                states.append(dict(rel=state_rel, frame=r.frame(),
                                   wram=wram_hash(r), state=str(state_path)))
                print(json.dumps(states[-1]), flush=True)
            if rel >= next_shot:
                next_shot = rel + a.shot_every
                path = r.screenshot(f'f{rel:05d}.png')
                item = dict(rel=rel, frame=r.frame(), speed=st.speed,
                            lat=round(lat, 2), curv=st.curv, slope=st.slope,
                            clock=st.clock, lap=st.lap, wram=wram_hash(r),
                            shot=str(path), **state_info(r))
                shots.append(item)
                print(json.dumps(item), flush=True)
        end = r.frame()
    finally:
        code = r.stop()
    summary = dict(scene=a.scene, track=scene['track'], country=scene['country'],
                   slot=scene['slot'], widescreen=a.widescreen, scale=a.scale,
                   race_start_frame=start, end_frame=end, exit=code,
                   shots=shots, states=states)
    (out / 'capture.json').write_text(json.dumps(summary, indent=1) + '\n')
    print(json.dumps(dict(result='ok', shots=len(shots), exit=code)))
    return 0


def from_state(a):
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    state = a.state.resolve()
    r = Runner(port=a.port, out=out, exe=a.exe, rom=a.rom, widescreen=a.widescreen,
               max_frames=20000, env_extra={'TG2_HIGHRES_SCALE': str(a.scale)},
               extra_args=['--turbo'], video_driver='dummy')
    r.start()
    try:
        r.command('load_state', path=str(state))
        for _ in range(a.waits):
            r.wait_frame(r.frame() + 1)
        # Optional closed-loop run from the restored state, so a moment a few
        # seconds after the quickstate can be used in every mode (the
        # controller reads only guest state, which widescreen does not change).
        pad, prev = 0, None
        for _ in range(a.drive):
            st = r.step(pad)
            lat = st.lat_units
            d = 0.0 if prev is None else lat - prev
            u = -lat - 4.0 * d
            pad = 0x10 | (0x08 if u > 9.0 else 0x04 if u < -9.0 else 0)
            prev = lat
        info = state_info(r)
        assert_settings(info, a.scale)
        frame = r.frame()
        path = r.screenshot(a.name)
        record = dict(state=str(state), widescreen=a.widescreen, waits=a.waits,
                      drive=a.drive,
                      wram=wram_hash(r), frame=frame, shot=str(path), **info)
        print(json.dumps(record))
    finally:
        code = r.stop()
    (out / 'shot.json').write_text(json.dumps(dict(record, exit=code), indent=1) + '\n')
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--port', type=int, default=4720)
    sub = p.add_subparsers(dest='command', required=True)
    c = sub.add_parser('capture')
    c.add_argument('--scene', choices=sorted(SCENES), required=True)
    c.add_argument('--out', type=Path, required=True)
    c.add_argument('--widescreen', default='16:9')
    c.add_argument('--scale', type=int, default=4)
    c.add_argument('--seconds', type=float, default=25.0)
    c.add_argument('--skip', type=int, default=30,
                   help='race-relative frame of the first screenshot')
    c.add_argument('--shot-every', type=int, default=30)
    c.add_argument('--state-at', default='', help='comma-separated race frames to quickstate')
    c.set_defaults(func=capture)
    s = sub.add_parser('from-state')
    s.add_argument('--state', type=Path, required=True)
    s.add_argument('--out', type=Path, required=True)
    s.add_argument('--widescreen', default='16:9')
    s.add_argument('--scale', type=int, default=4)
    s.add_argument('--waits', type=int, default=1)
    s.add_argument('--drive', type=int, default=0,
                   help='closed-loop race frames to drive after the quickstate')
    s.add_argument('--name', default='shot.png')
    s.set_defaults(func=from_state)
    a = p.parse_args()
    return a.func(a)


if __name__ == '__main__':
    sys.exit(main())
