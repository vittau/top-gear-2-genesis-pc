#!/usr/bin/env python3
"""Drive Top Gear 2 through the real player route into the RACE SOUND page.

The route is an open-loop controller timeline shared by both back ends, so a
trace-enabled build driven over TCP and a release build driven by a runner
input script receive identical input:

  * default: live TCP run (`--port`), RAM sampling, screenshots, WAV capture
    and the whole-run FM/PSG write dump.
  * `--script-out FILE`: write the same timeline as a runner input script
    (input only: WAIT/PRESS/HOLD/RELEASE/ASSERT_RAM*, no WRITE_RAM).

Routes (`--route`):
  menu         SOUND -> RACE SOUND -> value -> leave the page -> main menu ->
               START -> 1P race
  password     value selected, then CONTINUE -> PASSWORDS -> submit -> race
  second-race  menu route, then finish and press through to a second race

`--mode` selects the RACE SOUND value with the stock up/down keys:
sfx = SOUND EFFECTS (0 downs), music = MUSIC (1), both = BOTH (2).
`--exit` selects the button used to leave the value page: A, B, C or START
(START is not part of the stock leave mask, so the run also presses B).

Evidence under `--out`: stdout.log, stderr.log, race.wav, writes.txt,
samples.json, summary.json, screenshots, copied miss/floor manifests.
"""
from __future__ import annotations

import argparse
import array
import cmath
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, KEYS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / 'build' / 'TG2Recomp'
DEFAULT_ROM = Path.home() / 'roms/genesis/tg2.bin'
DEFAULT_PORT = 4550

# Guest state the route depends on (docs/AUDIO.md, docs/RAM_MAP.md).
RAM_SOUND_MODE = 0x0240E     # word: 0 = SOUND EFFECTS, 1 = MUSIC
RAM_MENU_PAGE = 0x02554      # menu controller page index (word)
RAM_MENU_VALUE = 0x02560     # RACE SOUND page value (word)
RAM_VINT = 0x001EC           # long: current V-int target
RACE_VINT = 0x4714           # race V-int routine
RACE_CLOCK = 0x023B8


def _wait(steps, n):
    steps.append(dict(op='wait', frames=n))


def _press(steps, *names, frames=6):
    steps.append(dict(op='press', keys=list(names), frames=frames))


def _hold(steps, *names):
    steps.append(dict(op='hold', keys=list(names)))


def _release(steps):
    steps.append(dict(op='release'))


def route_steps(mode: str, exit_button: str, route: str) -> list[dict]:
    """Open-loop controller timeline in wall frames."""
    steps: list[dict] = []
    _wait(steps, 400)                     # title screen steady
    _press(steps, 'START', frames=8)      # -> main menu
    _wait(steps, 200)
    # Main menu rows: 1P GAME, DIFFICULTY, SOUND, CONTINUE, START.
    if route == 'direct':
        # Straight to the START row: never opens the SOUND pages, so the
        # cartridge's own sound word keeps its boot value all the way into
        # the race.  Used to prove BOTH does not depend on that word.
        for _ in range(4):
            _press(steps, 'DOWN'); _wait(steps, 40)
        _press(steps, 'START', frames=8)
        _wait(steps, 250)
        for _ in range(12):
            _press(steps, 'START', frames=7)
            _wait(steps, 300)
        return steps
    _press(steps, 'DOWN'); _wait(steps, 40)
    _press(steps, 'DOWN'); _wait(steps, 40)
    _press(steps, 'START', frames=8)      # SOUND submenu
    _wait(steps, 200)
    _press(steps, 'START', frames=8)      # RACE SOUND value page
    _wait(steps, 200)
    for _ in range({'sfx': 0, 'music': 1, 'both': 2}[mode]):
        _press(steps, 'DOWN')
        _wait(steps, 60)
    if exit_button in ('A', 'B', 'C'):
        _press(steps, exit_button)        # leave the value page
        _wait(steps, 150)
        _press(steps, exit_button)        # leave the SOUND submenu
        _wait(steps, 150)
    else:                                 # START: stock leaf ignores it
        _press(steps, 'START', frames=8)
        _wait(steps, 150)
        _press(steps, 'B'); _wait(steps, 150)
        _press(steps, 'B'); _wait(steps, 150)

    if route == 'password':
        _press(steps, 'DOWN'); _wait(steps, 40)     # SOUND -> CONTINUE
        _press(steps, 'START', frames=8)            # CONTINUE submenu
        _wait(steps, 200)
        _press(steps, 'START', frames=8)            # ENTER PASSWORD
        _wait(steps, 250)
        _press(steps, 'A', frames=6)                # END: accept prefilled password
        _wait(steps, 300)
    else:
        _press(steps, 'DOWN'); _wait(steps, 40)     # SOUND -> CONTINUE
        _press(steps, 'DOWN'); _wait(steps, 40)     # CONTINUE -> START
        _press(steps, 'START', frames=8)            # -> game setup
        _wait(steps, 250)

    # Press through setup / shop / intro screens.
    for _ in range(12):
        _press(steps, 'START', frames=7)
        _wait(steps, 300)

    if route == 'second-race':
        _hold(steps, 'B')
        _wait(steps, 60 * 95)
        _release(steps)
        for _ in range(10):                       # results -> new championship
            _press(steps, 'START', frames=7)
            _wait(steps, 240)
        for _ in range(12):                       # -> race 2 countdown
            _press(steps, 'START', frames=7)
            _wait(steps, 300)
    return steps


def script_text(steps: list[dict], tail: str = '') -> str:
    out = ['# Generated by tools/tg2_both_route.py -- input only.',
           '# (WAIT/PRESS/HOLD/RELEASE/ASSERT_RAM*/SCREENSHOT/DUMP_RAM)']
    for st in steps:
        if st['op'] == 'wait':
            out.append(f'WAIT {st["frames"]}')
        elif st['op'] == 'press':
            out.append(f'PRESS {" ".join(st["keys"])} {st["frames"]}')
        elif st['op'] == 'hold':
            out.append(f'HOLD {" ".join(st["keys"])}')
        else:
            out.append('RELEASE')
    if tail:
        out.append(tail.rstrip())
    return '\n'.join(out) + '\n'


def analyze_wav(path: Path) -> dict:
    data = path.read_bytes()
    if data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        return dict(error='not a wav')
    pos, fmt, pcm = 12, None, None
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        size = int.from_bytes(data[pos + 4:pos + 8], 'little')
        body = data[pos + 8:pos + 8 + size]
        if cid == b'fmt ' and len(body) >= 16:
            fmt = dict(channels=int.from_bytes(body[2:4], 'little'),
                       rate=int.from_bytes(body[4:8], 'little'),
                       bits=int.from_bytes(body[14:16], 'little'))
        elif cid == b'data':
            pcm = body
        pos += 8 + size + (size & 1)
    if not fmt or pcm is None:
        return dict(error='no fmt/data chunk')
    a = array.array('h')
    a.frombytes(pcm[:len(pcm) - (len(pcm) % 2)])
    if not a:
        return dict(error='empty')
    peak = max(abs(v) for v in a)
    rms = math.sqrt(sum(v * v for v in a) / len(a))
    dur = len(a) / fmt['channels'] / fmt['rate']
    return dict(duration_s=round(dur, 3), rate=fmt['rate'],
                channels=fmt['channels'], samples=len(a),
                peak=peak, rms=round(rms, 2))


def analyze_writes(path: Path, last_frames: int) -> dict:
    """Chip writes by originating PC; pcz=$FFFF is the 68k.

    Only the last `last_frames` sound frames are counted, which is the race
    window of every route this tool produces.
    """
    if not path.exists():
        return dict(error='missing write dump')
    rx = re.compile(r'^f=(\d+).*pcz=\$([0-9A-Fa-f]{4})')
    rows = []
    max_f = -1
    with open(path, 'r', errors='replace') as f:
        for line in f:
            m = rx.match(line)
            if not m:
                continue
            fr = int(m.group(1))
            rows.append((fr, m.group(2).upper()))
            if fr > max_f:
                max_f = fr
    lo = max_f - last_frames
    by_pcz, z80, m68k = {}, 0, 0
    for fr, pcz in rows:
        if fr < lo:
            continue
        by_pcz[pcz] = by_pcz.get(pcz, 0) + 1
        if pcz == 'FFFF':
            m68k += 1
        else:
            z80 += 1
    return dict(window=dict(first_frame=lo, last_frame=max_f),
                total=z80 + m68k, z80=z80, m68k=m68k,
                writers=dict(sorted(by_pcz.items(), key=lambda kv: -kv[1])))


class Live:
    def __init__(self, a):
        self.a = a
        self.out = a.out.resolve()
        self.out.mkdir(parents=True, exist_ok=True)
        self.samples = []
        self.r = None

    def sample(self, tag):
        r = self.r
        s = dict(tag=tag, frame=r.frame(), mode=r.ram16(RAM_SOUND_MODE),
                 page=r.ram16(RAM_MENU_PAGE), value=r.ram16(RAM_MENU_VALUE),
                 vint=r.ram32(RAM_VINT), clock=r.ram32(RACE_CLOCK))
        self.samples.append(s)
        print(f'{tag:20s} f={s["frame"]:5d} mode={s["mode"]} '
              f'page={s["page"]:4d} value={s["value"]} vint={s["vint"]:06X}',
              flush=True)
        return s

    def run(self):
        a = self.a
        writes = self.out / 'writes.txt'
        writes.unlink(missing_ok=True)
        env = {'TG2_RACE_60FPS': '1' if a.fps60 else '0',
               'GENESIS_AUDIO_WRITEDUMP': str(writes)}
        self.r = r = Runner(port=a.port, out=self.out, exe=a.exe, rom=a.rom,
                            widescreen=a.widescreen, max_frames=a.max_frames,
                            env_extra=env)
        r.start()
        result = dict(result='error')
        try:
            for st in route_steps(a.mode, a.exit, a.route):
                if st['op'] == 'wait':
                    left = st['frames']
                    while left > 0:
                        step = min(left, 60)
                        r.wait_frame(r.frame() + step)
                        left -= step
                        if r.ram16(RAM_MENU_PAGE) == 4:
                            self.sample('racesound-page')
                            r.screenshot('menu-racesound.png')
                elif st['op'] == 'press':
                    pad = 0
                    for k in st['keys']:
                        pad |= KEYS[k]
                    r.set_input(pad)
                    r.wait_frame(r.frame() + st['frames'])
                    r.set_input(0)
                    self.sample('press-' + '+'.join(st['keys']))
                elif st['op'] == 'hold':
                    pad = 0
                    for k in st['keys']:
                        pad |= KEYS[k]
                    r.set_input(pad)
                else:
                    r.set_input(0)

            # Race: the race V-int installed and its clock ticking.
            deadline = r.frame() + a.race_wait
            race_start = None
            while r.frame() < deadline:
                if r.ram16(RAM_VINT + 2) == RACE_VINT and r.ram32(RACE_CLOCK) > 0:
                    race_start = r.frame()
                    break
                r.wait_frame(r.frame() + 4)
            self.sample('race-detect')
            if race_start is None:
                result['result'] = 'no-race'
                return result
            r.screenshot('race.png')
            r.command('audio_wav', action='start',
                      path=str(self.out / 'race.wav'))
            r.set_input(KEYS['B'])
            for i in range(a.race_frames // 60):
                r.wait_frame(r.frame() + 60)
                self.sample(f'race+{(i + 1) * 60}')
            r.set_input(0)
            r.command('audio_wav', action='stop')
            r.screenshot('race-end.png')
            result.update(result='captured', race_start_frame=race_start,
                          race_end_frame=r.frame())
        finally:
            r.stop()
        return result

    def evidence(self, result):
        a = self.a
        wav = self.out / 'race.wav'
        summary = dict(
            mode=a.mode, route=a.route, exit=a.exit,
            widescreen=a.widescreen, race_60fps=a.fps60,
            exe=str(a.exe), result=result, samples=self.samples,
            modes_seen=sorted({s['mode'] for s in self.samples}),
            wav=analyze_wav(wav) if wav.exists() else {},
            writes=analyze_writes(self.out / 'writes.txt', a.race_frames),
        )
        (self.out / 'samples.json').write_text(json.dumps(self.samples, indent=1) + '\n')
        (self.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        return summary


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=DEFAULT_PORT)
    p.add_argument('--out', type=Path, default=ROOT / 'build/audio/route')
    p.add_argument('--exe', type=Path, default=DEFAULT_EXE)
    p.add_argument('--rom', type=Path, default=DEFAULT_ROM)
    p.add_argument('--widescreen', default='off')
    p.add_argument('--60fps', dest='fps60', action='store_true')
    p.add_argument('--mode', choices=['music', 'sfx', 'both'], default='both')
    p.add_argument('--route', choices=['menu', 'password', 'second-race', 'direct'],
                   default='menu')
    p.add_argument('--exit', choices=['A', 'B', 'C', 'START'], default='B')
    p.add_argument('--max-frames', type=int, default=60000)
    p.add_argument('--race-wait', type=int, default=6000)
    p.add_argument('--race-frames', type=int, default=2400)
    p.add_argument('--script-out', type=Path, default=None)
    p.add_argument('--script-race', action='store_true',
                   help='with --script-out: append a race phase (HOLD B, DUMP_RAM)')
    a = p.parse_args()

    steps = route_steps(a.mode, a.exit, a.route)
    if a.script_out:
        expected = {'sfx': 0, 'music': 1, 'both': 1}[a.mode]
        dumpdir = a.script_out.resolve().parent
        if a.script_race:
            tail = (f'WAIT_RAM16 0x00ff01ee {RACE_VINT:#06x}\n'
                    f'ASSERT_RAM16 0x00ff240e {expected}\n'
                    f'DUMP_RAM {dumpdir}/ram-race-a.bin\n'
                    f'HOLD B\n'
                    f'WAIT 600\nDUMP_RAM {dumpdir}/ram-race-b.bin\n'
                    f'WAIT 600\nDUMP_RAM {dumpdir}/ram-race-c.bin\n'
                    f'WAIT 600\nDUMP_RAM {dumpdir}/ram-race-d.bin\n'
                    f'RELEASE\nWAIT 4\n'
                    f'ASSERT_RAM16 0x00ff240e {expected}\n'
                    f'EXIT 0')
        else:
            tail = (f'WAIT 4\nASSERT_RAM16 0x00ff240e {expected}\n'
                    f'WAIT 2\nEXIT 0')
        a.script_out.parent.mkdir(parents=True, exist_ok=True)
        a.script_out.write_text(script_text(steps, tail))
        print(f'wrote {a.script_out} ({sum(s.get("frames", 0) for s in steps)} frames)')
        return 0

    live = Live(a)
    result = live.run()
    summary = live.evidence(result)
    print(json.dumps(dict(result=summary['result'], modes=summary['modes_seen'],
                          wav=summary['wav'], writes=summary['writes']), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
