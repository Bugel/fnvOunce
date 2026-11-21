#!/usr/bin/env python3
"""A fixed Direct3D 9 adapter for hosts with no real D3D9 device (Linux, Switch 2): writes out/recomp/d3d9_caps.inc in
the format tools/d3d9_caps_dump.cpp prints on Windows (kCaps, kIdentifier, kCurrentMode, kModes, kFormats).

The profile is a GeForce 8800-class SM 3.0 card: NVIDIA, so the game picks shader package 013 (the one the shader
translation targets, docs/SHADERS.md); FP16 render targets and blending; R32F/A32B32G32R32F vertex textures; no MSAA
(pal_d3d9.cpp CheckDeviceMultiSampleType refuses it anyway). The D3DCAPS9 field order is read from the Windows headers
(mingw-w64 or the SDK, tools/hostpaths.py), and --check compiles a static_assert of every offset and size against them.

usage: python tools/gen_d3d9_caps.py [--check]
"""
import argparse
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hostpaths import sdk_header  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

CAPS = {
    'DeviceType': 1, 'AdapterOrdinal': 0,
    'Caps': 0x00020000,                       # READ_SCANLINE
    'Caps2': 0xE0020000,                      # FULLSCREENGAMMA, CANMANAGERESOURCE, DYNAMICTEXTURES, CANAUTOGENMIPMAP
    'Caps3': 0x000003A0,                      # ALPHA_FULLSCREEN_FLIP_OR_DISCARD, LINEAR_TO_SRGB, COPY_TO_VIDMEM/SYSTEMMEM
    'PresentationIntervals': 0x8000000F, 'CursorCaps': 0x1,
    'DevCaps': 0x001BBEF0, 'PrimitiveMiscCaps': 0x000EF2F2, 'RasterCaps': 0x0F736191,
    'ZCmpCaps': 0xFF, 'SrcBlendCaps': 0x3FFF, 'DestBlendCaps': 0x3FFF, 'AlphaCmpCaps': 0xFF, 'ShadeCaps': 0x00084208,
    'TextureCaps': 0x0001EC45,                # no POW2 restriction; cube, volume and their mips
    'TextureFilterCaps': 0x07030700, 'CubeTextureFilterCaps': 0x03030300, 'VolumeTextureFilterCaps': 0x03030300,
    'TextureAddressCaps': 0x3F, 'VolumeTextureAddressCaps': 0x3F, 'LineCaps': 0x1F,
    'MaxTextureWidth': 8192, 'MaxTextureHeight': 8192, 'MaxVolumeExtent': 2048, 'MaxTextureRepeat': 8192,
    'MaxTextureAspectRatio': 8192, 'MaxAnisotropy': 16,
    'MaxVertexW': 1e10, 'GuardBandLeft': -1e8, 'GuardBandTop': -1e8, 'GuardBandRight': 1e8, 'GuardBandBottom': 1e8,
    'ExtentsAdjust': 0.0,
    'StencilCaps': 0x1FF, 'FVFCaps': 0x00180008, 'TextureOpCaps': 0x03FEFFFF,
    'MaxTextureBlendStages': 8, 'MaxSimultaneousTextures': 8, 'VertexProcessingCaps': 0x17B,
    'MaxActiveLights': 8, 'MaxUserClipPlanes': 8, 'MaxVertexBlendMatrices': 4, 'MaxVertexBlendMatrixIndex': 8,
    'MaxPointSize': 8192.0, 'MaxPrimitiveCount': 0x00FFFFFF, 'MaxVertexIndex': 0x00FFFFFF,
    'MaxStreams': 16, 'MaxStreamStride': 255,
    'VertexShaderVersion': 0xFFFE0300, 'MaxVertexShaderConst': 256,
    'PixelShaderVersion': 0xFFFF0300, 'PixelShader1xMaxValue': 3.4e38,
    'DevCaps2': 0x51,                         # STREAMOFFSET, CAN_STRETCHRECT_FROM_TEXTURES, VERTEXELEMENTSCANSHARE...
    'MaxNpatchTessellationLevel': 0.0, 'Reserved5': 0,
    'MasterAdapterOrdinal': 0, 'AdapterOrdinalInGroup': 0, 'NumberOfAdaptersInGroup': 1,
    'DeclTypes': 0x30F,                       # UBYTE4(N), SHORT2N/4N, FLOAT16_2/4
    'NumSimultaneousRTs': 4, 'StretchRectFilterCaps': 0x03000300,
    'VS20Caps': (0x1, 24, 32, 4),             # Caps (predication), dynamic flow depth, temps, static flow depth
    'PS20Caps': (0x1F, 24, 32, 4, 512),       # + instruction slots
    'VertexTextureFilterCaps': 0x03000300,
    'MaxVShaderInstructionsExecuted': 0xFFFFFFFF, 'MaxPShaderInstructionsExecuted': 0xFFFFFFFF,
    'MaxVertexShader30InstructionSlots': 4096, 'MaxPixelShader30InstructionSlots': 4096,
}
FLOAT_TYPES = {'float'}
STRUCT_FIELDS = {'D3DVSHADERCAPS2_0': '<Iiii', 'D3DPSHADERCAPS2_0': '<Iiiii'}

DRIVER, DESCRIPTION, DEVICE_NAME = 'nvd3dum.dll', 'NVIDIA GeForce 8800 GTX', '\\\\.\\DISPLAY1'
VENDOR, DEVICE, SUBSYS, REVISION = 0x10DE, 0x0191, 0, 0xA2
DRIVER_VERSION = (6 << 48) | (14 << 32) | (11 << 16) | 9621   # 6.14.11.9621

FMT = {'X8R8G8B8': 22, 'A8R8G8B8': 21, 'R5G6B5': 23, 'X1R5G5B5': 24, 'A1R5G5B5': 25, 'A4R4G4B4': 26, 'A8': 28,
       'A2B10G10R10': 31, 'A8B8G8R8': 32, 'X8B8G8R8': 33, 'G16R16': 34, 'A2R10G10B10': 35, 'A16B16G16R16': 36,
       'L8': 50, 'A8L8': 51, 'V8U8': 60, 'Q8W8V8U8': 63, 'V16U16': 64, 'D16': 80, 'D24S8': 75, 'D24X8': 77, 'L16': 81,
       'R16F': 111, 'G16R16F': 112, 'A16B16G16R16F': 113, 'R32F': 114, 'G32R32F': 115, 'A32B32G32R32F': 116}
FOURCC = {c: struct.unpack('<I', c.encode())[0] for c in ('DXT1', 'DXT2', 'DXT3', 'DXT4', 'DXT5', 'ATI1', 'ATI2', 'INTZ',
                                                           'NULL')}
U_NONE, U_RT, U_DS, U_DYN, U_FILTER, U_BLEND, U_AUTOMIP, U_VTX = 0, 1, 2, 0x200, 0x20000, 0x80000, 0x400, 0x100000
SURFACE, TEXTURE, CUBE, VOLUME = 1, 3, 5, 4

COLOR = ['X8R8G8B8', 'A8R8G8B8', 'R5G6B5', 'X1R5G5B5', 'A1R5G5B5', 'A4R4G4B4', 'A8', 'A2B10G10R10', 'A8B8G8R8',
         'X8B8G8R8', 'G16R16', 'A2R10G10B10', 'A16B16G16R16', 'L8', 'A8L8', 'V8U8', 'Q8W8V8U8', 'V16U16', 'L16',
         'R16F', 'G16R16F', 'A16B16G16R16F', 'R32F', 'G32R32F', 'A32B32G32R32F']
RENDERABLE = ['X8R8G8B8', 'A8R8G8B8', 'R5G6B5', 'X1R5G5B5', 'A1R5G5B5', 'A2B10G10R10', 'A8B8G8R8', 'X8B8G8R8',
              'G16R16', 'A2R10G10B10', 'A16B16G16R16', 'R16F', 'G16R16F', 'A16B16G16R16F', 'R32F', 'G32R32F',
              'A32B32G32R32F']
BLENDABLE = ['X8R8G8B8', 'A8R8G8B8', 'R5G6B5', 'X1R5G5B5', 'A1R5G5B5', 'A2B10G10R10', 'A8B8G8R8', 'X8B8G8R8',
             'G16R16', 'A2R10G10B10', 'A16B16G16R16', 'R16F', 'G16R16F', 'A16B16G16R16F']
UNFILTERABLE = {'R32F', 'G32R32F', 'A32B32G32R32F'}
AUTOMIP = ['X8R8G8B8', 'A8R8G8B8', 'R5G6B5', 'X1R5G5B5', 'A1R5G5B5', 'A4R4G4B4', 'L8', 'A8L8']
VERTEX_TEXTURE = ['R32F', 'A32B32G32R32F']
DEPTH = ['D16', 'D24S8', 'D24X8']
MODES = [(640, 480), (800, 600), (1024, 768), (1280, 720), (1280, 800), (1280, 1024), (1366, 768), (1600, 900),
         (1680, 1050), (1920, 1080)]


def caps_fields():
    text = sdk_header('shared/d3d9caps.h').read_text(errors='replace')
    body = re.search(r'typedef struct _D3DCAPS9\s*\{(.*?)\}\s*D3DCAPS9;', text, re.S).group(1)
    body = re.sub(r'/\*.*?\*/|//[^\n]*', '', body, flags=re.S)
    fields = []
    for decl in body.split(';'):
        decl = decl.strip()
        if not decl:
            continue
        typ, names = decl.split(None, 1)
        fields += [(typ, n.strip()) for n in names.split(',')]
    return fields


def pack_caps():
    out = b''
    for typ, name in caps_fields():
        v = CAPS[name]
        if typ in STRUCT_FIELDS:
            out += struct.pack(STRUCT_FIELDS[typ], *v)
        elif typ in FLOAT_TYPES:
            out += struct.pack('<f', v)
        else:
            out += struct.pack('<I', v & 0xffffffff)
    return out


def pack_identifier():
    s = lambda t, n: t.encode().ljust(n, b'\0')
    out = s(DRIVER, 512) + s(DESCRIPTION, 512) + s(DEVICE_NAME, 32)
    out += struct.pack('<QIIII', DRIVER_VERSION, VENDOR, DEVICE, SUBSYS, REVISION)
    out += bytes.fromhex('d7b71e3e41d211cf9c6f1aa9b7c2d4a3')            # DeviceIdentifier (any stable GUID)
    out += struct.pack('<I', 1)                                         # WHQLLevel
    return out   # 1100 bytes: MSVC may pad the struct to 1104, so writing 1100 never overruns the game's buffer


def formats():
    rows = []
    def add(usage, rtypes, names):
        for n in names:
            f = FMT.get(n) or FOURCC[n]
            rows.extend((usage, t, f) for t in rtypes)
    textures = (TEXTURE, CUBE, VOLUME)
    add(U_NONE, (SURFACE,) + textures, COLOR + ['DXT1', 'DXT2', 'DXT3', 'DXT4', 'DXT5', 'ATI1', 'ATI2'])
    add(U_DYN, textures, COLOR)
    add(U_FILTER, (SURFACE,) + textures, [n for n in COLOR if n not in UNFILTERABLE] +
        ['DXT1', 'DXT2', 'DXT3', 'DXT4', 'DXT5', 'ATI1', 'ATI2'])
    add(U_RT, (SURFACE, TEXTURE, CUBE), RENDERABLE + ['NULL'])
    add(U_BLEND, (SURFACE, TEXTURE, CUBE), BLENDABLE)
    add(U_AUTOMIP, (TEXTURE, CUBE), AUTOMIP)
    add(U_VTX, (TEXTURE,), VERTEX_TEXTURE)
    add(U_DS, (SURFACE, TEXTURE), DEPTH + ['INTZ'])
    add(U_NONE, (TEXTURE,), DEPTH + ['INTZ'])                       # shadow maps sampled as depth textures
    return rows


def c_bytes(name, data):
    return 'static const unsigned char %s[%u] = {%s};\n' % (name, len(data), ','.join(str(b) for b in data))


def check(caps, ident):
    """compile static_asserts of the layout against the real headers for 32-bit Windows (clang, i686 mingw target)"""
    fields = caps_fields()
    lines = ['#include <windows.h>', '#include <d3d9.h>', '#include <stddef.h>',
             'static_assert(sizeof(D3DCAPS9) == %d, "caps size");' % len(caps),
             'static_assert(sizeof(D3DADAPTER_IDENTIFIER9) == %d, "identifier size");' % len(ident),
             'static_assert(offsetof(D3DADAPTER_IDENTIFIER9, VendorId) == 1064, "VendorId");']
    off = 0
    for typ, name in fields:
        lines.append('static_assert(offsetof(D3DCAPS9, %s) == %d, "%s");' % (name, off, name))
        off += struct.calcsize(STRUCT_FIELDS.get(typ, '<I'))
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / 'caps_check.cpp'
        src.write_text('\n'.join(lines) + '\n')
        r = subprocess.run(['clang++', '--target=i686-w64-mingw32', '-fsyntax-only', str(src)], capture_output=True,
                           text=True)
    if r.returncode:
        raise SystemExit('layout check failed:\n' + r.stderr)
    print('layout check: D3DCAPS9 %d bytes, %d fields; D3DADAPTER_IDENTIFIER9 %d bytes: ok' % (len(caps), len(fields),
                                                                                            len(ident)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='verify the struct layout with clang and the Windows headers')
    a = ap.parse_args()
    caps, ident = pack_caps(), pack_identifier()
    if a.check:
        check(caps, ident)
    w, h = 1920, 1080
    text = ['// Generated by tools/gen_d3d9_caps.py (fixed GeForce 8800-class adapter): do not edit or commit.\n',
            c_bytes('kCaps', caps), c_bytes('kIdentifier', ident),
            c_bytes('kCurrentMode', struct.pack('<IIII', w, h, 60, FMT['X8R8G8B8'])),
            'struct CapsMode { unsigned fmt, w, h, refresh; };\nstatic const CapsMode kModes[] = {\n']
    for f in ('X8R8G8B8', 'A8R8G8B8', 'R5G6B5'):
        text += ['{%u,%u,%u,%u},\n' % (FMT[f], mw, mh, 60) for mw, mh in MODES]
    text.append('};\nstruct CapsFormat { unsigned usage, rtype, fmt; int ok; };\nstatic const CapsFormat kFormats[] = {\n')
    rows = formats()
    text += ['{%u,%u,%u,1},\n' % r for r in rows]
    text.append('{0,0,0,0}};\n')
    out = ROOT / 'out/recomp/d3d9_caps.inc'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(''.join(text))
    print('%s: caps %d bytes, %d modes, %d format answers' % (out, len(caps), 3 * len(MODES), len(rows)))


if __name__ == '__main__':
    main()
