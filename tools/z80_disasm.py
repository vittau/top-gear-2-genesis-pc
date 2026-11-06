#!/usr/bin/env python3
"""Small Z80 disassembler for reading a cartridge sound driver image.

Covers the plain (non-prefixed) instruction set plus the CB/ED forms these
drivers use; unknown opcodes print `db`. It is a bring-up aid only.

  python3 tools/z80_disasm.py <bin> <file-offset> <base-addr> <bytes>
"""
import sys

R8 = ['b', 'c', 'd', 'e', 'h', 'l', '(hl)', 'a']
RP = ['bc', 'de', 'hl', 'sp']
RP2 = ['bc', 'de', 'hl', 'af']
CC = ['nz', 'z', 'nc', 'c', 'po', 'pe', 'p', 'm']
ALU = ['add a,', 'adc a,', 'sub ', 'sbc a,', 'and ', 'xor ', 'or ', 'cp ']
CB_FIRST = ['rlc', 'rrc', 'rl', 'rr', 'sla', 'sra', 'sll', 'srl']
CB_GROUP = ['rot', 'bit', 'res', 'set']


def dis(data, base):
    i, n = 0, len(data)
    lines = []
    while i < n:
        start = i
        here = base + i

        def b(k=0):
            return data[i + k] if i + k < n else 0

        def w(k=0):
            return b(k) | (b(k + 1) << 8)

        def rel(k):
            d = b(k)
            return base + i + k + 1 + (d - 256 if d > 127 else d)

        op = b()
        i += 1
        t = None
        if op == 0xCB:
            x = b(); i += 1
            grp, idx, reg = x >> 6, (x >> 3) & 7, x & 7
            if grp == 1:
                t = 'bit %d,%s' % (idx, R8[reg])
            else:
                t = '%s %s' % (CB_FIRST[idx] if grp == 0 else CB_GROUP[grp], R8[reg])
        elif op == 0xED:
            x = b(); i += 1
            ed = {0x56: 'im 1', 0x5E: 'im 2', 0x57: 'ld a,i', 0x5F: 'ld a,r',
                  0x4B: 'ld bc,(%04X)' % w(0), 0x5B: 'ld de,(%04X)' % w(0),
                  0x43: 'ld (%04X),bc' % w(0), 0x53: 'ld (%04X),de' % w(0),
                  0xB0: 'ldir', 0xB8: 'lddr', 0x67: 'rrd', 0x6F: 'rld',
                  0x44: 'neg', 0x45: 'retn', 0x4D: 'reti'}
            t = ed.get(x, 'db ED %02X' % x)
            if x in (0x4B, 0x5B, 0x43, 0x53):
                i += 2
        elif 0x40 <= op <= 0x7F:
            t = 'halt' if op == 0x76 else 'ld %s,%s' % (R8[(op >> 3) & 7], R8[op & 7])
        elif 0x80 <= op <= 0xBF:
            t = ALU[(op >> 3) & 7] + R8[op & 7]
        elif op == 0x00:
            t = 'nop'
        elif op == 0x08:
            t = "ex af,af'"
        elif op == 0x10:
            t = 'djnz %04X' % rel(0); i += 1
        elif op in (0x18, 0x20, 0x28, 0x30, 0x38):
            cc = {0x18: '', 0x20: 'nz', 0x28: 'z', 0x30: 'nc', 0x38: 'c'}[op]
            t = ('jr %s,%04X' % (cc, rel(0))).replace('jr ,', 'jr ')
            i += 1
        elif op in (0x01, 0x11, 0x21, 0x31):
            t = 'ld %s,%04X' % (RP[(op >> 4) & 3], w(0)); i += 2
        elif op == 0x0A:
            t = 'ld a,(bc)'
        elif op == 0x1A:
            t = 'ld a,(de)'
        elif op == 0x36:
            t = 'ld (hl),%02X' % b(0); i += 1
        elif op == 0x3A:
            t = 'ld a,(%04X)' % w(0); i += 2
        elif op == 0x32:
            t = 'ld (%04X),a' % w(0); i += 2
        elif op in (0x3E, 0x06, 0x0E, 0x16, 0x1E, 0x26, 0x2E):
            names = {0x3E: 'a', 0x06: 'b', 0x0E: 'c', 0x16: 'd', 0x1E: 'e', 0x26: 'h', 0x2E: 'l'}
            t = 'ld %s,%02X' % (names[op], b(0)); i += 1
        elif op == 0x02:
            t = 'ld (bc),a'
        elif op == 0x12:
            t = 'ld (de),a'
        elif op == 0x22:
            t = 'ld (%04X),hl' % w(0); i += 2
        elif op == 0x2A:
            t = 'ld hl,(%04X)' % w(0); i += 2
        elif op in (0x03, 0x13, 0x23, 0x33):
            t = 'inc ' + RP[(op >> 4) & 3]
        elif op in (0x0B, 0x1B, 0x2B, 0x3B):
            t = 'dec ' + RP[(op >> 4) & 3]
        elif op in (0x04, 0x0C, 0x14, 0x1C, 0x24, 0x2C, 0x34, 0x3C):
            t = 'inc ' + R8[(op >> 3) & 7]
        elif op in (0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D):
            t = 'dec ' + R8[(op >> 3) & 7]
        elif op in (0x07, 0x0F, 0x17, 0x1F, 0x27, 0x2F, 0x37, 0x3F):
            t = {0x07: 'rlca', 0x0F: 'rrca', 0x17: 'rla', 0x1F: 'rra',
                 0x27: 'daa', 0x2F: 'cpl', 0x37: 'scf', 0x3F: 'ccf'}[op]
        elif op in (0xC0, 0xC8, 0xD0, 0xD8, 0xE0, 0xE8, 0xF0, 0xF8):
            t = 'ret ' + CC[(op >> 3) & 7]
        elif op in (0xC2, 0xCA, 0xD2, 0xDA, 0xE2, 0xEA, 0xF2, 0xFA):
            if op == 0xE2:
                t = 'jp (c)'
            else:
                t = 'jp %s,%04X' % (CC[(op >> 3) & 7], w(0)); i += 2
        elif op == 0xC3:
            t = 'jp %04X' % w(0); i += 2
        elif op in (0xC4, 0xCC, 0xD4, 0xDC, 0xE4, 0xEC, 0xF4, 0xFC):
            t = 'call %s,%04X' % (CC[(op >> 3) & 7], w(0)); i += 2
        elif op == 0xCD:
            t = 'call %04X' % w(0); i += 2
        elif op in (0xC5, 0xD5, 0xE5, 0xF5):
            t = 'push ' + RP2[(op >> 4) & 3]
        elif op in (0xC1, 0xD1, 0xE1, 0xF1):
            t = 'pop ' + RP2[(op >> 4) & 3]
        elif op == 0xC9:
            t = 'ret'
        elif op == 0xC7 or op == 0xCF or op == 0xD7 or op == 0xDF or op == 0xE7 or op == 0xEF or op == 0xF7 or op == 0xFF:
            t = 'rst %02X' % (op & 0x38)
        elif op == 0xE9:
            t = 'jp (hl)'
        elif op == 0xD3:
            t = 'out (%02X),a' % b(0); i += 1
        elif op == 0xDB:
            t = 'in a,(%02X)' % b(0); i += 1
        elif op == 0xF3:
            t = 'di'
        elif op == 0xFB:
            t = 'ei'
        elif op in (0xC6, 0xCE, 0xD6, 0xDE, 0xE6, 0xEE, 0xF6, 0xFE):
            m = {0xC6: 'add a,', 0xCE: 'adc a,', 0xD6: 'sub ', 0xDE: 'sbc a,',
                 0xE6: 'and ', 0xEE: 'xor ', 0xF6: 'or ', 0xFE: 'cp '}[op]
            t = '%s%02X' % (m, b(0)); i += 1
        elif op == 0xE3:
            t = 'ex (sp),hl'
        elif op == 0xEB:
            t = 'ex de,hl'
        elif op in (0x09, 0x19, 0x29, 0x39):
            t = 'add hl,' + RP[(op >> 4) & 3]
        elif op == 0xD9:
            t = 'exx'
        else:
            t = 'db %02X' % op
        raw = ' '.join('%02X' % x for x in data[start:i])
        lines.append('%05X: %-22s ; %s' % (here, t, raw))
    return '\n'.join(lines)


if __name__ == '__main__':
    path, off, base, count = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0), int(sys.argv[4], 0)
    with open(path, 'rb') as f:
        f.seek(off)
        data = f.read(count)
    print(dis(data, base))
