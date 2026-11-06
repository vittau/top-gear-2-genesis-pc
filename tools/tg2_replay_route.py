#!/usr/bin/env python3
"""Replay a recorded pad route deterministically, one presentation mode per run.

`tools/tg2_race_driver.py` writes `route.json` (frame -> pad mask changes). This
tool turns it into the runner's exact-wall-frame input script, launches one
headless process, samples race state over TCP, and reports lap times plus the
runtime manifests.

Because the input timeline is frame-exact, the same route run in Off, 16:9 and
16:9+60 fps isolates presentation differences from input jitter.

  python3 tools/tg2_replay_route.py --route build/qual/race-off/route.json \
      --out build/qual/replay-off --widescreen off
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import socket
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, RaceState, BUTTON_ORDER  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def route_to_input_script(route, path: Path, shift: int = 0, trace_end: int = 0):
    actions = {}
    for entry in sorted(route, key=lambda e: e['frame']):
        frame = max(1, int(entry['frame']) + shift)
        mask = int(entry['keys'], 16)
        body = ['RELEASE'] + [f'HOLD {name}' for bit, name in enumerate(BUTTON_ORDER)
                              if mask & (1 << bit)]
        actions.setdefault(frame, []).extend(body)
    last = max(actions, default=1)
    lines, previous = [], 1
    for frame, body in sorted(actions.items()):
        lines.extend([f'WAIT {frame - previous}', *body])
        previous = frame
    lines.append(f'WAIT {max(600, trace_end - previous + 600)}')
    # runner/input_script.c has a fixed MAX_OPS, and the runner can otherwise
    # continue without inputs when parsing fails. Reject an oversized route.
    if len(lines) > 4096:
        raise ValueError(f'route exceeds the runner limit of 4096 directives: {len(lines)}')
    path.write_text('\n'.join(lines) + '\n')
    return last


def capture_exact_trace(r, out, end, timeout):
    """Read the always-on frame ring before eviction; never pause the guest.

    A persistent connection avoids a frame of reconnect overhead per request.
    Four 64KiB snapshots per batch fit the runner's nonblocking reply socket.
    Missing/evicted records are fatal; there is no sparse-sample success path.
    """
    dump_dir = out / 'state-ram'
    dump_dir.mkdir(exist_ok=True)
    next_frame, request_id = 1, 0
    deadline = time.monotonic() + timeout
    timings, next_timing = [], 3300
    with socket.create_connection(('127.0.0.1', r.port), timeout=10) as sock:
        sock.settimeout(10)
        reader = sock.makefile()
        def batch(commands):
            nonlocal request_id
            payload = []
            for cmd, args in commands:
                request_id += 1
                payload.append(json.dumps(dict(args, id=request_id, cmd=cmd)) + '\n')
            sock.sendall(''.join(payload).encode())
            result = [json.loads(reader.readline()) for _ in commands]
            for row in result:
                if not row.get('ok'):
                    raise RuntimeError(f'frame history query failed: {row}')
            return result
        while next_frame <= end:
            if time.monotonic() > deadline:
                raise TimeoutError(f'exact trace stopped at frame {next_frame - 1}')
            info = batch([('frame_info', {})])[0]
            if info['oldest_frame'] > next_frame:
                raise RuntimeError(f'frame {next_frame} evicted before capture: {info}')
            available = min(end + 1, info['current_frame'])
            while next_frame < available:
                frames = list(range(next_frame, min(available, next_frame + 4)))
                rows = batch([('get_frame', dict(frame=f, include='wram')) for f in frames])
                for frame, row in zip(frames, rows):
                    if row['frame'] != frame:
                        raise RuntimeError('incorrect frame returned from history')
                    ram = bytes.fromhex(row['wram'])
                    if len(ram) != 65536:
                        raise RuntimeError('incomplete WRAM snapshot')
                    (dump_dir / f'frame-{frame:06d}.ram').write_bytes(ram)
                next_frame = frames[-1] + 1
            if next_frame >= next_timing and next_timing <= 5300:
                timings.append(batch([('tg2_video', {})])[0])
                next_timing += 100
    (out / 'presentation-timing.json').write_text(json.dumps(timings, indent=2) + '\n')


def write_exact_trace(out, expected):
    """History snapshots have an exact V-int label; live TCP sampling can skip.

    Hash all WRAM and the entire player record as well as decoding known fields:
    this covers gear/RPM and every other player field without guessing offsets.
    """
    from tg2_runner import STATE_LO, STATE_LEN, P_BASE
    files = sorted((out / 'state-ram').glob('frame-*.ram'))
    frames = [int(path.stem.split('-')[1]) for path in files]
    if frames != list(range(1, expected + 1)):
        raise RuntimeError(f'incomplete V-int trace: expected {expected} snapshots, got {len(frames)}')
    with (out / 'state-trace.csv').open('w') as f:
        writer = csv.writer(f)
        writer.writerow(['frame', 'clock', 'lap', 'pos', 'lat_raw', 'view', 'speed',
                         'speed2', 'curv', 'slope', 'builds', 'player_sha256', 'wram_sha256'])
        for path in files:
            frame = int(path.stem.split('-')[1])
            ram = path.read_bytes()
            st = RaceState(ram[STATE_LO:STATE_LO + STATE_LEN], frame)
            writer.writerow([frame, st.clock, st.lap, st.pos, st.lat, st.view, st.speed,
                             st.speed2, st.curv, st.slope,
                             int.from_bytes(ram[0x23B4:0x23B6], 'big'),
                             hashlib.sha256(ram[P_BASE:P_BASE + 0x458]).hexdigest(),
                             hashlib.sha256(ram).hexdigest()])


def apply_exact_summary(out, summary):
    from compare_race_replay import read, laps
    exact = read(out)
    lap_times = laps(exact)
    race = summary.setdefault('races', [{}])[0]
    race['lap_times'] = lap_times
    race['start_frame'] = next((f for f, row in sorted(exact.items())
                                if int(row['clock']) > 0), None)
    race['lap_boundaries'] = [dict(lap=x['lap'], frame=x['frame'],
                                  clock=int(exact[x['frame']]['clock']))
                              for x in lap_times if not x['finish']]
    if lap_times and lap_times[-1]['finish']:
        frame = lap_times[-1]['frame']
        race['finish_frame'] = frame
        race['finish_clock'] = int(exact[frame]['clock'])
    return lap_times


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--trace-frames', type=int, default=0,
                   help='fetch exact WRAM from the always-on frame ring at every V-int 1..N')
    p.add_argument('--route', type=Path, required=True)
    p.add_argument('--port', type=int, default=4470)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--widescreen', default='off')
    p.add_argument('--60fps', dest='fps60', action='store_true')
    p.add_argument('--turbo', action='store_true', default=True)
    p.add_argument('--no-turbo', dest='turbo', action='store_false')
    p.add_argument('--hash-frames', type=int, default=60,
                   help='emit framebuffer hashes every N wall frames (1 = cadence counting)')
    p.add_argument('--dump-frames', default='',
                   help='comma-separated frames at which to dump full 64KB WRAM')
    p.add_argument('--screenshot-frames', default='',
                   help='comma-separated frames at which to write a PNG')
    p.add_argument('--shift', type=int, default=0,
                   help='shift every input event by N frames (latency calibration)')
    p.add_argument('--grace', type=int, default=2400,
                   help='frames to keep monitoring past the last route event')
    p.add_argument('--monitor-every', type=int, default=1,
                   help='pause N frames between state polls (keeps turbo replay fast)')
    p.add_argument('--timeout', type=float, default=1800.0)
    a = p.parse_args()

    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    route = json.loads(a.route.read_text())
    last = route_to_input_script(route, out / 'route.input', a.shift, a.trace_frames)
    env = {'TG2_RACE_60FPS': '1' if a.fps60 else '0'}
    args = ['--hash-frames', str(a.hash_frames), '--input-script',
            str((out / 'route.input').resolve())]
    if a.turbo:
        args.append('--turbo')
    r = Runner(port=a.port, out=out, exe=a.exe, rom=a.rom, widescreen=a.widescreen,
               max_frames=max(last + a.grace, a.trace_frames) + 600, env_extra=env, extra_args=args,
               video_driver='offscreen' if a.turbo else 'dummy')
    trace, races = [], []
    result = 'error'
    dump_frames = {int(x) for x in a.dump_frames.split(',') if x.strip()}
    shot_frames = {int(x) for x in a.screenshot_frames.split(',') if x.strip()}
    try:
        r.start()
        if a.trace_frames:
            capture_exact_trace(r, out, a.trace_frames, a.timeout)
        deadline = time.monotonic() + a.timeout
        prev_clock = None
        prev_lap = None
        prev_lat = None
        stall = 0
        race = dict(start_frame=None, finish_frame=None, finish_clock=None,
                    lap_boundaries=[])
        while True:
            if time.monotonic() > deadline:
                result = 'timeout'
                break
            if r.proc.poll() is not None:
                break
            st = r.state_and_frame()
            if st.frame in dump_frames:
                r.dump_ram_file(out / f'ram-{st.frame}.ram')
                dump_frames.discard(st.frame)
            if st.frame in shot_frames:
                r.screenshot(str(out / f'frame-{st.frame}.png'))
                shot_frames.discard(st.frame)
            trace.append(dict(frame=st.frame, clock=st.clock, phase=st.phase,
                              lap=st.lap, pos=st.pos, lat=round(st.lat_units, 3),
                              speed=st.speed, curv=st.curv, slope=st.slope,
                              two_p=st.two_p))
            if race['start_frame'] is None and st.clock > 0:
                race['start_frame'] = st.frame
            if prev_lap is None:
                prev_lap = st.lap
            if st.lap != prev_lap:
                race['lap_boundaries'].append(dict(lap=st.lap, frame=st.frame,
                                                   clock=st.clock))
                prev_lap = st.lap
            stall = stall + 1 if st.clock == prev_clock and st.clock > 0 else 0
            prev_clock = st.clock
            prev_lat = st.lat_units
            if st.clock > 0 and stall >= 12 and st.speed == 0:
                if race['finish_frame'] is None:
                    race['finish_frame'] = st.frame
                    race['finish_clock'] = st.clock
                    r.screenshot(str(out / 'finish.png'))
                result = 'finished'
                if st.frame > a.trace_frames:
                    break
            if st.frame > max(last + a.grace, a.trace_frames):
                result = 'route-ended'
                break
            if a.monitor_every > 1:
                time.sleep(a.monitor_every / 60.0)
        races.append(race)
        lap_times = []
        prev = 0
        boundaries = race['lap_boundaries']
        final_lap = (boundaries[-1]['lap'] + 1) if boundaries else 1
        for b in boundaries + ([dict(lap=final_lap, frame=race['finish_frame'],
                                     clock=race['finish_clock'])]
                               if race['finish_clock'] else []):
            if b['clock'] is None:
                continue
            ticks = b['clock'] - prev
            if ticks <= 0:
                continue
            lap_times.append(dict(lap=b['lap'], ticks=ticks,
                                  seconds=round(ticks / 65536.0 / 50.0, 4),
                                  frame=b['frame']))
            prev = b['clock']
        race['lap_times'] = lap_times
        (out / 'trace.csv').write_text(
            'frame,clock,phase,lap,pos,lat,speed,curv,slope,two_p\n' +
            '\n'.join(','.join(str(t[k]) for k in
                               ('frame', 'clock', 'phase', 'lap', 'pos', 'lat',
                                'speed', 'curv', 'slope', 'two_p')) for t in trace) + '\n')
        summary = dict(result=result, route=str(a.route), races=races,
                       widescreen=a.widescreen, race_60fps=bool(a.fps60),
                       turbo=a.turbo, input_script=str(out / 'route.input'))
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        if not a.trace_frames:
            print(json.dumps(lap_times, indent=2))
        print('result', result)
    finally:
        code = r.stop()
        if a.trace_frames:
            write_exact_trace(out, a.trace_frames)
        from tg2_race_driver import manifests
        m = manifests(out)
        path = out / 'summary.json'
        summary = json.loads(path.read_text()) if path.exists() else {}
        if a.trace_frames:
            lap_times = apply_exact_summary(out, summary)
            print('exact lap times', json.dumps(lap_times))
        summary.update(exit_code=code, manifests=m)
        path.write_text(json.dumps(summary, indent=2) + '\n')
        print('exit', code, 'manifests', m)


if __name__ == '__main__':
    main()
