from __future__ import annotations

from pathlib import Path

from setuptools import setup

try:
    from pybind11.setup_helpers import Pybind11Extension, build_ext
except Exception:  # pragma: no cover - editable installs without C++ tools can still use Python modules.
    Pybind11Extension = None
    build_ext = None


ext_modules = []
cmdclass = {}
if Pybind11Extension is not None:
    ext_modules.append(
        Pybind11Extension(
            "five_axis_slicer_native",
            [str(Path("native") / "five_axis_slicer_native.cpp")],
            cxx_std=17,
        )
    )
    cmdclass["build_ext"] = build_ext


setup(ext_modules=ext_modules, cmdclass=cmdclass)
