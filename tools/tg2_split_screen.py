#!/usr/bin/env python3
"""Two-player split-screen qualification check.

The 2P flow needs pad port 1: the setup screen shows one panel per player and
waits for the second pad, while the TCP `set_input` command only drives port 0.
The runner's input script can drive any logical player, so this tool writes a
two-pad script, runs it frame-exactly with the presentation mode under test, and
measures:

  * `$FF189E` (two-player race flag) during the race,
  * the presented framebuffer width (split-screen must stay 4:3),
  * distinct framebuffers per second (60 fps must not engage in split-screen).

  python3 tools/tg2_split_screen.py --port 4470 \
      --out build/qual/split-2p --widescreen 16:9 --60fps
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


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

    def release(self, player=None):
        if player:
            self.lines.append(f'PLAYER {player}')
        self.lines.append('RELEASE')

    def text(self):
        return '\n'.join(self.lines) + '\n'


def build_script(press_count=12, press_gap=280, unpause_at=()):
    """Title -> 2P GAME -> two-panel setup -> intro -> shop -> race."""
    s = Script()
    s.wait(700)
    s.tap('START')                       # title -> main menu
    s.wait(260)
    s.tap('START')                       # 1P GAME -> 2P GAME
    s.wait(170)
    for _ in range(4):                   # cursor -> START row
        s.tap('DOWN', 12)
        s.wait(80)
    s.tap('START')                       # -> setup (two panels)
    s.wait(520)
    # Both players confirm their RACE row, then walk the shared screens.
    s.tap('START')                       # player 1 panel
    s.wait(260)
    s.tap('START', player=2)             # player 2 panel
    s.wait(320)
    for _ in range(press_count):         # intro / shop / confirmations
        s.tap('START')
        s.tap('START', player=2)
        s.wait(press_gap)
    race_start = s.frame
    if unpause_at:
        for f in sorted(unpause_at):
            s.wait(f - s.frame)
            s.tap('START')
        s.wait(max(1, 1500 - (s.frame - race_start)))
    s.hold('B')
    s.hold('B', player=2)
    s.wait(1500)
    return s, race_start


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4470)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--widescreen', default='16:9')
    p.add_argument('--60fps', dest='fps60', action='store_true')
    p.add_argument('--press-count', type=int, default=12)
    p.add_argument('--press-gap', type=int, default=280)
    p.add_argument('--unpause-at', default='',
                   help='comma-separated frames at which to tap START (unpause)')
    a = p.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    script, race_start = build_script(a.press_count, a.press_gap,
                                      [int(x) for x in a.unpause_at.split(',') if x.strip()])
    (out / 'split2p.input').write_text(script.text())
    env = {'TG2_RACE_60FPS': '1'} if a.fps60 else {}
    r = Runner(port=a.port, out=out, exe=a.exe, rom=a.rom, widescreen=a.widescreen,
               max_frames=script.frame + 300, env_extra=env,
               extra_args=['--turbo', '--hash-frames', '1', '--input-script',
                           str(out / 'split2p.input')],
               video_driver='offscreen')
    samples = []
    shots = []
    last_shot = 0
    try:
        r.start()
        while r.proc.poll() is None:
            st = r.state_and_frame()
            samples.append(dict(frame=st.frame, clock=st.clock, lap=st.lap,
                                two_p=st.two_p, speed=st.speed,
                                lat=round(st.lat_units, 2)))
            if st.frame - last_shot >= 240:
                last_shot = st.frame
                shots.append(str(r.screenshot(f'shot-{st.frame}.png').name))
            if st.frame > script.frame:
                break
            time.sleep(0.005)
    finally:
        r.stop()
    stderr = (out / 'stderr.log').read_text(errors='replace')
    hashes = re.findall(r'\[FBHASH\] frame=(\d+) w=(\d+) h=(\d+) hash=0x([A-F0-9]+)', stderr)
    entries = [(int(f), int(w), int(ht), hs) for f, w, ht, hs in hashes]
    windows = {}
    for lo in range(race_start, race_start + 1500, 360):
        win = [hs for f, w, ht, hs in entries if lo <= f < lo + 360]
        if win:
            windows[lo] = len(set(win))
    race_samples = [s for s in samples if s['clock'] > 0]
    summary = dict(
        script_end_frame=script.frame,
        race_start_estimate=race_start,
        first_race_sample=race_samples[0] if race_samples else None,
        two_p_values=sorted({s['two_p'] for s in samples}),
        two_player_frames=sum(1 for s in samples if s['two_p']),
        two_player_race_samples=sum(1 for s in race_samples if s['two_p']),
        presented_frames=len(entries),
        widths=sorted({w for f, w, ht, hs in entries}),
        distinct_per_360=windows,
        screenshots=shots,
    )
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
