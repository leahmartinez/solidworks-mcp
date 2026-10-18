---
name: swdraw-part-editing
description: Change an existing SolidWorks part (dimensions, global variables, equations, configuration or design-table row) with a swdraw edit spec, check it after the rebuild and save it with a backup. Use when asked to resize, modify or re-parameterise a part.
---

# Editing a part from a spec

Use the `swdraw_model_*` tools. Read `../../references/modelling.md` first, and
`../../references/api-gotchas.md` if something misbehaves.

## 1. See what the part has
- Run `swdraw_model_inspect` on the part (absolute path, or with it active).
- Find what drives the size you're changing. Prefer a global variable. Never change a dimension
  marked `driven_by_equation`.
- Note the current `measured` values and any `feature_errors`. Fix existing errors first, or tell
  the user they're already there.

## 2. Write the spec
- Start from `edit_template.yaml` in this folder, or from `spec` in the inspect result.
- Keep only the values that change. Give globals a unit (`42mm`).
- Work out `expect` for the changed part: volume, bounding box and, if a material is assigned,
  mass. Explain where the numbers come from. Don't copy them from the result after the edit.

## 3. Validate, edit, check
1. Run `swdraw_model_validate` and fix everything it finds.
2. Run `swdraw_model_edit` without `save`.
3. Read `check`:
   - `failed_changes`: wrong name, refused value, or a value that didn't stick after the rebuild
   - `rebuild_errors`: features that broke
   - `failed_expect`: the part measures something else; compare `measured.before` and `after`
4. On a failure, the changes are still in the open part (unless `on_failure: revert`). Fix the
   spec, or have the user close the part without saving.

## 4. Save only when asked
- Show the user what changed (`changes`) and what it measures now, then ask before saving.
- Run again with `save: true`. Report `check.backup`, the copy of the original.
- If the save is refused because of earlier unsaved changes, ask the user. Don't set
  `allow_unsaved_changes` yourself.
- Drawings of the part update when they're next opened and rebuilt. Offer to rebuild the drawing
  (`swdraw_build_drawing`) if its dimensions should move.
