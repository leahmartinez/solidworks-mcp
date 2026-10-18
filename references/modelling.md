# Editing parts

Read this when changing a part's dimensions, global variables, equations, configuration or
design table with `swdraw_model_edit`, or writing an edit spec (`*.edit.yaml`).

Building parts from a spec (sketches, extrudes, cuts, holes, patterns) isn't available yet. For
now, swdraw only edits existing parts.

## The loop

1. `swdraw_model_inspect` on the part. It lists every dimension by full name with its value, the
   global variables, the equations, the configurations, any design table, features with rebuild
   errors, and the current volume, mass, surface area and bounding box. `spec` in the result
   (and `spec_file`) is an edit spec with the current values.
2. Copy that spec, keep only what should change, and set `expect` to what the part should measure
   **after** the change.
3. `swdraw_model_validate`, then `swdraw_model_edit` without `save`. Read `check`.
4. If it passed and the user agrees, run it again with `save: true`.

## An edit spec, annotated

```yaml
part: C:/work/ACME1-MEC-2101.SLDPRT    # optional; the active part otherwise
configuration: Default                 # activate first (optional)
apply_to: this                         # dimensions: this configuration (default) or all
design_table: {row: Large, set: {D1@Sketch1: 42}}   # cells in one row; that row is then activated
globals:
  flange_d: 42mm                       # written as given: "flange_d" = 42mm
equations:
  bore_r@Profile: '"bore_d" / 2'       # right-hand side, by left-hand side
dimensions:
  length@Profile: 30                   # mm, degrees or a count
  D2@Revolve1: 180deg                  # or with a unit: mm, cm, m, in, ft, deg, rad
expect:                                # every entry needs tol (absolute) or tol_pct
  volume_mm3: {value: 11711.73, tol: 0.5}
  mass_g: {value: 104.2, tol_pct: 0.5}
  surface_area_mm2: {value: 5841.53, tol: 0.5}
  bbox_mm: {value: [42, 25, 42], tol: 0.01}    # sizes along model X, Y, Z
save: false                            # true: back up, then save (only if every check passed)
backup_dir: ~/swdraw-backups           # default: next to the part
on_failure: keep                       # or revert: put the old values back
allow_unsaved_changes: false           # see Saving
```

Changes are applied in this order: design-table cells, configuration, globals, equations,
dimensions. Then swdraw evaluates the equations and rebuilds once.

## What the self-check does

- **Every change is checked.** A name that doesn't exist, a refused value or an expression that
  SolidWorks won't accept is listed in `check.failed_changes`.
- **Dimensions are read back after the rebuild.** If a value doesn't stick, the edit fails. This
  usually means an equation, the design table or a configuration overrode it.
- **Dimensions driven by an equation are refused.** Change the global variable or the equation
  instead. `inspect` marks these `driven_by_equation`.
- **Rebuild errors fail the edit.** Features with errors are listed in `check.rebuild_errors`.
  Warnings are reported, but don't fail it.
- **`expect` is compared with the rebuilt part.** Volume, mass, surface area and bounding box,
  each within its tolerance.

On any failure nothing is saved. With `on_failure: keep` the changes stay in the open part so you
can look at them; close it without saving to discard them. With `on_failure: revert` swdraw puts
every old value back and rebuilds. `measured.after_revert` shows the result.

## Saving

`save: true` in the spec, or `save` on the tool, which overrides the spec. swdraw saves only when:

- every check passed
- the part has been saved to a file before and is writable, not open read-only
- the part had no unsaved changes before the edit, because saving would include them. Set
  `allow_unsaved_changes: true` if that's what the user wants.

Before saving, swdraw copies the file on disk to `<name>.bak.SLDPRT`. It goes next to the part,
or into `backup_dir` (or `SWDRAW_BACKUP_DIR`, or the extension's backup folder setting). An
existing backup is never overwritten: the new one gets a timestamp. `check.backup` is the path.

## Global variables or dimensions?

If the part has global variables driving its dimensions, change the globals. That's what the
designer meant to be edited, and equations keep the rest consistent. Change a dimension directly
only when nothing drives it.

Write globals with units (`42mm`). A plain number is in the part's document units, which may not
be millimetres.

## Expected values

- Work them out from the geometry where you can. For a turned part, the volume of the revolved
  profile (`swdraw.geometry.revolved_volume`) is exact.
- `mass_g` depends on the material. With no material assigned, SolidWorks uses a default density
  and swdraw warns.
- `bbox_mm` is the exact box of the solid bodies along the model axes, not the smallest box.
- Use tolerances that catch a wrong feature but not rounding: about 0.01% on volume and area is a
  good start.

## Example

`examples/flanged_bush/bush.edit.yaml` widens the bush flange from 40 to 42 mm by changing the
`flange_d` global, and expects the new volume, surface area and bounding box.
