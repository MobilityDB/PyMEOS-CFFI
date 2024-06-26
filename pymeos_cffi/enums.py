from _meos_cffi import lib as _lib
from enum import IntEnum


class MeosType(IntEnum):
    T_UNKNOWN = _lib.T_UNKNOWN
    T_BOOL = _lib.T_BOOL
    T_DATE = _lib.T_DATE
    T_DATEMULTIRANGE = _lib.T_DATEMULTIRANGE
    T_DATERANGE = _lib.T_DATERANGE
    T_DATESET = _lib.T_DATESET
    T_DATESPAN = _lib.T_DATESPAN
    T_DATESPANSET = _lib.T_DATESPANSET
    T_DOUBLE2 = _lib.T_DOUBLE2
    T_DOUBLE3 = _lib.T_DOUBLE3
    T_DOUBLE4 = _lib.T_DOUBLE4
    T_FLOAT8 = _lib.T_FLOAT8
    T_FLOATSET = _lib.T_FLOATSET
    T_FLOATSPAN = _lib.T_FLOATSPAN
    T_FLOATSPANSET = _lib.T_FLOATSPANSET
    T_INT4 = _lib.T_INT4
    T_INT4MULTIRANGE = _lib.T_INT4MULTIRANGE
    T_INT4RANGE = _lib.T_INT4RANGE
    T_INTSET = _lib.T_INTSET
    T_INTSPAN = _lib.T_INTSPAN
    T_INTSPANSET = _lib.T_INTSPANSET
    T_INT8 = _lib.T_INT8
    T_BIGINTSET = _lib.T_BIGINTSET
    T_BIGINTSPAN = _lib.T_BIGINTSPAN
    T_BIGINTSPANSET = _lib.T_BIGINTSPANSET
    T_STBOX = _lib.T_STBOX
    T_TBOOL = _lib.T_TBOOL
    T_TBOX = _lib.T_TBOX
    T_TDOUBLE2 = _lib.T_TDOUBLE2
    T_TDOUBLE3 = _lib.T_TDOUBLE3
    T_TDOUBLE4 = _lib.T_TDOUBLE4
    T_TEXT = _lib.T_TEXT
    T_TEXTSET = _lib.T_TEXTSET
    T_TFLOAT = _lib.T_TFLOAT
    T_TIMESTAMPTZ = _lib.T_TIMESTAMPTZ
    T_TINT = _lib.T_TINT
    T_TSTZMULTIRANGE = _lib.T_TSTZMULTIRANGE
    T_TSTZRANGE = _lib.T_TSTZRANGE
    T_TSTZSET = _lib.T_TSTZSET
    T_TSTZSPAN = _lib.T_TSTZSPAN
    T_TSTZSPANSET = _lib.T_TSTZSPANSET
    T_TTEXT = _lib.T_TTEXT
    T_GEOMETRY = _lib.T_GEOMETRY
    T_GEOMSET = _lib.T_GEOMSET
    T_GEOGRAPHY = _lib.T_GEOGRAPHY
    T_GEOGSET = _lib.T_GEOGSET
    T_TGEOMPOINT = _lib.T_TGEOMPOINT
    T_TGEOGPOINT = _lib.T_TGEOGPOINT
    T_NPOINT = _lib.T_NPOINT
    T_NPOINTSET = _lib.T_NPOINTSET
    T_NSEGMENT = _lib.T_NSEGMENT
    T_TNPOINT = _lib.T_TNPOINT


class MeosTemporalSubtype(IntEnum):
    ANY = _lib.ANYTEMPSUBTYPE
    INSTANT = _lib.TINSTANT
    SEQUENCE = _lib.TSEQUENCE
    SEQUENCE_SET = _lib.TSEQUENCESET


class MeosOperation(IntEnum):
    UNKNOWN_OP = _lib.UNKNOWN_OP
    EQ_OP = _lib.EQ_OP
    NE_OP = _lib.NE_OP
    LT_OP = _lib.LT_OP
    LE_OP = _lib.LE_OP
    GT_OP = _lib.GT_OP
    GE_OP = _lib.GE_OP
    ADJACENT_OP = _lib.ADJACENT_OP
    UNION_OP = _lib.UNION_OP
    MINUS_OP = _lib.MINUS_OP
    INTERSECT_OP = _lib.INTERSECT_OP
    OVERLAPS_OP = _lib.OVERLAPS_OP
    CONTAINS_OP = _lib.CONTAINS_OP
    CONTAINED_OP = _lib.CONTAINED_OP
    SAME_OP = _lib.SAME_OP
    LEFT_OP = _lib.LEFT_OP
    OVERLEFT_OP = _lib.OVERLEFT_OP
    RIGHT_OP = _lib.RIGHT_OP
    OVERRIGHT_OP = _lib.OVERRIGHT_OP
    BELOW_OP = _lib.BELOW_OP
    OVERBELOW_OP = _lib.OVERBELOW_OP
    ABOVE_OP = _lib.ABOVE_OP
    OVERABOVE_OP = _lib.OVERABOVE_OP
    FRONT_OP = _lib.FRONT_OP
    OVERFRONT_OP = _lib.OVERFRONT_OP
    BACK_OP = _lib.BACK_OP
    OVERBACK_OP = _lib.OVERBACK_OP
    BEFORE_OP = _lib.BEFORE_OP
    OVERBEFORE_OP = _lib.OVERBEFORE_OP
    AFTER_OP = _lib.AFTER_OP
    OVERAFTER_OP = _lib.OVERAFTER_OP
    EVEREQ_OP = _lib.EVEREQ_OP
    EVERNE_OP = _lib.EVERNE_OP
    EVERLT_OP = _lib.EVERLT_OP
    EVERLE_OP = _lib.EVERLE_OP
    EVERGT_OP = _lib.EVERGT_OP
    EVERGE_OP = _lib.EVERGE_OP
    ALWAYSEQ_OP = _lib.ALWAYSEQ_OP
    ALWAYSNE_OP = _lib.ALWAYSNE_OP
    ALWAYSLT_OP = _lib.ALWAYSLT_OP
    ALWAYSLE_OP = _lib.ALWAYSLE_OP
    ALWAYSGT_OP = _lib.ALWAYSGT_OP
    ALWAYSGE_OP = _lib.ALWAYSGE_OP


class InterpolationType(IntEnum):
    NONE = _lib.INTERP_NONE
    DISCRETE = _lib.DISCRETE
    STEP = _lib.STEP
    LINEAR = _lib.LINEAR


class SpatialRelation(IntEnum):
    INTERSECTS = _lib.INTERSECTS
    CONTAINS = _lib.CONTAINS
    TOUCHES = _lib.TOUCHES


class ErrorLevel(IntEnum):
    NOTICE = 18
    WARNING = 19
    ERROR = 21
