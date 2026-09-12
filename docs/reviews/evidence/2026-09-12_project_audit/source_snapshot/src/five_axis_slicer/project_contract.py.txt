"""Stable project persistence errors shared by readers and asset verifiers."""

from __future__ import annotations


class ProjectError(RuntimeError):
    """Base class for project persistence failures."""


class ProjectFormatError(ProjectError):
    """The project JSON structure or a persisted domain object is invalid."""


class ProjectIntegrityError(ProjectError):
    """An embedded file or immutable resource differs from its saved hash."""


class UnsupportedProjectVersionError(ProjectFormatError):
    """The project was written by a newer unsupported schema."""


class ProjectLoadCancelled(ProjectError):
    """A cooperative project verification or embedded STEP load was cancelled."""


__all__ = [
    "ProjectError",
    "ProjectFormatError",
    "ProjectIntegrityError",
    "ProjectLoadCancelled",
    "UnsupportedProjectVersionError",
]
