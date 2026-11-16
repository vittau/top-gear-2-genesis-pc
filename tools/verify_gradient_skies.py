#!/usr/bin/env python3
"""Task 42 private headless captures; one runtime, ports 4740–4749 only.

Captures follow real password/menu input; later slots use the documented
setup-only selector from readme_shots. Outputs are ROM-derived, under build/.
"""
from pathlib import Path
import argparse
import json
from tg2_runner import Runner, manifest_counts
from readme_shots import enter_race
from PIL import Image
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
CASES = {0:'day-auckland',2:'night-canterbury',60:'night-vegas',19:'nightrain-paris',
         20:'rain-bavaria',3:'storm-sydney',23:'snow-munich',4:'fog-lochness',33:'overcast-galway'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=ROOT/'build/task42/classes')
    p.add_argument('--port',type=int,default=4740)
    p.add_argument('--indices',default=','.join(map(str,CASES)))
    a=p.parse_args()
    if not 4740<=a.port<=4749: p.error('use port 4740–4749')
    results=[]
    for idx in map(int,a.indices.split(',')):
        out=(a.out/CASES[idx]).resolve();out.mkdir(parents=True,exist_ok=True)
        r=Runner(port=a.port,out=out,widescreen='16:9',max_frames=0,
                 env_extra={'TG2_GRADIENT_SKIES':'1','TG2_RACE_60FPS':'0','TG2_HIGHRES_SCALE':'1','SDL_RENDER_VSYNC':'0'},
                 extra_args=['--measure-runtime','20000','--runtime-uncapped'])
        r.start()
        try:
            st,_=enter_race(r,out,idx//4,idx%4)
            if st is None: raise RuntimeError('no race')
            r.wait_frame(r.frame()+180)
            path=out/'on.png'
            for attempt in range(300):
                _,info=r.command_many([('screenshot',dict(path=str(path))),('tg2_video',dict(rows=1))])
                if info['sky_live']==info['sky_base']: break
                if not (out/'flash.png').exists():
                    path.replace(out/'flash.png')
                    (out/'flash.json').write_text(json.dumps(info,indent=1)+'\n')
                r.wait_frame(r.frame()+1)
            else: raise RuntimeError(f'{idx}: no stock palette frame in 300 samples')
            r.command('save_state',path=str(out/'race.state'))
            r.wait_frame(r.frame()+10)
            info.update(index=idx,shot=str(path),frame=r.frame(),cram=r.command('read_cram',addr='0',size=128))
            lo,hi=info['sky_bands'][0]
            image=Image.open(path).convert('RGB')
            first=8 if info['crop'] else 0
            samples=[]
            for y in (lo,round(lo+.6*(hi-lo)),hi):
                row=list(image.crop((0,y-first,image.width,y-first+1)).getdata())
                samples.append(Counter(row).most_common(1)[0][0])
            refs=[int(v) for v in info['sky_stops']]
            delta=max(abs(c-((ref>>shift)&255)) for rgb,ref in zip(samples,refs)
                      for c,shift in zip(rgb,(16,8,0)))
            info.update(measured_stops=samples,max_channel_error=delta)
            assert info['sky_pixels']>0 and info['sky_live']==info['sky_base'],info
            assert delta<=2,(idx,samples,refs,delta)
            (out/'capture.json').write_text(json.dumps(info,indent=1)+'\n')
        finally:
            r.proc.wait(timeout=60)
            code=r.stop();counts=manifest_counts(out)
        if code or any(x!=0 for x in counts.values()): raise RuntimeError((idx,code,counts))
        results.append(dict(exit=code,manifests=counts,**{k:v for k,v in info.items() if k!='rows'}))
        (a.out/'summary.json').write_text(json.dumps(results,indent=1)+'\n')
        print(json.dumps(results[-1]),flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
