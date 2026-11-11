#!/usr/bin/env python3
"""Headless evidence for the TG2 trigger pedals and the fixed TYPE 1 controls.

Covers, against the real executable over its TCP probe server:

  * analog triggers: RT presses Genesis B, LT presses Genesis A, the player's
    deadzone threshold applies, release clears them, P1 and P2 gamepads both
    work, and a remapped face button keeps working alongside them;
  * a fresh install, an existing settings.ini (no trigger key exists) and a
    user-overridden B binding all behave the same;
  * the applied control table is TYPE 1, a non-zero type word is clamped, and
    a quickstate that carries another type is corrected on load;
  * the setup carousel has four rows (no CONTROL), wraps 0..3, and the removed
    button is absent from the presented picture;
  * the stock framebuffer gates (frames 60 and 300) and empty manifests.

  build/venv/bin/python tools/test_tg2_controls.py

Everything is read-only guest access plus the engine's dev probes
(`virtual_pad` / `virtual_axis` / `pad`), which attach a synthetic SDL
controller; no physical gamepad is needed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, manifest_counts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

GPAD_UP, GPAD_DOWN, GPAD_LEFT, GPAD_RIGHT = 0x01, 0x02, 0x04, 0x08
GPAD_B, GPAD_C, GPAD_A, GPAD_START = 0x10, 0x20, 0x40, 0x80

TYPE1 = [5, 6, 0, 1, 3, 2, 4]          # UP DOWN LEFT RIGHT B A C
P1_TABLE, P2_TABLE = 0x19AE, 0x1E06      # 16-bit WRAM offsets
P1_TYPE, P2_TYPE = 0x1BC6, 0x201E
CAROUSEL_ROW = 0x255A
P2_CAROUSEL_ROW = 0x25C8
TWO_PLAYER = 0x189E
CONTROL_RECT_2P = ((100, 80, 211, 95), (100, 192, 211, 207))


def wram(off):
    """Full 24-bit address (the write_memory probe takes a bus address)."""
    return 0xFF0000 | off
CONTROL_RECT = (100, 136, 211, 151)    # native 256x224, inclusive

HASH60 = 0x2A0B972960C5E325
HASH300 = 0x1131D937D70234FD

failures: list[str] = []


def check(cond, what):
    print(('  ok   ' if cond else '  FAIL ') + what, flush=True)
    if not cond:
        failures.append(what)


def pad(r):
    return int(r.command('pad')['pad0']), int(r.command('pad')['pad1'])


def attach(r, slot):
    r.command('virtual_pad', pad=slot, attach=1)
    r.wait_frame(r.frame() + 4)


def axis(r, slot, name, value):
    r.command('virtual_axis', pad=slot, axis=name, value=value)
    r.wait_frame(r.frame() + 2)


def button(r, slot, name, held):
    r.command('virtual_pad', pad=slot, button=name, held=held)
    r.wait_frame(r.frame() + 2)


def reset_pads(r):
    for slot in (1, 2):
        for name in ('lt', 'rt', 'lx', 'ly'):
            axis(r, slot, name, 0)
        for name in ('a', 'b', 'start', 'up', 'down'):
            button(r, slot, name, 0)


def press(r, key, gap=250):
    r.tap(key, 6)
    r.wait_frame(r.frame() + gap)


def boot(r):
    r.wait_frame(700)


def to_carousel(r):
    """Title -> main menu -> carousel row list."""
    press(r, 'START', 500)
    for _ in range(4):
        press(r, 'DOWN')
    press(r, 'START', 500)


def read_table(r, base):
    return [r.ram16(base + 2 * i) for i in range(7)]


def trigger_checks(r, label, b_face='a'):
    print(f'[{label}] analog triggers', flush=True)
    reset_pads(r)
    p0, p1 = pad(r)
    check(not (p0 & (GPAD_A | GPAD_B)) and not (p1 & (GPAD_A | GPAD_B)),
          f'{label}: nothing held reads as neither A nor B (pad0={p0:#04x} pad1={p1:#04x})')

    # P1 deadzone is the shared 25 % default: 8191 of 32767.
    axis(r, 1, 'rt', 8000)
    p0, p1 = pad(r)
    check(not (p0 & GPAD_B), f'{label}: RT below the 25 % deadzone does not press B (pad0={p0:#04x})')
    axis(r, 1, 'rt', 9000)
    p0, p1 = pad(r)
    check(bool(p0 & GPAD_B) and not (p0 & GPAD_A),
          f'{label}: RT above the deadzone presses Genesis B only (pad0={p0:#04x})')
    check(not (p1 & (GPAD_A | GPAD_B)), f'{label}: player 2 pad is untouched by player 1 RT')
    axis(r, 1, 'rt', 0)
    p0, _ = pad(r)
    check(not (p0 & GPAD_B), f'{label}: releasing RT releases B (pad0={p0:#04x})')

    axis(r, 1, 'lt', 9000)
    p0, _ = pad(r)
    check(bool(p0 & GPAD_A) and not (p0 & GPAD_B),
          f'{label}: LT presses Genesis A only (pad0={p0:#04x})')
    axis(r, 1, 'lt', 0)
    p0, _ = pad(r)
    check(not (p0 & GPAD_A), f'{label}: releasing LT releases A (pad0={p0:#04x})')

    # Additive: the face button bound to Genesis B keeps working (SDL A on a
    # fresh install; the settings override moves it to SDL Y).
    button(r, 1, b_face, 1)
    p0, _ = pad(r)
    check(bool(p0 & GPAD_B), f'{label}: the face button still presses B (pad0={p0:#04x})')
    axis(r, 1, 'rt', 9000)
    p0, _ = pad(r)
    check(bool(p0 & GPAD_B), f'{label}: B stays pressed with face button + RT')
    button(r, 1, b_face, 0)
    p0, _ = pad(r)
    check(bool(p0 & GPAD_B), f'{label}: RT alone keeps B pressed after the face button is released')
    axis(r, 1, 'rt', 0)
    button(r, 1, 'a', 1)
    axis(r, 1, 'rt', 9000)
    button(r, 1, b_face, 0)
    p0, _ = pad(r)
    check(bool(p0 & GPAD_B), f'{label}: face-button release while RT is held leaves B held')
    axis(r, 1, 'rt', 0)

    # Player 2's gamepad, same mapping.
    axis(r, 2, 'rt', 9000)
    p0, p1 = pad(r)
    check(bool(p1 & GPAD_B) and not (p1 & GPAD_A),
          f'{label}: player 2 RT presses Genesis B (pad1={p1:#04x})')
    check(not (p0 & GPAD_B), f'{label}: player 1 pad is untouched by player 2 RT')
    axis(r, 2, 'lt', 9000)
    axis(r, 2, 'rt', 0)
    _, p1 = pad(r)
    check(bool(p1 & GPAD_A), f'{label}: player 2 LT presses Genesis A (pad1={p1:#04x})')
    axis(r, 2, 'lt', 0)
    reset_pads(r)


def picture_rect_black(path, rect):
    """True when every pixel of the rect is the presented backdrop (black)."""
    from PIL import Image
    im = Image.open(path).convert('RGB')
    x0, y0, x1, y1 = rect
    px = im.load()
    return all(px[x, y] == (0, 0, 0)
               for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)), im.size


def two_player_checks(r, label):
    """Both players' carousels lose the CONTROL row in the stacked 2P layout."""
    print(f'[{label}] two-player carousel', flush=True)
    press(r, 'START', 500)          # title -> main menu
    press(r, 'START', 300)          # 1P GAME -> 2P GAME
    for _ in range(4):
        press(r, 'DOWN')
    press(r, 'START', 700)          # -> 2P setup screen
    check(r.ram16(TWO_PLAYER) != 0, f'{label}: two-player setup is active')

    p1, p2 = [], []
    for _ in range(8):
        p1.append(r.ram16(CAROUSEL_ROW))
        press(r, 'UP')
    check(max(p1) <= 3 and 3 in p1, f'{label}: player 1 rows stay within 0..3 (saw {p1})')

    attach(r, 2)
    button(r, 2, 'down', 0)
    for _ in range(8):
        p2.append(r.ram16(P2_CAROUSEL_ROW))
        button(r, 2, 'down', 1)
        r.wait_frame(r.frame() + 4)
        button(r, 2, 'down', 0)
        r.wait_frame(r.frame() + 6)
    check(max(p2) <= 3 and 0 in p2,
          f'{label}: player 2 rows stay within 0..3 with its own pad (saw {p2})')
    shot = out_shot = Path(r.out) / 'carousel-2p.png'
    r.screenshot(shot)
    for i, rect in enumerate(CONTROL_RECT_2P):
        black, size = picture_rect_black(shot, rect)
        check(black, f'{label}: player {i + 1} CONTROL button is not drawn')
    from PIL import Image
    im = Image.open(shot).convert('RGB')
    px = im.load()
    rows = ((18, 33), (34, 49), (50, 65), (66, 81),
            (130, 145), (146, 161), (162, 177), (178, 193))
    drawn = sum(1 for (y0, y1) in rows
                if any(px[x, y] != (0, 0, 0)
                       for y in range(y0, y1 + 1) for x in range(101, 211)))
    check(drawn == 8, f'{label}: four rows are still drawn for each player ({drawn}/8)')


def run(args):
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    settings = Path(args.exe).resolve().parent / 'settings.ini'
    original = None
    if settings.exists():
        original = settings.read_text()
    try:
        if args.settings:
            settings.write_text(Path(args.settings).read_text())
        elif settings.exists():
            settings.unlink()

        print(f'== run: {args.label}', flush=True)
        r = Runner(port=args.port, out=out, exe=args.exe, widescreen='off',
                   max_frames=args.max_frames)
        r.start()
        try:
            boot(r)
            attach(r, 1)
            attach(r, 2)
            r.wait_frame(r.frame() + 30)
            if args.two_player:
                two_player_checks(r, args.label)
                r.stop()
                gate_checks(r, out, args.label)
                return finish()
            trigger_checks(r, args.label, args.b_face)

            # --- TYPE 1 lock -------------------------------------------
            print(f'[{args.label}] control type', flush=True)
            r.write_memory(wram(P1_TYPE), '0002')
            r.write_memory(wram(P2_TYPE), '0003')
            r.wait_frame(r.frame() + 3)
            check(r.ram16(P1_TYPE) == 0 and r.ram16(P2_TYPE) == 0,
                  f'{args.label}: non-zero type words are clamped to TYPE 1')
            log = (out / 'stderr.log').read_text(errors='replace')
            check('holding TYPE 1' in log, f'{args.label}: the correction is logged once')

            # --- carousel ----------------------------------------------
            print(f'[{args.label}] setup carousel', flush=True)
            to_carousel(r)
            seen = []
            for _ in range(8):
                seen.append(r.ram16(CAROUSEL_ROW))
                press(r, 'UP')
            check(max(seen) <= 3 and 3 in seen,
                  f'{args.label}: carousel rows stay within 0..3 (saw {seen})')
            down = []
            for _ in range(6):
                press(r, 'DOWN')
                down.append(r.ram16(CAROUSEL_ROW))
            check(max(down) <= 3 and 0 in down,
                  f'{args.label}: carousel wraps 0..3 with no CONTROL row (saw {down})')
            for _ in range(4):
                press(r, 'UP')
            shot = out / 'carousel.png'
            r.screenshot(shot)
            black, size = picture_rect_black(shot, CONTROL_RECT)
            check(size == (256, 224), f'{args.label}: presented picture is 256x224 ({size})')
            check(black, f'{args.label}: the removed CONTROL button is not drawn')
            # The other four rows are still drawn.
            from PIL import Image
            im = Image.open(shot).convert('RGB')
            px = im.load()
            rows_nonblack = sum(
                1 for (y0, y1) in ((72, 87), (88, 103), (104, 119), (120, 135))
                if any(px[x, y] != (0, 0, 0)
                       for y in range(y0, y1 + 1) for x in range(101, 211)))
            check(rows_nonblack == 4,
                  f'{args.label}: RACE, PLAYER, GEARS and SPEED are still drawn')

            # --- triggers in menus stay additive -----------------------
            axis(r, 1, 'rt', 9000)
            before = r.ram16(CAROUSEL_ROW)
            press(r, 'DOWN')
            after = r.ram16(CAROUSEL_ROW)
            check(after != before,
                  f'{args.label}: a face-button menu press still navigates with RT held')
            axis(r, 1, 'rt', 0)

            # --- quickstate with another type -------------------------
            print(f'[{args.label}] quickstate type correction', flush=True)
            # Leave the carousel through the RACE row and wait for the clock.
            for _ in range(4):
                if r.ram16(CAROUSEL_ROW) == 0:
                    break
                press(r, 'UP')
            check(r.ram16(CAROUSEL_ROW) == 0, f'{args.label}: RACE row selected before leaving')
            start = r.frame()
            r.tap('START', 7)
            r.wait_frame(r.frame() + 120)
            taps = 0
            next_tap = start
            while r.frame() - start < args.race_wait:
                if r.ram32(0x23B8):
                    break
                if r.frame() >= next_tap and taps < 12:
                    r.tap('START', 7)
                    taps += 1
                    next_tap = r.frame() + 420
                r.wait_frame(r.frame() + 10)
            check(r.ram32(0x23B8) != 0, f'{args.label}: a race started')
            check(read_table(r, P1_TABLE) == TYPE1 and read_table(r, P2_TABLE) == TYPE1,
                  f'{args.label}: the race applies TYPE 1 to both players '
                  f'(p1={read_table(r, P1_TABLE)} p2={read_table(r, P2_TABLE)})')
            # The game's own remapped control byte: bit 3 ACCEL, bit 2 BRAKE.
            reset_pads(r)
            axis(r, 1, 'rt', 9000)
            r.wait_frame(r.frame() + 4)
            accel = r.ram8(0x18FA)
            check(bool(accel & 0x08) and not (accel & 0x04),
                  f'{args.label}: RT alone sets the game ACCEL bit (0x18FA={accel:#04x})')
            axis(r, 1, 'rt', 0)
            axis(r, 1, 'lt', 9000)
            r.wait_frame(r.frame() + 4)
            brake = r.ram8(0x18FA)
            check(bool(brake & 0x04) and not (brake & 0x08),
                  f'{args.label}: LT alone sets the game BRAKE bit (0x18FA={brake:#04x})')
            axis(r, 1, 'lt', 0)
            reset_pads(r)
            # Tamper, save the tampered state, then load it: the adapter must
            # correct the restored type and table.
            r.write_memory(wram(P1_TYPE), '0002')
            r.write_memory(wram(P2_TYPE), '0001')
            for addr, values in ((P1_TABLE, [0, 1, 2, 3, 4, 5, 6]),
                                 (P2_TABLE, [1, 0, 5, 6, 2, 3, 4])):
                hexbytes = ''.join('%04x' % v for v in values)
                r.write_memory(wram(addr), hexbytes)
            r.wait_frame(r.frame() + 3)
            state = out / 'tampered.state'
            r.command('save_state', path=str(state))
            r.wait_frame(r.frame() + 120)
            r.command('load_state', path=str(state))
            r.wait_frame(r.frame() + 120)
            check(read_table(r, P1_TABLE) == TYPE1 and read_table(r, P2_TABLE) == TYPE1,
                  f'{args.label}: a loaded quickstate is corrected to TYPE 1 '
                  f'(p1={read_table(r, P1_TABLE)} p2={read_table(r, P2_TABLE)})')
            check(r.ram16(P1_TYPE) == 0 and r.ram16(P2_TYPE) == 0,
                  f'{args.label}: restored type words are clamped after the load')

            # --- stock gates ------------------------------------------
            r.stop()
            gate_checks(r, out, args.label)
        finally:
            r.stop()
    finally:
        if settings.exists():
            settings.unlink()
        if original is not None:
            settings.write_text(original)

    return finish()


def gate_checks(r, out, label):
    err = (out / 'stderr.log').read_text(errors='replace')
    hashes = {}
    for line in err.splitlines():
        if line.startswith('[FBHASH]'):
            fields = dict(part.split('=', 1) for part in line.split()[1:])
            hashes[int(fields['frame'])] = int(fields['hash'], 16)
    check(hashes.get(60) == HASH60,
          f'{label}: frame 60 hash 0x{hashes.get(60, 0):016X} == 0x{HASH60:016X}')
    check(hashes.get(300) == HASH300,
          f'{label}: frame 300 hash 0x{hashes.get(300, 0):016X} == 0x{HASH300:016X}')
    counts = manifest_counts(out)
    check(all(v == 0 for v in counts.values()),
          f'{label}: manifests empty ({counts})')


def finish():
    print()
    if failures:
        print(f'{len(failures)} FAILED:')
        for f in failures:
            print(' -', f)
        return 1
    print('all checks passed')
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--out', type=Path, default=ROOT / 'build/trigger-pedals')
    p.add_argument('--port', type=int, default=4641)
    p.add_argument('--max-frames', type=int, default=40000)
    p.add_argument('--race-wait', type=int, default=6000)
    p.add_argument('--label', default='fresh install')
    p.add_argument('--settings', type=Path, default=None,
                   help='settings.ini to install for the run')
    p.add_argument('--b-face', default='a',
                   help='probe name of the face button bound to Genesis B')
    p.add_argument('--two-player', action='store_true',
                   help='check the stacked two-player carousel instead')
    return run(p.parse_args())


if __name__ == '__main__':
    sys.exit(main())
