#!/usr/bin/env python3
"""Frame slots in locals for functions without a frame pointer (optimized code): a post-pass after tools/stack_slots.py.

Optimized functions address their locals as [esp + N], and esp moves with every push, pop and call. This pass follows
esp's distance below its value on entry (d) through every path and turns each slot of the frame into a C++ local,
like stack_slots.py does for [ebp - N]:

    M32((uint32_t)(0u + s.esp + 0x1cu))  at d = 0x20  ->  entry offset -4  ->  FNV_SL(sl_e_m04, ...)

What d does:
  - push +4, pop -4, sub esp +n, add esp -n, `s.esp += n` (an inlined stdcall import) -n
  - a direct call: -(the bytes the callee's ret pops), known from the callee's RETURN(n) when it has only one kind
  - any other call (indirect, or a callee whose pop is unknown): the callee pops the bytes pushed since the last call,
    or none when an `add esp, k` follows it (cdecl). This is inferred, so the pass also emits a check after each such
    call (FNV_ESPCHK, fnv_recomp.h) that traps if esp is not where the analysis says.
  - every path into a label must agree on d, and every ret must have d = 0; otherwise the function stays as it was.
Which slots: the frame the function sets up on entry (the leading pushes and `sub esp`), offsets [-F, 0), and its
arguments (offsets >= 4). Bytes below the frame are outgoing arguments, read by callees: those stay in memory, as do
slots accessed at more than one offset or size, and everything at or above an address the function hands out
(`lea eax, [esp + N]`, a copy of esp). No tail jumps, exception frames or calls to frame-sharing helpers
(tools/stack_slots.py has the reasons).
"""
import re
import sys

import stack_slots as ss

LABEL_RE = re.compile(r'^\s*(L_[0-9a-f]{8}):\s*$')
GOTO_RE = re.compile(r'goto (L_[0-9a-f]{8});')
ESP_MEM_RE = re.compile(r'\b(M8|M16|M32|MF|M64|MD)\(\(uint32_t\)\(0u \+ s\.esp(?: \+ 0x([0-9a-f]+)u)?\)\)')
ESP_MEM2_RE = re.compile(r'\b(M8|M16|M32|MF|M64|MD)\(s\.esp(?: \+ (\d+))?\)')
ESP_ADDR_RE = re.compile(r'\(0u \+ s\.esp(?: \+ (s\.e[a-z]{2}(?:\*\d)?))?(?: ([+-]) 0x([0-9a-f]+)u)?\)')
ADD_ESP_RE = ss.ADD_ESP_RE
POPN_RE = re.compile(r's\.esp \+= (\d+);')
RCALL_RE = re.compile(r'\bRCALL\((fl?)_([0-9a-f]{8}), (0x[0-9a-f]{8})u\)')
RCALLI_RE = re.compile(r'\bRCALLI\(.*, (0x[0-9a-f]{8})u\);')
RETURN_RE = re.compile(r'\bRETURN\((\d+)\)')
SIZES = ss.SIZES
CTYPE = ss.CTYPE


class NotLocal(Exception):
    pass


def callee_pops(texts):
    """{'%08x': bytes its ret pops} for functions whose every return pops the same amount and that never tail-jump"""
    out = {}
    for a, t in texts.items():
        m = ss.FUNC_RE.match(t)
        if not m or ss.TAIL_RE.search(t):
            continue
        pops = set(int(x) for x in RETURN_RE.findall(m.group(2)))
        if len(pops) == 1:
            out['%08x' % a if isinstance(a, int) else a] = pops.pop()
    return out


def slot_name(off):
    return 'sl_e_%s%02x' % ('p' if off >= 0 else 'm', abs(off))


def code_of(l):
    return re.sub(r'\s*//.*$', '', l)


def analyze(body, pops, helpers=frozenset()):
    """(slots {entry offset: size}, d before each line, setup_end, guarded call lines {k: d after}) or NotLocal"""
    lines = body.split('\n')
    k0 = 0
    while k0 < len(lines) and (ss.HEAD_RE.match(lines[k0]) or not lines[k0].strip()):
        k0 += 1
    if k0 + 1 < len(lines) and lines[k0].strip().startswith('PUSH(s.ebp);') and \
            lines[k0 + 1].strip().startswith('s.ebp = (uint32_t)(s.esp);'):
        raise NotLocal('ebp frame (stack_slots.py)')
    has_tail = bool(ss.TAIL_RE.search(body))      # allowed once the frame is gone (d = 0); arguments then stay in
    if 'fs_base' in body:                           # memory, since the target reads them there
        raise NotLocal('exception frame')
    if helpers and any(c in helpers for c in ss.RCALL_TARGET_RE.findall(body)):
        raise NotLocal('calls a frame-sharing helper')
    if not ESP_MEM_RE.search(body):
        raise NotLocal('no esp slots')
    labels = {}
    for k, l in enumerate(lines):
        m = LABEL_RE.match(l)
        if m:
            labels[m.group(1)] = k
    # the frame: leading pushes and sub esp from the first body line
    k = k0
    F = 0
    while k < len(lines):
        c = code_of(lines[k]).strip()
        m = ADD_ESP_RE.fullmatch(c) if c else None
        if re.fullmatch(r'PUSH\(s\.e[a-z]{2}\);', c):
            F += 4
        elif m and m.group(2) == '-':
            F += int(m.group(1), 16)
        else:
            break
        k += 1
    setup_end = k
    d_at = [None] * (len(lines) + 1)
    pushed_at = [0] * (len(lines) + 1)          # bytes pushed since the last call on this path (argument guess)
    d_at[k0] = 0
    work = [k0]
    accesses = {}                               # entry offset -> set of sizes (promotable candidates)
    fixed = []                                  # (lo, hi) byte ranges accessed in ways that keep them in memory
    escape = None
    guarded = {}

    def flow(k, d, pushed):
        if k >= len(lines):
            return
        if d_at[k] is None:
            d_at[k] = d
            pushed_at[k] = pushed
            work.append(k)
        elif d_at[k] != d:
            raise NotLocal('esp differs where paths meet (line %d: %d vs %d)' % (k, d_at[k], d))
        else:
            pushed_at[k] = min(pushed_at[k], pushed)

    seen = set()
    while work:
        k = work.pop()
        if k in seen:
            continue
        seen.add(k)
        d, pushed = d_at[k], pushed_at[k]
        l = lines[k]
        c = code_of(l)
        if LABEL_RE.match(l) or not c.strip():
            flow(k + 1, d, 0 if LABEL_RE.match(l) else pushed)
            continue
        rest = c
        if '= POP()' in rest and 's.esp' in rest.split('= POP()')[0]:
            raise NotLocal('pop into an esp slot')
        # esp-relative memory, at the depth before this line's pushes and pops
        for mm in ESP_MEM_RE.finditer(rest):
            n = int(mm.group(2), 16) if mm.group(2) else 0
            off, sz = n - d, SIZES[mm.group(1)]
            if -F <= off and off + sz <= 0 or off >= 4:
                accesses.setdefault(off, set()).add(sz)
            elif off < 0 and off + sz > -F:
                fixed.append((off, off + sz))
        for mm in ESP_MEM2_RE.finditer(rest):
            n = int(mm.group(2)) if mm.group(2) else 0
            off = n - d
            fixed.append((off, off + SIZES[mm.group(1)]))
        rest2 = ESP_MEM_RE.sub('ESPMEM', ESP_MEM2_RE.sub('ESPMEM', rest))
        # stack sizes changed by this line
        m = ADD_ESP_RE.search(rest2)
        delta = 0
        if m:
            delta = int(m.group(1), 16) * (1 if m.group(2) == '-' else -1)
            rest2 = rest2.replace(m.group(0), '')
        for mm in POPN_RE.finditer(rest2):
            delta -= int(mm.group(1))
        rest2 = POPN_RE.sub('', rest2)
        # other uses of esp: an address handed out, a copy, or something else
        for mm in ESP_ADDR_RE.finditer(rest2):
            n = int(mm.group(3), 16) * (1 if mm.group(2) != '-' else -1) if mm.group(3) else 0
            off = n - d
            escape = off if escape is None else min(escape, off)
        rest2 = ESP_ADDR_RE.sub('ESC', rest2)
        if re.search(r'= \(uint32_t\)\(s\.esp\);', rest2) or re.search(r'\(s\.esp\)', rest2):
            off = -d                            # the current esp copied: everything from here up
            escape = off if escape is None else min(escape, off)
            rest2 = rest2.replace('(s.esp)', 'ESC')
        if 's.esp' in rest2:
            raise NotLocal('esp used otherwise: ' + l.strip()[-60:])
        npush, npop = rest2.count('PUSH('), rest2.count('POP()')
        delta += 4 * npush - 4 * npop
        pushed2 = max(0, pushed + delta)
        d2 = d + delta
        # calls: the callee's pop
        cm = RCALL_RE.search(rest2)
        ci = RCALLI_RE.search(rest2) if not cm else None
        if cm or ci:
            pop = pops.get(cm.group(2)) if cm else None
            if pop is None:                     # inferred: cdecl if an add esp follows, else the pushed bytes
                nxt = k + 1
                while nxt < len(lines) and not code_of(lines[nxt]).strip():
                    nxt += 1
                an = ADD_ESP_RE.search(code_of(lines[nxt])) if nxt < len(lines) else None
                pop = 0 if an and an.group(2) == '+' else pushed2
                d2 -= pop
                guarded[k] = d2
            else:
                d2 -= pop
            pushed2 = 0
        if d2 < 0:
            raise NotLocal('esp above its entry value')
        rm = RETURN_RE.search(rest2)
        if rm and d2 != 0:
            raise NotLocal('ret with esp off by %d' % d2)
        tm = ss.TAIL_RE.search(rest2)
        if tm and d2 != 0:
            raise NotLocal('tail jump with the frame live')
        for t in GOTO_RE.findall(rest2):
            if t not in labels:
                raise NotLocal('goto outside the function')
            flow(labels[t], d2, 0)
        s0 = rest2.strip()
        terminal = (s0.startswith('goto ') and s0.endswith(';')) or s0.startswith('switch') or \
            ((rm is not None or tm is not None) and not s0.startswith('if')) or \
            (s0.startswith('fnv_trap(') or s0.startswith('{ fnv_trap('))
        if not terminal:
            flow(k + 1, d2, pushed2)
    # promote: exact size, no clash with another access or a fixed range, below any escape
    ranges = [(off, off + sz) for off, szs in accesses.items() for sz in szs]
    out = {}
    for off, szs in accesses.items():
        if len(szs) != 1:
            continue
        sz = next(iter(szs))
        lo, hi = off, off + sz
        if 0 <= lo < 4 or (lo < 0 < hi):
            continue
        if any(a < hi and lo < b and (a, b) != (lo, hi) for a, b in ranges + fixed):
            continue
        if escape is not None and hi > escape:
            continue
        if has_tail and off >= 0:
            continue
        out[off] = sz
    if not out:
        raise NotLocal('no promotable slots')
    return out, d_at, setup_end, guarded


def rewrite(body, pops, helpers=frozenset()):
    slots, d_at, setup_end, guarded = analyze(body, pops, helpers)
    fn = re.search(r'FNV_ENTER\((0x[0-9a-f]+u)\)', body).group(1)
    lines = body.split('\n')
    k0 = 0
    while k0 < len(lines) and (ss.HEAD_RE.match(lines[k0]) or not lines[k0].strip()):
        k0 += 1

    def addr0(off):
        return 'fnv_esp0 %s 0x%xu' % ('+' if off >= 0 else '-', abs(off))

    out = lines[:k0]
    out.append('    const uint32_t fnv_esp0 = s.esp; ' +
               ' '.join('%s %s = 0;' % (CTYPE[sz], slot_name(off)) for off, sz in sorted(slots.items())))
    args = ' '.join('FNV_SLA(%s, %s);' % (slot_name(off), addr0(off)) for off in sorted(slots) if off >= 0)
    if args:
        out.append('    ' + args)
    locs = ' '.join('FNV_SLL(%s, %s);' % (slot_name(off), addr0(off)) for off in sorted(slots) if off < 0)
    for k in range(k0, len(lines)):
        l = lines[k]
        if k == setup_end and locs:
            out.append('    ' + locs)
        d = d_at[k]
        if d is not None:
            def sub(m, d=d):
                n = int(m.group(2), 16) if m.group(2) else 0
                off = n - d
                if off not in slots or SIZES[m.group(1)] != slots[off]:
                    return m.group(0)
                a = 's.esp + 0x%xu' % n
                sig = '%s, %s, %s, %d' % (slot_name(off), a, fn, off)
                if m.group(1) == 'MF':
                    return 'FNV_SLF(%s)' % sig
                if m.group(1) == 'MD':
                    return 'FNV_SLD(%s)' % sig
                return 'FNV_SL(%s)' % sig
            code, sep, comment = l.partition('  //')
            l = ESP_MEM_RE.sub(sub, code) + sep + comment
        out.append(l)
        if k in guarded:
            ret = re.search(r', (0x[0-9a-f]{8})u\)', l)
            out.append('    FNV_ESPCHK(fnv_esp0, %d, %s);' % (guarded[k], ret.group(1) + 'u' if ret else '0u'))
    return '\n'.join(out)


def main(paths):
    import collections
    texts = {}
    for p in paths:
        for m in ss.FUNC_RE.finditer(open(p).read()):
            texts[int(m.group(1)[2:], 16)] = 'void %s(FnvCpu& s_)\n{\n%s\n}' % (m.group(1), m.group(2))
    pops = callee_pops(texts)
    helpers = ss.frame_helpers(texts)
    ok = 0
    why = collections.Counter()
    for a, t in texts.items():
        m = ss.FUNC_RE.match(t)
        try:
            rewrite(m.group(2), pops, helpers)
            ok += 1
        except NotLocal as e:
            why[str(e).split('(')[0].split(':')[0]] += 1
    print('%d functions, %d with esp-frame slots in locals' % (len(texts), ok))
    for w, n in why.most_common(15):
        print('  %6d  %s' % (n, w))


if __name__ == '__main__':
    main(sys.argv[1:])
