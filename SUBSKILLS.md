# Subskills

Workflows built on the swdraw tools. Each folder has a `SKILL.md` that Claude reads when the task
matches, plus any templates it needs.

| Subskill | What it covers | Files |
|---|---|---|
| [engineering-drawing](subskills/engineering-drawing/SKILL.md) | a complete drawing from a part: views, sections, self-checked dimensions, GD&T, notes, title block, review loop | `SKILL.md`, `spec_template.yaml` |
| [part-editing](subskills/part-editing/SKILL.md) | changing an existing part: inspect, edit spec, self-check after the rebuild, save with a backup | `SKILL.md`, `edit_template.yaml` |

To add one, create `subskills/<name>/SKILL.md` with `name` and `description` front matter and list
it here and in the root `SKILL.md`. Keep product-specific content in specs and profiles.
