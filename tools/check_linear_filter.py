#!/usr/bin/env python3
"""Compare exact-frame final SDL output for saved/live Linear Filter.

Use the release's pinned SDL2, not sdl2-compat. Run under the heavy lock, with
one runtime. macOS Metal uses a hidden Cocoa window. Requires Pillow/NumPy;
images, sampler JSON, settings, hashes and manifests stay under build/.
The tool restores the scratch build's settings.ini, even on an error.
"""
import argparse
import json
import hashlib
import time
from pathlib import Path

import numpy as np
from PIL import Image

from check_highres import geometry_hashes, route_script, route_script_shots
from tg2_runner import ROOT, Runner, manifest_counts


def tap(r, button):
    r.command('virtual_pad', attach=1, button=button, held=1)
    time.sleep(.08)
    r.command('virtual_pad', attach=1, button=button, held=0)
    time.sleep(.08)


def live_on(r):
    r.command('ui_open', section='VIDEO')
    time.sleep(.15)
    for _ in range(20):
        rows = r.command('ui_rows')['rows']
        if next(row for row in rows if row['selected'])['label'] == 'Linear filter':
            break
        tap(r, 'down')
    else:
        raise RuntimeError('Linear filter was not reachable')
    before = r.command('ui_rows')['rows']
    tap(r, 'right')
    after = r.command('ui_rows')['rows']
    assert next(x for x in before if x['label'] == 'Linear filter')['value'] == 'Off'
    assert next(x for x in after if x['label'] == 'Linear filter')['value'] == 'On'
    tap(r, 'b')
    tap(r, 'b')
    return dict(before=before, after=after)


def compare(a, b):
    aa = np.array(Image.open(a).convert('RGB'))
    bb = np.array(Image.open(b).convert('RGB'))
    if aa.shape != bb.shape:
        raise RuntimeError(f'capture sizes differ: {a}, {b}')
    diff = np.abs(aa.astype(np.int16) - bb.astype(np.int16)).max(2)
    ys, xs = np.where(diff > 0)
    return dict(changed=int((diff > 0).sum()), above2=int((diff > 2).sum()),
                mean=float(diff.mean()), maximum=int(diff.max()),
                first=[int(xs[0]), int(ys[0])] if len(xs) else None,
                bounds=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
                if len(xs) else None)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--exe', type=Path, default=ROOT / 'build/TG2Recomp')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--out', type=Path, default=ROOT / 'build/linear-filter')
    p.add_argument('--backend', choices=['software', 'metal'], default='software')
    p.add_argument('--size', default='1280x800')
    p.add_argument('--scales', default='1,2,4')
    p.add_argument('--port', type=int, default=4640)
    p.add_argument('--native-art-filter', action='store_true', help='Expect game-owned native filtering at N x; guest race RGB hashes then differ')
    p.add_argument('--live-frame', type=int, default=0, help='Frame to exercise the controller toggle (2800 is a race before the route accelerates)')
    p.add_argument('--uncapped', action='store_true', help='Keep full presentation/audio work but disable host pacing for short probes')
    p.add_argument('--live', action='store_true', help='Also compare a real controller Off→On toggle before the route')
    a = p.parse_args()
    a.exe = a.exe.resolve()
    a.out = a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    width, height = (int(x) for x in a.size.split('x'))
    settings = a.exe.parent / 'settings.ini'
    old = settings.read_bytes() if settings.exists() else None
    summary = dict(backend=a.backend, size=[width, height], runs=[], comparisons=[], failures=[])
    try:
        for scale in (int(x) for x in a.scales.split(',')):
            records = {}
            for name, initial in [('off', 0), ('on', 1)] + ([('live', 0)] if a.live else []):
                out = a.out / f's{scale}-{name}'
                out.mkdir(exist_ok=True)
                settings.write_text(f'[video]\nlinear_filter = {initial}\ninternal_scale = {scale}\nfullscreen = 0\n')
                script = route_script(ROOT / 'game/baseline-route.json', out / 'route.input', 3340)
                if a.native_art_filter:
                    script = route_script_shots(ROOT / 'game/baseline-route.json', script, 3340, (3300,))
                    text = script.read_text().replace(f'SCREENSHOT {out}/frame-3300.png', f'SCREENSHOT {out}/frame-3300.png\nDUMP_RAM {out}/ram-3300.bin')
                    script.write_text(text)
                env = dict(SDL_RENDER_DRIVER=a.backend, TG2_RACE_60FPS='0',
                           LNG_SCRIPT='0', LNG_TEST_HIDDEN='1',
                           GENESIS_WINDOW_CAPTURE_FRAMES='1350,3300',
                           GENESIS_WINDOW_CAPTURE_PREFIX=str(out / 'window'))
                if a.native_art_filter:
                    env['TG2_HIGHRES_FILTER_MASK_FRAME'] = '3300'
                    env['TG2_HIGHRES_FILTER_MASK_PATH'] = str(out / 'native-coverage-3300.pgm')
                r = Runner(exe=a.exe, rom=a.rom, out=out, port=a.port,
                           max_frames=0 if a.uncapped else 3340, widescreen='fit', env_extra=env,
                           extra_args=(['--measure-runtime', '3340', '--runtime-uncapped'] if a.uncapped else ['--turbo']) + ['--input-script', str(script)],
                           video_driver='cocoa' if a.backend == 'metal' else 'dummy')
                item = dict(scale=scale, choice=name, out=str(out))
                try:
                    r.start()
                    r.command('video_configure', mode='fit', window_width=width, window_height=height)
                    if name == 'live':
                        if a.live_frame: r.wait_frame(a.live_frame)
                        item['toggle'] = live_on(r)
                        item['saved'] = settings.read_text()
                        item['live_complete_frame'] = r.frame()
                        assert item['live_complete_frame'] < (2990 if a.live_frame else 650), 'live navigation overlapped the route input'
                    deadline = time.monotonic() + 180
                    while r.proc.poll() is None:
                        if time.monotonic() > deadline:
                            raise TimeoutError('runtime deadline exceeded')
                        if a.native_art_filter and 'highres' not in item and r.frame() >= 3310:
                            item['highres'] = r.command('tg2_highres')
                        time.sleep(.02)
                    item['exit'] = r.proc.returncode
                finally:
                    r.stop()
                item['manifests'] = manifest_counts(out)
                item['geometry'] = geometry_hashes(out)
                if a.native_art_filter:
                    item['ram3300_sha256'] = hashlib.sha256((out / 'ram-3300.bin').read_bytes()).hexdigest()
                item['captures'] = {}
                for frame in (1350, 3300):
                    meta = json.loads((out / f'window-{frame}.json').read_text())
                    item['captures'][frame] = meta
                    expected = int(name != 'off' and not (name == 'live' and frame < a.live_frame))
                    assert meta['saved_filter'] == meta['active_filter'] == meta['sampler'] == expected, meta
                if item['exit'] or any(v != 0 for v in item['manifests'].values()):
                    summary['failures'].append(f'{out.name}: exit/manifests')
                if a.native_art_filter and scale > 1 and name != 'off':
                    if not item.get('highres', {}).get('filtered_frames') or item['highres']['filter_incomplete']:
                        summary['failures'].append(f'{out.name}: native filter coverage/counter failed')
                summary['runs'].append(item)
                records[name] = item
                print(a.backend, a.size, scale, name, item['exit'], flush=True)
                (a.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
            for other in ['off'] + (['live'] if a.live else []):
                ref, test = records['on'], records[other]
                common = ref['geometry'].keys() & test['geometry'].keys()
                different = [f for f in sorted(common) if ref['geometry'][f] != test['geometry'][f]]
                if a.native_art_filter and ref['ram3300_sha256'] != test['ram3300_sha256']:
                    summary['failures'].append(f's{scale} on/{other}: guest RAM differs at 3300')
                dimensions = [f for f in common if ref['geometry'][f][:2] != test['geometry'][f][:2]]
                relevant = [f for f in different if other != 'live' or f >= test.get('live_complete_frame', 0)]
                unexpected = relevant if not a.native_art_filter or other == 'live' else [f for f in relevant if ref['geometry'][f][1] <= 224]
                if dimensions or unexpected:
                    summary['failures'].append(f's{scale} on/{other}: unexpected guest divergence {dimensions[:1] or unexpected[:1]}')
                for frame in (1350, 3300):
                    delta = compare(Path(ref['out']) / f'window-{frame}.png', Path(test['out']) / f'window-{frame}.png')
                    summary['comparisons'].append(dict(scale=scale, pair=f'on/{other}', frame=frame,
                                                       common_guest_hashes=len(common), guest_differences=different, **delta))
                    if other == 'live' and frame >= a.live_frame and delta['changed']:
                        summary['failures'].append(f's{scale} frame {frame}: saved/live output differs')
                    if a.native_art_filter and scale == 4 and [width,height] == [1280,800] and other == 'off' and frame == 3300:
                        mask = np.array(Image.open(Path(ref['out']) / 'native-coverage-3300.pgm'))
                        on_pixels = np.array(Image.open(Path(ref['out']) / 'window-3300.png').convert('RGB'))
                        off_pixels = np.array(Image.open(Path(test['out']) / 'window-3300.png').convert('RGB'))
                        untouched = mask == 0
                        changed = np.any(on_pixels != off_pixels,axis=2)
                        summary.setdefault('road_coverage',[]).append(dict(scale=scale, uncovered=int(untouched.sum()), changed=int((changed & untouched).sum())))
                        if (changed & untouched).any(): summary['failures'].append('uncovered analytic road changed')
                    if a.native_art_filter and scale > 1 and other == 'off' and frame == 3300 and not delta['changed']:
                        summary['failures'].append(f's{scale}: native filter had no effect')
    finally:
        if old is None:
            settings.unlink(missing_ok=True)
        else:
            settings.write_bytes(old)
    (a.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary['comparisons'], indent=2))
    return int(bool(summary['failures']))


if __name__ == '__main__':
    raise SystemExit(main())
