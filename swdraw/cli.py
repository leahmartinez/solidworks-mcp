"""Command line: ``python -m swdraw <command> [options]``.

Commands that need SolidWorks: build, revise, renumber, notes, export, diag, run.
Commands that don't: validate, tidy, register, number.

Every command prints one JSON result between SWDRAW_RESULT_BEGIN/END markers.
"""
from __future__ import annotations

import argparse
import os
import runpy
import sys
from typing import Any, Dict, List, Optional

from . import runner
from .config import HouseStyle, load_file, load_title_block


def _args(ns) -> Dict[str, Any]:
    return runner.parse_args_value(ns.args) if getattr(ns, "args", None) else {}


def cmd_build(ns) -> Dict[str, Any]:
    from .drawing import build, load_spec
    spec = load_spec(ns.spec)
    steps = [s.strip() for s in ns.steps.split(",")] if ns.steps else None
    return build(spec, steps=steps, title_overrides=_args(ns).get("title_block"), strict=ns.strict)


def cmd_validate(ns) -> Dict[str, Any]:
    from .drawing import load_spec, validate_spec
    probs = validate_spec(load_spec(ns.spec))
    return {"ok": not probs, "problems": probs}


def cmd_revise(ns) -> Dict[str, Any]:
    from . import com, revision
    a = _args(ns)
    dwg = com.open_doc(a["drawing"]) if a.get("drawing") else com.active()
    rep = revision.apply(dwg, a, load_title_block(a.get("title_block_profile")), HouseStyle.load())
    if a.get("save"):
        rep["saved"] = bool(dwg.Save2(True))
    return rep


def cmd_renumber(ns) -> Dict[str, Any]:
    from . import renumber
    from .numbering import Scheme
    a = _args(ns)
    cfg = load_file(a["numbering_profile"]) if a.get("numbering_profile") else None
    return renumber.renumber(a, Scheme(cfg), HouseStyle.load())


def cmd_notes(ns) -> Dict[str, Any]:
    from . import com, notes
    a = _args(ns)
    dwg = com.open_doc(a["drawing"]) if a.get("drawing") else com.active()
    pos = [p / 1000.0 for p in a["pos"]] if a.get("pos") else None
    if ns.action == "replace":
        rep = notes.replace_block(dwg, a["lines"], pos, HouseStyle.load(), values=a.get("values"))
    else:
        rep = notes.dedupe_blocks(dwg, pos)
    if a.get("save") and not rep.get("errors"):
        rep["saved"] = bool(dwg.Save2(True))
    return rep


def cmd_export(ns) -> Dict[str, Any]:
    from . import com
    from .drawing import export as exp
    a = _args(ns)
    dwg = com.open_doc(a["drawing"]) if a.get("drawing") else com.active()
    res = exp.export_pdf(dwg, a.get("path"))
    if res.get("ok") and a.get("png", True):
        res["png"] = exp.preview_png(res["path"])
    return res


def cmd_tidy(ns) -> Dict[str, Any]:
    from .tidy import tidy
    a = _args(ns)
    return tidy(a["working"], a.get("keep", []), a.get("superseded"), a.get("move_folders"),
                dry_run=a.get("dry_run", True))


def cmd_register(ns) -> Dict[str, Any]:
    from .numbering import Scheme
    from .register import build_register
    a = _args(ns)
    data = load_file(a["data"]) if isinstance(a.get("data"), str) else a
    cfg = load_file(a["numbering_profile"]) if a.get("numbering_profile") else None
    out = os.path.expanduser(a.get("out") or os.path.join(runner.output_dir(), "Drawing Register.xlsx"))
    return {"path": build_register(out, data, Scheme(cfg))}


def cmd_number(ns) -> Dict[str, Any]:
    from .numbering import Scheme
    a = _args(ns)
    sc = Scheme(load_file(a["numbering_profile"]) if a.get("numbering_profile") else None)
    used = a.get("used", [])
    if ns.action == "next-part":
        return {"number": sc.next_part(a["assembly"], used)}
    if ns.action == "next-assembly":
        return {"number": sc.next_assembly(used, a.get("discipline", "MEC"))}
    return {n: (sc.describe(n) if sc.is_valid(n) else "invalid") for n in a.get("numbers", [])}


def cmd_diag(ns) -> Dict[str, Any]:
    from . import com, diagnostics as dg
    a = _args(ns)
    if ns.what == "refs":
        return dg.refs_report(a.get("paths", []))
    dwg = com.active()
    return {"views": dg.views_report, "selection": dg.selection_report,
            "annotations": dg.annotations_report}[ns.what](dwg)


def cmd_run(ns) -> Optional[Dict[str, Any]]:
    """Run your own script with swdraw importable and the args available via swdraw.runner.args()."""
    runner.set_args(_args(ns))
    sys.argv = [ns.script]
    runpy.run_path(ns.script, run_name="__main__")
    return None      # the script prints its own result


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="swdraw", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, fn, helptext, spec=False):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--args", help="JSON object, or path to a .json/.yaml file")
        if spec:
            sp.add_argument("--spec", required=True, help="drawing spec (.yaml/.json)")
        sp.set_defaults(fn=fn)
        return sp

    b = add("build", cmd_build, "build the active drawing from a spec", spec=True)
    b.add_argument("--steps", help="comma-separated subset of steps")
    b.add_argument("--strict", action="store_true", help="refuse to run if the spec has problems")
    add("validate", cmd_validate, "check a spec without SolidWorks", spec=True)
    add("revise", cmd_revise, "apply a revision to a drawing")
    add("renumber", cmd_renumber, "reference-safe renumber of a part and its drawing")
    n = add("notes", cmd_notes, "replace or dedupe the numbered notes block")
    n.add_argument("action", choices=["replace", "dedupe"])
    add("export", cmd_export, "export the drawing to PDF (+PNG preview)")
    add("tidy", cmd_tidy, "move non-live files out of a working folder (dry run by default)")
    add("register", cmd_register, "generate the drawing register workbook")
    nb = add("number", cmd_number, "part numbers: check, next-part, next-assembly")
    nb.add_argument("action", choices=["check", "next-part", "next-assembly"])
    d = add("diag", cmd_diag, "read-only diagnostics")
    d.add_argument("what", choices=["views", "selection", "annotations", "refs"])
    r = add("run", cmd_run, "run your own script with swdraw available")
    r.add_argument("script")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    ns = make_parser().parse_args(argv)
    try:
        res = ns.fn(ns)
    except Exception as exc:
        runner.result({"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}, name=ns.command)
        return 1
    if res is not None:
        runner.result(res if isinstance(res, dict) else {"result": res}, name=ns.command)
    return 0
