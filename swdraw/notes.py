"""The numbered notes block: build its text, replace it, remove stale copies.

``Note.SetText`` drops SolidWorks' automatic list numbering, so the block is always deleted and
re-inserted with literal "1.  ", "2.  " prefixes. Continuation lines (starting with whitespace or
listed as nested lists) are indented under their item.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Sequence, Union

from . import com
from .config import HouseStyle

INDENT = "     "
_NUMBERED = re.compile(r"^\s*\d+\.\s")

Line = Union[str, Sequence[str]]


def numbered_text(lines: Sequence[Line], heading: str = "NOTES:", values: Optional[Dict[str, Any]] = None) -> str:
    """``["FIRST", ["SECOND", "continued"], "THIRD"]`` ->

    ``NOTES:\\n1.  FIRST\\n2.  SECOND\\n     continued\\n3.  THIRD``

    Lines already starting with a number are kept as written. ``{key}`` placeholders are filled
    from ``values`` (unknown keys are left untouched).
    """
    values = values or {}
    out = [heading] if heading else []
    n = 0

    def fmt(s: str) -> str:
        return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), s)

    for item in lines:
        parts = [item] if isinstance(item, str) else list(item)
        first, rest = fmt(parts[0]), [fmt(p) for p in parts[1:]]
        if _NUMBERED.match(first):
            out.append(first.strip())
        elif first[:1].isspace():
            out.append(INDENT + first.strip())
            continue
        else:
            n += 1
            out.append(f"{n}.  {first}")
        out.extend(INDENT + r.strip() for r in rest)
    return "\n".join(out)


def is_notes_block(text: str, heading: str = "NOTES:") -> bool:
    return text.strip().upper().startswith(heading.upper())


def has_numbering(text: str) -> bool:
    return bool(re.search(r"(^|\n)\s*1\.\s", text.replace("\r", "")))


def find_blocks(dwg, heading: str = "NOTES:"):
    """[(note, view_name, (x_m, y_m), text)] for every notes block in every view."""
    out = []
    for v in com.views(dwg):
        vn = com.view_name(v)
        for nt in com.notes(v):
            t = str(com.call(nt, "GetText"))
            if is_notes_block(t, heading):
                pos = list(com.call(com.call(nt, "GetAnnotation"), "GetPosition"))[:2]
                out.append((nt, vn, pos, t))
    return out


def delete_note(dwg, note, view_name: str) -> bool:
    """``Annotation.Select2(False, 0)`` then ``EditDelete`` works where ``Select3`` returns False."""
    dwg.ClearSelection2(True)
    ok = False
    try:
        ok = bool(com.call(note, "GetAnnotation").Select2(False, 0))
    except Exception:
        ok = False
    if not ok:
        try:
            name = str(com.call(note, "GetName"))
            ok = bool(dwg.Extension.SelectByID2(f"{name}@{view_name}", "NOTE", 0, 0, 0, False, 0, com.nothing(), 0))
        except Exception:
            ok = False
    if ok:
        dwg.EditDelete()
    dwg.ClearSelection2(True)
    return ok


def insert_block(dwg, text: str, pos_m: Sequence[float], style: Optional[HouseStyle] = None):
    style = style or HouseStyle()
    dwg.ClearSelection2(True)
    n = dwg.InsertNote(text)
    if n is None:
        raise RuntimeError("InsertNote returned None")
    ann = com.call(n, "GetAnnotation")
    tf = ann.GetTextFormat(0)
    tf.TypeFaceName = style.font
    tf.CharHeightInPts = style.note_height_pt
    ann.SetTextFormat(0, False, tf)
    if pos_m:
        ann.SetPosition2(pos_m[0], pos_m[1], 0)
    return n


def replace_block(dwg, lines: Sequence[Line], pos_m: Optional[Sequence[float]] = None,
                  style: Optional[HouseStyle] = None, heading: str = "NOTES:",
                  values: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Delete every existing notes block and insert one numbered block (at ``pos_m`` or the old position)."""
    rep: Dict[str, Any] = {"deleted": 0, "errors": []}
    blocks = find_blocks(dwg, heading)
    old_pos = blocks[0][2] if blocks else None
    for nt, vn, _pos, _t in blocks:
        if delete_note(dwg, nt, vn):
            rep["deleted"] += 1
        else:
            rep["errors"].append(f"could not delete notes block in {vn}")
    text = numbered_text(lines, heading=heading, values=values)
    insert_block(dwg, text, pos_m or old_pos, style)
    rep["position_m"] = list(pos_m or old_pos or [])
    rep["text_head"] = text[:120]
    com.call(dwg, "GraphicsRedraw2")
    return rep


def dedupe_blocks(dwg, pos_m: Optional[Sequence[float]] = None, heading: str = "NOTES:") -> Dict[str, Any]:
    """Keep the numbered notes block, delete copies that lost their numbering, optionally move the keeper."""
    rep: Dict[str, Any] = {"deleted": [], "errors": []}
    blocks = find_blocks(dwg, heading)
    keep = next((nt for nt, _vn, _p, t in blocks if has_numbering(t)), None)
    rep["kept"] = keep is not None
    if keep is None:
        # SolidWorks' own list numbering isn't visible in GetText: don't delete what might be the real one
        rep["errors"].append(f"no notes block with visible '1.' numbering among {len(blocks)}; nothing deleted. "
                             "Use 'notes replace' to rebuild the block.")
        return rep
    for nt, vn, _pos, t in blocks:
        if has_numbering(t):
            continue
        if delete_note(dwg, nt, vn):
            rep["deleted"].append(vn)
        else:
            rep["errors"].append(f"could not delete notes block in {vn}")
    if pos_m:
        com.call(keep, "GetAnnotation").SetPosition2(pos_m[0], pos_m[1], 0)
    com.call(dwg, "GraphicsRedraw2")
    return rep
