#!/usr/bin/env python3
"""High-resolution rendering checks: S1 (row-state capture) and S2 (engine
seam for a taller presented picture), per docs/HIGHRES.md §8.

Subcommands:

  g1        Canonical framebuffer hashes with the render scale at 1 and above
            (the S1 builder copies native rows, so every hash must match), in
            both `--widescreen off` and `16:9`, and with the temporary S2 test
            provider enabled on non-race frames. Every run must also leave the
            four runtime manifests empty.

  capture   Drive a race and sample the compact per-row capture three times.
            Compares every captured row with the live row words the renderer
            used for the same picture, and reports the capture cost.

  s2        Drive a race with the temporary synthetic test provider and check
            that the taller picture is presented correctly (dimensions and
            pattern content) in `off` and `16:9`, that menus keep the stock
            canvas and height, and that the 1x picture is unchanged. Add
            `--windowed` for the one real-window check.

  route     Replay the committed baseline route (frame-exact input script) at
            scale 1 and at scale 2 with the builder stub, in `off` and `16:9`,
            and require the same framebuffer hash on every sampled frame,
            race frames included. This is the byte-identity gate for S1/S2.

  split     Run the committed two-pad split-screen script at scale 2 with the
            test provider off and on: the 2P flag must be observed, no picture
            may grow, and every framebuffer hash must match. 2P is excluded
            from the N x path by design.

Only read-only TCP queries and controller input are used. All captures stay
under the ignored build/ directory. Nothing here writes guest state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
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
        ('off', 2, True, False, 'off-scale2-testprovider-menus'),
        ('off', 1, False, True, 'off-race60-scale1'),
        ('off', 2, False, True, 'off-race60-scale2-stub'),
    ]
    results = [run_hashes(args, mode, scale, provider, tag, race60)
               for mode, scale, provider, race60, tag in plan]
    failures = []
    for item in results:
        for name, count in item['manifests'].items():
            if count:
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
            if count:
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
    frame-exact, so the framebuffer series with and without the test provider
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
                   widescreen='16:9', max_frames=script.frame + 300,
                   env_extra={'TG2_HIGHRES_SCALE': '2',
                              'TG2_HIGHRES_TEST_PROVIDER': '1' if provider else '0'},
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
    heights = {h for (_, h, _) in stock['frames'].values()}
    widths = {w for (w, _, _) in stock['frames'].values()}
    if heights - {224, 448}:
        failures.append(f'2P presented height changed: {sorted(heights)}')
    if any(w > 398 for w in widths):
        failures.append(f'2P presented width changed: {sorted(widths)}')
    common = sorted(set(stock['frames']) & set(test['frames']))
    differing = [f for f in common if stock['frames'][f] != test['frames'][f]]
    if not common:
        failures.append('no 2P framebuffer hashes captured')
    if differing:
        failures.append(f'test provider changed {len(differing)}/{len(common)} 2P frames')
    for item in results:
        for name, count in item['manifests'].items():
            if count:
                failures.append(f"{item['tag']}: manifest {name} has {count} entries")
    summary = {'check': 'split', 'runs': results, 'widths': sorted(widths),
               'heights': sorted(heights), 'compared_frames': len(common),
               'failures': failures, 'ok': not failures}
    (out_root / 'split-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'ok': not failures, 'failures': failures,
                      'widths': sorted(widths), 'heights': sorted(heights),
                      'compared': len(common)}, indent=1))
    return 0 if not failures else 1


def check_s2(args):
    plan = [
        ('off', 1, False, 'off-scale1'),
        ('off', 2, False, 'off-scale2-stub'),
        ('off', 2, True, 'off-scale2-test'),
        ('16:9', 1, False, '169-scale1'),
        ('16:9', 2, False, '169-scale2-stub'),
        ('16:9', 2, True, '169-scale2-test'),
    ]
    if args.only:
        wanted = set(args.only.split(','))
        plan = [p for p in plan if p[3] in wanted]
    results, failures = [], []
    for mode, scale, provider, tag in plan:
        out = args.out / tag
        out.mkdir(parents=True, exist_ok=True)
        extra = {'TG2_HIGHRES_SCALE': str(scale),
                 'TG2_HIGHRES_TEST_PROVIDER': '1' if provider else '0'}
        r = Runner(port=args.port, out=out, exe=args.exe, rom=args.rom,
                   widescreen=mode, max_frames=200000, env_extra=extra,
                   extra_args=['--turbo'],
                   video_driver='cocoa' if args.windowed else 'dummy')
        r.start()
        item = {'tag': tag, 'mode': mode, 'scale': scale, 'provider': provider}
        try:
            title = r.screenshot(f'{tag}-title.png')
            tw, th, _, _, title_digest = png_pixels(Path(title))
            item['title'] = [tw, th]
            item['title_digest'] = title_digest
            # No input after the race starts: the start picture is then a
            # function of the race state alone, not of when a TCP input
            # landed. Byte identity across scales is checked by `route`.
            state = enter_race(r, args.port, out)
            r.wait_frame(state.frame + 300)
            shot = r.screenshot(f'{tag}-race.png')
            w, h, channels, pixels, digest = png_pixels(Path(shot))
            item.update({'race': [w, h], 'pixel_digest': digest, 'shot': str(shot)})
            if provider:
                item['pattern'] = pattern_report(pixels, w, h, channels)
        finally:
            item['exit'] = r.stop()
        item['manifests'] = empty_manifests(out)
        item['hashes'] = hashes(out)
        results.append(item)
        print(tag, item.get('title'), item.get('race'), item.get('exit'))
    by_mode = {}
    for item in results:
        by_mode.setdefault(item['mode'], []).append(item)
        for name, count in item['manifests'].items():
            if count:
                failures.append(f"{item['tag']}: manifest {name} has {count} entries")
        if item['exit'] != 0:
            failures.append(f"{item['tag']}: exit {item['exit']}")
    for mode, items in by_mode.items():
        reference = next((i for i in items if i['scale'] == 1 and not i['provider']), None)
        stub = next((i for i in items if i['scale'] > 1 and not i['provider']), None)
        test = next((i for i in items if i['provider']), None)
        # Menus keep the stock picture and the stock canvas: the 16:9 boot
        # canvas is 398 wide, and it must not grow with the test provider.
        # Compared on the title screenshot, because absolute-frame hashes of
        # menus depend on when the password-screen taps landed.
        for item in items:
            if reference and item['title'] != reference['title']:
                failures.append(f"{item['tag']}: menu canvas {item['title']} != stock {reference['title']}")
            if reference and item.get('title_digest') != reference.get('title_digest'):
                failures.append(f"{item['tag']}: title picture differs from stock")
        if reference and reference['title'] != [320, 224] and mode == 'off':
            failures.append(f"{reference['tag']}: menu picture {reference['title']} is not native 320x224")
        if reference and stub:
            # Byte identity at scale > 1 with the builder stub is proven by the
            # deterministic route check; here only the presented size matters,
            # and the race picture must not have become the synthetic pattern.
            if stub['race'] != reference['race']:
                failures.append(f"{mode}: scale {stub['scale']} picture size {stub['race']} != {reference['race']}")
            expected = reference['race']
            if test:
                want_h = expected[1] * 2
                want_w = expected[0] * 2 if mode != 'off' else expected[0]
                if test['race'] != [want_w, want_h]:
                    failures.append(f"{mode}: test provider picture {test['race']} != {[want_w, want_h]}")
                if test['pixel_digest'] == reference['pixel_digest']:
                    failures.append(f"{mode}: test provider picture is identical to 1x")
                race_frames = [f for f in sorted(set(test['hashes']) & set(reference['hashes']))
                               if f >= 8300]
                if race_frames and all(test['hashes'][f] == reference['hashes'][f] for f in race_frames):
                    failures.append(f"{mode}: test provider never changed a race frame")
                pattern = test.get('pattern') or {}
                if pattern.get('left_edge') != (255, 0, 255) or pattern.get('right_edge') != (255, 0, 255):
                    failures.append(f"{mode}: test pattern edge markers missing {pattern.get('left_edge')}")
                if not pattern.get('ruler_rows'):
                    failures.append(f"{mode}: test pattern row rulers missing")
                if pattern.get('distinct_rows', 0) < pattern.get('sampled_rows', 1):
                    failures.append(f"{mode}: test pattern has repeated rows")
    summary = {'check': 's2', 'windowed': args.windowed, 'runs': results,
               'failures': failures, 'ok': not failures}
    (args.out / 's2-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'ok': not failures, 'failures': failures}, indent=1))
    return 0 if not failures else 1


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='check', required=True)
    for name in ('g1', 'capture', 's2', 'route', 'split'):
        s = sub.add_parser(name)
        s.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
        s.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
        s.add_argument('--out', type=Path, default=ROOT / 'build/highres-check')
        s.add_argument('--port', type=int, default=4494)
    s = sub.choices['g1']
    s.add_argument('--frames', type=int, default=360)
    s = sub.choices['capture']
    s.add_argument('--samples', type=int, default=3)
    s.add_argument('--spacing', type=int, default=40)
    s = sub.choices['route']
    s.add_argument('--end-frame', type=int, default=5600)
    s.add_argument('--route', type=Path, default=ROOT / 'game/baseline-route.json')
    s = sub.choices['s2']
    s.add_argument('--windowed', action='store_true',
                   help='one real-window run (cocoa driver) instead of the dummy driver')
    s.add_argument('--only', default='', help='comma list of run tags (see the plan)')
    args = p.parse_args()
    args.exe = args.exe.resolve()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    for name in ('exe', 'rom'):
        if not getattr(args, name).exists():
            p.error(f'--{name} not found: {getattr(args, name)}')
    return {'g1': check_g1, 'capture': check_capture, 's2': check_s2,
            'route': check_route, 'split': check_split}[args.check](args)


if __name__ == '__main__':
    sys.exit(main())
