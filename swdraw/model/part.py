"""Read and write a part through the SolidWorks API.

Dimensions, global variables and equations, configurations, the design table, rebuild errors and
mass properties. Everything this module returns is in mm, mm², mm³, g and degrees; the API works
in metres, kilograms and radians.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Optional

from .. import com
from ..runner import log
from .spec import ANGULAR, INTEGER, LINEAR, from_system, unit_of

# swDimensionParamType_e
_DIM_KIND = {1: LINEAR, 2: ANGULAR, 3: INTEGER}
# swSetValueInConfiguration_e
SET_THIS_CONFIG, SET_ALL_CONFIGS = 1, 2
# swInConfigurationOpts_e
EQ_THIS_CONFIG, EQ_ALL_CONFIGS = 1, 2
# swDesignTableUpdateOptions_e
DT_UPDATE_ALL = 2
SAVE_SILENT = 1           # swSaveAsOptions_e
SOLID_BODY = 0            # swBodyType_e

_EQUATION = re.compile(r'^\s*"([^"]+)"\s*=\s*(.*?)\s*$', re.S)


def open_part(path: Optional[str] = None):
    """Open a part by path (or return it if it is already open), or use the active document."""
    doc = com.open_doc(path) if path else com.active()
    if int(com.call(doc, "GetType")) != com.DOC_PART:
        raise RuntimeError("The document is not a part." if path else "The active document is not a part.")
    return doc


def path_of(doc) -> str:
    return str(com.call(doc, "GetPathName") or "")


# --------------------------------------------------------------------------- features and errors
def features(doc) -> Iterator[Any]:
    """Every feature, with sub-features (absorbed sketches) straight after their parent."""
    for f in com.iter_chain(com.call(doc, "FirstFeature"), "GetNextFeature"):
        yield f
        yield from com.iter_chain(com.call(f, "GetFirstSubFeature"), "GetNextSubFeature")


def _error_code(feat):
    warn = com.byref_bool()
    try:
        res = feat.GetErrorCode2(warn)
    except Exception:
        return int(com.call(feat, "GetErrorCode") or 0), False
    if isinstance(res, tuple):           # some pywin32 builds return (code, is_warning)
        return int(res[0] or 0), bool(res[1])
    return int(res or 0), bool(getattr(warn, "value", False))


def feature_errors(doc) -> List[Dict[str, Any]]:
    """Features whose last rebuild left an error or a warning (``swFeatureError_e`` code)."""
    out, seen = [], set()
    for f in features(doc):
        name = str(com.call(f, "Name"))
        if name in seen:
            continue
        seen.add(name)
        code, warning = _error_code(f)
        if code:
            out.append({"feature": name, "type": str(com.call(f, "GetTypeName2")), "code": code,
                        "warning": warning})
    return out


def rebuild(doc) -> bool:
    try:
        return bool(doc.ForceRebuild3(False))
    except Exception as exc:
        log(f"  rebuild: {exc}")
        return False


# --------------------------------------------------------------------------- dimensions
def dim_kind(dim) -> str:
    try:
        return _DIM_KIND.get(int(com.call(dim, "GetType")), LINEAR)
    except Exception:
        return LINEAR


def dim_value(dim) -> float:
    """Current value in mm, degrees or a count."""
    return from_system(float(com.call(dim, "SystemValue")), dim_kind(dim))


def dim_read_only(dim) -> bool:
    try:
        return bool(com.call(dim, "ReadOnly"))
    except Exception:
        return False


def get_dimension(doc, full_name: str):
    """A dimension by its full name (``D1@Sketch1``), or None."""
    try:
        return doc.Parameter(full_name)
    except Exception:
        return None


def dimensions(doc) -> List[Dict[str, Any]]:
    """Every dimension on every feature: full name, value, unit, kind and whether it is read-only."""
    out, seen = [], set()
    for f in features(doc):
        fname = str(com.call(f, "Name"))
        dd, guard = com.call(f, "GetFirstDisplayDimension"), 0
        while dd is not None and guard < 1000:
            d = dd.GetDimension2(0)
            name = f"{com.call(d, 'Name')}@{fname}"
            if name not in seen:
                seen.add(name)
                kind = dim_kind(d)
                out.append({"name": name, "value": round(dim_value(d), 6), "unit": unit_of(kind),
                            "kind": kind, "read_only": dim_read_only(d)})
            dd = f.GetNextDisplayDimension(dd)
            guard += 1
    return out


def set_dimension(dim, value_si: float, all_configs: bool = False) -> Optional[str]:
    """Write a value in system units. Returns the call that worked, or None.

    The older calls are only tried when a newer one is missing or raises; a refusal status from
    SolidWorks is final, so it is never bypassed by writing ``SystemValue`` directly.
    """
    opt = SET_ALL_CONFIGS if all_configs else SET_THIS_CONFIG
    for how in ("SetSystemValue3", "SetSystemValue2", "SystemValue"):
        try:
            if how == "SetSystemValue3":
                status = dim.SetSystemValue3(value_si, opt, None)
            elif how == "SetSystemValue2":
                status = dim.SetSystemValue2(value_si, opt)
            else:
                setattr(dim, "SystemValue", value_si)
                status = 0
        except Exception as exc:
            log(f"  {how}: {exc}")
            continue
        if int(status or 0) != 0:              # swSetValueReturnStatus_e: 0 = success
            log(f"  {how} refused the value (status {status})")
            return None
        return how
    return None


# --------------------------------------------------------------------------- equations and globals
def equation_mgr(doc):
    return com.call(doc, "GetEquationMgr")


def split_equation(text: str):
    """``'"flange_d" = 40mm'`` -> ("flange_d", "40mm"); (None, None) if it isn't ``"name" = ...``."""
    m = _EQUATION.match(text or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def equations(doc) -> List[Dict[str, Any]]:
    """Every equation and global variable, in order."""
    mgr = equation_mgr(doc)
    if mgr is None:
        return []
    out = []
    for i in range(int(com.call(mgr, "GetCount") or 0)):
        text = str(com.call(mgr, "Equation", i))
        lhs, rhs = split_equation(text)
        try:
            value = float(com.call(mgr, "Value", i))
        except Exception:
            value = None
        out.append({"index": i, "text": text, "lhs": lhs, "rhs": rhs,
                    "global": bool(com.call(mgr, "GlobalVariable", i)), "value": value})
    return out


def find_equation(eqs: List[Dict[str, Any]], name: str, want_global: Optional[bool] = None):
    """The equation whose left-hand side is ``name`` (case-insensitive; ``@Part.SLDPRT`` ignored)."""
    key = _bare(name)
    for e in eqs:
        if e["lhs"] and _bare(e["lhs"]) == key and (want_global is None or e["global"] == want_global):
            return e
    return None


def _bare(name: str) -> str:
    parts = str(name).strip().lower().split("@")
    if len(parts) > 2 and parts[-1].endswith((".sldprt", ".part")):
        parts = parts[:-1]
    return "@".join(parts)


def set_equation(doc, index: int, text: str, all_configs: bool = True) -> Optional[str]:
    """Replace equation ``index``. Returns the call that worked, or None if the text didn't stick."""
    mgr = equation_mgr(doc)
    opt = EQ_ALL_CONFIGS if all_configs else EQ_THIS_CONFIG
    for how in ("SetEquationAndConfigurationOption", "Equation"):
        try:
            if how == "Equation":
                com.put(mgr, "Equation", index, text)
            else:
                status = mgr.SetEquationAndConfigurationOption(index, text, opt, None)
                if int(status or 0) != 0:
                    log(f"  {how} returned status {status}")
                    continue
        except Exception as exc:
            log(f"  {how}: {exc}")
            continue
        if _same_text(str(com.call(mgr, "Equation", index)), text):
            return how
        log(f"  {how}: equation {index} reads back as {com.call(mgr, 'Equation', index)!r}")
    return None


def _same_text(a: str, b: str) -> bool:
    return re.sub(r"\s+", "", a).lower() == re.sub(r"\s+", "", b).lower()


def evaluate_equations(doc) -> None:
    mgr = equation_mgr(doc)
    if mgr is not None:
        try:
            com.call(mgr, "EvaluateAll")
        except Exception as exc:
            log(f"  EvaluateAll: {exc}")


# --------------------------------------------------------------------------- configurations, design table
def configurations(doc) -> Dict[str, Any]:
    names = [str(n) for n in (com.call(doc, "GetConfigurationNames") or [])]
    try:
        active = str(com.call(com.call(com.call(doc, "ConfigurationManager"), "ActiveConfiguration"), "Name"))
    except Exception:
        active = None
    return {"active": active, "names": names}


def activate_configuration(doc, name: str) -> bool:
    try:
        return bool(doc.ShowConfiguration2(name))
    except Exception as exc:
        log(f"  ShowConfiguration2({name}): {exc}")
        return False


def _design_table(doc):
    try:
        return com.call(doc, "GetDesignTable")
    except Exception:
        return None


def design_table(doc) -> Optional[Dict[str, Any]]:
    """Header row and every row by configuration name, as text. None if the part has no table."""
    dt = _design_table(doc)
    if dt is None:
        return None
    rows, cols = _dt_size(dt)
    headers = {c: str(dt.GetHeaderText(c)) for c in range(1, cols + 1)}
    table = {}
    for r in range(1, rows + 1):
        cfg = str(dt.GetEntryText(r, 0))
        if cfg:
            table[cfg] = {headers[c]: str(dt.GetEntryText(r, c)) for c in headers}
    return {"columns": list(headers.values()), "rows": table}


def _dt_size(dt):
    return int(com.call(dt, "GetTotalRowCount") or 0), int(com.call(dt, "GetTotalColumnCount") or 0)


def set_design_table(doc, row_name: str, values: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Write cells in one design-table row and update the model. One record per cell."""
    dt = _design_table(doc)
    if dt is None:
        return [{"kind": "design_table", "name": row_name, "error": "the part has no design table"}]
    rows, cols = _dt_size(dt)
    row = next((r for r in range(1, rows + 1) if str(dt.GetEntryText(r, 0)) == row_name), None)
    if row is None:
        return [{"kind": "design_table", "name": row_name, "error": "no such row"}]
    col_of = {str(dt.GetHeaderText(c)).lower(): c for c in range(1, cols + 1)}
    out = []
    try:
        com.call(dt, "EditTable2", False)
    except Exception as exc:
        log(f"  EditTable2: {exc}")
    for header, value in values.items():
        rec = {"kind": "design_table", "name": f"{row_name}/{header}", "new": value}
        c = col_of.get(str(header).lower())
        if c is None:
            rec["error"] = "no such column"
        else:
            rec["old"] = str(dt.GetEntryText(row, c))
            try:
                if not dt.SetEntryValue(row, c, False, str(value)):
                    rec["error"] = "SetEntryValue returned False"
            except Exception as exc:
                rec["error"] = f"SetEntryValue: {exc}"
        out.append(rec)
    try:
        dt.UpdateTable(DT_UPDATE_ALL, True)
    except Exception as exc:
        out.append({"kind": "design_table", "name": row_name, "error": f"UpdateTable: {exc}"})
    return out


# --------------------------------------------------------------------------- mass properties
def material(doc) -> Optional[str]:
    """Material name, or None if none is assigned (mass then uses SolidWorks' default density)."""
    try:
        ident = str(com.call(doc, "MaterialIdName") or "")
    except Exception:
        return None
    parts = ident.split("|")
    return (parts[1] if len(parts) > 1 else ident) or None


def mass_properties(doc) -> Dict[str, Any]:
    ext = com.call(doc, "Extension")
    mp = None
    for how in ("CreateMassProperty2", "CreateMassProperty"):
        try:
            mp = com.call(ext, how)
        except Exception:
            mp = None
        if mp is not None:
            break
    if mp is None:
        return {"error": "could not create mass properties (is there a solid body?)"}
    com.set_prop(mp, "UseSystemUnits", True)
    vol = float(com.call(mp, "Volume"))
    mass = float(com.call(mp, "Mass"))
    return {"volume_mm3": round(vol * 1e9, 4), "mass_g": round(mass * 1e3, 4),
            "surface_area_mm2": round(float(com.call(mp, "SurfaceArea")) * 1e6, 4),
            "density_kg_m3": round(mass / vol, 3) if vol else None, "material": material(doc)}


def bounding_box(doc) -> Optional[Dict[str, Any]]:
    """Exact box of the solid bodies in mm: min and max corners and the sizes along X, Y, Z."""
    box = None
    try:
        box = list(doc.GetPartBox(True))
    except Exception as exc:
        log(f"  GetPartBox: {exc}")
    if not box or len(box) < 6 or not any(box):
        box = None
        for b in com.call(doc, "GetBodies2", SOLID_BODY, True) or []:
            bb = list(com.call(b, "GetBodyBox"))
            box = bb if box is None else [min(box[i], bb[i]) for i in range(3)] + [max(box[i], bb[i]) for i in range(3, 6)]
    if not box:
        return None
    lo, hi = [v * 1000.0 for v in box[:3]], [v * 1000.0 for v in box[3:6]]
    return {"min": [round(v, 4) for v in lo], "max": [round(v, 4) for v in hi],
            "size": [round(h - l, 4) for l, h in zip(lo, hi)]}


def measure(doc) -> Dict[str, Any]:
    out = mass_properties(doc)
    out["bbox_mm"] = bounding_box(doc)
    return out


# --------------------------------------------------------------------------- inspect
def inspect(doc) -> Dict[str, Any]:
    """Everything an edit spec can change, plus what the part measures now.

    ``spec`` is a ready-to-edit stub: every editable value at its current setting and an
    ``expect`` block from the current mass properties.
    """
    eqs = equations(doc)
    driven = {_bare(e["lhs"]) for e in eqs if e["lhs"] and not e["global"]}
    dims = dimensions(doc)
    for d in dims:
        d["driven_by_equation"] = _bare(d["name"]) in driven
    meas = measure(doc)
    cfg = configurations(doc)
    rep = {"part": path_of(doc), "configurations": cfg, "dimensions": dims,
           "globals": [{"name": e["lhs"], "value": e["value"], "text": e["text"]} for e in eqs if e["global"]],
           "equations": [e for e in eqs if not e["global"]],
           "design_table": design_table(doc), "feature_errors": feature_errors(doc), "measured": meas}
    rep["spec"] = spec_stub(rep)
    return rep


def spec_stub(rep: Dict[str, Any]) -> Dict[str, Any]:
    stub: Dict[str, Any] = {}
    if rep.get("part"):
        stub["part"] = rep["part"]
    if rep["configurations"].get("active") and len(rep["configurations"]["names"]) > 1:
        stub["configuration"] = rep["configurations"]["active"]
    g = {x["name"]: _rhs(x["text"]) for x in rep["globals"]}
    if g:
        stub["globals"] = g
    d = {x["name"]: x["value"] for x in rep["dimensions"] if not x["read_only"] and not x["driven_by_equation"]}
    if d:
        stub["dimensions"] = d
    m = rep["measured"]
    exp: Dict[str, Any] = {}
    if m.get("volume_mm3"):
        exp["volume_mm3"] = {"value": m["volume_mm3"], "tol": round(max(0.01, m["volume_mm3"] * 1e-4), 3)}
    if m.get("surface_area_mm2"):
        exp["surface_area_mm2"] = {"value": m["surface_area_mm2"], "tol": round(max(0.01, m["surface_area_mm2"] * 1e-4), 3)}
    if m.get("mass_g") and m.get("material"):
        exp["mass_g"] = {"value": m["mass_g"], "tol_pct": 0.1}
    if m.get("bbox_mm"):
        exp["bbox_mm"] = {"value": m["bbox_mm"]["size"], "tol": 0.01}
    if exp:
        stub["expect"] = exp
    stub["save"] = False
    return stub


def _rhs(text: str):
    return split_equation(text)[1]


# --------------------------------------------------------------------------- state and saving
def is_dirty(doc) -> bool:
    try:
        return bool(com.call(doc, "GetSaveFlag"))
    except Exception:
        return False


def is_read_only(doc) -> bool:
    try:
        return bool(com.call(doc, "IsOpenedReadOnly"))
    except Exception:
        return False


def save(doc) -> Dict[str, Any]:
    errors, warnings = com.byref_int(), com.byref_int()
    try:
        ok = bool(doc.Save3(SAVE_SILENT, errors, warnings))
    except Exception as exc:
        return {"saved": False, "error": f"Save3: {exc}"}
    out = {"saved": ok and not errors.value, "errors": int(errors.value or 0), "warnings": int(warnings.value or 0)}
    if not out["saved"]:
        out["error"] = f"Save3 failed (errors={out['errors']})"
    return out
