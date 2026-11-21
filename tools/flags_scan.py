#!/usr/bin/env python3
"""Check that no lifted code reads an x86 arithmetic flag across a call boundary.

fnv_recomp.h's RCALL/RCALLI/RETURN leave the flags out of the FnvCpu (FnvLocal::out_call), so a caller that reads a
flag the callee left behind, or a function that reads one on entry before setting it, would see a stale value. MSVC
never generates either; this proves it for the whole exe from the instruction comments in out/recomp/recomp_*.cpp:

  after every call: each path from the return address must set a flag before reading it
  at every function entry: the same, from the first instruction

Paths follow fall-through and direct jumps. They stop at ret, at a jump to another function's entry (a tail jump keeps
the flags: RJMP/TAILCALL still store them, so the target's own entry check covers it) and at indirect jumps, which
are reported if a flag is still unset there.

usage: python tools/flags_scan.py   (exit status 1 on any finding)
"""
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'out/recomp'
ALL = frozenset('czsop')            # cf zf sf of pf
CC = {'o': 'o', 'no': 'o', 'b': 'c', 'c': 'c', 'nae': 'c', 'ae': 'c', 'nb': 'c', 'nc': 'c', 'e': 'z', 'z': 'z',
      'ne': 'z', 'nz': 'z', 'be': 'cz', 'na': 'cz', 'a': 'cz', 'nbe': 'cz', 's': 's', 'ns': 's', 'p': 'p', 'pe': 'p',
      'np': 'p', 'po': 'p', 'l': 'so', 'nge': 'so', 'ge': 'so', 'nl': 'so', 'le': 'zso', 'ng': 'zso', 'g': 'zso',
      'nle': 'zso'}
WRITE_ALL = {'add', 'sub', 'cmp', 'test', 'and', 'or', 'xor', 'neg', 'adc', 'sbb', 'cmpxchg', 'xadd', 'mul', 'imul',
             'div', 'idiv', 'comiss', 'comisd', 'ucomiss', 'ucomisd', 'popfd', 'popf', 'bsf', 'bsr', 'aaa', 'aas',
             'daa', 'das', 'cmpsb', 'cmpsw', 'cmpsd', 'scasb', 'scasw', 'scasd'}
WRITES = {'inc': 'zsop', 'dec': 'zsop', 'bt': 'c', 'bts': 'c', 'btr': 'c', 'btc': 'c', 'stc': 'c', 'clc': 'c',
          'sahf': 'czsp', 'fcomi': 'czp', 'fcomip': 'czp', 'fucomi': 'czp', 'fucomip': 'czp'}
READS = {'adc': 'c', 'sbb': 'c', 'rcl': 'c', 'rcr': 'c', 'cmc': 'c', 'pushfd': 'czsop', 'pushf': 'czsop',
         'lahf': 'czsp', 'into': 'o'}
# Entries that are not functions, reviewed 2026-11-20: constants that look like code addresses (0x600000, 0x779ff2 is
# a value stored into an object field; nothing calls them) and offsets inside another instruction
NOT_FUNCTIONS = {0x007152d4, 0x00416a81, 0x00caedff, 0x00600000, 0x00779ff2}
LINE = re.compile(r'//\s+([0-9a-f]{8}) ([a-z0-9]+)(?: (.*))?$')
FUNC = re.compile(r'^void f_([0-9a-f]{8})\(FnvCpu& s_\)')
TARGET = re.compile(r'^0x([0-9a-f]+)$')


def effects(mn, ops):
    """(flags read, flags written)"""
    for pre in ('rep ', 'repe ', 'repne ', 'lock '):
        if mn + ' ' == pre and ops:
            mn, _, ops = ops.partition(' ')
    if mn.startswith('j') and mn[1:] in CC:
        return set(CC[mn[1:]]), set()
    for p in ('set', 'cmov', 'fcmov'):
        if mn.startswith(p) and mn[len(p):] in CC:
            return set(CC[mn[len(p):]]), set()
    if mn.startswith('fcmov'):                     # fcmovb/fcmove/fcmovbe/fcmovu and their n forms
        return set({'b': 'c', 'e': 'z', 'be': 'cz', 'u': 'p'}[mn[5:].lstrip('n')]), set()
    r = set(READS.get(mn, ''))
    if mn in WRITE_ALL:
        return r, set(ALL)
    if mn in WRITES:
        return r, set(WRITES[mn])
    if mn in ('shl', 'shr', 'sar', 'sal', 'rol', 'ror', 'shld', 'shrd', 'rcl', 'rcr'):
        cnt = (ops or '').split(',')[-1].strip()
        if cnt == 'cl':                            # a zero count leaves every flag alone
            return r, set()
        if mn in ('rol', 'ror', 'rcl', 'rcr'):
            return r, {'c', 'o'}
        return r, set(ALL)
    return r, set()


def main():
    ins = {}                                       # addr -> (mnemonic, operands)
    entries = set()
    nxt = {}                                       # fall-through, in the function body's own order (the global
    for f in sorted(OUT.glob('recomp_[0-9][0-9].cpp')):    # address order mixes in bytes decoded at other offsets)
        prev = None
        for line in f.read_text(errors='replace').splitlines():
            m = FUNC.match(line)
            if m:
                entries.add(int(m.group(1), 16))
                prev = None
                continue
            m = LINE.search(line)
            if m:
                a = int(m.group(1), 16)
                ins[a] = (m.group(2), (m.group(3) or '').strip())
                if prev is not None and prev < a:
                    nxt.setdefault(prev, a)
                prev = a
    print('%d instructions, %d entries' % (len(ins), len(entries)))

    findings, unresolved = [], []

    def walk(start, origin, kind):
        """depth-first from start with every flag unset; report a read of an unset flag"""
        seen = {}
        stack = [(start, frozenset(ALL))]
        while stack:
            a, unset = stack.pop()
            while True:
                if a not in ins:
                    break
                prev = seen.get(a)
                if prev is not None and unset <= prev:
                    break
                seen[a] = unset | prev if prev else unset
                mn, ops = ins[a]
                rd, wr = effects(mn, ops)
                bad = rd & unset
                if bad:
                    findings.append((kind, origin, a, mn, ops, ''.join(sorted(bad))))
                    break
                unset = unset - wr
                if not unset:
                    break
                if mn in ('ret', 'retn', 'iretd', 'hlt', 'ud2', 'int3'):
                    break
                if mn == 'jmp' or (mn.startswith('j') and mn[1:] in CC) or mn in ('jecxz', 'loop', 'loope', 'loopne'):
                    t = TARGET.match(ops)
                    if not t:
                        unresolved.append((kind, origin, a, mn, ops, ''.join(sorted(unset))))
                        break
                    tgt = int(t.group(1), 16)
                    if tgt not in entries or tgt == start:
                        stack.append((tgt, unset))
                    if mn == 'jmp':
                        break
                if a not in nxt:
                    break
                a = nxt[a]

    calls = 0
    for a, (mn, ops) in ins.items():
        if mn == 'call' and a in nxt:
            calls += 1
            walk(nxt[a], a, 'after call')
    for e in entries - NOT_FUNCTIONS:
        walk(e, e, 'entry')
    print('%d call sites, %d entries checked' % (calls, len(entries)))
    for k, o, a, mn, ops, fl in findings[:60]:
        print('READ  %-10s from %08x: %08x %s %s reads %s' % (k, o, a, mn, ops, fl))
    for k, o, a, mn, ops, fl in [u for u in unresolved if "*" in u[4] or "+" in u[4]][:20]:
        print('UNRES %-10s from %08x: %08x %s %s with %s unset' % (k, o, a, mn, ops, fl))
    print('%d reads of an unset flag, %d indirect jumps with flags unset' % (len(findings), len(unresolved)))
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
