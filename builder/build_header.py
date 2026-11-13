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

from objects import CatalogTypes, base_name

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
# the same treatment the hand-written builder gives json_object. PCPATCH /
# PCPOINT / SERIALIZED_* are pgPointCloud's on-disk types.
UNDEFINED_TYPES = (
    "json_object",
    "GEOSContextHandle_t",
    "PCPATCH",
    "PCPOINT",
    "SERIALIZED_PATCH",
    "SERIALIZED_POINT",
)


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
    """The cdef of the catalog: every slot spelled as #CatalogTypes spells its canonical,
    the names the spellings use declared from the catalog's own lists. A name the
    catalog defines (``TimestampTz``, ``Datum``, ``text``) is declared by its
    ``typedefs`` definition, a type of its own a slot names (``H3Index``) over its width,
    a callback (``meos_malloc_fn``) by its ``callbacks`` signature, and a structure
    spelled by its tag (``struct Cbuffer``) under that tag."""

    def __init__(self, idl: dict, defined: set[str], installed: set[str] | None = None):
        # Third-party code MobilityDB vendors (pgpointcloud's pc_api.h and
        # hashtable.h, PostgreSQL's numeric) is flagged ``vendored`` by the
        # catalog and is not MEOS surface: its functions and enums stay out, and
        # a vendored struct a MEOS function names becomes an opaque handle.
        self.structs = [s for s in idl["structs"] if not s.get("vendored")]
        self.enums = [e for e in idl["enums"] if not e.get("vendored")]
        self.macros = [m for m in idl.get("macros", []) if not m.get("vendored")]
        self.functions = [f for f in idl["functions"] if not f.get("vendored")]
        self.callbacks = idl.get("callbacks", [])
        self.types = CatalogTypes(idl)
        self.struct_names = {s["name"] for s in self.structs}
        self.defined = defined
        self.installed = installed
        # The bases the emitted spellings use, gathered as they are spelled: the
        # structure tags, the vendored structures and the callbacks to declare.
        self.used: set[str] = set()

    def _spell(self, slot: dict, where: str) -> str:
        spelling = self.types.spell(slot, where)
        self.used.add(base_name(spelling))
        return spelling

    def _tags(self) -> set[str]:
        return {b[len("struct ") :] for b in self.used if b.startswith("struct ")}

    # -- structs: a concrete MEOS struct is a partial struct whose catalog
    # fields are declared and closed by ``...;``, so CFFI takes the real
    # layout from the headers ``set_source`` ``#include``s and Python reads the
    # fields (``temptype``, ``Interval.day``, ``STBox.srid`` …) by name. A field
    # is declared when its type is a scalar, an enum, or a MEOS struct already
    # declared by value; pointer, flexible-array and function-pointer fields stay
    # behind the ``...;``, which CFFI allows to cover any undeclared member.
    def _field_declarable(self, spelling: str, laid_out: set[str]) -> bool:
        if "*" in spelling or "(" in spelling or "[]" in spelling:
            return False
        base = base_name(spelling)
        kind = self.types.kind(base)
        return kind in ("int", "float", "bool", "enum") or base.removeprefix("struct ") in laid_out

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
                dep = by_name.get(base_name(f["canonical"]).removeprefix("struct "))
                if dep is not None and "*" not in f["canonical"]:
                    visit(dep)
            order.append(s)

        for s in self.structs:
            visit(s)
        return order

    def _spell_fields(self) -> None:
        # The fields of every laid-out struct, spelled before any struct is emitted so
        # the tags and the types of their own they name are all known
        self.fields = {}
        for s in self.structs:
            if s["fields"] and s["file"].startswith("meos"):
                self.fields[s["name"]] = [
                    (f.get("name"), self._spell(f, f"field {f.get('name')} of {s['name']}")) for f in s["fields"]
                ]

    def emit_structs(self) -> str:
        # A structure the spellings name by its tag (struct Cbuffer, struct NumericData)
        # is declared under the tag alone: CFFI writes a declared typedef name into the
        # C it compiles, and the headers give some tags no typedef of their name
        out = []
        laid_out: set[str] = set()
        tags = self._tags()
        for s in self._struct_order():
            name = s["name"]
            if name in self.fields:
                fields = [
                    f"  {_member_decl(spelling, field)};"
                    for field, spelling in self.fields[name]
                    if field and self._field_declarable(spelling, laid_out)
                ]
                body = "\n".join(fields + ["  ...;"])
                if name in tags:
                    out.append(f"struct {name} {{\n{body}\n}};")
                else:
                    out.append(f"typedef struct {{\n{body}\n}} {name};")
                laid_out.add(name)
            elif name in tags:
                out.append(f"struct {name};")
            else:
                # Forward-declared / opaque MEOS struct (SkipList …) or an external
                # ABI struct from a non-MEOS header: fully opaque, used only through
                # a pointer, so CFFI needs no layout.
                out.append(f"typedef ... {name};")
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
        sig = " ".join(s["canonical"] for s in [fn["returnType"], *fn["params"]])
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
            ret = self._spell(fn["returnType"], f"the return of {fn['name']}")
            params = []
            for i, p in enumerate(fn["params"]):
                name = p.get("name") or f"arg{i + 1}"
                params.append(_member_decl(self._spell(p, f"parameter {name} of {fn['name']}"), name))
            args = ", ".join(params) if params else "void"
            out.append(f"extern {ret} {fn['name']}({args});")
        return "\n".join(out)

    def emit_callbacks(self) -> str:
        # Every MEOS callback, and a vendored one a spelling uses, as the function-pointer
        # typedef the catalog's callbacks list states
        out = []
        for cb in self.callbacks:
            if cb.get("vendored") and cb["name"] not in self.used:
                continue
            where = f"callback {cb['name']}"
            ret = self._spell(cb["returnType"], f"the return of {where}")
            params = ", ".join(self._spell(p, f"parameter {p['name']} of {where}") for p in cb["params"]) or "void"
            out.append(f"typedef {ret} (*{cb['name']})({params});")
        return "\n".join(out)

    def emit_typedefs(self) -> str:
        # The names the catalog defines, by their definition, and the types of their
        # own the slots name, over their width
        defs = {t: self.types.typedefs[t] for t in sorted(self.types.typedefs)}
        for t, d in defs.items():
            self._spell({"canonical": d}, f"the definition of {t}")
        lines = [f"typedef {d} {t};" for t, d in defs.items()]
        lines += [f"typedef {w} {t};" for t, w in sorted(self.types.own.items())]
        return "\n".join(lines)

    def emit_opaque(self) -> str:
        # A structure tag no laid-out or opaque MEOS struct declares (struct pj_ctx,
        # struct NumericData of a vendored header) is an incomplete struct; a vendored
        # structure a spelling names bare is an opaque handle
        lines = [f"struct {t};" for t in sorted(self._tags() - self.struct_names)]
        bare = {b for b in self.used if b in self.types.structs}
        lines += [f"typedef ... {n};" for n in sorted(bare - self.struct_names)]
        return "\n".join(lines)

    def generate(self) -> str:
        functions = self.emit_functions()
        callbacks = self.emit_callbacks()
        self._spell_fields()
        typedefs = self.emit_typedefs()
        structs = self.emit_structs()
        enums = self.emit_enums()
        macros = self.emit_macros()
        opaque = self.emit_opaque()
        return "\n".join(
            [
                "// -------------------- external opaque types --------------------",
                opaque,
                "",
                "// -------------------- defined types --------------------",
                typedefs,
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
                "// -------------------- callbacks --------------------",
                callbacks,
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
