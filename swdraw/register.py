"""Drawing register workbook (openpyxl): Register, Revision History and Numbering tabs.

* **Register**: one row per drawing. *Current rev* and *Rev date* are formulas that look up the
  latest entry for that number in Revision History, so the register never goes stale.
* **Revision History**: the only tab people type into. Input cells are yellow; Status and the
  drawing number have dropdowns.
* **Numbering**: the numbering rules from the profile and the numbers allocated so far.

Input (``build_register(path, data, scheme)``)::

    title: "ACME1 drawing register"
    drawings: [{number, title, type: Part|Assembly|Drawing, parent, file}]
    revisions: [{number, rev, date: "2026-10-18" | date, description, by, approved, status}]
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

from .numbering import Scheme

YELLOW = "FFF2CC"
HEADER = "D9D9D9"
STATUSES = ["DRAFT", "PROTOTYPE", "FOR REVIEW", "RELEASED", "SUPERSEDED", "OBSOLETE"]
TYPES = ["Part", "Assembly", "Drawing", "Purchased"]
HISTORY_ROWS = 500          # pre-formatted input rows


def _date(v):
    if v is None or v == "":
        return None
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return _dt.datetime.strptime(str(v), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date {v!r} (use YYYY-MM-DD or DD/MM/YYYY)")


def build_register(path: str, data: Dict[str, Any], scheme: Optional[Scheme] = None) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    scheme = scheme or Scheme()
    drawings: List[Dict[str, Any]] = list(data.get("drawings") or [])
    revisions: List[Dict[str, Any]] = list(data.get("revisions") or [])
    bold = Font(bold=True)
    hdr_fill = PatternFill("solid", fgColor=HEADER)
    in_fill = PatternFill("solid", fgColor=YELLOW)
    thin = Side(style="thin", color="BFBFBF")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)

    wb = Workbook()
    reg = wb.active
    reg.title = "Register"
    hist = wb.create_sheet("Revision History")
    num = wb.create_sheet("Numbering")

    def header(ws, row, cols, widths):
        for i, (c, w) in enumerate(zip(cols, widths), 1):
            cell = ws.cell(row=row, column=i, value=c)
            cell.font, cell.fill, cell.border = bold, hdr_fill, box
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = ws.cell(row=row + 1, column=1)

    # ------------------------------------------------------------------ Revision History
    hcols = ["Drawing No.", "Rev", "Date", "Description", "Drawn", "Approved", "Status"]
    header(hist, 1, hcols, [20, 6, 12, 50, 8, 10, 14])
    last = HISTORY_ROWS + 1
    for r in range(2, last + 1):
        for c in range(1, len(hcols) + 1):
            cell = hist.cell(row=r, column=c)
            cell.fill, cell.border = in_fill, box
        hist.cell(row=r, column=3).number_format = "DD/MM/YYYY"
    for i, rv in enumerate(revisions, 2):
        vals = [rv.get("number"), rv.get("rev"), _date(rv.get("date")), rv.get("description"),
                rv.get("by"), rv.get("approved"), rv.get("status")]
        for c, v in enumerate(vals, 1):
            hist.cell(row=i, column=c, value=v)
    n_dwg = max(len(drawings), 1)
    dv_num = DataValidation(type="list", formula1=f"=Register!$A$5:$A${4 + max(n_dwg, 200)}", allow_blank=True)
    dv_stat = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=True)
    hist.add_data_validation(dv_num)
    hist.add_data_validation(dv_stat)
    dv_num.add(f"A2:A{last}")
    dv_stat.add(f"G2:G{last}")
    hist.auto_filter.ref = f"A1:G{last}"

    # ------------------------------------------------------------------ Register
    reg["A1"] = data.get("title") or f"{scheme.product} drawing register"
    reg["A1"].font = Font(bold=True, size=14)
    reg["A2"] = ("Current rev and date are calculated from Revision History. "
                 "Add a row there to issue a revision; do not type in the grey columns.")
    rcols = ["Drawing No.", "Title", "Type", "Parent", "Current Rev", "Rev Date", "Status", "File"]
    header(reg, 4, rcols, [20, 40, 11, 20, 11, 12, 14, 34])
    H = "'Revision History'"
    rng = lambda col: f"{H}!${col}$2:${col}${last}"  # noqa: E731
    for i, d in enumerate(drawings, 5):
        reg.cell(row=i, column=1, value=d.get("number"))
        reg.cell(row=i, column=2, value=d.get("title"))
        reg.cell(row=i, column=3, value=d.get("type"))
        reg.cell(row=i, column=4, value=d.get("parent"))
        # last matching row in Revision History (LOOKUP(2, 1/(cond), result) works in Excel and LibreOffice)
        reg.cell(row=i, column=5, value=f'=IFERROR(LOOKUP(2,1/({rng("A")}=$A{i}),{rng("B")}),"")')
        c = reg.cell(row=i, column=6, value=f'=IFERROR(LOOKUP(2,1/({rng("A")}=$A{i}),{rng("C")}),"")')
        c.number_format = "DD/MM/YYYY"
        reg.cell(row=i, column=7, value=f'=IFERROR(LOOKUP(2,1/({rng("A")}=$A{i}),{rng("G")}),"")')
        reg.cell(row=i, column=8, value=d.get("file"))
        for col in range(1, 9):
            reg.cell(row=i, column=col).border = box
    dv_type = DataValidation(type="list", formula1='"' + ",".join(TYPES) + '"', allow_blank=True)
    reg.add_data_validation(dv_type)
    dv_type.add(f"C5:C{4 + max(n_dwg, 200)}")

    # ------------------------------------------------------------------ Numbering
    num["A1"] = "Numbering rules"
    num["A1"].font = Font(bold=True, size=14)
    rules = [
        ("Format", scheme.pattern.replace("{number:04d}", "NNNN")),
        ("Product code", scheme.product),
        ("Assemblies", f"multiples of {scheme.block} (e.g. {scheme.format(scheme.first_block)})"),
        ("Parts", f"assembly number + 1 to + {scheme.block - 1} "
                  f"(e.g. {scheme.format(scheme.first_block + 1)})"),
    ] + [(f"Discipline {k}", v) for k, v in scheme.disciplines.items()]
    for i, (k, v) in enumerate(rules, 3):
        num.cell(row=i, column=1, value=k).font = bold
        num.cell(row=i, column=2, value=v)
    start = len(rules) + 5
    header(num, start, ["Allocated No.", "Kind", "Title"], [20, 40, 40])
    num.freeze_panes = None
    for i, d in enumerate(sorted(drawings, key=lambda d: str(d.get("number"))), start + 1):
        n = str(d.get("number") or "")
        kind = scheme.describe(n) if scheme.is_valid(n) else "does not match the scheme"
        num.cell(row=i, column=1, value=n)
        num.cell(row=i, column=2, value=kind)
        num.cell(row=i, column=3, value=d.get("title"))

    wb.save(path)
    return path
