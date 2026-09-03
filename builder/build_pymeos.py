import json
import os

from cffi import FFI

# The MEOS public headers to #include in the compiled extension, derived from
# the catalog's own ``file`` field so a new family header rides in with the
# next catalog refresh — no hand-maintained list. The PostgreSQL-compat headers
# (pg_*.h, pgtypes.h) are pulled transitively by meos.h.
with open(os.path.join(os.path.dirname(__file__), "meos-idl.json")) as f:
    _idl = json.load(f)
_files = {e["file"] for e in _idl["functions"] + _idl["structs"]}
header_files = sorted(f for f in _files if f.startswith("meos"))

ffibuilder = FFI()

with open(os.path.join(os.path.dirname(__file__), "meos.h")) as f:
    content = f.read()

ffibuilder.cdef(content)


# A MEOS install prefix may be supplied out of band so the extension can be built
# against a MEOS that is not on the default system paths (e.g. a scratch prefix used
# by tools/refresh-from-master.sh). MEOS_PREFIX adds <prefix>/lib and <prefix>/include;
# MEOS_LIB_DIR / MEOS_INCLUDE_DIR override a single dir. Unset => unchanged behaviour.
def _search_dirs(single_env, subdir, defaults):
    paths = []
    explicit = os.environ.get(single_env)
    if explicit:
        paths.append(explicit)
    prefix = os.environ.get("MEOS_PREFIX")
    if prefix:
        paths.append(os.path.join(prefix, subdir))
    paths.extend(defaults)
    return [path for path in paths if os.path.exists(path)]


def get_library_dirs():
    return _search_dirs("MEOS_LIB_DIR", "lib", ["/usr/local/lib", "/opt/homebrew/lib"])


def get_include_dirs():
    # The optional families expose external library types through their own
    # headers (H3's h3api.h, raster's GDAL, PROJ), so those include paths sit
    # among the defaults; _search_dirs drops the ones that do not exist.
    return _search_dirs(
        "MEOS_INCLUDE_DIR",
        "include",
        [
            "/usr/local/include",
            "/opt/homebrew/include",
            "/usr/include/h3",
            "/usr/include/gdal",
            "/usr/include/proj",
        ],
    )


# Compile the MEOS headers with every optional family enabled, matching the
# all-families libmeos and the catalog it is derived from — the declarations
# guarded by ``#if <FAMILY>`` are otherwise preprocessed out and diverge from
# the catalog. In sync with MobilityDB CMakeLists.txt's ``if(ALL)`` loop.
ALL_FAMILIES = (
    "ARROW",
    "CBUFFER",
    "H3",
    "JSON",
    "NPOINT",
    "POINTCLOUD",
    "POSE",
    "QUADBIN",
    "RASTER",
    "RGEO",
)

ffibuilder.set_source(
    "_meos_cffi",
    "\n".join(f'#include "{h}"' for h in header_files),
    libraries=["meos"],
    library_dirs=get_library_dirs(),
    include_dirs=get_include_dirs(),
    define_macros=[("MEOS", "1")] + [(f, "1") for f in ALL_FAMILIES],
)

if __name__ == "__main__":  # not when running with setuptools
    ffibuilder.compile(verbose=True)
