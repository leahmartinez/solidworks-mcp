"""Read-only probes for when a step misbehaves. None of these change or save anything."""
from __future__ import annotations

import os
from typing import Any, Dict, List

from . import com
from .geometry import model_to_sheet


def views_report(dwg) -> List[Dict[str, Any]]:
    """Name, position, scale, orientation and annotation counts for every view."""
    out = []
    for i, v in enumerate(com.views(dwg)):
        row: Dict[str, Any] = {"name": com.view_name(v), "sheet": i == 0}
        try:
            xf = list(com.call(v, "GetXform"))
            row["origin_mm"] = [round(xf[0] * 1000, 2), round(xf[1] * 1000, 2)]
            row["scale"] = xf[2]
            a = list(com.call(com.call(v, "ModelToViewTransform"), "ArrayData"))
            row["model_y_up"] = a[4] > 0
            row["origin_on_sheet_mm"] = [round(c * 1000, 2) for c in model_to_sheet(a, 0, 0, 0)]
        except Exception as exc:
            row["transform_error"] = str(exc)
        row["dims"] = len(com.display_dims(v))
        row["notes"] = len(com.notes(v))
        row["gtols"] = len(com.gtols(v))
        out.append(row)
    return out


def selection_report(dwg) -> List[Dict[str, Any]]:
    """What is selected right now (type id per item): useful when a pick lands on the view."""
    sm = com.call(dwg, "SelectionManager")
    n = int(sm.GetSelectedObjectCount2(-1))
    return [{"index": i, "type": int(sm.GetSelectedObjectType3(i, -1))} for i in range(1, n + 1)]


def annotations_report(dwg) -> List[Dict[str, Any]]:
    out = []
    for v in com.views(dwg):
        vn = com.view_name(v)
        for a in (com.call(v, "GetAnnotations") or []):
            row = {"view": vn}
            for k in ("GetName", "GetType"):
                try:
                    row[k[3:].lower()] = com.call(a, k)
                except Exception:
                    pass
            try:
                row["dangling"] = bool(com.call(a, "IsDangling"))
            except Exception:
                pass
            try:
                row["pos_mm"] = [round(c * 1000, 2) for c in list(com.call(a, "GetPosition"))[:2]]
            except Exception:
                pass
            out.append(row)
    return out


def refs_report(paths: List[str]) -> Dict[str, Any]:
    """Dependencies of each file (and whether each referenced file exists), plus open/dirty state."""
    sw = com.app()
    out: Dict[str, Any] = {}
    for p in paths:
        r: Dict[str, Any] = {}
        try:
            deps = list(sw.GetDocumentDependencies2(p, False, True, False) or [])[1::2]
            r["deps"] = [{"path": d, "exists": os.path.exists(d)} for d in deps]
        except Exception as exc:
            r["deps_error"] = str(exc)
        doc = sw.GetOpenDocumentByName(p)
        r["open"] = doc is not None
        if doc is not None:
            try:
                r["dirty"] = bool(com.call(doc, "GetSaveFlag"))
            except Exception:
                pass
        out[p] = r
    return out
