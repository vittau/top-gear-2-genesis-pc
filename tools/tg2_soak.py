#!/usr/bin/env python3
"""Long-run soak: continuous racing for a wall-clock budget in one process.

Reuses the qualification driver (closed loop, one-frame control delay) and keeps
starting races until the deadline. Between races it drives the normal post-race
flow; if the championship ended (the game returns to the main menu after a
failed qualification, where START toggles the 1P/2P row instead of starting),
it recovers by selecting the START row again.

  python3 tools/tg2_soak.py --port 4470 --out build/qual/soak \
      --minutes 30 --widescreen 16:9 --60fps
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner  # noqa: E402
from tg2_race_driver import Driver, manifests  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4470)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--widescreen', default='16:9')
    p.add_argument('--60fps', dest='fps60', action='store_true')
    p.add_argument('--minutes', type=float, default=30.0)
    p.add_argument('--periodic-shots', action='store_true')
    p.add_argument('--sp-every', type=int, default=600)
    p.add_argument('--launch-delay', type=int, default=300)
    p.add_argument('--drive-frames', type=int, default=26000)
    p.add_argument('--post-frames', type=int, default=3000)
    p.add_argument('--post-interval', type=int, default=130)
    p.add_argument('--target-lat', type=float, default=0.0)
    p.add_argument('--kp', type=float, default=1.0)
    p.add_argument('--kd', type=float, default=4.0)
    p.add_argument('--kc', type=float, default=0.0)
    p.add_argument('--deadband', type=float, default=9.0)
    p.add_argument('--max-frames', type=int, default=400000)
    a = p.parse_args()
    a.stage_dumps = False
    env = {'TG2_RACE_60FPS': '1'} if a.fps60 else {}
    r = Runner(port=a.port, out=a.out, exe=a.exe, rom=a.rom,
               widescreen=a.widescreen, max_frames=a.max_frames, env_extra=env)
    started = time.monotonic()
    deadline = started + a.minutes * 60.0
    result = 'error'
    try:
        r.start()
        d = Driver(r, a)
        d.boot_to_setup()
        n = 0
        while time.monotonic() < deadline and r.proc.poll() is None:
            n += 1
            st = d.press_start_until_race(limit=2400, label=f'race{n}')
            if st is None:
                # Main menu after a failed qualification: START toggles the
                # 1P/2P row, so select the START row explicitly and try again.
                for _ in range(3):
                    d.tap('DOWN', 7)
                    r.wait_frame(r.frame() + 70)
                d.tap('DOWN', 7)
                r.wait_frame(r.frame() + 120)
                d.tap('START', 7)
                r.wait_frame(r.frame() + 300)
                if time.monotonic() >= deadline:
                    break
                continue
            d.shot(f'race{n}-start')
            race = d.drive_race(a)
            d.races.append(race)
            if race.get('timeout'):
                result = 'timeout'
                break
            result = 'finished'
            if time.monotonic() >= deadline:
                break
            _, raced = d.post_race(a, f'race{n}', race['finish_clock'])
            if not raced:
                # Normal: post race flow ended in the main menu; the next loop
                # iteration performs the recovery.
                pass
        summary = d.write_evidence(result, dict(
            soak_minutes=a.minutes,
            wall_seconds=round(time.monotonic() - started, 1),
            races_started=n))
        print(json.dumps({k: summary[k] for k in ('result', 'wall_seconds',
                                                 'races_started', 'sp_stats')},
                         indent=2))
        for race in summary['races']:
            print('race', race['start_frame'], '->', race['finish_frame'],
                  [(l['lap'], l['seconds']) for l in race['lap_times']])
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
