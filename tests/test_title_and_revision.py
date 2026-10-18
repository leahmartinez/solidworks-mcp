"""Title-block matching and revision application, using the bundled profile."""
import copy

from fakes import FakeDrawing, FakeNote, FakePart

from swdraw import revision, title_block as tb
from swdraw.config import HouseStyle, load_title_block

PROFILE = load_title_block()


def placeholder_profile():
    p = copy.deepcopy(PROFILE)
    p["mode"] = "placeholder_notes"
    return p


def sheet_notes():
    """The placeholder layout the A3 template produces (sheet mm from bottom-left)."""
    raw = [("PART-NO", 301.2, 15.6), ("PART DESCRIPTION", 301.2, 29.6), ("MATERIAL SPECIFICATION", 231.2, 29.8),
           ("FINISH / TREATMENT", 231.2, 25.05),            # the label
           ("FINISH / TREATMENT", 231.2, 21.6),             # the value placeholder
           ("NAME", 231.2, 45.8), ("DD/MM/YYYY", 279.2, 45.5),
           ("NAME", 231.2, 37.8), ("DD/MM/YYYY", 279.2, 37.5),
           ("A", 358.5, 15.6), ("REV", 356.2, 21.0), ("DRAFT", 332.0, 57.7),
           ("A", 233.5, 73.4), ("FIRST ISSUE", 242.0, 73.4), ("DD/MM/YYYY", 353.5, 73.4), ("XX", 376.5, 73.4), ("XX", 393.5, 73.4),
           ("B", 233.5, 78.4), ("REVISION DESCRIPTION", 242.0, 78.4), ("DD/MM/YYYY", 353.5, 78.4), ("XX", 376.5, 78.4),
           ("XX", 393.5, 78.4)]
    return [tb.SheetNote(t, x, y) for t, x, y in raw]


def by_field(updates):
    return {u.field: u for u in updates}


def test_fields_disambiguated_by_position():
    ups = by_field(tb.plan_fields(sheet_notes(), {"drawn_by": "A. DRAFTER", "approved_by": "C. CHECKER",
                                                   "finish": "AS MACHINED", "part_no": "ACME1-MEC-2101"},
                                  placeholder_profile()))
    assert ups["drawn_by"].note.y == 45.8 and ups["approved_by"].note.y == 37.8
    assert ups["finish"].note.y == 21.6               # the value, not the label above it
    assert ups["part_no"].new_text == "ACME1-MEC-2101"


def test_filled_fields_are_not_overwritten_without_flag():
    notes = sheet_notes()
    notes[0].text = "ACME1-MEC-0040"
    assert "part_no" not in by_field(tb.plan_fields(notes, {"part_no": "X"}, placeholder_profile()))
    assert "part_no" in by_field(tb.plan_fields(notes, {"part_no": "X"}, placeholder_profile(), overwrite=True))


def test_rev_row_and_box():
    notes = sheet_notes()
    ups = tb.plan_rev_row(notes, 1, {"rev": "B", "desc": "BORE TOL", "date": "18/10/2026", "drawn": "AD",
                                     "approved": "CC"}, placeholder_profile())
    f = by_field(ups)
    assert set(f) == {"rev2.rev", "rev2.desc", "rev2.date", "rev2.drawn", "rev2.approved"}
    assert all(u.note.y == 78.4 for u in ups)
    box = tb.plan_rev_box(notes, "B", placeholder_profile())
    assert [u.note.x for u in box] == [358.5]           # "REV" label is left alone


def test_see_note():
    n = [tb.SheetNote("AS MACHINED - SEE NOTE 4", 0, 0)]
    assert tb.plan_see_note(n, 6, placeholder_profile())[0].new_text == "AS MACHINED - SEE NOTE 6"


def test_property_mapping():
    vals = {"part_no": "P", "drawn_by": "D", "unknown": "x"}
    assert tb.property_values(vals, PROFILE) == {"PartNo": "P", "DrawnBy": "D"}
    assert tb.rev_row_properties(1, {"rev": "B", "desc": "X"}, PROFILE) == {"Rev2": "B", "Rev2Desc": "X"}


def _drawing_with(notes):
    dwg = FakeDrawing()
    for n in notes:
        dwg.sheet.notes.append(FakeNote(dwg, n.text, (n.x / 1000, n.y / 1000)))
    return dwg


def test_revision_placeholder_mode_writes_sheet_notes():
    dwg = _drawing_with(sheet_notes())
    rep = revision.apply(dwg, {"rev": "B", "desc": "BORE TOL", "date": "18/10/2026", "drawn": "AD",
                               "approved": "CC", "approver_name": "C. CHECKER"}, placeholder_profile(), HouseStyle())
    texts = {(round(n.ann.position[0] * 1000, 1), round(n.ann.position[1] * 1000, 1)): n.text for n in dwg.sheet.notes}
    assert texts[(242.0, 78.4)] == "BORE TOL"
    assert texts[(358.5, 15.6)] == "B"
    assert texts[(231.2, 37.8)] == "C. CHECKER" and texts[(279.2, 37.5)] == "18/10/2026"
    assert texts[(242.0, 73.4)] == "FIRST ISSUE"          # rev A row untouched
    assert not rep["errors"]


def test_revision_custom_property_mode():
    dwg = FakeDrawing()
    v = dwg.add_view("Drawing View1", dwg.sheet.ModelToViewTransform.ArrayData)
    v.ReferencedDocument = FakePart()
    v.ReferencedDocument.props["Finish"] = "AS MACHINED - SEE NOTE 4"      # finish lives on the part
    rep = revision.apply(dwg, {"rev": "B", "desc": "BORE TOL", "date": "18/10/2026", "finish_note": 5},
                         PROFILE, HouseStyle())
    assert dwg.props["Revision"] == "B" and dwg.props["Rev2"] == "B" and dwg.props["Rev2Desc"] == "BORE TOL"
    assert v.ReferencedDocument.props["Finish"].endswith("SEE NOTE 5")
    assert not rep["errors"]
