"""Builder steps against the fake drawing, notes replace/dedupe, CLI and MCP guards."""
import importlib
import json
import os

import pytest
from fakes import FakeDrawing, FakeNote, FakePart, section_array

from swdraw import cli, notes, runner
from swdraw.drawing import build

SPEC = {
    "drawing": {"id": "T"},
    "dimensions": [{"id": "D", "view": "Section View C-C", "pick": [[0, 12, -8], [0, 12, 8]],
                    "text_at": [0, 18, 0], "expect": 16}],
    "notes": {"at": [24, 92], "lines": ["MATERIAL: {material}.", "SECOND"]},
    "title_block": {"part_no": "ACME1-MEC-2101", "material": "BRONZE", "drawn_date": "today"},
}


def fake():
    dwg = FakeDrawing()
    sec = dwg.add_view("Section View C-C", section_array())
    sec.ReferencedDocument = FakePart()
    dwg.add_geometry(sec, (0, 12, -8), "l")
    dwg.add_geometry(sec, (0, 12, 8), "r")
    dwg.measure[("l", "r")] = 0.016
    return dwg


def test_build_subset_of_steps(monkeypatch):
    import swdraw.drawing.context as ctxmod
    monkeypatch.setattr(ctxmod.time, "sleep", lambda s: None)
    dwg = fake()
    rep = build(SPEC, steps=["dimensions", "notes", "title"], dwg=dwg)
    assert rep["steps"]["dimensions"] == "1 ok, 0 failed"
    assert rep["check"]["ok"], rep
    block = dwg.inserted_notes[0]
    assert block.text.splitlines()[:2] == ["NOTES:", "1.  MATERIAL: BRONZE."]
    assert block.ann.tf.CharHeightInPts == 8 and block.ann.tf.TypeFaceName == "Arial"
    assert block.ann.position == pytest.approx((0.024, 0.092))
    part = dwg._views[1].ReferencedDocument
    assert part.props["PartNo"] == "ACME1-MEC-2101" and part.props["Material"] == "BRONZE"   # $PRPSHEET fields
    assert "PartNo" not in dwg.props
    assert dwg.props["DrawnDate"].count("/") == 2          # "today" -> DD/MM/YYYY


def test_build_rejects_unknown_step():
    with pytest.raises(ValueError):
        build(SPEC, steps=["nope"], dwg=fake())


def test_replace_and_dedupe_notes_block():
    dwg = FakeDrawing()
    dwg.sheet.notes += [FakeNote(dwg, "NOTES:\n1.  OLD", (0.03, 0.09)), FakeNote(dwg, "NOTES:\nOLD COPY", (0.03, 0.05))]
    rep = notes.dedupe_blocks(dwg, pos_m=[0.024, 0.092])
    assert rep["kept"] and len(rep["deleted"]) == 1
    assert [n.text for n in dwg.sheet.notes] == ["NOTES:\n1.  OLD"]
    rep = notes.replace_block(dwg, ["NEW ONE", "NEW TWO"])
    assert rep["deleted"] == 1
    assert [n.text for n in dwg.sheet.notes] == ["NOTES:\n1.  NEW ONE\n2.  NEW TWO"]
    assert dwg.sheet.notes[0].ann.position == pytest.approx((0.024, 0.092))   # kept the old position


def run_cli(capsys, *argv):
    code = cli.main(list(argv))
    return code, runner.extract_result(capsys.readouterr().out)


def test_cli_validate_example(capsys):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code, res = run_cli(capsys, "validate", "--spec", os.path.join(root, "examples/flanged_bush/bush.drawing.yaml"))
    assert code == 0 and res == {"ok": True, "problems": []}


def test_cli_number_and_tidy(capsys, tmp_path):
    code, res = run_cli(capsys, "number", "next-part", "--args",
                        json.dumps({"assembly": "ACME1-MEC-2100", "used": ["ACME1-MEC-2101"]}))
    assert res == {"number": "ACME1-MEC-2102"}
    (tmp_path / "W").mkdir()
    (tmp_path / "W" / "x.txt").write_text("x")
    code, res = run_cli(capsys, "tidy", "--args", json.dumps({"working": str(tmp_path / "W"), "keep": []}))
    assert res["dry_run"] is True and res["moves"]


def test_cli_register(capsys, tmp_path):
    out = tmp_path / "r.xlsx"
    code, res = run_cli(capsys, "register", "--args", json.dumps({"out": str(out), "drawings": [{"number": "ACME1-MEC-2101"}]}))
    assert code == 0 and out.exists()


def test_cli_reports_errors_as_json(capsys):
    code, res = run_cli(capsys, "validate", "--spec", "does-not-exist.yaml")
    assert code == 1 and res["ok"] is False


def test_cli_run_passes_args(capsys, tmp_path):
    s = tmp_path / "s.py"
    s.write_text("import swdraw as sw\nsw.result({'got': sw.args()['x']})\n")
    code, res = run_cli(capsys, "run", str(s), "--args", '{"x": 7}')
    assert res == {"got": 7}


def test_mcp_run_script_is_confined(monkeypatch, tmp_path):
    pytest.importorskip("mcp")
    server = importlib.import_module("mcp_server.server")
    monkeypatch.setenv("SWDRAW_SCRIPTS_DIR", str(tmp_path))
    assert "inside" in server.swdraw_run_script("../evil.py")["error"]
    assert "inside" in server.swdraw_run_script("notes.txt")["error"]
    (tmp_path / "ok.py").write_text("import swdraw as sw\nsw.result({'v': sw.args().get('v')})\n")
    assert server.swdraw_run_script("ok.py", {"v": 3}) == {"v": 3}


def test_dedupe_without_visible_numbering_deletes_nothing():
    dwg = FakeDrawing()
    dwg.sheet.notes += [FakeNote(dwg, "NOTES:\nA"), FakeNote(dwg, "NOTES:\nB")]
    rep = notes.dedupe_blocks(dwg)
    assert rep["errors"] and not rep["kept"] and len(dwg.sheet.notes) == 2


def test_datum_finds_dimension_placed_in_an_earlier_run(monkeypatch):
    from swdraw import com
    from swdraw.drawing import annotations as ann
    from swdraw.drawing.context import DrawingContext
    dwg = fake()
    ctx = DrawingContext(dwg)
    ctx.regen_pause_s = 0
    from swdraw.drawing.dims import add_dimension
    add_dimension(ctx, SPEC["dimensions"][0])
    dd = dwg.dims[0]
    fresh = DrawingContext(dwg)                       # a new run: no handles in state
    fresh.state["dimspec:D"] = SPEC["dimensions"][0]
    monkeypatch.setattr(com, "display_dims", lambda v: [dd])
    assert ann._find_existing_dim(fresh, "D") is dd
