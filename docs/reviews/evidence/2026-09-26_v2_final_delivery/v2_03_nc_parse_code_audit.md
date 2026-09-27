# V2-03 NC parsing code audit

2026-09-27. Read-only source inspection during the live GUI load. No timing run, load test, Qt operation or production edit was performed. Therefore this report identifies likely work reduction, not a measured attribution of the observed 1–2 minute load time.

## Main repeated work

`gcode_parser._append_motion` calls `preview_kinematics.reconstruct_preview_motion` once per parsed motion. That function calls `_machine_to_workpiece_transform` independently for both start and end, even when their rotary values are identical. Each call decodes the controller axes, invokes `MachineProfile.link_transform`, which invokes `forward_kinematics`, which validates the entire machine profile and constructs transforms for every link in both machine chains, then inverts the requested workpiece transform. For the reported 91,516 motions this permits roughly 183,032 full transform evaluations, even though Indexed deposition repeats one A/C pose across many points. This is the strongest static optimization candidate.

Minimal optimization: keep a bounded, parser-session-local cache of the workpiece inverse transform keyed by the actual registered semantics/profile identity and exact normalized rotary values. Reuse start/end at identical poses and the preceding end as the following start. Retain controller-word validation, active/present-word distinction, unsupported-axis errors, zero offsets, axis-word decoding, machine limits and file-wide fallback. Do not round rotary angles or replace a general registered profile with a hardcoded AC formula. Keep tool-length and per-point material-center offsets outside a pose-only cache, or explicitly include their inputs if caching complete reconstructed points. Avoid an unbounded cache for continuous-rotation files.

`ControllerAxisSemantics.controller_word_map` builds a new dictionary and MappingProxyType on every property access; `supported_rotary_words` repeats it. The reconstruction path asks for this more than once per motion. A prepared immutable per-session mapping is a smaller improvement, subordinate to transform reuse.

## Indexed metadata

`IndexedPreviewMetadata.comment` parses one small JSON object per metadata line and validates three numeric fields plus height/offset consistency. Its work is linear in source bytes; no history scan or growing-list lookup was found. `motion` consumes one pending record in constant time. `material_preview_positions` performs two fixed-length vector additions. These semantics should remain strict: declaration required, no missing/unconsumed point record, no malformed dimensions, and no unknown-kinematics reconstruction.

After metadata handling, `_apply_comment_tag` still applies generic type/width/height/layer matching and `_role_from_comment_hint` regex cleanup to an already recognized INDEXED_TUBE_POINT JSON comment. An explicit handled result could bypass irrelevant generic comment processing without bypassing metadata validation. This is a secondary optimization and requires role/modal regression tests.

## Complexity and cancellation

The inspected parser has linear passes over motions for `_file_rotary_words`, `_apply_file_coordinate_result`, and `_PreviewStats.finalize_coordinate_result`; these are O(N), not O(N²). The machine's repeated full-chain work depends on joint count, which is fixed and small for this profile. No motion-count-squared operation was found in the scoped files. This does not exclude costs in render-index construction, cache serialization or VTK outside this audit.

`parse_lines` checks cancellation at line 1 and each 4,096 lines. Final coordinate-policy scans, coordinate reassignment and bounds recomputation then run without internal cancellation polling; cancellation is checked after all finalization. Preserve the final all-file coordinate decision, but add bounded cancellation checks to those loops if measured cancellation latency requires it. Progress should describe finalization separately rather than claiming completion before those passes finish. Avoid per-line GUI signal emission.

## Validation needed before accepting an optimization

Use identical legacy and explicit Indexed NC inputs to compare complete motion coordinates, raw machine coordinates, per-point width/height, issue codes, modal behavior and file-wide unsupported-word fallback. Include repeated A/C poses, changing poses, nonzero tool length, changing material offsets, zero-valued U/V/W and invalid metadata. Measure cancellation during parsing and finalization. Time parse/reconstruction, cache and render-index stages separately only after the live GUI evidence run finishes. A speedup claim requires those measurements; this static audit makes none.
