"""Broad-phase candidates must preserve the brute-force collision result."""

import random
from dataclasses import replace

import test_tube_indexed_pipeline as pipeline
from five_axis_slicer.validation.indexed_tube import (
    _DepositedSegmentIndex,
    _point_segment_distance,
    validate_indexed_tube,
)


def test_capsule_candidates_include_every_exact_hit():
    rng = random.Random(1309)
    index = _DepositedSegmentIndex(0.6)
    segments = [
        ((-10000.0, 0.0, 0.0), (10000.0, 0.0, 0.0), 0.5),
        ((-1.2, 0.0, 0.0), (-1.2, 0.0, 0.0), 0.6),
    ]
    segments.extend(
        (
            tuple(rng.uniform(-5, 5) for _ in range(3)),
            tuple(rng.uniform(-5, 5) for _ in range(3)),
            rng.uniform(0.01, 1),
        )
        for _ in range(100)
    )
    for ordinal, (start, end, radius) in enumerate(segments):
        index.add(ordinal, start, end, radius)
    queries = [(0.0, 0.0, 0.0), (-2.4, 0.0, 0.0), (0.0, 1.1, 0.0)]
    queries.extend(start for start, _, _ in segments)
    queries.extend(tuple(rng.uniform(-8, 8) for _ in range(3)) for _ in range(200))
    for point in queries:
        for before in (0, 2, len(segments) - 2, len(segments)):
            candidates = index.candidates(point, before=before)
            assert candidates == sorted(set(candidates))
            assert all(value < before for value in candidates)
            for ordinal, (start, end, radius) in enumerate(segments[:before]):
                if _point_segment_distance(point, start, end) <= radius + 0.6:
                    assert ordinal in candidates
    assert len(index.candidates((100.0, 100.0, 100.0), before=len(segments))) < 5
    assert index.large == [0]


def test_full_report_matches_brute_force_including_first_hit_order(monkeypatch):
    fixture = pipeline.IndexedValidationTests()
    fixture.setUp()
    fixture.toolpath = replace(
        fixture.toolpath,
        points=tuple(
            replace(point, nozzle_axis=(1.0, 0.0, 0.0)) for point in fixture.toolpath.points
        ),
    )
    arguments = (
        fixture.feature,
        fixture.plan,
        fixture.toolpath,
        fixture.trajectory,
        fixture.nozzle,
    )
    indexed = validate_indexed_tube(*arguments)
    monkeypatch.setattr(
        _DepositedSegmentIndex,
        "candidates",
        lambda self, center, *, before: list(range(max(0, before))),
    )
    brute = validate_indexed_tube(*arguments)
    assert indexed.to_json() == brute.to_json()
    assert indexed.has_errors  # The known IPW collision must not disappear.
