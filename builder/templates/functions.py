import logging
import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Any

import _meos_cffi
import shapely.geometry as spg
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


def _read_string(ptr: Annotated[_ffi.CData, "const char *"]) -> str | None:
    return _ffi.string(ptr).decode("utf-8") if ptr != _ffi.NULL else None


def _take_string(ptr: Annotated[_ffi.CData, "char *"]) -> str | None:
    """The string MEOS hands the caller, copied and then freed, as #_read_string reads it"""
    if ptr == _ffi.NULL:
        return None
    result = _ffi.string(ptr).decode("utf-8")
    _lib.free(ptr)
    return result


def _take_bytes(ptr: Annotated[_ffi.CData, "uint8_t *"], size: int) -> bytes | None:
    """The byte buffer MEOS hands the caller, copied and then freed, as #_take_string takes a string"""
    if ptr == _ffi.NULL:
        return None
    result = bytes(_ffi.buffer(ptr, size))
    _lib.free(ptr)
    return result


def create_pointer(object: "Any", type: str) -> Annotated[_ffi.CData, "Any *"]:
    return _ffi.new(f"{type} *", object)


def get_address(value: "Any") -> Annotated[_ffi.CData, "Any *"]:
    return _ffi.addressof(value)


# The casts of the time types. Each is a generated wrapper of a MEOS conversion (MobilityDB
# doc/specs/meos-bindings-algebra.md, section 5) and a constructor of the host type: MEOS raises
# for a value it cannot state, the constructor for one the host type cannot state. A wrapper of a
# conversion with out-parameters answers (found, *outs) (#interval_to_parts, #time_to_parts).

_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_UNIX_EPOCH_NAIVE = datetime(1970, 1, 1)
_UNIX_EPOCH_ORDINAL = date(1970, 1, 1).toordinal()
_MICROSECOND = timedelta(microseconds=1)


def datetime_to_timestamptz(dt: datetime) -> Annotated[int, "TimestampTz"]:
    """An aware datetime as its instant; a naive one read in the time zone of MEOS"""
    if dt.utcoffset() is None:
        return timestamp_to_timestamptz(datetime_to_timestamp(dt))
    return unix_us_to_timestamptz((dt - _UNIX_EPOCH) // _MICROSECOND)


def timestamptz_to_datetime(ts: Annotated[int, "TimestampTz"]) -> datetime:
    return _UNIX_EPOCH + timedelta(microseconds=timestamptz_to_unix_us(ts))


def datetime_to_timestamp(dt: datetime) -> Annotated[int, "Timestamp"]:
    return unix_us_to_timestamp((dt - _UNIX_EPOCH_NAIVE) // _MICROSECOND)


def timestamp_to_datetime(ts: Annotated[int, "Timestamp"]) -> datetime:
    return _UNIX_EPOCH_NAIVE + timedelta(microseconds=timestamp_to_unix_us(ts))


def date_to_date_adt(dt: date) -> Annotated[int, "DateADT"]:
    return unix_days_to_date(dt.toordinal() - _UNIX_EPOCH_ORDINAL)


def date_adt_to_date(ts: Annotated[int, "DateADT"]) -> date:
    return date.fromordinal(date_to_unix_days(ts) + _UNIX_EPOCH_ORDINAL)


def timedelta_to_interval(td: timedelta) -> Annotated[_ffi.CData, "Interval *"]:
    return interval_from_parts(0, td.days, td.seconds * 1_000_000 + td.microseconds)


def interval_to_timedelta(interval: Annotated[_ffi.CData, "const Interval *"]) -> timedelta:
    """A month has no fixed length, so an interval with months has no timedelta"""
    _, months, days, us = interval_to_parts(interval)
    if months != 0:
        raise ValueError(f"An interval of {months} month(s) has no fixed duration")
    return timedelta(days=days, microseconds=us)


def time_to_time_adt(t: time) -> Annotated[int, "TimeADT"]:
    if t.tzinfo is not None:
        raise ValueError(f"A time has no time zone: {t}")
    return time_from_parts((datetime.combine(date.min, t) - datetime.min) // _MICROSECOND)


def time_adt_to_time(t: Annotated[int, "TimeADT"]) -> time:
    """24:00:00 raises the ValueError of time, which ends its day before it"""
    _, us = time_to_parts(t)
    seconds, microsecond = divmod(us, 1_000_000)
    return time(seconds // 3600, seconds // 60 % 60, seconds % 60, microsecond)


def timetz_to_timetz_adt(t: time) -> Annotated[_ffi.CData, "TimeTzADT *"]:
    """The offset in whole seconds east of UTC, as MEOS holds it"""
    us = (datetime.combine(date.min, t.replace(tzinfo=None)) - datetime.min) // _MICROSECOND
    return timetz_from_parts(us, t.utcoffset() // timedelta(seconds=1))


def timetz_adt_to_timetz(t: Annotated[_ffi.CData, "const TimeTzADT *"]) -> time:
    _, us, offset = timetz_to_parts(t)
    seconds, microsecond = divmod(us, 1_000_000)
    return time(
        seconds // 3600, seconds // 60 % 60, seconds % 60, microsecond, tzinfo=timezone(timedelta(seconds=offset))
    )


def geo_to_gserialized(geom: BaseGeometry, geodetic: bool) -> Annotated[_ffi.CData, "GSERIALIZED *"]:
    if geodetic:
        return geography_to_gserialized(geom)
    else:
        return geometry_to_gserialized(geom)


def geometry_to_gserialized(geom: BaseGeometry) -> Annotated[_ffi.CData, "GSERIALIZED *"]:
    text = wkt.dumps(geom)
    if get_srid(geom) > 0:
        text = f"SRID={get_srid(geom)};{text}"
    gs = geom_in(text, -1)
    return gs


def geography_to_gserialized(geom: BaseGeometry) -> Annotated[_ffi.CData, "GSERIALIZED *"]:
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


def as_tinstant(temporal: Annotated[_ffi.CData, "Temporal *"]) -> Annotated[_ffi.CData, "TInstant *"]:
    return _ffi.cast("TInstant *", temporal)


def as_tsequence(temporal: Annotated[_ffi.CData, "Temporal *"]) -> Annotated[_ffi.CData, "TSequence *"]:
    return _ffi.cast("TSequence *", temporal)


def as_tsequenceset(temporal: Annotated[_ffi.CData, "Temporal *"]) -> Annotated[_ffi.CData, "TSequenceSet *"]:
    return _ffi.cast("TSequenceSet *", temporal)


def float_to_datum(value: float) -> Annotated[_ffi.CData, "Datum"]:
    # PostgreSQL's Float8GetDatum reinterprets the 8-byte double as a Datum.
    buf = _ffi.new("double[1]", [value])
    return _ffi.cast("Datum *", buf)[0]


def int_to_datum(value: int) -> Annotated[_ffi.CData, "Datum"]:
    # Int32GetDatum / Int64GetDatum widen the integer to Datum (uintptr_t).
    return _ffi.cast("Datum", value)


def tbox_expand_float(box: Annotated[_ffi.CData, "const TBox *"], d: float) -> Annotated[_ffi.CData, "TBox *"]:
    return tbox_expand_value(box, float_to_datum(d), _lib.T_FLOAT8)


def tbox_expand_int(box: Annotated[_ffi.CData, "const TBox *"], i: int) -> Annotated[_ffi.CData, "TBox *"]:
    return tbox_expand_value(box, int_to_datum(i), _lib.T_INT4)


def tbox_shift_scale_float(
    box: Annotated[_ffi.CData, "const TBox *"],
    shift: float,
    width: float,
    hasshift: bool,
    haswidth: bool,
) -> Annotated[_ffi.CData, "TBox *"]:
    return tbox_shift_scale_value(box, float_to_datum(shift), float_to_datum(width), hasshift, haswidth)


def tbox_shift_scale_int(
    box: Annotated[_ffi.CData, "const TBox *"],
    shift: int,
    width: int,
    hasshift: bool,
    haswidth: bool,
) -> Annotated[_ffi.CData, "TBox *"]:
    return tbox_shift_scale_value(box, int_to_datum(shift), int_to_datum(width), hasshift, haswidth)


# -----------------------------------------------------------------------------
# ----------------------End of manually-defined functions----------------------
# -----------------------------------------------------------------------------
