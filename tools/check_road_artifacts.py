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
# The S3 builder writes one frame-NNNNNN.nxroad per presented picture: one
# record per presented row of every road row it redrew. Each record carries
# the authored silhouettes of the row and of the neighbour it leaned on, the
# edges the builder aimed for, and what the BUILT pixels show (measured back
# from the finished row, not from the builder's variables): first/last road
# pixel, lane-mark runs, verge pixels inside the road, and pixels whose colour
# the native row cannot explain within the distance the silhouette moved.
NX_MAGIC = b'TG2NXR03'
NX_DTYPE = np.dtype([(name, '<i4') for name in (
    'line', 'sub', 'py', 'flags', 'neighbour',
    'own_l', 'own_r', 'nb_l', 'nb_r', 'el_x256', 'er_x256',
    'seen_l', 'seen_r', 'lanes', 'lanes_src', 'holes',
    'outliers', 'margin_outliers', 'band', 'lane_error_x256')])
NX_INTERPOLATED, NX_FULL, NX_STRUCTURE, NX_AMBIGUOUS = 1, 2, 4, 8
# The fitted silhouette may sit this far from the authored one (FIT_LIMIT in
# game/tg2_highres.c), in native pixels.
NX_FIT_LIMIT = 1.5


def load_nx(path):
    data = path.read_bytes()
    if data[:8] not in (NX_MAGIC, b'TG2NXR02'):
        raise ValueError(f'invalid N x road capture: {path}')
    frame, scale, w1, native_w, count, size = struct.unpack_from('<6I', data, 8)
    dtype = NX_DTYPE if data[:8] == NX_MAGIC else np.dtype(NX_DTYPE.descr[:-1])
    if size != dtype.itemsize or len(data) != 32 + count * size:
        raise ValueError(f'incomplete N x road capture: {path}')
    rows = np.frombuffer(data, dtype=dtype, offset=32)
    rows = rows[np.lexsort((rows['sub'], rows['line']))]
    return dict(frame=frame, scale=scale, w1=w1, native_w=native_w), rows


def main_nx(a):
    audit = a.capture / 'audit'
    paths = sorted(audit.glob('frame-*.nxroad'))
    if not paths:
        raise SystemExit('no N x road audit files; run with TG2_ROAD_AUDIT_DIR')
    counters = ['envelope_violations', 'gap_violations', 'geometry_violations',
                'hole_violations', 'stripe_violations', 'continuity_violations',
                'outlier_rows', 'margin_outlier_rows', 'stripe_centre_violations']
    totals = dict(mode='nx', frames=0, road_frames=0, scales=[], presented_rows=0,
                  interpolated_rows=0, full_rows=0, stripe_rows_checked=0,
                  continuity_pairs_checked=0, band_breaks=0,
                  max_envelope_violation_px=0.0, max_geometry_error_px=0.0,
                  max_fit_offset_px=0.0, max_edge_step_px=0.0,
                  stripe_centres_checked=0, max_stripe_centre_error_px=0.0, examples=[])
    totals.update({k: 0 for k in counters})
    for path in paths:
        h, r = load_nx(path)
        totals['frames'] += 1
        if h['scale'] not in totals['scales']:
            totals['scales'].append(h['scale'])
        if not len(r):
            continue
        totals['road_frames'] += 1
        n, w1 = h['scale'], h['w1']
        el, er = r['el_x256'] / 256.0, r['er_x256'] / 256.0
        # Rows whose verge shares a colour with the road are not measurable.
        full = (r['flags'] & NX_FULL != 0) & (r['flags'] & NX_AMBIGUOUS == 0)
        totals['presented_rows'] += len(r)
        totals['interpolated_rows'] += int((r['flags'] & NX_INTERPOLATED != 0).sum())
        totals['full_rows'] += int(full.sum())
        # 1. The drawn edge stays between the two authored silhouettes it was
        #    built from, give or take the fit allowance.
        lo_l, hi_l = np.minimum(r['own_l'], r['nb_l']), np.maximum(r['own_l'], r['nb_l'])
        lo_r, hi_r = np.minimum(r['own_r'], r['nb_r']), np.maximum(r['own_r'], r['nb_r'])
        envelope = np.maximum.reduce([lo_l - el, el - hi_l, lo_r - er, er - hi_r]) - NX_FIT_LIMIT
        bad_env = envelope > 1e-3
        totals['max_envelope_violation_px'] = max(totals['max_envelope_violation_px'],
                                                  float(max(envelope.max(), 0)))
        totals['max_fit_offset_px'] = max(totals['max_fit_offset_px'], float(np.maximum(
            np.abs(el - r['own_l']), np.abs(er - r['own_r']))[r['neighbour'] == 0].max(initial=0)))
        # 2. No vanishing road.
        bad_gap = er - el < 2.0
        # 3. The built pixels show the road where the builder aimed, on rows
        #    nothing covers and the canvas does not clip.
        free = full & (el > 1) & (er < w1 - 1) & (r['seen_l'] >= 0)
        geometry = np.maximum(np.abs(r['seen_l'] - el * n), np.abs(r['seen_r'] + 1 - er * n))
        geometry = np.where(free, geometry, 0.0)
        bad_geo = geometry > 1.5
        totals['max_geometry_error_px'] = max(totals['max_geometry_error_px'],
                                              float(geometry.max()))
        # 4. No verge pixel inside the road, and the lane marks are all there.
        bad_hole = full & (r['holes'] > 0)
        bad_stripe = free & (r['lanes'] != r['lanes_src'])
        totals['stripe_rows_checked'] += int(free.sum())
        bad_centre = np.zeros(len(r), dtype=bool)
        if 'lane_error_x256' in r.dtype.names:
            lane_rows = free & (r['lanes_src'] > 0)
            error = np.where(lane_rows, r['lane_error_x256'] / 256.0, 0.0)
            bad_centre = error > 1.5
            totals['stripe_centres_checked'] += int(lane_rows.sum())
            totals['max_stripe_centre_error_px'] = max(
                totals['max_stripe_centre_error_px'], float(error.max(initial=0)))
        # 5. Nothing the native row cannot explain, margins included.
        bad_out = r['outliers'] > 0
        bad_margin = r['margin_outliers'] > 0
        # 6. Presented row to presented row, inside one band, the edge moves
        #    by no more than its share of the authored step: a bigger jump is
        #    a tear, a fan or a duplicated row.
        consecutive = ((r['line'][1:] * n + r['sub'][1:]) -
                       (r['line'][:-1] * n + r['sub'][:-1])) == 1
        same_band = consecutive & (r['band'][1:] == r['band'][:-1])
        totals['band_breaks'] += int((consecutive & ~same_band).sum())
        step_l = np.maximum(np.abs(r['own_l'] - r['nb_l'])[1:], np.abs(r['own_l'] - r['nb_l'])[:-1])
        step_r = np.maximum(np.abs(r['own_r'] - r['nb_r'])[1:], np.abs(r['own_r'] - r['nb_r'])[:-1])
        row_l = np.abs(r['own_l'][1:] - r['own_l'][:-1])
        row_r = np.abs(r['own_r'][1:] - r['own_r'][:-1])
        allow_l = (np.maximum(step_l, row_l) + 2 * NX_FIT_LIMIT) / n + 0.02
        allow_r = (np.maximum(step_r, row_r) + 2 * NX_FIT_LIMIT) / n + 0.02
        d_el, d_er = np.abs(np.diff(el)), np.abs(np.diff(er))
        both = same_band & free[1:] & free[:-1]
        seen_l = np.abs(np.diff(r['seen_l'])) > d_el * n + 2
        seen_r = np.abs(np.diff(r['seen_r'])) > d_er * n + 2
        bad_pair = same_band & ((d_el > allow_l) | (d_er > allow_r)) | both & (seen_l | seen_r)
        totals['continuity_pairs_checked'] += int(same_band.sum())
        if same_band.any():
            totals['max_edge_step_px'] = max(totals['max_edge_step_px'],
                                             float(np.maximum(d_el, d_er)[same_band].max()))
        bad_cont = np.zeros(len(r), dtype=bool)
        bad_cont[1:] = bad_pair
        for name, bad in zip(counters, [bad_env, bad_gap, bad_geo, bad_hole, bad_stripe,
                                        bad_cont, bad_out, bad_margin, bad_centre]):
            totals[name] += int(bad.sum())
            for i in np.flatnonzero(bad)[:2]:
                if sum(e['rule'] == name for e in totals['examples']) < 4:
                    totals['examples'].append(dict(
                        rule=name, frame=int(h['frame']), line=int(r['line'][i]),
                        sub=int(r['sub'][i]), py=int(r['py'][i]), flags=int(r['flags'][i]),
                        edges=[float(el[i]), float(er[i])],
                        own=[int(r['own_l'][i]), int(r['own_r'][i])],
                        neighbour=[int(r['nb_l'][i]), int(r['nb_r'][i])],
                        seen=[int(r['seen_l'][i]), int(r['seen_r'][i])],
                        lanes=[int(r['lanes'][i]), int(r['lanes_src'][i])],
                        holes=int(r['holes'][i]), outliers=int(r['outliers'][i]),
                        margin_outliers=int(r['margin_outliers'][i])))
    totals['passed'] = (totals['frames'] >= a.min_frames and totals['presented_rows'] > 0
                        and not any(totals[k] for k in counters))
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
