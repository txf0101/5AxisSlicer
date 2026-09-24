# G-code File Preview Guide

This guide covers opening NC/G-code, overlaying STEP geometry, inspecting paths, and locating source lines. Preview is for offline inspection; settings and results must be qualified on the user's equipment.

## Open a file

From the Workbench, choose **G-code File Preview** or **Open Existing G-code…** and select `.gcode`, `.nc`, `.tap`, or `.txt`. You can also launch with a file:

```powershell
python -m five_axis_slicer.app --gcode "example\pipe2\弯管.gcode"
```

To open the file preview with both STEP and G-code:

```powershell
python -m five_axis_slicer.app --results --model "example\叶轮\叶轮.stp" --gcode "example\叶轮\叶轮完整.gcode"
```

Paths generated in a Workbench should first be inspected there. To inspect the exported code in this page, export it and open `main.gcode`. G-code can be viewed without a model; open the matching STEP when checking path placement. Keep the source of historical or external code clear; its appearance does not establish how it was generated.

![G-code file preview](assets/product_delivery/10_gcode_file_preview_zh.jpg)

The screenshot contains G-code only. The “No STEP model loaded” message does not prevent path inspection. The program shown demonstrates the preview controls and is not a manufacturing qualification for the pipe example.

## Model, view, and path filters

Open STEP to overlay the model in the current coordinate context. Use **FIT** to frame all paths, the wheel to zoom, **ISO** or the orientation cube to change view. If the model hides inner or rear paths, clear **Show model** under scene visibility. Use **Full lines (fast)** for the whole route; **Bead width** is useful for local width inspection and may respond more slowly.

The X/Y/Z orientation marker at the lower left follows camera rotation. It indicates the viewing direction; it does not change model or machine coordinates. Check dimensions from both side and top views after using FIT.

- Stage Navigation: NC exported by this software can be viewed by operation. Legacy blade markers, when present, provide base/blade choices. Without markers, use layer ranges or progress. Once an operation is selected, the slider advances within that operation.
- Layer range or progress: limit the visible layers or path prefix.
- Travel: show or hide non-deposition moves such as retract, indexing, and approach.
- Extrusion: show or hide deposited material.
- Role colours: distinguish travel, deposition, retract, index, approach, and prime. Colours are diagnostic and do not represent machine or material colours.
- Progress and code context: select a progress point or source line to inspect the segment, layer, region, feed, and coordinates.

## Safe fallback for five-axis A/C transforms

The parser reconstructs coordinates only when controller semantics are known. If rotary-axis conventions, units, or axis mapping cannot be confirmed, it uses a safe fallback and preserves a transform marker. The inverse transform is for display and inspection; it is not inverse kinematics and does not prove collision safety. If orientation jumps, axis ranges look wrong, or the model and path do not align, return to machine coordinates and verify controller configuration, units, and modes such as G90/G91.

The bundled AC exporter records its machine profile and tool length. Preview uses both to recover the extrusion-tip position in part coordinates. For older `main.gcode` exports, keep the accompanying `manifest.json` in the same directory. If a standalone NC file does not declare tool length, verify that value and its coordinate convention before judging alignment against the STEP model.

## Example and troubleshooting

For `example/pipe2/弯管新.stp`, choose Tube Buildup, generate, open **View path**, choose **Full lines (fast)**, and hide the model. Inspect base coverage, wall continuity, and the inlet/outlet connection. The 0.6 mm bead width, 0.2 mm layer height, and 0.02 mm chord error shown in the example are practice values only. Set values for your own machine, nozzle, material, and accuracy needs.

The separate `example/pipe2/弯管.gcode` is historical input with an external/manual source. Compare source, layer order, travel, A/C range, and coverage separately; visual similarity alone does not establish equivalence.

| Symptom | Check |
| --- | --- |
| Model is missing | Confirm STEP path and units; use FIT/ISO; check whether only G-code was loaded. |
| Only a few outer lines are visible | Hide the model, enable extrusion, and check layer/progress filters. |
| View is slow | Use Full lines (fast), hide the model and pose aids, or narrow the layer range. |
| Path is offset from the model | Check Model/Build/machine frames, placement, and rotary-axis semantics; first fall back to source machine coordinates. |
| Travel or colours are missing | Check Travel, Extrusion, role legend, and layer range. |
| Code line and path disagree | Let indexing finish; reopen the unchanged file and verify its source hash. |
| Inverse transform looks wrong | Do not infer machinability; record controller semantics and inspect in original machine coordinates. |

Preview success means only that a file was read and displayed. Verify machine calibration, controller axis semantics, setup, path, and trial-print results before using equipment.
