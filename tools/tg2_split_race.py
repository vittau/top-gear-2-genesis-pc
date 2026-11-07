#!/usr/bin/env python3
"""One full two-player split-screen race, player 1 driven closed-loop.

The 2P setup waits for pad port 1, which the TCP `set_input` command cannot
reach, so the menu presses and player 2's throttle come from a runner input
script; player 1 is driven over TCP by the same lateral controller the 1P
qualification uses. Presentation runs the release defaults (16:9, 60 fps races
On, HUD Centered, Hide overscan On); the port in `$FF189E` must stay 1 and the
presented picture must stay 4:3 for the whole race.

  python3 tools/tg2_split_race.py --port 4610 --out build/qual/qa-split-race
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


class Script:
    def __init__(self):
        self.frame = 1
        self.lines = []

    def wait(self, n):
        n = max(1, int(n))
        self.lines.append(f'WAIT {n}')
        self.frame += n

    def tap(self, name, frames=14, player=None):
        if player:
            self.lines.append(f'PLAYER {player}')
        self.lines += ['RELEASE', f'HOLD {name}', f'WAIT {frames}', 'RELEASE']
        self.frame += frames + 1
        if player:
            self.lines.append('PLAYER 1')

    def hold(self, name, player=None):
        if player:
            self.lines.append(f'PLAYER {player}')
        self.lines.append(f'HOLD {name}')
        if player:
            self.lines.append('PLAYER 1')

    def text(self):
        return '\n'.join(self.lines) + '\n'


def build_script(press_count=4, press_gap=280, unpause_at=(3700,)):
    """Title -> 2P GAME -> both setup panels -> intro/shop -> race.

    Player 1's race input is left to TCP; only player 2 holds throttle.
    """
    s = Script()
    s.wait(700)
    s.tap('START')                        # title -> main menu
    s.wait(260)
    s.tap('START')                        # 1P GAME -> 2P GAME
    s.wait(170)
    for _ in range(4):                    # cursor -> START row
        s.tap('DOWN', 12)
        s.wait(80)
    s.tap('START')                        # -> two-panel setup
    s.wait(520)
    s.tap('START')                        # player 1 panel
    s.wait(260)
    s.tap('START', player=2)              # player 2 panel
    s.wait(320)
    for _ in range(press_count):          # intro / shop confirmations
        s.tap('START')
        s.tap('START', player=2)
        s.wait(press_gap)
    race_start = s.frame
    for f in sorted(unpause_at):
        s.wait(f - s.frame)
        s.tap('START')                    # unpause the countdown
    s.wait(max(1, 1500 - (s.frame - race_start)))
    s.hold('B', player=2)                 # player 2: throttle only
    s.wait(40000)                         # long enough for a full race
    return s, race_start


def manifests(out: Path) -> dict:
    from tg2_runner import manifest_counts
    return manifest_counts(out)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4610)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--widescreen', default='16:9')
    p.add_argument('--kp', type=float, default=1.0)
    p.add_argument('--kd', type=float, default=4.0)
    p.add_argument('--kc', type=float, default=0.0)
    p.add_argument('--deadband', type=float, default=9.0)
    p.add_argument('--target-lat', type=float, default=0.0)
    p.add_argument('--drive-frames', type=int, default=40000)
    p.add_argument('--press-count', type=int, default=4)
    p.add_argument('--press-gap', type=int, default=280)
    p.add_argument('--unpause-at', default='')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    script, race_start = build_script(a.press_count, a.press_gap,
                                      [int(x) for x in a.unpause_at.split(',') if x.strip()])
    (a.out / 'split2p.input').write_text(script.text())
    da = SimpleNamespace(stage_dumps=False, sp_every=0, kp=a.kp, kd=a.kd, kc=a.kc,
                         deadband=a.deadband, target_lat=a.target_lat,
                         launch_delay=0, periodic_shots=True,
                         post_frames=0, post_interval=0,
                         drive_frames=a.drive_frames)
    r = Runner(port=a.port, out=a.out, widescreen=a.widescreen,
               max_frames=script.frame + 500,
               env_extra={'TG2_RACE_60FPS': '1', 'TG2_HIDE_OVERSCAN': '1'},
               extra_args=['--turbo', '--input-script', str(a.out / 'split2p.input')],
               video_driver='offscreen')
    evidence = dict(result='error', race=None, two_p_frames=0,
                    two_p_values=[], screenshots=[], script_end_frame=script.frame)
    try:
        r.start()
        d = Driver(r, da)
        st = None
        # Poll in wall-frame steps for the whole scripted boot: a tight
        # frame_info loop can outrun the uncapped guest on the first sample.
        deadline = script.frame
        target = r.frame() + 120
        while target < deadline:
            r.wait_frame(target)
            st = r.state_and_frame()
            if st.clock > 0:
                break
            target += 120
        if st is None or st.clock == 0:
            evidence['result'] = 'no-race'
        else:
            d.shot('race-start')
            race = d.drive_race(da)
            race['lap_times'] = d.lap_times(race)
            d.shot('race-finish')
            evidence['race'] = race
            evidence['result'] = ('timeout' if race.get('timeout') else 'finished')
            samples = d.trace
            race_samples = [s for s in samples if s['clock'] > 0]
            evidence['two_p_frames'] = sum(1 for s in race_samples if s['two_p'])
            evidence['two_p_values'] = sorted({s['two_p'] for s in race_samples})
            evidence['screenshots'] = d.shots
            (a.out / 'trace.csv').write_text(
                'frame,clock,phase,lap,pos,lat,speed,curv,slope,pad,two_p\n' +
                '\n'.join(f"{t['frame']},{t['clock']},{t['phase']},{t['lap']},"
                          f"{t['pos']},{t['lat']},{t['speed']},{t['curv']},"
                          f"{t['slope']},{t['pad']},{t['two_p']}"
                          for t in samples) + '\n')
    finally:
        code = r.stop()
        evidence['exit_code'] = code
        evidence['manifests'] = manifests(a.out)
        (a.out / 'summary.json').write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps({k: v for k, v in evidence.items()
                          if k not in ('screenshots', 'race')}, indent=1))
        if evidence.get('race'):
            print('race', evidence['race'].get('start_frame'),
                  '->', evidence['race'].get('finish_frame'),
                  [round(x['seconds'], 1) for x in evidence['race'].get('lap_times', [])])


if __name__ == '__main__':
    main()
