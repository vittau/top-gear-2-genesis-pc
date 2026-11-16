#!/usr/bin/env python3
"""Capture all 64 race skies and audit flat panorama joins (private output).

One fresh process per race follows the real password/setup flow.
Only the documented setup selector writes RAM; race execution stays stock.
Run under flock ~/.cache/tg2-heavy.lock, with Pillow and ports 4740–4749.
"""
from pathlib import Path
import argparse
import json
import struct
from PIL import Image
from tg2_runner import Runner, RaceState, STATE_LO, STATE_LEN, manifest_counts
from readme_shots import enter_race

ROOT = Path(__file__).resolve().parents[1]
DAC = (0,49,87,119,146,174,206,255)

def rgb(word):
    return (DAC[(word>>1)&7],DAC[(word>>5)&7],DAC[(word>>9)&7])

def texel(vram, base, x, y):
    attr=struct.unpack_from('>H',vram,(base+(((y>>3)&63)*64+((x>>3)&63))*2)&65535)[0]
    px=x&7;py=y&7
    if attr&0x800:px^=7
    if attr&0x1000:py^=7
    byte=vram[((attr&2047)*32+py*4+px//2)&65535]
    nib=(byte&15) if px&1 else byte>>4
    return (((attr>>9)&48)|nib) if nib else 0

def references():
    result={}
    for line in (ROOT/'docs/tasks/42-gradient-skies.md').read_text().splitlines():
        c=[v.strip().strip('`') for v in line.strip('|').split('|')]
        if len(c)==8 and c[0].isdigit() and c[5].startswith('#'):
            result[int(c[0])]=dict(track=c[1],kind=c[4],horizon=c[7])
    assert len(result)==64
    return result

def analyse(info, vram, cram, path):
    image=Image.open(path).convert('RGB');w,h=image.size;origin=(w-256)//2
    first=8 if info['crop'] else 0
    base=rgb(info['sky_base']);horizon=tuple((info['sky_stops'][2]>>s)&255 for s in (16,8,0))
    scans=[]
    for y in range(max(first+1,info['sky_bands'][0][1]+1),min(first+h,208)):
        above=info['sky_rows'][y-1]
        py=info['sky_rows'][y][0]
        if py<0 or above[2]==0:continue
        row=info['rows'][y];hb,vb,bb=row[1],row[3],row[5]
        opaque=[];original=[];photo_original=0
        for x in range(w):
            nx=x-origin
            sx=nx-hb
            if not 0<=nx<256 and py<448:
                if py>=432:sx=max(0,min(255,nx))-hb
                else:
                    centre=128+((hb-128+256)&511)-256
                    sx=max(-256,min(255,nx-centre))
            idx=texel(vram,bb,sx,y+vb)
            pixel=image.getpixel((x,y-first))
            non_sky=idx!=0 and not (idx==63 and py>=448)
            same=non_sky and rgb(cram[idx])==base and pixel==base
            opaque.append(non_sky);original.append(same);photo_original+=pixel==base
        count=sum(original)
        scans.append(dict(row=y,above_row=y-1,atlas_y=py,source_region="panorama" if py>=448 else "ground" if py>=432 else "road",above_sky_pixels=above[2],
                          opaque_non_sky=sum(opaque),opaque_original=count,
                          photo_original=photo_original,width=w,
                          opaque_original_percent=round(100*count/w,2)))
    # Highest matching fraction is retained even when it does not reach a
    # majority, to make negative results inspectable and threshold explicit.
    best=max(scans,key=lambda r:(r['opaque_original'],-r['row'])) if scans else None
    structural=[r for r in scans if r['opaque_original']*2>w]
    delta=max(abs(a-b) for a,b in zip(base,horizon))
    return dict(base_rgb=base,horizon_rgb=horizon,max_channel_jump=delta,
                flat_panorama_join=bool(structural),seam=bool(structural and delta>2),
                best=best,joins=structural,scanned_transition_rows=scans)

def capture(r,out,index,refs):
    out.mkdir(parents=True,exist_ok=True)
    # Seek a genuinely flat camera for twelve zero-slope controller samples.
    prev=None;pad=0;flat=0;start=r.frame()
    while r.frame()-start<2800:
        st=r.step(pad)
        lat=st.lat_units;d=0 if prev is None else lat-prev;u=-lat-4*d;prev=lat
        pad=0x10|(0x08 if u>9 else 0x04 if u< -9 else 0)
        flat=flat+1 if st.slope==0 else 0
        if flat>=12:break
    else:raise RuntimeError(f'{index}: no flat camera within 2800 frames')
    path=out/'on.png'
    for attempt in range(400):
        shot,info,dump,cram,ram=r.command_many([
            ('screenshot',dict(path=str(path))),('tg2_video',dict(rows=1)),
            ('dump_vram',dict(path=str(out/'vram.bin'))),
            ('read_cram',{}),('read_ram',dict(addr=f'0x{STATE_LO:04X}',size=STATE_LEN))])
        state=RaceState(bytes.fromhex(ram['hex']),0)
        if state.slope==0 and info['sky_live']==info['sky_base'] and info['sky_pixels']>0:break
        r.step(pad)
    else:raise RuntimeError(f'{index}: no flat stock-palette capture')
    assert info['sky_class']==refs[index]['kind'],(index,info['sky_class'])
    expected=struct.unpack_from('>I',r.rom.read_bytes(),0x1B8E8+index*4)[0]
    assert info['sky_descriptor']==expected,(index,info['sky_descriptor'],expected)
    vr=(out/'vram.bin').read_bytes();cr=struct.unpack('>64H',bytes.fromhex(cram['hex']))
    info.update(index=index,track=refs[index]['track'],slope=state.slope,shot=str(path),cram=list(cr))
    result=dict(index=index,track=refs[index]['track'],kind=info['sky_class'],slope=state.slope,
                band=info['sky_bands'][0],shot=str(path),**analyse(info,vr,cr,path))
    (out/'capture.json').write_text(json.dumps(info,indent=1)+'\n')
    (out/'audit.json').write_text(json.dumps(result,indent=1)+'\n')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=ROOT/'build/task42/seam-audit')
    p.add_argument('--countries',default=','.join(map(str,range(16))))
    p.add_argument('--port',type=int,default=4740)
    p.add_argument('--analyse-only',action='store_true')
    p.add_argument('--resume',action='store_true',help='skip completed captures in this output directory')
    a=p.parse_args();assert 4740<=a.port<=4749
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=True)
    refs=references();results=[]
    summary=a.out/'summary.json'
    if summary.exists() and (a.resume or a.analyse_only):results=json.loads(summary.read_text())['tracks']
    if a.analyse_only:
        refreshed=[]
        for old in results:
            index=old['index'];work=a.out/f'{index:02}'
            info=json.loads((work/'capture.json').read_text())
            counts=manifest_counts(work)
            assert old['exit']==0 and all(v==0 for v in counts.values()),(index,counts)
            updated=dict(index=index,track=old['track'],kind=old['kind'],slope=info['slope'],
                band=info['sky_bands'][0],shot=info['shot'],exit=old['exit'],manifests=counts,
                **analyse(info,(work/'vram.bin').read_bytes(),info['cram'],info['shot']))
            (work/'audit.json').write_text(json.dumps(updated,indent=1)+'\n');refreshed.append(updated)
        summary.write_text(json.dumps(dict(tracks=refreshed,flagged=[v['index'] for v in refreshed if v['seam']]),indent=1)+'\n')
        print(json.dumps(dict(tracks=len(refreshed),flagged=[v['index'] for v in refreshed if v['seam']])))
        return 0
    indices=[country*4+slot for country in map(int,a.countries.split(',')) for slot in range(4)]
    for index in indices:
        country,slot=divmod(index,4)
        if any(v['index']==index for v in results):continue
        work=a.out/f'{index:02}';work.mkdir(exist_ok=True)
        r=Runner(port=a.port,out=work,widescreen='16:9',max_frames=0,
                 env_extra={'TG2_GRADIENT_SKIES':'1','TG2_RACE_60FPS':'0','TG2_HIGHRES_SCALE':'1'},
                 extra_args=['--measure-runtime','16000','--runtime-uncapped'])
        r.start()
        try:
            st,cov=enter_race(r,work,country,slot)
            if st is None:raise RuntimeError(f'{index}: no race')
            r.wait_frame(r.frame()+60)
            result=capture(r,work,index,refs)
        finally:
            r.proc.wait(timeout=90);code=r.stop();counts=manifest_counts(work)
        if code or any(v!=0 for v in counts.values()):raise RuntimeError((index,code,counts))
        result.update(exit=code,manifests=counts)
        results.append(result);results.sort(key=lambda v:v['index'])
        summary.write_text(json.dumps(dict(tracks=results,flagged=[v['index'] for v in results if v['seam']]),indent=1)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k not in ('scanned_transition_rows','joins')}),flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
