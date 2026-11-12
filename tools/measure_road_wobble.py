#!/usr/bin/env python3
"""Compare streamed TG2 road-boundary evidence from two matched captures.

Requires NumPy. Enable TG2_ROAD_AUDIT_DIR and TG2_ROAD_BOUNDARY_AUDIT=1 in
trace builds. .edges holds source-row geometry, .nxroad measures built pixels.
Frame evidence is processed one file at a time. Output is scalar JSON only.
"""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from check_road_artifacts import load_nx, NX_FIT_LIMIT


def geometry(path):
    rows = {}
    with path.open() as stream:
        for r in csv.DictReader(stream):
            row = rows.setdefault(int(r['line']), (int(r['band']), []))
            row[1].append((int(r['boundary']), int(r['left']), int(r['right']),
                           float(r['raw']), float(r['fit'])))
    groups = {}
    for y, (band, boundaries) in rows.items():
        topology = tuple((b[1], b[2]) for b in boundaries)
        for k, left, right, raw, fit in boundaries:
            outer = k in (0, len(boundaries)-1)
            # Silhouettes remain continuous across topology/stripe changes.
            key = (band, 'outer', int(k != 0)) if outer else (band, topology, k)
            groups.setdefault(key, []).append((y, raw, fit, outer))
    return groups


def measure(before, after):
    totals = {which: {kind: dict(count=0, raw_ss=0., fit_ss=0., max_deviation=0.)
                      for kind in ('outer', 'inner')}
              for which in ('before', 'after')}
    files = 0
    paths = sorted((before/'audit').glob('*.edges'))
    if {p.name for p in paths} != {p.name for p in (after/'audit').glob('*.edges')}:
        raise ValueError('different source-boundary frame sets')
    for a in paths:
        b = after/'audit'/a.name
        if not b.exists():
            raise ValueError(f'missing matched frame {b}')
        ga, gb = geometry(a), geometry(b)
        if ga.keys() != gb.keys():
            raise ValueError(f'different authored topology: {a.name}')
        for key in ga:
            av, bv = np.array(ga[key]), np.array(gb[key])
            if not np.array_equal(av[:, :2], bv[:, :2]):
                raise ValueError(f'different authored geometry: {a.name}')
            for which, values in [('before', av), ('after', bv)]:
                kind = 'outer' if values[0, 3] else 'inner'
                t = totals[which][kind]
                t['max_deviation'] = max(t['max_deviation'], float(np.abs(values[:, 2]-values[:, 1]).max()))
                if len(values) < 3:
                    continue
                dy = np.diff(values[:, 0])
                eligible = (dy[:-1] <= 4) & (dy[1:] <= 4)
                for field, name in [(1, 'raw_ss'), (2, 'fit_ss')]:
                    slopes = np.diff(values[:, field])/dy
                    d2 = 2*np.diff(slopes)/(dy[1:]+dy[:-1])
                    t[name] += float(np.square(d2[eligible]).sum())
                t['count'] += int(eligible.sum())
        files += 1
    for which in totals.values():
        for t in which.values():
            for k in ('raw', 'fit'):
                t[k+'_rms_d2'] = (t.pop(k+'_ss')/max(t['count'], 1))**.5
    presented = {}
    for which, directory in [('before', before), ('after', after)]:
        count, ss, deviation, rows = 0, 0., 0., 0
        for path in sorted((directory/'audit').glob('*.nxroad')):
            h, r = load_nx(path)
            if not len(r):
                continue
            scale = h['scale']
            y = r['line']*scale+r['sub']
            good = (np.diff(y) == 1) & (np.diff(r['band']) == 0)
            good2 = good[:-1] & good[1:]
            weight = np.abs((r['sub']+.5)/scale-.5)*(r['neighbour'] != 0)
            for side in ('l', 'r'):
                edge = r['e'+side+'_x256']/256
                authored = r['own_'+side]+weight*(r['nb_'+side]-r['own_'+side])
                deviation = max(deviation, float(np.abs(edge-authored).max()))
                d2 = np.diff(edge, n=2)*scale*scale
                ss += float(np.square(d2[good2]).sum())
                count += int(good2.sum())
            rows += len(r)
        presented[which] = dict(rows=rows, count=count, rms_d2=(ss/max(count, 1))**.5,
                                max_deviation_from_interpolated_authored=deviation)
    if not files:
        raise ValueError('no matched .edges files')
    if any(t['max_deviation'] > NX_FIT_LIMIT+1e-7 for t in totals['after'].values()):
        raise ValueError('fitted source boundary exceeds authored envelope')
    if presented['after']['max_deviation_from_interpolated_authored'] > NX_FIT_LIMIT+1/256:
        raise ValueError('presented silhouette exceeds interpolated authored envelope')
    return dict(frames=files, units='native pixels / native row squared',
                source_boundaries=totals, presented_silhouettes=presented)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('before', type=Path)
    p.add_argument('after', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    result = measure(a.before, a.after)
    a.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
