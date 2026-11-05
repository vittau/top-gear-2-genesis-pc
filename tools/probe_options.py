#!/usr/bin/env python3
"""Capture the player-facing TG2 options: launcher, in-game overlay, persistence.

Everything runs headless. Launcher screenshots use recomp-ui's LNG_SCRIPT
harness; the in-game overlay is opened and navigated through the game's own
TCP `tg2_ui` command. The settings live in an isolated GENESIS_USER_DIR, so a
real player's settings.ini is never touched.

Outputs (under --out, default build/options):
  launcher-dashboard.png  launcher-mods.png  launcher-changed.png
  launcher-widescreen.png launcher-race60.png launcher-hud.png
  overlay-options.png     overlay-hud.png
  settings-after-launcher.ini, settings-after-relaunch.ini
  summary.json
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
p.add_argument('--out', type=Path, default=ROOT / 'build/options')
p.add_argument('--port', type=int, default=4450)
p.add_argument('--timeout', type=float, default=90.0)
a = p.parse_args()
a.exe = a.exe.resolve()
a.out = a.out.resolve()
a.out.mkdir(parents=True, exist_ok=True)
for pattern in ('launcher-*.png', 'overlay-*.png', 'settings-after-*.ini', 'summary.json'):
    for stale in a.out.glob(pattern):
        stale.unlink()
(a.exe.parent / 'debug.ini').touch()

# The launcher only lists a cartridge it can find through content detection.
# A symlink in the build tree is not ROM-derived data and is ignored by git.
rom_link = a.exe.parent / 'tg2.bin'
created_link = False
if not rom_link.exists():
    rom_link.symlink_to(a.rom.resolve())
    created_link = True


def command(name, **kw):
    with socket.create_connection(('127.0.0.1', a.port), timeout=5) as s:
        s.sendall((json.dumps(dict(cmd=name, id=1, **kw)) + '\n').encode())
        return json.loads(s.makefile().readline())


def wait_server(proc, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f'runtime exited early ({proc.returncode})')
        try:
            command('ping')
            return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError('TCP debug server never became reachable')


def run_launcher(user_dir, shots):
    script = ('size:880x736;wait:20;'
              f'shot:{shots}/launcher-dashboard.png;'
              'view:mods;wait:20;'
              f'shot:{shots}/launcher-mods.png;'
              'click:62,516;click:62,570;wait:20;'
              'click:500,200;wait:20;'
              'mod-select:3;wait:10;'
              f'shot:{shots}/launcher-race60.png;'
              'mod-select:4;wait:10;'
              f'shot:{shots}/launcher-hud.png;'
              'click:740,456;wait:60;'
              f'shot:{shots}/launcher-hud-values.png;'
              'click:500,200;wait:20;'
              'mod-select:0;wait:10;'
              'click:740,440;wait:60;'
              f'shot:{shots}/launcher-widescreen.png;'
              'click:500,200;wait:20;'
              'click:750,682;wait:120')
    env = dict(os.environ, SDL_VIDEODRIVER='offscreen', LNG_TEST_HIDDEN='1',
               LNG_SCRIPT=script, GENESIS_USER_DIR=str(user_dir) + '/')
    env.pop('APPIMAGE', None)
    with (shots / 'launcher.log').open('w') as log:
        proc = subprocess.Popen([str(a.exe), '--launcher'], cwd=a.exe.parent,
                                env=env, stdout=log, stderr=subprocess.STDOUT)
        settings = user_dir / 'settings.ini'
        deadline = time.monotonic() + 25
        try:
            while time.monotonic() < deadline and proc.poll() is None:
                if settings.exists() and 'placement = edges' in settings.read_text():
                    break
                time.sleep(0.2)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()


def start_game(user_dir):
    (user_dir / 'debug.ini').touch()
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_RENDER_DRIVER='software',
               SDL_AUDIODRIVER='dummy', GENESIS_USER_DIR=str(user_dir) + '/')
    env.pop('APPIMAGE', None)
    log = (a.out / 'game.log').open('w')
    proc = subprocess.Popen(
        [str(a.exe), str(a.rom), '--no-launcher', '--port', str(a.port),
         '--max-frames', '4000'],
        cwd=a.exe.parent, env=env, stdout=log, stderr=subprocess.STDOUT)
    wait_server(proc, 20)
    return proc, log


def read_settings(path):
    values = {}
    section = None
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
        elif section and '=' in line:
            key, value = line.split('=', 1)
            values[f'{section}.{key.strip()}'] = value.strip()
    return values


# 1. Launcher: change 60 fps to Off and HUD to Edges, then PLAY to persist.
persist = a.out / 'persist'
if persist.exists():
    shutil.rmtree(persist)
persist.mkdir(parents=True)
(persist / 'debug.ini').touch()
run_launcher(persist, a.out)
settings_path = persist / 'settings.ini'
if not settings_path.exists():
    raise RuntimeError('launcher did not write settings.ini; check launcher.log')
shutil.copyfile(settings_path, a.out / 'settings-after-launcher.ini')
after_launcher = read_settings(settings_path)
assert after_launcher.get('mods.race60.enabled') == '0', after_launcher
assert after_launcher.get('mods.hud.placement') == 'edges', after_launcher

# 2. Relaunch and read the values back through the in-game overlay.
proc, log = start_game(persist)
try:
    for action in ['open', 'down', 'down', 'down', 'down', 'accept']:
        command('tg2_ui', action=action)
        time.sleep(0.4)
    time.sleep(0.6)
    command('screenshot', path=str(a.out / 'overlay-options.png'))
    for _ in range(3):
        command('tg2_ui', action='down')
        time.sleep(0.35)
    command('screenshot', path=str(a.out / 'overlay-hud.png'))
    command('tg2_ui', action='back')
    time.sleep(0.4)
    command('quit')
    time.sleep(1.0)
finally:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    log.close()
shutil.copyfile(settings_path, a.out / 'settings-after-relaunch.ini')
after_relaunch = read_settings(settings_path)
assert after_relaunch.get('mods.race60.enabled') == '0', after_relaunch
assert after_relaunch.get('mods.hud.placement') == 'edges', after_relaunch

summary = dict(
    launcher=dict(race60='Off', hud='Edges', widescreen='On / Adaptive',
                  screenshots=sorted(str(x.name) for x in a.out.glob('launcher-*.png'))),
    overlay=dict(screenshots=sorted(str(x.name) for x in a.out.glob('overlay-*.png'))),
    persisted=dict(after_launcher=after_launcher, after_relaunch=after_relaunch),
)
(a.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))

if created_link:
    rom_link.unlink()
