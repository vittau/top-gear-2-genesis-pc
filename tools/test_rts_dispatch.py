#!/usr/bin/env python3
"""Execute synthetic generated C for stack-based RTS tail dispatch (no ROM)."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'segagenesisrecomp/tests/tools'))
import test_stack_skip as support
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--recompiler', type=Path, default=ROOT / 'build/GenesisRecomp')
a = p.parse_args()
harness = support.HARNESS.split('int main(')[0] + r'''
int main(int argc,char **argv) {
    (void)argc;
    g_cpu.A[7]=0xFFFE00; g_cpu.SR=0x2700;
    recomp_call_addr(0x200);
    if (g_cpu.D[0]!=42 || g_cpu.D[1]!=6 ||
        g_cpu.D[3]!=(atoi(argv[1])?0x1234u:0u) ||
        g_cpu.A[7]!=0xFFFE00 || pending) {
        fprintf(stderr,"D0=%u D1=%u D3=%x SP=%x pending=%d\n",
                g_cpu.D[0],g_cpu.D[1],g_cpu.D[3],g_cpu.A[7],pending);
        return 1;
    }
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='tg2-rts-dispatch-') as tmp:
    d = Path(tmp)
    config = support.CONFIG.replace('0x2F0]', '0x2F0, 0x300]')
    (d / 'game.toml').write_text(config)
    (d / 'harness.c').write_text(harness)
    for name, push in [('immediate', '2f3c00000300'), ('address-register', '41f9000003002f08'), ('PEA', '487900000300')]:
        for split in (False, True):
            for mixed in (False, True):
                rom = bytearray(b'\xff' * 0x400)
                rom[:8] = bytes.fromhex('00fffe00 00000200')
                rom[0x100:0x200] = b' ' * 256
                rom[0x100:0x104] = b'SEGA'
                rom[0x200:0x20a] = bytes.fromhex('4eb900000240702a4e75')
                for pc in (0x280, 0x2c0, 0x2e0, 0x2f0):
                    rom[pc:pc+2] = bytes.fromhex('4e75')
                body = bytes.fromhex('7205' + ('3f3c1234' if mixed else '') + push + ('4ef900000280' if split else '4e75'))
                rom[0x240:0x240+len(body)] = body
                target = bytes.fromhex(('361f' if mixed else '') + '52414e75')
                rom[0x300:0x300+len(target)] = target
                (d / 'test.bin').write_bytes(rom)
                support.run([a.recompiler.resolve(), 'test.bin', '--game', 'game.toml', '--output-dir', 'generated'], d)
                sources = sorted((d / 'generated').glob('skip_part*.c')) + [d / 'generated/skip_dispatch.c', d / 'harness.c']
                exe = d / 'check'
                support.run(['cc', '-std=c11', '-O1', '-I', ROOT / 'segagenesisrecomp/runner/include', '-I', ROOT / 'segagenesisrecomp/runner', *sources, '-o', exe], d)
                support.run([exe, str(int(mixed))], d)
                print(f'PASS {name} split={split} mixed-width-data={mixed}', flush=True)
