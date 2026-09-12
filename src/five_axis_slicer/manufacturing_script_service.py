"""Namespace-safe restricted-script dispatcher for manufacturing workbenches."""

from __future__ import annotations

import json
from typing import Any

from .command_kernel import CommandInvocation
from .restricted_script import ScriptParseError, parse_script


class ManufacturingScriptService:
    def __init__(self, window: Any) -> None:
        self._window = window

    def _services(self) -> dict[str, Any]:
        return {
            "tube": self._window.tube_script_service,
            "planar": self._window.planar_command_service,
            "curve": self._window.curve_command_service,
            "rotary": self._window.rotary_command_service,
        }

    def execute_script(self, source: str) -> str:
        try:
            output: list[str] = []
            for group in parse_script(source):
                if not group.calls:
                    continue
                namespace = group.calls[0].namespace
                if any(call.namespace != namespace for call in group.calls):
                    raise ScriptParseError(
                        "E_SCRIPT_FORBIDDEN",
                        "A transaction may modify only one manufacturing workbench",
                        group.calls[0].line,
                        group.calls[0].column,
                    )
                service = self._services()[namespace]
                calls = tuple(
                    CommandInvocation(call.name, call.args, call.kwargs, origin="script")
                    for call in group.calls
                )
                result = (
                    service.kernel.transaction(calls, origin="script")
                    if group.atomic
                    else service.kernel.execute(calls[0])
                )
                output.append(json.dumps(result.payload, ensure_ascii=False, sort_keys=True))
            return "\n".join(output)
        except Exception as exc:
            return f"ERROR: {exc}"


__all__ = ["ManufacturingScriptService"]
