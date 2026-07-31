"""Portable Manufacturing Setup YAML contract and atomic text storage.

``project.json`` remains the complete project authority.  This module exposes
only portable Setup values: frozen resources, resolved Source-CS coordinates,
placement, and one Tube operation.  Geometry identities, Part assignments,
drafts, issues, and derived states stay in the project domain.

YAML is treated as untrusted input.  Parsing accepts a deliberately small
YAML 1.2 subset before JSON Schema and domain validation run; no constructors,
tags, aliases, or merge keys reach application state.
"""

from __future__ import annotations

import hmac
import io
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, cast

from jsonschema import Draft202012Validator
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq, TaggedScalar
from ruamel.yaml.events import AliasEvent, DocumentStartEvent, MappingEndEvent
from ruamel.yaml.events import MappingStartEvent, NodeEvent, SequenceEndEvent, SequenceStartEvent
from ruamel.yaml.scalarstring import ScalarString

from .manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    LocalAdjustment,
    PointReference,
    RigidTransform,
    _quaternion_from_rotation,
)
from .manufacturing.machine import MachineProfile
from .manufacturing.resources import (
    MaterialProfile,
    NozzleProfile,
    ResourceSnapshot,
    canonical_content_hash,
)
from .manufacturing.setup import (
    ManufacturingSetup,
    NodeState,
    TubeOperationDefinition,
)

FORMAT_ID: Final = "five-axis-slicer.manufacturing-setup"
SCHEMA_VERSION: Final = 1
CONFIG_FILENAME: Final = "manufacturing-setup.yaml"
MAX_CONFIG_BYTES: Final = 2 * 1024 * 1024
MAX_CONFIG_DEPTH: Final = 32
MAX_CONFIG_NODES: Final = 50_000
COORDINATE_CONVENTION: Final = "source_mm_right_handed_column_vector"
PART_POLICY: Final = "preserve_current"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_POINT_PROVENANCE = frozenset(
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
_DIRECTION_PROVENANCE = frozenset(
    {"line_edge", "two_points", "plane_normal", "surface_axis", "numeric"}
)


class SetupConfigError(ValueError):
    """Stable, UI-safe configuration failure without parser tracebacks."""

    def __init__(self, message: str, *, code: str = "E_CONFIG_SCHEMA") -> None:
        super().__init__(message)
        self.code = code


class SetupConfigConflictError(SetupConfigError):
    """The destination changed after its expected fingerprint was captured."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="E_CONFIG_DIVERGED")


def _text(value: Any, field: str) -> str:
    result = str(value).strip()
    if not result:
        raise SetupConfigError(f"{field} must not be empty")
    return result


def _finite_vector(value: Sequence[Any], size: int, field: str) -> tuple[float, ...]:
    if isinstance(value, str | bytes):
        raise SetupConfigError(f"{field} must contain {size} numbers")
    try:
        raw = tuple(value)
    except TypeError as exc:
        raise SetupConfigError(f"{field} must contain {size} numbers") from exc
    if len(raw) != size:
        raise SetupConfigError(f"{field} must contain {size} numbers")
    result: list[float] = []
    for item in raw:
        if isinstance(item, bool):
            raise SetupConfigError(f"{field} must contain finite numbers")
        try:
            number = float(item)
        except (OverflowError, TypeError, ValueError) as exc:
            raise SetupConfigError(f"{field} must contain finite numbers") from exc
        if not math.isfinite(number):
            raise SetupConfigError(f"{field} must contain finite numbers")
        result.append(0.0 if number == 0.0 else number)
    return tuple(result)


def _unit_vector(value: Sequence[Any], field: str) -> tuple[float, float, float]:
    vector = _finite_vector(value, 3, field)
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 1.0e-12:
        raise SetupConfigError(f"{field} must be non-zero")
    return tuple(component / length for component in vector)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class PortableCoordinateFrame:
    """Applied coordinate values with topology-free provenance."""

    name: str
    origin_in_source_mm: tuple[float, float, float]
    z_direction_in_source: tuple[float, float, float]
    x_direction_in_source: tuple[float, float, float]
    origin_provenance: str = "numeric"
    z_provenance: str = "numeric"
    x_provenance: str = "numeric"
    geometry_resolved: bool = False

    def __post_init__(self) -> None:
        name = _text(self.name, "coordinate name")
        origin = _finite_vector(self.origin_in_source_mm, 3, "origin_in_source_mm")
        z_axis = _unit_vector(self.z_direction_in_source, "z_direction_in_source")
        x_axis = _unit_vector(self.x_direction_in_source, "x_direction_in_source")
        if self.origin_provenance not in _POINT_PROVENANCE:
            raise SetupConfigError("unsupported origin provenance")
        if self.z_provenance not in _DIRECTION_PROVENANCE:
            raise SetupConfigError("unsupported Z-direction provenance")
        if self.x_provenance not in _DIRECTION_PROVENANCE:
            raise SetupConfigError("unsupported X-direction provenance")
        expected_geometry = any(
            value != "numeric"
            for value in (self.origin_provenance, self.z_provenance, self.x_provenance)
        )
        if type(self.geometry_resolved) is not bool or self.geometry_resolved != expected_geometry:
            raise SetupConfigError("coordinate provenance has an inconsistent geometry marker")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "origin_in_source_mm", origin)
        object.__setattr__(self, "z_direction_in_source", z_axis)
        object.__setattr__(self, "x_direction_in_source", x_axis)
        self.to_domain("validation")

    @classmethod
    def from_domain(cls, frame: CoordinateFrameDefinition) -> PortableCoordinateFrame:
        return cls(
            name=frame.name,
            origin_in_source_mm=frame.origin_reference.resolved_point,
            z_direction_in_source=frame.z_direction_reference.resolved_direction,
            x_direction_in_source=frame.x_direction_reference.resolved_direction,
            origin_provenance=frame.origin_reference.reference_type,
            z_provenance=frame.z_direction_reference.reference_type,
            x_provenance=frame.x_direction_reference.reference_type,
            geometry_resolved=any(
                reference.reference_type != "numeric"
                for reference in (
                    frame.origin_reference,
                    frame.z_direction_reference,
                    frame.x_direction_reference,
                )
            ),
        )

    def to_domain(self, frame_id: str, *, revision: int = 1) -> CoordinateFrameDefinition:
        """Create an applied frame; the portable provenance remains on this object."""

        return CoordinateFrameDefinition.from_references(
            frame_id,
            self.name,
            PointReference("numeric", self.origin_in_source_mm, confirmed=True),
            DirectionReference("numeric", self.z_direction_in_source, confirmed=True),
            DirectionReference("numeric", self.x_direction_in_source, confirmed=True),
            revision=revision,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "origin_in_source_mm": list(self.origin_in_source_mm),
            "z_direction_in_source": list(self.z_direction_in_source),
            "x_direction_in_source": list(self.x_direction_in_source),
            "provenance": {
                "origin": self.origin_provenance,
                "z_direction": self.z_provenance,
                "x_direction": self.x_provenance,
                "geometry_resolved": self.geometry_resolved,
            },
        }


@dataclass(frozen=True, slots=True)
class TransformComponents:
    """Rigid transform components used by the readable YAML contract."""

    translation_mm: tuple[float, float, float]
    quaternion_xyzw: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        translation = cast(
            tuple[float, float, float], _finite_vector(self.translation_mm, 3, "translation_mm")
        )
        quaternion = cast(
            tuple[float, float, float, float],
            _finite_vector(self.quaternion_xyzw, 4, "quaternion_xyzw"),
        )
        local = LocalAdjustment(
            translation,
            quaternion,
        )
        object.__setattr__(self, "translation_mm", local.translation_mm)
        object.__setattr__(self, "quaternion_xyzw", local.quaternion_xyzw)

    @classmethod
    def from_transform(cls, transform: RigidTransform) -> TransformComponents:
        # Coordinates owns the canonical matrix-to-quaternion conversion.
        return cls(transform.translation, _quaternion_from_rotation(transform.rotation))

    @classmethod
    def from_adjustment(cls, adjustment: LocalAdjustment) -> TransformComponents:
        return cls(adjustment.translation_mm, adjustment.quaternion_xyzw)

    def as_adjustment(self) -> LocalAdjustment:
        return LocalAdjustment(self.translation_mm, self.quaternion_xyzw)

    def as_transform(self, source_frame: str, target_frame: str) -> RigidTransform:
        local = self.as_adjustment().to_transform()
        return RigidTransform(
            local.matrix,
            source_frame=source_frame,
            target_frame=target_frame,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "translation_mm": list(self.translation_mm),
            "quaternion_xyzw": list(self.quaternion_xyzw),
        }


@dataclass(frozen=True, slots=True)
class PortablePlacement:
    mount_datum_id: str
    reference: TransformComponents
    adjustment: TransformComponents

    def __post_init__(self) -> None:
        object.__setattr__(self, "mount_datum_id", _text(self.mount_datum_id, "mount_datum_id"))
        if not isinstance(self.reference, TransformComponents):
            raise SetupConfigError("placement reference must be transform components")
        if not isinstance(self.adjustment, TransformComponents):
            raise SetupConfigError("placement adjustment must be transform components")

    @classmethod
    def from_domain(cls, setup: ManufacturingSetup) -> PortablePlacement | None:
        if setup.mount_datum_id is None or setup.T_mount_from_build is None:
            return None
        local_inverse = setup.placement_adjustment.to_transform("build").inverse()
        reference = setup.T_mount_from_build @ local_inverse
        return cls(
            setup.mount_datum_id,
            TransformComponents.from_transform(reference),
            TransformComponents.from_adjustment(setup.placement_adjustment),
        )

    @property
    def T_mount_from_build(self) -> RigidTransform:
        reference = self.reference.as_transform("build", self.mount_datum_id)
        return self.adjustment.as_adjustment().apply_to(reference)

    def to_document(self) -> dict[str, Any]:
        return {
            "mount_datum_id": self.mount_datum_id,
            "reference": self.reference.to_document(),
            "adjustment": self.adjustment.to_document(),
        }


@dataclass(frozen=True, slots=True)
class PortableTubeOperation:
    name: str = "Tube Thin-Wall Indexed"
    enabled: bool = True
    operation_type: str = "tube_thin_wall_indexed"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "operation name"))
        if self.operation_type != "tube_thin_wall_indexed":
            raise SetupConfigError("unsupported Tube operation type")
        if type(self.enabled) is not bool:
            raise SetupConfigError("operation enabled must be a boolean")

    @classmethod
    def from_domain(cls, operation: TubeOperationDefinition) -> PortableTubeOperation:
        return cls(operation.name, operation.enabled, operation.operation_type)

    def to_domain(self, operation_id: str, setup_id: str) -> TubeOperationDefinition:
        return TubeOperationDefinition(
            operation_id=operation_id,
            setup_id=setup_id,
            name=self.name,
            operation_type=self.operation_type,
            state=NodeState.DIRTY,
            dirty_reasons=("setup_config_applied",),
            enabled=self.enabled,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "operation_type": self.operation_type,
            "name": self.name,
            "enabled": self.enabled,
        }


@dataclass(frozen=True, slots=True)
class SetupConfig:
    """Validated portable state ready for a command provider to apply."""

    setup_name: str
    machine: ResourceSnapshot | None
    nozzle: ResourceSnapshot | None
    material: ResourceSnapshot | None
    model_coordinate_system: PortableCoordinateFrame | None
    build_coordinate_system: PortableCoordinateFrame | None
    placement: PortablePlacement | None
    operations: tuple[PortableTubeOperation, ...]
    revision: int
    content_sha256: str
    base_project_setup_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "setup_name", _text(self.setup_name, "setup name"))
        if type(self.revision) is not int or self.revision < 1:
            raise SetupConfigError("metadata revision must be a positive integer")
        if self.content_sha256 is None:
            raise SetupConfigError("content_sha256 must be a lowercase SHA-256 value")
        operations = tuple(self.operations)
        if any(not isinstance(item, PortableTubeOperation) for item in operations):
            raise SetupConfigError("operations must contain portable Tube operations")
        object.__setattr__(self, "operations", operations)
        for field_name in ("content_sha256", "base_project_setup_sha256"):
            value = getattr(self, field_name)
            if value is not None and not _SHA256_RE.fullmatch(value):
                raise SetupConfigError(f"{field_name} must be a lowercase SHA-256 value")
        if len(self.operations) > 1:
            raise SetupConfigError("schema v1 permits at most one Tube operation")
        _validate_resources(self.machine, self.nozzle, self.material)
        _validate_placement(self.machine, self.build_coordinate_system, self.placement)

    @property
    def semantic_sha256(self) -> str:
        return semantic_hash(self.to_document())

    @property
    def content_matches_metadata(self) -> bool:
        return hmac.compare_digest(self.content_sha256, self.semantic_sha256)

    @property
    def geometry_review_required(self) -> bool:
        return any(
            frame is not None and frame.geometry_resolved
            for frame in (self.model_coordinate_system, self.build_coordinate_system)
        )

    def apply_to_setup(self, current: ManufacturingSetup) -> ManufacturingSetup:
        """Replace portable values while retaining project-owned Setup and Part identities."""

        model_revision = (
            1
            if current.model_coordinate_system is None
            else current.model_coordinate_system.revision + 1
        )
        build_revision = (
            1
            if current.build_coordinate_system is None
            else current.build_coordinate_system.revision + 1
        )
        model = (
            None
            if self.model_coordinate_system is None
            else self.model_coordinate_system.to_domain("model", revision=model_revision)
        )
        build = (
            None
            if self.build_coordinate_system is None
            else self.build_coordinate_system.to_domain("build", revision=build_revision)
        )
        placement = self.placement
        return ManufacturingSetup(
            setup_id=current.setup_id,
            name=self.setup_name,
            assignments=current.assignments,
            machine=self.machine,
            nozzle=self.nozzle,
            material=self.material,
            model_coordinate_system=model,
            build_coordinate_system=build,
            mount_datum_id=None if placement is None else placement.mount_datum_id,
            placement_adjustment=(
                LocalAdjustment() if placement is None else placement.adjustment.as_adjustment()
            ),
            T_mount_from_build=(None if placement is None else placement.T_mount_from_build),
            revision=current.revision + 1,
        )

    def apply_to_domain(
        self,
        current_setup: ManufacturingSetup,
        current_operations: Sequence[TubeOperationDefinition],
        *,
        new_operation_id: str | None = None,
    ) -> tuple[ManufacturingSetup, tuple[TubeOperationDefinition, ...]]:
        """Apply portable values and retain current Setup, Part, and operation IDs."""

        setup = self.apply_to_setup(current_setup)
        if not self.operations:
            return setup, ()
        if len(current_operations) > 1:
            raise SetupConfigError("current Tube state contains more than one operation")
        operation_id = (
            current_operations[0].operation_id if current_operations else new_operation_id
        )
        if operation_id is None:
            raise SetupConfigError("new_operation_id is required when no operation exists")
        operation = self.operations[0].to_domain(operation_id, setup.setup_id)
        return setup, (operation,)

    def to_document(self) -> dict[str, Any]:
        def resource(value: ResourceSnapshot | None) -> dict[str, Any] | None:
            return None if value is None else value.to_json()

        def frame(value: PortableCoordinateFrame | None) -> dict[str, Any] | None:
            return None if value is None else value.to_document()

        return {
            "format": FORMAT_ID,
            "schema_version": SCHEMA_VERSION,
            "units": {"length": "mm", "script_angle": "deg"},
            "coordinate_convention": COORDINATE_CONVENTION,
            "part_policy": PART_POLICY,
            "metadata": {
                "revision": self.revision,
                "content_sha256": self.content_sha256,
                "base_project_setup_sha256": self.base_project_setup_sha256,
            },
            "setup": {
                "name": self.setup_name,
                "resources": {
                    "machine": resource(self.machine),
                    "nozzle": resource(self.nozzle),
                    "material": resource(self.material),
                },
                "coordinate_systems": {
                    "model": frame(self.model_coordinate_system),
                    "build": frame(self.build_coordinate_system),
                },
                "placement": None if self.placement is None else self.placement.to_document(),
            },
            "operations": [operation.to_document() for operation in self.operations],
        }


def _validate_resources(
    machine: ResourceSnapshot | None,
    nozzle: ResourceSnapshot | None,
    material: ResourceSnapshot | None,
) -> None:
    for expected, snapshot in (("machine", machine), ("nozzle", nozzle), ("material", material)):
        if snapshot is None:
            continue
        if snapshot.resource_type != expected:
            raise SetupConfigError(f"{expected} slot contains {snapshot.resource_type}")
        try:
            if expected == "machine":
                profile_json = MachineProfile.from_json(snapshot.payload).to_json()
            elif expected == "nozzle":
                profile_json = NozzleProfile.from_json(snapshot.payload).to_json()
            else:
                profile_json = MaterialProfile.from_json(snapshot.payload).to_json()
        except (KeyError, OverflowError, TypeError, ValueError) as exc:
            raise SetupConfigError(f"invalid {expected} resource payload") from exc
        if canonical_content_hash(profile_json) != canonical_content_hash(snapshot.payload):
            raise SetupConfigError(f"{expected} resource payload contains unknown fields")


def _validate_placement(
    machine: ResourceSnapshot | None,
    build: PortableCoordinateFrame | None,
    placement: PortablePlacement | None,
) -> None:
    if placement is None:
        return
    if machine is None or build is None:
        raise SetupConfigError("placement requires Machine and Build CS")
    profile = MachineProfile.from_json(machine.payload)
    if placement.mount_datum_id not in profile.mount_map:
        raise SetupConfigError("placement mount does not belong to Machine")


def export_setup_config(
    setup: ManufacturingSetup,
    operations: Sequence[TubeOperationDefinition] = (),
    *,
    revision: int | None = None,
    base_project_setup_sha256: str | None = None,
) -> SetupConfig:
    """Project an authoritative domain aggregate into its portable subset."""

    portable = SetupConfig(
        setup_name=setup.name,
        machine=setup.machine,
        nozzle=setup.nozzle,
        material=setup.material,
        model_coordinate_system=(
            None
            if setup.model_coordinate_system is None
            else PortableCoordinateFrame.from_domain(setup.model_coordinate_system)
        ),
        build_coordinate_system=(
            None
            if setup.build_coordinate_system is None
            else PortableCoordinateFrame.from_domain(setup.build_coordinate_system)
        ),
        placement=PortablePlacement.from_domain(setup),
        operations=tuple(PortableTubeOperation.from_domain(item) for item in operations),
        revision=setup.revision if revision is None else revision,
        content_sha256="0" * 64,
        base_project_setup_sha256=base_project_setup_sha256,
    )
    return replace(portable, content_sha256=portable.semantic_sha256)


def export_setup_document(
    setup: ManufacturingSetup,
    operations: Sequence[TubeOperationDefinition] = (),
    *,
    revision: int | None = None,
    base_project_setup_sha256: str | None = None,
) -> dict[str, Any]:
    return export_setup_config(
        setup,
        operations,
        revision=revision,
        base_project_setup_sha256=base_project_setup_sha256,
    ).to_document()


def semantic_hash(document: Mapping[str, Any] | SetupConfig) -> str:
    """Hash portable behavior while excluding synchronization metadata."""

    payload = (
        document.to_document() if isinstance(document, SetupConfig) else _to_plain_json(document)
    )
    semantic = {key: value for key, value in payload.items() if key != "metadata"}
    return canonical_content_hash(semantic)


def validate_setup_config(document: Mapping[str, Any]) -> SetupConfig:
    """Validate a parsed document against Schema and existing domain contracts."""

    plain = _to_plain_json(document)
    raw_version = plain.get("schema_version")
    if type(raw_version) is int and raw_version > SCHEMA_VERSION:
        raise SetupConfigError(
            f"unsupported Manufacturing Setup schema {raw_version}",
            code="E_CONFIG_VERSION",
        )
    errors = sorted(
        _validator().iter_errors(plain),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        raise SetupConfigError(f"{path}: {error.message}")
    try:
        setup_payload = plain["setup"]
        resources = setup_payload["resources"]
        coordinates = setup_payload["coordinate_systems"]
        metadata = plain["metadata"]
        return SetupConfig(
            setup_name=setup_payload["name"],
            machine=_resource_from_document(resources["machine"]),
            nozzle=_resource_from_document(resources["nozzle"]),
            material=_resource_from_document(resources["material"]),
            model_coordinate_system=_frame_from_document(coordinates["model"]),
            build_coordinate_system=_frame_from_document(coordinates["build"]),
            placement=_placement_from_document(setup_payload["placement"]),
            operations=tuple(_operation_from_document(item) for item in plain["operations"]),
            revision=metadata["revision"],
            content_sha256=metadata["content_sha256"],
            base_project_setup_sha256=metadata["base_project_setup_sha256"],
        )
    except SetupConfigError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise SetupConfigError(f"invalid Manufacturing Setup semantics: {exc}") from exc


def load_setup_config(text: str | bytes) -> SetupConfig:
    """Strictly parse UTF-8 YAML text without constructing executable objects."""

    _, plain = _parse_yaml_document(text)
    return validate_setup_config(plain)


def load_setup_config_file(path: str | Path) -> SetupConfig:
    from .setup_config_io import load_setup_config_file as load_file

    return load_file(path)


def read_setup_config_snapshot(path: str | Path) -> tuple[SetupConfig, str, str]:
    from .setup_config_io import read_setup_config_snapshot as read_snapshot

    return read_snapshot(path)


def dump_setup_config(
    document: Mapping[str, Any] | SetupConfig,
    *,
    existing_text: str | bytes | None = None,
) -> str:
    """Serialize canonical values while retaining compatible user comments and quotes."""

    plain = (
        document.to_document() if isinstance(document, SetupConfig) else _to_plain_json(document)
    )
    metadata = plain.get("metadata")
    if not isinstance(metadata, dict):
        raise SetupConfigError("metadata must be an object")
    metadata["content_sha256"] = semantic_hash(plain)
    validate_setup_config(plain)
    output: Mapping[str, Any] = plain
    if existing_text is not None:
        round_trip, existing_plain = _parse_yaml_document(existing_text)
        validate_setup_config(existing_plain)
        output = _merge_round_trip(round_trip, plain)
    stream = io.StringIO()
    yaml = _yaml()
    yaml.dump(output, stream)
    result = stream.getvalue().replace("\r\n", "\n").replace("\r", "\n")
    if not result.endswith("\n"):
        result += "\n"
    if len(result.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise SetupConfigError("configuration exceeds 2 MiB")
    return result


def setup_config_fingerprint(path: str | Path) -> str | None:
    from .setup_config_io import setup_config_fingerprint as fingerprint

    return fingerprint(path)


def atomic_write_setup_config(
    destination: str | Path,
    text: str | bytes,
    *,
    expected_fingerprint: str | None = None,
    expect_missing: bool = False,
) -> str:
    from .setup_config_io import atomic_write_setup_config as atomic_write

    return atomic_write(
        destination,
        text,
        expected_fingerprint=expected_fingerprint,
        expect_missing=expect_missing,
    )


def schema_path() -> Path:
    """Locate the source-tree or wheel-installed public JSON Schema."""

    candidates = (
        Path(__file__).resolve().parents[2] / "schemas" / "manufacturing-setup-v1.schema.json",
        Path(sys.prefix)
        / "share"
        / "five-axis-slicer"
        / "schemas"
        / "manufacturing-setup-v1.schema.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SetupConfigError("Manufacturing Setup JSON Schema is unavailable", code="E_CONFIG_IO")


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    try:
        schema = json.loads(schema_path().read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except SetupConfigError:
        raise
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SetupConfigError(f"invalid bundled JSON Schema: {exc}", code="E_CONFIG_IO") from exc
    return Draft202012Validator(schema)


def _resource_from_document(value: Any) -> ResourceSnapshot | None:
    return None if value is None else ResourceSnapshot.from_json(value)


def _frame_from_document(value: Any) -> PortableCoordinateFrame | None:
    if value is None:
        return None
    provenance = value["provenance"]
    return PortableCoordinateFrame(
        name=value["name"],
        origin_in_source_mm=value["origin_in_source_mm"],
        z_direction_in_source=value["z_direction_in_source"],
        x_direction_in_source=value["x_direction_in_source"],
        origin_provenance=provenance["origin"],
        z_provenance=provenance["z_direction"],
        x_provenance=provenance["x_direction"],
        geometry_resolved=provenance["geometry_resolved"],
    )


def _components_from_document(value: Mapping[str, Any]) -> TransformComponents:
    return TransformComponents(value["translation_mm"], value["quaternion_xyzw"])


def _placement_from_document(value: Any) -> PortablePlacement | None:
    if value is None:
        return None
    return PortablePlacement(
        value["mount_datum_id"],
        _components_from_document(value["reference"]),
        _components_from_document(value["adjustment"]),
    )


def _operation_from_document(value: Mapping[str, Any]) -> PortableTubeOperation:
    return PortableTubeOperation(value["name"], value["enabled"], value["operation_type"])


def _decode_yaml_text(value: str | bytes) -> str:
    if isinstance(value, bytes):
        if len(value) > MAX_CONFIG_BYTES:
            raise SetupConfigError("configuration exceeds 2 MiB")
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SetupConfigError("configuration must use UTF-8") from exc
    if not isinstance(value, str):
        raise SetupConfigError("configuration must be text or UTF-8 bytes")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise SetupConfigError("configuration must use UTF-8") from exc
    if size > MAX_CONFIG_BYTES:
        raise SetupConfigError("configuration exceeds 2 MiB")
    return value


def _parse_yaml_document(text: str | bytes) -> tuple[CommentedMap, dict[str, Any]]:
    decoded = _decode_yaml_text(text)
    yaml = _yaml()
    try:
        _scan_yaml_events(yaml, decoded)
        loaded = yaml.load(decoded)
    except SetupConfigError:
        raise
    except Exception as exc:
        raise SetupConfigError(f"invalid YAML: {exc}") from exc
    if not isinstance(loaded, CommentedMap):
        raise SetupConfigError("configuration root must be a mapping")
    _reject_round_trip_features(loaded)
    plain = _to_plain_json(loaded)
    return loaded, plain


def _scan_yaml_events(yaml: YAML, text: str) -> None:
    depth = 0
    nodes = 0
    documents = 0
    starts = (MappingStartEvent, SequenceStartEvent)
    ends = (MappingEndEvent, SequenceEndEvent)
    for event in yaml.parse(text):
        if isinstance(event, DocumentStartEvent):
            documents += 1
        if isinstance(event, AliasEvent):
            raise SetupConfigError("YAML aliases are not allowed")
        if isinstance(event, NodeEvent):
            nodes += 1
            if event.anchor is not None:
                raise SetupConfigError("YAML anchors are not allowed")
            if getattr(event, "tag", None) is not None:
                raise SetupConfigError("explicit YAML tags are not allowed")
        if isinstance(event, starts):
            depth += 1
            if depth > MAX_CONFIG_DEPTH:
                raise SetupConfigError("configuration nesting exceeds 32 levels")
        elif isinstance(event, ends):
            depth -= 1
        if nodes > MAX_CONFIG_NODES:
            raise SetupConfigError("configuration exceeds 50000 nodes")
    if documents != 1:
        raise SetupConfigError("configuration must contain exactly one YAML document")


def _reject_round_trip_features(value: Any) -> None:
    anchor = getattr(value, "anchor", None)
    if anchor is not None and getattr(anchor, "value", None):
        raise SetupConfigError("YAML anchors are not allowed")
    if isinstance(value, CommentedMap):
        if getattr(getattr(value, "tag", None), "value", None) is not None:
            raise SetupConfigError("explicit YAML tags are not allowed")
        if value.merge:
            raise SetupConfigError("YAML merge keys are not allowed")
        for key, item in value.items():
            _reject_round_trip_features(key)
            _reject_round_trip_features(item)
    elif isinstance(value, CommentedSeq):
        if getattr(getattr(value, "tag", None), "value", None) is not None:
            raise SetupConfigError("explicit YAML tags are not allowed")
        for item in value:
            _reject_round_trip_features(item)
    elif isinstance(value, TaggedScalar):
        raise SetupConfigError("explicit YAML tags are not allowed")


def _to_plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SetupConfigError("all YAML mapping keys must be strings")
            result[str(key)] = _to_plain_json(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_to_plain_json(item) for item in value]
    if isinstance(value, TaggedScalar):
        if str(value.tag) == "tag:yaml.org,2002:str":
            return str(value.value)
        raise SetupConfigError("explicit YAML tag is not JSON-compatible")
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SetupConfigError("NaN and infinity are not allowed")
        return 0.0 if value == 0.0 else float(value)
    raise SetupConfigError(f"unsupported YAML value type: {type(value).__name__}")


def _merge_round_trip(existing: Any, fresh: Any) -> Any:
    if isinstance(existing, CommentedMap) and isinstance(fresh, Mapping):
        for key in tuple(existing):
            if key not in fresh:
                del existing[key]
        for key, value in fresh.items():
            existing[key] = (
                _merge_round_trip(existing[key], value)
                if key in existing
                else _to_round_trip(value)
            )
        for key in reversed(tuple(fresh)):
            existing.move_to_end(key, last=False)
        return existing
    if isinstance(existing, CommentedSeq) and isinstance(fresh, list):
        if len(existing) == len(fresh):
            for index, value in enumerate(fresh):
                existing[index] = _merge_round_trip(existing[index], value)
        else:
            existing.clear()
            existing.extend(_to_round_trip(value) for value in fresh)
        return existing
    if isinstance(existing, ScalarString) and isinstance(fresh, str):
        return type(existing)(fresh)
    return _to_round_trip(fresh)


def _to_round_trip(value: Any) -> Any:
    if isinstance(value, Mapping):
        return CommentedMap((key, _to_round_trip(item)) for key, item in value.items())
    if isinstance(value, list):
        return CommentedSeq(_to_round_trip(item) for item in value)
    return value


def _yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.allow_duplicate_keys = False
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    yaml.width = 100
    yaml.indent(mapping=2, sequence=4, offset=2)

    def represent_none(representer: Any, _: None) -> Any:
        return representer.represent_scalar("tag:yaml.org,2002:null", "null")

    yaml.representer.add_representer(type(None), represent_none)
    return yaml
