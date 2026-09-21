"""Broad-phase candidates must preserve the brute-force collision result."""

import random
import pytest
from dataclasses import replace

import test_tube_indexed_pipeline as pipeline
from five_axis_slicer.validation.indexed_tube import (
    _DepositedSegmentIndex,
    _collision_issues,
    _point_segment_distance,
    validate_indexed_tube,
)


def test_collision_checkpoint_preserves_report_and_propagates_cancellation():
    fixture = pipeline.IndexedValidationTests()
    fixture.setUp()
    args = (fixture.toolpath, fixture.nozzle, (), 0.25)
    expected = _collision_issues(*args, check_ipw=True)
    calls = []
    actual = _collision_issues(*args, check_ipw=True, checkpoint=lambda: calls.append(1))
    assert actual == expected
    assert calls

    def stop():
        raise RuntimeError("cancel requested")

    with pytest.raises(RuntimeError, match="cancel requested"):
        _collision_issues(*args, check_ipw=True, checkpoint=stop)


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
            near = index.near_candidates(point, 0.6, before=before)
            assert candidates == sorted(set(candidates))
            assert all(value < before for value in candidates)
            for ordinal, (start, end, radius) in enumerate(segments[:before]):
                if _point_segment_distance(point, start, end) <= radius + 0.6:
                    assert ordinal in candidates
                    assert ordinal in near
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
    fast, checked = _collision_issues(
        fixture.toolpath, fixture.nozzle, (), 0.25, check_ipw=True, stop_on_collision=True
    )
    assert fast
    assert checked < indexed.collision_samples_checked
    assert fast[0] in indexed.issues
    incomplete = replace(indexed, issues=(), collision_check_complete=False)
    assert incomplete.has_errors
    assert not incomplete.ready_for_export


def test_trajectory_checkpoint_preserves_fk_and_cancels():
    from five_axis_slicer.kinematics.xyzac import solve_xyzac_trajectory
    from five_axis_slicer.manufacturing.own_printer import own_ac_profile

    fixture = pipeline.IndexedValidationTests()
    fixture.setUp()
    machine = own_ac_profile()
    expected = solve_xyzac_trajectory(fixture.toolpath, machine)
    calls = []
    actual = solve_xyzac_trajectory(fixture.toolpath, machine, checkpoint=lambda: calls.append(1))
    assert actual == expected
    assert calls

    def stop():
        raise RuntimeError("cancel requested")

    with pytest.raises(RuntimeError, match="cancel requested"):
        solve_xyzac_trajectory(fixture.toolpath, machine, checkpoint=stop)


def test_buildup_geometry_checkpoint_preserves_path_and_cancels():
    from five_axis_slicer.algorithms.tube.buildup import (
        TubeBuildupParameters,
        plan_tube_buildup,
        generate_tube_buildup_toolpath,
    )

    fixture = pipeline.IndexedValidationTests()
    fixture.setUp()
    parameters = TubeBuildupParameters(
        bead_width_mm=0.5, layer_height_mm=0.5, maximum_pass_spacing_mm=0.5
    )
    plan = plan_tube_buildup(fixture.feature, parameters)
    args = ("checkpoint", fixture.feature, plan, parameters)
    expected = generate_tube_buildup_toolpath(*args)
    calls = []
    assert generate_tube_buildup_toolpath(*args, checkpoint=lambda: calls.append(1)) == expected
    assert len(calls) == len(plan.layers)

    def stop():
        raise RuntimeError("cancel requested")

    with pytest.raises(RuntimeError, match="cancel requested"):
        generate_tube_buildup_toolpath(*args, checkpoint=stop)
