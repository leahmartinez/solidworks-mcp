"""Geometry, runner, config, notes text and numbering: no COM involved."""
import os

import pytest

from swdraw import runner
from swdraw.config import HouseStyle, deep_merge, load_title_block
from swdraw.geometry import model_to_sheet, sheet_to_sketch, up_is_positive
from swdraw.notes import has_numbering, numbered_text
from swdraw.numbering import Scheme
from swdraw.renumber import plan_paths, replace_numbers
from swdraw.revision import row_for

from fakes import identity_array, section_array


# --------------------------------------------------------------------------- geometry
def test_model_to_sheet_identity_and_scale():
    a = identity_array(0.1, 0.2, scale=2.0)
    assert model_to_sheet(a, 10, 5, 99) == pytest.approx((0.1 + 0.02, 0.2 + 0.01))


def test_model_to_sheet_section_uses_z():
    a = section_array(0.2, 0.1)
    assert model_to_sheet(a, 99, 5, -20) == pytest.approx((0.2 - 0.02, 0.1 + 0.005))


def test_sheet_to_sketch_round_trip():
    xf = [0.2, 0.1, 2.0]
    sx, sy, sc = sheet_to_sketch(xf, 0.24, 0.12)
    assert (sx, sy, sc) == pytest.approx((0.02, 0.01, 2.0))


def test_upright_flag():
    assert up_is_positive(identity_array())
    flipped = identity_array()
    flipped[4] = -1
    assert not up_is_positive(flipped)


# --------------------------------------------------------------------------- runner
def test_args_from_env_json_and_file(monkeypatch, tmp_path):
    monkeypatch.setenv("SWDRAW_ARGS", '{"a": 1}')
    assert runner.args() == {"a": 1}
    runner._ARGS = None
    f = tmp_path / "a.yaml"
    f.write_text("b: [1, 2]\n")
    monkeypatch.setenv("SWDRAW_ARGS", str(f))
    assert runner.args() == {"b": [1, 2]}


def test_result_markers_round_trip(capsys):
    runner.result({"ok": True, "obj": object()}, name="t")
    out = capsys.readouterr().out
    res = runner.extract_result(out)
    assert res["ok"] is True and isinstance(res["obj"], str)
    assert os.path.isfile(os.path.join(runner.output_dir(), "t.json"))


# --------------------------------------------------------------------------- config
def test_house_style_defaults_and_overrides():
    st = HouseStyle.load(overrides={"note_height_pt": 10, "unknown_key": 1})
    assert st.font == "Arial" and st.dim_h == pytest.approx(0.0025) and st.label_h == pytest.approx(0.0035)
    assert st.note_height_pt == 10
    assert st.general_tolerance == "ISO 2768-mK"


def test_profile_dir_env_overrides_bundled(monkeypatch, tmp_path):
    (tmp_path / "house_style.yaml").write_text("font: Helvetica\n")
    monkeypatch.setenv("SWDRAW_PROFILES", str(tmp_path))
    assert HouseStyle.load().font == "Helvetica"


def test_deep_merge():
    assert deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}}) == {"a": {"b": 1, "c": 3}}


def test_bundled_title_block_profile_shape():
    tb = load_title_block()
    assert tb["mode"] == "custom_properties"
    cols = tb["placeholder_notes"]["rev_table"]["columns"]
    assert set(cols) == {"rev", "desc", "date", "drawn", "approved"}


# --------------------------------------------------------------------------- notes text
def test_numbered_text_with_continuations_and_values():
    t = numbered_text(["FIRST {x}", ["SECOND", "more"], "   indented", "THIRD"], values={"x": "OK"})
    assert t.splitlines() == ["NOTES:", "1.  FIRST OK", "2.  SECOND", "     more", "     indented", "3.  THIRD"]
    assert has_numbering(t)
    assert not has_numbering("NOTES:\nFIRST\nSECOND")


def test_numbered_text_keeps_unknown_placeholders():
    assert "{nope}" in numbered_text(["A {nope}"])


# --------------------------------------------------------------------------- numbering
@pytest.fixture
def scheme():
    return Scheme({"product": "ACME1", "pattern": "{product}-{discipline}-{number:04d}", "block_size": 100,
                   "first_block": 2100, "disciplines": {"MEC": "m", "ELE": "e"},
                   "part_properties": {"PartNo": "{number}", "ParentAssy": "{parent}", "Supplier": "{supplier}"},
                   "properties_static": {"supplier": "TBC"}})


def test_parse_and_format(scheme):
    pn = scheme.parse("ACME1-MEC-2101")
    assert (pn.product, pn.discipline, pn.number) == ("ACME1", "MEC", 2101)
    assert scheme.format(2101) == "ACME1-MEC-2101"
    assert not scheme.is_valid("ACME1-XYZ-2101")
    assert not scheme.is_valid("ACME1-MEC-11O1")


def test_blocks(scheme):
    assert scheme.describe("ACME1-MEC-2100").startswith("assembly")
    assert "ACME1-MEC-2100" in scheme.describe("ACME1-MEC-2105")
    used = ["ACME1-MEC-2100", "ACME1-MEC-2101", "ACME1-MEC-2102", "ACME1-MEC-2200"]
    assert scheme.next_part("ACME1-MEC-2100", used) == "ACME1-MEC-2103"
    assert scheme.next_assembly(used) == "ACME1-MEC-2300"
    with pytest.raises(ValueError):
        scheme.next_part("ACME1-MEC-2101", used)


def test_properties_template(scheme):
    p = scheme.properties("part", "ACME1-MEC-2101", parent="ACME1-MEC-2100")
    assert p == {"PartNo": "ACME1-MEC-2101", "ParentAssy": "ACME1-MEC-2100", "Supplier": "TBC"}


def test_bundled_numbering_profile_loads():
    sc = Scheme()
    assert sc.is_valid(sc.format(sc.first_block + 1))


# --------------------------------------------------------------------------- renumber / revision helpers
def test_replace_numbers_longest_first():
    m = {"X-MEC-004": "X-MEC-2100", "X-MEC-0041": "X-MEC-2101"}
    assert replace_numbers("X-MEC-0041 IN X-MEC-004", m) == "X-MEC-2101 IN X-MEC-2100"


def test_plan_paths(tmp_path):
    d = str(tmp_path / "A-MEC-0042.SLDDRW")
    p = plan_paths(d, "A-MEC-0042", "A-MEC-2101")
    assert p["old_part"].endswith("A-MEC-0042.SLDPRT")
    assert p["new_drawing"].endswith("A-MEC-2101.SLDDRW")


def test_row_for():
    assert row_for("A") == 1 and row_for("c") == 3 and row_for("0") == 1
    with pytest.raises(ValueError):
        row_for("AB")


def test_replace_numbers_updates_revision():
    t = "DEFINED BY 3D MODEL X-MEC-0042 REV A (STEP SUPPLIED)"
    assert replace_numbers(t, {"X-MEC-0042": "X-MEC-2101"}, "B") == "DEFINED BY 3D MODEL X-MEC-2101 REV B (STEP SUPPLIED)"
    assert replace_numbers("X-MEC-0042", {"X-MEC-0042": "X-MEC-2101"}, "B") == "X-MEC-2101"


class _ComLike:
    """Callable like a pywin32 CDispatch: calling it is the bug com.call must avoid."""

    def __call__(self, *a):
        raise AssertionError("COM object was called")


def test_call_returns_com_objects_from_properties(monkeypatch):
    from swdraw import com
    monkeypatch.setattr(com, "EXTRA_DISPATCH_TYPES", [_ComLike])
    sel = _ComLike()

    class Doc:
        SelectionManager = sel
        value = 3

        def GetTitle(self):
            return "t"

    assert com.call(Doc(), "SelectionManager") is sel
    assert com.call(Doc(), "GetTitle") == "t" and com.call(Doc(), "value") == 3
