#!/usr/bin/env python3
"""Windowed frame-time / audio-clock measurement for the TG2 runtime.

Runs the committed baseline race route through the runner's exact-wall-frame
input script (no TCP, no debug server, so a release build measures the same as
a development build) and records the host-side frame statistics ring plus the
DRC bridge counters. Nothing is written outside --out.

The runner records one row per realtime frame in the always-on ring
(GENESIS_FRAME_STATS); this tool only post-processes it:

  frame, interval_us, wait_us, present_us, phase0..8, corr_ppm, fill_us,
  underruns, conceals, pushed_frames, pulled_frames

Reported per window: p50/p95/p99 of the frame interval, the emulation+render
cost (interval minus the pacer wait), DRC ratio range (ppm), ring fill range,
the audio clock error (device frames / wall time) and the guest clock error
(guest frames / wall time).

Example:
  python3 tools/probe_perf.py --exe build-rel/TG2Recomp --out build/perf/rel-on \
      --widescreen 16:9 --hud edges --60fps --display wayland-tg2 \
      --start 3300 --count 3600
"""
import argparse
import csv
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NAMES = ['UP', 'DOWN', 'LEFT', 'RIGHT', 'B', 'C', 'A', 'START']
NTSC_FPS = 60000.0 / 1001.0
PSG_RATE = 223721.0


def route_script(frames: int) -> str:
    """Exact-wall-frame input script for the committed baseline route."""
    actions = {}
    for row in json.loads((ROOT / 'game/baseline-route.json').read_text()):
        if 'keys' in row:
            mask = int(row['keys'], 16)
            actions.setdefault(row['frame'], []).extend(
                ['RELEASE'] + [f'HOLD {name}' for i, name in enumerate(NAMES) if mask & (1 << i)])
    script, previous = [], 1
    for frame, lines in sorted(actions.items()):
        if frame <= previous:
            script.extend(lines)
            continue
        script.extend([f'WAIT {frame - previous}', *lines])
        previous = frame
    if frames > previous:
        script.append(f'WAIT {frames - previous}')
    return '\n'.join(script) + '\n'


def pct(values, p):
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * (len(ordered) - 1) + 0.5))]


def summarise(rows, wall_fps):
    out = {}
    if not rows:
        return out
    interval = [int(r['interval_us']) for r in rows]
    wait = [int(r['wait_us']) for r in rows]
    present = [int(r['present_us']) for r in rows]
    emulation = [i - w for i, w in zip(interval, wait)]
    # Load-independent cost: thread CPU time for the frame minus the CPU burned
    # inside the pacer wait (the busy-spin tail). Present/vsync blocking burns
    # no CPU, so this is emulation + renderer + audio mix.
    cpu_work = []
    for r in rows:
        if 'cpu_wait_us' not in r:
            cpu_work = []
            break
        total = sum(int(r[c]) for c in r if c.startswith('cpu') and
                    c not in ('cpu_wait_us',))
        cpu_work.append(max(0, total - int(r['cpu_wait_us'])))
    corr = [int(r['corr_ppm']) for r in rows]
    fill = [int(r['fill_us']) / 1000.0 for r in rows]
    out['frames'] = len(rows)
    out['interval_us'] = {'p50': pct(interval, .5), 'p95': pct(interval, .95),
                          'p99': pct(interval, .99), 'max': max(interval),
                          'mean': sum(interval) // len(interval)}
    out['emulation_render_us'] = {'p50': pct(emulation, .5), 'p95': pct(emulation, .95),
                                  'p99': pct(emulation, .99), 'max': max(emulation)}
    out['wait_us'] = {'p50': pct(wait, .5), 'p95': pct(wait, .95), 'p99': pct(wait, .99)}
    out['present_us'] = {'p50': pct(present, .5), 'p95': pct(present, .95),
                         'p99': pct(present, .99)}
    out['budget_percent_p95'] = round(100.0 * pct(emulation, .95) /
                                      (1e6 / NTSC_FPS), 2)
    if cpu_work:
        out['cpu_work_us'] = {'p50': pct(cpu_work, .5), 'p95': pct(cpu_work, .95),
                              'p99': pct(cpu_work, .99), 'max': max(cpu_work)}
        out['cpu_budget_percent_p95'] = round(
            100.0 * pct(cpu_work, .95) / (1e6 / NTSC_FPS), 2)
    out['corr_ppm'] = {'min': min(corr), 'max': max(corr),
                       'abs_mean': round(sum(abs(c) for c in corr) / len(corr), 1),
                       'final': corr[-1]}
    out['fill_ms'] = {'min': round(min(fill), 2), 'max': round(max(fill), 2),
                      'final': round(fill[-1], 2)}
    out['underruns'] = int(rows[-1]['underruns'])
    out['conceals'] = int(rows[-1]['conceals'])
    pushed = int(rows[-1]['pushed_frames']) - int(rows[0]['pushed_frames'])
    pulled = int(rows[-1]['pulled_frames']) - int(rows[0]['pulled_frames'])
    # Exact wall span from the absolute pacer stamps (the per-frame interval
    # excludes the loop tail after the last phase marker).
    if 'wall_us' in rows[0] and int(rows[-1]['wall_us']) > int(rows[0]['wall_us']):
        wall = (int(rows[-1]['wall_us']) - int(rows[0]['wall_us'])) / 1e6
    else:
        wall = sum(interval[1:]) / 1e6
    if wall > 0:
        out['wall_seconds'] = round(wall, 3)
        out['guest_frames_per_second'] = round((len(rows) - 1) / wall, 4)
        out['guest_clock_error_ppm'] = round(
            1e6 * ((len(rows) - 1) / wall - NTSC_FPS) / NTSC_FPS, 1)
        out['audio_produced_seconds'] = round(pushed / PSG_RATE, 4)
        out['audio_produced_clock_error_ppm'] = round(
            1e6 * (pushed / PSG_RATE - wall) / wall, 1)
        out['audio_device_seconds'] = round(pulled / wall_fps, 4)
        out['audio_device_clock_error_ppm'] = round(
            1e6 * (pulled / wall_fps - wall) / wall, 1)
        out['audio_drift_ms'] = round(
            1000.0 * ((pushed / PSG_RATE) - wall), 2)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--out', type=Path, default=ROOT / 'build/perf/run')
    p.add_argument('--frames', type=int, default=4000)
    p.add_argument('--start', type=int, default=3096,
                   help='first analysed frame (default: 60 fps option engages)')
    p.add_argument('--count', type=int, default=0,
                   help='analysed frame count (default: to the end)')
    p.add_argument('--windows', default='',
                   help='extra windows as start:count[,start:count...]')
    p.add_argument('--widescreen', default='16:9')
    p.add_argument('--hud', choices=['centered', 'edges'], default='edges')
    p.add_argument('--60fps', dest='fps60', action='store_true', default=True)
    p.add_argument('--no-60fps', dest='fps60', action='store_false')
    p.add_argument('--display', default='',
                   help='WAYLAND_DISPLAY for a nested compositor (empty = real session)')
    p.add_argument('--runtime-dir', default='')
    p.add_argument('--audio-driver', default='',
                   help='SDL_AUDIODRIVER override (dummy for a silent real-time sink)')
    p.add_argument('--volume', type=int, default=0,
                   help='master volume passed to the runtime (measurement is silent)')
    p.add_argument('--load', type=int, default=0,
                   help='run this many CPU burners during the capture')
    p.add_argument('--wav', action='store_true', help='also capture the generated WAV')
    p.add_argument('--cpus', default='',
                   help='taskset CPU list for the runtime (e.g. 4-7)')
    p.add_argument('--extra', nargs='*', default=[])
    a = p.parse_args()

    a.out = a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    a.exe = a.exe.resolve()
    rom = Path.home() / 'roms/genesis/tg2.bin'
    script = a.out / 'route.input'
    script.write_text(route_script(a.frames))

    env = dict(os.environ, TG2_RACE_60FPS='1' if a.fps60 else '0',
               TG2_HUD_MODE=a.hud, GENESIS_FRAME_STATS=str(a.out / 'frame-stats.csv'))
    if a.display:
        env['WAYLAND_DISPLAY'] = a.display
        env.setdefault('SDL_VIDEODRIVER', 'wayland')
    if a.runtime_dir:
        env['XDG_RUNTIME_DIR'] = a.runtime_dir
    if a.audio_driver:
        env['SDL_AUDIODRIVER'] = a.audio_driver
    args = [str(a.exe), str(rom), '--no-launcher',
            '--widescreen', a.widescreen, '--max-frames', str(a.frames),
            '--volume', str(a.volume), '--input-script', str(script), *a.extra]
    if a.wav:
        args += ['--wav', str(a.out / 'audio.wav')]

    if a.cpus:
        args = ['taskset', '-c', a.cpus] + args
    burners = []
    for _ in range(a.load):
        burners.append(subprocess.Popen(
            [sys.executable, '-c', 'while True: pass'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    try:
        with (a.out / 'stdout.log').open('w') as out, (a.out / 'stderr.log').open('w') as err:
            proc = subprocess.Popen(args, cwd=a.exe.parent, env=env, stdout=out, stderr=err)
            code = proc.wait(timeout=600)
    finally:
        for b in burners:
            b.terminate()
        for b in burners:
            try:
                b.wait(timeout=5)
            except subprocess.TimeoutExpired:
                b.kill()

    rows = list(csv.DictReader((a.out / 'frame-stats.csv').open()))
    by_frame = [r for r in rows if int(r['frame']) >= a.start]
    if a.count:
        by_frame = by_frame[:a.count]
    wall_fps = a.extra and 0 or 0
    # device rate is whatever the runner reported; default 48000
    rate = 48000
    text = (a.out / 'stderr.log').read_text(errors='replace')
    for line in text.splitlines():
        if 'Hz device' in line:
            rate = int(line.split('-> ')[1].split(' Hz')[0])
    windows = {'race': by_frame}
    for spec in filter(None, (w.strip() for w in a.windows.split(','))):
        s, c = spec.split(':')
        windows['f%s+%s' % (s, c)] = [r for r in rows
                                      if int(s) <= int(r['frame']) < int(s) + int(c)]
    summary = {
        'command': args,
        'env': {k: v for k, v in env.items()
                if k in ('WAYLAND_DISPLAY', 'SDL_VIDEODRIVER', 'SDL_AUDIODRIVER',
                         'TG2_RACE_60FPS', 'TG2_HUD_MODE', 'XDG_RUNTIME_DIR')},
        'load_burners': a.load,
        'audio_device_rate': rate,
        'exit': code,
        'windows': {name: summarise(rows_win, rate) for name, rows_win in windows.items()},
    }
    (a.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    raise SystemExit(code)


if __name__ == '__main__':
    main()
