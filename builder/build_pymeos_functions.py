import json
import os.path
import re
import shutil
import subprocess
import sys

from build_pymeos_functions_modifiers import *
from objects import Conversion, conversion_map

# The wrappers project exactly the functions the CFFI cdef declares: build_header.py
# emits builder/meos.h from the same catalog, keeping the functions libmeos defines and
# whose types cross the CFFI boundary, so functions.py follows it rather than a list of
# headers. Catalog order is kept, which groups the wrappers by defining header.
_CDEF_FUNCTION = re.compile(r"^extern .*?\b(\w+)\(", re.MULTILINE)


def cdef_functions(header_path: str) -> set[str]:
    with open(header_path) as f:
        return set(_CDEF_FUNCTION.findall(f.read()))


class Parameter:
    def __init__(
        self,
        name: str,
        converted_name: str,
        ctype: str,
        ptype: str,
        cp_conversion: str | None,
    ) -> None:
        super().__init__()
        self.name = name
        self.converted_name = converted_name
        self.ctype = ctype
        self.ptype = ptype
        self.cp_conversion = cp_conversion
        # A length taken from the array it counts is not a Python argument (#apply_input_arrays).
        self.derived = False

    def is_interoperable(self):
        return any(self.ctype.startswith(x) for x in ["int", "bool", "double", "TimestampTz"])

    def get_ptype_without_pointers(self):
        if self.is_interoperable():
            return self.ptype.replace(" *'", "'").replace("**", "*")
        else:
            return self.ptype

    def __str__(self) -> str:
        return f"{self.name=}, {self.converted_name=}, {self.ctype=}, {self.ptype=}, {self.cp_conversion=}"


class ReturnType:
    def __init__(self, ctype: str, ptype: str, conversion: str | None) -> None:
        super().__init__()
        self.ctype = ctype
        self.return_type = ptype
        self.conversion = conversion


# List of functions defined in functions.py that shouldn't be exported

hidden_functions = [
    "_check_error",
]

# List of MEOS functions that should not be defined in functions.py
skipped_functions = [
    "py_error_handler",
    "meos_initialize_timezone",
    "meos_initialize_error_handler",
    "meos_finalize_timezone",
]

function_notes = {}

function_modifiers = {
    "meos_initialize": meos_initialize_modifier,
    "meos_finalize": remove_error_check_modifier,
    "cstring_to_text": cstring_to_text_modifier,
    "text_to_cstring": text_to_cstring_modifier,
    "temporal_as_wkb": as_wkb_modifier,
    "set_as_wkb": as_wkb_modifier,
    "span_as_wkb": as_wkb_modifier,
    "spanset_as_wkb": as_wkb_modifier,
    "tbox_as_wkb": as_wkb_modifier,
    "stbox_as_wkb": as_wkb_modifier,
    "mi_span_span": mi_span_span_modifier,
}

# Function-parameter facts the codegen needs sit in the IDL itself, under
# each function's ``shape`` key (populated from MEOS-API's meta/meos-meta.json
# at IDL-generation time).  The catalog has three flavours we consume:
#
#   shape.outputArrays  -> (function, param) is an extra Python return.  The
#                          5 trailing _value_at_timestamptz functions stay
#                          local because their ergonomic (out-param becomes
#                          the primary return when the bool succeeds) is
#                          PyMEOS-CFFI-specific.
#   shape.nullable      -> (function, param) accepts None.
#   shape.namedOutputs  -> (function, param) is an out-param without the
#                          canonical result/value name.
#
# The hardcoded sets below were emptied by 2026-05-14 once
# meta/meos-meta.json carried every entry; result_parameters is kept because
# the override is PyMEOS-CFFI-specific.

result_parameters = {
    ("tbool_value_at_timestamptz", "value"),
    ("ttext_value_at_timestamptz", "value"),
    ("tint_value_at_timestamptz", "value"),
    ("tfloat_value_at_timestamptz", "value"),
    ("tgeo_value_at_timestamptz", "value"),
}

# Populated from IDL shape entries at parse time; see ``_load_shape_pairs``.
output_parameters: set[tuple[str, str]] = set()
nullable_parameters: set[tuple[str, str]] = set()


def _load_shape_pairs(idl: dict) -> None:
    """Populate output_parameters / nullable_parameters from IDL shape data."""
    for entry in idl["functions"]:
        sh = entry.get("shape", {})
        name = entry["name"]
        # arrayReturn.lengthFrom={"kind":"param","name":...} marks the named
        # parameter as an output count when MEOS writes it through a pointer.  It
        # applies to both plain ``T *foo(..., int *count)`` returns and to the
        # split-family which additionally lists outputArrays parallel to the
        # primary return.  A count taken by value is the length of an input array
        # the return matches, as in ``stboxarr_round(boxarr, count, maxdd)``.
        length = sh.get("arrayReturn", {}).get("lengthFrom")
        ctypes = {p["name"]: p["cType"] for p in entry["params"]}
        if length and length.get("kind") == "param" and ctypes.get(length["name"], "").rstrip().endswith("*"):
            output_parameters.add((name, length["name"]))
        for oa in sh.get("outputArrays", []):
            output_parameters.add((name, oa["param"]))
        # outParams lists every parameter the function writes through for its
        # caller (an output geometry array, an output box, a value_n result).
        for param in sh.get("outParams", []):
            output_parameters.add((name, param))
        for nm in sh.get("nullable", []):
            nullable_parameters.add((name, nm))


# Checks if parameter in function is nullable
def is_nullable_parameter(function: str, parameter: str) -> bool:
    return (function, parameter) in nullable_parameters


# Checks if parameter in function is actually a result parameter
def is_result_parameter(function: str, parameter: Parameter) -> bool:
    if parameter.name == "result":
        return True
    return (function, parameter.name) in result_parameters


# Checks if parameter in function is actually an output parameter
def is_output_parameter(function: str, parameter: Parameter) -> bool:
    if parameter.name.endswith("_out"):
        return True
    # ``int *count`` is the canonical trailing-output pattern that returns
    # an array's length; auto-detect it on name + raw ctype.
    if parameter.name == "count" and parameter.ctype == "int *":
        return True
    return (function, parameter.name) in output_parameters


def check_modifiers(functions: list[str]) -> None:
    for func in function_modifiers:
        if func not in functions:
            print(f"Modifier defined for non-existent function {func}")
    for func, param in result_parameters:
        if func not in functions:
            print(f"Result parameter defined for non-existent function {func} ({param})")
    for func, param in output_parameters:
        if func not in functions:
            print(f"Output parameter defined for non-existent function {func} ({param})")
    for func, param in nullable_parameters:
        if func not in functions:
            print(f"Nullable Parameter defined for non-existent function {func} ({param})")


def build_pymeos_functions(idl_path="builder/meos-idl.json", header_path="builder/meos.h"):
    with open(idl_path) as f:
        idl = json.load(f)
    _load_shape_pairs(idl)
    struct_names = {s["name"] for s in idl["structs"]}

    file_path = os.path.dirname(__file__)
    template_path = os.path.join(file_path, "templates/functions.py")
    init_template_path = os.path.join(file_path, "templates/init.py")
    with open(template_path) as f, open(init_template_path) as i:
        base = f.read()
        init_text = i.read()

    functions_path = os.path.join(file_path, "../pymeos_cffi/functions.py")
    init_path = os.path.join(file_path, "../pymeos_cffi/__init__.py")

    declared = cdef_functions(header_path)
    with open(functions_path, "w+") as file:
        file.write(base)
        for entry in idl["functions"]:
            function = entry["name"]
            if function not in declared or function in skipped_functions:
                continue
            return_type = get_return_type(entry["returnType"]["c"])
            params = get_params(function, entry["params"])
            if entry["api"] == "public":
                apply_input_arrays(params, entry.get("shape", {}).get("inputArrays", []), struct_names)
            function_string = build_function_string(function, return_type, params)
            file.write(function_string)
            file.write("\n\n\n")

    functions = []
    with open(functions_path) as funcs:
        content = funcs.read()
        matches = list(re.finditer(r"def (\w+)\(", content))
        function_text = ""
        for fn in matches:
            function_name = fn.group(1)
            if function_name in hidden_functions:
                continue
            function_text += f"    '{function_name}',\n"
            functions.append(function_name)
    init_text = init_text.replace("    FUNCTIONS_REPLACE,", function_text)
    with open(init_path, "w+") as init:
        init.write(init_text)

    format_generated([functions_path, init_path])
    check_modifiers(functions)


def format_generated(paths: list[str]) -> None:
    """Format the generated surface with ruff, the formatter the lint workflow checks, so
    a regeneration -- by hand, by tools/refresh.conf or by the scheduled refresh -- is
    ruff-clean as written: the generated signatures run past the line length until ruff
    folds them. Runs the tool as #get_defined_functions of build_header.py runs nm, a
    failure raising, since an unformatted surface fails the lint workflow."""
    ruff = shutil.which("ruff")
    command = [ruff] if ruff else [sys.executable, "-m", "ruff"]
    subprocess.check_call(command + ["format", "--quiet", *paths])


def apply_input_arrays(params: list[Parameter], input_arrays: list[dict], struct_names: set[str]) -> None:
    """Turn each array the catalog's ``shape.inputArrays`` names into one Python list.

    MEOS takes an array as a pointer plus the parameter its ``lengthFrom`` names; Python
    takes the list, whose length is the count. Arrays sharing one count are read in
    parallel, so each must be as long as the first of them, as the array readers of
    MEOS.NET's tools/objectgen.py state. An array of ``uint8_t`` is ``bytes``. Each
    element converts as #get_param_conversion converts a scalar argument of its type,
    a pointer element is cast to it, and a struct element is the struct itself, as
    PyMEOS passes ``span._inner[0]``. CFFI builds the C array from the list for the call, of
    the element type the cdef declares. Only a public function's arrays are lists: an
    internal one such as ``tsequence_make_free`` frees the array it is given, which
    must then be MEOS's own and not one CFFI builds for the call."""
    by_name = {p.name: p for p in params}
    first_of_count: dict[str, str] = {}
    for array in input_arrays:
        param = by_name.get(array["param"])
        length = by_name.get(array["lengthFrom"]["name"])
        if param is None or length is None:
            continue
        name = param.name
        element = array["element"]["c"]
        nullable = param.ptype.endswith("| None")
        first = first_of_count.setdefault(length.name, name)

        if element == "uint8_t":
            ptype = "bytes"
            value = f"_ffi.new('uint8_t []', {name})"
        else:
            conversion = conversion_map.get(element)
            if element.endswith("*") and (conversion is None or conversion.p_to_c is None):
                item_type = f"Annotated[_ffi.CData, '{element}']"
                item = f"_ffi.cast('{element}', x)"
            elif element in struct_names:
                item_type = f"Annotated[_ffi.CData, '{element}']"
                item = None
            elif conversion is not None:
                item_type = conversion.p_type
                item = conversion.p_to_c("x") if conversion.p_to_c else None
            else:
                item_type = f"Annotated[int, '{element}']"
                item = None
            ptype = f"list[{item_type}]"
            value = f"[{item} for x in {name}]" if item else name

        checks = []
        if name != first:
            guard = f"{name} is not None and " if nullable else ""
            checks.append(
                f"if {guard}len({name}) != len({first}):\n"
                f"        raise ValueError('{name} and {first} must have the same length')"
            )
        if nullable:
            ptype += " | None"
            value += f" if {name} is not None else _ffi.NULL"
        param.ptype = ptype
        param.converted_name = f"{name}_converted"
        param.cp_conversion = "\n    ".join([*checks, f"{name}_converted = {value}"])

        length.derived = True
        length.converted_name = f"len({first})"
        length.cp_conversion = None


def get_params(function: str, params: list[dict]) -> list[Parameter]:
    return [p for p in (get_param(function, entry) for entry in params) if p is not None]


# Creates a Parameter object from a meos-idl.json parameter entry
def get_param(function: str, entry: dict) -> Parameter | None:
    param_name = entry["name"]
    param_type = entry["cType"]

    # Check if the parameter name is a reserved word and change it if necessary
    reserved_words = {"str": "string", "is": "iset", "from": "from_"}
    if param_name in reserved_words:
        param_name = reserved_words[param_name]

    # Return None to remove the parameter if it's void
    if param_name == "void":
        return None

    # Get the type conversion
    conversion = get_param_conversion(param_type)

    # Check if parameter is nullable
    nullable = is_nullable_parameter(function, param_name)

    # If no conversion is needed from Python to C, use the parameter name also as converted name
    if conversion.p_to_c is None:
        # If nullable, add null check
        if nullable:
            return Parameter(
                param_name,
                f"{param_name}_converted",
                param_type,
                f"{conversion.p_type} | None",
                f"{param_name}_converted = {param_name} if {param_name} is not None else _ffi.NULL",
            )
        return Parameter(param_name, param_name, param_type, conversion.p_type, None)

    # If a conversion is needed, create a new name and add the conversion
    if nullable:
        return Parameter(
            param_name,
            f"{param_name}_converted",
            param_type,
            f"{conversion.p_type} | None",
            f"{param_name}_converted = {conversion.p_to_c(param_name)} if {param_name} is not None else _ffi.NULL",
        )
    return Parameter(
        param_name,
        f"{param_name}_converted",
        param_type,
        conversion.p_type,
        f"{param_name}_converted = {conversion.p_to_c(param_name)}",
    )


# Returns a conversion for a type
def get_param_conversion(param_type: str) -> Conversion:
    # Check if the type is known
    if param_type in conversion_map:
        return conversion_map[param_type]
    # Otherwise, create a new conversion

    # If it's a double pointer, cast as an array
    if param_type.endswith("**"):
        return Conversion(
            param_type,
            f"Annotated[list, '{param_type}']",
            lambda name: f"[_ffi.cast('{param_type[:-1]}', x) for x in {name}]",
            lambda name: name,
        )

    # Otherwise, cast normally
    else:
        return Conversion(
            param_type,
            f"Annotated[_ffi.CData, '{param_type}']",
            lambda name: f"_ffi.cast('{param_type}', {name})",
            lambda name: name,
        )


# Creates a ReturnType object from the function return type
def get_return_type(inner_return_type) -> ReturnType:
    # Check if a conversion is known
    if inner_return_type in conversion_map:
        conversion = conversion_map[inner_return_type]
        return ReturnType(
            conversion.c_type,
            conversion.p_type,
            conversion.c_to_p("result") if conversion.c_to_p else None,
        )
    # Otherwise, don't transform anything
    return ReturnType(inner_return_type, "_ffi.CData", None)


def build_function_string(function_name: str, return_type: ReturnType, parameters: list[Parameter]) -> str:
    # Check if there is a result param, i.e., output parameters that are the actual
    # product of the function, instead of whatever the function returns (typically
    # void or bool/int indicating the success or failure of the function)
    result_param = None
    if len(parameters) > 1 and is_result_parameter(function_name, parameters[-1]):
        # Remove it from the list of parameters
        result_param = parameters.pop(-1)

    # Check if there are output parameters. Unlike result parameters, these are just
    # normal parameters that provide extra information or actual results that are meant
    # to go along with whatever the function returns
    out_params = []
    if len(parameters) > 1:
        out_params = [p for p in parameters if is_output_parameter(function_name, p)]

    # Create wrapper function parameter list
    params = ", ".join(f"{p.name}: {p.ptype}" for p in parameters if p not in out_params and not p.derived)

    # Create necessary conversions for the parameters
    param_conversions = "\n    ".join(
        p.cp_conversion for p in parameters if p.cp_conversion is not None and p not in out_params
    )

    # Create CFFI function parameter list
    inner_params = ", ".join(pc.name if pc in out_params else pc.converted_name for pc in parameters)

    # Add result conversion if necessary
    result_manipulation = None
    if return_type.conversion is not None:
        result_manipulation = f"    result = {return_type.conversion}\n"

    # Initialize the function return type to the python type unless it needs no
    # conversion (where the C type gives extra information while being interoperable),
    # or the function is void
    function_return_type = f"Annotated[{return_type.return_type}, '{return_type.ctype}']"
    # function_return_type = (
    #     return_type.return_type
    #     if return_type.conversion is not None or return_type.return_type == "None"
    #     else f"'{return_type.ctype}'"
    # )
    # If there is a result param
    if result_param is not None:
        # Create the CFFI object to hold it
        param_conversions += f"\n    out_result = _ffi.new('{result_param.ctype}')"
        # Add it to the CFFI call param list
        inner_params += ", out_result"

        # If result is interoperable, remove pointer, otherwise, keep pointer
        returning_object = "out_result"
        if result_param.is_interoperable():
            returning_object += "[0]"

        # If original C function returned bool, use it to return it when result is True,
        # or return None otherwise.
        if return_type.return_type == "bool":
            boll_guard = (
                "    if result:\n"
                f"        return {returning_object} if {returning_object} != "
                "_ffi.NULL else None\n"
                "    return None"
            )
            result_manipulation = (result_manipulation or "") + boll_guard
        # Otherwise, just return it normally
        else:
            result_manipulation = (
                result_manipulation or ""
            ) + f"    return {returning_object} if {returning_object}!= _ffi.NULL else None\n"
        # Set the return type as the Python type, removing the pointer modifier if
        # necessary
        function_return_type = result_param.get_ptype_without_pointers()
    # Otherwise, return the result normally (if needed)
    elif return_type.return_type != "None":
        result_manipulation = (result_manipulation or "") + "    return result if result != _ffi.NULL else None"

    # For each output param, create the CFFI object to hold it
    for out_param in out_params:
        param_conversions += f"\n    {out_param.name} = _ffi.new('{out_param.ctype}')"
    out_types = [p.get_ptype_without_pointers() for p in out_params]
    out_values = [f"{p.name}[0]" for p in out_params]

    if out_params and result_manipulation is None:
        # A void function answers only through its output params, so they alone
        # are returned
        function_return_type = out_types[0] if len(out_types) == 1 else f"tuple[{', '.join(out_types)}]"
        result_manipulation = "    return " + ", ".join(out_values)
    elif out_params:
        # Otherwise they go along with the result, removing the pointer modifier
        # from their types if necessary
        function_return_type = f"tuple[{', '.join([function_return_type] + out_types)}]"
        result_manipulation += "".join(f", {value}" for value in out_values)

    # Add padding to param conversions
    if len(param_conversions) > 0:
        param_conversions = f"    {param_conversions}\n"

    # Add TO DO note if the function is listed in the function_notes dictionary
    note = ""
    if function_name in function_notes:
        note = f"#TODO {function_notes[function_name]}\n"

    # Create common part of function string (note, name, parameters, return type and
    # parameter conversions).
    base = f"{note}def {function_name}({params}) -> {function_return_type}:\n{param_conversions}"
    # Most codegen paths don't need the C-level return value: void returns
    # discard it outright, and result_param wrappers route the value back
    # through out_result with the only consumer being the bool-guard.  Drop
    # the assignment in those cases so ruff does not flag ``result`` as
    # unused.
    keep_result_assign = return_type.return_type != "None" and (
        result_param is None or return_type.return_type == "bool"
    )
    if keep_result_assign:
        function_string = f"{base}    result = _lib.{function_name}({inner_params})"
    else:
        function_string = f"{base}    _lib.{function_name}({inner_params})"

    # Add error handling
    function_string += "\n    _check_error()"

    # Add whatever manipulation the result needs (maybe empty)
    if result_manipulation is not None:
        function_string += f"\n{result_manipulation}"

    # Check if there is function modifiers to modify specific elements of the function
    if function_name in function_modifiers:
        function_string = function_modifiers[function_name](function_string)

    return function_string


if __name__ == "__main__":
    build_pymeos_functions(*sys.argv[1:])
