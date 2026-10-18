---
name: swdraw
description: Build, revise and renumber SolidWorks drawings with the swdraw tools. Use when asked to create or fix a SolidWorks drawing, dimension a part, add GD&T or notes, issue a revision, renumber or rename parts and drawings, tidy a CAD working folder or update a drawing register.
---

# Working with SolidWorks drawings through swdraw

## Before you start
- Ask which drawing (or make it active) and whether the user wants it saved. swdraw never saves
  unless told to (`save: true`).
- Read the house style, title-block and numbering profiles if the user has their own.

## Building a drawing
1. Write or update a spec (see `examples/flanged_bush/bush.drawing.yaml`). Get model coordinates
   from the part, not by guessing: dimensions of features, `swdraw_diagnostics views` for view
   names and orientation.
2. Give every dimension an `expect` value. Add `alternatives` for picks near other edges.
3. `swdraw_validate_spec`, fix everything it reports.
4. `swdraw_build_drawing`. Read `result.check`: failed dimensions or annotations name what to fix.
5. **Look at the exported PNG.** Check every view has geometry, nothing overlaps, the notes block
   clears the title block, view labels are readable. Move things with `text_at` / `at` and re-run
   only the steps you need (`steps: ["dimensions", "gdt", "fonts", "export"]`).
6. Tell the user what's left that the API can't do (for example dangling centre marks).

## Revisions and renumbering
- Revisions: `swdraw_revise` with `rev`, `desc`, initials and approver. Confirm the row and the
  wording with the user first.
- Renumbering renames files. Confirm the old and new numbers, run with `save: false` first if
  unsure, and only use `supersede` once the user agrees. Report `dependencies` afterwards.

## Folders and the register
- `swdraw_tidy` is a dry run by default. Show the user the planned moves before running with
  `dry_run: false`.
- `swdraw_register` regenerates the workbook. Revision history comes from the data you pass, so
  read the existing workbook first if one exists.

## If something misbehaves
Check `GOTCHAS.md`, then `swdraw_diagnostics` (`views`, `selection`, `annotations`, `refs`).
