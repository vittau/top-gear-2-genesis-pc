#!/usr/bin/env python3
"""Bounded 1x country actor inventory, input only and streamed evidence.

Run under flock ~/.cache/tg2-heavy.lock. Password cursor movement is reused
from PasswordUI; assertions verify the actual typed buffer/country/race.
Finite uncapped runtime avoids spending minutes waiting on menus per country.
Only the final 900-frame driving window enters the inventory. This is a
first-race survey, not all four tracks or N x final-SAT qualification.
"""
from __future__ import annotations

import argparse
import json
import struct
import re
from collections import Counter
from pathlib import Path

from tg2_runner import ROOT, Runner, manifest_counts
from tg2_password_ui import PasswordUI, cell_of, CURSOR_END
from tg2_password import encode, ALPHABET
from tg2_qual_coverage import COUNTRIES, NAMES
from check_highres import wait_exit
from actor_sheet import Memory, model_pixels, extent


def password_script(country, out, frames, resume=False):
    lines = ['WAIT 700']
    def tap(key, frames=6, settle=6):
        lines.extend([f'PRESS {key} {frames}', f'WAIT {settle}'])
    tap('START', 8, 250)
    for _ in range(3): tap('DOWN', 6, 60)
    tap('START', 8, 200)
    tap('START', 8, 220)
    lines.append('ASSERT_RAM16 0xFF2594 0xFFFF')
    ui = PasswordUI(None, None)
    ui.tap = tap
    symbols = encode(country=country, stage=0)['symbols']
    codes = []
    for ch in symbols:
        code = ALPHABET.index(ch)+1
        codes.append(code)
        ui.move_to(*cell_of(code))
        tap('A', 6, 40)
    for i in range(0,16,2):
        lines.append(f'ASSERT_RAM16 {0xFF2570+i:#x} {codes[i]*256+codes[i+1]:#x}')
    ui.move_to(*CURSOR_END)
    tap('A', 6, 320)
    lines.append(f'ASSERT_RAM16 0xFF16BE {country*4:#x}')
    for _ in range(12): tap('START', 7, 300)
    if resume: tap('START', 7, 20)
    lines += ['WAIT_RAM16 0xFF01EE 0x4714', 'ASSERT_RAM16 0xFF22FA 0',
              f'DUMP_RAM {out}/start.ram', 'HOLD B', f'WAIT {frames}',
              f'DUMP_RAM {out}/snap.ram', f'DUMP_VRAM {out}/snap.vram',
              f'SCREENSHOT {out}/snap.png', 'WAIT 2', 'EXIT 0']
    script = out/'survey.input'
    script.write_text('\n'.join(lines)+'\n')
    return script


def classify(out, first, last):
    rom = (Path.home()/'roms/genesis/tg2.bin').read_bytes()
    ram = (out/'snap.ram').read_bytes();vram=(out/'snap.vram').read_bytes()
    mem = Memory(rom,ram);player = mem.u16(0xFF17D6)
    by_kind = {}; sizes={}
    source=(ROOT/'game/tg2_actors.c').read_text()
    policy=source.split('static int tabulated(',1)[1].split('\n}',1)[0]
    ordinary={int(v,16) for v in re.findall(r'kind == (0x[0-9A-Fa-f]+)',policy)}
    def bounds(record,model):
        key=(record,model)
        if key not in sizes:
            pixels,_=model_pixels(mem,vram,record,model)
            e=extent(pixels);sizes[key]=None if e is None else (e[2]-e[0],e[3]-e[1])
        return sizes[key]
    with (out/'actors.csv').open() as stream:
        for line in stream:
            if not line.startswith('O,'): continue
            p=line.split(',');frame=int(p[1])
            if frame<first or frame>=last:continue
            kind=int(p[2],16);special=int(p[3],16);record=int(p[4],16)
            path=int(p[5]);guest=int(p[7]);car=record>=0xFF8E94
            k='car' if car and kind==0 else f'{kind:02X}'
            counts=by_kind.setdefault(k,Counter());counts['mapper_calls']+=1
            if not path or special in (0xFFFE,0xFD66) or kind in (0x82,0x83,0x84,0xBD,0x8A,0xF8,0xF9,0xFC,0xFD):
                counts['native_special_or_unprojected']+=1;continue
            if car and special==player:counts['native_player']+=1;continue
            if not car and kind not in ordinary:
                counts['fallback1_untabulated']+=1;continue
            model=0
            if car:
                for row in range(24):
                    values=list(rom[0x57C8+row*9:0x57C8+(row+1)*9])
                    if guest in values:
                        best=min((i for i,v in enumerate(values) if v==guest),key=lambda i:abs(i-4))
                        model=guest if row==0 else rom[0x57C8+(4 if len(set(values))==1 else best)]
                        break
            mapping=mem.u32(mem.u32(record+4)+4*model)&0xFFFFFF
            if not mapping or mapping&1 or not(mapping<0x100000 or mapping>=0xFF0000):
                counts['fallback2_invalid_mapping']+=1;continue
            detailed,small=bounds(record,model),bounds(record,guest)
            if detailed is None:counts['fallback3_empty_art']+=1;continue
            if small and (small[0]/detailed[0] if detailed[0]>=detailed[1] else small[1]/detailed[1])>1:
                counts['fallback4_smaller_detail']+=1;continue
            counts['eligible_ordinary']+=1
    return by_kind


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--country',type=int,required=True,choices=range(16))
    p.add_argument('--frames',type=int,default=900)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    attempts=[]
    for resume in (False,True):
        evidence=out/('resume' if resume else 'initial')
        evidence.mkdir(exist_ok=True)
        script=password_script(a.country,evidence,a.frames,resume)
        r=Runner(out=evidence,port=4494,max_frames=0,widescreen='off',env_extra={
            'TG2_HIGHRES_SCALE':'1','TG2_RACE_60FPS':'0','TG2_ACTOR_LOG':str(evidence/'actors.csv')},
            extra_args=['--measure-runtime','30000','--runtime-uncapped','--input-script',str(script)])
        try:r.start();wait_exit(r,timeout=120)
        finally:code=r.stop()
        log=(evidence/'stderr.log').read_text()
        starts=[int(x) for x in re.findall(r'DUMP_RAM requested at frame (\d+)',log)]
        result=dict(country=a.country,name=COUNTRIES[a.country],track=NAMES[(a.country,0)],
                    exit=code,manifests=manifest_counts(evidence),frames=a.frames,
                    evidence_dir=str(evidence),resume=resume)
        if len(starts)>=2 and (evidence/'snap.ram').exists():
            ram=(evidence/'snap.ram').read_bytes();before=(evidence/'start.ram').read_bytes()
            result.update(start_frame=starts[0],end_frame=starts[1],
                          race_index=struct.unpack_from('>H',ram,0x16BE)[0],
                          position_before=struct.unpack_from('>I',before,0x18CA)[0],
                          position_after=struct.unpack_from('>I',ram,0x18CA)[0])
        result['ok']=code==0 and result.get('race_index')==a.country*4 and \
            result.get('position_before')!=result.get('position_after') and \
            len(starts)>=2 and starts[1]-starts[0]==a.frames and all(v==0 for v in result['manifests'].values())
        attempts.append({k:v for k,v in result.items() if k!='kinds'})
        if result['ok']:
            result['kinds']=classify(evidence,starts[0],starts[1])
            break
        if code!=0:break  # a script/runtime error is not a pause retry
    result['attempts']=attempts
    (out/'survey-summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
