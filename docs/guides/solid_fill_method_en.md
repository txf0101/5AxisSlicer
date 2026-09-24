# Choose and Check a Solid-Growth Method

Choose an operation from the supporting base, growth direction, and family of layer surfaces. The [click-through guide](quickstart_clickthrough_en.md#5-freeform-surfaces-and-solids) shows the UI. Inspect paths, readback, and issues for every output; offline results do not qualify a real machine.

| Geometry and intent | Candidate operation | Inputs to reselect and verify | Unsuitable when |
| --- | --- | --- | --- |
| Constant circular-section tube growing along its centreline | Tube Buildup/Continuous, with Planar/CAD base | Tube, inlet/outlet, base, centreline direction, wall thickness, pass count | Branching, strongly varying section, or no single centreline |
| Raised solid on concentric spherical layers | Spherical Solid Fill | Sphere centre, base radius, solid group, radial thickness, hemisphere | General doubly curved surface or multiple centres |
| Stack layers through the thickness between supporting and opposite faces | Surface Solid Fill → Layers through surface thickness | Supporting face, opposite face, root edge, and thickness direction for each body | Intended growth is actually outward from the root; thickness layers lack support from the base |
| Grow outward over a surface from a supported root edge | Surface Solid Fill → Grow outward from root edge | Supporting face, opposite face, root edge, and root-to-base contact for each body | Branching surface, non-monotone distance field, multi-valued projection, incomplete root edge |
| Blades growing outward from a hub about a defined rotary axis | Radial Solid Fill | Hub, each blade body, root and outer faces, rotary centre/axis, allowed overlap | Hub support cannot be established, growth is not radial, or axis is unclear |

Visual similarity alone does not determine the method. Check the base, first-layer contact, layer family, growth direction, nozzle axis, and rotary motion relationship.

The **Surface-solid growth** selector appears in the Surface Solid Fill parameter area. After selecting bodies and root edges, decide whether material should grow through thickness or outward from the root, then click **Apply**. **Layers through surface thickness** remains the default for existing projects. For either choice, generate and inspect the full deposition and travel paths, issues, and NC readback; choosing a menu item alone does not qualify an output. For multicolour work, apply geometry first, then choose bodies or stages in the [material table](material_channels_en.md).

## Shared parameters

- Bead width determines finite material coverage; a CAD boundary alone is not a path centreline.
- Layer height can mean base Z layers, spherical radial layers, surface-thickness layers, or blade radial layers. The same label refers to different physical directions.
- Check path spacing in the physical metric of the relevant surface. A planar chart distance is not spherical surface length; general surfaces need an in-surface distance measure.
- Sampling step controls discretization. Do not reduce sampling density to bypass trimmed boundaries, self-intersections, or topology errors.
- Deposition, travel, retract, and clearance are represented as Toolpath events. Inter-operation transfers must not extrude.
- PLA 195/45 °C is example configuration only. Recalibrate for the actual material, nozzle, and machine.

## Checklist for each new model

1. Reselect bodies, faces, and edges by their actual roles; never copy example topology IDs.
2. Verify Source, Build, Workpiece, and Machine coordinate transformations are applied exactly once.
3. Check the full first-layer path against the actual deposited base and specify any permitted half-bead-width overlap.
4. Check layer spacing, maximum segment length, local support, shell/infill roles, and material volume by region.
5. Solve AC for all operations together; inspect singularities, limits, cumulative rotation, and non-deposition transfers.
6. Strictly read back the complete NC for coordinates, feed, extrusion, and event order. Generate review images from the readback path.
7. Report actual status for collisions, controller macros, calibration, dynamic limits, and trial prints. Items not performed must not be marked as passed.

## Common mistakes

- Holding a fan blade at fixed A=90° and stacking planar layers can start without support. The blade root needs finite-width contact along the hub, followed by the correct layer family.
- In the example fan STEP only, the blades and centre body have an approximately 0.5 mm CAD gap. Check the actual model and provide explicit overlap where required; the CAD root face alone is not proof of contact.
- More sample points do not create solid fill on spherical or general surfaces. Generate finite-width shells and internal paths.
- An old NC file's B axis and coordinate macros are uncalibrated assumptions. A new program must solve AC from nozzle orientation.
- Strict readback still requires checking the SHA-256 of the final saved files. Windows newline conversion can make an in-memory text hash differ from the saved file hash.

In Freeform, select the mode that matches the model, then assign bodies, faces, root edges, and rotary axis explicitly. Candidate selection only narrows the search; inspect the actual geometry in the Viewer. Do not infer a hub or base from maximum volume alone. If the UI reports `complete enabled operation`, check that the operation Setup matches the current completed Setup. For a new model, reselect roles and coordinates.
