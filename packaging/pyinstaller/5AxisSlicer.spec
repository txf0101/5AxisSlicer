# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

spec_dir = Path(globals().get("SPECPATH", Path.cwd())).resolve()
repo_root = spec_dir.parents[1] if spec_dir.name == "pyinstaller" else Path.cwd().resolve()
packaging_dir = repo_root / "packaging"

sys.path.insert(0, str(packaging_dir))

from build_support import APP_NAME, app_datas, gmsh_binaries, hidden_imports

main_script = str(repo_root / "main.py")


a = Analysis(
    [main_script],
    pathex=[str(repo_root)],
    binaries=gmsh_binaries(),
    datas=app_datas(),
    hiddenimports=hidden_imports(),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

gui_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

collected_targets = []
if sys.platform == "darwin":
    gui_app = BUNDLE(
        gui_exe,
        name=f"{APP_NAME}.app",
        icon=None,
        bundle_identifier="io.github.tangxufeng.5axisslicer",
    )
    collected_targets.append(gui_app)
else:
    cli_exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=f"{APP_NAME}-cli",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
    )
    collected_targets.extend([gui_exe, cli_exe])

coll = COLLECT(
    *collected_targets,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)
