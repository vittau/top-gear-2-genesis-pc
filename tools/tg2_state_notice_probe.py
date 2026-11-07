#!/usr/bin/env python3
"""Quickstate save/load through the in-game menu, exactly as a player does it.

Drives the real runtime menu (ESC menu) with real SDL key events injected over
TCP (`key`, `ui_open`, `ui_rows`) and the same held-key state those events
imply, then records:

  * whether the dismissing Enter leaked into the guest as START (`pad` probe),
  * whether the state file was written and the guest kept running,
  * the presented-window picture of every notice (top-left overlay), plus the
    guest framebuffer of the same frame to show the notice is presentation-only.

Flow: password screen (refusal + rejected load) -> race: menu save while
holding Enter, menu load, Shift+F5 save, F5 load.

Usage (needs a dev build with GEN_ENABLE_TRACE):
  python3 tools/tg2_state_notice_probe.py --widescreen off \
      --out build/evidence/state-notice/4x3 --port 4630
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, KEYS, manifest_counts  # noqa: E402
import tg2_password as pw  # noqa: E402
from tg2_password_ui import PasswordUI  # noqa: E402


class Args:
    pass


def key(r, name, down=1, shift=0):
    r.command('key', name=name, held=down, shift=shift)


def tap_key(r, name, settle=8, shift=0):
    key(r, name, 1, shift)
    r.wait_frame(r.frame() + 3)
    key(r, name, 0, shift)
    r.wait_frame(r.frame() + settle)


def menu_rows(r):
    return r.command('ui_rows')['rows']


def selected_label(r):
    for row in menu_rows(r):
        if row['selected']:
            return row['label']
    return None


def close_menu(r):
    """BACK leaves the open section, a second BACK closes the menu."""
    tap_key(r, 'escape', settle=4)
    tap_key(r, 'escape', settle=4)


def notice_shot(r, name):
    """Presented window (with the notice) and the guest framebuffer (without)."""
    frame = r.frame()
    presented = str(r.screenshot(name + '.png', presented=True))
    guest = str(r.screenshot(name + '-guest.png'))
    return {'frame': frame, 'presented': presented, 'guest': guest}


def open_save_section(r, row_label):
    r.command('ui_open', section='Save states')
    r.wait_frame(r.frame() + 2)
    target = {'Save state': 1, 'Slot': 0, 'Load state': 2}[row_label]
    for _ in range(target):
        tap_key(r, 'down', settle=5)
    selected = selected_label(r)
    if selected != row_label:
        raise RuntimeError(f'menu selection is {selected!r}, expected {row_label!r}')
    return selected


def save_lines(out):
    err = (Path(out) / 'stderr.log').read_text(errors='replace')
    return [l for l in err.splitlines() if l.startswith('[SAVE]') or l.startswith('[LOAD]')]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--exe', type=Path, default=Path(__file__).resolve().parents[1] / 'build/TG2Recomp')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--port', type=int, default=4630)
    p.add_argument('--widescreen', default='off', help='off (4:3) or fit (16:9)')
    p.add_argument('--turbo', action='store_true', help='run unpaced (frame-accurate, fast)')
    p.add_argument('--country', type=int, default=4)
    p.add_argument('--frames-in-race', type=int, default=90,
                   help='race frames to run before the save/load cases')
    a = p.parse_args()

    report = {'widescreen': a.widescreen, 'out': str(a.out.resolve())}
    slots = {n: a.exe.resolve().parent / f'native_save_{n}.bin' for n in (1, 5)}
    report['state_files_before'] = {str(v): {'exists': v.exists(),
                                             'mtime': v.stat().st_mtime if v.exists() else None}
                                    for v in slots.values()}
    for path in slots.values():
        if path.exists():
            path.unlink()

    extra = ['--turbo'] if a.turbo else []
    with Runner(port=a.port, out=a.out, exe=a.exe, rom=a.rom,
                widescreen=a.widescreen, max_frames=200000,
                extra_args=extra, timeout=120.0) as r:
        ui = PasswordUI(r, Args())
        ui.to_password_screen()

        # ---- refusal: a screen with no resumable boundary (password entry) ----
        report['selected_refusal'] = open_save_section(r, 'Save state')
        key(r, 'return', 1)
        r.wait_frame(r.frame() + 3)
        key(r, 'return', 0)
        r.wait_frame(r.frame() + 125)            # the 120-frame boundary timeout
        close_menu(r)                           # a refused save leaves it open
        report['notice_refusal'] = notice_shot(r, 'refusal')
        report['refusal_lines'] = save_lines(a.out)[-2:]

        # ---- rejected load: an empty slot ----
        r.command('ui_open', section='Save states')
        r.wait_frame(r.frame() + 2)
        tap_key(r, 'down', settle=5)             # Slot
        tap_key(r, 'right', settle=5)            # slot 2 (empty)
        r.command('ui_open', section='Save states')
        r.wait_frame(r.frame() + 2)
        tap_key(r, 'down', settle=5)
        tap_key(r, 'down', settle=5)
        report['selected_load'] = selected_label(r)
        key(r, 'return', 1)
        r.wait_frame(r.frame() + 3)
        key(r, 'return', 0)
        r.wait_frame(r.frame() + 4)
        close_menu(r)                           # a rejected load leaves it open
        report['notice_load_rejected'] = notice_shot(r, 'load-rejected')
        report['reject_lines'] = save_lines(a.out)[-2:]

        # ---- into a race ----
        ui.type_symbols(pw.encode(country=a.country, u54=1)['symbols'])
        ui.submit()
        start = r.frame()
        taps = 0
        nxt = start
        race = None
        while r.frame() - start < 3200:
            if r.state_and_frame().clock > 0:
                race = r.frame()
                break
            if r.frame() >= nxt and taps < 10:
                ui.tap('START', 7, 40)
                taps += 1
                nxt = r.frame() + 200
        report['race_frame'] = race
        if race is None:
            report['error'] = 'never reached a running race clock'
            print(json.dumps(report, indent=2))
            return 2
        r.wait_frame(r.frame() + a.frames_in_race)
        report['race_clock_before'] = r.state_and_frame().clock

        # ---- menu save, holding Enter as the row is accepted ----
        report['selected_save'] = open_save_section(r, 'Save state')
        save_frame = r.frame()
        key(r, 'return', 1)                      # Enter goes down and stays down
        r.wait_frame(save_frame + 2)
        report['pad_while_enter_held'] = r.command('pad')
        r.wait_frame(save_frame + 5)
        report['notice_save'] = notice_shot(r, 'save')
        key(r, 'return', 0)                      # the player lets go
        r.wait_frame(r.frame() + 20)
        report['pad_after_release'] = r.command('pad')
        report['race_clock_after_save'] = r.state_and_frame().clock

        # ---- menu load ----
        report['selected_load_race'] = open_save_section(r, 'Load state')
        load_frame = r.frame()
        tap_key(r, 'return', settle=5)
        r.wait_frame(load_frame + 6)
        report['notice_loaded'] = notice_shot(r, 'load')
        r.wait_frame(r.frame() + 20)
        report['race_clock_after_load'] = r.state_and_frame().clock

        # ---- F-key path: Shift+F5 saves, F5 loads (slot 5) ----
        r.wait_frame(r.frame() + 30)
        fkey_frame = r.frame()
        tap_key(r, 'f5', settle=4, shift=1)
        r.wait_frame(fkey_frame + 5)
        report['notice_fkey_save'] = notice_shot(r, 'fkey-save')
        r.wait_frame(r.frame() + 30)
        tap_key(r, 'f5', settle=4)
        r.wait_frame(r.frame() + 8)
        report['notice_fkey_load'] = notice_shot(r, 'fkey-load')
        report['race_clock_end'] = r.state_and_frame().clock
        report['final_frame'] = r.frame()

    lines = save_lines(a.out)
    report['save_lines'] = lines
    report['manifests'] = manifest_counts(a.out)
    report['state_files'] = {str(v): {'exists': v.exists(),
                                      'size': v.stat().st_size if v.exists() else None,
                                      'mtime': v.stat().st_mtime if v.exists() else None}
                             for v in slots.values()}
    report['ok'] = bool(report.get('pad_while_enter_held', {}).get('pad0', 1) == 0
                        and report['state_files'][str(slots[1])]['exists']
                        and report['state_files'][str(slots[5])]['exists']
                        and any('no resumable game boundary' in l for l in lines))
    print(json.dumps(report, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
