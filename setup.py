import os
import shutil

from setuptools import setup


def package_proj_data() -> str:
    print("Copying PROJ data to package data")
    projdatadir = os.environ.get("PROJ_DATA", os.environ.get("PROJ_LIB", "/usr/local/share/proj"))
    if os.path.exists(projdatadir):
        shutil.rmtree("pymeos_cffi/proj_data", ignore_errors=True)
        shutil.copytree(
            projdatadir,
            "pymeos_cffi/proj_data",
            ignore=shutil.ignore_patterns("*.txt", "*.tif"),
        )  # Don't copy .tiff files and their related .txt files
    else:
        raise FileNotFoundError(
            f"PROJ data directory not found at {projdatadir}. Unable to generate self-contained wheel."
        )
    return "proj_data/*"


def package_meos_data() -> str:
    print("Copying MEOS spatial reference table to package data")
    spatial_ref_sys_path = os.environ.get("MEOS_SPATIAL_REF_SYS_PATH", "/usr/local/share/spatial_ref_sys.csv")
    shutil.rmtree("pymeos_cffi/meos_data", ignore_errors=True)
    os.makedirs("pymeos_cffi/meos_data", exist_ok=True)
    shutil.copy(
        spatial_ref_sys_path,
        "pymeos_cffi/meos_data/spatial_ref_sys.csv",
    )
    return "meos_data/*"


package_data = []

if os.environ.get("PACKAGE_DATA"):
    print("Packaging data for self-contained wheel")
    package_data.append(package_proj_data())
    package_data.append(package_meos_data())
else:
    print("Not packaging data")


setup(
    packages=["pymeos_cffi"],
    package_data={"pymeos_cffi": package_data},
    setup_requires=["cffi"],
    cffi_modules=["builder/build_pymeos.py:ffibuilder"],
)
