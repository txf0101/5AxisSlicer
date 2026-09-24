# 5AxisSclicer V2.0 Learning Manual

This course teaches a repeatable offline workflow: inspect geometry, assign roles, establish Setup, choose a Workbench, generate, inspect, read back, export, save, reopen, and transfer the method to a new part. Example models, IDs, coordinates, dimensions, axis ranges, and settings are practice material only. Re-select and measure for your own machine and part.

Start from the [click-through guide](quickstart_clickthrough_en.md) for a first operation. Use the [guide index](README.md) for Workbench and reference topics. `run_app.py` and `scripts/run_app.ps1` are the project launch entry points.

## Learning route

| Lesson | Topic | You should be able to |
| --- | --- | --- |
| L01 | Interface, project, Viewer | Locate Workbench, operation tree, editor, Viewer, issues, and file preview. |
| L02 | CAD objects and references | Distinguish body, face, edge, and vertex; assign Part and explain each selected role. |
| L03 | Setup and coordinates | Complete Part, Machine, Nozzle/Material, Model CS, Build CS, and Placement without guessing unknown values. |
| L04 | Workbench choice | Match geometry and process intent to Planar, Curve, Rotary, Tube, or finite Freeform. |
| L05 | Operations and parameters | Create an operation and distinguish geometry, process, motion, and inspection inputs. |
| L06 | Generation and recovery | Interpret Ready, Warning, Error, and Stale; correct inputs and regenerate. |
| W01–W05 | Workbench specialization | Complete a practice case and a migration case in one selected Workbench. |
| L07 | Viewer and NC readback | Cross-check model frame, machine frame, deposition, travel, events, and source code. |
| L08 | Export and project lifecycle | Explain all six exported files and save/reopen a project. |
| L09 | Transfer to your part | Build a new workflow without copying example IDs or values. |

## Choose a Workbench

| Question | Consider | Do not force it when |
| --- | --- | --- |
| Can the part be represented by planar sections? | Planar | Build direction must change continuously. |
| Is deposition defined by an ordered STEP edge chain? | Curve | The process needs a whole surface or volume fill. |
| Can the region be expressed by a fixed axis and coaxial cylinder/cone? | Rotary | The tube centreline changes spatially. |
| Is it one tube with a constant circular section? | Tube | It branches, changes section, or has arbitrary sections. |
| Is there a finite trimmed face group and explicit guide chain? | Freeform | Global surface recognition or arbitrary mesh parameterization is needed. |
| Do you only have external NC to inspect? | G-code File Preview | You need to generate or qualify a path. |

Similar-looking geometry can imply different manufacturing intent. Record why a Workbench fits and what condition would make it unsuitable.

## Inputs and result states

Geometry inputs include bodies, faces, edges, regions, and ports. Process inputs include bead width, layer height, spacing, pass count, and material region. Motion inputs include feed, clearance, retract, pose, and angular speed. A change to geometry, process, motion, Setup, or controller semantics makes the generated product Stale. View, camera, visibility, and layer filters normally affect display only.

| State | Meaning | Next action |
| --- | --- | --- |
| Draft / unapplied | Editor values are not in project state | Apply or discard draft |
| Ready | Current offline generation and checks pass | Inspect Viewer and readback |
| Warning | Result exists but needs human review | Review every issue; do not treat as production qualification |
| Error | Generation or validation failed | Resolve cause; export is disabled |
| Stale | Geometry, parameters, material, Setup, or controller changed | Regenerate; do not use old export qualification |

Cancel should preserve the prior valid result. A visible model or successful preview alone does not prove that a manufacturing path was generated.

## Inspect and export

Compare the selected geometry, generated path, machine-axis trajectory, issues, and NC source. Check coordinate frames, direction, coverage, travel, events, F/E values, and controller axis words. Where a transform depends on controller semantics, keep the raw machine-coordinate fallback available.

An allowed result contains six files:

| File | Minimum review |
| --- | --- |
| `main.gcode` | Modes, axis words, E/F, events, and ending state |
| `toolpath.json` | Points, layers, regions, materials, and source |
| `machine_axes.csv` | Axis range, continuity, and units |
| `warnings.json` | Disposition or reason to retain each warning |
| `preview.json` | Source frame and segment counts |
| `manifest.json` | Hashes, status, readback, and `machine_executable` |

Export only when the operation allows it. Choose a dedicated empty output folder. Save the project and reopen `project.json`; runtime results become Stale and need regeneration.

## Migration checklist

1. Identify the actual bodies, faces, edges, ports, and material regions in the new STEP.
2. Measure or obtain machine, nozzle, material, coordinate, fixture, and controller data. Leave unknown values unresolved.
3. Choose the Workbench from geometry and deposition intent; record rejection conditions.
4. Start with a small, inspectable operation. Check geometry references, path direction, coverage, motion, and warnings.
5. Regenerate after any semantic input changes, then inspect strict G-code readback and all six outputs.
6. Save/reopen the project and record any remaining unknown qualification items.

The software's offline output does not establish real-machine readiness. Verify controller and macro versions, calibrated axes, rotary centre and offsets, fixtures, full tool sweep, material suitability, sensors, collision safety, and trial-print results on the actual equipment. `machine_executable=false` means device-specific automated qualification is incomplete. Research is unavailable; use a supported Workbench.
