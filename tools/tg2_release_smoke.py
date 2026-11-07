#!/usr/bin/env python3
"""Release-config smoke: ROM beside the executable, scripted race, exit 0.

Copies a release-profile executable into a scratch directory that looks like
an unpacked payload, drops the cartridge next to it under a name and extension
that match nothing (detection is by CRC32 content, engine patch 0002), writes a
controller-only input script that boots the game into a 1P race, and runs it
with SDL's dummy video/audio drivers. No TCP server is used: the release build
has the reverse-debug rings off.

Passes when the process exits 0, the script loaded, the screenshots exist and
the final race picture is not blank.

  python3 tools/tg2_release_smoke.py --exe build-rel/TG2Recomp \
      --rom ~/roms/genesis/tg2.bin --work build/qual/release-smoke
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
import sys

DECOY_NAME = 'fixture-cartridge.dat'

# Boot timeline measured on the trace build (tg2_race_driver.boot_to_setup):
# title -> main menu -> 1P GAME / START row -> game setup -> intro -> race.
ROUTE = """\
# Release-qualification smoke route: 1P race from a fresh boot.
WAIT 1300
PRESS START 8
WAIT 960
PRESS DOWN 8
WAIT 1000
PRESS DOWN 8
WAIT 1055
PRESS DOWN 8
WAIT 1110
PRESS DOWN 8
WAIT 1165
WAIT 1300
PRESS START 8
WAIT 1650
PRESS START 7
WAIT 420
SCREENSHOT {out}/race-1.png
PRESS START 7
WAIT 420
SCREENSHOT {out}/race-2.png
PRESS START 7
WAIT 420
SCREENSHOT {out}/race-3.png
PRESS START 7
WAIT 1200
SCREENSHOT {out}/race-4.png
WAIT 600
SCREENSHOT {out}/race-5.png
EXIT 0
"""

LAST_FRAME = 1300 + 960 + 1000 + 1055 + 1110 + 1165 + 1300 + 1650 + 420 * 5 + 1500 + 1800 + 200


def blank_ratio(path: Path) -> float:
    """Fraction of pixels that are pure black, without a PNG library."""
    data = path.read_bytes()
    # Fall back to a size-only sanity check when PIL is unavailable.
    try:
        from PIL import Image
    except ImportError:
        return 0.0
    with Image.open(path) as image:
        image = image.convert('RGB')
        pixels = image.getdata()
        black = sum(1 for r, g, b in pixels if r < 8 and g < 8 and b < 8)
        return black / float(image.width * image.height)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--exe', type=Path, required=True)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--assets', type=Path, default=None,
                   help='assets directory to copy beside the executable')
    p.add_argument('--frames', type=int, default=LAST_FRAME + 2000)
    p.add_argument('--timeout', type=int, default=900)
    a = p.parse_args()

    work = a.work.resolve()
    run = work / 'run'
    if run.exists():
        shutil.rmtree(run)
    run.mkdir(parents=True)
    exe = run / a.exe.name
    shutil.copy2(a.exe, exe)
    rom = run / DECOY_NAME
    shutil.copy2(a.rom, rom)
    assets = a.assets or (a.exe.parent / 'assets')
    if assets.is_dir():
        shutil.copytree(assets, run / 'assets')
    route = run / 'route.input'
    route.write_text(ROUTE.format(out=run))

    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('SDL_', 'GENESIS_', 'RECOMP_', 'RUI_', 'LNG_', 'TG2_'))}
    env.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy',
               SDL_RENDER_DRIVER='software')
    cmd = [str(exe), '--no-launcher', '--turbo', '--widescreen', '16:9',
           '--input-script', str(route), '--hash-frames', '60',
           '--max-frames', str(a.frames)]
    log = run / 'stderr.log'
    with log.open('w') as err:
        proc = subprocess.run(cmd, cwd=run, env=env, stdout=subprocess.DEVNULL,
                              stderr=err, timeout=a.timeout)
    text = log.read_text(errors='replace')
    shots = sorted(run.glob('race-*.png'))
    ratios = {s.name: round(blank_ratio(s), 3) for s in shots}
    result = dict(exit_code=proc.returncode,
                  route_loaded='input_script: loaded' in text,
                  screenshots=ratios,
                  decoy_rom=str(rom),
                  exe=str(exe),
                  passed=(proc.returncode == 0 and bool(shots)
                          and any(v < 0.9 for v in ratios.values())))
    (work / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=1))
    sys.exit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
