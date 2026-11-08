#!/usr/bin/env python3
"""Does a quickstate saved between races resume in a fresh process?

Process A finishes a race and walks the post-race flow to a chosen screen,
then saves a quickstate there (the state carries the screen's frame-wait site
as its resume PC). Process B starts from a cold boot, loads that file, and the
probe checks that the restored screen is live: the picture changes, the pad
still reaches the game, and START advances the flow (the next race's clock
starts and runs).

  python3 tools/tg2_postrace_resume_probe.py --out build/qual/resume-intro \
      --country 4 --screen 4
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, KEYS, manifest_counts  # noqa: E402
from tg2_race_driver import Driver  # noqa: E402
import tg2_password as pw  # noqa: E402
from tg2_password_ui import PasswordUI  # noqa: E402
from tg2_progress import NitroDriver, driver_args, UPGRADES  # noqa: E402


def picture_hash(r):
    import hashlib
    path = r.screenshot('probe.png')
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def ram_hash(r):
    from tg2_replay_drive import fnv1a32
    return fnv1a32(r.dump_ram())


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4670)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--country', type=int, default=4)
    p.add_argument('--stage', type=int, default=0)
    p.add_argument('--money', type=int, default=150)
    p.add_argument('--screen', type=int, default=4,
                   help='post-race taps to walk before saving (4 = intro panel)')
    p.add_argument('--until-countdown', action='store_true',
                   help='keep tapping until the next race countdown, save there')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--exe', type=Path,
                   default=Path(__file__).resolve().parents[1] / 'build/TG2Recomp')
    p.add_argument('--kp', type=float, default=1.0)
    p.add_argument('--kd', type=float, default=4.0)
    p.add_argument('--kc', type=float, default=0.0)
    p.add_argument('--deadband', type=float, default=9.0)
    p.add_argument('--target-lat', type=float, default=0.0)
    p.add_argument('--launch-delay', type=int, default=0)
    p.add_argument('--post-frames', type=int, default=4000)
    p.add_argument('--post-interval', type=int, default=110)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    state = (a.out / 'between-races.bin').resolve()
    state.unlink(missing_ok=True)
    report = {'out': str(a.out.resolve()), 'screen': a.screen}

    fields = dict(country=a.country, stage=a.stage, money=a.money)
    fields.update({name: (7 if name in ('u52', 'u54') else 3) for name in UPGRADES})
    password = pw.encode(**fields)
    da = driver_args(a)

    # ---- process A: finish a race, walk to the screen, save ----
    with Runner(port=a.port, out=a.out / 'a', exe=a.exe, rom=a.rom,
                widescreen='off', max_frames=400000,
                extra_args=['--turbo'], video_driver='dummy') as r:
        ui = PasswordUI(r, a)
        ui.to_password_screen()
        ui.type_symbols(password['symbols'])
        ui.submit()
        r.wait_frame(r.frame() + 200)
        ui.tap('START', 7, 50)
        d = NitroDriver(r, da)
        st = d.press_start_until_race(label='pre-race', prev_clock=None)
        assert st is not None, 'no race'
        race = d.drive_race(da)
        assert not race.get('timeout'), 'race timed out'
        frozen = race['finish_clock']
        if a.until_countdown:
            # Walk the post-race flow until the next race's countdown: the race
            # picture is up (phase 0) with the clock still at zero and the
            # picture-build counter moving.
            for _ in range(12):
                st = d.state()
                if st.clock == 0 and r.ram8(0x1866) == 0:
                    a_pic = r.ram16(0x23B4)
                    r.wait_frame(r.frame() + 30)
                    if r.ram16(0x23B4) != a_pic:
                        break
                if st.clock > 0 and st.clock < frozen:
                    break                      # race already running
                d.tap('START', 7)
                r.wait_frame(r.frame() + 240)
        else:
            for step in range(1, a.screen + 1):
                d.tap('START', 7)
                stop = r.frame() + 300
                while r.frame() < stop:
                    s = d.state()
                    if s.clock < frozen:
                        break
                    time.sleep(0.004)
        r.wait_frame(r.frame() + 120)
        d.shot('saved-screen')
        saved = d.state()
        report['saved'] = {'frame': r.frame(), 'clock': saved.clock,
                           'phase': r.ram8(0x1866), 'race_index': r.ram16(0x16BE),
                           'picture': picture_hash(r)}
        r.command('save_state', path=str(state))
        r.wait_frame(r.frame() + 150)
        assert state.exists(), 'state was not written on the chosen screen'
        report['state_size'] = state.stat().st_size

    # ---- process B: cold boot, load, verify the screen is live ----
    with Runner(port=a.port + 1, out=a.out / 'b', exe=a.exe, rom=a.rom,
                widescreen='off', max_frames=400000,
                extra_args=['--turbo'], video_driver='dummy') as r:
        r.wait_frame(400)
        report['boot_picture'] = picture_hash(r)
        r.command('load_state', path=str(state))
        r.wait_frame(r.frame() + 20)
        loaded = {'clock': r.state_and_frame().clock, 'phase': r.ram8(0x1866),
                  'race_index': r.ram16(0x16BE), 'picture': picture_hash(r),
                  'ram': '%08x' % ram_hash(r)}
        report['loaded'] = loaded
        r.wait_frame(r.frame() + 60)
        after = {'picture': picture_hash(r), 'ram': '%08x' % ram_hash(r)}
        report['loaded_after_60_frames'] = after
        report['screen_is_live'] = (loaded['ram'] != after['ram'])

        d = NitroDriver(r, da)
        clock0 = r.state_and_frame().clock
        taps = 0
        running = False
        if a.until_countdown:
            # The countdown runs by itself; START would pause it.
            for _ in range(20):
                st = r.state_and_frame()
                if st.clock > 0:
                    running = True
                    break
                r.wait_frame(r.frame() + 60)
        # Advance the restored screen until a new race clock is running; never
        # tap while it runs (START would pause the race).
        if not running:
            for _ in range(10):
                st = r.state_and_frame()
                if st.clock > 0 and st.clock < clock0:
                    running = True
                    break
                d.tap('START', 7)
                taps += 1
                r.wait_frame(r.frame() + 220)
        report['start_taps'] = taps
        report['race_running_after_load'] = running
        d.shot('resumed-next')
        race = None
        if running:
            race = d.drive_race(da)
            d.shot('resumed-finish')
            report['resumed_race'] = {k: race.get(k) for k in
                                      ('start_frame', 'finish_frame',
                                       'finish_clock', 'timeout')}
            report['resumed_laps'] = d.lap_times(race)
        report['resumed_race_index'] = r.ram16(0x16BE)
        report['final_frame'] = r.frame()
        report['final_clock'] = r.state_and_frame().clock
    report['manifests'] = manifest_counts(a.out / 'a')
    report['manifests_b'] = manifest_counts(a.out / 'b')
    resumed = report.get('resumed_race') or {}
    report['ok'] = bool(report['screen_is_live']
                        and report['race_running_after_load']
                        and not resumed.get('timeout'))
    (a.out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
