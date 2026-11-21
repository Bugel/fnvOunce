#!/usr/bin/env python3
"""x87 stack in registers: a post-pass over each recompiled function (tools/recomp.py).

The lifter emits the x87 register stack as FPUSH/FPOP/ST(i) over FnvCpu::st[] and FnvCpu::depth, both in memory. The
build has no strict aliasing, so after every guest-memory store the compiler reloads depth and the slots, and the
slots never live in host registers. In almost every function the stack depth at each instruction is fixed relative to
the depth on entry; this pass works it out and, where it can, rewrites the function so each slot is a local double:

    ST(i) at relative depth r   ->  x87_<r-1-i>
    FPUSH(v) at r               ->  x87_<r> = (v)       (r + 1 afterwards)
    FPOP()                      ->  nothing             (r - 1)
    FSW()                       ->  FSW_AT(r)           (the TOP field from the real depth + r)

Calls, returns, tail jumps and traps see the real stack: the live slots are stored to FnvCpu::st[] above the entry
depth first, and after a call the slots are reloaded. How many values a call leaves on the
stack (0, or 1 for a float result) is read off the code after it: if that code reads below what the caller had, the
call returned one. X87_CHECK compares the real depth with that and traps on a mismatch, so a wrong guess stops the
game with a message instead of corrupting arithmetic.

A function stays as it was (memory stack) when anything is not fixed: the depth differs where paths meet, the code
reads slots it did not push (values from its caller), it uses the depth directly (fxam, fsave/frstor, finit), or it
pushes more than 8.

usage (coverage report over existing shards): python tools/x87_static.py out/recomp/recomp_*.cpp
"""
import re
import sys

FUNC_RE = re.compile(r'^void (f_[0-9a-f]{8})\(FnvCpu& s_\)\n\{\n(.*?)\n\}$', re.M | re.S)
LABEL_RE = re.compile(r'^(L_[0-9a-f]{8}):\s*$')
GOTO_RE = re.compile(r'goto (L_[0-9a-f]{8});')
TOKEN_RE = re.compile(r'FPUSH\(|FPOP\(\)|ST\((\d)\)|FSW\(\)|\bs\.depth\b|\bs\.st\b')
CALL_RE = re.compile(r'\b(RCALLI?|RJMP|TAILCALL|RETURN|fnv_trap)\(')


class NotStatic(Exception):
    pass


def match_paren(text, i):
    """index just past the ')' that closes the '(' at text[i-1]"""
    depth = 1
    while depth:
        c = text[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        i += 1
    return i


class Rewriter:
    """Rewrites one line's x87 operations at relative depth `rel`; returns (new_text, rel_after, slots_used)."""

    def __init__(self):
        self.max_slot = -1

    def expr(self, text, rel):
        out = []
        i = 0
        while True:
            m = TOKEN_RE.search(text, i)
            if not m:
                out.append(text[i:])
                return ''.join(out), rel
            out.append(text[i:m.start()])
            tok = m.group(0)
            if tok == 'FPUSH(':
                end = match_paren(text, m.end())
                inner, rel2 = self.expr(text[m.end():end - 1], rel)
                if rel2 != rel:
                    raise NotStatic('push inside push')
                if rel >= 8:
                    raise NotStatic('stack overflow')
                out.append('x87_%d = (%s)' % (rel, inner))
                self.max_slot = max(self.max_slot, rel)
                rel += 1
                i = end
            elif tok == 'FPOP()':
                rel -= 1
                if rel < 0:
                    raise NotStatic('pop below entry')
                out.append('(void)0')
                i = m.end()
            elif tok.startswith('ST('):
                slot = rel - 1 - int(m.group(1))
                if slot < 0:
                    raise NotStatic('reads a slot it did not push')
                out.append('x87_%d' % slot)
                self.max_slot = max(self.max_slot, slot)
                i = m.end()
            elif tok == 'FSW()':
                out.append('FSW_AT(%d)' % rel)
                i = m.end()
            else:
                raise NotStatic('uses the depth directly')


def split_lines(body):
    return body.split('\n')


COMMENT_RE = re.compile(r'\s*//.*$')


def code_of(s):
    """a stripped line without its trailing `// address instruction` comment: `goto L_x;  // jmp ...` is unconditional"""
    return COMMENT_RE.sub('', s)


RCALL_TARGET = re.compile(r'\bRCALL\((f_[0-9a-f]{8}),')


class Resolve(Exception):
    """a path whose depth is set by calls of unknown result (a frozenset of their lines) met one of fixed depth:
    those calls left that many values"""

    def __init__(self, calls, n):
        super().__init__()
        self.calls, self.n = calls, n


def analyze(body, deltas=None, need_x87=True):
    """Relative depth before each line, the call results and the return depth; raises NotStatic. `deltas`: the
    values each known function leaves on the x87 stack when it returns, used for direct calls.

    A call whose result nothing shows (it is followed straight by the return, and the callee is unknown: a virtual
    call) makes the depth after it dynamic: the code leaves the real stack as the callee left it up to the return.
    Where such a path meets one of fixed depth, that depth is the calls' result (checked at run time like any other)."""
    fixed = {}
    for _ in range(64):
        try:
            return _analyze(body, deltas, need_x87, fixed)
        except Resolve as r:
            if not isinstance(r.n, int) or any(c in fixed for c in r.calls):
                raise NotStatic('dynamic depth meets itself')
            for c in r.calls:
                fixed[c] = r.n
    raise NotStatic('unresolved')


def _analyze(body, deltas, need_x87, fixed):
    deltas = deltas or {}
    lines = split_lines(body)
    labels = {}
    for k, l in enumerate(lines):
        m = LABEL_RE.match(l.strip())
        if m:
            labels[m.group(1)] = k
    # quick reject: no x87 at all (for rewriting; the return-depth pass looks through calls and tail jumps too)
    if need_x87 and not any(('FPUSH(' in l or 'ST(' in l or 'FPOP()' in l) for l in lines):
        return None
    rel_at = [None] * (len(lines) + 1)
    rel_at[0] = 0
    work = [0]
    call_result = {}                           # line index of a call -> values it leaves (0 or 1)
    returns = set()                            # relative depths at the function's returns

    def flow(k, rel):
        if k > len(lines):
            return
        cur = rel_at[k]
        if cur is None:
            rel_at[k] = rel
            work.append(k)
        elif cur == rel:
            return
        elif isinstance(cur, frozenset) and isinstance(rel, frozenset):
            rel_at[k] = cur | rel
            work.append(k)
        elif isinstance(cur, frozenset):
            raise Resolve(cur, rel)
        elif isinstance(rel, frozenset):
            raise Resolve(rel, cur)
        else:
            raise NotStatic('depth differs where paths meet (line %d: %d vs %d)' % (k, cur, rel))

    def probe_result(k, rel):
        """values a call at line k left, from the code after it (nothing live across the call): 1 if it reads below
        `rel` (the result), 0 if it uses the stack otherwise or reaches a branch or another call first (the compiler
        pops an unused float result at once), 'pass' if it reaches the function's return without touching the stack
        (a float result would be passed on: only the callee can tell)"""
        r = rel
        j = k + 1
        visited = set()
        while j < len(lines) and j not in visited:
            visited.add(j)
            l = lines[j]
            st = l.strip()
            if LABEL_RE.match(st) or not st:
                j += 1
                continue
            i = 0
            while True:
                m = TOKEN_RE.search(l, i)
                if not m:
                    break
                tok = m.group(0)
                if tok == 'FPUSH(':
                    # the pushed expression is evaluated before the push
                    end = match_paren(l, m.end())
                    for mm in re.finditer(r'ST\((\d)\)', l[m.end():end]):
                        if r - 1 - int(mm.group(1)) < rel:
                            return 1
                    return 0
                if tok == 'FPOP()':
                    return 1 if r - 1 < rel else 0
                if tok.startswith('ST('):
                    return 1 if r - 1 - int(m.group(1)) < rel else 0
                if tok == 'FSW()':
                    return 0
                raise NotStatic('uses the depth directly')
            cm = CALL_RE.search(l)
            if st.startswith('goto '):
                g = GOTO_RE.search(l)
                if not g or g.group(1) not in labels:
                    return 0
                j = labels[g.group(1)]
                continue
            if cm and not st.startswith('if') and cm.group(1) in ('RETURN', 'RJMP', 'TAILCALL'):
                return 'pass'
            if cm or GOTO_RE.search(l) or st.startswith('switch'):
                return 0
            j += 1
        return 0

    rw = Rewriter()
    while work:
        k = work.pop()
        if k >= len(lines):
            continue
        rel = rel_at[k]
        l = lines[k]
        s = l.strip()
        if LABEL_RE.match(s) or not s:
            flow(k + 1, rel)
            continue
        if isinstance(rel, frozenset):              # dynamic: no x87 and no calls until the return
            if TOKEN_RE.search(l):
                raise NotStatic('x87 after a call of unknown result')
            cm = CALL_RE.search(l)
            if cm and cm.group(1) in ('RCALL', 'RCALLI'):
                raise NotStatic('call after a call of unknown result')
            for t in GOTO_RE.findall(l):
                if t not in labels:
                    raise NotStatic('goto outside the function')
                flow(labels[t], rel)
            terminal = s.startswith('switch') or (s.startswith('goto ') and code_of(s).endswith(';'))
            if cm and not s.startswith('if'):
                terminal = True
                returns.add('?')
            if not terminal:
                flow(k + 1, rel)
            continue
        _, rel_after = rw.expr(l, rel)
        targets = GOTO_RE.findall(l)
        for t in targets:
            if t not in labels:
                raise NotStatic('goto outside the function')
            flow(labels[t], rel_after)
        cm = CALL_RE.search(l)
        terminal = False
        if cm:
            kind = cm.group(1)
            if kind in ('RCALL', 'RCALLI'):
                # a direct call: the callee's own return depth (from the earlier pass). Otherwise what the following
                # code does with the stack, which only tells when nothing is live across the call: with values of
                # its own on the stack, the caller popping below its depth is ambiguous (its own value, or a result)
                # With nothing live across the call, what the following code does decides (reading below the
                # caller's depth can only be the result); when it shows nothing, the callee's own return depth. With
                # values live across the call that evidence is ambiguous (popping its own value, or a result), so
                # only the callee's return depth will do. No answer: the function keeps the memory stack.
                if k in fixed:
                    res = fixed[k]
                else:
                    tm = RCALL_TARGET.search(l)
                    callee = deltas.get(tm.group(1)) if tm else None
                    res = probe_result(k, rel_after) if rel_after == 0 else 'pass'
                    if res == 'pass':
                        res = callee
                    if res is None:
                        if rel_after:
                            raise NotStatic('call result unknown')
                        res = 'D'
                call_result[k] = res
                if res == 'D':
                    rel_after = frozenset([k])
                else:
                    rel_after += res
                    if rel_after > 8:
                        raise NotStatic('stack overflow')
            elif not s.startswith('if'):
                terminal = True
                if kind == 'RETURN':
                    returns.add(rel_after)
                elif kind == 'RJMP':
                    jm = re.search(r'\bRJMP\((f_[0-9a-f]{8})\)', l)
                    d = deltas.get(jm.group(1)) if jm else None
                    returns.add('?' if d is None else rel_after + d)
                elif kind == 'TAILCALL':
                    returns.add('?')
        if s.startswith('switch') or (s.startswith('goto ') and code_of(s).endswith(';')) or s.startswith('return'):
            terminal = True
        if not terminal:
            flow(k + 1, rel_after)
    ret = returns.pop() if len(returns) == 1 else None
    return lines, rel_at, call_result, rw, (ret if isinstance(ret, int) else None)


def return_delta(body, deltas=None):
    """values the function leaves on the x87 stack when it returns, if fixed (0 for code without x87)"""
    try:
        res = analyze(body, deltas, need_x87=False)
    except NotStatic:
        return None
    return res[4]


def spill_code(rel):
    """the live slots to FnvCpu::st[] above the entry depth, and the real depth, before code that sees the stack"""
    if rel == 0:
        return ''
    return ''.join('s.st[x87_base + %d] = x87_%d; ' % (j, j) for j in range(rel)) + 's.depth = x87_base + %d; ' % rel


def wrap_calls(line, rel, result, rw):
    """each call, return, tail jump or trap in the line as a block: spill first; after a call, check the depth and
    reload the slots (the call left `result` more values)"""
    out = []
    i = 0
    while True:
        m = CALL_RE.search(line, i)
        if not m:
            out.append(line[i:])
            return ''.join(out)
        out.append(line[i:m.start()])
        end = match_paren(line, m.end())
        call = line[m.start():end]
        kind = m.group(1)
        if kind in ('RCALL', 'RCALLI') and result == 'D':
            # unknown result, straight to the return: the real stack stays as the callee left it
            out.append('{ %s%s; }' % (spill_code(rel), call))
        elif kind in ('RCALL', 'RCALLI'):
            n = rel + result
            ret = re.search(r'0x([0-9a-f]{8})u\)$', call)
            reload = 'X87_CHECK(%d, %s); ' % (n, '0x%su' % ret.group(1) if ret else '0u')
            reload += ''.join('x87_%d = s.st[x87_base + %d]; ' % (j, j) for j in range(n))
            reload += 's.depth = x87_base;'
            if n:
                rw.max_slot = max(rw.max_slot, n - 1)
            out.append('{ %s%s; %s }' % (spill_code(rel), call, reload))
        else:
            out.append('{ %s%s; }' % (spill_code(rel), call))
        # the statement's own ';' after the macro is now an empty statement
        i = end


def rewrite(body, deltas=None):
    """the function body with registers for the x87 stack, or None (no x87, or not static)"""
    res = analyze(body, deltas)
    if res is None:
        return None
    lines, rel_at, call_result, rw0, _ = res
    rw = Rewriter()
    out = []
    for k, l in enumerate(lines):
        rel = rel_at[k]
        if rel is None or isinstance(rel, frozenset):   # unreachable, or after a call of unknown result: as it was
            out.append(l)
            continue
        s = l.strip()
        if not s or LABEL_RE.match(s):
            out.append(l)
            continue
        new, rel_after = rw.expr(l, rel)
        new = wrap_calls(new, rel_after, call_result.get(k, 0), rw)
        out.append(new)
    nslots = rw.max_slot + 1
    decl = '    const int x87_base = s.depth; double %s;' % ', '.join('x87_%d = 0' % i for i in range(max(nslots, 1)))
    # after FnvLocal (line 2 of the body: FNV_ENTER, FnvLocal)
    for k, l in enumerate(out):
        if 'FnvLocal<' in l:
            out.insert(k + 1, decl)
            break
    else:
        raise NotStatic('no FnvLocal')
    return '\n'.join(out)


# the statically linked MSVC CRT (port/compat/crt_map.json: 0x00ec2xxx..): its SSE2 math dispatchers and their
# helpers leave results on the x87 stack through paths this pass cannot follow, so their return depths are unknown
CRT_LO, CRT_HI = 0x00ec0000, 0x00fe0000


class Deltas:
    """values each function leaves on the x87 stack when it returns, worked out on demand in call order (a callee
    before its caller), so chains of float-returning helpers resolve in one pass; a recursion cycle counts as
    unknown"""

    def __init__(self, bodies):
        self.bodies = bodies
        self.memo = {}
        self.busy = set()

    def get(self, name, default=None):
        if CRT_LO <= int(name[2:], 16) < CRT_HI:   # the CRT's math internals return in ways this pass misreads
            return default
        if name in self.memo:
            v = self.memo[name]
        elif name in self.busy or name not in self.bodies:
            return default
        else:
            self.busy.add(name)
            v = return_delta(self.bodies[name], self)
            self.busy.discard(name)
            self.memo[name] = v
        return default if v is None else v


def all_deltas(bodies):
    import sys
    import threading
    sys.setrecursionlimit(1000000)
    threading.stack_size(512 << 20)
    d = Deltas(bodies)
    result = {}

    def run():
        for name in bodies:
            v = d.get(name)
            if v is not None:
                result[name] = v
    t = threading.Thread(target=run)
    t.start()
    t.join()
    return result


def main(paths):
    bodies = {}
    for p in paths:
        for m in FUNC_RE.finditer(open(p).read()):
            bodies[m.group(1)] = m.group(2)
    deltas = all_deltas(bodies)
    print('return depth known for %d functions (%d return a float)' % (len(deltas), sum(1 for d in deltas.values() if d == 1)))
    funcs = static = x87_funcs = 0
    lines_x87 = lines_static = 0
    reasons = {}
    for name, body in bodies.items():
        if True:
            funcs += 1
            n = sum(1 for l in body.split('\n') if 'FPUSH(' in l or 'ST(' in l or 'FPOP()' in l)
            if not n:
                continue
            x87_funcs += 1
            lines_x87 += n
            try:
                if rewrite(body, deltas) is not None:
                    static += 1
                    lines_static += n
            except NotStatic as e:
                r = str(e).split(' (')[0]
                reasons[r] = reasons.get(r, 0) + 1
    print('functions %d, with x87 %d, static %d (%.0f%%); x87 lines %d, in static functions %d (%.0f%%)' % (
        funcs, x87_funcs, static, 100 * static / max(x87_funcs, 1), lines_x87, lines_static,
        100 * lines_static / max(lines_x87, 1)))
    for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
        print('  %5d  %s' % (c, r))


if __name__ == '__main__':
    main(sys.argv[1:])
