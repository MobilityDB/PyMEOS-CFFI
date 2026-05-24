import json
import os.path
import sys

from build_pymeos_functions_modifiers import *
from objects import Conversion, conversion_map

# Headers PyMEOS-CFFI wraps, in the same iteration order as
# builder/build_header.py concatenates them into builder/meos.h.  Iteration
# order is preserved so the generated functions.py groups symbols by their
# defining header.
IDL_HEADER_ORDER = [
    "meos.h",
    "meos_catalog.h",
    "meos_geo.h",
    "meos_internal.h",
    "meos_internal_geo.h",
    "meos_npoint.h",
    "meos_cbuffer.h",
    "meos_pose.h",
    "meos_rgeo.h",
]

# Types declared in MEOS headers but not exposed through the CFFI cdef.
# Mirrors builder/build_header.py's ``undefined_types`` list: functions whose
# signatures reference these are skipped at codegen time.
IDL_OPAQUE_TYPES = ("json_object",)


def _references_opaque(entry: dict) -> bool:
    if any(t in entry["returnType"]["c"] for t in IDL_OPAQUE_TYPES):
        return True
    return any(any(t in p["cType"] for t in IDL_OPAQUE_TYPES) for p in entry["params"])


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
    "cstring2text": cstring2text_modifier,
    "text2cstring": text2cstring_modifier,
    "spanset_make": spanset_make_modifier,
    "temporal_from_wkb": from_wkb_modifier("temporal_from_wkb", "Temporal"),
    "set_from_wkb": from_wkb_modifier("set_from_wkb", "Set"),
    "span_from_wkb": from_wkb_modifier("span_from_wkb", "Span"),
    "spanset_from_wkb": from_wkb_modifier("spanset_from_wkb", "SpanSet"),
    "tbox_from_wkb": from_wkb_modifier("tbox_from_wkb", "TBOX"),
    "stbox_from_wkb": from_wkb_modifier("stbox_from_wkb", "STBOX"),
    "temporal_as_wkb": as_wkb_modifier,
    "set_as_wkb": as_wkb_modifier,
    "span_as_wkb": as_wkb_modifier,
    "spanset_as_wkb": as_wkb_modifier,
    "tbox_as_wkb": as_wkb_modifier,
    "stbox_as_wkb": as_wkb_modifier,
    "tstzset_make": tstzset_make_modifier,
    "dateset_make": array_parameter_modifier("values", "count"),
    "intset_make": array_parameter_modifier("values", "count"),
    "bigintset_make": array_parameter_modifier("values", "count"),
    "floatset_make": array_parameter_modifier("values", "count"),
    "textset_make": textset_make_modifier,
    "geoset_make": array_length_remover_modifier("values", "count"),
    "tsequenceset_make_gaps": array_length_remover_modifier("instants", "count"),
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
        # parameter as an output count.  It applies to both plain
        # ``T *foo(..., int *count)`` returns and to the split-family which
        # additionally lists outputArrays parallel to the primary return.
        length = sh.get("arrayReturn", {}).get("lengthFrom")
        if length and length.get("kind") == "param":
            output_parameters.add((name, length["name"]))
        for oa in sh.get("outputArrays", []):
            output_parameters.add((name, oa["param"]))
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


def build_pymeos_functions(idl_path="builder/meos-idl.json"):
    with open(idl_path) as f:
        idl = json.load(f)
    _load_shape_pairs(idl)

    file_path = os.path.dirname(__file__)
    template_path = os.path.join(file_path, "templates/functions.py")
    init_template_path = os.path.join(file_path, "templates/init.py")
    with open(template_path) as f, open(init_template_path) as i:
        base = f.read()
        init_text = i.read()

    functions_path = os.path.join(file_path, "../pymeos_cffi/functions.py")
    init_path = os.path.join(file_path, "../pymeos_cffi/__init__.py")

    entries_by_file = {h: [] for h in IDL_HEADER_ORDER}
    for entry in idl["functions"]:
        if entry["file"] in entries_by_file:
            entries_by_file[entry["file"]].append(entry)

    with open(functions_path, "w+") as file:
        file.write(base)
        for header in IDL_HEADER_ORDER:
            for entry in entries_by_file[header]:
                function = entry["name"]
                if function in skipped_functions:
                    continue
                if _references_opaque(entry):
                    continue
                return_type = get_return_type(entry["returnType"]["c"])
                params = get_params(function, entry["params"])
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

    check_modifiers(functions)


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
    params = ", ".join(f"{p.name}: {p.ptype}" for p in parameters if p not in out_params)

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

    # For each output param
    for out_param in out_params:
        # Create the CFFI object to hold it
        param_conversions += f"\n    {out_param.name} = _ffi.new('{out_param.ctype}')"
        # Add its type to the return type of the function, removing the pointer modifier
        # if necessary
        function_return_type += ", " + out_param.get_ptype_without_pointers()
        # Add it to the return statement
        result_manipulation += f", {out_param.name}[0]"

    # If there are output params, wrap the function return type in a tuple
    if len(out_params) > 0:
        function_return_type = f"tuple[{function_return_type}]"

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
