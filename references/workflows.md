# Revisions, renumbering, notes, folders and the register

Read this before revising a drawing, renaming or renumbering parts, tidying a working folder or
regenerating the drawing register. All of these change files or drawings, so confirm the details
with the user first.

## Revise a drawing (`swdraw_revise`)

```json
{"rev": "B", "desc": "BORE TOLERANCE CHANGED", "date": "18/10/2026", "drawn": "AD", "approved": "CC",
 "approver_name": "C. CHECKER", "finish_note": 4, "save": false}
```

- `row` defaults from the letter (A = 1, B = 2). Pass it for numeric revisions or odd tables.
- Title-block mode comes from the profile: custom properties (`Rev2`, `Rev2Desc` ...) or placeholder
  notes found by position.
- `finish_note` rewrites "... SEE NOTE n" in the title block (the finish property in custom-properties
  mode) to point at note `n`.
- Layout tweaks in the same call: `shift_views` (mm), `notes_pos` (sheet mm), `move_dims`
  (`{view, value, tol?, to: [x,y,z]}`), `move_gtols` (`{view, symbol, to}`).
- `save: true` saves the drawing; otherwise it is left modified for the user to check.

## Renumber a part and its drawing (`swdraw_renumber`)

```json
{"drawing": "C:/.../ACME1-MEC-0042.SLDDRW", "old": "ACME1-MEC-0042", "new": "ACME1-MEC-2101",
 "old_parent": "ACME1-MEC-0040", "new_parent": "ACME1-MEC-2100", "description": "FLANGED BUSH",
 "revision": "B", "save": true, "supersede": false}
```

Order of operations (each one matters, see `api-gotchas.md`):

1. Part custom properties from `numbering.yaml`.
2. Part Save As with the drawing open (the drawing follows).
3. Number swap in drawing notes, including "<old> REV x" to "<new> REV <revision>"; the notes block
   is deleted and re-inserted, never `SetText`.
4. Drawing Save As, then a dependency check: the drawing must reference the new part.
5. Only with `supersede: true`: close both, move the old files to `_Superseded`, optionally
   `rename_folder: {from, to}`, reopen from the final location, rebuild, save, re-check references.

Run with `save: false` first if unsure. New numbers that don't match the numbering pattern are refused.

## Notes block (`swdraw_notes`)

- `replace`: `{"lines": ["...", ["item", "continuation"]], "pos": [x_mm, y_mm], "values": {...}}`.
  Deletes every NOTES: block and inserts one numbered block in the house style.
- `dedupe`: keeps the block whose text shows "1." numbering and deletes copies without it. If none
  shows numbering, nothing is deleted.

## Tidy a working folder (`swdraw_tidy`)

```json
{"working": "C:/.../Working", "keep": ["ACME1-MEC-21*.*", "*Register.xlsx", "Master*.SLDPRT"],
 "move_folders": {"Reference": "<parent>"}, "dry_run": true}
```

- Dry run by default: show the user `moves` before running with `dry_run: false`.
- Byte-identical copies already in `_Superseded` are merged; anything else gets a timestamp suffix.
  Nothing is overwritten. Lock files (`~$...`) and unlisted folders are skipped.
- Keep master parts that derived parts reference in the working folder (`keep`), or their links break.
- Close the files in SolidWorks first; open files are locked and reported in `errors`.

## Drawing register (`swdraw_register`)

```json
{"out": "C:/.../Drawing Register.xlsx", "title": "ACME1 drawing register",
 "drawings": [{"number": "ACME1-MEC-2101", "title": "FLANGED BUSH", "type": "Part", "parent": "ACME1-MEC-2100"}],
 "revisions": [{"number": "ACME1-MEC-2101", "rev": "A", "date": "2026-10-18", "description": "FIRST ISSUE",
                "by": "AD", "approved": "CC", "status": "PROTOTYPE"}]}
```

- The workbook is regenerated from what you pass. If one exists, read its Revision History first and
  pass all rows, or history is lost.
- Register: Current Rev, Rev Date and Status are formulas over Revision History.
- Revision History: yellow input cells, dropdowns for drawing number and status.
- Numbering: rules from `numbering.yaml` and every allocated number.

## Part numbers (`swdraw_number`)

- `check`: `{"numbers": [...]}` describes each (assembly / part of which assembly / invalid).
- `next-part`: `{"assembly": "ACME1-MEC-2100", "used": [...]}`.
- `next-assembly`: `{"used": [...], "discipline": "MEC"}`.
