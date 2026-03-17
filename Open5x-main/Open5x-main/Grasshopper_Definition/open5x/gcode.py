from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .models import MachineConfig, Pose


@dataclass(slots=True)
class GCodeBuilder:
    machine: MachineConfig
    lines: list[str] = field(default_factory=list)

    def comment(self, text: str) -> None:
        self.lines.append(f"; {text}")

    def extend(self, values: list[str]) -> None:
        self.lines.extend(values)

    def move(
        self,
        pose: Pose,
        *,
        feed_mm_min: float,
        extrusion_delta_mm: float | None = None,
        machine_point_override: np.ndarray | None = None,
        command: str = "G1",
    ) -> None:
        point = machine_point_override if machine_point_override is not None else pose.machine_point_mm
        parts = [command]
        for axis, value in zip(self.machine.translation_axes, point, strict=True):
            parts.append(f"{axis}{value:.4f}")
        for axis, value in zip(self.machine.rotation_axes, pose.rotation_deg, strict=True):
            parts.append(f"{axis}{value:.4f}")
        if extrusion_delta_mm is not None and abs(extrusion_delta_mm) > 1e-9:
            parts.append(f"E{extrusion_delta_mm:.5f}")
        parts.append(f"F{feed_mm_min:.1f}")
        self.lines.append(" ".join(parts))

    def extruder_only(self, extrusion_delta_mm: float, feed_mm_min: float) -> None:
        if abs(extrusion_delta_mm) <= 1e-9:
            return
        self.lines.append(f"G1 E{extrusion_delta_mm:.5f} F{feed_mm_min:.1f}")

    def emit_program(self) -> str:
        return "\n".join(self.lines) + "\n"
