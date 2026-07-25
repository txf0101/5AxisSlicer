from __future__ import annotations

import os
from pathlib import Path

from setuptools import setup


def native_build() -> tuple[list[object], dict[str, object]]:
    """Return native build hooks only when the caller explicitly opts in."""
    if os.environ.get("FIVE_AXIS_BUILD_NATIVE") != "1":
        return [], {}

    from pybind11.setup_helpers import Pybind11Extension, build_ext

    warning_flags = ["/W4"] if os.name == "nt" else ["-Wall", "-Wextra", "-Wpedantic"]
    extension = Pybind11Extension(
        "five_axis_slicer_native",
        [str(Path("native") / "five_axis_slicer_native.cpp")],
        cxx_std=17,
        extra_compile_args=warning_flags,
    )
    return [extension], {"build_ext": build_ext}


extensions, commands = native_build()
setup(
    ext_modules=extensions,
    cmdclass=commands,
)
