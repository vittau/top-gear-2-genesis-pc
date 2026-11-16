#!/usr/bin/env python3
"""Compile the production sky colour code and compare all 64 approved stops.

Run under the shared heavy lock. The task document is the reference; no
palette, reference colour or ROM-derived output is generated into Git.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include "tg2_sky.c"
uint8_t g_rom[0x400000],g_ram[65536];
const GVDPRasterRow *tg2v_filter_layers;
int tg2v_crop_top_rows,tg2v_hide_overscan;
int tg2v_window_at(const GVDP *v,int y,int x) {(void)v;(void)y;(void)x;return 0;}
int main(int argc,char **argv) {
    if(argc!=2)return 2;
    FILE *f=fopen(argv[1],"rb");if(!f)return 2;
    if(fread(g_rom,1,0x100000,f)!=0x100000)return 3;fclose(f);
    GVDP v={0};v.reg[16]=0x11;v.reg[2]=0x30;v.reg[4]=7;v.reg[1]=64;
    g_ram[0xF9FE]=0x2C;g_ram[0xF9FF]=0x9D;
    tg2_video_set_gradient_skies(1);
    for(int i=0;i<64;++i) {
        unsigned d=tg2_mem32(0x1B8E8+i*4);
        g_ram[0x241C]=d>>24;g_ram[0x241D]=d>>16;g_ram[0x241E]=d>>8;g_ram[0x241F]=d;
        tg2_sky_begin_row(&v,0,256);
        printf("%d %s %06X %06X %06X\n",i,rules[kind].name,ramp(base_sky,0)&0xFFFFFF,
               ramp(base_sky,.6)&0xFFFFFF,ramp(base_sky,1)&0xFFFFFF);
    }
    return 0;
}
'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=ROOT/'build/task42/colours')
    p.add_argument('--rom',type=Path,default=Path.home()/'roms/genesis/tg2.bin')
    p.add_argument('--cc',default='cc')
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    source=out/'check.c';source.write_text(HARNESS)
    runner=ROOT/'segagenesisrecomp/runner'
    cmd=[a.cc,'-O2',*[f'-I{v}' for v in (ROOT/'game',runner,runner/'include',runner/'external/clowncommon')],str(source),'-lm','-o',str(out/'check')]
    subprocess.run(cmd,check=True)
    result=subprocess.run([str(out/'check'),str(a.rom)],check=True,capture_output=True,text=True)
    refs=[]
    for line in (ROOT/'docs/tasks/42-gradient-skies.md').read_text().splitlines():
        cells=[v.strip().strip('`') for v in line.strip('|').split('|')]
        if len(cells)==8 and cells[0].isdigit() and re.fullmatch(r'#[0-9a-fA-F]{6}',cells[5]):refs.append(cells)
    assert len(refs)==64
    # Owner-approved fog seam correction: its horizon joins the original
    # grey panorama; guard this separately from the document parser.
    assert all(ref[7].lower()=='#929292' for ref in refs if ref[4]=='fog')
    checks=[]
    for line,ref in zip(result.stdout.splitlines(),refs,strict=True):
        i,cls,*stops=line.split()
        delta=max(abs(int(c[k:k+2],16)-int(r[1+k:3+k],16)) for c,r in zip(stops,ref[5:]) for k in (0,2,4))
        checks.append(dict(index=int(i),kind=cls,stops=stops,reference=ref[5:],max_channel_error=delta,ok=cls==ref[4] and delta<=2))
    report=dict(ok=all(c['ok'] for c in checks),max_channel_error=max(c['max_channel_error'] for c in checks),checks=checks)
    (out/'result.json').write_text(json.dumps(report,indent=1)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='checks'}))
    return 0 if report['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
