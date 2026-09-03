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

# Live initialisation check: the standard happy-path cycle works.
meos_initialize("UTC")
meos_finalize()
print(f"PyMEOS CFFI build + shape smoke test OK on {label}")
