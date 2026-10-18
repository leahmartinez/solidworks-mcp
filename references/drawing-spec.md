# Drawing specs

Read this when writing or fixing a drawing spec (`*.drawing.yaml`).

Coordinates are **model millimetres** for anything attached to geometry (`pick`, `text_at`, section
`line`, detail `centre`) and **sheet millimetres from the bottom-left corner** for positions on the
sheet (`at`). For a revolved or symmetric part, pick on the section plane.

## A dimension, annotated

```yaml
dimensions:
  - id: D_BORE                      # used in the report, by datums (on_dim) and by revise move_dims
    view: C                         # a view name, or the id of a section/detail from this spec
    pick: [[0, 12, -8], [0, 12, 8]] # two edges, or one for a radius/diameter
    text_at: [0, 18, 0]             # where the text goes, in model mm on that view
    prefix: "<MOD-DIAM>"
    suffix: " H7"
    expect: 16.0                    # the self-check: measured value must match within 0.005 mm
    tolerance: {type: bilateral, lower: 0, upper: 0.018}
    precision: 3
    alternatives:                   # tried in order if the picks fail or measure wrong
      - [[0, 6, -8], [0, 6, 8]]
```

What happens on a mismatch: delete, regenerate the views, try the next pair; after the last pair,
regenerate once and retry it; if it still measures wrong, the last attempt is kept on the sheet,
marked `mismatch: true` and listed in `check.wrong_value_dimensions`.

## Getting coordinates right

- Take model coordinates from the part (sketch dimensions, *Measure*, or the parameters file the
  part was built from), never by eye from the sheet.
- Pick the middle of an edge, away from corners where two edges meet. A point within 0.2 mm of
  another edge can select the wrong one; give such dimensions an `alternatives` pair.
- `text_at` is in the same model space, so "above the part" means a larger model Y in a view where
  +Y is up. Check orientation with `swdraw_diagnostics views` (`model_y_up`).
- Sheet positions (`at`) on an A3 sheet: 420 x 297 mm. Keep views and notes clear of the title
  block and revision table (bottom right) and any confidentiality box (bottom left).

## All keys

See `examples/flanged_bush/bush.drawing.yaml` for a complete spec. In short:

| Key | Contents |
|---|---|
| `drawing` | `id` (used for export file names), `sheet_scale: [num, den]` |
| `style`, `profiles` | per-drawing overrides |
| `clear` | `note_patterns` to delete (view labels and title block are always kept), `dangling_centre_marks` |
| `layout` | `[{view, at: [x_mm, y_mm], scale: sheet | [num, den]}]`, or `{view, suppress: true}` to hide a view |
| `sections` | `[{id, from_views: [...], line: [[x,y,z],[x,y,z]], at, alt_at: [[x,y], ...], require_upright, remove_alignment}]`. An `alt_at` on the other side of the cutting line reverses the viewing direction |
| `details` | `[{id, parent, centre: [x,y,z], radius_mm, scale, at}]` |
| `dimensions` | `[{id, view, pick, alternatives, text_at, expect, tolerance, prefix, suffix, diametric, precision, arc_expect}]` |
| `gdt.datums` | `[{label, view, on_dim}]` or `[{label, view, edge, text_at}]` |
| `gdt.frames` | `[{id, view, edge, text_at, frames: [[SYMBOL, tol, datum1, datum2]], above}]` |
| `leader_notes` | `[{id, view, edge, text_at, text}]` |
| `notes` | `{at: [x_mm, y_mm], lines: [...], heading}`; lines may use `{key}` from `title_block` |
| `title_block` | field values (see the profile); `drawn_date: today` is filled in |
| `revision_row` | `{desc, date, drawn, approved}` for the current revision's row (custom-properties mode) |
| `export` | `{pdf: true, png: true, path}` |

Tolerance types: `none`, `basic` (boxed, theoretically exact), `bilateral`, `limit`,
`symmetric`, `min`, `max`, `metric`, `fit`, `fit_with_tolerance`, `fit_tolerance_only`, or the
`swTolType_e` number. Only bilateral, limit and symmetric take `lower`/`upper`. Limits are in mm. `lower` is signed, so a symmetric ±0.05 is
`lower: -0.05, upper: 0.05`.

GD&T symbols are the SolidWorks `<GTOL-...>` codes without the brackets and prefix, for example
`FLAT`, `PARA`, `PERP`, `SPROF` and `SRUN`. The full list is in `gtol.sym` in your SolidWorks
installation (under `lang\<language>`).

`uv run python -m swdraw validate --spec your.yaml` checks a spec without SolidWorks. It reports missing
keys, malformed points, duplicate ids, datums pointing at unknown dimensions and any dimension
without `expect`.

With the MCP tools, pass absolute paths: the server runs from its own install folder.

A datum on a dimension (`on_dim`) in a run without the `dimensions` step finds the existing
dimension in its view by its `expect` value.
