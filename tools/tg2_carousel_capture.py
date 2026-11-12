#!/usr/bin/env python3
"""Capture every presented frame across the setup carousel, then analyse it.

For the carousel CONTROL-row removal: the recomp makes the game stop drawing
the CONTROL button at all, so no presented frame may contain it. This tool
drives the real executable headlessly and records, from the presentation
provider (`TG2_CONTROL_CAPTURE`), one line per presented picture with the
non-backdrop pixel count of the CONTROL rectangles:

  r1 = one-player row list     (x 100..211, y 136..151)
  r2 = two-player player 1     (x 100..211, y  80..95)
  r3 = two-player player 2     (x 100..211, y 192..207)

The run covers frames before the menu opens, entry, at least 12 cursor moves
each way (with wraps) and leaving the menu, in one-player and two-player
layouts. The active layout decides which rectangles are asserted (a highlight
border may legitimately cross the other layout's rectangle).

  build/venv/bin/python tools/tg2_carousel_capture.py --two-player
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

HEADER = (128, 136, 151)          # r1 rect's y rows, only used for reporting


def press(r, key, gap=250):
    r.tap(key, 6)
    r.wait_frame(r.frame() + gap)


def p2_press(r, key, gap=30):
    r.command('virtual_pad', pad=2, button=key, held=1)
    r.wait_frame(r.frame() + 4)
    r.command('virtual_pad', pad=2, button=key, held=0)
    r.wait_frame(r.frame() + gap)


def capture(args):
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    log = out / ('capture-2p.log' if args.two_player else 'capture-1p.log')
    r = Runner(port=args.port, out=out, exe=args.exe, widescreen='off',
               max_frames=args.max_frames,
               env_extra={'TG2_CONTROL_CAPTURE': str(log)})
    marks = {}
    rows = []
    r.start()
    try:
        r.wait_frame(700)                      # title, before the menu opens
        marks['before_entry'] = r.frame()
        press(r, 'START', 500)                 # title -> main menu
        if args.two_player:
            press(r, 'START', 300)             # 1P GAME -> 2P GAME
        for _ in range(4):                     # START row
            press(r, 'DOWN')
        marks['entry'] = r.frame()
        press(r, 'START', 700)                 # -> setup carousel
        rows.append(r.ram16(0x255A))
        for i in range(args.moves):
            press(r, 'UP')
            rows.append(r.ram16(0x255A))
        for i in range(args.moves):
            press(r, 'DOWN')
            rows.append(r.ram16(0x255A))
        if args.two_player:
            r.command('virtual_pad', pad=2, attach=1)
            r.wait_frame(r.frame() + 20)
            for i in range(8):
                p2_press(r, 'down', 20)
                rows.append(r.ram16(0x25C8))
        # select RACE and leave
        for _ in range(6):
            if r.ram16(0x255A) == 0:
                break
            press(r, 'UP')
        marks['leave'] = r.frame()
        r.tap('START', 7)
        r.wait_frame(r.frame() + 500)
        marks['after_leave'] = r.frame()
    finally:
        r.stop()
    with open(out / 'marks.json', 'w') as f:
        json.dump({'marks': marks, 'rows': rows, 'two_player': args.two_player,
                   'log': str(log)}, f, indent=1)
    return log, rows, marks


def analyse(log, two_player, marks=None):
    frames = []
    with open(log) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) not in (7, 8):
                continue
            values = [int(p) for p in parts]
            if len(values) == 8:              # older log: rowlist twop masked pieces...
                values = [values[0]] + values[1:3] + values[4:]
            frame, rowlist, twop, pieces, r1, r2, r3 = values
            frames.append((frame, rowlist, twop, pieces, r1, r2, r3))
    applicable = (1, 2) if two_player else (0,)
    entry = marks['entry'] if marks else (frames[0][0] if frames else 0)
    leave = marks['leave'] if marks else (frames[-1][0] if frames else 0)
    window = [f for f in frames if entry <= f[0] <= leave]
    window_rowlist = [f for f in window if f[1]]
    # Offending: a visible CONTROL button anywhere from entry to leaving.
    offending = [f for f in window
                 if any(f[4 + i] for i in applicable)]
    # The four CONTROL sprites must never be in the display list, before,
    # during or after the menu.
    pieces_frames = [f for f in frames if f[3]]
    return {
        'presented_frames': len(frames),
        'first_frame': frames[0][0] if frames else None,
        'last_frame': frames[-1][0] if frames else None,
        'window': [entry, leave],
        'window_frames': len(window),
        'window_rowlist_frames': len(window_rowlist),
        'rowlist_frames': sum(1 for f in frames if f[1]),
        'sprites_in_control_rect_frames': len(pieces_frames),
        'sprites_in_control_rect_first': pieces_frames[0] if pieces_frames else None,
        'offending_frames': [f[0] for f in offending],
        'offending_rows': [f[1:] for f in offending],
        'applicable': applicable,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--out', type=Path, default=ROOT / 'build/carousel-capture')
    p.add_argument('--port', type=int, default=4645)
    p.add_argument('--max-frames', type=int, default=40000)
    p.add_argument('--moves', type=int, default=14)
    p.add_argument('--two-player', action='store_true')
    a = p.parse_args()
    log, rows, marks = capture(a)
    report = analyse(log, a.two_player, marks)
    report['log'] = str(log)
    report['marks'] = marks
    report['rows'] = rows
    print(json.dumps(report, indent=1))
    return 0 if not report['offending_frames'] else 1


if __name__ == '__main__':
    sys.exit(main())
