#!/usr/bin/env python3
"""Run one headless native process and drive a free-running TCP timeline.

Example: tools/probe_run.py --frames 2400 --actions '[{"frame":900,"keys":"80"},{"frame":910,"keys":"0"}]'
No guest pause/step or RAM modifications. Logs, PNGs and JSON stay under build/.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
p.add_argument('--out', type=Path, default=ROOT / 'build/probe')
p.add_argument('--frames', type=int, default=1800)
p.add_argument('--port', type=int, default=4400)
p.add_argument('--widescreen', default='off', help='Explicit presentation mode (off, fit, 16:9, 21:9)')
p.add_argument('--shots', default='300,600,900,1200,1500')
p.add_argument('--actions', default='[]', help='JSON list: frame, keys (hex), optional shot name')
p.add_argument('--actions-file', type=Path, help='Read the timeline from a JSON file')
p.add_argument('--force-interp', action='store_true', help='Diagnostic comparison only; not native qualification')
p.add_argument('--timeout', type=int, default=180)
a = p.parse_args()
a.exe = a.exe.resolve()
a.out = a.out.resolve()
a.out.mkdir(parents=True, exist_ok=True)
with socket.socket() as port_check:
    try:
        port_check.bind(('127.0.0.1', a.port))
    except OSError:
        p.error(f'TCP port {a.port} is already in use; stop its owner before launching')
(a.exe.parent / 'debug.ini').touch()
env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_RENDER_DRIVER='software', SDL_AUDIODRIVER='dummy')
# The runner anchors config/saves beside $APPIMAGE when it is set. This probe
# launches the native build directly, not the AppImage, so an inherited
# $APPIMAGE would move debug.ini lookup (and therefore the TCP server) away
# from the build directory.
env.pop('APPIMAGE', None)
if a.force_interp:
    env['GENESIS_FORCE_INTERP'] = '1'
actions = json.loads(a.actions_file.read_text() if a.actions_file else a.actions)
actions += [dict(frame=int(f), shot=f'frame-{f}') for f in a.shots.split(',') if f]
actions.sort(key=lambda x: x['frame'])
events = []
request_id = 0

def command(cmd, **args):
    global request_id
    request_id += 1
    with socket.create_connection(('127.0.0.1', a.port), timeout=5) as s:
        s.sendall((json.dumps(dict(args, id=request_id, cmd=cmd)) + '\n').encode())
        response = json.loads(s.makefile().readline())
    if not response.get('ok'):
        raise RuntimeError(response)
    return response

with (a.out / 'stdout.log').open('w') as out, (a.out / 'stderr.log').open('w') as err:
    proc = subprocess.Popen([str(a.exe), str(a.rom), '--no-launcher', '--port', str(a.port),
        '--max-frames', str(a.frames), '--widescreen', a.widescreen,
        '--hash-frames', '60', '--fresh-evidence',
        '--exec-coverage-out', str(a.out / 'executed-pcs.txt')], cwd=a.exe.parent,
        env=env, stdout=out, stderr=err)
    deadline = time.monotonic() + a.timeout
    try:
        while proc.poll() is None:
            if time.monotonic() > deadline:
                raise TimeoutError('runtime deadline exceeded')
            try:
                frame = command('frame_info')['current_frame']
            except (ConnectionRefusedError, ConnectionResetError):
                time.sleep(0.05)
                continue
            while actions and frame >= actions[0]['frame']:
                action = actions.pop(0)
                record = dict(requested=action, observed_frame=frame)
                if 'cmd' in action:
                    args = {k: v.replace('{out}', str(a.out)) if isinstance(v, str) else v
                            for k, v in action.get('args', {}).items()}
                    record['command'] = command(action['cmd'], **args)
                if 'keys' in action:
                    record['input'] = command('set_input', keys=action['keys'])
                if 'shot' in action:
                    record['screenshot'] = command('screenshot', path=str(a.out / (action['shot'] + '.png')))
                    for cmd in ('get_registers', 'audio_stats', 'dispatch_miss_info', 'vdp_state'):
                        record[cmd] = command(cmd)
                events.append(record)
                (a.out / 'events.json').write_text(json.dumps(events, indent=2) + '\n')
            time.sleep(0.03)
        print(f'exit={proc.returncode} evidence={a.out}')
        if proc.returncode:
            raise SystemExit(proc.returncode)
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
        for name in ('dispatch_misses.toml', 'floor_coverage.toml', 'interior_label_misses.toml', 'floor_unsafe.toml'):
            src = a.exe.parent / name
            if src.exists():
                (a.out / name).write_bytes(src.read_bytes())
