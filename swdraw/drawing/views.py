"""Sheet scale, clearing old annotations, view layout, section and detail views."""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .. import com
from ..geometry import up_is_positive
from ..runner import log
from .context import DrawingContext, as_list, resolve_view

ANN_CENTERMARK = 13   # swAnnotationType_e: swCenterMarkSym
ANN_NOTE = 6


def set_sheet_scale(ctx: DrawingContext, num: float, den: float) -> str:
    sh = com.call(ctx.dwg, "GetCurrentSheet")
    pr = list(com.call(sh, "GetProperties2"))
    ok = sh.SetProperties2(int(pr[0]), int(pr[1]), float(num), float(den), bool(pr[4]),
                           float(pr[5]), float(pr[6]), bool(pr[7]))
    return f"sheet {num:g}:{den:g} -> {ok}"


def clear_annotations(ctx: DrawingContext, note_patterns: Sequence[str] = ("NOTES:",),
                      keep_prefixes: Sequence[str] = None, dangling_marks: bool = True) -> str:
    """Delete dimensions, GTols and datum tags in every view, plus notes matching ``note_patterns``.

    View labels (``keep_prefixes``) and the title block are kept. Notes that cannot be deleted
    (they live in the sheet format) are blanked instead. Dangling centre marks are attempted, but
    some cannot be selected through the API at all and need a manual delete (see GOTCHAS.md).
    """
    keep = tuple(p.upper() for p in (keep_prefixes or ctx.style.view_label_prefixes))
    patterns = [p.upper() for p in note_patterns]
    found: List[str] = []
    selected = 0
    to_blank = []
    ctx.clear()
    for v in com.views(ctx.dwg):
        vn = com.view_name(v)
        for first, nxt, kind in (("GetFirstDisplayDimension5", "GetNext5", "dim"),
                                 ("GetFirstGTOL", "GetNext", "gtol"),
                                 ("GetFirstNote", "GetNext", "note")):
            try:
                items = list(com.iter_chain(com.call(v, first), nxt, limit=500))
            except Exception as exc:
                found.append(f"{vn}:{first} error {exc}")
                continue
            for o in items:
                txt = ""
                if kind == "note":
                    txt = str(com.call(o, "GetText")).upper().strip()
                    if txt.startswith(keep) or not any(p in txt for p in patterns):
                        continue
                ok = False
                try:
                    if kind == "dim":
                        ok = ctx.select_by_name(str(com.call(o, "GetNameForSelection")), "DIMENSION", append=True)
                    if not ok:
                        ok = bool(com.call(o, "GetAnnotation").Select3(True, com.nothing()))
                except Exception:
                    ok = False
                selected += int(ok)
                if kind == "note":
                    to_blank.append(o)
                found.append(f"{vn}:{kind}:{txt[:25]}:{'sel' if ok else 'nosel'}")
    marks = _select_dangling_marks(ctx) if dangling_marks else 0
    selected += marks
    if selected:
        com.call(ctx.dwg, "EditDelete")
    if dangling_marks:
        _delete_dangling_command(ctx)      # after EditDelete so it can't clear the selection first
    blanked = 0
    for o in to_blank:
        try:
            if str(com.call(o, "GetText")).strip():
                o.SetText(" ")
                blanked += 1
        except Exception:
            pass
    ctx.report.extra["cleared"] = found
    return f"selected {selected} (centre marks {marks}), blanked {blanked}"


def _delete_dangling_command(ctx: DrawingContext) -> None:
    """Use SolidWorks' own 'delete dangling annotations' if this version exposes it."""
    for owner in (ctx.dwg, ctx.dwg.Extension):
        for name in ("DeleteDanglingAnnotations", "DeleteAllDanglingAnnotations"):
            if not com.has_member(owner, name):
                continue
            try:
                com.invoke(owner, name)
                ctx.report.extra["dangling_command"] = name
            except Exception as exc:
                ctx.report.extra["dangling_command"] = f"{name} failed: {exc}"
            return


def _select_dangling_marks(ctx: DrawingContext) -> int:
    n = 0
    for v in com.views(ctx.dwg)[1:]:
        vn = com.view_name(v)
        for a in (com.call(v, "GetAnnotations") or []):
            try:
                if int(com.call(a, "GetType")) != ANN_CENTERMARK or not bool(com.call(a, "IsDangling")):
                    continue
                name = f"{com.call(a, 'GetName')}@{vn}"
                ok = any(ctx.select_by_name(name, k, append=True) for k in ("CENTERMARKSYMS", "CENTERMARKS", ""))
                if not ok:
                    ok = bool(a.Select3(True, com.nothing()))
                n += int(ok)
            except Exception:
                continue
    return n


def layout(ctx: DrawingContext, entries: Sequence[Dict[str, Any]]) -> str:
    """``[{view: "Drawing View1", at: [x_mm, y_mm], scale: [1, 1] | sheet}]``.

    Scale changes are applied and rebuilt first, then positions, because a rescale moves the view.
    """
    done, failed, hidden = [], [], []
    for e in entries:
        v = resolve_view(ctx, e["view"])
        if e.get("suppress"):
            # e.g. a plain exterior view that adds nothing once a section exists
            ctx.clear()
            if ctx.select_by_name(com.view_name(v), "DRAWINGVIEW"):
                try:
                    com.call(ctx.dwg, "SuppressView")
                    hidden.append(e["view"])
                except Exception as exc:
                    log(f"  SuppressView {e['view']}: {exc}")
            ctx.clear()
            continue
        sc = e.get("scale", "sheet")
        if sc == "sheet":
            com.set_prop(v, "UseSheetScale", 1)
        elif sc is not None:
            com.set_prop(v, "UseSheetScale", 0)
            com.set_prop(v, "ScaleRatio", com.arr8(sc))
    com.call(ctx.dwg, "EditRebuild3")
    for e in entries:
        if e.get("at") is not None and not e.get("suppress"):
            v = resolve_view(ctx, e["view"])
            if com.set_prop(v, "Position", com.arr8([e["at"][0] / 1000.0, e["at"][1] / 1000.0])):
                done.append(e["view"])
            else:
                failed.append(e["view"])
                ctx.report.errors.append(f"layout: could not position {e['view']}")
    com.call(ctx.dwg, "EditRebuild3")
    out = f"placed {len(done)}"
    if failed:
        out += f", failed {failed}"
    if hidden:
        out += f", suppressed {hidden}"
    return out


def section(ctx: DrawingContext, spec: Dict[str, Any]) -> str:
    """Cut a section from a line between two model points.

    ``{id: A, from_views: ["Drawing View1", ...], line: [[x,y,z],[x,y,z]], at: [x_mm, y_mm],
       alt_at: [[x_mm, y_mm], ...], require_upright: true, remove_alignment: false}``

    For each source view in ``from_views``, the section is created at ``at`` with both
    ``CreateSectionViewAt5`` option values, then at each ``alt_at`` placement. Placing the view on
    the other side of the cutting line is what reverses the viewing direction. With
    ``require_upright`` a result whose model +Y points down the sheet is deleted and the next
    attempt made. Rotating a section view breaks its transform, so cut from the opposite view
    instead (GOTCHAS.md); ``remove_alignment`` then lets it move to ``at``. The section line is
    drawn in the source view's sketch space.
    """
    label = spec["id"]
    tried = []
    sv = None
    at = spec["at"]
    attempts = [(0, at), (1, at)] + [(0, alt) for alt in spec.get("alt_at") or []]
    for vname in as_list(spec.get("from_views") or spec.get("from_view")):
        src = resolve_view(ctx, vname)
        for opt, place in attempts:
            a_s = ctx.to_sheet(src, spec["line"][0])
            b_s = ctx.to_sheet(src, spec["line"][1])
            ax, ay, _ = ctx.to_sketch(src, *a_s)
            bx, by, _ = ctx.to_sketch(src, *b_s)
            ctx.clear()
            ctx.dwg.ActivateView(com.view_name(src))
            seg = com.call(ctx.dwg, "SketchManager").CreateLine(ax, ay, 0, bx, by, 0)
            ctx.clear()
            seg.Select4(False, com.nothing())
            sv = ctx.dwg.CreateSectionViewAt5(place[0] / 1000.0, place[1] / 1000.0, 0, label, opt, com.nothing(), 0.0)
            tag = f"{vname}/opt{opt}@{place[0]:g},{place[1]:g}"
            if sv is None:
                tried.append(f"{tag}: none")
                continue
            arr = list(com.call(com.call(sv, "ModelToViewTransform"), "ArrayData"))
            upright = up_is_positive(arr)
            tried.append(f"{tag}: upright={upright}")
            if upright or not spec.get("require_upright", False):
                break
            ctx.clear()
            ctx.select_by_name(com.view_name(sv), "DRAWINGVIEW")
            com.call(ctx.dwg, "EditDelete")
            ctx.clear()
            sv = None
        if sv is not None:
            break
    if sv is None:
        raise RuntimeError(f"section {label} failed: " + "; ".join(tried))
    if spec.get("remove_alignment", False):
        try:
            com.call(sv, "RemoveAlignment")
        except Exception as exc:
            log(f"  RemoveAlignment: {exc}")
    com.set_prop(sv, "Position", com.arr8([at[0] / 1000.0, at[1] / 1000.0]))
    com.call(ctx.dwg, "EditRebuild3")
    ctx.alias(label, com.view_name(sv))
    ctx.clear()
    return f"{com.view_name(sv)} ({'; '.join(tried)})"


def detail(ctx: DrawingContext, spec: Dict[str, Any]) -> str:
    """``{id: B, parent: A, centre: [x,y,z], radius_mm: 3, scale: 5, at: [x_mm, y_mm]}``.

    The circle radius is in sheet mm on the parent view; it is converted to the view's sketch space.
    """
    label = spec["id"]
    parent = resolve_view(ctx, spec["parent"])
    ctx.clear()
    ctx.dwg.ActivateView(com.view_name(parent))
    cx, cy = ctx.to_sheet(parent, spec["centre"])
    cx, cy, vsc = ctx.to_sketch(parent, cx, cy)
    r = (spec["radius_mm"] / 1000.0) / vsc
    circ = com.call(ctx.dwg, "SketchManager").CreateCircleByRadius(cx, cy, 0, r)
    if circ is None:
        # seen on the second detail from the same view: re-enter the view's sketch and retry
        com.call(ctx.dwg, "EditRebuild3")
        ctx.clear()
        ctx.dwg.ActivateView(com.view_name(parent))
        circ = com.call(ctx.dwg, "SketchManager").CreateCircle(cx, cy, 0, cx + r, cy, 0)
    if circ is None:
        raise RuntimeError(f"detail {label}: could not sketch the detail circle")
    ctx.clear()
    circ.Select4(False, com.nothing())
    x, y, scale = spec["at"][0] / 1000.0, spec["at"][1] / 1000.0, float(spec["scale"])
    dv = None
    try:
        dv = ctx.dwg.CreateDetailViewAt3(x, y, 0, 0, scale, 1.0, label, 1, False)
    except Exception as exc:
        log(f"  CreateDetailViewAt3: {exc}; trying At4")
    if dv is None:
        try:
            dv = ctx.dwg.CreateDetailViewAt4(x, y, 0, 0, scale, 1.0, label, 1, False, False, False, 5)
        except Exception as exc:
            log(f"  CreateDetailViewAt4: {exc}")
    ctx.clear()
    if dv is None:
        raise RuntimeError(f"detail {label} failed")
    ctx.alias(label, com.view_name(dv))
    return com.view_name(dv)
