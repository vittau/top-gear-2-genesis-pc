#!/usr/bin/env python3
"""Closed-loop TG2 race driver: boot, race, finish, post-race flow, next race.

Everything is controller input plus read-only RAM. The controller keeps the car
near the road centre using the player's lateral position (`$FF18CE`, clamp
`+/-288` at `$FF1690`/`$FF1694`) and its per-frame derivative; throttle is the B
button. Right raises the lateral value, so `u = kp*(target-lat) - kd*dlat`
drives RIGHT when positive.

The exact pad mask at every change is written to `route.json`, which
`tools/tg2_replay_route.py` turns into an open-loop input script for
deterministic Off / 16:9 / 60 fps comparison.

Evidence under --out:
  trace.csv        frame,clock,phase,lap,pos,lat,speed,curv,slope,pad,two_p
  route.json       [{frame, keys}] pad-mask changes (replayable)
  laps.json        lap boundaries with race-clock ticks
  summary.json     results, screenshots, manifest counts, exit code
  *.png            stage screenshots

Usage:
  python3 tools/tg2_race_driver.py --port 4470 --out build/qual/race-off
  python3 tools/tg2_race_driver.py --port 4470 --out build/qual/race-60 \
      --widescreen 16:9 --60fps
  python3 tools/tg2_race_driver.py --races 3 ...     # continue through the flow
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, RaceState, KEYS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class Driver:
    def __init__(self, runner: Runner, args):
        self.r = runner
        self.args = args
        self.trace = []
        self._last_sp = 0
        self._go_frame = None
        self.laps = []
        self.races = []
        self.shots = []
        self.route = []
        self.sp_samples = []

    # -- plumbing ------------------------------------------------------
    def shot(self, name):
        path = self.r.screenshot(f'{name}.png')
        entry = dict(name=name, path=str(path), frame=self.r.frame())
        if self.args.stage_dumps:
            ram = self.r.dump_ram_file(f'ram-{name}.ram')
            entry['ram'] = str(ram)
        self.shots.append(entry)
        return path

    def record_pad(self, pad: int):
        if not self.route or self.route[-1]['keys'] != f'{pad:02X}':
            self.route.append(dict(frame=self.r.frame(), keys=f'{pad:02X}'))

    def tap(self, name, frames=7):
        """Press-and-release that is also written to the replayable route."""
        from tg2_runner import KEYS
        pad = KEYS[name]
        self.r.set_input(pad)
        self.record_pad(pad)
        self.r.wait_frame(self.r.frame() + frames)
        self.r.set_input(0)
        self.record_pad(0)

    def state(self) -> RaceState:
        # One TCP round trip for both the state block and the frame number.
        return self.r.state_and_frame()

    def log(self, st: RaceState, pad: int):
        self.trace.append(dict(frame=st.frame, clock=st.clock, phase=st.phase,
                               lap=st.lap, pos=st.pos, lat=round(st.lat_units, 3),
                               speed=st.speed, curv=st.curv, slope=st.slope,
                               pad=pad, two_p=st.two_p))
        if not self.route or self.route[-1]['keys'] != f'{pad:02X}':
            self.route.append(dict(frame=st.frame, keys=f'{pad:02X}'))

    # -- menus ---------------------------------------------------------
    def boot_to_setup(self, down_rows=4):
        """Title -> main menu -> 1P game setup screen."""
        r = self.r
        r.wait_frame(600)
        self.shot('title')
        r.wait_frame(700)
        self.tap('START', 8)               # title -> main menu
        r.wait_frame(950)
        self.shot('main-menu')
        for i in range(down_rows):      # 1P GAME -> START
            self.tap('DOWN', 8)
            r.wait_frame(1000 + i * 55)
        r.wait_frame(1300)
        self.shot('menu-start')
        r.wait_frame(1400)
        self.tap('START', 8)               # -> game setup
        r.wait_frame(1650)
        self.shot('setup')

    def choose_two_player(self):
        r = self.r
        r.wait_frame(1700)
        self.tap('DOWN', 8)                # RACE -> PLAYER
        r.wait_frame(1800)
        self.shot('setup-player')
        self.tap('RIGHT', 8)               # 1P -> 2P
        r.wait_frame(1900)
        self.shot('setup-player-2p')
        self.tap('UP', 8)                  # back to RACE
        r.wait_frame(2000)

    def press_start_until_race(self, limit=2400, label='pre', max_taps=12):
        """Advance intro/shop/result screens until the race clock is running.

        START is only tapped when the clock has not started for a whole
        `stuck` window, so the countdown (clock 0, ~250 frames) is never
        interrupted into the pause menu.
        """
        r = self.r
        last = None
        start = r.frame()
        taps = 0
        next_tap = start
        while r.frame() - start < limit:
            st = self.state()
            self.log(st, 0)
            if st.clock > 0 and st.clock != last:
                return st
            if r.frame() >= next_tap and taps < max_taps:
                self.shot(f'{label}-tap-{taps:02d}')
                self.tap('START', 7)
                taps += 1
                next_tap = r.frame() + 420
            last = st.clock
            time.sleep(0.004)
        return None

    # -- controller ----------------------------------------------------
    def control_pad(self, st: RaceState, prev_lat, args):
        if st.two_p:
            return KEYS['B']            # split-screen: player 1 only
        if st.clock == 0:
            return 0                    # countdown
        if args.launch_delay and self._go_frame is not None:
            # Let the pack clear the grid: no throttle for the first N frames
            # after the clock starts, so the drive has no traffic collisions.
            if st.frame - self._go_frame < args.launch_delay:
                return 0
        lat = st.lat_units
        d = 0.0 if prev_lat is None else lat - prev_lat
        # Curvature feed-forward: the road bends ahead, so lean into it instead
        # of waiting for the lateral error to build up.
        u = (args.kp * (args.target_lat - lat) - args.kd * d
             + args.kc * st.curv)
        pad = KEYS['B']
        if u > args.deadband:
            pad |= KEYS['RIGHT']
        elif u < -args.deadband:
            pad |= KEYS['LEFT']
        return pad

    def drive_race(self, args, shots=()):
        """Drive the current race to its finish; returns a race record.

        Each iteration is one TCP round trip carrying `set_input` + the state
        read, so the control delay is exactly one frame (no jitter) and the
        recorded route replays the same inputs on the same frames.
        """
        r = self.r
        prev_lat = None
        prev_clock = None
        stall = 0
        race = dict(start_frame=None, finish_frame=None, lap_boundaries=[],
                    finish_clock=None, lap_times=[])
        last_lap = None
        frame_limit = r.frame() + args.drive_frames
        shot_set = set(shots)
        last_shot = 0
        pad = 0
        while True:
            # The pad from the previous iteration is latched for the frame
            # after the polled state, so it is what the returned state reflects.
            st = r.step(pad)
            f = st.frame
            if race['start_frame'] is None and st.clock > 0:
                race['start_frame'] = f
                self._go_frame = f
            self.log(st, pad)
            pad = self.control_pad(st, prev_lat, args)
            if args.sp_every and f - self._last_sp >= args.sp_every:
                self._last_sp = f
                regs = r.registers()
                self.sp_samples.append(dict(frame=f, sp=regs.get('A7')))
            if args.periodic_shots and f - last_shot >= 900:
                last_shot = f
                self.shot(f'race-{f}')
            if f in shot_set:
                self.shot(f'race-{f}')
            if last_lap is None:
                last_lap = st.lap
            if st.lap != last_lap:
                race['lap_boundaries'].append(dict(lap=st.lap, frame=f,
                                                   clock=st.clock))
                last_lap = st.lap
            if st.clock == prev_clock and st.clock > 0:
                stall += 1
            else:
                stall = 0
            prev_clock = st.clock
            prev_lat = st.lat_units
            # The finish freezes the race clock and the car; the results screen
            # follows ('YOU HAVE QUALIFIED').
            if st.clock > 0 and stall >= 12 and st.speed == 0:
                race['finish_frame'] = f
                race['finish_clock'] = st.clock
                self.shot('finish')
                return race
            if f >= frame_limit:
                self.shot('timeout')
                race['timeout'] = True
                return race

    def post_race(self, args, label, frozen_clock):
        """Press START through the results / next-track / shop screens.

        Returns (shots, started) where `started` means a new race countdown was
        reached (its clock is reset below the frozen finish clock), so START
        tapping must stop before it pauses the race.
        """
        r = self.r
        shots = []
        start = r.frame()
        n = 0
        while r.frame() - start < args.post_frames:
            self.tap('START', 7)
            n += 1
            wait_until = r.frame() + args.post_interval
            while r.frame() < wait_until:
                st = self.state()
                self.log(st, 0)
                if st.clock < frozen_clock:
                    return shots, True
                time.sleep(0.004)
            shots.append(str(self.shot(f'{label}-post-{n:02d}')))
        return shots, False

    # -- results -------------------------------------------------------
    @staticmethod
    def lap_times(race):
        out = []
        prev = 0
        for b in race['lap_boundaries'] + [
                dict(lap=(race['lap_boundaries'][-1]['lap'] + 1) if race['lap_boundaries'] else 1,
                     frame=race['finish_frame'], clock=race['finish_clock'])]:
            if b['clock'] is None:
                continue
            ticks = b['clock'] - prev
            if ticks <= 0:
                continue
            out.append(dict(lap=b['lap'], kind='runup' if b['lap'] == 0 else 'lap',
                            ticks=ticks,
                            seconds=round(ticks / 65536.0 / 50.0, 4),
                            frame=b['frame']))
            prev = b['clock']
        return out

    def write_evidence(self, result, extra=None):
        out = self.r.out
        (out / 'trace.csv').write_text(
            'frame,clock,phase,lap,pos,lat,speed,curv,slope,pad,two_p\n' +
            '\n'.join(f"{t['frame']},{t['clock']},{t['phase']},{t['lap']},"
                      f"{t['pos']},{t['lat']},{t['speed']},{t['curv']},"
                      f"{t['slope']},{t['pad']},{t['two_p']}" for t in self.trace) + '\n')
        for race in self.races:
            race['lap_times'] = self.lap_times(race)
        (out / 'laps.json').write_text(json.dumps(self.races, indent=2) + '\n')
        (out / 'route.json').write_text(json.dumps(self.route, indent=1) + '\n')
        trimmed = []
        for race in self.races:
            if race.get('finish_frame'):
                trimmed = [e for e in self.route if e['frame'] <= race['finish_frame']]
                break
        (out / 'route-race.json').write_text(json.dumps(trimmed or self.route, indent=1) + '\n')
        sp = [x['sp'] for x in self.sp_samples]
        sp_stats = dict(samples=len(sp), min=min(sp) if sp else None,
                        max=max(sp) if sp else None) if sp else None
        summary = dict(result=result, races=self.races, shots=self.shots,
                       sp_samples=self.sp_samples, sp_stats=sp_stats,
                       widescreen=self.r.widescreen,
                       race_60fps=bool(os.environ.get('TG2_RACE_60FPS')),
                       commands=self.r.commands, **extra or {})
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        return summary


def manifests(out: Path) -> dict:
    counts = {}
    for name in ('dispatch_misses.toml', 'floor_coverage.toml',
                 'interior_label_misses.toml', 'floor_unsafe.toml'):
        path = out / name
        if not path.exists():
            counts[name] = None
            continue
        entries = 0
        for line in path.read_text(errors='replace').splitlines():
            s = line.strip()
            if s.startswith('[[`') or s.startswith('[['):
                entries += 1
        counts[name] = entries
    return counts


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4470)
    p.add_argument('--out', type=Path, default=ROOT / 'build/qual/race')
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--widescreen', default='off')
    p.add_argument('--60fps', dest='fps60', action='store_true')
    p.add_argument('--two-player', action='store_true')
    p.add_argument('--races', type=int, default=1)
    p.add_argument('--max-frames', type=int, default=200000)
    p.add_argument('--drive-frames', type=int, default=20000)
    p.add_argument('--post-frames', type=int, default=1200)
    p.add_argument('--post-interval', type=int, default=110)
    p.add_argument('--periodic-shots', action='store_true')
    p.add_argument('--shots', default='')
    p.add_argument('--target-lat', type=float, default=0.0)
    p.add_argument('--kp', type=float, default=1.0)
    p.add_argument('--kd', type=float, default=4.0)
    p.add_argument('--deadband', type=float, default=9.0)
    p.add_argument('--kc', type=float, default=0.0,
                   help='curvature feed-forward gain (curv is $FF18DE)')
    p.add_argument('--skip-post', action='store_true')
    p.add_argument('--sp-every', type=int, default=0,
                   help='sample the 68K stack pointer (A7) every N wall frames')
    p.add_argument('--stage-dumps', action='store_true',
                   help='dump full 64KB WRAM next to every stage screenshot')
    p.add_argument('--launch-delay', type=int, default=0,
                   help='hold no throttle for N frames after the race clock starts')
    p.add_argument('--hash-every', type=int, default=0,
                   help='emit a framebuffer hash every N frames (1 = cadence)')
    p.add_argument('--turbo', action='store_true',
                   help='uncapped guest (offscreen video) for fast closed-loop runs')
    a = p.parse_args()
    env = {'TG2_RACE_60FPS': '1'} if a.fps60 else {}
    extra = ['--turbo'] if a.turbo else []
    if a.hash_every:
        extra += ['--hash-frames', str(a.hash_every)]
    r = Runner(port=a.port, out=a.out, exe=a.exe, rom=a.rom,
               widescreen=a.widescreen, max_frames=a.max_frames, env_extra=env,
               extra_args=extra,
               video_driver='offscreen' if a.turbo else 'dummy')
    result = 'error'
    try:
        r.start()
        d = Driver(r, a)
        d.boot_to_setup()
        if a.two_player:
            d.choose_two_player()
        shots = {int(x) for x in a.shots.split(',') if x.strip()}
        for i in range(a.races):
            st = d.press_start_until_race(label=f'race{i + 1}')
            if st is None:
                result = 'no-race'
                break
            d.shot(f'race{i + 1}-start')
            race = d.drive_race(a, shots=shots if i == 0 else ())
            d.races.append(race)
            if race.get('timeout'):
                result = 'timeout'
                break
            result = 'finished'
            if i + 1 < a.races and not a.skip_post:
                _, raced = d.post_race(a, f'race{i + 1}', race['finish_clock'])
                if not raced:
                    result = 'stopped-after-race'
                    break
            elif not a.skip_post:
                d.post_race(a, f'race{i + 1}', race['finish_clock'])
        summary = d.write_evidence(result)
        for race in summary['races']:
            print('race', race['start_frame'], '->', race['finish_frame'],
                  [(l['lap'], l['seconds']) for l in race['lap_times']])
        print('result', result)
    finally:
        code = r.stop()
        m = manifests(a.out)
        path = a.out / 'summary.json'
        summary = json.loads(path.read_text()) if path.exists() else {}
        summary.update(exit_code=code, manifests=m)
        path.write_text(json.dumps(summary, indent=2) + '\n')
        print('exit', code, 'manifests', m)


if __name__ == '__main__':
    main()
