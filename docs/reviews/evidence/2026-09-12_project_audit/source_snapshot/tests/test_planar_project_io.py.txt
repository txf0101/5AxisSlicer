"""Default project IO loaders for Planar and Tube operation definitions."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.planar_parameters import (
    PlanarOperationDefinition,
    PlanarProcessParameters,
)
from five_axis_slicer.manufacturing.setup import TubeOperationDefinition
from five_axis_slicer.manufacturing.tube_parameters import TubeBuildupOperationConfig
from five_axis_slicer.models import SelectionState
from five_axis_slicer.project_io import load_project, save_project


def test_default_loader_round_trips_planar_operation(tmp_path: Path):
    operation = PlanarOperationDefinition(
        "planar-1",
        "setup-1",
        name="Floor",
        parameters=PlanarProcessParameters(
            offset_pass_count=5,
            wall_thickness_mm=1.2,
            thin_wall_max_passes=2,
            spiral_samples_per_contour=80,
        ),
    )
    project_json = save_project(
        tmp_path / "planar-project", None, SelectionState(), operations=(operation,)
    )

    loaded = load_project(project_json)

    assert loaded.operations == (operation,)
    assert isinstance(loaded.operations[0], PlanarOperationDefinition)


def test_default_loader_still_reads_tube_buildup_operation(tmp_path: Path):
    operation = TubeOperationDefinition(
        "tube-1",
        "setup-1",
        operation_type="tube_buildup",
        type_config=TubeBuildupOperationConfig(
            maximum_pass_spacing_mm=0.4, include_planar_base=True, base_order="after_tube"
        ),
    )
    project_json = save_project(
        tmp_path / "tube-project", None, SelectionState(), operations=(operation,)
    )

    loaded = load_project(project_json)

    assert loaded.operations == (operation,)
    assert isinstance(loaded.operations[0], TubeOperationDefinition)
    assert loaded.operations[0].type_config == operation.type_config
