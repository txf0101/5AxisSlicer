from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

APP_NAME = "5AxisSlicer"
COMPANY_NAME = "Tang Xufeng"
PUBLISHER = "Tang Xufeng"

_VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent



def package_root() -> Path:
    return project_root() / "five_axis_slicer"



def read_version() -> str:
    init_path = package_root() / "__init__.py"
    match = _VERSION_RE.search(init_path.read_text(encoding="utf-8-sig"))
    if not match:
        raise RuntimeError(f"Could not find __version__ in {init_path}")
    return match.group(1)



def app_datas() -> list[tuple[str, str]]:
    datas: list[tuple[str, str]] = []
    for path in sorted((package_root() / "assets").glob("*")):
        if path.is_file():
            datas.append((str(path), "five_axis_slicer/assets"))
    return datas



def hidden_imports() -> list[str]:
    return [
        "gmsh",
        "matplotlib.backends.backend_qtagg",
        "mpl_toolkits.mplot3d",
        "PyQt6.sip",
    ]



def _runtime_patterns() -> tuple[str, list[str]]:
    if sys.platform.startswith("win"):
        return (
            ".",
            [
                "gmsh*.dll",
                "TK*.dll",
                "tbb*.dll",
                "mkl_tbb_thread*.dll",
                "msvcp*.dll",
                "vcruntime*.dll",
                "ucrtbase.dll",
                "api-ms-win-crt-*.dll",
                "concrt*.dll",
                "vcomp*.dll",
                "libiomp*.dll",
                "libgcc*.dll",
                "libstdc++*.dll",
                "libwinpthread*.dll",
                "libgomp*.dll",
                "libatomic*.dll",
                "libquadmath*.dll",
                "libgfortran*.dll",
                "libgmp*.dll",
                "libssp*.dll",
                "libblas.dll",
                "libcblas.dll",
                "liblapack.dll",
                "zlib.dll",
                "freetype.dll",
                "FreeImage*.dll",
                "freeimage*.dll",
                "opengl32sw.dll",
                "cairo*.dll",
                "glib-*.dll",
                "gobject-*.dll",
                "gmodule-*.dll",
                "gio-*.dll",
                "fontconfig*.dll",
                "graphite2.dll",
                "expat.dll",
                "charset.dll",
                "ffi*.dll",
                "icu*.dll",
                "libcrypto-*.dll",
                "libssl-*.dll",
                "libxml2.dll",
                "sqlite3.dll",
                "iconv*.dll",
                "deflate.dll",
                "bzip2.dll",
            ],
        )
    if sys.platform == "darwin":
        return (
            "lib",
            [
                "libgmsh*.dylib",
                "libTK*.dylib",
                "libtbb*.dylib",
                "libomp*.dylib",
                "libiomp*.dylib",
                "libfreetype*.dylib",
                "libz*.dylib",
                "libfreeimage*.dylib",
            ],
        )
    return (
        "lib",
        [
            "libgmsh*.so*",
            "libTK*.so*",
            "libtbb*.so*",
            "libomp*.so*",
            "libiomp*.so*",
            "libfreetype*.so*",
            "libz*.so*",
            "libfreeimage*.so*",
        ],
    )



def _runtime_source_directories() -> list[Path]:
    seen: set[str] = set()
    directories: list[Path] = []

    def add(path: Path | None) -> None:
        if path is None:
            return
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = str(resolved).lower()
        if key in seen or not resolved.exists():
            return
        seen.add(key)
        directories.append(resolved)

    prefix = Path(sys.prefix)
    add(prefix / "Library" / "bin")
    add(prefix / "Library" / "mingw-w64" / "bin")
    add(prefix / "DLLs")
    add(prefix / "bin")
    add(prefix / "lib")

    gmsh_spec = importlib.util.find_spec("gmsh")
    if gmsh_spec and gmsh_spec.origin:
        module_dir = Path(gmsh_spec.origin).resolve().parent
        add(module_dir)
        add(module_dir.parent)
        add(module_dir.parent.parent)
        add(module_dir.parent.parent / "Library" / "bin")
        add(module_dir.parent.parent / "Library" / "mingw-w64" / "bin")
        add(module_dir.parent.parent / "lib")

    return directories



def gmsh_binaries() -> list[tuple[str, str]]:
    destination, patterns = _runtime_patterns()
    binaries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for directory in _runtime_source_directories():
        for pattern in patterns:
            for path in sorted(directory.glob(pattern)):
                if not path.is_file():
                    continue
                key = str(path.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                binaries.append((str(path), destination))
    return binaries



def main() -> int:
    parser = argparse.ArgumentParser(description="Build metadata helper for 5AxisSlicer packaging")
    parser.add_argument("--version", action="store_true", help="Print the current application version")
    parser.add_argument("--app-name", action="store_true", help="Print the application name")
    args = parser.parse_args()

    if args.version:
        print(read_version())
        return 0
    if args.app_name:
        print(APP_NAME)
        return 0

    parser.print_help()
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
