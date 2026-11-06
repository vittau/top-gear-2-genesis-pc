#!/usr/bin/env python3
"""Run TG2 in real time against a null sink and record what the device played.

The device side is captured from the null sink's monitor (`parecord`), so the
WAV is what the audio device was actually given (post-DRC, post-concealment),
not what the guest generated.

The null sink is created once by the caller, in the owner's own PipeWire
session, and is never the default device:

  pactl load-module module-null-sink sink_name=tg2_test \\
      sink_properties=device.description=tg2_test

This script only ever moves *its own* sink-input onto that sink (SDL opens the
default device, so the stream is moved right after it appears, while the game is
still booting silently), verifies the move, and fails loudly if it could not.

  python3 tools/audio_device_capture.py --exe build-rel/TG2Recomp \\
      --out build/audio15/c27839b-on --sink tg2_test --frames 11000 --mode on

Writes: device.wav (monitor capture), frame-stats.csv, stderr.log, command.txt.
--load N starts N CPU burners for the whole capture.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from probe_perf import route_script  # noqa: E402


def sink_inputs():
    """[(index, sink_name, application_name)] from pactl."""
    out = subprocess.run(['pactl', 'list', 'sink-inputs'], capture_output=True,
                         text=True).stdout
    entries = []
    idx = sink = app = None
    for line in out.splitlines():
        m = re.search(r'Sink Input #(\d+)', line)
        if m:
            if idx is not None:
                entries.append((idx, sink, app))
            idx, sink, app = int(m.group(1)), None, None
            continue
        m = re.search(r'Sink: (\S+)', line.strip())
        if m and idx is not None:
            sink = m.group(1)
        m = re.search(r'application\.name = "([^"]*)"', line)
        if m and idx is not None:
            app = m.group(1)
    if idx is not None:
        entries.append((idx, sink, app))
    sinks = {}
    for line in subprocess.run(['pactl', 'list', 'short', 'sinks'],
                               capture_output=True, text=True).stdout.splitlines():
        parts = line.split('\t')
        if len(parts) >= 2:
            sinks[parts[0]] = parts[1]
    return [(i, sinks.get(s or '', s or ''), a) for i, s, a in entries]


def move_app_streams(app, sink, timeout=3.0):
    """Move every sink-input of `app` to `sink`. Returns True when verified."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        entries = [e for e in sink_inputs() if e[2] == app]
        if entries:
            for idx, cur, _ in entries:
                if cur != sink:
                    subprocess.run(['pactl', 'move-sink-input', str(idx), sink],
                                   capture_output=True)
            entries = [e for e in sink_inputs() if e[2] == app]
            if entries and all(e[1] == sink for e in entries):
                return True
        time.sleep(0.05)
    return False


def wait_for_exit(proc, timeout):
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return -9


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--exe', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--sink', default='tg2_test')
    p.add_argument('--frames', type=int, default=11000)
    p.add_argument('--mode', choices=['on', 'off'], default='on',
                   help='60 fps option (on = owner configuration)')
    p.add_argument('--widescreen', default='16:9')
    p.add_argument('--hud', default='edges')
    p.add_argument('--load', type=int, default=0, help='CPU burners in parallel')
    p.add_argument('--video', default='offscreen',
                   help='SDL_VIDEODRIVER (offscreen keeps the window invisible)')
    p.add_argument('--audio-driver', default='pulseaudio')
    p.add_argument('--taskset', default='')
    p.add_argument('--env', action='append', default=[],
                   help='extra environment K=V (measurement knobs)')
    p.add_argument('--tap', action='store_true',
                   help='also record the in-process device tap (lab builds only)')
    p.add_argument('--extra', nargs='*', default=[])
    a = p.parse_args()

    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    exe = a.exe.resolve()
    rom = Path.home() / 'roms/genesis/tg2.bin'
    script = out / 'route.input'
    script.write_text(route_script(a.frames))
    app_name = exe.name

    env = dict(os.environ)
    env.pop('PULSE_SERVER', None)
    env.update({
        'SDL_VIDEODRIVER': a.video,
        'SDL_AUDIODRIVER': a.audio_driver,
        'TG2_RACE_60FPS': '1' if a.mode == 'on' else '0',
        'TG2_HUD_MODE': a.hud,
        'GENESIS_FRAME_STATS': str(out / 'frame-stats.csv'),
        'GENESIS_AUDIO_BUFFER_TRACE': '1',
    })
    env.pop('PULSE_SINK', None)

    args = [str(exe), str(rom), '--no-launcher', '--widescreen', a.widescreen,
            '--max-frames', str(a.frames), '--volume', '100',
            '--input-script', str(script)] + a.extra
    for kv in a.env:
        k, _, v = kv.partition('=')
        env[k] = v
    if a.tap:
        env['TG2_LAB_DEVICE_WAV'] = str(out / 'tap.wav')
    if a.taskset:
        args = ['taskset', '-c', a.taskset] + args
    rec_path = out / 'device.wav'
    rec_args = ['parecord', '--device=' + a.sink + '.monitor',
                '--rate=48000', '--channels=2', '--format=s16le',
                '--file-format=wav', str(rec_path)]

    burners = []
    recorder = None
    moved = False
    result = {}
    with (out / 'command.txt').open('w') as f:
        f.write(' '.join(args) + '\n')
        for k in sorted(env):
            if k in ('SDL_VIDEODRIVER', 'SDL_AUDIODRIVER', 'PULSE_SINK',
                     'TG2_RACE_60FPS', 'TG2_HUD_MODE'):
                f.write('%s=%s\n' % (k, env[k]))
        f.write('load_burners=%d\nsink=%s\n' % (a.load, a.sink))
    try:
        recorder = subprocess.Popen(
            rec_args, env=env, stdout=subprocess.DEVNULL,
            stderr=(out / 'recorder.log').open('w'))
        time.sleep(0.3)
        for _ in range(a.load):
            burners.append(subprocess.Popen(
                [sys.executable, '-c', 'while True: pass'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        with (out / 'stdout.log').open('w') as so, (out / 'stderr.log').open('w') as se:
            proc = subprocess.Popen(args, cwd=exe.parent, env=env, stdout=so, stderr=se)
            moved = move_app_streams(app_name, a.sink, timeout=5.0)
            if not moved:
                proc.kill()
                proc.wait()
                raise SystemExit('could not move %r to sink %r' % (app_name, a.sink))
            code = wait_for_exit(proc, 900)
            # keep the recorder alive for the tail, then verify we stayed put
        time.sleep(0.6)
        still = [e for e in sink_inputs() if e[2] == app_name]
        result['ended_on_sink'] = [e[1] for e in still] or ['gone']
    finally:
        for b in burners:
            b.terminate()
        for b in burners:
            wait_for_exit(b, 5)
        if recorder:
            recorder.send_signal(signal.SIGINT)
            try:
                recorder.wait(timeout=10)
            except subprocess.TimeoutExpired:
                recorder.kill()
                recorder.wait()
    size = rec_path.stat().st_size if rec_path.exists() else 0
    result.update({'moved': moved, 'exit': code, 'device_wav_bytes': size,
                   'tap_wav_bytes': (out / 'tap.wav').stat().st_size
                   if (out / 'tap.wav').exists() else 0, 'out': str(out)})
    (out / 'capture.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return 0 if code == 0 and size > 100000 else 1


if __name__ == '__main__':
    raise SystemExit(main())
