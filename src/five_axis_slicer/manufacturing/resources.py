"""Versioned manufacturing resources and immutable project snapshots.

The resource layer intentionally contains no Qt or CAD dependencies.  Profiles
can therefore be used by the desktop UI, project persistence, automation, and
headless validation without creating import cycles.

All built-in profiles are immutable value objects.  Editing a built-in is
modelled as creating a user-owned copy with a new resource identifier.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5

from .json_contract import parse_json_bool, require_bool


RESOURCE_SCHEMA_VERSION = 1
CURA_FDM_MATERIALS_COMMIT = "886e7ad927463493cc9c64f427b1ae2cf4ce12c1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RESOURCE_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ERROR = "error"
_WARNING = "warning"


class ResourceIntegrityError(ValueError):
    """Raised when a persisted resource snapshot fails its content hash."""


def _normalise_json(value: Any, path: str = "$") -> Any:
    """Return a deterministic, JSON-compatible representation of *value*.

    This is deliberately smaller than a general Python serializer.  Rejecting
    unsupported values prevents a hash from depending on an object's repr or
    another process-specific implementation detail.
    """

    if hasattr(value, "to_json") and not isinstance(value, Mapping):
        value = value.to_json()
    elif isinstance(value, Enum):
        value = value.value
    elif isinstance(value, Path):
        value = str(value)

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        # JSON distinguishes -0.0 textually even though the values compare
        # equal.  Normalising it avoids two hashes for the same geometry value.
        return 0.0 if value == 0.0 else value
    if isinstance(value, Mapping):
        normalised: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise TypeError(f"{path} contains a non-string mapping key")
            normalised[key] = _normalise_json(value[key], f"{path}.{key}")
        return normalised
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _normalise_json(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise TypeError(f"{path} contains unsupported value type {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Encode JSON with the project's stable resource-hash convention."""

    normalised = _normalise_json(value)
    return json.dumps(
        normalised,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_content_hash(value: Any) -> str:
    """Return the lowercase SHA-256 of canonical JSON content."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _freeze_json(value: Any) -> Any:
    normalised = _normalise_json(value)
    if isinstance(normalised, dict):
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in normalised.items()}
        )
    if isinstance(normalised, list):
        return tuple(_freeze_json(item) for item in normalised)
    return normalised


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a JSON object")
    return value


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field)


def _require_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer")
    return value


def _require_float(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _optional_float(value: Any, field: str) -> float | None:
    if value is None:
        return None
    return _require_float(value, field)


def _is_positive_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def _snapshot_identity(payload: Mapping[str, Any]) -> tuple[str, int]:
    id_values = [
        payload[key] for key in ("resource_id", "id", "profile_id") if key in payload
    ]
    if not id_values:
        raise TypeError("profile payload must contain resource_id or id")
    resource_id = _require_string(id_values[0], "resource_id")
    if any(value != resource_id for value in id_values[1:]):
        raise ResourceIntegrityError("profile payload contains conflicting identifiers")

    version_values = [
        payload[key] for key in ("profile_version", "version") if key in payload
    ]
    if not version_values:
        raise TypeError("profile payload must contain profile_version or version")
    profile_version = _require_int(version_values[0], "profile_version")
    if any(value != profile_version for value in version_values[1:]):
        raise ResourceIntegrityError("profile payload contains conflicting versions")
    return resource_id, profile_version


def _snapshot_hash_content(
    resource_type: str,
    resource_id: str,
    profile_version: int,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "profile_version": profile_version,
        "payload": payload,
    }


@dataclass(frozen=True, slots=True)
class ResourceValidationIssue:
    """Stable machine-readable resource validation result.

    Human-readable and localised messages are intentionally kept outside the
    persisted resource layer.  UI code can map ``code`` to translated text.
    """

    code: str
    severity: str
    field: str

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("validation issue code cannot be blank")
        if self.severity not in {_ERROR, _WARNING}:
            raise ValueError("validation issue severity must be error or warning")
        if not self.field.strip():
            raise ValueError("validation issue field cannot be blank")

    def to_json(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "field": self.field,
        }


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Pinned provenance for a profile or a recommendation value."""

    title: str
    url: str
    revision: str
    file_path: str
    sha256: str

    def validate(
        self, field_prefix: str = "source"
    ) -> tuple[ResourceValidationIssue, ...]:
        issues: list[ResourceValidationIssue] = []
        for field_name, value in (
            ("title", self.title),
            ("url", self.url),
            ("revision", self.revision),
            ("file_path", self.file_path),
        ):
            if not isinstance(value, str) or not value.strip():
                issues.append(
                    ResourceValidationIssue(
                        "resource.source_field_missing",
                        _ERROR,
                        f"{field_prefix}.{field_name}",
                    )
                )
        if not isinstance(self.sha256, str) or not _SHA256_RE.fullmatch(
            self.sha256.lower()
        ):
            issues.append(
                ResourceValidationIssue(
                    "resource.source_hash_invalid",
                    _ERROR,
                    f"{field_prefix}.sha256",
                )
            )
        return tuple(issues)

    def to_json(self) -> dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "revision": self.revision,
            "file_path": self.file_path,
            "sha256": self.sha256.lower(),
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "SourceReference":
        payload = _require_mapping(value, "source")
        return cls(
            title=_require_string(payload.get("title"), "source.title"),
            url=_require_string(payload.get("url"), "source.url"),
            revision=_require_string(payload.get("revision"), "source.revision"),
            file_path=_require_string(payload.get("file_path"), "source.file_path"),
            sha256=_require_string(payload.get("sha256"), "source.sha256").lower(),
        )


@dataclass(frozen=True, slots=True)
class MaterialRecommendations:
    """Source-provided single nominal temperatures, not a process range."""

    nozzle_temperature_c: float
    build_plate_temperature_c: float

    def validate(self) -> tuple[ResourceValidationIssue, ...]:
        issues: list[ResourceValidationIssue] = []
        if not _is_positive_number(self.nozzle_temperature_c):
            issues.append(
                ResourceValidationIssue(
                    "material.nozzle_temperature_invalid",
                    _ERROR,
                    "recommendations.nozzle_temperature_c",
                )
            )
        if not _is_positive_number(self.build_plate_temperature_c):
            issues.append(
                ResourceValidationIssue(
                    "material.build_plate_temperature_invalid",
                    _ERROR,
                    "recommendations.build_plate_temperature_c",
                )
            )
        return tuple(issues)

    def to_json(self) -> dict[str, float]:
        return {
            "nozzle_temperature_c": float(self.nozzle_temperature_c),
            "build_plate_temperature_c": float(self.build_plate_temperature_c),
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "MaterialRecommendations":
        payload = _require_mapping(value, "recommendations")
        return cls(
            nozzle_temperature_c=_require_float(
                payload.get("nozzle_temperature_c"),
                "recommendations.nozzle_temperature_c",
            ),
            build_plate_temperature_c=_require_float(
                payload.get("build_plate_temperature_c"),
                "recommendations.build_plate_temperature_c",
            ),
        )


@dataclass(frozen=True, slots=True)
class NozzleProfile:
    """Nozzle identity, compatibility, and axisymmetric collision envelope."""

    resource_id: str
    display_name: str
    orifice_diameter_mm: float
    filament_diameter_mm: float
    profile_version: int = 1
    interface: str | None = None
    length_mm: float | None = None
    construction_material: str | None = None
    flow_category: str | None = None
    temperature_limit_c: float | None = None
    wear_resistance_rating: str | None = None
    outer_profile_rz_mm: tuple[tuple[float, float], ...] = ()
    source: SourceReference | None = None
    is_builtin: bool = False

    def __post_init__(self) -> None:
        # Make direct construction with lists just as immutable as JSON loading.
        try:
            profile = tuple(
                (float(point[0]), float(point[1])) for point in self.outer_profile_rz_mm
            )
        except (TypeError, ValueError, IndexError) as exc:
            raise TypeError(
                "outer_profile_rz_mm must contain (radius, z) pairs"
            ) from exc
        object.__setattr__(self, "outer_profile_rz_mm", profile)
        object.__setattr__(
            self,
            "is_builtin",
            require_bool(self.is_builtin, field_name="is_builtin"),
        )

    def validate(self) -> tuple[ResourceValidationIssue, ...]:
        issues: list[ResourceValidationIssue] = []
        if not isinstance(self.resource_id, str) or not self.resource_id.strip():
            issues.append(
                ResourceValidationIssue("resource.id_missing", _ERROR, "resource_id")
            )
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            issues.append(
                ResourceValidationIssue("resource.name_missing", _ERROR, "display_name")
            )
        if (
            not isinstance(self.profile_version, int)
            or isinstance(self.profile_version, bool)
            or self.profile_version < 1
        ):
            issues.append(
                ResourceValidationIssue(
                    "resource.version_invalid", _ERROR, "profile_version"
                )
            )
        if not _is_positive_number(self.orifice_diameter_mm):
            issues.append(
                ResourceValidationIssue(
                    "nozzle.orifice_diameter_invalid", _ERROR, "orifice_diameter_mm"
                )
            )
        if not _is_positive_number(self.filament_diameter_mm):
            issues.append(
                ResourceValidationIssue(
                    "nozzle.filament_diameter_invalid", _ERROR, "filament_diameter_mm"
                )
            )
        if self.interface is None or not self.interface.strip():
            issues.append(
                ResourceValidationIssue("nozzle.interface_missing", _ERROR, "interface")
            )
        if self.length_mm is None:
            issues.append(
                ResourceValidationIssue("nozzle.length_missing", _ERROR, "length_mm")
            )
        elif not _is_positive_number(self.length_mm):
            issues.append(
                ResourceValidationIssue("nozzle.length_invalid", _ERROR, "length_mm")
            )
        if not self.outer_profile_rz_mm:
            issues.append(
                ResourceValidationIssue(
                    "nozzle.outer_profile_missing", _ERROR, "outer_profile_rz_mm"
                )
            )
        elif len(self.outer_profile_rz_mm) < 2 or any(
            not math.isfinite(radius) or not math.isfinite(z) or radius < 0.0
            for radius, z in self.outer_profile_rz_mm
        ):
            issues.append(
                ResourceValidationIssue(
                    "nozzle.outer_profile_invalid", _ERROR, "outer_profile_rz_mm"
                )
            )
        if self.temperature_limit_c is not None and not _is_positive_number(
            self.temperature_limit_c
        ):
            issues.append(
                ResourceValidationIssue(
                    "nozzle.temperature_limit_invalid",
                    _ERROR,
                    "temperature_limit_c",
                )
            )
        if self.source is not None:
            issues.extend(self.source.validate())
        return tuple(issues)

    @property
    def readiness_blockers(self) -> tuple[ResourceValidationIssue, ...]:
        return tuple(issue for issue in self.validate() if issue.severity == _ERROR)

    @property
    def is_ready(self) -> bool:
        return not self.readiness_blockers

    def editable_copy(
        self,
        resource_id: str,
        *,
        display_name: str | None = None,
    ) -> "NozzleProfile":
        """Return a user-owned immutable copy suitable for profile editing."""

        if not resource_id.strip():
            raise ValueError("resource_id cannot be blank")
        return replace(
            self,
            resource_id=resource_id,
            display_name=self.display_name if display_name is None else display_name,
            profile_version=1,
            is_builtin=False,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": RESOURCE_SCHEMA_VERSION,
            "resource_id": self.resource_id,
            "display_name": self.display_name,
            "profile_version": self.profile_version,
            "orifice_diameter_mm": float(self.orifice_diameter_mm),
            "filament_diameter_mm": float(self.filament_diameter_mm),
            "interface": self.interface,
            "length_mm": self.length_mm,
            "construction_material": self.construction_material,
            "flow_category": self.flow_category,
            "temperature_limit_c": self.temperature_limit_c,
            "wear_resistance_rating": self.wear_resistance_rating,
            "outer_profile_rz_mm": [
                [float(radius), float(z)] for radius, z in self.outer_profile_rz_mm
            ],
            "source": None if self.source is None else self.source.to_json(),
            "is_builtin": self.is_builtin,
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "NozzleProfile":
        payload = _require_mapping(value, "nozzle_profile")
        schema_version = _require_int(
            payload.get("schema_version"), "nozzle_profile.schema_version"
        )
        if schema_version != RESOURCE_SCHEMA_VERSION:
            raise ValueError(f"unsupported nozzle profile schema {schema_version}")
        raw_profile = payload.get("outer_profile_rz_mm")
        if not isinstance(raw_profile, Sequence) or isinstance(
            raw_profile, (str, bytes, bytearray)
        ):
            raise TypeError("nozzle_profile.outer_profile_rz_mm must be an array")
        points: list[tuple[float, float]] = []
        for index, raw_point in enumerate(raw_profile):
            if (
                not isinstance(raw_point, Sequence)
                or isinstance(raw_point, (str, bytes, bytearray))
                or len(raw_point) != 2
            ):
                raise TypeError(
                    f"nozzle_profile.outer_profile_rz_mm[{index}] must have two values"
                )
            points.append(
                (
                    _require_float(raw_point[0], f"outer_profile_rz_mm[{index}][0]"),
                    _require_float(raw_point[1], f"outer_profile_rz_mm[{index}][1]"),
                )
            )
        source_payload = payload.get("source")
        return cls(
            resource_id=_require_string(payload.get("resource_id"), "resource_id"),
            display_name=_require_string(payload.get("display_name"), "display_name"),
            profile_version=_require_int(
                payload.get("profile_version"), "profile_version"
            ),
            orifice_diameter_mm=_require_float(
                payload.get("orifice_diameter_mm"), "orifice_diameter_mm"
            ),
            filament_diameter_mm=_require_float(
                payload.get("filament_diameter_mm"), "filament_diameter_mm"
            ),
            interface=_optional_string(payload.get("interface"), "interface"),
            length_mm=_optional_float(payload.get("length_mm"), "length_mm"),
            construction_material=_optional_string(
                payload.get("construction_material"), "construction_material"
            ),
            flow_category=_optional_string(
                payload.get("flow_category"), "flow_category"
            ),
            temperature_limit_c=_optional_float(
                payload.get("temperature_limit_c"), "temperature_limit_c"
            ),
            wear_resistance_rating=_optional_string(
                payload.get("wear_resistance_rating"), "wear_resistance_rating"
            ),
            outer_profile_rz_mm=tuple(points),
            source=(
                None
                if source_payload is None
                else SourceReference.from_json(
                    _require_mapping(source_payload, "source")
                )
            ),
            is_builtin=parse_json_bool(
                payload,
                "is_builtin",
                default=False,
                field_name="nozzle_profile.is_builtin",
            ),
        )


@dataclass(frozen=True, slots=True)
class MaterialProfile:
    """FFF/FDM filament identity with pinned generic source recommendations."""

    resource_id: str
    display_name: str
    brand: str
    material: str
    guid: str
    upstream_version: int
    filament_diameter_mm: float
    density_g_cm3: float
    recommendations: MaterialRecommendations
    source: SourceReference
    profile_version: int = 1
    form: str = "filament"
    process: str = "FFF/FDM"
    review_required: bool = True
    review_confirmed: bool = False
    is_builtin: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "review_required",
            "review_confirmed",
            "is_builtin",
        ):
            object.__setattr__(
                self,
                field_name,
                require_bool(getattr(self, field_name), field_name=field_name),
            )

    def validate(self) -> tuple[ResourceValidationIssue, ...]:
        issues: list[ResourceValidationIssue] = []
        for field_name, value in (
            ("resource_id", self.resource_id),
            ("display_name", self.display_name),
            ("brand", self.brand),
            ("material", self.material),
            ("guid", self.guid),
            ("form", self.form),
            ("process", self.process),
        ):
            if not isinstance(value, str) or not value.strip():
                issues.append(
                    ResourceValidationIssue(
                        f"material.{field_name}_missing", _ERROR, field_name
                    )
                )
        if (
            not isinstance(self.profile_version, int)
            or isinstance(self.profile_version, bool)
            or self.profile_version < 1
        ):
            issues.append(
                ResourceValidationIssue(
                    "resource.version_invalid", _ERROR, "profile_version"
                )
            )
        if (
            not isinstance(self.upstream_version, int)
            or isinstance(self.upstream_version, bool)
            or self.upstream_version < 1
        ):
            issues.append(
                ResourceValidationIssue(
                    "material.upstream_version_invalid", _ERROR, "upstream_version"
                )
            )
        if not _is_positive_number(self.filament_diameter_mm):
            issues.append(
                ResourceValidationIssue(
                    "material.filament_diameter_invalid",
                    _ERROR,
                    "filament_diameter_mm",
                )
            )
        if not _is_positive_number(self.density_g_cm3):
            issues.append(
                ResourceValidationIssue(
                    "material.density_invalid", _ERROR, "density_g_cm3"
                )
            )
        issues.extend(self.recommendations.validate())
        issues.extend(self.source.validate())
        if self.review_required and not self.review_confirmed:
            issues.append(
                ResourceValidationIssue(
                    "material.review_required", _ERROR, "review_confirmed"
                )
            )
        return tuple(issues)

    @property
    def readiness_blockers(self) -> tuple[ResourceValidationIssue, ...]:
        return tuple(issue for issue in self.validate() if issue.severity == _ERROR)

    @property
    def is_ready(self) -> bool:
        return not self.readiness_blockers

    def reviewed_copy(
        self,
        resource_id: str,
        *,
        display_name: str | None = None,
    ) -> "MaterialProfile":
        """Create a reviewed user resource while leaving the template intact."""

        if not resource_id.strip():
            raise ValueError("resource_id cannot be blank")
        return replace(
            self,
            resource_id=resource_id,
            display_name=self.display_name if display_name is None else display_name,
            profile_version=1,
            review_confirmed=True,
            is_builtin=False,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": RESOURCE_SCHEMA_VERSION,
            "resource_id": self.resource_id,
            "display_name": self.display_name,
            "profile_version": self.profile_version,
            "brand": self.brand,
            "material": self.material,
            "guid": self.guid,
            "upstream_version": self.upstream_version,
            "filament_diameter_mm": float(self.filament_diameter_mm),
            "density_g_cm3": float(self.density_g_cm3),
            "form": self.form,
            "process": self.process,
            "recommendations": self.recommendations.to_json(),
            "source": self.source.to_json(),
            "review_required": self.review_required,
            "review_confirmed": self.review_confirmed,
            "is_builtin": self.is_builtin,
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "MaterialProfile":
        payload = _require_mapping(value, "material_profile")
        schema_version = _require_int(
            payload.get("schema_version"), "material_profile.schema_version"
        )
        if schema_version != RESOURCE_SCHEMA_VERSION:
            raise ValueError(f"unsupported material profile schema {schema_version}")
        return cls(
            resource_id=_require_string(payload.get("resource_id"), "resource_id"),
            display_name=_require_string(payload.get("display_name"), "display_name"),
            profile_version=_require_int(
                payload.get("profile_version"), "profile_version"
            ),
            brand=_require_string(payload.get("brand"), "brand"),
            material=_require_string(payload.get("material"), "material"),
            guid=_require_string(payload.get("guid"), "guid"),
            upstream_version=_require_int(
                payload.get("upstream_version"), "upstream_version"
            ),
            filament_diameter_mm=_require_float(
                payload.get("filament_diameter_mm"), "filament_diameter_mm"
            ),
            density_g_cm3=_require_float(payload.get("density_g_cm3"), "density_g_cm3"),
            form=_require_string(payload.get("form"), "form"),
            process=_require_string(payload.get("process"), "process"),
            recommendations=MaterialRecommendations.from_json(
                _require_mapping(payload.get("recommendations"), "recommendations")
            ),
            source=SourceReference.from_json(
                _require_mapping(payload.get("source"), "source")
            ),
            review_required=parse_json_bool(
                payload,
                "review_required",
                default=True,
                field_name="material_profile.review_required",
            ),
            review_confirmed=parse_json_bool(
                payload,
                "review_confirmed",
                default=False,
                field_name="material_profile.review_confirmed",
            ),
            is_builtin=parse_json_bool(
                payload,
                "is_builtin",
                default=False,
                field_name="material_profile.is_builtin",
            ),
        )


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    """Deeply immutable, self-verifying copy of a project resource."""

    resource_type: str
    resource_id: str
    profile_version: int
    payload: Mapping[str, Any]
    content_hash: str
    schema_version: int = RESOURCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.resource_type, str) or not _RESOURCE_TYPE_RE.fullmatch(
            self.resource_type
        ):
            raise ValueError(
                "resource_type must use lowercase letters, digits, and underscores"
            )
        if not isinstance(self.resource_id, str) or not self.resource_id.strip():
            raise ValueError("resource_id cannot be blank")
        if (
            not isinstance(self.profile_version, int)
            or isinstance(self.profile_version, bool)
            or self.profile_version < 1
        ):
            raise ValueError("profile_version must be a positive integer")
        if self.schema_version != RESOURCE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported resource snapshot schema {self.schema_version}"
            )
        if not isinstance(self.content_hash, str) or not _SHA256_RE.fullmatch(
            self.content_hash.lower()
        ):
            raise ValueError("content_hash must be a lowercase SHA-256 value")
        frozen_payload = _freeze_json(_require_mapping(self.payload, "payload"))
        object.__setattr__(self, "payload", frozen_payload)
        object.__setattr__(self, "content_hash", self.content_hash.lower())
        actual_hash = canonical_content_hash(
            _snapshot_hash_content(
                self.resource_type,
                self.resource_id,
                self.profile_version,
                frozen_payload,
            )
        )
        if not hmac.compare_digest(actual_hash, self.content_hash):
            raise ResourceIntegrityError(
                f"resource snapshot hash mismatch: expected {self.content_hash}, "
                f"calculated {actual_hash}"
            )
        embedded_id, embedded_version = _snapshot_identity(frozen_payload)
        if embedded_id != self.resource_id:
            raise ResourceIntegrityError(
                "snapshot resource_id differs from its payload"
            )
        if embedded_version != self.profile_version:
            raise ResourceIntegrityError(
                "snapshot profile_version differs from its payload"
            )

    @classmethod
    def capture(cls, resource_type: str, profile: Any) -> "ResourceSnapshot":
        """Freeze any profile exposing ``to_json`` and standard identity fields."""

        if not hasattr(profile, "to_json"):
            raise TypeError("profile must provide to_json()")
        payload = _normalise_json(profile.to_json())
        payload_mapping = _require_mapping(payload, "profile payload")
        resource_id, profile_version = _snapshot_identity(payload_mapping)
        hash_content = _snapshot_hash_content(
            resource_type,
            resource_id,
            profile_version,
            payload_mapping,
        )
        return cls(
            resource_type=resource_type,
            resource_id=resource_id,
            profile_version=profile_version,
            payload=payload_mapping,
            content_hash=canonical_content_hash(hash_content),
        )

    def verify(self) -> bool:
        return hmac.compare_digest(
            self.content_hash,
            canonical_content_hash(
                _snapshot_hash_content(
                    self.resource_type,
                    self.resource_id,
                    self.profile_version,
                    self.payload,
                )
            ),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "profile_version": self.profile_version,
            "payload": _thaw_json(self.payload),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "ResourceSnapshot":
        payload = _require_mapping(value, "resource_snapshot")
        return cls(
            schema_version=_require_int(
                payload.get("schema_version"), "resource_snapshot.schema_version"
            ),
            resource_type=_require_string(
                payload.get("resource_type"), "resource_snapshot.resource_type"
            ),
            resource_id=_require_string(
                payload.get("resource_id"), "resource_snapshot.resource_id"
            ),
            profile_version=_require_int(
                payload.get("profile_version"), "resource_snapshot.profile_version"
            ),
            payload=_require_mapping(
                payload.get("payload"), "resource_snapshot.payload"
            ),
            content_hash=_require_string(
                payload.get("content_hash"), "resource_snapshot.content_hash"
            ),
        )

    def as_nozzle_profile(self) -> NozzleProfile:
        if self.resource_type != "nozzle":
            raise TypeError(f"snapshot contains {self.resource_type}, not nozzle")
        return NozzleProfile.from_json(self.payload)

    def as_material_profile(self) -> MaterialProfile:
        if self.resource_type != "material":
            raise TypeError(f"snapshot contains {self.resource_type}, not material")
        return MaterialProfile.from_json(self.payload)


def _builtin_nozzle(diameter_mm: float) -> NozzleProfile:
    identity = f"urn:five-axis-slicer:nozzle-identity:{diameter_mm:.1f}mm"
    return NozzleProfile(
        resource_id=str(uuid5(NAMESPACE_URL, identity)),
        display_name=f"Generic {diameter_mm:.1f} mm nozzle identity",
        orifice_diameter_mm=diameter_mm,
        filament_diameter_mm=1.75,
        interface=None,
        length_mm=None,
        construction_material=None,
        flow_category=None,
        temperature_limit_c=None,
        wear_resistance_rating=None,
        outer_profile_rz_mm=(),
        source=None,
        is_builtin=True,
    )


GENERIC_NOZZLE_0_4 = _builtin_nozzle(0.4)
GENERIC_NOZZLE_0_6 = _builtin_nozzle(0.6)
GENERIC_NOZZLE_0_8 = _builtin_nozzle(0.8)

BUILTIN_NOZZLE_PROFILES: Mapping[str, NozzleProfile] = MappingProxyType(
    {
        "0.4": GENERIC_NOZZLE_0_4,
        "0.6": GENERIC_NOZZLE_0_6,
        "0.8": GENERIC_NOZZLE_0_8,
    }
)


def _cura_source(file_name: str, title: str, sha256: str) -> SourceReference:
    return SourceReference(
        title=title,
        url=(
            "https://github.com/Ultimaker/fdm_materials/blob/"
            f"{CURA_FDM_MATERIALS_COMMIT}/{file_name}"
        ),
        revision=CURA_FDM_MATERIALS_COMMIT,
        file_path=file_name,
        sha256=sha256,
    )


GENERIC_PLA_175 = MaterialProfile(
    resource_id="0ff92885-617b-4144-a03c-9989872454bc",
    display_name="Cura Generic PLA 1.75 mm",
    brand="Generic",
    material="PLA",
    guid="0ff92885-617b-4144-a03c-9989872454bc",
    upstream_version=13,
    filament_diameter_mm=1.75,
    density_g_cm3=1.24,
    recommendations=MaterialRecommendations(200.0, 60.0),
    source=_cura_source(
        "generic_pla_175.xml.fdm_material",
        "Ultimaker fdm_materials: Generic PLA 1.75 mm",
        "5bc7c562e14cb10c15323bca26f1afddedcf6e18166c92adf4d638611907a4be",
    ),
    review_required=True,
    review_confirmed=False,
    is_builtin=True,
)

GENERIC_PETG_175 = MaterialProfile(
    resource_id="69386c85-5b6c-421a-bec5-aeb1fb33f060",
    display_name="Cura Generic PETG 1.75 mm",
    brand="Generic",
    material="PETG",
    guid="69386c85-5b6c-421a-bec5-aeb1fb33f060",
    upstream_version=7,
    filament_diameter_mm=1.75,
    density_g_cm3=1.27,
    recommendations=MaterialRecommendations(215.0, 70.0),
    source=_cura_source(
        "generic_petg_175.xml.fdm_material",
        "Ultimaker fdm_materials: Generic PETG 1.75 mm",
        "d1e41783828696f374f6267bc9f07b8336a0ceedfafbf32dcbaf930d5595c0e3",
    ),
    review_required=True,
    review_confirmed=False,
    is_builtin=True,
)

GENERIC_ABS_175 = MaterialProfile(
    resource_id="2780b345-577b-4a24-a2c5-12e6aad3e690",
    display_name="Cura Generic ABS 1.75 mm",
    brand="Generic",
    material="ABS",
    guid="2780b345-577b-4a24-a2c5-12e6aad3e690",
    upstream_version=12,
    filament_diameter_mm=1.75,
    density_g_cm3=1.1,
    recommendations=MaterialRecommendations(230.0, 80.0),
    source=_cura_source(
        "generic_abs_175.xml.fdm_material",
        "Ultimaker fdm_materials: Generic ABS 1.75 mm",
        "6687016b42e144e8ae717cf87024f383815c61b3ae300ac1adb6045093c9d1b4",
    ),
    review_required=True,
    review_confirmed=False,
    is_builtin=True,
)

BUILTIN_MATERIAL_PROFILES: Mapping[str, MaterialProfile] = MappingProxyType(
    {
        "PLA": GENERIC_PLA_175,
        "PETG": GENERIC_PETG_175,
        "ABS": GENERIC_ABS_175,
    }
)


def builtin_nozzle_profiles() -> tuple[NozzleProfile, ...]:
    return tuple(BUILTIN_NOZZLE_PROFILES.values())


def builtin_material_profiles() -> tuple[MaterialProfile, ...]:
    return tuple(BUILTIN_MATERIAL_PROFILES.values())


def get_builtin_nozzle_profile(diameter_mm: float) -> NozzleProfile:
    if isinstance(diameter_mm, bool) or not isinstance(diameter_mm, (int, float)):
        raise TypeError("diameter_mm must be a number")
    for profile in BUILTIN_NOZZLE_PROFILES.values():
        if math.isclose(
            profile.orifice_diameter_mm,
            float(diameter_mm),
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            return profile
    raise KeyError(f"no built-in nozzle identity for {diameter_mm!r} mm")


def get_builtin_material_profile(material: str) -> MaterialProfile:
    if not isinstance(material, str):
        raise TypeError("material must be a string")
    key = material.strip().upper()
    try:
        return BUILTIN_MATERIAL_PROFILES[key]
    except KeyError as exc:
        raise KeyError(f"no built-in material profile for {material!r}") from exc


__all__ = [
    "BUILTIN_MATERIAL_PROFILES",
    "BUILTIN_NOZZLE_PROFILES",
    "CURA_FDM_MATERIALS_COMMIT",
    "GENERIC_ABS_175",
    "GENERIC_NOZZLE_0_4",
    "GENERIC_NOZZLE_0_6",
    "GENERIC_NOZZLE_0_8",
    "GENERIC_PETG_175",
    "GENERIC_PLA_175",
    "MaterialProfile",
    "MaterialRecommendations",
    "NozzleProfile",
    "RESOURCE_SCHEMA_VERSION",
    "ResourceIntegrityError",
    "ResourceSnapshot",
    "ResourceValidationIssue",
    "SourceReference",
    "builtin_material_profiles",
    "builtin_nozzle_profiles",
    "canonical_content_hash",
    "canonical_json_bytes",
    "get_builtin_material_profile",
    "get_builtin_nozzle_profile",
]
