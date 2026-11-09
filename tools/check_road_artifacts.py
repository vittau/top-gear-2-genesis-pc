#!/usr/bin/env python3
"""Check every baseline presentation row against its two real road pictures.

TG2_ROAD_AUDIT_DIR exports independent plane-B pixels before sprite/HUD
occlusion. This checks the actual selected atlas pixels, not renderer geometry
variables: road edges, stripe runs, nearest-source translation and source
snapshot consistency. Raw indices retain palette-bank/stripe-phase identity.
Requires NumPy; --strips also requires Pillow. Assets stay under build/.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import numpy as np


def load(path):
    data = path.read_bytes()
    if data[:8] != b'TG2ROAD1':
        raise ValueError(f'invalid road capture: {path}')
    frame, a, b, num, den, origin, width, y, height = struct.unpack_from('<9I', data, 8)
    if origin & 0x80000000:
        origin -= 1 << 32
    dtype = np.dtype([('py', '<u4'), ('hs', '<u4'), ('pixels', 'u1', (width,))])
    if len(data) != 44 + height * 3 * dtype.itemsize:
        raise ValueError(f'incomplete road capture: {path}')
    rows = np.frombuffer(data, dtype=dtype, offset=44).reshape(height, 3)
    return dict(frame=frame, a=a, b=b, num=num, den=den, origin=origin,
                width=width, y=y, height=height), rows


def features(pixels, origin):
    nib = pixels & 15
    road = (nib == 6) | (nib == 13) | (nib == 14)
    left = road.argmax(axis=-1) + origin
    right = road.shape[-1] - 1 - road[..., ::-1].argmax(axis=-1) + origin
    stripes = nib == 13
    count = stripes[..., 0].astype(int) + ((~stripes[..., :-1]) & stripes[..., 1:]).sum(axis=-1)
    return left, right, count, road.any(axis=-1)


def strip(out, audit, start):
    from PIL import Image, ImageDraw
    panels = []
    for frame in range(start, start + 12):
        image = Image.open(out / f'shot-{frame}.png').convert('RGB')
        crop = image.crop((60, 140, image.width, 212)).resize(((image.width - 60) * 2, 144), Image.Resampling.NEAREST)
        panel = Image.new('RGB', (crop.width, 166), '#202020')
        panel.paste(crop, (0, 22))
        f = audit / f'frame-{frame - 1:06d}.road'
        label = f'frame {frame}'
        if f.exists():
            h, _ = load(f)
            label += f"  {'intermediate' if h['num'] and h['a'] != h['b'] else 'real'}  {h['a'] + 1}->{h['b'] + 1}  {h['num']}/{h['den']}"
        ImageDraw.Draw(panel).text((6, 4), label, fill='white')
        panels.append(panel)
    sheet = Image.new('RGB', (panels[0].width * 3, 166 * 4), '#202020')
    for i, panel in enumerate(panels):
        sheet.paste(panel, ((i % 3) * panel.width, (i // 3) * 166))
    target = out / f'road-strip-{start}-2x.png'
    sheet.save(target)
    return str(target)


# ── N x mode (docs/HIGHRES.md §8 S3) ──────────────────────────────────────
# The S3 builder writes one frame-NNNNNN.nxroad per presented picture: the
# native-row-granular road geometry it actually drew, measured back from the
# built picture, next to the two authored neighbours it interpolated between.
NX_MAGIC = b'TG2NXR01'
NX_DTYPE = np.dtype([
    ('line', '<u4'), ('py_src', '<u4'), ('py_next', '<u4'),
    ('centre_src', '<i4'), ('centre_next', '<i4'),
    ('left_src', '<i4'), ('right_src', '<i4'),
    ('left_next', '<i4'), ('right_next', '<i4'),
    ('el_x256', '<i4'), ('er_x256', '<i4'),
    ('measured_left', '<i4'), ('measured_right', '<i4'),
    ('stripes', '<u4'), ('stripes_src', '<u4'), ('flags', '<u4'),
])
NX_ROAD, NX_INTERPOLATED, NX_FULL = 1, 2, 4


def load_nx(path):
    data = path.read_bytes()
    if data[:8] != NX_MAGIC:
        raise ValueError(f'invalid N x road capture: {path}')
    header = struct.unpack_from('<7I', data, 8)
    rows = np.frombuffer(data, dtype=NX_DTYPE, offset=8 + 28)
    if len(rows) != header[6]:
        raise ValueError(f'incomplete N x road capture: {path}')
    return dict(frame=header[1], scale=header[2], stride=header[3],
                w1=header[4], native_w=header[5], height=header[6]), rows


def main_nx(a):
    audit = a.capture / 'audit'
    paths = sorted(audit.glob('frame-*.nxroad'))
    if not paths:
        a.capture.joinpath('audit').mkdir(parents=True, exist_ok=True)
        p.error('no N x road audit files; run with TG2_ROAD_AUDIT_DIR')
    totals = dict(mode='nx', frames=0, scales=[], tested_rows=0,
                  envelope_violations=0, max_envelope_violation_px=0.0,
                  geometry_violations=0, max_geometry_error_px=0.0,
                  gap_violations=0, stripe_rows_checked=0, stripe_violations=0,
                  continuity_rows_checked=0,
                  max_stripe_violation=0, continuity_violations=0,
                  max_left_step_px=0, max_right_step_px=0, examples=[])
    for path in paths:
        h, rows = load_nx(path)
        totals['frames'] += 1
        if h['scale'] not in totals['scales']:
            totals['scales'].append(h['scale'])
        road = rows['flags'] & NX_ROAD != 0
        totals['tested_rows'] += int(road.sum())
        el = rows['el_x256'] / 256.0
        er = rows['er_x256'] / 256.0
        interp = rows['flags'] & NX_INTERPOLATED != 0
        env_l = np.minimum(rows['left_src'], np.where(interp, rows['left_next'], 1 << 20))
        env_r = np.maximum(rows['right_src'], np.where(interp, rows['right_next'], -(1 << 20)))
        envelope = np.maximum.reduce([env_l - 1.0 - el, el - (env_r + 1.0),
                                      env_l - 1.0 - er, er - (env_r + 1.0),
                                      np.zeros_like(el)])
        envelope = np.where(road, envelope, 0.0)
        totals['envelope_violations'] += int((envelope > 0).sum())
        if road.any():
            totals['max_envelope_violation_px'] = max(
                totals['max_envelope_violation_px'], float(envelope.max()))
        width = er - el
        gaps = road & (width < 2.0)
        totals['gap_violations'] += int(gaps.sum())
        # The committed strip is what fits on the canvas; a road wider than the
        # picture is clipped by it, so compare against the clipped geometry.
        # Only rows the builder reported as fully scenery are compared: a
        # sprite or the car can cover part of the strip.
        w1 = h['w1']
        covered = road & (rows['flags'] & NX_FULL != 0)
        authored = (covered & (el <= rows['left_src'] + 1) &
                    (er >= rows['right_src'] - 1) & (rows['left_src'] >= 0) &
                    (rows['right_src'] < w1 - 1))
        vis_l = np.clip(el, 0, w1 - 1)
        vis_r = np.clip(er - 1, 0, w1 - 1)
        geometry = np.maximum(np.abs(rows['measured_left'] - vis_l),
                              np.abs(rows['measured_right'] - vis_r))
        geometry = np.where(covered, geometry, 0.0)
        totals['geometry_violations'] += int((geometry > 1.5).sum())
        if road.any():
            totals['max_geometry_error_px'] = max(totals['max_geometry_error_px'],
                                                  float(geometry.max()))
        # Stripe phase on the same fully-scenery rows.
        stripe_error = np.abs(rows['stripes'].astype(int) - rows['stripes_src'].astype(int))
        totals['stripe_rows_checked'] += int(authored.sum())
        totals['stripe_violations'] += int(((stripe_error > 0) & authored).sum())
        if authored.any():
            totals['max_stripe_violation'] = max(totals['max_stripe_violation'],
                                                 int(stripe_error[authored].max()))
        # Row-to-row continuity: ignore rows whose strip is clipped by the
        # canvas edge (their measured edge is pinned to 0 / w1-1 by design).
        free = covered & (rows['measured_left'] > 0) & (rows['measured_right'] < w1 - 1)
        # A curve legitimately moves the authored edge by many pixels per row,
        # so the committed edge may only step by as much as the interpolated
        # one plus antialiasing slop: a bigger step is a tear or a duplicate.
        left = np.where(free, rows['measured_left'], np.nan)
        right = np.where(free, rows['measured_right'], np.nan)
        dleft = np.abs(np.diff(left))
        dright = np.abs(np.diff(right))
        d_el = np.abs(np.diff(el))
        d_er = np.abs(np.diff(er))
        bad = np.zeros(len(rows), dtype=bool)
        if len(rows) > 1:
            bad[1:] = ((dleft > d_el + 2) & ~np.isnan(dleft)) | \
                      ((dright > d_er + 2) & ~np.isnan(dright))
        totals['continuity_rows_checked'] += int(free.sum())
        totals['continuity_violations'] += int(bad.sum())
        if np.isfinite(dleft).any():
            totals['max_left_step_px'] = max(totals['max_left_step_px'],
                                             int(np.nanmax(dleft)))
            totals['max_right_step_px'] = max(totals['max_right_step_px'],
                                              int(np.nanmax(dright)))
        flagged = (envelope > 0) | gaps | (geometry > 1.5) | ((stripe_error > 0) & authored)
        for line in np.flatnonzero(flagged)[:3]:
            if len(totals['examples']) < 12:
                totals['examples'].append(dict(
                    frame=int(h['frame']) + 1, line=int(rows['line'][line]),
                    py=int(rows['py_src'][line]), edges=[float(el[line]), float(er[line])],
                    envelope=[float(env_l[line] - 1), float(env_r[line] + 1)],
                    measured=[int(rows['measured_left'][line]), int(rows['measured_right'][line])],
                    stripes=[int(rows['stripes'][line]), int(rows['stripes_src'][line])]))
    violations = ['envelope_violations', 'geometry_violations', 'gap_violations',
                  'stripe_violations', 'continuity_violations']
    totals['passed'] = (totals['frames'] >= a.min_frames and
                        totals['tested_rows'] > 0 and
                        not any(totals[k] for k in violations))
    target = a.out or (a.capture / 'road-artifacts-nx.json')
    target.write_text(json.dumps(totals, indent=2) + '\n')
    print(json.dumps(totals, indent=2))
    raise SystemExit(0 if totals['passed'] else 1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', type=Path, help='probe output with audit/ and screenshots')
    p.add_argument('--out', type=Path)
    p.add_argument('--strip-start', type=int, action='append', default=[])
    p.add_argument('--nx', action='store_true',
                   help='check the S3 N x road records instead of the 60 fps strips')
    p.add_argument('--min-frames', type=int, default=3000,
                   help='N x mode: minimum presented pictures the audit must cover')
    a = p.parse_args()
    if a.nx:
        return main_nx(a)
    audit = a.capture / 'audit'
    paths = sorted(audit.glob('frame-*.road'))
    if not paths:
        p.error('no road audit files; run with TG2_ROAD_AUDIT_DIR')
    totals = dict(frames=0, synthesized_frames=0, tested_road_lines=0,
                  edge_violating_lines=0, max_edge_violation_px=0,
                  stripe_violating_lines=0, max_stripe_count_violation=0,
                  discrete_row_violations=0, source_translation_violating_lines=0,
                  max_source_translation_pixel_mismatches=0,
                  source_snapshot_inconsistencies=0, unchecked_synthesized_frames=0)
    sources, frames, examples = {}, [], []
    for path in paths:
        h, rows = load(path)
        frames.append(h['frame'])
        totals['frames'] += 1
        for source, side in [(h['a'], 0), (h['b'], 1)]:
            fingerprint = hashlib.sha256(rows[:, side].tobytes()).hexdigest()
            if source in sources and sources[source] != fingerprint:
                totals['source_snapshot_inconsistencies'] += 1
            sources[source] = fingerprint
        if h['a'] == h['b'] or not h['num']:
            continue
        if not (h['a'] < h['b'] and 0 < h['num'] < h['den']):
            raise ValueError(f'invalid real-picture bracket: {path}')
        totals['synthesized_frames'] += 1
        pix = rows['pixels']
        left, right, stripes, any_road = features(pix, h['origin'])
        valid = (rows['py'][:, 0] < 432) & (rows['py'][:, 1] < 432) & any_road[:, 0] & any_road[:, 1]
        edge_error = np.maximum.reduce([left[:, :2].min(axis=1) - left[:, 2],
                                       left[:, 2] - left[:, :2].max(axis=1),
                                       right[:, :2].min(axis=1) - right[:, 2],
                                       right[:, 2] - right[:, :2].max(axis=1),
                                       np.zeros(h['height'], dtype=int)])
        stripe_error = np.abs(stripes[:, :2] - stripes[:, 2:3]).min(axis=1)
        discrete = (rows['py'][:, 2] != rows['py'][:, 0]) & (rows['py'][:, 2] != rows['py'][:, 1])
        side = int(h['num'] * 2 >= h['den'])
        delta = left[:, 2] - left[:, side]
        indices = np.clip(np.arange(h['width'])[None, :] - delta[:, None], 0, h['width'] - 1)
        translated = np.take_along_axis(pix[:, side], indices, axis=1)
        mismatches = (translated != pix[:, 2]).sum(axis=1)
        totals['unchecked_synthesized_frames'] += int(not valid.any())
        totals['tested_road_lines'] += int(valid.sum())
        totals['edge_violating_lines'] += int(((edge_error > 0) & valid).sum())
        totals['stripe_violating_lines'] += int(((stripe_error > 0) & valid).sum())
        totals['discrete_row_violations'] += int((discrete & valid).sum())
        totals['source_translation_violating_lines'] += int(((mismatches > 0) & valid).sum())
        if valid.any():
            totals['max_edge_violation_px'] = max(totals['max_edge_violation_px'], int(edge_error[valid].max()))
            totals['max_stripe_count_violation'] = max(totals['max_stripe_count_violation'], int(stripe_error[valid].max()))
            totals['max_source_translation_pixel_mismatches'] = max(totals['max_source_translation_pixel_mismatches'], int(mismatches[valid].max()))
        bad = valid & ((edge_error > 0) | (stripe_error > 0) | discrete | (mismatches > 0))
        for line in np.flatnonzero(bad)[:3]:
            if len(examples) < 12:
                examples.append(dict(frame=h['frame'] + 1, line=int(line + h['y']),
                                     atlas_rows=rows['py'][line].tolist(),
                                     edges_left=left[line].tolist(), edges_right=right[line].tolist(),
                                     stripe_counts=stripes[line].tolist()))
    missing = sorted(set(range(frames[0], frames[-1] + 1)) - set(frames))
    totals.update(first_frame=frames[0] + 1, last_frame=frames[-1] + 1,
                  missing_frames=[f + 1 for f in missing], unique_real_pictures=len(sources),
                  examples=examples, strips=[strip(a.capture, audit, f) for f in a.strip_start])
    violations = ['edge_violating_lines', 'stripe_violating_lines', 'discrete_row_violations',
                  'source_translation_violating_lines', 'source_snapshot_inconsistencies', 'unchecked_synthesized_frames']
    totals['passed'] = not missing and totals['synthesized_frames'] > 0 and totals['tested_road_lines'] > 0 and not any(totals[k] for k in violations)
    target = a.out or a.capture / 'road-artifacts.json'
    target.write_text(json.dumps(totals, indent=2) + '\n')
    print(json.dumps(totals, indent=2))
    raise SystemExit(0 if totals['passed'] else 1)


if __name__ == '__main__':
    main()
