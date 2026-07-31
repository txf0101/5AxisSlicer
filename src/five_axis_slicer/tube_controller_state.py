"""Transactional state boundary for the Qt-independent Tube controller.

Command execution forks only Python-owned workflow state.  CAD/OCP objects and
the resource library remain shared read-only authorities, avoiding unsafe or
expensive native-object deep copies.
"""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, TypeVar, cast

from .manufacturing.setup import ManufacturingSetup, TubeOperationDefinition
from .tube_drafts import CoordinateFrameDraft, PlacementDraft
from .tube_resource_context import TubeResourceContext

Draft = CoordinateFrameDraft | PlacementDraft
_Controller = TypeVar("_Controller", bound="TubeControllerStateBoundary")


@dataclass(frozen=True, slots=True)
class TubeControllerCheckpoint:
    """Immutable Python state used for rollback and bounded undo history."""

    setup: ManufacturingSetup
    operations: tuple[TubeOperationDefinition, ...]
    drafts: Mapping[str, Draft] = field(default_factory=dict)
    modified: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.setup, ManufacturingSetup):
            raise TypeError("checkpoint setup must be ManufacturingSetup")
        operations = tuple(self.operations)
        if any(not isinstance(item, TubeOperationDefinition) for item in operations):
            raise TypeError("checkpoint operations must contain TubeOperationDefinition")
        identifiers = tuple(item.operation_id for item in operations)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("checkpoint operations contain duplicate IDs")
        drafts = dict(self.drafts)
        if any(
            not isinstance(item, CoordinateFrameDraft | PlacementDraft) for item in drafts.values()
        ):
            raise TypeError("checkpoint drafts contain an unsupported value")
        object.__setattr__(self, "operations", operations)
        object.__setattr__(self, "drafts", MappingProxyType(drafts))
        object.__setattr__(self, "modified", bool(self.modified))

    def without_drafts(self) -> TubeControllerCheckpoint:
        return TubeControllerCheckpoint(self.setup, self.operations, modified=self.modified)


class TubeControllerStateBoundary:
    """Mixin exposing the minimal candidate/fork/publish contract to commands."""

    def command_checkpoint(self) -> TubeControllerCheckpoint:
        current = cast(Any, self)
        return TubeControllerCheckpoint(
            current._setup,
            current._operations,
            current._drafts,
            current._modified,
        )

    def command_applied_token(self) -> tuple[object, ...]:
        """Identity token that ignores transient drafts and saved/dirty UI state."""

        current = cast(Any, self)
        return (
            current._setup,
            current._operations,
            current._source_hash,
            id(current._cad_model),
            tuple(current._body_catalog.items()),
        )

    def restore_command_checkpoint(self, checkpoint: TubeControllerCheckpoint) -> None:
        if not isinstance(checkpoint, TubeControllerCheckpoint):
            raise TypeError("checkpoint must be TubeControllerCheckpoint")
        current = cast(Any, self)
        current._setup = checkpoint.setup
        current._operations = checkpoint.operations
        current._drafts = dict(checkpoint.drafts)
        current._modified = checkpoint.modified
        current.refresh_resource_library()

    def fork(self: _Controller) -> _Controller:
        """Return an isolated command candidate without copying native CAD."""

        current = cast(Any, self)
        candidate = copy(current)
        candidate._body_catalog = dict(current._body_catalog)
        candidate._drafts = dict(current._drafts)
        candidate._resources = TubeResourceContext(current.resource_library)
        candidate.refresh_resource_library()
        return cast(_Controller, candidate)

    def publish_from(self, candidate: TubeControllerStateBoundary) -> None:
        """Publish a validated fork while retaining this controller's authority."""

        if type(candidate) is not type(self):
            raise TypeError("candidate must have the same controller type")
        current = cast(Any, self)
        proposed = cast(Any, candidate)
        if _authority_token(current) != _authority_token(proposed):
            raise ValueError("candidate CAD authority differs from the active controller")
        current._setup = proposed._setup
        current._operations = proposed._operations
        current._drafts = dict(proposed._drafts)
        current._modified = proposed._modified
        current._resources = proposed._resources


def _authority_token(controller: Any) -> tuple[object, ...]:
    return (
        id(controller._cad_model),
        controller._source_hash,
        controller._source_path,
        tuple(controller._body_catalog.items()),
        controller._topology_ids,
    )


__all__ = ["TubeControllerCheckpoint", "TubeControllerStateBoundary"]
