"""Reference-safe renumbering of a part and its drawing.

The order matters (see references/api-gotchas.md):

1. write the new custom properties to the part
2. **Save As the part while its drawing is open**: the open drawing re-points to the new file
3. swap the number in the drawing's notes; the NOTES: block is re-inserted (SetText would drop
   its numbering); title block via custom properties or placeholder notes
4. Save As the drawing
5. check the drawing's dependencies point at the new part
6. optionally, once the documents are closed (SolidWorks keeps renamed files locked), move the old
   files to a superseded folder, rename the containing folder, reopen and verify

Arguments::

    drawing: path to the .SLDDRW (must be open, or it is opened)
    old: ACME1-MEC-0042          new: ACME1-MEC-2101
    old_parent: ACME1-MEC-0040   new_parent: ACME1-MEC-2100   (optional)
    description: "FLANGED BUSH"  revision: B
    part: path to the part (default: <folder>/<old>.SLDPRT)
    notes_lines: [...]           # optional new notes block content
    save: true                   # Save As both; false = properties and text only
    supersede: false             # close both, move old files to <folder>/../_Superseded
    rename_folder: {from: "ACME1-MEC-0040 Bracket", to: "ACME1-MEC-2100 Bracket"}   # optional, needs supersede
"""
from __future__ import annotations

import os
import re
import shutil
import time
from typing import Any, Dict, List, Optional

from . import com
from .config import HouseStyle
from .notes import delete_note, find_blocks, insert_block, is_notes_block, numbered_text
from .numbering import Scheme
from .title_block import set_custom_properties

SAVE_AS_SILENT, SAVE_AS_COPY = 1, 2


def replace_numbers(text: str, mapping: Dict[str, str], revision: Optional[str] = None) -> str:
    """Swap numbers (longest first, so ACME1-MEC-004 doesn't clip ACME1-MEC-0041).

    With ``revision``, "<old> REV x" also becomes "<new> REV <revision>" (e.g. the
    "DEFINED BY 3D MODEL ... REV A" note).
    """
    for old in sorted(mapping, key=len, reverse=True):
        if revision:
            text = re.sub(re.escape(old) + r"(\s+REV\s+)[A-Z0-9]{1,2}\b", lambda m: mapping[old] + m.group(1) + revision, text)
        text = text.replace(old, mapping[old])
    return text


def plan_paths(drawing: str, old: str, new: str, part: Optional[str] = None, scheme: Optional[Scheme] = None) -> Dict[str, str]:
    scheme = scheme or Scheme({})
    folder = os.path.dirname(os.path.abspath(drawing))
    return {
        "old_drawing": os.path.abspath(drawing),
        "old_part": os.path.abspath(part) if part else os.path.join(folder, scheme.file_stem(old) + ".SLDPRT"),
        "new_part": os.path.join(folder, scheme.file_stem(new) + ".SLDPRT"),
        "new_drawing": os.path.join(folder, scheme.file_stem(new) + ".SLDDRW"),
        "folder": folder,
    }


def dependencies(path: str) -> List[str]:
    """Referenced file paths (GetDocumentDependencies2 returns name/path pairs)."""
    deps = list(com.app().GetDocumentDependencies2(path, False, True, False) or [])
    return deps[1::2]


def _save_as(doc, path: str) -> int:
    err = doc.SaveAs3(path, 0, SAVE_AS_SILENT)
    return int(err or 0)


def renumber(a: Dict[str, Any], scheme: Optional[Scheme] = None, style: Optional[HouseStyle] = None) -> Dict[str, Any]:
    scheme = scheme or Scheme()
    style = style or HouseStyle()
    rep: Dict[str, Any] = {"done": [], "errors": []}
    old, new = a["old"], a["new"]
    for n in (new, a.get("new_parent")):
        if n and not scheme.is_valid(n):
            rep["errors"].append(f"{n} does not match the numbering scheme {scheme.pattern}")
    if rep["errors"]:
        return rep
    paths = plan_paths(a["drawing"], old, new, a.get("part"), scheme)
    rep["paths"] = paths
    mapping = {old: new}
    if a.get("old_parent") and a.get("new_parent"):
        mapping[a["old_parent"]] = a["new_parent"]
    rev, desc = a.get("revision", "A"), a.get("description", "")

    drw = com.open_doc(paths["old_drawing"]) if com.get_open(paths["new_drawing"]) is None else com.get_open(paths["new_drawing"])
    part = com.get_open(paths["old_part"]) or com.get_open(paths["new_part"])
    if part is None:
        rep["errors"].append(f"part not loaded with the drawing: {paths['old_part']}")
        return rep

    # 1-2. part properties, then Save As while the drawing is open
    rep["done"] += set_custom_properties(part, scheme.properties("part", new, desc, rev, a.get("new_parent", "")))
    if a.get("save", True) and str(com.call(part, "GetPathName")).lower() != paths["new_part"].lower():
        err = _save_as(part, paths["new_part"])
        if err:
            rep["errors"].append(f"part Save As error {err}")
            return rep
        rep["done"].append(f"part -> {os.path.basename(paths['new_part'])}")

    # 3. drawing text
    for v in com.views(drw):
        for nt in com.notes(v):
            t = str(com.call(nt, "GetText"))
            if is_notes_block(t):
                continue        # handled below (re-inserted, never SetText)
            nt_new = replace_numbers(t, mapping, rev)
            if nt_new != t:
                nt.SetText(nt_new)
                rep["done"].append(f"note {t.strip()[:40]!r} updated")
    for nt, vn, pos, t in find_blocks(drw):
        lines = a.get("notes_lines")
        new_text = numbered_text(lines) if lines else replace_numbers(t, mapping, rev)
        if new_text != t:
            if delete_note(drw, nt, vn):
                insert_block(drw, new_text, pos, style)
                rep["done"].append(f"notes block re-inserted in {vn}")
            else:
                rep["errors"].append(f"could not delete notes block in {vn}")
    rep["done"] += set_custom_properties(drw, scheme.properties("drawing", new, desc, rev, a.get("new_parent", "")))
    com.call(drw, "GraphicsRedraw2")

    # 4-5. drawing Save As and dependency check
    if a.get("save", True) and not rep["errors"]:
        if str(com.call(drw, "GetPathName")).lower() != paths["new_drawing"].lower():
            err = _save_as(drw, paths["new_drawing"])
            if err:
                rep["errors"].append(f"drawing Save As error {err}")
                return rep
            rep["done"].append(f"drawing -> {os.path.basename(paths['new_drawing'])}")
        deps = dependencies(paths["new_drawing"])
        rep["dependencies"] = deps
        if not any(os.path.normcase(d) == os.path.normcase(paths["new_part"]) for d in deps):
            rep["errors"].append("drawing does not reference the new part; check before superseding")

    # 6. supersede old files and optionally rename the folder
    if a.get("supersede") and not rep["errors"]:
        rep.update(supersede(paths, a.get("rename_folder")))
    return rep


def supersede(paths: Dict[str, str], rename_folder: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"superseded": [], "supersede_errors": []}
    sw = com.app()
    for p in (paths["new_drawing"], paths["new_part"], paths["old_drawing"], paths["old_part"]):
        try:
            sw.CloseDoc(p)
        except Exception:
            pass
    time.sleep(2)       # let SolidWorks release the file locks
    folder = paths["folder"]
    sup = os.path.join(os.path.dirname(folder), "_Superseded")
    os.makedirs(sup, exist_ok=True)
    for p in (paths["old_drawing"], paths["old_part"]):
        if os.path.exists(p):
            try:
                dst = os.path.join(sup, os.path.basename(p))
                if os.path.exists(dst):
                    stem, ext = os.path.splitext(dst)
                    dst = f"{stem} ({time.strftime('%Y-%m-%d %H%M')}){ext}"
                shutil.move(p, dst)
                out["superseded"].append(os.path.basename(p))
            except Exception as exc:
                out["supersede_errors"].append(f"{os.path.basename(p)}: {exc.__class__.__name__}")
    new_drawing = paths["new_drawing"]
    if rename_folder:
        parent = os.path.dirname(os.path.dirname(folder)) if os.path.basename(folder) == "Working" else os.path.dirname(folder)
        src = os.path.join(parent, rename_folder["from"])
        dst = os.path.join(parent, rename_folder["to"])
        if os.path.isdir(src) and not os.path.exists(dst):
            try:
                os.rename(src, dst)
                new_drawing = new_drawing.replace(src, dst, 1)
                out["folder_renamed"] = dst
            except OSError as exc:
                out["supersede_errors"].append(f"rename folder: {exc.__class__.__name__}: {exc} "
                                               "(close Explorer windows and SolidWorks documents in it, then rename by hand)")
        else:
            out["supersede_errors"].append(f"rename folder skipped: {src} missing or {dst} exists")
    # reopen from the final location, rebuild and save so stored reference paths update
    try:
        d = com.open_doc(new_drawing)
        com.call(d, "ForceRebuild3", False)
        out["resaved"] = bool(d.Save2(True))
        out["dependencies_after"] = dependencies(new_drawing)
        out["missing_after"] = [p for p in out["dependencies_after"] if not os.path.exists(p)]
    except Exception as exc:
        out["supersede_errors"].append(f"reopen: {exc}")
    return out
