#!/usr/bin/env python3
"""Check every race scanline exported by TG2_MARGIN_AUDIT.

The trace is emitted before sprites/HUD can cover a margin defect. Native edge
colours come from the native row producer, including 60 fps synthesis, rather
than from the margin renderer. Captures stay private under build/.
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def check(path, max_brief_frames=3):
    totals = dict(rows=0, frames=0, black_violations=0, ground_colour_violations=0,
                  band_colour_violations=0, brief_backdrop_lines=0,
                  solid_band_samples=0, plane_a_short_extension=0,
                  examples=[], brief_examples=[])
    frames, slopes, lines = {}, set(), set()
    # Backdrop rows that appear for only a few consecutive presented pictures
    # are the motion-only thin black line seen on hills: a real picture can
    # carry one, and a synthesized picture can move one row into view.
    backdrop = defaultdict(list)
    with Path(path).open() as source:
        for record in csv.DictReader(source):
            row = {key: int(value) for key, value in record.items()}
            frames[row['frame']] = frames.get(row['frame'], 0) | (1 << (row['line'] * 2 + row['side']))
            slopes.add(row['slope'])
            lines.add(row['line'])
            totals['rows'] += 1
            if row['backdrop_band'] and not row['window_band'] and not row['margin'] & 0xffffff:
                backdrop[(row['side'], row['line'])].append(row['frame'])
            # Opaque black panorama art and native plane-A effects are not
            # the backdrop gap: require visible scenery at the native edge.
            # Plane A also draws full-screen raster effects (the Auckland
            # tunnel wall, solid sky overlays). When its opaque high-priority
            # texel covers the native edge, the visible layer is not plane B,
            # so the ground-continuity rule below cannot compare with it.
            plane_a_cover = bool(row['ap'] and row['attr_a'] & 0x8000)
            black = (not row['window_band'] and row['margin'] & 0xffffff == 0 and row['native'] & 0xffffff
                     and row['native_b'] & 0xffffff and not row['margin_bp'])
            # The margins continue the weather overlay (docs/RAIN_WIDESCREEN.md):
            # a rain/snow particle on the sampled margin texel is plane A, not
            # a break in the ground. margin_weather is exported since task 33.
            ground = (not row['window_band'] and not plane_a_cover
                      and not row.get('margin_weather', 0)
                      and row['native'] & 0xffffff and row['bp'] in (5, 15, 21, 31)
                      and (432 <= row['atlas_y'] < 448
                           or row['margin_bp'] in (5, 15, 21, 31))
                      and row['margin'] != row['native_b'])
            band = row['edge_solid'] and (row['window_band'] or row['backdrop_band'])
            totals['solid_band_samples'] += int(bool(band))
            # Weather (rain/snow) is a point feature on the otherwise
            # transparent plane A. Continuing such a texel's colour paints a
            # one-line streak across the whole margin; only a surface that owns
            # the edge (an opaque run) may be continued. pa_run/pa_extend are
            # emitted by tg2_video.c since the task 22 fix.
            short_extend = bool(row.get('pa_extend', 0) and row.get('pa_run', 8) < 8)
            totals['plane_a_short_extension'] += int(short_extend)
            band_bad = band and row['margin'] != row['native']
            totals['band_colour_violations'] += int(bool(band_bad))
            totals['ground_colour_violations'] += int(ground)
            if black:
                totals['black_violations'] += 1
            if (black or ground or band_bad or short_extend) and len(totals['examples']) < 20:
                row['source'] = ('window' if row['window_band'] else
                                 'backdrop' if row['backdrop_band'] else
                                 'road' if row['atlas_y'] < 432 else
                                 'ground/separator' if row['atlas_y'] < 448 else 'panorama')
                totals['examples'].append(row)
    # A backdrop row is expected to persist while its scene persists. A run of
    # one to three consecutive presented pictures means the row appeared and
    # vanished: either a synthesized line with no real source, or a stock line
    # that only a fast transition shows for one picture.
    ordered = sorted(frames)
    order = {frame: index for index, frame in enumerate(ordered)}
    for (side, line), seen in backdrop.items():
        indexes = sorted(order[frame] for frame in seen)
        start = 0
        while start < len(indexes):
            end = start
            while end + 1 < len(indexes) and indexes[end + 1] == indexes[end] + 1:
                end += 1
            length = end - start + 1
            boundary = indexes[start] == 0 or indexes[end] == len(ordered) - 1
            if length <= max_brief_frames and not boundary:
                totals['brief_backdrop_lines'] += 1
                if len(totals['brief_examples']) < 20:
                    totals['brief_examples'].append(dict(
                        frame=ordered[indexes[start]], side=side, line=line,
                        pictures=length))
            start = end + 1
    totals['frames'] = len(frames)
    totals['first_frame'] = ordered[0] if ordered else None
    totals['last_frame'] = max(frames) if frames else None
    totals['missing_frames'] = sorted(set(range(min(frames), max(frames) + 1)) - frames.keys()) if frames else []
    totals['incomplete_frames'] = [f for f, coverage in frames.items()
                                  if coverage != (1 << 448) - 1]
    totals['line_range'] = [min(lines), max(lines)] if lines else []
    totals['slope_range'] = [min(slopes), max(slopes)] if slopes else []
    totals['passed'] = (totals['rows'] > 0 and not totals['missing_frames']
                        and not totals['incomplete_frames']
                        and not totals['black_violations']
                        and not totals['ground_colour_violations']
                        and not totals['band_colour_violations']
                        and not totals['plane_a_short_extension']
                        and not totals['brief_backdrop_lines'])
    return totals


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--max-brief-frames', type=int, default=3,
                   help='a backdrop row present for at most N presented pictures is a flicker line')
    a = p.parse_args()
    result = check(a.trace, a.max_brief_frames)
    if a.out:
        a.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
