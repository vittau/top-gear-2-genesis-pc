#!/usr/bin/env python3
"""Deterministic TG2 picture/audio regression (Python 3.11+, no dependencies).

Build first, then run under the machine-wide heavy lock:
  flock ~/.cache/tg2-heavy.lock python3 tools/regression.py
  flock ~/.cache/tg2-heavy.lock python3 tools/regression.py --record
WAVs are streamed into SHA-256 and deleted, including on failure. Logs and
manifest counts remain in --out. No TCP server or display is required.

Besides the ten picture/audio cases, the tool resumes a race quickstate in a
fresh process sitting at the menus (`*-load-both`, `*-load-sfx`) and compares
the effects layer against the uninterrupted race that saved it, so a
quickstate that loses a sound layer fails here instead of in the player's ear.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tg2_state_audio  # noqa: E402  (resumed-race audio comparison)
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


def route_lines():
    """The shared route as input-script lines (no trailing WAIT/EXIT)."""
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
    return lines


def route_script(path):
    path.write_text('\n'.join(route_lines() + ['WAIT 200', 'EXIT 0']) + '\n')


def insert_options(text, changes):
    """Split absolute WAIT spans; RELEASE/HOLD/OPTION consume no frames."""
    lines, frame = [], 1
    pending = dict(changes)
    for line in text.splitlines():
        if line.startswith('WAIT '):
            end = frame + int(line.split()[1])
            for at in sorted(k for k in pending if frame <= k < end):
                if at > frame:
                    lines.append(f'WAIT {at - frame}')
                lines.append(f'OPTION mods.racesound.mode {pending.pop(at)}')
                frame = at
            if end > frame:
                lines.append(f'WAIT {end - frame}')
            frame = end
        else:
            lines.append(line)
    if pending:
        raise ValueError(f'live options past end of script: {pending}')
    return '\n'.join(lines) + '\n'


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_from_menu_case(args, out, presentation, sound, route):
    """Save during a race, then load that state in a fresh process at the menus.

    The owner's report: with RACE SOUND = BOTH, saving a race quickstate,
    returning to the game's menus and loading it resumed the race without the
    engine sound. BOTH runs the race SFX on a second virtual chip, and the
    quickstate format used to carry only the canonical chip, so the restored
    race drove an idle effects chip: sustained FM voices and the DAC stream
    stayed silent while one-shot effects still keyed themselves.

    Two runs, both ending a fixed number of frames after the save point:
      save   the uninterrupted race (reference audio for those guest frames)
      load   a fresh process sitting at the menus that loads the state
    The comparison is the effects layer's 20-frame RMS windows (see
    tools/tg2_state_audio.py): it needs no sample alignment and fails loudly
    if the layer is missing or mismatched.
    """
    import tomllib
    name = f'{presentation}-load-{sound}'
    directory = out / name
    directory.mkdir(exist_ok=True)
    state = (directory / 'race.state').resolve()
    (directory / 'save.input').write_text(
        '\n'.join(route + ['HOLD B', 'WAIT 240', f'SAVE_STATE {state}',
                           'WAIT 200', 'RELEASE', 'EXIT 0']) + '\n')
    (directory / 'load.input').write_text(
        '\n'.join(['WAIT 600', f'LOAD_STATE {state}', 'HOLD B',
                   'WAIT 200', 'RELEASE', 'EXIT 0']) + '\n')
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('TG2_', 'GENESIS_', 'LNG_'))}
    env.update(SDL_VIDEODRIVER=args.video_driver, SDL_AUDIODRIVER='dummy',
               SDL_RENDER_DRIVER='software', SDL_RENDER_VSYNC='0',
               TG2_RACE_60FPS=str(int(presentation == 'on')),
               TG2_HIDE_OVERSCAN=str(int(presentation == 'on')),
               TG2_HUD_MODE='centered', TG2_RACE_SOUND=sound,
               TG2_HIGHRES_SCALE=str(args.scale))
    runs, counts = {}, {}
    # The save run must outlast the load run: the state is parked at the next
    # resumable gameplay boundary, which is a few frames after the request.
    for role, limit in (('save', 8000), ('load', 2000)):
        work = directory / role
        work.mkdir(exist_ok=True)
        (work / 'settings.ini').write_text('[meta]\nsettings_version = 2\n')
        run_env = dict(env, GENESIS_USER_DIR=str(work) + '/',
                       GENESIS_AUDIO_CHIPDUMP=str(work / 'chip'))
        wav = work / 'run.wav'
        cmd = [str(args.exe.resolve()), str(args.rom.resolve()), '--no-launcher',
               '--widescreen', '16:9' if presentation == 'on' else 'off',
               '--input-script', str(directory / f'{role}.input'),
               '--max-frames', str(limit), '--hash-frames', '60',
               '--fresh-evidence', '--debug', '--turbo', '--wav', str(wav)]
        with (work / 'run.log').open('w') as log:
            completed = subprocess.run(cmd, env=run_env, stdout=log,
                                       stderr=subprocess.STDOUT,
                                       timeout=args.timeout)
        if completed.returncode:
            raise RuntimeError(f'{name}: {role} run exit {completed.returncode}; '
                               f'see {work / "run.log"}')
        counts[f'{role}'] = {}
        for filename, (section, key) in MANIFESTS.items():
            manifest = tomllib.loads((work / filename).read_text())
            counts[f'{role}'][filename] = len(manifest[section][key])
        if any(counts[f'{role}'].values()):
            raise RuntimeError(f'{name}: {role} manifest {counts[f"{role}"]}')
        runs[role] = dict(work=work, wav=wav)
    frames = {}
    for frame, width, height, value in re.findall(
            r'\[FBHASH\] frame=(\d+) w=(\d+) h=(\d+) hash=0x([0-9A-Fa-f]+)',
            (runs['load']['work'] / 'run.log').read_text()):
        frames[frame] = dict(width=int(width), height=int(height), hash=value.upper())
    # Effects layer: chip B in BOTH; the single chip is the whole capture in SFX.
    if sound == 'both':
        channel = 'chipB'
        ref_audio = runs['save']['work'] / 'chipB.wav'
        load_audio = runs['load']['work'] / 'chipB.wav'
    else:
        channel = 'mix'
        ref_audio = runs['save']['wav']
        load_audio = runs['load']['wav']
    verdict = tg2_state_audio.compare(ref_audio, load_audio)
    if not verdict['ok']:
        raise RuntimeError(
            f'{name}: resumed {channel} does not match the uninterrupted race: '
            f'rms {verdict["rms_ref"]} vs {verdict["rms_load"]} '
            f'(ratio {verdict["rms_ratio"]}), windows inside '
            f'{verdict["windows_inside"]}/{verdict["windows"]}: '
            f'{verdict["window_ratios"]}')
    result = dict(frames=frames,
                  wav_sha256=file_sha256(runs['load']['wav']),
                  reference_wav_sha256=file_sha256(runs['save']['wav']),
                  audio={k: verdict[k] for k in
                         ('frames', 'win_frames', 'windows', 'rms_ref', 'rms_load',
                          'rms_ratio', 'peak_ref', 'peak_load', 'peak_ratio',
                          'windows_inside')})
    result['audio']['channel'] = channel
    # The state is a ROM-derived artifact: keep it out of any tree.
    state.unlink(missing_ok=True)
    for role in runs.values():
        path = role['work'] / 'run.wav'
        path.unlink(missing_ok=True)
        for side in ('chipA.wav', 'chipB.wav'):
            (role['work'] / side).unlink(missing_ok=True)
    print(f'{name}: {len(frames)} frames, {channel} RMS '
          f'{verdict["rms_load"]}/{verdict["rms_ref"]} '
          f'(ratio {verdict["rms_ratio"]}), windows '
          f'{verdict["windows_inside"]}/{verdict["windows"]}', flush=True)
    return result, counts


def capture(args):
    import tomllib
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    script = out / 'route.input'
    route_script(script)
    result, counts = {}, {}
    cases = [(f'{p}-{s}', p, s, False, False) for p in ('off', 'on')
             for s in ('sfx', 'music', 'both')]
    cases += [(f'{p}-live-race', p, 'both', True, False) for p in ('off', 'on')]
    cases += [(f'{p}-sound-page', p, 'sfx', False, True) for p in ('off', 'on')]
    for name, presentation, sound, live, page in cases:
        directory = out / name
        directory.mkdir(exist_ok=True)
        (directory / 'settings.ini').write_text('[meta]\nsettings_version = 2\n')
        case_script = script
        limit = 5400
        shots = []
        if live:
            case_script = directory / 'route.input'
            # OPTION uses exactly the runtime-menu setter, at fixed frames.
            text = script.read_text()
            case_script.write_text(insert_options(text, {4200: 0, 4500: 1, 4800: 2}))
        if page:
            case_script = directory / 'route.input'
            lines = ['WAIT 400', 'PRESS START 8', 'WAIT 200', 'PRESS DOWN 6',
                     'WAIT 40', 'PRESS DOWN 6', 'WAIT 40', 'PRESS START 8',
                     'WAIT 200', 'PRESS START 8', 'WAIT 200',
                     'ASSERT_RAM16 0xFF2554 4']
            def shot(label):
                target = directory / (label + '.png')
                shots.append(target)
                lines.extend(['SCREENSHOT ' + str(target), 'WAIT 1'])
            shot('sfx')
            for key, label in [('DOWN', 'music'), ('DOWN', 'both'),
                               ('UP', 'music-again'), ('UP', 'sfx-again')]:
                lines.extend(['PRESS ' + key + ' 6', 'WAIT 120'])
                shot(label)
            for mode in (2, 1, 0):
                lines.extend([f'OPTION mods.racesound.mode {mode}', 'WAIT 120'])
                shot('live-' + ('sfx', 'music', 'both')[mode])
            lines.append('WAIT 300')
            case_script.write_text('\n'.join(lines) + '\n')
            limit = 2161
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
               '--input-script', str(case_script), '--max-frames', str(limit if page else 5500),
               '--hash-frames', '60', '--fresh-evidence', '--debug', '--turbo', '--wav', str(wav)]
        if args.uncapped:
            # Full runtime measurement preserves rendering and WAV work;
            # the separate engine benchmark profile suppresses WAV audio.
            at = cmd.index('--max-frames')
            del cmd[at:at + 2]
            cmd.remove('--turbo')
            cmd.extend(['--measure-runtime', str(limit), '--runtime-uncapped'])
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
            expected_frames = {str(f) for f in range(60, limit, 60)}
            if frames.keys() != expected_frames:
                raise RuntimeError(f'{name}: incomplete frame cadence ({len(frames)}/{len(expected_frames)})')
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
            if shots:
                result[name]['screenshots'] = {p.stem: hashlib.sha256(p.read_bytes()).hexdigest() for p in shots}
            print(f'{name}: {len(frames)} frames, WAV {digest.hexdigest()}, manifests {counts[name]}', flush=True)
        finally:
            wav.unlink(missing_ok=True)
    (out / 'manifest-counts.json').write_text(json.dumps(counts, indent=2) + '\n')
    # Resumed-race audio: save in a race, load in a fresh process at the menus.
    # BOTH is the reported (and fixed) case; SOUND EFFECTS proves the stock
    # single-chip path still resumes exactly as before.
    route = route_lines()
    for presentation, sound in (('off', 'both'), ('off', 'sfx')):
        entry, case_counts = load_from_menu_case(args, out, presentation, sound, route)
        name = f'{presentation}-load-{sound}'
        result[name] = entry
        counts[name] = case_counts['load']
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
        print('PASS: all frame, WAV and SOUND-page screenshot hashes match; all manifest counts zero.')
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
