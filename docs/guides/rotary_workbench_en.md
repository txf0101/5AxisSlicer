# Rotary Workbench Guide

Rotary supports fixed-axis deposition on cylindrical or conical surfaces: Spiral, Thin Wall, and Around Part. Complete Setup and explicitly select the axis, surface, and any profile geometry. Numeric axis values alone are not sufficient to establish the geometric reference. Geometry references are saved with signatures; topology changes require an unambiguous rebind or a new selection.

The left Manufacturing Setup panel shares Common Setup by default. Use **Import Common Setup into this Workbench** to create a Rotary-specific copy. See the [click-through guide](quickstart_clickthrough_en.md#common-and-workbench-specific-settings) for scope and persistence.

## Axis, angle, and operations

Choose an axis edge and apply it, then choose the coaxial cylindrical/conical face and apply it. Define a zero-angle direction perpendicular to the axis. Rotary phase is continuous and may span multiple revolutions; intervals crossing zero are unwrapped in travel direction. Specify nonzero angular intervals and an explicit CW/CCW direction.

- **Spiral** winds around the selected surface while advancing by pitch per revolution. The total pitch travel must fit the axial profile and must not cross a degenerate cone apex.
- **Thin Wall** generates finite radial passes. The interval must cover one full turn (360°); pass widths and spacing must fit the target wall thickness. A reduced bead width may produce a Warning where enabled.
- **Around Part** creates one or more directed angular regions. Use semicolon-separated non-overlapping intervals, including intervals across the cycle boundary where needed.

![Around Part path regions](assets/product_delivery/09_rotary_around_part_paths_zh.png)

The displayed `350:20;120:210` cylindrical regions are an example only. Reselect references and angles for your own part.

## Parameters

Interface defaults and screenshot values are for learning only. Recalculate them for the machine, nozzle, material, part, and trial results.

| Parameter | Example default | Rule |
| --- | ---: | --- |
| Pitch | 5 mm/rev | Positive; Spiral only |
| Direction | CCW | Spiral/Thin Wall start direction; Thin Wall alternates later passes |
| Start/end angle | 0°/360° | Must differ; UI uses degrees, stored as radians |
| Rotary angular speed | 0.5 rad/s | Positive; combines with linear feed for segment timing |
| Angular sampling step | 5° | Positive; affects chord error, point count, interpolation |
| Bead width/layer height | 0.6/0.2 mm | Positive; used in offset and material volume |
| Deposition/travel feed | 900/1800 mm/min | Positive; deposition and safe travel timing |
| Retract | 1 mm | Nonnegative; explicit Retract/Prime events |
| Dwell | 0 s | Only zero is supported; nonzero raises `rotary.dwell_unsupported` |
| Axial step | 2 mm | Positive; Thin Wall/Around Part, endpoint included |
| Radial passes/spacing | 1 / 0.6 mm | Thin Wall only; 1–100 passes |
| Target wall thickness | 0.6 mm | Must fit effective bead width and radial passes |
| Insufficient bead-width policy | error | `error` blocks generation; `reduce` reduces width and warns |
| Safe connection gap | 1 mm | Positive; radial departure between passes/regions |

## Generation states and recovery

Apply geometry and parameters, then **Generate and Validate**. Cancel preserves the previous valid product.

| State | Meaning | Export |
| --- | --- | --- |
| Draft | Operation or Setup not applied | Disabled |
| Ready | Path, machine trajectory, offline checks, and readback passed | Available |
| Warning | No blocking Error; review warnings | Available with warnings |
| Error | Planning, IK/FK, limits, motion, collision, or readback failed | Disabled |
| Stale | Inputs changed or project reopened without runtime product | Disabled; regenerate |

For invalid axis or zero direction, reselect a valid reference. `rotary.surface_reference_invalid` means the selected face is not cylindrical/conical. `rotary.period_ambiguous` requires a clear direction and nonzero interval. `rotary.pitch_exceeds_profile` requires fewer turns, smaller pitch, or a suitable surface. Avoid a cone apex. For thin-wall width/pass errors, adjust target thickness or passes. Around Part region overlap/empty errors require non-overlapping directed intervals. Unreachable orientation requires checking Build CS, placement, machine limits, and path direction. Velocity/acceleration errors require appropriate feed or angular-speed changes. Nozzle/fixture or nozzle/deposit collisions require review of the actual geometry, setup, regions, order, and gap; never downgrade collision severity to enable export.

## Export and qualification boundary

Allowed results export the six files: `main.gcode`, `toolpath.json`, `machine_axes.csv`, `warnings.json`, `preview.json`, and `manifest.json`. NC uses the registered controller semantics, mapped rotary axis words, and G93 inverse-time coordinated motion where required. Strict readback checks points, axes, F/E, and events.

Projects save operations and stable references; after reopen, regenerate before export. Script and HTTP interfaces use the same command kernel as the UI. Generic XYZAC, offline IK/FK, axis and motion limits, conservative collision interfaces, readback, and Viewer are offline checks. Real controller semantics, machine calibration, complete fixture/nozzle collision checks, and trial printing require on-site qualification.
