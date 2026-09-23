"""Connect restricted Tube commands to Qt without exposing a Python runtime.

The service is the single application-level entry for console, GUI Apply, and
HTTP mutations.  Parsing, domain publication, YAML persistence, and one UI
refresh remain separate layers so each failure has a stable boundary.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from .command_kernel import (
    CommandController,
    CommandError,
    CommandInvocation,
    CommandKernel,
    CommandResult,
)
from .restricted_script import MAX_SOURCE_BYTES, ScriptCall, ScriptParseError, parse_script
from .setup_config import (
    CONFIG_FILENAME,
    SetupConfigConflictError,
    atomic_write_setup_config,
    dump_setup_config,
    export_setup_config,
    load_setup_config_file,
    setup_config_fingerprint,
)
from .setup_config_session import (
    Resolution,
    SetupConfigInspection,
    SetupConfigStore,
    semantic_differences,
)
from .tube_commands import TubeCommandProvider
from .tube_controller import TubeSetupController

_ZH_ALIASES = {
    "help": "帮助",
    "state": "状态",
    "issues": "问题",
    "validate": "校验",
    "create_operation": "创建操作",
    "set_operation": "设置操作",
    "generate_operation": "生成操作",
    "cancel_generation": "取消生成",
    "export_operation": "导出操作",
    "confirm_part": "确认零件",
    "set_machine": "设置机床",
    "set_machine_axis_words": "设置旋转轴字",
    "set_nozzle": "设置喷嘴",
    "set_material": "设置材料",
    "set_model_cs": "设置模型坐标",
    "set_build_cs": "设置构建坐标",
    "set_placement": "设置装夹",
    "undo": "撤销",
    "redo": "重做",
}

_UI_TEXT = {
    "project_yaml_warning": (
        "[E_CONFIG_IO] 项目已保存，YAML 尚未同步：{error}",
        "[E_CONFIG_IO] Project saved, but YAML is not synchronized: {error}",
    ),
    "project_yaml_synced": (
        "[r{revision}] 配置已同步：{path}",
        "[r{revision}] YAML synchronized: {path}",
    ),
    "load_script_title": ("加载 Tube 设置脚本", "Load Tube Setup Script"),
    "import_config_title": ("导入 Manufacturing Setup", "Import Manufacturing Setup"),
    "export_config_title": ("导出 Manufacturing Setup 副本", "Export Manufacturing Setup Copy"),
    "export_complete": ("配置副本已导出：{path}", "Configuration copy exported: {path}"),
    "no_config_directory": (
        "[E_CONFIG_IO] 当前项目尚无配置目录",
        "[E_CONFIG_IO] The current project has no configuration directory",
    ),
    "error_location": (
        "[{code}] 第 {line} 行，第 {column} 列：{error}{context}",
        "[{code}] line {line}, column {column}: {error}{context}",
    ),
    "error_nodes": ("节点：{nodes}", "Nodes: {nodes}"),
    "recovery_title": ("Manufacturing Setup 恢复", "Manufacturing Setup Recovery"),
    "recovery_recoverable": (
        "检测到上次未保存的 YAML 工作态。",
        "An unsaved YAML working state was found.",
    ),
    "recovery_project_newer": ("项目主档比 YAML 更新。", "The project is newer than YAML."),
    "recovery_diverged": (
        "项目主档与 YAML 已分别修改。",
        "The project and YAML were modified independently.",
    ),
    "recovery_body": ("{summary}\n差异字段：\n{fields}", "{summary}\nChanged fields:\n{fields}"),
    "none": ("• 无", "• none"),
    "use_yaml": ("使用 YAML", "Use YAML"),
    "use_project": ("使用项目", "Use Project"),
    "cancel_open": ("取消打开项目", "Cancel Project Open"),
    "open_cancelled": ("用户取消了项目打开", "Project open was cancelled"),
    "import_title": ("导入 Setup 配置", "Import Setup Configuration"),
    "geometry_review": (
        "\n几何解析坐标需在当前模型上复核。",
        "\nGeometry-resolved coordinates require review on the current model.",
    ),
    "import_body": (
        "文件：{path}\n差异字段：\n{fields}{review}\n\n应用到当前项目？",
        "File: {path}\nChanged fields:\n{fields}{review}\n\nApply to the current project?",
    ),
    "external_title": ("YAML 已被外部修改", "YAML Was Modified Externally"),
    "external_body": (
        "自动覆盖已暂停。请选择载入外部文件或以当前 Setup 覆盖。",
        "Automatic writes are paused. Load the external file or overwrite it with the current Setup.",
    ),
    "load_preview": ("载入并预览", "Load and Preview"),
    "overwrite_current": ("以当前状态覆盖", "Overwrite with Current Setup"),
    "cancel": ("取消", "Cancel"),
}

LOGGER = logging.getLogger(__name__)

_COMMAND_NODES = {
    "create_operation": ("operation",),
    "set_operation": ("operation",),
    "confirm_part": ("part",),
    "set_machine": ("machine", "placement"),
    "set_machine_axis_words": ("machine", "placement"),
    "set_nozzle": ("nozzle",),
    "set_complete_nozzle": ("nozzle",),
    "set_material": ("material",),
    "set_model_cs": ("model_cs",),
    "set_build_cs": ("build_cs", "placement"),
    "set_placement": ("placement",),
    "apply_coordinate_draft": ("model_cs", "build_cs"),
    "apply_placement_draft": ("placement",),
}


class ProjectOpenCancelled(RuntimeError):
    """A YAML recovery prompt was cancelled before project publication."""


class TubeScriptService:
    """Own one command kernel and its project-local YAML attachment."""

    def __init__(self, window: Any, console: Any) -> None:
        self.window = window
        self.page = window.tube_page
        self.console = console
        self.provider = TubeCommandProvider()
        self.config = SetupConfigStore()
        self._prepared_config: SetupConfigStore | None = None
        self._prepared_project_modified = False
        self.kernel = self._new_kernel(self.page.controller)
        self.config.reset_memory(self.page.controller)
        self._connect_console()
        self._bind_page_executor()
        self.page.state_changed.connect(lambda _state: self._sync_console())
        self._sync_console()

    def _text(self, key: str, **values: Any) -> str:
        language_index = 1 if self.window.language == "en" else 0
        return _UI_TEXT[key][language_index].format(**values)

    def _new_kernel(self, controller: TubeSetupController) -> CommandKernel:
        return CommandKernel(
            cast(CommandController, controller),
            self.provider,
            persist=self._persist_candidate,
            on_publish=self._published,
            is_busy=lambda: bool(self.window.load_coordinator.busy),
        )

    def _connect_console(self) -> None:
        self.console.set_executor(self.execute_script)
        self.console.set_completion_provider(self.completions)
        self.console.load_script_requested.connect(self.load_script_dialog)
        self.console.import_config_requested.connect(self.import_config_dialog)
        self.console.export_config_requested.connect(self.export_config_dialog)
        self.console.reveal_config_requested.connect(self.reveal_config_directory)
        self.console.apply_drafts_requested.connect(self.apply_drafts)
        self.console.discard_drafts_requested.connect(self.discard_drafts)
        self.console.node_link_requested.connect(self._jump_to_node)

    def _bind_page_executor(self) -> None:
        binder = getattr(self.page, "set_command_executor", None)
        if callable(binder):
            binder(self.execute_invocation)

    def bind_new_controller(self, controller: TubeSetupController) -> None:
        """Start a new unsaved STEP context and clear state history."""

        self.kernel.rebind(cast(CommandController, controller), clear_history=True)
        self.config.reset_memory(controller, self.kernel.revision)
        self._bind_page_executor()
        self._sync_console()

    def prepare_project_controller(
        self,
        controller: TubeSetupController,
        project_directory: str | Path,
        *,
        interactive: bool,
    ) -> SetupConfigInspection:
        """Resolve project/YAML state before any Viewer or controller publish."""

        self._prepared_config = None
        self._prepared_project_modified = False
        pending = SetupConfigStore()
        inspection = pending.inspect_project(controller, project_directory)
        resolution: Resolution = "project"
        if inspection.needs_resolution:
            if not interactive:
                raise SetupConfigConflictError(
                    "project and YAML require an explicit recovery choice"
                )
            resolution = self._ask_project_resolution(inspection)
        pending.attach_project(controller, inspection, resolution)
        self._prepared_config = pending
        self._prepared_project_modified = resolution == "yaml"
        return inspection

    def bind_prepared_project(self, controller: TubeSetupController) -> bool:
        if self._prepared_config is None:
            raise RuntimeError("project configuration was not prepared")
        self.config = self._prepared_config
        self._prepared_config = None
        modified = self._prepared_project_modified
        self._prepared_project_modified = False
        self.kernel.rebind(cast(CommandController, controller), clear_history=True)
        self._bind_page_executor()
        self._sync_console()
        return modified

    def synchronize_external_controller(self, *, write_config: bool) -> None:
        """Invalidate undo after source or legacy code changes applied state."""

        changed = self.kernel.synchronize_external_state(clear_history=True)
        if not changed or not write_config:
            self._sync_console()
            return
        try:
            self.config.persist_candidate(self.page.controller, self.kernel.revision, False)
        except Exception as exc:
            self._append_error(exc)
        self._sync_console()

    def project_saved(self, project_directory: str | Path) -> str | None:
        """Attach/update YAML after the authoritative project save succeeds."""

        self.kernel.synchronize_external_state(clear_history=True)
        try:
            path = self.config.project_saved(
                self.page.controller,
                project_directory,
                self.kernel.revision,
            )
        except Exception as exc:
            message = self._text("project_yaml_warning", error=exc)
            self.console.append_output(message)
            self._sync_console()
            return message
        self.console.append_output(
            self._text("project_yaml_synced", revision=self.kernel.revision, path=path)
        )
        self._sync_console()
        return None

    def execute_invocation(self, invocation: CommandInvocation) -> CommandResult:
        """Entry used by GUI Apply and HTTP adapters."""

        result = self.kernel.execute(invocation)
        if not result.changed:
            self._sync_console()
        return result

    def _persist_candidate(
        self,
        candidate: CommandController,
        revision: int,
        project_only: bool,
    ) -> bool:
        if not isinstance(candidate, TubeSetupController):
            raise TypeError("Tube persistence requires TubeSetupController")
        return self.config.persist_candidate(candidate, revision, project_only)

    def execute_command(
        self,
        command_name: str,
        *args: Any,
        command_origin: str,
        command_id: str | None = None,
        expected_revision: int | None = None,
        **kwargs: Any,
    ) -> CommandResult:
        return self.execute_invocation(
            CommandInvocation(
                command_name,
                args,
                kwargs,
                origin=command_origin,
                command_id=command_id,
                expected_revision=expected_revision,
            )
        )

    def execute_script(self, source: str) -> str:
        """Parse and run only the restricted AST grammar."""

        try:
            groups = parse_script(source)
            if not groups:
                return ""
            output: list[str] = []
            for group in groups:
                if group.atomic:
                    calls = tuple(self._script_invocation(call) for call in group.calls)
                    try:
                        result = self.kernel.transaction(calls, origin="script")
                    except CommandError as exc:
                        location = next(
                            (call for call in group.calls if call.name == exc.command),
                            group.calls[0],
                        )
                        return self._format_error(exc, location.line, location.column)
                    output.append(self._format_result(result))
                    continue
                call = group.calls[0]
                try:
                    result = self.execute_invocation(self._script_invocation(call))
                except CommandError as exc:
                    return self._format_error(exc, call.line, call.column)
                output.append(self._format_result(result))
            return "\n\n".join(output)
        except ScriptParseError as exc:
            return self._format_error(exc, exc.line, exc.column)
        except CommandError as exc:
            return self._format_error(exc)
        except Exception as exc:
            return self._format_error(exc)

    def completions(self, source: str) -> Sequence[str]:
        """Complete command names and stable domain identifiers."""

        match = re.search(r"[\"']([^\r\n\"']*)$", source)
        if match is None:
            match = re.search(r"([\w\u4e00-\u9fff-]*)$", source)
        prefix = "" if match is None else match.group(1)
        values = list(self.provider.public_commands)
        values.extend(_ZH_ALIASES.values())
        controller = self.page.controller
        for kind in ("machine", "nozzle", "material"):
            values.extend(
                str(getattr(item, "resource_id", getattr(item, "profile_id", "")))
                for item in controller.available_resource_profiles(kind)
            )
        values.extend(item.body_id for item in controller.body_candidates)
        if controller.setup.machine is not None:
            try:
                values.extend(controller.machine_profile().mount_map)
            except ValueError:
                pass
        return tuple(value for value in dict.fromkeys(values) if value and value.startswith(prefix))

    def state_json(self) -> dict[str, Any]:
        return {
            "revision": self.kernel.revision,
            "can_undo": self.kernel.can_undo,
            "can_redo": self.kernel.can_redo,
            "config": self.config.state_json(),
        }

    def retranslate(self) -> None:
        self._sync_console()

    def resolve_resource_id(self, kind: str, identifier: str) -> str:
        """Resolve legacy labels while commands continue to receive stable IDs."""

        canonical_kind = str(kind).strip().lower()
        if canonical_kind not in {"machine", "nozzle", "material"}:
            raise ValueError(f"unsupported resource kind: {kind!r}")
        key = str(identifier).strip().lower()
        profiles = self.page.controller.available_resource_profiles(canonical_kind)
        for profile in profiles:
            resource_id = str(getattr(profile, "profile_id", getattr(profile, "resource_id", "")))
            labels = {
                resource_id.lower(),
                str(getattr(profile, "name", "")).lower(),
                str(getattr(profile, "display_name", "")).lower(),
                str(getattr(profile, "material", "")).lower(),
            }
            diameter = getattr(profile, "orifice_diameter_mm", None)
            if diameter is not None:
                labels.add(f"{float(diameter):g}")
            if key in labels or any(key and key in label for label in labels):
                return resource_id
        raise KeyError(identifier)

    def load_script_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.window,
            self._text("load_script_title"),
            "",
            "Tube Setup Script (*.py)",
        )
        if not path:
            return
        try:
            source_path = Path(path)
            with source_path.open("rb") as stream:
                data = stream.read(MAX_SOURCE_BYTES + 1)
            if len(data) > MAX_SOURCE_BYTES:
                raise ScriptParseError("E_SCRIPT_FORBIDDEN", "Script exceeds 256 KiB", 1, 1)
            source = data.decode("utf-8")
            response = self.execute_script(source)
        except (OSError, UnicodeError) as exc:
            response = self._format_error(exc)
        if response:
            self.console.append_output(response)

    def import_config_dialog(self) -> None:
        if self.config.suspended:
            self._resolve_external_change()
            return
        path, _ = QFileDialog.getOpenFileName(
            self.window,
            self._text("import_config_title"),
            "",
            "YAML (*.yaml *.yml)",
        )
        if not path:
            return
        try:
            config = load_setup_config_file(path)
            current = export_setup_config(
                self.page.controller.setup,
                self.page.controller.operations,
                revision=max(1, self.kernel.revision),
            )
            differences = semantic_differences(current, config)
            if not self._confirm_import(path, differences, config.geometry_review_required):
                return
            result = self.execute_command(
                "apply_setup_config",
                config,
                command_origin="gui",
            )
            self.console.append_output(self._format_result(result))
        except Exception as exc:
            self._append_error(exc)

    def export_config_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self.window,
            self._text("export_config_title"),
            CONFIG_FILENAME,
            "YAML (*.yaml)",
        )
        if not path:
            return
        destination = Path(path)
        try:
            config = export_setup_config(
                self.page.controller.setup,
                self.page.controller.operations,
                revision=max(1, self.kernel.revision),
                base_project_setup_sha256=self.config.state_json()["base_project_setup_sha256"],
            )
            text = dump_setup_config(config)
            fingerprint = setup_config_fingerprint(destination)
            atomic_write_setup_config(
                destination,
                text,
                expected_fingerprint=fingerprint,
                expect_missing=fingerprint is None,
            )
            self.console.append_output(self._text("export_complete", path=destination))
        except Exception as exc:
            self._append_error(exc)

    def reveal_config_directory(self) -> None:
        path = self.config.path
        directory = path.parent if path is not None else self.window.last_project_dir
        if directory is None or not Path(directory).is_dir():
            self.console.append_output(self._text("no_config_directory"))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(directory).resolve())))

    def apply_drafts(self) -> None:
        try:
            result = self.execute_command("apply_all_drafts", command_origin="gui")
            self.console.append_output(self._format_result(result))
        except Exception as exc:
            self._append_error(exc)

    def discard_drafts(self) -> None:
        try:
            result = self.execute_command("discard_all_drafts", command_origin="gui")
            self.console.append_output(self._format_result(result))
        except Exception as exc:
            self._append_error(exc)

    def _published(self, result: CommandResult) -> None:
        try:
            _sync_shared_workbench_setups(self)
            self.page.refresh()
            self._sync_console()
            self.window.statusBar().showMessage(
                "当前项目已更新。"
                if self.window.language == "zh"
                else "Current project updated."
            )
        except Exception as exc:
            LOGGER.exception("Tube command committed but UI refresh failed")
            try:
                self.console.append_output(f"[E_UI_REFRESH] {exc}")
            except Exception:
                LOGGER.exception("cannot report Tube UI refresh failure")

    def _sync_console(self) -> None:
        state = self.config.state_json()
        labels = {
            "zh": {
                "memory": "配置仅在内存中",
                "pending": "配置将在项目保存时创建",
                "synced": "YAML 已同步",
                "diverged": "YAML 外部修改，自动写入已暂停",
            },
            "en": {
                "memory": "Configuration is in memory only",
                "pending": "YAML will be created when the project is saved",
                "synced": "YAML synchronized",
                "diverged": "External YAML change; automatic writes paused",
            },
        }
        language = self.window.language if self.window.language in labels else "zh"
        self.console.set_status(labels[language][state["status"]], revision=self.kernel.revision)
        self.console.set_draft_conflict(self.page.controller.has_drafts)

    @staticmethod
    def _script_invocation(call: ScriptCall) -> CommandInvocation:
        if call.namespace != "tube":
            raise ScriptParseError(
                "E_SCRIPT_FORBIDDEN",
                "Tube command service accepts only tube/管状 commands",
                call.line,
                call.column,
            )
        return CommandInvocation(call.name, call.args, call.kwargs, origin="script")

    def _format_result(self, result: CommandResult) -> str:
        return _result_text(result, english=self.window.language == "en")

    def _format_error(self, error: Exception, line: int = 1, column: int = 1) -> str:
        fallback = (
            "E_CONFIG_IO" if isinstance(error, OSError | UnicodeError) else "E_COMMAND_FAILED"
        )
        code = str(getattr(error, "code", fallback))
        details = getattr(error, "details", {})
        context = ""
        if isinstance(details, Mapping) and details:
            context = " | " + ", ".join(f"{key}={value}" for key, value in details.items())
        message = self._text(
            "error_location",
            code=code,
            line=line,
            column=column,
            error=error,
            context=context,
        )
        nodes = self._error_nodes(error)
        if nodes:
            separator = ", " if self.window.language == "en" else "、"
            links = separator.join(f"[[node:{node}]]" for node in nodes)
            message += "\n" + self._text("error_nodes", nodes=links)
        return message

    def _error_nodes(self, error: Exception) -> tuple[str, ...]:
        if str(getattr(error, "code", "")) == "E_DRAFT_ACTIVE":
            return tuple(self.page.controller.draft_nodes)
        command = str(getattr(error, "command", ""))
        return _COMMAND_NODES.get(command, ())

    def _jump_to_node(self, node: str) -> None:
        selector = getattr(self.page, "select_setup_node", None)
        if callable(selector):
            selector(node)

    def _append_error(self, error: Exception) -> None:
        self.console.append_output(self._format_error(error))
        self._sync_console()

    def _ask_project_resolution(self, inspection: SetupConfigInspection) -> Resolution:
        dialog = QMessageBox(self.window)
        dialog.setWindowTitle(self._text("recovery_title"))
        kind = {
            "recoverable": self._text("recovery_recoverable"),
            "project_newer": self._text("recovery_project_newer"),
            "diverged": self._text("recovery_diverged"),
        }[inspection.comparison]
        fields = "\n".join(f"• {item}" for item in inspection.differences[:12])
        dialog.setText(
            self._text("recovery_body", summary=kind, fields=fields or self._text("none"))
        )
        yaml_button = dialog.addButton(self._text("use_yaml"), QMessageBox.AcceptRole)
        project_button = dialog.addButton(self._text("use_project"), QMessageBox.DestructiveRole)
        dialog.addButton(self._text("cancel_open"), QMessageBox.RejectRole)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked is yaml_button:
            return "yaml"
        if clicked is project_button:
            return "project"
        raise ProjectOpenCancelled(self._text("open_cancelled"))

    def _confirm_import(
        self,
        path: str,
        differences: Sequence[str],
        geometry_review: bool,
    ) -> bool:
        fields = "\n".join(f"• {item}" for item in differences[:12]) or self._text("none")
        review = self._text("geometry_review") if geometry_review else ""
        answer = QMessageBox.question(
            self.window,
            self._text("import_title"),
            self._text("import_body", path=path, fields=fields, review=review),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    def _resolve_external_change(self) -> None:
        _resolve_external_change(self)


def _sync_shared_workbench_setups(service: TubeScriptService) -> None:
    """Publish the authoritative Setup to every loaded manufacturing workbench."""

    from . import curve_shell, planar_shell, rotary_shell

    setup = service.page.controller.setup
    consumers = (
        ("planar_page", "planar_command_service", planar_shell.sync_shared_setup),
        ("curve_page", "curve_command_service", curve_shell.sync_shared_setup),
        ("rotary_page", "rotary_command_service", rotary_shell.sync_shared_setup),
    )
    changed_pages: list[tuple[str, Any]] = []
    for page_name, service_name, sync in consumers:
        page = getattr(service.window, page_name, None)
        if page is None or not sync(page.controller, setup):
            continue
        command_service = getattr(service.window, service_name, None)
        kernel = getattr(command_service, "kernel", None)
        if kernel is not None:
            kernel.synchronize_external_state(clear_history=True)
        changed_pages.append((page_name, page))

    # All controllers and command epochs must be synchronized before any UI
    # rendering is attempted.  A broken page refresh must never leave a later
    # workbench pointing at an exportable result from the previous machine map.
    for page_name, page in changed_pages:
        try:
            page.refresh()
        except Exception:
            LOGGER.exception("%s refresh failed after shared Setup synchronization", page_name)


def _resolve_external_change(service: TubeScriptService) -> None:
    dialog = QMessageBox(service.window)
    dialog.setWindowTitle(service._text("external_title"))
    dialog.setText(service._text("external_body"))
    load_button = dialog.addButton(service._text("load_preview"), QMessageBox.AcceptRole)
    overwrite_button = dialog.addButton(
        service._text("overwrite_current"), QMessageBox.DestructiveRole
    )
    dialog.addButton(service._text("cancel"), QMessageBox.RejectRole)
    dialog.exec()
    clicked = dialog.clickedButton()
    if clicked is load_button:
        try:
            config, fingerprint = service.config.preview_external()
            current = export_setup_config(
                service.page.controller.setup,
                service.page.controller.operations,
                revision=max(1, service.kernel.revision),
            )
            if not service._confirm_import(
                str(service.config.path),
                semantic_differences(current, config),
                config.geometry_review_required,
            ):
                return
            accepted = service.config.accept_external(fingerprint)
            result = service.execute_command("apply_setup_config", accepted, command_origin="gui")
            service.console.append_output(service._format_result(result))
        except Exception as exc:
            service._append_error(exc)
        return
    if clicked is overwrite_button:
        try:
            service.config.overwrite_external(service.page.controller, service.kernel.revision)
            service._sync_console()
        except Exception as exc:
            service._append_error(exc)


def command_result_json(result: CommandResult) -> dict[str, Any]:
    """Stable HTTP representation without leaking domain objects."""

    return {
        "command": result.command,
        "revision": result.revision,
        "changed": result.changed,
        "payload": result.payload,
        "affected_nodes": list(result.affected_nodes),
        "changed_fields": list(result.changed_fields),
        "project_only": result.project_only,
        "coordinates_valid": result.coordinates_valid,
        "setup_ready": result.setup_ready,
        "issue_codes": list(result.issue_codes),
        "origin": result.origin,
        "command_id": result.command_id,
        "config_synced": result.config_synced,
    }


def _result_text(result: CommandResult, *, english: bool) -> str:
    header = f"[r{result.revision}] {result.command}"
    if not result.changed and result.command in {"help", "state", "issues", "validate"}:
        return header + "\n" + json.dumps(result.payload, ensure_ascii=False, indent=2)
    empty = "none" if english else "无"
    changed = ", ".join(result.changed_fields) or empty
    nodes = ", ".join(result.affected_nodes) or empty
    issues = ", ".join(result.issue_codes) or empty
    config = _config_result_label(result, english=english)
    if english:
        return (
            f"{header}\nChanged fields: {changed}\nAffected nodes: {nodes}\n"
            f"Configuration: {config}\n"
            f"Coordinates Valid: {'yes' if result.coordinates_valid else 'no'}\n"
            f"Setup Ready: {'yes' if result.setup_ready else 'no'}\nIssue codes: {issues}"
        )
    return (
        f"{header}\n修改字段：{changed}\n受影响节点：{nodes}\n配置：{config}\n"
        f"Coordinates Valid：{'是' if result.coordinates_valid else '否'}\n"
        f"Setup Ready：{'是' if result.setup_ready else '否'}\n问题码：{issues}"
    )


def _config_result_label(result: CommandResult, *, english: bool) -> str:
    if result.project_only:
        return "project-only; YAML unchanged" if english else "项目专属，YAML 未变化"
    if result.config_synced is True:
        return "YAML synchronized" if english else "YAML 已同步"
    if result.config_synced is False:
        return "in-memory configuration updated" if english else "内存配置已更新"
    return "configuration unchanged" if english else "配置未变化"


__all__ = [
    "ProjectOpenCancelled",
    "TubeScriptService",
    "command_result_json",
]
