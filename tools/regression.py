#!/usr/bin/env python3
"""Deterministic TG2 picture/audio regression (Python 3.11+, no dependencies).

Build first, then run under the machine-wide heavy lock:
  flock ~/.cache/tg2-heavy.lock python3 tools/regression.py
  flock ~/.cache/tg2-heavy.lock python3 tools/regression.py --record
WAVs are streamed into SHA-256 and deleted, including on failure. Logs and
manifest counts remain in --out. No TCP server or display is required.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'tools/regression-golden.json'
MANIFESTS = {
    'dispatch_misses.toml': ('functions', 'extra'),
    'floor_coverage.toml': ('functions', 'extra'),
    'interior_label_misses.toml': ('interior_labels', 'addresses'),
    'floor_unsafe.toml': ('floor_unsafe', 'addresses'),
}


def boot_hashes():
    """Canonical stock hashes used by the focused picture probes."""
    frames = json.loads(GOLDEN.read_text())['off-sfx']['frames']
    return {f: frames[str(f)]['hash'] for f in (60, 300)}


def route_script(path):
    lines, previous = [], 1
    for action in json.loads((ROOT / 'game/baseline-route.json').read_text()):
        if 'keys' not in action:
            continue
        frame = action['frame']
        if frame > previous:
            lines.append(f'WAIT {frame - previous}')
        lines.append('RELEASE')
        mask = int(action['keys'], 16)
        lines.extend('HOLD ' + name for bit, name in enumerate(
            ['UP', 'DOWN', 'LEFT', 'RIGHT', 'B', 'C', 'A', 'START']) if mask & (1 << bit))
        previous = frame
    path.write_text('\n'.join(lines + ['WAIT 200', 'EXIT 0']) + '\n')


def capture(args):
    import tomllib
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    script = out / 'route.input'
    route_script(script)
    result, counts = {}, {}
    for presentation in ('off', 'on'):
        for sound in ('sfx', 'music'):
            name = f'{presentation}-{sound}'
            directory = out / name
            directory.mkdir(exist_ok=True)
            (directory / 'settings.ini').write_text('[meta]\nsettings_version = 2\n')
            wav = directory / 'race.wav'
            # An isolated settings directory and explicit overrides prevent a
            # developer's saved options/diagnostic environment affecting the run.
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(('TG2_', 'GENESIS_', 'LNG_'))}
            env.update(SDL_VIDEODRIVER=args.video_driver, SDL_AUDIODRIVER='dummy',
                       SDL_RENDER_DRIVER='software', SDL_RENDER_VSYNC='0', GENESIS_USER_DIR=str(directory) + '/',
                       TG2_RACE_60FPS=str(int(presentation == 'on')),
                       TG2_HIDE_OVERSCAN=str(int(presentation == 'on')),
                       TG2_HUD_MODE='centered', TG2_RACE_SOUND=sound,
                       TG2_HIGHRES_SCALE=str(args.scale))
            cmd = [str(args.exe.resolve()), str(args.rom.resolve()), '--no-launcher',
                   '--widescreen', '16:9' if presentation == 'on' else 'off',
                   '--input-script', str(script), '--max-frames', '5500',
                   '--hash-frames', '60', '--fresh-evidence', '--debug', '--turbo', '--wav', str(wav)]
            if args.uncapped:
                # Full runtime measurement preserves rendering and WAV work;
                # the separate engine benchmark profile suppresses WAV audio.
                at = cmd.index('--max-frames')
                del cmd[at:at + 2]
                cmd.remove('--turbo')
                cmd.extend(['--measure-runtime', '5400', '--runtime-uncapped'])
            try:
                with (directory / 'run.log').open('w') as log:
                    # subprocess.run kills and waits for its child on timeout.
                    completed = subprocess.run(cmd, env=env, stdout=log,
                                               stderr=subprocess.STDOUT, timeout=args.timeout)
                if completed.returncode:
                    raise RuntimeError(f'{name}: exit {completed.returncode}; see {directory / "run.log"}')
                frames = {}
                for frame, width, height, value in re.findall(
                        r'\[FBHASH\] frame=(\d+) w=(\d+) h=(\d+) hash=0x([0-9A-Fa-f]+)',
                        (directory / 'run.log').read_text()):
                    frames[frame] = dict(width=int(width), height=int(height), hash=value.upper())
                expected_frames = {str(f) for f in range(60, 5400, 60)}
                if frames.keys() != expected_frames:
                    raise RuntimeError(f'{name}: incomplete frame cadence ({len(frames)}/89)')
                digest = hashlib.sha256()
                with wav.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(65536), b''):
                        digest.update(chunk)
                counts[name] = {}
                for filename, (section, key) in MANIFESTS.items():
                    manifest = tomllib.loads((directory / filename).read_text())
                    counts[name][filename] = len(manifest[section][key])
                if any(counts[name].values()):
                    raise RuntimeError(f'{name}: nonempty evidence: {counts[name]}')
                result[name] = dict(frames=frames, wav_sha256=digest.hexdigest())
                print(f'{name}: {len(frames)} frames, WAV {digest.hexdigest()}, manifests {counts[name]}', flush=True)
            finally:
                wav.unlink(missing_ok=True)
    (out / 'manifest-counts.json').write_text(json.dumps(counts, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    parser.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/regression')
    parser.add_argument('--golden', type=Path, default=GOLDEN)
    parser.add_argument('--record', action='store_true')
    parser.add_argument('--scale', type=int, choices=range(1, 5), default=1, help='additional N× checks need their own --golden file')
    parser.add_argument('--video-driver', default='dummy', help='SDL driver (dummy works on macOS and Linux; offscreen optional)')
    parser.add_argument('--uncapped', action='store_true', help='full runtime work without host pacing; verify against the same golden')
    parser.add_argument('--timeout', type=int, default=180, help='per-case timeout in seconds')
    args = parser.parse_args()
    if args.scale != 1 and args.golden == GOLDEN:
        parser.error("N× checks require a separate --golden path; the canonical golden is 1×")
    try:
        actual = json.dumps(capture(args), indent=2, sort_keys=True) + '\n'
        (args.out / 'hashes.json').write_text(actual)
        if args.record:
            args.golden.write_text(actual)
            print(f'Recorded {args.golden}')
            return 0
        expected = json.dumps(json.loads(args.golden.read_text()), indent=2, sort_keys=True) + '\n'
        if actual != expected:
            sys.stderr.writelines(difflib.unified_diff(expected.splitlines(True), actual.splitlines(True),
                                                     fromfile=str(args.golden), tofile='actual'))
            return 1
        print('PASS: all 356 frame hashes and four WAV hashes match; all manifest counts zero.')
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
