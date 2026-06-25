# PyMEOS-CFFI generation — the canonical per-binding generator policy

PyMEOS-CFFI is a **generated** binding — the low-level CFFI layer that PyMEOS (the OO layer,
a separate repo) sits on. This document is the contract for how it is generated, under the
ecosystem-wide per-binding generator policy.

## The policy (ecosystem-wide)

Every MobilityDB language binding is a **pure projection of the MEOS-API catalog**, and
**each binding owns its own generator, in its own repo**, in a canonical layout. The single
source of truth is the **catalog** (`MEOS-API/output/meos-idl.json`, generated from the MEOS
C headers). A binding is an independent, plug-and-play module that owns its generation.

Each binding repo satisfies the same invariants: in-repo generator; own
`tools/pin/compose-order.txt`; vendored/pinned catalog; thin language projection
(language-neutral decisions live in the catalog); full automation toward a zero-hand-written
surface (generate-then-retire; the last green-CI version is the equivalence probe).

## PyMEOS-CFFI scope: the generated CFFI function layer

The generator lives in **`builder/`**: `build_pymeos_functions.py` reads the vendored
`builder/meos-idl.json` and generates `pymeos_cffi/functions.py` (the CFFI wrappers around
the MEOS C API), driven by the `builder/templates`. `build_header.py` / `build_pymeos.py`
assemble the cdef and the compiled CFFI module.

This is the lower of PyMEOS's two layers (the analog of Rust's `meos-sys`): it exposes the
flat MEOS function surface; the PyMEOS repo generates the idiomatic OO layer on top of it.

## Generate-then-retire — the green-CI version is the probe

Any remaining hand-written wrappers are replaced by generated ones **little by little**:
generate the full surface, build green, **prove generated ⊇ hand** against the **last
green-CI version** (the test suite) family by family, then retire the hand path. Never
wipe-first.

## Pinning

PyMEOS-CFFI's vendored `builder/meos-idl.json` is generated from a MobilityDB
`ecosystem-pin-*` via the MEOS-API `run.py`. That pin is the *catalog/surface* input;
PyMEOS-CFFI's own `tools/pin/compose-order.txt` governs *this repo's* PR accumulate. See it
for the composing set and the disposition of every open PR.
