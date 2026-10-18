"""Build a drawing from a spec, step by step.

Steps, in order (run all, or pass ``steps`` to run a subset)::

    scale         sheet scale
    clear         delete old dimensions, GTols, datums, matching notes, dangling centre marks
    layout        view scales and positions
    sections      section views (upright check, alternative source views)
    details       detail views
    dimensions    self-checked dimensions with tolerances
    gdt           datum tags, then feature control frames
    leader_notes  notes with leaders
    notes         numbered notes block
    title         title block (custom properties or placeholder notes); `revision_row` fills the
                  revision-table row for the current revision
    fonts         house style everywhere except the title block
    export        PDF (+ PNG preview) and a check summary

The active document must be a drawing whose model views already exist (the spec names them).
The drawing is never saved by the builder.
"""
from __future__ import annotations

import datetime as _dt
import traceback
from typing import Any, Callable, Dict, List, Optional, Sequence

from .. import com, title_block as tb
from ..config import HouseStyle, load_file, load_title_block
from ..runner import log
from . import annotations as ann
from . import dims, export as exp, fonts, views
from .context import DrawingContext, Report

STEPS = ["scale", "clear", "layout", "sections", "details", "dimensions", "gdt",
         "leader_notes", "notes", "title", "fonts", "export"]


class SpecError(ValueError):
    pass


def validate_spec(spec: Dict[str, Any]) -> List[str]:
    """Return a list of problems (empty = OK). Pure: runs without SolidWorks."""
    probs: List[str] = []
    ids = set()

    def need(obj, keys, where):
        for k in keys:
            if k not in obj:
                probs.append(f"{where}: missing '{k}'")

    def point(p, where):
        try:
            seq = p["at"] if isinstance(p, dict) else p
            if len(seq) < 3 or not all(isinstance(v, (int, float)) for v in list(seq)[:3]):
                raise TypeError
        except Exception:
            probs.append(f"{where}: expected a model point [x, y, z] (mm)")

    for i, s in enumerate(spec.get("sections") or []):
        need(s, ("id", "line", "at"), f"sections[{i}]")
        if not (s.get("from_views") or s.get("from_view")):
            probs.append(f"sections[{i}]: missing 'from_views'")
        ids.add(s.get("id"))
    for i, d in enumerate(spec.get("details") or []):
        need(d, ("id", "parent", "centre", "radius_mm", "scale", "at"), f"details[{i}]")
        ids.add(d.get("id"))
    seen = set()
    for i, d in enumerate(spec.get("dimensions") or []):
        w = f"dimensions[{i}] ({d.get('id', '?')})"
        need(d, ("id", "view", "pick", "text_at"), w)
        if d.get("id") in seen:
            probs.append(f"{w}: duplicate id")
        seen.add(d.get("id"))
        for j, p in enumerate(d.get("pick") or []):
            point(p, f"{w}.pick[{j}]")
        if "pick" in d and not 1 <= len(d["pick"]) <= 2:
            probs.append(f"{w}: pick needs one or two points")
        if "expect" not in d:
            probs.append(f"{w}: no 'expect' value; the dimension cannot be self-checked")
        tol = d.get("tolerance")
        if tol:
            t = str(tol.get("type", "")).lower()
            if t not in dims.TOL and not (t.isdigit() and int(t) in dims.TOL.values()):
                probs.append(f"{w}: unknown tolerance type {t!r}")
            if t in ("bilateral", "limit", "symmetric", "2", "3", "4") and ("lower" not in tol or "upper" not in tol):
                probs.append(f"{w}: tolerance needs 'lower' and 'upper' (mm)")
    for i, d in enumerate((spec.get("gdt") or {}).get("datums") or []):
        need(d, ("label", "view"), f"gdt.datums[{i}]")
        if d.get("on_dim") and d["on_dim"] not in seen:
            probs.append(f"gdt.datums[{i}]: on_dim {d['on_dim']!r} is not a dimension id")
        if not d.get("on_dim") and d.get("edge") is None:
            probs.append(f"gdt.datums[{i}]: needs 'on_dim' or 'edge'")
    for i, f in enumerate((spec.get("gdt") or {}).get("frames") or []):
        need(f, ("view", "frames", "text_at"), f"gdt.frames[{i}]")
    for i, n in enumerate(spec.get("leader_notes") or []):
        need(n, ("view", "text", "text_at"), f"leader_notes[{i}]")
    nb = spec.get("notes")
    if nb:
        need(nb, ("lines", "at"), "notes")
    return probs


def _steps_table(spec: Dict[str, Any], ctx: DrawingContext, title_profile: Dict[str, Any],
                 values: Dict[str, Any]) -> Dict[str, Callable[[], Any]]:
    def do_scale():
        sc = (spec.get("drawing") or {}).get("sheet_scale")
        return views.set_sheet_scale(ctx, *sc) if sc else "skipped"

    def do_clear():
        c = spec.get("clear") or {}
        return views.clear_annotations(ctx, c.get("note_patterns", ["NOTES:"]),
                                       dangling_marks=c.get("dangling_centre_marks", True))

    def do_layout():
        return views.layout(ctx, spec.get("layout") or []) if spec.get("layout") else "skipped"

    def do_sections():
        return "; ".join(views.section(ctx, s) for s in spec.get("sections") or []) or "skipped"

    def do_details():
        out = []
        for d in spec.get("details") or []:
            try:
                out.append(views.detail(ctx, d))
            except Exception as exc:
                ctx.report.errors.append(f"detail {d.get('id')}: {exc}")
                out.append(f"{d.get('id')}: failed")
        return "; ".join(out) or "skipped"

    def do_dimensions():
        ctx.regen()
        for d in spec.get("dimensions") or []:
            try:
                dims.add_dimension(ctx, d)
            except Exception as exc:
                ctx.report.dims.append({"id": d.get("id"), "error": str(exc)})
                ctx.report.errors.append(f"{d.get('id')}: {exc}")
        bad = [d for d in ctx.report.dims if "error" in d]
        return f"{len(ctx.report.dims) - len(bad)} ok, {len(bad)} failed"

    def do_gdt():
        g = spec.get("gdt") or {}
        for d in spec.get("dimensions") or []:
            ctx.state.setdefault("dimspec:" + str(d.get("id")), d)
        ok = sum(ann.datum_tag(ctx, d) for d in g.get("datums") or [])
        ok += sum(ann.gdt_frame(ctx, f) for f in g.get("frames") or [])
        return f"{ok} placed"

    def do_leader_notes():
        return f"{sum(ann.leader_note(ctx, n) for n in spec.get('leader_notes') or [])} placed"

    def do_notes():
        nb = spec.get("notes")
        if not nb:
            return "skipped"
        ann.notes_block(ctx, nb["lines"], nb["at"], nb.get("heading", "NOTES:"), values)
        return "ok"

    def do_title():
        if not values:
            return "skipped"
        done = tb.fill(ctx.dwg, values, title_profile, font=None)
        row = spec.get("revision_row")
        if row and title_profile.get("mode", "custom_properties") == "custom_properties":
            from ..revision import row_for
            rev = str(values.get("revision", "A"))
            cells = {"rev": rev, "desc": row.get("desc"), "date": row.get("date") or values.get("drawn_date"),
                     "drawn": row.get("drawn"), "approved": row.get("approved")}
            done += tb.set_custom_properties(ctx.dwg, tb.rev_row_properties(row_for(rev) - 1, cells, title_profile))
        ctx.report.extra["title_block"] = done
        return f"{len(done)} fields"

    def do_fonts():
        return fonts.apply_house_style(ctx)

    def do_export():
        e = spec.get("export") or {}
        if e.get("pdf", True) is False:
            return "skipped"
        ctx.rebuild()
        res = exp.export_pdf(ctx.dwg, e.get("path"), stem=(spec.get("drawing") or {}).get("id"))
        if res.get("ok") and e.get("png", True):
            res["png"] = exp.preview_png(res["path"])
        ctx.report.extra["export"] = res
        return "ok" if res.get("ok") else "failed"

    return {"scale": do_scale, "clear": do_clear, "layout": do_layout, "sections": do_sections,
            "details": do_details, "dimensions": do_dimensions, "gdt": do_gdt,
            "leader_notes": do_leader_notes, "notes": do_notes, "title": do_title,
            "fonts": do_fonts, "export": do_export}


def title_values(spec: Dict[str, Any], overrides: Optional[Dict[str, Any]] = None,
                 style: Optional[HouseStyle] = None) -> Dict[str, Any]:
    style = style or HouseStyle()
    vals = dict(spec.get("title_block") or {})
    vals.update(overrides or {})
    today = _dt.date.today().strftime(style.date_format)
    for k in ("drawn_date",):
        if vals.get(k) == "today":
            vals[k] = today
    if vals.get("approved_date") == "today":
        vals["approved_date"] = today
    return vals


def build(spec: Dict[str, Any], steps: Optional[Sequence[str]] = None, dwg=None,
          title_overrides: Optional[Dict[str, Any]] = None, strict: bool = False) -> Dict[str, Any]:
    """Run the spec against the active drawing (or ``dwg``). Returns the report dict."""
    problems = validate_spec(spec)
    if problems and strict:
        raise SpecError("; ".join(problems))
    style = HouseStyle.load((spec.get("profiles") or {}).get("house_style"), spec.get("style"))
    title_profile = load_title_block((spec.get("profiles") or {}).get("title_block"))
    dwg = dwg or com.active()
    if int(com.call(dwg, "GetType")) != com.DOC_DRAWING:
        raise RuntimeError("The active document is not a drawing.")
    ctx = DrawingContext(dwg, style, Report())
    if problems:
        ctx.report.extra["spec_warnings"] = problems
    values = title_values(spec, title_overrides, style)
    table = _steps_table(spec, ctx, title_profile, values)
    wanted = list(steps) if steps else STEPS
    unknown = [s for s in wanted if s not in table]
    if unknown:
        raise SpecError(f"unknown steps: {unknown} (valid: {STEPS})")
    for name in STEPS:
        if name not in wanted:
            continue
        log(f"step {name}")
        try:
            out = table[name]()
            ctx.report.steps[name] = out if out is not None else "ok"
        except Exception as exc:
            ctx.report.steps[name] = f"ERROR: {exc}"
            ctx.report.errors.append(f"{name}: {exc}")
            log(traceback.format_exc())
        log(f"step {name}: {ctx.report.steps[name]}")
    ctx.clear()
    ctx.rebuild()       # regenerate section/detail geometry before anyone exports or saves
    com.call(dwg, "GraphicsRedraw2")
    rep = ctx.report.as_dict()
    rep["views"] = [com.view_name(v) for v in com.views(dwg)]
    rep["check"] = summarise(rep)
    return rep


def summarise(rep: Dict[str, Any]) -> Dict[str, Any]:
    """What a reviewer (human or Claude) should look at before trusting the sheet."""
    failed_dims = [d["id"] for d in rep.get("dims", []) if "error" in d]
    wrong_dims = [d["id"] for d in rep.get("dims", []) if d.get("mismatch")]
    failed_ann = [a["id"] for a in rep.get("annotations", []) if "error" in a]
    no_leader = [a["id"] for a in rep.get("annotations", []) if a.get("leader") is False]
    failed_steps = [k for k, v in rep.get("steps", {}).items() if str(v).startswith("ERROR")]
    exp_ = rep.get("export") or {}
    return {
        "ok": not (failed_dims or wrong_dims or failed_ann or failed_steps),
        "failed_steps": failed_steps,
        "failed_dimensions": failed_dims,
        "wrong_value_dimensions": wrong_dims,
        "failed_annotations": failed_ann,
        "annotations_without_leader": no_leader,
        "pdf": exp_.get("path"),
        "png": exp_.get("png"),
        "next": "Open the PNG/PDF and check every view: geometry present, no dimension overlapping a "
                "view or another dimension, notes block clear of the title block.",
    }


def load_spec(path: str) -> Dict[str, Any]:
    return load_file(path)
