import os

from cffi import FFI

header_files = [
    "meos.h",
    "meos_catalog.h",
    "meos_geo.h",
    "meos_internal.h",
    "meos_internal_geo.h",
    "meos_npoint.h",
]

ffibuilder = FFI()

with open(os.path.join(os.path.dirname(__file__), "meos.h")) as f:
    content = f.read()

ffibuilder.cdef(content)


def get_library_dirs():
    paths = ["/usr/local/lib", "/opt/homebrew/lib"]
    return [path for path in paths if os.path.exists(path)]


def get_include_dirs():
    paths = ["/usr/local/include", "/opt/homebrew/include"]
    return [path for path in paths if os.path.exists(path)]


ffibuilder.set_source(
    "_meos_cffi",
    "\n".join(f'#include "{h}"' for h in header_files),
    libraries=["meos"],
    library_dirs=get_library_dirs(),
    include_dirs=get_include_dirs(),
)

if __name__ == "__main__":  # not when running with setuptools
    ffibuilder.compile(verbose=True)
