"""Machine profiles and forward kinematics.

Transforms use column vectors in a right-handed frame. Linear values are
millimetres, rotary values are radians, and forward kinematics returns
``T_machine_from_link``. Only ``PostAxisMap`` converts controller units.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast

from .coordinates import Matrix4, RigidTransform
from .json_contract import parse_json_bool, require_bool

Vector3 = tuple[float, float, float]

_IDENTITY_MATRIX: Matrix4 = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)
_AXIS_WORD = re.compile(r"^[A-Z]$")
_JOINT_TYPES = frozenset({"linear", "rotary"})
_MOTION_SIDES = frozenset({"tool", "workpiece"})
_SURFACE_SHAPES = frozenset({"rectangle", "circle"})
_OUTPUT_UNITS = frozenset({"native", "mm", "inch", "rad", "deg"})
_EPSILON = 1.0e-9


def _vector3(value: Iterable[float], field_name: str) -> Vector3:
    items = tuple(float(component) for component in value)
    if len(items) != 3:
        raise ValueError(f"{field_name} must contain exactly three values")
    return cast(Vector3, items)


def _identity_transform(source_frame: str, target_frame: str) -> RigidTransform:
    return RigidTransform(
        _IDENTITY_MATRIX,
        source_frame=source_frame,
        target_frame=target_frame,
    )


def _transform_to_json(transform: RigidTransform) -> dict[str, Any]:
    return transform.to_json()


def _transform_from_json(payload: Mapping[str, Any]) -> RigidTransform:
    return RigidTransform.from_json(dict(payload))


@dataclass(frozen=True, slots=True)
class PostAxisMap:
    """Controller-word mapping for one machine joint.

    Joint values are stored as millimetres for linear axes and radians for
    rotary axes. Unit conversion occurs before scale and offset are applied.
    """

    word: str
    output_unit: str = "native"
    scale: float = 1.0
    offset: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "word", str(self.word).upper())
        object.__setattr__(self, "output_unit", str(self.output_unit).lower())
        object.__setattr__(self, "scale", float(self.scale))
        object.__setattr__(self, "offset", float(self.offset))

    def validation_errors(self, joint_type: str | None = None) -> tuple[str, ...]:
        errors: list[str] = []
        if not _AXIS_WORD.fullmatch(self.word):
            errors.append("post_axis.invalid_word")
        if self.output_unit not in _OUTPUT_UNITS:
            errors.append("post_axis.invalid_output_unit")
        if not math.isfinite(self.scale) or abs(self.scale) <= _EPSILON:
            errors.append("post_axis.invalid_scale")
        if not math.isfinite(self.offset):
            errors.append("post_axis.invalid_offset")
        if joint_type == "linear" and self.output_unit in {"rad", "deg"}:
            errors.append("post_axis.linear_angular_unit")
        if joint_type == "rotary" and self.output_unit in {"mm", "inch"}:
            errors.append("post_axis.rotary_linear_unit")
        return tuple(errors)

    def encode(self, internal_value: float, joint_type: str) -> float:
        value = float(internal_value)
        if not math.isfinite(value):
            raise ValueError("axis value must be finite")
        errors = self.validation_errors(joint_type)
        if errors:
            raise ValueError(", ".join(errors))
        if self.output_unit == "inch":
            value /= 25.4
        elif self.output_unit == "deg":
            value = math.degrees(value)
        return value * self.scale + self.offset

    def decode(self, controller_value: float, joint_type: str) -> float:
        value = float(controller_value)
        if not math.isfinite(value):
            raise ValueError("controller value must be finite")
        errors = self.validation_errors(joint_type)
        if errors:
            raise ValueError(", ".join(errors))
        value = (value - self.offset) / self.scale
        if self.output_unit == "inch":
            value *= 25.4
        elif self.output_unit == "deg":
            value = math.radians(value)
        return value

    def to_json(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "output_unit": self.output_unit,
            "scale": self.scale,
            "offset": self.offset,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> PostAxisMap:
        return cls(
            word=str(payload["word"]),
            output_unit=str(payload.get("output_unit", "native")),
            scale=float(payload.get("scale", 1.0)),
            offset=float(payload.get("offset", 0.0)),
        )


@dataclass(frozen=True, slots=True)
class BuildSurface:
    """Physical build-plate envelope attached to a mount datum."""

    surface_id: str
    name: str
    shape: str
    width_mm: float | None = None
    depth_mm: float | None = None
    diameter_mm: float | None = None
    thickness_mm: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "surface_id", str(self.surface_id))
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "shape", str(self.shape).lower())
        for name in ("width_mm", "depth_mm", "diameter_mm"):
            value = getattr(self, name)
            object.__setattr__(self, name, None if value is None else float(value))
        object.__setattr__(self, "thickness_mm", float(self.thickness_mm))

    @property
    def kind(self) -> str:
        return self.shape

    def validation_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not self.surface_id:
            errors.append("build_surface.missing_id")
        if not self.name:
            errors.append(f"build_surface.missing_name:{self.surface_id}")
        if self.shape not in _SURFACE_SHAPES:
            errors.append(f"build_surface.invalid_shape:{self.surface_id}")
        if not math.isfinite(self.thickness_mm) or self.thickness_mm < 0.0:
            errors.append(f"build_surface.invalid_thickness:{self.surface_id}")
        if self.shape == "rectangle":
            if not _positive_finite(self.width_mm):
                errors.append(f"build_surface.invalid_width:{self.surface_id}")
            if not _positive_finite(self.depth_mm):
                errors.append(f"build_surface.invalid_depth:{self.surface_id}")
        if self.shape == "circle" and not _positive_finite(self.diameter_mm):
            errors.append(f"build_surface.invalid_diameter:{self.surface_id}")
        return tuple(errors)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.surface_id,
            "name": self.name,
            "shape": self.shape,
            "width_mm": self.width_mm,
            "depth_mm": self.depth_mm,
            "diameter_mm": self.diameter_mm,
            "thickness_mm": self.thickness_mm,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> BuildSurface:
        return cls(
            surface_id=str(payload.get("id", payload.get("surface_id", ""))),
            name=str(payload.get("name", "")),
            shape=str(payload.get("shape", payload.get("kind", ""))),
            width_mm=_optional_float(payload.get("width_mm")),
            depth_mm=_optional_float(payload.get("depth_mm")),
            diameter_mm=_optional_float(payload.get("diameter_mm")),
            thickness_mm=float(payload.get("thickness_mm", 0.0)),
        )


@dataclass(frozen=True, slots=True)
class MountDatum:
    """Named installation datum rigidly attached to a machine link."""

    mount_id: str
    name: str
    parent_link_id: str
    build_surface_id: str
    T_parent_from_mount: RigidTransform | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mount_id", str(self.mount_id))
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "parent_link_id", str(self.parent_link_id))
        object.__setattr__(self, "build_surface_id", str(self.build_surface_id))
        transform = self.T_parent_from_mount
        if transform is None:
            transform = _identity_transform(self.mount_id, self.parent_link_id)
            object.__setattr__(
                self,
                "T_parent_from_mount",
                transform,
            )
        elif not isinstance(transform, RigidTransform):
            raise TypeError("T_parent_from_mount must be RigidTransform")
        if transform.source_frame != self.mount_id:
            raise ValueError("T_parent_from_mount source_frame must equal mount_id")
        if transform.target_frame != self.parent_link_id:
            raise ValueError("T_parent_from_mount target_frame must equal parent_link_id")

    @property
    def datum_id(self) -> str:
        return self.mount_id

    def to_json(self) -> dict[str, Any]:
        assert self.T_parent_from_mount is not None
        return {
            "id": self.mount_id,
            "name": self.name,
            "parent_link_id": self.parent_link_id,
            "build_surface_id": self.build_surface_id,
            "T_parent_from_mount": _transform_to_json(self.T_parent_from_mount),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> MountDatum:
        raw_transform = payload.get("T_parent_from_mount")
        return cls(
            mount_id=str(payload.get("id", payload.get("mount_id", ""))),
            name=str(payload.get("name", "")),
            parent_link_id=str(payload.get("parent_link_id", "")),
            build_surface_id=str(payload.get("build_surface_id", "")),
            T_parent_from_mount=(
                _transform_from_json(raw_transform) if isinstance(raw_transform, Mapping) else None
            ),
        )


@dataclass(frozen=True, slots=True)
class JointSpec:
    """One prismatic or revolute joint in a machine kinematic chain.

    ``axis_direction`` and ``rotation_center_mm`` are expressed in the parent
    link frame. Rotary quantities use radians; linear quantities use mm.
    ``T_parent_from_child_zero`` captures the calibrated zero pose.
    """

    joint_id: str
    name: str
    parent_link_id: str
    child_link_id: str
    joint_type: str
    motion_side: str
    axis_direction: Vector3
    rotation_center_mm: Vector3 = (0.0, 0.0, 0.0)
    zero_offset: float = 0.0
    soft_limit_min: float | None = None
    soft_limit_max: float | None = None
    max_velocity: float | None = None
    max_acceleration: float | None = None
    T_parent_from_child_zero: RigidTransform | None = None
    post_axis_map: PostAxisMap | None = None

    def __post_init__(self) -> None:
        for name in (
            "joint_id",
            "name",
            "parent_link_id",
            "child_link_id",
            "joint_type",
            "motion_side",
        ):
            object.__setattr__(self, name, str(getattr(self, name)))
        object.__setattr__(self, "joint_type", self.joint_type.lower())
        object.__setattr__(self, "motion_side", self.motion_side.lower())
        object.__setattr__(self, "axis_direction", _vector3(self.axis_direction, "axis_direction"))
        object.__setattr__(
            self,
            "rotation_center_mm",
            _vector3(self.rotation_center_mm, "rotation_center_mm"),
        )
        for name in (
            "zero_offset",
            "soft_limit_min",
            "soft_limit_max",
            "max_velocity",
            "max_acceleration",
        ):
            value = getattr(self, name)
            object.__setattr__(self, name, None if value is None else float(value))
        zero_transform = self.T_parent_from_child_zero
        if zero_transform is None:
            zero_transform = _identity_transform(
                self.child_link_id,
                self.parent_link_id,
            )
            object.__setattr__(
                self,
                "T_parent_from_child_zero",
                zero_transform,
            )
        elif not isinstance(zero_transform, RigidTransform):
            raise TypeError("T_parent_from_child_zero must be RigidTransform")
        if zero_transform.source_frame != self.child_link_id:
            raise ValueError("T_parent_from_child_zero source_frame must equal child_link_id")
        if zero_transform.target_frame != self.parent_link_id:
            raise ValueError("T_parent_from_child_zero target_frame must equal parent_link_id")

    @property
    def axis(self) -> Vector3:
        return self.axis_direction

    @property
    def soft_limits(self) -> tuple[float | None, float | None]:
        return self.soft_limit_min, self.soft_limit_max

    def effective_position(self, commanded_position: float) -> float:
        value = float(commanded_position) + self.zero_offset
        if not math.isfinite(value):
            raise ValueError(f"joint position must be finite: {self.joint_id}")
        if self.soft_limit_min is not None and value < self.soft_limit_min - _EPSILON:
            raise ValueError(f"joint position below soft limit: {self.joint_id}")
        if self.soft_limit_max is not None and value > self.soft_limit_max + _EPSILON:
            raise ValueError(f"joint position above soft limit: {self.joint_id}")
        return value

    def motion_transform(self, commanded_position: float) -> RigidTransform:
        value = self.effective_position(commanded_position)
        if self.joint_type == "linear":
            matrix = _translation_matrix(self.axis_direction, value)
        elif self.joint_type == "rotary":
            matrix = _rotation_about_axis_matrix(
                self.axis_direction,
                self.rotation_center_mm,
                value,
            )
        else:
            raise ValueError(f"unsupported joint type: {self.joint_type}")
        return RigidTransform(
            matrix,
            source_frame=self.parent_link_id,
            target_frame=self.parent_link_id,
        )

    def local_transform(self, commanded_position: float) -> RigidTransform:
        assert self.T_parent_from_child_zero is not None
        return self.motion_transform(commanded_position) @ self.T_parent_from_child_zero

    def to_json(self) -> dict[str, Any]:
        assert self.T_parent_from_child_zero is not None
        return {
            "id": self.joint_id,
            "name": self.name,
            "parent_link_id": self.parent_link_id,
            "child_link_id": self.child_link_id,
            "joint_type": self.joint_type,
            "motion_side": self.motion_side,
            "axis_direction": list(self.axis_direction),
            "rotation_center_mm": list(self.rotation_center_mm),
            "zero_offset": self.zero_offset,
            "soft_limit_min": self.soft_limit_min,
            "soft_limit_max": self.soft_limit_max,
            "max_velocity": self.max_velocity,
            "max_acceleration": self.max_acceleration,
            "T_parent_from_child_zero": _transform_to_json(self.T_parent_from_child_zero),
            "post_axis_map": (
                self.post_axis_map.to_json() if self.post_axis_map is not None else None
            ),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> JointSpec:
        raw_transform = payload.get("T_parent_from_child_zero")
        raw_post = payload.get("post_axis_map")
        limits = payload.get("soft_limits")
        limit_min = payload.get("soft_limit_min")
        limit_max = payload.get("soft_limit_max")
        if isinstance(limits, list | tuple) and len(limits) == 2:
            limit_min, limit_max = limits
        return cls(
            joint_id=str(payload.get("id", payload.get("joint_id", ""))),
            name=str(payload.get("name", "")),
            parent_link_id=str(payload.get("parent_link_id", "")),
            child_link_id=str(payload.get("child_link_id", "")),
            joint_type=str(payload.get("joint_type", payload.get("type", ""))),
            motion_side=str(payload.get("motion_side", "")),
            axis_direction=_vector3(
                payload.get("axis_direction", payload.get("axis", ())),
                "axis_direction",
            ),
            rotation_center_mm=_vector3(
                payload.get("rotation_center_mm", (0.0, 0.0, 0.0)),
                "rotation_center_mm",
            ),
            zero_offset=float(payload.get("zero_offset", 0.0)),
            soft_limit_min=_optional_float(limit_min),
            soft_limit_max=_optional_float(limit_max),
            max_velocity=_optional_float(payload.get("max_velocity")),
            max_acceleration=_optional_float(payload.get("max_acceleration")),
            T_parent_from_child_zero=(
                _transform_from_json(raw_transform) if isinstance(raw_transform, Mapping) else None
            ),
            post_axis_map=(
                PostAxisMap.from_json(raw_post) if isinstance(raw_post, Mapping) else None
            ),
        )


class MachineProfileValidationError(ValueError):
    def __init__(self, errors: Iterable[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("invalid machine profile: " + ", ".join(self.errors))


@dataclass(frozen=True, slots=True)
class MachineProfile:
    """Versioned machine resource with serial tool and workpiece chains."""

    profile_id: str
    name: str
    version: int
    joints: tuple[JointSpec, ...]
    mount_datums: tuple[MountDatum, ...]
    build_surfaces: tuple[BuildSurface, ...]
    root_link_id: str = "machine"
    tool_link_id: str | None = None
    workpiece_link_id: str | None = None
    reference_only: bool = True
    manufacturer: str = ""
    model: str = ""
    source_uri: str = ""

    def __post_init__(self) -> None:
        for name in (
            "profile_id",
            "name",
            "root_link_id",
            "manufacturer",
            "model",
            "source_uri",
        ):
            object.__setattr__(self, name, str(getattr(self, name)))
        object.__setattr__(self, "version", int(self.version))
        object.__setattr__(self, "joints", tuple(self.joints))
        object.__setattr__(self, "mount_datums", tuple(self.mount_datums))
        object.__setattr__(self, "build_surfaces", tuple(self.build_surfaces))
        object.__setattr__(
            self,
            "tool_link_id",
            None if self.tool_link_id is None else str(self.tool_link_id),
        )
        object.__setattr__(
            self,
            "workpiece_link_id",
            None if self.workpiece_link_id is None else str(self.workpiece_link_id),
        )
        object.__setattr__(
            self,
            "reference_only",
            require_bool(self.reference_only, field_name="reference_only"),
        )

    @property
    def joint_map(self) -> Mapping[str, JointSpec]:
        return MappingProxyType({joint.joint_id: joint for joint in self.joints})

    @property
    def mount_map(self) -> Mapping[str, MountDatum]:
        return MappingProxyType({mount.mount_id: mount for mount in self.mount_datums})

    @property
    def build_surface_map(self) -> Mapping[str, BuildSurface]:
        return MappingProxyType({surface.surface_id: surface for surface in self.build_surfaces})

    def validation_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        _validate_machine_identity(self, errors)
        _validate_machine_duplicates(self, errors)
        child_to_joint = {joint.child_link_id: joint for joint in self.joints}
        valid_links = {self.root_link_id, *child_to_joint}
        _validate_machine_joints(self, child_to_joint, valid_links, errors)
        errors.extend(_chain_errors(self.root_link_id, self.joints))
        _validate_machine_mounts(self, valid_links, errors)
        _validate_machine_endpoints(self, child_to_joint, valid_links, errors)
        return tuple(dict.fromkeys(errors))

    def validate(self) -> MachineProfile:
        errors = self.validation_errors()
        if errors:
            raise MachineProfileValidationError(errors)
        return self

    def forward_kinematics(
        self,
        joint_positions: Mapping[str, float] | None = None,
    ) -> dict[str, RigidTransform]:
        """Return ``T_machine_from_link`` for every link in both chains."""

        self.validate()
        positions = dict(joint_positions or {})
        known_ids = {joint.joint_id for joint in self.joints}
        unknown = sorted(set(positions) - known_ids)
        if unknown:
            raise KeyError(f"unknown joint position(s): {', '.join(unknown)}")

        transforms: dict[str, RigidTransform] = {
            self.root_link_id: RigidTransform.identity(self.root_link_id)
        }
        pending = list(self.joints)
        while pending:
            remaining: list[JointSpec] = []
            for joint in pending:
                parent_transform = transforms.get(joint.parent_link_id)
                if parent_transform is None:
                    remaining.append(joint)
                    continue
                local = joint.local_transform(positions.get(joint.joint_id, 0.0))
                transforms[joint.child_link_id] = parent_transform @ local
            if len(remaining) == len(pending):
                raise MachineProfileValidationError(("machine.kinematic_chain_not_resolvable",))
            pending = remaining
        return transforms

    def link_transform(
        self,
        link_id: str,
        joint_positions: Mapping[str, float] | None = None,
    ) -> RigidTransform:
        transforms = self.forward_kinematics(joint_positions)
        if link_id not in transforms:
            raise KeyError(f"unknown machine link: {link_id}")
        return transforms[link_id]

    def mount_transform(
        self,
        mount_id: str,
        joint_positions: Mapping[str, float] | None = None,
    ) -> RigidTransform:
        """Return the evaluated ``T_machine_from_mount`` transform."""

        self.validate()
        mount = self.mount_map.get(mount_id)
        if mount is None:
            raise KeyError(f"unknown mount datum: {mount_id}")
        assert mount.T_parent_from_mount is not None
        parent = self.link_transform(mount.parent_link_id, joint_positions)
        return parent @ mount.T_parent_from_mount

    def controller_values(self, joint_positions: Mapping[str, float]) -> dict[str, float]:
        self.validate()
        unknown = sorted(set(joint_positions) - set(self.joint_map))
        if unknown:
            raise KeyError(f"unknown joint position(s): {', '.join(unknown)}")
        result: dict[str, float] = {}
        for joint in self.joints:
            if joint.joint_id not in joint_positions or joint.post_axis_map is None:
                continue
            value = joint.effective_position(joint_positions[joint.joint_id])
            result[joint.post_axis_map.word] = joint.post_axis_map.encode(value, joint.joint_type)
        return result

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.profile_id,
            "name": self.name,
            "version": self.version,
            "root_link_id": self.root_link_id,
            "tool_link_id": self.tool_link_id,
            "workpiece_link_id": self.workpiece_link_id,
            "reference_only": self.reference_only,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "source_uri": self.source_uri,
            "joints": [joint.to_json() for joint in self.joints],
            "mount_datums": [mount.to_json() for mount in self.mount_datums],
            "build_surfaces": [surface.to_json() for surface in self.build_surfaces],
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> MachineProfile:
        if not isinstance(payload, Mapping):
            raise ValueError("Machine Profile payload must be an object")
        raw_joints = _mapping_array(payload.get("joints", ()), "joints")
        raw_mounts = _mapping_array(
            payload.get("mount_datums", payload.get("mounts", ())),
            "mount_datums",
        )
        raw_surfaces = _mapping_array(
            payload.get("build_surfaces", ()),
            "build_surfaces",
        )
        try:
            profile = cls(
                profile_id=str(payload.get("id", payload.get("profile_id", ""))),
                name=str(payload.get("name", "")),
                version=int(payload.get("version", 1)),
                root_link_id=str(payload.get("root_link_id", "machine")),
                tool_link_id=_optional_string(payload.get("tool_link_id")),
                workpiece_link_id=_optional_string(payload.get("workpiece_link_id")),
                reference_only=parse_json_bool(
                    payload,
                    "reference_only",
                    default=True,
                    field_name="machine.reference_only",
                ),
                manufacturer=str(payload.get("manufacturer", "")),
                model=str(payload.get("model", "")),
                source_uri=str(payload.get("source_uri", "")),
                joints=tuple(JointSpec.from_json(item) for item in raw_joints),
                mount_datums=tuple(MountDatum.from_json(item) for item in raw_mounts),
                build_surfaces=tuple(BuildSurface.from_json(item) for item in raw_surfaces),
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid Machine Profile payload") from exc
        return profile.validate()


def _validate_machine_identity(profile: MachineProfile, errors: list[str]) -> None:
    if not profile.profile_id:
        errors.append("machine.missing_id")
    if not profile.name:
        errors.append("machine.missing_name")
    if profile.version < 1:
        errors.append("machine.invalid_version")
    if not profile.root_link_id:
        errors.append("machine.missing_root_link")


def _validate_machine_duplicates(profile: MachineProfile, errors: list[str]) -> None:
    groups = (
        ("joint.duplicate_id", (joint.joint_id for joint in profile.joints)),
        (
            "joint.duplicate_child_link",
            (joint.child_link_id for joint in profile.joints),
        ),
        ("mount.duplicate_id", (mount.mount_id for mount in profile.mount_datums)),
        (
            "build_surface.duplicate_id",
            (surface.surface_id for surface in profile.build_surfaces),
        ),
    )
    for code, identifiers in groups:
        errors.extend(f"{code}:{item}" for item in _duplicates(identifiers))


def _validate_machine_joints(
    profile: MachineProfile,
    child_to_joint: Mapping[str, JointSpec],
    valid_links: set[str],
    errors: list[str],
) -> None:
    branch_counts: dict[tuple[str, str], int] = {}
    post_words: dict[str, str] = {}
    for joint in profile.joints:
        prefix = f"joint:{joint.joint_id}"
        _validate_joint_identity(joint, profile.root_link_id, valid_links, prefix, errors)
        _validate_joint_motion(joint, prefix, errors)
        _validate_joint_limits(joint, prefix, errors)
        _validate_joint_transform(joint, prefix, errors)
        _validate_joint_post_axis(joint, prefix, post_words, errors)

        branch_key = (joint.parent_link_id, joint.motion_side)
        branch_counts[branch_key] = branch_counts.get(branch_key, 0) + 1
        parent_joint = child_to_joint.get(joint.parent_link_id)
        if parent_joint is not None and parent_joint.motion_side != joint.motion_side:
            errors.append(f"{prefix}.motion_side_changes_within_chain")

    for (parent_link, side), count in sorted(branch_counts.items()):
        if count > 1:
            errors.append(f"joint.branching_chain:{parent_link}:{side}")


def _validate_joint_identity(
    joint: JointSpec,
    root_link_id: str,
    valid_links: set[str],
    prefix: str,
    errors: list[str],
) -> None:
    if not joint.joint_id:
        errors.append("joint.missing_id")
    if not joint.name:
        errors.append(f"{prefix}.missing_name")
    if not joint.parent_link_id or not joint.child_link_id:
        errors.append(f"{prefix}.missing_link")
    if joint.parent_link_id == joint.child_link_id:
        errors.append(f"{prefix}.self_link")
    if joint.child_link_id == root_link_id:
        errors.append(f"{prefix}.root_is_child")
    if joint.parent_link_id not in valid_links:
        errors.append(f"{prefix}.unknown_parent:{joint.parent_link_id}")


def _validate_joint_motion(joint: JointSpec, prefix: str, errors: list[str]) -> None:
    if joint.joint_type not in _JOINT_TYPES:
        errors.append(f"{prefix}.invalid_type")
    if joint.motion_side not in _MOTION_SIDES:
        errors.append(f"{prefix}.invalid_motion_side")
    if not _finite_vector(joint.axis_direction):
        errors.append(f"{prefix}.non_finite_axis")
    elif abs(_norm(joint.axis_direction) - 1.0) > 1.0e-7:
        errors.append(f"{prefix}.axis_not_unit")
    if not _finite_vector(joint.rotation_center_mm):
        errors.append(f"{prefix}.non_finite_rotation_center")
    if not math.isfinite(joint.zero_offset):
        errors.append(f"{prefix}.non_finite_zero_offset")


def _validate_joint_limits(joint: JointSpec, prefix: str, errors: list[str]) -> None:
    low, high = joint.soft_limits
    if low is not None and not math.isfinite(low):
        errors.append(f"{prefix}.invalid_soft_limit_min")
    if high is not None and not math.isfinite(high):
        errors.append(f"{prefix}.invalid_soft_limit_max")
    if low is not None and high is not None and low > high:
        errors.append(f"{prefix}.reversed_soft_limits")
    if joint.max_velocity is not None and not _positive_finite(joint.max_velocity):
        errors.append(f"{prefix}.invalid_max_velocity")
    if joint.max_acceleration is not None and not _positive_finite(joint.max_acceleration):
        errors.append(f"{prefix}.invalid_max_acceleration")


def _validate_joint_transform(joint: JointSpec, prefix: str, errors: list[str]) -> None:
    transform = joint.T_parent_from_child_zero
    if transform is None:
        errors.append(f"{prefix}.missing_zero_transform")
        return
    if transform.source_frame != joint.child_link_id:
        errors.append(f"{prefix}.zero_transform_source_mismatch")
    if transform.target_frame != joint.parent_link_id:
        errors.append(f"{prefix}.zero_transform_target_mismatch")


def _validate_joint_post_axis(
    joint: JointSpec,
    prefix: str,
    post_words: dict[str, str],
    errors: list[str],
) -> None:
    axis_map = joint.post_axis_map
    if axis_map is None:
        return
    errors.extend(f"{prefix}.{error}" for error in axis_map.validation_errors(joint.joint_type))
    if axis_map.word in post_words:
        errors.append(f"post_axis.duplicate_word:{axis_map.word}")
    else:
        post_words[axis_map.word] = joint.joint_id


def _validate_machine_mounts(
    profile: MachineProfile, valid_links: set[str], errors: list[str]
) -> None:
    for surface in profile.build_surfaces:
        errors.extend(surface.validation_errors())
    surface_ids = {surface.surface_id for surface in profile.build_surfaces}
    for mount in profile.mount_datums:
        prefix = f"mount:{mount.mount_id}"
        if not mount.mount_id:
            errors.append("mount.missing_id")
        if not mount.name:
            errors.append(f"{prefix}.missing_name")
        if mount.parent_link_id not in valid_links:
            errors.append(f"{prefix}.unknown_parent:{mount.parent_link_id}")
        if mount.build_surface_id not in surface_ids:
            errors.append(f"{prefix}.unknown_build_surface:{mount.build_surface_id}")
        _validate_mount_transform(mount, prefix, errors)


def _validate_mount_transform(mount: MountDatum, prefix: str, errors: list[str]) -> None:
    transform = mount.T_parent_from_mount
    if transform is None:
        errors.append(f"{prefix}.missing_transform")
        return
    if transform.source_frame != mount.mount_id:
        errors.append(f"{prefix}.transform_source_mismatch")
    if transform.target_frame != mount.parent_link_id:
        errors.append(f"{prefix}.transform_target_mismatch")


def _validate_machine_endpoints(
    profile: MachineProfile,
    child_to_joint: Mapping[str, JointSpec],
    valid_links: set[str],
    errors: list[str],
) -> None:
    endpoints = (
        (profile.tool_link_id, "tool", "tool_link_id"),
        (profile.workpiece_link_id, "workpiece", "workpiece_link_id"),
    )
    for endpoint, side, field_name in endpoints:
        if endpoint is None:
            continue
        if endpoint not in valid_links:
            errors.append(f"machine.unknown_{field_name}:{endpoint}")
            continue
        endpoint_joint = child_to_joint.get(endpoint)
        if (
            endpoint != profile.root_link_id
            and endpoint_joint is not None
            and endpoint_joint.motion_side != side
        ):
            errors.append(f"machine.invalid_{field_name}_side:{endpoint}")


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _mapping_array(value: Any, field_name: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list | tuple):
        raise ValueError(f"Machine Profile {field_name} must be an array")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(f"Machine Profile {field_name}[{index}] must be an object")
        result.append(item)
    return tuple(result)


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _positive_finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0.0


def _finite_vector(value: Vector3) -> bool:
    return all(math.isfinite(component) for component in value)


def _norm(value: Vector3) -> float:
    return math.sqrt(sum(component * component for component in value))


def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return tuple(sorted(duplicates))


def _chain_errors(root_link_id: str, joints: tuple[JointSpec, ...]) -> list[str]:
    child_to_parent = {
        joint.child_link_id: joint.parent_link_id for joint in joints if joint.child_link_id
    }
    errors: list[str] = []
    for child in sorted(child_to_parent):
        path: set[str] = set()
        current = child
        while current != root_link_id:
            if current in path:
                errors.append(f"joint.cycle:{current}")
                break
            path.add(current)
            parent = child_to_parent.get(current)
            if parent is None:
                break
            current = parent
    return errors


def _translation_matrix(
    axis: Vector3,
    distance: float,
) -> Matrix4:
    return (
        (1.0, 0.0, 0.0, axis[0] * distance),
        (0.0, 1.0, 0.0, axis[1] * distance),
        (0.0, 0.0, 1.0, axis[2] * distance),
        (0.0, 0.0, 0.0, 1.0),
    )


def _rotation_about_axis_matrix(
    axis: Vector3,
    center: Vector3,
    angle_rad: float,
) -> Matrix4:
    x, y, z = axis
    cosine = math.cos(angle_rad)
    sine = math.sin(angle_rad)
    one_minus_cosine = 1.0 - cosine
    rotation = (
        (
            cosine + x * x * one_minus_cosine,
            x * y * one_minus_cosine - z * sine,
            x * z * one_minus_cosine + y * sine,
        ),
        (
            y * x * one_minus_cosine + z * sine,
            cosine + y * y * one_minus_cosine,
            y * z * one_minus_cosine - x * sine,
        ),
        (
            z * x * one_minus_cosine - y * sine,
            z * y * one_minus_cosine + x * sine,
            cosine + z * z * one_minus_cosine,
        ),
    )
    cx, cy, cz = center
    translation = (
        cx - (rotation[0][0] * cx + rotation[0][1] * cy + rotation[0][2] * cz),
        cy - (rotation[1][0] * cx + rotation[1][1] * cy + rotation[1][2] * cz),
        cz - (rotation[2][0] * cx + rotation[2][1] * cy + rotation[2][2] * cz),
    )
    return (
        (*rotation[0], translation[0]),
        (*rotation[1], translation[1]),
        (*rotation[2], translation[2]),
        (0.0, 0.0, 0.0, 1.0),
    )


def _linear_joint(
    joint_id: str,
    parent_link_id: str,
    child_link_id: str,
    axis: Vector3,
    *,
    travel_min_mm: float,
    travel_max_mm: float,
) -> JointSpec:
    return JointSpec(
        joint_id=joint_id,
        name=f"{joint_id} linear axis",
        parent_link_id=parent_link_id,
        child_link_id=child_link_id,
        joint_type="linear",
        motion_side="tool",
        axis_direction=axis,
        soft_limit_min=travel_min_mm,
        soft_limit_max=travel_max_mm,
        max_velocity=300.0,
        max_acceleration=1000.0,
        post_axis_map=PostAxisMap(joint_id, "mm"),
    )


def cartesian_reference_profile() -> MachineProfile:
    """Return the immutable, non-production Cartesian reference template."""

    plate = BuildSurface(
        surface_id="cartesian_plate",
        name="Cartesian reference build plate",
        shape="rectangle",
        width_mm=300.0,
        depth_mm=300.0,
        thickness_mm=10.0,
    )
    profile = MachineProfile(
        profile_id="builtin.machine.cartesian_reference.v1",
        name="Cartesian Reference",
        version=1,
        root_link_id="machine",
        tool_link_id="tool",
        workpiece_link_id="machine",
        reference_only=True,
        manufacturer="5AxisSclicer",
        model="Cartesian reference template",
        source_uri="builtin://machine/cartesian-reference/v1",
        joints=(
            _linear_joint(
                "X",
                "machine",
                "x_carriage",
                (1.0, 0.0, 0.0),
                travel_min_mm=0.0,
                travel_max_mm=300.0,
            ),
            _linear_joint(
                "Y",
                "x_carriage",
                "y_carriage",
                (0.0, 1.0, 0.0),
                travel_min_mm=0.0,
                travel_max_mm=300.0,
            ),
            _linear_joint(
                "Z",
                "y_carriage",
                "tool",
                (0.0, 0.0, 1.0),
                travel_min_mm=0.0,
                travel_max_mm=300.0,
            ),
        ),
        mount_datums=(
            MountDatum(
                mount_id="build_plate_mount",
                name="Build plate center",
                parent_link_id="machine",
                build_surface_id=plate.surface_id,
            ),
        ),
        build_surfaces=(plate,),
    )
    return profile.validate()


def generic_xyzac_reference_profile() -> MachineProfile:
    """Return the immutable XYZAC reference template.

    The workpiece chain is A followed by C. Its zero-centre transform is
    ``T_machine_from_table = Rx(A) @ Rz(C)``; the corresponding inverse is
    ``Rz(-C) @ Rx(-A)``, matching the documented pipe2 convention.
    """

    plate = BuildSurface(
        surface_id="xyzac_plate",
        name="XYZAC reference rotary table",
        shape="circle",
        diameter_mm=250.0,
        thickness_mm=10.0,
    )
    profile = MachineProfile(
        profile_id="builtin.machine.generic_xyzac_reference.v1",
        name="Generic XYZAC Reference",
        version=1,
        root_link_id="machine",
        tool_link_id="tool",
        workpiece_link_id="c_table",
        reference_only=True,
        manufacturer="5AxisSclicer",
        model="Generic XYZAC reference template",
        source_uri="builtin://machine/generic-xyzac-reference/v1",
        joints=(
            _linear_joint(
                "X",
                "machine",
                "x_carriage",
                (1.0, 0.0, 0.0),
                travel_min_mm=0.0,
                travel_max_mm=500.0,
            ),
            _linear_joint(
                "Y",
                "x_carriage",
                "y_carriage",
                (0.0, 1.0, 0.0),
                travel_min_mm=0.0,
                travel_max_mm=500.0,
            ),
            _linear_joint(
                "Z",
                "y_carriage",
                "tool",
                (0.0, 0.0, 1.0),
                travel_min_mm=0.0,
                travel_max_mm=500.0,
            ),
            JointSpec(
                joint_id="A",
                name="A rotary axis",
                parent_link_id="machine",
                child_link_id="a_cradle",
                joint_type="rotary",
                motion_side="workpiece",
                axis_direction=(1.0, 0.0, 0.0),
                soft_limit_min=math.radians(-120.0),
                soft_limit_max=math.radians(120.0),
                max_velocity=math.radians(60.0),
                max_acceleration=math.radians(120.0),
                post_axis_map=PostAxisMap("A", "deg"),
            ),
            JointSpec(
                joint_id="C",
                name="C rotary axis",
                parent_link_id="a_cradle",
                child_link_id="c_table",
                joint_type="rotary",
                motion_side="workpiece",
                axis_direction=(0.0, 0.0, 1.0),
                soft_limit_min=math.radians(-360.0),
                soft_limit_max=math.radians(360.0),
                max_velocity=math.radians(120.0),
                max_acceleration=math.radians(240.0),
                post_axis_map=PostAxisMap("C", "deg"),
            ),
        ),
        mount_datums=(
            MountDatum(
                mount_id="build_plate_mount",
                name="Rotary table center",
                parent_link_id="c_table",
                build_surface_id=plate.surface_id,
            ),
        ),
        build_surfaces=(plate,),
    )
    return profile.validate()


def builtin_machine_profiles() -> tuple[MachineProfile, ...]:
    return CARTESIAN_REFERENCE, GENERIC_XYZAC_REFERENCE


CARTESIAN_REFERENCE = cartesian_reference_profile()
GENERIC_XYZAC_REFERENCE = generic_xyzac_reference_profile()


__all__ = [
    "BuildSurface",
    "CARTESIAN_REFERENCE",
    "GENERIC_XYZAC_REFERENCE",
    "JointSpec",
    "MachineProfile",
    "MachineProfileValidationError",
    "MountDatum",
    "PostAxisMap",
    "builtin_machine_profiles",
    "cartesian_reference_profile",
    "generic_xyzac_reference_profile",
]
