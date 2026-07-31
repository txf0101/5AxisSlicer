"""Track the live portable Setup document beside the project authority.

``project.json`` owns Part and source-model identity.  This module owns the
compare-before-replace YAML attachment, including the saved-project baseline
used to distinguish recoverable work from a true two-sided divergence.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from .manufacturing.setup import IssueSeverity, ValidationIssue
from .setup_config import (
    CONFIG_FILENAME,
    SetupConfig,
    SetupConfigConflictError,
    atomic_write_setup_config,
    dump_setup_config,
    export_setup_config,
    read_setup_config_snapshot,
    setup_config_fingerprint,
)
from .tube_controller import TubeSetupController

Comparison = Literal["missing", "equal", "recoverable", "project_newer", "diverged"]
Resolution = Literal["project", "yaml"]

_GEOMETRY_REVIEW_CODE = "CONFIG_GEOMETRY_REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class SetupConfigInspection:
    """One side-effect-free comparison made before publishing a project."""

    path: Path
    comparison: Comparison
    project_hash: str
    config_hash: str | None
    base_hash: str | None
    differences: tuple[str, ...]
    config: SetupConfig | None = None
    text: str | None = None
    fingerprint: str | None = None

    @property
    def needs_resolution(self) -> bool:
        return self.comparison in {"recoverable", "project_newer", "diverged"}


class SetupConfigStore:
    """Maintain one YAML attachment and reject unseen external replacements."""

    def __init__(self) -> None:
        self._project_directory: Path | None = None
        self._path: Path | None = None
        self._config: SetupConfig | None = None
        self._text: str | None = None
        self._fingerprint: str | None = None
        self._base_project_hash: str | None = None
        self._suspended = False

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def suspended(self) -> bool:
        return self._suspended

    def state_json(self) -> dict[str, Any]:
        if self._path is None:
            status = "memory"
        elif self._suspended:
            status = "diverged"
        elif self._fingerprint is None:
            status = "pending"
        else:
            status = "synced"
        return {
            "status": status,
            "path": None if self._path is None else str(self._path),
            "fingerprint": self._fingerprint,
            "base_project_setup_sha256": self._base_project_hash,
        }

    def reset_memory(self, controller: TubeSetupController, revision: int = 1) -> None:
        """Start an unsaved session without touching the previous project."""

        self._project_directory = None
        self._path = None
        self._config = export_setup_config(
            controller.setup,
            controller.operations,
            revision=max(1, revision),
        )
        self._text = dump_setup_config(self._config)
        self._fingerprint = None
        self._base_project_hash = None
        self._suspended = False

    def inspect_project(
        self,
        controller: TubeSetupController,
        project_directory: str | Path,
    ) -> SetupConfigInspection:
        """Classify YAML against the loaded project without changing either."""

        directory = Path(project_directory).expanduser().resolve()
        path = directory / CONFIG_FILENAME
        project_config = export_setup_config(controller.setup, controller.operations, revision=1)
        project_hash = project_config.semantic_sha256
        if not path.exists():
            return SetupConfigInspection(path, "missing", project_hash, None, None, ())

        config, text, fingerprint = _read_config_path(path)
        config_hash = config.semantic_sha256
        base_hash = config.base_project_setup_sha256
        differences = semantic_differences(project_config, config)
        if config_hash == project_hash:
            comparison: Comparison = "equal"
        elif base_hash == project_hash:
            comparison = "recoverable"
        elif base_hash == config_hash:
            comparison = "project_newer"
        else:
            comparison = "diverged"
        return SetupConfigInspection(
            path,
            comparison,
            project_hash,
            config_hash,
            base_hash,
            differences,
            config,
            text,
            fingerprint,
        )

    def attach_project(
        self,
        controller: TubeSetupController,
        inspection: SetupConfigInspection,
        resolution: Resolution,
    ) -> None:
        """Attach a resolved candidate controller after the user choice."""

        if resolution not in {"project", "yaml"}:
            raise ValueError("resolution must be 'project' or 'yaml'")
        if resolution == "yaml":
            if inspection.config is None:
                raise ValueError("the project has no YAML configuration to apply")
            apply_setup_config(controller, inspection.config)

        self._project_directory = inspection.path.parent
        self._path = inspection.path
        self._fingerprint = inspection.fingerprint
        self._text = inspection.text
        self._suspended = False
        if resolution == "yaml":
            self._config = inspection.config
            self._base_project_hash = inspection.base_hash
            return

        self._base_project_hash = inspection.project_hash
        self._config = export_setup_config(
            controller.setup,
            controller.operations,
            revision=1,
            base_project_setup_sha256=inspection.project_hash,
        )
        if inspection.config is not None and inspection.comparison != "equal":
            self._publish(self._config, preserve_text=inspection.text)

    def persist_candidate(
        self,
        candidate: TubeSetupController,
        revision: int,
        project_only: bool,
    ) -> bool:
        """Persist portable candidate state before the command publishes it."""

        if project_only:
            return self._path is not None and self._fingerprint is not None
        proposed = export_setup_config(
            candidate.setup,
            candidate.operations,
            revision=max(1, revision),
            base_project_setup_sha256=self._base_project_hash,
        )
        if self._path is None:
            self._config = proposed
            self._text = dump_setup_config(proposed, existing_text=self._text)
            return False
        if self._suspended:
            raise SetupConfigConflictError("automatic YAML writes are paused")
        self._publish(proposed, preserve_text=self._text)
        return True

    def project_saved(
        self,
        controller: TubeSetupController,
        project_directory: str | Path,
        revision: int,
    ) -> Path:
        """Write the saved-project baseline after ``project.json`` succeeds."""

        directory = Path(project_directory).expanduser().resolve()
        path = directory / CONFIG_FILENAME
        same_attachment = self._path == path
        if not same_attachment:
            self._project_directory = directory
            self._path = path
            self._text = None
            self._fingerprint = None
            self._suspended = False
        semantic = export_setup_config(controller.setup, controller.operations, revision=1)
        self._base_project_hash = semantic.semantic_sha256
        proposed = export_setup_config(
            controller.setup,
            controller.operations,
            revision=max(1, revision),
            base_project_setup_sha256=self._base_project_hash,
        )
        self._publish(proposed, preserve_text=self._text)
        return path

    def accept_external(self, expected_fingerprint: str) -> SetupConfig:
        """Adopt the current work file after an explicit load-and-preview choice."""

        if self._path is None or not self._path.is_file():
            raise FileNotFoundError("no attached YAML configuration exists")
        config, text, fingerprint = _read_config_path(self._path)
        if not hmac.compare_digest(fingerprint, expected_fingerprint):
            raise SetupConfigConflictError("YAML changed after preview")
        self._config = config
        self._text = text
        self._fingerprint = fingerprint
        self._base_project_hash = config.base_project_setup_sha256
        self._suspended = False
        return config

    def preview_external(self) -> tuple[SetupConfig, str]:
        """Read the current work file without resuming automatic writes."""

        if self._path is None or not self._path.is_file():
            raise FileNotFoundError("no attached YAML configuration exists")
        config, _, fingerprint = _read_config_path(self._path)
        return config, fingerprint

    def pause_writes(self) -> None:
        if self._path is not None:
            self._suspended = True

    def overwrite_external(self, controller: TubeSetupController, revision: int) -> Path:
        """Replace an externally changed work file after explicit confirmation."""

        if self._path is None:
            raise FileNotFoundError("no attached YAML configuration exists")
        self._fingerprint = setup_config_fingerprint(self._path)
        self._text = _valid_existing_text(self._path)
        self._suspended = False
        proposed = export_setup_config(
            controller.setup,
            controller.operations,
            revision=max(1, revision),
            base_project_setup_sha256=self._base_project_hash,
        )
        self._publish(proposed, preserve_text=self._text)
        return self._path

    def _publish(self, config: SetupConfig, *, preserve_text: str | None) -> None:
        assert self._path is not None
        text = dump_setup_config(config, existing_text=preserve_text)
        try:
            fingerprint = atomic_write_setup_config(
                self._path,
                text,
                expected_fingerprint=self._fingerprint,
                expect_missing=self._fingerprint is None,
            )
        except SetupConfigConflictError:
            self._suspended = True
            raise
        self._config = config
        self._text = text
        self._fingerprint = fingerprint


def apply_setup_config(controller: TubeSetupController, config: SetupConfig) -> None:
    """Apply portable values while retaining project-only Part and identities."""

    previous_issues = controller.setup.issues
    operation_id = _new_operation_id(controller)
    setup, operations = config.apply_to_domain(
        controller.setup,
        controller.operations,
        new_operation_id=operation_id,
    )
    retained = tuple(issue for issue in previous_issues if issue.code != _GEOMETRY_REVIEW_CODE)
    if config.geometry_review_required:
        retained += (
            ValidationIssue(
                _GEOMETRY_REVIEW_CODE,
                IssueSeverity.WARNING,
                setup.setup_id,
                {"source": CONFIG_FILENAME},
            ),
        )
    checkpoint = controller.command_checkpoint()
    controller.restore_command_checkpoint(
        replace(
            checkpoint,
            setup=replace(setup, issues=retained),
            operations=operations,
            drafts={},
            modified=True,
        )
    )


def semantic_differences(left: SetupConfig, right: SetupConfig) -> tuple[str, ...]:
    """Return stable field paths for a compact recovery preview."""

    left_document = left.to_document()
    right_document = right.to_document()
    left_document.pop("metadata", None)
    right_document.pop("metadata", None)
    paths: list[str] = []
    _collect_differences(left_document, right_document, "$", paths)
    return tuple(paths)


def _collect_differences(left: Any, right: Any, path: str, output: list[str]) -> None:
    if type(left) is not type(right):
        output.append(path)
        return
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                output.append(f"{path}.{key}")
            else:
                _collect_differences(left[key], right[key], f"{path}.{key}", output)
        return
    if isinstance(left, list):
        if len(left) != len(right):
            output.append(path)
            return
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            _collect_differences(left_item, right_item, f"{path}[{index}]", output)
        return
    if left != right:
        output.append(path)


def _new_operation_id(controller: TubeSetupController) -> str:
    known = {item.operation_id for item in controller.operations}
    index = 1
    while f"tube-operation-{index}" in known:
        index += 1
    return f"tube-operation-{index}"


def _valid_existing_text(path: Path) -> str | None:
    try:
        _, text, _ = _read_config_path(path)
    except (OSError, UnicodeError, ValueError):
        return None
    return text


def _read_config_path(path: Path) -> tuple[SetupConfig, str, str]:
    """Read config, text, and fingerprint from one bounded descriptor."""

    return read_setup_config_snapshot(path)


__all__ = [
    "SetupConfigInspection",
    "SetupConfigStore",
    "apply_setup_config",
    "semantic_differences",
]
