import json
import os
import re

from cffi import FFI

# The headers to #include in the compiled extension: the defining header of
# every function the cdef (builder/meos.h) declares, and of every MEOS struct,
# both read from the catalog's own ``file`` field so a new family header rides
# in with the next catalog refresh — no hand-maintained list. Each cdef
# function thereby has its prototype in the compiled unit.
_builder_dir = os.path.dirname(__file__)
with open(os.path.join(_builder_dir, "meos-idl.json")) as f:
    _idl = json.load(f)
with open(os.path.join(_builder_dir, "meos.h")) as f:
    content = f.read()
_declared = set(re.findall(r"^extern .*?\b(\w+)\(", content, re.MULTILINE))
_files = {e["file"] for e in _idl["functions"] if e["name"] in _declared}
_files |= {e["file"] for e in _idl["structs"] if e["file"].startswith("meos")}
# meos.h first: the other headers build on the types it declares.
header_files = sorted(_files, key=lambda h: (h != "meos.h", h))

ffibuilder = FFI()
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
            "/usr/local/include/h3",
            "/opt/homebrew/include/h3",
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
    # A cdef function the #included headers do not declare would be called as
    # returning int, truncating every 64-bit result; refuse to build instead.
    extra_compile_args=["-Werror=implicit-function-declaration"],
)

if __name__ == "__main__":  # not when running with setuptools
    ffibuilder.compile(verbose=True)
