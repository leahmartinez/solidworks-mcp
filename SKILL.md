---
name: swdraw
description: Build, revise and renumber SolidWorks drawings, and edit SolidWorks parts, with the swdraw MCP tools. Use when asked to create or fix a SolidWorks drawing, dimension a part, add GD&T or notes, change a part's dimensions, global variables, equations or configuration, issue a revision, renumber or rename parts and drawings, tidy a CAD working folder or update a drawing register.
---

# SolidWorks drawings and parts with swdraw

swdraw builds the active SolidWorks drawing from a YAML spec and checks every dimension against
the value it should measure. It also handles the jobs around a drawing: revisions, reference-safe
renumbering, the notes block, folder tidy and the drawing register. It also edits existing parts
from a spec and checks them after the rebuild before saving.

## Tools

| Tool | Use for |
|---|---|
| `swdraw_validate_spec` | checking a spec before building (no SolidWorks needed) |
| `swdraw_build_drawing` | building or rebuilding the active drawing from a spec |
| `swdraw_export_pdf` | PDF plus PNG preview of a drawing |
| `swdraw_revise` | revision row, REV box, approval, small layout moves |
| `swdraw_renumber` | renaming a part and drawing without breaking references |
| `swdraw_notes` | replacing or de-duplicating the numbered notes block |
| `swdraw_tidy` | moving non-live files out of a working folder (dry run first) |
| `swdraw_register` | generating the drawing register workbook |
| `swdraw_number` | checking and allocating part numbers |
| `swdraw_diagnostics` | read-only look at views, selection, annotations, references |
| `swdraw_model_inspect` | read-only look at a part: dimensions, globals, equations, configurations, mass properties |
| `swdraw_model_validate` | checking a part edit spec (no SolidWorks needed) |
| `swdraw_model_edit` | changing a part from a spec, rebuild and self-check; saves only with `save: true` |
| `swdraw_run_script` | the user's own scripts from their scripts folder |

Full list with arguments: `capabilities.yaml`.

## References: read the one you need

| Read | When |
|---|---|
| `references/drawing-spec.md` | writing or fixing a drawing spec |
| `references/profiles.md` | setting up house style, title block or numbering; a profile isn't picked up |
| `references/modelling.md` | editing a part or writing an edit spec |
| `references/workflows.md` | before revising, renumbering, tidying or regenerating the register |
| `references/troubleshooting.md` | a build reports failures or the sheet looks wrong |
| `references/api-gotchas.md` | a SolidWorks call misbehaves, or before changing swdraw's code |

## Subskills

| Subskill | When |
|---|---|
| `subskills/engineering-drawing/SKILL.md` | making a new drawing of a part, or fully redoing one |
| `subskills/part-editing/SKILL.md` | changing an existing part's sizes or configuration |

## Rules
- **Ask before changing files.** Confirm which drawing or part, and whether to save. swdraw never
  saves unless asked (`save: true`).
- **Use absolute paths** for specs and files. The server runs from its own folder.
- **Give every dimension an `expect` value**, and validate the spec before building.
- **Check the result after every build.** Read `check`, then look at the PNG before telling the
  user it's done. The self-check proves the right edges were dimensioned, not that the layout is
  clean.
- **Include `clear` when re-running a build**, or annotations are added twice.
- **Edit a part without saving first.** Read `check`, show the user what changed, then save. Give
  every edit an `expect` block worked out from the geometry, not copied from the result.
- **Renumbering and tidying move and rename files.** Show the plan (dry run, `save: false`)
  and get a yes first.
- **Report what the API couldn't do.** Some things need a manual fix (for example, dangling
  centre marks); tell the user.
