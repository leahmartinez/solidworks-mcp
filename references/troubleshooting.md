# Troubleshooting

Read this when a build reports failures or the sheet looks wrong.

| Symptom | Likely cause | What to do |
|---|---|---|
| `failed_dimensions`: selection failed | pick point not on an edge in that view, or the view has no geometry yet | `swdraw_diagnostics views` to confirm the view and `model_y_up`; check the point against the part; add `alternatives` |
| `wrong_value_dimensions` | the pick hit a neighbouring edge | move the pick to the middle of the intended edge, add an alternative pair, re-run `clear,dimensions,...` |
| tolerance shows ±0.00 | tolerance write failed | the result's `tolerance` field is empty; check `type`, `lower`, `upper` (mm, `lower` signed) |
| section comes out upside down | cut from the wrong side | `from_views: [opposite, original]`, `require_upright: true`, an `alt_at` on the other side of the line |
| section or detail view is blank, picks miss | views not regenerated | the builder regenerates before dimensions; re-run from `dimensions` if views were edited by hand |
| title-block fields don't change (custom-properties mode) | template uses `$PRPSHEET:` (part properties) for that field | list the field under `model_fields` in the title-block profile |
| title-block fields don't change (placeholder mode) | position or placeholder text doesn't match | `swdraw_diagnostics annotations` on a blank drawing for the real positions; adjust `at` / `tolerance_mm` |
| notes block lost its numbering | something called `SetText` on it | `swdraw_notes replace` (delete and re-insert) |
| dangling centre marks remain after `clear` | API can't select them | delete them by hand; `swdraw_diagnostics annotations` lists them (`dangling: true`) |
| renumber: "drawing does not reference the new part" | drawing wasn't open when the part was saved as, or loaded a different copy | open the drawing, then re-run; never rename files in Explorer |
| tidy/renumber: permission or "in use" errors | SolidWorks or Explorer holds the file | close the documents (and Explorer windows on the folder), wait, re-run |
| model edit: "driven by equation" | an equation sets that dimension | change the global variable or the equation (`inspect` shows which) |
| model edit: value "reads ... after the rebuild" | an equation, design table or configuration overrides it | `swdraw_model_inspect`; change what drives it, or the design-table row |
| model edit: `rebuild_errors` | the new values break a feature (wall too thin, sketch can't solve) | look at the feature in SolidWorks; `on_failure: revert` puts the old values back |
| model edit: `failed_expect` | the part changed, but not as expected | compare `measured.before` and `after`; check the expected values and the change |
| model edit: not saved, "unsaved changes" | the part was already modified before the edit | save or discard those changes in SolidWorks first, or `allow_unsaved_changes: true` if the user agrees |
| model edit: mass is wrong | no material assigned (default density) | assign the material in SolidWorks, or check volume instead |
| MCP tool times out | a SolidWorks dialog is waiting for input | dismiss it in SolidWorks; raise `SWDRAW_TIMEOUT_S` for very large drawings |
| tool returns `exit_code` with `stderr` | Python error before a result was printed | read `stderr` and `swdraw.log` in the output folder |

Every run appends to `swdraw.log` and writes `<command>.json` in the output folder
(`SWDRAW_OUTPUT_DIR`, default `~/swdraw-output`).
