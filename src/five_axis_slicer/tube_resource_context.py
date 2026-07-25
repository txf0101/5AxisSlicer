"""Environment resource catalogs around project-owned frozen snapshots."""

from __future__ import annotations

from pathlib import Path

from .manufacturing.library import (
    ResourceLibraryDiagnostic,
    ResourceLibraryError,
    ResourceProfile,
    ResourceSnapshotAudit,
    UserResourceLibrary,
)
from .manufacturing.machine import MachineProfile, builtin_machine_profiles
from .manufacturing.resources import (
    MaterialProfile,
    NozzleProfile,
    builtin_material_profiles,
    builtin_nozzle_profiles,
)
from .manufacturing.setup import ManufacturingSetup


class TubeResourceContext:
    """Caches library data without replacing project snapshot authority."""

    def __init__(self, library: UserResourceLibrary | None = None) -> None:
        self._library: UserResourceLibrary | None = None
        self.catalogs: dict[str, tuple[ResourceProfile, ...]] = {}
        self.audits: dict[str, ResourceSnapshotAudit] = {}
        self.audit_failures: dict[str, str] = {}
        self.diagnostics: tuple[ResourceLibraryDiagnostic, ...] = ()
        self.set_library(library)

    @property
    def library(self) -> UserResourceLibrary | None:
        return self._library

    @property
    def ordered_audits(self) -> tuple[ResourceSnapshotAudit, ...]:
        return tuple(
            self.audits[kind] for kind in ("machine", "nozzle", "material") if kind in self.audits
        )

    def set_library(self, library: UserResourceLibrary | None) -> None:
        if library is not None and not isinstance(library, UserResourceLibrary):
            raise TypeError("library must be UserResourceLibrary")
        self._library = library

    def refresh(self, setup: ManufacturingSetup) -> tuple[ResourceSnapshotAudit, ...]:
        self.audits.clear()
        self.audit_failures.clear()
        self.catalogs.clear()
        self.diagnostics = ()
        if self._library is None:
            return ()
        diagnostics: list[ResourceLibraryDiagnostic] = []
        for kind in ("machine", "nozzle", "material"):
            catalog = self._library.catalog(kind)
            self.catalogs[kind] = catalog.profiles
            diagnostics.extend(catalog.diagnostics)
        self.diagnostics = tuple(diagnostics)
        for kind in ("machine", "nozzle", "material"):
            snapshot = getattr(setup, kind)
            if snapshot is None:
                continue
            try:
                self.audits[kind] = self._library.audit_snapshot(snapshot)
            except (
                AttributeError,
                KeyError,
                ResourceLibraryError,
                TypeError,
                ValueError,
            ) as exc:
                self.audit_failures[kind] = str(exc)
        return self.ordered_audits

    def available_profiles(self, resource_type: str) -> tuple[ResourceProfile, ...]:
        kind = resource_kind(resource_type)
        if self._library is not None:
            return self.catalogs.get(kind, ())
        if kind == "machine":
            return tuple(builtin_machine_profiles())
        if kind == "nozzle":
            return tuple(builtin_nozzle_profiles())
        return tuple(builtin_material_profiles())

    def resolve(self, resource_type: str, resource_id: str) -> ResourceProfile:
        kind = resource_kind(resource_type)
        identifier = str(resource_id).strip()
        if not identifier:
            raise ValueError("resource_id must not be empty")
        if self._library is not None:
            return self._library.resolve(kind, identifier)
        for profile in self.available_profiles(kind):
            if profile_resource_id(profile) == identifier:
                return profile
        raise KeyError(identifier)

    def save(self, profile: ResourceProfile) -> Path:
        if self._library is None:
            raise ResourceLibraryError("no user resource library is configured")
        return self._library.save(profile)

    def state_json(self) -> dict[str, object]:
        return {
            "configured": self._library is not None,
            "audits": [audit.to_json() for audit in self.ordered_audits],
            "audit_failures": [
                {"resource_type": kind, "detail": detail}
                for kind, detail in sorted(self.audit_failures.items())
            ],
            "diagnostics": [diagnostic.to_json() for diagnostic in self.diagnostics],
        }


def resource_kind(value: str) -> str:
    kind = str(value).strip().lower().removesuffix("_profile")
    if kind not in {"machine", "nozzle", "material"}:
        raise ValueError(f"unsupported resource type: {value!r}")
    return kind


def profile_resource_id(
    profile: MachineProfile | NozzleProfile | MaterialProfile,
) -> str:
    return profile.profile_id if isinstance(profile, MachineProfile) else profile.resource_id


__all__ = ["TubeResourceContext", "profile_resource_id", "resource_kind"]
