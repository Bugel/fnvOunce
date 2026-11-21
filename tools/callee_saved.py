#!/usr/bin/env python3
"""Which lifted functions keep the x86 callee-saved registers (ebx, esi, edi, ebp) for their caller, and which read
one of them as an input. Coverage report over existing shards: python tools/callee_saved.py out/recomp/recomp_*.cpp

A function preserves register R when, on every path, R is either never written, or saved with PUSH(s.R) before its
first write and restored with s.R = POP() before each return, with every call it makes going to a function that
preserves R too (a callee that clobbers R clobbers it for us). Calls through a pointer and tail jumps count as
clobbering unless the target is known and preserves it.

A function reads R as an input when R is read before it is written or saved on some path, or it calls (directly)
a function that does while R still holds the caller's value.

Both are worked out over the whole program, iterating to a fixed point (recursion: assume the best, then refine).
"""
import re
import sys

import stack_slots as ss

REGS = ('ebx', 'esi', 'edi', 'ebp')
CALL_RE = re.compile(r'\b(RCALL|RJMP)\((fl?)_([0-9a-f]{8})')
ANY_CALL_RE = re.compile(r'\b(RCALLI|TAILCALL|RCALL|RJMP)\(')


def scan(body, r):
    """(writes R unsaved?, reads R first?, direct callees in order with whether R was still the caller's value)
    in a linear walk of the text: conservative for branches because a save is a push at the top and the restores
    sit before each return"""
    tok_read = re.compile(r'\bs\.%s\b' % r)
    lines = body.split('\n')
    saved = False
    written = False
    read_first = False
    calls = []                                  # (callee, R still the caller's value)
    pushes_seen = False
    for l in lines:
        c = re.sub(r'\s*//.*$', '', l)
        if not c.strip():
            continue
        if re.search(r'PUSH\(s\.%s\);' % r, c) and not written and not saved:
            saved = True
            continue
        if re.search(r's\.%s = \(uint32_t\)\(POP\(\)\);' % r, c):
            continue                            # the restore (or a pop into R: written, see below)
        for m in CALL_RE.finditer(c):
            calls.append((m.group(3), not written))
        if re.search(r'\bs\.%s = ' % r, c):
            # a read of R on the right side happens first
            rhs = c.split('s.%s = ' % r, 1)[1]
            if tok_read.search(rhs) and not written and not saved:
                read_first = True
            written = True
            continue
        if tok_read.search(c) and not written and not saved:
            read_first = True
    return written and not saved, read_first, calls


def analyze(texts, abi_indirect=True):
    """{addr: (set of preserved regs, set of input regs)}. abi_indirect: a call through a pointer keeps the four
    registers and reads none (the x86 calling convention compiled code follows; FNV_CALLEE_CHECK verifies it)"""
    info = {}
    for a, t in texts.items():
        m = ss.FUNC_RE.match(t)
        if not m:
            continue
        body = m.group(2)
        unknown_calls = False if abi_indirect else bool(re.search(r'\b(RCALLI|TAILCALL)\(', body))
        per = {}
        for r in REGS:
            per[r] = scan(body, r)
        info['%08x' % a] = (per, unknown_calls)
    keeps = {a: set(REGS) for a in info}
    inputs = {a: set() for a in info}
    changed = True
    while changed:
        changed = False
        for a, (per, unknown) in info.items():
            for r in REGS:
                clobbers, read_first, calls = per[r]
                k = not clobbers and not unknown and all(c in keeps and r in keeps[c] for c, _ in calls)
                if not k and r in keeps[a]:
                    keeps[a].discard(r)
                    changed = True
                inp = read_first or any(live and (c not in inputs or r in inputs[c]) for c, live in calls)
                if inp and r not in inputs[a]:
                    inputs[a].add(r)
                    changed = True
    return keeps, inputs


def main(paths):
    texts = {}
    for p in paths:
        for m in ss.FUNC_RE.finditer(open(p).read()):
            texts[int(m.group(1)[2:], 16)] = 'void %s(FnvCpu& s_)\n{\n%s\n}' % (m.group(1), m.group(2))
    keeps, inputs = analyze(texts)
    n = len(keeps)
    for r in REGS:
        print('%s: kept by %d of %d functions, an input of %d' % (
            r, sum(1 for a in keeps if r in keeps[a]), n, sum(1 for a in inputs if r in inputs[a])))
    full = sum(1 for a in keeps if keeps[a] == set(REGS) and not inputs[a])
    print('keep all four and read none: %d' % full)


if __name__ == '__main__':
    main(sys.argv[1:])
