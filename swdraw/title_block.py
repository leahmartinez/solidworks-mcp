"""Fill a title block from values, using a title-block profile (see profiles/title_block.yaml).

The matching logic works on plain ``SheetNote`` records so it can be tested without SolidWorks;
``read_sheet_notes`` / ``apply_updates`` do the COM part.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from . import com


@dataclass
class SheetNote:
    text: str
    x: float          # sheet mm from bottom-left
    y: float
    handle: Any = None


@dataclass
class Update:
    note: SheetNote
    new_text: str
    height_mm: Optional[float] = None
    field: str = ""


def _near(n: SheetNote, at: Sequence[float], tol: float) -> bool:
    return abs(n.x - at[0]) <= tol and abs(n.y - at[1]) <= tol


def _placeholder_ok(text: str, placeholders) -> bool:
    t = text.strip()
    if not t:
        return True
    if placeholders is None:
        return True
    if isinstance(placeholders, str):
        placeholders = [placeholders]
    return t in placeholders


def plan_fields(notes: Sequence[SheetNote], values: Dict[str, Any], profile: Dict[str, Any],
                overwrite: bool = False) -> List[Update]:
    """Match each value in ``values`` to the sheet note at its profile position.

    A note is only replaced if it still shows its placeholder (or is blank), unless ``overwrite``.
    Values that are ``None`` are skipped; ``""`` blanks the field (written as a single space,
    because SolidWorks deletes empty notes).
    """
    pn = profile.get("placeholder_notes", profile)
    tol_default = float(pn.get("tolerance_mm", 2.5))
    out: List[Update] = []
    for key, fspec in (pn.get("fields") or {}).items():
        if key not in values or values[key] is None:
            continue
        tol = float(fspec.get("tolerance_mm", tol_default))
        cands = [n for n in notes if _near(n, fspec["at"], tol)
                 and (overwrite or _placeholder_ok(n.text, fspec.get("placeholder")))]
        if not cands:
            continue
        best = min(cands, key=lambda n: (n.x - fspec["at"][0]) ** 2 + (n.y - fspec["at"][1]) ** 2)
        out.append(Update(best, str(values[key]) or " ", fspec.get("height_mm"), key))
    return out


def plan_rev_box(notes: Sequence[SheetNote], rev: str, profile: Dict[str, Any]) -> List[Update]:
    pn = profile.get("placeholder_notes", profile)
    box = pn.get("rev_box")
    if not box:
        return []
    hits = [n for n in notes if n.x > box["min_x"] and n.y < box["max_y"]
            and len(n.text.strip()) <= 2 and n.text.strip().isalpha()]
    return [Update(n, rev, box.get("height_mm"), "rev_box") for n in hits]


def plan_rev_row(notes: Sequence[SheetNote], row_index: int, row: Dict[str, Any], profile: Dict[str, Any],
                 overwrite: bool = False) -> List[Update]:
    """Fill revision-table row ``row_index`` (0 = first issue) with ``row`` = {rev, desc, date, drawn, approved}."""
    pn = profile.get("placeholder_notes", profile)
    tbl = pn.get("rev_table")
    if not tbl:
        return []
    ys = tbl["rows_y"]
    if row_index >= len(ys):
        raise IndexError(f"revision table has {len(ys)} rows; row {row_index + 1} requested")
    y = ys[row_index]
    out: List[Update] = []
    phs = tbl.get("placeholders", {})
    for col, x in tbl["columns"].items():
        if row.get(col) is None:
            continue
        tol = float(tbl.get("desc_tolerance_mm" if col == "desc" else "tolerance_mm", 2.5))
        cands = [n for n in notes if _near(n, (x, y), tol) and (overwrite or _placeholder_ok(n.text, phs.get(col)))]
        if cands:
            best = min(cands, key=lambda n: (n.x - x) ** 2 + (n.y - y) ** 2)
            out.append(Update(best, str(row[col]) or " ", tbl.get("text_height_mm"), f"rev{row_index + 1}.{col}"))
    return out


def plan_see_note(notes: Sequence[SheetNote], note_number: int, profile: Dict[str, Any]) -> List[Update]:
    marker = (profile.get("placeholder_notes", profile).get("see_note_marker") or "SEE NOTE").upper()
    out = []
    for n in notes:
        up = n.text.upper()
        if marker in up:
            new = n.text[:up.index(marker)] + f"{marker} {note_number}"
            if new != n.text:
                out.append(Update(n, new, None, "see_note"))
    return out


# --------------------------------------------------------------------------- COM side
def read_sheet_notes(dwg) -> List[SheetNote]:
    sheet = com.views(dwg)[0]
    out = []
    for n in com.notes(sheet):
        pos = list(com.call(com.call(n, "GetAnnotation"), "GetPosition"))
        out.append(SheetNote(str(com.call(n, "GetText")), pos[0] * 1000.0, pos[1] * 1000.0, n))
    return out


def apply_updates(updates: Sequence[Update], font: Optional[str] = None) -> List[str]:
    """Write the planned text; only re-applies the font/height where the profile asks for one."""
    done = []
    for u in updates:
        n = u.note.handle
        if u.new_text != u.note.text:
            n.SetText(u.new_text)
        if u.height_mm or font:
            try:
                ann = com.call(n, "GetAnnotation")
                tf = ann.GetTextFormat(0)
                if font:
                    tf.TypeFaceName = font
                if u.height_mm:
                    tf.CharHeight = u.height_mm / 1000.0
                ann.SetTextFormat(0, False, tf)
            except Exception:
                pass
        done.append(f"{u.field}: {u.note.text.strip() or '(blank)'} -> {u.new_text.strip() or '(blank)'} "
                    f"@({u.note.x:.0f},{u.note.y:.0f})")
    return done


def set_custom_properties(doc, props: Dict[str, Any], config: str = "") -> List[str]:
    """Add-or-replace text custom properties (swCustomInfoText=30, swCustomPropertyReplaceValue=2)."""
    cpm = doc.Extension.CustomPropertyManager(config)
    done = []
    for k, v in props.items():
        if v is None:
            continue
        cpm.Add3(str(k), 30, str(v) if str(v) != "" else " ", 2)
        done.append(f"{k}={v}")
    return done


def property_values(values: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Map field keys (part_no, drawn_by ...) to the template's custom property names."""
    names = (profile.get("custom_properties") or {}).get("fields") or {}
    return {names[k]: v for k, v in values.items() if k in names and v is not None}


def rev_row_properties(row_index: int, row: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    rows = (profile.get("custom_properties") or {}).get("rev_rows") or []
    if row_index >= len(rows):
        raise IndexError(f"profile defines {len(rows)} revision rows; row {row_index + 1} requested")
    names = rows[row_index]
    return {names[c]: v for c, v in row.items() if c in names and v is not None}


def referenced_model(dwg):
    """The part/assembly shown in the first model view (what ``$PRPSHEET:`` links read from)."""
    for v in com.views(dwg)[1:]:
        try:
            doc = com.call(v, "ReferencedDocument")
        except Exception:
            doc = None
        if doc is not None:
            return doc
    return None


def fill(dwg, values: Dict[str, Any], profile: Dict[str, Any], font: Optional[str] = None,
         overwrite: bool = False) -> List[str]:
    """Fill the title block in whichever mode the profile selects.

    In ``custom_properties`` mode, fields listed under ``model_fields`` are written to the
    referenced part (the template links them with ``$PRPSHEET:``); the rest go on the drawing.
    The part is modified but not saved.
    """
    if profile.get("mode", "custom_properties") == "custom_properties":
        model_keys = set((profile.get("custom_properties") or {}).get("model_fields") or [])
        on_dwg = {k: v for k, v in values.items() if k not in model_keys}
        on_model = {k: v for k, v in values.items() if k in model_keys}
        done = set_custom_properties(dwg, property_values(on_dwg, profile))
        if on_model:
            model = referenced_model(dwg)
            if model is None:
                done += set_custom_properties(dwg, property_values(on_model, profile))
                done.append("warning: no referenced model found; model fields written to the drawing")
            else:
                done += [f"model: {d}" for d in set_custom_properties(model, property_values(on_model, profile))]
        return done
    notes = read_sheet_notes(dwg)
    ups = plan_fields(notes, values, profile, overwrite=overwrite)
    if values.get("revision"):
        ups += plan_rev_box(notes, values["revision"], profile)
    return apply_updates(ups, font)
