import os
import platform
import shutil
import sys

from setuptools import setup

# Add current directory to sys.path to be able to run builder functions
current_directory = os.path.abspath(os.path.dirname(__file__))
if current_directory not in sys.path:
    sys.path.append(current_directory)

from builder.build_header import build_header_file
from builder.build_pymeos_functions import build_pymeos_functions


def build_pymeos():  # Build Header File
    if os.environ.get("MEOS_LIB"):
        include_dir = os.environ.get("MEOS_LIB")
    else:
        if sys.platform == "linux":
            include_dir = "/usr/local/include"
        elif sys.platform == "darwin":
            if platform.processor() == "arm":
                include_dir = "/opt/homebrew/include"
            else:
                include_dir = "/usr/local/include"
        else:
            raise ValueError(
                "Unable to determine MEOS include directory. Please specify the location "
                "dir of MEOS header files (meos.h, meos_catalog.h, meos_internal.h) using "
                "the MEOS_LIB environment variable."
            )

    if os.environ.get("MEOS_BIN"):
        meos_bin = os.environ.get("MEOS_BIN")
    else:
        if sys.platform == "linux":
            meos_bin = "/usr/local/lib/libmeos.so"
        elif sys.platform == "darwin":
            if platform.processor() == "arm":
                meos_bin = "/opt/homebrew/lib/libmeos.dylib"
            else:
                meos_bin = "/usr/local/lib/libmeos.dylib"
        else:
            raise ValueError(
                "Unable to determine MEOS binary path. Please specify the location "
                "of the MEOS library binary using the MEOS_BIN environment variable."
            )

    header_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "builder", "meos.h")
    )

    build_header_file(include_dir, meos_bin, header_path)

    # Build PyMEOS-CFFI Functions
    build_pymeos_functions(header_path)


cffi_modules = []

if "bdist_wheel" in sys.argv:
    build_pymeos()
    cffi_modules.append("builder/build_pymeos.py:ffibuilder")
else:
    init_template = os.path.join(
        os.path.dirname(__file__), "builder", "templates", "init.py"
    )
    init_file = os.path.join(os.path.dirname(__file__), "pymeos_cffi", "__init__.py")
    with open(init_template, "r") as i, open(init_file, "w") as o:
        lines = i.readlines()
        version_line = next(line for line in lines if line.startswith("__version__"))
        o.write(version_line)


# Copy PROJ data to package data
package_data = []

# Conditionally copy PROJ DATA to make self-contained wheels
if os.environ.get("PACKAGE_DATA"):
    print("Copying PROJ data to package data")
    projdatadir = os.environ.get(
        "PROJ_DATA", os.environ.get("PROJ_LIB", "/usr/local/share/proj")
    )
    if os.path.exists(projdatadir):
        shutil.rmtree("pymeos_cffi/proj_data", ignore_errors=True)
        shutil.copytree(
            projdatadir,
            "pymeos_cffi/proj_data",
            ignore=shutil.ignore_patterns("*.txt", "*.tif"),
        )  # Don't copy .tiff files and their related .txt files
    else:
        raise FileNotFoundError(
            f"PROJ data directory not found at {projdatadir}. "
            f"Unable to generate self-contained wheel."
        )
    package_data.append("proj_data/*")
else:
    print("Not copying PROJ data to package data")


setup(
    packages=["pymeos_cffi"],
    package_data={"pymeos_cffi": package_data},
    setup_requires=["cffi"],
    cffi_modules=cffi_modules,
)
