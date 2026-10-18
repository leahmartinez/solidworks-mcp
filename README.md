# swdraw

Spec-driven SolidWorks drawings that check themselves.

You describe a drawing in a YAML file: which views, where to cut sections and details, which
edges to dimension and the value each dimension *should* measure, tolerances, GD&T, notes and
title-block values. swdraw builds the active drawing from it. If a dimension lands on the wrong
edge, it notices (the measured value doesn't match), deletes it, regenerates the views and tries
again with your alternative picks. If nothing matches, it keeps the last attempt on the sheet and
flags it in the result.

It also covers the jobs around a drawing:

| Tool | What it does |
|---|---|
| `build` | scale, clear, layout, sections, details, self-checked dimensions and tolerances, datums and GD&T frames, leader notes, numbered notes block, title block, house-style fonts, PDF + PNG export with a check summary |
| `revise` | revision-table row, REV box, approver and date, "SEE NOTE n" reference, moving dimensions and GD&T frames to model coordinates |
| `renumber` | reference-safe rename of a part and its drawing: properties, Save As in the right order, number swap in notes, dependency check, supersede old files, folder rename and verify |
| `notes` | replace the numbered notes block, or delete copies that lost their numbering |
| `tidy` | keep only live files in a working folder; identical copies merged, nothing overwritten |
| `register` | drawing register workbook: Register, Revision History (inputs) and Numbering tabs |
| `number` | check part numbers and allocate the next part or assembly number |
| `diag` | read-only probes: views and transforms, selection, annotations, file references |

Everything runs from the command line, from your own Python, or from Claude Desktop through the
bundled MCP server.

## Requirements

- Windows with SolidWorks 2025 or later (earlier versions probably work; untested)
- Python 3.10+ with `pywin32`, `pyyaml`, `openpyxl`
- Optional: `pymupdf` for PNG previews, `mcp` for the Claude Desktop extension

`validate`, `tidy`, `register`, `number` and the test-suite run anywhere, without SolidWorks.

## Install

```powershell
git clone https://github.com/<you>/swdraw.git
cd swdraw
python -m pip install -e ".[mcp,preview]"
```

Install it editable (`-e`) so the bundled `profiles/` are found next to the package.

### Claude Desktop extension (optional)

The repository is an MCP Bundle: `manifest.json` plus `mcp_server/server.py`.

```powershell
npx @anthropic-ai/mcpb pack . swdraw.mcpb
```

Open the `.mcpb` with Claude Desktop (or drag it onto Settings > Extensions) and set:

- **Output folder**: where traces, results, PDFs and PNG previews go
- **Profiles folder** (optional): your own `house_style.yaml`, `title_block.yaml`, `numbering.yaml`
- **Scripts folder** (optional): the only folder `swdraw_run_script` may run scripts from

The extension runs `python` from your PATH, so install the dependencies into that interpreter.

## Set up a profiles folder

Copy `profiles/` somewhere of your own and point `SWDRAW_PROFILES` (or the extension setting) at
it. Anything you leave out falls back to the bundled files. See [CONFIGURATION.md](CONFIGURATION.md).

To generate a matching A3 sheet format and drawing template, import `templates/A3_SheetFormat.bas`
into a new SolidWorks macro, edit the constants at the top (company name, projection,
confidentiality block, linked properties or placeholders) and run `main`.

## Quick start: the flanged bush

```powershell
# 1. make the part and a drawing with front + isometric views
python examples/flanged_bush/make_part.py --args "{\"out\": \"~/swdraw-example\"}"

# 2. check the spec (no SolidWorks needed)
python -m swdraw validate --spec examples/flanged_bush/bush.drawing.yaml

# 3. with the new drawing active in SolidWorks, build it
python -m swdraw build --spec examples/flanged_bush/bush.drawing.yaml
```

The result lists every step, each dimension's measured value and which pick pair produced it,
and a `check` block naming anything that failed. Open the PNG it exports and look at it: the
self-check proves the right edges were dimensioned, not that the layout is pleasant.

Run part of the build again after an edit. Include `clear`, or the annotations are added a
second time:

```powershell
python -m swdraw build --spec bush.drawing.yaml --steps clear,dimensions,gdt,leader_notes,notes,fonts,export
```

Then issue revision B:

```powershell
python -m swdraw revise --args "{\"rev\": \"B\", \"desc\": \"BORE TOLERANCE CHANGED\", \"drawn\": \"AD\", \"approved\": \"CC\", \"approver_name\": \"C. CHECKER\"}"
```

## Writing a spec

Coordinates are **model millimetres** for anything attached to geometry (`pick`, `text_at`,
section `line`, detail `centre`) and **sheet millimetres from the bottom-left corner** for
positions on the sheet (`at`). Find model coordinates in SolidWorks with *Measure* or from the
sketch; for a revolved or symmetric part, pick on the section plane.

```yaml
dimensions:
  - id: D_BORE
    view: C                         # a view name, or the id of a section/detail from this spec
    pick: [[0, 12, -8], [0, 12, 8]] # two edges (or one, for a radius/diameter)
    text_at: [0, 18, 0]
    prefix: "<MOD-DIAM>"
    expect: 16.0                    # the self-check
    tolerance: {type: bilateral, lower: 0, upper: 0.018}
    alternatives:                   # tried in order if the picks fail or measure wrong
      - [[0, 6, -8], [0, 6, 8]]
```

The full example with every step is [examples/flanged_bush/bush.drawing.yaml](examples/flanged_bush/bush.drawing.yaml).

## Your own scripts

`swdraw` keeps its helpers small so you can write one-off scripts against the same conventions:

```python
import swdraw as sw

dwg = sw.active()
names = [sw.call(v, "GetName2") for v in sw.views(dwg)]
sw.result({"views": names, "args": sw.args()})
```

Run it with `python -m swdraw run my_script.py --args "{...}"`, or from Claude with
`swdraw_run_script` if it lives in your scripts folder.

## When something goes wrong

Read [GOTCHAS.md](GOTCHAS.md) first; most surprises are SolidWorks API behaviour. Then:

```powershell
python -m swdraw diag views          # names, origins, scales, whether model +Y is up
python -m swdraw diag annotations    # incl. dangling centre marks
```

Each run appends to `swdraw.log` in the output folder.

## Tests

```powershell
python -m pytest
```

The tests use a fake of the SolidWorks drawing API (`tests/fakes.py`). They cover selection,
dimension self-checking and fallback, tolerances, title-block matching, revisions, notes, tidy,
the register (including formula results when LibreOffice is installed), numbering, spec
validation and the example's geometry. What they can't cover is listed in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT. See [LICENSE](LICENSE).
