"""Broad-phase XY segment pairs for exact polygon-intersection checks."""

from __future__ import annotations

from collections.abc import Iterator

from ..models import Vector3


def nonadjacent_overlap_pairs(
    loop: tuple[Vector3, ...], *, tolerance: float = 0.0
) -> Iterator[tuple[int, int]]:
    """Yield only non-neighbouring edge pairs whose XY bounds may intersect.

    The caller retains its own exact segment predicate. This sweep never
    decides whether two segments cross; it only avoids comparing disjoint
    bounding boxes, including those separated by a small tolerance.
    """
    count = len(loop) - 1
    boxes = []
    for index, (start, end) in enumerate(zip(loop, loop[1:], strict=False)):
        boxes.append((
            min(start[0], end[0]), max(start[0], end[0]),
            min(start[1], end[1]), max(start[1], end[1]), index,
        ))
    active: list[tuple[float, float, float, int]] = []
    for min_x, max_x, min_y, max_y, index in sorted(boxes):
        active = [box for box in active if box[0] + tolerance >= min_x]
        for _other_max_x, other_min_y, other_max_y, other_index in active:
            if abs(index - other_index) == 1 or {index, other_index} == {0, count - 1}:
                continue
            if other_max_y + tolerance < min_y or max_y + tolerance < other_min_y:
                continue
            yield (min(index, other_index), max(index, other_index))
        active.append((max_x, min_y, max_y, index))
