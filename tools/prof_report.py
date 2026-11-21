#!/usr/bin/env python3
"""Where the game's main thread spends its time, per recompiled function, from the shadow-call-stack profiler
(build with FNV_PROFILE_STACK: port/switch2/fnv_prof, or tools/recomp_build_posix.py --profile; host_posix.cpp
profiler() writes fnv_prof.txt). Prints a markdown report: the top functions by self time with decomp names, the same
grouped by subsystem, and how concentrated the profile is (how many functions make up 50/80/90% of the time).

usage: python tools/prof_report.py fnv_prof.txt [--log fnv.log] [--intervals 6-30] [--top 200] [--title ...] > report.md
  --intervals  which 10 s intervals to count (default: all); `--list` prints them with fps (from --log) to choose
"""
import argparse
import bisect
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decomp_path import DECOMP_DIR  # noqa: E402

HOST_BASE = 0xf0000000      # host_posix.cpp: platform-layer functions live at 0xf0000000+ (dispatch keys)


def read_profile(path):
    """[(interval, t, samples, outside, {addr: [self, incl, name]}, {(caller, callee): n})]"""
    out = []
    for line in Path(path).read_text(errors='replace').splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == 'I':
            out.append((int(p[1]), float(p[2]), int(p[3]), int(p[4]), {}, {}))
        elif p[0] == 'F' and out:
            out[-1][4][int(p[1], 16)] = [int(p[2]), int(p[3]), ' '.join(p[4:]) or None]
        elif p[0] == 'E' and out:
            out[-1][5][(int(p[1], 16), int(p[2], 16))] = int(p[3])
    return out


def fps_by_interval(log):
    """The last [perf] fps logged before each '[prof] interval N' line."""
    fps, res = None, {}
    for line in Path(log).read_text(errors='replace').splitlines():
        m = re.match(r'\[perf\] ([\d.]+) fps', line)
        if m:
            fps = float(m.group(1))
        m = re.match(r'\[prof\] interval (\d+):', line)
        if m:
            res[int(m.group(1))] = fps
    return res


def decomp_names():
    units = json.loads((Path(DECOMP_DIR) / 'build/units.json').read_text())['units']
    names, src = {}, {}
    for u in units:
        for f in u['functions']:
            a = int(f['address'], 16)
            names.setdefault(a, f['symbol'])
            src.setdefault(a, u['source'])
    return names, src


def demangle(syms):
    syms = sorted(set(s for s in syms if s and s.startswith('?')))
    try:
        r = subprocess.run(['llvm-undname'], input='\n'.join(syms) + '\n', capture_output=True, text=True)
        outs = [l for l in r.stdout.splitlines() if l.strip()]
        # llvm-undname echoes each input line, then its demangled form
        res = {}
        i = 0
        while i + 1 < len(outs):
            if outs[i] in syms or outs[i].startswith('?'):
                res[outs[i]] = outs[i + 1]
                i += 2
            else:
                i += 1
        return res
    except OSError:
        return {}


def short(dm):
    """'public: void __thiscall NiNode::UpdateDownwardPass(class NiUpdateData &, unsigned int)' -> NiNode::UpdateDownwardPass"""
    if not dm:
        return dm
    s = re.sub(r'^(public|private|protected): ', '', dm)
    s = re.sub(r'^(static |virtual )', '', s)
    m = re.search(r'(?:__thiscall|__cdecl|__stdcall|__fastcall|__clrcall) ([^(]+)\(', s)
    if m:
        return m.group(1).strip()
    return s.split('(')[0].strip()


# Subsystem rules: first match wins, tested against "<source path> <demangled name>".
GROUPS = [
    ('platform layer (PAL)', None),     # host functions (D3D9, files, sound, waits): decided by address
    ('memory / allocator', r'MemoryManager|ScrapHeap|MemoryHeap|NiMemObject::operator|NiAlloc|NiFree|NiMalloc|'
                           r'\bmalloc\b|\bfree\b|operator new|operator delete|HeapAlloc|BSSmallBlock|AbstractHeap|'
                           r'\bmemcpy|\bmemset|\bmemmove|\bmemcmp|FormHeap'),
    ('containers / strings / refcount', r'NiTArray|NiTList|NiTPointerList|NiTMap|NiTPointerMap|NiTStringMap|NiTLargeArray|'
                           r'NiTPrimitiveArray|NiTSet|NiTScrapHeap|BSSimpleList|BSSimpleArray|BSTArray|tList|tHashTable|'
                           r'BSTHashMap|BSMap|LockFreeMap|BSTCaseInsensitiveStringMap|NiTDefaultAllocator|NiTObjectArray|'
                           r'NiTListBase|NiTMapBase|BSString|NiFixedString|NiGlobalStringTable|BSFixedString|'
                           r'NiRefObject|NiPointer<|IncRefCount|DecRefCount|BSSpinLock|BSCriticalSection|'
                           r'\bstrcmp|\bstrlen|\b_stricmp|\bstrncpy|\bsprintf|\bstrcpy|Interlocked'),
    ('physics (Havok)', r'^havok/|^src/havok|\bhk[A-Z]|\bbhk|hkp[A-Z]|bshavok'),
    ('culling / visibility', r'Cull|Frustum|Occlusion|Occluder|BSMultiBound|BSPortal|Visible|NiBound::WhichSide|'
                             r'BSCompoundFrustum|PlaneTest|NiCamera::'),
    ('animation / skinning', r'NiControllerManager|NiControllerSequence|Interpolator|NiKeyframe|NiSkin|NiTimeController|'
                             r'NiMultiTargetTransformController|NiTransformController|NiGeomMorpher|BSAnimGroup|AnimData|'
                             r'NiAnimation|NiAVObjectPalette|KFModel|NiBSpline|NiFloatData|NiTransformData|'
                             r'NiSequenceData|BSFaceGen|FaceGen|NiPathController|Morph|Bone|Ragdoll|IK|NiBlend'),
    ('scene graph update', r'NiAVObject::Update|NiNode::Update|UpdateDownwardPass|UpdateWorldData|UpdateWorldBound|'
                           r'UpdateSelected|UpdateRigid|UpdatePropert|UpdateEffects|UpdateControllers|NiNode::|NiAVObject::|'
                           r'BSFadeNode|NiObjectNET|NiSwitchNode|NiBillboardNode|BSOrderedNode|NiUpdateData|'
                           r'NiParticle|BSMasterParticle|NiPSys|ParticleSystem'),
    ('math / transform', r'NiPoint[234]|NiMatrix3|NiTransform|NiQuaternion|NiColor|NiBound|NiPlane|NiSqrt|NiFastATan|'
                         r'NiCos|NiSin|NiACos|NiASin|\bsqrt|\b_CIsqrt|\b_CIcos|\b_CIsin|\b_CIpow|\b_CIatan|\bfloor\b|'
                         r'\b_ftol|\bpow\b|\batan2?\b|\bcos\b|\bsin\b|\bfabs\b|NiMatrix|Vector3|\bVector\b|Quaternion|'
                         r'NiMath|BSMath|fmod|\bceil\b'),
    ('AI / actors', r'Actor|Character|Creature|Process|\bAI|AI[A-Z]|Package|Path(ing|Finder|ing)|NavMesh|Navmesh|'
                    r'Detection|Combat|ActorMover|Movement|bhkCharacter|Dialog|Topic|Behavior|HighProcess|Pathing'),
    ('renderer submit / shaders / lighting', r'^bsshader/|NiDX9|NiD3D|Renderer|Shader|RenderPass|Accumulator|Batch|'
                           r'ShadowSceneNode|Light|Shadow|NiGeometry|NiTriShape|NiTriStrips|NiDynamicEffect|'
                           r'NiTexture|NiSourceTexture|NiProperty|NiTexturingProperty|NiAlphaProperty|D3D|Render|'
                           r'Imagespace|ImageSpace|BSGrass|BSTreeNode|SpeedTree|^speedtree/|BSLOD|Water|Sky|Precipitation'),
    ('world / forms / extra data', r'TESObjectREFR|TESForm|TESObjectCELL|TESWorldSpace|ExtraData|BaseExtraList|'
                                   r'ExtraContainer|TESObject|TESBound|TESDataHandler|GridCell|TES::|LoadedArea|'
                                   r'BGSPrimitive|BGS[A-Z]|TESNPC|TESRace|TESModel|InventoryChanges'),
    ('scripts / events', r'Script|Expression|Event|Quest'),
    ('UI / menus', r'Menu|Tile|HUD|Interface'),
    ('audio', r'Audio|Sound|BSGameSound|Voice'),
    ('I/O / streaming / tasks', r'BSFile|Archive|NiStream|Stream|IOManager|QueuedFile|Task|BSResource|BSA'),
]
UNKNOWN = 'other / unnamed'


def classify(addr, src, dm, host):
    if host:
        return GROUPS[0][0]
    key = (src or '') + ' ' + (dm or '')
    for g, rx in GROUPS[1:]:
        if re.search(rx, key):
            return g
    return UNKNOWN


def concentration(counts, total):
    """How many functions (largest first) make up 50/80/90% of `total`."""
    res, acc, n = {}, 0, 0
    for c in sorted(counts, reverse=True):
        acc += c
        n += 1
        for p in (50, 80, 90, 95, 99):
            if p not in res and acc * 100 >= p * total:
                res[p] = n
    return res


def parse_range(s, have):
    if not s:
        return set(have)
    keep = set()
    for part in s.split(','):
        a, _, b = part.partition('-')
        keep |= set(range(int(a), int(b or a) + 1))
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('profile')
    ap.add_argument('--log')
    ap.add_argument('--intervals')
    ap.add_argument('--top', type=int, default=200)
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--title', default='Main-thread profile')
    ap.add_argument('--note', default='')
    a = ap.parse_args()

    prof = read_profile(a.profile)
    fps = fps_by_interval(a.log) if a.log else {}
    if a.list:
        for i, t, n, outside, fn, _ in prof:
            top = max(fn.items(), key=lambda kv: kv[1][0]) if fn else (0, [0, 0, None])
            print('%3d %6.0f s %6d samples  fps %-5s  top %08x %.1f%%' % (
                i, t, n, fps.get(i), top[0], 100.0 * top[1][0] / max(n, 1)))
        return
    keep = parse_range(a.intervals, [p[0] for p in prof])

    self_c, incl_c, hostname, edges = Counter(), Counter(), {}, Counter()
    samples = outside = 0
    used = []
    for i, t, n, out, fn, ed in prof:
        if i not in keep:
            continue
        used.append(i)
        samples += n
        outside += out
        for addr, (s, inc, name) in fn.items():
            self_c[addr] += s
            incl_c[addr] += inc
            if name:
                hostname[addr] = name
        edges.update(ed)
    if not samples:
        raise SystemExit('no samples in the chosen intervals')

    names, srcs = decomp_names()
    dem = demangle(names.get(x) for x in self_c)
    starts = sorted(names)

    def info(addr):
        host = addr >= HOST_BASE
        if host:
            return 'PAL ' + hostname.get(addr, '?'), '', '', True
        sym = names.get(addr)
        if sym is None:                      # a lifted function the decomp does not list: say what it is inside
            k = bisect.bisect_right(starts, addr) - 1
            inside = (' (inside %s)' % short(dem.get(names[starts[k]], names[starts[k]]))) if k >= 0 and \
                addr - starts[k] < 0x2000 else ''
            return '?' + inside, '', srcs.get(starts[k], '') if k >= 0 else '', False
        d = dem.get(sym, sym)
        return short(d) or sym, d, srcs.get(addr, ''), False

    guest_self = sum(c for x, c in self_c.items() if x < HOST_BASE)
    pal_self = sum(c for x, c in self_c.items() if x >= HOST_BASE)
    guest_fns = [c for x, c in self_c.items() if x < HOST_BASE]
    conc_guest = concentration(guest_fns, guest_self)
    conc_all = concentration(list(self_c.values()), samples)

    group_self, group_n, group_fn = Counter(), Counter(), defaultdict(list)
    rows = []
    for addr, c in self_c.most_common():
        label, dm, src, host = info(addr)
        g = classify(addr, src, dm or label, host)
        group_self[g] += c
        group_n[g] += 1
        group_fn[g].append((c, addr, label))
        rows.append((addr, c, incl_c[addr], label, g, src))

    pct = lambda c, tot=samples: 100.0 * c / tot   # noqa: E731
    w = sys.stdout.write
    w('# %s\n\n' % a.title)
    if a.note:
        w(a.note.rstrip() + '\n\n')
    secs = samples / 1000.0
    fl = [fps[i] for i in used if fps.get(i)]
    w('- **Samples:** %d of the main thread at 1 kHz (%.0f s), intervals %s%s.\n' % (
        samples, secs, '%d-%d' % (min(used), max(used)) if used == list(range(min(used), max(used) + 1)) else used,
        ('; fps in those intervals %.0f-%.0f (mean %.1f)' % (min(fl), max(fl), sum(fl) / len(fl))) if fl else ''))
    w('- **Where:** %.1f%% in recompiled game code (%d functions seen), %.1f%% in platform-layer calls '
      '(D3D9, files, sound, waits), %.1f%% outside any guest code.\n' % (
          pct(guest_self), len(guest_fns), pct(pal_self), pct(outside)))
    w('- **Self time** = the function was the innermost recompiled function on the shadow call stack; '
      '**inclusive** = it was anywhere on the stack. Percentages are of all main-thread samples unless marked '
      '"of guest".\n\n')

    w('## How concentrated is it?\n\n')
    w('Functions, largest self time first, needed to cover a share of the time spent in recompiled code '
      '(platform layer and idle excluded):\n\n')
    w('| share of guest time | functions |\n|---:|---:|\n')
    for p in (50, 80, 90, 95, 99):
        w('| %d%% | %s |\n' % (p, conc_guest.get(p, '-')))
    top_share = sum(sorted(guest_fns, reverse=True)[:a.top]) * 100.0 / max(guest_self, 1)
    w('\nThe top %d functions cover %.1f%% of guest time; the top 20 cover %.1f%%, the top 50 %.1f%%.\n' % (
        a.top, top_share, sum(sorted(guest_fns, reverse=True)[:20]) * 100.0 / max(guest_self, 1),
        sum(sorted(guest_fns, reverse=True)[:50]) * 100.0 / max(guest_self, 1)))
    w('Counting platform-layer calls as functions too: 50%% = %s, 80%% = %s, 90%% = %s of all samples.\n\n' % (
        conc_all.get(50, '-'), conc_all.get(80, '-'), conc_all.get(90, '-')))

    w('## By subsystem (self time)\n\n')
    w('Classified from the decomp unit and the demangled name (tools/prof_report.py GROUPS; first match wins, so '
      'treat the split as approximate).\n\n')
    w('| subsystem | self % of all | % of guest | functions | biggest |\n|---|---:|---:|---:|---|\n')
    for g, c in group_self.most_common():
        big = ', '.join('%s %.1f%%' % (lab[:48], pct(cc)) for cc, ad, lab in sorted(group_fn[g], reverse=True)[:3])
        w('| %s | %.1f | %s | %d | %s |\n' % (g, pct(c), '-' if g == GROUPS[0][0] else '%.1f' % pct(c, guest_self),
                                          group_n[g], big.replace('|', '\\|')))
    w('\n')

    # inclusive: the frames the time sits under (subsystem roots)
    w('## Largest inclusive times (where the frame goes)\n\n')
    w('| inclusive % | self % | address | function |\n|---:|---:|---|---|\n')
    for addr, c in incl_c.most_common(60):
        label = info(addr)[0]
        w('| %.1f | %.2f | %08x | %s |\n' % (pct(c), pct(self_c[addr]), addr, label.replace('|', '\\|')[:110]))
    w('\n')

    callers = defaultdict(Counter)
    for (cr, ce), n in edges.items():
        callers[ce][cr] += n

    w('## Top %d functions by self time\n\n' % a.top)
    w('| # | self % | cum % of guest | incl % | address | function | subsystem | top callers (share of its self) |\n'
      '|---:|---:|---:|---:|---|---|---|---|\n')
    cum = 0
    rank = 0
    for addr, c, inc, label, g, src in rows:
        if rank >= a.top:
            break
        rank += 1
        if addr < HOST_BASE:
            cum += c
        cs = callers.get(addr)
        ctext = ', '.join('%08x %.0f%%' % (cr, 100.0 * n / max(c, 1)) for cr, n in cs.most_common(2)) if cs else ''
        w('| %d | %.2f | %s | %.1f | %08x | %s | %s | %s |\n' % (
            rank, pct(c), '%.1f' % pct(cum, guest_self) if addr < HOST_BASE else '', pct(inc), addr,
            label.replace('|', '\\|')[:100], g, ctext))
    w('\n')


if __name__ == '__main__':
    main()
