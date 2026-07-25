"""Immutable edit-session values for the Tube Setup workflow.

Drafts stay outside ``ManufacturingSetup`` until Apply succeeds.  This keeps
Cancel and failed multi-node Apply operations from mutating the last valid
project state.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    LocalAdjustment,
    PointReference,
    RigidTransform,
    apply_local_adjustment,
)
from .manufacturing.setup import BUILD_CS_NODE, MODEL_CS_NODE, PLACEMENT_NODE
from .models import BodyInfo


class TubeControllerError(RuntimeError):
    """Base error raised at the Tube workflow boundary."""


class OperationLimitError(TubeControllerError):
    """Raised when the interactive operation limit is reached."""


class DraftNotFoundError(TubeControllerError):
    """Raised when an edit command has no active draft."""


class PendingDraftError(TubeControllerError):
    """Raised when persistence is requested with unapplied edits."""

    def __init__(self, nodes: Iterable[str]) -> None:
        self.nodes = tuple(sorted({str(node) for node in nodes}))
        super().__init__("pending Setup drafts: " + ", ".join(self.nodes))


class StaleDraftError(TubeControllerError):
    """Raised when Placement dependencies changed during editing."""


class BodyRole(str, Enum):
    PART = "part"
    IGNORE = "ignore"
    FIXTURE = "fixture"
    UNASSIGNED = "unassigned"


@dataclass(frozen=True, slots=True)
class BodyCandidate:
    """Kernel-independent body descriptor used by the Part editor."""

    body_id: str
    name: str
    kind: str
    signature: str = ""

    def __post_init__(self) -> None:
        body_id = str(self.body_id).strip()
        kind = str(self.kind).strip().lower()
        if not body_id:
            raise ValueError("body_id must not be empty")
        if not kind:
            raise ValueError("body kind must not be empty")
        object.__setattr__(self, "body_id", body_id)
        object.__setattr__(self, "name", str(self.name).strip() or body_id)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "signature", str(self.signature).strip())

    @classmethod
    def from_body_info(cls, body: BodyInfo) -> BodyCandidate:
        return cls(body.body_id, body.name, body.kind, body.signature)

    @property
    def is_part_eligible(self) -> bool:
        return self.kind == "solid"

    def to_json(self) -> dict[str, Any]:
        return {
            "body_id": self.body_id,
            "name": self.name,
            "kind": self.kind,
            "signature": self.signature,
            "is_part_eligible": self.is_part_eligible,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> BodyCandidate:
        if not isinstance(payload, Mapping):
            raise ValueError("body candidate payload must be an object")
        return cls(
            body_id=str(payload.get("body_id", payload.get("id", ""))),
            name=str(payload.get("name", "")),
            kind=str(payload.get("kind", "")),
            signature=str(payload.get("signature", "")),
        )


@dataclass(frozen=True, slots=True)
class CoordinateFrameDraft:
    """Partial three-reference frame awaiting atomic Apply."""

    node: str
    frame_id: str
    name: str
    origin_reference: PointReference | None = None
    z_direction_reference: DirectionReference | None = None
    x_direction_reference: DirectionReference | None = None
    base_revision: int = 0

    def __post_init__(self) -> None:
        node = coordinate_node(self.node)
        frame_id = str(self.frame_id).strip()
        name = str(self.name).strip()
        if not frame_id or not name:
            raise ValueError("draft frame_id and name must not be empty")
        if self.origin_reference is not None and not isinstance(
            self.origin_reference, PointReference
        ):
            raise TypeError("origin_reference must be PointReference")
        for field_name in ("z_direction_reference", "x_direction_reference"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, DirectionReference):
                raise TypeError(f"{field_name} must be DirectionReference")
        base_revision = int(self.base_revision)
        if base_revision < 0:
            raise ValueError("base_revision cannot be negative")
        object.__setattr__(self, "node", node)
        object.__setattr__(self, "frame_id", frame_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "base_revision", base_revision)

    @classmethod
    def from_applied(
        cls,
        node: str,
        frame: CoordinateFrameDefinition | None,
    ) -> CoordinateFrameDraft:
        canonical = coordinate_node(node)
        frame_id = "model" if canonical == MODEL_CS_NODE else "build"
        if frame is None:
            name = "Model CS" if canonical == MODEL_CS_NODE else "Build CS"
            return cls(canonical, frame_id, name)
        return cls(
            node=canonical,
            frame_id=frame_id,
            name=frame.name,
            origin_reference=frame.origin_reference,
            z_direction_reference=frame.z_direction_reference,
            x_direction_reference=frame.x_direction_reference,
            base_revision=frame.revision,
        )

    @property
    def is_complete(self) -> bool:
        return (
            self.origin_reference is not None
            and self.z_direction_reference is not None
            and self.x_direction_reference is not None
        )

    @property
    def is_confirmed(self) -> bool:
        references = (
            self.origin_reference,
            self.z_direction_reference,
            self.x_direction_reference,
        )
        return self.is_complete and all(
            reference is not None and reference.confirmed for reference in references
        )

    def to_applied(self) -> CoordinateFrameDefinition:
        if not self.is_complete:
            raise ValueError(f"{self.node} requires origin, Z, and X references")
        if not self.is_confirmed:
            raise ValueError(f"{self.node} references must be individually confirmed")
        assert self.origin_reference is not None
        assert self.z_direction_reference is not None
        assert self.x_direction_reference is not None
        return CoordinateFrameDefinition.from_references(
            self.frame_id,
            self.name,
            self.origin_reference,
            self.z_direction_reference,
            self.x_direction_reference,
            revision=self.base_revision + 1,
        )

    def to_json(self) -> dict[str, Any]:
        references = {
            "origin_reference": self.origin_reference,
            "z_direction_reference": self.z_direction_reference,
            "x_direction_reference": self.x_direction_reference,
        }
        return {
            "node": self.node,
            "frame_id": self.frame_id,
            "name": self.name,
            **{
                key: None if value is None else value.to_json() for key, value in references.items()
            },
            "base_revision": self.base_revision,
            "complete": self.is_complete,
            "confirmed": self.is_confirmed,
        }


@dataclass(frozen=True, slots=True)
class PlacementDraft:
    """Mount pairing and local six-DOF adjustment under edit."""

    mount_datum_id: str | None = None
    T_reference_mount_from_build: RigidTransform | None = None
    adjustment: LocalAdjustment = field(default_factory=LocalAdjustment)
    build_cs_revision: int | None = None
    machine_content_hash: str | None = None

    def __post_init__(self) -> None:
        mount_id = _optional_text(self.mount_datum_id)
        if self.T_reference_mount_from_build is not None and not isinstance(
            self.T_reference_mount_from_build, RigidTransform
        ):
            raise TypeError("T_reference_mount_from_build must be RigidTransform")
        if not isinstance(self.adjustment, LocalAdjustment):
            raise TypeError("adjustment must be LocalAdjustment")
        revision = None if self.build_cs_revision is None else int(self.build_cs_revision)
        if revision is not None and revision < 1:
            raise ValueError("build_cs_revision must be positive")
        object.__setattr__(self, "mount_datum_id", mount_id)
        object.__setattr__(self, "build_cs_revision", revision)
        object.__setattr__(self, "machine_content_hash", _optional_text(self.machine_content_hash))

    @property
    def is_complete(self) -> bool:
        return self.mount_datum_id is not None and self.T_reference_mount_from_build is not None

    @property
    def T_mount_from_build(self) -> RigidTransform:
        if self.T_reference_mount_from_build is None:
            raise ValueError("Placement requires a mount reference transform")
        return apply_local_adjustment(
            self.T_reference_mount_from_build,
            self.adjustment,
        )

    def to_json(self) -> dict[str, Any]:
        reference = self.T_reference_mount_from_build
        return {
            "mount_datum_id": self.mount_datum_id,
            "T_reference_mount_from_build": (None if reference is None else reference.to_json()),
            "adjustment": self.adjustment.to_json(),
            "build_cs_revision": self.build_cs_revision,
            "machine_content_hash": self.machine_content_hash,
            "complete": self.is_complete,
        }


def coordinate_node(node: str) -> str:
    aliases = {
        "model": MODEL_CS_NODE,
        "model_cs": MODEL_CS_NODE,
        "build": BUILD_CS_NODE,
        "build_cs": BUILD_CS_NODE,
    }
    try:
        return aliases[str(node).strip().lower()]
    except KeyError as exc:
        raise ValueError(f"unsupported coordinate node: {node!r}") from exc


def draft_node(node: str) -> str:
    canonical = str(node).strip().lower()
    if canonical in {"placement", PLACEMENT_NODE}:
        return PLACEMENT_NODE
    return coordinate_node(canonical)


def direction_axis(axis: str) -> str:
    canonical = str(axis).strip().lower()
    if canonical in {"z", "z_direction"}:
        return "z"
    if canonical in {"x", "x_direction"}:
        return "x"
    raise ValueError(f"direction axis must be X or Z: {axis!r}")


def numeric_input_frame(node: str, input_frame: str | None) -> str:
    if input_frame is None:
        return "source" if coordinate_node(node) == MODEL_CS_NODE else "model"
    canonical = str(input_frame).strip().lower().removesuffix("_cs")
    if canonical not in {"source", "model", "build"}:
        raise ValueError(f"unsupported numeric input frame: {input_frame!r}")
    return canonical


def identity_mount_transform(mount_datum_id: str) -> RigidTransform:
    return RigidTransform(
        RigidTransform.identity().matrix,
        source_frame="build",
        target_frame=str(mount_datum_id).strip(),
    )


def normalise_mount_transform(
    mount_datum_id: str,
    transform: RigidTransform,
) -> RigidTransform:
    if not isinstance(transform, RigidTransform):
        raise TypeError("reference_transform must be RigidTransform")
    mount_id = str(mount_datum_id).strip()
    if transform.source_frame not in {"", "build"}:
        raise ValueError("T_mount_from_build source frame must be Build CS")
    if transform.target_frame not in {"", "mount", mount_id}:
        raise ValueError("T_mount_from_build target frame must match the mount datum")
    return RigidTransform(
        transform.matrix,
        source_frame="build",
        target_frame=mount_id,
    )


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


__all__ = [
    "BodyCandidate",
    "BodyRole",
    "CoordinateFrameDraft",
    "DraftNotFoundError",
    "OperationLimitError",
    "PendingDraftError",
    "PlacementDraft",
    "StaleDraftError",
    "TubeControllerError",
    "coordinate_node",
    "direction_axis",
    "draft_node",
    "identity_mount_transform",
    "normalise_mount_transform",
    "numeric_input_frame",
]
