"""Safe kinematic reconstruction for imported NC preview coordinates.

Imported NC positions are controller coordinates.  A workpiece-space preview
is produced only when the controller word semantics have been registered with
a validated machine profile.  Unsupported or ambiguous words leave the motion
in machine coordinates and emit stable, localisable validation issues.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Iterable, Mapping

from .coordinates import RigidTransform
from .machine import GENERIC_XYZAC_REFERENCE, MachineProfile
from .setup import IssueSeverity, ValidationIssue


MACHINE_COORDINATE_TRANSFORM = "machine_xyz"
AC_INVERSE_TRANSFORM = "ac_inverse_rz_minus_c_after_rx_minus_a"
GENERIC_XYZAC_AC_SEMANTICS = "generic_xyzac_reference.ac_table_deg.v1"
NC_PREVIEW_OBJECT_ID = "imported_nc_preview"

_ROTARY_WORDS = frozenset({"A", "B", "C", "U", "V", "W"})
_ZERO_TOLERANCE = 1.0e-12


@dataclass(frozen=True, slots=True)
class ControllerAxisSemantics:
    """A registered mapping from NC rotary words to a machine workpiece chain."""

    semantics_id: str
    machine_profile: MachineProfile
    workpiece_link_id: str
    transform_name: str

    def __post_init__(self) -> None:
        semantics_id = str(self.semantics_id).strip()
        workpiece_link_id = str(self.workpiece_link_id).strip()
        transform_name = str(self.transform_name).strip()
        if not semantics_id:
            raise ValueError("semantics_id must not be empty")
        if not workpiece_link_id:
            raise ValueError("workpiece_link_id must not be empty")
        if not transform_name:
            raise ValueError("transform_name must not be empty")
        self.machine_profile.validate()
        link_ids = {self.machine_profile.root_link_id}
        for joint in self.machine_profile.joints:
            link_ids.add(joint.parent_link_id)
            link_ids.add(joint.child_link_id)
        if workpiece_link_id not in link_ids:
            raise ValueError(f"unknown workpiece link: {workpiece_link_id}")
        if self.machine_profile.workpiece_link_id != workpiece_link_id:
            raise ValueError("workpiece_link_id must be the machine workpiece endpoint")
        if not self.controller_word_map:
            raise ValueError("registered semantics must map at least one rotary word")
        object.__setattr__(self, "semantics_id", semantics_id)
        object.__setattr__(self, "workpiece_link_id", workpiece_link_id)
        object.__setattr__(self, "transform_name", transform_name)

    @property
    def controller_word_map(self) -> Mapping[str, str]:
        mapping: dict[str, str] = {}
        for joint in self.machine_profile.joints:
            post_map = joint.post_axis_map
            if joint.joint_type != "rotary" or post_map is None:
                continue
            mapping[post_map.word] = joint.joint_id
        return MappingProxyType(mapping)

    @property
    def supported_rotary_words(self) -> frozenset[str]:
        return frozenset(self.controller_word_map)

    def joint_positions(
        self, controller_values: Mapping[str, float]
    ) -> dict[str, float]:
        """Decode controller values into the profile's internal joint units."""

        positions: dict[str, float] = {}
        for joint in self.machine_profile.joints:
            post_map = joint.post_axis_map
            if joint.joint_type != "rotary" or post_map is None:
                continue
            controller_value = float(controller_values.get(post_map.word, 0.0))
            effective_position = post_map.decode(controller_value, joint.joint_type)
            positions[joint.joint_id] = effective_position - joint.zero_offset
        return positions


@dataclass(frozen=True, slots=True)
class PreviewPoseReconstruction:
    point: tuple[float, float, float]
    nozzle_axis: tuple[float, float, float]
    coordinate_transform: str
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def reconstructed(self) -> bool:
        return self.coordinate_transform != MACHINE_COORDINATE_TRANSFORM


@dataclass(frozen=True, slots=True)
class PreviewMotionReconstruction:
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    start_nozzle_axis: tuple[float, float, float]
    end_nozzle_axis: tuple[float, float, float]
    coordinate_transform: str
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def reconstructed(self) -> bool:
        return self.coordinate_transform != MACHINE_COORDINATE_TRANSFORM


class PreviewKinematicsRegistry:
    """Read-only registry used by the NC parser and coordinate services."""

    def __init__(self, semantics: Iterable[ControllerAxisSemantics]) -> None:
        entries: dict[str, ControllerAxisSemantics] = {}
        for entry in semantics:
            if entry.semantics_id in entries:
                raise ValueError(
                    f"duplicate controller semantics: {entry.semantics_id}"
                )
            entries[entry.semantics_id] = entry
        self._entries = MappingProxyType(entries)

    def get(self, semantics_id: str | None) -> ControllerAxisSemantics | None:
        if semantics_id is None:
            return None
        return self._entries.get(str(semantics_id).strip())

    @property
    def semantics_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))


GENERIC_XYZAC_SEMANTICS = ControllerAxisSemantics(
    semantics_id=GENERIC_XYZAC_AC_SEMANTICS,
    machine_profile=GENERIC_XYZAC_REFERENCE,
    workpiece_link_id="c_table",
    transform_name=AC_INVERSE_TRANSFORM,
)

DEFAULT_PREVIEW_KINEMATICS_REGISTRY = PreviewKinematicsRegistry(
    (GENERIC_XYZAC_SEMANTICS,)
)


def reconstruct_preview_pose(
    machine_point: tuple[float, float, float],
    rotary_values: Mapping[str, float],
    *,
    controller_semantics: str | None = None,
    fixed_machine_nozzle_axis: tuple[float, float, float] = (0.0, 0.0, -1.0),
    registry: PreviewKinematicsRegistry = DEFAULT_PREVIEW_KINEMATICS_REGISTRY,
) -> PreviewPoseReconstruction:
    """Reconstruct one pose using a registered controller semantic definition."""

    motion = reconstruct_preview_motion(
        machine_point,
        machine_point,
        rotary_values,
        rotary_values,
        controller_semantics=controller_semantics,
        fixed_machine_nozzle_axis=fixed_machine_nozzle_axis,
        registry=registry,
    )
    return PreviewPoseReconstruction(
        point=motion.end,
        nozzle_axis=motion.end_nozzle_axis,
        coordinate_transform=motion.coordinate_transform,
        issues=motion.issues,
    )


def reconstruct_preview_motion(
    machine_start: tuple[float, float, float],
    machine_end: tuple[float, float, float],
    rotary_start: Mapping[str, float],
    rotary_end: Mapping[str, float],
    *,
    controller_semantics: str | None = None,
    fixed_machine_nozzle_axis: tuple[float, float, float] = (0.0, 0.0, -1.0),
    registry: PreviewKinematicsRegistry = DEFAULT_PREVIEW_KINEMATICS_REGISTRY,
) -> PreviewMotionReconstruction:
    """Reconstruct a complete motion atomically or preserve both machine points."""

    start = _vector3(machine_start, "machine_start")
    end = _vector3(machine_end, "machine_end")
    nozzle_axis = _unit_vector3(fixed_machine_nozzle_axis, "fixed_machine_nozzle_axis")
    start_values, start_issue = _normalise_rotary_values(rotary_start)
    end_values, end_issue = _normalise_rotary_values(rotary_end)
    if start_issue is not None or end_issue is not None:
        return _raw_motion(
            start, end, nozzle_axis, _unique_issues(start_issue, end_issue)
        )

    present_words = set(start_values) | set(end_values)
    active_words = {
        word
        for word, value in (*start_values.items(), *end_values.items())
        if abs(value) > _ZERO_TOLERANCE
    }
    semantics_required_words = active_words | (present_words & {"U", "V", "W"})
    if not semantics_required_words:
        return _raw_motion(start, end, nozzle_axis)

    semantics = registry.get(controller_semantics)
    if semantics is None:
        issue = ValidationIssue(
            code="nc_preview.controller_semantics_unknown",
            severity=IssueSeverity.WARNING,
            object_id=NC_PREVIEW_OBJECT_ID,
            context={
                "controller_semantics": (
                    "" if controller_semantics is None else str(controller_semantics)
                ),
                "active_rotary_words": sorted(active_words),
                "present_rotary_words": sorted(present_words),
            },
        )
        return _raw_motion(start, end, nozzle_axis, (issue,))

    unsupported_words = sorted(
        (active_words - semantics.supported_rotary_words)
        | ((present_words & {"U", "V", "W"}) - semantics.supported_rotary_words)
    )
    if unsupported_words:
        issue = ValidationIssue(
            code="nc_preview.rotary_words_unsupported",
            severity=IssueSeverity.WARNING,
            object_id=NC_PREVIEW_OBJECT_ID,
            context={
                "controller_semantics": semantics.semantics_id,
                "unsupported_rotary_words": unsupported_words,
                "active_rotary_words": sorted(active_words),
            },
        )
        return _raw_motion(start, end, nozzle_axis, (issue,))

    try:
        start_transform = _machine_to_workpiece_transform(semantics, start_values)
        end_transform = _machine_to_workpiece_transform(semantics, end_values)
    except (KeyError, TypeError, ValueError) as exc:
        issue = ValidationIssue(
            code="nc_preview.kinematic_reconstruction_failed",
            severity=IssueSeverity.WARNING,
            object_id=NC_PREVIEW_OBJECT_ID,
            context={
                "controller_semantics": semantics.semantics_id,
                "reason": str(exc),
            },
        )
        return _raw_motion(start, end, nozzle_axis, (issue,))

    return PreviewMotionReconstruction(
        start=start_transform.transform_point(start),
        end=end_transform.transform_point(end),
        start_nozzle_axis=start_transform.transform_vector(nozzle_axis),
        end_nozzle_axis=end_transform.transform_vector(nozzle_axis),
        coordinate_transform=semantics.transform_name,
    )


def _machine_to_workpiece_transform(
    semantics: ControllerAxisSemantics,
    controller_values: Mapping[str, float],
) -> RigidTransform:
    joint_positions = semantics.joint_positions(controller_values)
    machine_from_workpiece = semantics.machine_profile.link_transform(
        semantics.workpiece_link_id,
        joint_positions,
    )
    return machine_from_workpiece.inverse()


def _normalise_rotary_values(
    values: Mapping[str, float],
) -> tuple[dict[str, float], ValidationIssue | None]:
    result: dict[str, float] = {}
    try:
        items = values.items()
    except AttributeError:
        issue = ValidationIssue(
            code="nc_preview.rotary_values_invalid",
            severity=IssueSeverity.WARNING,
            object_id=NC_PREVIEW_OBJECT_ID,
            context={"reason": "rotary values must be a mapping"},
        )
        return result, issue
    for raw_word, raw_value in items:
        word = str(raw_word).strip().upper()
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = math.nan
        if word not in _ROTARY_WORDS or not math.isfinite(value) or word in result:
            issue = ValidationIssue(
                code="nc_preview.rotary_values_invalid",
                severity=IssueSeverity.WARNING,
                object_id=NC_PREVIEW_OBJECT_ID,
                context={
                    "word": word,
                    "value": repr(raw_value),
                    "reason": (
                        "duplicate word" if word in result else "invalid word or value"
                    ),
                },
            )
            return result, issue
        result[word] = value
    return result, None


def _raw_motion(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    nozzle_axis: tuple[float, float, float],
    issues: tuple[ValidationIssue, ...] = (),
) -> PreviewMotionReconstruction:
    return PreviewMotionReconstruction(
        start=start,
        end=end,
        start_nozzle_axis=nozzle_axis,
        end_nozzle_axis=nozzle_axis,
        coordinate_transform=MACHINE_COORDINATE_TRANSFORM,
        issues=issues,
    )


def _vector3(
    value: tuple[float, float, float], name: str
) -> tuple[float, float, float]:
    try:
        result = tuple(float(component) for component in value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain three finite values") from exc
    if len(result) != 3 or not all(math.isfinite(component) for component in result):
        raise ValueError(f"{name} must contain three finite values")
    return result  # type: ignore[return-value]


def _unit_vector3(
    value: tuple[float, float, float], name: str
) -> tuple[float, float, float]:
    vector = _vector3(value, name)
    length = math.sqrt(sum(component * component for component in vector))
    if length <= _ZERO_TOLERANCE:
        raise ValueError(f"{name} must not be zero")
    return tuple(component / length for component in vector)  # type: ignore[return-value]


def _unique_issues(*issues: ValidationIssue | None) -> tuple[ValidationIssue, ...]:
    result: list[ValidationIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        if issue is None:
            continue
        key = (issue.code, issue.severity.value, repr(issue.context))
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return tuple(result)


__all__ = [
    "AC_INVERSE_TRANSFORM",
    "ControllerAxisSemantics",
    "DEFAULT_PREVIEW_KINEMATICS_REGISTRY",
    "GENERIC_XYZAC_AC_SEMANTICS",
    "GENERIC_XYZAC_SEMANTICS",
    "MACHINE_COORDINATE_TRANSFORM",
    "NC_PREVIEW_OBJECT_ID",
    "PreviewKinematicsRegistry",
    "PreviewMotionReconstruction",
    "PreviewPoseReconstruction",
    "reconstruct_preview_motion",
    "reconstruct_preview_pose",
]
