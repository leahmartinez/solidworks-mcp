"""Revise an already-built drawing: revision row, REV box, approval, finish reference, small moves.

Arguments (all optional except ``rev``)::

    rev: B                     # new revision letter
    row: 2                     # revision-table row (1 = first issue); default from the letter
    desc: "UPDATED BORE TOLERANCE"
    date: 18/10/2026           # default today in the house date format
    drawn: AB                  # initials for the DRAWN column
    approved: CD               # initials for the APP'D column
    approver_name: "C. DOE"    # title-block APPROVED name
    approved_date: 18/10/2026  # default = date
    finish_note: 4             # rewrite "... SEE NOTE n" references to this number
    shift_views: {"Drawing View1": [dx_mm, dy_mm]}
    notes_pos: [x_mm, y_mm]    # move the NOTES: block
    move_dims:  [{view, value, tol (optional swTolType), to: [x,y,z] model mm}]
    move_gtols: [{view, symbol: SRUN, to: [x,y,z]}]
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List

from . import com, title_block as tb
from .config import HouseStyle
from .geometry import model_to_sheet
from .notes import find_blocks


def row_for(rev: str) -> int:
    """1-based revision-table row for a revision letter (A=1, B=2 ...) or a number."""
    rev = str(rev).strip().upper()
    if rev.isdigit():
        return int(rev) + 1          # numeric revisions start at 0
    if len(rev) == 1 and rev.isalpha():
        return ord(rev) - ord("A") + 1
    raise ValueError(f"cannot infer a revision-table row from {rev!r}; pass row explicitly")


def get_custom_property(doc, name: str, config: str = "") -> str:
    cpm = doc.Extension.CustomPropertyManager(config)
    try:
        res = cpm.Get6(name, False, "", "", False, False)
        # late binding returns (status, value, resolved, wasResolved, linkToProperty)
        if isinstance(res, (list, tuple)) and len(res) >= 3:
            return str(res[2] or res[1] or "")
        return str(res or "")
    except Exception:
        return ""


def _see_note(text: str, n: int, marker: str = "SEE NOTE") -> str:
    up = text.upper()
    if marker not in up:
        return text
    return text[:up.index(marker)] + f"{marker} {n}"


def apply(dwg, a: Dict[str, Any], profile: Dict[str, Any], style: HouseStyle = None) -> Dict[str, Any]:
    style = style or HouseStyle()
    rep: Dict[str, Any] = {"title": [], "moved": [], "errors": []}
    rev = str(a["rev"])
    row = int(a.get("row") or row_for(rev)) - 1
    date = a.get("date") or _dt.date.today().strftime(style.date_format)
    row_vals = {"rev": rev, "desc": a.get("desc"), "date": date, "drawn": a.get("drawn"),
                "approved": a.get("approved")}
    fields = {"revision": rev, "approved_by": a.get("approver_name"),
              "approved_date": a.get("approved_date") or (date if a.get("approver_name") else None)}

    if profile.get("mode", "custom_properties") == "custom_properties":
        props = tb.property_values(fields, profile)
        props.update(tb.rev_row_properties(row, row_vals, profile))
        rep["title"] += tb.set_custom_properties(dwg, props)
        if a.get("finish_note"):
            cp = profile["custom_properties"]
            prop = cp["fields"].get("finish", "Finish")
            owner = dwg
            if "finish" in (cp.get("model_fields") or []):
                owner = tb.referenced_model(dwg) or dwg
            cur = get_custom_property(owner, prop)
            new = _see_note(cur, int(a["finish_note"]))
            if new != cur:
                rep["title"] += tb.set_custom_properties(owner, {prop: new})
            elif "SEE NOTE" not in cur.upper():
                rep["errors"].append(f"finish_note: property {prop!r} has no 'SEE NOTE' reference")
    else:
        notes = tb.read_sheet_notes(dwg)
        ups = tb.plan_rev_row(notes, row, row_vals, profile)
        ups += tb.plan_rev_box(notes, rev, profile)
        ups += tb.plan_fields(notes, fields, profile)
        if a.get("finish_note"):
            ups += tb.plan_see_note(notes, int(a["finish_note"]), profile)
        rep["title"] += tb.apply_updates(ups, style.font)
        if not any(u.field.startswith(f"rev{row + 1}.") for u in ups):
            rep["errors"].append(f"no revision-table cells found for row {row + 1}; check rev_table in the profile")

    _shift_views(dwg, a.get("shift_views") or {}, rep)
    if a.get("notes_pos"):
        for nt, _vn, _p, _t in find_blocks(dwg):
            com.call(nt, "GetAnnotation").SetPosition2(a["notes_pos"][0] / 1000.0, a["notes_pos"][1] / 1000.0, 0)
            rep["moved"].append(f"notes -> {a['notes_pos']}")
    for m in a.get("move_dims") or []:
        _move_dim(dwg, m, rep)
    for m in a.get("move_gtols") or []:
        _move_gtol(dwg, m, rep)
    com.call(dwg, "GraphicsRedraw2")
    return rep


def _shift_views(dwg, shifts: Dict[str, List[float]], rep) -> None:
    for vn, (dx, dy) in shifts.items():
        v = com.find_view(dwg, vn)
        if v is None:
            rep["errors"].append(f"no view {vn}")
            continue
        p = list(com.call(v, "Position"))
        v.Position = com.arr8([p[0] + dx / 1000.0, p[1] + dy / 1000.0])
        rep["moved"].append(f"{vn} by ({dx}, {dy}) mm")
    if shifts:
        com.call(dwg, "EditRebuild3")


def _sheet_point(view, xyz):
    return model_to_sheet(list(com.call(com.call(view, "ModelToViewTransform"), "ArrayData")), *xyz)


def _move_dim(dwg, m, rep) -> None:
    v = com.find_view(dwg, m["view"])
    if v is None:
        rep["errors"].append(f"no view {m['view']}")
        return
    for dd in com.display_dims(v):
        d = dd.GetDimension2(0)
        val = float(com.call(d, "SystemValue")) * 1000
        tt = int(com.call(com.call(d, "Tolerance"), "Type"))
        if abs(val - float(m["value"])) < 0.002 and ("tol" not in m or tt == int(m["tol"])):
            tx, ty = _sheet_point(v, m["to"])
            com.call(dd, "GetAnnotation").SetPosition2(tx, ty, 0)
            rep["moved"].append(f"dim {m['value']} in {m['view']}")
            return
    rep["errors"].append(f"dim {m['value']} not found in {m['view']}")


def _move_gtol(dwg, m, rep) -> None:
    v = com.find_view(dwg, m["view"])
    for g in (com.gtols(v) if v is not None else []):
        try:
            sym = str(list(g.GetFrameSymbols3(1))[0])
        except Exception:
            sym = ""
        if m["symbol"] in sym:
            tx, ty = _sheet_point(v, m["to"])
            com.call(g, "GetAnnotation").SetPosition2(tx, ty, 0)
            rep["moved"].append(f"gtol {m['symbol']} in {m['view']}")
            return
    rep["errors"].append(f"gtol {m['symbol']} not found in {m['view']}")
