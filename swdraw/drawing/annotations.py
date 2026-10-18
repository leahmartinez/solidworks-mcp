"""Datum tags, GD&T frames, leader notes and the numbered notes block."""
from __future__ import annotations

from typing import Any, Dict, Sequence

from .. import com
from ..notes import numbered_text
from ..runner import log
from .context import DrawingContext, resolve_view


def _find_existing_dim(ctx: DrawingContext, dim_id: str):
    """In a partial run the dimension was placed earlier: find it in its view by expected value."""
    dspec = ctx.state.get("dimspec:" + dim_id)
    if not dspec or dspec.get("expect") is None:
        return None
    try:
        view = resolve_view(ctx, dspec["view"])
    except LookupError:
        return None
    for dd in com.display_dims(view):
        try:
            if abs(float(com.call(dd.GetDimension2(0), "SystemValue")) * 1000 - float(dspec["expect"])) < 0.005:
                return dd
        except Exception:
            continue
    return None


def datum_tag(ctx: DrawingContext, spec: Dict[str, Any]) -> bool:
    """``{label: A, view: A, on_dim: D_BORE}`` or ``{label: A, view: A, edge: [x,y,z], text_at: [x,y,z]}``.

    Attached to a dimension, SolidWorks keeps its own placement; on an edge, ``text_at`` positions it.
    ``InsertDatumTag2`` only works through an explicit IDispatch call.
    """
    label = spec["label"]
    view = resolve_view(ctx, spec["view"])
    tries = []
    if spec.get("edge") is not None:
        tries.append("edge")
    if spec.get("on_dim"):
        tries.append("dim")
    for how in tries:
        try:
            ctx.clear()
            if how == "dim":
                dd = ctx.state.get("dim:" + spec["on_dim"]) or _find_existing_dim(ctx, spec["on_dim"])
                if dd is None or not ctx.select_by_name(str(com.call(dd, "GetNameForSelection")), "DIMENSION"):
                    log(f"  datum {label}: dimension {spec['on_dim']} not found")
                    continue
            elif not ctx.select(view, spec["edge"], False):
                continue
            dt = com.invoke(ctx.dwg, "InsertDatumTag2")
            if dt is None:
                continue
            try:
                com.invoke(dt, "SetLabel", label)
            except Exception as exc:
                log(f"  datum SetLabel: {exc}")
            if how == "edge" and spec.get("text_at"):
                ctx.place(dt, view, spec["text_at"])
            ctx.apply_font(dt, ctx.style.gdt_h)
            ctx.report.annotations.append({"id": "datum " + label, "ok": True, "via": how})
            ctx.clear()
            return True
        except Exception as exc:
            log(f"  datum {label} via {how}: {exc}")
    ctx.report.annotations.append({"id": "datum " + label, "error": "InsertDatumTag2 failed"})
    ctx.report.errors.append(f"datum {label} failed")
    ctx.clear()
    return False


def gdt_frame(ctx: DrawingContext, spec: Dict[str, Any]) -> bool:
    """Feature control frame with a leader to the picked edge.

    ``{id, view, edge: [x,y,z], text_at: [x,y,z], frames: [[symbol, tol, d1, d2], ...], above: "ALL AROUND"}``
    ``symbol`` is the SolidWorks GTOL code without brackets (SPROF, SRUN, FLAT, PARA, PERP, POS ...).
    """
    tag = spec.get("id", "gtol")
    view = resolve_view(ctx, spec["view"])
    try:
        ctx.clear()
        leader = ctx.select(view, spec["edge"], False) if spec.get("edge") is not None else False
        g = com.invoke(ctx.dwg, "InsertGtol")
        if g is None:
            raise RuntimeError("InsertGtol returned None")
        for i, frame in enumerate(spec["frames"], 1):
            sym, tol = frame[0], frame[1]
            d1 = frame[2] if len(frame) > 2 else ""
            d2 = frame[3] if len(frame) > 3 else ""
            g.SetFrameSymbols2(i, f"<GTOL-{sym}>", False, "", False, "", "", "", "")
            g.SetFrameValues(i, str(tol), "", d1 or "", d2 or "", "")
        if spec.get("above"):
            try:
                g.SetText(3, spec["above"])
            except Exception as exc:
                log(f"  gtol text {tag}: {exc}")
        ctx.place(g, view, spec["text_at"])
        ctx.apply_font(g, ctx.style.gdt_h)
        ctx.report.annotations.append({"id": tag, "ok": True, "leader": leader})
        ctx.clear()
        return True
    except Exception as exc:
        ctx.report.annotations.append({"id": tag, "error": str(exc)})
        ctx.report.errors.append(f"{tag}: {exc}")
        ctx.clear()
        return False


def leader_note(ctx: DrawingContext, spec: Dict[str, Any]) -> bool:
    """``{id, view, edge: [x,y,z], text_at: [x,y,z], text: "0.5 x 45°"}``. No edge = no leader."""
    tag = spec.get("id", "note")
    view = resolve_view(ctx, spec["view"])
    try:
        ctx.clear()
        leader = ctx.select(view, spec["edge"], False) if spec.get("edge") is not None else False
        n = ctx.dwg.InsertNote(spec["text"])
        if n is None:
            raise RuntimeError("InsertNote returned None")
        ctx.apply_font(n, pts=ctx.style.note_height_pt)
        ctx.place(n, view, spec["text_at"])
        ctx.report.annotations.append({"id": tag, "ok": True, "leader": leader})
        ctx.clear()
        return True
    except Exception as exc:
        ctx.report.annotations.append({"id": tag, "error": str(exc)})
        ctx.report.errors.append(f"{tag}: {exc}")
        ctx.clear()
        return False


def notes_block(ctx: DrawingContext, lines: Sequence[str], at_sheet_mm: Sequence[float],
                heading: str = "NOTES:", values: Dict[str, Any] = None) -> bool:
    """Insert the numbered notes block at a sheet position (mm from bottom-left).

    Numbers are written as text ("1.  ", "2.  " ...) because ``Note.SetText`` drops SolidWorks'
    automatic list numbering; to change the block later, delete and re-insert it (``swdraw.notes``).
    ``{placeholders}`` in the lines are filled from ``values``.
    """
    text = numbered_text(lines, heading=heading, values=values or {})
    ctx.clear()
    n = ctx.dwg.InsertNote(text)
    if n is None:
        raise RuntimeError("InsertNote returned None")
    ctx.apply_font(n, pts=ctx.style.note_height_pt)
    com.call(n, "GetAnnotation").SetPosition2(at_sheet_mm[0] / 1000.0, at_sheet_mm[1] / 1000.0, 0)
    ctx.clear()
    return True
