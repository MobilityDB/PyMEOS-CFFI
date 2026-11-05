import re
from collections.abc import Callable

# The C types CFFI knows by name, by the Python value a slot of the type carries
C_INTEGERS = {
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
    "size_t",
    "int8_t",
    "int16_t",
    "int32_t",
    "int64_t",
    "uint8_t",
    "uint16_t",
    "uint32_t",
    "uint64_t",
    "intptr_t",
    "uintptr_t",
}
C_FLOATS = {"float", "double"}


def base_name(spelling: str) -> str:
    """The type a spelling names, without qualifiers, pointers, array bounds or a
    function-pointer tail, a structure keeping its tag: ``const struct Cbuffer **``
    names ``struct Cbuffer``"""
    s = re.sub(r"\b(const|volatile)\b", " ", spelling)
    s = re.sub(r"\(.*", " ", s)
    s = re.sub(r"\[.*?\]", " ", s)
    return " ".join(s.replace("*", " ").split())


class CatalogTypes:
    """The types of the catalog's slots, read from their ``canonical`` spelling.

    A canonical names a C type, a structure (``Temporal``, or ``struct Cbuffer`` by its
    tag), an enumeration, a callback of the catalog's ``callbacks`` list, or a name the
    catalog's ``typedefs`` list defines (``TimestampTz`` is ``int64_t``, ``text`` is
    ``struct varlena``), which resolves through that definition. A slot whose ``typedef``
    names a type of its own over its width (``H3Index`` over ``uint64_t``, ``lwflags_t``
    over ``uint16_t``) is spelled by that name. A name none of these covers stops the
    build, naming the type and where it occurs. build_header.py's #Emitter declares the
    cdef from it and build_pymeos_functions.py's #get_param_conversion converts from it."""

    def __init__(self, idl: dict) -> None:
        self.typedefs = {t["name"]: t["canonical"] for t in idl.get("typedefs", [])}
        self.structs = {s["name"] for s in idl["structs"]}
        self.enums = {e["name"] for e in idl["enums"]}
        self.callbacks = {c["name"]: c for c in idl.get("callbacks", [])}
        # The types of their own the slots name, each with the width it is over
        self.own: dict[str, str] = {}

    def kind(self, base: str) -> str | None:
        """What a type name is: int, float, bool, void, struct, enum or callback, a
        defined name being what its definition is; None when the catalog does not state
        it"""
        if base in C_INTEGERS:
            return "int"
        if base in C_FLOATS:
            return "float"
        if base in ("bool", "void"):
            return base
        if re.fullmatch(r"struct \w+", base):
            return "struct"
        if base in self.own:
            return self.kind(self.own[base])
        if base in self.typedefs:
            return self.kind(base_name(self.typedefs[base]))
        if base in self.structs:
            return "struct"
        if base in self.enums:
            return "enum"
        if base in self.callbacks:
            return "callback"
        return None

    def spell(self, slot: dict, where: str) -> str:
        """The C spelling of a slot: its canonical, with the type of its own its
        ``typedef`` names in place of the width, as #base_name reads the width"""
        canonical = slot.get("canonical")
        if canonical is None:
            raise SystemExit(f"Cannot map the type of {where}: the catalog gives it no canonical spelling")
        base = base_name(canonical)
        if self.kind(base) is None:
            raise SystemExit(
                f"Cannot map the type {base!r} of {where}: the catalog states it neither as a C type "
                "nor as an entry of its structs, enums, callbacks or typedefs"
            )
        own = slot.get("typedef")
        if not own:
            return canonical
        width = self.own.setdefault(own, base)
        if width != base:
            raise SystemExit(
                f"Cannot map the type {own!r} of {where}: it is over {base!r} here and {width!r} elsewhere"
            )
        return re.sub(rf"\b{re.escape(base)}\b", own, canonical, count=1)

    def is_scalar(self, spelling: str) -> bool:
        """Whether the type, without its pointers, carries a Python bool, int or float, the
        question build_pymeos_functions.py's #is_interoperable asks"""
        return self.kind(base_name(spelling)) in ("bool", "int", "float")


class Conversion:
    def __init__(
        self,
        c_type: str,
        p_type: str,
        p_to_c: Callable[[str], str] | None,
        c_to_p: Callable[[str], str] | None,
    ) -> None:
        super().__init__()
        self.c_type = c_type
        self.p_type = p_type
        self.p_to_c = p_to_c
        self.c_to_p = c_to_p


# The conversions a canonical spelling takes beyond those of its kind: a scalar whose
# type resolves to an integer or a floating number (#CatalogTypes) is a Python int or
# float, as #get_param_conversion of build_pymeos_functions.py derives it.
conversion_map: dict[str, Conversion] = {
    "void": Conversion("void", "None", None, None),
    "bool": Conversion("bool", "bool", None, None),
    "double": Conversion("double", "float", None, None),
    # A char * MEOS returns is the caller's, so it is freed once copied
    # (#_take_string); a const char * names a string MEOS keeps, such as a type
    # name, and is copied alone.
    "char *": Conversion(
        "char *",
        "str",
        lambda p_obj: f"{p_obj}.encode('utf-8')",
        lambda c_obj: f"_take_string({c_obj})",
    ),
    "const char *": Conversion(
        "const char *",
        "str",
        lambda p_obj: f"{p_obj}.encode('utf-8')",
        lambda c_obj: f"_read_string({c_obj})",
    ),
    "text": Conversion(
        "text",
        "str",
        lambda p_obj: f"cstring_to_text({p_obj})",
        lambda c_obj: f"text_to_cstring({c_obj})",
    ),
    "text *": Conversion(
        "text *",
        "str",
        lambda p_obj: f"cstring_to_text({p_obj})",
        lambda c_obj: f"text_to_cstring({c_obj})",
    ),
    "const text": Conversion(
        "const text",
        "str",
        lambda p_obj: f"cstring_to_text({p_obj})",
        lambda c_obj: f"text_to_cstring({c_obj})",
    ),
    "const text *": Conversion(
        "const text *",
        "str",
        lambda p_obj: f"cstring_to_text({p_obj})",
        lambda c_obj: f"text_to_cstring({c_obj})",
    ),
    "int": Conversion("int", "int", None, None),
    "TimestampTz *": Conversion(
        "TimestampTz *",
        "int",
        lambda p_obj: f"_ffi.cast('TimestampTz *', {p_obj})",
        None,
    ),
    "const TimestampTz *": Conversion(
        "const TimestampTz *",
        "int",
        lambda p_obj: f"_ffi.cast('const TimestampTz *', {p_obj})",
        None,
    ),
    "interpType": Conversion("interpType", "InterpolationType", None, None),
}
