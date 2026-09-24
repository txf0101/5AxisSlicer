# Tube Setup: Coordinates and Placement

This guide covers Part, machine, nozzle, material, coordinate frames, and fixture placement in Common Manufacturing Setup. After setup, choose an operation in Tube Workbench. Generic XYZAC is for offline validation only; it does not replace real-machine calibration or qualification.

## Open Setup and use the Viewer

Import STEP in the app, then click **Common Manufacturing Setup**. In Tube Workbench, you can also select Setup nodes in the left tree. After setup, return to Workbench and choose Tube.

| Mouse action | Result |
| --- | --- |
| Short left-click on body, face, edge, or vertex | Selects geometry of the current pick type |
| Short left-click in empty space | Clears selection |
| Left drag | Rotates view |
| Middle/right drag | Pans in screen plane |
| Wheel | Zooms around the cursor's focal plane |

`F` fits the view, `H` resets it, and `Esc` clears selection. Dragging controls the camera; objects cannot be dragged directly. A movement beyond the system drag threshold is not treated as a pick.

## Assign Part and resources

Recommended order: **Part → Machine → Model CS → Build CS → Placement**.

In **Part**, mark each closed solid used in manufacturing as Part, then confirm. Leave unrelated geometry unassigned or ignored. Sheets and shells are not valid Part solids. In the pipe example, the base and tube are both part of the same build.

Select and apply a Machine Profile before Placement; it supplies bed mount positions. `Cartesian Reference` and `Generic XYZAC Reference` are reference machines and retain Warnings. A real machine needs calibrated configuration.

Nozzle and Material affect Setup readiness. A nozzle needs its mounting interface, measured overall length, and collision profile. Built-in 0.4, 0.6, and 0.8 mm entries provide identity only. A material needs its review acknowledgement. If measured data is missing, keep Setup not ready rather than guessing.

Measure nozzle length along its axis from the tip (`Z=0`) to the farthest mounting end in +Z. The R–Z collision outline is retained from the profile; if missing, an approximate axisymmetric shape may be generated from bore diameter and total length. This does not replace measured geometry or complete tool-sweep and collision qualification. If changing total length, remove the prior outline, apply, enter the measured length, then generate a matching simplified outline; this discards the prior profile shape. Outline radius and Z must be finite and nonnegative, start at tip Z=0, increase in Z, and end at the total length. Tip outer radius cannot be smaller than the bore radius.

## Define Model CS and Build CS

For each frame, confirm origin, Z direction, and X direction separately, then Apply. You can enter values or pick geometry. X/Z cannot be zero or collinear. Model CS numeric input is relative to STEP Source CS; Build CS numeric input defaults to Model CS and is converted to Source CS for storage.

The app projects X onto the plane normal to Z and forms a right-handed frame with `Y = Z × X`. Zero vectors, collinear X/Z, non-finite values, scale, or shear prevent application.

## Set Placement

After Machine and Build CS are valid, choose a bed mount. Enter `DX/DY/DZ` in mm and `RX/RY/RZ` in degrees if measured adjustments are needed, then Apply. Transform order is translation, `Rx`, `Ry`, `Rz`. Keep all six values at zero when no measured offset is available.

An empty mount list usually means no machine has been applied or the selected profile has no mounts.

## Check, save, and reopen

**Coordinates Valid** requires valid Part, Machine, Model CS, Build CS, and Placement. **Setup Ready** also requires a complete nozzle, reviewed material, and no Error. Reference-machine Warnings remain visible and require review.

Save the project to a dedicated folder. It stores `project.json`, an authoritative STEP copy, resource snapshots, frames, mount, and placement. On reopen, select `project.json`. The project copy is used normally; the original STEP path is only used for an explicit update from source.

| Problem | Action |
| --- | --- |
| Setup nodes are not visible | Open Common Manufacturing Setup and select a node in the left tree. |
| Create Tube operation is disabled | Check existing operations and allowed operation count for current Setup. |
| No mount is available | Apply a Machine Profile that includes mounts. |
| Frame cannot be applied | Confirm all three references; remove zero vectors and collinear X/Z. |
| Click rotates instead of selecting | Keep the pointer still for a short click; movement past the drag threshold is a drag. |
| Coordinates valid but Setup not ready | Check nozzle interface/length/outline and material review. |
