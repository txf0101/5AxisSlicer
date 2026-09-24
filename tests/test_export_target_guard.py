"""A six-file export must never replace a project or unrelated user files."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from five_axis_slicer.postprocessing.curve_product import export_curve_product
from five_axis_slicer.postprocessing.freeform_product import export_freeform_product
from five_axis_slicer.postprocessing.indexed_tube import export_indexed_product
from five_axis_slicer.postprocessing.planar_product import export_planar_product
from five_axis_slicer.postprocessing.rotary_product import export_rotary_product
from five_axis_slicer.postprocessing.export_target_guard import (
    ARTIFACT_NAMES,
    validate_export_target,
)


@pytest.mark.parametrize("export", [
    export_curve_product,
    export_freeform_product,
    export_indexed_product,
    export_planar_product,
    export_rotary_product,
])
def test_export_preserves_project_directory(export, tmp_path: Path) -> None:
    target = tmp_path / "project"
    target.mkdir()
    project = target / "project.json"
    project.write_text('{"keep":true}', encoding="utf-8")
    snapshot = target / "preview.jpg"
    snapshot.write_bytes(b"keep")
    result = SimpleNamespace(exportable=True, offline_exportable=True)

    with pytest.raises(ValueError, match="contains a project or unrelated files"):
        export(result, target)

    assert project.read_text(encoding="utf-8") == '{"keep":true}'
    assert snapshot.read_bytes() == b"keep"
    assert {path.name for path in target.iterdir()} == {"project.json", "preview.jpg"}


def test_export_guard_accepts_only_new_or_previous_six_file_output(tmp_path: Path) -> None:
    target = tmp_path / "result"
    validate_export_target(target)
    target.mkdir()
    validate_export_target(target)
    for name in ARTIFACT_NAMES:
        (target / name).write_text("generated", encoding="utf-8")
    validate_export_target(target)
    (target / "notes.txt").write_text("user data", encoding="utf-8")
    with pytest.raises(ValueError, match="unrelated files"):
        validate_export_target(target)
