from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    GENERIC_NOZZLE_0_4,
    SourceReference,
)
from five_axis_slicer.tube_resource_selection import (  # noqa: E402
    configured_nozzle_copy,
    nozzle_editor_profile,
)


def measured_nozzle_fields() -> dict[str, object]:
    return {
        "interface": "M6",
        "length_mm": 12.5,
        "construction_material": "brass",
        "flow_category": "standard",
        "temperature_limit_c": 300.0,
        "wear_resistance_rating": "standard",
        "outer_profile_rz_mm": ((0.2, 0.0), (3.0, 2.0), (3.0, 12.5)),
    }


def test_complete_nozzle_requires_explicit_physical_fields() -> None:
    with pytest.raises(ValueError, match="outer_profile_rz_mm"):
        configured_nozzle_copy(
            GENERIC_NOZZLE_0_4,
            {
                key: value
                for key, value in measured_nozzle_fields().items()
                if key != "outer_profile_rz_mm"
            },
        )


def test_measured_nozzle_copy_is_ready_without_mutating_template() -> None:
    profile = configured_nozzle_copy(GENERIC_NOZZLE_0_4, measured_nozzle_fields())

    assert profile.is_ready
    assert profile.outer_profile_rz_mm[-1] == (3.0, 12.5)
    assert not profile.is_builtin
    assert not GENERIC_NOZZLE_0_4.is_ready
    assert GENERIC_NOZZLE_0_4.outer_profile_rz_mm == ()


def test_nozzle_editor_returns_an_unchanged_selected_profile() -> None:
    profile = configured_nozzle_copy(GENERIC_NOZZLE_0_4, measured_nozzle_fields())

    selected = nozzle_editor_profile(
        profile,
        interface="M6",
        length_mm=12.5,
        use_collision_envelope=True,
    )

    assert selected is profile


def test_nozzle_editor_keeps_partial_physical_data_explicit() -> None:
    profile = nozzle_editor_profile(
        GENERIC_NOZZLE_0_4,
        interface="",
        length_mm=12.5,
        use_collision_envelope=False,
    )

    assert profile.length_mm == 12.5
    assert profile.interface is None
    assert profile.construction_material is None
    assert profile.flow_category is None
    assert profile.outer_profile_rz_mm == ()
    assert not profile.is_ready


def test_nozzle_editor_preserves_measured_shape_during_text_edit() -> None:
    profile = configured_nozzle_copy(GENERIC_NOZZLE_0_4, measured_nozzle_fields())

    edited = nozzle_editor_profile(
        profile,
        interface="M6×1",
        length_mm=12.5,
        use_collision_envelope=True,
    )

    assert edited is not profile
    assert edited.outer_profile_rz_mm == profile.outer_profile_rz_mm
    assert edited.construction_material == "brass"


@pytest.mark.parametrize(
    "outer_profile",
    (
        ((0.2, -0.1), (3.0, 12.5)),
        ((0.2, 1.0), (3.0, 12.5)),
        ((0.2, 0.0), (3.0, 0.0)),
        ((0.2, 0.0), (3.0, 12.0)),
        ((0.2, 0.0), (3.0, 12.5), (2.0, 5.0)),
        ((0.0, 0.0), (0.0, 12.5)),
        ((0.19, 0.0), (3.0, 12.5)),
        ((-0.01, 0.0), (3.0, 12.5)),
        ((float("nan"), 0.0), (3.0, 12.5)),
        ((0.2, 0.0), (3.0, float("inf"))),
    ),
)
def test_nozzle_rejects_inconsistent_rz_extent(
    outer_profile: tuple[tuple[float, float], ...],
) -> None:
    profile = replace(
        configured_nozzle_copy(GENERIC_NOZZLE_0_4, measured_nozzle_fields()),
        outer_profile_rz_mm=outer_profile,
    )

    assert "nozzle.outer_profile_invalid" in {issue.code for issue in profile.readiness_blockers}


def test_nozzle_rejects_rz_points_with_extra_values() -> None:
    with pytest.raises(TypeError, match="radius, z"):
        replace(
            GENERIC_NOZZLE_0_4,
            outer_profile_rz_mm=((0.2, 0.0, 1.0), (3.0, 12.5, 1.0)),
        )


def test_nozzle_editor_requires_length_before_generating_shape() -> None:
    with pytest.raises(ValueError, match="length_mm is required"):
        nozzle_editor_profile(
            GENERIC_NOZZLE_0_4,
            interface="M6×1",
            length_mm=0.0,
            use_collision_envelope=True,
        )


def test_nozzle_editor_rejects_length_change_with_existing_shape() -> None:
    profile = configured_nozzle_copy(GENERIC_NOZZLE_0_4, measured_nozzle_fields())

    with pytest.raises(ValueError, match="cannot change"):
        nozzle_editor_profile(
            profile,
            interface="M6",
            length_mm=18.0,
            use_collision_envelope=True,
        )


def test_physical_edits_clear_template_source_attribution() -> None:
    source = SourceReference(
        title="Measured nozzle drawing",
        url="https://example.com/nozzle.pdf",
        revision="rev-a",
        file_path="nozzle.pdf",
        sha256="0" * 64,
    )
    template = replace(
        configured_nozzle_copy(GENERIC_NOZZLE_0_4, measured_nozzle_fields()),
        source=source,
    )

    edited = nozzle_editor_profile(
        template,
        interface="M6×1",
        length_mm=12.5,
        use_collision_envelope=True,
    )

    assert edited.source is None
