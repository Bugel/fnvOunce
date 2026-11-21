#!/usr/bin/env python3
"""Stack frame slots in locals: a post-pass over each recompiled function (tools/recomp.py), after the x87 pass.

Most of the game is built with little optimization: every local variable (`this` included) lives in the stack frame
and is reloaded from [ebp - N] around nearly every instruction. In the lifted code those are guest-memory accesses,
and the build has no strict aliasing, so every guest store makes the compiler assume each of them may have changed.
Where nothing but the function itself can reach its frame, this pass turns each frame slot into a C++ local:

    M32((uint32_t)(0u + s.ebp - 0x28u))   ->  sl_m28          (uint32_t; MF -> FNV_SF(sl_m28), the same bits as float)
    M32((uint32_t)(0u + s.ebp + 0xcu))    ->  sl_p0c          (an argument: loaded once when the frame is set up)

A function qualifies only when its frame cannot be seen from outside:
  - it starts with `push ebp; mov ebp, esp`, and ebp appears nowhere else except [ebp +/- constant] accesses, the
    epilogue (`mov esp, ebp`, `pop ebp`, `leave`) and `xor reg, ebp` (the /GS cookie): no `lea x, [ebp - N]`, no
    indexed [ebp + 4*reg - N], no copy of ebp (an address handed out, an SEH or EH registration, a by-reference local)
  - no tail jump (RJMP/TAILCALL): the target would run on this frame and read its slots from memory
  - no `fs:` access: an SEH or C++ exception registration, whose handlers run on this frame
  - no direct call to a frame-sharing helper: a function without its own frame that reads ebp before setting it
    works on its caller's frame (the CRT's x87 error path: 0x00ed60eb builds an exception record and its helpers
    0x00ed25b7 and 0x00ed6133 fill it in through ebp); frame_helpers() finds them over the whole program
  - every esp-relative access stays inside bytes this function pushed since the last call or label (outgoing
    arguments, which sit below the frame): `fstp [esp]` after `push ecx` is fine, an access that could reach the
    locals is not; esp is never copied (`mov ecx, esp`, `lea eax, [esp + 8]`) or replaced (`mov esp, eax`, `and esp`)
  - no argument slot below +8 (the saved ebp and the return address)
When the function hands out the address of a frame object (`lea ecx, [ebp - 0x34]` for a temporary passed to a
constructor, an array indexed as [ebp + 4*reg - N]), the bytes from that address upward may be reached through the
pointer and stay in memory; slots wholly below the lowest such address are still private. Unoptimized MSVC frames
put the spilled `this`, the most reloaded slot, at the bottom. (A callee stepping down from a member's address to its
enclosing object would break this; compiled code reaches an enclosing object from its own start.)
Slots whose bytes are accessed at more than one offset or size (a struct read field by field and as a whole) stay in
memory; the rest become locals. Once the frame is set up, every promoted slot is loaded from its stack bytes, so a
read before any write sees what the original saw: a `push ecx` that reserves the frame also fills it with ecx, and
some code reads such a byte as a flag (0x0065fe40 CallWithFlag passes [ebp-1] on).

usage (coverage report over existing shards): python tools/stack_slots.py out/recomp/recomp_*.cpp
"""
import re
import sys

FUNC_RE = re.compile(r'^void (f_[0-9a-f]{8})\(FnvCpu& s_\)\n\{\n(.*?)\n\}$', re.M | re.S)
SIZES = {'M8': 1, 'M16': 2, 'M32': 4, 'MF': 4, 'M64': 8, 'MD': 8}
CTYPE = {1: 'uint8_t', 2: 'uint16_t', 4: 'uint32_t', 8: 'uint64_t'}
SLOT_RE = re.compile(r'\b(M8|M16|M32|MF|M64|MD)\(\(uint32_t\)\(0u \+ s\.ebp ([+-]) 0x([0-9a-f]+)u\)\)')
ESP_MEM_RE = re.compile(r'\b(M8|M16|M32|MF|M64|MD)\(\(uint32_t\)\(0u \+ s\.esp(?: \+ 0x([0-9a-f]+)u)?\)\)')
ESP_MEM2_RE = re.compile(r'\b(M8|M16|M32|MF|M64|MD)\(s\.esp(?: \+ (\d+))?\)')       # inline imports' forms
ADD_ESP_RE = re.compile(r'\{ uint32_t a_ = s\.esp, b_ = 0x([0-9a-f]+)u, r_ = a_ ([+-]) b_; (?:ADDF|SUBF)\(a_, b_, r_, 32\); '
                        r's\.esp = \(uint32_t\)\(r_\); \}')
ESP_POP_RE = re.compile(r's\.esp \+= (\d+);')
LABEL_RE = re.compile(r'^\s*L_[0-9a-f]{8}:\s*$')
CALL_RE = re.compile(r'\b(RCALLI?|RETURN|fnv_trap)\(')
TAIL_RE = re.compile(r'\b(RJMP|TAILCALL)\(')
HEAD_RE = re.compile(r'^\s*(FNV_ENTER\(|FnvLocal<|const int x87_base)')
EPILOGUE = ('s.esp = (uint32_t)(s.ebp);', 's.ebp = (uint32_t)(POP());', 's.esp = s.ebp; s.ebp = POP();')
# the frame address in any other expression with a constant (lea, indexed access, SSE access): the bytes from there up
# may be reached through a pointer
ESCAPE_RE = re.compile(r'\(0u \+ s\.ebp(?: \+ s\.e[a-z]{2}(?:\*\d)?)?(?: ([+-]) 0x([0-9a-f]+)u)?\)')


class NotLocal(Exception):
    pass


def slot_name(sign, off):
    return 'sl_%s%02x' % ('p' if sign == '+' else 'm', off)


FIRST_EBP_RE = re.compile(r'PUSH\(s\.ebp\)|s\.ebp = |s\.ebp\b')
RCALL_TARGET_RE = re.compile(r'\bRCALL\(fl?_([0-9a-f]{8}),')


def frame_helpers(texts):
    """{'%08x'} of functions that read ebp (the caller's frame) before saving or setting it"""
    out = set()
    for a, t in texts.items():
        m = FUNC_RE.match(t)
        if not m:
            continue
        body = m.group(2)
        for mm in FIRST_EBP_RE.finditer(body):
            tok = mm.group(0)
            if tok.startswith('PUSH') or tok.startswith('s.ebp = '):
                break                           # saved or overwritten first: not the caller's frame
            out.add('%08x' % a if isinstance(a, int) else a)
            break
    return out


def analyze(body, helpers=frozenset()):
    """({(sign, off): size} of the slots to promote, the line where the frame is fully set up); raises NotLocal"""
    lines = body.split('\n')
    k = 0
    while k < len(lines) and (HEAD_RE.match(lines[k]) or not lines[k].strip()):
        k += 1
    if k + 1 >= len(lines) or not lines[k].strip().startswith('PUSH(s.ebp);') or \
            not lines[k + 1].strip().startswith('s.ebp = (uint32_t)(s.esp);'):
        raise NotLocal('no ebp frame')
    if TAIL_RE.search(body):
        raise NotLocal('tail jump')
    if 'fs_base' in body:                       # an SEH or C++ EH registration: handlers run on this frame
        raise NotLocal('exception frame')
    if helpers and any(c in helpers for c in RCALL_TARGET_RE.findall(body)):
        raise NotLocal('calls a frame-sharing helper')
    prologue = (k, k + 1)
    accesses = {}                               # (sign, off) -> set of sizes
    escape = None                               # lowest frame address (signed offset) handed out or indexed
    pending = 0                                 # bytes this function surely pushed below the frame since a call/label
    setup_end = None
    setup = True                                # still allocating the frame: `sub esp, F` and pushes right after
    for i, l in enumerate(lines):           # `mov ebp, esp` (a `push ecx` is often the frame itself) are frame bytes
        code = re.sub(r'\s*//.*$', '', l)
        if i < k:
            continue
        if LABEL_RE.match(code):
            pending = 0
            if setup:                           # the loads go before the label: a jump back must not redo them
                setup, setup_end = False, i
            continue
        if i in prologue:
            continue
        if setup:
            if re.match(r'^\s*PUSH\(s\.e[a-z]{2}\);$', code) or ADD_ESP_RE.fullmatch(code.strip() or '-') and '- b_' in code:
                continue
            setup = False
            setup_end = i
        # ---- ebp: only constant-offset slots, the epilogue and xor with the cookie
        rest = SLOT_RE.sub(lambda m: accesses.setdefault((m.group(2), int(m.group(3), 16)), set()).add(SIZES[m.group(1)])
                           or 'SLOT', code)
        for e in EPILOGUE:
            rest = rest.replace(e, '')
        rest = re.sub(r'\^ \(s\.ebp\)', '', rest)
        for mm in ESCAPE_RE.finditer(rest):
            off = int(mm.group(2), 16) if mm.group(2) else 0
            off = -off if mm.group(1) == '-' else off
            escape = off if escape is None else min(escape, off)
        rest = ESCAPE_RE.sub('ESC', rest)
        if 's.ebp' in rest:
            raise NotLocal('ebp escapes: ' + l.strip()[-60:])
        # ---- esp: pushes, pops and esp-relative accesses inside what was pushed
        if 'PUSH(s.esp)' in rest:
            raise NotLocal('push esp')
        m = ADD_ESP_RE.search(rest)
        if m:
            n = int(m.group(1), 16)
            if m.group(2) == '-':
                pending += n
            else:
                pending = max(0, pending - n)
            rest = rest.replace(m.group(0), '')
        for mm in list(ESP_MEM_RE.finditer(rest)) + list(ESP_MEM2_RE.finditer(rest)):
            off = int(mm.group(2), 16 if mm.re is ESP_MEM_RE else 10) if mm.group(2) else 0
            if off + SIZES[mm.group(1)] > pending:
                raise NotLocal('esp access may reach the frame: ' + l.strip()[-50:])
        rest = ESP_MEM_RE.sub('ESPMEM', ESP_MEM2_RE.sub('ESPMEM', rest))
        for mm in ESP_POP_RE.finditer(rest):
            pending = max(0, pending - int(mm.group(1)))
        rest = ESP_POP_RE.sub('', rest)
        if 's.esp' in rest:
            raise NotLocal('esp used otherwise: ' + l.strip()[-60:])
        # PUSH/POP in statement order is close enough: a line holds one instruction
        pending += 4 * rest.count('PUSH(')
        pending = max(0, pending - 4 * rest.count('POP()'))
        if CALL_RE.search(rest):
            pending = 0
    # promote a slot only when all accesses to its bytes use exactly its offset and size
    ranges = []
    for (sign, off), sizes in accesses.items():
        lo = -off if sign == '-' else off
        for sz in sizes:
            ranges.append((lo, lo + sz, sign, off, sz))
    out = {}
    for lo, hi, sign, off, sz in ranges:
        if sign == '+' and off < 8:
            raise NotLocal('saved ebp or return address')
        clash = any(o is not None and (a < hi and lo < b) and (a, b) != (lo, hi) for a, b, _, o, _s in ranges)
        if not clash and (escape is None or hi <= escape):
            out[(sign, off)] = sz
    if not out:
        raise NotLocal('no slots')
    return out, setup_end


def rewrite(body, helpers=frozenset()):
    """the body with its frame slots in locals, or None. The slots are spelled through macros (fnv_recomp.h):
    plain locals normally, and under FNV_SLOT_CHECK proxies that also keep guest memory up to date and report any
    read where memory changed behind the function's back (a pointer the analysis missed)."""
    slots, setup_end = analyze(body, helpers)
    fn = re.search(r'FNV_ENTER\((0x[0-9a-f]+u)\)', body).group(1)
    lines = body.split('\n')
    k = 0
    while k < len(lines) and (HEAD_RE.match(lines[k]) or not lines[k].strip()):
        k += 1

    def addr(sign, off):
        return 's.ebp %s 0x%xu' % (sign, off)

    def sub(m):
        key = (m.group(2), int(m.group(3), 16))
        if key not in slots:
            return m.group(0)
        name = slot_name(*key)
        sig = '%s, %s, %s, %s%d' % (name, addr(*key), fn, key[0], key[1])
        if m.group(1) == 'MF':
            return 'FNV_SLF(%s)' % sig
        if m.group(1) == 'MD':
            return 'FNV_SLD(%s)' % sig
        return 'FNV_SL(%s)' % sig

    decl = '    ' + ' '.join('%s %s = 0;' % (CTYPE[sz], slot_name(*key)) for key, sz in sorted(slots.items()))
    init = ' '.join('%s(%s, %s);' % ('FNV_SLA' if key[0] == '+' else 'FNV_SLL', slot_name(*key), addr(*key))
                    for key, sz in sorted(slots.items()))
    out = lines[:k] + [decl]
    for i in range(k, len(lines)):
        l = SLOT_RE.sub(sub, lines[i])
        if i == setup_end:
            out.append('    ' + init)
        out.append(l)
    return '\n'.join(out)


def main(paths):
    import collections
    total = ok = 0
    why = collections.Counter()
    for p in paths:
        for m in FUNC_RE.finditer(open(p).read()):
            total += 1
            try:
                rewrite(m.group(2))
                ok += 1
            except NotLocal as e:
                why[str(e).split(':')[0]] += 1
    print('%d functions, %d with frame slots in locals' % (total, ok))
    for w, n in why.most_common():
        print('  %6d  %s' % (n, w))


if __name__ == '__main__':
    main(sys.argv[1:])
