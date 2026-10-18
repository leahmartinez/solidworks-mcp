# Profiles and environment

Read this when setting up a house style, a title block or a numbering scheme, or when a
profile isn't being picked up.

swdraw reads three profiles. Each is a YAML (or JSON) file. Lookup order:

1. a path passed explicitly (`profiles: {house_style: ...}` in a spec, or `title_block_profile` /
   `numbering_profile` in tool args)
2. `$SWDRAW_PROFILES/<name>.yaml`
3. the bundled defaults in `profiles/`

Environment variables:

| Variable | Default | Used for |
|---|---|---|
| `SWDRAW_OUTPUT_DIR` | `~/swdraw-output` | traces (`swdraw.log`), JSON results, PDF and PNG exports |
| `SWDRAW_PROFILES` | (bundled) | your profiles folder |
| `SWDRAW_SCRIPTS_DIR` | (none) | the only folder the MCP `swdraw_run_script` tool may run from |
| `SWDRAW_ARGS` | (none) | arguments for a script, as JSON or a path to a JSON/YAML file |
| `SWDRAW_PART_TEMPLATE`, `SWDRAW_DRAWING_TEMPLATE` | SolidWorks defaults | used by the example's `make_part.py` |
| `SWDRAW_TIMEOUT_S` | 600 | per-call timeout in the MCP server |

Paths in profiles and args may use `~` and `${ENV_VAR}`. No paths are hard-coded anywhere.

## House style: `house_style.yaml`

```yaml
font: Arial
dimension_height_mm: 2.5      # dimensions, tolerances, GD&T frames, datum tags
gdt_height_mm: 2.5
view_label_height_mm: 3.5     # SECTION A-A, DETAIL B, SCALE 2:1
note_height_pt: 8             # leader notes and the notes block
general_tolerance: ISO 2768-mK
label_threshold_mm: 3.0       # document text defaults above this height are restyled as labels
view_label_prefixes: [SECTION, DETAIL, SCALE, VIEW]
date_format: "%d/%m/%Y"
```

The `fonts` step applies this to the document text defaults and to every annotation outside the
sheet format. It captures the title-block notes' font, height and bold first and restores them
afterwards, because changing document defaults resizes those too.

A spec can override any key for one drawing:

```yaml
style: {note_height_pt: 10}
```

`general_tolerance` is available to notes text as `{general_tolerance}` when you put it in the
spec's `title_block` values.

---

## Title block: `title_block.yaml`

Two ways to fill a title block. Pick one with `mode`.

### `custom_properties` (recommended)

The sheet format's text is linked to document custom properties (`$PRP:"PartNo"`), and swdraw
writes the properties. SolidWorks updates the text itself.

- Layout changes in the sheet format don't break anything.
- No `Note.SetText`, so no lost formatting.
- The same properties feed BOMs, file names and PDM.

```yaml
mode: custom_properties
custom_properties:
  fields:                 # swdraw field -> property name in your template
    part_no: PartNo
    description: Description
    material: Material
    finish: Finish
    project: Project
    parent: ParentAssy
    status: Status
    revision: Revision
    drawn_by: DrawnBy
    drawn_date: DrawnDate
    approved_by: ApprovedBy
    approved_date: ApprovedDate
  rev_rows:               # one entry per revision-table row, oldest first
    - {rev: Rev1, desc: Rev1Desc, date: Rev1Date, drawn: Rev1By, approved: Rev1App}
    - {rev: Rev2, desc: Rev2Desc, date: Rev2Date, drawn: Rev2By, approved: Rev2App}
```

`templates/A3_SheetFormat.bas` with `USE_LINKED_PROPS = True` produces a sheet format that
matches these names. For an existing template, open the sheet format, double-click each field
and link it to a property (*Link to Property*), then list the names here.

Fields your template links with `$PRPSHEET:` (properties of the model shown on the sheet) belong
on the part, not the drawing. List them under `model_fields`; swdraw writes them to the model in
the first view, which modifies that part, though it doesn't save it. The bundled template reads
part number, description, material, finish, project and parent assembly this way:

```yaml
  model_fields: [part_no, description, material, finish, project, parent]
```

`swdraw renumber` writes part properties for you from `numbering.yaml`.

### `placeholder_notes`

The sheet has plain notes ("PART-NO", "NAME", "DD/MM/YYYY") and swdraw replaces each one by
position. Use this for templates you can't change.

```yaml
mode: placeholder_notes
placeholder_notes:
  tolerance_mm: 2.5
  fields:
    part_no:     {at: [301.2, 15.6], placeholder: "PART-NO"}
    drawn_by:    {at: [231.2, 45.8], placeholder: "NAME"}
    approved_by: {at: [231.2, 37.8], placeholder: "NAME"}     # same text, different place
    finish:      {at: [231.2, 21.6], placeholder: "FINISH / TREATMENT"}
    # ...
  rev_box: {min_x: 330, max_y: 22, height_mm: 3.5}
  rev_table:
    rows_y: [73.4, 78.4]          # row 1 (first issue), row 2, ...
    columns: {rev: 233.5, desc: 242.0, date: 353.5, drawn: 376.5, approved: 393.5}
    tolerance_mm: 2.5
    desc_tolerance_mm: 4.0
    placeholders: {rev: ["A", "B"], desc: ["FIRST ISSUE", "REVISION DESCRIPTION"], date: ["DD/MM/YYYY"],
                   drawn: ["XX"], approved: ["XX"]}
  see_note_marker: "SEE NOTE"
```

- `at` is in **sheet millimetres from the bottom-left corner**, measured at the note's anchor (what
  `Annotation.GetPosition` returns, which is the top-left of the text). The easiest way to get the
  numbers for your template: open a blank drawing and run `uv run python -m swdraw diag annotations`. The
  sheet-level entries list each note's position.
- A note is replaced only while it still shows its placeholder (or is blank), so running twice
  doesn't overwrite real values. Pass `overwrite` in code if you need to.
- Same-text fields (two "NAME" notes, the "FINISH / TREATMENT" label and its value) are told apart by
  position. Set `tolerance_mm` smaller than the gap between them.
- The REV box is any one- or two-letter note right of `min_x` and below `max_y`.
- `finish_note` in `revise` rewrites any title-block text containing `SEE NOTE` to point at the
  given note number.

---

## Numbering: `numbering.yaml`

```yaml
product: ACME1
pattern: "{product}-{discipline}-{number:04d}"
block_size: 100            # x100 is an assembly, x101..x199 are its parts
first_block: 2100
disciplines:
  MEC: Mechanical parts and assemblies
  ELE: Electrical / wiring
  PCB: Printed circuit boards
  PUR: Purchased (bought-in) items
file_name: "{number}"
part_properties:
  PartNo: "{number}"
  Description: "{description}"
  Revision: "{revision}"
  ParentAssy: "{parent}"
drawing_properties:
  PartNo: "{number}"
  Description: "{description}"
  Revision: "{revision}"
properties_static: {}       # extra values for the templates above, e.g. {project: ACME1}
```

- `ACME1-MEC-2100` is an assembly, and `ACME1-MEC-2101` to `-2199` are its parts. The next
  assembly is `-2200`.
- `swdraw number next-part --args '{"assembly": "ACME1-MEC-2100", "used": [...]}'` gives the next
  free part number. `next-assembly` gives the next free block.
- `renumber` refuses new numbers that don't match `pattern` and writes `part_properties` /
  `drawing_properties` to the part and drawing.
- The register's Numbering tab is generated from this file.

A different scheme works as long as it can be written as a pattern with `{product}`,
`{discipline}` and `{number}`. For example, `"{discipline}{number:05d}"` with an empty product
also works.
