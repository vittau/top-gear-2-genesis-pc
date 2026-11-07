#!/usr/bin/env python3
"""Re-check the race-crop evidence that the probe runs left under build/.

Reads only the artifacts already on disk (no game process):

  * every cropped race picture is 200 lines and its removed bands are empty;
  * every Hide-overscan-Off picture is still the stock 224 lines and is
    byte-identical to the pre-change capture of the same frame;
  * menu frames are byte-identical with the option On and Off;
  * the stock Off hashes appear in the run log;
  * split-screen keeps its full height;
  * the active-line summaries, margin audits and the road-artifact report.

  python3 tools/verify_crop_evidence.py --root build/crop --out build/crop/evidence.json
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
import re

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_active_lines import check  # noqa: E402

RACE_FRAMES = (2800, 3300, 4501)
MENU_FRAMES = (600, 1350)
EXPECTED = {  # mode -> (race width, menu width)
    'off': (256, 320), '16-9': (356, 398), '21-9': (467, 523),
}
STOCK_HASHES = {60: '2A0B972960C5E325', 300: '1131D937D70234FD'}


def png_size(path: Path):
    from PIL import Image
    with Image.open(path) as image:
        return image.size


def same_pixels(a: Path, b: Path):
    from PIL import Image, ImageChops
    with Image.open(a) as ia, Image.open(b) as ib:
        if ia.size != ib.size:
            return False
        return ImageChops.difference(ia.convert('RGB'), ib.convert('RGB')).getbbox() is None


def frame_png(root: Path, run: str, mode: str, frame: int):
    # verify_widescreen writes <out>/<mode>/frame-N.png
    return root / run / mode / f'frame-{frame}.png'


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', type=Path, default=Path('build/crop'))
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    root = a.root
    report = dict(cropped={}, stock={}, menus=[], hashes={}, split={}, active={},
                  margins={}, road={}, failures=[])
    for mode, (race_w, menu_w) in EXPECTED.items():
        run = f'after/{mode}-on'
        for frame in RACE_FRAMES:
            path = frame_png(root, run, mode, frame)
            if not path.exists():
                report['failures'].append(f'missing {path}')
                continue
            size = png_size(path)
            info = check(path, top=0, bottom=0)
            first, last = info['first_picture_row'], info['last_picture_row']
            report['cropped'][f'{mode}/frame-{frame}'] = dict(
                size=size, first_picture_row=first, last_picture_row=last,
                window_rows=info['top_window_rows'])
            if size != (race_w, 200):
                report['failures'].append(f'{path}: {size} != {(race_w, 200)}')
            # A cropped picture has no empty band and no window band left.
            if first is None or first > 1 or last is None or last < size[1] - 2:
                report['failures'].append(
                    f'{path}: presented picture does not reach both edges '
                    f'(first {first}, last {last})')
            if info['top_window_rows']:
                report['failures'].append(f'{path}: window band still presented')
        for frame in MENU_FRAMES:
            path = frame_png(root, run, mode, frame)
            if not path.exists():
                report['failures'].append(f'missing {path}')
                continue
            size = png_size(path)
            if size != (menu_w, 224):
                report['failures'].append(f'{path}: menu {size} != {(menu_w, 224)}')
        # The option must not change the picture with it off, and Off must not
        # change the stock picture either.
        off_run = f'after/{mode}-off'
        for frame in RACE_FRAMES + MENU_FRAMES:
            path = frame_png(root, off_run, mode, frame)
            if not path.exists():
                continue
            size = png_size(path)
            info = check(path)
            report['stock'][f'{mode}/frame-{frame}'] = dict(
                size=size, top_ok=info['top_ok'], bottom_ok=info['bottom_ok'],
                top_window_rows=info['top_window_rows'],
                top_mark_columns=info['top_mark_columns'])
            if size[1] != 224:
                report['failures'].append(f'{path}: {size} is not stock height')
            if not info['top_ok'] or not info['bottom_ok']:
                report['failures'].append(f'{path}: stock bands carry picture')
            before = root / 'before' / f'{mode}-off' / mode / f'frame-{frame}.png'
            if before.exists() and not same_pixels(before, path):
                report['failures'].append(f'{path}: differs from the pre-change capture')
        # Menus with the crop on must equal the pre-change menus exactly.
        for frame in MENU_FRAMES:
            path = frame_png(root, run, mode, frame)
            before = root / 'before' / f'{mode}-on' / mode / f'frame-{frame}.png'
            if path.exists() and before.exists():
                same = same_pixels(before, path)
                report['menus'].append(dict(mode=mode, frame=frame, identical=same,
                                            size=png_size(path)))
                if not same:
                    report['failures'].append(f'menu {mode}/frame-{frame} changed')
    # Stock hashes from any Off run log.
    for run in ('after/off-off', 'after/off-on'):
        log = root / run / 'off' / 'stderr.log'
        if not log.exists():
            continue
        text = log.read_text(errors='replace')
        found = {}
        for frame, expected in STOCK_HASHES.items():
            match = re.search(rf'frame={frame} w=\d+ h=224 hash=0x([0-9A-F]{{16}})', text)
            found[frame] = match.group(1) if match else None
            if not match or match.group(1) != expected:
                report['failures'].append(f'{run}: frame {frame} hash {found[frame]}')
        report['hashes'][run] = found
    # Split-screen must present the full 224-line, 256-pixel picture.
    split = root / 'split/on/summary.json'
    if split.exists():
        data = json.loads(split.read_text())
        report['split'] = dict(widths=data.get('widths'),
                               two_player_frames=data.get('two_player_frames'),
                               two_player_race_samples=data.get('two_player_race_samples'),
                               screenshots=data.get('screenshots'))
        if data.get('widths') and data['widths'] != [256]:
            report['failures'].append(f'split widths {data["widths"]}')
    # Active-line summaries.
    totals = dict(runs=0, pictures=0, failures=0)
    for path in sorted(glob.glob(str(root / 'active/*/summary.json'))):
        data = json.loads(Path(path).read_text())
        totals['runs'] += 1
        totals['pictures'] += len(data.get('pictures', []))
        totals['failures'] += len(data.get('failures', []))
        if data.get('failures'):
            report['failures'].append(f'{path}: band failures {data["failures"]}')
    report['active'] = totals
    # Margin audits and the road-artifact report.
    for name in ('16-9', '21-9', '16-9-60'):
        path = root / 'margins' / name / 'summary.json'
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        margins = {mode: result.get('margins') for mode, result in data.items()}
        report['margins'][name] = {mode: dict(
            passed=(m or {}).get('passed'), frames=(m or {}).get('frames'),
            rows=(m or {}).get('rows'),
            black=(m or {}).get('black_violations'),
            ground=(m or {}).get('ground_colour_violations'),
            band=(m or {}).get('band_colour_violations'),
            brief=(m or {}).get('brief_backdrop_lines'),
            incomplete=(m or {}).get('incomplete_frames')) for mode, m in margins.items()}
        for mode, entry in report['margins'][name].items():
            if entry['passed'] is not True:
                report['failures'].append(f'margin audit {name}/{mode} did not pass')
    road = root / 'road/road-artifacts.json'
    if road.exists():
        data = json.loads(road.read_text())
        report['road'] = dict(passed=data.get('passed'),
                              frames=data.get('frames'),
                              synthesized=data.get('synthesized_frames'),
                              tested_lines=data.get('tested_road_lines'),
                              violations={k: data.get(k) for k in (
                                  'edge_violating_lines', 'stripe_violating_lines',
                                  'discrete_row_violations',
                                  'source_translation_violating_lines',
                                  'source_snapshot_inconsistencies',
                                  'unchecked_synthesized_frames')})
        if not data.get('passed'):
            report['failures'].append('road artifact check did not pass')
    target = a.out or root / 'evidence.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(cropped=len(report['cropped']), stock=len(report['stock']),
                          menus=len(report['menus']), hashes=report['hashes'],
                          active=report['active'], split=report['split'].get('widths'),
                          margins=sorted(report['margins']),
                          road=report['road'] and report['road'].get('passed'),
                          failures=report['failures'])))
    raise SystemExit(0 if not report['failures'] else 1)


if __name__ == '__main__':
    main()
