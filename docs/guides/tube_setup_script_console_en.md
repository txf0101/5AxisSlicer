# Tube Setup Script Console

## Open the console and use the editor

In Tube Workbench, the Setup Script dock appears at the bottom. Its title-bar close button hides it; use **Tools > Setup Script** to show it again or **Tools > Collapse Setup Script** to collapse the content. Dock height is stored in local Qt settings, not the project.

- `Enter`: run the current command.
- `Shift+Enter`: insert a newline.
- `Ctrl+Enter`: run the script block.
- `Tab`: complete commands, resource IDs, mount IDs, or entity IDs.
- `Up`/`Down`: browse the last 200 inputs; `Ctrl+R` searches history.

Viewer shortcuts `F`, `H`, `Esc`, `Ctrl++`, and `Ctrl+-` are suspended while the console has focus.

## Minimal setup

After importing a model, commands can create an operation and configure the part, machine, and coordinate frames:

```python
tube.create_operation()
tube.confirm_part()
tube.set_machine("<machine resource ID>")
tube.set_model_cs()
tube.set_build_cs()
tube.set_placement("<mount ID>")
```

An empty `tube.confirm_part()` selects all current closed solids that are not ignored. Part assignment belongs to the project and is not written to portable YAML. Use `tube.state()`, `tube.issues()`, and `tube.validate()` to inspect state, stable issue codes, coordinate validity, and Setup readiness. `tube.help()` lists public commands; `tube.help("set_nozzle")` shows a command signature.

## Transactions and coordinate inputs

Use the transaction commands shown by `tube.help()` to group supported edits atomically. A failed command reports the issue and leaves the prior committed state in place. Confirm or discard open coordinate/placement drafts before scripting; an active editor draft returns `E_DRAFT_ACTIVE` to prevent overwriting unconfirmed picks.

Coordinates are stored as millimetres, right-handed frames, and column vectors in Source CS. Model CS numerical input defaults to Source CS; Build CS numerical input defaults to Model CS. `input_frame` can make the source frame explicit:

```python
tube.set_model_cs(origin=(0, 0, 0), z=(0, 0, 1), x=(1, 0, 0), input_frame="source")
tube.set_build_cs(origin=(0, 0, 0), z=(0, 0, 1), x=(1, 0, 0), input_frame="model")
tube.set_placement("build_plate_mount", translation_mm=(0, 0, 0), rotation_xyz_deg=(0, 0, 0))
```

## YAML work file

Before a project is saved, portable settings exist only in memory. The first project save creates `manufacturing-setup.yaml`. Each successful portable edit is atomically written before it is published to the UI and Viewer. Part changes are project-specific and leave YAML unchanged.

When a project opens, the app compares project settings, YAML semantics, and `base_project_setup_sha256`. If both sides changed, choose **Use YAML**, **Use Project**, or cancel. If an external edit is detected, automatic overwrite pauses; preview or explicitly replace the file with current Setup. Import applies semantic settings without changing Part. Export Copy writes an independent YAML file. See [Manufacturing Setup YAML v1](../formats/manufacturing-setup-yaml.md).

## Security boundary

Input is parsed by a restricted AST parser; it is not executed by Python. Values are limited to numbers, strings, booleans, `None`, tuples, lists, and dictionaries with string keys. Imports, assignments, variable references, expressions, attribute chains, loops, conditionals, lambdas, comprehensions, `eval`, `exec`, dunder access, semicolon chaining, filesystem/network/process/thread access, and PowerShell commands are rejected.

A `.py` file is only a container for this restricted language. Limits are 256 KiB, 500 commands, and 32 nesting levels. Format references: [Python AST](https://docs.python.org/3/library/ast.html), [YAML 1.2.2](https://yaml.org/spec/1.2.2/), [RFC 9512](https://www.rfc-editor.org/rfc/rfc9512), and [JSON Schema 2020-12](https://json-schema.org/draft/2020-12).
