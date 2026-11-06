#!/usr/bin/env python3
"""Break on the Top Gear 2 password validator and dump its context.

Used to reverse the password codec (docs/PASSWORDS.md). Boots to ENTER
PASSWORD, arms a block breakpoint on the validator entry, and prints the
registers plus the struct it was handed.

  python3 tools/tg2_password_break.py --port 4490 --out build/qual/pw-break1
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, KEYS  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4490)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--block', default='0x023594')
    p.add_argument('--keys', default='')
    p.add_argument('--widescreen', default='off')
    p.add_argument('--no-turbo', dest='turbo', action='store_false', default=True)
    a = p.parse_args()
    r = Runner(port=a.port, out=a.out, widescreen=a.widescreen, max_frames=60000,
               extra_args=['--turbo'] if a.turbo else [],
               video_driver='offscreen' if a.turbo else 'dummy')

    def tap(name, frames=8, settle=230):
        r.set_input(KEYS[name])
        r.wait_frame(r.frame() + frames)
        r.set_input(0)
        r.wait_frame(r.frame() + settle)

    try:
        r.start()
        r.wait_frame(700)
        tap('START', 8, 320)
        for _ in range(3):
            tap('DOWN', 8, 140)
        tap('START', 8, 400)
        tap('START', 8, 520)          # PASSWORD row -> password screen
        r.screenshot('screen.png')
        print('screen frame', r.frame())
        r.command('rdb_break', block=a.block)
        r.set_input(KEYS['A'])          # activate END (default cursor)
        hits = []
        for attempt in range(6):
            parked = False
            st = None
            deadline = 4000
            while deadline > 0:
                st = r.command('rdb_get_state')
                deadline -= 1
                if st.get('parked'):
                    parked = True
                    break
                time.sleep(0.005)
            if not parked:
                print('never parked')
                break
            r.set_input(0)
            regs = st
            (a.out / f'state-{attempt}.json').write_text(json.dumps(regs, indent=1) + '\n')
            # Dump the A0 struct and the stack.
            try:
                a0 = int(str(regs.get('A0') or regs.get('a0')), 0) & 0xFFFF
                a7 = int(str(regs.get('A7') or regs.get('a7')), 0) & 0xFFFF
            except Exception:
                a0 = a7 = 0
            mem = {}
            if a0:
                mem['a0'] = r.ram(a0 - 0x10, 0xB0).hex()
            if a7:
                mem['stack'] = r.ram(a7, 0x40).hex()
            hits.append(dict(regs=regs, mem=mem, frame=r.frame()))
            r.screenshot(f'break-{attempt}.png')
            r.command('rdb_continue')
            r.wait_frame(r.frame() + 30)
        r.command('rdb_break_clear')
        (a.out / 'breaks.json').write_text(json.dumps(hits, indent=1) + '\n')
        for h in hits:
            print(json.dumps(h['regs'])[:400])
            print(' mem', {k: v[:120] for k, v in h['mem'].items()})
    finally:
        print('exit', r.stop())


if __name__ == '__main__':
    main()
