#!/usr/bin/env python3
"""Acceptance probe: player 2 is usable out of the box.

1. The effective player map (the runner logs it once) enables player 2 in a
   fresh runtime directory and keeps a saved `[input.p2] device = 0` from the
   owner's settings.ini.
2. The cartridge's 2-player setup screen only advances when the second port
   presses Start: the same scripted menu walk is played twice, once with a
   PLAYER 2 Start and once without, and the pictures must differ only in the
   first case.

Exits 0 when every check passes; writes the pictures and a summary into --out.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / 'build' / 'TG2Recomp'
DEFAULT_ROM = Path.home() / 'roms/genesis/tg2.bin'
OWNER = Path('/home/vitor/git/top-gear-2-genesis-pc/build/owner-session-e586c00/settings.ini')

# P1 walks: title -> options -> toggle 2P GAME on the first row -> START row ->
# START; that lands on the two-player setup screen.
WALK = """PLAYER 1
WAIT 400
PRESS START 8
WAIT 150
PRESS START 8
WAIT 150
PRESS DOWN 6
WAIT 60
PRESS DOWN 6
WAIT 60
PRESS DOWN 6
WAIT 60
PRESS DOWN 6
WAIT 60
PRESS START 8
WAIT 300
"""


def session(exe: Path, out: Path, settings: Path | None):
    d = out / 'run'
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    shutil.copy2(exe, d / exe.name)
    if (exe.parent / 'assets').is_dir():
        shutil.copytree(exe.parent / 'assets', d / 'assets')
    if settings is not None:
        shutil.copy2(settings, d / 'settings.ini')
    return d


def run(exe: Path, rom: Path, out: Path, settings: Path | None, script: str | None,
        frames: int, port: int):
    d = session(exe, out, settings)
    args = [str(d / exe.name), str(rom), '--no-launcher', '--widescreen', 'fit',
            '--max-frames', str(frames), '--port', str(port)]
    if script is not None:
        p = d / 'probe.input'
        p.write_text(script)
        args += ['--input-script', str(p)]
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy',
               SDL_RENDER_DRIVER='software')
    proc = subprocess.run(args, cwd=d, env=env, capture_output=True, text=True)
    (d / 'stderr.log').write_text(proc.stderr or '')
    (d / 'stdout.log').write_text(proc.stdout or '')
    line = next((l for l in (proc.stderr or '').splitlines() if l.startswith('[input]')), '')
    return proc.returncode, line.strip(), d


def diff_fraction(a: Path, b: Path) -> float:
    from PIL import Image
    ia = Image.open(a).convert('RGB')
    ib = Image.open(b).convert('RGB')
    if ia.size != ib.size:
        return 1.0
    pa, pb = ia.load(), ib.load()
    w, h = ia.size
    n = 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if pa[x, y] != pb[x, y]:
                n += 1
    return n / ((h // 2 + h % 2) * (w // 2 + w % 2))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--exe', type=Path, default=DEFAULT_EXE)
    p.add_argument('--rom', type=Path, default=DEFAULT_ROM)
    p.add_argument('--out', type=Path, default=ROOT / 'build/verify-player2')
    p.add_argument('--port', type=int, default=4640)
    p.add_argument('--owner-settings', type=Path, default=OWNER)
    a = p.parse_args()
    a.exe, a.out = a.exe.resolve(), a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    problems = []

    rc, line, d = run(a.exe, a.rom, a.out / 'fresh', None, None, 90, a.port)
    print(f'fresh:   rc={rc} {line}', flush=True)
    if rc != 0:
        problems.append(f'fresh run failed (exit {rc})')
    if 'p2=keyboard+gamepad' not in line:
        problems.append('fresh install does not enable player 2')

    rc, line, d = run(a.exe, a.rom, a.out / 'owner', a.owner_settings, None, 90, a.port + 1)
    print(f'owner:   rc={rc} {line}', flush=True)
    if rc != 0:
        problems.append(f'owner-settings run failed (exit {rc})')
    if ' p2=' in line:
        problems.append('owner settings.ini lost its player 2 "none" device')

    setup = a.out / 'setup.png'
    advanced = a.out / 'advanced.png'
    stuck = a.out / 'stuck.png'
    with_p2 = WALK + f"""SCREENSHOT {setup}
PLAYER 2
PRESS START 8
WAIT 150
SCREENSHOT {advanced}
PLAYER 1
PRESS START 8
WAIT 300
SCREENSHOT {advanced}
WAIT 200
EXIT 0
"""
    without_p2 = WALK + f"""SCREENSHOT {stuck}
PLAYER 1
PRESS START 8
WAIT 300
SCREENSHOT {stuck}
WAIT 200
EXIT 0
"""
    rc, line, _ = run(a.exe, a.rom, a.out / 'with-p2', None, with_p2, 3000, a.port + 2)
    if rc != 0:
        problems.append(f'2P flow run failed (exit {rc})')
    rc2, _, _ = run(a.exe, a.rom, a.out / 'without-p2', None, without_p2, 3000, a.port + 3)
    if rc2 != 0:
        problems.append(f'control run failed (exit {rc2})')

    for shot in (setup, advanced, stuck):
        if not shot.is_file():
            problems.append(f'missing capture {shot}')
    if not problems:
        moved = diff_fraction(setup, advanced)
        held = diff_fraction(setup, stuck)
        print(f'2P start advanced the screen: {moved:.3f} of pixels changed', flush=True)
        print(f'without P2 start the screen held: {held:.3f} of pixels changed', flush=True)
        # Player 1's Start hands the setup screen to player 2: the highlight
        # moves to the second column (a small change), and only player 2's
        # Start continues to the country screen (a completely different
        # picture). The two cases must therefore be far apart.
        if moved < 0.30:
            problems.append(f'player 2 Start did not advance the setup screen ({moved:.3f})')
        if held > 0.25:
            problems.append(f'the setup screen advanced without player 2 ({held:.3f})')
        if moved < 2 * held:
            problems.append(f'player 2 Start is not what advances the screen '
                            f'({moved:.3f} vs {held:.3f})')

    summary = a.out / 'summary.txt'
    summary.write_text(('PASS\n' if not problems else 'FAIL\n') + ''.join('  ' + p + '\n' for p in problems))
    print(('all checks passed' if not problems else '\n'.join(problems)))
    print(f'summary: {summary}')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
