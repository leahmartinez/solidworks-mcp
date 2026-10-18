"""Regenerate capabilities.yaml from the MCP server's tool definitions.

    uv run --extra mcp python scripts/generate_capabilities.py          # write
    uv run --extra mcp python scripts/generate_capabilities.py --check  # fail if out of date (CI)
"""
from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "capabilities.yaml")

NEEDS_SOLIDWORKS = {"swdraw_build_drawing", "swdraw_revise", "swdraw_renumber", "swdraw_notes",
                    "swdraw_export_pdf", "swdraw_diagnostics", "swdraw_run_script"}
CHANGES_FILES = {"swdraw_build_drawing": "the active drawing (not saved)",
                 "swdraw_revise": "the drawing; saves only with save: true",
                 "swdraw_renumber": "renames part and drawing files; supersede moves old files",
                 "swdraw_notes": "the drawing; saves only with save: true",
                 "swdraw_export_pdf": "writes PDF/PNG to the output folder",
                 "swdraw_tidy": "moves files unless dry_run (default true)",
                 "swdraw_register": "writes the register workbook",
                 "swdraw_run_script": "whatever the script does"}


def render() -> str:
    import yaml
    from mcp_server import server
    tools = asyncio.run(server.mcp.list_tools())
    data = {"name": "swdraw", "version": __import__("swdraw").__version__,
            "generated_by": "scripts/generate_capabilities.py (do not edit by hand)",
            "tools": []}
    for t in sorted(tools, key=lambda t: t.name):
        schema = getattr(t, "inputSchema", None) or getattr(t, "input_schema", {}) or {}
        props = schema.get("properties", {})
        req = set(schema.get("required", []))
        data["tools"].append({
            "name": t.name,
            "description": " ".join((t.description or "").split()),
            "needs_solidworks": t.name in NEEDS_SOLIDWORKS,
            "changes": CHANGES_FILES.get(t.name, "nothing (read-only)"),
            "arguments": {k: ("required" if k in req else "optional") for k in props},
        })
    return "# swdraw MCP tools. Generated; run scripts/generate_capabilities.py after changing mcp_server/server.py.\n" + \
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        cur = open(OUT, encoding="utf-8").read() if os.path.isfile(OUT) else ""
        if cur != text:
            print("capabilities.yaml is out of date: run scripts/generate_capabilities.py")
            return 1
        print("capabilities.yaml is up to date")
        return 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
