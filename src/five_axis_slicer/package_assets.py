"""Filesystem locations for read-only assets shipped with the application package."""

from __future__ import annotations

from pathlib import Path


PACKAGE_DIRECTORY = Path(__file__).resolve().parent
ASSET_DIRECTORY = PACKAGE_DIRECTORY / "assets"
IMPELLER_FOUR_PANEL_REFERENCE = ASSET_DIRECTORY / "impeller_four_panel_reference.png"


__all__ = [
    "ASSET_DIRECTORY",
    "IMPELLER_FOUR_PANEL_REFERENCE",
    "PACKAGE_DIRECTORY",
]
