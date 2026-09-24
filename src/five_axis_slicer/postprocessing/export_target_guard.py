"""Keep six-file exports from replacing a project or an unrelated folder."""

from __future__ import annotations

from pathlib import Path


ARTIFACT_NAMES = frozenset({
    "main.gcode", "toolpath.json", "machine_axes.csv",
    "warnings.json", "preview.json", "manifest.json",
})


def validate_export_target(target: Path) -> None:
    """Allow a new folder or a prior six-file export, preserving other data."""

    if target.is_symlink():
        raise ValueError("export destination cannot be a symbolic link")
    if not target.exists():
        return
    if not target.is_dir():
        raise ValueError("export destination is not a directory")
    children = tuple(target.iterdir())
    if not children:
        return
    if not (target / "manifest.json").is_file() or any(
        child.name not in ARTIFACT_NAMES or not child.is_file() or child.is_symlink()
        for child in children
    ):
        raise ValueError(
            "export destination contains a project or unrelated files; "
            "choose a new empty folder"
        )
