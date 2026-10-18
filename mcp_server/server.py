"""MCP server exposing swdraw to Claude Desktop (or any MCP client) over stdio.

Each tool runs ``python -m swdraw <command>`` in a fresh subprocess, so a COM failure in one call
cannot wedge the server, and returns the command's JSON result.

Environment (set by the extension's user config, or by hand):
    SWDRAW_OUTPUT_DIR    traces, results, PDFs and PNG previews
    SWDRAW_PROFILES      folder with your house_style / title_block / numbering profiles
    SWDRAW_SCRIPTS_DIR   the only folder swdraw_run_script may run scripts from
    SWDRAW_TIMEOUT_S     per-call timeout (default 600)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:                                   # MCP Python SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server  # noqa: E402
except ImportError:                    # 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # noqa: E402

from swdraw.runner import extract_result  # noqa: E402

mcp = _Server("swdraw")


def _run(cmd: List[str], args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONPATH"] = ROOT + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("PYTHONUTF8", "1")
    full = [sys.executable, "-m", "swdraw"] + cmd
    if args is not None:
        full += ["--args", json.dumps(args)]
    timeout = int(os.environ.get("SWDRAW_TIMEOUT_S", "600"))
    try:
        p = subprocess.run(full, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=env, cwd=ROOT, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timed out after {timeout} s (is a SolidWorks dialog open?)"}
    res = extract_result(p.stdout)
    if res is None:
        return {"ok": False, "exit_code": p.returncode, "stdout": p.stdout[-4000:], "stderr": p.stderr[-4000:]}
    if p.returncode and "log_tail" not in res:
        res["log_tail"] = p.stderr[-2000:]
    return res


@mcp.tool()
def swdraw_validate_spec(spec_path: str) -> Dict[str, Any]:
    """Check a drawing spec (YAML/JSON, absolute path) for missing keys, bad points and dimensions without `expect`. No SolidWorks needed."""
    return _run(["validate", "--spec", spec_path])


@mcp.tool()
def swdraw_build_drawing(spec_path: str, steps: Optional[List[str]] = None,
                         title_block: Optional[Dict[str, Any]] = None, strict: bool = False) -> Dict[str, Any]:
    """Build the ACTIVE SolidWorks drawing from a spec: scale, clear, layout, sections, details, self-checked
    dimensions, GD&T, leader notes, notes block, title block, fonts, PDF/PNG export. Does not save.
    `spec_path` must be absolute. `steps` runs a subset (e.g. ["clear", "dimensions", "gdt", "export"]).
    Look at result.check and the PNG afterwards."""
    cmd = ["build", "--spec", spec_path]
    if steps:
        cmd += ["--steps", ",".join(steps)]
    if strict:
        cmd.append("--strict")
    return _run(cmd, {"title_block": title_block} if title_block else None)


@mcp.tool()
def swdraw_revise(args: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a revision to a drawing (active, or args.drawing): rev row, REV box, approval, SEE NOTE n,
    view shifts, moving dims/GTols to model points. Keys: rev, row, desc, date, drawn, approved,
    approver_name, approved_date, finish_note, shift_views, notes_pos, move_dims, move_gtols, save."""
    return _run(["revise"], args)


@mcp.tool()
def swdraw_renumber(args: Dict[str, Any]) -> Dict[str, Any]:
    """Reference-safe renumber of a part and its drawing (part Save As with the drawing open, notes swap,
    drawing Save As, dependency check, optional supersede/folder rename/verify). Keys: drawing, old, new,
    old_parent, new_parent, description, revision, part, notes_lines, save, supersede, rename_folder."""
    return _run(["renumber"], args)


@mcp.tool()
def swdraw_notes(action: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """action 'replace': delete and re-insert the numbered NOTES: block (args: lines, pos [mm], values, drawing, save).
    action 'dedupe': keep the numbered block, delete copies that lost their numbering (args: pos, drawing, save)."""
    return _run(["notes", action], args)


@mcp.tool()
def swdraw_export_pdf(args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Export the active drawing (or args.drawing) to PDF, plus a PNG preview for visual checking (args.path, args.png)."""
    return _run(["export"], args or {})


@mcp.tool()
def swdraw_tidy(args: Dict[str, Any]) -> Dict[str, Any]:
    """Move files that aren't live out of a working folder. DRY RUN unless dry_run is false.
    Keys: working, keep (glob list), superseded, move_folders, dry_run."""
    return _run(["tidy"], args)


@mcp.tool()
def swdraw_register(args: Dict[str, Any]) -> Dict[str, Any]:
    """Generate the drawing register workbook (Register / Revision History / Numbering).
    Keys: out, title, drawings [{number,title,type,parent,file}], revisions [{number,rev,date,description,by,approved,status}],
    or data: path to a YAML/JSON file with those keys; numbering_profile."""
    return _run(["register"], args)


@mcp.tool()
def swdraw_number(action: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Part numbers. action 'check' (args.numbers), 'next-part' (args.assembly, args.used), 'next-assembly' (args.used, args.discipline)."""
    return _run(["number", action], args)


@mcp.tool()
def swdraw_diagnostics(what: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Read-only probes of the active drawing: 'views', 'selection', 'annotations'; or 'refs' with args.paths."""
    return _run(["diag", what], args or {})


@mcp.tool()
def swdraw_run_script(script: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run one of your own Python scripts from SWDRAW_SCRIPTS_DIR with swdraw importable
    (`import swdraw as sw; sw.args(); sw.result({...})`)."""
    base = os.environ.get("SWDRAW_SCRIPTS_DIR")
    if not base:
        return {"ok": False, "error": "SWDRAW_SCRIPTS_DIR is not set"}
    base = os.path.realpath(os.path.expanduser(base))
    path = os.path.realpath(os.path.join(base, script))
    if os.path.commonpath([base, path]) != base or not path.lower().endswith(".py"):
        return {"ok": False, "error": "script must be a .py file inside SWDRAW_SCRIPTS_DIR"}
    if not os.path.isfile(path):
        return {"ok": False, "error": f"not found: {script}"}
    return _run(["run", path], args or {})


if __name__ == "__main__":
    mcp.run()
