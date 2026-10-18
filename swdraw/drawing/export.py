"""PDF export and a raster preview for visual checking."""
from __future__ import annotations

import os
from typing import Dict, Optional

from .. import com
from ..runner import log, output_dir

SAVE_AS_CURRENT_VERSION = 0
SAVE_AS_SILENT = 1


def export(dwg, path: str) -> Dict[str, object]:
    """Save a copy of the drawing as PDF/PNG/DXF etc. (format from the extension)."""
    path = os.path.abspath(os.path.expanduser(path))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    errors, warnings = com.byref_int(), com.byref_int()
    ok = dwg.Extension.SaveAs(path, SAVE_AS_CURRENT_VERSION, SAVE_AS_SILENT, com.nothing(), errors, warnings)
    res = {"path": path, "ok": bool(ok) and os.path.isfile(path),
           "errors": getattr(errors, "value", None), "warnings": getattr(warnings, "value", None)}
    if not res["ok"]:
        log(f"  export failed: {res}")
    return res


def export_pdf(dwg, path: Optional[str] = None, stem: Optional[str] = None) -> Dict[str, object]:
    if path is None:
        stem = stem or os.path.splitext(os.path.basename(str(com.call(dwg, "GetPathName")) or "drawing"))[0] or "drawing"
        path = os.path.join(output_dir(), stem + ".pdf")
    return export(dwg, path)


def preview_png(pdf_path: str, dpi: int = 110) -> Optional[str]:
    """Render page 1 of the PDF to PNG for a visual check (needs PyMuPDF; optional)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        log("  PyMuPDF not installed; skipping PNG preview (pip install pymupdf)")
        return None
    doc = fitz.open(pdf_path)
    try:
        pix = doc[0].get_pixmap(dpi=dpi)
        out = os.path.splitext(pdf_path)[0] + ".png"
        pix.save(out)
        return out
    finally:
        doc.close()
