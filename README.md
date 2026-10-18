# swdraw

Turn a SolidWorks part into a finished, checked engineering drawing. Ask Claude, or run it yourself.

## From part to drawing

1. **Start with a part.** Use your own, or generate one by script like the example
   [flanged bush](examples/flanged_bush/), which is built from a parameters file.
2. **Describe the drawing in YAML.** List the views, sections, details, dimensions, tolerances,
   GD&T, notes and title-block values. Each dimension also gets the value it should measure.
3. **swdraw builds it.** If a dimension measures wrong, it deletes it, regenerates the views and
   tries your alternative picks. If nothing works, it leaves the last attempt on the sheet and
   flags it.
4. **Check the PDF and PNG.** The result lists anything that failed.
5. **Keep it current.** Issue revisions, renumber parts without breaking references, tidy the
   working folder and update the drawing register.

**Planned:** 3D modelling, meaning building and editing parts from a spec (sketches, extrudes,
revolves, cuts, holes, fillets, dimension changes) with the same self-checks. For now, the example
script is the only modelling code.

## Tools

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

Run it from the command line, from Python, or from Claude through the MCP server.

## Requirements

- Windows with SolidWorks 2025 or later. Earlier versions probably work but aren't tested.
- [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`). It installs Python and the
  dependencies on first run.

`validate`, `tidy`, `register`, `number`, `setup` and the tests don't need SolidWorks.

## Install

```powershell
git clone https://github.com/<you>/swdraw.git
cd swdraw
uv sync --extra mcp --extra preview
```

Then connect it to your AI client.

**Claude Desktop extension.** Get `swdraw-<version>.mcpb` from Releases (or build it with
`npx @anthropic-ai/mcpb pack . swdraw.mcpb`) and open it in Claude Desktop. Set:

- **Output folder**: traces, results, PDFs and PNG previews
- **Profiles folder** (optional): your `house_style.yaml`, `title_block.yaml`, `numbering.yaml`
- **Scripts folder** (optional): the only folder `swdraw_run_script` can run scripts from

**One command from the clone.** `setup` shows the change first. Add `--apply` to make it. Config
files get a `.bak` backup.

```powershell
uv run python -m swdraw setup claude-code --skill --output-dir ~/swdraw-output --apply
uv run python -m swdraw setup claude-desktop --output-dir ~/swdraw-output --apply   # not if you installed the .mcpb
uv run python -m swdraw setup codex --output-dir ~/swdraw-output --apply
```

`--skill` copies `SKILL.md`, `references/` and `subskills/` to `~/.claude/skills/swdraw` so
Claude Code knows the workflow. Restart the client after.

**Other MCP clients.** Run `uv run --directory <clone> --extra mcp --extra preview python
mcp_server/server.py` over stdio. See [mcp_server/README.md](mcp_server/README.md).

## Profiles and template

Copy `profiles/` somewhere and point `SWDRAW_PROFILES` (or the extension setting) at it. Anything
missing falls back to the bundled files. See [references/profiles.md](references/profiles.md).

For a matching A3 sheet format and drawing template, import `templates/A3_SheetFormat.bas` into a
new SolidWorks macro, edit the constants at the top and run `main`. The constants cover company
name, projection, confidentiality block, and linked properties or placeholders.

## Quick start: the flanged bush

```powershell
# 1. make the part and a drawing with front + isometric views
uv run python examples/flanged_bush/make_part.py --args "{\"out\": \"~/swdraw-example\"}"

# 2. check the spec (no SolidWorks needed)
uv run python -m swdraw validate --spec examples/flanged_bush/bush.drawing.yaml

# 3. with the new drawing active in SolidWorks, build it
uv run python -m swdraw build --spec examples/flanged_bush/bush.drawing.yaml
```

The result lists each step, what each dimension measured, which pick pair worked, and a `check`
block with anything that failed. Look at the exported PNG too. The self-check proves the right
edges got dimensioned, not that the layout is good.

To re-run part of the build, include `clear` or you'll get everything twice:

```powershell
uv run python -m swdraw build --spec bush.drawing.yaml --steps clear,dimensions,gdt,leader_notes,notes,fonts,export
```

Issue revision B:

```powershell
uv run python -m swdraw revise --args "{\"rev\": \"B\", \"desc\": \"BORE TOLERANCE CHANGED\", \"drawn\": \"AD\", \"approved\": \"CC\", \"approver_name\": \"C. CHECKER\"}"
```

## Writing a spec

Anything on geometry (`pick`, `text_at`, section `line`, detail `centre`) is in **model mm**.
Positions on the sheet (`at`) are **sheet mm from the bottom-left corner**. Every dimension has an
`expect` value.

Start from [the spec template](subskills/engineering-drawing/spec_template.yaml). The
[flanged bush spec](examples/flanged_bush/bush.drawing.yaml) is a full example, and
[references/drawing-spec.md](references/drawing-spec.md) covers every key.

## Your own scripts

The helpers are small, so one-off scripts are easy:

```python
import swdraw as sw

dwg = sw.active()
names = [sw.call(v, "GetName2") for v in sw.views(dwg)]
sw.result({"views": names, "args": sw.args()})
```

Run it with `uv run python -m swdraw run my_script.py --args "{...}"`, or from Claude with
`swdraw_run_script` if it's in your scripts folder.

## When something goes wrong

Check [references/troubleshooting.md](references/troubleshooting.md), then
[references/api-gotchas.md](references/api-gotchas.md). Most surprises are the SolidWorks API.

```powershell
uv run python -m swdraw diag views          # names, origins, scales, whether model +Y is up
uv run python -m swdraw diag annotations    # incl. dangling centre marks
```

Every run logs to `swdraw.log` in the output folder.

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

The tests run against a fake SolidWorks API (`tests/fakes.py`). They cover:

- selection and dimension self-checking, including the fallbacks and tolerances
- title-block matching, revisions and notes
- tidy, the register (including formula results when LibreOffice is installed) and numbering
- spec validation and the example's geometry

[CONTRIBUTING.md](CONTRIBUTING.md) lists what they can't cover. CI runs them on Windows and Linux
on every push.

## Licence

MIT. See [LICENSE](LICENSE).
