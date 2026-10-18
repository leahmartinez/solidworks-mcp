"""Edit an existing part from a spec, rebuild it and check the result before saving.

Order: design-table cells, configuration, global variables, equations, dimensions; then
evaluate equations, rebuild, read every changed dimension back, list features with rebuild errors
and compare mass properties with ``expect``. The part is saved only when everything passed and
the spec (or the caller) says ``save: true``, and only after the file on disk has been copied to a
backup. On a failure nothing is saved; with ``on_failure: revert`` the old values are put back.
"""
from __future__ import annotations

import datetime as _dt
import os
import shutil
from typing import Any, Callable, Dict, List, Optional

from .. import com
from ..config import expand
from ..runner import log
from . import part as P
from .spec import INTEGER, check_expect, from_system, to_system, unit_of, validate_edit_spec

READ_BACK_TOL = 1e-6        # mm or degrees


def backup_path(part_path: str, backup_dir: Optional[str] = None, now: Optional[_dt.datetime] = None) -> str:
    """``<name>.bak.SLDPRT`` next to the part (or in ``backup_dir``); timestamped if that exists."""
    folder = expand(backup_dir) if backup_dir else os.path.dirname(part_path)
    stem, ext = os.path.splitext(os.path.basename(part_path))
    path = os.path.join(folder, f"{stem}.bak{ext}")
    if os.path.exists(path):
        stamp = (now or _dt.datetime.now()).strftime("%Y%m%d-%H%M%S")
        path = os.path.join(folder, f"{stem}.bak-{stamp}{ext}")
    return path


def _fmt(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


class _Edit:
    def __init__(self, doc, spec: Dict[str, Any]):
        self.doc, self.spec = doc, spec
        self.all_configs = spec.get("apply_to", "this") == "all"
        self.changes: List[Dict[str, Any]] = []
        self.undo: List[Callable[[], Any]] = []
        self.dims_to_check: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ changes
    def design_table(self):
        dt = self.spec.get("design_table") or {}
        if dt.get("set"):
            recs = P.set_design_table(self.doc, dt["row"], dt["set"])
            for r in recs:
                if "old" in r and "error" not in r:
                    row, header = r["name"].split("/", 1)
                    self.undo.append(lambda row=row, h=header, old=r["old"]: P.set_design_table(self.doc, row, {h: old}))
            self.changes += recs

    def configuration(self):
        name = self.spec.get("configuration") or (self.spec.get("design_table") or {}).get("row")
        if not name:
            return
        before = P.configurations(self.doc)
        rec = {"kind": "configuration", "name": name, "old": before["active"], "new": name}
        if name not in before["names"]:
            rec["error"] = f"no such configuration (has: {', '.join(before['names'])})"
        elif name != before["active"]:
            if P.activate_configuration(self.doc, name):
                self.undo.append(lambda old=before["active"]: P.activate_configuration(self.doc, old))
            else:
                rec["error"] = "ShowConfiguration2 returned False"
        self.changes.append(rec)

    def _equation(self, kind: str, name: str, rhs, want_global: bool):
        eqs = P.equations(self.doc)
        e = P.find_equation(eqs, name, want_global)
        rec = {"kind": kind, "name": name, "new": _fmt(rhs)}
        if e is None:
            what = "global variable" if want_global else "equation with that left-hand side"
            rec["error"] = f"no {what}; run swdraw model inspect to see what the part has"
            self.changes.append(rec)
            return
        rec["old"] = e["rhs"]
        text = f'"{e["lhs"]}" = {_fmt(rhs)}'
        how = P.set_equation(self.doc, e["index"], text, all_configs=True)
        if how is None:
            rec["error"] = "SolidWorks did not accept the new equation (check the expression)"
        else:
            rec["via"] = how
            self.undo.append(lambda i=e["index"], t=e["text"]: P.set_equation(self.doc, i, t))
        self.changes.append(rec)

    def globals(self):
        for name, value in (self.spec.get("globals") or {}).items():
            self._equation("global", str(name), value, True)

    def equations(self):
        for name, rhs in (self.spec.get("equations") or {}).items():
            self._equation("equation", str(name), rhs, False)

    def dimensions(self):
        eqs = P.equations(self.doc) if self.spec.get("dimensions") else []
        for name, value in (self.spec.get("dimensions") or {}).items():
            name = str(name)
            rec: Dict[str, Any] = {"kind": "dimension", "name": name}
            self.changes.append(rec)
            dim = P.get_dimension(self.doc, name)
            if dim is None:
                rec["error"] = "no dimension with that name; run swdraw model inspect for the full names"
                continue
            kind = P.dim_kind(dim)
            rec.update(old=round(P.dim_value(dim), 6), unit=unit_of(kind) or "count")
            try:
                target = to_system(value, kind)
            except ValueError as exc:
                rec["error"] = str(exc)
                continue
            rec["new"] = from_system(target, kind)
            if kind == INTEGER and not float(rec["new"]).is_integer():
                rec["error"] = "a count must be a whole number"
                continue
            driver = P.find_equation(eqs, name, want_global=False)
            if driver is not None:
                rec["error"] = (f"driven by equation {driver['index']} ({driver['text']}); "
                                "change the global variable or the equation instead")
                continue
            if P.dim_read_only(dim):
                rec["error"] = "read-only (a driven or reference dimension)"
                continue
            old_si = float(com.call(dim, "SystemValue"))
            how = P.set_dimension(dim, target, self.all_configs)
            if how is None:
                rec["error"] = "SolidWorks refused the value"
                continue
            rec["via"] = how
            self.undo.append(lambda d=dim, v=old_si: P.set_dimension(d, v, self.all_configs))
            self.dims_to_check.append(rec)

    # ------------------------------------------------------------------ after the rebuild
    def read_back(self):
        for rec in self.dims_to_check:
            dim = P.get_dimension(self.doc, rec["name"])
            got = P.dim_value(dim) if dim is not None else None
            rec["read_back"] = None if got is None else round(got, 6)
            if got is None or abs(got - float(rec["new"])) > READ_BACK_TOL * max(1.0, abs(float(rec["new"]))):
                rec["error"] = (f"reads {rec['read_back']} {rec['unit']} after the rebuild "
                                "(an equation, design table or configuration may override it)")

    def revert(self) -> List[str]:
        problems = []
        for fn in reversed(self.undo):
            try:
                if fn() in (None, False):
                    problems.append("an undo step did not report success")
            except Exception as exc:
                problems.append(str(exc))
        P.evaluate_equations(self.doc)
        P.rebuild(self.doc)
        return problems


def edit(spec: Dict[str, Any], doc=None, save: Optional[bool] = None) -> Dict[str, Any]:
    """Apply an edit spec to a part. ``save`` overrides the spec's ``save``."""
    problems = validate_edit_spec(spec)
    if problems:
        return {"ok": False, "problems": problems,
                "check": {"ok": False, "next": "Fix the spec (swdraw model validate) and run again."}}
    doc = doc or P.open_part(expand(spec["part"]) if spec.get("part") else None)
    want_save = bool(spec.get("save", False) if save is None else save)
    path = P.path_of(doc)
    was_dirty = P.is_dirty(doc)
    rep: Dict[str, Any] = {"part": path, "warnings": []}
    if was_dirty:
        rep["warnings"].append("the part already had unsaved changes before this edit")
    before = P.measure(doc)
    log(f"model edit: {path or '(unsaved part)'}")

    ed = _Edit(doc, spec)
    for step in (ed.design_table, ed.configuration, ed.globals, ed.equations, ed.dimensions):
        step()
    P.evaluate_equations(doc)
    rebuilt = P.rebuild(doc)
    ed.read_back()

    flagged = P.feature_errors(doc)
    errors = [e for e in flagged if not e["warning"]]
    warnings = [e for e in flagged if e["warning"]]
    after = P.measure(doc)
    checks = check_expect(spec.get("expect") or {}, after)
    if "mass_g" in (spec.get("expect") or {}) and not after.get("material"):
        rep["warnings"].append("no material assigned: mass uses SolidWorks' default density")
    if not rebuilt:
        rep["warnings"].append("ForceRebuild3 returned False")

    failed_changes = [c["name"] for c in ed.changes if "error" in c]
    failed_expect = [c["check"] for c in checks if not c["ok"]]
    ok = not (failed_changes or errors or failed_expect)
    rep.update(changes=ed.changes, rebuild_errors=errors, rebuild_warnings=warnings, expect=checks,
               measured={"before": before, "after": after})

    if not ok and spec.get("on_failure", "keep") == "revert" and ed.undo:
        rep["reverted"] = True
        rep["revert_problems"] = ed.revert()
        rep["measured"]["after_revert"] = P.measure(doc)

    rep["save"] = _save(doc, spec, path, ok, want_save, was_dirty) if want_save else {"saved": False, "requested": False}
    rep["ok"] = ok and (rep["save"].get("saved") or not want_save)
    rep["check"] = {
        "ok": rep["ok"], "failed_changes": failed_changes, "rebuild_errors": [e["feature"] for e in errors],
        "failed_expect": failed_expect, "saved": bool(rep["save"].get("saved")), "backup": rep["save"].get("backup"),
        "next": _next(ok, want_save, rep),
    }
    return rep


def _save(doc, spec, path, ok, want_save, was_dirty) -> Dict[str, Any]:
    out: Dict[str, Any] = {"requested": True, "saved": False}
    if not ok:
        out["error"] = "checks failed, so the part was not saved"
    elif not path or not os.path.isfile(path):
        out["error"] = "the part has never been saved to a file; save it in SolidWorks first"
    elif P.is_read_only(doc) or not os.access(path, os.W_OK):
        out["error"] = "the part is open read-only or the file is not writable"
    elif was_dirty and not spec.get("allow_unsaved_changes"):
        out["error"] = ("the part had unsaved changes before this edit; saving would include them. "
                        "Save or discard them in SolidWorks, or set allow_unsaved_changes: true")
    if "error" in out:
        return out
    bak = backup_path(path, spec.get("backup_dir") or os.environ.get("SWDRAW_BACKUP_DIR"))
    try:
        os.makedirs(os.path.dirname(bak), exist_ok=True)
        shutil.copy2(path, bak)
    except OSError as exc:
        out["error"] = f"backup failed ({exc}); not saved"
        return out
    if os.path.getsize(bak) != os.path.getsize(path):
        out["error"] = f"backup {bak} is incomplete; not saved"
        return out
    out["backup"] = bak
    out.update(P.save(doc))
    return out


def _next(ok: bool, want_save: bool, rep: Dict[str, Any]) -> str:
    if not ok:
        if rep.get("reverted"):
            return "Checks failed and the old values were put back. Fix the spec and run again."
        return ("Checks failed; nothing was saved and the changes are still in the open part. Look at "
                "changes, rebuild_errors and expect, then fix the spec or close the part without saving.")
    if want_save:
        return "Saved. The original is at save.backup." if rep["save"].get("saved") else \
            f"Checks passed but the part was not saved: {rep['save'].get('error')}"
    return "Checks passed. The part is changed in SolidWorks but not saved; run again with save: true to keep it."
