"""Broad-phase checks must preserve both exact polygon predicates."""

from __future__ import annotations

import random
import math

from five_axis_slicer.algorithms._segment_pairs import nonadjacent_overlap_pairs
from five_axis_slicer.algorithms.freeform.spherical_fill import _segments_cross
from five_axis_slicer.algorithms.planar.offset import _segments_intersect


def _brute_pairs(count: int):
    for left in range(count):
        for right in range(left + 1, count):
            if right != left + 1 and not (left == 0 and right == count - 1):
                yield left, right


def test_sweep_preserves_exact_crossing_and_contact_results() -> None:
    randomizer = random.Random(20260924)
    loops = [
        ((0.0, 0.0, 0.0), (2.0, 2.0, 0.0), (0.0, 2.0, 0.0),
         (2.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 2.0, 0.0),
         (1.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 0.0)),
    ]
    for _ in range(40):
        vertices = tuple(
            (randomizer.uniform(-3, 3), randomizer.uniform(-3, 3), 0.0)
            for _ in range(12)
        )
        loops.append((*vertices, vertices[0]))

    for loop in loops:
        edges = tuple(zip(loop, loop[1:], strict=False))
        eligible = set(_brute_pairs(len(edges)))
        for predicate, tolerance in ((_segments_cross, 1.0e-8),
                                     (_segments_intersect, 1.0e-7)):
            expected = {
                pair for pair in _brute_pairs(len(edges))
                if predicate(*edges[pair[0]], *edges[pair[1]])
            }
            candidates = set(nonadjacent_overlap_pairs(loop, tolerance=tolerance))
            assert expected <= candidates
            assert candidates <= eligible


def test_sweep_prunes_most_pairs_on_a_dense_convex_contour() -> None:
    vertices = tuple(
        (math.cos(index * 2 * math.pi / 128), math.sin(index * 2 * math.pi / 128), 0.0)
        for index in range(128)
    )
    loop = (*vertices, vertices[0])
    assert len(tuple(nonadjacent_overlap_pairs(loop, tolerance=1.0e-8))) < 128
    assert len(set(_brute_pairs(128))) == 8000
