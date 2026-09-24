# 5AxisSclicer V2.0

5AxisSclicer is a Windows desktop workbench for offline five-axis additive-manufacturing planning. It imports STEP/STP models, records manufacturing Setup, selects geometry for an operation, generates and previews paths, and exports G-code with a strict readback report. It is under active testing. Example values and print results depend on your own machine, nozzle, material, fixture, and trials.

Start with the [illustrated click-through guide](docs/guides/quickstart_clickthrough_en.md). The [learning manual](docs/guides/user_learning_manual_en.md) explains how to choose a method and transfer it to a different model. [All English guides](docs/guides/README.md#english-guides) cover the Workbenches, Setup, material channels, and file preview. [Example models and NC files](example/README.en.md) are practice inputs, not settings to copy to another part.

## Workbenches

| Workbench | Offline scope | Choose it when |
| --- | --- | --- |
| Planar | Region inspection, Zigzag, Offset, Thin Wall, Spiral, and build-plate-connected Grid/Lines support | The intended layers and paths are planar |
| Curve | Buildup, Multi-pass Buildup, and Offset Buildup | Deposition follows an ordered STEP edge chain |
| Rotary | Spiral, Thin Wall, and Around Part | Geometry follows a fixed cylindrical or conical axis |
| Tube | Indexed, Buildup, and Continuous | A single constant circular-section tube grows along a centreline |
| Freeform | Guide-based surface paths and explicitly assigned spherical, surface-solid, or radial-solid growth | The part requires a supported nonplanar layer family |

Research is unavailable in this version. A Workbench choice depends on support, growth direction, layer surfaces, nozzle orientation, and coordinate setup; visual similarity to an example is insufficient. The [solid-growth method guide](docs/guides/solid_fill_method_en.md) gives rejection conditions as well as suitable inputs.

## Install and launch

Python 3.10–3.12 is supported. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe run_app.py
```

Alternatively run `scripts/run_app.ps1`; its `-Python` option accepts the full path to a virtual-environment or Conda interpreter. For a bundled preview example, use `./scripts/run_app.ps1 -Demo`. Large example NC and intermediate data use Git LFS; run `git lfs pull` after cloning if those files are needed.

For each new model, open STEP/STP, complete **Common Manufacturing Setup**, choose a Workbench, assign its actual bodies/faces/edges, apply the operation, generate, and inspect the complete path. Shared Setup can be copied into one Workbench and later saved back to the common settings. Save the project separately from the export folder. Export a current Ready/Warning result to a new empty folder or a recognizable previous six-file output folder; do not select the project directory.

The six exported files are `main.gcode`, `toolpath.json`, `machine_axes.csv`, `warnings.json`, `preview.json`, and `manifest.json`. Error blocks export; Stale requires regeneration; every Warning needs review. Saved projects contain `project.json` and content-addressed source files. Reopen `project.json` to inspect the saved operation and Setup, then regenerate before exporting a new result.

## Machine and material boundary

The Generic XYZAC machine and the own-AC controller profile are offline references. A strict NC readback checks command order, axes, feed, extrusion, and events against the generated path. `machine_executable=false` means the program has not completed device-specific automated qualification. Before machine use, check controller commands and macros, rotary-axis meaning, coordinate offsets, actual nozzle and fixture geometry, travel limits, path safety, and test prints. Actual settings and print results follow the user's equipment trials; this project is being improved continuously.

Freeform supports explicit T0–T3 material-region assignments. A configured station can generate nozzle withdrawal, cutter travel and actuation, unload/load, purge, wipe, and return around an effective tool change. Initial T selection does not cut. Cutter commands and station coordinates must match the user's controller and machine; the example configuration remains offline-only. See [material channels](docs/guides/material_channels_en.md).

## Verification and developer entry points

Install development dependencies with `.\.venv\Scripts\python.exe -m pip install -e ".[dev,cad-tests]"`. Run `python scripts\check_quality.py` and `python -m pytest -q` in that environment. `run_app.py` and `scripts/run_app.ps1` are the desktop entry points; the installed `five-axis-slicer` command is also available.

Desktop shortcuts: `Ctrl+O` opens STEP/STP, `Ctrl+G` opens NC/G-code, `Ctrl+S` saves the project, `Ctrl+W` returns to the Workbench home, `F` fits the view, `H` resets it, and `Esc` clears selection. A short left click selects geometry in the active pick mode; left drag rotates, middle/right drag pans, and the wheel zooms around the pointer's focal plane. Dragging past the system threshold does not select on release.

HTTP automation listens on `127.0.0.1:8765` by default. Remote listening requires `-AllowRemoteAutomation` and a process-environment `FIVE_AXIS_SLICER_AUTOMATION_TOKEN` of at least 32 characters; restrict access to a trusted network and use a host firewall. For example, after launching the GUI:

```powershell
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/state
curl -Method POST http://127.0.0.1:8765/workbench/select -Body '{"key":"curve"}' -ContentType 'application/json'
```

The [developer documentation index](docs/README.md) links architecture, validation, and reference-source records.
