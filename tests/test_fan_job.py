from __future__ import annotations

from dataclasses import replace

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
    assert not restored.offline_ready
    assert "wall_count: missing source" in restored.provenance_issues
    assert not restored.machine_ready
    assert restored.parameters == FanProcessParameters()


def _sourced_contract() -> FanManufacturingContract:
    contract = _contract()
    return replace(
        contract,
        parameter_sources={
            name: SourcedValue(value, ParameterSource.ENGINEERING_DEFAULT, "test fixture")
            for name, value in contract.parameters.to_json().items()
        },
    )


def test_parameter_edit_invalidates_provenance_until_source_is_updated() -> None:
    contract = _sourced_contract()
    assert contract.offline_ready
    edited = replace(contract, parameters=replace(contract.parameters, layer_height_mm=0.3))
    restored = FanManufacturingContract.from_json(edited.to_json())
    assert not restored.offline_ready
    assert restored.provenance_issues == ("layer_height_mm: source value differs from parameter",)
    sources = dict(restored.parameter_sources)
    sources["layer_height_mm"] = SourcedValue(0.3, ParameterSource.USER, "fixture revision")
    assert replace(restored, parameter_sources=sources).offline_ready
    assert contract.semantic_sha256() != edited.semantic_sha256()


def test_completion_flag_cannot_replace_measurement_records() -> None:
    contract = replace(_sourced_contract(), machine_measurements_complete=True)
    assert not contract.machine_ready
    sources = dict(contract.parameter_sources)
    for name in ("nozzle_envelope", "machine_zero", "controller_macro_version"):
        sources[name] = SourcedValue({"fixture": 1}, ParameterSource.MEASURED, "fixture record")
    recorded = replace(contract, parameter_sources=sources)
    assert recorded.machine_ready
    sources["machine_zero"] = SourcedValue(None, ParameterSource.PENDING_MEASUREMENT)
    assert not replace(recorded, parameter_sources=sources).machine_ready


@pytest.mark.parametrize(
    "source, expected",
    [
        (SourcedValue(0.2, ParameterSource.PENDING_MEASUREMENT), "pending measurement"),
        (SourcedValue(0.2, ParameterSource.ENGINEERING_DEFAULT), "missing source reference"),
    ],
)
def test_unverified_source_does_not_qualify_contract(source, expected) -> None:
    contract = _sourced_contract()
    sources = dict(contract.parameter_sources)
    sources["layer_height_mm"] = source
    candidate = replace(contract, parameter_sources=sources)
    assert candidate.provenance_issues == (f"layer_height_mm: {expected}",)
    assert not candidate.offline_ready


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
