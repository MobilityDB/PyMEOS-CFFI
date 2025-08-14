import logging
import os
from datetime import date, datetime, timedelta
from typing import Annotated, Any

import _meos_cffi
import shapely.geometry as spg
from cffi import cdata
from dateutil.parser import parse
from shapely import get_srid, set_srid, wkt
from shapely.geometry.base import BaseGeometry

from .enums import InterpolationType
from .errors import report_meos_exception

_ffi = _meos_cffi.ffi
_lib = _meos_cffi.lib

_error: int | None = None
_error_level: int | None = None
_error_message: str | None = None

logger = logging.getLogger("pymeos_cffi")


def _check_error() -> None:
    global _error, _error_level, _error_message
    if _error is not None:
        error = _error
        error_level = _error_level
        error_message = _error_message
        _error = None
        _error_level = None
        _error_message = None
        report_meos_exception(error_level, error, error_message)


@_ffi.def_extern()
def py_error_handler(error_level, error_code, error_msg):
    global _error, _error_level, _error_message
    _error = error_code
    _error_level = error_level
    _error_message = _ffi.string(error_msg).decode("utf-8")
    logger.debug(f"ERROR Handler called: Level: {_error} | Code: {_error_level} | Message: {_error_message}")


def create_pointer(object: "Any", type: str) -> Annotated[cdata, "Any *"]:
    return _ffi.new(f"{type} *", object)


def get_address(value: "Any") -> Annotated[cdata, "Any *"]:
    return _ffi.addressof(value)


def datetime_to_timestamptz(dt: datetime) -> Annotated[int, "TimestampTz"]:
    return _lib.pg_timestamptz_in(dt.strftime("%Y-%m-%d %H:%M:%S%z").encode("utf-8"), -1)


def timestamptz_to_datetime(ts: Annotated[int, "TimestampTz"]) -> datetime:
    return parse(pg_timestamptz_out(ts))


def date_to_date_adt(dt: date) -> Annotated[int, "DateADT"]:
    return _lib.pg_date_in(dt.strftime("%Y-%m-%d").encode("utf-8"))


def date_adt_to_date(ts: Annotated[int, "DateADT"]) -> date:
    return parse(pg_date_out(ts)).date()


def timedelta_to_interval(td: timedelta) -> Any:
    return _ffi.new(
        "Interval *",
        {"time": td.microseconds + td.seconds * 1000000, "day": td.days, "month": 0},
    )


def interval_to_timedelta(interval: Any) -> timedelta:
    # TODO fix for months/years
    return timedelta(days=interval.day, microseconds=interval.time)


def geo_to_gserialized(geom: BaseGeometry, geodetic: bool) -> Annotated[cdata, "GSERIALIZED *"]:
    if geodetic:
        return geography_to_gserialized(geom)
    else:
        return geometry_to_gserialized(geom)


def geometry_to_gserialized(geom: BaseGeometry) -> Annotated[cdata, "GSERIALIZED *"]:
    text = wkt.dumps(geom)
    if get_srid(geom) > 0:
        text = f"SRID={get_srid(geom)};{text}"
    gs = geom_in(text, -1)
    return gs


def geography_to_gserialized(geom: BaseGeometry) -> Annotated[cdata, "GSERIALIZED *"]:
    text = wkt.dumps(geom)
    if get_srid(geom) > 0:
        text = f"SRID={get_srid(geom)};{text}"
    gs = geog_in(text, -1)
    return gs


def gserialized_to_shapely_point(geom: "const GSERIALIZED *", precision: int = 15) -> spg.Point:
    text = geo_as_text(geom, precision)
    geometry = wkt.loads(text)
    srid = geo_srid(geom)
    if srid > 0:
        geometry = set_srid(geometry, srid)
    return geometry


def gserialized_to_shapely_geometry(geom: "const GSERIALIZED *", precision: int = 15) -> BaseGeometry:
    text = geo_as_text(geom, precision)
    geometry = wkt.loads(text)
    srid = geo_srid(geom)
    if srid > 0:
        geometry = set_srid(geometry, srid)
    return geometry


def as_tinstant(temporal: Annotated[cdata, "Temporal *"]) -> Annotated[cdata, "TInstant *"]:
    return _ffi.cast("TInstant *", temporal)


def as_tsequence(temporal: Annotated[cdata, "Temporal *"]) -> Annotated[cdata, "TSequence *"]:
    return _ffi.cast("TSequence *", temporal)


def as_tsequenceset(temporal: Annotated[cdata, "Temporal *"]) -> Annotated[cdata, "TSequenceSet *"]:
    return _ffi.cast("TSequenceSet *", temporal)


# -----------------------------------------------------------------------------
# ----------------------End of manually-defined functions----------------------
# -----------------------------------------------------------------------------
def date_in(string: str) -> Annotated[int, "DateADT"]:
    string_converted = string.encode("utf-8")
    result = _lib.date_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def date_out(d: int) -> Annotated[str, "char *"]:
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.date_out(d_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def interval_cmp(
    interv1: Annotated[cdata, "const Interval *"], interv2: Annotated[cdata, "const Interval *"]
) -> Annotated[int, "int"]:
    interv1_converted = _ffi.cast("const Interval *", interv1)
    interv2_converted = _ffi.cast("const Interval *", interv2)
    result = _lib.interval_cmp(interv1_converted, interv2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def interval_in(string: str, typmod: int) -> Annotated[cdata, "Interval *"]:
    string_converted = string.encode("utf-8")
    typmod_converted = _ffi.cast("int32", typmod)
    result = _lib.interval_in(string_converted, typmod_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def interval_out(interv: Annotated[cdata, "const Interval *"]) -> Annotated[str, "char *"]:
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.interval_out(interv_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def time_in(string: str, typmod: int) -> Annotated[cdata, "TimeADT"]:
    string_converted = string.encode("utf-8")
    typmod_converted = _ffi.cast("int32", typmod)
    result = _lib.time_in(string_converted, typmod_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def time_out(t: Annotated[cdata, "TimeADT"]) -> Annotated[str, "char *"]:
    t_converted = _ffi.cast("TimeADT", t)
    result = _lib.time_out(t_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def timestamp_in(string: str, typmod: int) -> Annotated[int, "Timestamp"]:
    string_converted = string.encode("utf-8")
    typmod_converted = _ffi.cast("int32", typmod)
    result = _lib.timestamp_in(string_converted, typmod_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timestamp_out(t: int) -> Annotated[str, "char *"]:
    t_converted = _ffi.cast("Timestamp", t)
    result = _lib.timestamp_out(t_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def timestamptz_in(string: str, typmod: int) -> Annotated[int, "TimestampTz"]:
    string_converted = string.encode("utf-8")
    typmod_converted = _ffi.cast("int32", typmod)
    result = _lib.timestamptz_in(string_converted, typmod_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timestamptz_out(t: int) -> Annotated[str, "char *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.timestamptz_out(t_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def meos_errno() -> Annotated[int, "int"]:
    result = _lib.meos_errno()
    _check_error()
    return result if result != _ffi.NULL else None


def meos_errno_set(err: int) -> Annotated[int, "int"]:
    result = _lib.meos_errno_set(err)
    _check_error()
    return result if result != _ffi.NULL else None


def meos_errno_restore(err: int) -> Annotated[int, "int"]:
    result = _lib.meos_errno_restore(err)
    _check_error()
    return result if result != _ffi.NULL else None


def meos_errno_reset() -> Annotated[int, "int"]:
    result = _lib.meos_errno_reset()
    _check_error()
    return result if result != _ffi.NULL else None


def meos_finalize_projsrs() -> Annotated[None, "void"]:
    _lib.meos_finalize_projsrs()
    _check_error()


def meos_finalize_ways() -> Annotated[None, "void"]:
    _lib.meos_finalize_ways()
    _check_error()


def meos_set_datestyle(newval: str, extra: Annotated[cdata, "void *"]) -> Annotated[bool, "bool"]:
    newval_converted = newval.encode("utf-8")
    extra_converted = _ffi.cast("void *", extra)
    result = _lib.meos_set_datestyle(newval_converted, extra_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def meos_set_intervalstyle(newval: str, extra: int | None) -> Annotated[bool, "bool"]:
    newval_converted = newval.encode("utf-8")
    extra_converted = extra if extra is not None else _ffi.NULL
    result = _lib.meos_set_intervalstyle(newval_converted, extra_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def meos_get_datestyle() -> Annotated[str, "char *"]:
    result = _lib.meos_get_datestyle()
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def meos_get_intervalstyle() -> Annotated[str, "char *"]:
    result = _lib.meos_get_intervalstyle()
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def meos_set_spatial_ref_sys_csv(path: Annotated[cdata, "const char*"]) -> Annotated[None, "void"]:
    path_converted = _ffi.cast("const char*", path)
    _lib.meos_set_spatial_ref_sys_csv(path_converted)
    _check_error()


def meos_initialize(tz_str: str | None) -> None:
    if "PROJ_DATA" not in os.environ and "PROJ_LIB" not in os.environ:
        proj_dir = os.path.join(os.path.dirname(__file__), "proj_data")
        if os.path.exists(proj_dir):
            # Assume we are in a wheel and the PROJ data is in the package
            os.environ["PROJ_DATA"] = proj_dir
            os.environ["PROJ_LIB"] = proj_dir

    _lib.meos_initialize()

    # Check if local spatial ref system csv exists (meaning wheel installation). If it does, use it.
    wheel_path = os.path.join(os.path.dirname(__file__), "meos_data", "spatial_ref_sys.csv")
    if os.path.exists(wheel_path):
        _lib.meos_set_spatial_ref_sys_csv(wheel_path.encode("utf-8"))

    # Timezone is already initialized by meos_initialize, so we only need to set it if tz_str is provided
    if tz_str is not None:
        _lib.meos_initialize_timezone(tz_str.encode("utf-8"))
    _lib.meos_initialize_error_handler(_lib.py_error_handler)


def meos_finalize() -> Annotated[None, "void"]:
    _lib.meos_finalize()
    _check_error()


def add_date_int(d: int, days: int) -> Annotated[int, "DateADT"]:
    d_converted = _ffi.cast("DateADT", d)
    days_converted = _ffi.cast("int32", days)
    result = _lib.add_date_int(d_converted, days_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def add_interval_interval(
    interv1: Annotated[cdata, "const Interval *"], interv2: Annotated[cdata, "const Interval *"]
) -> Annotated[cdata, "Interval *"]:
    interv1_converted = _ffi.cast("const Interval *", interv1)
    interv2_converted = _ffi.cast("const Interval *", interv2)
    result = _lib.add_interval_interval(interv1_converted, interv2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def add_timestamptz_interval(t: int, interv: Annotated[cdata, "const Interval *"]) -> Annotated[int, "TimestampTz"]:
    t_converted = _ffi.cast("TimestampTz", t)
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.add_timestamptz_interval(t_converted, interv_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bool_in(string: str) -> Annotated[bool, "bool"]:
    string_converted = string.encode("utf-8")
    result = _lib.bool_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bool_out(b: bool) -> Annotated[str, "char *"]:
    result = _lib.bool_out(b)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def cstring2text(cstring: str) -> "text *":
    cstring_converted = cstring.encode("utf-8")
    result = _lib.cstring2text(cstring_converted)
    return result


def date_to_timestamp(dateVal: int) -> Annotated[int, "Timestamp"]:
    dateVal_converted = _ffi.cast("DateADT", dateVal)
    result = _lib.date_to_timestamp(dateVal_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def date_to_timestamptz(d: int) -> Annotated[int, "TimestampTz"]:
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.date_to_timestamptz(d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def float_exp(d: float) -> Annotated[float, "double"]:
    result = _lib.float_exp(d)
    _check_error()
    return result if result != _ffi.NULL else None


def float_ln(d: float) -> Annotated[float, "double"]:
    result = _lib.float_ln(d)
    _check_error()
    return result if result != _ffi.NULL else None


def float_log10(d: float) -> Annotated[float, "double"]:
    result = _lib.float_log10(d)
    _check_error()
    return result if result != _ffi.NULL else None


def float_round(d: float, maxdd: int) -> Annotated[float, "double"]:
    result = _lib.float_round(d, maxdd)
    _check_error()
    return result if result != _ffi.NULL else None


def interval_make(
    years: int, months: int, weeks: int, days: int, hours: int, mins: int, secs: float
) -> Annotated[cdata, "Interval *"]:
    years_converted = _ffi.cast("int32", years)
    months_converted = _ffi.cast("int32", months)
    weeks_converted = _ffi.cast("int32", weeks)
    days_converted = _ffi.cast("int32", days)
    hours_converted = _ffi.cast("int32", hours)
    mins_converted = _ffi.cast("int32", mins)
    result = _lib.interval_make(
        years_converted, months_converted, weeks_converted, days_converted, hours_converted, mins_converted, secs
    )
    _check_error()
    return result if result != _ffi.NULL else None


def minus_date_date(d1: int, d2: int) -> Annotated[cdata, "Interval *"]:
    d1_converted = _ffi.cast("DateADT", d1)
    d2_converted = _ffi.cast("DateADT", d2)
    result = _lib.minus_date_date(d1_converted, d2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_date_int(d: int, days: int) -> Annotated[int, "DateADT"]:
    d_converted = _ffi.cast("DateADT", d)
    days_converted = _ffi.cast("int32", days)
    result = _lib.minus_date_int(d_converted, days_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_timestamptz_interval(t: int, interv: Annotated[cdata, "const Interval *"]) -> Annotated[int, "TimestampTz"]:
    t_converted = _ffi.cast("TimestampTz", t)
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.minus_timestamptz_interval(t_converted, interv_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_timestamptz_timestamptz(t1: int, t2: int) -> Annotated[cdata, "Interval *"]:
    t1_converted = _ffi.cast("TimestampTz", t1)
    t2_converted = _ffi.cast("TimestampTz", t2)
    result = _lib.minus_timestamptz_timestamptz(t1_converted, t2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def mul_interval_double(interv: Annotated[cdata, "const Interval *"], factor: float) -> Annotated[cdata, "Interval *"]:
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.mul_interval_double(interv_converted, factor)
    _check_error()
    return result if result != _ffi.NULL else None


def pg_date_in(string: str) -> Annotated[int, "DateADT"]:
    string_converted = string.encode("utf-8")
    result = _lib.pg_date_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def pg_date_out(d: int) -> Annotated[str, "char *"]:
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.pg_date_out(d_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def pg_interval_cmp(
    interv1: Annotated[cdata, "const Interval *"], interv2: Annotated[cdata, "const Interval *"]
) -> Annotated[int, "int"]:
    interv1_converted = _ffi.cast("const Interval *", interv1)
    interv2_converted = _ffi.cast("const Interval *", interv2)
    result = _lib.pg_interval_cmp(interv1_converted, interv2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def pg_interval_in(string: str, typmod: int) -> Annotated[cdata, "Interval *"]:
    string_converted = string.encode("utf-8")
    typmod_converted = _ffi.cast("int32", typmod)
    result = _lib.pg_interval_in(string_converted, typmod_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def pg_interval_out(interv: Annotated[cdata, "const Interval *"]) -> Annotated[str, "char *"]:
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.pg_interval_out(interv_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def pg_timestamp_in(string: str, typmod: int) -> Annotated[int, "Timestamp"]:
    string_converted = string.encode("utf-8")
    typmod_converted = _ffi.cast("int32", typmod)
    result = _lib.pg_timestamp_in(string_converted, typmod_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def pg_timestamp_out(t: int) -> Annotated[str, "char *"]:
    t_converted = _ffi.cast("Timestamp", t)
    result = _lib.pg_timestamp_out(t_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def pg_timestamptz_in(string: str, typmod: int) -> Annotated[int, "TimestampTz"]:
    string_converted = string.encode("utf-8")
    typmod_converted = _ffi.cast("int32", typmod)
    result = _lib.pg_timestamptz_in(string_converted, typmod_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def pg_timestamptz_out(t: int) -> Annotated[str, "char *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.pg_timestamptz_out(t_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def text2cstring(textptr: "text *") -> str:
    result = _lib.text2cstring(textptr)
    result = _ffi.string(result).decode("utf-8")
    return result


def text_cmp(txt1: str, txt2: str) -> Annotated[int, "int"]:
    txt1_converted = cstring2text(txt1)
    txt2_converted = cstring2text(txt2)
    result = _lib.text_cmp(txt1_converted, txt2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def text_copy(txt: str) -> Annotated[str, "text *"]:
    txt_converted = cstring2text(txt)
    result = _lib.text_copy(txt_converted)
    _check_error()
    result = text2cstring(result)
    return result if result != _ffi.NULL else None


def text_initcap(txt: str) -> Annotated[str, "text *"]:
    txt_converted = cstring2text(txt)
    result = _lib.text_initcap(txt_converted)
    _check_error()
    result = text2cstring(result)
    return result if result != _ffi.NULL else None


def text_lower(txt: str) -> Annotated[str, "text *"]:
    txt_converted = cstring2text(txt)
    result = _lib.text_lower(txt_converted)
    _check_error()
    result = text2cstring(result)
    return result if result != _ffi.NULL else None


def text_out(txt: str) -> Annotated[str, "char *"]:
    txt_converted = cstring2text(txt)
    result = _lib.text_out(txt_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def text_upper(txt: str) -> Annotated[str, "text *"]:
    txt_converted = cstring2text(txt)
    result = _lib.text_upper(txt_converted)
    _check_error()
    result = text2cstring(result)
    return result if result != _ffi.NULL else None


def textcat_text_text(txt1: str, txt2: str) -> Annotated[str, "text *"]:
    txt1_converted = cstring2text(txt1)
    txt2_converted = cstring2text(txt2)
    result = _lib.textcat_text_text(txt1_converted, txt2_converted)
    _check_error()
    result = text2cstring(result)
    return result if result != _ffi.NULL else None


def timestamptz_shift(t: int, interv: Annotated[cdata, "const Interval *"]) -> Annotated[int, "TimestampTz"]:
    t_converted = _ffi.cast("TimestampTz", t)
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.timestamptz_shift(t_converted, interv_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timestamp_to_date(t: int) -> Annotated[int, "DateADT"]:
    t_converted = _ffi.cast("Timestamp", t)
    result = _lib.timestamp_to_date(t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timestamptz_to_date(t: int) -> Annotated[int, "DateADT"]:
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.timestamptz_to_date(t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintset_in(string: str) -> Annotated[cdata, "Set *"]:
    string_converted = string.encode("utf-8")
    result = _lib.bigintset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintset_out(set: Annotated[cdata, "const Set *"]) -> Annotated[str, "char *"]:
    set_converted = _ffi.cast("const Set *", set)
    result = _lib.bigintset_out(set_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def bigintspan_in(string: str) -> Annotated[cdata, "Span *"]:
    string_converted = string.encode("utf-8")
    result = _lib.bigintspan_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintspan_out(s: Annotated[cdata, "const Span *"]) -> Annotated[str, "char *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.bigintspan_out(s_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def bigintspanset_in(string: str) -> Annotated[cdata, "SpanSet *"]:
    string_converted = string.encode("utf-8")
    result = _lib.bigintspanset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintspanset_out(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[str, "char *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.bigintspanset_out(ss_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def dateset_in(string: str) -> Annotated[cdata, "Set *"]:
    string_converted = string.encode("utf-8")
    result = _lib.dateset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def dateset_out(s: Annotated[cdata, "const Set *"]) -> Annotated[str, "char *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.dateset_out(s_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def datespan_in(string: str) -> Annotated[cdata, "Span *"]:
    string_converted = string.encode("utf-8")
    result = _lib.datespan_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datespan_out(s: Annotated[cdata, "const Span *"]) -> Annotated[str, "char *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.datespan_out(s_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def datespanset_in(string: str) -> Annotated[cdata, "SpanSet *"]:
    string_converted = string.encode("utf-8")
    result = _lib.datespanset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datespanset_out(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[str, "char *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.datespanset_out(ss_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def floatset_in(string: str) -> Annotated[cdata, "Set *"]:
    string_converted = string.encode("utf-8")
    result = _lib.floatset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatset_out(set: Annotated[cdata, "const Set *"], maxdd: int) -> Annotated[str, "char *"]:
    set_converted = _ffi.cast("const Set *", set)
    result = _lib.floatset_out(set_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def floatspan_in(string: str) -> Annotated[cdata, "Span *"]:
    string_converted = string.encode("utf-8")
    result = _lib.floatspan_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspan_out(s: Annotated[cdata, "const Span *"], maxdd: int) -> Annotated[str, "char *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.floatspan_out(s_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def floatspanset_in(string: str) -> Annotated[cdata, "SpanSet *"]:
    string_converted = string.encode("utf-8")
    result = _lib.floatspanset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspanset_out(ss: Annotated[cdata, "const SpanSet *"], maxdd: int) -> Annotated[str, "char *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.floatspanset_out(ss_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def intset_in(string: str) -> Annotated[cdata, "Set *"]:
    string_converted = string.encode("utf-8")
    result = _lib.intset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intset_out(set: Annotated[cdata, "const Set *"]) -> Annotated[str, "char *"]:
    set_converted = _ffi.cast("const Set *", set)
    result = _lib.intset_out(set_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def intspan_in(string: str) -> Annotated[cdata, "Span *"]:
    string_converted = string.encode("utf-8")
    result = _lib.intspan_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intspan_out(s: Annotated[cdata, "const Span *"]) -> Annotated[str, "char *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.intspan_out(s_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def intspanset_in(string: str) -> Annotated[cdata, "SpanSet *"]:
    string_converted = string.encode("utf-8")
    result = _lib.intspanset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intspanset_out(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[str, "char *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.intspanset_out(ss_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def set_as_hexwkb(
    s: Annotated[cdata, "const Set *"], variant: int
) -> tuple[Annotated[str, "char *"], Annotated[cdata, "size_t *"]]:
    s_converted = _ffi.cast("const Set *", s)
    variant_converted = _ffi.cast("uint8_t", variant)
    size_out = _ffi.new("size_t *")
    result = _lib.set_as_hexwkb(s_converted, variant_converted, size_out)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None, size_out[0]


def set_as_wkb(
    s: Annotated[cdata, "const Set *"], variant: int
) -> tuple[Annotated[cdata, "uint8_t *"], Annotated[cdata, "size_t *"]]:
    s_converted = _ffi.cast("const Set *", s)
    variant_converted = _ffi.cast("uint8_t", variant)
    size_out = _ffi.new("size_t *")
    result = _lib.set_as_wkb(s_converted, variant_converted, size_out)
    _check_error()
    result_converted = bytes(result[i] for i in range(size_out[0])) if result != _ffi.NULL else None
    return result_converted


def set_from_hexwkb(hexwkb: str) -> Annotated[cdata, "Set *"]:
    hexwkb_converted = hexwkb.encode("utf-8")
    result = _lib.set_from_hexwkb(hexwkb_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_from_wkb(wkb: bytes) -> "Set *":
    wkb_converted = _ffi.new("uint8_t []", wkb)
    result = _lib.set_from_wkb(wkb_converted, len(wkb))
    return result if result != _ffi.NULL else None


def span_as_hexwkb(
    s: Annotated[cdata, "const Span *"], variant: int
) -> tuple[Annotated[str, "char *"], Annotated[cdata, "size_t *"]]:
    s_converted = _ffi.cast("const Span *", s)
    variant_converted = _ffi.cast("uint8_t", variant)
    size_out = _ffi.new("size_t *")
    result = _lib.span_as_hexwkb(s_converted, variant_converted, size_out)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None, size_out[0]


def span_as_wkb(
    s: Annotated[cdata, "const Span *"], variant: int
) -> tuple[Annotated[cdata, "uint8_t *"], Annotated[cdata, "size_t *"]]:
    s_converted = _ffi.cast("const Span *", s)
    variant_converted = _ffi.cast("uint8_t", variant)
    size_out = _ffi.new("size_t *")
    result = _lib.span_as_wkb(s_converted, variant_converted, size_out)
    _check_error()
    result_converted = bytes(result[i] for i in range(size_out[0])) if result != _ffi.NULL else None
    return result_converted


def span_from_hexwkb(hexwkb: str) -> Annotated[cdata, "Span *"]:
    hexwkb_converted = hexwkb.encode("utf-8")
    result = _lib.span_from_hexwkb(hexwkb_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_from_wkb(wkb: bytes) -> "Span *":
    wkb_converted = _ffi.new("uint8_t []", wkb)
    result = _lib.span_from_wkb(wkb_converted, len(wkb))
    return result if result != _ffi.NULL else None


def spanset_as_hexwkb(
    ss: Annotated[cdata, "const SpanSet *"], variant: int
) -> tuple[Annotated[str, "char *"], Annotated[cdata, "size_t *"]]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    variant_converted = _ffi.cast("uint8_t", variant)
    size_out = _ffi.new("size_t *")
    result = _lib.spanset_as_hexwkb(ss_converted, variant_converted, size_out)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None, size_out[0]


def spanset_as_wkb(
    ss: Annotated[cdata, "const SpanSet *"], variant: int
) -> tuple[Annotated[cdata, "uint8_t *"], Annotated[cdata, "size_t *"]]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    variant_converted = _ffi.cast("uint8_t", variant)
    size_out = _ffi.new("size_t *")
    result = _lib.spanset_as_wkb(ss_converted, variant_converted, size_out)
    _check_error()
    result_converted = bytes(result[i] for i in range(size_out[0])) if result != _ffi.NULL else None
    return result_converted


def spanset_from_hexwkb(hexwkb: str) -> Annotated[cdata, "SpanSet *"]:
    hexwkb_converted = hexwkb.encode("utf-8")
    result = _lib.spanset_from_hexwkb(hexwkb_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_from_wkb(wkb: bytes) -> "SpanSet *":
    wkb_converted = _ffi.new("uint8_t []", wkb)
    result = _lib.spanset_from_wkb(wkb_converted, len(wkb))
    return result if result != _ffi.NULL else None


def textset_in(string: str) -> Annotated[cdata, "Set *"]:
    string_converted = string.encode("utf-8")
    result = _lib.textset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def textset_out(set: Annotated[cdata, "const Set *"]) -> Annotated[str, "char *"]:
    set_converted = _ffi.cast("const Set *", set)
    result = _lib.textset_out(set_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def tstzset_in(string: str) -> Annotated[cdata, "Set *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tstzset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzset_out(set: Annotated[cdata, "const Set *"]) -> Annotated[str, "char *"]:
    set_converted = _ffi.cast("const Set *", set)
    result = _lib.tstzset_out(set_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def tstzspan_in(string: str) -> Annotated[cdata, "Span *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tstzspan_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspan_out(s: Annotated[cdata, "const Span *"]) -> Annotated[str, "char *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tstzspan_out(s_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def tstzspanset_in(string: str) -> Annotated[cdata, "SpanSet *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tstzspanset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspanset_out(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[str, "char *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tstzspanset_out(ss_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def bigintset_make(values: "list[const int64]") -> Annotated[cdata, "Set *"]:
    values_converted = _ffi.new("const int64 []", values)
    result = _lib.bigintset_make(values_converted, len(values))
    _check_error()
    return result if result != _ffi.NULL else None


def bigintspan_make(lower: int, upper: int, lower_inc: bool, upper_inc: bool) -> Annotated[cdata, "Span *"]:
    lower_converted = _ffi.cast("int64", lower)
    upper_converted = _ffi.cast("int64", upper)
    result = _lib.bigintspan_make(lower_converted, upper_converted, lower_inc, upper_inc)
    _check_error()
    return result if result != _ffi.NULL else None


def dateset_make(values: "list[const DateADT]") -> Annotated[cdata, "Set *"]:
    values_converted = _ffi.new("const DateADT []", values)
    result = _lib.dateset_make(values_converted, len(values))
    _check_error()
    return result if result != _ffi.NULL else None


def datespan_make(lower: int, upper: int, lower_inc: bool, upper_inc: bool) -> Annotated[cdata, "Span *"]:
    lower_converted = _ffi.cast("DateADT", lower)
    upper_converted = _ffi.cast("DateADT", upper)
    result = _lib.datespan_make(lower_converted, upper_converted, lower_inc, upper_inc)
    _check_error()
    return result if result != _ffi.NULL else None


def floatset_make(values: "list[const double]") -> Annotated[cdata, "Set *"]:
    values_converted = _ffi.new("const double []", values)
    result = _lib.floatset_make(values_converted, len(values))
    _check_error()
    return result if result != _ffi.NULL else None


def floatspan_make(lower: float, upper: float, lower_inc: bool, upper_inc: bool) -> Annotated[cdata, "Span *"]:
    result = _lib.floatspan_make(lower, upper, lower_inc, upper_inc)
    _check_error()
    return result if result != _ffi.NULL else None


def intset_make(values: "list[const int]") -> Annotated[cdata, "Set *"]:
    values_converted = _ffi.new("const int []", values)
    result = _lib.intset_make(values_converted, len(values))
    _check_error()
    return result if result != _ffi.NULL else None


def intspan_make(lower: int, upper: int, lower_inc: bool, upper_inc: bool) -> Annotated[cdata, "Span *"]:
    result = _lib.intspan_make(lower, upper, lower_inc, upper_inc)
    _check_error()
    return result if result != _ffi.NULL else None


def set_copy(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_copy(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_copy(s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.span_copy(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_copy(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_copy(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_make(spans: list[Annotated[cdata, "Span *"]]) -> Annotated[cdata, "SpanSet *"]:
    spans_converted = _ffi.new("Span []", spans)
    result = _lib.spanset_make(spans_converted, len(spans))
    _check_error()
    return result if result != _ffi.NULL else None


def textset_make(values: list[str]) -> Annotated[cdata, "Set *"]:
    values_converted = [cstring2text(x) for x in values]
    result = _lib.textset_make(values_converted, len(values))
    _check_error()
    return result if result != _ffi.NULL else None


def tstzset_make(values: list[int]) -> Annotated[cdata, "Set *"]:
    values_converted = [_ffi.cast("const TimestampTz", x) for x in values]
    result = _lib.tstzset_make(values_converted, len(values))
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspan_make(lower: int, upper: int, lower_inc: bool, upper_inc: bool) -> Annotated[cdata, "Span *"]:
    lower_converted = _ffi.cast("TimestampTz", lower)
    upper_converted = _ffi.cast("TimestampTz", upper)
    result = _lib.tstzspan_make(lower_converted, upper_converted, lower_inc, upper_inc)
    _check_error()
    return result if result != _ffi.NULL else None


def bigint_to_set(i: int) -> Annotated[cdata, "Set *"]:
    i_converted = _ffi.cast("int64", i)
    result = _lib.bigint_to_set(i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigint_to_span(i: int) -> Annotated[cdata, "Span *"]:
    result = _lib.bigint_to_span(i)
    _check_error()
    return result if result != _ffi.NULL else None


def bigint_to_spanset(i: int) -> Annotated[cdata, "SpanSet *"]:
    result = _lib.bigint_to_spanset(i)
    _check_error()
    return result if result != _ffi.NULL else None


def date_to_set(d: int) -> Annotated[cdata, "Set *"]:
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.date_to_set(d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def date_to_span(d: int) -> Annotated[cdata, "Span *"]:
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.date_to_span(d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def date_to_spanset(d: int) -> Annotated[cdata, "SpanSet *"]:
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.date_to_spanset(d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def dateset_to_tstzset(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.dateset_to_tstzset(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datespan_to_tstzspan(s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.datespan_to_tstzspan(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datespanset_to_tstzspanset(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.datespanset_to_tstzspanset(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def float_to_set(d: float) -> Annotated[cdata, "Set *"]:
    result = _lib.float_to_set(d)
    _check_error()
    return result if result != _ffi.NULL else None


def float_to_span(d: float) -> Annotated[cdata, "Span *"]:
    result = _lib.float_to_span(d)
    _check_error()
    return result if result != _ffi.NULL else None


def float_to_spanset(d: float) -> Annotated[cdata, "SpanSet *"]:
    result = _lib.float_to_spanset(d)
    _check_error()
    return result if result != _ffi.NULL else None


def floatset_to_intset(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.floatset_to_intset(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspan_to_intspan(s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.floatspan_to_intspan(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspanset_to_intspanset(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.floatspanset_to_intspanset(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def int_to_set(i: int) -> Annotated[cdata, "Set *"]:
    result = _lib.int_to_set(i)
    _check_error()
    return result if result != _ffi.NULL else None


def int_to_span(i: int) -> Annotated[cdata, "Span *"]:
    result = _lib.int_to_span(i)
    _check_error()
    return result if result != _ffi.NULL else None


def int_to_spanset(i: int) -> Annotated[cdata, "SpanSet *"]:
    result = _lib.int_to_spanset(i)
    _check_error()
    return result if result != _ffi.NULL else None


def intset_to_floatset(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intset_to_floatset(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intspan_to_floatspan(s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.intspan_to_floatspan(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intspanset_to_floatspanset(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.intspanset_to_floatspanset(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_to_span(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_to_span(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_to_spanset(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_to_spanset(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_to_spanset(s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.span_to_spanset(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def text_to_set(txt: str) -> Annotated[cdata, "Set *"]:
    txt_converted = cstring2text(txt)
    result = _lib.text_to_set(txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timestamptz_to_set(t: int) -> Annotated[cdata, "Set *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.timestamptz_to_set(t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timestamptz_to_span(t: int) -> Annotated[cdata, "Span *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.timestamptz_to_span(t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timestamptz_to_spanset(t: int) -> Annotated[cdata, "SpanSet *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.timestamptz_to_spanset(t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzset_to_dateset(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tstzset_to_dateset(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspan_to_datespan(s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tstzspan_to_datespan(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspanset_to_datespanset(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tstzspanset_to_datespanset(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintset_end_value(s: Annotated[cdata, "const Set *"]) -> Annotated[int, "int64"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.bigintset_end_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintset_start_value(s: Annotated[cdata, "const Set *"]) -> Annotated[int, "int64"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.bigintset_start_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintset_value_n(s: Annotated[cdata, "const Set *"], n: int) -> Annotated[cdata, "int64"]:
    s_converted = _ffi.cast("const Set *", s)
    out_result = _ffi.new("int64 *")
    result = _lib.bigintset_value_n(s_converted, n, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def bigintset_values(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "int64 *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.bigintset_values(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintspan_lower(s: Annotated[cdata, "const Span *"]) -> Annotated[int, "int64"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.bigintspan_lower(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintspan_upper(s: Annotated[cdata, "const Span *"]) -> Annotated[int, "int64"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.bigintspan_upper(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintspan_width(s: Annotated[cdata, "const Span *"]) -> Annotated[int, "int64"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.bigintspan_width(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintspanset_lower(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "int64"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.bigintspanset_lower(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintspanset_upper(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "int64"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.bigintspanset_upper(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintspanset_width(ss: Annotated[cdata, "const SpanSet *"], boundspan: bool) -> Annotated[int, "int64"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.bigintspanset_width(ss_converted, boundspan)
    _check_error()
    return result if result != _ffi.NULL else None


def dateset_end_value(s: Annotated[cdata, "const Set *"]) -> Annotated[int, "DateADT"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.dateset_end_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def dateset_start_value(s: Annotated[cdata, "const Set *"]) -> Annotated[int, "DateADT"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.dateset_start_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def dateset_value_n(s: Annotated[cdata, "const Set *"], n: int) -> Annotated[cdata, "DateADT *"]:
    s_converted = _ffi.cast("const Set *", s)
    out_result = _ffi.new("DateADT *")
    result = _lib.dateset_value_n(s_converted, n, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def dateset_values(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "DateADT *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.dateset_values(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datespan_duration(s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "Interval *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.datespan_duration(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datespan_lower(s: Annotated[cdata, "const Span *"]) -> Annotated[int, "DateADT"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.datespan_lower(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datespan_upper(s: Annotated[cdata, "const Span *"]) -> Annotated[int, "DateADT"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.datespan_upper(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datespanset_date_n(ss: Annotated[cdata, "const SpanSet *"], n: int) -> Annotated[cdata, "DateADT *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    out_result = _ffi.new("DateADT *")
    result = _lib.datespanset_date_n(ss_converted, n, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def datespanset_dates(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "Set *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.datespanset_dates(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datespanset_duration(ss: Annotated[cdata, "const SpanSet *"], boundspan: bool) -> Annotated[cdata, "Interval *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.datespanset_duration(ss_converted, boundspan)
    _check_error()
    return result if result != _ffi.NULL else None


def datespanset_end_date(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "DateADT"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.datespanset_end_date(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datespanset_num_dates(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "int"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.datespanset_num_dates(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datespanset_start_date(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "DateADT"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.datespanset_start_date(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatset_end_value(s: Annotated[cdata, "const Set *"]) -> Annotated[float, "double"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.floatset_end_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatset_start_value(s: Annotated[cdata, "const Set *"]) -> Annotated[float, "double"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.floatset_start_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatset_value_n(s: Annotated[cdata, "const Set *"], n: int) -> Annotated[cdata, "double"]:
    s_converted = _ffi.cast("const Set *", s)
    out_result = _ffi.new("double *")
    result = _lib.floatset_value_n(s_converted, n, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def floatset_values(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "double *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.floatset_values(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspan_lower(s: Annotated[cdata, "const Span *"]) -> Annotated[float, "double"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.floatspan_lower(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspan_upper(s: Annotated[cdata, "const Span *"]) -> Annotated[float, "double"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.floatspan_upper(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspan_width(s: Annotated[cdata, "const Span *"]) -> Annotated[float, "double"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.floatspan_width(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspanset_lower(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[float, "double"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.floatspanset_lower(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspanset_upper(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[float, "double"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.floatspanset_upper(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspanset_width(ss: Annotated[cdata, "const SpanSet *"], boundspan: bool) -> Annotated[float, "double"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.floatspanset_width(ss_converted, boundspan)
    _check_error()
    return result if result != _ffi.NULL else None


def intset_end_value(s: Annotated[cdata, "const Set *"]) -> Annotated[int, "int"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intset_end_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intset_start_value(s: Annotated[cdata, "const Set *"]) -> Annotated[int, "int"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intset_start_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intset_value_n(s: Annotated[cdata, "const Set *"], n: int) -> Annotated[cdata, "int"]:
    s_converted = _ffi.cast("const Set *", s)
    out_result = _ffi.new("int *")
    result = _lib.intset_value_n(s_converted, n, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def intset_values(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "int *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intset_values(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intspan_lower(s: Annotated[cdata, "const Span *"]) -> Annotated[int, "int"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.intspan_lower(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intspan_upper(s: Annotated[cdata, "const Span *"]) -> Annotated[int, "int"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.intspan_upper(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intspan_width(s: Annotated[cdata, "const Span *"]) -> Annotated[int, "int"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.intspan_width(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intspanset_lower(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "int"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.intspanset_lower(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intspanset_upper(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "int"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.intspanset_upper(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intspanset_width(ss: Annotated[cdata, "const SpanSet *"], boundspan: bool) -> Annotated[int, "int"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.intspanset_width(ss_converted, boundspan)
    _check_error()
    return result if result != _ffi.NULL else None


def set_hash(s: Annotated[cdata, "const Set *"]) -> Annotated[int, "uint32"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_hash(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_hash_extended(s: Annotated[cdata, "const Set *"], seed: int) -> Annotated[int, "uint64"]:
    s_converted = _ffi.cast("const Set *", s)
    seed_converted = _ffi.cast("uint64", seed)
    result = _lib.set_hash_extended(s_converted, seed_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_num_values(s: Annotated[cdata, "const Set *"]) -> Annotated[int, "int"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_num_values(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_hash(s: Annotated[cdata, "const Span *"]) -> Annotated[int, "uint32"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.span_hash(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_hash_extended(s: Annotated[cdata, "const Span *"], seed: int) -> Annotated[int, "uint64"]:
    s_converted = _ffi.cast("const Span *", s)
    seed_converted = _ffi.cast("uint64", seed)
    result = _lib.span_hash_extended(s_converted, seed_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_lower_inc(s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.span_lower_inc(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_upper_inc(s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.span_upper_inc(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_end_span(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "Span *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_end_span(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_hash(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "uint32"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_hash(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_hash_extended(ss: Annotated[cdata, "const SpanSet *"], seed: int) -> Annotated[int, "uint64"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    seed_converted = _ffi.cast("uint64", seed)
    result = _lib.spanset_hash_extended(ss_converted, seed_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_lower_inc(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_lower_inc(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_num_spans(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "int"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_num_spans(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_span(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "Span *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_span(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_span_n(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[cdata, "Span *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_span_n(ss_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_spanarr(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "Span **"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_spanarr(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_start_span(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "Span *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_start_span(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_upper_inc(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_upper_inc(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def textset_end_value(s: Annotated[cdata, "const Set *"]) -> Annotated[str, "text *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.textset_end_value(s_converted)
    _check_error()
    result = text2cstring(result)
    return result if result != _ffi.NULL else None


def textset_start_value(s: Annotated[cdata, "const Set *"]) -> Annotated[str, "text *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.textset_start_value(s_converted)
    _check_error()
    result = text2cstring(result)
    return result if result != _ffi.NULL else None


def textset_value_n(s: Annotated[cdata, "const Set *"], n: int) -> Annotated[list, "text **"]:
    s_converted = _ffi.cast("const Set *", s)
    out_result = _ffi.new("text **")
    result = _lib.textset_value_n(s_converted, n, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def textset_values(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "text **"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.textset_values(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzset_end_value(s: Annotated[cdata, "const Set *"]) -> Annotated[int, "TimestampTz"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tstzset_end_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzset_start_value(s: Annotated[cdata, "const Set *"]) -> Annotated[int, "TimestampTz"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tstzset_start_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzset_value_n(s: Annotated[cdata, "const Set *"], n: int) -> int:
    s_converted = _ffi.cast("const Set *", s)
    out_result = _ffi.new("TimestampTz *")
    result = _lib.tstzset_value_n(s_converted, n, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tstzset_values(s: Annotated[cdata, "const Set *"]) -> Annotated[int, "TimestampTz *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tstzset_values(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspan_duration(s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "Interval *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tstzspan_duration(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspan_lower(s: Annotated[cdata, "const Span *"]) -> Annotated[int, "TimestampTz"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tstzspan_lower(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspan_upper(s: Annotated[cdata, "const Span *"]) -> Annotated[int, "TimestampTz"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tstzspan_upper(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspanset_duration(ss: Annotated[cdata, "const SpanSet *"], boundspan: bool) -> Annotated[cdata, "Interval *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tstzspanset_duration(ss_converted, boundspan)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspanset_end_timestamptz(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "TimestampTz"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tstzspanset_end_timestamptz(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspanset_lower(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "TimestampTz"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tstzspanset_lower(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspanset_num_timestamps(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "int"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tstzspanset_num_timestamps(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspanset_start_timestamptz(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "TimestampTz"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tstzspanset_start_timestamptz(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspanset_timestamps(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "Set *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tstzspanset_timestamps(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspanset_timestamptz_n(ss: Annotated[cdata, "const SpanSet *"], n: int) -> int:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    out_result = _ffi.new("TimestampTz *")
    result = _lib.tstzspanset_timestamptz_n(ss_converted, n, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tstzspanset_upper(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "TimestampTz"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tstzspanset_upper(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintset_shift_scale(
    s: Annotated[cdata, "const Set *"], shift: int, width: int, hasshift: bool, haswidth: bool
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    shift_converted = _ffi.cast("int64", shift)
    width_converted = _ffi.cast("int64", width)
    result = _lib.bigintset_shift_scale(s_converted, shift_converted, width_converted, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintspan_shift_scale(
    s: Annotated[cdata, "const Span *"], shift: int, width: int, hasshift: bool, haswidth: bool
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    shift_converted = _ffi.cast("int64", shift)
    width_converted = _ffi.cast("int64", width)
    result = _lib.bigintspan_shift_scale(s_converted, shift_converted, width_converted, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintspanset_shift_scale(
    ss: Annotated[cdata, "const SpanSet *"], shift: int, width: int, hasshift: bool, haswidth: bool
) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    shift_converted = _ffi.cast("int64", shift)
    width_converted = _ffi.cast("int64", width)
    result = _lib.bigintspanset_shift_scale(ss_converted, shift_converted, width_converted, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def dateset_shift_scale(
    s: Annotated[cdata, "const Set *"], shift: int, width: int, hasshift: bool, haswidth: bool
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.dateset_shift_scale(s_converted, shift, width, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def datespan_shift_scale(
    s: Annotated[cdata, "const Span *"], shift: int, width: int, hasshift: bool, haswidth: bool
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.datespan_shift_scale(s_converted, shift, width, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def datespanset_shift_scale(
    ss: Annotated[cdata, "const SpanSet *"], shift: int, width: int, hasshift: bool, haswidth: bool
) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.datespanset_shift_scale(ss_converted, shift, width, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def floatset_ceil(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.floatset_ceil(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatset_degrees(s: Annotated[cdata, "const Set *"], normalize: bool) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.floatset_degrees(s_converted, normalize)
    _check_error()
    return result if result != _ffi.NULL else None


def floatset_floor(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.floatset_floor(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatset_radians(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.floatset_radians(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatset_shift_scale(
    s: Annotated[cdata, "const Set *"], shift: float, width: float, hasshift: bool, haswidth: bool
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.floatset_shift_scale(s_converted, shift, width, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspan_ceil(s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.floatspan_ceil(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspan_degrees(s: Annotated[cdata, "const Span *"], normalize: bool) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.floatspan_degrees(s_converted, normalize)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspan_floor(s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.floatspan_floor(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspan_radians(s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.floatspan_radians(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspan_round(s: Annotated[cdata, "const Span *"], maxdd: int) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.floatspan_round(s_converted, maxdd)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspan_shift_scale(
    s: Annotated[cdata, "const Span *"], shift: float, width: float, hasshift: bool, haswidth: bool
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.floatspan_shift_scale(s_converted, shift, width, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspanset_ceil(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.floatspanset_ceil(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspanset_floor(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.floatspanset_floor(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspanset_degrees(ss: Annotated[cdata, "const SpanSet *"], normalize: bool) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.floatspanset_degrees(ss_converted, normalize)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspanset_radians(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.floatspanset_radians(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspanset_round(ss: Annotated[cdata, "const SpanSet *"], maxdd: int) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.floatspanset_round(ss_converted, maxdd)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspanset_shift_scale(
    ss: Annotated[cdata, "const SpanSet *"], shift: float, width: float, hasshift: bool, haswidth: bool
) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.floatspanset_shift_scale(ss_converted, shift, width, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def intset_shift_scale(
    s: Annotated[cdata, "const Set *"], shift: int, width: int, hasshift: bool, haswidth: bool
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intset_shift_scale(s_converted, shift, width, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def intspan_shift_scale(
    s: Annotated[cdata, "const Span *"], shift: int, width: int, hasshift: bool, haswidth: bool
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.intspan_shift_scale(s_converted, shift, width, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def intspanset_shift_scale(
    ss: Annotated[cdata, "const SpanSet *"], shift: int, width: int, hasshift: bool, haswidth: bool
) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.intspanset_shift_scale(ss_converted, shift, width, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def numspan_expand(s: Annotated[cdata, "const Span *"], value: Annotated[cdata, "Datum"]) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.numspan_expand(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspan_expand(
    s: Annotated[cdata, "const Span *"], interv: Annotated[cdata, "const Interval *"]
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.tstzspan_expand(s_converted, interv_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_round(s: Annotated[cdata, "const Set *"], maxdd: int) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_round(s_converted, maxdd)
    _check_error()
    return result if result != _ffi.NULL else None


def textcat_text_textset(txt: str, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    txt_converted = cstring2text(txt)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.textcat_text_textset(txt_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def textcat_textset_text(s: Annotated[cdata, "const Set *"], txt: str) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    txt_converted = cstring2text(txt)
    result = _lib.textcat_textset_text(s_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def textset_initcap(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.textset_initcap(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def textset_lower(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.textset_lower(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def textset_upper(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.textset_upper(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timestamptz_tprecision(
    t: int, duration: Annotated[cdata, "const Interval *"], torigin: int
) -> Annotated[int, "TimestampTz"]:
    t_converted = _ffi.cast("TimestampTz", t)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    result = _lib.timestamptz_tprecision(t_converted, duration_converted, torigin_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzset_shift_scale(
    s: Annotated[cdata, "const Set *"],
    shift: Annotated[cdata, "const Interval *"] | None,
    duration: Annotated[cdata, "const Interval *"] | None,
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    shift_converted = _ffi.cast("const Interval *", shift) if shift is not None else _ffi.NULL
    duration_converted = _ffi.cast("const Interval *", duration) if duration is not None else _ffi.NULL
    result = _lib.tstzset_shift_scale(s_converted, shift_converted, duration_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzset_tprecision(
    s: Annotated[cdata, "const Set *"], duration: Annotated[cdata, "const Interval *"], torigin: int
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    result = _lib.tstzset_tprecision(s_converted, duration_converted, torigin_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspan_shift_scale(
    s: Annotated[cdata, "const Span *"],
    shift: Annotated[cdata, "const Interval *"] | None,
    duration: Annotated[cdata, "const Interval *"] | None,
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    shift_converted = _ffi.cast("const Interval *", shift) if shift is not None else _ffi.NULL
    duration_converted = _ffi.cast("const Interval *", duration) if duration is not None else _ffi.NULL
    result = _lib.tstzspan_shift_scale(s_converted, shift_converted, duration_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspan_tprecision(
    s: Annotated[cdata, "const Span *"], duration: Annotated[cdata, "const Interval *"], torigin: int
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    result = _lib.tstzspan_tprecision(s_converted, duration_converted, torigin_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspanset_shift_scale(
    ss: Annotated[cdata, "const SpanSet *"],
    shift: Annotated[cdata, "const Interval *"] | None,
    duration: Annotated[cdata, "const Interval *"] | None,
) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    shift_converted = _ffi.cast("const Interval *", shift) if shift is not None else _ffi.NULL
    duration_converted = _ffi.cast("const Interval *", duration) if duration is not None else _ffi.NULL
    result = _lib.tstzspanset_shift_scale(ss_converted, shift_converted, duration_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspanset_tprecision(
    ss: Annotated[cdata, "const SpanSet *"], duration: Annotated[cdata, "const Interval *"], torigin: int
) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    result = _lib.tstzspanset_tprecision(ss_converted, duration_converted, torigin_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_cmp(s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]) -> Annotated[int, "int"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.set_cmp(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_eq(s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.set_eq(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_ge(s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.set_ge(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_gt(s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.set_gt(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_le(s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.set_le(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_lt(s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.set_lt(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_ne(s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.set_ne(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_cmp(s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]) -> Annotated[int, "int"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.span_cmp(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_eq(s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.span_eq(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_ge(s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.span_ge(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_gt(s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.span_gt(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_le(s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.span_le(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_lt(s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.span_lt(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_ne(s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.span_ne(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_cmp(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[int, "int"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.spanset_cmp(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_eq(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.spanset_eq(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_ge(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.spanset_ge(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_gt(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.spanset_gt(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_le(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.spanset_le(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_lt(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.spanset_lt(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_ne(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.spanset_ne(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_spans(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_spans(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_split_each_n_spans(
    s: Annotated[cdata, "const Set *"], elems_per_span: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Set *", s)
    count_converted = _ffi.cast("int *", count)
    result = _lib.set_split_each_n_spans(s_converted, elems_per_span, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_split_n_spans(
    s: Annotated[cdata, "const Set *"], span_count: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Set *", s)
    count_converted = _ffi.cast("int *", count)
    result = _lib.set_split_n_spans(s_converted, span_count, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_spans(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "Span *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_spans(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_split_each_n_spans(
    ss: Annotated[cdata, "const SpanSet *"], elems_per_span: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    count_converted = _ffi.cast("int *", count)
    result = _lib.spanset_split_each_n_spans(ss_converted, elems_per_span, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_split_n_spans(
    ss: Annotated[cdata, "const SpanSet *"], span_count: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    count_converted = _ffi.cast("int *", count)
    result = _lib.spanset_split_n_spans(ss_converted, span_count, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_span_bigint(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.adjacent_span_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_span_date(s: Annotated[cdata, "const Span *"], d: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.adjacent_span_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_span_float(s: Annotated[cdata, "const Span *"], d: float) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.adjacent_span_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_span_int(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.adjacent_span_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.adjacent_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_span_spanset(
    s: Annotated[cdata, "const Span *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.adjacent_span_spanset(s_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_span_timestamptz(s: Annotated[cdata, "const Span *"], t: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.adjacent_span_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_spanset_bigint(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    i_converted = _ffi.cast("int64", i)
    result = _lib.adjacent_spanset_bigint(ss_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_spanset_date(ss: Annotated[cdata, "const SpanSet *"], d: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.adjacent_spanset_date(ss_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_spanset_float(ss: Annotated[cdata, "const SpanSet *"], d: float) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.adjacent_spanset_float(ss_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_spanset_int(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.adjacent_spanset_int(ss_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_spanset_timestamptz(ss: Annotated[cdata, "const SpanSet *"], t: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.adjacent_spanset_timestamptz(ss_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_spanset_span(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.adjacent_spanset_span(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_spanset_spanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.adjacent_spanset_spanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_bigint_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.contained_bigint_set(i_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_bigint_span(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.contained_bigint_span(i_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_bigint_spanset(i: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.contained_bigint_spanset(i_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_date_set(d: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.contained_date_set(d_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_date_span(d: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.contained_date_span(d_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_date_spanset(d: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.contained_date_spanset(d_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_float_set(d: float, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.contained_float_set(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_float_span(d: float, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.contained_float_span(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_float_spanset(d: float, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.contained_float_spanset(d, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_int_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.contained_int_set(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_int_span(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.contained_int_span(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_int_spanset(i: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.contained_int_spanset(i, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_set_set(
    s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.contained_set_set(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.contained_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_span_spanset(
    s: Annotated[cdata, "const Span *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.contained_span_spanset(s_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_spanset_span(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.contained_spanset_span(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_spanset_spanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.contained_spanset_spanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_text_set(txt: str, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    txt_converted = cstring2text(txt)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.contained_text_set(txt_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_timestamptz_set(t: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.contained_timestamptz_set(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_timestamptz_span(t: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.contained_timestamptz_span(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_timestamptz_spanset(t: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.contained_timestamptz_spanset(t_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_set_bigint(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.contains_set_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_set_date(s: Annotated[cdata, "const Set *"], d: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.contains_set_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_set_float(s: Annotated[cdata, "const Set *"], d: float) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.contains_set_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_set_int(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.contains_set_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_set_set(
    s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.contains_set_set(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_set_text(s: Annotated[cdata, "const Set *"], t: str) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    t_converted = cstring2text(t)
    result = _lib.contains_set_text(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_set_timestamptz(s: Annotated[cdata, "const Set *"], t: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.contains_set_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_span_bigint(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.contains_span_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_span_date(s: Annotated[cdata, "const Span *"], d: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.contains_span_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_span_float(s: Annotated[cdata, "const Span *"], d: float) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.contains_span_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_span_int(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.contains_span_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.contains_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_span_spanset(
    s: Annotated[cdata, "const Span *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.contains_span_spanset(s_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_span_timestamptz(s: Annotated[cdata, "const Span *"], t: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.contains_span_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_spanset_bigint(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    i_converted = _ffi.cast("int64", i)
    result = _lib.contains_spanset_bigint(ss_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_spanset_date(ss: Annotated[cdata, "const SpanSet *"], d: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.contains_spanset_date(ss_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_spanset_float(ss: Annotated[cdata, "const SpanSet *"], d: float) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.contains_spanset_float(ss_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_spanset_int(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.contains_spanset_int(ss_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_spanset_span(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.contains_spanset_span(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_spanset_spanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.contains_spanset_spanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_spanset_timestamptz(ss: Annotated[cdata, "const SpanSet *"], t: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.contains_spanset_timestamptz(ss_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_set_set(
    s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.overlaps_set_set(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.overlaps_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_span_spanset(
    s: Annotated[cdata, "const Span *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overlaps_span_spanset(s_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_spanset_span(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overlaps_spanset_span(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_spanset_spanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.overlaps_spanset_spanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_date_set(d: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.after_date_set(d_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_date_span(d: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.after_date_span(d_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_date_spanset(d: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.after_date_spanset(d_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_set_date(s: Annotated[cdata, "const Set *"], d: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.after_set_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_set_timestamptz(s: Annotated[cdata, "const Set *"], t: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.after_set_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_span_date(s: Annotated[cdata, "const Span *"], d: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.after_span_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_span_timestamptz(s: Annotated[cdata, "const Span *"], t: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.after_span_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_spanset_date(ss: Annotated[cdata, "const SpanSet *"], d: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.after_spanset_date(ss_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_spanset_timestamptz(ss: Annotated[cdata, "const SpanSet *"], t: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.after_spanset_timestamptz(ss_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_timestamptz_set(t: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.after_timestamptz_set(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_timestamptz_span(t: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.after_timestamptz_span(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_timestamptz_spanset(t: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.after_timestamptz_spanset(t_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_date_set(d: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.before_date_set(d_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_date_span(d: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.before_date_span(d_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_date_spanset(d: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.before_date_spanset(d_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_set_date(s: Annotated[cdata, "const Set *"], d: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.before_set_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_set_timestamptz(s: Annotated[cdata, "const Set *"], t: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.before_set_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_span_date(s: Annotated[cdata, "const Span *"], d: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.before_span_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_span_timestamptz(s: Annotated[cdata, "const Span *"], t: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.before_span_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_spanset_date(ss: Annotated[cdata, "const SpanSet *"], d: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.before_spanset_date(ss_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_spanset_timestamptz(ss: Annotated[cdata, "const SpanSet *"], t: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.before_spanset_timestamptz(ss_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_timestamptz_set(t: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.before_timestamptz_set(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_timestamptz_span(t: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.before_timestamptz_span(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_timestamptz_spanset(t: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.before_timestamptz_spanset(t_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_bigint_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.left_bigint_set(i_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_bigint_span(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.left_bigint_span(i_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_bigint_spanset(i: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.left_bigint_spanset(i_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_float_set(d: float, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.left_float_set(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_float_span(d: float, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.left_float_span(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_float_spanset(d: float, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.left_float_spanset(d, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_int_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.left_int_set(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_int_span(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.left_int_span(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_int_spanset(i: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.left_int_spanset(i, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_set_bigint(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.left_set_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_set_float(s: Annotated[cdata, "const Set *"], d: float) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.left_set_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def left_set_int(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.left_set_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def left_set_set(s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.left_set_set(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_set_text(s: Annotated[cdata, "const Set *"], txt: str) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    txt_converted = cstring2text(txt)
    result = _lib.left_set_text(s_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_span_bigint(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.left_span_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_span_float(s: Annotated[cdata, "const Span *"], d: float) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.left_span_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def left_span_int(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.left_span_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def left_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.left_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_span_spanset(
    s: Annotated[cdata, "const Span *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.left_span_spanset(s_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_spanset_bigint(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    i_converted = _ffi.cast("int64", i)
    result = _lib.left_spanset_bigint(ss_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_spanset_float(ss: Annotated[cdata, "const SpanSet *"], d: float) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.left_spanset_float(ss_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def left_spanset_int(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.left_spanset_int(ss_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def left_spanset_span(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.left_spanset_span(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_spanset_spanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.left_spanset_spanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_text_set(txt: str, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    txt_converted = cstring2text(txt)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.left_text_set(txt_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_date_set(d: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overafter_date_set(d_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_date_span(d: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overafter_date_span(d_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_date_spanset(d: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overafter_date_spanset(d_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_set_date(s: Annotated[cdata, "const Set *"], d: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.overafter_set_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_set_timestamptz(s: Annotated[cdata, "const Set *"], t: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.overafter_set_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_span_date(s: Annotated[cdata, "const Span *"], d: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.overafter_span_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_span_timestamptz(s: Annotated[cdata, "const Span *"], t: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.overafter_span_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_spanset_date(ss: Annotated[cdata, "const SpanSet *"], d: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.overafter_spanset_date(ss_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_spanset_timestamptz(ss: Annotated[cdata, "const SpanSet *"], t: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.overafter_spanset_timestamptz(ss_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_timestamptz_set(t: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overafter_timestamptz_set(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_timestamptz_span(t: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overafter_timestamptz_span(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_timestamptz_spanset(t: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overafter_timestamptz_spanset(t_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_date_set(d: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overbefore_date_set(d_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_date_span(d: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overbefore_date_span(d_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_date_spanset(d: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("DateADT", d)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overbefore_date_spanset(d_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_set_date(s: Annotated[cdata, "const Set *"], d: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.overbefore_set_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_set_timestamptz(s: Annotated[cdata, "const Set *"], t: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.overbefore_set_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_span_date(s: Annotated[cdata, "const Span *"], d: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.overbefore_span_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_span_timestamptz(s: Annotated[cdata, "const Span *"], t: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.overbefore_span_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_spanset_date(ss: Annotated[cdata, "const SpanSet *"], d: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.overbefore_spanset_date(ss_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_spanset_timestamptz(ss: Annotated[cdata, "const SpanSet *"], t: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.overbefore_spanset_timestamptz(ss_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_timestamptz_set(t: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overbefore_timestamptz_set(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_timestamptz_span(t: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overbefore_timestamptz_span(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_timestamptz_spanset(t: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    t_converted = _ffi.cast("TimestampTz", t)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overbefore_timestamptz_spanset(t_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_bigint_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overleft_bigint_set(i_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_bigint_span(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overleft_bigint_span(i_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_bigint_spanset(i: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overleft_bigint_spanset(i_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_float_set(d: float, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overleft_float_set(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_float_span(d: float, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overleft_float_span(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_float_spanset(d: float, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overleft_float_spanset(d, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_int_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overleft_int_set(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_int_span(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overleft_int_span(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_int_spanset(i: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overleft_int_spanset(i, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_set_bigint(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.overleft_set_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_set_float(s: Annotated[cdata, "const Set *"], d: float) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overleft_set_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_set_int(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overleft_set_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_set_set(
    s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.overleft_set_set(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_set_text(s: Annotated[cdata, "const Set *"], txt: str) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    txt_converted = cstring2text(txt)
    result = _lib.overleft_set_text(s_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_span_bigint(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.overleft_span_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_span_float(s: Annotated[cdata, "const Span *"], d: float) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overleft_span_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_span_int(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overleft_span_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.overleft_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_span_spanset(
    s: Annotated[cdata, "const Span *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overleft_span_spanset(s_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_spanset_bigint(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    i_converted = _ffi.cast("int64", i)
    result = _lib.overleft_spanset_bigint(ss_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_spanset_float(ss: Annotated[cdata, "const SpanSet *"], d: float) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overleft_spanset_float(ss_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_spanset_int(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overleft_spanset_int(ss_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_spanset_span(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overleft_spanset_span(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_spanset_spanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.overleft_spanset_spanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_text_set(txt: str, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    txt_converted = cstring2text(txt)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overleft_text_set(txt_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_bigint_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overright_bigint_set(i_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_bigint_span(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overright_bigint_span(i_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_bigint_spanset(i: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overright_bigint_spanset(i_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_float_set(d: float, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overright_float_set(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_float_span(d: float, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overright_float_span(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_float_spanset(d: float, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overright_float_spanset(d, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_int_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overright_int_set(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_int_span(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overright_int_span(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_int_spanset(i: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overright_int_spanset(i, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_set_bigint(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.overright_set_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_set_float(s: Annotated[cdata, "const Set *"], d: float) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overright_set_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_set_int(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overright_set_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_set_set(
    s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.overright_set_set(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_set_text(s: Annotated[cdata, "const Set *"], txt: str) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    txt_converted = cstring2text(txt)
    result = _lib.overright_set_text(s_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_span_bigint(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.overright_span_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_span_float(s: Annotated[cdata, "const Span *"], d: float) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overright_span_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_span_int(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overright_span_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.overright_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_span_spanset(
    s: Annotated[cdata, "const Span *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overright_span_spanset(s_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_spanset_bigint(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    i_converted = _ffi.cast("int64", i)
    result = _lib.overright_spanset_bigint(ss_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_spanset_float(ss: Annotated[cdata, "const SpanSet *"], d: float) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overright_spanset_float(ss_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_spanset_int(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overright_spanset_int(ss_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_spanset_span(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overright_spanset_span(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_spanset_spanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.overright_spanset_spanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_text_set(txt: str, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    txt_converted = cstring2text(txt)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overright_text_set(txt_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_bigint_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.right_bigint_set(i_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_bigint_span(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.right_bigint_span(i_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_bigint_spanset(i: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    i_converted = _ffi.cast("int64", i)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.right_bigint_spanset(i_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_float_set(d: float, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.right_float_set(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_float_span(d: float, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.right_float_span(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_float_spanset(d: float, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.right_float_spanset(d, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_int_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.right_int_set(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_int_span(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.right_int_span(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_int_spanset(i: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.right_int_spanset(i, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_set_bigint(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.right_set_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_set_float(s: Annotated[cdata, "const Set *"], d: float) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.right_set_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def right_set_int(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.right_set_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def right_set_set(s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.right_set_set(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_set_text(s: Annotated[cdata, "const Set *"], txt: str) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    txt_converted = cstring2text(txt)
    result = _lib.right_set_text(s_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_span_bigint(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.right_span_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_span_float(s: Annotated[cdata, "const Span *"], d: float) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.right_span_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def right_span_int(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.right_span_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def right_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.right_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_span_spanset(
    s: Annotated[cdata, "const Span *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.right_span_spanset(s_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_spanset_bigint(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    i_converted = _ffi.cast("int64", i)
    result = _lib.right_spanset_bigint(ss_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_spanset_float(ss: Annotated[cdata, "const SpanSet *"], d: float) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.right_spanset_float(ss_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def right_spanset_int(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.right_spanset_int(ss_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def right_spanset_span(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.right_spanset_span(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_spanset_spanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.right_spanset_spanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_text_set(txt: str, s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    txt_converted = cstring2text(txt)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.right_text_set(txt_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_bigint_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    i_converted = _ffi.cast("int64", i)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intersection_bigint_set(i_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_date_set(d: int, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    d_converted = _ffi.cast("DateADT", d)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intersection_date_set(d_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_float_set(d: float, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intersection_float_set(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_int_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intersection_int_set(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_set_bigint(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.intersection_set_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_set_date(s: Annotated[cdata, "const Set *"], d: int) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.intersection_set_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_set_float(s: Annotated[cdata, "const Set *"], d: float) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intersection_set_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_set_int(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intersection_set_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_set_set(
    s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Set *"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.intersection_set_set(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_set_text(s: Annotated[cdata, "const Set *"], txt: str) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    txt_converted = cstring2text(txt)
    result = _lib.intersection_set_text(s_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_set_timestamptz(s: Annotated[cdata, "const Set *"], t: int) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.intersection_set_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_span_bigint(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.intersection_span_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_span_date(s: Annotated[cdata, "const Span *"], d: int) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.intersection_span_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_span_float(s: Annotated[cdata, "const Span *"], d: float) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.intersection_span_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_span_int(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.intersection_span_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "Span *"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.intersection_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_span_spanset(
    s: Annotated[cdata, "const Span *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.intersection_span_spanset(s_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_span_timestamptz(s: Annotated[cdata, "const Span *"], t: int) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.intersection_span_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_spanset_bigint(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    i_converted = _ffi.cast("int64", i)
    result = _lib.intersection_spanset_bigint(ss_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_spanset_date(ss: Annotated[cdata, "const SpanSet *"], d: int) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.intersection_spanset_date(ss_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_spanset_float(ss: Annotated[cdata, "const SpanSet *"], d: float) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.intersection_spanset_float(ss_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_spanset_int(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.intersection_spanset_int(ss_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_spanset_span(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.intersection_spanset_span(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_spanset_spanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "SpanSet *"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.intersection_spanset_spanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_spanset_timestamptz(ss: Annotated[cdata, "const SpanSet *"], t: int) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.intersection_spanset_timestamptz(ss_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_text_set(txt: str, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    txt_converted = cstring2text(txt)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intersection_text_set(txt_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_timestamptz_set(t: int, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intersection_timestamptz_set(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_bigint_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    i_converted = _ffi.cast("int64", i)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.minus_bigint_set(i_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_bigint_span(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "SpanSet *"]:
    i_converted = _ffi.cast("int64", i)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.minus_bigint_span(i_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_bigint_spanset(i: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    i_converted = _ffi.cast("int64", i)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.minus_bigint_spanset(i_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_date_set(d: int, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    d_converted = _ffi.cast("DateADT", d)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.minus_date_set(d_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_date_span(d: int, s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "SpanSet *"]:
    d_converted = _ffi.cast("DateADT", d)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.minus_date_span(d_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_date_spanset(d: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    d_converted = _ffi.cast("DateADT", d)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.minus_date_spanset(d_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_float_set(d: float, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.minus_float_set(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_float_span(d: float, s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.minus_float_span(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_float_spanset(d: float, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.minus_float_spanset(d, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_int_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.minus_int_set(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_int_span(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.minus_int_span(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_int_spanset(i: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.minus_int_spanset(i, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_set_bigint(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.minus_set_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_set_date(s: Annotated[cdata, "const Set *"], d: int) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.minus_set_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_set_float(s: Annotated[cdata, "const Set *"], d: float) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.minus_set_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_set_int(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.minus_set_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_set_set(
    s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Set *"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.minus_set_set(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_set_text(s: Annotated[cdata, "const Set *"], txt: str) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    txt_converted = cstring2text(txt)
    result = _lib.minus_set_text(s_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_set_timestamptz(s: Annotated[cdata, "const Set *"], t: int) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.minus_set_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_span_bigint(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.minus_span_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_span_date(s: Annotated[cdata, "const Span *"], d: int) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.minus_span_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_span_float(s: Annotated[cdata, "const Span *"], d: float) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.minus_span_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_span_int(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.minus_span_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "SpanSet *"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.minus_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_span_spanset(
    s: Annotated[cdata, "const Span *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.minus_span_spanset(s_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_span_timestamptz(s: Annotated[cdata, "const Span *"], t: int) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.minus_span_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_spanset_bigint(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    i_converted = _ffi.cast("int64", i)
    result = _lib.minus_spanset_bigint(ss_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_spanset_date(ss: Annotated[cdata, "const SpanSet *"], d: int) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.minus_spanset_date(ss_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_spanset_float(ss: Annotated[cdata, "const SpanSet *"], d: float) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.minus_spanset_float(ss_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_spanset_int(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.minus_spanset_int(ss_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_spanset_span(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.minus_spanset_span(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_spanset_spanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "SpanSet *"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.minus_spanset_spanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_spanset_timestamptz(ss: Annotated[cdata, "const SpanSet *"], t: int) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.minus_spanset_timestamptz(ss_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_text_set(txt: str, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    txt_converted = cstring2text(txt)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.minus_text_set(txt_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_timestamptz_set(t: int, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.minus_timestamptz_set(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_timestamptz_span(t: int, s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "SpanSet *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.minus_timestamptz_span(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_timestamptz_spanset(t: int, ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.minus_timestamptz_spanset(t_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_bigint_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    i_converted = _ffi.cast("int64", i)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.union_bigint_set(i_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_bigint_span(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.union_bigint_span(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_bigint_spanset(i: int, ss: Annotated[cdata, "SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    i_converted = _ffi.cast("int64", i)
    ss_converted = _ffi.cast("SpanSet *", ss)
    result = _lib.union_bigint_spanset(i_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_date_set(d: int, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    d_converted = _ffi.cast("DateADT", d)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.union_date_set(d_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_date_span(s: Annotated[cdata, "const Span *"], d: int) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.union_date_span(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_date_spanset(d: int, ss: Annotated[cdata, "SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    d_converted = _ffi.cast("DateADT", d)
    ss_converted = _ffi.cast("SpanSet *", ss)
    result = _lib.union_date_spanset(d_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_float_set(d: float, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.union_float_set(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_float_span(s: Annotated[cdata, "const Span *"], d: float) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.union_float_span(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def union_float_spanset(d: float, ss: Annotated[cdata, "SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("SpanSet *", ss)
    result = _lib.union_float_spanset(d, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_int_set(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.union_int_set(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_int_span(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.union_int_span(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_int_spanset(i: int, ss: Annotated[cdata, "SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("SpanSet *", ss)
    result = _lib.union_int_spanset(i, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_set_bigint(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.union_set_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_set_date(s: Annotated[cdata, "const Set *"], d: int) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.union_set_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_set_float(s: Annotated[cdata, "const Set *"], d: float) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.union_set_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def union_set_int(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.union_set_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def union_set_set(
    s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Set *"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.union_set_set(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_set_text(s: Annotated[cdata, "const Set *"], txt: str) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    txt_converted = cstring2text(txt)
    result = _lib.union_set_text(s_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_set_timestamptz(s: Annotated[cdata, "const Set *"], t: int) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.union_set_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_span_bigint(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.union_span_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_span_date(s: Annotated[cdata, "const Span *"], d: int) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.union_span_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_span_float(s: Annotated[cdata, "const Span *"], d: float) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.union_span_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def union_span_int(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.union_span_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def union_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "SpanSet *"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.union_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_span_spanset(
    s: Annotated[cdata, "const Span *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.union_span_spanset(s_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_span_timestamptz(s: Annotated[cdata, "const Span *"], t: int) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.union_span_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_spanset_bigint(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    i_converted = _ffi.cast("int64", i)
    result = _lib.union_spanset_bigint(ss_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_spanset_date(ss: Annotated[cdata, "const SpanSet *"], d: int) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.union_spanset_date(ss_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_spanset_float(ss: Annotated[cdata, "const SpanSet *"], d: float) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.union_spanset_float(ss_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def union_spanset_int(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.union_spanset_int(ss_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def union_spanset_span(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.union_spanset_span(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_spanset_spanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "SpanSet *"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.union_spanset_spanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_spanset_timestamptz(ss: Annotated[cdata, "const SpanSet *"], t: int) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.union_spanset_timestamptz(ss_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_text_set(txt: str, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    txt_converted = cstring2text(txt)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.union_text_set(txt_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_timestamptz_set(t: int, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.union_timestamptz_set(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_timestamptz_span(t: int, s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "SpanSet *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.union_timestamptz_span(t_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_timestamptz_spanset(t: int, ss: Annotated[cdata, "SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    ss_converted = _ffi.cast("SpanSet *", ss)
    result = _lib.union_timestamptz_spanset(t_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_bigintset_bigintset(
    s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]
) -> Annotated[int, "int64"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.distance_bigintset_bigintset(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_bigintspan_bigintspan(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[int, "int64"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.distance_bigintspan_bigintspan(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_bigintspanset_bigintspan(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[int, "int64"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.distance_bigintspanset_bigintspan(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_bigintspanset_bigintspanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[int, "int64"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.distance_bigintspanset_bigintspanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_dateset_dateset(
    s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]
) -> Annotated[int, "int"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.distance_dateset_dateset(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_datespan_datespan(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[int, "int"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.distance_datespan_datespan(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_datespanset_datespan(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[int, "int"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.distance_datespanset_datespan(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_datespanset_datespanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[int, "int"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.distance_datespanset_datespanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_floatset_floatset(
    s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]
) -> Annotated[float, "double"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.distance_floatset_floatset(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_floatspan_floatspan(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[float, "double"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.distance_floatspan_floatspan(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_floatspanset_floatspan(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[float, "double"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.distance_floatspanset_floatspan(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_floatspanset_floatspanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[float, "double"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.distance_floatspanset_floatspanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_intset_intset(
    s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]
) -> Annotated[int, "int"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.distance_intset_intset(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_intspan_intspan(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[int, "int"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.distance_intspan_intspan(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_intspanset_intspan(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[int, "int"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.distance_intspanset_intspan(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_intspanset_intspanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[int, "int"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.distance_intspanset_intspanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_set_bigint(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[int, "int64"]:
    s_converted = _ffi.cast("const Set *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.distance_set_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_set_date(s: Annotated[cdata, "const Set *"], d: int) -> Annotated[int, "int"]:
    s_converted = _ffi.cast("const Set *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.distance_set_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_set_float(s: Annotated[cdata, "const Set *"], d: float) -> Annotated[float, "double"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.distance_set_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_set_int(s: Annotated[cdata, "const Set *"], i: int) -> Annotated[int, "int"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.distance_set_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_set_timestamptz(s: Annotated[cdata, "const Set *"], t: int) -> Annotated[float, "double"]:
    s_converted = _ffi.cast("const Set *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.distance_set_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_span_bigint(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[int, "int64"]:
    s_converted = _ffi.cast("const Span *", s)
    i_converted = _ffi.cast("int64", i)
    result = _lib.distance_span_bigint(s_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_span_date(s: Annotated[cdata, "const Span *"], d: int) -> Annotated[int, "int"]:
    s_converted = _ffi.cast("const Span *", s)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.distance_span_date(s_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_span_float(s: Annotated[cdata, "const Span *"], d: float) -> Annotated[float, "double"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.distance_span_float(s_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_span_int(s: Annotated[cdata, "const Span *"], i: int) -> Annotated[int, "int"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.distance_span_int(s_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_span_timestamptz(s: Annotated[cdata, "const Span *"], t: int) -> Annotated[float, "double"]:
    s_converted = _ffi.cast("const Span *", s)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.distance_span_timestamptz(s_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_spanset_bigint(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[int, "int64"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    i_converted = _ffi.cast("int64", i)
    result = _lib.distance_spanset_bigint(ss_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_spanset_date(ss: Annotated[cdata, "const SpanSet *"], d: int) -> Annotated[int, "int"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.distance_spanset_date(ss_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_spanset_float(ss: Annotated[cdata, "const SpanSet *"], d: float) -> Annotated[float, "double"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.distance_spanset_float(ss_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_spanset_int(ss: Annotated[cdata, "const SpanSet *"], i: int) -> Annotated[int, "int"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.distance_spanset_int(ss_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_spanset_timestamptz(ss: Annotated[cdata, "const SpanSet *"], t: int) -> Annotated[float, "double"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.distance_spanset_timestamptz(ss_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_tstzset_tstzset(
    s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]
) -> Annotated[float, "double"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.distance_tstzset_tstzset(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_tstzspan_tstzspan(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[float, "double"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.distance_tstzspan_tstzspan(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_tstzspanset_tstzspan(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[float, "double"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.distance_tstzspanset_tstzspan(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_tstzspanset_tstzspanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[float, "double"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.distance_tstzspanset_tstzspanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigint_extent_transfn(state: Annotated[cdata, "Span *"], i: int) -> Annotated[cdata, "Span *"]:
    state_converted = _ffi.cast("Span *", state)
    i_converted = _ffi.cast("int64", i)
    result = _lib.bigint_extent_transfn(state_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigint_union_transfn(state: Annotated[cdata, "Set *"], i: int) -> Annotated[cdata, "Set *"]:
    state_converted = _ffi.cast("Set *", state)
    i_converted = _ffi.cast("int64", i)
    result = _lib.bigint_union_transfn(state_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def date_extent_transfn(state: Annotated[cdata, "Span *"], d: int) -> Annotated[cdata, "Span *"]:
    state_converted = _ffi.cast("Span *", state)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.date_extent_transfn(state_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def date_union_transfn(state: Annotated[cdata, "Set *"], d: int) -> Annotated[cdata, "Set *"]:
    state_converted = _ffi.cast("Set *", state)
    d_converted = _ffi.cast("DateADT", d)
    result = _lib.date_union_transfn(state_converted, d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def float_extent_transfn(state: Annotated[cdata, "Span *"], d: float) -> Annotated[cdata, "Span *"]:
    state_converted = _ffi.cast("Span *", state)
    result = _lib.float_extent_transfn(state_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def float_union_transfn(state: Annotated[cdata, "Set *"], d: float) -> Annotated[cdata, "Set *"]:
    state_converted = _ffi.cast("Set *", state)
    result = _lib.float_union_transfn(state_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def int_extent_transfn(state: Annotated[cdata, "Span *"], i: int) -> Annotated[cdata, "Span *"]:
    state_converted = _ffi.cast("Span *", state)
    result = _lib.int_extent_transfn(state_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def int_union_transfn(state: Annotated[cdata, "Set *"], i: int) -> Annotated[cdata, "Set *"]:
    state_converted = _ffi.cast("Set *", state)
    i_converted = _ffi.cast("int32", i)
    result = _lib.int_union_transfn(state_converted, i_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_extent_transfn(
    state: Annotated[cdata, "Span *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Span *"]:
    state_converted = _ffi.cast("Span *", state)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_extent_transfn(state_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_union_finalfn(state: Annotated[cdata, "Set *"]) -> Annotated[cdata, "Set *"]:
    state_converted = _ffi.cast("Set *", state)
    result = _lib.set_union_finalfn(state_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_union_transfn(state: Annotated[cdata, "Set *"], s: Annotated[cdata, "Set *"]) -> Annotated[cdata, "Set *"]:
    state_converted = _ffi.cast("Set *", state)
    s_converted = _ffi.cast("Set *", s)
    result = _lib.set_union_transfn(state_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_extent_transfn(
    state: Annotated[cdata, "Span *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "Span *"]:
    state_converted = _ffi.cast("Span *", state)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.span_extent_transfn(state_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_union_transfn(
    state: Annotated[cdata, "SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "SpanSet *"]:
    state_converted = _ffi.cast("SpanSet *", state)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.span_union_transfn(state_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_extent_transfn(
    state: Annotated[cdata, "Span *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "Span *"]:
    state_converted = _ffi.cast("Span *", state)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_extent_transfn(state_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_union_finalfn(state: Annotated[cdata, "SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    state_converted = _ffi.cast("SpanSet *", state)
    result = _lib.spanset_union_finalfn(state_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_union_transfn(
    state: Annotated[cdata, "SpanSet *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "SpanSet *"]:
    state_converted = _ffi.cast("SpanSet *", state)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_union_transfn(state_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def text_union_transfn(state: Annotated[cdata, "Set *"], txt: str) -> Annotated[cdata, "Set *"]:
    state_converted = _ffi.cast("Set *", state)
    txt_converted = cstring2text(txt)
    result = _lib.text_union_transfn(state_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timestamptz_extent_transfn(state: Annotated[cdata, "Span *"], t: int) -> Annotated[cdata, "Span *"]:
    state_converted = _ffi.cast("Span *", state)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.timestamptz_extent_transfn(state_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timestamptz_union_transfn(state: Annotated[cdata, "Set *"], t: int) -> Annotated[cdata, "Set *"]:
    state_converted = _ffi.cast("Set *", state)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.timestamptz_union_transfn(state_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigint_get_bin(value: int, vsize: int, vorigin: int) -> Annotated[int, "int64"]:
    value_converted = _ffi.cast("int64", value)
    vsize_converted = _ffi.cast("int64", vsize)
    vorigin_converted = _ffi.cast("int64", vorigin)
    result = _lib.bigint_get_bin(value_converted, vsize_converted, vorigin_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintspan_bins(
    s: Annotated[cdata, "const Span *"], vsize: int, vorigin: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    vsize_converted = _ffi.cast("int64", vsize)
    vorigin_converted = _ffi.cast("int64", vorigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.bigintspan_bins(s_converted, vsize_converted, vorigin_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bigintspanset_bins(
    ss: Annotated[cdata, "const SpanSet *"], vsize: int, vorigin: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    vsize_converted = _ffi.cast("int64", vsize)
    vorigin_converted = _ffi.cast("int64", vorigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.bigintspanset_bins(ss_converted, vsize_converted, vorigin_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def date_get_bin(d: int, duration: Annotated[cdata, "const Interval *"], torigin: int) -> Annotated[int, "DateADT"]:
    d_converted = _ffi.cast("DateADT", d)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("DateADT", torigin)
    result = _lib.date_get_bin(d_converted, duration_converted, torigin_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datespan_bins(
    s: Annotated[cdata, "const Span *"],
    duration: Annotated[cdata, "const Interval *"],
    torigin: int,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("DateADT", torigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.datespan_bins(s_converted, duration_converted, torigin_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datespanset_bins(
    ss: Annotated[cdata, "const SpanSet *"],
    duration: Annotated[cdata, "const Interval *"],
    torigin: int,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "Span *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("DateADT", torigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.datespanset_bins(ss_converted, duration_converted, torigin_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def float_get_bin(value: float, vsize: float, vorigin: float) -> Annotated[float, "double"]:
    result = _lib.float_get_bin(value, vsize, vorigin)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspan_bins(
    s: Annotated[cdata, "const Span *"], vsize: float, vorigin: float, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    count_converted = _ffi.cast("int *", count)
    result = _lib.floatspan_bins(s_converted, vsize, vorigin, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspanset_bins(
    ss: Annotated[cdata, "const SpanSet *"], vsize: float, vorigin: float, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    count_converted = _ffi.cast("int *", count)
    result = _lib.floatspanset_bins(ss_converted, vsize, vorigin, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def int_get_bin(value: int, vsize: int, vorigin: int) -> Annotated[int, "int"]:
    result = _lib.int_get_bin(value, vsize, vorigin)
    _check_error()
    return result if result != _ffi.NULL else None


def intspan_bins(
    s: Annotated[cdata, "const Span *"], vsize: int, vorigin: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    count_converted = _ffi.cast("int *", count)
    result = _lib.intspan_bins(s_converted, vsize, vorigin, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intspanset_bins(
    ss: Annotated[cdata, "const SpanSet *"], vsize: int, vorigin: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    count_converted = _ffi.cast("int *", count)
    result = _lib.intspanset_bins(ss_converted, vsize, vorigin, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timestamptz_get_bin(
    t: int, duration: Annotated[cdata, "const Interval *"], torigin: int
) -> Annotated[int, "TimestampTz"]:
    t_converted = _ffi.cast("TimestampTz", t)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    result = _lib.timestamptz_get_bin(t_converted, duration_converted, torigin_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspan_bins(
    s: Annotated[cdata, "const Span *"],
    duration: Annotated[cdata, "const Interval *"],
    origin: int,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    duration_converted = _ffi.cast("const Interval *", duration)
    origin_converted = _ffi.cast("TimestampTz", origin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tstzspan_bins(s_converted, duration_converted, origin_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspanset_bins(
    ss: Annotated[cdata, "const SpanSet *"],
    duration: Annotated[cdata, "const Interval *"],
    torigin: int,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "Span *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tstzspanset_bins(ss_converted, duration_converted, torigin_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_as_hexwkb(
    box: Annotated[cdata, "const TBox *"], variant: int
) -> tuple[Annotated[str, "char *"], Annotated[cdata, "size_t *"]]:
    box_converted = _ffi.cast("const TBox *", box)
    variant_converted = _ffi.cast("uint8_t", variant)
    size = _ffi.new("size_t *")
    result = _lib.tbox_as_hexwkb(box_converted, variant_converted, size)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None, size[0]


def tbox_as_wkb(
    box: Annotated[cdata, "const TBox *"], variant: int
) -> tuple[Annotated[cdata, "uint8_t *"], Annotated[cdata, "size_t *"]]:
    box_converted = _ffi.cast("const TBox *", box)
    variant_converted = _ffi.cast("uint8_t", variant)
    size_out = _ffi.new("size_t *")
    result = _lib.tbox_as_wkb(box_converted, variant_converted, size_out)
    _check_error()
    result_converted = bytes(result[i] for i in range(size_out[0])) if result != _ffi.NULL else None
    return result_converted


def tbox_from_hexwkb(hexwkb: str) -> Annotated[cdata, "TBox *"]:
    hexwkb_converted = hexwkb.encode("utf-8")
    result = _lib.tbox_from_hexwkb(hexwkb_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_from_wkb(wkb: bytes) -> "TBOX *":
    wkb_converted = _ffi.new("uint8_t []", wkb)
    result = _lib.tbox_from_wkb(wkb_converted, len(wkb))
    return result if result != _ffi.NULL else None


def tbox_in(string: str) -> Annotated[cdata, "TBox *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tbox_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_out(box: Annotated[cdata, "const TBox *"], maxdd: int) -> Annotated[str, "char *"]:
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.tbox_out(box_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def float_timestamptz_to_tbox(d: float, t: int) -> Annotated[cdata, "TBox *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.float_timestamptz_to_tbox(d, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def float_tstzspan_to_tbox(d: float, s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "TBox *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.float_tstzspan_to_tbox(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def int_timestamptz_to_tbox(i: int, t: int) -> Annotated[cdata, "TBox *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.int_timestamptz_to_tbox(i, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def int_tstzspan_to_tbox(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "TBox *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.int_tstzspan_to_tbox(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def numspan_tstzspan_to_tbox(
    span: Annotated[cdata, "const Span *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "TBox *"]:
    span_converted = _ffi.cast("const Span *", span)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.numspan_tstzspan_to_tbox(span_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def numspan_timestamptz_to_tbox(span: Annotated[cdata, "const Span *"], t: int) -> Annotated[cdata, "TBox *"]:
    span_converted = _ffi.cast("const Span *", span)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.numspan_timestamptz_to_tbox(span_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_copy(box: Annotated[cdata, "const TBox *"]) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.tbox_copy(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_make(
    s: Annotated[cdata, "const Span *"] | None, p: Annotated[cdata, "const Span *"] | None
) -> Annotated[cdata, "TBox *"]:
    s_converted = _ffi.cast("const Span *", s) if s is not None else _ffi.NULL
    p_converted = _ffi.cast("const Span *", p) if p is not None else _ffi.NULL
    result = _lib.tbox_make(s_converted, p_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def float_to_tbox(d: float) -> Annotated[cdata, "TBox *"]:
    result = _lib.float_to_tbox(d)
    _check_error()
    return result if result != _ffi.NULL else None


def int_to_tbox(i: int) -> Annotated[cdata, "TBox *"]:
    result = _lib.int_to_tbox(i)
    _check_error()
    return result if result != _ffi.NULL else None


def set_to_tbox(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "TBox *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_to_tbox(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_to_tbox(s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "TBox *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.span_to_tbox(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_to_tbox(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "TBox *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_to_tbox(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_to_intspan(box: Annotated[cdata, "const TBox *"]) -> Annotated[cdata, "Span *"]:
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.tbox_to_intspan(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_to_floatspan(box: Annotated[cdata, "const TBox *"]) -> Annotated[cdata, "Span *"]:
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.tbox_to_floatspan(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_to_tstzspan(box: Annotated[cdata, "const TBox *"]) -> Annotated[cdata, "Span *"]:
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.tbox_to_tstzspan(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timestamptz_to_tbox(t: int) -> Annotated[cdata, "TBox *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.timestamptz_to_tbox(t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_hast(box: Annotated[cdata, "const TBox *"]) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.tbox_hast(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_hasx(box: Annotated[cdata, "const TBox *"]) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.tbox_hasx(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_tmax(box: Annotated[cdata, "const TBox *"]) -> int:
    box_converted = _ffi.cast("const TBox *", box)
    out_result = _ffi.new("TimestampTz *")
    result = _lib.tbox_tmax(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tbox_tmax_inc(box: Annotated[cdata, "const TBox *"]) -> Annotated[cdata, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    out_result = _ffi.new("bool *")
    result = _lib.tbox_tmax_inc(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tbox_tmin(box: Annotated[cdata, "const TBox *"]) -> int:
    box_converted = _ffi.cast("const TBox *", box)
    out_result = _ffi.new("TimestampTz *")
    result = _lib.tbox_tmin(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tbox_tmin_inc(box: Annotated[cdata, "const TBox *"]) -> Annotated[cdata, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    out_result = _ffi.new("bool *")
    result = _lib.tbox_tmin_inc(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tbox_xmax(box: Annotated[cdata, "const TBox *"]) -> Annotated[cdata, "double"]:
    box_converted = _ffi.cast("const TBox *", box)
    out_result = _ffi.new("double *")
    result = _lib.tbox_xmax(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tbox_xmax_inc(box: Annotated[cdata, "const TBox *"]) -> Annotated[cdata, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    out_result = _ffi.new("bool *")
    result = _lib.tbox_xmax_inc(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tbox_xmin(box: Annotated[cdata, "const TBox *"]) -> Annotated[cdata, "double"]:
    box_converted = _ffi.cast("const TBox *", box)
    out_result = _ffi.new("double *")
    result = _lib.tbox_xmin(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tbox_xmin_inc(box: Annotated[cdata, "const TBox *"]) -> Annotated[cdata, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    out_result = _ffi.new("bool *")
    result = _lib.tbox_xmin_inc(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tboxfloat_xmax(box: Annotated[cdata, "const TBox *"]) -> Annotated[cdata, "double"]:
    box_converted = _ffi.cast("const TBox *", box)
    out_result = _ffi.new("double *")
    result = _lib.tboxfloat_xmax(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tboxfloat_xmin(box: Annotated[cdata, "const TBox *"]) -> Annotated[cdata, "double"]:
    box_converted = _ffi.cast("const TBox *", box)
    out_result = _ffi.new("double *")
    result = _lib.tboxfloat_xmin(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tboxint_xmax(box: Annotated[cdata, "const TBox *"]) -> Annotated[cdata, "int"]:
    box_converted = _ffi.cast("const TBox *", box)
    out_result = _ffi.new("int *")
    result = _lib.tboxint_xmax(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tboxint_xmin(box: Annotated[cdata, "const TBox *"]) -> Annotated[cdata, "int"]:
    box_converted = _ffi.cast("const TBox *", box)
    out_result = _ffi.new("int *")
    result = _lib.tboxint_xmin(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tbox_expand_float(box: Annotated[cdata, "const TBox *"], d: float) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.tbox_expand_float(box_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_expand_int(box: Annotated[cdata, "const TBox *"], i: int) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.tbox_expand_int(box_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_expand_time(
    box: Annotated[cdata, "const TBox *"], interv: Annotated[cdata, "const Interval *"]
) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("const TBox *", box)
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.tbox_expand_time(box_converted, interv_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_round(box: Annotated[cdata, "const TBox *"], maxdd: int) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.tbox_round(box_converted, maxdd)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_shift_scale_float(
    box: Annotated[cdata, "const TBox *"], shift: float, width: float, hasshift: bool, haswidth: bool
) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.tbox_shift_scale_float(box_converted, shift, width, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_shift_scale_int(
    box: Annotated[cdata, "const TBox *"], shift: int, width: int, hasshift: bool, haswidth: bool
) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.tbox_shift_scale_int(box_converted, shift, width, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_shift_scale_time(
    box: Annotated[cdata, "const TBox *"],
    shift: Annotated[cdata, "const Interval *"] | None,
    duration: Annotated[cdata, "const Interval *"] | None,
) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("const TBox *", box)
    shift_converted = _ffi.cast("const Interval *", shift) if shift is not None else _ffi.NULL
    duration_converted = _ffi.cast("const Interval *", duration) if duration is not None else _ffi.NULL
    result = _lib.tbox_shift_scale_time(box_converted, shift_converted, duration_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"], strict: bool
) -> Annotated[cdata, "TBox *"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.union_tbox_tbox(box1_converted, box2_converted, strict)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[cdata, "TBox *"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.intersection_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.adjacent_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.contained_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.contains_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.overlaps_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def same_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.same_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.after_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.before_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.left_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.overafter_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.overbefore_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.overleft_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.overright_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.right_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_cmp(box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]) -> Annotated[int, "int"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.tbox_cmp(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_eq(box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.tbox_eq(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_ge(box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.tbox_ge(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_gt(box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.tbox_gt(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_le(box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.tbox_le(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_lt(box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.tbox_lt(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_ne(box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.tbox_ne(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbool_from_mfjson(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tbool_from_mfjson(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbool_in(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tbool_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbool_out(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[str, "char *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tbool_out(temp_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def temporal_as_hexwkb(
    temp: Annotated[cdata, "const Temporal *"], variant: int
) -> tuple[Annotated[str, "char *"], Annotated[cdata, "size_t *"]]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    variant_converted = _ffi.cast("uint8_t", variant)
    size_out = _ffi.new("size_t *")
    result = _lib.temporal_as_hexwkb(temp_converted, variant_converted, size_out)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None, size_out[0]


def temporal_as_mfjson(
    temp: Annotated[cdata, "const Temporal *"], with_bbox: bool, flags: int, precision: int, srs: str | None
) -> Annotated[str, "char *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    srs_converted = srs.encode("utf-8") if srs is not None else _ffi.NULL
    result = _lib.temporal_as_mfjson(temp_converted, with_bbox, flags, precision, srs_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def temporal_as_wkb(
    temp: Annotated[cdata, "const Temporal *"], variant: int
) -> tuple[Annotated[cdata, "uint8_t *"], Annotated[cdata, "size_t *"]]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    variant_converted = _ffi.cast("uint8_t", variant)
    size_out = _ffi.new("size_t *")
    result = _lib.temporal_as_wkb(temp_converted, variant_converted, size_out)
    _check_error()
    result_converted = bytes(result[i] for i in range(size_out[0])) if result != _ffi.NULL else None
    return result_converted


def temporal_from_hexwkb(hexwkb: str) -> Annotated[cdata, "Temporal *"]:
    hexwkb_converted = hexwkb.encode("utf-8")
    result = _lib.temporal_from_hexwkb(hexwkb_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_from_wkb(wkb: bytes) -> "Temporal *":
    wkb_converted = _ffi.new("uint8_t []", wkb)
    result = _lib.temporal_from_wkb(wkb_converted, len(wkb))
    return result if result != _ffi.NULL else None


def tfloat_from_mfjson(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tfloat_from_mfjson(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_in(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tfloat_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_out(temp: Annotated[cdata, "const Temporal *"], maxdd: int) -> Annotated[str, "char *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_out(temp_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def tint_from_mfjson(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tint_from_mfjson(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_in(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tint_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_out(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[str, "char *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_out(temp_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def ttext_from_mfjson(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.ttext_from_mfjson(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttext_in(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.ttext_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttext_out(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[str, "char *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ttext_out(temp_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def tbool_from_base_temp(b: bool, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tbool_from_base_temp(b, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tboolinst_make(b: bool, t: int) -> Annotated[cdata, "TInstant *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.tboolinst_make(b, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tboolseq_from_base_tstzset(b: bool, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "TSequence *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tboolseq_from_base_tstzset(b, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tboolseq_from_base_tstzspan(b: bool, s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "TSequence *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tboolseq_from_base_tstzspan(b, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tboolseqset_from_base_tstzspanset(
    b: bool, ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tboolseqset_from_base_tstzspanset(b, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_copy(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_copy(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_from_base_temp(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_from_base_temp(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloatinst_make(d: float, t: int) -> Annotated[cdata, "TInstant *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.tfloatinst_make(d, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloatseq_from_base_tstzset(d: float, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "TSequence *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tfloatseq_from_base_tstzset(d, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloatseq_from_base_tstzspan(
    d: float, s: Annotated[cdata, "const Span *"], interp: InterpolationType
) -> Annotated[cdata, "TSequence *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tfloatseq_from_base_tstzspan(d, s_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloatseqset_from_base_tstzspanset(
    d: float, ss: Annotated[cdata, "const SpanSet *"], interp: InterpolationType
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tfloatseqset_from_base_tstzspanset(d, ss_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_from_base_temp(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_from_base_temp(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tintinst_make(i: int, t: int) -> Annotated[cdata, "TInstant *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.tintinst_make(i, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tintseq_from_base_tstzset(i: int, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "TSequence *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tintseq_from_base_tstzset(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tintseq_from_base_tstzspan(i: int, s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "TSequence *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tintseq_from_base_tstzspan(i, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tintseqset_from_base_tstzspanset(
    i: int, ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tintseqset_from_base_tstzspanset(i, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_make(
    instants: Annotated[list, "const TInstant **"],
    count: int,
    lower_inc: bool,
    upper_inc: bool,
    interp: InterpolationType,
    normalize: bool,
) -> Annotated[cdata, "TSequence *"]:
    instants_converted = [_ffi.cast("const TInstant *", x) for x in instants]
    result = _lib.tsequence_make(instants_converted, count, lower_inc, upper_inc, interp, normalize)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_make(
    sequences: Annotated[list, "const TSequence **"], count: int, normalize: bool
) -> Annotated[cdata, "TSequenceSet *"]:
    sequences_converted = [_ffi.cast("const TSequence *", x) for x in sequences]
    result = _lib.tsequenceset_make(sequences_converted, count, normalize)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_make_gaps(
    instants: Annotated[list, "const TInstant **"],
    interp: InterpolationType,
    maxt: Annotated[cdata, "const Interval *"] | None,
    maxdist: float,
) -> Annotated[cdata, "TSequenceSet *"]:
    instants_converted = [_ffi.cast("const TInstant *", x) for x in instants]
    maxt_converted = _ffi.cast("const Interval *", maxt) if maxt is not None else _ffi.NULL
    result = _lib.tsequenceset_make_gaps(instants_converted, len(instants), interp, maxt_converted, maxdist)
    _check_error()
    return result if result != _ffi.NULL else None


def ttext_from_base_temp(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ttext_from_base_temp(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttextinst_make(txt: str, t: int) -> Annotated[cdata, "TInstant *"]:
    txt_converted = cstring2text(txt)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.ttextinst_make(txt_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttextseq_from_base_tstzset(txt: str, s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "TSequence *"]:
    txt_converted = cstring2text(txt)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.ttextseq_from_base_tstzset(txt_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttextseq_from_base_tstzspan(txt: str, s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "TSequence *"]:
    txt_converted = cstring2text(txt)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.ttextseq_from_base_tstzspan(txt_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttextseqset_from_base_tstzspanset(
    txt: str, ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "TSequenceSet *"]:
    txt_converted = cstring2text(txt)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.ttextseqset_from_base_tstzspanset(txt_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbool_to_tint(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tbool_to_tint(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_to_tstzspan(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Span *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_to_tstzspan(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_to_tint(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_to_tint(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_to_tfloat(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_to_tfloat(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_to_span(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Span *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnumber_to_span(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_to_tbox(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "TBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnumber_to_tbox(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbool_end_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tbool_end_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbool_start_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tbool_start_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbool_value_at_timestamptz(
    temp: Annotated[cdata, "const Temporal *"], t: int, strict: bool
) -> Annotated[cdata, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    t_converted = _ffi.cast("TimestampTz", t)
    out_result = _ffi.new("bool *")
    result = _lib.tbool_value_at_timestamptz(temp_converted, t_converted, strict, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tbool_value_n(temp: Annotated[cdata, "const Temporal *"], n: int) -> Annotated[cdata, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    out_result = _ffi.new("bool *")
    result = _lib.tbool_value_n(temp_converted, n, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tbool_values(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "bool *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tbool_values(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_duration(temp: Annotated[cdata, "const Temporal *"], boundspan: bool) -> Annotated[cdata, "Interval *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_duration(temp_converted, boundspan)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_end_instant(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "TInstant *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_end_instant(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_end_sequence(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "TSequence *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_end_sequence(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_end_timestamptz(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "TimestampTz"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_end_timestamptz(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_hash(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "uint32"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_hash(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_instant_n(temp: Annotated[cdata, "const Temporal *"], n: int) -> Annotated[cdata, "TInstant *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_instant_n(temp_converted, n)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_instants(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "TInstant **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.temporal_instants(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_interp(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[str, "const char *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_interp(temp_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def temporal_lower_inc(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_lower_inc(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_max_instant(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "TInstant *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_max_instant(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_min_instant(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "TInstant *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_min_instant(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_num_instants(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_num_instants(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_num_sequences(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_num_sequences(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_num_timestamps(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_num_timestamps(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_segments(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "TSequence **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.temporal_segments(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_sequence_n(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[cdata, "TSequence *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_sequence_n(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_sequences(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "TSequence **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.temporal_sequences(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_start_instant(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "TInstant *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_start_instant(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_start_sequence(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "TSequence *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_start_sequence(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_start_timestamptz(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "TimestampTz"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_start_timestamptz(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_stops(
    temp: Annotated[cdata, "const Temporal *"], maxdist: float, minduration: Annotated[cdata, "const Interval *"]
) -> Annotated[cdata, "TSequenceSet *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    minduration_converted = _ffi.cast("const Interval *", minduration)
    result = _lib.temporal_stops(temp_converted, maxdist, minduration_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_subtype(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[str, "const char *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_subtype(temp_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def temporal_time(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "SpanSet *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_time(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_timestamps(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[int, "TimestampTz *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.temporal_timestamps(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_timestamptz_n(temp: Annotated[cdata, "const Temporal *"], n: int) -> int:
    temp_converted = _ffi.cast("const Temporal *", temp)
    out_result = _ffi.new("TimestampTz *")
    result = _lib.temporal_timestamptz_n(temp_converted, n, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def temporal_upper_inc(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_upper_inc(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_end_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_end_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_max_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_max_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_min_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_min_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_start_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_start_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_value_at_timestamptz(
    temp: Annotated[cdata, "const Temporal *"], t: int, strict: bool
) -> Annotated[cdata, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    t_converted = _ffi.cast("TimestampTz", t)
    out_result = _ffi.new("double *")
    result = _lib.tfloat_value_at_timestamptz(temp_converted, t_converted, strict, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tfloat_value_n(temp: Annotated[cdata, "const Temporal *"], n: int) -> Annotated[cdata, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    out_result = _ffi.new("double *")
    result = _lib.tfloat_value_n(temp_converted, n, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tfloat_values(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "double *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tfloat_values(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_end_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_end_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_max_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_max_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_min_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_min_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_start_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_start_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_value_at_timestamptz(
    temp: Annotated[cdata, "const Temporal *"], t: int, strict: bool
) -> Annotated[cdata, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    t_converted = _ffi.cast("TimestampTz", t)
    out_result = _ffi.new("int *")
    result = _lib.tint_value_at_timestamptz(temp_converted, t_converted, strict, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tint_value_n(temp: Annotated[cdata, "const Temporal *"], n: int) -> Annotated[cdata, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    out_result = _ffi.new("int *")
    result = _lib.tint_value_n(temp_converted, n, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tint_values(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "int *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tint_values(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_integral(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnumber_integral(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_twavg(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnumber_twavg(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_valuespans(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "SpanSet *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnumber_valuespans(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttext_end_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[str, "text *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ttext_end_value(temp_converted)
    _check_error()
    result = text2cstring(result)
    return result if result != _ffi.NULL else None


def ttext_max_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[str, "text *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ttext_max_value(temp_converted)
    _check_error()
    result = text2cstring(result)
    return result if result != _ffi.NULL else None


def ttext_min_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[str, "text *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ttext_min_value(temp_converted)
    _check_error()
    result = text2cstring(result)
    return result if result != _ffi.NULL else None


def ttext_start_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[str, "text *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ttext_start_value(temp_converted)
    _check_error()
    result = text2cstring(result)
    return result if result != _ffi.NULL else None


def ttext_value_at_timestamptz(
    temp: Annotated[cdata, "const Temporal *"], t: int, strict: bool
) -> Annotated[list, "text **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    t_converted = _ffi.cast("TimestampTz", t)
    out_result = _ffi.new("text **")
    result = _lib.ttext_value_at_timestamptz(temp_converted, t_converted, strict, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def ttext_value_n(temp: Annotated[cdata, "const Temporal *"], n: int) -> Annotated[list, "text **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    out_result = _ffi.new("text **")
    result = _lib.ttext_value_n(temp_converted, n, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def ttext_values(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "text **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.ttext_values(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def float_degrees(value: float, normalize: bool) -> Annotated[float, "double"]:
    result = _lib.float_degrees(value, normalize)
    _check_error()
    return result if result != _ffi.NULL else None


def temparr_round(
    temp: Annotated[list, "const Temporal **"], count: int, maxdd: int
) -> Annotated[cdata, "Temporal **"]:
    temp_converted = [_ffi.cast("const Temporal *", x) for x in temp]
    result = _lib.temparr_round(temp_converted, count, maxdd)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_round(temp: Annotated[cdata, "const Temporal *"], maxdd: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_round(temp_converted, maxdd)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_scale_time(
    temp: Annotated[cdata, "const Temporal *"], duration: Annotated[cdata, "const Interval *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    duration_converted = _ffi.cast("const Interval *", duration)
    result = _lib.temporal_scale_time(temp_converted, duration_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_set_interp(
    temp: Annotated[cdata, "const Temporal *"], interp: InterpolationType
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_set_interp(temp_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_shift_scale_time(
    temp: Annotated[cdata, "const Temporal *"],
    shift: Annotated[cdata, "const Interval *"] | None,
    duration: Annotated[cdata, "const Interval *"] | None,
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    shift_converted = _ffi.cast("const Interval *", shift) if shift is not None else _ffi.NULL
    duration_converted = _ffi.cast("const Interval *", duration) if duration is not None else _ffi.NULL
    result = _lib.temporal_shift_scale_time(temp_converted, shift_converted, duration_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_shift_time(
    temp: Annotated[cdata, "const Temporal *"], shift: Annotated[cdata, "const Interval *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    shift_converted = _ffi.cast("const Interval *", shift)
    result = _lib.temporal_shift_time(temp_converted, shift_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_to_tinstant(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "TInstant *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_to_tinstant(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_to_tsequence(
    temp: Annotated[cdata, "const Temporal *"], interp: InterpolationType
) -> Annotated[cdata, "TSequence *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_to_tsequence(temp_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_to_tsequenceset(
    temp: Annotated[cdata, "const Temporal *"], interp: InterpolationType
) -> Annotated[cdata, "TSequenceSet *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_to_tsequenceset(temp_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_ceil(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_ceil(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_degrees(temp: Annotated[cdata, "const Temporal *"], normalize: bool) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_degrees(temp_converted, normalize)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_floor(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_floor(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_radians(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_radians(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_scale_value(temp: Annotated[cdata, "const Temporal *"], width: float) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_scale_value(temp_converted, width)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_shift_scale_value(
    temp: Annotated[cdata, "const Temporal *"], shift: float, width: float
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_shift_scale_value(temp_converted, shift, width)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_shift_value(temp: Annotated[cdata, "const Temporal *"], shift: float) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_shift_value(temp_converted, shift)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_scale_value(temp: Annotated[cdata, "const Temporal *"], width: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_scale_value(temp_converted, width)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_shift_scale_value(
    temp: Annotated[cdata, "const Temporal *"], shift: int, width: int
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_shift_scale_value(temp_converted, shift, width)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_shift_value(temp: Annotated[cdata, "const Temporal *"], shift: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_shift_value(temp_converted, shift)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_append_tinstant(
    temp: Annotated[cdata, "Temporal *"],
    inst: Annotated[cdata, "const TInstant *"],
    interp: InterpolationType,
    maxdist: float,
    maxt: Annotated[cdata, "const Interval *"] | None,
    expand: bool,
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("Temporal *", temp)
    inst_converted = _ffi.cast("const TInstant *", inst)
    maxt_converted = _ffi.cast("const Interval *", maxt) if maxt is not None else _ffi.NULL
    result = _lib.temporal_append_tinstant(temp_converted, inst_converted, interp, maxdist, maxt_converted, expand)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_append_tsequence(
    temp: Annotated[cdata, "Temporal *"], seq: Annotated[cdata, "const TSequence *"], expand: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("Temporal *", temp)
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.temporal_append_tsequence(temp_converted, seq_converted, expand)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_delete_timestamptz(
    temp: Annotated[cdata, "const Temporal *"], t: int, connect: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.temporal_delete_timestamptz(temp_converted, t_converted, connect)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_delete_tstzset(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Set *"], connect: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.temporal_delete_tstzset(temp_converted, s_converted, connect)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_delete_tstzspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"], connect: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.temporal_delete_tstzspan(temp_converted, s_converted, connect)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_delete_tstzspanset(
    temp: Annotated[cdata, "const Temporal *"], ss: Annotated[cdata, "const SpanSet *"], connect: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.temporal_delete_tstzspanset(temp_converted, ss_converted, connect)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_insert(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"], connect: bool
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.temporal_insert(temp1_converted, temp2_converted, connect)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_merge(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.temporal_merge(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_merge_array(temparr: Annotated[list, "const Temporal **"], count: int) -> Annotated[cdata, "Temporal *"]:
    temparr_converted = [_ffi.cast("const Temporal *", x) for x in temparr]
    result = _lib.temporal_merge_array(temparr_converted, count)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_update(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"], connect: bool
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.temporal_update(temp1_converted, temp2_converted, connect)
    _check_error()
    return result if result != _ffi.NULL else None


def tbool_at_value(temp: Annotated[cdata, "const Temporal *"], b: bool) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tbool_at_value(temp_converted, b)
    _check_error()
    return result if result != _ffi.NULL else None


def tbool_minus_value(temp: Annotated[cdata, "const Temporal *"], b: bool) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tbool_minus_value(temp_converted, b)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_at_max(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_at_max(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_at_min(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_at_min(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_at_timestamptz(temp: Annotated[cdata, "const Temporal *"], t: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.temporal_at_timestamptz(temp_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_at_tstzset(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.temporal_at_tstzset(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_at_tstzspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.temporal_at_tstzspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_at_tstzspanset(
    temp: Annotated[cdata, "const Temporal *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.temporal_at_tstzspanset(temp_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_at_values(
    temp: Annotated[cdata, "const Temporal *"], set: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    set_converted = _ffi.cast("const Set *", set)
    result = _lib.temporal_at_values(temp_converted, set_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_minus_max(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_minus_max(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_minus_min(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_minus_min(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_minus_timestamptz(temp: Annotated[cdata, "const Temporal *"], t: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.temporal_minus_timestamptz(temp_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_minus_tstzset(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.temporal_minus_tstzset(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_minus_tstzspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.temporal_minus_tstzspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_minus_tstzspanset(
    temp: Annotated[cdata, "const Temporal *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.temporal_minus_tstzspanset(temp_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_minus_values(
    temp: Annotated[cdata, "const Temporal *"], set: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    set_converted = _ffi.cast("const Set *", set)
    result = _lib.temporal_minus_values(temp_converted, set_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_at_value(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_at_value(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_minus_value(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_minus_value(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_at_value(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_at_value(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_minus_value(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_minus_value(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_at_span(
    temp: Annotated[cdata, "const Temporal *"], span: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    span_converted = _ffi.cast("const Span *", span)
    result = _lib.tnumber_at_span(temp_converted, span_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_at_spanset(
    temp: Annotated[cdata, "const Temporal *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tnumber_at_spanset(temp_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_at_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.tnumber_at_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_minus_span(
    temp: Annotated[cdata, "const Temporal *"], span: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    span_converted = _ffi.cast("const Span *", span)
    result = _lib.tnumber_minus_span(temp_converted, span_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_minus_spanset(
    temp: Annotated[cdata, "const Temporal *"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tnumber_minus_spanset(temp_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_minus_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.tnumber_minus_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttext_at_value(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.ttext_at_value(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttext_minus_value(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.ttext_minus_value(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_cmp(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.temporal_cmp(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_eq(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.temporal_eq(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_ge(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.temporal_ge(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_gt(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.temporal_gt(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_le(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.temporal_le(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_lt(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.temporal_lt(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_ne(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.temporal_ne(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_bool_tbool(b: bool, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_eq_bool_tbool(b, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_eq_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_eq_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_tbool_bool(temp: Annotated[cdata, "const Temporal *"], b: bool) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_eq_tbool_bool(temp_converted, b)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.always_eq_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_eq_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_eq_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_eq_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.always_eq_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ge_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ge_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ge_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ge_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ge_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.always_ge_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ge_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ge_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ge_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ge_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ge_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ge_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ge_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.always_ge_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_gt_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_gt_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_gt_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_gt_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_gt_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.always_gt_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_gt_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_gt_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_gt_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_gt_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def always_gt_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_gt_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def always_gt_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.always_gt_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_le_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_le_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_le_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_le_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_le_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.always_le_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_le_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_le_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_le_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_le_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def always_le_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_le_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def always_le_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.always_le_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_lt_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_lt_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_lt_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_lt_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_lt_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.always_lt_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_lt_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_lt_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_lt_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_lt_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def always_lt_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_lt_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def always_lt_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.always_lt_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_bool_tbool(b: bool, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ne_bool_tbool(b, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ne_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ne_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_tbool_bool(temp: Annotated[cdata, "const Temporal *"], b: bool) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ne_tbool_bool(temp_converted, b)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.always_ne_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ne_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ne_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ne_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.always_ne_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_bool_tbool(b: bool, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_eq_bool_tbool(b, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_eq_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_eq_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_tbool_bool(temp: Annotated[cdata, "const Temporal *"], b: bool) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_eq_tbool_bool(temp_converted, b)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.ever_eq_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_eq_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_eq_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_eq_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.ever_eq_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ge_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ge_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ge_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ge_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ge_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.ever_ge_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ge_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ge_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ge_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ge_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ge_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ge_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ge_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.ever_ge_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_gt_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_gt_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_gt_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_gt_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_gt_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.ever_gt_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_gt_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_gt_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_gt_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_gt_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_gt_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_gt_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_gt_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.ever_gt_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_le_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_le_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_le_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_le_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_le_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.ever_le_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_le_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_le_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_le_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_le_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_le_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_le_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_le_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.ever_le_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_lt_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_lt_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_lt_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_lt_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_lt_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.ever_lt_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_lt_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_lt_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_lt_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_lt_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_lt_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_lt_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_lt_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.ever_lt_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_bool_tbool(b: bool, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ne_bool_tbool(b, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ne_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ne_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_tbool_bool(temp: Annotated[cdata, "const Temporal *"], b: bool) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ne_tbool_bool(temp_converted, b)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.ever_ne_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ne_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ne_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ne_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.ever_ne_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def teq_bool_tbool(b: bool, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.teq_bool_tbool(b, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def teq_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.teq_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def teq_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.teq_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def teq_tbool_bool(temp: Annotated[cdata, "const Temporal *"], b: bool) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.teq_tbool_bool(temp_converted, b)
    _check_error()
    return result if result != _ffi.NULL else None


def teq_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.teq_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def teq_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.teq_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def teq_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.teq_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def teq_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.teq_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def teq_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.teq_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tge_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tge_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tge_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tge_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tge_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tge_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tge_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tge_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tge_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tge_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def tge_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tge_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def tge_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.tge_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgt_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgt_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgt_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgt_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgt_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tgt_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgt_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgt_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgt_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgt_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def tgt_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgt_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def tgt_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.tgt_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tle_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tle_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tle_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tle_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tle_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tle_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tle_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tle_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tle_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tle_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def tle_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tle_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def tle_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.tle_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tlt_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tlt_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tlt_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tlt_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tlt_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tlt_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tlt_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tlt_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tlt_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tlt_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def tlt_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tlt_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def tlt_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.tlt_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tne_bool_tbool(b: bool, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tne_bool_tbool(b, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tne_float_tfloat(d: float, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tne_float_tfloat(d, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tne_int_tint(i: int, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tne_int_tint(i, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tne_tbool_bool(temp: Annotated[cdata, "const Temporal *"], b: bool) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tne_tbool_bool(temp_converted, b)
    _check_error()
    return result if result != _ffi.NULL else None


def tne_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tne_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tne_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tne_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tne_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tne_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def tne_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tne_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def tne_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.tne_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_spans(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.temporal_spans(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_split_each_n_spans(
    temp: Annotated[cdata, "const Temporal *"], elem_count: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.temporal_split_each_n_spans(temp_converted, elem_count, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_split_n_spans(
    temp: Annotated[cdata, "const Temporal *"], span_count: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.temporal_split_n_spans(temp_converted, span_count, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_split_each_n_tboxes(
    temp: Annotated[cdata, "const Temporal *"], elem_count: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "TBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tnumber_split_each_n_tboxes(temp_converted, elem_count, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_split_n_tboxes(
    temp: Annotated[cdata, "const Temporal *"], box_count: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "TBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tnumber_split_n_tboxes(temp_converted, box_count, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_tboxes(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "TBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tnumber_tboxes(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_numspan_tnumber(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.adjacent_numspan_tnumber(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_tbox_tnumber(
    box: Annotated[cdata, "const TBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.adjacent_tbox_tnumber(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.adjacent_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_temporal_tstzspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.adjacent_temporal_tstzspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_tnumber_numspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.adjacent_tnumber_numspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_tnumber_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.adjacent_tnumber_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.adjacent_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_tstzspan_temporal(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.adjacent_tstzspan_temporal(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_numspan_tnumber(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.contained_numspan_tnumber(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_tbox_tnumber(
    box: Annotated[cdata, "const TBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.contained_tbox_tnumber(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.contained_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_temporal_tstzspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.contained_temporal_tstzspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_tnumber_numspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.contained_tnumber_numspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_tnumber_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.contained_tnumber_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.contained_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_tstzspan_temporal(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.contained_tstzspan_temporal(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_numspan_tnumber(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.contains_numspan_tnumber(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_tbox_tnumber(
    box: Annotated[cdata, "const TBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.contains_tbox_tnumber(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_temporal_tstzspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.contains_temporal_tstzspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.contains_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_tnumber_numspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.contains_tnumber_numspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_tnumber_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.contains_tnumber_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.contains_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_tstzspan_temporal(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.contains_tstzspan_temporal(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_numspan_tnumber(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overlaps_numspan_tnumber(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_tbox_tnumber(
    box: Annotated[cdata, "const TBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overlaps_tbox_tnumber(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overlaps_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_temporal_tstzspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overlaps_temporal_tstzspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_tnumber_numspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overlaps_tnumber_numspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_tnumber_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.overlaps_tnumber_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overlaps_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_tstzspan_temporal(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overlaps_tstzspan_temporal(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def same_numspan_tnumber(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.same_numspan_tnumber(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def same_tbox_tnumber(
    box: Annotated[cdata, "const TBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.same_tbox_tnumber(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def same_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.same_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def same_temporal_tstzspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.same_temporal_tstzspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def same_tnumber_numspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.same_tnumber_numspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def same_tnumber_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.same_tnumber_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def same_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.same_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def same_tstzspan_temporal(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.same_tstzspan_temporal(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_tbox_tnumber(
    box: Annotated[cdata, "const TBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.after_tbox_tnumber(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_temporal_tstzspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.after_temporal_tstzspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.after_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_tnumber_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.after_tnumber_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.after_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_tstzspan_temporal(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.after_tstzspan_temporal(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_tbox_tnumber(
    box: Annotated[cdata, "const TBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.before_tbox_tnumber(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_temporal_tstzspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.before_temporal_tstzspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.before_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_tnumber_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.before_tnumber_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.before_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_tstzspan_temporal(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.before_tstzspan_temporal(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_tbox_tnumber(
    box: Annotated[cdata, "const TBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.left_tbox_tnumber(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_numspan_tnumber(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.left_numspan_tnumber(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_tnumber_numspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.left_tnumber_numspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_tnumber_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.left_tnumber_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.left_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_tbox_tnumber(
    box: Annotated[cdata, "const TBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overafter_tbox_tnumber(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_temporal_tstzspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overafter_temporal_tstzspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overafter_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_tnumber_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.overafter_tnumber_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overafter_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_tstzspan_temporal(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overafter_tstzspan_temporal(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_tbox_tnumber(
    box: Annotated[cdata, "const TBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overbefore_tbox_tnumber(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_temporal_tstzspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overbefore_temporal_tstzspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_temporal_temporal(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overbefore_temporal_temporal(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_tnumber_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.overbefore_tnumber_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overbefore_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_tstzspan_temporal(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overbefore_tstzspan_temporal(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_numspan_tnumber(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overleft_numspan_tnumber(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_tbox_tnumber(
    box: Annotated[cdata, "const TBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overleft_tbox_tnumber(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_tnumber_numspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overleft_tnumber_numspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_tnumber_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.overleft_tnumber_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overleft_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_numspan_tnumber(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overright_numspan_tnumber(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_tbox_tnumber(
    box: Annotated[cdata, "const TBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overright_tbox_tnumber(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_tnumber_numspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overright_tnumber_numspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_tnumber_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.overright_tnumber_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overright_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_numspan_tnumber(
    s: Annotated[cdata, "const Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.right_numspan_tnumber(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_tbox_tnumber(
    box: Annotated[cdata, "const TBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const TBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.right_tbox_tnumber(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_tnumber_numspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.right_tnumber_numspan(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_tnumber_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.right_tnumber_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.right_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tand_bool_tbool(b: bool, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tand_bool_tbool(b, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tand_tbool_bool(temp: Annotated[cdata, "const Temporal *"], b: bool) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tand_tbool_bool(temp_converted, b)
    _check_error()
    return result if result != _ffi.NULL else None


def tand_tbool_tbool(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tand_tbool_tbool(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbool_when_true(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "SpanSet *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tbool_when_true(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnot_tbool(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnot_tbool(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tor_bool_tbool(b: bool, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tor_bool_tbool(b, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tor_tbool_bool(temp: Annotated[cdata, "const Temporal *"], b: bool) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tor_tbool_bool(temp_converted, b)
    _check_error()
    return result if result != _ffi.NULL else None


def tor_tbool_tbool(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tor_tbool_tbool(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def add_float_tfloat(d: float, tnumber: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.add_float_tfloat(d, tnumber_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def add_int_tint(i: int, tnumber: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.add_int_tint(i, tnumber_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def add_tfloat_float(tnumber: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.add_tfloat_float(tnumber_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def add_tint_int(tnumber: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.add_tint_int(tnumber_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def add_tnumber_tnumber(
    tnumber1: Annotated[cdata, "const Temporal *"], tnumber2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    tnumber1_converted = _ffi.cast("const Temporal *", tnumber1)
    tnumber2_converted = _ffi.cast("const Temporal *", tnumber2)
    result = _lib.add_tnumber_tnumber(tnumber1_converted, tnumber2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def div_float_tfloat(d: float, tnumber: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.div_float_tfloat(d, tnumber_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def div_int_tint(i: int, tnumber: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.div_int_tint(i, tnumber_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def div_tfloat_float(tnumber: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.div_tfloat_float(tnumber_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def div_tint_int(tnumber: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.div_tint_int(tnumber_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def div_tnumber_tnumber(
    tnumber1: Annotated[cdata, "const Temporal *"], tnumber2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    tnumber1_converted = _ffi.cast("const Temporal *", tnumber1)
    tnumber2_converted = _ffi.cast("const Temporal *", tnumber2)
    result = _lib.div_tnumber_tnumber(tnumber1_converted, tnumber2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def mult_float_tfloat(d: float, tnumber: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.mult_float_tfloat(d, tnumber_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def mult_int_tint(i: int, tnumber: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.mult_int_tint(i, tnumber_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def mult_tfloat_float(tnumber: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.mult_tfloat_float(tnumber_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def mult_tint_int(tnumber: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.mult_tint_int(tnumber_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def mult_tnumber_tnumber(
    tnumber1: Annotated[cdata, "const Temporal *"], tnumber2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    tnumber1_converted = _ffi.cast("const Temporal *", tnumber1)
    tnumber2_converted = _ffi.cast("const Temporal *", tnumber2)
    result = _lib.mult_tnumber_tnumber(tnumber1_converted, tnumber2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def sub_float_tfloat(d: float, tnumber: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.sub_float_tfloat(d, tnumber_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def sub_int_tint(i: int, tnumber: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.sub_int_tint(i, tnumber_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def sub_tfloat_float(tnumber: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.sub_tfloat_float(tnumber_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def sub_tint_int(tnumber: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[cdata, "Temporal *"]:
    tnumber_converted = _ffi.cast("const Temporal *", tnumber)
    result = _lib.sub_tint_int(tnumber_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def sub_tnumber_tnumber(
    tnumber1: Annotated[cdata, "const Temporal *"], tnumber2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    tnumber1_converted = _ffi.cast("const Temporal *", tnumber1)
    tnumber2_converted = _ffi.cast("const Temporal *", tnumber2)
    result = _lib.sub_tnumber_tnumber(tnumber1_converted, tnumber2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_derivative(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_derivative(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_exp(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_exp(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_ln(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_ln(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_log10(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_log10(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_abs(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnumber_abs(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def float_angular_difference(degrees1: float, degrees2: float) -> Annotated[float, "double"]:
    result = _lib.float_angular_difference(degrees1, degrees2)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_angular_difference(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnumber_angular_difference(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_delta_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnumber_delta_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def textcat_text_ttext(txt: str, temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    txt_converted = cstring2text(txt)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.textcat_text_ttext(txt_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def textcat_ttext_text(temp: Annotated[cdata, "const Temporal *"], txt: str) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    txt_converted = cstring2text(txt)
    result = _lib.textcat_ttext_text(temp_converted, txt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def textcat_ttext_ttext(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.textcat_ttext_ttext(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttext_initcap(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ttext_initcap(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttext_upper(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ttext_upper(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttext_lower(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ttext_lower(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tdistance_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tdistance_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def tdistance_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tdistance_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def tdistance_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tdistance_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tboxfloat_tboxfloat(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[float, "double"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.nad_tboxfloat_tboxfloat(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tboxint_tboxint(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[int, "int"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.nad_tboxint_tboxint(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tfloat_float(temp: Annotated[cdata, "const Temporal *"], d: float) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.nad_tfloat_float(temp_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tfloat_tfloat(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[float, "double"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.nad_tfloat_tfloat(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tfloat_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.nad_tfloat_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tint_int(temp: Annotated[cdata, "const Temporal *"], i: int) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.nad_tint_int(temp_converted, i)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tint_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.nad_tint_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tint_tint(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.nad_tint_tint(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbool_tand_transfn(
    state: Annotated[cdata, "SkipList *"] | None, temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tbool_tand_transfn(state_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbool_tor_transfn(
    state: Annotated[cdata, "SkipList *"] | None, temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tbool_tor_transfn(state_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_extent_transfn(
    s: Annotated[cdata, "Span *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("Span *", s)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_extent_transfn(s_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_tagg_finalfn(state: Annotated[cdata, "SkipList *"]) -> Annotated[cdata, "Temporal *"]:
    state_converted = _ffi.cast("SkipList *", state)
    result = _lib.temporal_tagg_finalfn(state_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_tcount_transfn(
    state: Annotated[cdata, "SkipList *"] | None, temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_tcount_transfn(state_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_tmax_transfn(
    state: Annotated[cdata, "SkipList *"] | None, temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_tmax_transfn(state_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_tmin_transfn(
    state: Annotated[cdata, "SkipList *"] | None, temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_tmin_transfn(state_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_tsum_transfn(
    state: Annotated[cdata, "SkipList *"] | None, temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tfloat_tsum_transfn(state_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_wmax_transfn(
    state: Annotated[cdata, "SkipList *"],
    temp: Annotated[cdata, "const Temporal *"],
    interv: Annotated[cdata, "const Interval *"],
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state)
    temp_converted = _ffi.cast("const Temporal *", temp)
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.tfloat_wmax_transfn(state_converted, temp_converted, interv_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_wmin_transfn(
    state: Annotated[cdata, "SkipList *"],
    temp: Annotated[cdata, "const Temporal *"],
    interv: Annotated[cdata, "const Interval *"],
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state)
    temp_converted = _ffi.cast("const Temporal *", temp)
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.tfloat_wmin_transfn(state_converted, temp_converted, interv_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_wsum_transfn(
    state: Annotated[cdata, "SkipList *"],
    temp: Annotated[cdata, "const Temporal *"],
    interv: Annotated[cdata, "const Interval *"],
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state)
    temp_converted = _ffi.cast("const Temporal *", temp)
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.tfloat_wsum_transfn(state_converted, temp_converted, interv_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timestamptz_tcount_transfn(state: Annotated[cdata, "SkipList *"] | None, t: int) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.timestamptz_tcount_transfn(state_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_tmax_transfn(
    state: Annotated[cdata, "SkipList *"] | None, temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_tmax_transfn(state_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_tmin_transfn(
    state: Annotated[cdata, "SkipList *"] | None, temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_tmin_transfn(state_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_tsum_transfn(
    state: Annotated[cdata, "SkipList *"] | None, temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tint_tsum_transfn(state_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_wmax_transfn(
    state: Annotated[cdata, "SkipList *"],
    temp: Annotated[cdata, "const Temporal *"],
    interv: Annotated[cdata, "const Interval *"],
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state)
    temp_converted = _ffi.cast("const Temporal *", temp)
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.tint_wmax_transfn(state_converted, temp_converted, interv_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_wmin_transfn(
    state: Annotated[cdata, "SkipList *"],
    temp: Annotated[cdata, "const Temporal *"],
    interv: Annotated[cdata, "const Interval *"],
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state)
    temp_converted = _ffi.cast("const Temporal *", temp)
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.tint_wmin_transfn(state_converted, temp_converted, interv_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_wsum_transfn(
    state: Annotated[cdata, "SkipList *"],
    temp: Annotated[cdata, "const Temporal *"],
    interv: Annotated[cdata, "const Interval *"],
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state)
    temp_converted = _ffi.cast("const Temporal *", temp)
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.tint_wsum_transfn(state_converted, temp_converted, interv_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_extent_transfn(
    box: Annotated[cdata, "TBox *"] | None, temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("TBox *", box) if box is not None else _ffi.NULL
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnumber_extent_transfn(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_tavg_finalfn(state: Annotated[cdata, "SkipList *"]) -> Annotated[cdata, "Temporal *"]:
    state_converted = _ffi.cast("SkipList *", state)
    result = _lib.tnumber_tavg_finalfn(state_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_tavg_transfn(
    state: Annotated[cdata, "SkipList *"] | None, temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnumber_tavg_transfn(state_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_wavg_transfn(
    state: Annotated[cdata, "SkipList *"],
    temp: Annotated[cdata, "const Temporal *"],
    interv: Annotated[cdata, "const Interval *"],
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state)
    temp_converted = _ffi.cast("const Temporal *", temp)
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.tnumber_wavg_transfn(state_converted, temp_converted, interv_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzset_tcount_transfn(
    state: Annotated[cdata, "SkipList *"] | None, s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tstzset_tcount_transfn(state_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspan_tcount_transfn(
    state: Annotated[cdata, "SkipList *"] | None, s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tstzspan_tcount_transfn(state_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspanset_tcount_transfn(
    state: Annotated[cdata, "SkipList *"] | None, ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tstzspanset_tcount_transfn(state_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttext_tmax_transfn(
    state: Annotated[cdata, "SkipList *"] | None, temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ttext_tmax_transfn(state_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttext_tmin_transfn(
    state: Annotated[cdata, "SkipList *"] | None, temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state) if state is not None else _ffi.NULL
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ttext_tmin_transfn(state_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_simplify_dp(
    temp: Annotated[cdata, "const Temporal *"], eps_dist: float, synchronized: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_simplify_dp(temp_converted, eps_dist, synchronized)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_simplify_max_dist(
    temp: Annotated[cdata, "const Temporal *"], eps_dist: float, synchronized: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_simplify_max_dist(temp_converted, eps_dist, synchronized)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_simplify_min_dist(
    temp: Annotated[cdata, "const Temporal *"], dist: float
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_simplify_min_dist(temp_converted, dist)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_simplify_min_tdelta(
    temp: Annotated[cdata, "const Temporal *"], mint: Annotated[cdata, "const Interval *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    mint_converted = _ffi.cast("const Interval *", mint)
    result = _lib.temporal_simplify_min_tdelta(temp_converted, mint_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_tprecision(
    temp: Annotated[cdata, "const Temporal *"], duration: Annotated[cdata, "const Interval *"], origin: int
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    duration_converted = _ffi.cast("const Interval *", duration)
    origin_converted = _ffi.cast("TimestampTz", origin)
    result = _lib.temporal_tprecision(temp_converted, duration_converted, origin_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_tsample(
    temp: Annotated[cdata, "const Temporal *"],
    duration: Annotated[cdata, "const Interval *"],
    origin: int,
    interp: InterpolationType,
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    duration_converted = _ffi.cast("const Interval *", duration)
    origin_converted = _ffi.cast("TimestampTz", origin)
    result = _lib.temporal_tsample(temp_converted, duration_converted, origin_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_dyntimewarp_distance(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[float, "double"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.temporal_dyntimewarp_distance(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_dyntimewarp_path(
    temp1: Annotated[cdata, "const Temporal *"],
    temp2: Annotated[cdata, "const Temporal *"],
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "Match *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    count_converted = _ffi.cast("int *", count)
    result = _lib.temporal_dyntimewarp_path(temp1_converted, temp2_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_frechet_distance(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[float, "double"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.temporal_frechet_distance(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_frechet_path(
    temp1: Annotated[cdata, "const Temporal *"],
    temp2: Annotated[cdata, "const Temporal *"],
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "Match *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    count_converted = _ffi.cast("int *", count)
    result = _lib.temporal_frechet_path(temp1_converted, temp2_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_hausdorff_distance(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[float, "double"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.temporal_hausdorff_distance(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_time_bins(
    temp: Annotated[cdata, "const Temporal *"],
    duration: Annotated[cdata, "const Interval *"],
    origin: int,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "Span *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    duration_converted = _ffi.cast("const Interval *", duration)
    origin_converted = _ffi.cast("TimestampTz", origin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.temporal_time_bins(temp_converted, duration_converted, origin_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_time_split(
    temp: Annotated[cdata, "const Temporal *"], duration: Annotated[cdata, "const Interval *"], torigin: int
) -> tuple[Annotated[cdata, "Temporal **"], Annotated[list, "TimestampTz *"], Annotated[cdata, "int"]]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    time_bins = _ffi.new("TimestampTz **")
    count = _ffi.new("int *")
    result = _lib.temporal_time_split(temp_converted, duration_converted, torigin_converted, time_bins, count)
    _check_error()
    return result if result != _ffi.NULL else None, time_bins[0], count[0]


def tfloat_time_boxes(
    temp: Annotated[cdata, "const Temporal *"],
    duration: Annotated[cdata, "const Interval *"],
    torigin: int,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "TBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tfloat_time_boxes(temp_converted, duration_converted, torigin_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_value_bins(
    temp: Annotated[cdata, "const Temporal *"], vsize: float, vorigin: float, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tfloat_value_bins(temp_converted, vsize, vorigin, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_value_boxes(
    temp: Annotated[cdata, "const Temporal *"], vsize: float, vorigin: float, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "TBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tfloat_value_boxes(temp_converted, vsize, vorigin, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_value_split(
    temp: Annotated[cdata, "const Temporal *"], size: float, origin: float
) -> tuple[Annotated[cdata, "Temporal **"], Annotated[list, "double *"], Annotated[cdata, "int"]]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    bins = _ffi.new("double **")
    count = _ffi.new("int *")
    result = _lib.tfloat_value_split(temp_converted, size, origin, bins, count)
    _check_error()
    return result if result != _ffi.NULL else None, bins[0], count[0]


def tfloat_value_time_boxes(
    temp: Annotated[cdata, "const Temporal *"],
    vsize: float,
    duration: Annotated[cdata, "const Interval *"],
    vorigin: float,
    torigin: int,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "TBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tfloat_value_time_boxes(
        temp_converted, vsize, duration_converted, vorigin, torigin_converted, count_converted
    )
    _check_error()
    return result if result != _ffi.NULL else None


def tfloat_value_time_split(
    temp: Annotated[cdata, "const Temporal *"],
    vsize: float,
    duration: Annotated[cdata, "const Interval *"],
    vorigin: float,
    torigin: int,
) -> tuple[
    Annotated[cdata, "Temporal **"],
    Annotated[list, "double *"],
    Annotated[list, "TimestampTz *"],
    Annotated[cdata, "int"],
]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    value_bins = _ffi.new("double **")
    time_bins = _ffi.new("TimestampTz **")
    count = _ffi.new("int *")
    result = _lib.tfloat_value_time_split(
        temp_converted, vsize, duration_converted, vorigin, torigin_converted, value_bins, time_bins, count
    )
    _check_error()
    return result if result != _ffi.NULL else None, value_bins[0], time_bins[0], count[0]


def tfloatbox_time_tiles(
    box: Annotated[cdata, "const TBox *"],
    duration: Annotated[cdata, "const Interval *"],
    torigin: int,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("const TBox *", box)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tfloatbox_time_tiles(box_converted, duration_converted, torigin_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloatbox_value_tiles(
    box: Annotated[cdata, "const TBox *"], vsize: float, vorigin: float, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("const TBox *", box)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tfloatbox_value_tiles(box_converted, vsize, vorigin, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloatbox_value_time_tiles(
    box: Annotated[cdata, "const TBox *"],
    vsize: float,
    duration: Annotated[cdata, "const Interval *"],
    vorigin: float,
    torigin: int | None,
) -> tuple[Annotated[cdata, "TBox *"], Annotated[cdata, "int"]]:
    box_converted = _ffi.cast("const TBox *", box)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin) if torigin is not None else _ffi.NULL
    count = _ffi.new("int *")
    result = _lib.tfloatbox_value_time_tiles(
        box_converted, vsize, duration_converted, vorigin, torigin_converted, count
    )
    _check_error()
    return result if result != _ffi.NULL else None, count[0]


def tint_time_boxes(
    temp: Annotated[cdata, "const Temporal *"],
    duration: Annotated[cdata, "const Interval *"],
    torigin: int,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "TBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tint_time_boxes(temp_converted, duration_converted, torigin_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_value_bins(
    temp: Annotated[cdata, "const Temporal *"], vsize: int, vorigin: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Span *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tint_value_bins(temp_converted, vsize, vorigin, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_value_boxes(
    temp: Annotated[cdata, "const Temporal *"], vsize: int, vorigin: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "TBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tint_value_boxes(temp_converted, vsize, vorigin, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tint_value_split(
    temp: Annotated[cdata, "const Temporal *"], vsize: int, vorigin: int
) -> tuple[Annotated[cdata, "Temporal **"], Annotated[list, "int *"], Annotated[cdata, "int"]]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    bins = _ffi.new("int **")
    count = _ffi.new("int *")
    result = _lib.tint_value_split(temp_converted, vsize, vorigin, bins, count)
    _check_error()
    return result if result != _ffi.NULL else None, bins[0], count[0]


def tint_value_time_boxes(
    temp: Annotated[cdata, "const Temporal *"],
    vsize: int,
    duration: Annotated[cdata, "const Interval *"],
    vorigin: int,
    torigin: int,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "TBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tint_value_time_boxes(
        temp_converted, vsize, duration_converted, vorigin, torigin_converted, count_converted
    )
    _check_error()
    return result if result != _ffi.NULL else None


def tint_value_time_split(
    temp: Annotated[cdata, "const Temporal *"],
    size: int,
    duration: Annotated[cdata, "const Interval *"],
    vorigin: int,
    torigin: int,
) -> tuple[
    Annotated[cdata, "Temporal **"], Annotated[list, "int *"], Annotated[list, "TimestampTz *"], Annotated[cdata, "int"]
]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    value_bins = _ffi.new("int **")
    time_bins = _ffi.new("TimestampTz **")
    count = _ffi.new("int *")
    result = _lib.tint_value_time_split(
        temp_converted, size, duration_converted, vorigin, torigin_converted, value_bins, time_bins, count
    )
    _check_error()
    return result if result != _ffi.NULL else None, value_bins[0], time_bins[0], count[0]


def tintbox_time_tiles(
    box: Annotated[cdata, "const TBox *"],
    duration: Annotated[cdata, "const Interval *"],
    torigin: int,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("const TBox *", box)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tintbox_time_tiles(box_converted, duration_converted, torigin_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tintbox_value_tiles(
    box: Annotated[cdata, "const TBox *"], xsize: int, xorigin: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("const TBox *", box)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tintbox_value_tiles(box_converted, xsize, xorigin, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tintbox_value_time_tiles(
    box: Annotated[cdata, "const TBox *"],
    xsize: int,
    duration: Annotated[cdata, "const Interval *"],
    xorigin: int | None,
    torigin: int | None,
) -> tuple[Annotated[cdata, "TBox *"], Annotated[cdata, "int"]]:
    box_converted = _ffi.cast("const TBox *", box)
    duration_converted = _ffi.cast("const Interval *", duration)
    xorigin_converted = xorigin if xorigin is not None else _ffi.NULL
    torigin_converted = _ffi.cast("TimestampTz", torigin) if torigin is not None else _ffi.NULL
    count = _ffi.new("int *")
    result = _lib.tintbox_value_time_tiles(
        box_converted, xsize, duration_converted, xorigin_converted, torigin_converted, count
    )
    _check_error()
    return result if result != _ffi.NULL else None, count[0]


def tempsubtype_name(subtype: Annotated[cdata, "tempSubtype"]) -> Annotated[str, "const char *"]:
    subtype_converted = _ffi.cast("tempSubtype", subtype)
    result = _lib.tempsubtype_name(subtype_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def tempsubtype_from_string(string: str, subtype: Annotated[cdata, "int16 *"]) -> Annotated[bool, "bool"]:
    string_converted = string.encode("utf-8")
    subtype_converted = _ffi.cast("int16 *", subtype)
    result = _lib.tempsubtype_from_string(string_converted, subtype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def meosoper_name(oper: Annotated[cdata, "meosOper"]) -> Annotated[str, "const char *"]:
    oper_converted = _ffi.cast("meosOper", oper)
    result = _lib.meosoper_name(oper_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def meosoper_from_string(name: str) -> Annotated[cdata, "meosOper"]:
    name_converted = name.encode("utf-8")
    result = _lib.meosoper_from_string(name_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def interptype_name(interp: InterpolationType) -> Annotated[str, "const char *"]:
    result = _lib.interptype_name(interp)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def interptype_from_string(interp_str: str) -> Annotated[InterpolationType, "interpType"]:
    interp_str_converted = interp_str.encode("utf-8")
    result = _lib.interptype_from_string(interp_str_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def meostype_name(type: Annotated[cdata, "meosType"]) -> Annotated[str, "const char *"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.meostype_name(type_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def temptype_basetype(type: Annotated[cdata, "meosType"]) -> Annotated[cdata, "meosType"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.temptype_basetype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def settype_basetype(type: Annotated[cdata, "meosType"]) -> Annotated[cdata, "meosType"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.settype_basetype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spantype_basetype(type: Annotated[cdata, "meosType"]) -> Annotated[cdata, "meosType"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.spantype_basetype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spantype_spansettype(type: Annotated[cdata, "meosType"]) -> Annotated[cdata, "meosType"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.spantype_spansettype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spansettype_spantype(type: Annotated[cdata, "meosType"]) -> Annotated[cdata, "meosType"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.spansettype_spantype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def basetype_spantype(type: Annotated[cdata, "meosType"]) -> Annotated[cdata, "meosType"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.basetype_spantype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def basetype_settype(type: Annotated[cdata, "meosType"]) -> Annotated[cdata, "meosType"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.basetype_settype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_basetype(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.tnumber_basetype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_basetype(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.geo_basetype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def time_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.time_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.set_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def numset_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.numset_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_numset_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_numset_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timeset_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.timeset_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_spantype(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.set_spantype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_set_spantype(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_set_spantype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def alphanumset_type(settype: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    settype_converted = _ffi.cast("meosType", settype)
    result = _lib.alphanumset_type(settype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geoset_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.geoset_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_geoset_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_geoset_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spatialset_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.spatialset_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_spatialset_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_spatialset_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_basetype(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.span_basetype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_canon_basetype(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.span_canon_basetype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.span_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def type_span_bbox(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.type_span_bbox(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_tbox_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.span_tbox_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_span_tbox_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_span_tbox_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def numspan_basetype(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.numspan_basetype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def numspan_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.numspan_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_numspan_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_numspan_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timespan_basetype(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.timespan_basetype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timespan_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.timespan_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.spanset_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timespanset_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.timespanset_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_timespanset_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_timespanset_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.temporal_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temptype_continuous(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.temptype_continuous(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def basetype_byvalue(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.basetype_byvalue(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def basetype_varlength(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.basetype_varlength(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def basetype_length(type: Annotated[cdata, "meosType"]) -> Annotated[int, "int16"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.basetype_length(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def talpha_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.talpha_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.tnumber_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_tnumber_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_tnumber_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_tnumber_basetype(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_tnumber_basetype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_spantype(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.tnumber_spantype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spatial_basetype(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.spatial_basetype(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tspatial_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.tspatial_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_tspatial_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_tspatial_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.tpoint_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_tpoint_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_tpoint_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.tgeo_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_tgeo_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_tgeo_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_type_all(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.tgeo_type_all(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_tgeo_type_all(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_tgeo_type_all(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeometry_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.tgeometry_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_tgeometry_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_tgeometry_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeodetic_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.tgeodetic_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_tgeodetic_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_tgeodetic_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ensure_tnumber_tpoint_type(type: Annotated[cdata, "meosType"]) -> Annotated[bool, "bool"]:
    type_converted = _ffi.cast("meosType", type)
    result = _lib.ensure_tnumber_tpoint_type(type_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_as_ewkb(
    gs: Annotated[cdata, "const GSERIALIZED *"], endian: str, size: Annotated[cdata, "size_t *"]
) -> Annotated[cdata, "uint8_t *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    endian_converted = endian.encode("utf-8")
    size_converted = _ffi.cast("size_t *", size)
    result = _lib.geo_as_ewkb(gs_converted, endian_converted, size_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_as_ewkt(gs: Annotated[cdata, "const GSERIALIZED *"], precision: int) -> Annotated[str, "char *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geo_as_ewkt(gs_converted, precision)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def geo_as_geojson(
    gs: Annotated[cdata, "const GSERIALIZED *"], option: int, precision: int, srs: str | None
) -> Annotated[str, "char *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    srs_converted = srs.encode("utf-8") if srs is not None else _ffi.NULL
    result = _lib.geo_as_geojson(gs_converted, option, precision, srs_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def geo_as_hexewkb(gs: Annotated[cdata, "const GSERIALIZED *"], endian: str) -> Annotated[str, "char *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    endian_converted = endian.encode("utf-8")
    result = _lib.geo_as_hexewkb(gs_converted, endian_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def geo_as_text(gs: Annotated[cdata, "const GSERIALIZED *"], precision: int) -> Annotated[str, "char *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geo_as_text(gs_converted, precision)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def geo_from_ewkb(
    wkb: Annotated[cdata, "const uint8_t *"], wkb_size: Annotated[cdata, "size_t"], srid: int
) -> Annotated[cdata, "GSERIALIZED *"]:
    wkb_converted = _ffi.cast("const uint8_t *", wkb)
    wkb_size_converted = _ffi.cast("size_t", wkb_size)
    srid_converted = _ffi.cast("int32", srid)
    result = _lib.geo_from_ewkb(wkb_converted, wkb_size_converted, srid_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_from_geojson(geojson: str) -> Annotated[cdata, "GSERIALIZED *"]:
    geojson_converted = geojson.encode("utf-8")
    result = _lib.geo_from_geojson(geojson_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_from_text(wkt: str, srid: Annotated[cdata, "int32_t"]) -> Annotated[cdata, "GSERIALIZED *"]:
    wkt_converted = wkt.encode("utf-8")
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.geo_from_text(wkt_converted, srid_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_out(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[str, "char *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geo_out(gs_converted)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def geog_from_binary(wkb_bytea: str) -> Annotated[cdata, "GSERIALIZED *"]:
    wkb_bytea_converted = wkb_bytea.encode("utf-8")
    result = _lib.geog_from_binary(wkb_bytea_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geog_from_hexewkb(wkt: str) -> Annotated[cdata, "GSERIALIZED *"]:
    wkt_converted = wkt.encode("utf-8")
    result = _lib.geog_from_hexewkb(wkt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geog_in(string: str, typmod: int) -> Annotated[cdata, "GSERIALIZED *"]:
    string_converted = string.encode("utf-8")
    typmod_converted = _ffi.cast("int32", typmod)
    result = _lib.geog_in(string_converted, typmod_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_from_hexewkb(wkt: str) -> Annotated[cdata, "GSERIALIZED *"]:
    wkt_converted = wkt.encode("utf-8")
    result = _lib.geom_from_hexewkb(wkt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_in(string: str, typmod: int) -> Annotated[cdata, "GSERIALIZED *"]:
    string_converted = string.encode("utf-8")
    typmod_converted = _ffi.cast("int32", typmod)
    result = _lib.geom_in(string_converted, typmod_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_copy(g: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    g_converted = _ffi.cast("const GSERIALIZED *", g)
    result = _lib.geo_copy(g_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geogpoint_make2d(srid: Annotated[cdata, "int32_t"], x: float, y: float) -> Annotated[cdata, "GSERIALIZED *"]:
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.geogpoint_make2d(srid_converted, x, y)
    _check_error()
    return result if result != _ffi.NULL else None


def geogpoint_make3dz(
    srid: Annotated[cdata, "int32_t"], x: float, y: float, z: float
) -> Annotated[cdata, "GSERIALIZED *"]:
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.geogpoint_make3dz(srid_converted, x, y, z)
    _check_error()
    return result if result != _ffi.NULL else None


def geompoint_make2d(srid: Annotated[cdata, "int32_t"], x: float, y: float) -> Annotated[cdata, "GSERIALIZED *"]:
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.geompoint_make2d(srid_converted, x, y)
    _check_error()
    return result if result != _ffi.NULL else None


def geompoint_make3dz(
    srid: Annotated[cdata, "int32_t"], x: float, y: float, z: float
) -> Annotated[cdata, "GSERIALIZED *"]:
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.geompoint_make3dz(srid_converted, x, y, z)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_to_geog(geom: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    geom_converted = _ffi.cast("const GSERIALIZED *", geom)
    result = _lib.geom_to_geog(geom_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geog_to_geom(geog: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    geog_converted = _ffi.cast("const GSERIALIZED *", geog)
    result = _lib.geog_to_geom(geog_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_is_empty(g: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[bool, "bool"]:
    g_converted = _ffi.cast("const GSERIALIZED *", g)
    result = _lib.geo_is_empty(g_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_typename(type: int) -> Annotated[str, "const char *"]:
    result = _lib.geo_typename(type)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def geog_area(g: Annotated[cdata, "const GSERIALIZED *"], use_spheroid: bool) -> Annotated[float, "double"]:
    g_converted = _ffi.cast("const GSERIALIZED *", g)
    result = _lib.geog_area(g_converted, use_spheroid)
    _check_error()
    return result if result != _ffi.NULL else None


def geog_centroid(g: Annotated[cdata, "const GSERIALIZED *"], use_spheroid: bool) -> Annotated[cdata, "GSERIALIZED *"]:
    g_converted = _ffi.cast("const GSERIALIZED *", g)
    result = _lib.geog_centroid(g_converted, use_spheroid)
    _check_error()
    return result if result != _ffi.NULL else None


def geog_length(g: Annotated[cdata, "const GSERIALIZED *"], use_spheroid: bool) -> Annotated[float, "double"]:
    g_converted = _ffi.cast("const GSERIALIZED *", g)
    result = _lib.geog_length(g_converted, use_spheroid)
    _check_error()
    return result if result != _ffi.NULL else None


def geog_perimeter(g: Annotated[cdata, "const GSERIALIZED *"], use_spheroid: bool) -> Annotated[float, "double"]:
    g_converted = _ffi.cast("const GSERIALIZED *", g)
    result = _lib.geog_perimeter(g_converted, use_spheroid)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_azimuth(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "double"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    out_result = _ffi.new("double *")
    result = _lib.geom_azimuth(gs1_converted, gs2_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def geom_length(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[float, "double"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geom_length(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_perimeter(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[float, "double"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geom_perimeter(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def line_numpoints(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[int, "int"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.line_numpoints(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def line_point_n(geom: Annotated[cdata, "const GSERIALIZED *"], n: int) -> Annotated[cdata, "GSERIALIZED *"]:
    geom_converted = _ffi.cast("const GSERIALIZED *", geom)
    result = _lib.line_point_n(geom_converted, n)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_reverse(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geo_reverse(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_round(gs: Annotated[cdata, "const GSERIALIZED *"], maxdd: int) -> Annotated[cdata, "GSERIALIZED *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geo_round(gs_converted, maxdd)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_set_srid(
    gs: Annotated[cdata, "const GSERIALIZED *"], srid: Annotated[cdata, "int32_t"]
) -> Annotated[cdata, "GSERIALIZED *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.geo_set_srid(gs_converted, srid_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_srid(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[cdata, "int32_t"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geo_srid(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_transform(
    geom: Annotated[cdata, "GSERIALIZED *"], srid_to: Annotated[cdata, "int32_t"]
) -> Annotated[cdata, "GSERIALIZED *"]:
    geom_converted = _ffi.cast("GSERIALIZED *", geom)
    srid_to_converted = _ffi.cast("int32_t", srid_to)
    result = _lib.geo_transform(geom_converted, srid_to_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_transform_pipeline(
    gs: Annotated[cdata, "const GSERIALIZED *"], pipeline: str, srid_to: Annotated[cdata, "int32_t"], is_forward: bool
) -> Annotated[cdata, "GSERIALIZED *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    pipeline_converted = pipeline.encode("utf-8")
    srid_to_converted = _ffi.cast("int32_t", srid_to)
    result = _lib.geo_transform_pipeline(gs_converted, pipeline_converted, srid_to_converted, is_forward)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_collect_garray(gsarr: Annotated[list, "GSERIALIZED **"], count: int) -> Annotated[cdata, "GSERIALIZED *"]:
    gsarr_converted = [_ffi.cast("GSERIALIZED *", x) for x in gsarr]
    result = _lib.geo_collect_garray(gsarr_converted, count)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_makeline_garray(gsarr: Annotated[list, "GSERIALIZED **"], count: int) -> Annotated[cdata, "GSERIALIZED *"]:
    gsarr_converted = [_ffi.cast("GSERIALIZED *", x) for x in gsarr]
    result = _lib.geo_makeline_garray(gsarr_converted, count)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_npoints(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[int, "int"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geo_npoints(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_ngeos(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[int, "int"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geo_ngeos(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_geoN(geom: Annotated[cdata, "const GSERIALIZED *"], n: int) -> Annotated[cdata, "GSERIALIZED *"]:
    geom_converted = _ffi.cast("const GSERIALIZED *", geom)
    result = _lib.geo_geoN(geom_converted, n)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_array_union(gsarr: Annotated[list, "GSERIALIZED **"], count: int) -> Annotated[cdata, "GSERIALIZED *"]:
    gsarr_converted = [_ffi.cast("GSERIALIZED *", x) for x in gsarr]
    result = _lib.geom_array_union(gsarr_converted, count)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_boundary(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geom_boundary(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_buffer(
    gs: Annotated[cdata, "const GSERIALIZED *"], size: float, params: str
) -> Annotated[cdata, "GSERIALIZED *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    params_converted = params.encode("utf-8")
    result = _lib.geom_buffer(gs_converted, size, params_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_centroid(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geom_centroid(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_convex_hull(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geom_convex_hull(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_difference2d(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "GSERIALIZED *"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geom_difference2d(gs1_converted, gs2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_intersection2d(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "GSERIALIZED *"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geom_intersection2d(gs1_converted, gs2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_shortestline2d(
    gs1: Annotated[cdata, "const GSERIALIZED *"], s2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "GSERIALIZED *"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    s2_converted = _ffi.cast("const GSERIALIZED *", s2)
    result = _lib.geom_shortestline2d(gs1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_shortestline3d(
    gs1: Annotated[cdata, "const GSERIALIZED *"], s2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "GSERIALIZED *"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    s2_converted = _ffi.cast("const GSERIALIZED *", s2)
    result = _lib.geom_shortestline3d(gs1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_unary_union(gs: Annotated[cdata, "GSERIALIZED *"], prec: float) -> Annotated[cdata, "GSERIALIZED *"]:
    gs_converted = _ffi.cast("GSERIALIZED *", gs)
    result = _lib.geom_unary_union(gs_converted, prec)
    _check_error()
    return result if result != _ffi.NULL else None


def line_interpolate_point(
    gs: Annotated[cdata, "GSERIALIZED *"], distance_fraction: float, repeat: bool
) -> Annotated[cdata, "GSERIALIZED *"]:
    gs_converted = _ffi.cast("GSERIALIZED *", gs)
    result = _lib.line_interpolate_point(gs_converted, distance_fraction, repeat)
    _check_error()
    return result if result != _ffi.NULL else None


def line_locate_point(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[float, "double"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.line_locate_point(gs1_converted, gs2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def line_substring(
    gs: Annotated[cdata, "const GSERIALIZED *"], from_: float, to: float
) -> Annotated[cdata, "GSERIALIZED *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.line_substring(gs_converted, from_, to)
    _check_error()
    return result if result != _ffi.NULL else None


def geog_dwithin(
    g1: Annotated[cdata, "const GSERIALIZED *"],
    g2: Annotated[cdata, "const GSERIALIZED *"],
    tolerance: float,
    use_spheroid: bool,
) -> Annotated[bool, "bool"]:
    g1_converted = _ffi.cast("const GSERIALIZED *", g1)
    g2_converted = _ffi.cast("const GSERIALIZED *", g2)
    result = _lib.geog_dwithin(g1_converted, g2_converted, tolerance, use_spheroid)
    _check_error()
    return result if result != _ffi.NULL else None


def geog_intersects(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"], use_spheroid: bool
) -> Annotated[bool, "bool"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geog_intersects(gs1_converted, gs2_converted, use_spheroid)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_contains(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[bool, "bool"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geom_contains(gs1_converted, gs2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_covers(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[bool, "bool"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geom_covers(gs1_converted, gs2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_disjoint2d(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[bool, "bool"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geom_disjoint2d(gs1_converted, gs2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_dwithin2d(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"], tolerance: float
) -> Annotated[bool, "bool"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geom_dwithin2d(gs1_converted, gs2_converted, tolerance)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_dwithin3d(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"], tolerance: float
) -> Annotated[bool, "bool"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geom_dwithin3d(gs1_converted, gs2_converted, tolerance)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_intersects2d(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[bool, "bool"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geom_intersects2d(gs1_converted, gs2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_intersects3d(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[bool, "bool"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geom_intersects3d(gs1_converted, gs2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_relate_pattern(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"], patt: str
) -> Annotated[bool, "bool"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    patt_converted = patt.encode("utf-8")
    result = _lib.geom_relate_pattern(gs1_converted, gs2_converted, patt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_touches(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[bool, "bool"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geom_touches(gs1_converted, gs2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_stboxes(
    gs: Annotated[cdata, "const GSERIALIZED *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "STBox *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    count_converted = _ffi.cast("int *", count)
    result = _lib.geo_stboxes(gs_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_split_each_n_stboxes(
    gs: Annotated[cdata, "const GSERIALIZED *"], elem_count: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "STBox *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    count_converted = _ffi.cast("int *", count)
    result = _lib.geo_split_each_n_stboxes(gs_converted, elem_count, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_split_n_stboxes(
    gs: Annotated[cdata, "const GSERIALIZED *"], box_count: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "STBox *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    count_converted = _ffi.cast("int *", count)
    result = _lib.geo_split_n_stboxes(gs_converted, box_count, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geog_distance(
    g1: Annotated[cdata, "const GSERIALIZED *"], g2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[float, "double"]:
    g1_converted = _ffi.cast("const GSERIALIZED *", g1)
    g2_converted = _ffi.cast("const GSERIALIZED *", g2)
    result = _lib.geog_distance(g1_converted, g2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_distance2d(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[float, "double"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geom_distance2d(gs1_converted, gs2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_distance3d(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[float, "double"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geom_distance3d(gs1_converted, gs2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_equals(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geo_equals(gs1_converted, gs2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_same(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[bool, "bool"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    result = _lib.geo_same(gs1_converted, gs2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geogset_in(string: str) -> Annotated[cdata, "Set *"]:
    string_converted = string.encode("utf-8")
    result = _lib.geogset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geomset_in(string: str) -> Annotated[cdata, "Set *"]:
    string_converted = string.encode("utf-8")
    result = _lib.geomset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spatialset_as_text(set: Annotated[cdata, "const Set *"], maxdd: int) -> Annotated[str, "char *"]:
    set_converted = _ffi.cast("const Set *", set)
    result = _lib.spatialset_as_text(set_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def spatialset_as_ewkt(set: Annotated[cdata, "const Set *"], maxdd: int) -> Annotated[str, "char *"]:
    set_converted = _ffi.cast("const Set *", set)
    result = _lib.spatialset_as_ewkt(set_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def geoset_make(values: Annotated[list, "const GSERIALIZED **"]) -> Annotated[cdata, "Set *"]:
    values_converted = [_ffi.cast("const GSERIALIZED *", x) for x in values]
    result = _lib.geoset_make(values_converted, len(values))
    _check_error()
    return result if result != _ffi.NULL else None


def geo_to_set(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[cdata, "Set *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geo_to_set(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geoset_end_value(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.geoset_end_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geoset_start_value(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.geoset_start_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geoset_value_n(s: Annotated[cdata, "const Set *"], n: int) -> Annotated[list, "GSERIALIZED **"]:
    s_converted = _ffi.cast("const Set *", s)
    out_result = _ffi.new("GSERIALIZED **")
    result = _lib.geoset_value_n(s_converted, n, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def geoset_values(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "GSERIALIZED **"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.geoset_values(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_geo_set(
    gs: Annotated[cdata, "const GSERIALIZED *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[bool, "bool"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.contained_geo_set(gs_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_set_geo(
    s: Annotated[cdata, "const Set *"], gs: Annotated[cdata, "GSERIALIZED *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    gs_converted = _ffi.cast("GSERIALIZED *", gs)
    result = _lib.contains_set_geo(s_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_union_transfn(
    state: Annotated[cdata, "Set *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "Set *"]:
    state_converted = _ffi.cast("Set *", state)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geo_union_transfn(state_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_geo_set(
    gs: Annotated[cdata, "const GSERIALIZED *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Set *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intersection_geo_set(gs_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_set_geo(
    s: Annotated[cdata, "const Set *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.intersection_set_geo(s_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_geo_set(
    gs: Annotated[cdata, "const GSERIALIZED *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Set *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.minus_geo_set(gs_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_set_geo(
    s: Annotated[cdata, "const Set *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.minus_set_geo(s_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_geo_set(
    gs: Annotated[cdata, "const GSERIALIZED *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Set *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.union_geo_set(gs_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_set_geo(
    s: Annotated[cdata, "const Set *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.union_set_geo(s_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spatialset_set_srid(
    s: Annotated[cdata, "const Set *"], srid: Annotated[cdata, "int32_t"]
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.spatialset_set_srid(s_converted, srid_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spatialset_srid(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "int32_t"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.spatialset_srid(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spatialset_transform(
    s: Annotated[cdata, "const Set *"], srid: Annotated[cdata, "int32_t"]
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.spatialset_transform(s_converted, srid_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spatialset_transform_pipeline(
    s: Annotated[cdata, "const Set *"], pipelinestr: str, srid: Annotated[cdata, "int32_t"], is_forward: bool
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    pipelinestr_converted = pipelinestr.encode("utf-8")
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.spatialset_transform_pipeline(s_converted, pipelinestr_converted, srid_converted, is_forward)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_as_hexwkb(
    box: Annotated[cdata, "const STBox *"], variant: int
) -> tuple[Annotated[str, "char *"], Annotated[cdata, "size_t *"]]:
    box_converted = _ffi.cast("const STBox *", box)
    variant_converted = _ffi.cast("uint8_t", variant)
    size = _ffi.new("size_t *")
    result = _lib.stbox_as_hexwkb(box_converted, variant_converted, size)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None, size[0]


def stbox_as_wkb(
    box: Annotated[cdata, "const STBox *"], variant: int
) -> tuple[Annotated[cdata, "uint8_t *"], Annotated[cdata, "size_t *"]]:
    box_converted = _ffi.cast("const STBox *", box)
    variant_converted = _ffi.cast("uint8_t", variant)
    size_out = _ffi.new("size_t *")
    result = _lib.stbox_as_wkb(box_converted, variant_converted, size_out)
    _check_error()
    result_converted = bytes(result[i] for i in range(size_out[0])) if result != _ffi.NULL else None
    return result_converted


def stbox_from_hexwkb(hexwkb: str) -> Annotated[cdata, "STBox *"]:
    hexwkb_converted = hexwkb.encode("utf-8")
    result = _lib.stbox_from_hexwkb(hexwkb_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_from_wkb(wkb: bytes) -> "STBOX *":
    wkb_converted = _ffi.new("uint8_t []", wkb)
    result = _lib.stbox_from_wkb(wkb_converted, len(wkb))
    return result if result != _ffi.NULL else None


def stbox_in(string: str) -> Annotated[cdata, "STBox *"]:
    string_converted = string.encode("utf-8")
    result = _lib.stbox_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_out(box: Annotated[cdata, "const STBox *"], maxdd: int) -> Annotated[str, "char *"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_out(box_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def geo_timestamptz_to_stbox(gs: Annotated[cdata, "const GSERIALIZED *"], t: int) -> Annotated[cdata, "STBox *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.geo_timestamptz_to_stbox(gs_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_tstzspan_to_stbox(
    gs: Annotated[cdata, "const GSERIALIZED *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "STBox *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.geo_tstzspan_to_stbox(gs_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_copy(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "STBox *"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_copy(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_make(
    hasx: bool,
    hasz: bool,
    geodetic: bool,
    srid: int,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    zmin: float,
    zmax: float,
    s: Annotated[cdata, "const Span *"] | None,
) -> Annotated[cdata, "STBox *"]:
    srid_converted = _ffi.cast("int32", srid)
    s_converted = _ffi.cast("const Span *", s) if s is not None else _ffi.NULL
    result = _lib.stbox_make(hasx, hasz, geodetic, srid_converted, xmin, xmax, ymin, ymax, zmin, zmax, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_to_stbox(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[cdata, "STBox *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geo_to_stbox(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spatialset_to_stbox(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "STBox *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.spatialset_to_stbox(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_to_box3d(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "BOX3D *"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_to_box3d(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_to_gbox(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "GBOX *"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_to_gbox(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_to_geo(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_to_geo(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_to_tstzspan(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "Span *"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_to_tstzspan(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def timestamptz_to_stbox(t: int) -> Annotated[cdata, "STBox *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.timestamptz_to_stbox(t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzset_to_stbox(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "STBox *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tstzset_to_stbox(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspan_to_stbox(s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "STBox *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tstzspan_to_stbox(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspanset_to_stbox(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "STBox *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tstzspanset_to_stbox(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_area(box: Annotated[cdata, "const STBox *"], spheroid: bool) -> Annotated[float, "double"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_area(box_converted, spheroid)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_hast(box: Annotated[cdata, "const STBox *"]) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_hast(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_hasx(box: Annotated[cdata, "const STBox *"]) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_hasx(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_hasz(box: Annotated[cdata, "const STBox *"]) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_hasz(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_isgeodetic(box: Annotated[cdata, "const STBox *"]) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_isgeodetic(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_perimeter(box: Annotated[cdata, "const STBox *"], spheroid: bool) -> Annotated[float, "double"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_perimeter(box_converted, spheroid)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_tmax(box: Annotated[cdata, "const STBox *"]) -> int:
    box_converted = _ffi.cast("const STBox *", box)
    out_result = _ffi.new("TimestampTz *")
    result = _lib.stbox_tmax(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def stbox_tmax_inc(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    out_result = _ffi.new("bool *")
    result = _lib.stbox_tmax_inc(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def stbox_tmin(box: Annotated[cdata, "const STBox *"]) -> int:
    box_converted = _ffi.cast("const STBox *", box)
    out_result = _ffi.new("TimestampTz *")
    result = _lib.stbox_tmin(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def stbox_tmin_inc(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    out_result = _ffi.new("bool *")
    result = _lib.stbox_tmin_inc(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def stbox_volume(box: Annotated[cdata, "const STBox *"]) -> Annotated[float, "double"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_volume(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_xmax(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "double"]:
    box_converted = _ffi.cast("const STBox *", box)
    out_result = _ffi.new("double *")
    result = _lib.stbox_xmax(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def stbox_xmin(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "double"]:
    box_converted = _ffi.cast("const STBox *", box)
    out_result = _ffi.new("double *")
    result = _lib.stbox_xmin(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def stbox_ymax(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "double"]:
    box_converted = _ffi.cast("const STBox *", box)
    out_result = _ffi.new("double *")
    result = _lib.stbox_ymax(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def stbox_ymin(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "double"]:
    box_converted = _ffi.cast("const STBox *", box)
    out_result = _ffi.new("double *")
    result = _lib.stbox_ymin(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def stbox_zmax(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "double"]:
    box_converted = _ffi.cast("const STBox *", box)
    out_result = _ffi.new("double *")
    result = _lib.stbox_zmax(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def stbox_zmin(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "double"]:
    box_converted = _ffi.cast("const STBox *", box)
    out_result = _ffi.new("double *")
    result = _lib.stbox_zmin(box_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def stbox_expand_space(box: Annotated[cdata, "const STBox *"], d: float) -> Annotated[cdata, "STBox *"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_expand_space(box_converted, d)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_expand_time(
    box: Annotated[cdata, "const STBox *"], interv: Annotated[cdata, "const Interval *"]
) -> Annotated[cdata, "STBox *"]:
    box_converted = _ffi.cast("const STBox *", box)
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.stbox_expand_time(box_converted, interv_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_get_space(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "STBox *"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_get_space(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_quad_split(
    box: Annotated[cdata, "const STBox *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "STBox *"]:
    box_converted = _ffi.cast("const STBox *", box)
    count_converted = _ffi.cast("int *", count)
    result = _lib.stbox_quad_split(box_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_round(box: Annotated[cdata, "const STBox *"], maxdd: int) -> Annotated[cdata, "STBox *"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_round(box_converted, maxdd)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_shift_scale_time(
    box: Annotated[cdata, "const STBox *"],
    shift: Annotated[cdata, "const Interval *"] | None,
    duration: Annotated[cdata, "const Interval *"] | None,
) -> Annotated[cdata, "STBox *"]:
    box_converted = _ffi.cast("const STBox *", box)
    shift_converted = _ffi.cast("const Interval *", shift) if shift is not None else _ffi.NULL
    duration_converted = _ffi.cast("const Interval *", duration) if duration is not None else _ffi.NULL
    result = _lib.stbox_shift_scale_time(box_converted, shift_converted, duration_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stboxarr_round(boxarr: Annotated[cdata, "const STBox *"], count: int, maxdd: int) -> Annotated[cdata, "STBox *"]:
    boxarr_converted = _ffi.cast("const STBox *", boxarr)
    result = _lib.stboxarr_round(boxarr_converted, count, maxdd)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_set_srid(
    box: Annotated[cdata, "const STBox *"], srid: Annotated[cdata, "int32_t"]
) -> Annotated[cdata, "STBox *"]:
    box_converted = _ffi.cast("const STBox *", box)
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.stbox_set_srid(box_converted, srid_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_srid(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "int32_t"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_srid(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_transform(
    box: Annotated[cdata, "const STBox *"], srid: Annotated[cdata, "int32_t"]
) -> Annotated[cdata, "STBox *"]:
    box_converted = _ffi.cast("const STBox *", box)
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.stbox_transform(box_converted, srid_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_transform_pipeline(
    box: Annotated[cdata, "const STBox *"], pipelinestr: str, srid: Annotated[cdata, "int32_t"], is_forward: bool
) -> Annotated[cdata, "STBox *"]:
    box_converted = _ffi.cast("const STBox *", box)
    pipelinestr_converted = pipelinestr.encode("utf-8")
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.stbox_transform_pipeline(box_converted, pipelinestr_converted, srid_converted, is_forward)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.adjacent_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.contained_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.contains_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.overlaps_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def same_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.same_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def above_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.above_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.after_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def back_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.back_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.before_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def below_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.below_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def front_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.front_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.left_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overabove_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.overabove_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.overafter_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overback_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.overback_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.overbefore_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbelow_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.overbelow_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overfront_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.overfront_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.overleft_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.overright_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.right_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"], strict: bool
) -> Annotated[cdata, "STBox *"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.union_stbox_stbox(box1_converted, box2_converted, strict)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[cdata, "STBox *"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.intersection_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_cmp(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[int, "int"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.stbox_cmp(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_eq(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.stbox_eq(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_ge(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.stbox_ge(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_gt(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.stbox_gt(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_le(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.stbox_le(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_lt(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.stbox_lt(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_ne(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.stbox_ne(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def rtree_create_stbox() -> Annotated[cdata, "RTree *"]:
    result = _lib.rtree_create_stbox()
    _check_error()
    return result if result != _ffi.NULL else None


def rtree_free(rtree: Annotated[cdata, "RTree *"]) -> Annotated[None, "void"]:
    rtree_converted = _ffi.cast("RTree *", rtree)
    _lib.rtree_free(rtree_converted)
    _check_error()


def rtree_insert(
    rtree: Annotated[cdata, "RTree *"], box: Annotated[cdata, "STBox *"], id: int
) -> Annotated[None, "void"]:
    rtree_converted = _ffi.cast("RTree *", rtree)
    box_converted = _ffi.cast("STBox *", box)
    id_converted = _ffi.cast("int64", id)
    _lib.rtree_insert(rtree_converted, box_converted, id_converted)
    _check_error()


def rtree_search(
    rtree: Annotated[cdata, "const RTree *"], query: Annotated[cdata, "const STBox *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "int *"]:
    rtree_converted = _ffi.cast("const RTree *", rtree)
    query_converted = _ffi.cast("const STBox *", query)
    count_converted = _ffi.cast("int *", count)
    result = _lib.rtree_search(rtree_converted, query_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_out(temp: Annotated[cdata, "const Temporal *"], maxdd: int) -> Annotated[str, "char *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeo_out(temp_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def tgeogpoint_from_mfjson(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeogpoint_from_mfjson(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeogpoint_in(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeogpoint_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeography_from_mfjson(mfjson: str) -> Annotated[cdata, "Temporal *"]:
    mfjson_converted = mfjson.encode("utf-8")
    result = _lib.tgeography_from_mfjson(mfjson_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeography_in(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeography_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeometry_from_mfjson(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeometry_from_mfjson(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeometry_in(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeometry_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeompoint_from_mfjson(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeompoint_from_mfjson(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeompoint_in(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeompoint_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tspatial_as_ewkt(temp: Annotated[cdata, "const Temporal *"], maxdd: int) -> Annotated[str, "char *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tspatial_as_ewkt(temp_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def tspatial_as_text(temp: Annotated[cdata, "const Temporal *"], maxdd: int) -> Annotated[str, "char *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tspatial_as_text(temp_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def tgeo_from_base_temp(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeo_from_base_temp(gs_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeoinst_make(gs: Annotated[cdata, "const GSERIALIZED *"], t: int) -> Annotated[cdata, "TInstant *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.tgeoinst_make(gs_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeoseq_from_base_tstzset(
    gs: Annotated[cdata, "const GSERIALIZED *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "TSequence *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tgeoseq_from_base_tstzset(gs_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeoseq_from_base_tstzspan(
    gs: Annotated[cdata, "const GSERIALIZED *"], s: Annotated[cdata, "const Span *"], interp: InterpolationType
) -> Annotated[cdata, "TSequence *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tgeoseq_from_base_tstzspan(gs_converted, s_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeoseqset_from_base_tstzspanset(
    gs: Annotated[cdata, "const GSERIALIZED *"], ss: Annotated[cdata, "const SpanSet *"], interp: InterpolationType
) -> Annotated[cdata, "TSequenceSet *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tgeoseqset_from_base_tstzspanset(gs_converted, ss_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_from_base_temp(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tpoint_from_base_temp(gs_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpointinst_make(gs: Annotated[cdata, "const GSERIALIZED *"], t: int) -> Annotated[cdata, "TInstant *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.tpointinst_make(gs_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpointseq_from_base_tstzset(
    gs: Annotated[cdata, "const GSERIALIZED *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "TSequence *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tpointseq_from_base_tstzset(gs_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpointseq_from_base_tstzspan(
    gs: Annotated[cdata, "const GSERIALIZED *"], s: Annotated[cdata, "const Span *"], interp: InterpolationType
) -> Annotated[cdata, "TSequence *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tpointseq_from_base_tstzspan(gs_converted, s_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tpointseq_make_coords(
    xcoords: Annotated[cdata, "const double *"],
    ycoords: Annotated[cdata, "const double *"],
    zcoords: Annotated[cdata, "const double *"],
    times: int,
    count: int,
    srid: int,
    geodetic: bool,
    lower_inc: bool,
    upper_inc: bool,
    interp: InterpolationType,
    normalize: bool,
) -> Annotated[cdata, "TSequence *"]:
    xcoords_converted = _ffi.cast("const double *", xcoords)
    ycoords_converted = _ffi.cast("const double *", ycoords)
    zcoords_converted = _ffi.cast("const double *", zcoords)
    times_converted = _ffi.cast("const TimestampTz *", times)
    srid_converted = _ffi.cast("int32", srid)
    result = _lib.tpointseq_make_coords(
        xcoords_converted,
        ycoords_converted,
        zcoords_converted,
        times_converted,
        count,
        srid_converted,
        geodetic,
        lower_inc,
        upper_inc,
        interp,
        normalize,
    )
    _check_error()
    return result if result != _ffi.NULL else None


def tpointseqset_from_base_tstzspanset(
    gs: Annotated[cdata, "const GSERIALIZED *"], ss: Annotated[cdata, "const SpanSet *"], interp: InterpolationType
) -> Annotated[cdata, "TSequenceSet *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tpointseqset_from_base_tstzspanset(gs_converted, ss_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def box3d_to_stbox(box: Annotated[cdata, "const BOX3D *"]) -> Annotated[cdata, "STBox *"]:
    box_converted = _ffi.cast("const BOX3D *", box)
    result = _lib.box3d_to_stbox(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def gbox_to_stbox(box: Annotated[cdata, "const GBOX *"]) -> Annotated[cdata, "STBox *"]:
    box_converted = _ffi.cast("const GBOX *", box)
    result = _lib.gbox_to_stbox(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geomeas_to_tpoint(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[cdata, "Temporal *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geomeas_to_tpoint(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeogpoint_to_tgeography(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeogpoint_to_tgeography(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeography_to_tgeogpoint(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeography_to_tgeogpoint(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeography_to_tgeometry(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeography_to_tgeometry(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeometry_to_tgeography(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeometry_to_tgeography(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeometry_to_tgeompoint(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeometry_to_tgeompoint(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeompoint_to_tgeometry(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeompoint_to_tgeometry(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_as_mvtgeom(
    temp: Annotated[cdata, "const Temporal *"],
    bounds: Annotated[cdata, "const STBox *"],
    extent: Annotated[cdata, "int32_t"],
    buffer: Annotated[cdata, "int32_t"],
    clip_geom: bool,
    gsarr: Annotated[list, "GSERIALIZED **"],
    timesarr: Annotated[list, "int64 **"],
    count: Annotated[cdata, "int *"],
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    bounds_converted = _ffi.cast("const STBox *", bounds)
    extent_converted = _ffi.cast("int32_t", extent)
    buffer_converted = _ffi.cast("int32_t", buffer)
    gsarr_converted = [_ffi.cast("GSERIALIZED *", x) for x in gsarr]
    timesarr_converted = [_ffi.cast("int64 *", x) for x in timesarr]
    count_converted = _ffi.cast("int *", count)
    result = _lib.tpoint_as_mvtgeom(
        temp_converted,
        bounds_converted,
        extent_converted,
        buffer_converted,
        clip_geom,
        gsarr_converted,
        timesarr_converted,
        count_converted,
    )
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_tfloat_to_geomeas(
    tpoint: Annotated[cdata, "const Temporal *"], measure: Annotated[cdata, "const Temporal *"], segmentize: bool
) -> Annotated[list, "GSERIALIZED **"]:
    tpoint_converted = _ffi.cast("const Temporal *", tpoint)
    measure_converted = _ffi.cast("const Temporal *", measure)
    out_result = _ffi.new("GSERIALIZED **")
    result = _lib.tpoint_tfloat_to_geomeas(tpoint_converted, measure_converted, segmentize, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def tspatial_to_stbox(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "STBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tspatial_to_stbox(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bearing_point_point(
    gs1: Annotated[cdata, "const GSERIALIZED *"], gs2: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "double"]:
    gs1_converted = _ffi.cast("const GSERIALIZED *", gs1)
    gs2_converted = _ffi.cast("const GSERIALIZED *", gs2)
    out_result = _ffi.new("double *")
    result = _lib.bearing_point_point(gs1_converted, gs2_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def bearing_tpoint_point(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"], invert: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.bearing_tpoint_point(temp_converted, gs_converted, invert)
    _check_error()
    return result if result != _ffi.NULL else None


def bearing_tpoint_tpoint(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.bearing_tpoint_tpoint(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_centroid(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeo_centroid(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_convex_hull(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeo_convex_hull(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_end_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeo_end_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_start_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeo_start_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_traversed_area(
    temp: Annotated[cdata, "const Temporal *"], unary_union: bool
) -> Annotated[cdata, "GSERIALIZED *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeo_traversed_area(temp_converted, unary_union)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_value_at_timestamptz(
    temp: Annotated[cdata, "const Temporal *"], t: int, strict: bool
) -> Annotated[list, "GSERIALIZED **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    t_converted = _ffi.cast("TimestampTz", t)
    out_result = _ffi.new("GSERIALIZED **")
    result = _lib.tgeo_value_at_timestamptz(temp_converted, t_converted, strict, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def tgeo_value_n(temp: Annotated[cdata, "const Temporal *"], n: int) -> Annotated[list, "GSERIALIZED **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    out_result = _ffi.new("GSERIALIZED **")
    result = _lib.tgeo_value_n(temp_converted, n, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def tgeo_values(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "GSERIALIZED **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tgeo_values(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_angular_difference(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tpoint_angular_difference(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_azimuth(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tpoint_azimuth(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_cumulative_length(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tpoint_cumulative_length(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_direction(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    out_result = _ffi.new("double *")
    result = _lib.tpoint_direction(temp_converted, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tpoint_get_x(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tpoint_get_x(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_get_y(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tpoint_get_y(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_get_z(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tpoint_get_z(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_is_simple(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tpoint_is_simple(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_length(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tpoint_length(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_speed(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tpoint_speed(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_trajectory(
    temp: Annotated[cdata, "const Temporal *"], unary_union: bool
) -> Annotated[cdata, "GSERIALIZED *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tpoint_trajectory(temp_converted, unary_union)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_twcentroid(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tpoint_twcentroid(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_affine(
    temp: Annotated[cdata, "const Temporal *"], a: Annotated[cdata, "const AFFINE *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    a_converted = _ffi.cast("const AFFINE *", a)
    result = _lib.tgeo_affine(temp_converted, a_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_scale(
    temp: Annotated[cdata, "const Temporal *"],
    scale: Annotated[cdata, "const GSERIALIZED *"],
    sorigin: Annotated[cdata, "const GSERIALIZED *"],
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    scale_converted = _ffi.cast("const GSERIALIZED *", scale)
    sorigin_converted = _ffi.cast("const GSERIALIZED *", sorigin)
    result = _lib.tgeo_scale(temp_converted, scale_converted, sorigin_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_make_simple(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Temporal **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tpoint_make_simple(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tspatial_srid(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "int32_t"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tspatial_srid(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tspatial_set_srid(
    temp: Annotated[cdata, "const Temporal *"], srid: Annotated[cdata, "int32_t"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.tspatial_set_srid(temp_converted, srid_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tspatial_transform(
    temp: Annotated[cdata, "const Temporal *"], srid: Annotated[cdata, "int32_t"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.tspatial_transform(temp_converted, srid_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tspatial_transform_pipeline(
    temp: Annotated[cdata, "const Temporal *"], pipelinestr: str, srid: Annotated[cdata, "int32_t"], is_forward: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    pipelinestr_converted = pipelinestr.encode("utf-8")
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.tspatial_transform_pipeline(temp_converted, pipelinestr_converted, srid_converted, is_forward)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_at_geom(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.tgeo_at_geom(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_at_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"], border_inc: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.tgeo_at_stbox(temp_converted, box_converted, border_inc)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_at_value(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "GSERIALIZED *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("GSERIALIZED *", gs)
    result = _lib.tgeo_at_value(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_minus_geom(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.tgeo_minus_geom(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_minus_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"], border_inc: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.tgeo_minus_stbox(temp_converted, box_converted, border_inc)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_minus_value(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "GSERIALIZED *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("GSERIALIZED *", gs)
    result = _lib.tgeo_minus_value(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_at_geom(
    temp: Annotated[cdata, "const Temporal *"],
    gs: Annotated[cdata, "const GSERIALIZED *"],
    zspan: Annotated[cdata, "const Span *"],
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    zspan_converted = _ffi.cast("const Span *", zspan)
    result = _lib.tpoint_at_geom(temp_converted, gs_converted, zspan_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_at_value(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "GSERIALIZED *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("GSERIALIZED *", gs)
    result = _lib.tpoint_at_value(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_minus_geom(
    temp: Annotated[cdata, "const Temporal *"],
    gs: Annotated[cdata, "const GSERIALIZED *"],
    zspan: Annotated[cdata, "const Span *"],
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    zspan_converted = _ffi.cast("const Span *", zspan)
    result = _lib.tpoint_minus_geom(temp_converted, gs_converted, zspan_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_minus_value(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "GSERIALIZED *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("GSERIALIZED *", gs)
    result = _lib.tpoint_minus_value(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_eq_geo_tgeo(gs_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.always_eq_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.always_eq_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ne_geo_tgeo(gs_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.always_ne_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.always_ne_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_eq_geo_tgeo(gs_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.ever_eq_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.ever_eq_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ne_geo_tgeo(gs_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.ever_ne_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.ever_ne_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def teq_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.teq_geo_tgeo(gs_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def teq_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.teq_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tne_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tne_geo_tgeo(gs_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tne_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.tne_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_stboxes(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "STBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tgeo_stboxes(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_space_boxes(
    temp: Annotated[cdata, "const Temporal *"],
    xsize: float,
    ysize: float,
    zsize: float,
    sorigin: Annotated[cdata, "const GSERIALIZED *"],
    bitmatrix: bool,
    border_inc: bool,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "STBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    sorigin_converted = _ffi.cast("const GSERIALIZED *", sorigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tgeo_space_boxes(
        temp_converted, xsize, ysize, zsize, sorigin_converted, bitmatrix, border_inc, count_converted
    )
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_space_time_boxes(
    temp: Annotated[cdata, "const Temporal *"],
    xsize: float,
    ysize: float,
    zsize: float,
    duration: Annotated[cdata, "const Interval *"],
    sorigin: Annotated[cdata, "const GSERIALIZED *"],
    torigin: int,
    bitmatrix: bool,
    border_inc: bool,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "STBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    duration_converted = _ffi.cast("const Interval *", duration)
    sorigin_converted = _ffi.cast("const GSERIALIZED *", sorigin)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tgeo_space_time_boxes(
        temp_converted,
        xsize,
        ysize,
        zsize,
        duration_converted,
        sorigin_converted,
        torigin_converted,
        bitmatrix,
        border_inc,
        count_converted,
    )
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_split_each_n_stboxes(
    temp: Annotated[cdata, "const Temporal *"], elem_count: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "STBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tgeo_split_each_n_stboxes(temp_converted, elem_count, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_split_n_stboxes(
    temp: Annotated[cdata, "const Temporal *"], box_count: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "STBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tgeo_split_n_stboxes(temp_converted, box_count, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.adjacent_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.adjacent_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.adjacent_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.contained_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.contained_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.contained_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.contains_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.contains_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.contains_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overlaps_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.overlaps_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overlaps_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overlaps_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def same_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.same_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def same_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.same_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def same_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.same_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def above_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.above_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def above_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.above_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def above_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.above_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.after_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.after_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def after_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.after_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def back_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.back_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def back_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.back_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def back_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.back_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.before_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.before_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def before_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.before_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def below_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.below_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def below_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.below_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def below_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.below_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def front_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.front_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def front_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.front_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def front_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.front_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.left_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.left_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.left_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overabove_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overabove_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overabove_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.overabove_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overabove_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overabove_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overafter_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.overafter_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overafter_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overafter_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overback_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overback_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overback_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.overback_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overback_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overback_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overbefore_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.overbefore_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbefore_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overbefore_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbelow_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overbelow_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbelow_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.overbelow_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overbelow_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overbelow_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overfront_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overfront_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overfront_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.overfront_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overfront_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overfront_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overleft_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.overleft_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overleft_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.overright_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.overright_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.overright_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_stbox_tspatial(
    box: Annotated[cdata, "const STBox *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    box_converted = _ffi.cast("const STBox *", box)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.right_stbox_tspatial(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_tspatial_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.right_tspatial_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_tspatial_tspatial(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[bool, "bool"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.right_tspatial_tspatial(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def acontains_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.acontains_geo_tgeo(gs_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def acontains_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.acontains_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def acontains_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.acontains_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adisjoint_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.adisjoint_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adisjoint_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.adisjoint_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adwithin_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"], dist: float
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.adwithin_tgeo_geo(temp_converted, gs_converted, dist)
    _check_error()
    return result if result != _ffi.NULL else None


def adwithin_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"], dist: float
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.adwithin_tgeo_tgeo(temp1_converted, temp2_converted, dist)
    _check_error()
    return result if result != _ffi.NULL else None


def aintersects_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.aintersects_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def aintersects_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.aintersects_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def atouches_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.atouches_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def atouches_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.atouches_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def atouches_tpoint_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.atouches_tpoint_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def econtains_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.econtains_geo_tgeo(gs_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def econtains_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.econtains_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def econtains_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.econtains_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ecovers_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ecovers_geo_tgeo(gs_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ecovers_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.ecovers_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ecovers_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.ecovers_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def edisjoint_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.edisjoint_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def edisjoint_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.edisjoint_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def edwithin_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"], dist: float
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.edwithin_tgeo_geo(temp_converted, gs_converted, dist)
    _check_error()
    return result if result != _ffi.NULL else None


def edwithin_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"], dist: float
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.edwithin_tgeo_tgeo(temp1_converted, temp2_converted, dist)
    _check_error()
    return result if result != _ffi.NULL else None


def eintersects_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.eintersects_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def eintersects_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.eintersects_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def etouches_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.etouches_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def etouches_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.etouches_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def etouches_tpoint_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.etouches_tpoint_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tcontains_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tcontains_geo_tgeo(gs_converted, temp_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tcontains_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.tcontains_tgeo_geo(temp_converted, gs_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tcontains_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tcontains_tgeo_tgeo(temp1_converted, temp2_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tcovers_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tcovers_geo_tgeo(gs_converted, temp_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tcovers_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.tcovers_tgeo_geo(temp_converted, gs_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tcovers_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tcovers_tgeo_tgeo(temp1_converted, temp2_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tdisjoint_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tdisjoint_geo_tgeo(gs_converted, temp_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tdisjoint_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.tdisjoint_tgeo_geo(temp_converted, gs_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tdisjoint_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tdisjoint_tgeo_tgeo(temp1_converted, temp2_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tdwithin_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"],
    temp: Annotated[cdata, "const Temporal *"],
    dist: float,
    restr: bool,
    atvalue: bool,
) -> Annotated[cdata, "Temporal *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tdwithin_geo_tgeo(gs_converted, temp_converted, dist, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tdwithin_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"],
    gs: Annotated[cdata, "const GSERIALIZED *"],
    dist: float,
    restr: bool,
    atvalue: bool,
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.tdwithin_tgeo_geo(temp_converted, gs_converted, dist, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tdwithin_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"],
    temp2: Annotated[cdata, "const Temporal *"],
    dist: float,
    restr: bool,
    atvalue: bool,
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tdwithin_tgeo_tgeo(temp1_converted, temp2_converted, dist, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tintersects_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tintersects_geo_tgeo(gs_converted, temp_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tintersects_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.tintersects_tgeo_geo(temp_converted, gs_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tintersects_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tintersects_tgeo_tgeo(temp1_converted, temp2_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def ttouches_geo_tgeo(
    gs: Annotated[cdata, "const GSERIALIZED *"], temp: Annotated[cdata, "const Temporal *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ttouches_geo_tgeo(gs_converted, temp_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def ttouches_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.ttouches_tgeo_geo(temp_converted, gs_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def ttouches_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"], restr: bool, atvalue: bool
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.ttouches_tgeo_tgeo(temp1_converted, temp2_converted, restr, atvalue)
    _check_error()
    return result if result != _ffi.NULL else None


def tdistance_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.tdistance_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tdistance_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tdistance_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_stbox_geo(
    box: Annotated[cdata, "const STBox *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[float, "double"]:
    box_converted = _ffi.cast("const STBox *", box)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.nad_stbox_geo(box_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[float, "double"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    result = _lib.nad_stbox_stbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.nad_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tgeo_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.nad_tgeo_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[float, "double"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.nad_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nai_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "TInstant *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.nai_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nai_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "TInstant *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.nai_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def shortestline_tgeo_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "GSERIALIZED *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.shortestline_tgeo_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def shortestline_tgeo_tgeo(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "GSERIALIZED *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.shortestline_tgeo_tgeo(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_tcentroid_finalfn(state: Annotated[cdata, "SkipList *"]) -> Annotated[cdata, "Temporal *"]:
    state_converted = _ffi.cast("SkipList *", state)
    result = _lib.tpoint_tcentroid_finalfn(state_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_tcentroid_transfn(
    state: Annotated[cdata, "SkipList *"], temp: Annotated[cdata, "Temporal *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state)
    temp_converted = _ffi.cast("Temporal *", temp)
    result = _lib.tpoint_tcentroid_transfn(state_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tspatial_extent_transfn(
    box: Annotated[cdata, "STBox *"] | None, temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "STBox *"]:
    box_converted = _ffi.cast("STBox *", box) if box is not None else _ffi.NULL
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tspatial_extent_transfn(box_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_get_space_tile(
    point: Annotated[cdata, "const GSERIALIZED *"],
    xsize: float,
    ysize: float,
    zsize: float,
    sorigin: Annotated[cdata, "const GSERIALIZED *"],
) -> Annotated[cdata, "STBox *"]:
    point_converted = _ffi.cast("const GSERIALIZED *", point)
    sorigin_converted = _ffi.cast("const GSERIALIZED *", sorigin)
    result = _lib.stbox_get_space_tile(point_converted, xsize, ysize, zsize, sorigin_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_get_space_time_tile(
    point: Annotated[cdata, "const GSERIALIZED *"],
    t: int,
    xsize: float,
    ysize: float,
    zsize: float,
    duration: Annotated[cdata, "const Interval *"],
    sorigin: Annotated[cdata, "const GSERIALIZED *"],
    torigin: int,
) -> Annotated[cdata, "STBox *"]:
    point_converted = _ffi.cast("const GSERIALIZED *", point)
    t_converted = _ffi.cast("TimestampTz", t)
    duration_converted = _ffi.cast("const Interval *", duration)
    sorigin_converted = _ffi.cast("const GSERIALIZED *", sorigin)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    result = _lib.stbox_get_space_time_tile(
        point_converted, t_converted, xsize, ysize, zsize, duration_converted, sorigin_converted, torigin_converted
    )
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_get_time_tile(
    t: int, duration: Annotated[cdata, "const Interval *"], torigin: int
) -> Annotated[cdata, "STBox *"]:
    t_converted = _ffi.cast("TimestampTz", t)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    result = _lib.stbox_get_time_tile(t_converted, duration_converted, torigin_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_space_tiles(
    bounds: Annotated[cdata, "const STBox *"],
    xsize: float,
    ysize: float,
    zsize: float,
    sorigin: Annotated[cdata, "const GSERIALIZED *"],
    border_inc: bool,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "STBox *"]:
    bounds_converted = _ffi.cast("const STBox *", bounds)
    sorigin_converted = _ffi.cast("const GSERIALIZED *", sorigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.stbox_space_tiles(
        bounds_converted, xsize, ysize, zsize, sorigin_converted, border_inc, count_converted
    )
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_space_time_tiles(
    bounds: Annotated[cdata, "const STBox *"],
    xsize: float,
    ysize: float,
    zsize: float,
    duration: Annotated[cdata, "const Interval *"] | None,
    sorigin: Annotated[cdata, "const GSERIALIZED *"],
    torigin: int,
    border_inc: bool,
) -> tuple[Annotated[cdata, "STBox *"], Annotated[cdata, "int"]]:
    bounds_converted = _ffi.cast("const STBox *", bounds)
    duration_converted = _ffi.cast("const Interval *", duration) if duration is not None else _ffi.NULL
    sorigin_converted = _ffi.cast("const GSERIALIZED *", sorigin)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    count = _ffi.new("int *")
    result = _lib.stbox_space_time_tiles(
        bounds_converted,
        xsize,
        ysize,
        zsize,
        duration_converted,
        sorigin_converted,
        torigin_converted,
        border_inc,
        count,
    )
    _check_error()
    return result if result != _ffi.NULL else None, count[0]


def stbox_time_tiles(
    bounds: Annotated[cdata, "const STBox *"],
    duration: Annotated[cdata, "const Interval *"],
    torigin: int,
    border_inc: bool,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "STBox *"]:
    bounds_converted = _ffi.cast("const STBox *", bounds)
    duration_converted = _ffi.cast("const Interval *", duration)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.stbox_time_tiles(bounds_converted, duration_converted, torigin_converted, border_inc, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_space_split(
    temp: Annotated[cdata, "const Temporal *"],
    xsize: float,
    ysize: float,
    zsize: float,
    sorigin: Annotated[cdata, "const GSERIALIZED *"],
    bitmatrix: bool,
    border_inc: bool,
) -> tuple[Annotated[cdata, "Temporal **"], Annotated[list, "GSERIALIZED ***"], Annotated[cdata, "int"]]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    sorigin_converted = _ffi.cast("const GSERIALIZED *", sorigin)
    space_bins = _ffi.new("GSERIALIZED ***")
    count = _ffi.new("int *")
    result = _lib.tgeo_space_split(
        temp_converted, xsize, ysize, zsize, sorigin_converted, bitmatrix, border_inc, space_bins, count
    )
    _check_error()
    return result if result != _ffi.NULL else None, space_bins[0], count[0]


def tgeo_space_time_split(
    temp: Annotated[cdata, "const Temporal *"],
    xsize: float,
    ysize: float,
    zsize: float,
    duration: Annotated[cdata, "const Interval *"],
    sorigin: Annotated[cdata, "const GSERIALIZED *"],
    torigin: int,
    bitmatrix: bool,
    border_inc: bool,
) -> tuple[
    Annotated[cdata, "Temporal **"],
    Annotated[list, "GSERIALIZED ***"],
    Annotated[list, "TimestampTz *"],
    Annotated[cdata, "int"],
]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    duration_converted = _ffi.cast("const Interval *", duration)
    sorigin_converted = _ffi.cast("const GSERIALIZED *", sorigin)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    space_bins = _ffi.new("GSERIALIZED ***")
    time_bins = _ffi.new("TimestampTz **")
    count = _ffi.new("int *")
    result = _lib.tgeo_space_time_split(
        temp_converted,
        xsize,
        ysize,
        zsize,
        duration_converted,
        sorigin_converted,
        torigin_converted,
        bitmatrix,
        border_inc,
        space_bins,
        time_bins,
        count,
    )
    _check_error()
    return result if result != _ffi.NULL else None, space_bins[0], time_bins[0], count[0]


def geo_cluster_kmeans(
    geoms: Annotated[list, "const GSERIALIZED **"],
    ngeoms: Annotated[cdata, "uint32_t"],
    k: Annotated[cdata, "uint32_t"],
) -> Annotated[cdata, "int *"]:
    geoms_converted = [_ffi.cast("const GSERIALIZED *", x) for x in geoms]
    ngeoms_converted = _ffi.cast("uint32_t", ngeoms)
    k_converted = _ffi.cast("uint32_t", k)
    result = _lib.geo_cluster_kmeans(geoms_converted, ngeoms_converted, k_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_cluster_dbscan(
    geoms: Annotated[list, "const GSERIALIZED **"],
    ngeoms: Annotated[cdata, "uint32_t"],
    tolerance: float,
    minpoints: int,
) -> Annotated[cdata, "uint32_t *"]:
    geoms_converted = [_ffi.cast("const GSERIALIZED *", x) for x in geoms]
    ngeoms_converted = _ffi.cast("uint32_t", ngeoms)
    result = _lib.geo_cluster_dbscan(geoms_converted, ngeoms_converted, tolerance, minpoints)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_cluster_intersecting(
    geoms: Annotated[list, "const GSERIALIZED **"],
    ngeoms: Annotated[cdata, "uint32_t"],
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "GSERIALIZED **"]:
    geoms_converted = [_ffi.cast("const GSERIALIZED *", x) for x in geoms]
    ngeoms_converted = _ffi.cast("uint32_t", ngeoms)
    count_converted = _ffi.cast("int *", count)
    result = _lib.geo_cluster_intersecting(geoms_converted, ngeoms_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geo_cluster_within(
    geoms: Annotated[list, "const GSERIALIZED **"],
    ngeoms: Annotated[cdata, "uint32_t"],
    tolerance: float,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "GSERIALIZED **"]:
    geoms_converted = [_ffi.cast("const GSERIALIZED *", x) for x in geoms]
    ngeoms_converted = _ffi.cast("uint32_t", ngeoms)
    count_converted = _ffi.cast("int *", count)
    result = _lib.geo_cluster_within(geoms_converted, ngeoms_converted, tolerance, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def gsl_get_generation_rng() -> Annotated[cdata, "gsl_rng *"]:
    result = _lib.gsl_get_generation_rng()
    _check_error()
    return result if result != _ffi.NULL else None


def gsl_get_aggregation_rng() -> Annotated[cdata, "gsl_rng *"]:
    result = _lib.gsl_get_aggregation_rng()
    _check_error()
    return result if result != _ffi.NULL else None


def datum_ceil(d: Annotated[cdata, "Datum"]) -> Annotated[cdata, "Datum"]:
    d_converted = _ffi.cast("Datum", d)
    result = _lib.datum_ceil(d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datum_degrees(d: Annotated[cdata, "Datum"], normalize: Annotated[cdata, "Datum"]) -> Annotated[cdata, "Datum"]:
    d_converted = _ffi.cast("Datum", d)
    normalize_converted = _ffi.cast("Datum", normalize)
    result = _lib.datum_degrees(d_converted, normalize_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datum_float_round(value: Annotated[cdata, "Datum"], size: Annotated[cdata, "Datum"]) -> Annotated[cdata, "Datum"]:
    value_converted = _ffi.cast("Datum", value)
    size_converted = _ffi.cast("Datum", size)
    result = _lib.datum_float_round(value_converted, size_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datum_floor(d: Annotated[cdata, "Datum"]) -> Annotated[cdata, "Datum"]:
    d_converted = _ffi.cast("Datum", d)
    result = _lib.datum_floor(d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datum_hash(d: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"]) -> Annotated[int, "uint32"]:
    d_converted = _ffi.cast("Datum", d)
    basetype_converted = _ffi.cast("meosType", basetype)
    result = _lib.datum_hash(d_converted, basetype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datum_hash_extended(
    d: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"], seed: int
) -> Annotated[int, "uint64"]:
    d_converted = _ffi.cast("Datum", d)
    basetype_converted = _ffi.cast("meosType", basetype)
    seed_converted = _ffi.cast("uint64", seed)
    result = _lib.datum_hash_extended(d_converted, basetype_converted, seed_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datum_radians(d: Annotated[cdata, "Datum"]) -> Annotated[cdata, "Datum"]:
    d_converted = _ffi.cast("Datum", d)
    result = _lib.datum_radians(d_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def floatspan_round_set(s: Annotated[cdata, "const Span *"], maxdd: int) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    out_result = _ffi.new("Span *")
    _lib.floatspan_round_set(s_converted, maxdd, out_result)
    _check_error()
    return out_result if out_result != _ffi.NULL else None


def set_in(string: str, basetype: Annotated[cdata, "meosType"]) -> Annotated[cdata, "Set *"]:
    string_converted = string.encode("utf-8")
    basetype_converted = _ffi.cast("meosType", basetype)
    result = _lib.set_in(string_converted, basetype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_out(s: Annotated[cdata, "const Set *"], maxdd: int) -> Annotated[str, "char *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_out(s_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def span_in(string: str, spantype: Annotated[cdata, "meosType"]) -> Annotated[cdata, "Span *"]:
    string_converted = string.encode("utf-8")
    spantype_converted = _ffi.cast("meosType", spantype)
    result = _lib.span_in(string_converted, spantype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_out(s: Annotated[cdata, "const Span *"], maxdd: int) -> Annotated[str, "char *"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.span_out(s_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def spanset_in(string: str, spantype: Annotated[cdata, "meosType"]) -> Annotated[cdata, "SpanSet *"]:
    string_converted = string.encode("utf-8")
    spantype_converted = _ffi.cast("meosType", spantype)
    result = _lib.spanset_in(string_converted, spantype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_out(ss: Annotated[cdata, "const SpanSet *"], maxdd: int) -> Annotated[str, "char *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_out(ss_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def set_make(
    values: Annotated[cdata, "const Datum *"], count: int, basetype: Annotated[cdata, "meosType"], order: bool
) -> Annotated[cdata, "Set *"]:
    values_converted = _ffi.cast("const Datum *", values)
    basetype_converted = _ffi.cast("meosType", basetype)
    result = _lib.set_make(values_converted, count, basetype_converted, order)
    _check_error()
    return result if result != _ffi.NULL else None


def set_make_exp(
    values: Annotated[cdata, "const Datum *"],
    count: int,
    maxcount: int,
    basetype: Annotated[cdata, "meosType"],
    order: bool,
) -> Annotated[cdata, "Set *"]:
    values_converted = _ffi.cast("const Datum *", values)
    basetype_converted = _ffi.cast("meosType", basetype)
    result = _lib.set_make_exp(values_converted, count, maxcount, basetype_converted, order)
    _check_error()
    return result if result != _ffi.NULL else None


def set_make_free(
    values: Annotated[cdata, "Datum *"], count: int, basetype: Annotated[cdata, "meosType"], order: bool
) -> Annotated[cdata, "Set *"]:
    values_converted = _ffi.cast("Datum *", values)
    basetype_converted = _ffi.cast("meosType", basetype)
    result = _lib.set_make_free(values_converted, count, basetype_converted, order)
    _check_error()
    return result if result != _ffi.NULL else None


def span_make(
    lower: Annotated[cdata, "Datum"],
    upper: Annotated[cdata, "Datum"],
    lower_inc: bool,
    upper_inc: bool,
    basetype: Annotated[cdata, "meosType"],
) -> Annotated[cdata, "Span *"]:
    lower_converted = _ffi.cast("Datum", lower)
    upper_converted = _ffi.cast("Datum", upper)
    basetype_converted = _ffi.cast("meosType", basetype)
    result = _lib.span_make(lower_converted, upper_converted, lower_inc, upper_inc, basetype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_set(
    lower: Annotated[cdata, "Datum"],
    upper: Annotated[cdata, "Datum"],
    lower_inc: bool,
    upper_inc: bool,
    basetype: Annotated[cdata, "meosType"],
    spantype: Annotated[cdata, "meosType"],
    s: Annotated[cdata, "Span *"],
) -> Annotated[None, "void"]:
    lower_converted = _ffi.cast("Datum", lower)
    upper_converted = _ffi.cast("Datum", upper)
    basetype_converted = _ffi.cast("meosType", basetype)
    spantype_converted = _ffi.cast("meosType", spantype)
    s_converted = _ffi.cast("Span *", s)
    _lib.span_set(
        lower_converted, upper_converted, lower_inc, upper_inc, basetype_converted, spantype_converted, s_converted
    )
    _check_error()


def spanset_make_exp(
    spans: Annotated[cdata, "Span *"], count: int, maxcount: int, normalize: bool, order: bool
) -> Annotated[cdata, "SpanSet *"]:
    spans_converted = _ffi.cast("Span *", spans)
    result = _lib.spanset_make_exp(spans_converted, count, maxcount, normalize, order)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_make_free(
    spans: Annotated[cdata, "Span *"], count: int, normalize: bool, order: bool
) -> Annotated[cdata, "SpanSet *"]:
    spans_converted = _ffi.cast("Span *", spans)
    result = _lib.spanset_make_free(spans_converted, count, normalize, order)
    _check_error()
    return result if result != _ffi.NULL else None


def set_span(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_span(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_spanset(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_spanset(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def value_set_span(
    value: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"], s: Annotated[cdata, "Span *"]
) -> Annotated[None, "void"]:
    value_converted = _ffi.cast("Datum", value)
    basetype_converted = _ffi.cast("meosType", basetype)
    s_converted = _ffi.cast("Span *", s)
    _lib.value_set_span(value_converted, basetype_converted, s_converted)
    _check_error()


def value_set(d: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"]) -> Annotated[cdata, "Set *"]:
    d_converted = _ffi.cast("Datum", d)
    basetype_converted = _ffi.cast("meosType", basetype)
    result = _lib.value_set(d_converted, basetype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def value_span(d: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"]) -> Annotated[cdata, "Span *"]:
    d_converted = _ffi.cast("Datum", d)
    basetype_converted = _ffi.cast("meosType", basetype)
    result = _lib.value_span(d_converted, basetype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def value_spanset(
    d: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"]
) -> Annotated[cdata, "SpanSet *"]:
    d_converted = _ffi.cast("Datum", d)
    basetype_converted = _ffi.cast("meosType", basetype)
    result = _lib.value_spanset(d_converted, basetype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def numspan_width(s: Annotated[cdata, "const Span *"]) -> Annotated[cdata, "Datum"]:
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.numspan_width(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def numspanset_width(ss: Annotated[cdata, "const SpanSet *"], boundspan: bool) -> Annotated[cdata, "Datum"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.numspanset_width(ss_converted, boundspan)
    _check_error()
    return result if result != _ffi.NULL else None


def set_end_value(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Datum"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_end_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_mem_size(s: Annotated[cdata, "const Set *"]) -> Annotated[int, "int"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_mem_size(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_set_subspan(s: Annotated[cdata, "const Set *"], minidx: int, maxidx: int) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Set *", s)
    out_result = _ffi.new("Span *")
    _lib.set_set_subspan(s_converted, minidx, maxidx, out_result)
    _check_error()
    return out_result if out_result != _ffi.NULL else None


def set_set_span(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Set *", s)
    out_result = _ffi.new("Span *")
    _lib.set_set_span(s_converted, out_result)
    _check_error()
    return out_result if out_result != _ffi.NULL else None


def set_start_value(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Datum"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_start_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_value_n(s: Annotated[cdata, "const Set *"], n: int) -> Annotated[cdata, "Datum *"]:
    s_converted = _ffi.cast("const Set *", s)
    out_result = _ffi.new("Datum *")
    result = _lib.set_value_n(s_converted, n, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def set_vals(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Datum *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_vals(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def set_values(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Datum *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_values(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_lower(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "Datum"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_lower(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_mem_size(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[int, "int"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_mem_size(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_sps(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "const Span **"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_sps(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_upper(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "Datum"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_upper(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def datespan_set_tstzspan(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "Span *"]
) -> Annotated[None, "void"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("Span *", s2)
    _lib.datespan_set_tstzspan(s1_converted, s2_converted)
    _check_error()


def floatspan_set_intspan(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "Span *"]
) -> Annotated[None, "void"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("Span *", s2)
    _lib.floatspan_set_intspan(s1_converted, s2_converted)
    _check_error()


def intspan_set_floatspan(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "Span *"]
) -> Annotated[None, "void"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("Span *", s2)
    _lib.intspan_set_floatspan(s1_converted, s2_converted)
    _check_error()


def numset_shift_scale(
    s: Annotated[cdata, "const Set *"],
    shift: Annotated[cdata, "Datum"],
    width: Annotated[cdata, "Datum"],
    hasshift: bool,
    haswidth: bool,
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    shift_converted = _ffi.cast("Datum", shift)
    width_converted = _ffi.cast("Datum", width)
    result = _lib.numset_shift_scale(s_converted, shift_converted, width_converted, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def numspan_shift_scale(
    s: Annotated[cdata, "const Span *"],
    shift: Annotated[cdata, "Datum"],
    width: Annotated[cdata, "Datum"],
    hasshift: bool,
    haswidth: bool,
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    shift_converted = _ffi.cast("Datum", shift)
    width_converted = _ffi.cast("Datum", width)
    result = _lib.numspan_shift_scale(s_converted, shift_converted, width_converted, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def numspanset_shift_scale(
    ss: Annotated[cdata, "const SpanSet *"],
    shift: Annotated[cdata, "Datum"],
    width: Annotated[cdata, "Datum"],
    hasshift: bool,
    haswidth: bool,
) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    shift_converted = _ffi.cast("Datum", shift)
    width_converted = _ffi.cast("Datum", width)
    result = _lib.numspanset_shift_scale(ss_converted, shift_converted, width_converted, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def set_compact(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.set_compact(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_expand(s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "Span *"]) -> Annotated[None, "void"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("Span *", s2)
    _lib.span_expand(s1_converted, s2_converted)
    _check_error()


def spanset_compact(ss: Annotated[cdata, "const SpanSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.spanset_compact(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_expand_value(
    box: Annotated[cdata, "const TBox *"], value: Annotated[cdata, "Datum"], basetyp: Annotated[cdata, "meosType"]
) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("const TBox *", box)
    value_converted = _ffi.cast("Datum", value)
    basetyp_converted = _ffi.cast("meosType", basetyp)
    result = _lib.tbox_expand_value(box_converted, value_converted, basetyp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def textcat_textset_text_int(s: Annotated[cdata, "const Set *"], txt: str, invert: bool) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    txt_converted = cstring2text(txt)
    result = _lib.textcat_textset_text_int(s_converted, txt_converted, invert)
    _check_error()
    return result if result != _ffi.NULL else None


def tstzspan_set_datespan(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "Span *"]
) -> Annotated[None, "void"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("Span *", s2)
    _lib.tstzspan_set_datespan(s1_converted, s2_converted)
    _check_error()


def adjacent_span_value(
    s: Annotated[cdata, "const Span *"], value: Annotated[cdata, "Datum"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.adjacent_span_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_spanset_value(
    ss: Annotated[cdata, "const SpanSet *"], value: Annotated[cdata, "Datum"]
) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.adjacent_spanset_value(ss_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def adjacent_value_spanset(
    value: Annotated[cdata, "Datum"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.adjacent_value_spanset(value_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_value_set(
    value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Set *"]
) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.contained_value_set(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_value_span(
    value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.contained_value_span(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_value_spanset(
    value: Annotated[cdata, "Datum"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.contained_value_spanset(value_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_set_value(s: Annotated[cdata, "const Set *"], value: Annotated[cdata, "Datum"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.contains_set_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_span_value(
    s: Annotated[cdata, "const Span *"], value: Annotated[cdata, "Datum"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.contains_span_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_spanset_value(
    ss: Annotated[cdata, "const SpanSet *"], value: Annotated[cdata, "Datum"]
) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.contains_spanset_value(ss_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ovadj_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.ovadj_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_set_value(s: Annotated[cdata, "const Set *"], value: Annotated[cdata, "Datum"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.left_set_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_span_value(s: Annotated[cdata, "const Span *"], value: Annotated[cdata, "Datum"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.left_span_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_spanset_value(
    ss: Annotated[cdata, "const SpanSet *"], value: Annotated[cdata, "Datum"]
) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.left_spanset_value(ss_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_value_set(value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.left_value_set(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_value_span(value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.left_value_span(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def left_value_spanset(
    value: Annotated[cdata, "Datum"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.left_value_spanset(value_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def lfnadj_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.lfnadj_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_set_value(s: Annotated[cdata, "const Set *"], value: Annotated[cdata, "Datum"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.overleft_set_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_span_value(
    s: Annotated[cdata, "const Span *"], value: Annotated[cdata, "Datum"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.overleft_span_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_spanset_value(
    ss: Annotated[cdata, "const SpanSet *"], value: Annotated[cdata, "Datum"]
) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.overleft_spanset_value(ss_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_value_set(value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overleft_value_set(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_value_span(
    value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overleft_value_span(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overleft_value_spanset(
    value: Annotated[cdata, "Datum"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overleft_value_spanset(value_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_set_value(
    s: Annotated[cdata, "const Set *"], value: Annotated[cdata, "Datum"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.overright_set_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_span_value(
    s: Annotated[cdata, "const Span *"], value: Annotated[cdata, "Datum"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.overright_span_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_spanset_value(
    ss: Annotated[cdata, "const SpanSet *"], value: Annotated[cdata, "Datum"]
) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.overright_spanset_value(ss_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_value_set(
    value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Set *"]
) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.overright_value_set(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_value_span(
    value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Span *"]
) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.overright_value_span(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def overright_value_spanset(
    value: Annotated[cdata, "Datum"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.overright_value_spanset(value_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_value_set(value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Set *"]) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.right_value_set(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_set_value(s: Annotated[cdata, "const Set *"], value: Annotated[cdata, "Datum"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.right_set_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_value_span(value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Span *"]) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.right_value_span(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_value_spanset(
    value: Annotated[cdata, "Datum"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[bool, "bool"]:
    value_converted = _ffi.cast("Datum", value)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.right_value_spanset(value_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_span_value(s: Annotated[cdata, "const Span *"], value: Annotated[cdata, "Datum"]) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Span *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.right_span_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def right_spanset_value(
    ss: Annotated[cdata, "const SpanSet *"], value: Annotated[cdata, "Datum"]
) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.right_spanset_value(ss_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def bbox_union_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "Span *"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    out_result = _ffi.new("Span *")
    _lib.bbox_union_span_span(s1_converted, s2_converted, out_result)
    _check_error()
    return out_result if out_result != _ffi.NULL else None


def inter_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "Span *"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    out_result = _ffi.new("Span *")
    result = _lib.inter_span_span(s1_converted, s2_converted, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def intersection_set_value(
    s: Annotated[cdata, "const Set *"], value: Annotated[cdata, "Datum"]
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.intersection_set_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_span_value(
    s: Annotated[cdata, "const Span *"], value: Annotated[cdata, "Datum"]
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.intersection_span_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_spanset_value(
    ss: Annotated[cdata, "const SpanSet *"], value: Annotated[cdata, "Datum"]
) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.intersection_spanset_value(ss_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_value_set(
    value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Set *"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intersection_value_set(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_value_span(
    value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "Span *"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.intersection_value_span(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_value_spanset(
    value: Annotated[cdata, "Datum"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "SpanSet *"]:
    value_converted = _ffi.cast("Datum", value)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.intersection_value_spanset(value_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def mi_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "Span *"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    out_result = _ffi.new("Span *")
    result = _lib.mi_span_span(s1_converted, s2_converted, out_result)
    _check_error()
    return out_result, result if out_result != _ffi.NULL else None


def minus_set_value(s: Annotated[cdata, "const Set *"], value: Annotated[cdata, "Datum"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.minus_set_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_span_value(
    s: Annotated[cdata, "const Span *"], value: Annotated[cdata, "Datum"]
) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.minus_span_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_spanset_value(
    ss: Annotated[cdata, "const SpanSet *"], value: Annotated[cdata, "Datum"]
) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.minus_spanset_value(ss_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_value_set(value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.minus_value_set(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_value_span(
    value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "SpanSet *"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.minus_value_span(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_value_spanset(
    value: Annotated[cdata, "Datum"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "SpanSet *"]:
    value_converted = _ffi.cast("Datum", value)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.minus_value_spanset(value_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def super_union_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "Span *"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.super_union_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_set_value(s: Annotated[cdata, "const Set *"], value: Annotated[cdata, "Datum"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.union_set_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_span_value(
    s: Annotated[cdata, "const Span *"], value: Annotated[cdata, "Datum"]
) -> Annotated[cdata, "SpanSet *"]:
    s_converted = _ffi.cast("const Span *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.union_span_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_spanset_value(
    ss: Annotated[cdata, "const SpanSet *"], value: Annotated[cdata, "Datum"]
) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.union_spanset_value(ss_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_value_set(value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.union_value_set(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_value_span(
    value: Annotated[cdata, "Datum"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "SpanSet *"]:
    value_converted = _ffi.cast("Datum", value)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.union_value_span(value_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_value_spanset(
    value: Annotated[cdata, "Datum"], ss: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "SpanSet *"]:
    value_converted = _ffi.cast("Datum", value)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.union_value_spanset(value_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_set_set(
    s1: Annotated[cdata, "const Set *"], s2: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Datum"]:
    s1_converted = _ffi.cast("const Set *", s1)
    s2_converted = _ffi.cast("const Set *", s2)
    result = _lib.distance_set_set(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_set_value(
    s: Annotated[cdata, "const Set *"], value: Annotated[cdata, "Datum"]
) -> Annotated[cdata, "Datum"]:
    s_converted = _ffi.cast("const Set *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.distance_set_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_span_span(
    s1: Annotated[cdata, "const Span *"], s2: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "Datum"]:
    s1_converted = _ffi.cast("const Span *", s1)
    s2_converted = _ffi.cast("const Span *", s2)
    result = _lib.distance_span_span(s1_converted, s2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_span_value(
    s: Annotated[cdata, "const Span *"], value: Annotated[cdata, "Datum"]
) -> Annotated[cdata, "Datum"]:
    s_converted = _ffi.cast("const Span *", s)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.distance_span_value(s_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_spanset_span(
    ss: Annotated[cdata, "const SpanSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "Datum"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.distance_spanset_span(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_spanset_spanset(
    ss1: Annotated[cdata, "const SpanSet *"], ss2: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "Datum"]:
    ss1_converted = _ffi.cast("const SpanSet *", ss1)
    ss2_converted = _ffi.cast("const SpanSet *", ss2)
    result = _lib.distance_spanset_spanset(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_spanset_value(
    ss: Annotated[cdata, "const SpanSet *"], value: Annotated[cdata, "Datum"]
) -> Annotated[cdata, "Datum"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.distance_spanset_value(ss_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def distance_value_value(
    l: Annotated[cdata, "Datum"], r: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"]
) -> Annotated[cdata, "Datum"]:
    l_converted = _ffi.cast("Datum", l)
    r_converted = _ffi.cast("Datum", r)
    basetype_converted = _ffi.cast("meosType", basetype)
    result = _lib.distance_value_value(l_converted, r_converted, basetype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanbase_extent_transfn(
    state: Annotated[cdata, "Span *"], value: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"]
) -> Annotated[cdata, "Span *"]:
    state_converted = _ffi.cast("Span *", state)
    value_converted = _ffi.cast("Datum", value)
    basetype_converted = _ffi.cast("meosType", basetype)
    result = _lib.spanbase_extent_transfn(state_converted, value_converted, basetype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def value_union_transfn(
    state: Annotated[cdata, "Set *"], value: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"]
) -> Annotated[cdata, "Set *"]:
    state_converted = _ffi.cast("Set *", state)
    value_converted = _ffi.cast("Datum", value)
    basetype_converted = _ffi.cast("meosType", basetype)
    result = _lib.value_union_transfn(state_converted, value_converted, basetype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def number_tstzspan_to_tbox(
    d: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "TBox *"]:
    d_converted = _ffi.cast("Datum", d)
    basetype_converted = _ffi.cast("meosType", basetype)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.number_tstzspan_to_tbox(d_converted, basetype_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def number_timestamptz_to_tbox(
    d: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"], t: int
) -> Annotated[cdata, "TBox *"]:
    d_converted = _ffi.cast("Datum", d)
    basetype_converted = _ffi.cast("meosType", basetype)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.number_timestamptz_to_tbox(d_converted, basetype_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_set(
    s: Annotated[cdata, "const Span *"], p: Annotated[cdata, "const Span *"], box: Annotated[cdata, "TBox *"]
) -> Annotated[None, "void"]:
    s_converted = _ffi.cast("const Span *", s)
    p_converted = _ffi.cast("const Span *", p)
    box_converted = _ffi.cast("TBox *", box)
    _lib.tbox_set(s_converted, p_converted, box_converted)
    _check_error()


def float_set_tbox(d: float, box: Annotated[cdata, "TBox *"]) -> Annotated[None, "void"]:
    box_converted = _ffi.cast("TBox *", box)
    _lib.float_set_tbox(d, box_converted)
    _check_error()


def int_set_tbox(i: int, box: Annotated[cdata, "TBox *"]) -> Annotated[None, "void"]:
    box_converted = _ffi.cast("TBox *", box)
    _lib.int_set_tbox(i, box_converted)
    _check_error()


def number_set_tbox(
    d: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"], box: Annotated[cdata, "TBox *"]
) -> Annotated[None, "void"]:
    d_converted = _ffi.cast("Datum", d)
    basetype_converted = _ffi.cast("meosType", basetype)
    box_converted = _ffi.cast("TBox *", box)
    _lib.number_set_tbox(d_converted, basetype_converted, box_converted)
    _check_error()


def number_tbox(value: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"]) -> Annotated[cdata, "TBox *"]:
    value_converted = _ffi.cast("Datum", value)
    basetype_converted = _ffi.cast("meosType", basetype)
    result = _lib.number_tbox(value_converted, basetype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def numset_set_tbox(s: Annotated[cdata, "const Set *"], box: Annotated[cdata, "TBox *"]) -> Annotated[None, "void"]:
    s_converted = _ffi.cast("const Set *", s)
    box_converted = _ffi.cast("TBox *", box)
    _lib.numset_set_tbox(s_converted, box_converted)
    _check_error()


def numspan_set_tbox(
    span: Annotated[cdata, "const Span *"], box: Annotated[cdata, "TBox *"]
) -> Annotated[None, "void"]:
    span_converted = _ffi.cast("const Span *", span)
    box_converted = _ffi.cast("TBox *", box)
    _lib.numspan_set_tbox(span_converted, box_converted)
    _check_error()


def timestamptz_set_tbox(t: int, box: Annotated[cdata, "TBox *"]) -> Annotated[None, "void"]:
    t_converted = _ffi.cast("TimestampTz", t)
    box_converted = _ffi.cast("TBox *", box)
    _lib.timestamptz_set_tbox(t_converted, box_converted)
    _check_error()


def tstzset_set_tbox(s: Annotated[cdata, "const Set *"], box: Annotated[cdata, "TBox *"]) -> Annotated[None, "void"]:
    s_converted = _ffi.cast("const Set *", s)
    box_converted = _ffi.cast("TBox *", box)
    _lib.tstzset_set_tbox(s_converted, box_converted)
    _check_error()


def tstzspan_set_tbox(s: Annotated[cdata, "const Span *"], box: Annotated[cdata, "TBox *"]) -> Annotated[None, "void"]:
    s_converted = _ffi.cast("const Span *", s)
    box_converted = _ffi.cast("TBox *", box)
    _lib.tstzspan_set_tbox(s_converted, box_converted)
    _check_error()


def tbox_shift_scale_value(
    box: Annotated[cdata, "const TBox *"],
    shift: Annotated[cdata, "Datum"],
    width: Annotated[cdata, "Datum"],
    hasshift: bool,
    haswidth: bool,
) -> Annotated[cdata, "TBox *"]:
    box_converted = _ffi.cast("const TBox *", box)
    shift_converted = _ffi.cast("Datum", shift)
    width_converted = _ffi.cast("Datum", width)
    result = _lib.tbox_shift_scale_value(box_converted, shift_converted, width_converted, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_expand(box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "TBox *"]) -> Annotated[None, "void"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("TBox *", box2)
    _lib.tbox_expand(box1_converted, box2_converted)
    _check_error()


def inter_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[cdata, "TBox *"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    out_result = _ffi.new("TBox *")
    result = _lib.inter_tbox_tbox(box1_converted, box2_converted, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def tboolinst_in(string: str) -> Annotated[cdata, "TInstant *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tboolinst_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tboolseq_in(string: str, interp: InterpolationType) -> Annotated[cdata, "TSequence *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tboolseq_in(string_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tboolseqset_in(string: str) -> Annotated[cdata, "TSequenceSet *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tboolseqset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_in(string: str, temptype: Annotated[cdata, "meosType"]) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    temptype_converted = _ffi.cast("meosType", temptype)
    result = _lib.temporal_in(string_converted, temptype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_out(temp: Annotated[cdata, "const Temporal *"], maxdd: int) -> Annotated[str, "char *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_out(temp_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def temparr_out(temparr: Annotated[list, "const Temporal **"], count: int, maxdd: int) -> Annotated[cdata, "char **"]:
    temparr_converted = [_ffi.cast("const Temporal *", x) for x in temparr]
    result = _lib.temparr_out(temparr_converted, count, maxdd)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloatinst_in(string: str) -> Annotated[cdata, "TInstant *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tfloatinst_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloatseq_in(string: str, interp: InterpolationType) -> Annotated[cdata, "TSequence *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tfloatseq_in(string_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tfloatseqset_in(string: str) -> Annotated[cdata, "TSequenceSet *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tfloatseqset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_in(string: str, temptype: Annotated[cdata, "meosType"]) -> Annotated[cdata, "TInstant *"]:
    string_converted = string.encode("utf-8")
    temptype_converted = _ffi.cast("meosType", temptype)
    result = _lib.tinstant_in(string_converted, temptype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_out(inst: Annotated[cdata, "const TInstant *"], maxdd: int) -> Annotated[str, "char *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    result = _lib.tinstant_out(inst_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def tintinst_in(string: str) -> Annotated[cdata, "TInstant *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tintinst_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tintseq_in(string: str, interp: InterpolationType) -> Annotated[cdata, "TSequence *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tintseq_in(string_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tintseqset_in(string: str) -> Annotated[cdata, "TSequenceSet *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tintseqset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_in(
    string: str, temptype: Annotated[cdata, "meosType"], interp: InterpolationType
) -> Annotated[cdata, "TSequence *"]:
    string_converted = string.encode("utf-8")
    temptype_converted = _ffi.cast("meosType", temptype)
    result = _lib.tsequence_in(string_converted, temptype_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_out(seq: Annotated[cdata, "const TSequence *"], maxdd: int) -> Annotated[str, "char *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_out(seq_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def tsequenceset_in(
    string: str, temptype: Annotated[cdata, "meosType"], interp: InterpolationType
) -> Annotated[cdata, "TSequenceSet *"]:
    string_converted = string.encode("utf-8")
    temptype_converted = _ffi.cast("meosType", temptype)
    result = _lib.tsequenceset_in(string_converted, temptype_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_out(ss: Annotated[cdata, "const TSequenceSet *"], maxdd: int) -> Annotated[str, "char *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_out(ss_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def ttextinst_in(string: str) -> Annotated[cdata, "TInstant *"]:
    string_converted = string.encode("utf-8")
    result = _lib.ttextinst_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ttextseq_in(string: str, interp: InterpolationType) -> Annotated[cdata, "TSequence *"]:
    string_converted = string.encode("utf-8")
    result = _lib.ttextseq_in(string_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def ttextseqset_in(string: str) -> Annotated[cdata, "TSequenceSet *"]:
    string_converted = string.encode("utf-8")
    result = _lib.ttextseqset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_from_mfjson(mfjson: str, temptype: Annotated[cdata, "meosType"]) -> Annotated[cdata, "Temporal *"]:
    mfjson_converted = mfjson.encode("utf-8")
    temptype_converted = _ffi.cast("meosType", temptype)
    result = _lib.temporal_from_mfjson(mfjson_converted, temptype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_from_base_temp(
    value: Annotated[cdata, "Datum"], temptype: Annotated[cdata, "meosType"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    value_converted = _ffi.cast("Datum", value)
    temptype_converted = _ffi.cast("meosType", temptype)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_from_base_temp(value_converted, temptype_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_copy(inst: Annotated[cdata, "const TInstant *"]) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    result = _lib.tinstant_copy(inst_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_make(
    value: Annotated[cdata, "Datum"], temptype: Annotated[cdata, "meosType"], t: int
) -> Annotated[cdata, "TInstant *"]:
    value_converted = _ffi.cast("Datum", value)
    temptype_converted = _ffi.cast("meosType", temptype)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.tinstant_make(value_converted, temptype_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_make_free(
    value: Annotated[cdata, "Datum"], temptype: Annotated[cdata, "meosType"], t: int
) -> Annotated[cdata, "TInstant *"]:
    value_converted = _ffi.cast("Datum", value)
    temptype_converted = _ffi.cast("meosType", temptype)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.tinstant_make_free(value_converted, temptype_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_copy(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "TSequence *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_copy(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_from_base_temp(
    value: Annotated[cdata, "Datum"], temptype: Annotated[cdata, "meosType"], seq: Annotated[cdata, "const TSequence *"]
) -> Annotated[cdata, "TSequence *"]:
    value_converted = _ffi.cast("Datum", value)
    temptype_converted = _ffi.cast("meosType", temptype)
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_from_base_temp(value_converted, temptype_converted, seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_from_base_tstzset(
    value: Annotated[cdata, "Datum"], temptype: Annotated[cdata, "meosType"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "TSequence *"]:
    value_converted = _ffi.cast("Datum", value)
    temptype_converted = _ffi.cast("meosType", temptype)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tsequence_from_base_tstzset(value_converted, temptype_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_from_base_tstzspan(
    value: Annotated[cdata, "Datum"],
    temptype: Annotated[cdata, "meosType"],
    s: Annotated[cdata, "const Span *"],
    interp: InterpolationType,
) -> Annotated[cdata, "TSequence *"]:
    value_converted = _ffi.cast("Datum", value)
    temptype_converted = _ffi.cast("meosType", temptype)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tsequence_from_base_tstzspan(value_converted, temptype_converted, s_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_make_exp(
    instants: Annotated[list, "const TInstant **"],
    count: int,
    maxcount: int,
    lower_inc: bool,
    upper_inc: bool,
    interp: InterpolationType,
    normalize: bool,
) -> Annotated[cdata, "TSequence *"]:
    instants_converted = [_ffi.cast("const TInstant *", x) for x in instants]
    result = _lib.tsequence_make_exp(instants_converted, count, maxcount, lower_inc, upper_inc, interp, normalize)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_make_free(
    instants: Annotated[list, "TInstant **"],
    count: int,
    lower_inc: bool,
    upper_inc: bool,
    interp: InterpolationType,
    normalize: bool,
) -> Annotated[cdata, "TSequence *"]:
    instants_converted = [_ffi.cast("TInstant *", x) for x in instants]
    result = _lib.tsequence_make_free(instants_converted, count, lower_inc, upper_inc, interp, normalize)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_copy(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_copy(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tseqsetarr_to_tseqset(
    seqsets: Annotated[list, "TSequenceSet **"], count: int, totalseqs: int
) -> Annotated[cdata, "TSequenceSet *"]:
    seqsets_converted = [_ffi.cast("TSequenceSet *", x) for x in seqsets]
    result = _lib.tseqsetarr_to_tseqset(seqsets_converted, count, totalseqs)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_from_base_temp(
    value: Annotated[cdata, "Datum"],
    temptype: Annotated[cdata, "meosType"],
    ss: Annotated[cdata, "const TSequenceSet *"],
) -> Annotated[cdata, "TSequenceSet *"]:
    value_converted = _ffi.cast("Datum", value)
    temptype_converted = _ffi.cast("meosType", temptype)
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_from_base_temp(value_converted, temptype_converted, ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_from_base_tstzspanset(
    value: Annotated[cdata, "Datum"],
    temptype: Annotated[cdata, "meosType"],
    ss: Annotated[cdata, "const SpanSet *"],
    interp: InterpolationType,
) -> Annotated[cdata, "TSequenceSet *"]:
    value_converted = _ffi.cast("Datum", value)
    temptype_converted = _ffi.cast("meosType", temptype)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tsequenceset_from_base_tstzspanset(value_converted, temptype_converted, ss_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_make_exp(
    sequences: Annotated[list, "const TSequence **"], count: int, maxcount: int, normalize: bool
) -> Annotated[cdata, "TSequenceSet *"]:
    sequences_converted = [_ffi.cast("const TSequence *", x) for x in sequences]
    result = _lib.tsequenceset_make_exp(sequences_converted, count, maxcount, normalize)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_make_free(
    sequences: Annotated[list, "TSequence **"], count: int, normalize: bool
) -> Annotated[cdata, "TSequenceSet *"]:
    sequences_converted = [_ffi.cast("TSequence *", x) for x in sequences]
    result = _lib.tsequenceset_make_free(sequences_converted, count, normalize)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_set_tstzspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "Span *"]
) -> Annotated[None, "void"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("Span *", s)
    _lib.temporal_set_tstzspan(temp_converted, s_converted)
    _check_error()


def tinstant_set_tstzspan(
    inst: Annotated[cdata, "const TInstant *"], s: Annotated[cdata, "Span *"]
) -> Annotated[None, "void"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    s_converted = _ffi.cast("Span *", s)
    _lib.tinstant_set_tstzspan(inst_converted, s_converted)
    _check_error()


def tnumber_set_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "TBox *"]
) -> Annotated[None, "void"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("TBox *", box)
    _lib.tnumber_set_tbox(temp_converted, box_converted)
    _check_error()


def tnumberinst_set_tbox(
    inst: Annotated[cdata, "const TInstant *"], box: Annotated[cdata, "TBox *"]
) -> Annotated[None, "void"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    box_converted = _ffi.cast("TBox *", box)
    _lib.tnumberinst_set_tbox(inst_converted, box_converted)
    _check_error()


def tnumberseq_set_tbox(
    seq: Annotated[cdata, "const TSequence *"], box: Annotated[cdata, "TBox *"]
) -> Annotated[None, "void"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    box_converted = _ffi.cast("TBox *", box)
    _lib.tnumberseq_set_tbox(seq_converted, box_converted)
    _check_error()


def tnumberseqset_set_tbox(
    ss: Annotated[cdata, "const TSequenceSet *"], box: Annotated[cdata, "TBox *"]
) -> Annotated[None, "void"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    box_converted = _ffi.cast("TBox *", box)
    _lib.tnumberseqset_set_tbox(ss_converted, box_converted)
    _check_error()


def tsequence_set_tstzspan(
    seq: Annotated[cdata, "const TSequence *"], s: Annotated[cdata, "Span *"]
) -> Annotated[None, "void"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    s_converted = _ffi.cast("Span *", s)
    _lib.tsequence_set_tstzspan(seq_converted, s_converted)
    _check_error()


def tsequenceset_set_tstzspan(
    ss: Annotated[cdata, "const TSequenceSet *"], s: Annotated[cdata, "Span *"]
) -> Annotated[None, "void"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    s_converted = _ffi.cast("Span *", s)
    _lib.tsequenceset_set_tstzspan(ss_converted, s_converted)
    _check_error()


def temporal_end_inst(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "const TInstant *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_end_inst(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_end_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Datum"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_end_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_inst_n(temp: Annotated[cdata, "const Temporal *"], n: int) -> Annotated[cdata, "const TInstant *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_inst_n(temp_converted, n)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_instants_p(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "const TInstant **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.temporal_instants_p(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_max_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Datum"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_max_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_mem_size(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "size_t"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_mem_size(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_min_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Datum"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_min_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_sequences_p(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "const TSequence **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.temporal_sequences_p(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_set_bbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "void *"]
) -> Annotated[None, "void"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("void *", box)
    _lib.temporal_set_bbox(temp_converted, box_converted)
    _check_error()


def temporal_start_inst(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "const TInstant *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_start_inst(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_start_value(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Datum"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_start_value(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_values_p(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Datum *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.temporal_values_p(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_value_n(temp: Annotated[cdata, "const Temporal *"], n: int) -> Annotated[cdata, "Datum *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    out_result = _ffi.new("Datum *")
    result = _lib.temporal_value_n(temp_converted, n, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def temporal_values(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Datum *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.temporal_values(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_hash(inst: Annotated[cdata, "const TInstant *"]) -> Annotated[int, "uint32"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    result = _lib.tinstant_hash(inst_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_insts(
    inst: Annotated[cdata, "const TInstant *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "const TInstant **"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tinstant_insts(inst_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_set_bbox(
    inst: Annotated[cdata, "const TInstant *"], box: Annotated[cdata, "void *"]
) -> Annotated[None, "void"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    box_converted = _ffi.cast("void *", box)
    _lib.tinstant_set_bbox(inst_converted, box_converted)
    _check_error()


def tinstant_time(inst: Annotated[cdata, "const TInstant *"]) -> Annotated[cdata, "SpanSet *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    result = _lib.tinstant_time(inst_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_timestamps(
    inst: Annotated[cdata, "const TInstant *"], count: Annotated[cdata, "int *"]
) -> Annotated[int, "TimestampTz *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tinstant_timestamps(inst_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_value_p(inst: Annotated[cdata, "const TInstant *"]) -> Annotated[cdata, "Datum"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    result = _lib.tinstant_value_p(inst_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_value(inst: Annotated[cdata, "const TInstant *"]) -> Annotated[cdata, "Datum"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    result = _lib.tinstant_value(inst_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_value_at_timestamptz(inst: Annotated[cdata, "const TInstant *"], t: int) -> Annotated[cdata, "Datum *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    t_converted = _ffi.cast("TimestampTz", t)
    out_result = _ffi.new("Datum *")
    result = _lib.tinstant_value_at_timestamptz(inst_converted, t_converted, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def tinstant_values_p(
    inst: Annotated[cdata, "const TInstant *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Datum *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tinstant_values_p(inst_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_set_span(
    temp: Annotated[cdata, "const Temporal *"], span: Annotated[cdata, "Span *"]
) -> Annotated[None, "void"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    span_converted = _ffi.cast("Span *", span)
    _lib.tnumber_set_span(temp_converted, span_converted)
    _check_error()


def tnumberinst_valuespans(inst: Annotated[cdata, "const TInstant *"]) -> Annotated[cdata, "SpanSet *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    result = _lib.tnumberinst_valuespans(inst_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseq_valuespans(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "SpanSet *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tnumberseq_valuespans(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseqset_valuespans(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tnumberseqset_valuespans(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_duration(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "Interval *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_duration(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_end_timestamptz(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[int, "TimestampTz"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_end_timestamptz(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_hash(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[int, "uint32"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_hash(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_insts_p(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "const TInstant **"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_insts_p(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_max_inst(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "const TInstant *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_max_inst(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_max_val(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "Datum"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_max_val(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_min_inst(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "const TInstant *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_min_inst(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_min_val(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "Datum"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_min_val(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_segments(
    seq: Annotated[cdata, "const TSequence *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "TSequence **"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tsequence_segments(seq_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_seqs(
    seq: Annotated[cdata, "const TSequence *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "const TSequence **"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tsequence_seqs(seq_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_start_timestamptz(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[int, "TimestampTz"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_start_timestamptz(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_time(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "SpanSet *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_time(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_timestamps(
    seq: Annotated[cdata, "const TSequence *"], count: Annotated[cdata, "int *"]
) -> Annotated[int, "TimestampTz *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tsequence_timestamps(seq_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_value_at_timestamptz(
    seq: Annotated[cdata, "const TSequence *"], t: int, strict: bool
) -> Annotated[cdata, "Datum *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    t_converted = _ffi.cast("TimestampTz", t)
    out_result = _ffi.new("Datum *")
    result = _lib.tsequence_value_at_timestamptz(seq_converted, t_converted, strict, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def tsequence_values_p(
    seq: Annotated[cdata, "const TSequence *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Datum *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tsequence_values_p(seq_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_duration(
    ss: Annotated[cdata, "const TSequenceSet *"], boundspan: bool
) -> Annotated[cdata, "Interval *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_duration(ss_converted, boundspan)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_end_timestamptz(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[int, "TimestampTz"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_end_timestamptz(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_hash(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[int, "uint32"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_hash(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_inst_n(ss: Annotated[cdata, "const TSequenceSet *"], n: int) -> Annotated[cdata, "const TInstant *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_inst_n(ss_converted, n)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_insts_p(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "const TInstant **"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_insts_p(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_max_inst(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "const TInstant *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_max_inst(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_max_val(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "Datum"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_max_val(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_min_inst(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "const TInstant *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_min_inst(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_min_val(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "Datum"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_min_val(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_num_instants(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[int, "int"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_num_instants(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_num_timestamps(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[int, "int"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_num_timestamps(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_segments(
    ss: Annotated[cdata, "const TSequenceSet *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "TSequence **"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tsequenceset_segments(ss_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_sequences_p(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "const TSequence **"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_sequences_p(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_start_timestamptz(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[int, "TimestampTz"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_start_timestamptz(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_time(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "SpanSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_time(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_timestamptz_n(ss: Annotated[cdata, "const TSequenceSet *"], n: int) -> int:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    out_result = _ffi.new("TimestampTz *")
    result = _lib.tsequenceset_timestamptz_n(ss_converted, n, out_result)
    _check_error()
    if result:
        return out_result[0] if out_result[0] != _ffi.NULL else None
    return None


def tsequenceset_timestamps(
    ss: Annotated[cdata, "const TSequenceSet *"], count: Annotated[cdata, "int *"]
) -> Annotated[int, "TimestampTz *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tsequenceset_timestamps(ss_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_value_at_timestamptz(
    ss: Annotated[cdata, "const TSequenceSet *"], t: int, strict: bool
) -> Annotated[cdata, "Datum *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    t_converted = _ffi.cast("TimestampTz", t)
    out_result = _ffi.new("Datum *")
    result = _lib.tsequenceset_value_at_timestamptz(ss_converted, t_converted, strict, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def tsequenceset_value_n(ss: Annotated[cdata, "const TSequenceSet *"], n: int) -> Annotated[cdata, "Datum *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    out_result = _ffi.new("Datum *")
    result = _lib.tsequenceset_value_n(ss_converted, n, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def tsequenceset_values_p(
    ss: Annotated[cdata, "const TSequenceSet *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Datum *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tsequenceset_values_p(ss_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_restart(temp: Annotated[cdata, "Temporal *"], count: int) -> Annotated[None, "void"]:
    temp_converted = _ffi.cast("Temporal *", temp)
    _lib.temporal_restart(temp_converted, count)
    _check_error()


def temporal_tsequence(
    temp: Annotated[cdata, "const Temporal *"], interp: InterpolationType
) -> Annotated[cdata, "TSequence *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_tsequence(temp_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_tsequenceset(
    temp: Annotated[cdata, "const Temporal *"], interp: InterpolationType
) -> Annotated[cdata, "TSequenceSet *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_tsequenceset(temp_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_shift_time(
    inst: Annotated[cdata, "const TInstant *"], interv: Annotated[cdata, "const Interval *"]
) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    interv_converted = _ffi.cast("const Interval *", interv)
    result = _lib.tinstant_shift_time(inst_converted, interv_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_to_tsequence(
    inst: Annotated[cdata, "const TInstant *"], interp: InterpolationType
) -> Annotated[cdata, "TSequence *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    result = _lib.tinstant_to_tsequence(inst_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_to_tsequence_free(
    inst: Annotated[cdata, "TInstant *"], interp: InterpolationType
) -> Annotated[cdata, "TSequence *"]:
    inst_converted = _ffi.cast("TInstant *", inst)
    result = _lib.tinstant_to_tsequence_free(inst_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_to_tsequenceset(
    inst: Annotated[cdata, "const TInstant *"], interp: InterpolationType
) -> Annotated[cdata, "TSequenceSet *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    result = _lib.tinstant_to_tsequenceset(inst_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_shift_scale_value(
    temp: Annotated[cdata, "const Temporal *"],
    shift: Annotated[cdata, "Datum"],
    width: Annotated[cdata, "Datum"],
    hasshift: bool,
    haswidth: bool,
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    shift_converted = _ffi.cast("Datum", shift)
    width_converted = _ffi.cast("Datum", width)
    result = _lib.tnumber_shift_scale_value(temp_converted, shift_converted, width_converted, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberinst_shift_value(
    inst: Annotated[cdata, "const TInstant *"], shift: Annotated[cdata, "Datum"]
) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    shift_converted = _ffi.cast("Datum", shift)
    result = _lib.tnumberinst_shift_value(inst_converted, shift_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseq_shift_scale_value(
    seq: Annotated[cdata, "const TSequence *"],
    shift: Annotated[cdata, "Datum"],
    width: Annotated[cdata, "Datum"],
    hasshift: bool,
    haswidth: bool,
) -> Annotated[cdata, "TSequence *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    shift_converted = _ffi.cast("Datum", shift)
    width_converted = _ffi.cast("Datum", width)
    result = _lib.tnumberseq_shift_scale_value(seq_converted, shift_converted, width_converted, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseqset_shift_scale_value(
    ss: Annotated[cdata, "const TSequenceSet *"],
    start: Annotated[cdata, "Datum"],
    width: Annotated[cdata, "Datum"],
    hasshift: bool,
    haswidth: bool,
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    start_converted = _ffi.cast("Datum", start)
    width_converted = _ffi.cast("Datum", width)
    result = _lib.tnumberseqset_shift_scale_value(ss_converted, start_converted, width_converted, hasshift, haswidth)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_restart(seq: Annotated[cdata, "TSequence *"], count: int) -> Annotated[None, "void"]:
    seq_converted = _ffi.cast("TSequence *", seq)
    _lib.tsequence_restart(seq_converted, count)
    _check_error()


def tsequence_set_interp(
    seq: Annotated[cdata, "const TSequence *"], interp: InterpolationType
) -> Annotated[cdata, "Temporal *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_set_interp(seq_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_shift_scale_time(
    seq: Annotated[cdata, "const TSequence *"],
    shift: Annotated[cdata, "const Interval *"],
    duration: Annotated[cdata, "const Interval *"],
) -> Annotated[cdata, "TSequence *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    shift_converted = _ffi.cast("const Interval *", shift)
    duration_converted = _ffi.cast("const Interval *", duration)
    result = _lib.tsequence_shift_scale_time(seq_converted, shift_converted, duration_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_subseq(
    seq: Annotated[cdata, "const TSequence *"], from_: int, to: int, lower_inc: bool, upper_inc: bool
) -> Annotated[cdata, "TSequence *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_subseq(seq_converted, from_, to, lower_inc, upper_inc)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_to_tinstant(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "TInstant *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_to_tinstant(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_to_tsequenceset(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "TSequenceSet *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_to_tsequenceset(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_to_tsequenceset_free(seq: Annotated[cdata, "TSequence *"]) -> Annotated[cdata, "TSequenceSet *"]:
    seq_converted = _ffi.cast("TSequence *", seq)
    result = _lib.tsequence_to_tsequenceset_free(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_to_tsequenceset_interp(
    seq: Annotated[cdata, "const TSequence *"], interp: InterpolationType
) -> Annotated[cdata, "TSequenceSet *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_to_tsequenceset_interp(seq_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_restart(ss: Annotated[cdata, "TSequenceSet *"], count: int) -> Annotated[None, "void"]:
    ss_converted = _ffi.cast("TSequenceSet *", ss)
    _lib.tsequenceset_restart(ss_converted, count)
    _check_error()


def tsequenceset_set_interp(
    ss: Annotated[cdata, "const TSequenceSet *"], interp: InterpolationType
) -> Annotated[cdata, "Temporal *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_set_interp(ss_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_shift_scale_time(
    ss: Annotated[cdata, "const TSequenceSet *"],
    start: Annotated[cdata, "const Interval *"],
    duration: Annotated[cdata, "const Interval *"],
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    start_converted = _ffi.cast("const Interval *", start)
    duration_converted = _ffi.cast("const Interval *", duration)
    result = _lib.tsequenceset_shift_scale_time(ss_converted, start_converted, duration_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_to_discrete(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "TSequence *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_to_discrete(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_to_linear(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_to_linear(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_to_step(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_to_step(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_to_tinstant(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "TInstant *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_to_tinstant(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_to_tsequence(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "TSequence *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_to_tsequence(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_merge(
    inst1: Annotated[cdata, "const TInstant *"], inst2: Annotated[cdata, "const TInstant *"]
) -> Annotated[cdata, "Temporal *"]:
    inst1_converted = _ffi.cast("const TInstant *", inst1)
    inst2_converted = _ffi.cast("const TInstant *", inst2)
    result = _lib.tinstant_merge(inst1_converted, inst2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_merge_array(instants: Annotated[list, "const TInstant **"], count: int) -> Annotated[cdata, "Temporal *"]:
    instants_converted = [_ffi.cast("const TInstant *", x) for x in instants]
    result = _lib.tinstant_merge_array(instants_converted, count)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_append_tinstant(
    seq: Annotated[cdata, "TSequence *"],
    inst: Annotated[cdata, "const TInstant *"],
    maxdist: float,
    maxt: Annotated[cdata, "const Interval *"],
    expand: bool,
) -> Annotated[cdata, "Temporal *"]:
    seq_converted = _ffi.cast("TSequence *", seq)
    inst_converted = _ffi.cast("const TInstant *", inst)
    maxt_converted = _ffi.cast("const Interval *", maxt)
    result = _lib.tsequence_append_tinstant(seq_converted, inst_converted, maxdist, maxt_converted, expand)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_append_tsequence(
    seq1: Annotated[cdata, "const TSequence *"], seq2: Annotated[cdata, "const TSequence *"], expand: bool
) -> Annotated[cdata, "Temporal *"]:
    seq1_converted = _ffi.cast("const TSequence *", seq1)
    seq2_converted = _ffi.cast("const TSequence *", seq2)
    result = _lib.tsequence_append_tsequence(seq1_converted, seq2_converted, expand)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_delete_timestamptz(
    seq: Annotated[cdata, "const TSequence *"], t: int, connect: bool
) -> Annotated[cdata, "Temporal *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.tsequence_delete_timestamptz(seq_converted, t_converted, connect)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_delete_tstzset(
    seq: Annotated[cdata, "const TSequence *"], s: Annotated[cdata, "const Set *"], connect: bool
) -> Annotated[cdata, "Temporal *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tsequence_delete_tstzset(seq_converted, s_converted, connect)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_delete_tstzspan(
    seq: Annotated[cdata, "const TSequence *"], s: Annotated[cdata, "const Span *"], connect: bool
) -> Annotated[cdata, "Temporal *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tsequence_delete_tstzspan(seq_converted, s_converted, connect)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_delete_tstzspanset(
    seq: Annotated[cdata, "const TSequence *"], ss: Annotated[cdata, "const SpanSet *"], connect: bool
) -> Annotated[cdata, "Temporal *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tsequence_delete_tstzspanset(seq_converted, ss_converted, connect)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_insert(
    seq1: Annotated[cdata, "const TSequence *"], seq2: Annotated[cdata, "const TSequence *"], connect: bool
) -> Annotated[cdata, "Temporal *"]:
    seq1_converted = _ffi.cast("const TSequence *", seq1)
    seq2_converted = _ffi.cast("const TSequence *", seq2)
    result = _lib.tsequence_insert(seq1_converted, seq2_converted, connect)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_merge(
    seq1: Annotated[cdata, "const TSequence *"], seq2: Annotated[cdata, "const TSequence *"]
) -> Annotated[cdata, "Temporal *"]:
    seq1_converted = _ffi.cast("const TSequence *", seq1)
    seq2_converted = _ffi.cast("const TSequence *", seq2)
    result = _lib.tsequence_merge(seq1_converted, seq2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_merge_array(
    sequences: Annotated[list, "const TSequence **"], count: int
) -> Annotated[cdata, "Temporal *"]:
    sequences_converted = [_ffi.cast("const TSequence *", x) for x in sequences]
    result = _lib.tsequence_merge_array(sequences_converted, count)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_append_tinstant(
    ss: Annotated[cdata, "TSequenceSet *"],
    inst: Annotated[cdata, "const TInstant *"],
    maxdist: float,
    maxt: Annotated[cdata, "const Interval *"],
    expand: bool,
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("TSequenceSet *", ss)
    inst_converted = _ffi.cast("const TInstant *", inst)
    maxt_converted = _ffi.cast("const Interval *", maxt)
    result = _lib.tsequenceset_append_tinstant(ss_converted, inst_converted, maxdist, maxt_converted, expand)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_append_tsequence(
    ss: Annotated[cdata, "TSequenceSet *"], seq: Annotated[cdata, "const TSequence *"], expand: bool
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("TSequenceSet *", ss)
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequenceset_append_tsequence(ss_converted, seq_converted, expand)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_delete_timestamptz(
    ss: Annotated[cdata, "const TSequenceSet *"], t: int
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.tsequenceset_delete_timestamptz(ss_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_delete_tstzset(
    ss: Annotated[cdata, "const TSequenceSet *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tsequenceset_delete_tstzset(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_delete_tstzspan(
    ss: Annotated[cdata, "const TSequenceSet *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tsequenceset_delete_tstzspan(ss_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_delete_tstzspanset(
    ss: Annotated[cdata, "const TSequenceSet *"], ps: Annotated[cdata, "const SpanSet *"]
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    ps_converted = _ffi.cast("const SpanSet *", ps)
    result = _lib.tsequenceset_delete_tstzspanset(ss_converted, ps_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_insert(
    ss1: Annotated[cdata, "const TSequenceSet *"], ss2: Annotated[cdata, "const TSequenceSet *"]
) -> Annotated[cdata, "TSequenceSet *"]:
    ss1_converted = _ffi.cast("const TSequenceSet *", ss1)
    ss2_converted = _ffi.cast("const TSequenceSet *", ss2)
    result = _lib.tsequenceset_insert(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_merge(
    ss1: Annotated[cdata, "const TSequenceSet *"], ss2: Annotated[cdata, "const TSequenceSet *"]
) -> Annotated[cdata, "TSequenceSet *"]:
    ss1_converted = _ffi.cast("const TSequenceSet *", ss1)
    ss2_converted = _ffi.cast("const TSequenceSet *", ss2)
    result = _lib.tsequenceset_merge(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_merge_array(
    seqsets: Annotated[list, "const TSequenceSet **"], count: int
) -> Annotated[cdata, "TSequenceSet *"]:
    seqsets_converted = [_ffi.cast("const TSequenceSet *", x) for x in seqsets]
    result = _lib.tsequenceset_merge_array(seqsets_converted, count)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_expand_bbox(
    seq: Annotated[cdata, "TSequence *"], inst: Annotated[cdata, "const TInstant *"]
) -> Annotated[None, "void"]:
    seq_converted = _ffi.cast("TSequence *", seq)
    inst_converted = _ffi.cast("const TInstant *", inst)
    _lib.tsequence_expand_bbox(seq_converted, inst_converted)
    _check_error()


def tsequence_set_bbox(
    seq: Annotated[cdata, "const TSequence *"], box: Annotated[cdata, "void *"]
) -> Annotated[None, "void"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    box_converted = _ffi.cast("void *", box)
    _lib.tsequence_set_bbox(seq_converted, box_converted)
    _check_error()


def tsequenceset_expand_bbox(
    ss: Annotated[cdata, "TSequenceSet *"], seq: Annotated[cdata, "const TSequence *"]
) -> Annotated[None, "void"]:
    ss_converted = _ffi.cast("TSequenceSet *", ss)
    seq_converted = _ffi.cast("const TSequence *", seq)
    _lib.tsequenceset_expand_bbox(ss_converted, seq_converted)
    _check_error()


def tsequenceset_set_bbox(
    ss: Annotated[cdata, "const TSequenceSet *"], box: Annotated[cdata, "void *"]
) -> Annotated[None, "void"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    box_converted = _ffi.cast("void *", box)
    _lib.tsequenceset_set_bbox(ss_converted, box_converted)
    _check_error()


def tdiscseq_restrict_minmax(
    seq: Annotated[cdata, "const TSequence *"], min: bool, atfunc: bool
) -> Annotated[cdata, "TSequence *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tdiscseq_restrict_minmax(seq_converted, min, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tcontseq_restrict_minmax(
    seq: Annotated[cdata, "const TSequence *"], min: bool, atfunc: bool
) -> Annotated[cdata, "TSequenceSet *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tcontseq_restrict_minmax(seq_converted, min, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_bbox_restrict_set(
    temp: Annotated[cdata, "const Temporal *"], set: Annotated[cdata, "const Set *"]
) -> Annotated[bool, "bool"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    set_converted = _ffi.cast("const Set *", set)
    result = _lib.temporal_bbox_restrict_set(temp_converted, set_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_restrict_minmax(
    temp: Annotated[cdata, "const Temporal *"], min: bool, atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_restrict_minmax(temp_converted, min, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_restrict_timestamptz(
    temp: Annotated[cdata, "const Temporal *"], t: int, atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.temporal_restrict_timestamptz(temp_converted, t_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_restrict_tstzset(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Set *"], atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.temporal_restrict_tstzset(temp_converted, s_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_restrict_tstzspan(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Span *"], atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.temporal_restrict_tstzspan(temp_converted, s_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_restrict_tstzspanset(
    temp: Annotated[cdata, "const Temporal *"], ss: Annotated[cdata, "const SpanSet *"], atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.temporal_restrict_tstzspanset(temp_converted, ss_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_restrict_value(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"], atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.temporal_restrict_value(temp_converted, value_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_restrict_values(
    temp: Annotated[cdata, "const Temporal *"], set: Annotated[cdata, "const Set *"], atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    set_converted = _ffi.cast("const Set *", set)
    result = _lib.temporal_restrict_values(temp_converted, set_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_value_at_timestamptz(
    temp: Annotated[cdata, "const Temporal *"], t: int, strict: bool
) -> Annotated[cdata, "Datum *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    t_converted = _ffi.cast("TimestampTz", t)
    out_result = _ffi.new("Datum *")
    result = _lib.temporal_value_at_timestamptz(temp_converted, t_converted, strict, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def tinstant_restrict_tstzspan(
    inst: Annotated[cdata, "const TInstant *"], period: Annotated[cdata, "const Span *"], atfunc: bool
) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    period_converted = _ffi.cast("const Span *", period)
    result = _lib.tinstant_restrict_tstzspan(inst_converted, period_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_restrict_tstzspanset(
    inst: Annotated[cdata, "const TInstant *"], ss: Annotated[cdata, "const SpanSet *"], atfunc: bool
) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tinstant_restrict_tstzspanset(inst_converted, ss_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_restrict_timestamptz(
    inst: Annotated[cdata, "const TInstant *"], t: int, atfunc: bool
) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.tinstant_restrict_timestamptz(inst_converted, t_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_restrict_tstzset(
    inst: Annotated[cdata, "const TInstant *"], s: Annotated[cdata, "const Set *"], atfunc: bool
) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tinstant_restrict_tstzset(inst_converted, s_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_restrict_value(
    inst: Annotated[cdata, "const TInstant *"], value: Annotated[cdata, "Datum"], atfunc: bool
) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.tinstant_restrict_value(inst_converted, value_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_restrict_values(
    inst: Annotated[cdata, "const TInstant *"], set: Annotated[cdata, "const Set *"], atfunc: bool
) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    set_converted = _ffi.cast("const Set *", set)
    result = _lib.tinstant_restrict_values(inst_converted, set_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_restrict_span(
    temp: Annotated[cdata, "const Temporal *"], span: Annotated[cdata, "const Span *"], atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    span_converted = _ffi.cast("const Span *", span)
    result = _lib.tnumber_restrict_span(temp_converted, span_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_restrict_spanset(
    temp: Annotated[cdata, "const Temporal *"], ss: Annotated[cdata, "const SpanSet *"], atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tnumber_restrict_spanset(temp_converted, ss_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberinst_restrict_span(
    inst: Annotated[cdata, "const TInstant *"], span: Annotated[cdata, "const Span *"], atfunc: bool
) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    span_converted = _ffi.cast("const Span *", span)
    result = _lib.tnumberinst_restrict_span(inst_converted, span_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberinst_restrict_spanset(
    inst: Annotated[cdata, "const TInstant *"], ss: Annotated[cdata, "const SpanSet *"], atfunc: bool
) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tnumberinst_restrict_spanset(inst_converted, ss_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseqset_restrict_span(
    ss: Annotated[cdata, "const TSequenceSet *"], span: Annotated[cdata, "const Span *"], atfunc: bool
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    span_converted = _ffi.cast("const Span *", span)
    result = _lib.tnumberseqset_restrict_span(ss_converted, span_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseqset_restrict_spanset(
    ss: Annotated[cdata, "const TSequenceSet *"], spanset: Annotated[cdata, "const SpanSet *"], atfunc: bool
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    spanset_converted = _ffi.cast("const SpanSet *", spanset)
    result = _lib.tnumberseqset_restrict_spanset(ss_converted, spanset_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_at_timestamptz(seq: Annotated[cdata, "const TSequence *"], t: int) -> Annotated[cdata, "TInstant *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.tsequence_at_timestamptz(seq_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_restrict_tstzspan(
    seq: Annotated[cdata, "const TSequence *"], s: Annotated[cdata, "const Span *"], atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tsequence_restrict_tstzspan(seq_converted, s_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_restrict_tstzspanset(
    seq: Annotated[cdata, "const TSequence *"], ss: Annotated[cdata, "const SpanSet *"], atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    ss_converted = _ffi.cast("const SpanSet *", ss)
    result = _lib.tsequence_restrict_tstzspanset(seq_converted, ss_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_restrict_minmax(
    ss: Annotated[cdata, "const TSequenceSet *"], min: bool, atfunc: bool
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_restrict_minmax(ss_converted, min, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_restrict_tstzspan(
    ss: Annotated[cdata, "const TSequenceSet *"], s: Annotated[cdata, "const Span *"], atfunc: bool
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.tsequenceset_restrict_tstzspan(ss_converted, s_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_restrict_tstzspanset(
    ss: Annotated[cdata, "const TSequenceSet *"], ps: Annotated[cdata, "const SpanSet *"], atfunc: bool
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    ps_converted = _ffi.cast("const SpanSet *", ps)
    result = _lib.tsequenceset_restrict_tstzspanset(ss_converted, ps_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_restrict_timestamptz(
    ss: Annotated[cdata, "const TSequenceSet *"], t: int, atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.tsequenceset_restrict_timestamptz(ss_converted, t_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_restrict_tstzset(
    ss: Annotated[cdata, "const TSequenceSet *"], s: Annotated[cdata, "const Set *"], atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tsequenceset_restrict_tstzset(ss_converted, s_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_restrict_value(
    ss: Annotated[cdata, "const TSequenceSet *"], value: Annotated[cdata, "Datum"], atfunc: bool
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.tsequenceset_restrict_value(ss_converted, value_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_restrict_values(
    ss: Annotated[cdata, "const TSequenceSet *"], s: Annotated[cdata, "const Set *"], atfunc: bool
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tsequenceset_restrict_values(ss_converted, s_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_cmp(
    inst1: Annotated[cdata, "const TInstant *"], inst2: Annotated[cdata, "const TInstant *"]
) -> Annotated[int, "int"]:
    inst1_converted = _ffi.cast("const TInstant *", inst1)
    inst2_converted = _ffi.cast("const TInstant *", inst2)
    result = _lib.tinstant_cmp(inst1_converted, inst2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tinstant_eq(
    inst1: Annotated[cdata, "const TInstant *"], inst2: Annotated[cdata, "const TInstant *"]
) -> Annotated[bool, "bool"]:
    inst1_converted = _ffi.cast("const TInstant *", inst1)
    inst2_converted = _ffi.cast("const TInstant *", inst2)
    result = _lib.tinstant_eq(inst1_converted, inst2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_cmp(
    seq1: Annotated[cdata, "const TSequence *"], seq2: Annotated[cdata, "const TSequence *"]
) -> Annotated[int, "int"]:
    seq1_converted = _ffi.cast("const TSequence *", seq1)
    seq2_converted = _ffi.cast("const TSequence *", seq2)
    result = _lib.tsequence_cmp(seq1_converted, seq2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_eq(
    seq1: Annotated[cdata, "const TSequence *"], seq2: Annotated[cdata, "const TSequence *"]
) -> Annotated[bool, "bool"]:
    seq1_converted = _ffi.cast("const TSequence *", seq1)
    seq2_converted = _ffi.cast("const TSequence *", seq2)
    result = _lib.tsequence_eq(seq1_converted, seq2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_cmp(
    ss1: Annotated[cdata, "const TSequenceSet *"], ss2: Annotated[cdata, "const TSequenceSet *"]
) -> Annotated[int, "int"]:
    ss1_converted = _ffi.cast("const TSequenceSet *", ss1)
    ss2_converted = _ffi.cast("const TSequenceSet *", ss2)
    result = _lib.tsequenceset_cmp(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_eq(
    ss1: Annotated[cdata, "const TSequenceSet *"], ss2: Annotated[cdata, "const TSequenceSet *"]
) -> Annotated[bool, "bool"]:
    ss1_converted = _ffi.cast("const TSequenceSet *", ss1)
    ss2_converted = _ffi.cast("const TSequenceSet *", ss2)
    result = _lib.tsequenceset_eq(ss1_converted, ss2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_base_temporal(
    value: Annotated[cdata, "Datum"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    value_converted = _ffi.cast("Datum", value)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_eq_base_temporal(value_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_temporal_base(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.always_eq_temporal_base(temp_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_base_temporal(
    value: Annotated[cdata, "Datum"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    value_converted = _ffi.cast("Datum", value)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ne_base_temporal(value_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_temporal_base(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.always_ne_temporal_base(temp_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ge_base_temporal(
    value: Annotated[cdata, "Datum"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    value_converted = _ffi.cast("Datum", value)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ge_base_temporal(value_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ge_temporal_base(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.always_ge_temporal_base(temp_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_gt_base_temporal(
    value: Annotated[cdata, "Datum"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    value_converted = _ffi.cast("Datum", value)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_gt_base_temporal(value_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_gt_temporal_base(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.always_gt_temporal_base(temp_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_le_base_temporal(
    value: Annotated[cdata, "Datum"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    value_converted = _ffi.cast("Datum", value)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_le_base_temporal(value_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_le_temporal_base(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.always_le_temporal_base(temp_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_lt_base_temporal(
    value: Annotated[cdata, "Datum"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    value_converted = _ffi.cast("Datum", value)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_lt_base_temporal(value_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_lt_temporal_base(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.always_lt_temporal_base(temp_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_base_temporal(
    value: Annotated[cdata, "Datum"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    value_converted = _ffi.cast("Datum", value)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_eq_base_temporal(value_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_temporal_base(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.ever_eq_temporal_base(temp_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_base_temporal(
    value: Annotated[cdata, "Datum"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    value_converted = _ffi.cast("Datum", value)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ne_base_temporal(value_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_temporal_base(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.ever_ne_temporal_base(temp_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ge_base_temporal(
    value: Annotated[cdata, "Datum"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    value_converted = _ffi.cast("Datum", value)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ge_base_temporal(value_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ge_temporal_base(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.ever_ge_temporal_base(temp_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_gt_base_temporal(
    value: Annotated[cdata, "Datum"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    value_converted = _ffi.cast("Datum", value)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_gt_base_temporal(value_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_gt_temporal_base(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.ever_gt_temporal_base(temp_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_le_base_temporal(
    value: Annotated[cdata, "Datum"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    value_converted = _ffi.cast("Datum", value)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_le_base_temporal(value_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_le_temporal_base(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.ever_le_temporal_base(temp_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_lt_base_temporal(
    value: Annotated[cdata, "Datum"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    value_converted = _ffi.cast("Datum", value)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_lt_base_temporal(value_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_lt_temporal_base(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.ever_lt_temporal_base(temp_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberinst_abs(inst: Annotated[cdata, "const TInstant *"]) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    result = _lib.tnumberinst_abs(inst_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseq_abs(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "TSequence *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tnumberseq_abs(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseq_angular_difference(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "TSequence *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tnumberseq_angular_difference(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseq_delta_value(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "TSequence *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tnumberseq_delta_value(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseqset_abs(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tnumberseqset_abs(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseqset_angular_difference(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "TSequence *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tnumberseqset_angular_difference(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseqset_delta_value(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tnumberseqset_delta_value(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tdistance_tnumber_number(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.tdistance_tnumber_number(temp_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tbox_tbox(
    box1: Annotated[cdata, "const TBox *"], box2: Annotated[cdata, "const TBox *"]
) -> Annotated[float, "double"]:
    box1_converted = _ffi.cast("const TBox *", box1)
    box2_converted = _ffi.cast("const TBox *", box2)
    result = _lib.nad_tbox_tbox(box1_converted, box2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tnumber_number(
    temp: Annotated[cdata, "const Temporal *"], value: Annotated[cdata, "Datum"]
) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    value_converted = _ffi.cast("Datum", value)
    result = _lib.nad_tnumber_number(temp_converted, value_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tnumber_tbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const TBox *"]
) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const TBox *", box)
    result = _lib.nad_tnumber_tbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tnumber_tnumber(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[float, "double"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.nad_tnumber_tnumber(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseq_integral(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[float, "double"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tnumberseq_integral(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseq_twavg(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[float, "double"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tnumberseq_twavg(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseqset_integral(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[float, "double"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tnumberseqset_integral(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumberseqset_twavg(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[float, "double"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tnumberseqset_twavg(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_compact(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.temporal_compact(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequence_compact(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "TSequence *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tsequence_compact(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tsequenceset_compact(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tsequenceset_compact(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def skiplist_free(list: Annotated[cdata, "SkipList *"]) -> Annotated[None, "void"]:
    list_converted = _ffi.cast("SkipList *", list)
    _lib.skiplist_free(list_converted)
    _check_error()


def temporal_app_tinst_transfn(
    state: Annotated[cdata, "Temporal *"],
    inst: Annotated[cdata, "const TInstant *"],
    interp: InterpolationType,
    maxdist: float,
    maxt: Annotated[cdata, "const Interval *"],
) -> Annotated[cdata, "Temporal *"]:
    state_converted = _ffi.cast("Temporal *", state)
    inst_converted = _ffi.cast("const TInstant *", inst)
    maxt_converted = _ffi.cast("const Interval *", maxt)
    result = _lib.temporal_app_tinst_transfn(state_converted, inst_converted, interp, maxdist, maxt_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def temporal_app_tseq_transfn(
    state: Annotated[cdata, "Temporal *"], seq: Annotated[cdata, "const TSequence *"]
) -> Annotated[cdata, "Temporal *"]:
    state_converted = _ffi.cast("Temporal *", state)
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.temporal_app_tseq_transfn(state_converted, seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def span_bins(
    s: Annotated[cdata, "const Span *"],
    size: Annotated[cdata, "Datum"],
    origin: Annotated[cdata, "Datum"],
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "Span *"]:
    s_converted = _ffi.cast("const Span *", s)
    size_converted = _ffi.cast("Datum", size)
    origin_converted = _ffi.cast("Datum", origin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.span_bins(s_converted, size_converted, origin_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spanset_bins(
    ss: Annotated[cdata, "const SpanSet *"],
    size: Annotated[cdata, "Datum"],
    origin: Annotated[cdata, "Datum"],
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "Span *"]:
    ss_converted = _ffi.cast("const SpanSet *", ss)
    size_converted = _ffi.cast("Datum", size)
    origin_converted = _ffi.cast("Datum", origin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.spanset_bins(ss_converted, size_converted, origin_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_value_bins(
    temp: Annotated[cdata, "const Temporal *"],
    size: Annotated[cdata, "Datum"],
    origin: Annotated[cdata, "Datum"],
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "Span *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    size_converted = _ffi.cast("Datum", size)
    origin_converted = _ffi.cast("Datum", origin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tnumber_value_bins(temp_converted, size_converted, origin_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_value_time_boxes(
    temp: Annotated[cdata, "const Temporal *"],
    vsize: Annotated[cdata, "Datum"],
    duration: Annotated[cdata, "const Interval *"],
    vorigin: Annotated[cdata, "Datum"],
    torigin: int,
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "TBox *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    vsize_converted = _ffi.cast("Datum", vsize)
    duration_converted = _ffi.cast("const Interval *", duration)
    vorigin_converted = _ffi.cast("Datum", vorigin)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tnumber_value_time_boxes(
        temp_converted, vsize_converted, duration_converted, vorigin_converted, torigin_converted, count_converted
    )
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_value_split(
    temp: Annotated[cdata, "const Temporal *"],
    vsize: Annotated[cdata, "Datum"],
    vorigin: Annotated[cdata, "Datum"],
    bins: Annotated[list, "Datum **"],
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "Temporal **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    vsize_converted = _ffi.cast("Datum", vsize)
    vorigin_converted = _ffi.cast("Datum", vorigin)
    bins_converted = [_ffi.cast("Datum *", x) for x in bins]
    count_converted = _ffi.cast("int *", count)
    result = _lib.tnumber_value_split(
        temp_converted, vsize_converted, vorigin_converted, bins_converted, count_converted
    )
    _check_error()
    return result if result != _ffi.NULL else None


def tbox_get_value_time_tile(
    value: Annotated[cdata, "Datum"],
    t: int,
    vsize: Annotated[cdata, "Datum"],
    duration: Annotated[cdata, "const Interval *"],
    vorigin: Annotated[cdata, "Datum"],
    torigin: int,
    basetype: Annotated[cdata, "meosType"],
    spantype: Annotated[cdata, "meosType"],
) -> Annotated[cdata, "TBox *"]:
    value_converted = _ffi.cast("Datum", value)
    t_converted = _ffi.cast("TimestampTz", t)
    vsize_converted = _ffi.cast("Datum", vsize)
    duration_converted = _ffi.cast("const Interval *", duration)
    vorigin_converted = _ffi.cast("Datum", vorigin)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    basetype_converted = _ffi.cast("meosType", basetype)
    spantype_converted = _ffi.cast("meosType", spantype)
    result = _lib.tbox_get_value_time_tile(
        value_converted,
        t_converted,
        vsize_converted,
        duration_converted,
        vorigin_converted,
        torigin_converted,
        basetype_converted,
        spantype_converted,
    )
    _check_error()
    return result if result != _ffi.NULL else None


def tnumber_value_time_split(
    temp: Annotated[cdata, "const Temporal *"],
    size: Annotated[cdata, "Datum"],
    duration: Annotated[cdata, "const Interval *"],
    vorigin: Annotated[cdata, "Datum"],
    torigin: int,
    value_bins: Annotated[list, "Datum **"],
    time_bins: Annotated[list, "TimestampTz **"],
    count: Annotated[cdata, "int *"],
) -> Annotated[cdata, "Temporal **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    size_converted = _ffi.cast("Datum", size)
    duration_converted = _ffi.cast("const Interval *", duration)
    vorigin_converted = _ffi.cast("Datum", vorigin)
    torigin_converted = _ffi.cast("TimestampTz", torigin)
    value_bins_converted = [_ffi.cast("Datum *", x) for x in value_bins]
    time_bins_converted = [_ffi.cast("TimestampTz *", x) for x in time_bins]
    count_converted = _ffi.cast("int *", count)
    result = _lib.tnumber_value_time_split(
        temp_converted,
        size_converted,
        duration_converted,
        vorigin_converted,
        torigin_converted,
        value_bins_converted,
        time_bins_converted,
        count_converted,
    )
    _check_error()
    return result if result != _ffi.NULL else None


def proj_get_context() -> Annotated[cdata, "PJ_CONTEXT *"]:
    result = _lib.proj_get_context()
    _check_error()
    return result if result != _ffi.NULL else None


def datum_geo_round(value: Annotated[cdata, "Datum"], size: Annotated[cdata, "Datum"]) -> Annotated[cdata, "Datum"]:
    value_converted = _ffi.cast("Datum", value)
    size_converted = _ffi.cast("Datum", size)
    result = _lib.datum_geo_round(value_converted, size_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def point_round(gs: Annotated[cdata, "const GSERIALIZED *"], maxdd: int) -> Annotated[cdata, "GSERIALIZED *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.point_round(gs_converted, maxdd)
    _check_error()
    return result if result != _ffi.NULL else None


def stbox_set(
    hasx: bool,
    hasz: bool,
    geodetic: bool,
    srid: int,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    zmin: float,
    zmax: float,
    s: Annotated[cdata, "const Span *"],
    box: Annotated[cdata, "STBox *"],
) -> Annotated[None, "void"]:
    srid_converted = _ffi.cast("int32", srid)
    s_converted = _ffi.cast("const Span *", s)
    box_converted = _ffi.cast("STBox *", box)
    _lib.stbox_set(hasx, hasz, geodetic, srid_converted, xmin, xmax, ymin, ymax, zmin, zmax, s_converted, box_converted)
    _check_error()


def gbox_set_stbox(
    box: Annotated[cdata, "const GBOX *"], srid: Annotated[cdata, "int32_t"]
) -> Annotated[cdata, "STBox *"]:
    box_converted = _ffi.cast("const GBOX *", box)
    srid_converted = _ffi.cast("int32_t", srid)
    out_result = _ffi.new("STBox *")
    _lib.gbox_set_stbox(box_converted, srid_converted, out_result)
    _check_error()
    return out_result if out_result != _ffi.NULL else None


def geo_set_stbox(
    gs: Annotated[cdata, "const GSERIALIZED *"], box: Annotated[cdata, "STBox *"]
) -> Annotated[bool, "bool"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    box_converted = _ffi.cast("STBox *", box)
    result = _lib.geo_set_stbox(gs_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geoarr_set_stbox(
    values: Annotated[cdata, "const Datum *"], count: int, box: Annotated[cdata, "STBox *"]
) -> Annotated[None, "void"]:
    values_converted = _ffi.cast("const Datum *", values)
    box_converted = _ffi.cast("STBox *", box)
    _lib.geoarr_set_stbox(values_converted, count, box_converted)
    _check_error()


def spatial_set_stbox(
    d: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"], box: Annotated[cdata, "STBox *"]
) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("Datum", d)
    basetype_converted = _ffi.cast("meosType", basetype)
    box_converted = _ffi.cast("STBox *", box)
    result = _lib.spatial_set_stbox(d_converted, basetype_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spatialset_set_stbox(
    set: Annotated[cdata, "const Set *"], box: Annotated[cdata, "STBox *"]
) -> Annotated[None, "void"]:
    set_converted = _ffi.cast("const Set *", set)
    box_converted = _ffi.cast("STBox *", box)
    _lib.spatialset_set_stbox(set_converted, box_converted)
    _check_error()


def stbox_set_box3d(
    box: Annotated[cdata, "const STBox *"], box3d: Annotated[cdata, "BOX3D *"]
) -> Annotated[None, "void"]:
    box_converted = _ffi.cast("const STBox *", box)
    box3d_converted = _ffi.cast("BOX3D *", box3d)
    _lib.stbox_set_box3d(box_converted, box3d_converted)
    _check_error()


def stbox_set_gbox(box: Annotated[cdata, "const STBox *"], gbox: Annotated[cdata, "GBOX *"]) -> Annotated[None, "void"]:
    box_converted = _ffi.cast("const STBox *", box)
    gbox_converted = _ffi.cast("GBOX *", gbox)
    _lib.stbox_set_gbox(box_converted, gbox_converted)
    _check_error()


def tstzset_set_stbox(s: Annotated[cdata, "const Set *"], box: Annotated[cdata, "STBox *"]) -> Annotated[None, "void"]:
    s_converted = _ffi.cast("const Set *", s)
    box_converted = _ffi.cast("STBox *", box)
    _lib.tstzset_set_stbox(s_converted, box_converted)
    _check_error()


def tstzspan_set_stbox(
    s: Annotated[cdata, "const Span *"], box: Annotated[cdata, "STBox *"]
) -> Annotated[None, "void"]:
    s_converted = _ffi.cast("const Span *", s)
    box_converted = _ffi.cast("STBox *", box)
    _lib.tstzspan_set_stbox(s_converted, box_converted)
    _check_error()


def tstzspanset_set_stbox(
    s: Annotated[cdata, "const SpanSet *"], box: Annotated[cdata, "STBox *"]
) -> Annotated[None, "void"]:
    s_converted = _ffi.cast("const SpanSet *", s)
    box_converted = _ffi.cast("STBox *", box)
    _lib.tstzspanset_set_stbox(s_converted, box_converted)
    _check_error()


def stbox_expand(box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "STBox *"]) -> Annotated[None, "void"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("STBox *", box2)
    _lib.stbox_expand(box1_converted, box2_converted)
    _check_error()


def inter_stbox_stbox(
    box1: Annotated[cdata, "const STBox *"], box2: Annotated[cdata, "const STBox *"]
) -> Annotated[cdata, "STBox *"]:
    box1_converted = _ffi.cast("const STBox *", box1)
    box2_converted = _ffi.cast("const STBox *", box2)
    out_result = _ffi.new("STBox *")
    result = _lib.inter_stbox_stbox(box1_converted, box2_converted, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def stbox_geo(box: Annotated[cdata, "const STBox *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.stbox_geo(box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeogpointinst_in(string: str) -> Annotated[cdata, "TInstant *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeogpointinst_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeogpointseq_in(string: str, interp: InterpolationType) -> Annotated[cdata, "TSequence *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeogpointseq_in(string_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeogpointseqset_in(string: str) -> Annotated[cdata, "TSequenceSet *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeogpointseqset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeompointinst_in(string: str) -> Annotated[cdata, "TInstant *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeompointinst_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeompointseq_in(string: str, interp: InterpolationType) -> Annotated[cdata, "TSequence *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeompointseq_in(string_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeompointseqset_in(string: str) -> Annotated[cdata, "TSequenceSet *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeompointseqset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeographyinst_in(string: str) -> Annotated[cdata, "TInstant *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeographyinst_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeographyseq_in(string: str, interp: InterpolationType) -> Annotated[cdata, "TSequence *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeographyseq_in(string_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeographyseqset_in(string: str) -> Annotated[cdata, "TSequenceSet *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeographyseqset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeometryinst_in(string: str) -> Annotated[cdata, "TInstant *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeometryinst_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeometryseq_in(string: str, interp: InterpolationType) -> Annotated[cdata, "TSequence *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeometryseq_in(string_converted, interp)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeometryseqset_in(string: str) -> Annotated[cdata, "TSequenceSet *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tgeometryseqset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tspatial_set_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "STBox *"]
) -> Annotated[None, "void"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("STBox *", box)
    _lib.tspatial_set_stbox(temp_converted, box_converted)
    _check_error()


def tgeoinst_set_stbox(
    inst: Annotated[cdata, "const TInstant *"], box: Annotated[cdata, "STBox *"]
) -> Annotated[None, "void"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    box_converted = _ffi.cast("STBox *", box)
    _lib.tgeoinst_set_stbox(inst_converted, box_converted)
    _check_error()


def tspatialseq_set_stbox(
    seq: Annotated[cdata, "const TSequence *"], box: Annotated[cdata, "STBox *"]
) -> Annotated[None, "void"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    box_converted = _ffi.cast("STBox *", box)
    _lib.tspatialseq_set_stbox(seq_converted, box_converted)
    _check_error()


def tspatialseqset_set_stbox(
    ss: Annotated[cdata, "const TSequenceSet *"], box: Annotated[cdata, "STBox *"]
) -> Annotated[None, "void"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    box_converted = _ffi.cast("STBox *", box)
    _lib.tspatialseqset_set_stbox(ss_converted, box_converted)
    _check_error()


def tgeo_restrict_geom(
    temp: Annotated[cdata, "const Temporal *"],
    gs: Annotated[cdata, "const GSERIALIZED *"],
    zspan: Annotated[cdata, "const Span *"],
    atfunc: bool,
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    zspan_converted = _ffi.cast("const Span *", zspan)
    result = _lib.tgeo_restrict_geom(temp_converted, gs_converted, zspan_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_restrict_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"], border_inc: bool, atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.tgeo_restrict_stbox(temp_converted, box_converted, border_inc, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeoinst_restrict_geom(
    inst: Annotated[cdata, "const TInstant *"],
    gs: Annotated[cdata, "const GSERIALIZED *"],
    zspan: Annotated[cdata, "const Span *"],
    atfunc: bool,
) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    zspan_converted = _ffi.cast("const Span *", zspan)
    result = _lib.tgeoinst_restrict_geom(inst_converted, gs_converted, zspan_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeoinst_restrict_stbox(
    inst: Annotated[cdata, "const TInstant *"], box: Annotated[cdata, "const STBox *"], border_inc: bool, atfunc: bool
) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.tgeoinst_restrict_stbox(inst_converted, box_converted, border_inc, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeoseq_restrict_geom(
    seq: Annotated[cdata, "const TSequence *"],
    gs: Annotated[cdata, "const GSERIALIZED *"],
    zspan: Annotated[cdata, "const Span *"],
    atfunc: bool,
) -> Annotated[cdata, "Temporal *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    zspan_converted = _ffi.cast("const Span *", zspan)
    result = _lib.tgeoseq_restrict_geom(seq_converted, gs_converted, zspan_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeoseq_restrict_stbox(
    seq: Annotated[cdata, "const TSequence *"], box: Annotated[cdata, "const STBox *"], border_inc: bool, atfunc: bool
) -> Annotated[cdata, "Temporal *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.tgeoseq_restrict_stbox(seq_converted, box_converted, border_inc, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeoseqset_restrict_geom(
    ss: Annotated[cdata, "const TSequenceSet *"],
    gs: Annotated[cdata, "const GSERIALIZED *"],
    zspan: Annotated[cdata, "const Span *"],
    atfunc: bool,
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    zspan_converted = _ffi.cast("const Span *", zspan)
    result = _lib.tgeoseqset_restrict_geom(ss_converted, gs_converted, zspan_converted, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeoseqset_restrict_stbox(
    ss: Annotated[cdata, "const TSequenceSet *"], box: Annotated[cdata, "const STBox *"], border_inc: bool, atfunc: bool
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.tgeoseqset_restrict_stbox(ss_converted, box_converted, border_inc, atfunc)
    _check_error()
    return result if result != _ffi.NULL else None


def spatial_srid(d: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"]) -> Annotated[cdata, "int32_t"]:
    d_converted = _ffi.cast("Datum", d)
    basetype_converted = _ffi.cast("meosType", basetype)
    result = _lib.spatial_srid(d_converted, basetype_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def spatial_set_srid(
    d: Annotated[cdata, "Datum"], basetype: Annotated[cdata, "meosType"], srid: Annotated[cdata, "int32_t"]
) -> Annotated[bool, "bool"]:
    d_converted = _ffi.cast("Datum", d)
    basetype_converted = _ffi.cast("meosType", basetype)
    srid_converted = _ffi.cast("int32_t", srid)
    result = _lib.spatial_set_srid(d_converted, basetype_converted, srid_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tspatialinst_srid(inst: Annotated[cdata, "const TInstant *"]) -> Annotated[int, "int"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    result = _lib.tspatialinst_srid(inst_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpointseq_azimuth(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "TSequenceSet *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tpointseq_azimuth(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpointseq_cumulative_length(
    seq: Annotated[cdata, "const TSequence *"], prevlength: float
) -> Annotated[cdata, "TSequence *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tpointseq_cumulative_length(seq_converted, prevlength)
    _check_error()
    return result if result != _ffi.NULL else None


def tpointseq_is_simple(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[bool, "bool"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tpointseq_is_simple(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpointseq_length(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[float, "double"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tpointseq_length(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpointseq_linear_trajectory(
    seq: Annotated[cdata, "const TSequence *"], unary_union: bool
) -> Annotated[cdata, "GSERIALIZED *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tpointseq_linear_trajectory(seq_converted, unary_union)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeoseq_stboxes(
    seq: Annotated[cdata, "const TSequence *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "STBox *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tgeoseq_stboxes(seq_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeoseq_split_n_stboxes(
    seq: Annotated[cdata, "const TSequence *"], max_count: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "STBox *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tgeoseq_split_n_stboxes(seq_converted, max_count, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpointseqset_azimuth(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tpointseqset_azimuth(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpointseqset_cumulative_length(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tpointseqset_cumulative_length(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpointseqset_is_simple(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[bool, "bool"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tpointseqset_is_simple(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpointseqset_length(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[float, "double"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tpointseqset_length(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeoseqset_stboxes(
    ss: Annotated[cdata, "const TSequenceSet *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "STBox *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tgeoseqset_stboxes(ss_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeoseqset_split_n_stboxes(
    ss: Annotated[cdata, "const TSequenceSet *"], max_count: int, count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "STBox *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tgeoseqset_split_n_stboxes(ss_converted, max_count, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpoint_get_coord(temp: Annotated[cdata, "const Temporal *"], coord: int) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tpoint_get_coord(temp_converted, coord)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeominst_tgeoginst(inst: Annotated[cdata, "const TInstant *"], oper: bool) -> Annotated[cdata, "TInstant *"]:
    inst_converted = _ffi.cast("const TInstant *", inst)
    result = _lib.tgeominst_tgeoginst(inst_converted, oper)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeomseq_tgeogseq(seq: Annotated[cdata, "const TSequence *"], oper: bool) -> Annotated[cdata, "TSequence *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tgeomseq_tgeogseq(seq_converted, oper)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeomseqset_tgeogseqset(
    ss: Annotated[cdata, "const TSequenceSet *"], oper: bool
) -> Annotated[cdata, "TSequenceSet *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tgeomseqset_tgeogseqset(ss_converted, oper)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeom_tgeog(temp: Annotated[cdata, "const Temporal *"], oper: bool) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeom_tgeog(temp_converted, oper)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeo_tpoint(temp: Annotated[cdata, "const Temporal *"], oper: bool) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeo_tpoint(temp_converted, oper)
    _check_error()
    return result if result != _ffi.NULL else None


def tspatialinst_set_srid(
    inst: Annotated[cdata, "TInstant *"], srid: Annotated[cdata, "int32_t"]
) -> Annotated[None, "void"]:
    inst_converted = _ffi.cast("TInstant *", inst)
    srid_converted = _ffi.cast("int32_t", srid)
    _lib.tspatialinst_set_srid(inst_converted, srid_converted)
    _check_error()


def tpointseq_make_simple(
    seq: Annotated[cdata, "const TSequence *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "TSequence **"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tpointseq_make_simple(seq_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tspatialseq_set_srid(
    seq: Annotated[cdata, "TSequence *"], srid: Annotated[cdata, "int32_t"]
) -> Annotated[None, "void"]:
    seq_converted = _ffi.cast("TSequence *", seq)
    srid_converted = _ffi.cast("int32_t", srid)
    _lib.tspatialseq_set_srid(seq_converted, srid_converted)
    _check_error()


def tpointseqset_make_simple(
    ss: Annotated[cdata, "const TSequenceSet *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "TSequence **"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tpointseqset_make_simple(ss_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tspatialseqset_set_srid(
    ss: Annotated[cdata, "TSequenceSet *"], srid: Annotated[cdata, "int32_t"]
) -> Annotated[None, "void"]:
    ss_converted = _ffi.cast("TSequenceSet *", ss)
    srid_converted = _ffi.cast("int32_t", srid)
    _lib.tspatialseqset_set_srid(ss_converted, srid_converted)
    _check_error()


def tpointseq_twcentroid(seq: Annotated[cdata, "const TSequence *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    seq_converted = _ffi.cast("const TSequence *", seq)
    result = _lib.tpointseq_twcentroid(seq_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tpointseqset_twcentroid(ss: Annotated[cdata, "const TSequenceSet *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    ss_converted = _ffi.cast("const TSequenceSet *", ss)
    result = _lib.tpointseqset_twcentroid(ss_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_as_ewkt(np: Annotated[cdata, "const Npoint *"], maxdd: int) -> Annotated[str, "char *"]:
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.npoint_as_ewkt(np_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def npoint_as_hexwkb(
    np: Annotated[cdata, "const Npoint *"], variant: int
) -> tuple[Annotated[str, "char *"], Annotated[cdata, "size_t *"]]:
    np_converted = _ffi.cast("const Npoint *", np)
    variant_converted = _ffi.cast("uint8_t", variant)
    size_out = _ffi.new("size_t *")
    result = _lib.npoint_as_hexwkb(np_converted, variant_converted, size_out)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None, size_out[0]


def npoint_as_text(np: Annotated[cdata, "const Npoint *"], maxdd: int) -> Annotated[str, "char *"]:
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.npoint_as_text(np_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def npoint_as_wkb(
    np: Annotated[cdata, "const Npoint *"], variant: int
) -> tuple[Annotated[cdata, "uint8_t *"], Annotated[cdata, "size_t *"]]:
    np_converted = _ffi.cast("const Npoint *", np)
    variant_converted = _ffi.cast("uint8_t", variant)
    size_out = _ffi.new("size_t *")
    result = _lib.npoint_as_wkb(np_converted, variant_converted, size_out)
    _check_error()
    return result if result != _ffi.NULL else None, size_out[0]


def npoint_from_hexwkb(hexwkb: str) -> Annotated[cdata, "Npoint *"]:
    hexwkb_converted = hexwkb.encode("utf-8")
    result = _lib.npoint_from_hexwkb(hexwkb_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_from_wkb(
    wkb: Annotated[cdata, "const uint8_t *"], size: Annotated[cdata, "size_t"]
) -> Annotated[cdata, "Npoint *"]:
    wkb_converted = _ffi.cast("const uint8_t *", wkb)
    size_converted = _ffi.cast("size_t", size)
    result = _lib.npoint_from_wkb(wkb_converted, size_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_in(string: str) -> Annotated[cdata, "Npoint *"]:
    string_converted = string.encode("utf-8")
    result = _lib.npoint_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_out(np: Annotated[cdata, "const Npoint *"], maxdd: int) -> Annotated[str, "char *"]:
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.npoint_out(np_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def nsegment_in(string: str) -> Annotated[cdata, "Nsegment *"]:
    string_converted = string.encode("utf-8")
    result = _lib.nsegment_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_out(ns: Annotated[cdata, "const Nsegment *"], maxdd: int) -> Annotated[str, "char *"]:
    ns_converted = _ffi.cast("const Nsegment *", ns)
    result = _lib.nsegment_out(ns_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def npoint_make(rid: int, pos: float) -> Annotated[cdata, "Npoint *"]:
    rid_converted = _ffi.cast("int64", rid)
    result = _lib.npoint_make(rid_converted, pos)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_make(rid: int, pos1: float, pos2: float) -> Annotated[cdata, "Nsegment *"]:
    rid_converted = _ffi.cast("int64", rid)
    result = _lib.nsegment_make(rid_converted, pos1, pos2)
    _check_error()
    return result if result != _ffi.NULL else None


def geompoint_to_npoint(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[cdata, "Npoint *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geompoint_to_npoint(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def geom_to_nsegment(gs: Annotated[cdata, "const GSERIALIZED *"]) -> Annotated[cdata, "Nsegment *"]:
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.geom_to_nsegment(gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_to_geompoint(np: Annotated[cdata, "const Npoint *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.npoint_to_geompoint(np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_to_nsegment(np: Annotated[cdata, "const Npoint *"]) -> Annotated[cdata, "Nsegment *"]:
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.npoint_to_nsegment(np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_to_stbox(np: Annotated[cdata, "const Npoint *"]) -> Annotated[cdata, "STBox *"]:
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.npoint_to_stbox(np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_to_geom(ns: Annotated[cdata, "const Nsegment *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    ns_converted = _ffi.cast("const Nsegment *", ns)
    result = _lib.nsegment_to_geom(ns_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_to_stbox(np: Annotated[cdata, "const Nsegment *"]) -> Annotated[cdata, "STBox *"]:
    np_converted = _ffi.cast("const Nsegment *", np)
    result = _lib.nsegment_to_stbox(np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_hash(np: Annotated[cdata, "const Npoint *"]) -> Annotated[int, "uint32"]:
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.npoint_hash(np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_hash_extended(np: Annotated[cdata, "const Npoint *"], seed: int) -> Annotated[int, "uint64"]:
    np_converted = _ffi.cast("const Npoint *", np)
    seed_converted = _ffi.cast("uint64", seed)
    result = _lib.npoint_hash_extended(np_converted, seed_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_position(np: Annotated[cdata, "const Npoint *"]) -> Annotated[float, "double"]:
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.npoint_position(np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_route(np: Annotated[cdata, "const Npoint *"]) -> Annotated[int, "int64"]:
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.npoint_route(np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_end_position(ns: Annotated[cdata, "const Nsegment *"]) -> Annotated[float, "double"]:
    ns_converted = _ffi.cast("const Nsegment *", ns)
    result = _lib.nsegment_end_position(ns_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_route(ns: Annotated[cdata, "const Nsegment *"]) -> Annotated[int, "int64"]:
    ns_converted = _ffi.cast("const Nsegment *", ns)
    result = _lib.nsegment_route(ns_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_start_position(ns: Annotated[cdata, "const Nsegment *"]) -> Annotated[float, "double"]:
    ns_converted = _ffi.cast("const Nsegment *", ns)
    result = _lib.nsegment_start_position(ns_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def route_exists(rid: int) -> Annotated[bool, "bool"]:
    rid_converted = _ffi.cast("int64", rid)
    result = _lib.route_exists(rid_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def route_geom(rid: int) -> Annotated[cdata, "GSERIALIZED *"]:
    rid_converted = _ffi.cast("int64", rid)
    result = _lib.route_geom(rid_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def route_length(rid: int) -> Annotated[float, "double"]:
    rid_converted = _ffi.cast("int64", rid)
    result = _lib.route_length(rid_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_round(np: Annotated[cdata, "const Npoint *"], maxdd: int) -> Annotated[cdata, "Npoint *"]:
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.npoint_round(np_converted, maxdd)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_round(ns: Annotated[cdata, "const Nsegment *"], maxdd: int) -> Annotated[cdata, "Nsegment *"]:
    ns_converted = _ffi.cast("const Nsegment *", ns)
    result = _lib.nsegment_round(ns_converted, maxdd)
    _check_error()
    return result if result != _ffi.NULL else None


def get_srid_ways() -> Annotated[cdata, "int32_t"]:
    result = _lib.get_srid_ways()
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_srid(np: Annotated[cdata, "const Npoint *"]) -> Annotated[cdata, "int32_t"]:
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.npoint_srid(np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_srid(ns: Annotated[cdata, "const Nsegment *"]) -> Annotated[cdata, "int32_t"]:
    ns_converted = _ffi.cast("const Nsegment *", ns)
    result = _lib.nsegment_srid(ns_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_timestamptz_to_stbox(np: Annotated[cdata, "const Npoint *"], t: int) -> Annotated[cdata, "STBox *"]:
    np_converted = _ffi.cast("const Npoint *", np)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.npoint_timestamptz_to_stbox(np_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_tstzspan_to_stbox(
    np: Annotated[cdata, "const Npoint *"], s: Annotated[cdata, "const Span *"]
) -> Annotated[cdata, "STBox *"]:
    np_converted = _ffi.cast("const Npoint *", np)
    s_converted = _ffi.cast("const Span *", s)
    result = _lib.npoint_tstzspan_to_stbox(np_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_cmp(
    np1: Annotated[cdata, "const Npoint *"], np2: Annotated[cdata, "const Npoint *"]
) -> Annotated[int, "int"]:
    np1_converted = _ffi.cast("const Npoint *", np1)
    np2_converted = _ffi.cast("const Npoint *", np2)
    result = _lib.npoint_cmp(np1_converted, np2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_eq(
    np1: Annotated[cdata, "const Npoint *"], np2: Annotated[cdata, "const Npoint *"]
) -> Annotated[bool, "bool"]:
    np1_converted = _ffi.cast("const Npoint *", np1)
    np2_converted = _ffi.cast("const Npoint *", np2)
    result = _lib.npoint_eq(np1_converted, np2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_ge(
    np1: Annotated[cdata, "const Npoint *"], np2: Annotated[cdata, "const Npoint *"]
) -> Annotated[bool, "bool"]:
    np1_converted = _ffi.cast("const Npoint *", np1)
    np2_converted = _ffi.cast("const Npoint *", np2)
    result = _lib.npoint_ge(np1_converted, np2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_gt(
    np1: Annotated[cdata, "const Npoint *"], np2: Annotated[cdata, "const Npoint *"]
) -> Annotated[bool, "bool"]:
    np1_converted = _ffi.cast("const Npoint *", np1)
    np2_converted = _ffi.cast("const Npoint *", np2)
    result = _lib.npoint_gt(np1_converted, np2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_le(
    np1: Annotated[cdata, "const Npoint *"], np2: Annotated[cdata, "const Npoint *"]
) -> Annotated[bool, "bool"]:
    np1_converted = _ffi.cast("const Npoint *", np1)
    np2_converted = _ffi.cast("const Npoint *", np2)
    result = _lib.npoint_le(np1_converted, np2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_lt(
    np1: Annotated[cdata, "const Npoint *"], np2: Annotated[cdata, "const Npoint *"]
) -> Annotated[bool, "bool"]:
    np1_converted = _ffi.cast("const Npoint *", np1)
    np2_converted = _ffi.cast("const Npoint *", np2)
    result = _lib.npoint_lt(np1_converted, np2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_ne(
    np1: Annotated[cdata, "const Npoint *"], np2: Annotated[cdata, "const Npoint *"]
) -> Annotated[bool, "bool"]:
    np1_converted = _ffi.cast("const Npoint *", np1)
    np2_converted = _ffi.cast("const Npoint *", np2)
    result = _lib.npoint_ne(np1_converted, np2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_same(
    np1: Annotated[cdata, "const Npoint *"], np2: Annotated[cdata, "const Npoint *"]
) -> Annotated[bool, "bool"]:
    np1_converted = _ffi.cast("const Npoint *", np1)
    np2_converted = _ffi.cast("const Npoint *", np2)
    result = _lib.npoint_same(np1_converted, np2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_cmp(
    ns1: Annotated[cdata, "const Nsegment *"], ns2: Annotated[cdata, "const Nsegment *"]
) -> Annotated[int, "int"]:
    ns1_converted = _ffi.cast("const Nsegment *", ns1)
    ns2_converted = _ffi.cast("const Nsegment *", ns2)
    result = _lib.nsegment_cmp(ns1_converted, ns2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_eq(
    ns1: Annotated[cdata, "const Nsegment *"], ns2: Annotated[cdata, "const Nsegment *"]
) -> Annotated[bool, "bool"]:
    ns1_converted = _ffi.cast("const Nsegment *", ns1)
    ns2_converted = _ffi.cast("const Nsegment *", ns2)
    result = _lib.nsegment_eq(ns1_converted, ns2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_ge(
    ns1: Annotated[cdata, "const Nsegment *"], ns2: Annotated[cdata, "const Nsegment *"]
) -> Annotated[bool, "bool"]:
    ns1_converted = _ffi.cast("const Nsegment *", ns1)
    ns2_converted = _ffi.cast("const Nsegment *", ns2)
    result = _lib.nsegment_ge(ns1_converted, ns2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_gt(
    ns1: Annotated[cdata, "const Nsegment *"], ns2: Annotated[cdata, "const Nsegment *"]
) -> Annotated[bool, "bool"]:
    ns1_converted = _ffi.cast("const Nsegment *", ns1)
    ns2_converted = _ffi.cast("const Nsegment *", ns2)
    result = _lib.nsegment_gt(ns1_converted, ns2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_le(
    ns1: Annotated[cdata, "const Nsegment *"], ns2: Annotated[cdata, "const Nsegment *"]
) -> Annotated[bool, "bool"]:
    ns1_converted = _ffi.cast("const Nsegment *", ns1)
    ns2_converted = _ffi.cast("const Nsegment *", ns2)
    result = _lib.nsegment_le(ns1_converted, ns2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_lt(
    ns1: Annotated[cdata, "const Nsegment *"], ns2: Annotated[cdata, "const Nsegment *"]
) -> Annotated[bool, "bool"]:
    ns1_converted = _ffi.cast("const Nsegment *", ns1)
    ns2_converted = _ffi.cast("const Nsegment *", ns2)
    result = _lib.nsegment_lt(ns1_converted, ns2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nsegment_ne(
    ns1: Annotated[cdata, "const Nsegment *"], ns2: Annotated[cdata, "const Nsegment *"]
) -> Annotated[bool, "bool"]:
    ns1_converted = _ffi.cast("const Nsegment *", ns1)
    ns2_converted = _ffi.cast("const Nsegment *", ns2)
    result = _lib.nsegment_ne(ns1_converted, ns2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npointset_in(string: str) -> Annotated[cdata, "Set *"]:
    string_converted = string.encode("utf-8")
    result = _lib.npointset_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npointset_out(s: Annotated[cdata, "const Set *"], maxdd: int) -> Annotated[str, "char *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.npointset_out(s_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def npointset_make(values: Annotated[list, "const Npoint **"], count: int) -> Annotated[cdata, "Set *"]:
    values_converted = [_ffi.cast("const Npoint *", x) for x in values]
    result = _lib.npointset_make(values_converted, count)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_to_set(np: Annotated[cdata, "const Npoint *"]) -> Annotated[cdata, "Set *"]:
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.npoint_to_set(np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npointset_end_value(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Npoint *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.npointset_end_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npointset_routes(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.npointset_routes(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npointset_start_value(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Npoint *"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.npointset_start_value(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npointset_value_n(s: Annotated[cdata, "const Set *"], n: int) -> Annotated[list, "Npoint **"]:
    s_converted = _ffi.cast("const Set *", s)
    out_result = _ffi.new("Npoint **")
    result = _lib.npointset_value_n(s_converted, n, out_result)
    _check_error()
    if result:
        return out_result if out_result != _ffi.NULL else None
    return None


def npointset_values(s: Annotated[cdata, "const Set *"]) -> Annotated[cdata, "Npoint **"]:
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.npointset_values(s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contained_npoint_set(
    np: Annotated[cdata, "const Npoint *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[bool, "bool"]:
    np_converted = _ffi.cast("const Npoint *", np)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.contained_npoint_set(np_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def contains_set_npoint(
    s: Annotated[cdata, "const Set *"], np: Annotated[cdata, "Npoint *"]
) -> Annotated[bool, "bool"]:
    s_converted = _ffi.cast("const Set *", s)
    np_converted = _ffi.cast("Npoint *", np)
    result = _lib.contains_set_npoint(s_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_npoint_set(
    np: Annotated[cdata, "const Npoint *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Set *"]:
    np_converted = _ffi.cast("const Npoint *", np)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.intersection_npoint_set(np_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def intersection_set_npoint(
    s: Annotated[cdata, "const Set *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.intersection_set_npoint(s_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_npoint_set(
    np: Annotated[cdata, "const Npoint *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Set *"]:
    np_converted = _ffi.cast("const Npoint *", np)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.minus_npoint_set(np_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def minus_set_npoint(
    s: Annotated[cdata, "const Set *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.minus_set_npoint(s_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def npoint_union_transfn(
    state: Annotated[cdata, "Set *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[cdata, "Set *"]:
    state_converted = _ffi.cast("Set *", state)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.npoint_union_transfn(state_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_npoint_set(
    np: Annotated[cdata, "const Npoint *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Set *"]:
    np_converted = _ffi.cast("const Npoint *", np)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.union_npoint_set(np_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def union_set_npoint(
    s: Annotated[cdata, "const Set *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[cdata, "Set *"]:
    s_converted = _ffi.cast("const Set *", s)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.union_set_npoint(s_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_in(string: str) -> Annotated[cdata, "Temporal *"]:
    string_converted = string.encode("utf-8")
    result = _lib.tnpoint_in(string_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_out(temp: Annotated[cdata, "const Temporal *"], maxdd: int) -> Annotated[str, "char *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnpoint_out(temp_converted, maxdd)
    _check_error()
    result = _ffi.string(result).decode("utf-8")
    return result if result != _ffi.NULL else None


def tnpointinst_make(np: Annotated[cdata, "const Npoint *"], t: int) -> Annotated[cdata, "TInstant *"]:
    np_converted = _ffi.cast("const Npoint *", np)
    t_converted = _ffi.cast("TimestampTz", t)
    result = _lib.tnpointinst_make(np_converted, t_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tgeompoint_to_tnpoint(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tgeompoint_to_tnpoint(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_to_tgeompoint(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnpoint_to_tgeompoint(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_cumulative_length(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnpoint_cumulative_length(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_length(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnpoint_length(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_positions(
    temp: Annotated[cdata, "const Temporal *"], count: Annotated[cdata, "int *"]
) -> Annotated[cdata, "Nsegment **"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    count_converted = _ffi.cast("int *", count)
    result = _lib.tnpoint_positions(temp_converted, count_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_route(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[int, "int64"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnpoint_route(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_routes(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Set *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnpoint_routes(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_speed(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnpoint_speed(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_trajectory(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnpoint_trajectory(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_twcentroid(temp: Annotated[cdata, "const Temporal *"]) -> Annotated[cdata, "GSERIALIZED *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.tnpoint_twcentroid(temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_at_geom(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.tnpoint_at_geom(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_at_npoint(
    temp: Annotated[cdata, "const Temporal *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.tnpoint_at_npoint(temp_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_at_npointset(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tnpoint_at_npointset(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_at_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"], border_inc: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.tnpoint_at_stbox(temp_converted, box_converted, border_inc)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_minus_geom(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.tnpoint_minus_geom(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_minus_npoint(
    temp: Annotated[cdata, "const Temporal *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.tnpoint_minus_npoint(temp_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_minus_npointset(
    temp: Annotated[cdata, "const Temporal *"], s: Annotated[cdata, "const Set *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    s_converted = _ffi.cast("const Set *", s)
    result = _lib.tnpoint_minus_npointset(temp_converted, s_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_minus_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"], border_inc: bool
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.tnpoint_minus_stbox(temp_converted, box_converted, border_inc)
    _check_error()
    return result if result != _ffi.NULL else None


def tdistance_tnpoint_npoint(
    temp: Annotated[cdata, "const Temporal *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.tdistance_tnpoint_npoint(temp_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tdistance_tnpoint_point(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.tdistance_tnpoint_point(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tdistance_tnpoint_tnpoint(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "Temporal *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.tdistance_tnpoint_tnpoint(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tnpoint_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.nad_tnpoint_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tnpoint_npoint(
    temp: Annotated[cdata, "const Temporal *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.nad_tnpoint_npoint(temp_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tnpoint_stbox(
    temp: Annotated[cdata, "const Temporal *"], box: Annotated[cdata, "const STBox *"]
) -> Annotated[float, "double"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    box_converted = _ffi.cast("const STBox *", box)
    result = _lib.nad_tnpoint_stbox(temp_converted, box_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nad_tnpoint_tnpoint(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[float, "double"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.nad_tnpoint_tnpoint(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nai_tnpoint_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "TInstant *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.nai_tnpoint_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nai_tnpoint_npoint(
    temp: Annotated[cdata, "const Temporal *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[cdata, "TInstant *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.nai_tnpoint_npoint(temp_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def nai_tnpoint_tnpoint(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "TInstant *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.nai_tnpoint_tnpoint(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def shortestline_tnpoint_geo(
    temp: Annotated[cdata, "const Temporal *"], gs: Annotated[cdata, "const GSERIALIZED *"]
) -> Annotated[cdata, "GSERIALIZED *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    gs_converted = _ffi.cast("const GSERIALIZED *", gs)
    result = _lib.shortestline_tnpoint_geo(temp_converted, gs_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def shortestline_tnpoint_npoint(
    temp: Annotated[cdata, "const Temporal *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[cdata, "GSERIALIZED *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.shortestline_tnpoint_npoint(temp_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def shortestline_tnpoint_tnpoint(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[cdata, "GSERIALIZED *"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.shortestline_tnpoint_tnpoint(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tnpoint_tcentroid_transfn(
    state: Annotated[cdata, "SkipList *"], temp: Annotated[cdata, "Temporal *"]
) -> Annotated[cdata, "SkipList *"]:
    state_converted = _ffi.cast("SkipList *", state)
    temp_converted = _ffi.cast("Temporal *", temp)
    result = _lib.tnpoint_tcentroid_transfn(state_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_npoint_tnpoint(
    np: Annotated[cdata, "const Npoint *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    np_converted = _ffi.cast("const Npoint *", np)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_eq_npoint_tnpoint(np_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_tnpoint_npoint(
    temp: Annotated[cdata, "const Temporal *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.always_eq_tnpoint_npoint(temp_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_eq_tnpoint_tnpoint(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.always_eq_tnpoint_tnpoint(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_npoint_tnpoint(
    np: Annotated[cdata, "const Npoint *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    np_converted = _ffi.cast("const Npoint *", np)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.always_ne_npoint_tnpoint(np_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_tnpoint_npoint(
    temp: Annotated[cdata, "const Temporal *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.always_ne_tnpoint_npoint(temp_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def always_ne_tnpoint_tnpoint(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.always_ne_tnpoint_tnpoint(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_npoint_tnpoint(
    np: Annotated[cdata, "const Npoint *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    np_converted = _ffi.cast("const Npoint *", np)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_eq_npoint_tnpoint(np_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_tnpoint_npoint(
    temp: Annotated[cdata, "const Temporal *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.ever_eq_tnpoint_npoint(temp_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_eq_tnpoint_tnpoint(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.ever_eq_tnpoint_tnpoint(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_npoint_tnpoint(
    np: Annotated[cdata, "const Npoint *"], temp: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    np_converted = _ffi.cast("const Npoint *", np)
    temp_converted = _ffi.cast("const Temporal *", temp)
    result = _lib.ever_ne_npoint_tnpoint(np_converted, temp_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_tnpoint_npoint(
    temp: Annotated[cdata, "const Temporal *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[int, "int"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.ever_ne_tnpoint_npoint(temp_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def ever_ne_tnpoint_tnpoint(
    temp1: Annotated[cdata, "const Temporal *"], temp2: Annotated[cdata, "const Temporal *"]
) -> Annotated[int, "int"]:
    temp1_converted = _ffi.cast("const Temporal *", temp1)
    temp2_converted = _ffi.cast("const Temporal *", temp2)
    result = _lib.ever_ne_tnpoint_tnpoint(temp1_converted, temp2_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def teq_tnpoint_npoint(
    temp: Annotated[cdata, "const Temporal *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.teq_tnpoint_npoint(temp_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None


def tne_tnpoint_npoint(
    temp: Annotated[cdata, "const Temporal *"], np: Annotated[cdata, "const Npoint *"]
) -> Annotated[cdata, "Temporal *"]:
    temp_converted = _ffi.cast("const Temporal *", temp)
    np_converted = _ffi.cast("const Npoint *", np)
    result = _lib.tne_tnpoint_npoint(temp_converted, np_converted)
    _check_error()
    return result if result != _ffi.NULL else None
