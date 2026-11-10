"""Post-install smoke test for the catalog-driven PyMEOS CFFI build.

Run after ``pip install`` of the freshly built wheel/sdist. The assertions are
shape-driven and evaluated before any MEOS runtime state is initialised so a
misbehaving wrapper cannot mask itself behind a crash inside ``meos_finalize``.
"""

import inspect
import os

import pymeos_cffi.functions as f
from pymeos_cffi import meos_finalize, meos_initialize, tstzspan_make

label = os.environ.get("PYMEOS_SMOKE_OS", "this platform")

assert callable(tstzspan_make), "tstzspan_make missing"
assert callable(f.tpoint_as_mvtgeom), "tpoint_as_mvtgeom missing"

# gsarr / timesarr are output parameters, not user-facing list args: they must
# NOT appear in the wrapper's parameter list.
sig = inspect.signature(f.tpoint_as_mvtgeom)
for forbidden in ("gsarr", "timesarr"):
    assert forbidden not in sig.parameters, f"tpoint_as_mvtgeom unexpectedly takes {forbidden} as input"

# meos_initialize.tz_str is nullable -> surfaces as a typed Optional. Verify the
# annotation rather than calling, since cycling finalize() can hit known MEOS
# global-state quirks unrelated to the codegen.
ms_sig = inspect.signature(meos_initialize)
tz_param = ms_sig.parameters.get("tz_str")
assert tz_param is not None, "meos_initialize lost tz_str arg"
assert "None" in str(tz_param.annotation), f"tz_str annotation does not allow None: {tz_param.annotation}"

# The cdef spells every callback by the signature the catalog's callbacks list
# states, and a name the catalog's typedefs list defines by that definition.
for name in ("error_handler_fn", "interrupt_handler_fn", "meos_malloc_fn", "meos_realloc_fn", "meos_free_fn"):
    assert f._ffi.typeof(name).kind == "function", f"{name} is {f._ffi.typeof(name).cname}, not a function pointer"
for name, definition in (("TimestampTz", "int64_t"), ("DateADT", "int32_t"), ("Datum", "uintptr_t")):
    assert f._ffi.typeof(name) is f._ffi.typeof(definition), f"{name} is {f._ffi.typeof(name).cname}, not {definition}"

# A function returning a byte array and its length through a size_t output
# parameter returns the bytes, whatever its name: an encoding, a sort key, an
# aggregate state.
for name in ("set_as_wkb", "temporal_sortkey", "npoint_as_wkb", "pose_as_wkb", "cbuffer_as_wkb"):
    ann = inspect.signature(getattr(f, name)).return_annotation
    assert ann in (bytes, "bytes"), f"{name} returns {ann}, not bytes"

# A function returning a string and its length through a size_t output parameter
# returns the string alone: the hexadecimal WKB and EWKB of every type.
for name in ("set_as_hexwkb", "temporal_as_hexwkb", "tspatial_as_hexewkb", "npoint_as_hexwkb", "pose_as_hexewkb"):
    ann = inspect.signature(getattr(f, name)).return_annotation
    assert "tuple" not in str(ann), f"{name} returns {ann}, not the string alone"

# Every string MEOS hands the caller comes with its size, written through a size_t
# output parameter: the wrapper takes no such argument and reads the string by its
# terminator.
for name in (
    "temporal_out",
    "set_out",
    "geo_as_text",
    "temporal_as_mfjson",
    "temporal_as_hexwkb",
    "date_out",
    "meos_version",
):
    fn = getattr(f, name)
    assert "size_out" not in inspect.signature(fn).parameters, f"{name} takes its size as an argument"
    assert "_take_string(result)" in inspect.getsource(fn), f"{name} does not free its string"

# Live initialisation check: the standard happy-path cycle works, and a WKB
# encoding comes back as bytes and its hexadecimal form as their string.
meos_initialize("UTC")
wkb = f.set_as_wkb(f.intset_in("{1, 2, 3}"), 4)
assert isinstance(wkb, bytes) and len(wkb) > 0, f"set_as_wkb returned {type(wkb)}"
hexwkb = f.set_as_hexwkb(f.intset_in("{1, 2, 3}"), 4)
assert isinstance(hexwkb, str) and bytes.fromhex(hexwkb) == wkb, f"set_as_hexwkb returned {hexwkb!r}"
# A string MEOS hands the caller is freed once copied, and one MEOS keeps is only
# copied: the subtype name reads the same on every call.
temp = f.tfloat_in("[1.5@2001-01-01, 2.5@2001-01-02]")
text = "[1.5@2001-01-01 00:00:00+00, 2.5@2001-01-02 00:00:00+00]"
assert f.temporal_out(temp, 15) == f.temporal_out(temp, 15) == text
assert f.temporal_subtype(temp) == f.temporal_subtype(temp) == "Sequence"
# A value holding a character UTF-8 writes in two bytes reads back whole.
ttext = '{"Zürich"@2001-01-01 00:00:00+00, "Liège"@2001-01-02 00:00:00+00}'
assert f.temporal_out(f.ttext_in(ttext), 0) == ttext, f"temporal_out returned {f.temporal_out(f.ttext_in(ttext), 0)!r}"
meos_finalize()
print(f"PyMEOS CFFI build + shape smoke test OK on {label}")
