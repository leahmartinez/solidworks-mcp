---
name: swdraw-engineering-drawing
description: Write and iterate a swdraw drawing spec for a SolidWorks part, from views and sections through self-checked dimensions, GD&T, notes and title block to a reviewed PDF. Use when asked to make or fully redo a drawing of a part.
---

# Engineering drawing from a spec

Use the `swdraw_*` tools. Read `../../references/drawing-spec.md` first, and
`../../references/api-gotchas.md` if anything misbehaves.

## 1. Understand the part
- Get the part's real geometry: its parameters file if it was generated, otherwise feature
  dimensions from the model. List every feature that needs a size, a tolerance or a callout.
- Decide the datum scheme with the user (what mates with what), then which features carry GD&T.

## 2. Plan the sheet
- Pick the views: a base view, sections through the features that need sizes, details for
  anything under about 2 mm at sheet scale, an isometric for orientation.
- Pick a sheet scale so the largest view fits about a quarter of an A3 sheet.
- Sketch positions in sheet mm and keep clear of the title block and revision table.

## 3. Write the spec
- Start from `spec_template.yaml` in this folder.
- Every dimension gets an `expect` (the nominal) and, near other edges, an `alternatives` pair.
- Tolerances: functional fits and datum features only; everything else is covered by the general
  tolerance note.
- Notes: material, general tolerance, edge breaks, finish, anything the model can't show.

## 4. Validate, build, review
1. `swdraw_validate_spec` and fix every problem.
2. `swdraw_build_drawing` (the drawing must be active).
3. Read `check`. Fix failed or wrong-value dimensions first (see `../../references/troubleshooting.md`).
4. Open the PNG. Check every view has geometry, no text overlaps a view or another dimension, the
   notes block clears the title block and leaders point at the right features.
5. Re-run only what changed, always with `clear` first:
   `steps: ["clear", "dimensions", "gdt", "leader_notes", "notes", "fonts", "export"]`.
6. Report what the API couldn't do (for example dangling centre marks) and leave saving to the user
   unless they asked.
