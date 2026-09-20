"""FAN08: independent body identity and non-overlapping material ownership."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import math

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from ...manufacturing.fan_job import FanGeometrySelection
from ...manufacturing.reference_descriptors import geometry_reference
from ...models import CadModel


@dataclass(frozen=True, slots=True)
class FanInterfaceAudit:
    body_ids: tuple[str, ...]
    pair_overlap_mm3: tuple[tuple[str, str, float], ...]
    root_gap_mm: tuple[tuple[str, float], ...]
    ownership_policy: str = "each solid owns its interior; zero-volume interface is shared"


def audit_fan_interfaces(model: CadModel, selection: FanGeometrySelection) -> FanInterfaceAudit:
    references = (selection.hub, *selection.blades)
    for reference in references:
        current = geometry_reference(model, reference.object_id, "body")
        if current.to_json() != reference.to_json():
            raise ValueError(f"fan.stale_body_reference: {reference.object_id}")
    ids = tuple(reference.object_id for reference in references)
    overlaps = tuple(
        (a, b, _overlap(model.shapes[a], model.shapes[b])) for a, b in combinations(ids, 2)
    )
    if any(volume > 1e-4 for _, _, volume in overlaps):
        raise ValueError(f"fan.overlapping_material_ownership: {overlaps}")
    gaps = tuple((blade, _distance(model.shapes[ids[0]], model.shapes[blade])) for blade in ids[1:])
    if any(gap > 0.005 for _, gap in gaps):
        raise ValueError(f"fan.disconnected_blade_root: {gaps}")
    return FanInterfaceAudit(ids, overlaps, gaps)


def blade_chart_center(model: CadModel, body_id: str) -> float:
    center = model.body_map[body_id].centroid
    if center is None:
        raise ValueError("fan.missing_blade_centroid")
    return math.atan2(center[1], center[0])


def _overlap(left, right):
    common = BRepAlgoAPI_Common(left, right)
    if not common.IsDone():
        raise ValueError("fan.interface_boolean_failed")
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(common.Shape(), properties)
    return abs(properties.Mass())


def _distance(left, right):
    distance = BRepExtrema_DistShapeShape(left, right)
    if not distance.IsDone():
        raise ValueError("fan.interface_distance_failed")
    return distance.Value()
