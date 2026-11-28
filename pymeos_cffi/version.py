"""The version of PyMEOS-CFFI, under its own name.

Each binding answers its own version under its own name, and the version of
the MEOS library it links under MEOS's name: #meos_version and
#meos_full_version, generated in functions.py from the catalog. The package
has no other version routine; these two stand beside #meos_full_version,
which the full version calls.
"""

from .functions import meos_full_version

__all__ = ["pymeos_cffi_version", "pymeos_cffi_full_version"]


def pymeos_cffi_version() -> str:
    """Return the version of PyMEOS-CFFI, its name first, as #meos_version
    answers MEOS's."""
    from . import __version__

    return f"PyMEOS-CFFI {__version__}"


def pymeos_cffi_full_version() -> str:
    """Return the version of PyMEOS-CFFI followed by the string of
    #meos_full_version: the MEOS library it links and MEOS's dependencies."""
    return f"{pymeos_cffi_version()}, {meos_full_version()}"
