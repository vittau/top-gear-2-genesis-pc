#!/usr/bin/env python3
"""High-resolution qualification (docs/HIGHRES.md §8, S3).

  g1        Canonical Off/1x hashes, non-race canvases, all four manifests.
  s3        Same-frame baseline-route PNGs and box-downscale comparison, 1x..4x.
  drive     Closed-loop track drive, road/stripe-centre/margin audits, paired
            1x/Nx pictures; --no-audit measures cost without audit/dump work.
  nx        Deterministic baseline-route road and margin audit.
  captures  Password-entry track captures (drive also supplies moving pictures).
  option    settings.ini and real Esc-menu scale persistence.
  launcher  Real macOS launcher persistence, scripted in a hidden cocoa window.
  split     Exact-frame 1x versus 4x two-player hashes; geometry stays native.
  cap       3x adaptive canvas cap and Off/fixed-aspect transitions.
  capture   S1 row-state capture versus the live renderer.
  route     Historical S1/S2 identity check, only for a stubbed Nx builder.

Cost example (set saved Linear Filter Off/On separately and keep distinct outputs):
  drive --no-audit --uncapped --cost-route --output-size 1280x800 --scale 4 --frames 360
uses the committed input script and CPU sample interval [3000,3360), with no
screenshots/native dumps or road/margin audits. --uncapped retains full audio
and presentation work, using the engine's finite runtime-measurement mode.

All guest-state access is read-only; controller/UI input drives the real game.
Captures remain under ignored build/. Launcher qualification restores settings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from tg2_runner import Runner, manifest_counts  # noqa: E402
from tg2_coverage import Coverage  # noqa: E402
import tg2_password  # noqa: E402

CANON = {60: '2A0B972960C5E325', 300: '1131D937D70234FD'}
MANIFESTS = ('dispatch_misses.toml', 'floor_coverage.toml',
             'interior_label_misses.toml', 'floor_unsafe.toml')


# ── PNG reading (standard library only: the tool must run without Pillow) ──

def read_png(path: Path):
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'{path}: not a PNG')
    i, idat = 8, b''
    width = height = depth = colour = None
    while i < len(data):
        size = struct.unpack('>I', data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        body = data[i + 8:i + 8 + size]
        i += 12 + size
        if kind == b'IHDR':
            width, height, depth, colour = struct.unpack('>IIBB', body[:10])
        elif kind == b'IDAT':
            idat += body
        elif kind == b'IEND':
            break
    if depth != 8 or colour not in (2, 6):
        raise ValueError(f'{path}: unsupported PNG depth/colour {depth}/{colour}')
    channels = 3 if colour == 2 else 4
    stride = width * channels
    raw = zlib.decompress(idat)
    pixels = bytearray(height * stride)
    previous = bytearray(stride)
    pos = 0
    for y in range(height):
        filt = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        for x in range(stride):
            left = line[x - channels] if x >= channels else 0
            up = previous[x]
            corner = previous[x - channels] if x >= channels else 0
            if filt == 1:
                line[x] = (line[x] + left) & 255
            elif filt == 2:
                line[x] = (line[x] + up) & 255
            elif filt == 3:
                line[x] = (line[x] + (left + up) // 2) & 255
            elif filt == 4:
                estimate = left + up - corner
                pa, pb, pc = abs(estimate - left), abs(estimate - up), abs(estimate - corner)
                line[x] = (line[x] + (left if pa <= pb and pa <= pc else up if pb <= pc else corner)) & 255
        pixels[y * stride:(y + 1) * stride] = line
        previous = line
    return width, height, channels, bytes(pixels)


def png_pixels(path: Path):
    width, height, channels, pixels = read_png(path)
    digest = hashlib.sha256(pixels).hexdigest()[:16]
    return width, height, channels, pixels, digest


# ── shared run helpers ──────────────────────────────────────────────────────

def hashes(out: Path) -> dict:
    found = {}
    for line in (out / 'stderr.log').read_text(errors='replace').splitlines():
        if line.startswith('[FBHASH]'):
            fields = dict(part.split('=', 1) for part in line.split()[1:])
            found[int(fields['frame'])] = fields['hash'][2:].upper()
    return found


def empty_manifests(out: Path) -> dict:
    counts = manifest_counts(out)
    return {name: counts.get(name) for name in MANIFESTS}


def enter_race(r: Runner, port: int, out: Path, country: int = 0, stage: int = 0):
    """Drive the game's own password screen into a race (read-only)."""
    args = SimpleNamespace(country=country, stage=stage, mode='off', port=port,
                           out=out, kp=1.0, kd=4.0, kc=0.0, deadband=9.0,
                           target_lat=0.0, nitro=False, nitro_at=10 ** 9,
                           nitro_for=0, shot_every=600)
    coverage = Coverage(r, args)
    coverage.ui.to_password_screen()
    coverage.ui.type_symbols(tg2_password.encode(country=country, stage=stage)['symbols'])
    coverage.ui.submit()
    state = coverage.press_until_race()
    if state is None:
        raise RuntimeError('never reached a race')
    return state


def wait_exit(r: Runner, timeout: float = 120.0):
    """Wait for the runner to end on its own (--max-frames), not for a frame."""
    import time
    deadline = time.monotonic() + timeout
    while r.proc is not None and r.proc.poll() is None:
        if time.monotonic() > deadline:
            raise TimeoutError('runner did not exit')
        time.sleep(0.02)


def run_hashes(args, mode: str, scale: int, provider: bool, tag: str, race60: bool = False):
    out = args.out / tag
    out.mkdir(parents=True, exist_ok=True)
    env = {'TG2_HIGHRES_SCALE': str(scale),
           'TG2_HIGHRES_TEST_PROVIDER': '1' if provider else '0'}
    if race60:
        env['TG2_RACE_60FPS'] = '1'
    r = Runner(port=args.port, out=out, exe=args.exe, rom=args.rom,
               widescreen=mode, max_frames=args.frames,
               env_extra=env,
               extra_args=['--turbo'])
    try:
        r.start()
        wait_exit(r)
    finally:
        code = r.stop()
    return {'tag': tag, 'mode': mode, 'scale': scale, 'provider': provider,
            'race60': race60, 'exit': code, 'hashes': hashes(out),
            'manifests': empty_manifests(out)}


def check_g1(args):
    plan = [
        ('off', 1, False, False, 'off-scale1'),
        ('off', 2, False, False, 'off-scale2-stub'),
        ('16:9', 1, False, False, '169-scale1'),
        ('16:9', 2, False, False, '169-scale2-stub'),
        ('32:9', 1, False, False, '329-native-menus-scale1'),
        ('32:9', 2, False, False, '329-native-menus-scale2'),
        ('off', 2, True, False, 'off-scale2-testprovider-menus'),
        ('off', 1, False, True, 'off-race60-scale1'),
        ('off', 2, False, True, 'off-race60-scale2-stub'),
    ]
    results = [run_hashes(args, mode, scale, provider, tag, race60)
               for mode, scale, provider, race60, tag in plan]
    failures = []
    for item in results:
        for name, count in item['manifests'].items():
            if count != 0:
                failures.append(f"{item['tag']}: manifest {name} has {count} entries")
        if item['exit'] != 0:
            failures.append(f"{item['tag']}: exit {item['exit']}")
    by_mode = {}
    for item in results:
        if item['provider']:
            continue
        by_mode.setdefault(item['mode'], []).append(item)
    for mode, items in by_mode.items():
        reference = items[0]
        for item in (items if mode == 'off' else []):
            for frame, want in CANON.items():
                got = item['hashes'].get(frame)
                if got != want:
                    failures.append(f"{item['tag']}: frame {frame} hash {got} != {want} (canonical)")
        for item in items[1:]:
            for frame, value in reference['hashes'].items():
                if item['hashes'].get(frame) != value:
                    failures.append(f"{item['tag']}: frame {frame} hash {item['hashes'].get(frame)}"
                                    f" differs from {reference['tag']} {value}")
    # The provider must decline every non-race (menu) frame.
    menu_run = [i for i in results if i['provider']][0]
    for frame, want in CANON.items():
        if menu_run['hashes'].get(frame) != want:
            failures.append(f"{menu_run['tag']}: frame {frame} hash {menu_run['hashes'].get(frame)} != {want}")
    summary = {'check': 'g1', 'runs': results,
               'canonical': {str(k): v for k, v in CANON.items()},
               'failures': failures, 'ok': not failures}
    (args.out / 'g1-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'ok': not failures, 'failures': failures[:8],
                      'runs': [(i['tag'], i['exit'], i['hashes'].get(60),
                                i['hashes'].get(300), i['manifests']) for i in results]}, indent=1))
    return 0 if not failures else 1


def check_capture(args):
    out = args.out / 'capture'
    out.mkdir(parents=True, exist_ok=True)
    r = Runner(port=args.port, out=out, exe=args.exe, rom=args.rom,
               widescreen='off', max_frames=200000,
               env_extra={'TG2_HIGHRES_SCALE': '2', 'TG2_HIGHRES_TIMING': '1'},
               extra_args=['--turbo'])
    samples = []
    failures = []
    r.start()
    try:
        state = enter_race(r, args.port, out)
        start = state.frame
        r.wait_frame(start + 300)
        r.set_input(0x10)
        last = 0
        while len(samples) < args.samples:
            frame = r.frame()
            if frame - last >= args.spacing:
                last = frame
                data = r.command('tg2_highres', rows=1)
                rows, live = data['rows'], data['live']
                serial = data['serial']
                fresh = [i for i in range(len(rows)) if rows[i]['gen'] == serial]
                mismatch = [i for i in fresh
                            if (rows[i]['ha'], rows[i]['hb'], rows[i]['va'], rows[i]['vb'])
                            != (live[i]['ha'], live[i]['hb'], live[i]['va'], live[i]['vb'])]
                road = [i for i in fresh if rows[i]['flags'] & 1]
                item = {'frame': frame, 'serial': serial,
                        'capture_frames': data['capture_frames'],
                        'capture_us': data['capture_us'],
                        'capture_rows': data['capture_rows'],
                        'fresh_rows': len(fresh), 'road_rows': len(road),
                        'mismatches': mismatch[:16],
                        'identical': not mismatch,
                        'rows': rows, 'live': live}
                samples.append(item)
                print(f"frame={frame} serial={serial} fresh={len(fresh)} road={len(road)} "
                      f"mismatch={len(mismatch)} capture_us={data['capture_us']:.2f} "
                      f"rows={data['capture_rows']}")
            r.set_input(0x10)
            r.wait_frame(frame + 5)
        r.set_input(0)
    finally:
        code = r.stop()
    for item in samples:
        if not item['identical']:
            failures.append(f"frame {item['frame']}: {len(item['mismatches'])} row mismatches")
        if not item['road_rows']:
            failures.append(f"frame {item['frame']}: no road rows classified")
    costs = [s['capture_us'] for s in samples if s['capture_rows']]
    per_picture = sum(costs) / len(costs) if costs else 0.0
    per_row = (sum(costs) / sum(s['capture_rows'] for s in samples)) if costs else 0.0
    summary = {'check': 'capture', 'scale': 2, 'exit': code,
               'samples': len(samples), 'spacing': args.spacing,
               'capture_us_per_picture': round(per_picture, 2),
               'capture_ns_per_row': round(per_row * 1000.0, 1),
               'manifests': empty_manifests(out),
               'failures': failures, 'ok': not failures}
    (out / 'samples.json').write_text(json.dumps(samples) + '\n')
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: summary[k] for k in
                      ('ok', 'failures', 'capture_us_per_picture', 'capture_ns_per_row',
                       'manifests')}, indent=1))
    return 0 if not failures else 1


def pattern_report(pixels, width, height, channels):
    """Facts about the S2 synthetic pattern after presentation. The 2x picture
    is cropped by 16 rows at the top (8N, the overscan band), so the pattern's
    32-row rulers land on presented rows where (y + 16) % 32 == 0."""
    def rgb(x, y):
        offset = (y * width + x) * channels
        return tuple(pixels[offset:offset + 3])

    rulers, distinct, sampled = [], set(), 0
    for y in range(0, height, 4):
        if (y + 16) % 32 == 0:
            if rgb(1, y) == (0, 255, 255):
                rulers.append(y)
            continue
        sampled += 1
        distinct.add(pixels[y * width * channels:(y + 1) * width * channels])
    return {
        'left_edge': rgb(0, 0),
        'right_edge': rgb(width - 1, 0),
        'first_row_mid': rgb(width // 2, 0),
        'ruler_rows': rulers,
        'distinct_rows': len(distinct),
        'sampled_rows': sampled,
    }


def route_script(route_path: Path, path: Path, end_frame: int):
    """Frame-exact input script from the committed baseline controller route.
    Only the key actions are used; the route's captures and commands are not."""
    names = ['UP', 'DOWN', 'LEFT', 'RIGHT', 'B', 'C', 'A', 'START']
    actions = {}
    for action in json.loads(route_path.read_text()):
        if 'keys' not in action:
            continue
        bits = int(action['keys'], 16)
        lines = ['RELEASE'] + ['HOLD ' + name for bit, name in enumerate(names) if bits & (1 << bit)]
        actions.setdefault(int(action['frame']), []).extend(lines)
    lines, previous = [], 1
    for frame in sorted(actions):
        if frame > previous:
            lines.append(f'WAIT {frame - previous}')
        lines.extend(actions[frame])
        previous = frame
    if end_frame > previous:
        lines.append(f'WAIT {end_frame - previous}')
    lines.append('EXIT 0')
    path.write_text('\n'.join(lines) + '\n')
    return path


def check_route(args):
    """The committed baseline route is frame-exact (input script), so two runs
    with different render scales must emit the same framebuffer hash on every
    sampled frame, race included. This is the byte-identity gate for S1/S2."""
    out_root = args.out / 'route'
    out_root.mkdir(parents=True, exist_ok=True)
    plan = [('off', 1, 'off-scale1'), ('off', 2, 'off-scale2-stub'),
            ('16:9', 1, '169-scale1'), ('16:9', 2, '169-scale2-stub')]
    results, failures = [], []
    for mode, scale, tag in plan:
        out = out_root / tag
        out.mkdir(parents=True, exist_ok=True)
        script = route_script(args.route, out / 'route.input', args.end_frame)
        r = Runner(port=args.port, out=out, exe=args.exe, rom=args.rom,
                   widescreen=mode, max_frames=args.end_frame + 1,
                   env_extra={'TG2_HIGHRES_SCALE': str(scale),
                              'TG2_HIGHRES_TEST_PROVIDER': '0'},
                   extra_args=['--turbo', '--input-script', str(script)])
        try:
            r.start()
            wait_exit(r, timeout=900)
        finally:
            code = r.stop()
        item = {'tag': tag, 'mode': mode, 'scale': scale, 'exit': code,
                'hashes': hashes(out), 'manifests': empty_manifests(out)}
        results.append(item)
        print(tag, 'exit', code, 'hashes', len(item['hashes']))
    by_mode = {}
    for item in results:
        by_mode.setdefault(item['mode'], []).append(item)
        for name, count in item['manifests'].items():
            if count != 0:
                failures.append(f"{item['tag']}: manifest {name} has {count} entries")
        if item['exit'] != 0:
            failures.append(f"{item['tag']}: exit {item['exit']}")
    for mode, items in by_mode.items():
        reference, stub = items[0], items[1]
        common = sorted(set(reference['hashes']) & set(stub['hashes']))
        differing = [f for f in common if reference['hashes'][f] != stub['hashes'][f]]
        stub['compared_frames'] = len(common)
        stub['identical_frames'] = len(common) - len(differing)
        if not common:
            failures.append(f'{mode}: no framebuffer hashes captured')
        if differing:
            failures.append(f"{mode}: scale {stub['scale']} differs from 1x at "
                            f"{len(differing)}/{len(common)} frames (first {differing[0]})")
        if mode == 'off':
            for frame, want in CANON.items():
                for item in items:
                    if item['hashes'].get(frame) != want:
                        failures.append(f"{item['tag']}: frame {frame} hash "
                                        f"{item['hashes'].get(frame)} != {want}")
        # The route must actually reach a race: the later frames have to differ
        # from the boot picture, otherwise this proves nothing about race rows.
        if len(common) > 80 and len({reference['hashes'][f] for f in common[-20:]}) < 2:
            failures.append(f'{mode}: route pictures stopped changing')
    summary = {'check': 'route', 'end_frame': args.end_frame, 'runs': results,
               'failures': failures, 'ok': not failures}
    (out_root / 'route-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'ok': not failures, 'failures': failures,
                      'compared': {i['tag']: i.get('compared_frames') for i in results}}, indent=1))
    return 0 if not failures else 1


def geometry_hashes(out: Path):
    """framebuffer hash lines with the geometry the runner reported."""
    found = {}
    for line in (out / 'stderr.log').read_text(errors='replace').splitlines():
        if line.startswith('[FBHASH]'):
            fields = dict(part.split('=', 1) for part in line.split()[1:])
            found[int(fields['frame'])] = (int(fields['w']), int(fields['h']),
                                           fields['hash'][2:].upper())
    return found


def check_split(args):
    """2P split-screen is excluded from the N x path: `race()` fails while
    `$FF189E != 0`, so the builder must decline. The committed 2P script is
    frame-exact, so the framebuffer series at 1x and 4x
    must be identical, and no picture may grow."""
    from tg2_split_screen import build_script
    out_root = args.out / 'split2p'
    out_root.mkdir(parents=True, exist_ok=True)
    script, race_start = build_script(12, 280, [])
    results, failures = [], []
    for provider in (False, True):
        tag = 'split2p-provider' if provider else 'split2p-stock'
        out = out_root / tag
        out.mkdir(parents=True, exist_ok=True)
        path = out / 'split2p.input'
        path.write_text(script.text())
        r = Runner(port=args.port, out=out, exe=args.exe, rom=args.rom,
                   widescreen=args.mode, max_frames=script.frame + 300,
                   env_extra={'TG2_HIGHRES_SCALE': str(args.scale) if provider else '1',
                              'TG2_HIGHRES_TEST_PROVIDER': '0'},
                   extra_args=['--turbo', '--hash-frames', '1',
                               '--input-script', str(path)],
                   video_driver='dummy')
        two_p, last_frame = 0, 0
        try:
            r.start()
            while r.proc.poll() is None:
                state = r.state_and_frame()
                last_frame = state.frame
                if state.two_p:
                    two_p += 1
                if state.frame > script.frame:
                    break
                import time as _time
                _time.sleep(0.01)
        finally:
            code = r.stop()
        item = {'tag': tag, 'exit': code, 'two_p_samples': two_p,
                'race_start_estimate': race_start, 'last_frame': last_frame,
                'frames': geometry_hashes(out), 'manifests': empty_manifests(out)}
        results.append(item)
        print(tag, 'exit', code, 'two_p samples', two_p, 'hash frames', len(item['frames']))
    stock, test = results
    if not stock['two_p_samples']:
        failures.append('never observed $FF189E != 0 (no 2P frame sampled)')
    heights = {h for item in results for (_, h, _) in item['frames'].values()}
    widths = {w for item in results for (w, _, _) in item['frames'].values()}
    if heights - {224, 448}:
        failures.append(f'2P presented height changed: {sorted(heights)}')
    numerator, denominator = (int(x) for x in args.mode.split(':'))
    expected_width = int(224 * numerator / denominator + 0.5)
    if any(w > expected_width for w in widths):
        failures.append(f'2P presented width changed: {sorted(widths)}')
    common = sorted(set(stock['frames']) & set(test['frames']))
    differing = [f for f in common if stock['frames'][f] != test['frames'][f]]
    if not common:
        failures.append('no 2P framebuffer hashes captured')
    if differing:
        failures.append(f'test provider changed {len(differing)}/{len(common)} 2P frames')
    for item in results:
        if item['exit'] != 0:
            failures.append(f"{item['tag']}: exit {item['exit']}")
        for name, count in item['manifests'].items():
            if count != 0:
                failures.append(f"{item['tag']}: manifest {name} has {count} entries")
    summary = {'check': 'split', 'mode': args.mode, 'test_scale': args.scale,
               'runs': results, 'widths': sorted(widths),
               'heights': sorted(heights), 'compared_frames': len(common),
               'failures': failures, 'ok': not failures}
    (out_root / 'split-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'ok': not failures, 'failures': failures,
                      'widths': sorted(widths), 'heights': sorted(heights),
                      'compared': len(common)}, indent=1))
    return 0 if not failures else 1


SHOTS = (3400, 3500, 3600, 4501)


def route_script_shots(route_path: Path, path: Path, end_frame: int, shots):
    """Frame-exact route script with SCREENSHOT directives at exact frames."""
    names = ['UP', 'DOWN', 'LEFT', 'RIGHT', 'B', 'C', 'A', 'START']
    actions = {}
    for action in json.loads(route_path.read_text()):
        if 'keys' not in action:
            continue
        bits = int(action['keys'], 16)
        lines = ['RELEASE'] + ['HOLD ' + name for bit, name in enumerate(names) if bits & (1 << bit)]
        actions.setdefault(int(action['frame']), []).extend(lines)
    for frame in shots:
        actions.setdefault(int(frame), []).append(f'SCREENSHOT {path.parent}/frame-{frame}.png')
    lines, previous = [], 1
    for frame in sorted(actions):
        if frame > previous:
            lines.append(f'WAIT {frame - previous}')
        lines.extend(actions[frame])
        previous = frame
    if end_frame > previous:
        lines.append(f'WAIT {end_frame - previous}')
    lines.append('EXIT 0')
    path.write_text('\n'.join(lines) + '\n')
    return path


def run_route_scale(args, mode, scale, tag, out_root, shots, audit=False, margin=False,
                    end_frame=None):
    out = out_root / tag
    out.mkdir(parents=True, exist_ok=True)
    end = end_frame or args.end_frame
    script = route_script_shots(args.route, out / 'route.input', end, shots)
    env = {'TG2_HIGHRES_SCALE': str(scale), 'TG2_RACE_60FPS': '0'}
    if audit:
        (out / 'audit').mkdir(exist_ok=True)
        env['TG2_ROAD_AUDIT_DIR'] = str((out / 'audit').resolve())
    if margin:
        env['TG2_MARGIN_AUDIT'] = str((out / 'margins.csv').resolve())
    r = Runner(port=args.port, out=out, exe=args.exe, rom=args.rom,
               widescreen=mode, max_frames=end + 1, env_extra=env,
               extra_args=['--turbo', '--input-script', str(script)])
    try:
        r.start()
        wait_exit(r, timeout=1800)
    finally:
        code = r.stop()
    item = {'tag': tag, 'mode': mode, 'scale': scale, 'exit': code,
            'manifests': empty_manifests(out), 'out': str(out)}
    return item


def downsample(pixels, w, h, channels, n):
    """Box-downsample an RGB picture by an integer factor."""
    out = bytearray()
    for y in range(0, h, n):
        for x in range(0, w, n):
            acc = [0, 0, 0]
            for dy in range(n):
                base = ((y + dy) * w + x) * channels
                for dx in range(n):
                    off = base + dx * channels
                    acc[0] += pixels[off]
                    acc[1] += pixels[off + 1]
                    acc[2] += pixels[off + 2]
            count = n * n
            out.extend(v // count for v in acc)
    return bytes(out)


def compare_downscaled(reference, candidate):
    """Structural comparison of two RGB pictures of the same size."""
    if len(reference) != len(candidate):
        return None
    total = len(reference) // 3
    mean = 0
    big = edge = worst = 0
    for i in range(0, len(reference), 3):
        d = max(abs(reference[i] - candidate[i]),
                abs(reference[i + 1] - candidate[i + 1]),
                abs(reference[i + 2] - candidate[i + 2]))
        mean += d
        if d > worst:
            worst = d
        if d > 64:
            big += 1
        elif d > 16:
            edge += 1
    return {'pixels': total, 'mean_abs_diff': round(mean / total, 3),
            'max_diff': worst, 'big_diff_pixels': big,
            'edge_diff_pixels': edge,
            'big_diff_ratio': round(big / total, 5),
            'edge_diff_ratio': round(edge / total, 5)}


def check_s3(args):
    """S3: real N x pictures on the deterministic route, byte-compared with the
    1x reference after a box downsample. Road edges may differ by antialiasing;
    a fan, gap or torn row breaks the structural budget."""
    out_root = args.out / 's3'
    out_root.mkdir(parents=True, exist_ok=True)
    scales = [int(x) for x in args.scales.split(',') if x.strip()]
    shots = tuple(args.shots)
    results, failures = [], []
    for scale in scales:
        tag = f'{args.mode.replace(":", "-")}-scale{scale}'
        item = run_route_scale(args, args.mode, scale, tag, out_root, shots)
        results.append(item)
        print(tag, 'exit', item['exit'])
        for name, count in item['manifests'].items():
            if count != 0:
                failures.append(f"{tag}: manifest {name} has {count} entries")
        if item['exit'] != 0:
            failures.append(f"{tag}: exit {item['exit']}")
    reference = results[0]
    for item in results[1:]:
        n = item['scale']
        for frame in shots:
            ref_path = Path(reference['out']) / f'frame-{frame}.png'
            cand_path = Path(item['out']) / f'frame-{frame}.png'
            if not ref_path.exists() or not cand_path.exists():
                failures.append(f"{item['tag']}: missing frame {frame} screenshot")
                continue
            rw, rh, rc, rpix, _ = png_pixels(ref_path)
            cw, ch, cc, cpix, _ = png_pixels(cand_path)
            if (cw, ch) != (rw * n, rh * n):
                failures.append(f"{item['tag']}: frame {frame} is {cw}x{ch}, "
                                f"expected {rw * n}x{rh * n}")
                continue
            small = downsample(cpix, cw, ch, cc, n)
            metrics = compare_downscaled(rpix, small)
            item.setdefault('downscale', {})[frame] = metrics
            if not metrics:
                failures.append(f"{item['tag']}: frame {frame} size mismatch")
                continue
            if metrics['mean_abs_diff'] > args.max_mean_diff:
                failures.append(f"{item['tag']}: frame {frame} mean diff "
                                f"{metrics['mean_abs_diff']} > {args.max_mean_diff}")
            if metrics['big_diff_ratio'] > args.max_big_ratio:
                failures.append(f"{item['tag']}: frame {frame} big-diff ratio "
                                f"{metrics['big_diff_ratio']} > {args.max_big_ratio}")
    summary = {'check': 's3', 'mode': args.mode, 'end_frame': args.end_frame,
               'shots': list(shots), 'runs': results,
               'failures': failures, 'ok': not failures}
    (out_root / 's3-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'ok': not failures, 'failures': failures,
                      'downscale': {i['tag']: i.get('downscale') for i in results[1:]}},
                     indent=1))
    return 0 if not failures else 1


# The password's country field is the 4-bit country; a password always starts
# at that country's first race, so only Bavaria (Germany slot 1) is rainy from
# the entry point (docs/PASSWORDS.md).
TRACKS = {
    'auckland': dict(country=0, stage=0, note='straight, curve and hill frames; the tunnel is here'),
    'bavaria-rain': dict(country=5, stage=0, note='Germany slot 1, rainy from the start (docs/PASSWORDS.md)'),
    'canada': dict(country=2, stage=0, note='a dry second track with its own atlas'),
}


def enter_race_password(r, port, out, country, stage):
    args = SimpleNamespace(country=country, stage=stage, mode='off', port=port,
                           out=out, kp=1.0, kd=4.0, kc=0.0, deadband=9.0,
                           target_lat=0.0, nitro=False, nitro_at=10 ** 9,
                           nitro_for=0, shot_every=600)
    coverage = Coverage(r, args)
    coverage.ui.to_password_screen()
    coverage.ui.type_symbols(tg2_password.encode(country=country, stage=stage)['symbols'])
    coverage.ui.submit()
    state = coverage.press_until_race()
    if state is None:
        raise RuntimeError('never reached a race')
    return state


def settings_write(settings: Path, key: str, value: int):
    """Set one key in settings.ini, preserving everything else."""
    lines = settings.read_text().splitlines() if settings.exists() else []
    out, done = [], False
    for line in lines:
        if line.strip().startswith(key) and '=' in line:
            out.append(f'{key} = {value}')
            done = True
        else:
            out.append(line)
    if not done:
        out.insert(0, f'{key} = {value}')
    settings.write_text('\n'.join(out) + '\n')


def settings_read(settings: Path, key: str):
    if not settings.exists():
        return None
    for line in settings.read_text().splitlines():
        line = line.strip()
        if line.startswith(key) and '=' in line:
            try:
                return int(line.split('=', 1)[1].strip())
            except ValueError:
                return None
    return None


def check_option(args):
    """The experimental render scale round-trips through settings.ini and the
    in-game (Esc) menu, and 1x stays a no-op."""
    out_root = args.out / 'option'
    out_root.mkdir(parents=True, exist_ok=True)
    settings = args.exe.parent / 'settings.ini'
    backup = settings.read_text() if settings.exists() else None
    results, failures = [], []
    try:
        for value, expect in [(1, 1), (2, 2), (3, 3), (4, 4), (8, 1)]:
            settings_write(settings, 'internal_scale', value)
            out = out_root / f'settings-{value}'
            out.mkdir(parents=True, exist_ok=True)
            r = Runner(port=args.port, out=out, exe=args.exe, rom=args.rom,
                       widescreen='off', max_frames=90,
                       env_extra={'TG2_RACE_60FPS': '0'}, extra_args=['--turbo'])
            try:
                r.start()
                data = r.command('tg2_video')
                got = data.get('highres_scale')
                r.wait_frame(60)
            finally:
                code = r.stop()
            item = {'settings_value': value, 'expected_scale': expect,
                    'reported_scale': got, 'exit': code,
                    'manifests': empty_manifests(out)}
            results.append(item)
            print(f'internal_scale={value} -> render scale {got} (expect {expect})')
            if got != expect:
                failures.append(f'settings {value}: reported scale {got}, expected {expect}')
            for name, count in item['manifests'].items():
                if count != 0:
                    failures.append(f'settings {value}: manifest {name} has {count} entries')
            if code != 0:
                failures.append(f'settings {value}: exit {code}')
        # In-game (Esc) menu: find the row, change it, read settings.ini back.
        settings_write(settings, 'internal_scale', 1)
        out = out_root / 'esc-menu'
        out.mkdir(parents=True, exist_ok=True)
        r = Runner(port=args.port, out=out, exe=args.exe, rom=args.rom,
                   widescreen='off', max_frames=1200,
                   env_extra={'TG2_RACE_60FPS': '0'}, extra_args=['--turbo'])
        menu = {}
        try:
            r.start()
            r.wait_frame(120)
            def tap(name):
                # "held" is the key state; a tap needs frames between the edges.
                r.command('key', name=name, held=1)
                r.wait_frame(r.frame() + 3)
                r.command('key', name=name, held=0)
                r.wait_frame(r.frame() + 8)

            # The runtime menu is paged; the row lives on the VIDEO page.
            r.command('ui_open', section='VIDEO')
            r.wait_frame(r.frame() + 8)
            rows = r.command('ui_rows')['rows']
            menu['rows'] = [row['label'] for row in rows]
            index = next(i for i, row in enumerate(rows)
                         if 'Internal resolution' in row['label'])
            menu['row_index'] = index
            menu['row_label'] = rows[index]['label']
            menu['before'] = rows[index]['value']
            menu['labels'] = [menu['before']]
            selected = next((i for i, row in enumerate(rows) if row['selected']), 0)
            for _ in range(abs(index - selected)):
                tap('down' if index > selected else 'up')
            # Walk the choice list to its end, recording every label.
            for _ in range(3):
                tap('right')
                label = r.command('ui_rows')['rows'][index]['value']
                if label not in menu['labels']:
                    menu['labels'].append(label)
            menu['after'] = r.command('ui_rows')['rows'][index]['value']
            tap('escape')
            r.wait_frame(r.frame() + 30)
        finally:
            menu['exit'] = r.stop()
        menu['settings_after'] = settings_read(settings, 'internal_scale')
        menu['manifests'] = empty_manifests(out)
        for name, count in menu['manifests'].items():
            if count != 0:
                failures.append(f'Esc menu: manifest {name} has {count} entries')
        results.append({'tag': 'esc-menu', **menu})
        print('esc menu', menu)
        if '4x' not in menu['labels']:
            failures.append(f"menu choices do not reach 4x: {menu['labels']}")
        if menu['before'] == menu['after']:
            failures.append('menu right did not change the value')
        if menu['settings_after'] != 4:
            failures.append(f"menu left settings.ini internal_scale at "
                            f"{menu['settings_after']}, expected 4")
    finally:
        if backup is None:
            if settings.exists():
                settings.unlink()
        else:
            settings.write_text(backup)
    summary = {'check': 'option', 'runs': results, 'failures': failures,
               'ok': not failures}
    (out_root / 'option-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'ok': not failures, 'failures': failures}, indent=1))
    return 0 if not failures else 1


def check_captures(args):
    """S3 captures: real N x race pictures on several tracks and scales."""
    out_root = args.out / 'captures'
    out_root.mkdir(parents=True, exist_ok=True)
    plan = []
    for spec in args.plan.split(';'):
        track, scales = spec.split(':')
        for scale in [int(x) for x in scales.split(',')]:
            plan.append((track, scale))
    results, failures = [], []
    for track, scale in plan:
        info = TRACKS[track]
        tag = f'{track}-scale{scale}'
        out = out_root / tag
        out.mkdir(parents=True, exist_ok=True)
        env = {'TG2_HIGHRES_SCALE': str(scale), 'TG2_RACE_60FPS': '0',
               'TG2_HIGHRES_TIMING': '1'}
        r = Runner(port=args.port, out=out, exe=args.exe, rom=args.rom,
                   widescreen=args.mode, max_frames=200000, env_extra=env,
                   extra_args=['--turbo'], timeout=120)
        shots, item = [], {'tag': tag, 'track': track, 'scale': scale,
                           'country': info['country'], 'note': info['note']}
        r.start()
        try:
            state = enter_race_password(r, args.port, out, info['country'], info['stage'])
            r.set_input(0x10)
            for offset in args.offsets:
                r.wait_frame(state.frame + offset)
                path = r.screenshot(f'{tag}-{offset}.png')
                w, h, channels, pixels, digest = png_pixels(Path(path))
                shots.append({'frame_offset': offset, 'path': str(path),
                              'size': [w, h], 'digest': digest})
            video = r.command('tg2_video')
            item['video'] = {k: video.get(k) for k in
                             ('highres_scale', 'highres_present_scale',
                              'highres_capture_us', 'highres_build_us',
                              'highres_build_frames', 'crop', 'crop_frames')}
            r.set_input(0)
        finally:
            item['exit'] = r.stop()
        item.update({'shots': shots, 'manifests': empty_manifests(out)})
        results.append(item)
        print(tag, item['exit'], [s['size'] for s in shots], item['video'])
        for name, count in item['manifests'].items():
            if count != 0:
                failures.append(f"{tag}: manifest {name} has {count} entries")
        if item['exit'] != 0:
            failures.append(f"{tag}: exit {item['exit']}")
        expect_w = None
        for shot in shots:
            w, h = shot['size']
            if h % 200 and h % 224:
                failures.append(f"{tag}: unexpected height {h}")
            if scale > 1 and h <= 224:
                failures.append(f"{tag}: scale {scale} picture is only {h} rows")
    summary = {'check': 'captures', 'mode': args.mode, 'offsets': args.offsets,
               'plan': args.plan, 'runs': results, 'failures': failures,
               'ok': not failures}
    (out_root / 'captures-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'ok': not failures, 'failures': failures}, indent=1))
    return 0 if not failures else 1


def read_ppm(path: Path):
    data = path.read_bytes()
    parts = data.split(b'\n', 3)
    w, h = (int(x) for x in parts[1].split())
    return w, h, parts[3]


def downscale_against(native: Path, shot: Path, scale: int, native_filter: bool = False):
    """Box-downsample the N x screenshot and compare it with the same frame's
    1x canvas (the builder's own input), cropped like the presented picture."""
    w, h, pixels = read_ppm(native)
    cw, ch, cc, cpix, _ = png_pixels(shot)
    if cw != w * scale or ch % scale:
        return None
    rows = ch // scale
    top = 8 if rows == 200 else (h - rows) // 2
    reference = pixels[top * w * 3:(top + rows) * w * 3]
    if native_filter:
        # Linear On intentionally filters native RGB before N x composition.
        # Compare with the same linear sampling of the native reference, not
        # with the unfiltered Off pixels. Road geometry has its own audit.
        from PIL import Image
        image = Image.frombytes('RGB', (w, rows), reference)
        reference = image.resize((cw, ch), Image.Resampling.BILINEAR).resize(
            (w, rows), Image.Resampling.BOX).tobytes()
    return compare_downscaled(reference, downsample(cpix, cw, ch, cc, scale))


def actor_regions(native, shot, scale, info, native_filter=False):
    """Same-frame RGB comparison including actor silhouette edges. Two native
    pixels of padding include subpixel shifts and differing authored short
    axes. Boxes include occlusion/background, not guessed colour ownership."""
    import math
    import numpy as np
    from PIL import Image
    ref = Image.open(native).convert('RGB')
    candidate = Image.open(shot).convert('RGB')
    top = 8 if candidate.height // scale == 200 else 0
    ref = ref.crop((0, top, ref.width, top + candidate.height // scale))
    if native_filter:
        ref = ref.resize(candidate.size, Image.Resampling.BILINEAR).resize(ref.size, Image.Resampling.BOX)
    candidate = candidate.resize(ref.size, Image.Resampling.BOX)
    diff = np.abs(np.asarray(ref, dtype=np.int16) - np.asarray(candidate, dtype=np.int16)).max(axis=2)
    mask = np.zeros(diff.shape, dtype=bool)
    regions = []
    for a in info['actors']:
        if not a['promoted'] or not a['pixels']: continue
        x0, y0, x1, y1 = a['box']
        # Continuous projection deliberately changes the silhouette. Include
        # BOTH the removed native extent and the new extent in changed-region
        # accounting, so a smaller projected actor cannot hide removed pixels
        # in the unchanged-background metric. guest_box is in native pixels.
        if 'guest_box' in a:
            gx0, gy0, gx1, gy1 = a['guest_box']
            origin = a['draw_origin']
            x0, y0 = min(x0, (gx0+origin)*scale), min(y0, gy0*scale)
            x1, y1 = max(x1, (gx1+origin)*scale), max(y1, gy1*scale)
        x0, x1 = max(0, math.floor(x0/scale)-2), min(ref.width, math.ceil(x1/scale)+2)
        y0 = max(0, math.floor(y0/scale)-top-2)
        y1 = min(ref.height, math.ceil(min(y1/scale, a['clip']))-top+2)
        if x1 <= x0 or y1 <= y0: continue
        mask[y0:y1, x0:x1] = True
        region = diff[y0:y1, x0:x1]
        distance = 'near' if a['size'] >= .5 else 'middle' if a['size'] >= .15 else 'far'
        # The smaller native bands contain only a few authored pixels: their
        # internal colours need not match a filtered detailed asset. Position,
        # size axis, palette, priority and SAT ownership have separate gates.
        # Task 39 changes projected silhouette area, even when model 0 is
        # already the native model (up to 24.6% extra area for the nearest
        # car). Its explicit near bound is 80; stepped S4 remains 64. Middle
        # and far stay 80/96, and unchanged pixels retain the S3 limits.
        continuous = bool(a.get('continuous_size'))
        tolerance = dict(near=80 if continuous else 64, middle=80, far=96)[distance]
        regions.append(dict(kind=a['kind'], guest_model=a['guest_model'], model=a['model'],
                            distance=distance, box=[x0,y0,x1,y1],
                            mean_abs_diff=round(float(region.mean()), 4), tolerance=tolerance))
    # Occluding actors must be compared together. A tiny far sign's box can
    # lie inside a nearby car; testing that patch alone would attribute the
    # car's intentional new detail to the hidden sign's silhouette.
    groups = []
    for region in regions:
        box = region['box'][:]
        members = [region]
        changed = True
        while changed:
            changed = False
            for group in groups[:]:
                a,b,c,d = group['box']
                if box[0] < c and box[2] > a and box[1] < d and box[3] > b:
                    box = [min(box[0],a),min(box[1],b),max(box[2],c),max(box[3],d)]
                    members += group['members']
                    groups.remove(group)
                    changed = True
        groups.append(dict(box=box,members=members))
    for group in groups:
        x0,y0,x1,y1 = group['box']
        group['mean_abs_diff'] = round(float(diff[y0:y1,x0:x1].mean()),4)
        group['tolerance'] = min(r['tolerance'] for r in group['members'])
    outside = diff[~mask]
    return dict(outside_mean_abs_diff=round(float(outside.mean()), 4) if outside.size else 0,
                outside_big_diff_ratio=round(float((outside>64).mean()), 6) if outside.size else 0,
                actor_box_pixels=int(mask.sum()), regions=regions, silhouette_groups=groups)


def actor_region_failures(result, mean=2.5, big=.02):
    failures = []
    if result['outside_mean_abs_diff'] > mean or result['outside_big_diff_ratio'] > big:
        failures.append(f"outside actor boxes: {result}")
    for r in result['silhouette_groups']:
        if r['mean_abs_diff'] > r['tolerance']: failures.append(f"actor silhouette/detail group: {r}")
    return failures


def check_sprite_pairs(args):
    """Recheck captured pairs without rerunning the guest. Always retain the
    global S3 metric, while S4's bounded box tolerances handle changed assets."""
    root = args.capture.resolve()
    pairs, failures = [], []
    for f in sorted(root.glob('frame-*-actors.json')):
        stem = f.name.replace('-actors.json', '')
        native, shot = root / (stem+'-1x.ppm'), root / (stem+'.png')
        if not native.exists(): continue
        info = json.loads(f.read_text())
        result = actor_regions(native, shot, args.scale, info, bool(info.get("native_filter")))
        pairs.append(dict(frame=stem, **result))
        failures.extend(f'{stem}: {e}' for e in actor_region_failures(result))
    if not pairs: failures.append('no actor/native image pairs')
    result = dict(check='sprite-pairs', pairs=pairs, failures=failures, ok=not failures)
    (root/'sprite-pairs-summary.json').write_text(json.dumps(result, indent=1))
    brief = dict(ok=not failures, failures=failures, pairs=len(pairs),
                 max_outside_mean=max((p['outside_mean_abs_diff'] for p in pairs),default=0),
                 max_outside_big_ratio=max((p['outside_big_diff_ratio'] for p in pairs),default=0),
                 max_actor_box_mean=max((r['mean_abs_diff'] for p in pairs for r in p['regions']),default=0),
                 max_silhouette_group_mean=max((r['mean_abs_diff'] for p in pairs for r in p['silhouette_groups']),default=0))
    print(json.dumps(brief,indent=1))
    return int(bool(failures))


def actor_table_sample(table, info, rom, failures, strict=True):
    """Check captured guest pieces independently of the painter's anchors,
    and the chosen car frame against the raw ROM remap, not a second copy of
    the C selection routine. Counts are per distinct displayed scene."""
    import math
    if info.get('actor_dropped', 0): failures.append(f"actor capture overflow: {info['actor_dropped']}")
    table['rows_checked'] = info['actor_rows']
    table['row_mismatches'] = info['actor_row_mismatches']
    for a in info['actors']:
        table['fallbacks'] += bool(a['fallback'])
        if not a['promoted']:
            table['native'] += 1
            continue
        key = f"{a['kind']:02X}"
        kind = table['kinds'].setdefault(key, dict(actors=0, models={}, fallbacks=0, visible=0))
        kind['actors'] += 1
        model = f"{a['guest_model']}->{a['model']}"
        kind['models'][model] = kind['models'].get(model, 0) + 1
        kind['fallbacks'] += bool(a['fallback'])
        kind['visible'] += bool(a['pixels'])
        table['actors'] += 1
        table['native_blocked'] += a['native_blocked']
        table['pole_blocked'] += a['pole_blocked']
        table['pole_overpaint'] += a['pole_overpaint']
        floor_error = max(abs(math.floor(a['anchor'][i])-a['guest'][i]) for i in (0, 1))
        table['max_floor_error'] = max(table['max_floor_error'], floor_error)
        expected = [(a['anchor'][0] + a['draw_origin'])*a['draw_scale'], a['anchor'][1]*a['draw_scale']]
        error = max(abs(a['drawn_anchor'][i]-expected[i]) for i in (0, 1))
        table['max_drawn_anchor_error'] = max(table['max_drawn_anchor_error'], error)
        table['position_mismatches'] += a['position_mismatches']
        table['palette_mismatches'] += a['palette_mask'] != a['guest_palette_mask']
        table['priority_mismatches'] += a['priority_mask'] != a['guest_priority_mask']
        table['inside_pieces'] += a['inside']
        table['sat_matched'] += a['matched']
        if strict and (floor_error or a['position_mismatches']):
            if len(failures)<20: failures.append(f"actor guest-position mismatch: {a}")
        if error >= 1 or a['palette_mask'] != a['guest_palette_mask'] or a['priority_mask'] != a['guest_priority_mask']:
            if len(failures)<20: failures.append(f"actor anchor/palette/priority mismatch: {a}")
        if a['record'] >= 0xFF8E94 and not a['fallback']:
            # A model used in row 0 keeps its angle; later rows choose the
            # mild level-0 frame of the left/centre/right run nearest column 4.
            rows = [list(rom[0x57C8+n*9:0x57C8+(n+1)*9]) for n in range(24)]
            row = next((r for r in rows if a['guest_model'] in r), None)
            if row is None: failures.append(f"car model outside ROM table: {a}")
            else:
                cols = [i for i,m in enumerate(row) if m == a['guest_model']]
                col = min(cols, key=lambda i: abs(i-4))
                want = a['guest_model'] if row is rows[0] else rows[0][4 if len(set(row)) == 1 else col]
                if a['model'] != want: failures.append(f"wrong car angle: {a}; expected {want}")
    if info['actor_row_mismatches'] and len(failures)<20:
        failures.append(f"native row reconstruction: {info['actor_row_mismatches']} mismatches")


def check_drive(args):
    """S3 audit on a driven race: password into a track, drive it with the
    closed-loop controller at a render scale, with the N x road records and
    the margin audit on, taking a picture every --shot-every frames. The trace
    carries curvature and slope so curve/hill pictures can be picked."""
    if args.actors and args.no_audit: raise ValueError('--actors cannot be combined with --no-audit')
    info = TRACKS[args.track]
    tag = (f'{args.track}-scale{args.scale}' + ('-60' if args.race60 else '') +
           ('-cost' if args.no_audit else ''))
    out = args.out / 'drive' / tag
    audit = out / 'audit'
    if audit.exists():
        for old in audit.glob('*.nxroad'):
            old.unlink()
    audit.mkdir(parents=True, exist_ok=True)
    env = {'TG2_HIGHRES_SCALE': str(args.scale),
           'TG2_RACE_60FPS': '1' if args.race60 else '0',
           'TG2_HIGHRES_TIMING': '1'}
    if args.actors: env['TG2_ACTOR_AUDIT'] = '1'
    if args.no_audit:
        env['GENESIS_FRAME_STATS'] = str(out / 'frame-stats.csv')
    if not args.no_audit:
        env['TG2_ROAD_AUDIT_DIR'] = str(audit)
        env['TG2_MARGIN_AUDIT'] = str(out / 'margins.csv')
    extra_args = [] if args.no_audit else ['--turbo']
    if args.uncapped:
        if not args.no_audit or not args.cost_route:
            raise ValueError('--uncapped requires --no-audit --cost-route')
        extra_args = ['--measure-runtime', str(3000 + args.frames + 60), '--runtime-uncapped']
    if args.cost_route:
        if not args.no_audit or not args.uncapped:
            raise ValueError('--cost-route requires --no-audit --uncapped')
        if args.track != 'auckland':
            raise ValueError('--cost-route uses the committed Auckland baseline route')
        script = route_script(ROOT / 'game/baseline-route.json', out / 'cost.input',
                              3000 + args.frames + 120)
        extra_args += ['--input-script', str(script)]
    r = Runner(port=args.port, out=out, exe=args.exe, rom=args.rom,
               widescreen=args.mode, max_frames=0 if args.uncapped else 400000,
               env_extra=env, extra_args=extra_args, timeout=120)
    item = {'tag': tag, 'track': args.track, 'scale': args.scale, 'mode': args.mode,
            'race60': bool(args.race60), 'frames': args.frames}
    trace, shots, failures = [], [], []
    actor_table = dict(actors=0, native=0, fallbacks=0, kinds={}, max_floor_error=0,
                       max_drawn_anchor_error=0, position_mismatches=0, palette_mismatches=0,
                       priority_mismatches=0, inside_pieces=0, sat_matched=0,
                       rows_checked=0, row_mismatches=0, native_blocked=0, pole_blocked=0, pole_overpaint=0)
    actor_serial = None
    actor_rom = args.rom.read_bytes() if args.actors else None
    r.start()
    try:
        if args.output_size:
            width, height = (int(v) for v in args.output_size.split('x'))
            r.command('video_configure', mode=args.mode, window_width=width, window_height=height)
        if args.cost_route:
            r.wait_frame(2980)
            state = r.state_and_frame()
            start = 3000
        else:
            if args.load_state:
                r.command('load_state', path=str(args.load_state.resolve()))
                r.wait_frame(r.frame()+30)  # republish immutable scene history after reset
                state = r.state_and_frame()
            else:
                state = enter_race_password(r, args.port, out, info['country'], info['stage'])
            if args.save_state: r.command('save_state', path=str(args.save_state.resolve()))
            start = r.frame()
        item['race_start_frame'] = state.frame
        item['native_filter'] = bool(r.command('tg2_highres')['native_filter'])
        if args.cost_route:
            r.wait_frame(start)
        builder_start, builder_start_frame = r.command_many([('tg2_highres', {}), ('frame_info', {})])
        item['builder_start_frame'] = builder_start_frame['current_frame']
        pad, previous, last_shot = 0, None, 0
        while r.frame() - start < args.frames:
            if args.cost_route:
                import time
                time.sleep(.02)
                continue
            due = not args.no_audit and args.scale > 1 and last_shot and r.frame() - last_shot >= args.shot_every
            if due:
                # The pictures this step builds also leave their 1x canvas.
                r.command('tg2_highres', dump=str(out / 'native.ppm'))
            if args.actors:
                st, samples = r.step_commands(pad, [('tg2_highres', {})])
                actor_info = samples[0]
            else:
                st = r.step(pad)
            lat = st.lat_units
            d = 0.0 if previous is None else lat - previous
            u = -1.0 * lat - 4.0 * d
            pad = 0x10 | (0x08 if u > 9.0 else 0x04 if u < -9.0 else 0)
            previous = lat
            trace.append([st.frame, st.speed, round(lat, 2), st.curv, st.slope, st.lap])
            if args.actors:
                if actor_info['serial'] != actor_serial:
                    actor_serial = actor_info['serial']
                    actor_table_sample(actor_table, actor_info, actor_rom, failures)
            if not args.no_audit and (due or not last_shot):
                last_shot = st.frame
                # One batch is served in one per-frame poll, so the screenshot
                # and the end of the 1x dump see the same completed picture.
                path = out / f'frame-{st.frame}.png'
                batch = [('screenshot', dict(path=str(path)))]
                if args.actors: batch.append(('tg2_highres', {}))
                if due:
                    batch.append(('tg2_highres', dict(dump='')))
                batch_result = r.command_many(batch)
                if args.actors: (out / f'frame-{st.frame}-actors.json').write_text(json.dumps(batch_result[1], indent=1))
                shot = {'frame': st.frame, 'path': str(path), 'speed': st.speed,
                        'curv': st.curv, 'slope': st.slope}
                native = out / 'native.ppm'
                if due and native.exists():
                    reference = out / f'frame-{st.frame}-1x.ppm'
                    native.replace(reference)
                    shot['native'] = str(reference)
                    shot['downscale'] = downscale_against(reference, Path(path), args.scale, item['native_filter'])
                    if args.actors:
                        shot['actor_regions'] = actor_regions(reference, Path(path), args.scale, batch_result[1], item['native_filter'])
                        failures.extend(f"{tag}: frame {st.frame} {e}" for e in actor_region_failures(shot['actor_regions'], args.max_mean_diff, args.max_big_ratio))
                shots.append(shot)
        builder_end, builder_end_frame = r.command_many([('tg2_highres', {}), ('frame_info', {})])
        item['highres_filter'] = builder_end
        if args.actors and 'all_actors' in builder_end:
            all_actors = builder_end['all_actors']
            item['sprite_table_all'] = all_actors
            keys = ['palette_mismatches', 'priority_mismatches', 'position_mismatches', 'max_floor_error']
            if any(all_actors[k] for k in keys) or all_actors['max_drawn_anchor_error'] >= 1:
                failures.append(f'all-frame actor checks: {all_actors}')
        item['builder_end_frame'] = builder_end_frame['current_frame']
        built = builder_end['build_frames'] - builder_start['build_frames']
        item['builder_interval'] = dict(frames=built,
            wall_us_per_frame=(builder_end['build_us'] - builder_start['build_us']) / built if built else None)
        item['sample_frames'] = [start, start + args.frames]
        item['uncapped'] = bool(args.uncapped)
        item['cost_route'] = bool(args.cost_route)
        video = r.command('tg2_video')
        item['video'] = {k: video.get(k) for k in
                         ('highres_scale', 'highres_capture_us', 'highres_build_us',
                          'highres_build_frames', 'crop_frames')}
        if args.no_audit:
            perf = r.command('frame_performance')
            # Keep the retrospective phase ring so the builder-only timing is
            # not mistaken for the cost of presenting the whole frame.
            item['frame_performance'] = perf
        if video.get('highres_build_frames'):
            item['build_us_per_frame'] = round(
                video['highres_build_us'] / video['highres_build_frames'], 1)
        r.set_input(0)
        if args.cost_route:
            wait_exit(r)  # finite runtime measurement must finish its requested frame count
    finally:
        item['exit'] = r.stop()
    if args.no_audit:
        import csv
        import statistics
        with (out / 'frame-stats.csv').open() as stream:
            rows = [row for row in csv.DictReader(stream) if start <= int(row['frame']) < start + args.frames]
        cpu_work = sorted(max(0, sum(int(v) for k, v in row.items()
                                    if k.startswith('cpu') and k != 'cpu_wait_us') -
                              int(row['cpu_wait_us'])) for row in rows)
        if not cpu_work:
            failures.append(f'{tag}: no realtime CPU frame costs recorded')
        else:
            item['cpu_work_us'] = dict(frames=len(cpu_work),
                                      p50=statistics.median(cpu_work),
                                      p95=cpu_work[int(.95 * (len(cpu_work) - 1))],
                                      mean=round(statistics.mean(cpu_work), 1))
            # Phase 7 covers game composition plus the presented-window crop.
            # Unlike the wall-time builder counter, these CPU samples use the
            # exact same fixed frame interval as the whole-frame cost.
            layout = sorted(int(row['cpu7_layout']) for row in rows)
            item['layout_cpu_us'] = dict(frames=len(layout),
                p50=statistics.median(layout), p95=layout[int(.95 * (len(layout) - 1))],
                mean=round(statistics.mean(layout), 1))
            item['pacing'] = dict(wait_max_us=max(int(row['wait_us']) for row in rows),
                wait_cpu_max_us=max(int(row['cpu_wait_us']) for row in rows),
                present_p50_us=statistics.median(int(row['present_us']) for row in rows))
    (out / 'trace.json').write_text(json.dumps(trace) + '\n')
    if args.actors:
        item['sprite_table'] = actor_table
        if not actor_table['actors'] or not actor_table['rows_checked']: failures.append('no actor/row samples')
    item.update({'shots': shots, 'manifests': empty_manifests(out),
                 'steps': len(trace),
                 'moving_steps': sum(1 for t in trace if t[1] > 500)})
    compared = [s['downscale'] for s in shots if s.get('downscale')]
    if compared:
        item['downscale'] = {
            'pictures': len(compared),
            'max_mean_abs_diff': max(c['mean_abs_diff'] for c in compared),
            'max_big_diff_ratio': max(c['big_diff_ratio'] for c in compared)}
        for shot in shots:
            c = shot.get('downscale')
            if not args.actors and c and (c['mean_abs_diff'] > args.max_mean_diff or
                      c['big_diff_ratio'] > args.max_big_ratio):
                failures.append(f"{tag}: frame {shot['frame']} downscale {c}")
    elif args.scale > 1 and shots[1:]:
        failures.append(f'{tag}: no 1x/N x picture pair was compared')
    for name, count in item['manifests'].items():
        if count != 0:
            failures.append(f"{tag}: manifest {name} has {count} entries")
    if item['exit'] != 0:
        failures.append(f"{tag}: exit {item['exit']}")
    if args.scale > 1 and not args.no_audit:
        report = out / 'road-artifacts-nx.json'
        proc = subprocess.run([sys.executable, str(ROOT / 'tools' / 'check_road_artifacts.py'),
                               str(out), '--nx', '--out', str(report),
                               '--min-frames', str(args.min_frames)],
                              capture_output=True, text=True)
        item['road_artifacts'] = json.loads(report.read_text()) if report.exists() else None
        item['road_artifacts_scope'] = 'analytic underlay before native-art filtering' if item.get('native_filter') else 'completed nearest picture'
        if proc.returncode != 0:
            failures.append(f"{tag}: road artefacts failed")
        if not (item['road_artifacts'] or {}).get('stripe_centres_checked'):
            failures.append(f"{tag}: no visible stripe centres were measured")
    if args.mode != 'off' and not args.no_audit:
        proc = subprocess.run([sys.executable, str(ROOT / 'tools' / 'check_margin_artifacts.py'),
                               str(out / 'margins.csv')], capture_output=True, text=True)
        item['margins'] = {'exit': proc.returncode, 'stdout': proc.stdout[-1500:]}
        if proc.returncode != 0:
            failures.append(f"{tag}: margin audit failed")
    if not args.keep_audit:
        # The records are large (AGENTS.md: delete once the numbers are out).
        for old in audit.glob('*.nxroad'):
            old.unlink()
        if (out / 'margins.csv').exists():
            (out / 'margins.csv').unlink()
    summary = {'check': 'drive', **item, 'failures': failures, 'ok': not failures}
    (out / 'drive-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    brief = {k: v for k, v in summary.items() if k not in ('shots',)}
    print(json.dumps(brief, indent=1))
    return 0 if not failures else 1


def check_lod(args):
    """S4 evidence: drive one track at 1x with the read-only actor log on
    (TG2_ACTOR_LOG, game/tg2_actors.c). The stream stays under the ignored
    build directory; tools/analyze_actors.py summarises it."""
    info = TRACKS[args.track]
    out = args.out / 'lod' / args.track
    out.mkdir(parents=True, exist_ok=True)
    log = out / 'actors.csv'
    r = Runner(port=args.port, out=out, exe=args.exe, rom=args.rom,
               widescreen=args.mode, max_frames=400000,
               env_extra={'TG2_ACTOR_LOG': str(log), 'TG2_HIGHRES_SCALE': '1'},
               extra_args=['--turbo'], timeout=120)
    item = {'track': args.track, 'frames': args.frames, 'log': str(log)}
    r.start()
    try:
        state = enter_race_password(r, args.port, out, info['country'], info['stage'])
        start = r.frame()
        item['race_start_frame'] = state.frame
        pad, previous, snapped = 0, None, False
        while r.frame() - start < args.frames:
            st = r.step(pad)
            lat = st.lat_units
            d = 0.0 if previous is None else lat - previous
            u = -1.0 * lat - 4.0 * d
            pad = 0x10 | (0x08 if u > 9.0 else 0x04 if u < -9.0 else 0)
            previous = lat
            if not snapped and st.frame - start >= args.snapshot_at:
                # One art snapshot for tools/actor_sheet.py (ignored build dir).
                snapped = True
                (out / 'snap.vram').write_bytes(b''.join(
                    r.vram(a, 0x1000) for a in range(0, 0x10000, 0x1000)))
                (out / 'snap.cram').write_bytes(bytes.fromhex(r.command('read_cram')['hex']))
                r.dump_ram_file(out / 'snap.ram')
                r.screenshot(out / 'snap.png')
                item['snapshot_frame'] = st.frame
        item['end_frame'] = r.frame()
    finally:
        item['exit'] = r.stop()
    item['manifests'] = empty_manifests(out)
    item['log_bytes'] = log.stat().st_size if log.exists() else 0
    item['ok'] = (item['exit'] == 0 and item['log_bytes'] > 0 and
                  all(v == 0 for v in item['manifests'].values()))
    (out / 'lod-summary.json').write_text(json.dumps(item, indent=1))
    print(json.dumps(item, indent=1))
    return 0 if item['ok'] else 1


def check_nx(args):
    """S3 audit: run the route with the N x road records and the margin audit,
    then check both."""
    sys.path.insert(0, str(ROOT / 'tools'))
    out_root = args.out / 'nx'
    out_root.mkdir(parents=True, exist_ok=True)
    results, failures = [], []
    for scale in [int(x) for x in args.scales.split(',') if x.strip()]:
        tag = f'{args.mode.replace(":", "-")}-scale{scale}'
        item = run_route_scale(args, args.mode, scale, tag, out_root, (),
                               audit=True, margin=args.margin)
        results.append(item)
        print(tag, 'exit', item['exit'], 'audit files',
              len(list((Path(item['out']) / 'audit').glob('*.nxroad'))))
        for name, count in item['manifests'].items():
            if count != 0:
                failures.append(f"{tag}: manifest {name} has {count} entries")
        if item['exit'] != 0:
            failures.append(f"{tag}: exit {item['exit']}")
    for item in results:
        out = Path(item['out'])
        report = out / 'road-artifacts-nx.json'
        cmd = [sys.executable, str(ROOT / 'tools' / 'check_road_artifacts.py'),
               str(out), '--nx', '--out', str(report),
               '--min-frames', str(args.min_frames)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        item['road_artifacts'] = json.loads(report.read_text()) if report.exists() else None
        print(item['tag'], 'road artifacts exit', proc.returncode)
        if proc.returncode != 0:
            failures.append(f"{item['tag']}: road artefacts failed: {proc.stdout[-400:]}")
        if args.margin:
            audit_csv = out / 'margins.csv'
            cmd = [sys.executable, str(ROOT / 'tools' / 'check_margin_artifacts.py'),
                   str(audit_csv)]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            item['margins'] = {'exit': proc.returncode, 'stdout': proc.stdout[-2000:]}
            print(item['tag'], 'margin audit exit', proc.returncode)
            if proc.returncode != 0:
                failures.append(f"{item['tag']}: margin audit failed: {proc.stdout[-400:]}")
    summary = {'check': 'nx', 'mode': args.mode, 'end_frame': args.end_frame,
               'runs': results, 'failures': failures, 'ok': not failures}
    (out_root / 'nx-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'ok': not failures, 'failures': failures}, indent=1))
    return 0 if not failures else 1


def check_launcher(args):
    """Exercise the real macOS launcher in a hidden window, then restore config."""
    import os
    if sys.platform != 'darwin':
        raise RuntimeError('launcher qualification currently uses the macOS cocoa driver')
    out = args.out / 'launcher'
    out.mkdir(parents=True, exist_ok=True)
    settings = args.exe.parent / 'settings.ini'
    backup = settings.read_bytes() if settings.exists() else None
    results, failures = [], []
    try:
        settings_write(settings, 'internal_scale', 1)
        for value in (2, 3, 4, 1):
            shot = out / f'selected-{value}.png'
            # Fixed logical size, independent of Retina framebuffer density.
            script = (f'size:1100x818;view:settings;wait:8;click:450,237;wait:4;'
                      f'click:450,{288 + 26 * (value - 1)};wait:4;shot:{shot};quit')
            env = dict(os.environ, SDL_VIDEODRIVER='cocoa', SDL_AUDIODRIVER='dummy',
                       LNG_TEST_HIDDEN='1', LNG_SCRIPT=script)
            for key in ('APPIMAGE', 'TG2_HIGHRES_SCALE', 'GENESIS_NO_LAUNCHER'):
                env.pop(key, None)
            with (out / f'selected-{value}.log').open('w') as log:
                proc = subprocess.run([str(args.exe), str(args.rom), '--launcher'],
                                      cwd=args.exe.parent, env=env, stdout=log,
                                      stderr=subprocess.STDOUT, timeout=25)
            actual = settings_read(settings, 'internal_scale')
            results.append(dict(selected=value, persisted=actual, exit=proc.returncode,
                                screenshot=str(shot), script=script))
            if proc.returncode != 0 or actual != value or not shot.exists():
                failures.append(f'launcher {value}: exit {proc.returncode}, persisted {actual}')
    finally:
        if backup is None:
            settings.unlink(missing_ok=True)
        else:
            settings.write_bytes(backup)
    summary = dict(check='launcher', runs=results, failures=failures, ok=not failures,
                   driver='cocoa', hidden=True)
    (out / 'launcher-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    return int(bool(failures))


def check_cap(args):
    """An extreme adaptive output still has whole N-pixel columns at 3x."""
    out = args.out / 'cap'
    r = Runner(port=args.port, out=out, exe=args.exe, rom=args.rom,
               widescreen='fit', env_extra={'TG2_HIGHRES_SCALE': '3',
                                           'TG2_RACE_60FPS': '0'},
               extra_args=['--turbo'])
    failures = []
    try:
        r.start()
        enter_race(r, args.port, out)
        r.command('video_configure', mode='fit', window_width=8192, window_height=224)
        r.wait_frame(r.frame() + 30)
        path = r.screenshot('capped-3x.png')
        w, h, *_ = png_pixels(Path(path))
        sizes = {'capped': [w, h]}
        if w != 4095 or h not in (600, 672):
            failures.append(f'capped 3x picture is {w}x{h}, expected 4095x600/672')
        off_downscale = None
        for mode, expected in [('off', 768), ('16:9', 1068)]:
            r.command('video_configure', mode=mode)
            r.wait_frame(r.frame() + 20)
            if mode == 'off':
                native = out / 'off-1x.ppm'
                r.command('tg2_highres', dump=str(native))
                r.wait_frame(r.frame() + 3)
                shot = out / 'off-3x.png'
                r.command_many([('screenshot', dict(path=str(shot))),
                                ('tg2_highres', dict(dump=''))])
                off_downscale = downscale_against(native, shot, 3)
                if not off_downscale or off_downscale['mean_abs_diff'] > 2.5 or off_downscale['big_diff_ratio'] > .02:
                    failures.append(f'Off 3x downscale mismatch: {off_downscale}')
            else:
                shot = r.screenshot(mode.replace(':', '-') + '-3x.png')
            mw, mh, *_ = png_pixels(Path(shot))
            sizes[mode] = [mw, mh]
            if (mw, mh) != (expected, 600):
                failures.append(f'{mode} 3x picture is {mw}x{mh}, expected {expected}x600')
    finally:
        code = r.stop()
    counts = empty_manifests(out)
    if code != 0 or any(n != 0 for n in counts.values()):
        failures.append(f'exit {code}, manifests {counts}')
    summary = dict(check='cap', sizes=sizes, off_downscale=off_downscale,
                   exit=code, manifests=counts,
                   failures=failures, ok=not failures)
    (out / 'cap-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    return int(bool(failures))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='check', required=True)
    for name in ('g1', 'capture', 's3', 'nx', 'drive', 'captures', 'option', 'route', 'split', 'cap', 'launcher', 'sprite-pairs'):
        s = sub.add_parser(name)
        s.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
        s.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
        s.add_argument('--out', type=Path, default=ROOT / 'build/highres-check')
        s.add_argument('--port', type=int, default=4494)
    s = sub.choices['sprite-pairs']
    s.add_argument('--capture', type=Path, required=True)
    s.add_argument('--scale', type=int, required=True)
    s = sub.choices['split']
    s.add_argument('--mode', default='16:9', choices=['16:9', '32:9'])
    s.add_argument('--scale', type=int, default=4, choices=[2,3,4])
    s = sub.choices['g1']
    s.add_argument('--frames', type=int, default=360)
    s = sub.choices['capture']
    s.add_argument('--samples', type=int, default=3)
    s.add_argument('--spacing', type=int, default=40)
    s = sub.choices['route']
    s.add_argument('--end-frame', type=int, default=5600)
    s.add_argument('--route', type=Path, default=ROOT / 'game/baseline-route.json')
    s = sub.choices['s3']
    s.add_argument('--route', type=Path, default=ROOT / 'game/baseline-route.json')
    s.add_argument('--mode', default='16:9')
    s.add_argument('--scales', default='1,2,3,4')
    s.add_argument('--shots', type=int, nargs='+', default=list(SHOTS))
    s.add_argument('--end-frame', type=int, default=4700)
    s.add_argument('--max-mean-diff', type=float, default=2.5)
    s.add_argument('--max-big-ratio', type=float, default=0.02)
    s = sub.choices['captures']
    s.add_argument('--mode', default='16:9')
    s.add_argument('--offsets', type=int, nargs='+', default=[500, 650, 800])
    s.add_argument('--plan', default='auckland:2,3,4;bavaria-rain:2;canada:2')
    s = sub.choices['nx']
    s.add_argument('--route', type=Path, default=ROOT / 'game/baseline-route.json')
    s.add_argument('--mode', default='16:9')
    s.add_argument('--scales', default='2')
    s.add_argument('--end-frame', type=int, default=5600)
    s.add_argument('--min-frames', type=int, default=3000)
    s.add_argument('--margin', action='store_true', default=True)
    s = sub.choices['drive']
    s.add_argument('--track', default='auckland', choices=sorted(TRACKS))
    s.add_argument('--scale', type=int, default=2)
    s.add_argument('--mode', default='16:9')
    s.add_argument('--frames', type=int, default=4200)
    s.add_argument('--shot-every', type=int, default=120)
    s.add_argument('--min-frames', type=int, default=3000)
    s.add_argument('--race60', action='store_true')
    s.add_argument('--actors', action='store_true', help='S4: independent sprite-position/variant and native-row coverage table')
    s.add_argument('--load-state', type=Path, help='ignored local race checkpoint; republish 30 frames before sampling')
    s.add_argument('--save-state', type=Path, help='save an ignored local race checkpoint before driving')
    s.add_argument('--no-audit', action='store_true', help='CPU timing with no road/margin audits, screenshots or native dumps')
    s.add_argument('--uncapped', action='store_true', help='Cost mode: full rendering/audio work without host pacing')
    s.add_argument('--cost-route', action='store_true', help='Cost mode: committed baseline input route; sample [3000,3000+frames)')
    s.add_argument('--output-size', help='Directed SDL drawable dimensions, e.g. 1280x800')
    s.add_argument('--keep-audit', action='store_true')
    s.add_argument('--max-mean-diff', type=float, default=2.5)
    s.add_argument('--max-big-ratio', type=float, default=0.02)
    s = sub.add_parser('lod')
    s.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    s.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    s.add_argument('--out', type=Path, default=ROOT / 'build/highres-check')
    s.add_argument('--port', type=int, default=4494)
    s.add_argument('--track', default='auckland', choices=sorted(TRACKS))
    s.add_argument('--mode', default='16:9')
    s.add_argument('--frames', type=int, default=3600)
    s.add_argument('--snapshot-at', type=int, default=1500)
    args = p.parse_args()
    args.exe = args.exe.resolve()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    for name in ('exe', 'rom'):
        if not getattr(args, name).exists():
            p.error(f'--{name} not found: {getattr(args, name)}')
    return {'g1': check_g1, 'capture': check_capture, 's3': check_s3,
            'nx': check_nx, 'drive': check_drive, 'captures': check_captures, 'option': check_option,
            'route': check_route, 'split': check_split, 'cap': check_cap,
            'launcher': check_launcher, 'lod': check_lod, 'sprite-pairs': check_sprite_pairs}[args.check](args)


if __name__ == '__main__':
    sys.exit(main())
