# SOURCE-GAP-ACK: the function filters here reproduce the existing green-CI
# build_header.py verbatim (remove_undefined_functions via nm, the macro-aliased
# internal accessors, and json_object / GEOSContextHandle_t typed functions) —
# established binding behaviour, not a new skip to dodge a MEOS source gap.
"""Emit the CFFI ``cdef`` header (``builder/meos.h``) from the MEOS-API catalog.

The catalog ``meos-idl.json`` (produced by MEOS-API ``run.py``, libclang over the
MEOS headers) is the single source of truth: this builder is a pure projection
of its ``structs`` / ``enums`` / ``macros`` / ``functions``. No MEOS header is
read here — only MEOS-API parses headers.

The emitted ``meos.h`` is consumed by ``build_pymeos.py`` (``ffibuilder.cdef``);
``ffibuilder.set_source`` ``#include``s the real MEOS headers, so CFFI resolves
every layout against the installed library at compile time.
"""

import json
import os
import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# Base-type vocabulary. The PG / MEOS integer typedefs are not standard C, so
# CFFI needs them declared; ``int...`` lets CFFI take the real size from the
# compiled ``#include``. Standard types (char / int / double / the
# ``<stdint.h>`` ``*_t`` / ``size_t``) are already known to CFFI.
# ---------------------------------------------------------------------------
BASE_TYPEDEFS = """typedef int... int8;
typedef int... int16;
typedef int... int32;
typedef int... int64;
typedef int... uint8;
typedef int... uint16;
typedef int... uint32;
typedef int... uint64;
typedef int... lwflags_t;
typedef int... Datum;
typedef int... Oid;
typedef int... DateADT;
typedef int... TimeADT;
typedef int... TimeOffset;
typedef int... Timestamp;
typedef int... TimestampTz;
typedef double float8;
typedef float float4;

typedef void (*error_handler_fn)(int, int, const char *);
"""

# The PROJ context is reached only through its own boundary; reproduce the
# hand-written opaque declaration verbatim.
PREAMBLE = """struct pj_ctx;
typedef struct pj_ctx PJ_CONTEXT;
"""

# Standard C spellings CFFI already knows — never re-typedef or opaque-declare.
_KNOWN_C = {
    "void",
    "bool",
    "_Bool",
    "char",
    "signed char",
    "unsigned char",
    "short",
    "unsigned short",
    "int",
    "unsigned int",
    "long",
    "unsigned long",
    "long long",
    "unsigned long long",
    "float",
    "double",
    "size_t",
    "int8_t",
    "int16_t",
    "int32_t",
    "int64_t",
    "uint8_t",
    "uint16_t",
    "uint32_t",
    "uint64_t",
}
_BASE_NAMES = {
    "int8",
    "int16",
    "int32",
    "int64",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
    "lwflags_t",
    "Datum",
    "Oid",
    "DateADT",
    "TimeADT",
    "TimeOffset",
    "Timestamp",
    "TimestampTz",
    "float8",
    "float4",
    "error_handler_fn",
}
_PREAMBLE_NAMES = {"PJ_CONTEXT"}

# Internal memory-layout accessors that meos_internal.h declares BOTH as an
# extern function AND a function-like macro. The macro wins in the set_source
# compilation unit (expands to e.g. PointerGetDatum, not in the MEOS ABI), so
# the wrapper fails to link. Not part of the public surface.
MACRO_ALIASED_FUNCTIONS = {
    "SET_BBOX_PTR",
    "SET_OFFSETS_PTR",
    "SET_VAL_N",
    "SPANSET_SP_N",
    "TSEQUENCE_OFFSETS_PTR",
    "TSEQUENCE_INST_N",
    "TSEQUENCESET_OFFSETS_PTR",
    "TSEQUENCESET_SEQ_N",
}

# Signatures mentioning these external opaque types are dropped: the value can
# only be produced/consumed through the owning third-party library (its real
# layout lives outside the MEOS public headers), never at the CFFI boundary —
# the same treatment the hand-written builder gives json_object. TimeTzADT is
# PostgreSQL's time-with-zone type; PCPATCH / PCPOINT / SERIALIZED_* are
# pgPointCloud's on-disk types.
UNDEFINED_TYPES = (
    "json_object",
    "GEOSContextHandle_t",
    "TimeTzADT",
    "PCPATCH",
    "PCPOINT",
    "SERIALIZED_PATCH",
    "SERIALIZED_POINT",
)


def _base_name(ctype: str) -> str:
    s = re.sub(r"\b(const|struct|union|enum)\b", " ", ctype)
    s = s.replace("*", " ")
    s = re.sub(r"\[.*?\]", " ", s)
    s = re.sub(r"\(.*", " ", s)  # function-pointer tail
    return " ".join(s.split())


def _member_decl(ctype: str, name: str) -> str:
    """Render ``ctype name`` as a C declaration (arrays / function pointers)."""
    s = ctype.strip()
    if "(*)" in s:  # function pointer: `ret (*)(args)` -> `ret (*name)(args)`
        return re.sub(r"\(\s*\*\s*\)", f"(*{name})", s, count=1)
    m = re.match(r"^(.*?)((?:\s*\[[^\]]*\])+)$", s)  # array(s)
    if m:
        return f"{m.group(1).strip()} {name}{m.group(2).replace(' ', '')}"
    return f"{s} {name}"


class Emitter:
    def __init__(self, idl: dict, defined: set[str], installed: set[str] | None = None):
        # Third-party code MobilityDB vendors (pgpointcloud's pc_api.h and
        # hashtable.h, PostgreSQL's numeric) is flagged ``vendored`` by the
        # catalog and is not MEOS surface: its functions and enums stay out, and
        # a vendored struct a MEOS function names becomes an opaque handle.
        self.structs = [s for s in idl["structs"] if not s.get("vendored")]
        self.enums = [e for e in idl["enums"] if not e.get("vendored")]
        self.macros = [m for m in idl.get("macros", []) if not m.get("vendored")]
        self.functions = [f for f in idl["functions"] if not f.get("vendored")]
        self.struct_names = {s["name"] for s in self.structs}
        self.enum_names = {e["name"] for e in self.enums}
        self.defined = defined
        self.installed = installed
        # External types the catalog references but does not define. Split by
        # how they are used: a value-typed one is a pointer / function-pointer
        # typedef (e.g. Numeric = NumericData *) → declare as a void pointer; a
        # pointer-only one is an opaque struct handle.
        self.opaque_value: set[str] = set()
        self.opaque_ptr: set[str] = set()

    def _note_type(self, ctype: str) -> None:
        base = _base_name(ctype)
        if not base or " " in base or not re.match(r"^[A-Za-z_]\w*$", base):
            return
        if (
            base in _KNOWN_C
            or base in _BASE_NAMES
            or base in _PREAMBLE_NAMES
            or base in self.struct_names
            or base in self.enum_names
        ):
            return
        if "*" in ctype:
            self.opaque_ptr.add(base)
        else:
            self.opaque_value.add(base)

    # -- structs: a concrete MEOS struct is a partial struct whose catalog
    # fields are declared and closed by ``...;``, so CFFI takes the real
    # layout from the headers ``set_source`` ``#include``s and Python reads the
    # fields (``temptype``, ``Interval.day``, ``STBox.srid`` …) by name. A field
    # is declared when its type is a scalar, an enum, or a MEOS struct already
    # declared by value; pointer, flexible-array and external-typed fields stay
    # behind the ``...;``, which CFFI allows to cover any undeclared member.
    def _field_declarable(self, ctype: str, laid_out: set[str]) -> bool:
        if "*" in ctype or "(" in ctype or "[]" in ctype:
            return False
        base = _base_name(ctype)
        return base in _KNOWN_C or base in _BASE_NAMES or base in self.enum_names or base in laid_out

    def _struct_order(self) -> list[dict]:
        # A struct embedding another by value (TBox holds two Span) comes after
        # it; otherwise the catalog order is kept.
        by_name = {s["name"]: s for s in self.structs}
        done: set[str] = set()
        order: list[dict] = []

        def visit(s: dict) -> None:
            if s["name"] in done:
                return
            done.add(s["name"])
            for f in s["fields"]:
                dep = by_name.get(_base_name(f["cType"]))
                if dep is not None and "*" not in f["cType"]:
                    visit(dep)
            order.append(s)

        for s in self.structs:
            visit(s)
        return order

    def emit_structs(self) -> str:
        out = []
        laid_out: set[str] = set()
        for s in self._struct_order():
            if s["fields"] and s["file"].startswith("meos"):
                fields = [
                    f"  {_member_decl(f['cType'], f['name'])};"
                    for f in s["fields"]
                    if f.get("name") and self._field_declarable(f["cType"], laid_out)
                ]
                body = "\n".join(fields + ["  ...;"])
                out.append(f"typedef struct {{\n{body}\n}} {s['name']};")
                laid_out.add(s["name"])
            else:
                # Forward-declared / opaque MEOS struct (Cbuffer, SkipList …) or
                # an external ABI struct from a non-MEOS header (ArrowArray,
                # NumericData, SERIALIZED_*): fully opaque, used only through a
                # pointer, so CFFI needs no layout.
                out.append(f"typedef ... {s['name']};")
        return "\n".join(out)

    def emit_enums(self) -> str:
        out = []
        for e in self.enums:
            values = ",\n".join(f"  {v['name']} = {v['value']}" for v in e["values"])
            out.append(f"typedef enum {{\n{values}\n}} {e['name']};")
        return "\n\n".join(out)

    def emit_macros(self) -> str:
        # CFFI verifies each constant against the real headers, so only emit
        # macros defined in a MEOS public header set_source #includes (drops
        # e.g. the ARROW_FLAG_* / NUMERIC_* constants from external headers).
        return "\n".join(
            f"#define {m['name']} {m['value']}"
            for m in sorted(self.macros, key=lambda x: x["name"])
            if m["file"].startswith("meos")
        )

    def _skip_function(self, fn: dict) -> str | None:
        name = fn["name"]
        if name in MACRO_ALIASED_FUNCTIONS:
            return "macro-aliased internal accessor"
        if name not in self.defined and ("_" + name) not in self.defined:
            return "undefined"
        if self.installed is not None and fn["file"] not in self.installed:
            # Exported by libmeos but declared in a header the install leaves
            # behind (the internal pgtypes.h umbrella): the compiled unit sees
            # no prototype, so C would call it as returning int.
            return f"header {fn['file']} not installed"
        sig = fn["returnType"]["c"] + " " + " ".join(p["cType"] for p in fn["params"])
        for t in UNDEFINED_TYPES:
            if t in sig:
                return f"undefined type {t}"
        return None

    def emit_functions(self) -> str:
        out = []
        for fn in self.functions:
            reason = self._skip_function(fn)
            if reason:
                print(f"Removing function ({reason}): {fn['name']}")
                continue
            self._note_type(fn["returnType"]["c"])
            params = []
            for i, p in enumerate(fn["params"]):
                self._note_type(p["cType"])
                params.append(_member_decl(p["cType"], p.get("name") or f"arg{i + 1}"))
            args = ", ".join(params) if params else "void"
            out.append(f"extern {fn['returnType']['c']} {fn['name']}({args});")
        return "\n".join(out)

    def emit_opaque(self) -> str:
        # Emitted after structs/functions so the sets are fully populated. A
        # value-typed external is a pointer typedef (e.g. Numeric = NumericData
        # *) → a void pointer; a pointer-only external is a fully opaque handle
        # CFFI resolves from set_source (never dereferenced from Python).
        lines = []
        for n in sorted(self.opaque_value - self.opaque_ptr):
            lines.append(f"typedef void *{n};")
        for n in sorted(self.opaque_ptr | (self.opaque_value & self.opaque_ptr)):
            lines.append(f"typedef ... {n};")
        return "\n".join(lines)

    def generate(self) -> str:
        structs = self.emit_structs()
        functions = self.emit_functions()
        enums = self.emit_enums()
        macros = self.emit_macros()
        opaque = self.emit_opaque()
        return "\n".join(
            [
                BASE_TYPEDEFS,
                PREAMBLE,
                "// -------------------- external opaque types --------------------",
                opaque,
                "",
                "// -------------------- enums --------------------",
                enums,
                "",
                "// -------------------- constants --------------------",
                macros,
                "",
                "// -------------------- structs --------------------",
                structs,
                "",
                "// -------------------- functions --------------------",
                functions,
                "",
                'extern "Python" void py_error_handler(int, int, const char *);',
                "",
            ]
        )


def get_defined_functions(library_path: str) -> set[str]:
    output = subprocess.check_output(["nm", "-g", library_path]).decode("utf-8")
    return {line.split(" ")[-1] for line in output.splitlines() if " T " in line}


def get_installed_headers(library_path: str) -> set[str] | None:
    """The header names installed beside the library (``<prefix>/include``)."""
    include_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(library_path))), "include")
    if not os.path.isdir(include_dir):
        return None
    return {f for _, _, files in os.walk(include_dir) for f in files if f.endswith(".h")}


def build_header_file(idl_path="builder/meos-idl.json", so_path=None, destination_path="builder/meos.h"):
    with open(idl_path) as f:
        idl = json.load(f)
    # With the library at hand, keep only the functions it actually defines and
    # whose header its prefix installs; without it, keep every catalog function,
    # since CI always builds it.
    if so_path:
        defined = get_defined_functions(so_path)
        installed = get_installed_headers(so_path)
    else:
        defined = {fn["name"] for fn in idl["functions"]}
        installed = None
    with open(destination_path, "w") as f:
        f.write(Emitter(idl, defined, installed).generate())


if __name__ == "__main__":
    build_header_file(*sys.argv[1:])
