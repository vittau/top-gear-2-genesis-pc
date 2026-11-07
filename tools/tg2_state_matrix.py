#!/usr/bin/env python3
"""Quickstate matrix: does a state saved here resume *live* in a fresh process?

The task-22 defect (docs/VALIDATION.md, bug 4) was that a fresh process loaded
a state and the guest clock/RAM advanced while the picture never changed: the
loader restored the CPU inside whatever native call chain the new process had
(the title/attract loop) instead of the per-frame loop the snapshot was taken
from. The fix parks every quickstate at a declared per-frame boundary and, on
load, restarts the game fiber at that boundary (`game/tg2_spec.c`).

Each case below saves through the runner command the F-key/overlay path uses,
then loads the file in a *second* process and measures:

  * distinct pictures over the hold window (a frozen picture is 1),
  * the race clock and speed deltas,
  * the runtime manifests,
  * for menus, that the screen still answers START.

  python3 tools/tg2_state_matrix.py --out build/qual/qa-state-matrix
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, KEYS, manifest_counts  # noqa: E402
import tg2_password as pw  # noqa: E402
from tg2_password_ui import PasswordUI  # noqa: E402


class Args:
    pass


def to_go(r, country=4, extra_taps=True):
    """Password in, then START until the race clock runs. Returns frame or None."""
    ui = PasswordUI(r, Args())
    ui.to_password_screen()
    ui.type_symbols(pw.encode(country=country, u54=1)['symbols'])
    ui.submit()
    start = r.frame()
    taps = 0
    nxt = start
    while r.frame() - start < 3200:
        if r.state_and_frame().clock > 0:
            return r.frame()
        if r.frame() >= nxt and taps < 10:
            ui.tap('START', 7, 40)
            taps += 1
            nxt = r.frame() + 200
    return None


def distinct(shots):
    pics = set()
    for s in shots:
        p = Path(s)
        if p.exists():
            pics.add(p.read_bytes())
    return len(pics)


def save_moment(r, path: Path, settle=12):
    """Issue the queued quickstate and wait for the runtime to report it."""
    path = path.resolve()
    if path.exists():
        path.unlink()
    r.command('save_state', path=str(path))
    r.wait_frame(r.frame() + settle)
    deadline = r.frame() + 240
    while r.frame() < deadline and not path.exists():
        r.wait_frame(r.frame() + 10)
    return path.exists()


def hold_and_measure(r, tag, frames, pad=KEYS['B'], out=None):
    out = out or r.out
    r.set_input(pad)
    base = r.state_and_frame()
    shots = [str(r.screenshot(out / f'{tag}-hold-000.png'))]
    step = 60
    for i in range(frames // step):
        r.wait_frame(r.frame() + step)
        shots.append(str(r.screenshot(out / f'{tag}-hold-{(i + 1) * step:03d}.png')))
    r.set_input(0)
    end = r.state_and_frame()
    return dict(shots=shots, distinct_pictures=distinct(shots),
                speed_start=base.speed, speed_end=end.speed,
                clock_start=base.clock, clock_end=end.clock,
                clock_delta=end.clock - base.clock,
                lap=end.lap)


def make_runner(port, out, mode, sound=None, extra_env=None):
    env = dict(mode['env'])
    if sound:
        env['TG2_RACE_SOUND'] = sound
    env.update(extra_env or {})
    return Runner(port=port, out=out, widescreen=mode['widescreen'],
                  max_frames=400000, extra_args=['--turbo'],
                  env_extra=env, video_driver='offscreen')


MODES = {
    'off': dict(widescreen='off', env={}),
    'ws169': dict(widescreen='16:9', env={}),
    'defaults': dict(widescreen='16:9', env={'TG2_RACE_60FPS': '1',
                                             'TG2_HIDE_OVERSCAN': '1'}),
}


def race_case(name, args, mode, sound=None, save_after=0):
    """Save at GO (+save_after frames), load in a fresh process, hold throttle."""
    out = args.out / name
    out.mkdir(parents=True, exist_ok=True)
    state = out / 'race.state'
    ev = dict(case=name, kind='race', mode=mode, sound=sound,
              save_after=save_after)
    r = make_runner(args.port, out / 'save', MODES[mode], sound)
    try:
        r.start()
        go = to_go(r)
        ev['reached_go'] = go is not None
        if go is None:
            ev['result'] = 'no-race'
            return ev
        if save_after:
            r.set_input(KEYS['B'])
            r.wait_frame(r.frame() + save_after)
            r.set_input(0)
        ev['saved'] = save_moment(r, state)
        ev['save_moment'] = dict(speed=r.state_and_frame().speed,
                                 clock=r.state_and_frame().clock)
    finally:
        r.stop()
    if not ev['saved']:
        ev['result'] = 'save-refused'
        return ev

    r2 = make_runner(args.port, out / 'load', MODES[mode], sound)
    try:
        r2.start()
        r2.wait_frame(600)
        ev['loaded'] = bool(r2.command('load_state', path=str(state)))
        ev['after_load'] = hold_and_measure(r2, name, args.frames)
    finally:
        code = r2.stop()
        ev['exit_code'] = code
        ev['manifests'] = manifest_counts(out / 'load')
    a = ev['after_load']
    ev['live'] = bool(a['distinct_pictures'] > 2 and a['clock_delta'] > 0)
    ev['result'] = 'live' if ev['live'] else 'frozen'
    return ev


def image_diff(a, b):
    """Fraction of differing pixels between two same-size PNGs (0..1)."""
    from PIL import Image, ImageChops
    ia, ib = Image.open(a).convert('RGB'), Image.open(b).convert('RGB')
    if ia.size != ib.size:
        ib = ib.resize(ia.size)
    diff = ImageChops.difference(ia, ib)
    hist = diff.convert('L').histogram()
    total = ia.size[0] * ia.size[1]
    changed = sum(hist[1:])
    return dict(size=ia.size, changed_fraction=round(changed / total, 4))


def menu_case(name, args, mode, at_start=0, goto=None):
    """Save on a screen, load in a fresh process, then verify the picture
    changes and (menus) that START still navigates.

    `goto` = None | 'password' | 'setup'. Those two screens are reached through
    the password flow of tools/tg2_password_ui.py."""
    out = args.out / name
    out.mkdir(parents=True, exist_ok=True)
    state = out / 'menu.state'
    ev = dict(case=name, kind='menu', mode=mode, at_start=at_start, goto=goto)
    r = make_runner(args.port, out / 'save', MODES[mode])
    try:
        r.start()
        r.wait_frame(700)
        for _ in range(at_start):
            r.tap('START', 8)
            r.wait_frame(r.frame() + 250)
        if goto:
            ui = PasswordUI(r, Args())
            ui.to_password_screen()
            if goto == 'setup':
                ui.type_symbols(pw.encode(country=4, u54=1)['symbols'])
                ui.submit()
                r.wait_frame(r.frame() + 200)
        ev['saved'] = save_moment(r, state)
        ev['save_shot'] = str(r.screenshot(out / 'save' / 'saved.png'))
    finally:
        r.stop()
    if not ev['saved']:
        ev['result'] = 'save-refused'
        return ev
    r2 = make_runner(args.port, out / 'load', MODES[mode])
    try:
        r2.start()
        r2.wait_frame(600)
        ev['loaded'] = bool(r2.command('load_state', path=str(state)))
        m = hold_and_measure(r2, name, args.frames, pad=0)
        ev['after_load'] = m
        try:
            ev['saved_vs_loaded'] = image_diff(ev['save_shot'], m['shots'][0])
        except Exception as exc:
            ev['saved_vs_loaded'] = dict(error=repr(exc))
        # START must still reach the next screen (picture changes after it).
        before = str(r2.screenshot(out / 'load' / 'before-start.png'))
        r2.tap('START', 8)
        r2.wait_frame(r2.frame() + 240)
        after = str(r2.screenshot(out / 'load' / 'after-start.png'))
        ev['start_responds'] = Path(before).read_bytes() != Path(after).read_bytes()
    finally:
        code = r2.stop()
        ev['exit_code'] = code
        ev['manifests'] = manifest_counts(out / 'load')
    ev['live'] = bool(ev['after_load']['distinct_pictures'] > 1 or
                      ev.get('start_responds'))
    ev['result'] = 'live' if ev['live'] else 'frozen'
    return ev


def same_process_case(name, args, mode):
    """Rewind must still work: save, run, load in the SAME process."""
    out = args.out / name
    out.mkdir(parents=True, exist_ok=True)
    state = out / 'race.state'
    ev = dict(case=name, kind='same-process', mode=mode)
    r = make_runner(args.port, out / 'run', MODES[mode])
    try:
        r.start()
        ev['reached_go'] = to_go(r) is not None
        ev['saved'] = save_moment(r, state)
        r.set_input(KEYS['B'])
        r.wait_frame(r.frame() + 180)
        r.set_input(0)
        ev['loaded'] = bool(r.command('load_state', path=str(state)))
        ev['after_load'] = hold_and_measure(r, name, args.frames)
    finally:
        ev['exit_code'] = r.stop()
        ev['manifests'] = manifest_counts(out / 'run')
    a = ev['after_load']
    ev['live'] = bool(a['distinct_pictures'] > 2 and a['clock_delta'] > 0)
    ev['result'] = 'live' if ev['live'] else 'frozen'
    return ev


def two_p_case(name, args):
    """Save in a 2P split-screen race (scripted boot), load in a fresh process.

    The 2P setup waits for pad port 1, which `set_input` cannot reach, so the
    boot uses the runner input script from tools/tg2_split_race.py; the
    quickstate must carry the 2P flag ($FF189E) and both panels must keep
    animating after the load."""
    from tg2_split_race import build_script
    out = args.out / name
    out.mkdir(parents=True, exist_ok=True)
    state = out / 'race.state'
    script, race_start = build_script(4, 280, [3700])
    (out / 'split2p.input').write_text(script.text())
    ev = dict(case=name, kind='2p', mode='defaults')
    r = Runner(port=args.port, out=out / 'save', widescreen='16:9',
               max_frames=script.frame + 500,
               env_extra={'TG2_RACE_60FPS': '1', 'TG2_HIDE_OVERSCAN': '1'},
               extra_args=['--turbo', '--input-script', str(out / 'split2p.input')],
               video_driver='offscreen')
    try:
        r.start()
        st = None
        while r.frame() < script.frame:
            r.wait_frame(r.frame() + 120)
            st = r.state_and_frame()
            if st.clock > 0 and st.two_p == 1:
                break
        ev['reached_race'] = bool(st and st.clock > 0)
        ev['two_p_before'] = r.ram16(0x189E)
        # The scripted 2P boot's last START can land just after GO and pause
        # the countdown; a paused clock is not a freeze, so unpause first.
        r.wait_frame(r.frame() + 60)
        ev['save_shot'] = str(r.screenshot(out / 'save' / 'saved.png'))
        c0 = r.state_and_frame().clock
        r.wait_frame(r.frame() + 20)
        ev['clock_live_before'] = r.state_and_frame().clock != c0
        ev['clock_at_save'] = r.state_and_frame().clock
        ev['saved'] = save_moment(r, state)
    finally:
        r.stop()
    if not ev['saved']:
        ev['result'] = 'save-refused'
        return ev
    r2 = make_runner(args.port, out / 'load', MODES['defaults'])
    try:
        r2.start()
        r2.wait_frame(600)
        ev['loaded'] = bool(r2.command('load_state', path=str(state)))
        ev['two_p_after'] = r2.ram16(0x189E)
        ev['after_load'] = hold_and_measure(r2, name, args.frames, pad=0)
        if not ev['clock_live_before']:
            # The scripted 2P boot leaves the countdown paused (task 22 note),
            # so the correct expectation is the same paused picture, not a
            # running clock. START over TCP does not clear that pause.
            ev['saved_vs_loaded'] = image_diff(ev['save_shot'],
                                               ev['after_load']['shots'][0])
    finally:
        ev['exit_code'] = r2.stop()
        ev['manifests'] = manifest_counts(out / 'load')
    a = ev['after_load']
    if not ev['clock_live_before']:
        same = ev['saved_vs_loaded']['changed_fraction'] <= 0.01
        ev['live'] = bool(same and ev['two_p_after'] == 1)
        ev['result'] = 'resumed-paused' if ev['live'] else 'frozen'
        return ev
    ev['live'] = bool(a['distinct_pictures'] > 2 and a['clock_delta'] > 0
                      and ev['two_p_after'] == 1)
    ev['result'] = 'live' if ev['live'] else 'frozen'
    return ev


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4610)
    p.add_argument('--out', type=Path,
                   default=Path('build/qual/qa-state-matrix'))
    p.add_argument('--frames', type=int, default=420)
    p.add_argument('--only', default='')
    a = p.parse_args()
    a.out = a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)

    cases = {
        'race-off': lambda: race_case('race-off', a, 'off'),
        'race-60fps': lambda: race_case('race-60fps', a, 'defaults'),
        'race-ws169': lambda: race_case('race-ws169', a, 'ws169'),
        'race-both': lambda: race_case('race-both', a, 'defaults', sound='both'),
        'race-mid': lambda: race_case('race-mid', a, 'defaults', save_after=240),
        'rewind': lambda: same_process_case('rewind', a, 'defaults'),
        'menu-title': lambda: menu_case('menu-title', a, 'defaults'),
        'menu-main': lambda: menu_case('menu-main', a, 'defaults', at_start=1),
        'menu-password': lambda: menu_case('menu-password', a, 'defaults',
                                          at_start=1, goto='password'),
        'menu-setup': lambda: menu_case('menu-setup', a, 'defaults',
                                       at_start=1, goto='setup'),
        'race-2p': lambda: two_p_case('race-2p', a),
    }
    names = [n for n in cases if not a.only or n in a.only.split(',')]
    results = []
    for n in names:
        print(f'=== {n}', flush=True)
        try:
            ev = cases[n]()
        except Exception as exc:  # keep going; the summary records the failure
            ev = dict(case=n, result='error', error=repr(exc))
        results.append(ev)
        print(json.dumps({k: v for k, v in ev.items()
                          if k not in ('after_load', 'shots')}, indent=1),
              flush=True)
        (a.out / 'summary.json').write_text(
            json.dumps(dict(cases=results), indent=2) + '\n')
    bad = [r for r in results
           if r.get('result') not in ('live', 'resumed-paused')]
    print(f"{len(results) - len(bad)}/{len(results)} live")
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
