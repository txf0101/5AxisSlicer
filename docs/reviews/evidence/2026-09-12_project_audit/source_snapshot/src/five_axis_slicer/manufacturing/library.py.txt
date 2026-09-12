"""Persistent user library for manufacturing resource profiles.

The library is deliberately independent from Qt and project persistence.
Projects retain immutable :class:`ResourceSnapshot` values, while this store
contains editable user profiles.  A profile update can therefore be reported
as a divergence without changing an already saved project.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, TypeAlias

from .machine import MachineProfile, builtin_machine_profiles
from .resources import (
    MaterialProfile,
    NozzleProfile,
    ResourceSnapshot,
    builtin_material_profiles,
    builtin_nozzle_profiles,
)


RESOURCE_LIBRARY_SCHEMA_VERSION = 1
_RESOURCE_TYPES = frozenset({"machine", "nozzle", "material"})


class ResourceLibraryError(RuntimeError):
    """The user resource library cannot safely read or persist a profile."""


@dataclass(frozen=True, slots=True)
class ResourceSnapshotAudit:
    """Comparison between a project snapshot and the current user library."""

    resource_type: str
    resource_id: str
    status: str
    snapshot_content_hash: str
    library_content_hash: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"match", "diverged", "missing"}:
            raise ValueError(f"unsupported resource audit status: {self.status}")

    @property
    def diverged(self) -> bool:
        return self.status == "diverged"

    def to_json(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "status": self.status,
            "snapshot_content_hash": self.snapshot_content_hash,
            "library_content_hash": self.library_content_hash,
        }


ResourceProfile: TypeAlias = MachineProfile | NozzleProfile | MaterialProfile


@dataclass(frozen=True, slots=True)
class ResourceLibraryDiagnostic:
    """Non-fatal problem found while scanning one user-library entry."""

    resource_type: str
    entry_name: str
    code: str
    detail: str
    resource_id: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "entry_name": self.entry_name,
            "code": self.code,
            "detail": self.detail,
            "resource_id": self.resource_id,
        }


@dataclass(frozen=True, slots=True)
class ResourceLibraryCatalog:
    """Usable profiles and isolated entry diagnostics from one scan."""

    resource_type: str
    profiles: tuple[ResourceProfile, ...]
    diagnostics: tuple[ResourceLibraryDiagnostic, ...] = ()


def default_user_resource_library_root() -> Path:
    """Return the per-user resource-library directory without creating it.

    ``FIVE_AXIS_SLICER_RESOURCE_LIBRARY`` is intentionally supported for
    managed installations and hermetic tests.  The fallback follows the host
    platform's conventional per-user application-data location.
    """

    configured = os.environ.get("FIVE_AXIS_SLICER_RESOURCE_LIBRARY", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        local_data = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_data) if local_data else Path.home() / "AppData" / "Local"
        return (base / "5AxisSclicer" / "resource-library").resolve()
    xdg_data = os.environ.get("XDG_DATA_HOME", "").strip()
    base = Path(xdg_data).expanduser() if xdg_data else Path.home() / ".local" / "share"
    return (base / "five-axis-slicer" / "resource-library").resolve()


class UserResourceLibrary:
    """Atomic, versioned store for editable Machine, Nozzle, and Material profiles."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def save(self, profile: ResourceProfile) -> Path:
        """Validate and atomically persist one non-built-in profile."""

        resource_type, resource_id, payload = _profile_payload(profile)
        if _is_builtin(profile):
            raise ResourceLibraryError(
                "built-in templates are immutable; save an editable copy with a new ID"
            )
        # Parse the serialized form before writing.  This keeps the file boundary
        # aligned with project loading rather than trusting an arbitrary object
        # that merely exposes to_json().
        _profile_from_payload(resource_type, payload)
        envelope = {
            "schema_version": RESOURCE_LIBRARY_SCHEMA_VERSION,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "profile": payload,
        }
        destination = self._entry_path(resource_type, resource_id)
        _atomic_write_json(destination, envelope)
        return destination

    def load(self, resource_type: str, resource_id: str) -> ResourceProfile:
        canonical_type = _resource_type(resource_type)
        identifier = _resource_id(resource_id)
        path = self._entry_path(canonical_type, identifier)
        if not path.is_file():
            raise KeyError(identifier)
        envelope = _read_envelope(path)
        if envelope["resource_type"] != canonical_type:
            raise ResourceLibraryError(f"resource type mismatch in {path}")
        if envelope["resource_id"] != identifier:
            raise ResourceLibraryError(f"resource ID mismatch in {path}")
        profile = _profile_from_payload(canonical_type, envelope["profile"])
        actual_type, actual_id, _payload = _profile_payload(profile)
        if actual_type != canonical_type or actual_id != identifier:
            raise ResourceLibraryError(f"profile identity mismatch in {path}")
        return profile

    def profiles(self, resource_type: str) -> tuple[ResourceProfile, ...]:
        """Return all valid profiles of one type in stable identity order."""

        canonical_type = _resource_type(resource_type)
        directory = self.root / canonical_type
        if not directory.exists():
            return ()
        profiles: list[ResourceProfile] = []
        seen: set[str] = set()
        for path in sorted(directory.glob("*.json")):
            envelope = _read_envelope(path)
            if envelope["resource_type"] != canonical_type:
                raise ResourceLibraryError(f"resource type mismatch in {path}")
            profile = _profile_from_payload(canonical_type, envelope["profile"])
            _actual_type, identifier, _payload = _profile_payload(profile)
            if identifier != envelope["resource_id"]:
                raise ResourceLibraryError(f"profile identity mismatch in {path}")
            if identifier in seen:
                raise ResourceLibraryError(f"duplicate {canonical_type} resource ID: {identifier}")
            seen.add(identifier)
            profiles.append(profile)
        return tuple(sorted(profiles, key=lambda item: _profile_payload(item)[1]))

    def scan_user_profiles(self, resource_type: str) -> ResourceLibraryCatalog:
        """Read valid user profiles while isolating damaged entries."""

        canonical_type = _resource_type(resource_type)
        directory = self.root / canonical_type
        if not directory.exists():
            return ResourceLibraryCatalog(canonical_type, ())
        profiles: list[ResourceProfile] = []
        diagnostics: list[ResourceLibraryDiagnostic] = []
        seen: set[str] = set()
        try:
            paths = tuple(sorted(directory.glob("*.json")))
        except OSError as exc:
            return ResourceLibraryCatalog(
                canonical_type,
                (),
                (
                    ResourceLibraryDiagnostic(
                        canonical_type,
                        directory.name,
                        "library_directory_unreadable",
                        str(exc),
                    ),
                ),
            )
        for path in paths:
            resource_id: str | None = None
            try:
                envelope = _read_envelope(path)
                resource_id = envelope["resource_id"]
                if envelope["resource_type"] != canonical_type:
                    raise ResourceLibraryError(f"resource type mismatch in {path}")
                profile = _profile_from_payload(canonical_type, envelope["profile"])
                _actual_type, identifier, _payload = _profile_payload(profile)
                if identifier != resource_id:
                    raise ResourceLibraryError(f"profile identity mismatch in {path}")
                if identifier in seen:
                    raise ResourceLibraryError(
                        f"duplicate {canonical_type} resource ID: {identifier}"
                    )
            except (
                AttributeError,
                KeyError,
                ResourceLibraryError,
                TypeError,
                ValueError,
            ) as exc:
                diagnostics.append(
                    ResourceLibraryDiagnostic(
                        canonical_type,
                        path.name,
                        "library_entry_invalid",
                        str(exc),
                        resource_id,
                    )
                )
                continue
            seen.add(identifier)
            profiles.append(profile)
        return ResourceLibraryCatalog(
            canonical_type,
            tuple(sorted(profiles, key=lambda item: _profile_payload(item)[1])),
            tuple(diagnostics),
        )

    def builtin_profiles(self, resource_type: str) -> tuple[ResourceProfile, ...]:
        """Return immutable bundled templates for one resource type."""

        canonical_type = _resource_type(resource_type)
        if canonical_type == "machine":
            return tuple(builtin_machine_profiles())
        if canonical_type == "nozzle":
            return tuple(builtin_nozzle_profiles())
        return tuple(builtin_material_profiles())

    def available_profiles(self, resource_type: str) -> tuple[ResourceProfile, ...]:
        """Return bundled templates followed by editable user profiles.

        Resource identities are unique across both stores.  Rejecting a
        collision prevents a user file from shadowing an immutable template.
        """

        return self.catalog(resource_type).profiles

    def catalog(self, resource_type: str) -> ResourceLibraryCatalog:
        """Return a resilient combined catalog for application startup."""

        canonical_type = _resource_type(resource_type)
        builtins = self.builtin_profiles(canonical_type)
        scan = self.scan_user_profiles(canonical_type)
        builtin_ids = {_profile_payload(profile)[1] for profile in builtins}
        accepted: list[ResourceProfile] = []
        diagnostics = list(scan.diagnostics)
        for profile in scan.profiles:
            identifier = _profile_payload(profile)[1]
            if identifier in builtin_ids:
                diagnostics.append(
                    ResourceLibraryDiagnostic(
                        canonical_type,
                        hashlib.sha256(identifier.encode("utf-8")).hexdigest() + ".json",
                        "builtin_identity_shadowed",
                        f"user resource shadows immutable built-in ID: {identifier}",
                        identifier,
                    )
                )
                continue
            accepted.append(profile)
        return ResourceLibraryCatalog(
            canonical_type,
            builtins + tuple(accepted),
            tuple(diagnostics),
        )

    def resolve(self, resource_type: str, resource_id: str) -> ResourceProfile:
        """Resolve an identity from the built-in and user stores."""

        canonical_type = _resource_type(resource_type)
        identifier = _resource_id(resource_id)
        for profile in self.builtin_profiles(canonical_type):
            if _profile_payload(profile)[1] == identifier:
                return profile
        return self.load(canonical_type, identifier)

    def audit_snapshot(self, snapshot: ResourceSnapshot) -> ResourceSnapshotAudit:
        """Compare a frozen project resource with its optional library counterpart."""

        if not isinstance(snapshot, ResourceSnapshot):
            raise TypeError("snapshot must be a ResourceSnapshot")
        canonical_type = _resource_type(snapshot.resource_type)
        try:
            profile = self.resolve(canonical_type, snapshot.resource_id)
        except KeyError:
            return ResourceSnapshotAudit(
                canonical_type,
                snapshot.resource_id,
                "missing",
                snapshot.content_hash,
            )
        current = ResourceSnapshot.capture(canonical_type, profile)
        status = "match" if current.content_hash == snapshot.content_hash else "diverged"
        return ResourceSnapshotAudit(
            canonical_type,
            snapshot.resource_id,
            status,
            snapshot.content_hash,
            current.content_hash,
        )

    def audit_snapshots(
        self,
        snapshots: Iterable[ResourceSnapshot],
    ) -> tuple[ResourceSnapshotAudit, ...]:
        return tuple(self.audit_snapshot(snapshot) for snapshot in snapshots)

    def _entry_path(self, resource_type: str, resource_id: str) -> Path:
        canonical_type = _resource_type(resource_type)
        identifier = _resource_id(resource_id)
        # Resource IDs are data, not path fragments.  A digest also avoids
        # Windows-reserved characters and keeps every write below ``root``.
        file_name = hashlib.sha256(identifier.encode("utf-8")).hexdigest() + ".json"
        return self.root / canonical_type / file_name


def _resource_type(value: object) -> str:
    result = str(value).strip().lower().removesuffix("_profile")
    if result not in _RESOURCE_TYPES:
        raise ValueError(f"unsupported resource type: {value!r}")
    return result


def _resource_id(value: object) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError("resource_id must not be empty")
    return result


def _profile_payload(profile: ResourceProfile) -> tuple[str, str, dict[str, Any]]:
    if isinstance(profile, MachineProfile):
        resource_type = "machine"
        resource_id = profile.profile_id
    elif isinstance(profile, NozzleProfile):
        resource_type = "nozzle"
        resource_id = profile.resource_id
    elif isinstance(profile, MaterialProfile):
        resource_type = "material"
        resource_id = profile.resource_id
    else:
        raise TypeError("profile must be MachineProfile, NozzleProfile, or MaterialProfile")
    payload = profile.to_json()
    if not isinstance(payload, dict):
        raise ResourceLibraryError("profile serialization must return an object")
    return resource_type, _resource_id(resource_id), payload


def _profile_from_payload(
    resource_type: str,
    payload: Mapping[str, Any],
) -> ResourceProfile:
    if not isinstance(payload, Mapping):
        raise ResourceLibraryError("profile must be a JSON object")
    try:
        if resource_type == "machine":
            return MachineProfile.from_json(payload)
        if resource_type == "nozzle":
            return NozzleProfile.from_json(payload)
        if resource_type == "material":
            return MaterialProfile.from_json(payload)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ResourceLibraryError(f"invalid {resource_type} profile") from exc
    raise ValueError(f"unsupported resource type: {resource_type!r}")


def _is_builtin(profile: ResourceProfile) -> bool:
    if isinstance(profile, MachineProfile):
        builtin_ids = {item.profile_id for item in builtin_machine_profiles()}
        return profile.profile_id in builtin_ids
    if isinstance(profile, NozzleProfile):
        builtin_ids = {item.resource_id for item in builtin_nozzle_profiles()}
    else:
        builtin_ids = {item.resource_id for item in builtin_material_profiles()}
    return bool(profile.is_builtin or profile.resource_id in builtin_ids)


def _read_envelope(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResourceLibraryError(f"cannot read resource library entry: {path}") from exc
    if not isinstance(payload, dict):
        raise ResourceLibraryError(f"resource library entry must be an object: {path}")
    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ResourceLibraryError(f"resource library schema is invalid: {path}")
    if version > RESOURCE_LIBRARY_SCHEMA_VERSION:
        raise ResourceLibraryError(
            f"resource library schema {version} is newer than supported schema "
            f"{RESOURCE_LIBRARY_SCHEMA_VERSION}: {path}"
        )
    if version != RESOURCE_LIBRARY_SCHEMA_VERSION:
        raise ResourceLibraryError(f"unsupported resource library schema {version}: {path}")
    resource_type = _resource_type(payload.get("resource_type"))
    resource_id = _resource_id(payload.get("resource_id"))
    profile = payload.get("profile")
    if not isinstance(profile, Mapping):
        raise ResourceLibraryError(f"resource profile must be an object: {path}")
    return {
        **payload,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "profile": dict(profile),
    }


def _atomic_write_json(destination: Path, payload: Mapping[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


__all__ = [
    "RESOURCE_LIBRARY_SCHEMA_VERSION",
    "ResourceLibraryCatalog",
    "ResourceLibraryDiagnostic",
    "ResourceLibraryError",
    "ResourceSnapshotAudit",
    "UserResourceLibrary",
    "default_user_resource_library_root",
]
