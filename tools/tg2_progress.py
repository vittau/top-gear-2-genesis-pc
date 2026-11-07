#!/usr/bin/env python3
"""Race a championship country in order: password in, then ride the flow.

Top Gear 2 has **64 races: 16 countries x 4 races**. A password is only
handed out between countries, so the PASSWORD row always resumes at a
country's first race; races 2..4 of a country are reachable only by finishing
the previous one in the top ten. This tool loads a generated password (with
money and upgrades, so a stock-car run is not the limiting factor), drives the
country's races to the finish with the closed-loop controller, and walks the
post-race flow (results -> championship table -> setup/shop -> next intro)
until the requested number of races is done.

Every race records the race index (`$FF16BE`) and the loaded intro descriptor
(`$FF241C`, the 64-entry table at ROM `$01B8E8`), so the coverage ledger can
name the race that was actually raced.

  python3 tools/tg2_progress.py --port 4610 --out build/qual/qa-prog-c00 \
      --country 0 --races 4 --mode ws169-all --turbo
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner  # noqa: E402
from tg2_race_driver import Driver  # noqa: E402
import tg2_password as pw  # noqa: E402
from tg2_password_ui import PasswordUI  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Presentation modes used by the release qualification.
MODES = {
    'off':          dict(widescreen='off',  env={}),
    'ws169':        dict(widescreen='16:9', env={}),
    # Release defaults: Adaptive (16:9 canvas here), 60 fps races on,
    # HUD Centered (the default, no override), Hide overscan on, default
    # race sound (no override).
    'defaults':     dict(widescreen='16:9', env={'TG2_RACE_60FPS': '1',
                                                 'TG2_HIDE_OVERSCAN': '1'}),
}

UPGRADES = ('u32', 'u34', 'u36', 'u38', 'u3a', 'u3c', 'u3e', 'u40', 'u42',
            'u44', 'u46', 'u48', 'u4a', 'u4c', 'u4e', 'u50', 'u52', 'u54')


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


def driver_args(a) -> SimpleNamespace:
    """The subset of the race driver's arguments the controller needs."""
    return SimpleNamespace(
        stage_dumps=False, sp_every=0, kp=a.kp, kd=a.kd, kc=a.kc,
        deadband=a.deadband, target_lat=a.target_lat, launch_delay=a.launch_delay,
        periodic_shots=True, post_frames=a.post_frames, post_interval=a.post_interval,
        drive_frames=30000,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4610)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--country', type=int, required=True)
    p.add_argument('--stage', type=int, default=0,
                   help='password stage = DIFFICULTY (0 AMATEUR, 1 PROFESSIONAL, 2 CHAMPIONSHIP)')
    p.add_argument('--races', type=int, default=4,
                   help='races to run inside the country (max 4)')
    p.add_argument('--mode', choices=sorted(MODES), default='defaults')
    p.add_argument('--money', type=int, default=150,
                   help='password money in thousands; with full upgrades the sum stays valid')
    p.add_argument('--no-upgrades', dest='upgrades', action='store_false')
    p.add_argument('--kp', type=float, default=1.0)
    p.add_argument('--kd', type=float, default=4.0)
    p.add_argument('--kc', type=float, default=0.0)
    p.add_argument('--deadband', type=float, default=9.0)
    p.add_argument('--target-lat', type=float, default=0.0)
    p.add_argument('--launch-delay', type=int, default=0)
    p.add_argument('--post-frames', type=int, default=4000)
    p.add_argument('--post-interval', type=int, default=110)
    p.add_argument('--start-gap', type=int, default=0,
                   help='wait this many extra frames per post START tap')
    p.add_argument('--turbo', action='store_true', default=True)
    p.add_argument('--realtime', dest='turbo', action='store_false')
    a = p.parse_args()

    mode = MODES[a.mode]
    fields = dict(country=a.country, stage=a.stage, money=a.money)
    if a.upgrades:
        fields.update({name: (7 if name in ('u52', 'u54') else 3)
                       for name in UPGRADES})
    password = pw.encode(**fields)
    if password['sum'] != sum(password[k] for k, _, _ in pw.FIELDS):
        raise SystemExit('password checksum invalid (money + upgrades > 255)')
    a.out.mkdir(parents=True, exist_ok=True)

    r = Runner(port=a.port, out=a.out, widescreen=mode['widescreen'],
               max_frames=400000, env_extra=dict(mode['env']),
               extra_args=['--turbo'] if a.turbo else [],
               video_driver='dummy' if not a.turbo else 'offscreen')
    da = driver_args(a)
    races = []
    evidence = dict(result='error', country=a.country, stage=a.stage,
                    mode=a.mode, races=[], shots=[],
                    password=pw.spaced(password['symbols']),
                    fields={k: password[k] for k, _, _ in pw.FIELDS})
    try:
        r.start()
        d = Driver(r, da)
        ui = PasswordUI(r, a)
        ui.to_password_screen()
        ui.type_symbols(password['symbols'])
        ui.submit()
        r.wait_frame(r.frame() + 200)
        ui.shot('setup')
        ui.tap('START', 7, 50)      # RACE row -> intro panel
        prev_finish = None
        for i in range(a.races):
            st = d.press_start_until_race(label=f'c{a.country}-r{i + 1}',
                                          prev_clock=prev_finish)
            if st is None:
                evidence['result'] = 'no-race'
                break
            idx = r.ram16(0x16BE)
            desc = r.ram32(0x241C)
            d.shot(f'c{a.country}-r{i + 1}-start')
            race = d.drive_race(da)
            d.shot(f'c{a.country}-r{i + 1}-finish')
            race['lap_times'] = d.lap_times(race)
            race.update(index=idx, descriptor=f'0x{desc:06x}', round=i + 1,
                        start_clock=st.clock)
            races.append(race)
            if race.get('timeout'):
                evidence['result'] = 'timeout'
                break
            prev_finish = race['finish_clock']
            if i + 1 < a.races:
                post, raced = d.post_race(da, f'c{a.country}-r{i + 1}',
                                          race['finish_clock'])
                race['post_shots'] = post
                if not raced:
                    evidence['result'] = 'stopped-after-race'
                    break
            else:
                race['post_shots'] = []
            evidence['result'] = 'finished'
        evidence['races'] = races
        evidence['shots'] = d.shots
    finally:
        code = r.stop()
        evidence['exit_code'] = code
        evidence['manifests'] = manifests(a.out)
        (a.out / 'summary.json').write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps(dict(country=a.country, mode=a.mode,
                              result=evidence['result'],
                              races=[dict(round=x.get('round'),
                                          index=x.get('index'),
                                          descriptor=x.get('descriptor'),
                                          finish_frame=x.get('finish_frame'),
                                          laps=len(x.get('lap_times', [])))
                                     for x in races],
                              manifests=evidence['manifests']), indent=1))


if __name__ == '__main__':
    main()
