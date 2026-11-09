#!/usr/bin/env python3
"""Type a Top Gear 2 password through the game's own ENTER PASSWORD screen.

The screen is a 13-column keyboard: row 0 holds symbols 1..13, row 1 holds
14..26, row 2 holds 27..32 in columns 0..5 and the control keys to the right,
with END at row 2, column 12 (confirmed at runtime: UP from END lands on the
symbol '9' = code 26 at row 1, col 12). A inserts the symbol under the
cursor; END submits.

Every inserted symbol is verified against the live password buffer at
$FF2570 (PASSWORD) or $FF25EA (COUNTRY SELECT), so a wrong assumption
fails loudly instead of submitting a wrong password.

  python3 tools/tg2_password_ui.py --port 4490 --out build/qual/pw-ui1 \
      --password "KVF2 2HQG CJL2 Y4YT"
  python3 tools/tg2_password_ui.py ... --field country=5
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, KEYS  # noqa: E402
import tg2_password as pw  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PW_BASE = 0x2570          # PASSWORD route; COUNTRY SELECT nests it another $7A bytes
CURSOR_END = (2, 12)      # row, column of the END key
ROWS = 3
COLS = 13


def cell_of(code: int) -> tuple[int, int]:
    return (code - 1) // COLS, (code - 1) % COLS


class PasswordUI:
    def __init__(self, runner: Runner, args):
        self.r = runner
        self.args = args
        self.row, self.col = CURSOR_END
        self.trace = []
        self.base = PW_BASE

    # -- plumbing ------------------------------------------------------
    def tap(self, name, frames=6, settle=6):
        r = self.r
        r.set_input(KEYS[name])
        r.wait_frame(r.frame() + frames)
        r.set_input(0)
        r.wait_frame(r.frame() + settle)

    def wait(self, frames):
        self.r.wait_frame(self.r.frame() + frames)

    def buffer(self) -> bytes:
        return self.r.ram(self.base, 16)

    def shot(self, name):
        path = self.r.screenshot(f'{name}.png')
        self.trace.append(dict(shot=name, frame=self.r.frame(), path=str(path)))
        return path

    # -- menu ----------------------------------------------------------
    def to_password_screen(self, country: int | None = None):
        r = self.r
        self.base = PW_BASE if country is None else PW_BASE + 0x7A
        r.wait_frame(700)
        self.shot('title')
        self.tap('START', 8, 250)            # title -> main menu
        for i in range(3):                   # 1P GAME -> CONTINUE
            self.tap('DOWN', 6, 60)
        self.tap('START', 8, 200)            # -> CONTINUE submenu
        self.shot('submenu')
        if country is None:
            self.tap('START', 8, 220)        # PASSWORDS -> ENTER PASSWORD
        else:
            self.tap('DOWN', 6, 80)          # PASSWORDS -> COUNTRY SELECT
            self.tap('START', 8, 200)        # confirm COUNTRY SELECT -> country list
            for _ in range(country):
                self.tap('DOWN', 6, 60)
            self.shot('country-selected')
            self.tap('START', 8, 240)        # -> ENTER PASSWORD for that country
        self.shot('password-screen')
        required = int.from_bytes(r.ram(self.base + 0x24, 2), 'big', signed=True)
        expected = -1 if country is None else country
        if required != expected:
            raise RuntimeError(f'password route mismatch: expected country requirement {expected}, got {required}')
        self.trace.append(dict(picker_requirement=required, work_address=f"0xFF{self.base:04X}", frame=r.frame()))
        return self.buffer()

    # -- cursor --------------------------------------------------------
    def _move_vertical(self, target_row: int):
        """UP/DOWN; an empty cell makes the widget retry, so count real moves."""
        while self.row != target_row:
            step = -1 if target_row < self.row else 1
            key = 'UP' if step < 0 else 'DOWN'
            for _ in range(4):               # gaps are skipped by the widget
                self.row = (self.row + step) % ROWS
                if self.row != 2 or self.col <= 5 or self.col == CURSOR_END[1]:
                    break
                self.tap('DOWN' if step > 0 else 'UP', 6, 30)
            self.tap(key, 6, 30)

    def _move_horizontal(self, target_col: int):
        while self.col != target_col:
            step = -1 if target_col < self.col else 1
            key = 'LEFT' if step < 0 else 'RIGHT'
            self.col = (self.col + step) % COLS
            self.tap(key, 6, 30)

    def move_to(self, row: int, col: int):
        # Row 2 only has live cells at columns 0..5 and 12; route through row 0.
        self._move_vertical(0)
        self._move_horizontal(col)
        self._move_vertical(row)

    # -- typing --------------------------------------------------------
    def type_symbols(self, symbols: str):
        symbols = pw.normalise(symbols)
        pw.chars_to_block(symbols)   # validate all 16 symbols before sending input
        expected = []
        for i, ch in enumerate(symbols):
            code = pw.ALPHABET.index(ch) + 1
            expected.append(code)
            row, col = cell_of(code)
            self.move_to(row, col)
            self.tap('A', 6, 40)
            got = self.buffer()
            self.trace.append(dict(insert=i, symbol=ch, code=code, cell=[row, col],
                                   buffer=got.hex(), frame=self.r.frame()))
            if got[i] != code or any(got[j] for j in range(i + 1, 16)):
                raise RuntimeError(f'insert {i}: wanted {code:02X} at {i}, '
                                   f'buffer {got.hex()} (cell {row},{col})')
        return expected

    def submit(self):
        self.move_to(*CURSOR_END)
        self.tap('A', 6, 320)
        self.shot('after-submit')
        return self.buffer()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4490)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--password', default='')
    p.add_argument('--field', action='append', default=[])
    p.add_argument('--picker-country', '--country', dest='country', type=int, default=-1,
                   help='use the COUNTRY SELECT list instead of the PASSWORD row')
    p.add_argument('--widescreen', default='off')
    p.add_argument('--60fps', dest='fps60', action='store_true')
    p.add_argument('--no-turbo', dest='turbo', action='store_false', default=True)
    p.add_argument('--race', action='store_true',
                   help='after acceptance, drive START through intro/shop and capture the race')
    p.add_argument('--keep', action='store_true', help='leave the process running')
    a = p.parse_args()
    values = {}
    for item in a.field:
        k, v = item.split('=', 1)
        values[k] = int(v, 0)
    symbols = pw.normalise(a.password) if a.password else pw.encode(**values)['symbols']
    env = {'TG2_RACE_60FPS': '1'} if a.fps60 else {}
    r = Runner(port=a.port, out=a.out, widescreen=a.widescreen, max_frames=80000,
               env_extra=env, extra_args=['--turbo'] if a.turbo else [],
               video_driver='dummy' if sys.platform == 'darwin' or not a.turbo else 'offscreen')
    try:
        r.start()
        ui = PasswordUI(r, a)
        pre = ui.to_password_screen(country=None if a.country < 0 else a.country)
        print('prefilled', pre.hex(), pw.spaced(pw.block_to_chars(
            pw.chars_to_block(''.join(pw.ALPHABET[b - 1] for b in pre)))))
        ui.type_symbols(symbols)
        ui.shot('typed')
        (a.out / 'typed-work.bin').write_bytes(r.ram(ui.base, 0x56))
        ui.submit()
        validation = r.command('tg2_password_trace')
        work = bytes.fromhex(validation['work'])
        assert validation['address'] == 0xFF0000 + ui.base
        (a.out / 'validated-work.bin').write_bytes(work)
        validation['record'] = pw.work_record(work)
        model = pw.decode(symbols, validation['record']['picker_country'])
        assert validation['record']['plain'] == model['_plain']
        assert validation['field_sum'] == model['_field_sum']
        assert bool(validation['result']) == model['valid'], (validation, model)
        (a.out / 'validation.json').write_text(json.dumps(validation, indent=2) + '\n')
        ui.shot('post-submit')
        (a.out / 'password.json').write_text(json.dumps(dict(
            symbols=symbols, spaced=pw.spaced(symbols), fields=values,
            decode=pw.decode(symbols, validation['record']['picker_country']), trace=ui.trace), indent=2) + '\n')
        print('typed', pw.spaced(symbols))
        if a.race:
            if not validation['result']:
                raise RuntimeError('cannot enter a race after a rejected password')
            from tg2_race_driver import Driver
            a.stage_dumps = False
            state = Driver(r, a).press_start_until_race(label='accepted')
            if state is None:
                raise RuntimeError('accepted password did not reach a running race')
            ui.wait(120)
            ui.shot('race')
            (a.out / 'race-index.json').write_text(json.dumps(dict(
                index=r.ram16(0x16be), descriptor=f'0x{r.ram32(0x241c):06X}'), indent=2) + '\n')
        if a.keep:
            print('frame', r.frame())
            input('press enter to stop')
    finally:
        print('exit', r.stop())


if __name__ == '__main__':
    main()
