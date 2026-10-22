def meos_initialize_modifier(_: str) -> str:
    return """def meos_initialize(tz_str: str | None) -> None:
    if "PROJ_DATA" not in os.environ and "PROJ_LIB" not in os.environ:
        proj_dir = os.path.join(os.path.dirname(__file__), "proj_data")
        if os.path.exists(proj_dir):
            # Assume we are in a wheel and the PROJ data is in the package
            os.environ["PROJ_DATA"] = proj_dir
            os.environ["PROJ_LIB"] = proj_dir

    _lib.meos_initialize()

    # Check if local spatial ref system csv exists (meaning wheel installation). If it does, use it.
    wheel_path = os.path.join(
        os.path.dirname(__file__), "meos_data", "spatial_ref_sys.csv"
    )
    if os.path.exists(wheel_path):
        _lib.meos_set_spatial_ref_sys_csv(wheel_path.encode("utf-8"))

    # Timezone is already initialized by meos_initialize, so we only need to set it if tz_str is provided
    if tz_str is not None:
        _lib.meos_initialize_timezone(tz_str.encode('utf-8'))
    _lib.meos_initialize_error_handler(_lib.py_error_handler)"""


def remove_error_check_modifier(function: str) -> str:
    return function.replace("    _check_error()\n", "")


def cstring_to_text_modifier(_: str) -> str:
    return """def cstring_to_text(cstring: str) -> 'text *':
    cstring_converted = cstring.encode('utf-8')
    result = _lib.cstring_to_text(cstring_converted)
    return result"""


def text_to_cstring_modifier(_: str) -> str:
    return """def text_to_cstring(textptr: 'text *') -> str:
    result = _lib.text_to_cstring(textptr)
    result = _ffi.string(result).decode('utf-8')
    return result"""


def as_wkb_modifier(function: str) -> str:
    return function.replace("-> \"Tuple['uint8_t *', 'size_t *']\":", "-> bytes:").replace(
        "return result if result != _ffi.NULL else None, size_out[0]",
        "result_converted = bytes(result[i] for i in range(size_out[0])) if result != _ffi.NULL else None\n"
        "    return result_converted",
    )


def mi_span_span_modifier(function: str) -> str:
    return (
        function.replace(
            '-> Annotated[_ffi.CData, "Span *"]',
            '-> tuple[Annotated[_ffi.CData, "Span *"], int]',
        )
        .replace("_lib.mi_span_span(", "result = _lib.mi_span_span(")
        .replace("return out_result", "return out_result, result")
    )
