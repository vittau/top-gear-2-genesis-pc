#!/usr/bin/env python3
"""Summarise TG2_ACTOR_LOG streams (game/tg2_actors.c) for the S4 LOD policy.

Reads the stream line by line (never whole-file), groups mapper entries by
object kind/record and prints: the depth->model tables, each record's model
ladder (size per model), the scale range each model is used at, and checks of
the sub-pixel projection reading against the guest's own integer results.
Usage: analyze_actors.py LOG [LOG...] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

CAR_RECORDS = 0xFF8E94


def s16(v):
    return v - 65536 if v >= 32768 else v


def analyze(path: Path):
    tables, defs, models = {}, {}, defaultdict(dict)
    groups = defaultdict(lambda: dict(count=0, paths=defaultdict(int), special=defaultdict(int),
                                      models=defaultdict(lambda: dict(n=0, scale=[1 << 30, 0], depth=[1 << 30, 0],
                                                                      types=defaultdict(int), headers=defaultdict(int)))))
    checks = dict(objects=0, path1=0, path2=0, path0=0, y_ok=0, y_bad=0, y_clamped=0,
                  frac_nonzero=0, yfrac_nonzero=0, y_examples=[])
    last = None
    frames = set()
    with path.open() as f:
        for line in f:
            p = line.rstrip('\n').split(',')
            tag = p[0]
            if tag == 'T':
                tables.setdefault((int(p[2]), p[3]), [int(v) for v in p[4:]])
            elif tag == 'D':
                defs[p[2]] = dict(art=p[3], map=p[4], attr=p[5], frame=int(p[1]))
            elif tag == 'M':
                hdrs = []
                for h in p[4:]:
                    if h == 'bad':
                        hdrs.append('bad')
                        continue
                    v = h.split(':')
                    hdrs.append(dict(set=int(v[0]), halfw=int(v[1]), height=int(v[2]), attr=v[3],
                                     pieces=int(v[4]), box=[int(x) for x in v[5:9]],
                                     tiles=[int(v[9]), int(v[10])]))
                models[p[1]][int(p[2])] = hdrs
            elif tag == 'O':
                (frame, kind, special, record, pth, type_in, model, depth2, frac, xi, xf, yi, yproj,
                 yf, scale4, scale0, h, shift, clip, ymax, bias, prio, sat, hud) = p[1:25]
                frames.add(int(frame))
                pth, model, scale4, scale0 = int(pth), int(model), int(scale4), int(scale0)
                car = int(record, 16) >= CAR_RECORDS
                key = ('car' if car else 'kind') + ':' + kind + ':' + record
                g = groups[key]
                g['count'] += 1
                g['paths'][pth] += 1
                g['special'][special] += 1
                m = g['models'][model]
                m['n'] += 1
                m['types'][int(type_in)] += 1
                if pth:
                    sc = scale4 / 4.0
                    m['scale'][0] = min(m['scale'][0], sc)
                    m['scale'][1] = max(m['scale'][1], sc)
                    d = int(depth2) // 2
                    m['depth'][0] = min(m['depth'][0], d)
                    m['depth'][1] = max(m['depth'][1], d)
                checks['objects'] += 1
                checks[f'path{pth}'] += 1
                if pth:
                    if int(xf):
                        checks['frac_nonzero'] += 1
                    if pth == 1 and int(yf):
                        checks['yfrac_nonzero'] += 1
                    # The reading of $B4E2..$B514: final y = projected y (clamped
                    # to ymax-2) - ((h*scale0)>>16 >> shift) - kind $82 term.
                    y = int(yproj)
                    lim = int(ymax) - 2
                    if pth == 1 and (y & 0xFFFF) >= (lim & 0xFFFF):
                        y = lim
                        checks['y_clamped'] += 1
                    hh = int(h)
                    if hh:
                        y -= s16(((hh * s16(scale0)) >> 16) & 0xFFFF) >> int(shift)
                    if kind == '82':
                        t = scale0 >> 5
                        y -= t + (t >> 1)
                    if y == int(yi):
                        checks['y_ok'] += 1
                    else:
                        checks['y_bad'] += 1
                        if len(checks['y_examples']) < 6:
                            checks['y_examples'].append(line.strip())
                last = m
            elif tag == 'H' and last is not None:
                last['headers'][(int(p[2]), int(p[3]), p[4])] += 1
    return dict(path=str(path), frames=len(frames), tables=tables, defs=defs, models=models,
                groups=groups, checks=checks)


def report(a):
    print(f"== {a['path']}: {a['frames']} frames, checks {json.dumps({k: v for k, v in a['checks'].items()})}")
    for (which, ptr), values in sorted(a['tables'].items()):
        print(f"  depth table {'cars' if which else 'scenery'} @{ptr}: {values[:72]}")
    for key in sorted(a['groups']):
        g = a['groups'][key]
        record = key.split(':')[2]
        d = a['defs'].get(record, {})
        print(f"  {key} n={g['count']} paths={dict(g['paths'])} special={dict(g['special'])} "
              f"art={d.get('art')} map={d.get('map')} attr={d.get('attr')}")
        for model in sorted(g['models']):
            m = g['models'][model]
            hdr = a['models'].get(record, {}).get(model)
            size = ''
            if hdr and hdr[0] != 'bad':
                size = ' '.join(f"[hw{h['halfw']} h{h['height']} a{h['attr']} p{h['pieces']} "
                                f"box{h['box']} t{h['tiles'][0]}-{h['tiles'][1]}]" for h in hdr if h != 'bad')
            ratio = ''
            if hdr and hdr[0] != 'bad' and m['scale'][1]:
                ratio = f" h/scale={hdr[0]['height'] / m['scale'][1]:.4f}..{hdr[0]['height'] / max(m['scale'][0], 1):.4f}"
            print(f"    model {model:2d} n={m['n']:6d} types={dict(m['types'])} depth={m['depth']} "
                  f"scale={m['scale']}{ratio} {size}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('logs', nargs='+', type=Path)
    p.add_argument('--json', type=Path)
    args = p.parse_args()
    out = []
    for path in args.logs:
        a = analyze(path)
        report(a)
        out.append(a)
    if args.json:
        def clean(o):
            if isinstance(o, dict):
                return {str(k): clean(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [clean(v) for v in o]
            return o
        args.json.write_text(json.dumps(clean(out), indent=1))


if __name__ == '__main__':
    main()
