from five_axis_slicer.manufacturing.toolpath import (
    GeneratedToolpath,
    ToolpathEvent,
    ToolpathPoint,
)
from five_axis_slicer.postprocessing.toolpath_sequence import merge_toolpath_sequence


def _path(operation, point, axis):
    points = (
        ToolpathPoint(
            operation + "-p1",
            point,
            (1, 0, 0),
            axis,
            operation,
            "stage",
            "layer",
            "region",
            "approach",
            feedrate_mm_min=3000,
        ),
        ToolpathPoint(
            operation + "-p2",
            (point[0] + 1, point[1], point[2]),
            (1, 0, 0),
            axis,
            operation,
            "stage",
            "layer",
            "region",
            "deposition",
            "infill",
            feedrate_mm_min=1200,
            bead_width_mm=0.4,
            layer_height_mm=0.2,
            material_volume_mm3=0.08,
        ),
    )
    return GeneratedToolpath(
        operation + "-path",
        operation,
        points=points,
        events=(
            ToolpathEvent(
                operation + "-prime",
                "prime",
                operation,
                "stage",
                "layer",
                "region",
                context={"sequence_index": 0, "extrusion_length_mm": 1.0},
            ),
        ),
    )


def test_merge_toolpath_sequence_adds_non_depositing_clearance_and_reindexes_events():
    base = _path("base", (0, 0, 1), (0, 0, -1))
    feature = _path("feature", (10, 0, 2), (-1, 0, 0))
    result = merge_toolpath_sequence(
        "combined",
        (base, feature),
        safe_clearance_mm=5,
        travel_feedrate_mm_min=3000,
        retract_length_mm=1,
    )
    assert len(result.points) == 6
    assert result.points[2].position == (1, 0, 6)
    assert result.points[3].position == (15, 0, 2)
    assert all(point.material_volume_mm3 == 0 for point in result.points[2:4])
    assert [event.event_type for event in result.events] == [
        "prime",
        "retract",
        "safe_depart",
        "operation_change",
        "safe_approach",
        "prime",
    ]
    assert result.events[-1].context["sequence_index"] == 4
    assert {point.operation_id for point in result.points} == {"combined"}


def test_merge_toolpath_sequence_rejects_duplicate_operations_and_frames():
    base = _path("base", (0, 0, 1), (0, 0, -1))
    try:
        merge_toolpath_sequence(
            "combined",
            (base, base),
            safe_clearance_mm=5,
            travel_feedrate_mm_min=3000,
            retract_length_mm=1,
        )
    except ValueError as error:
        assert "unique" in str(error)
    else:
        raise AssertionError("duplicate operations accepted")

    feature = GeneratedToolpath(
        "other-frame",
        "feature",
        coordinate_frame="other",
        points=tuple(
            ToolpathPoint(
                "other-" + point.point_id,
                point.position,
                point.tangent,
                point.nozzle_axis,
                "feature",
                point.stage_id,
                point.layer_id,
                point.region_id,
                point.point_type,
                point.extrusion_role,
                feedrate_mm_min=point.feedrate_mm_min,
                bead_width_mm=point.bead_width_mm,
                layer_height_mm=point.layer_height_mm,
                material_volume_mm3=point.material_volume_mm3,
            )
            for point in base.points
        ),
    )
    try:
        merge_toolpath_sequence(
            "combined",
            (base, feature),
            safe_clearance_mm=5,
            travel_feedrate_mm_min=3000,
            retract_length_mm=1,
        )
    except ValueError as error:
        assert "coordinate frame" in str(error)
    else:
        raise AssertionError("mixed coordinate frames accepted")
