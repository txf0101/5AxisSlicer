"""Conservative support-path checks against the selected target BRep.

The target CAD is a geometric exclusion domain, not a model of already
printed material. Part/support layer scheduling and nozzle sweeps are not
available here, so every reported intersection blocks export and a clear
qualification warning remains even when no intersection is found.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math

from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeVertex
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.gp import gp_Pnt

from ..manufacturing.coordinates import RigidTransform
from ..manufacturing.setup import IssueSeverity, ValidationIssue
from ..manufacturing.toolpath import GeneratedToolpath
from ..models import CadModel, Vector3

TARGET_CONTACT_TOLERANCE_MM = 1.0e-7


@dataclass(frozen=True)
class _Hit:
    point_id: str
    previous_point_id: str
    point_type: str
    start_build_mm: Vector3
    end_build_mm: Vector3


def support_cad_issues(
    toolpath: GeneratedToolpath,
    model: CadModel,
    body_id: str,
    T_model_from_build: RigidTransform,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[ValidationIssue, ...]:
    """Check complete 3-D segments and the initial point, without sampled gaps.

    OCCT whole-shape extrema detects both interior intersections and isolated
    boundary contacts. An OCCT failure is an Error, never a clear result.
    This read-only calculation does not enlarge target geometry tolerances.
    """
    _checkpoint(cancelled)
    boundary = _boundary_issue(body_id, len(toolpath.points))
    if toolpath.coordinate_frame != "workpiece_build":
        return boundary, _error(
            "planar.support_cad_frame_unsupported",
            body_id,
            {
                "coordinate_frame": toolpath.coordinate_frame,
            },
        )
    shape = model.shapes.get(body_id)
    if shape is None:
        return boundary, _error("planar.support_cad_unavailable", body_id, {})
    try:
        bounds = _solid_bounds(shape)
    except Exception as error:
        return boundary, _error("planar.support_cad_unavailable", body_id, {"detail": str(error)})
    hits, failure = _scan_path(toolpath, shape, bounds, T_model_from_build, cancelled)
    if failure is not None:
        return boundary, failure
    return (boundary, *_intersection_issues(hits, body_id))


def _scan_path(toolpath, shape, bounds, transform, cancelled):
    hits: list[_Hit] = []
    for index, current in enumerate(toolpath.points):
        _checkpoint(cancelled)
        previous = toolpath.points[index - 1] if index else current
        start = transform.transform_point(previous.position)
        end = transform.transform_point(current.position)
        if not _bounds_overlap(start, end, bounds):
            continue
        try:
            intersects = _intersects_shape(start, end, shape)
        except Exception as error:
            return hits, _error(
                "planar.support_cad_check_failed",
                current.point_id,
                {
                    "detail": str(error),
                    "previous_point_id": previous.point_id,
                },
            )
        if intersects:
            hits.append(
                _Hit(
                    current.point_id,
                    previous.point_id,
                    current.point_type,
                    previous.position,
                    current.position,
                )
            )
    return hits, None


def _solid_bounds(shape):
    if not TopExp_Explorer(shape, TopAbs_SOLID).More() or not BRepCheck_Analyzer(shape).IsValid():
        raise ValueError("a valid target solid is required")
    bounds = Bnd_Box()
    BRepBndLib.Add_s(shape, bounds, False)
    if bounds.IsVoid():
        raise ValueError("target solid has no bounds")
    return bounds.Get()


def _bounds_overlap(start, end, bounds):
    return all(
        max(start[axis], end[axis]) >= bounds[axis] - TARGET_CONTACT_TOLERANCE_MM
        and min(start[axis], end[axis]) <= bounds[axis + 3] + TARGET_CONTACT_TOLERANCE_MM
        for axis in range(3)
    )


def _intersects_shape(start, end, shape):
    segment = (
        BRepBuilderAPI_MakeVertex(gp_Pnt(*start)).Vertex()
        if math.dist(start, end) <= 1.0e-12
        else BRepBuilderAPI_MakeEdge(gp_Pnt(*start), gp_Pnt(*end)).Edge()
    )
    distance = BRepExtrema_DistShapeShape()
    distance.LoadS1(segment)
    distance.LoadS2(shape)
    distance.SetDeflection(TARGET_CONTACT_TOLERANCE_MM)
    distance.Perform()
    if not distance.IsDone():
        raise ValueError("OCCT target-solid distance calculation did not complete")
    return distance.InnerSolution() or distance.Value() <= TARGET_CONTACT_TOLERANCE_MM


def _intersection_issues(hits, body_id):
    issues = []
    for kind in ("travel", "deposition"):
        group = [hit for hit in hits if (hit.point_type == "deposition") == (kind == "deposition")]
        if not group:
            continue
        first = group[0]
        issues.append(
            _error(
                f"planar.support_{kind}_intersects_target_cad",
                first.point_id,
                {
                    "body_id": body_id,
                    "intersection_count": len(group),
                    "point_ids": [hit.point_id for hit in group[:32]],
                    "point_ids_truncated": len(group) > 32,
                    "first_previous_point_id": first.previous_point_id,
                    "first_point_type": first.point_type,
                    "first_start_build_mm": list(first.start_build_mm),
                    "first_end_build_mm": list(first.end_build_mm),
                    "basis": "selected_target_brep_including_boundary",
                    "contact_tolerance_mm": TARGET_CONTACT_TOLERANCE_MM,
                    "already_printed_state_assumed": False,
                },
            )
        )
    return tuple(issues)


def _boundary_issue(body_id: str, point_count: int) -> ValidationIssue:
    return ValidationIssue(
        "planar.support_joint_schedule_unverified",
        IssueSeverity.WARNING,
        context={
            "body_id": body_id,
            "path_point_count": point_count,
            "scope": "independent_support_operation_with_target_cad_centreline_check",
            "target_part_toolpath_included": False,
            "joint_layer_schedule_verified": False,
            "already_printed_state_available": False,
            "full_nozzle_sweep_verified": False,
        },
    )


def _error(code, object_id, context):
    return ValidationIssue(code, IssueSeverity.ERROR, object_id=object_id, context=context)


def _checkpoint(cancelled):
    if cancelled is not None and cancelled():
        from ..postprocessing.indexed_tube import GenerationCancelled

        raise GenerationCancelled("Planar support CAD validation cancelled")
