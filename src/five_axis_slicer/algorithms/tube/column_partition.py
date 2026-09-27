"""Geometric terminal-layer redistribution, not machine thickness limits.

Related geometric motivation: Song et al., Anti-aliasing for fused filament
deposition, sections 3.1–3.2, https://arxiv.org/html/1609.03032v2 . This restricted
one-column rule is not their complete path/interference algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class ColumnPartition:
    low: float
    high: float
    nominal_height: float
    count: int
    supported: bool
    reason: str | None = None
    ready_for_export: bool = False

    def interval(self, index: int) -> tuple[float, float] | None:
        """Return a zero-based interval, or None outside the supported column."""
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError("column index must be an integer")
        if index < 0:
            raise ValueError("column index must be non-negative")
        if not self.supported or index >= self.count:
            return None
        lower = self.low + index * self.nominal_height
        upper = self.high if index == self.count - 1 else self.low + (index + 1) * self.nominal_height
        if upper <= lower:
            raise ValueError("column layer is not numerically resolvable")
        return lower, upper


def partition_column(low: float, high: float, nominal_height: float) -> ColumnPartition:
    """Keep preceding full layers and absorb the residual into the last layer.

    n=max(1,floor(length/h+0.5)); the half-layer tie starts another layer.
    Lengths below h/2 are explicit unsupported geometry. h/2 is an algorithmic
    redistribution threshold, never a calibrated minimum printable thickness.
    No paths, extrusion, support or nozzle-clearance qualification is supplied.
    """
    low, high, height = float(low), float(high), float(nominal_height)
    if not all(math.isfinite(value) for value in (low, high, height)):
        raise ValueError("column coordinates and height must be finite")
    if high <= low or height <= 0:
        raise ValueError("column requires low < high and positive nominal height")
    length = high - low
    ratio = length / height
    if not math.isfinite(length) or not math.isfinite(ratio):
        raise ValueError("column length or layer count overflow")
    if ratio < 0.5:
        return ColumnPartition(low, high, height, 0, False, "column_below_geometric_half_layer")
    count = max(1, math.floor(ratio + 0.5))
    result = ColumnPartition(low, high, height, count, True)
    # Catch magnitudes at which adding a nominal layer cannot change position.
    result.interval(0)
    result.interval(count - 1)
    return result


__all__ = ["ColumnPartition", "partition_column"]
