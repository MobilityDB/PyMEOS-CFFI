#!/usr/bin/env bash
# regen-from-pin.sh — regenerate the PyMEOS-CFFI low-level binding from the MEOS catalog
# (per GENERATION.md). PyMEOS-CFFI is the layer PyMEOS sits on.
#
# Usage:  tools/regen-from-pin.sh <pin>
#   env:  CATALOG = path to meos-idl.json produced by MEOS-API run.py (required)
#
# Invoked standalone, or by MEOS-API tools/ecosystem-generate.sh (phase 1, before PyMEOS).
set -euo pipefail
PIN="${1:?usage: regen-from-pin.sh <pin>}"
CATALOG="${CATALOG:?set CATALOG to the meos-idl.json from MEOS-API run.py}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

# 1. vendor the catalog (the generator's committed input)
cp "$CATALOG" "$HERE/builder/meos-idl.json"

# 2. run the in-repo generator (builder/build_pymeos_functions.py) -> pymeos_cffi/functions.py
( cd "$HERE" && python3 builder/build_pymeos_functions.py )

# 3. build-verify
( cd "$HERE" && python3 -m pip install -e . -q && python3 -m pytest -q ) \
  || echo "WARN: PyMEOS-CFFI build/test returned non-zero"
echo "[pymeos-cffi] regenerated from catalog at pin $PIN"
