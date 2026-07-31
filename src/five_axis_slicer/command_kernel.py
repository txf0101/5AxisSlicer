"""Qt-free command transactions shared by GUI, scripts, and automation.

Providers mutate an isolated controller fork.  Persistence completes before
the fork is published, so failed validation or I/O leaves every live consumer
on the previous checkpoint.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
import logging
from threading import RLock
from types import MappingProxyType
from typing import Any, Literal, Protocol

from .tube_controller_state import TubeControllerCheckpoint

CommandKind = Literal["query", "mutation", "undo", "redo"]

LOGGER = logging.getLogger(__name__)


class CommandController(Protocol):
    @property
    def has_drafts(self) -> bool: ...

    @property
    def coordinates_valid(self) -> bool: ...

    @property
    def setup_ready(self) -> bool: ...

    def fork(self) -> CommandController: ...

    def publish_from(self, candidate: CommandController) -> None: ...

    def command_checkpoint(self) -> TubeControllerCheckpoint: ...

    def command_applied_token(self) -> tuple[object, ...]: ...

    def restore_command_checkpoint(self, checkpoint: TubeControllerCheckpoint) -> None: ...

    def validation_report(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class CommandInvocation:
    """One provider call plus concurrency and audit metadata."""

    name: str
    args: tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=dict)
    origin: str = "api"
    command_id: str | None = None
    expected_revision: int | None = None

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        origin = str(self.origin).strip()
        if not name:
            raise ValueError("command name must not be empty")
        if not origin:
            raise ValueError("command origin must not be empty")
        kwargs = dict(self.kwargs)
        if any(not isinstance(key, str) for key in kwargs):
            raise TypeError("command keyword names must be strings")
        revision = self.expected_revision
        if revision is not None and (
            isinstance(revision, bool) or not isinstance(revision, int) or revision < 0
        ):
            raise ValueError("expected_revision must be a non-negative integer")
        command_id = None if self.command_id is None else str(self.command_id).strip()
        if command_id == "":
            raise ValueError("command_id must not be empty")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "args", tuple(self.args))
        object.__setattr__(self, "kwargs", MappingProxyType(kwargs))
        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "command_id", command_id)
        object.__setattr__(self, "expected_revision", revision)


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """Provider-owned payload and publication policy for one invocation."""

    payload: Any = None
    affected_nodes: tuple[str, ...] = ()
    changed_fields: tuple[str, ...] = ()
    project_only: bool = False
    record_history: bool = True


@dataclass(frozen=True, slots=True)
class CommandResult:
    command: str
    revision: int
    changed: bool
    payload: Any = None
    affected_nodes: tuple[str, ...] = ()
    changed_fields: tuple[str, ...] = ()
    project_only: bool = False
    coordinates_valid: bool = False
    setup_ready: bool = False
    issue_codes: tuple[str, ...] = ()
    origin: str = "api"
    command_id: str | None = None
    config_synced: bool | None = None


class CommandError(RuntimeError):
    """Stable failure returned at every command entry point."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        command: str | None = None,
        command_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = str(code)
        self.command = command
        self.command_id = command_id
        self.details = MappingProxyType(dict(details or {}))

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "command": self.command,
            "command_id": self.command_id,
            "details": dict(self.details),
        }


class CommandProvider(Protocol):
    def canonical_name(self, name: str) -> str: ...

    def kind(self, name: str) -> CommandKind: ...

    def allows_drafts(self, name: str) -> bool: ...

    def invoke(
        self,
        controller: CommandController,
        invocation: CommandInvocation,
    ) -> CommandOutcome: ...


PersistCallback = Callable[[CommandController, int, bool], bool | None]
PublishCallback = Callable[[CommandResult], None]
BusyCallback = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class _HistoryEntry:
    before: TubeControllerCheckpoint
    after: TubeControllerCheckpoint
    affected_nodes: tuple[str, ...]
    changed_fields: tuple[str, ...]
    project_only: bool


class CommandKernel:
    """Serial command coordinator with bounded undo and monotonic revisions."""

    def __init__(
        self,
        controller: CommandController,
        provider: CommandProvider,
        *,
        persist: PersistCallback | None = None,
        on_publish: PublishCallback | None = None,
        is_busy: BusyCallback | None = None,
        history_limit: int = 100,
    ) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be positive")
        self._controller = controller
        self._provider = provider
        self._persist = persist
        self._on_publish = on_publish
        self._is_busy = is_busy or (lambda: False)
        self._history_limit = int(history_limit)
        self._undo: list[_HistoryEntry] = []
        self._redo: list[_HistoryEntry] = []
        self._revision = 0
        self._lock = RLock()
        self._bound_token = controller.command_applied_token()

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def controller(self) -> CommandController:
        return self._controller

    def is_bound_to(self, controller: CommandController) -> bool:
        return self._controller is controller

    def rebind(self, controller: CommandController, *, clear_history: bool = True) -> int:
        """Attach a new project/STEP context and invalidate stale revisions."""

        with self._lock:
            self._controller = controller
            if clear_history:
                self._undo.clear()
                self._redo.clear()
            self._revision += 1
            self._bound_token = controller.command_applied_token()
            return self._revision

    def synchronize_external_state(self, *, clear_history: bool = True) -> bool:
        """Detect direct applied-state edits made outside this kernel."""

        with self._lock:
            token = self._controller.command_applied_token()
            if token == self._bound_token:
                return False
            if clear_history:
                self._undo.clear()
                self._redo.clear()
            self._bound_token = token
            self._revision += 1
            return True

    def reset_external_state(self, *, clear_history: bool = True) -> int:
        """Force a new concurrency epoch after an external context mutation."""

        with self._lock:
            if clear_history:
                self._undo.clear()
                self._redo.clear()
            self._bound_token = self._controller.command_applied_token()
            self._revision += 1
            return self._revision

    def execute(self, invocation: CommandInvocation) -> CommandResult:
        with self._lock:
            self.synchronize_external_state()
            current = self._canonical(invocation)
            self._check_revision(current.expected_revision, current)
            kind = self._provider.kind(current.name)
            if kind == "query":
                outcome = self._invoke(self._controller, current)
                return self._result(current, outcome, changed=False)
            self._guard_mutation(current)
            if kind in {"undo", "redo"}:
                return self._history_move(current, redo=kind == "redo")
            return self._execute_mutation(current)

    def transaction(
        self,
        invocations: Sequence[CommandInvocation],
        *,
        origin: str = "api",
        command_id: str | None = None,
        expected_revision: int | None = None,
    ) -> CommandResult:
        """Execute modifying calls on one candidate and publish once."""

        with self._lock:
            self.synchronize_external_state()
            calls = tuple(self._canonical(item) for item in invocations)
            marker = CommandInvocation(
                "transaction",
                origin=origin,
                command_id=command_id,
                expected_revision=expected_revision,
            )
            if not calls:
                raise self._error("E_ARGUMENT_INVALID", "transaction requires commands", marker)
            self._check_revision(marker.expected_revision, marker)
            for call in calls:
                self._check_revision(call.expected_revision, call)
                if self._provider.kind(call.name) != "mutation":
                    raise self._error(
                        "E_DOMAIN_VALIDATION",
                        "transactions accept modifying commands only",
                        call,
                    )
            self._guard_mutation(
                marker, allow_drafts=all(self._provider.allows_drafts(c.name) for c in calls)
            )
            return self._execute_transaction(marker, calls)

    def clear_history(self) -> None:
        with self._lock:
            self._undo.clear()
            self._redo.clear()

    def _canonical(self, invocation: CommandInvocation) -> CommandInvocation:
        try:
            name = self._provider.canonical_name(invocation.name)
        except CommandError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise self._error("E_COMMAND_UNKNOWN", str(exc), invocation) from exc
        return replace(invocation, name=name)

    def _check_revision(
        self,
        expected: int | None,
        invocation: CommandInvocation,
    ) -> None:
        if expected is not None and expected != self._revision:
            raise self._error(
                "E_REVISION_CONFLICT",
                f"expected revision {expected}, current revision is {self._revision}",
                invocation,
                expected=expected,
                current=self._revision,
            )

    def _guard_mutation(
        self,
        invocation: CommandInvocation,
        *,
        allow_drafts: bool | None = None,
    ) -> None:
        if self._is_busy():
            raise self._error("E_LOAD_BUSY", "a background load is active", invocation)
        accepts = (
            self._provider.allows_drafts(invocation.name) if allow_drafts is None else allow_drafts
        )
        if self._controller.has_drafts and not accepts:
            raise self._error("E_DRAFT_ACTIVE", "unapplied Setup drafts are active", invocation)

    def _execute_mutation(self, invocation: CommandInvocation) -> CommandResult:
        before = self._controller.command_checkpoint()
        candidate = self._controller.fork()
        outcome = self._invoke(candidate, invocation)
        after = candidate.command_checkpoint()
        if after == before:
            return self._result(invocation, outcome, changed=False)
        return self._commit(invocation, candidate, before, after, outcome)

    def _execute_transaction(
        self,
        marker: CommandInvocation,
        calls: tuple[CommandInvocation, ...],
    ) -> CommandResult:
        before = self._controller.command_checkpoint()
        candidate = self._controller.fork()
        outcomes = tuple(self._invoke(candidate, call) for call in calls)
        after = candidate.command_checkpoint()
        outcome = CommandOutcome(
            payload=tuple(item.payload for item in outcomes),
            affected_nodes=_unique(node for item in outcomes for node in item.affected_nodes),
            changed_fields=_unique(field for item in outcomes for field in item.changed_fields),
            project_only=all(item.project_only for item in outcomes),
            record_history=any(item.record_history for item in outcomes),
        )
        if after == before:
            return self._result(marker, outcome, changed=False)
        return self._commit(marker, candidate, before, after, outcome)

    def _commit(
        self,
        invocation: CommandInvocation,
        candidate: CommandController,
        before: TubeControllerCheckpoint,
        after: TubeControllerCheckpoint,
        outcome: CommandOutcome,
    ) -> CommandResult:
        report = candidate.validation_report()
        next_revision = self._revision + 1
        synced = self._persist_candidate(candidate, next_revision, outcome.project_only, invocation)
        self._controller.publish_from(candidate)
        self._revision = next_revision
        self._bound_token = self._controller.command_applied_token()
        if outcome.record_history:
            self._append_history(
                _HistoryEntry(
                    before.without_drafts(),
                    after.without_drafts(),
                    outcome.affected_nodes,
                    outcome.changed_fields,
                    outcome.project_only,
                )
            )
        else:
            self._redo.clear()
        result = self._result(
            invocation,
            outcome,
            changed=True,
            config_synced=synced,
            report=report,
        )
        self._notify(result)
        return result

    def _history_move(self, invocation: CommandInvocation, *, redo: bool) -> CommandResult:
        source = self._redo if redo else self._undo
        if not source:
            direction = "redo" if redo else "undo"
            raise self._error("E_DOMAIN_VALIDATION", f"nothing to {direction}", invocation)
        entry = source[-1]
        target = entry.after if redo else entry.before
        candidate = self._controller.fork()
        candidate.restore_command_checkpoint(target)
        report = candidate.validation_report()
        next_revision = self._revision + 1
        synced = self._persist_candidate(candidate, next_revision, entry.project_only, invocation)
        self._controller.publish_from(candidate)
        self._revision = next_revision
        self._bound_token = self._controller.command_applied_token()
        source.pop()
        destination = self._undo if redo else self._redo
        destination.append(entry)
        outcome = CommandOutcome(
            payload={"direction": "redo" if redo else "undo"},
            affected_nodes=entry.affected_nodes,
            changed_fields=entry.changed_fields,
            project_only=entry.project_only,
        )
        result = self._result(
            invocation,
            outcome,
            changed=True,
            config_synced=synced,
            report=report,
        )
        self._notify(result)
        return result

    def _append_history(self, entry: _HistoryEntry) -> None:
        self._undo.append(entry)
        if len(self._undo) > self._history_limit:
            del self._undo[: len(self._undo) - self._history_limit]
        self._redo.clear()

    def _persist_candidate(
        self,
        candidate: CommandController,
        revision: int,
        project_only: bool,
        invocation: CommandInvocation,
    ) -> bool | None:
        if self._persist is None:
            return None
        try:
            result = self._persist(candidate, revision, project_only)
        except CommandError:
            raise
        except Exception as exc:
            code = str(getattr(exc, "code", "E_CONFIG_IO"))
            if code not in {"E_CONFIG_DIVERGED", "E_CONFIG_IO"}:
                code = "E_CONFIG_IO"
            raise self._error(code, str(exc), invocation) from exc
        return True if result is None else bool(result)

    def _invoke(
        self,
        controller: CommandController,
        invocation: CommandInvocation,
    ) -> CommandOutcome:
        try:
            return self._provider.invoke(controller, invocation)
        except CommandError as exc:
            if exc.command == invocation.name and (
                exc.command_id is not None or invocation.command_id is None
            ):
                raise
            raise CommandError(
                exc.code,
                str(exc),
                command=exc.command or invocation.name,
                command_id=exc.command_id or invocation.command_id,
                details=exc.details,
            ) from exc
        except (OverflowError, TypeError, ValueError) as exc:
            raise self._error("E_ARGUMENT_INVALID", str(exc), invocation) from exc
        except RuntimeError as exc:
            raise self._error("E_DOMAIN_VALIDATION", str(exc), invocation) from exc

    def _result(
        self,
        invocation: CommandInvocation,
        outcome: CommandOutcome,
        *,
        changed: bool,
        config_synced: bool | None = None,
        report: Any | None = None,
    ) -> CommandResult:
        report = self._controller.validation_report() if report is None else report
        return CommandResult(
            command=invocation.name,
            revision=self._revision,
            changed=changed,
            payload=outcome.payload,
            affected_nodes=_unique(outcome.affected_nodes),
            changed_fields=_unique(outcome.changed_fields) if changed else (),
            project_only=outcome.project_only,
            coordinates_valid=bool(report.coordinates_valid),
            setup_ready=bool(report.setup_ready),
            issue_codes=tuple(issue.code for issue in report.issues),
            origin=invocation.origin,
            command_id=invocation.command_id,
            config_synced=config_synced,
        )

    def _notify(self, result: CommandResult) -> None:
        if self._on_publish is not None:
            try:
                self._on_publish(result)
            except Exception:
                # Persistence and Controller publication already succeeded. A UI
                # observer must not turn that committed command into a false failure.
                LOGGER.exception("command publication observer failed: %s", result.command)

    @staticmethod
    def _error(
        code: str,
        message: str,
        invocation: CommandInvocation,
        **details: Any,
    ) -> CommandError:
        return CommandError(
            code,
            message,
            command=invocation.name,
            command_id=invocation.command_id,
            details=details,
        )


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values))


__all__ = [
    "CommandError",
    "CommandInvocation",
    "CommandKernel",
    "CommandOutcome",
    "CommandProvider",
    "CommandResult",
]
