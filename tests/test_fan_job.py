from __future__ import annotations

import pytest

from five_axis_slicer.manufacturing.coordinates import GeometryReference, RigidTransform
from five_axis_slicer.manufacturing.fan_job import (
    FanGeometrySelection,
    FanJobOperation,
    FanJobPublication,
    FanManufacturingContract,
    FanManufacturingJob,
    FanProcessParameters,
    ParameterSource,
    SourcedValue,
)


def _reference(identifier: str) -> GeometryReference:
    return GeometryReference(identifier, "body", {"signature": identifier})


def _contract() -> FanManufacturingContract:
    return FanManufacturingContract(
        contract_id="fan-reference-v1",
        source_sha256="a" * 64,
        geometry=FanGeometrySelection(
            _reference("hub"),
            (_reference("blade-1"), _reference("blade-2"), _reference("blade-3")),
        ),
        source_to_build=RigidTransform.from_rotation_translation(
            ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
            source_frame="source",
            target_frame="build",
        ),
        parameter_sources={
            "nozzle_diameter_mm": SourcedValue(0.4, ParameterSource.PAPER),
            "layer_height_mm": SourcedValue(0.2, ParameterSource.ENGINEERING_DEFAULT),
            "nozzle_envelope": SourcedValue(None, ParameterSource.PENDING_MEASUREMENT),
        },
    )


def test_fan_contract_roundtrip_and_machine_gate() -> None:
    contract = _contract()
    restored = FanManufacturingContract.from_json(contract.to_json())
    assert restored.semantic_sha256() == contract.semantic_sha256()
    assert restored.offline_ready
    assert not restored.machine_ready
    assert restored.parameters == FanProcessParameters()


def test_fan_geometry_requires_three_distinct_blades() -> None:
    with pytest.raises(ValueError, match="distinct"):
        FanGeometrySelection(
            _reference("hub"),
            (_reference("blade-1"), _reference("blade-1"), _reference("blade-3")),
        )


def test_job_graph_roundtrip_order_and_stale_propagation() -> None:
    operations = (
        FanJobOperation("base", "planar"),
        FanJobOperation("index", "indexing", ("base",)),
        FanJobOperation("blade-1", "freeform", ("index",)),
        FanJobOperation("blade-2", "freeform", ("blade-1",)),
        FanJobOperation("blade-3", "freeform", ("blade-2",)),
        FanJobOperation("program", "postprocess", ("blade-3",)),
    )
    job = FanManufacturingJob("fan-job", _contract().semantic_sha256(), operations)
    assert job.topological_order() == tuple(item.operation_id for item in operations)
    assert job.affected_operations(("blade-2",)) == ("blade-2", "blade-3", "program")
    assert FanManufacturingJob.from_json(job.to_json()).semantic_sha256() == job.semantic_sha256()


def test_job_graph_rejects_missing_and_cyclic_dependencies() -> None:
    with pytest.raises(ValueError, match="missing dependencies"):
        FanManufacturingJob("job", "a" * 64, (FanJobOperation("base", "planar", ("lost",)),))
    with pytest.raises(ValueError, match="cycle"):
        FanManufacturingJob(
            "job",
            "a" * 64,
            (
                FanJobOperation("left", "path", ("right",)),
                FanJobOperation("right", "path", ("left",)),
            ),
        )


def test_cancelled_publication_keeps_previous_result() -> None:
    publication = FanJobPublication("old")
    publication.stage("candidate")
    publication.cancel()
    assert publication.published_sha256 == "old"
    with pytest.raises(ValueError, match="no candidate"):
        publication.commit()
