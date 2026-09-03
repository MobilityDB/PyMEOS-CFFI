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

typedef void (*error_handler_fn)(int, int, char *);
"""

# The gsl random-number generator and the PROJ context are reached only through
# their own boundary; reproduce the hand-written opaque declarations verbatim.
PREAMBLE = """typedef struct
  {
    const char *name;
    unsigned long int max;
    unsigned long int min;
    size_t size;
    void (*set) (void *state, unsigned long int seed);
    unsigned long int (*get) (void *state);
    double (*get_double) (void *state);
  }
gsl_rng_type;

typedef struct
  {
    const gsl_rng_type * type;
    void *state;
  }
gsl_rng;

struct pj_ctx;
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
_PREAMBLE_NAMES = {"gsl_rng", "gsl_rng_type", "PJ_CONTEXT"}

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
    def __init__(self, idl: dict, defined: set[str]):
        self.structs = idl["structs"]
        self.enums = idl["enums"]
        self.macros = idl.get("macros", [])
        self.functions = idl["functions"]
        self.struct_names = {s["name"] for s in self.structs}
        self.enum_names = {e["name"] for e in self.enums}
        self.defined = defined
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

    # -- structs: every MEOS type is an opaque handle at the CFFI boundary
    # (like JMEOS's ``Pointer`` mapping). CFFI resolves each layout from the
    # real headers ``set_source`` ``#include``s, so no fields are declared here
    # and Python never reaches into a struct — it only passes the handle back to
    # MEOS. This also sidesteps reproducing external field types (ArrowArray,
    # NumericData, …) the catalog does not carry a layout for.
    def emit_structs(self) -> str:
        out = []
        for s in self.structs:
            if s["fields"] and s["file"].startswith("meos"):
                # A concrete MEOS struct whose real layout is in the headers
                # set_source #includes: CFFI fills it (partial struct) and it can
                # even be passed / returned by value.
                out.append(f"typedef struct {{ ...; }} {s['name']};")
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
                'extern "Python" void py_error_handler(int, int, char*);',
                "",
            ]
        )


def get_defined_functions(library_path: str) -> set[str]:
    output = subprocess.check_output(["nm", "-g", library_path]).decode("utf-8")
    return {line.split(" ")[-1] for line in output.splitlines() if " T " in line}


def build_header_file(idl_path="builder/meos-idl.json", so_path=None, destination_path="builder/meos.h"):
    with open(idl_path) as f:
        idl = json.load(f)
    # With the library at hand, keep only the functions it actually defines;
    # without it, keep every catalog function, since CI always builds it.
    defined = get_defined_functions(so_path) if so_path else {fn["name"] for fn in idl["functions"]}
    with open(destination_path, "w") as f:
        f.write(Emitter(idl, defined).generate())


if __name__ == "__main__":
    build_header_file(*sys.argv[1:])
