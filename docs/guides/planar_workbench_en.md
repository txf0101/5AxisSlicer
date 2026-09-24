# Planar Workbench Guide

Planar supports Region section preview, Zigzag Fill, Offset Fill, Thin Wall, Spiral, and buildplate-only vertical supports. Complete Part, coordinates, machine, nozzle, reviewed material, and placement before generating paths. Changes to STEP or Setup make prior results Stale. Error blocks export; review each Warning.

The left Manufacturing Setup panel edits shared settings by default. Choose **Import Common Setup into this Workbench** for a Planar-specific copy. See the [click-through guide](quickstart_clickthrough_en.md#common-and-workbench-specific-settings) for saving and publishing settings.

Zigzag checks bead-width envelope, material by region, and uncovered areas. Smaller line spacing may overfill; larger spacing may leave gaps. Use section preview and issues to judge coverage. Spiral uses finite sampling of the actual solid at intermediate Z. Support checks motion against the target CAD, but joint per-layer support scheduling and complete nozzle swept volume are not qualified.

## Create an operation

Open **Planar Slicing**, create Region, Zigzag, Offset, Thin Wall, Spiral, or Support, select the body, set parameters, and click **Apply**. Region displays sections, holes, and islands but cannot generate NC or export the six-file package. The other five operations use the common Toolpath, machine-axis, validation, postprocessing, and G-code readback chain.

![Planar path with the model hidden](assets/product_delivery/07_planar_full_lines_zh.png)

This one-layer screenshot uses `body_001` at Z=0.2 mm. Other practice settings use a different body and Z; do not mix or copy case values. Show the model to check placement, then hide it and choose **Full lines (fast)** for all paths or **Bead width** for width inspection.

## Parameters and units

Lengths are mm and feed is mm/min. Sectioning uses Workpiece Build-XY semantics. Body is required. Last-layer Z cannot be below first-layer Z. Spiral requires at least two adjacent layers. Support requires `first_layer_z_mm = layer_height_mm`, so its first deposition plane is one layer above Build Z=0.

Layer height and bead width must be positive and satisfy the current aspect-ratio constraint. Feed and travel feed are positive; retract is nonnegative. Zigzag line spacing must be positive. Offset pass count and Thin Wall maximum passes control finite coverage; narrow or disappearing regions remain diagnosed. Spiral samples per contour controls sampling density. Support overhang angle is strictly between 0° and 90°. Support XY/Z gaps must be nonnegative. Support line spacing and interface spacing are positive; interface layers range 0–100. Pattern is `Lines` or `Grid`; Grid alternates orthogonal Lines between layers and does not cross-extrude within a layer.

## Generate, inspect, and recover

Apply changes, then generate preview. Inspect the body, layers, holes, coverage, and path. Changes to geometry, coordinates, or resources make the result Stale and require regeneration. Cancel preserves the previous valid result.

| Issue/state | Meaning and response |
| --- | --- |
| `planar.spiral_layers_insufficient` | Spiral needs at least two adjacent layers; increase the range and regenerate. |
| `planar.coverage_residual_high` Warning | Review wall thickness, bead width, pass count, and region; adjust if fuller coverage is required. |
| `planar.spiral_discrete_layer_projection_only` Warning | Review maximum projection deviation and preview; this is not continuous-solid qualification. |
| `xyzac.rotary_singularity` Warning | Review `warnings.json` and machine limits; it does not qualify a real controller. |
| Setup/parameter/motion Error | Correct the indicated field or motion issue; export remains disabled until resolved. |
| Stale | Regenerate after changing inputs. |
| Cancelled | Previous Ready result remains; verify inputs before trying again. |

Allowed results export `main.gcode`, `toolpath.json`, `machine_axes.csv`, `warnings.json`, `preview.json`, and `manifest.json`. Review readback, warnings, path placement, and coverage. Support is limited to vertical supports connected to the build plate, using Lines/Grid with body and interface layers. Offline checks and reference XYZAC do not establish real-machine collision safety or print qualification.
