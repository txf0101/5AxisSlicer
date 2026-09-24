# Freeform Workbench Guide

Guide mode creates surface-conforming or thin-wall paths on one trimmed face or a finite set of up to 16 explicit faces, following up to 32 guide edge chains. Results can be checked, read back, saved, and reopened offline. Large jobs may take time; while a new result is Stale, do not export the previous path.

The left Manufacturing Setup panel edits the current machine, nozzle, material, and coordinates. It shares Common Setup by default. Choose **Import Common Setup into this Workbench** to create a Freeform-specific copy; **Save to Common Manufacturing Setup** publishes changes for other shared Workbenches. See the [click-through guide](quickstart_clickthrough_en.md#common-setup-and-workbench-specific-setup) for scope and save behaviour.

`Spherical Solid Fill`, `Surface Solid Fill`, and `Radial Solid Fill` require their respective explicit roles and references. This guide covers finite guide mode; see the [Workbench click-through guide](quickstart_clickthrough_en.md#5-freeform-surfaces-and-solids) for solid modes and [solid-growth method guide](solid_fill_method_en.md) for selection rules. See [multicolour setup](material_channels_en.md) for channels and stations. Reselect all geometry references when changing models; do not copy example IDs.

## Create an offline product

1. Open a STEP model and enter **Freeform Workbench**.
2. Choose **Surface** or **Thin Wall** as the new operation type, then scroll down and create it. When editing an existing operation, select it first; changing the new-operation type does not alter it.
3. Set Viewer selection to **Edge**, select guide edges, then **Face** and select the adjacent face. Click **Use selected Viewer edges** and check order, reverse flags, and face. Configure multiple guides in the guide JSON array.
4. The restricted face-group IDs must include the face referenced by each guide. References to faces outside the group are rejected.
5. If needed, edit the material table and tool-change station, then click **Apply**.
6. Click **Generate**. Hide the model to see occluded lines; use bead-width display to inspect local width. Warning can allow offline export after review; Error blocks export.
7. Export the six files: `main.gcode`, `toolpath.json`, `machine_axes.csv`, `warnings.json`, `preview.json`, and `manifest.json`.

![Freeform operation controls](assets/product_delivery/04_freeform_mode_zh.jpg)

The screenshot shows an existing radial-solid operation to explain the difference between operation selectors. For this guide's finite guide workflow, create Surface or Thin Wall. The screenshot has no generated path.

## Guide references and parameters

Each guide entry needs `edge_ids`, one `reversed_flags` value per edge, and `face_id`. Geometry references are saved with signatures. When the source changes, an unambiguous rebind may succeed; a failed rebind invalidates the operation, and even a successful rebind makes the old result Stale.

| Parameter | Unit | Purpose |
| --- | --- | --- |
| Arc-length sampling step | mm | Guide discretization spacing |
| Chord error | mm | Curve approximation error |
| Chain tolerance | mm | Continuity between guide edges |
| Bead width and layer height | mm | Deposition volume; layer height cannot exceed twice bead width |
| Lateral spacing and pass count | mm, count | Finite projected passes within trimmed faces |
| Layer count | count | Finite layers along the surface normal |
| Deposition/travel feed | mm/min | Toolpath and offline `G94` NC |
| Maximum adjacent normal change | rad | Exceeding it raises `freeform.normal_discontinuity` |

Changes to geometry, materials, Setup, parameters, or controller contract make the result Stale. Undo can restore the previous valid result; cancellation before publication preserves it. If export is disabled, check operation state and issues; a visible CAD model does not mean a path was generated.

### Solid modes: growth direction and material regions

For **Surface Solid Fill**, select the body, supporting face, opposite face, and root edge in the Viewer. Click **Build candidate from selected Viewer geometry** and verify each role. The **Surface-solid growth** selector appears for this operation type only. **Layers through surface thickness** keeps the original thickness-wise method. Choose **Grow outward from root edge** when a supported root edge is defined and layers should extend outward along the surface. Inspect first-bead support, layer-to-layer connection, and travel in the preview for either choice; see the [solid-growth method guide](solid_fill_method_en.md) for selection conditions.

Click **Apply** after choosing geometry and growth mode. To assign T0/T1 channels, open **Edit material table**, choose a body or stage in the region selector, click **Add selected region**, and set its Channel cell. Spherical solids and root-outward surface solids use stable body IDs where available; other modes show their applicable stage candidates. **Add manually (advanced)** remains available for custom paths. Apply again and generate. Temperatures, layer values, and station coordinates shown in examples are for those examples only; tune them for your material and equipment. See [multicolour setup](material_channels_en.md).

## Errors and limits

- `curve.offset_outside_face`: reselect an edge and face so the offset stays in the trimmed domain.
- `freeform.normal_discontinuity`: reduce the region, change guide, or verify face connectivity; do not hide a discontinuity by raising the threshold.
- `material.region_unassigned`: assign every guide/pass region explicitly.
- Axis-limit or cumulative-C errors block export. Unknown cumulative C limits remain an offline Warning.
- Any strict readback mismatch in modes, axes, feed, relative E, events, or command stream invalidates the product.

The algorithms support finite explicit face groups and guide chains. They do not perform arbitrary mesh parameterization, automatic pattern recognition/material zoning, complex self-intersection repair, or production collision proof. Controller and macro versions, coordinated XYZAC semantics, rotary centre, offsets, cumulative C limits, complete tool envelope, and temperature control require on-site evidence. Warning results are for offline review.
