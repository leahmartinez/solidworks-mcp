from fakes import FakeDrawing, section_array

from swdraw.drawing.context import DrawingContext, Pick
from swdraw.drawing.dims import add_dimension


def make():
    dwg = FakeDrawing()
    sec = dwg.add_view("Section View C-C", section_array())
    ctx = DrawingContext(dwg)
    ctx.regen_pause_s = 0
    ctx.alias("C", "Section View C-C")
    return dwg, sec, ctx


def test_pick_parse_forms():
    assert Pick.parse([1, 2, 3]).kind == "EDGE"
    assert Pick.parse([1, 2, 3, "vertex"]).kind == "VERTEX"
    p = Pick.parse({"at": [1, 2, 3], "kind": "silhouette"})
    assert (p.x, p.y, p.z, p.kind) == (1, 2, 3, "SILHOUETTE")


def test_select_rejects_view_only_pick():
    dwg, sec, ctx = make()
    assert ctx.select(sec, [0, 5, 5]) is False          # nothing there: only the view got picked
    dwg.add_geometry(sec, (0, 5, 5), "e1")
    assert ctx.select(sec, [0, 5, 5]) is True


def test_select_tries_other_kinds():
    dwg, sec, ctx = make()
    dwg.add_geometry(sec, (0, 1, 1), "s1", kind="SILHOUETTE")
    assert ctx.select(sec, [0, 1, 1, "EDGE"]) is True
    assert dwg.selection[-1][1] == "s1"


def test_dimension_with_expected_value_and_tolerance():
    dwg, sec, ctx = make()
    dwg.add_geometry(sec, (0, 12, -8), "bore_l")
    dwg.add_geometry(sec, (0, 12, 8), "bore_r")
    dwg.measure[("bore_l", "bore_r")] = 0.016
    dd = add_dimension(ctx, {"id": "D_BORE", "view": "C", "pick": [[0, 12, -8], [0, 12, 8]],
                             "text_at": [0, 18, 0], "prefix": "<MOD-DIAM>", "suffix": " H7", "expect": 16,
                             "tolerance": {"type": "bilateral", "lower": 0, "upper": 0.018}, "precision": 3})
    assert dd is not None
    assert dd.text == {1: "<MOD-DIAM>", 2: " H7"} and dd.precision == 3
    tol = dd.dim.Tolerance
    assert tol.Type == 2 and abs(tol.GetMaxValue() - 0.000018) < 1e-12
    rec = ctx.report.dims[-1]
    assert rec["id"] == "D_BORE" and rec["value_mm"] == 16.0 and rec["tolerance"] == "SetValues2"
    assert ctx.state["dim:D_BORE"] is dd


def test_wrong_value_falls_back_to_alternative_pair():
    dwg, sec, ctx = make()
    for gid, xyz in {"a": (0, 0, -14), "b": (0, 25, -10.5), "c": (0, 0, 14), "d": (0, 25, 10.5)}.items():
        dwg.add_geometry(sec, xyz, gid)
    dwg.measure[("a", "b")] = 0.0245          # wrong edge picked on the first pair
    dwg.measure[("c", "d")] = 0.025
    dd = add_dimension(ctx, {"id": "L", "view": "C", "pick": [[0, 0, -14], [0, 25, -10.5]],
                             "alternatives": [[[0, 0, 14], [0, 25, 10.5]]], "text_at": [0, 12, -30], "expect": 25})
    assert dd is not None
    assert ctx.report.dims[-1]["pair"] == 1
    assert len(dwg.dims) == 1                 # the wrong one was deleted
    assert dwg.rebuilds >= 1                  # regenerated before retrying


def test_last_mismatch_is_kept_and_flagged():
    dwg, sec, ctx = make()
    dwg.add_geometry(sec, (0, 0, 0), "a")
    dwg.add_geometry(sec, (0, 1, 0), "b")
    dwg.measure[("a", "b")] = 0.002
    dd = add_dimension(ctx, {"id": "X", "view": "C", "pick": [[0, 0, 0], [0, 1, 0]],
                             "text_at": [0, 0, 5], "expect": 1})
    assert dd is not None and len(dwg.dims) == 1          # retried once after a regen, then kept
    assert ctx.report.dims[-1]["mismatch"] is True
    assert any("X: measured 2.000" in e for e in ctx.report.errors)


def test_tolerance_codes():
    from swdraw.drawing.dims import tol_type
    assert tol_type("fit") == 8 and tol_type("symmetric") == 4 and tol_type(2) == 2 and tol_type("3") == 3


def test_selection_failure_reported():
    dwg, sec, ctx = make()
    assert add_dimension(ctx, {"id": "Y", "view": "C", "pick": [[0, 9, 9]], "text_at": [0, 0, 0], "expect": 1}) is None
    assert "error" in ctx.report.dims[-1]
