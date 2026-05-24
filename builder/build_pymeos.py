import os

from cffi import FFI

header_files = [
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
    return _search_dirs("MEOS_INCLUDE_DIR", "include", ["/usr/local/include", "/opt/homebrew/include"])


ffibuilder.set_source(
    "_meos_cffi",
    "\n".join(f'#include "{h}"' for h in header_files),
    libraries=["meos"],
    library_dirs=get_library_dirs(),
    include_dirs=get_include_dirs(),
)

if __name__ == "__main__":  # not when running with setuptools
    ffibuilder.compile(verbose=True)
