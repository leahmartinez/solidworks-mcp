# Subskills

Focused workflows built on the swdraw tools. Each folder has a `SKILL.md` that Claude (or another
agent) reads when the task matches, plus any templates it needs.

| Subskill | What it covers | Files |
|---|---|---|
| [engineering-drawing](subskills/engineering-drawing/SKILL.md) | a complete drawing from a part: views, sections, self-checked dimensions, GD&T, notes, title block, review loop | `SKILL.md`, `spec_template.yaml` |

To add a subskill: create `subskills/<name>/SKILL.md` with `name` and `description` front matter,
list it here and in the root `SKILL.md`, and keep product-specific content in specs and profiles.
