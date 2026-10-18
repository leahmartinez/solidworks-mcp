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
- [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`). It installs Python and every
  dependency on first run.

`validate`, `tidy`, `register`, `number`, `setup` and the test-suite run anywhere, without SolidWorks.

## Install

```powershell
git clone https://github.com/<you>/swdraw.git
cd swdraw
uv sync --extra mcp --extra preview
```

Then connect it to your AI client. Pick one:

**Claude Desktop, as an extension (one click).** Download `swdraw-<version>.mcpb` from the
Releases page, or build it with `npx @anthropic-ai/mcpb pack . swdraw.mcpb`, and open it with
Claude Desktop. Set:

- **Output folder**: where traces, results, PDFs and PNG previews go
- **Profiles folder** (optional): your own `house_style.yaml`, `title_block.yaml`, `numbering.yaml`
- **Scripts folder** (optional): the only folder `swdraw_run_script` may run scripts from

**From the clone, with one command.** Each `setup` shows the change first; add `--apply` to make
it. Config files are backed up to `.bak` first.

```powershell
uv run python -m swdraw setup claude-code --skill --output-dir ~/swdraw-output --apply
uv run python -m swdraw setup claude-desktop --output-dir ~/swdraw-output --apply   # not if you installed the .mcpb
uv run python -m swdraw setup codex --output-dir ~/swdraw-output --apply
```

`--skill` also copies `SKILL.md`, `references/` and `subskills/` to `~/.claude/skills/swdraw`, so
Claude Code knows the workflow. Restart the client afterwards.

**Any other MCP client:** run `uv run --directory <clone> --extra mcp --extra preview python
mcp_server/server.py` over stdio. See [mcp_server/README.md](mcp_server/README.md).

## Set up a profiles folder

Copy `profiles/` somewhere of your own and point `SWDRAW_PROFILES` (or the extension setting) at
it. Anything you leave out falls back to the bundled files. See
[references/profiles.md](references/profiles.md).

To generate a matching A3 sheet format and drawing template, import `templates/A3_SheetFormat.bas`
into a new SolidWorks macro, edit the constants at the top (company name, projection,
confidentiality block, linked properties or placeholders) and run `main`.

## Quick start: the flanged bush

```powershell
# 1. make the part and a drawing with front + isometric views
uv run python examples/flanged_bush/make_part.py --args "{\"out\": \"~/swdraw-example\"}"

# 2. check the spec (no SolidWorks needed)
uv run python -m swdraw validate --spec examples/flanged_bush/bush.drawing.yaml

# 3. with the new drawing active in SolidWorks, build it
uv run python -m swdraw build --spec examples/flanged_bush/bush.drawing.yaml
```

The result lists every step, each dimension's measured value and which pick pair produced it,
and a `check` block naming anything that failed. Open the PNG it exports and look at it: the
self-check proves the right edges were dimensioned, not that the layout is pleasant.

Run part of the build again after an edit. Include `clear`, or the annotations are added a
second time:

```powershell
uv run python -m swdraw build --spec bush.drawing.yaml --steps clear,dimensions,gdt,leader_notes,notes,fonts,export
```

Then issue revision B:

```powershell
uv run python -m swdraw revise --args "{\"rev\": \"B\", \"desc\": \"BORE TOLERANCE CHANGED\", \"drawn\": \"AD\", \"approved\": \"CC\", \"approver_name\": \"C. CHECKER\"}"
```

## Writing a spec

Coordinates are **model millimetres** for anything attached to geometry (`pick`, `text_at`,
section `line`, detail `centre`) and **sheet millimetres from the bottom-left corner** for
positions on the sheet (`at`). Every dimension carries `expect`, the value it must measure.

Start from [subskills/engineering-drawing/spec_template.yaml](subskills/engineering-drawing/spec_template.yaml).
For a complete example, see [examples/flanged_bush/bush.drawing.yaml](examples/flanged_bush/bush.drawing.yaml).
Every key is described in [references/drawing-spec.md](references/drawing-spec.md).

## Your own scripts

`swdraw` keeps its helpers small so you can write one-off scripts against the same conventions:

```python
import swdraw as sw

dwg = sw.active()
names = [sw.call(v, "GetName2") for v in sw.views(dwg)]
sw.result({"views": names, "args": sw.args()})
```

Run it with `uv run python -m swdraw run my_script.py --args "{...}"`, or from Claude with
`swdraw_run_script` if it lives in your scripts folder.

## When something goes wrong

Start with [references/troubleshooting.md](references/troubleshooting.md), then
[references/api-gotchas.md](references/api-gotchas.md); most surprises are SolidWorks API behaviour. Then:

```powershell
uv run python -m swdraw diag views          # names, origins, scales, whether model +Y is up
uv run python -m swdraw diag annotations    # incl. dangling centre marks
```

Each run appends to `swdraw.log` in the output folder.

## Repository layout

| Path | What's there |
|---|---|
| `SKILL.md`, `SUBSKILLS.md` | instructions for Claude: which tool when, which reference to read |
| `references/` | drawing specs, profiles, workflows, troubleshooting, SolidWorks API gotchas |
| `subskills/engineering-drawing/` | end-to-end drawing workflow and a spec template |
| `capabilities.yaml` | every MCP tool with its arguments (generated) |
| `swdraw/` | the Python package: COM helpers, drawing builder, revision, renumber, notes, tidy, register |
| `mcp_server/` | the MCP server (stdio) |
| `manifest.json` | the Claude Desktop extension manifest |
| `profiles/` | example house style, title block and numbering profiles |
| `templates/` | A3 sheet-format macro and a feature-dump macro (VBA source) |
| `examples/flanged_bush/` | worked example: part generator and drawing spec |
| `tests/` | tests against a fake SolidWorks API |
| `.github/workflows/` | CI on Windows and Linux; release builds the `.mcpb` from a tag |

## Tests

```powershell
uv run --extra dev python -m pytest
```

The tests use a fake of the SolidWorks drawing API (`tests/fakes.py`). They cover selection,
dimension self-checking and fallback, tolerances, title-block matching, revisions, notes, tidy,
the register (including formula results when LibreOffice is installed), numbering, spec
validation and the example's geometry. What they can't cover is listed in
[CONTRIBUTING.md](CONTRIBUTING.md). CI runs them on Windows and Linux for every push.

## Licence

MIT. See [LICENSE](LICENSE).
