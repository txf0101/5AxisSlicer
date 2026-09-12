from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path
import runpy
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.rotary import RotaryPlanningError, build_rotary_plan
from five_axis_slicer.manufacturing.coordinates import RigidTransform
from five_axis_slicer.manufacturing.rotary_parameters import (
    RotaryAngularRegion,
    RotaryFrame,
    RotaryGeometrySelection,
    RotaryOperationDefinition,
    RotaryProcessParameters,
    RotaryProfile,
)

TRUTH = json.loads(
    (Path(__file__).parent / "fixtures" / "analytic_rotary_truth.json").read_text(
        encoding="utf-8"
    )
)


def test_truth_fixture_matches_independent_derivation_script() -> None:
    namespace = runpy.run_path(
        str(Path(__file__).parent / "fixtures" / "derive_analytic_rotary_truth.py")
    )
    derived = namespace["derive"]()
    for section in ("cylinder_spiral", "cone_spiral", "thin_wall", "around_part"):
        assert derived[section]["length"] == pytest.approx(TRUTH[section]["length"], abs=1e-9)
        assert derived[section]["volume"] == pytest.approx(TRUTH[section]["volume"], abs=1e-9)


def _frame() -> RotaryFrame:
    return RotaryFrame((10, -20, 5), (0, 0, 1), (1, 0, 0))


def _operation(
    operation_type: str,
    profile: RotaryProfile,
    parameters: RotaryProcessParameters,
    regions: tuple[RotaryAngularRegion, ...] = (),
) -> RotaryOperationDefinition:
    return RotaryOperationDefinition(
        "rotary-test",
        "setup-test",
        operation_type=operation_type,
        geometry=RotaryGeometrySelection(_frame(), profile, regions),
        parameters=parameters,
    )


def _deposition_groups(plan):
    return [
        plan.points[path.start_point_index : path.end_point_index + 1]
        for path in plan.paths
    ]


def _axis_measurement(point):
    offset = tuple(a - b for a, b in zip(point.position, (10.0, -20.0, 5.0)))
    axial = offset[2]
    radius = math.hypot(offset[0], offset[1])
    wrapped = math.atan2(offset[1], offset[0])
    return axial, radius, wrapped


def test_r02_cylinder_spiral_matches_independent_truth_and_crosses_periods() -> None:
    expected = TRUTH["cylinder_spiral"]
    operation = _operation(
        "rotary_spiral",
        RotaryProfile(4, 28, 12, 12),
        RotaryProcessParameters(
            pitch_mm=8,
            start_angle_rad=expected["start_angle"],
            end_angle_rad=expected["end_angle"],
            sampling_angle_rad=math.radians(1),
            bead_width_mm=0.8,
            layer_height_mm=0.4,
            feedrate_mm_min=362.020752228998,
        ),
    )
    plan = build_rotary_plan(operation)
    deposited = _deposition_groups(plan)[0]
    assert deposited[0].position == pytest.approx(expected["start"], abs=1e-12)
    assert deposited[-1].position == pytest.approx(expected["end"], abs=1e-12)
    assert deposited[-1].unwrapped_angle_rad - deposited[0].unwrapped_angle_rad == pytest.approx(
        6 * math.pi
    )
    assert plan.deposition_length_mm == pytest.approx(expected["length"], abs=0.003)
    assert plan.material_volume_mm3 == pytest.approx(expected["volume"], abs=0.001)
    assert [event.event_type for event in plan.events] == [
        "safe_approach",
        "index_start",
        "prime",
        "index_end",
        "retract",
        "safe_depart",
        "finish",
    ]
    angles = [point.unwrapped_angle_rad for point in deposited]
    assert max(abs(right - left) for left, right in zip(angles, angles[1:])) < 0.02


def test_r02_cone_spiral_has_linear_radius_and_true_cone_normals() -> None:
    expected = TRUTH["cone_spiral"]
    operation = _operation(
        "rotary_spiral",
        RotaryProfile(0, 12, 15, 9),
        RotaryProcessParameters(
            pitch_mm=6,
            start_angle_rad=0,
            end_angle_rad=4 * math.pi,
            sampling_angle_rad=math.radians(1),
            bead_width_mm=0.75,
            layer_height_mm=0.3,
        ),
    )
    plan = build_rotary_plan(operation)
    deposited = _deposition_groups(plan)[0]
    independently_measured = [_axis_measurement(point) for point in deposited]
    assert independently_measured[0][:2] == pytest.approx((0, 15), abs=1e-10)
    assert independently_measured[-1][:2] == pytest.approx((12, 9), abs=1e-10)
    slopes = [
        (right[1] - left[1]) / (right[0] - left[0])
        for left, right in zip(independently_measured, independently_measured[1:])
    ]
    assert max(abs(value + 0.5) for value in slopes) < 1e-9
    assert plan.deposition_length_mm == pytest.approx(expected["length"], abs=0.003)
    assert plan.material_volume_mm3 == pytest.approx(expected["volume"], abs=0.001)
    assert deposited[0].surface_normal == pytest.approx(
        (1 / math.sqrt(1.25), 0, 0.5 / math.sqrt(1.25)), abs=1e-12
    )
    assert abs(sum(a * b for a, b in zip(deposited[0].surface_normal, deposited[0].tangent))) < 1e-12


def test_r01_nondefault_build_transform_preserves_geometry_and_rotates_frame() -> None:
    operation = _operation(
        "rotary_spiral",
        RotaryProfile(4, 12, 12, 12),
        RotaryProcessParameters(pitch_mm=8, sampling_angle_rad=math.radians(2)),
    )
    transform = RigidTransform.from_rotation_translation(
        ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
        (7, -11, 13),
        source_frame="source",
        target_frame="build",
    )
    source = build_rotary_plan(operation)
    build = build_rotary_plan(operation, T_build_from_source=transform)
    assert build.region_analysis.axis_origin_mm == pytest.approx((12, -1, -7))
    assert build.region_analysis.axis_direction == pytest.approx((1, 0, 0))
    assert build.region_analysis.zero_direction == pytest.approx((0, 1, 0))
    assert build.deposition_length_mm == pytest.approx(source.deposition_length_mm)
    for left, right in zip(source.points, build.points, strict=True):
        assert right.position == pytest.approx(transform.transform_point(left.position))
        assert right.surface_normal == pytest.approx(
            transform.transform_vector(left.surface_normal)
        )


def test_r03_thin_wall_has_known_layers_passes_snaking_and_volume() -> None:
    expected = TRUTH["thin_wall"]
    operation = _operation(
        "rotary_thin_wall",
        RotaryProfile(2, 14, 10, 10),
        RotaryProcessParameters(
            axial_step_mm=4,
            radial_pass_count=3,
            radial_spacing_mm=0.8,
            wall_thickness_mm=2.4,
            bead_width_mm=0.8,
            layer_height_mm=0.4,
            sampling_angle_rad=math.radians(1),
        ),
    )
    plan = build_rotary_plan(operation)
    assert len(plan.paths) == expected["layers"] * expected["passes_per_layer"]
    radii = []
    sweeps = []
    for group in _deposition_groups(plan):
        radii.append(_axis_measurement(group[0])[1])
        sweeps.append(group[-1].unwrapped_angle_rad - group[0].unwrapped_angle_rad)
    assert sorted(set(round(value, 8) for value in radii)) == expected["radii"]
    assert [math.copysign(1, value) for value in sweeps] == [1, -1] * 6
    assert plan.deposition_length_mm == pytest.approx(expected["length"], abs=0.012)
    assert plan.material_volume_mm3 == pytest.approx(expected["volume"], abs=0.004)
    assert sum(event.event_type == "retract" for event in plan.events) == 12
    assert sum(event.event_type == "prime" for event in plan.events) == 12


def test_rotary_connections_have_clearance_entry_exit_and_ordered_events() -> None:
    operation = _operation(
        "rotary_thin_wall",
        RotaryProfile(0, 1, 10, 10),
        RotaryProcessParameters(
            axial_step_mm=1,
            radial_pass_count=2,
            radial_spacing_mm=0.8,
            wall_thickness_mm=1.6,
            connection_clearance_mm=3.0,
            sampling_angle_rad=math.radians(10),
        ),
    )
    plan = build_rotary_plan(operation)
    assert plan.points[0].point_type == "travel"
    assert plan.points[1].point_type == "approach"
    assert plan.points[-1].point_type == "depart"
    assert _axis_measurement(plan.points[0])[1] - _axis_measurement(plan.points[1])[1] == (
        pytest.approx(3.0)
    )
    assert _axis_measurement(plan.points[-1])[1] - _axis_measurement(plan.points[-2])[1] == (
        pytest.approx(3.0)
    )
    event_types = [event.event_type for event in plan.events]
    assert event_types[:3] == ["safe_approach", "index_start", "prime"]
    assert event_types[-3:] == ["retract", "safe_depart", "finish"]
    boundary = event_types.index("safe_depart")
    assert event_types[boundary - 1] == "retract"
    assert "safe_approach" in event_types[boundary + 1 :]


def test_r04_around_part_unwraps_350_to_20_and_uses_short_cross_region_phase() -> None:
    expected = TRUTH["around_part"]
    regions = (
        RotaryAngularRegion("A", math.radians(350), math.radians(20), "ccw"),
        RotaryAngularRegion("B", math.radians(120), math.radians(210), "ccw"),
    )
    operation = _operation(
        "rotary_around_part",
        RotaryProfile(0, 1.6, 20, 20),
        RotaryProcessParameters(
            axial_step_mm=0.8,
            bead_width_mm=0.8,
            layer_height_mm=0.4,
            sampling_angle_rad=math.radians(1),
        ),
        regions,
    )
    plan = build_rotary_plan(operation)
    endpoints = [
        (
            math.degrees(plan.points[path.start_point_index].unwrapped_angle_rad),
            math.degrees(plan.points[path.end_point_index].unwrapped_angle_rad),
        )
        for path in plan.paths
    ]
    assert [value for pair in endpoints for value in pair] == pytest.approx(
        [350, 380, 380, 350, 350, 380, 480, 570, 570, 480, 480, 570]
    )
    assert endpoints[3][0] - endpoints[2][1] == pytest.approx(100)
    assert plan.deposition_length_mm == pytest.approx(expected["length"], abs=0.01)
    assert plan.material_volume_mm3 == pytest.approx(expected["volume"], abs=0.004)
    for left, right in zip(plan.points, plan.points[1:]):
        if left.region_id != right.region_id:
            assert right.point_type != "deposition"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"axis_direction": (0, 0, 0)}, "rotary.axis_invalid"),
        ({"zero_direction": (0, 0, 2)}, "rotary.zero_direction_invalid"),
    ],
)
def test_r01_invalid_rotary_frames_are_locatable(change, code) -> None:
    with pytest.raises(ValueError, match=code):
        RotaryFrame(**change)


def test_r02_apex_and_period_failures_are_locatable() -> None:
    with pytest.raises(ValueError, match="rotary.period_ambiguous"):
        RotaryProcessParameters(start_angle_rad=0, end_angle_rad=0)
    operation = _operation(
        "rotary_spiral",
        RotaryProfile(0, 10, 5, 0.00000000001),
        RotaryProcessParameters(pitch_mm=10),
    )
    with pytest.raises(RotaryPlanningError, match="rotary.cone_apex_degenerate"):
        build_rotary_plan(operation)


def test_r03_thin_wall_below_bead_width_has_error_or_reduced_warning() -> None:
    base = _operation(
        "rotary_thin_wall",
        RotaryProfile(0, 2, 10, 10),
        RotaryProcessParameters(
            bead_width_mm=0.8,
            wall_thickness_mm=0.5,
            radial_pass_count=1,
            axial_step_mm=2,
        ),
    )
    with pytest.raises(RotaryPlanningError, match="rotary.thin_wall_below_minimum"):
        build_rotary_plan(base)
    reduced = build_rotary_plan(
        replace(
            base,
            parameters=replace(base.parameters, thin_wall_width_policy="reduce"),
        )
    )
    assert "rotary.thin_wall_width_reduced" in reduced.issues
    assert {
        point.bead_width_mm
        for point in reduced.points
        if point.point_type == "deposition"
    } == {0.5}


def test_display_only_change_is_not_part_of_rotary_semantic_hash() -> None:
    operation = _operation(
        "rotary_spiral",
        RotaryProfile(0, 5, 12, 12),
        RotaryProcessParameters(),
    )
    original = operation.semantic_sha256()
    assert replace(operation, parameters=replace(operation.parameters, bead_width_mm=0.7)).semantic_sha256() != original
    assert operation.semantic_sha256() == original


def test_r02_cw_and_negative_frame_direction_reverse_geometric_winding() -> None:
    profile = RotaryProfile(0, 5, 10, 10)
    clockwise = _operation(
        "rotary_spiral",
        profile,
        RotaryProcessParameters(
            pitch_mm=5,
            direction="cw",
            start_angle_rad=0,
            end_angle_rad=-math.tau,
            sampling_angle_rad=math.radians(10),
        ),
    )
    clockwise_plan = build_rotary_plan(clockwise)
    assert clockwise_plan.points[-1].unwrapped_angle_rad == pytest.approx(-math.tau)
    clockwise_path = _deposition_groups(clockwise_plan)[0]
    assert clockwise_path[1].position[1] < clockwise_path[0].position[1]

    negative_frame = replace(
        clockwise,
        parameters=replace(
            clockwise.parameters,
            direction="ccw",
            end_angle_rad=math.tau,
        ),
        geometry=replace(
            clockwise.geometry,
            frame=replace(clockwise.geometry.frame, positive_direction=-1),
        ),
    )
    negative_plan = build_rotary_plan(negative_frame)
    assert negative_plan.points[-1].unwrapped_angle_rad == pytest.approx(math.tau)
    negative_path = _deposition_groups(negative_plan)[0]
    assert negative_path[1].position[1] < negative_path[0].position[1]


def test_r01_transform_requires_explicit_source_to_build_frames() -> None:
    operation = _operation(
        "rotary_spiral",
        RotaryProfile(0, 5, 10, 10),
        RotaryProcessParameters(),
    )
    invalid = RigidTransform.identity("source")
    with pytest.raises(RotaryPlanningError, match="rotary.build_frame_invalid"):
        build_rotary_plan(operation, T_build_from_source=invalid)


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"radius_start_mm": 0}, "rotary.radius_invalid"),
        ({"radius_end_mm": -1}, "rotary.radius_invalid"),
    ],
)
def test_r01_invalid_profile_radius_is_locatable(kwargs, code) -> None:
    with pytest.raises(ValueError, match=code):
        RotaryProfile(**kwargs)


def test_r02_invalid_pitch_is_locatable() -> None:
    with pytest.raises(ValueError, match="rotary.pitch_mm_invalid"):
        RotaryProcessParameters(pitch_mm=0)
