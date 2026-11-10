#!/usr/bin/env python3
"""Compare exact-frame final SDL output for saved/live Linear Filter.

Use the release's pinned SDL2, not sdl2-compat. Run under the heavy lock, with
one runtime. macOS Metal uses a hidden Cocoa window. Requires Pillow/NumPy;
images, sampler JSON, settings, hashes and manifests stay under build/.
The tool restores the scratch build's settings.ini, even on an error.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from check_highres import geometry_hashes, route_script
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
                env = dict(SDL_RENDER_DRIVER=a.backend, TG2_RACE_60FPS='0',
                           LNG_SCRIPT='0', LNG_TEST_HIDDEN='1',
                           GENESIS_WINDOW_CAPTURE_FRAMES='1350,3300',
                           GENESIS_WINDOW_CAPTURE_PREFIX=str(out / 'window'))
                r = Runner(exe=a.exe, rom=a.rom, out=out, port=a.port,
                           max_frames=0 if a.uncapped else 3340, widescreen='fit', env_extra=env,
                           extra_args=(['--measure-runtime', '3340', '--runtime-uncapped'] if a.uncapped else ['--turbo']) + ['--input-script', str(script)],
                           video_driver='cocoa' if a.backend == 'metal' else 'dummy')
                item = dict(scale=scale, choice=name, out=str(out))
                try:
                    r.start()
                    r.command('video_configure', mode='fit', window_width=width, window_height=height)
                    if name == 'live':
                        item['toggle'] = live_on(r)
                        item['saved'] = settings.read_text()
                        assert r.frame() < 650, 'live navigation overlapped the route input'
                    deadline = time.monotonic() + 180
                    while r.proc.poll() is None:
                        if time.monotonic() > deadline:
                            raise TimeoutError('runtime deadline exceeded')
                        time.sleep(.05)
                    item['exit'] = r.proc.returncode
                finally:
                    r.stop()
                item['manifests'] = manifest_counts(out)
                item['geometry'] = geometry_hashes(out)
                item['captures'] = {}
                for frame in (1350, 3300):
                    meta = json.loads((out / f'window-{frame}.json').read_text())
                    item['captures'][frame] = meta
                    expected = int(name != 'off')
                    assert meta['saved_filter'] == meta['active_filter'] == meta['sampler'] == expected, meta
                if item['exit'] or any(v != 0 for v in item['manifests'].values()):
                    summary['failures'].append(f'{out.name}: exit/manifests')
                summary['runs'].append(item)
                records[name] = item
                print(a.backend, a.size, scale, name, item['exit'], flush=True)
                (a.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
            for other in ['off'] + (['live'] if a.live else []):
                ref, test = records['on'], records[other]
                common = ref['geometry'].keys() & test['geometry'].keys()
                different = [f for f in sorted(common) if ref['geometry'][f] != test['geometry'][f]]
                if different:
                    summary['failures'].append(f's{scale} on/{other}: guest hash divergence {different[0]}')
                for frame in (1350, 3300):
                    delta = compare(Path(ref['out']) / f'window-{frame}.png', Path(test['out']) / f'window-{frame}.png')
                    summary['comparisons'].append(dict(scale=scale, pair=f'on/{other}', frame=frame,
                                                       common_guest_hashes=len(common), guest_differences=different, **delta))
                    if other == 'live' and delta['changed']:
                        summary['failures'].append(f's{scale} frame {frame}: saved/live output differs')
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
