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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', type=Path, help='probe output with audit/ and screenshots')
    p.add_argument('--out', type=Path)
    p.add_argument('--strip-start', type=int, action='append', default=[])
    a = p.parse_args()
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
