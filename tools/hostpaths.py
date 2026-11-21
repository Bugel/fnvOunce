"""Where the build tools and Windows SDK pieces live on this machine (Windows or Linux).

Windows keeps the original locations (LLVM in Program Files, the Windows 10 SDK). On Linux the tools come from the
distribution's LLVM and the Windows headers/import libraries from mingw-w64 (i686). Every path can be overridden:
  FNV_LLVM_BIN     folder with llvm-objdump / llvm-nm / clang
  FNV_SDK_INCLUDE  folder with d3d9.h, dinput.h, dsound.h (Windows: the SDK's Include\\<version>)
  FNV_SDK_LIB      folder with the x86 import libraries
"""
import os
import shutil
from pathlib import Path

WINDOWS = os.name == 'nt'


def llvm_tool(name):
    """Path of an LLVM tool (llvm-objdump, llvm-nm, ...)."""
    if os.environ.get('FNV_LLVM_BIN'):
        return str(Path(os.environ['FNV_LLVM_BIN']) / (name + ('.exe' if WINDOWS else '')))
    if WINDOWS:
        return r'C:\Program Files\LLVM\bin\%s.exe' % name
    for cand in [name] + ['%s-%d' % (name, v) for v in range(25, 13, -1)]:
        if shutil.which(cand):
            return shutil.which(cand)
    raise SystemExit('%s not found: install LLVM or set FNV_LLVM_BIN' % name)


def sdk_include():
    """Folder holding the SDK's shared/ and um/ headers (Windows) or the flat mingw-w64 include folder."""
    if os.environ.get('FNV_SDK_INCLUDE'):
        return Path(os.environ['FNV_SDK_INCLUDE'])
    if WINDOWS:
        return sorted(Path(r'C:/Program Files (x86)/Windows Kits/10/Include').iterdir())[-1]
    for p in (Path('/usr/share/mingw-w64/include'), Path('/usr/i686-w64-mingw32/include')):
        if (p / 'd3d9.h').exists():
            return p
    raise SystemExit('Windows headers not found: install mingw-w64 or set FNV_SDK_INCLUDE')


def sdk_header(rel):
    """An SDK header by its Windows SDK relative path ('um/dinput.h'); mingw-w64 keeps them in one folder."""
    inc = sdk_include()
    p = inc / rel
    return p if p.exists() else inc / Path(rel).name


def sdk_lib(name):
    """An x86 import library by its Windows SDK name ('kernel32.Lib'); mingw-w64 spells it libkernel32.a."""
    if os.environ.get('FNV_SDK_LIB'):
        base = Path(os.environ['FNV_SDK_LIB'])
    elif WINDOWS:
        base = sorted(Path(r'C:\Program Files (x86)\Windows Kits\10\Lib').iterdir())[-1] / 'um/x86'
    else:
        base = Path('/usr/i686-w64-mingw32/lib')
    if (base / name).exists():
        return base / name
    stem = Path(name).stem.lower()
    for cand in ('lib%s.a' % stem, '%s.lib' % stem):
        if (base / cand).exists():
            return base / cand
    raise SystemExit('import library %s not found in %s' % (name, base))
