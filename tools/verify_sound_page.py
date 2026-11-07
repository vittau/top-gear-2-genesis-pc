#!/usr/bin/env python3
"""Acceptance probe: the cartridge RACE SOUND page renders correctly.

The page is drawn from dynamic 8x16 glyph tiles plus sprites, and the port
repaints its value row as "BOTH" while the host choice is BOTH.  A regression
(task 26) made the first open of the page black and a later open garbled, so
this probe opens, cycles and re-opens the page in every mode, from a fresh
runtime directory and from the owner's settings.ini, and compares:

  * every page picture has text pixels and a live palette 3 in CRAM;
  * MUSIC and SOUND EFFECTS pages are pixel-identical to the stock reference
    captured with that mode alone (nothing of the port's paint leaks into the
    stock paths);
  * every BOTH page is pixel-identical to the first BOTH page of the run
    (no garbling across opens or mode changes).

Exits 0 when every check passes; writes PNGs and a summary into --out.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / 'build' / 'TG2Recomp'
DEFAULT_ROM = Path.home() / 'roms/genesis/tg2.bin'
OWNER = Path('/home/vitor/git/top-gear-2-genesis-pc/build/owner-session-e586c00/settings.ini')

# Inner part of the page box: text only, no border.
BOX = (80, 84, 240, 148)
MODE_NAMES = {0: 'sfx', 1: 'music', 2: 'both'}


def copy_session(exe: Path, out: Path, settings: Path | None):
    d = out / 'session'
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    shutil.copy2(exe, d / 'TG2Recomp')
    if (exe.parent / 'assets').is_dir():
        shutil.copytree(exe.parent / 'assets', d / 'assets')
    if settings is not None:
        shutil.copy2(settings, d / 'settings.ini')
    return d


def text_pixels(png: Path) -> int:
    from PIL import Image
    im = Image.open(png).convert('RGB').crop(BOX)
    n = 0
    for r, g, b in im.getdata():
        if max(r, g, b) > 96 and (r + g + b) > 220:
            n += 1
    return n


def same_pixels(a: Path, b: Path) -> bool:
    from PIL import Image
    ia = Image.open(a).convert('RGB').crop(BOX)
    ib = Image.open(b).convert('RGB').crop(BOX)
    return ia.tobytes() == ib.tobytes()


class Run:
    """One session; records a labelled page picture for each page visit."""

    def __init__(self, exe: Path, out: Path, settings: Path | None, port: int,
                 start_mode: int, label: str):
        self.exe, self.out, self.settings, self.port = exe, out, settings, port
        self.start_mode = start_mode
        self.label = label
        self.captures: list[tuple[str, Path, int]] = []
        self.problems: list[str] = []
        self.mode = start_mode

    # Mirrors menu_value_handler(): UP walks BOTH -> MUSIC -> SOUND EFFECTS,
    # DOWN walks SOUND EFFECTS -> MUSIC -> BOTH.
    def up(self):
        self.mode = 1 if self.mode == 2 else 0

    def down(self):
        self.mode = 1 if self.mode == 0 else 2

    def run(self):
        d = copy_session(self.exe, self.out, self.settings)
        caps = self.out / 'caps'
        caps.mkdir(exist_ok=True)
        r = Runner(port=self.port, out=self.out, exe=d / 'TG2Recomp',
                   widescreen='fit', max_frames=40000)
        r.start()

        def settle(n=150):
            r.wait_frame(r.frame() + n)

        def shot(tag):
            path = caps / f'{tag}.png'
            r.command('screenshot', path=str(path))
            cram = r.command('vdp_state', include='cram')['vdp']['cram']
            p3 = sum(cram[48:64])
            px = text_pixels(path)
            self.captures.append((tag, path, self.mode))
            print(f'[{self.label}] {tag:24s} mode={MODE_NAMES[self.mode]:5s} '
                  f'text_px={px:4d} palette3_sum={p3}', flush=True)
            if p3 == 0:
                self.problems.append(f'{tag}: palette 3 is black (page invisible)')
            if px < 60:
                self.problems.append(f'{tag}: page text missing (text_px={px})')

        try:
            r.wait_frame(400)
            r.tap('START', 8)
            settle(200)
            for _ in range(2):
                r.tap('DOWN', 6)
                settle(40)
            r.tap('START', 8)
            settle(200)                     # SOUND submenu
            for visit in range(3):
                r.tap('START', 8)
                settle(180)                 # RACE SOUND value page
                shot(f'visit{visit}-open-{MODE_NAMES[self.mode]}')
                for step in (1, 2):
                    r.tap('UP', 6)
                    self.up()
                    settle(120)
                    shot(f'visit{visit}-up{step}-{MODE_NAMES[self.mode]}')
                for step in (1, 2):
                    r.tap('DOWN', 6)
                    self.down()
                    settle(120)
                    shot(f'visit{visit}-down{step}-{MODE_NAMES[self.mode]}')
                r.tap('B', 8)
                settle(160)                 # back to the SOUND submenu
                shot(f'visit{visit}-submenu')
        finally:
            r.stop()
        return self


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--exe', type=Path, default=DEFAULT_EXE)
    p.add_argument('--rom', type=Path, default=DEFAULT_ROM)
    p.add_argument('--out', type=Path, default=ROOT / 'build/verify-sound-page')
    p.add_argument('--port', type=int, default=4620)
    p.add_argument('--owner-settings', type=Path, default=OWNER)
    a = p.parse_args()
    a.out = a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    if not os.environ.get('SDL_AUDIODRIVER'):
        os.environ['SDL_AUDIODRIVER'] = 'dummy'

    stock = a.out / 'stock-settings'
    stock.mkdir(exist_ok=True)
    owner_copy = stock / 'owner.ini'
    owner_copy.write_bytes(a.owner_settings.read_bytes())
    sfx = stock / 'sfx.ini'
    sfx.write_text(owner_copy.read_text().replace('mode = both', 'mode = sfx'))
    music = stock / 'music.ini'
    music.write_text(owner_copy.read_text().replace('mode = both', 'mode = music'))

    runs = [
        ('stock-sfx', sfx, 0),
        ('stock-music', music, 1),
        ('owner-both', owner_copy, 2),
        ('fresh-default', None, 0),
    ]
    finished: dict[str, Run] = {}
    problems: list[str] = []
    for label, settings, start in runs:
        run = Run(a.exe.resolve(), a.out / label, settings, a.port, start, label)
        try:
            run.run()
            problems += [f'[{label}] {p}' for p in run.problems]
        except Exception as exc:  # noqa: BLE001 - report, keep other runs going
            problems.append(f'[{label}] exception: {exc}')
        finished[label] = run

    def ref_for_mode(mode: int):
        for label in ('stock-sfx', 'stock-music'):
            for tag, path, m in finished[label].captures:
                if m == mode and not tag.endswith('submenu'):
                    return path
        return None

    refs = {0: ref_for_mode(0), 1: ref_for_mode(1)}
    for label, run in finished.items():
        both_ref = None
        for tag, path, mode in run.captures:
            if tag.endswith('submenu'):
                continue
            if mode in refs and refs[mode] is not None:
                if not same_pixels(path, refs[mode]):
                    problems.append(f'[{label}] {tag}: differs from the stock '
                                    f'{MODE_NAMES[mode]} page')
            else:
                if both_ref is None:
                    both_ref = path
                elif not same_pixels(path, both_ref):
                    problems.append(f'[{label}] {tag}: differs from the first '
                                    f'BOTH page of this run')

    summary = a.out / 'summary.txt'
    with summary.open('w') as f:
        for label, run in finished.items():
            f.write(f'{label}:\n')
            for tag, path, mode in run.captures:
                f.write(f'  {tag:26s} {MODE_NAMES[mode]:5s} {path.name}\n')
        f.write('\n')
        f.write('PASS\n' if not problems else 'FAIL\n')
        for p_ in problems:
            f.write('  ' + p_ + '\n')
    print('\n'.join(problems) if problems else 'all checks passed')
    print(f'summary: {summary}')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
