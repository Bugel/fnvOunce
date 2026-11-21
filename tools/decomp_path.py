r"""Where the decompilation lives. Every tool takes it from here; set FNV_DECOMP to use another copy.

The default is the updated copy (2026-11-06). The earlier copy (E:\Games\fnv_decomp-main)
was deleted on 2026-11-08.
"""
import os

_DEFAULTS = [r'E:\Games\fnv_decomp-main-updated',
             os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'fnv_decomp')]   # sibling clone
DECOMP_DIR = os.environ.get('FNV_DECOMP') or next((d for d in _DEFAULTS if os.path.isdir(d)), _DEFAULTS[0])
