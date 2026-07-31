"""Coordinate-system domain objects and rigid-transform mathematics.

All matrices in this module use column vectors and the explicit convention
``p_target = T_target_from_source @ p_source``.  Lengths are millimetres and
angles are radians.  The types contain no UI or CAD-kernel dependencies so the
same validation and serialisation rules can be reused by every workbench.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence, cast

from .json_contract import parse_json_bool, require_bool


Vector3 = tuple[float, float, float]
Matrix3 = tuple[Vector3, Vector3, Vector3]
Matrix4 = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]

_EPSILON = 1.0e-12
_RIGID_TOLERANCE = 1.0e-8
_IDENTITY_4: Matrix4 = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)


def _finite_float(value: Any, *, name: str) -> float:
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _vector3(value: Iterable[Any], *, name: str) -> Vector3:
    try:
        values = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{name} must contain exactly three numbers") from exc
    if len(values) != 3:
        raise ValueError(f"{name} must contain exactly three numbers")
    return tuple(
        _finite_float(component, name=f"{name}[{index}]") for index, component in enumerate(values)
    )  # type: ignore[return-value]


def _matrix4(value: Iterable[Iterable[Any]]) -> Matrix4:
    try:
        rows = tuple(tuple(row) for row in value)
    except TypeError as exc:
        raise ValueError("T_target_from_source must be a 4 x 4 matrix") from exc
    if len(rows) != 4 or any(len(row) != 4 for row in rows):
        raise ValueError("T_target_from_source must be a 4 x 4 matrix")
    return tuple(
        tuple(
            _finite_float(component, name=f"T_target_from_source[{i}][{j}]")
            for j, component in enumerate(row)
        )
        for i, row in enumerate(rows)
    )  # type: ignore[return-value]


def _dot(left: Vector3, right: Vector3) -> float:
    return sum(a * b for a, b in zip(left, right))


def _cross(left: Vector3, right: Vector3) -> Vector3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _norm(vector: Vector3) -> float:
    return math.sqrt(_dot(vector, vector))


def _normalise(vector: Vector3, *, name: str) -> Vector3:
    length = _norm(vector)
    if length <= _EPSILON:
        raise ValueError(f"{name} must be non-zero")
    return tuple(component / length for component in vector)  # type: ignore[return-value]


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a - b for a, b in zip(left, right))  # type: ignore[return-value]


def _scale(vector: Vector3, factor: float) -> Vector3:
    return tuple(component * factor for component in vector)  # type: ignore[return-value]


def _matrix_multiply(left: Matrix4, right: Matrix4) -> Matrix4:
    return tuple(
        tuple(sum(left[i][k] * right[k][j] for k in range(4)) for j in range(4)) for i in range(4)
    )  # type: ignore[return-value]


def _determinant3(rotation: Sequence[Sequence[float]]) -> float:
    return (
        rotation[0][0] * (rotation[1][1] * rotation[2][2] - rotation[1][2] * rotation[2][1])
        - rotation[0][1] * (rotation[1][0] * rotation[2][2] - rotation[1][2] * rotation[2][0])
        + rotation[0][2] * (rotation[1][0] * rotation[2][1] - rotation[1][1] * rotation[2][0])
    )


def _validate_rigid_matrix(matrix: Matrix4) -> None:
    expected_last_row = (0.0, 0.0, 0.0, 1.0)
    if any(
        abs(actual - expected) > _RIGID_TOLERANCE
        for actual, expected in zip(matrix[3], expected_last_row)
    ):
        raise ValueError("T_target_from_source must have homogeneous row [0, 0, 0, 1]")

    rotation = tuple(tuple(matrix[i][j] for j in range(3)) for i in range(3))
    for row_index in range(3):
        for other_index in range(3):
            product = sum(
                rotation[row_index][axis] * rotation[other_index][axis] for axis in range(3)
            )
            expected = 1.0 if row_index == other_index else 0.0
            if abs(product - expected) > _RIGID_TOLERANCE:
                raise ValueError(
                    "T_target_from_source rotation must be orthonormal; "
                    "scale and shear are not allowed"
                )
    determinant = _determinant3(rotation)
    if abs(determinant - 1.0) > _RIGID_TOLERANCE:
        raise ValueError("T_target_from_source rotation must be right-handed")


def _freeze_json(value: Any, *, name: str = "value") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return _finite_float(value, name=name)
    if isinstance(value, Mapping):
        frozen = {str(key): _freeze_json(item, name=f"{name}.{key}") for key, item in value.items()}
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json(item, name=f"{name}[{index}]") for index, item in enumerate(value)
        )
    raise ValueError(f"{name} contains a value that is not JSON-compatible")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class RigidTransform:
    """A validated transform following ``T_target_from_source`` convention."""

    T_target_from_source: Matrix4 = _IDENTITY_4
    source_frame: str = ""
    target_frame: str = ""

    def __post_init__(self) -> None:
        matrix = _matrix4(self.T_target_from_source)
        _validate_rigid_matrix(matrix)
        object.__setattr__(self, "T_target_from_source", matrix)
        object.__setattr__(self, "source_frame", str(self.source_frame).strip())
        object.__setattr__(self, "target_frame", str(self.target_frame).strip())

    @property
    def matrix(self) -> Matrix4:
        """Compatibility alias for numerical consumers."""

        return self.T_target_from_source

    @property
    def rotation(self) -> Matrix3:
        matrix = self.T_target_from_source
        return tuple(tuple(matrix[row][column] for column in range(3)) for row in range(3))  # type: ignore[return-value]

    @property
    def translation(self) -> Vector3:
        matrix = self.T_target_from_source
        return (matrix[0][3], matrix[1][3], matrix[2][3])

    @classmethod
    def identity(cls, frame: str = "") -> RigidTransform:
        return cls(_IDENTITY_4, source_frame=frame, target_frame=frame)

    @classmethod
    def from_rotation_translation(
        cls,
        rotation: Iterable[Iterable[Any]],
        translation: Iterable[Any] = (0.0, 0.0, 0.0),
        *,
        source_frame: str = "",
        target_frame: str = "",
    ) -> RigidTransform:
        try:
            rows = tuple(tuple(row) for row in rotation)
        except TypeError as exc:
            raise ValueError("rotation must be a 3 x 3 matrix") from exc
        if len(rows) != 3 or any(len(row) != 3 for row in rows):
            raise ValueError("rotation must be a 3 x 3 matrix")
        clean_rotation = cast(
            Matrix3,
            tuple(
                tuple(
                    _finite_float(value, name=f"rotation[{i}][{j}]") for j, value in enumerate(row)
                )
                for i, row in enumerate(rows)
            ),
        )
        clean_translation = _vector3(translation, name="translation")
        matrix: Matrix4 = (
            (*clean_rotation[0], clean_translation[0]),
            (*clean_rotation[1], clean_translation[1]),
            (*clean_rotation[2], clean_translation[2]),
            (0.0, 0.0, 0.0, 1.0),
        )
        return cls(matrix, source_frame=source_frame, target_frame=target_frame)

    @classmethod
    def from_translation(
        cls,
        translation: Iterable[Any],
        *,
        source_frame: str = "",
        target_frame: str = "",
    ) -> RigidTransform:
        return cls.from_rotation_translation(
            ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            translation,
            source_frame=source_frame,
            target_frame=target_frame,
        )

    @classmethod
    def from_axis_angle(
        cls,
        axis: Iterable[Any],
        angle_rad: Any,
        *,
        translation: Iterable[Any] = (0.0, 0.0, 0.0),
        source_frame: str = "",
        target_frame: str = "",
    ) -> RigidTransform:
        unit_axis = _normalise(_vector3(axis, name="axis"), name="axis")
        angle = _finite_float(angle_rad, name="angle_rad")
        x, y, z = unit_axis
        cosine = math.cos(angle)
        sine = math.sin(angle)
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
        return cls.from_rotation_translation(
            rotation,
            translation,
            source_frame=source_frame,
            target_frame=target_frame,
        )

    @classmethod
    def from_frame(
        cls,
        origin_in_source_mm: Iterable[Any],
        x_direction_in_source: Iterable[Any],
        z_direction_in_source: Iterable[Any],
        *,
        source_frame: str = "source",
        target_frame: str,
    ) -> RigidTransform:
        """Create source-to-frame transform after Gram-Schmidt projection.

        X is projected onto the plane normal to Z.  Y is then calculated as
        ``Z x X``, yielding a right-handed orthonormal frame.
        """

        origin = _vector3(origin_in_source_mm, name="origin_in_source_mm")
        z_axis = _normalise(
            _vector3(z_direction_in_source, name="z_direction_in_source"),
            name="z_direction_in_source",
        )
        raw_x = _vector3(x_direction_in_source, name="x_direction_in_source")
        projected_x = _subtract(raw_x, _scale(z_axis, _dot(raw_x, z_axis)))
        if _norm(projected_x) <= _EPSILON:
            raise ValueError("x_direction_in_source and z_direction_in_source are collinear")
        x_axis = _normalise(projected_x, name="projected x direction")
        y_axis = _normalise(_cross(z_axis, x_axis), name="calculated y direction")
        rotation: Matrix3 = (x_axis, y_axis, z_axis)
        translation = tuple(-_dot(axis, origin) for axis in rotation)
        return cls.from_rotation_translation(
            rotation,
            translation,
            source_frame=source_frame,
            target_frame=target_frame,
        )

    def inverse(self) -> RigidTransform:
        rotation = self.rotation
        transposed: Matrix3 = tuple(
            tuple(rotation[column][row] for column in range(3)) for row in range(3)
        )  # type: ignore[assignment]
        translation = self.translation
        inverse_translation = tuple(
            -sum(transposed[row][column] * translation[column] for column in range(3))
            for row in range(3)
        )
        return RigidTransform.from_rotation_translation(
            transposed,
            inverse_translation,
            source_frame=self.target_frame,
            target_frame=self.source_frame,
        )

    def compose(self, right: RigidTransform) -> RigidTransform:
        """Return ``self @ right`` (apply ``right`` before ``self``)."""

        if not isinstance(right, RigidTransform):
            raise TypeError("right must be a RigidTransform")
        if self.source_frame and right.target_frame and self.source_frame != right.target_frame:
            raise ValueError(
                "transform frame mismatch: "
                f"{right.target_frame!r} cannot feed {self.source_frame!r}"
            )
        return RigidTransform(
            _matrix_multiply(self.matrix, right.matrix),
            source_frame=right.source_frame,
            target_frame=self.target_frame,
        )

    def __matmul__(self, right: RigidTransform) -> RigidTransform:
        return self.compose(right)

    def transform_point(self, point: Iterable[Any]) -> Vector3:
        x, y, z = _vector3(point, name="point")
        matrix = self.matrix
        return tuple(
            matrix[row][0] * x + matrix[row][1] * y + matrix[row][2] * z + matrix[row][3]
            for row in range(3)
        )  # type: ignore[return-value]

    def transform_vector(self, vector: Iterable[Any]) -> Vector3:
        x, y, z = _vector3(vector, name="vector")
        matrix = self.matrix
        return tuple(
            matrix[row][0] * x + matrix[row][1] * y + matrix[row][2] * z for row in range(3)
        )  # type: ignore[return-value]

    def almost_equal(self, other: RigidTransform, *, tolerance: float = 1.0e-9) -> bool:
        if not isinstance(other, RigidTransform):
            return False
        return all(
            abs(self.matrix[row][column] - other.matrix[row][column]) <= tolerance
            for row in range(4)
            for column in range(4)
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "source_frame": self.source_frame,
            "target_frame": self.target_frame,
            "T_target_from_source": [list(row) for row in self.matrix],
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> RigidTransform:
        if not isinstance(payload, Mapping):
            raise ValueError("rigid transform payload must be an object")
        matrix = payload.get("T_target_from_source", payload.get("matrix"))
        if matrix is None:
            raise ValueError("rigid transform payload is missing T_target_from_source")
        return cls(
            matrix,
            source_frame=str(payload.get("source_frame", "")),
            target_frame=str(payload.get("target_frame", "")),
        )


def _rotation_xyz_matrix(rotation_xyz_rad: Vector3) -> Matrix4:
    x_angle, y_angle, z_angle = rotation_xyz_rad
    cx, sx = math.cos(x_angle), math.sin(x_angle)
    cy, sy = math.cos(y_angle), math.sin(y_angle)
    cz, sz = math.cos(z_angle), math.sin(z_angle)
    rotate_x: Matrix4 = (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, cx, -sx, 0.0),
        (0.0, sx, cx, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    rotate_y: Matrix4 = (
        (cy, 0.0, sy, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (-sy, 0.0, cy, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    rotate_z: Matrix4 = (
        (cz, -sz, 0.0, 0.0),
        (sz, cz, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    return _matrix_multiply(_matrix_multiply(rotate_x, rotate_y), rotate_z)


def _quaternion_from_rotation(
    rotation: Sequence[Sequence[float]],
) -> tuple[float, float, float, float]:
    trace = rotation[0][0] + rotation[1][1] + rotation[2][2]
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * scale
        x = (rotation[2][1] - rotation[1][2]) / scale
        y = (rotation[0][2] - rotation[2][0]) / scale
        z = (rotation[1][0] - rotation[0][1]) / scale
    elif rotation[0][0] > rotation[1][1] and rotation[0][0] > rotation[2][2]:
        scale = math.sqrt(1.0 + rotation[0][0] - rotation[1][1] - rotation[2][2]) * 2.0
        w = (rotation[2][1] - rotation[1][2]) / scale
        x = 0.25 * scale
        y = (rotation[0][1] + rotation[1][0]) / scale
        z = (rotation[0][2] + rotation[2][0]) / scale
    elif rotation[1][1] > rotation[2][2]:
        scale = math.sqrt(1.0 + rotation[1][1] - rotation[0][0] - rotation[2][2]) * 2.0
        w = (rotation[0][2] - rotation[2][0]) / scale
        x = (rotation[0][1] + rotation[1][0]) / scale
        y = 0.25 * scale
        z = (rotation[1][2] + rotation[2][1]) / scale
    else:
        scale = math.sqrt(1.0 + rotation[2][2] - rotation[0][0] - rotation[1][1]) * 2.0
        w = (rotation[1][0] - rotation[0][1]) / scale
        x = (rotation[0][2] + rotation[2][0]) / scale
        y = (rotation[1][2] + rotation[2][1]) / scale
        z = 0.25 * scale
    return (x, y, z, w)


def _rotation_from_quaternion(quaternion_xyzw: Sequence[float]) -> Matrix3:
    x, y, z, w = quaternion_xyzw
    return (
        (
            1.0 - 2.0 * (y * y + z * z),
            2.0 * (x * y - z * w),
            2.0 * (x * z + y * w),
        ),
        (
            2.0 * (x * y + z * w),
            1.0 - 2.0 * (x * x + z * z),
            2.0 * (y * z - x * w),
        ),
        (
            2.0 * (x * z - y * w),
            2.0 * (y * z + x * w),
            1.0 - 2.0 * (x * x + y * y),
        ),
    )


@dataclass(frozen=True, slots=True)
class LocalAdjustment:
    """A local six-DOF adjustment persisted as translation and quaternion."""

    translation_mm: Vector3 = (0.0, 0.0, 0.0)
    quaternion_xyzw: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)

    def __post_init__(self) -> None:
        translation = _vector3(self.translation_mm, name="translation_mm")
        try:
            raw_quaternion = tuple(self.quaternion_xyzw)
        except TypeError as exc:
            raise ValueError("quaternion_xyzw must contain four finite numbers") from exc
        if len(raw_quaternion) != 4:
            raise ValueError("quaternion_xyzw must contain four finite numbers")
        quaternion = tuple(
            _finite_float(value, name=f"quaternion_xyzw[{index}]")
            for index, value in enumerate(raw_quaternion)
        )
        length = math.sqrt(sum(value * value for value in quaternion))
        if length <= _EPSILON:
            raise ValueError("quaternion_xyzw must be non-zero")
        normalised = tuple(
            0.0 if abs(value / length) <= _EPSILON else value / length for value in quaternion
        )
        # q and -q encode the same rotation.  Canonicalise lexicographically
        # from w, then x/y/z so exact 180-degree rotations (w == 0) also have
        # one stable serialized representation and resource hash.
        canonical_key = (
            normalised[3],
            normalised[0],
            normalised[1],
            normalised[2],
        )
        first_significant = next(
            (value for value in canonical_key if abs(value) > _EPSILON),
            1.0,
        )
        if first_significant < 0.0:
            normalised = tuple(-value for value in normalised)
        object.__setattr__(self, "translation_mm", translation)
        object.__setattr__(self, "quaternion_xyzw", normalised)

    @classmethod
    def from_euler_xyz(
        cls,
        translation_mm: Iterable[Any] = (0.0, 0.0, 0.0),
        rotation_xyz_rad: Iterable[Any] = (0.0, 0.0, 0.0),
    ) -> LocalAdjustment:
        rotation_angles = _vector3(rotation_xyz_rad, name="rotation_xyz_rad")
        rotation_matrix = _rotation_xyz_matrix(rotation_angles)
        quaternion = _quaternion_from_rotation(
            tuple(tuple(rotation_matrix[row][column] for column in range(3)) for row in range(3))
        )
        return cls(_vector3(translation_mm, name="translation_mm"), quaternion)

    @property
    def euler_xyz_rad(self) -> Vector3:
        """Return editable Rx/Ry/Rz angles for the persisted quaternion."""

        rotation = _rotation_from_quaternion(self.quaternion_xyzw)
        y_angle = math.asin(max(-1.0, min(1.0, rotation[0][2])))
        cosine_y = math.cos(y_angle)
        if abs(cosine_y) > 1.0e-10:
            x_angle = math.atan2(-rotation[1][2], rotation[2][2])
            z_angle = math.atan2(-rotation[0][1], rotation[0][0])
        elif y_angle > 0.0:
            x_angle = math.atan2(rotation[1][0], rotation[1][1])
            z_angle = 0.0
        else:
            x_angle = -math.atan2(rotation[1][0], rotation[1][1])
            z_angle = 0.0
        return (x_angle, y_angle, z_angle)

    def to_transform(self, frame: str = "") -> RigidTransform:
        rotation = _rotation_from_quaternion(self.quaternion_xyzw)
        return RigidTransform.from_rotation_translation(
            rotation,
            self.translation_mm,
            source_frame=frame,
            target_frame=frame,
        )

    def apply_to(self, reference: RigidTransform) -> RigidTransform:
        """Apply ``T_ref * Translate * Rx * Ry * Rz`` in local coordinates."""

        adjusted_matrix = _matrix_multiply(reference.matrix, self.to_transform().matrix)
        return RigidTransform(
            adjusted_matrix,
            source_frame=reference.source_frame,
            target_frame=reference.target_frame,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "translation_mm": list(self.translation_mm),
            "quaternion_xyzw": list(self.quaternion_xyzw),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> LocalAdjustment:
        if not isinstance(payload, Mapping):
            raise ValueError("local adjustment payload must be an object")
        return cls(
            payload.get("translation_mm", (0.0, 0.0, 0.0)),
            payload.get("quaternion_xyzw", (0.0, 0.0, 0.0, 1.0)),
        )


def apply_local_adjustment(
    reference: RigidTransform,
    adjustment: LocalAdjustment | Iterable[Any] = (0.0, 0.0, 0.0),
    rotation_xyz_rad: Iterable[Any] = (0.0, 0.0, 0.0),
) -> RigidTransform:
    """Convenience API for the fixed local-adjustment multiplication order."""

    local = (
        adjustment
        if isinstance(adjustment, LocalAdjustment)
        else LocalAdjustment.from_euler_xyz(adjustment, rotation_xyz_rad)
    )
    return local.apply_to(reference)


_GEOMETRY_TYPES = frozenset({"body", "shell", "face", "edge", "vertex"})


@dataclass(frozen=True, slots=True)
class GeometryReference:
    """Stable topology reference plus a kernel-independent geometric signature."""

    object_id: str
    geometry_type: str
    signature: Mapping[str, Any] = field(default_factory=dict, hash=False)
    parent_body_id: str | None = None
    assembly_name: str | None = None

    def __post_init__(self) -> None:
        object_id = str(self.object_id).strip()
        geometry_type = str(self.geometry_type).strip().lower()
        if not object_id:
            raise ValueError("object_id must not be empty")
        if geometry_type not in _GEOMETRY_TYPES:
            raise ValueError(f"unsupported geometry_type: {geometry_type!r}")
        if not isinstance(self.signature, Mapping):
            raise ValueError("signature must be an object")
        parent_body_id = None if self.parent_body_id is None else str(self.parent_body_id).strip()
        assembly_name = None if self.assembly_name is None else str(self.assembly_name).strip()
        object.__setattr__(self, "object_id", object_id)
        object.__setattr__(self, "geometry_type", geometry_type)
        object.__setattr__(self, "signature", _freeze_json(self.signature, name="signature"))
        object.__setattr__(self, "parent_body_id", parent_body_id or None)
        object.__setattr__(self, "assembly_name", assembly_name or None)

    @property
    def stable_id(self) -> str:
        return self.object_id

    @property
    def topology_type(self) -> str:
        return self.geometry_type

    def to_json(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "geometry_type": self.geometry_type,
            "signature": _thaw_json(self.signature),
            "parent_body_id": self.parent_body_id,
            "assembly_name": self.assembly_name,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> GeometryReference:
        if not isinstance(payload, Mapping):
            raise ValueError("geometry reference payload must be an object")
        return cls(
            object_id=str(
                payload.get("object_id", payload.get("stable_id", payload.get("id", "")))
            ),
            geometry_type=str(payload.get("geometry_type", payload.get("topology_type", ""))),
            signature=payload.get("signature", {}),
            parent_body_id=payload.get("parent_body_id"),
            assembly_name=payload.get("assembly_name"),
        )


_POINT_REFERENCE_TYPES = frozenset(
    {
        "vertex",
        "circle_center",
        "ellipse_center",
        "arc_midpoint",
        "face_centroid",
        "face_pick",
        "numeric",
    }
)


@dataclass(frozen=True, slots=True)
class PointReference:
    """A confirmed or candidate frame-origin reference."""

    reference_type: str
    point_in_source_mm: Vector3 | None = None
    geometry: GeometryReference | None = None
    parameter: float | None = None
    confirmed: bool = False

    def __post_init__(self) -> None:
        reference_type = str(self.reference_type).strip().lower()
        if reference_type not in _POINT_REFERENCE_TYPES:
            raise ValueError(f"unsupported point reference_type: {reference_type!r}")
        point = (
            None
            if self.point_in_source_mm is None
            else _vector3(self.point_in_source_mm, name="point_in_source_mm")
        )
        parameter = (
            None if self.parameter is None else _finite_float(self.parameter, name="parameter")
        )
        if reference_type == "numeric" and point is None:
            raise ValueError("numeric point reference requires point_in_source_mm")
        if reference_type != "numeric" and self.geometry is None:
            raise ValueError(f"{reference_type} point reference requires geometry")
        object.__setattr__(self, "reference_type", reference_type)
        object.__setattr__(self, "point_in_source_mm", point)
        object.__setattr__(self, "parameter", parameter)
        object.__setattr__(
            self,
            "confirmed",
            require_bool(self.confirmed, field_name="confirmed"),
        )

    @property
    def kind(self) -> str:
        return self.reference_type

    @property
    def resolved_point(self) -> Vector3:
        if self.point_in_source_mm is None:
            raise ValueError("point reference has not been resolved in Source CS")
        return self.point_in_source_mm

    def to_json(self) -> dict[str, Any]:
        return {
            "reference_type": self.reference_type,
            "point_in_source_mm": (
                None if self.point_in_source_mm is None else list(self.point_in_source_mm)
            ),
            "geometry": None if self.geometry is None else self.geometry.to_json(),
            "parameter": self.parameter,
            "confirmed": self.confirmed,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> PointReference:
        if not isinstance(payload, Mapping):
            raise ValueError("point reference payload must be an object")
        geometry_payload = payload.get("geometry")
        return cls(
            reference_type=str(payload.get("reference_type", payload.get("kind", ""))),
            point_in_source_mm=payload.get("point_in_source_mm"),
            geometry=(
                None if geometry_payload is None else GeometryReference.from_json(geometry_payload)
            ),
            parameter=payload.get("parameter"),
            confirmed=parse_json_bool(
                payload,
                "confirmed",
                default=False,
                field_name="point_reference.confirmed",
            ),
        )


_DIRECTION_REFERENCE_TYPES = frozenset(
    {"line_edge", "two_points", "plane_normal", "surface_axis", "numeric"}
)


@dataclass(frozen=True, slots=True)
class DirectionReference:
    """A confirmed or candidate axis-direction reference."""

    reference_type: str
    direction_in_source: Vector3 | None = None
    geometry: GeometryReference | None = None
    secondary_geometry: GeometryReference | None = None
    first_point_in_source_mm: Vector3 | None = None
    second_point_in_source_mm: Vector3 | None = None
    flipped: bool = False
    confirmed: bool = False

    def __post_init__(self) -> None:
        reference_type = str(self.reference_type).strip().lower()
        if reference_type not in _DIRECTION_REFERENCE_TYPES:
            raise ValueError(f"unsupported direction reference_type: {reference_type!r}")
        direction = (
            None
            if self.direction_in_source is None
            else _vector3(self.direction_in_source, name="direction_in_source")
        )
        first_point = (
            None
            if self.first_point_in_source_mm is None
            else _vector3(self.first_point_in_source_mm, name="first_point_in_source_mm")
        )
        second_point = (
            None
            if self.second_point_in_source_mm is None
            else _vector3(self.second_point_in_source_mm, name="second_point_in_source_mm")
        )
        if direction is not None and _norm(direction) <= _EPSILON:
            raise ValueError("direction_in_source must be non-zero")
        if reference_type == "numeric" and direction is None:
            raise ValueError("numeric direction reference requires direction_in_source")
        if reference_type == "two_points":
            has_points = first_point is not None and second_point is not None
            if direction is None and not has_points:
                raise ValueError("two_points direction requires two resolved points or a direction")
            if has_points and _norm(_subtract(second_point, first_point)) <= _EPSILON:  # type: ignore[arg-type]
                raise ValueError("two_points direction requires distinct points")
        elif reference_type != "numeric" and self.geometry is None:
            raise ValueError(f"{reference_type} direction reference requires geometry")
        object.__setattr__(self, "reference_type", reference_type)
        object.__setattr__(self, "direction_in_source", direction)
        object.__setattr__(self, "first_point_in_source_mm", first_point)
        object.__setattr__(self, "second_point_in_source_mm", second_point)
        object.__setattr__(
            self,
            "flipped",
            require_bool(self.flipped, field_name="flipped"),
        )
        object.__setattr__(
            self,
            "confirmed",
            require_bool(self.confirmed, field_name="confirmed"),
        )

    @property
    def kind(self) -> str:
        return self.reference_type

    @property
    def resolved_direction(self) -> Vector3:
        direction = self.direction_in_source
        if (
            direction is None
            and self.first_point_in_source_mm is not None
            and self.second_point_in_source_mm is not None
        ):
            direction = _subtract(
                self.second_point_in_source_mm,
                self.first_point_in_source_mm,
            )
        if direction is None:
            raise ValueError("direction reference has not been resolved in Source CS")
        unit = _normalise(direction, name="resolved direction")
        return _scale(unit, -1.0) if self.flipped else unit

    def to_json(self) -> dict[str, Any]:
        return {
            "reference_type": self.reference_type,
            "direction_in_source": (
                None if self.direction_in_source is None else list(self.direction_in_source)
            ),
            "geometry": None if self.geometry is None else self.geometry.to_json(),
            "secondary_geometry": (
                None if self.secondary_geometry is None else self.secondary_geometry.to_json()
            ),
            "first_point_in_source_mm": (
                None
                if self.first_point_in_source_mm is None
                else list(self.first_point_in_source_mm)
            ),
            "second_point_in_source_mm": (
                None
                if self.second_point_in_source_mm is None
                else list(self.second_point_in_source_mm)
            ),
            "flipped": self.flipped,
            "confirmed": self.confirmed,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> DirectionReference:
        if not isinstance(payload, Mapping):
            raise ValueError("direction reference payload must be an object")
        geometry_payload = payload.get("geometry")
        secondary_payload = payload.get("secondary_geometry")
        return cls(
            reference_type=str(payload.get("reference_type", payload.get("kind", ""))),
            direction_in_source=payload.get("direction_in_source"),
            geometry=(
                None if geometry_payload is None else GeometryReference.from_json(geometry_payload)
            ),
            secondary_geometry=(
                None
                if secondary_payload is None
                else GeometryReference.from_json(secondary_payload)
            ),
            first_point_in_source_mm=payload.get("first_point_in_source_mm"),
            second_point_in_source_mm=payload.get("second_point_in_source_mm"),
            flipped=parse_json_bool(
                payload,
                "flipped",
                default=False,
                field_name="direction_reference.flipped",
            ),
            confirmed=parse_json_bool(
                payload,
                "confirmed",
                default=False,
                field_name="direction_reference.confirmed",
            ),
        )


@dataclass(frozen=True, slots=True)
class CoordinateFrameDefinition:
    """Applied three-reference coordinate frame in Source CS."""

    frame_id: str
    name: str
    origin_reference: PointReference
    z_direction_reference: DirectionReference
    x_direction_reference: DirectionReference
    T_target_from_source: RigidTransform
    revision: int = 1

    def __post_init__(self) -> None:
        frame_id = str(self.frame_id).strip()
        name = str(self.name).strip()
        if not frame_id:
            raise ValueError("frame_id must not be empty")
        if not name:
            raise ValueError("name must not be empty")
        if not isinstance(self.origin_reference, PointReference):
            raise TypeError("origin_reference must be a PointReference")
        if not isinstance(self.z_direction_reference, DirectionReference):
            raise TypeError("z_direction_reference must be a DirectionReference")
        if not isinstance(self.x_direction_reference, DirectionReference):
            raise TypeError("x_direction_reference must be a DirectionReference")
        if not isinstance(self.T_target_from_source, RigidTransform):
            raise TypeError("T_target_from_source must be a RigidTransform")
        if self.T_target_from_source.source_frame != "source":
            raise ValueError("coordinate transform source_frame must equal 'source'")
        if self.T_target_from_source.target_frame != frame_id:
            raise ValueError("coordinate transform target_frame must equal frame_id")
        revision = int(self.revision)
        if revision < 1:
            raise ValueError("revision must be at least 1")
        object.__setattr__(self, "frame_id", frame_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "revision", revision)

    @classmethod
    def from_references(
        cls,
        frame_id: str,
        name: str,
        origin_reference: PointReference,
        z_direction_reference: DirectionReference,
        x_direction_reference: DirectionReference,
        *,
        source_frame: str = "source",
        revision: int = 1,
    ) -> CoordinateFrameDefinition:
        transform = RigidTransform.from_frame(
            origin_reference.resolved_point,
            x_direction_reference.resolved_direction,
            z_direction_reference.resolved_direction,
            source_frame=source_frame,
            target_frame=str(frame_id).strip(),
        )
        return cls(
            frame_id=frame_id,
            name=name,
            origin_reference=origin_reference,
            z_direction_reference=z_direction_reference,
            x_direction_reference=x_direction_reference,
            T_target_from_source=transform,
            revision=revision,
        )

    @property
    def is_confirmed(self) -> bool:
        return (
            self.origin_reference.confirmed
            and self.z_direction_reference.confirmed
            and self.x_direction_reference.confirmed
        )

    @property
    def is_valid(self) -> bool:
        if not self.is_confirmed:
            return False
        try:
            expected = RigidTransform.from_frame(
                self.origin_reference.resolved_point,
                self.x_direction_reference.resolved_direction,
                self.z_direction_reference.resolved_direction,
                source_frame=self.T_target_from_source.source_frame,
                target_frame=self.frame_id,
            )
        except ValueError:
            return False
        return expected.almost_equal(self.T_target_from_source, tolerance=1.0e-7)

    def to_json(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "name": self.name,
            "origin_reference": self.origin_reference.to_json(),
            "z_direction_reference": self.z_direction_reference.to_json(),
            "x_direction_reference": self.x_direction_reference.to_json(),
            "T_target_from_source": self.T_target_from_source.to_json(),
            "revision": self.revision,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> CoordinateFrameDefinition:
        if not isinstance(payload, Mapping):
            raise ValueError("coordinate frame payload must be an object")
        required = (
            "origin_reference",
            "z_direction_reference",
            "x_direction_reference",
            "T_target_from_source",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"coordinate frame payload is missing {', '.join(missing)}")
        frame = cls(
            frame_id=str(payload.get("frame_id", "")),
            name=str(payload.get("name", "")),
            origin_reference=PointReference.from_json(payload["origin_reference"]),
            z_direction_reference=DirectionReference.from_json(payload["z_direction_reference"]),
            x_direction_reference=DirectionReference.from_json(payload["x_direction_reference"]),
            T_target_from_source=RigidTransform.from_json(payload["T_target_from_source"]),
            revision=int(payload.get("revision", 1)),
        )
        if frame.is_confirmed and not frame.is_valid:
            raise ValueError("coordinate frame references do not match its rigid transform")
        return frame


__all__ = [
    "CoordinateFrameDefinition",
    "DirectionReference",
    "GeometryReference",
    "LocalAdjustment",
    "Matrix3",
    "Matrix4",
    "PointReference",
    "RigidTransform",
    "Vector3",
    "apply_local_adjustment",
]
