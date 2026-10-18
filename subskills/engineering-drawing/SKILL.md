---
name: swdraw-engineering-drawing
description: Write and iterate a swdraw drawing spec for a SolidWorks part, from views and sections through self-checked dimensions, GD&T, notes and title block to a reviewed PDF. Use when asked to make or fully redo a drawing of a part.
---

# Engineering drawing from a spec

Use the `swdraw_*` tools. Read `../../references/drawing-spec.md` first, and
`../../references/api-gotchas.md` if something misbehaves.

## 1. Understand the part
- Get the real geometry: the parameters file if the part was generated, otherwise feature
  dimensions from the model. List every feature that needs a size, tolerance or callout.
- Agree the datum scheme with the user (what mates with what), then decide which features get GD&T.

## 2. Plan the sheet
- Views: a base view, sections through features that need sizes, details for anything under about
  2 mm at sheet scale, and an isometric for orientation.
- Pick a sheet scale where the biggest view fills about a quarter of an A3 sheet.
- Plan positions in sheet mm, clear of the title block and revision table.

## 3. Write the spec
- Start from `spec_template.yaml` in this folder.
- Every dimension gets an `expect` (the nominal). Add an `alternatives` pair if it's near other
  edges.
- Only tolerance functional fits and datum features. The general tolerance note covers the rest.
- Notes: material, general tolerance, edge breaks, finish, and anything the model can't show.

## 4. Validate, build, review
1. Run `swdraw_validate_spec` and fix everything it finds.
2. Run `swdraw_build_drawing` with the drawing active.
3. Read `check`. Fix failed or wrong-value dimensions first (see `../../references/troubleshooting.md`).
4. Open the PNG. Check:
   - every view has geometry
   - no text overlaps a view or another dimension
   - the notes block clears the title block
   - leaders point at the right features
5. Re-run only what changed, always starting with `clear`:
   `steps: ["clear", "dimensions", "gdt", "leader_notes", "notes", "fonts", "export"]`.
6. Tell the user what the API couldn't do, such as dangling centre marks. Don't save unless they
   asked.
