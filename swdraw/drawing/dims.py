"""Self-checking dimensions.

Each dimension in a spec names the geometry to pick and (ideally) the value it should measure.
After placing it, the measured value is compared with ``expect``; on a mismatch the dimension is
deleted, the drawing regenerated and the next alternative pick pair tried. Tolerances are written
in metres and read back, because a silent failure shows as ``±0.00`` on the sheet.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import com
from ..runner import log
from .context import DrawingContext, Pick, resolve_view

# swTolType_e
TOL = {"none": 0, "basic": 1, "bilateral": 2, "limit": 3, "symmetric": 4, "min": 5, "max": 6,
       "metric": 7, "fit": 8, "fit_with_tolerance": 9, "fit_tolerance_only": 10}
# swArcEndCondition_e, tried in this order when `arc_expect` is given
ARC_CONDITIONS = ((2, 2), (3, 3), (1, 1), (0, 0))
DIAMETER = "<MOD-DIAM>"
MATCH_MM = 0.005


def tol_type(value) -> int:
    if value is None:
        return -1
    if isinstance(value, int):
        return value
    if str(value).isdigit():
        return int(value)
    return TOL[str(value).lower()]


def _set_tolerance(ctx: DrawingContext, d, kind: int, lo_mm: float, hi_mm: float) -> Optional[str]:
    tl = com.call(d, "Tolerance")
    com.set_prop(tl, "Type", kind)
    if kind not in (TOL["bilateral"], TOL["limit"], TOL["symmetric"]):
        return None
    lo, hi = lo_mm / 1000.0, hi_mm / 1000.0
    for how in ("SetValues2", "SetValues", "SetToleranceValues"):
        try:
            if how == "SetValues2":
                tl.SetValues2(lo, hi, 1, "")
            elif how == "SetValues":
                tl.SetValues(lo, hi)
            else:
                d.SetToleranceValues(lo, hi, 1, "")
        except Exception as exc:
            log(f"  tolerance {how}: {exc}")
            continue
        try:
            got_hi = float(com.call(tl, "GetMaxValue"))
            got_lo = float(com.call(tl, "GetMinValue"))
        except Exception:
            got_hi = got_lo = None
        if got_hi is not None and abs(got_hi - hi) < 1e-9 and abs(got_lo - lo) < 1e-9:
            return how
    ctx.report.errors.append(f"tolerance not applied ({lo_mm}/{hi_mm})")
    return None


def _pick_pairs(spec: Dict[str, Any]) -> List[tuple]:
    pairs = [(spec["pick"][0], spec["pick"][1] if len(spec["pick"]) > 1 else None)]
    for alt in spec.get("alternatives", []) or []:
        pairs.append((alt[0], alt[1] if len(alt) > 1 else None))
    return pairs


def add_dimension(ctx: DrawingContext, spec: Dict[str, Any]):
    """Place one dimension from a spec entry. Returns the DisplayDimension or None.

    Spec keys::

        id: D_BORE              # tag used in the report and for datum/move references
        view: A                 # view name or id from the spec
        pick: [[x,y,z], [x,y,z]]   # one entry for radius/diameter of an arc
        alternatives: [[[..],[..]], ...]   # tried in order when picks fail or measure wrong
        text_at: [x, y, z]      # model mm where the dimension text goes
        expect: 16.0            # measured value that proves the right edges were picked
        tolerance: {type: limit, lower: 0, upper: 0.018}
        prefix: "<MOD-DIAM>"   suffix: " THRU"   diametric: true   precision: 3
        arc_expect: 46.494      # choose the arc end condition that gives this value
    """
    tag = spec.get("id", "?")
    view = resolve_view(ctx, spec["view"])
    expect = spec.get("expect")
    pairs = _pick_pairs(spec)
    regen_retry_left = 1

    i = 0
    while i < len(pairs):
        p1, p2 = Pick.parse(pairs[i][0]), (Pick.parse(pairs[i][1]) if pairs[i][1] is not None else None)
        ctx.clear()
        ok1 = ctx.select(view, p1, False)
        ok2 = True if p2 is None else ctx.select(view, p2, True)
        if not (ok1 and ok2):
            log(f"  {tag}: selection failed on pair {i} ({ok1},{ok2})")
            i += 1
            continue
        tx, ty = ctx.to_sheet(view, spec["text_at"])
        dd = ctx.dwg.AddDimension2(tx, ty, 0)
        if dd is None:
            ctx.report.dims.append({"id": tag, "error": "AddDimension2 returned None"})
            ctx.clear()
            return None
        _decorate(ctx, dd, spec)
        d = dd.GetDimension2(0)
        if spec.get("arc_expect") is not None:
            _choose_arc_condition(ctx, d, float(spec["arc_expect"]))
        tolset = None
        tol = spec.get("tolerance")
        if tol:
            tolset = _set_tolerance(ctx, d, tol_type(tol.get("type")), float(tol.get("lower", 0)), float(tol.get("upper", 0)))
        value = float(com.call(d, "SystemValue")) * 1000.0
        mismatch = expect is not None and abs(value - float(expect)) > MATCH_MM
        more = i + 1 < len(pairs) or regen_retry_left
        if mismatch and more:
            log(f"  {tag}: measured {value:.3f}, expected {expect}; retrying")
            ctx.delete_display_dim(dd)
            ctx.regen()
            if i + 1 >= len(pairs):
                regen_retry_left -= 1        # same picks once more after a regen
                continue
            i += 1
            continue
        rec = {"id": tag, "view": spec["view"], "value_mm": round(value, 4),
               "expect": expect, "pair": i, "tolerance": tolset}
        if mismatch:
            # out of options: keep the last attempt on the sheet so it can be fixed by hand
            rec["mismatch"] = True
            ctx.report.errors.append(f"{tag}: measured {value:.3f}, expected {expect} (kept, check it)")
        ctx.report.dims.append(rec)
        ctx.state["dim:" + tag] = dd
        ctx.clear()
        return dd

    msg = f"{tag}: selection failed on every pick pair"
    ctx.report.dims.append({"id": tag, "error": msg})
    ctx.report.errors.append(msg)
    ctx.clear()
    return None


def _decorate(ctx: DrawingContext, dd, spec: Dict[str, Any]) -> None:
    if spec.get("prefix"):
        dd.SetText(1, spec["prefix"])
    if spec.get("suffix"):
        dd.SetText(2, spec["suffix"])
    if spec.get("diametric"):
        com.set_prop(dd, "Diametric", True)
    if spec.get("precision") is not None:
        try:
            dd.SetPrecision3(int(spec["precision"]), -1, -1, -1)
        except Exception as exc:
            log(f"  precision: {exc}")


def _choose_arc_condition(ctx: DrawingContext, d, target_mm: float) -> None:
    """Arc end conditions (min/centre/max) live on IDimension, not on the display dimension."""
    for c1, c2 in ARC_CONDITIONS:
        try:
            d.SetArcEndCondition(1, c1)
            d.SetArcEndCondition(2, c2)
            com.call(ctx.dwg, "EditRebuild3")
        except Exception as exc:
            log(f"  arc condition {c1},{c2}: {exc}")
            continue
        if abs(float(com.call(d, "SystemValue")) * 1000 - target_mm) < 0.01:
            return
