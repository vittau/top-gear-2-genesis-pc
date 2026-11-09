#!/usr/bin/env python3
"""Drive a feedback replay with a different build (input-script translation).

A `TG2-feedback.replay` only plays back on the exact executable that recorded
it: playback compares a byte-exact hash of every machine part. This tool
translates the recorded controller timeline into the runner's input-script
format instead, so any build can follow the same session:

  * pad changes become HOLD/RELEASE at the same tick,
  * `L` markers become LOAD_STATE of the attachment the replay carries,
  * `W` markers become SAVE_STATE on the same path the menu/hotkey uses,
  * `DUMP_RAM` requests let the caller compare work RAM against the recorded
    per-frame `H` hashes to prove the translation stayed on the same session.

Known limit: a run that starts from a quickstate attachment diverges from the
recording on the first tick after that load (the recorded state was taken by
another executable), so this is a boot-and-inputs harness, not a bit-exact
replay. Compare the DUMP_RAM hashes with the recorded H lines to see where it
still agrees; it answered "which screen was the save requested on" for the
save-lost-r4 report.

Example:
  python3 tools/tg2_replay_drive.py --replay <dir>/TG2-feedback.replay \
      --run-dir /tmp/r4run --port 4651 --turbo --verify 500,10000,20129
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner  # noqa: E402

BUTTONS = ['UP', 'DOWN', 'LEFT', 'RIGHT', 'B', 'C', 'A', 'START']


def fnv1a32(data: bytes) -> int:
    h = 2166136261
    for b in data:
        h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return h


def parse_replay(path: Path):
    """Pads per tick, markers on the tick they run before, and H hashes."""
    pads: dict[int, int] = {}
    markers: list[dict] = []
    hashes: dict[int, tuple[int, int, int, int]] = {}
    pending: list[dict] = []
    states: list[dict] = []
    with path.open() as f:
        header = [next(f), next(f), next(f), next(f)]
        sram = 0
        for line in f:
            line = line.rstrip('\n')
            if not line:
                continue
            tag = line[0]
            if tag == 'I':
                f = line.split()
                frame = int(f[1])
                pads[frame] = int(f[2], 16)
                for mark in pending:
                    mark['frame'] = frame
                    markers.append(mark)
                pending = []
            elif tag == 'H':
                f = line.split()
                hashes[int(f[1])] = tuple(int(x, 16) for x in f[2:6])
            elif tag == 'S':
                f = line.split()
                states.append({'offset': int(f[1]), 'size': int(f[2]),
                               'crc': int(f[3], 16)})
                if pending:
                    pending[-1]['state'] = len(states) - 1
            elif line in ('W', 'L', 'A', 'P'):
                pending.append({'kind': line})
            elif tag == 'E':
                break
    return header, sram, pads, markers, hashes, states


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--replay', type=Path, required=True)
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--exe', type=Path,
                   default=Path(__file__).resolve().parents[1] / 'build/TG2Recomp')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--port', type=int, default=4651)
    p.add_argument('--frames', type=int, default=0,
                   help='stop after this wall frame (0 = replay length + 300)')
    p.add_argument('--turbo', action='store_true')
    p.add_argument('--verify', default='', help='comma-separated ticks to DUMP_RAM')
    p.add_argument('--shots', default='', help='comma-separated ticks to SCREENSHOT')
    p.add_argument('--save-name', default='native_save_1.bin',
                   help='file name a W marker saves to (same name the menu uses)')
    p.add_argument('--no-loads', action='store_true',
                   help='ignore L markers (measure the run from a cold boot)')
    p.add_argument('--load-shift', type=int, default=0,
                   help='move every L marker by this many ticks (alignment A/B)')
    p.add_argument('--no-tcp', action='store_true',
                   help='launch the executable directly (release builds have no debug server)')
    a = p.parse_args()

    replay = a.replay.resolve()
    run = a.run_dir.resolve()
    run.mkdir(parents=True, exist_ok=True)
    header, sram, pads, markers, hashes, states = parse_replay(replay)
    sav = Path(str(replay) + '.sav')
    sav_data = sav.read_bytes()
    last = max(pads)

    # Extract each load attachment once (they share content in practice).
    blobs: dict[int, Path] = {}
    for i, st in enumerate(states):
        if not st['size']:
            continue
        blob = sav_data[st['offset']:st['offset'] + st['size']]
        if len(blob) != st['size'] or fnv1a32(blob) != st['crc']:
            raise SystemExit(f'attachment {i} is damaged')
        out = run / f'attached-{i}-{st["size"]}.bin'
        out.write_bytes(blob)
        blobs[i] = out

    verify = [int(x) for x in a.verify.split(',') if x.strip()]
    shots = [int(x) for x in a.shots.split(',') if x.strip()]
    script = []
    script.append('# translated from ' + replay.name)
    # The runner's first input_script_tick call runs at frame 1, after sim tick
    # 0; an op executed at script frame F therefore precedes sim tick F.
    cursor = 1
    events: list[tuple[int, str]] = []
    prev = 0
    for frame in sorted(pads):
        pad = pads[frame]
        if pad == prev:
            continue
        for bit, name in enumerate(BUTTONS):
            if (pad ^ prev) & (1 << bit):
                events.append((frame, ('HOLD ' if pad & (1 << bit) else 'RELEASE ') + name))
        prev = pad
    for mark in markers:
        frame = mark['frame']
        if mark['kind'] == 'L' and not a.no_loads:
            idx = mark.get('state')
            if idx is None or idx not in blobs:
                raise SystemExit('load marker without a state attachment')
            events.append((frame + a.load_shift, f'LOAD_STATE {blobs[idx]}'))
        elif mark['kind'] == 'W':
            events.append((frame, f'SAVE_STATE {run / a.save_name}'))
    for frame in verify:
        events.append((frame, f'DUMP_RAM {run / f"ram-{frame}.bin"}'))
    for frame in shots:
        events.append((frame, f'SCREENSHOT {run / f"shot-{frame}.png"}'))
    events.sort(key=lambda e: e[0])
    for frame, op in events:
        if frame > cursor:
            script.append(f'WAIT {frame - cursor}')
            cursor = frame
        script.append(op)
    frames = a.frames or (last + 300)
    script.append(f'WAIT {max(1, frames - cursor)}')
    script.append('EXIT 0')
    script_path = run / 'replay.input'
    script_path.write_text('\n'.join(script) + '\n')

    settings_src = Path(str(replay) + '.config.ini')
    if settings_src.exists():
        (run / 'settings.ini').write_bytes(settings_src.read_bytes())
    mods_src = Path(str(replay) + '.mods.txt')
    if mods_src.exists():
        (run / 'capture.replay.mods.txt').write_bytes(mods_src.read_bytes())

    report = {'replay': str(replay), 'run_dir': str(run), 'script': str(script_path),
              'ops': len(script), 'last_tick': last, 'frames': frames,
              'save_path': str(run / a.save_name), 'loads': len(blobs),
              'markers': [{'kind': m['kind'], 'frame': m['frame']} for m in markers]}
    (run / a.save_name).unlink(missing_ok=True)

    (run / 'run').mkdir(parents=True, exist_ok=True)
    args = [str(a.exe), str(a.rom), '--no-launcher', '--max-frames', str(frames),
            '--input-script', str(script_path)]
    if a.turbo:
        args.append('--turbo')
    env = dict(__import__('os').environ, SDL_VIDEODRIVER='dummy',
               SDL_RENDER_DRIVER='software', SDL_AUDIODRIVER='dummy',
               GENESIS_USER_DIR=str(run))
    env.pop('APPIMAGE', None)
    with (run / 'run' / 'stdout.log').open('w') as out, \
         (run / 'run' / 'stderr.log').open('w') as err:
        if a.no_tcp:
            code = subprocess.call(args, cwd=run, env=env, stdout=out,
                                   stderr=err, timeout=3600)
        else:
            runner = Runner(port=a.port, out=run / 'run', exe=a.exe, rom=a.rom,
                            widescreen='off', max_frames=frames,
                            extra_args=(['--turbo'] if a.turbo else []) +
                                       ['--input-script', str(script_path)],
                            timeout=180.0)
            try:
                runner.start()
                runner.proc.wait(timeout=1800)
                code = runner.proc.returncode
            finally:
                runner.stop()
    report['exit'] = code

    # Compare sampled work RAM with the recorded per-frame hashes.
    checks = []
    for frame in verify:
        path = run / f'ram-{frame}.bin'
        want = hashes.get(frame)
        got = fnv1a32(path.read_bytes()) if path.exists() else None
        checks.append({'tick': frame,
                       'engine_wram': f'{got:08x}' if got is not None else None,
                       'replay_wram': f'{want[1]:08x}' if want else None,
                       'match': want is not None and got == want[1]})
    report['wram_checks'] = checks
    err = (run / 'run' / 'stderr.log').read_text(errors='replace')
    report['save_lines'] = [l for l in err.splitlines()
                            if l.startswith('[SAVE]') or l.startswith('[LOAD]')
                            or 'input_script' in l and ('SAVE_STATE' in l or 'LOAD_STATE' in l)]
    save = run / a.save_name
    report['state_file'] = {'exists': save.exists(),
                            'size': save.stat().st_size if save.exists() else None,
                            'mtime': save.stat().st_mtime if save.exists() else None}
    print(json.dumps(report, indent=2))
    return 0 if all(c['match'] for c in checks) and not code else 1


if __name__ == '__main__':
    raise SystemExit(main())
