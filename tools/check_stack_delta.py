#!/usr/bin/env python3
"""Cross-check the recompiler's stack-delta accounting against the ROM.

The generated C keeps a path-local guest stack counter (`_sp_popped`, carried
into split-function tails through `g_split_sp_popped`). An RTS whose total is
negative means "the guest left a jump target on the stack" (MOVE.L #target,-(SP);
RTS) and is dispatched instead of returning to the native caller, so the counter
must be exact: *every* instruction that moves the guest stack has to be
accounted, whatever its mnemonic.

Task 24 was exactly that gap: only the MOVE/MOVEA/MOVEM/PEA forms and
`ADDQ/SUBQ #n,SP` were credited, so `ADD.W (SP)+,Dn` popped a word the counter
never saw. Top Gear 2's func $7336 pushes/pops a word sixteen times per call and
the drift (-32) turned its ordinary RTS into a dispatch to the $650C return
slot, skipping the scene-init continuation.

This tool re-derives the expected delta from the ROM with capstone (the
project's ground-truth disassembler, `tools/disasm_tg2.py`) and checks it
against the emitted `_sp_popped` line for every instruction the generator
printed. It is intentionally an independent implementation: the recompiler uses
its own decoder and its own rule, so a mnemonic the generator forgets (or
double-counts) shows up here.

    python3 tools/check_stack_delta.py [--generated build/generated/tg2] \
        [--rom ~/roms/genesis/tg2.bin]

Exit codes: 0 all accounted, 1 mismatches, 2 environment error.

Requires capstone: `python3 -m venv /tmp/dis-venv && /tmp/dis-venv/bin/pip
install capstone` (the same dependency as tools/disasm_tg2.py). Run it after
every regeneration, and always after touching the code generator's stack
bookkeeping or `patches/segagenesisrecomp/core-0004-exact-stack-delta.patch`.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Control flow owns its return slot explicitly (recomp_push_return / the RTS
# epilogue), so the generator must not account it here.
CONTROL = {
    'rts', 'rte', 'rtr', 'jsr', 'bsr', 'jmp', 'bra', 'nop', 'stop', 'reset',
    'trap', 'trapv', 'illegal', 'link', 'unlk',
}
COND = re.compile(r'^(b[a-z]{2}|db[a-z]{2})(\.[bwl])?$')

INSTR = re.compile(r'/\* \$([0-9A-Fa-f]{6}) \*/')
DELTA = re.compile(r'_sp_popped\s*([+-])=\s*(\d+)')


def size_step(mnemonic: str) -> int:
    """Bytes the stack moves for one operand of this instruction."""
    return 4 if mnemonic.endswith('.l') else 2


def reg_count(field: str) -> int:
    """Number of registers in a capstone register-list operand."""
    total = 0
    for part in field.split('/'):
        part = part.strip()
        if '-' in part:
            lo, hi = part.split('-')
            total += abs(int(hi[1:]) - int(lo[1:])) + 1
        elif part:
            total += 1
    return total


def expected_delta(ins) -> int:
    """Independent derivation of the guest stack delta for one instruction."""
    mnemonic = ins.mnemonic.lower()
    if mnemonic in CONTROL or COND.match(mnemonic):
        return 0
    step = size_step(mnemonic)
    ops = [o.strip() for o in ins.op_str.split(',')] if ins.op_str else []

    if mnemonic == 'pea':
        return -4

    if mnemonic in ('addq', 'subq'):
        if len(ops) == 2 and ops[1] == 'sp':
            value = int(ops[0].lstrip('#$'), 0)
            return value if mnemonic == 'addq' else -value
        return 0

    if mnemonic.startswith('movem'):
        mem = next((o for o in ops if '(sp)' in o or '(a7)' in o), None)
        regs = next((o for o in ops if o is not mem), '')
        if mem is None:
            return 0
        flat = mem.replace(' ', '')
        if flat.endswith('(sp)+') or flat.endswith('(a7)+'):
            return reg_count(regs) * step
        if flat.startswith('-(sp)') or flat.startswith('-(a7)'):
            return -reg_count(regs) * step
        return 0

    delta = 0
    for op in ops:
        flat = op.replace(' ', '')
        if flat.endswith('(sp)+') or flat.endswith('(a7)+'):
            delta += step
        elif flat.startswith('-(sp)') or flat.startswith('-(a7)'):
            delta -= step
    return delta


def blocks(text: str):
    """Yield (address, body) for each emitted instruction block."""
    marks = list(INSTR.finditer(text))
    for i, match in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[match.end():end]
        stop = body.find('label_')
        if stop >= 0:
            body = body[:stop]
        yield int(match.group(1), 16), body


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--generated', type=Path, default=ROOT / 'build/generated/tg2')
    ap.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    try:
        from capstone import Cs, CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000
    except ImportError:
        print('check_stack_delta: capstone is required (see tools/disasm_tg2.py)',
              file=sys.stderr)
        return 2
    if not args.generated.is_dir():
        print(f'check_stack_delta: no generated tree at {args.generated}', file=sys.stderr)
        return 2
    if not args.rom.is_file():
        print(f'check_stack_delta: no ROM at {args.rom}', file=sys.stderr)
        return 2

    data = args.rom.read_bytes()
    md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)

    parts = sorted(args.generated.glob('*_part*.c'))
    if not parts:
        print(f'check_stack_delta: no *_part*.c under {args.generated}', file=sys.stderr)
        return 2

    checked = accounted = 0
    problems = []
    for part in parts:
        for addr, body in blocks(part.read_text(errors='replace')):
            found = DELTA.findall(body)
            ins = next(md.disasm(data[addr:addr + 16], addr), None)
            if ins is None:
                continue
            mnemonic = ins.mnemonic.lower()
            want = expected_delta(ins)
            checked += 1
            if mnemonic in CONTROL or COND.match(mnemonic):
                continue
            have = 0
            for sign, value in found:
                have += int(value) if sign == '+' else -int(value)
            if want == have:
                if found:
                    accounted += 1
                continue
            problems.append((addr, ins.mnemonic, ins.op_str, want, have, part.name))

    for addr, mnemonic, op_str, want, have, part in problems:
        print(f'{part}: ${addr:06X} {mnemonic} {op_str}: '
              f'expected delta {want:+d}, generated {have:+d}')
    print(f'check_stack_delta: {checked} instructions checked, '
          f'{accounted} stack operands accounted, {len(problems)} mismatches')

    if args.verbose and not problems:
        print('every SP-touching instruction matches the ROM')
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
