from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.manufacturing.toolpath import (  # noqa: E402
    GeneratedResultManifest,
    GeneratedResultStatus,
    GeneratedToolpath,
    GeneratedToolpathError,
    SourceFingerprint,
    ToolpathEvent,
    ToolpathPoint,
)


HASH = "a" * 64


def sample_point(point_id: str = "p-1") -> ToolpathPoint:
    return ToolpathPoint(
        point_id=point_id,
        position=(1.0, 2.0, 3.0),
        surface_normal=(0.0, 0.0, 2.0),
        tangent=(2.0, 0.0, 0.0),
        nozzle_axis=(0.0, 0.0, -5.0),
        feedrate_mm_min=1200.0,
        bead_width_mm=0.6,
        layer_height_mm=0.2,
        material_volume_mm3=0.12,
        operation_id="tube-op-1",
        stage_id="segment-1",
        layer_id="layer-1",
        region_id="outer-wall",
        point_type="deposition",
        extrusion_role="thin_wall",
    )


def sample_toolpath(*, include_second_point: bool = False) -> GeneratedToolpath:
    points = (sample_point(),)
    if include_second_point:
        points += (
            ToolpathPoint(
                point_id="p-2",
                position=(2.0, 2.0, 3.0),
                tangent=(1.0, 0.0, 0.0),
                nozzle_axis=(0.0, 0.0, -1.0),
                feedrate_mm_min=900.0,
                bead_width_mm=0.5,
                layer_height_mm=0.2,
                material_volume_mm3=0.1,
                operation_id="tube-op-1",
                stage_id="segment-1",
                layer_id="layer-1",
                region_id="outer-wall",
                point_type="deposition",
                extrusion_role="thin_wall",
            ),
        )
    return GeneratedToolpath(
        toolpath_id="toolpath-1",
        operation_id="tube-op-1",
        points=points,
        events=(
            ToolpathEvent(
                event_id="event-1",
                event_type="retract",
                operation_id="tube-op-1",
                stage_id="segment-1",
                duration_s=0.25,
                context={"reason": "safe_indexing"},
            ),
        ),
    )


class ToolpathContractTests(unittest.TestCase):
    def test_generated_manifest_round_trip_preserves_public_payload(self) -> None:
        manifest = GeneratedResultManifest(
            result_id="result-1",
            operation_id="tube-op-1",
            status=GeneratedResultStatus.READY,
            algorithm_version="tube-indexed-baseline.v1",
            parameter_semantic_sha256=HASH,
            input_sources=(
                SourceFingerprint(
                    source_id="pipe2-step",
                    sha256=HASH,
                    role="cad_model",
                    path="example/pipe2/弯管新.stp",
                ),
            ),
            machine_profile_id="builtin.machine.generic_xyzac_reference.v1",
            ready_for_export=True,
            toolpath=sample_toolpath(),
        )

        payload = json.loads(json.dumps(manifest.to_json(), ensure_ascii=False))
        restored = GeneratedResultManifest.from_json(payload)

        self.assertEqual(restored, manifest)
        self.assertEqual(restored.toolpath.coordinate_frame, "workpiece_build")
        self.assertEqual(restored.toolpath.points[0].tangent, (1.0, 0.0, 0.0))
        self.assertEqual(restored.toolpath.points[0].nozzle_axis, (0.0, 0.0, -1.0))

    def test_non_deposition_point_cannot_carry_material(self) -> None:
        with self.assertRaisesRegex(GeneratedToolpathError, "non-deposition"):
            ToolpathPoint(
                point_id="travel-1",
                position=(0.0, 0.0, 0.0),
                tangent=(1.0, 0.0, 0.0),
                nozzle_axis=(0.0, 0.0, -1.0),
                operation_id="tube-op-1",
                stage_id="segment-1",
                layer_id="layer-1",
                region_id="outer-wall",
                point_type="travel",
                material_volume_mm3=0.1,
            )

    def test_exportable_result_requires_ready_status_and_points(self) -> None:
        with self.assertRaisesRegex(GeneratedToolpathError, "only ready or warning"):
            GeneratedResultManifest(
                result_id="result-1",
                operation_id="tube-op-1",
                status="draft",
                algorithm_version="tube-indexed-baseline.v1",
                parameter_semantic_sha256=HASH,
                input_sources=(),
                machine_profile_id="builtin.machine.generic_xyzac_reference.v1",
                ready_for_export=True,
                toolpath=sample_toolpath(),
            )

        with self.assertRaisesRegex(GeneratedToolpathError, "at least one toolpath point"):
            GeneratedResultManifest(
                result_id="result-2",
                operation_id="tube-op-1",
                status="ready",
                algorithm_version="tube-indexed-baseline.v1",
                parameter_semantic_sha256=HASH,
                input_sources=(),
                machine_profile_id="builtin.machine.generic_xyzac_reference.v1",
                ready_for_export=True,
                toolpath=GeneratedToolpath("empty", "tube-op-1"),
            )

    def test_toolpath_rejects_duplicate_point_ids(self) -> None:
        with self.assertRaisesRegex(GeneratedToolpathError, "duplicate point_id"):
            GeneratedToolpath(
                toolpath_id="toolpath-1",
                operation_id="tube-op-1",
                points=(sample_point(), sample_point()),
            )

    def test_generated_path_adapts_to_existing_preview_segments(self) -> None:
        (segment,) = sample_toolpath(include_second_point=True).to_preview_segments()

        self.assertEqual(segment.start, (1.0, 2.0, 3.0))
        self.assertEqual(segment.end, (2.0, 2.0, 3.0))
        self.assertEqual(segment.move_type, "extrude")
        self.assertEqual(segment.extrusion_role, "external_perimeter")
        self.assertEqual(segment.coordinate_transform, "workpiece_build")
        self.assertEqual(segment.delta_e, 0.1)

    def test_analytic_tube_truth_is_machine_readable_and_self_consistent(self) -> None:
        fixture_path = ROOT / "tests" / "fixtures" / "analytic_tube_truth.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))

        straight = payload["cases"]["straight_tube"]
        self.assertEqual(straight["expected"]["centerline_length_mm"], 100.0)
        self.assertEqual(straight["expected"]["end_point_mm"], [0.0, 0.0, 100.0])

        arc = payload["cases"]["circular_arc_tube"]
        expected_length = arc["parameters"]["centerline_radius_mm"] * math.radians(
            arc["parameters"]["sweep_angle_deg"]
        )
        self.assertAlmostEqual(arc["expected"]["centerline_length_mm"], expected_length, 12)
        self.assertEqual(arc["provenance"]["derived_from"], "analytic_parameters")


if __name__ == "__main__":
    unittest.main()
