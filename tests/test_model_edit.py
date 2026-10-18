"""Part editing against a fake part: spec validation, units, globals, equations, dimensions,
configurations, the design table, the self-check, revert, backup and save, inspect, CLI and MCP."""
import importlib.util
import json
import math
import os
import sys

import pytest
from fakes import (DIM_ANGULAR, FakeDesignTable, FakeFeature, FakeModelDim, FakeModelDisplayDim, FakeModelPart)

from swdraw import cli, com, runner
from swdraw.config import load_file
from swdraw.geometry import revolved_area, revolved_volume
from swdraw.model import backup_path, edit, inspect, validate_edit_spec
from swdraw.model import part as P
from swdraw.model.spec import ANGULAR, INTEGER, LINEAR, check_expect, to_system

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "examples", "flanged_bush")
PARAMS = load_file(os.path.join(EX, "bush.params.yaml"))
EDIT = load_file(os.path.join(EX, "bush.edit.yaml"))


def make_part_module():
    spec = importlib.util.spec_from_file_location("make_part", os.path.join(EX, "make_part.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("swdraw", __import__("swdraw"))
    spec.loader.exec_module(mod)
    return mod


MP = make_part_module()


def bush_values(part):
    """The parameters the fake part currently describes, read back from its dimensions."""
    return {"bore_d": 2 * part.mm("bore_r@Profile"), "flange_d": 2 * part.mm("flange_r@Profile"),
            "body_d": 2 * part.mm("body_r@Profile"), "flange_t": part.mm("flange_t@Profile"),
            "length": part.mm("length@Profile"), "chamfer": part.mm("chamfer@Profile")}


def bush_model(part):
    q = bush_values(part)
    pts = MP.profile(q)
    r = max(q["flange_d"], q["body_d"]) / 2
    return {"volume_mm3": revolved_volume(pts), "surface_area_mm2": revolved_area(pts),
            "bbox": ((-r, 0, -r), (r, q["length"], r))}


def bush_errors(part):
    q = bush_values(part)
    return {"Revolve1": (1, False)} if q["bore_d"] / 2 + q["chamfer"] >= q["body_d"] / 2 else {}


def bush(tmp_path=None, params=PARAMS):
    """The part make_part.py builds: the Profile sketch with the planned dimensions, under Revolve1,
    with make_part's global variables and equations."""
    path = ""
    if tmp_path is not None:
        path = str(tmp_path / "ACME1-MEC-2101.SLDPRT")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("original")
    part = FakeModelPart(path=path, model=bush_model, errors=bush_errors, equations=MP.equations(params))
    q = dict(params)
    start = {"bore_r": q["bore_d"] / 2, "body_r": q["body_d"] / 2, "flange_r": q["flange_d"] / 2,
             "flange_t": q["flange_t"], "length": q["length"], "chamfer": q["chamfer"]}
    dims = [FakeModelDim(d["name"], start[d["name"]] / 1000.0) for d in MP.dimension_plan(params)
            if d["name"] in start]
    dims.append(FakeModelDim("chamfer_angle", math.radians(45), kind=DIM_ANGULAR))
    rev = part.add_feature(FakeFeature("Revolve1", "Revolution", [FakeModelDim("D1", 2 * math.pi, kind=DIM_ANGULAR)]))
    part.add_feature(FakeFeature("Profile", "ProfileFeature", dims), parent=rev)
    rev.display += [FakeModelDisplayDim(d) for d in dims]     # SolidWorks lists the absorbed sketch's too
    part.ForceRebuild3(False)
    part.dirty = False
    return part


# --------------------------------------------------------------------------- spec and units
def test_example_edit_spec_is_valid():
    assert validate_edit_spec(EDIT) == []


def test_example_expect_matches_the_geometry():
    q = dict(PARAMS, flange_d=float(str(EDIT["globals"]["flange_d"]).rstrip("m")))
    pts = MP.profile(q)
    measured = {"volume_mm3": revolved_volume(pts), "surface_area_mm2": revolved_area(pts),
                "bbox_mm": {"size": [q["flange_d"], q["length"], q["flange_d"]]}}
    assert all(c["ok"] for c in check_expect(EDIT["expect"], measured)), check_expect(EDIT["expect"], measured)


def test_example_names_exist_in_make_part():
    globals_ = {MP.equations(PARAMS)[i].split('"')[1] for i in range(3)}
    assert set(EDIT["globals"]) <= globals_
    planned = {d["name"] for d in MP.dimension_plan(PARAMS)}
    driven = {t.split('"')[1].split("@")[0] for t in MP.equations(PARAMS) if "@" in t.split("=")[0]}
    assert driven <= planned and {"length", "flange_t", "chamfer"} <= planned - driven


def test_validate_catches_problems():
    bad = {"dimension": {}, "part": "x.SLDDRW", "apply_to": "some",
           "dimensions": {"D1": 3, "D2@Sketch1": "3 furlongs", "D3@Sketch1": True},
           "globals": {'"g"': 1, "h": None}, "design_table": {"set": {}},
           "expect": {"volume_mm3": {"value": 1}, "bbox_mm": {"value": [1, 2], "tol": 0.1},
                      "mass_kg": {"value": 1, "tol": 1}, "surface_area_mm2": 5}}
    probs = " | ".join(validate_edit_spec(bad))
    for frag in ("unknown key 'dimension'", "not a .SLDPRT", "apply_to", "use the full name",
                 "unknown unit 'furlongs'", "D3@Sketch1: not a number", "without quotes",
                 "h: needs a number", "needs 'row'", "needs 'tol'", "three sizes", "unknown check",
                 "{value: ..., tol: ...}"):
        assert frag in probs, frag


def test_units():
    assert to_system(42, LINEAR) == pytest.approx(0.042)
    assert to_system("1.5in", LINEAR) == pytest.approx(0.0381)
    assert to_system("30deg", ANGULAR) == pytest.approx(math.pi / 6)
    assert to_system(30, ANGULAR) == pytest.approx(math.pi / 6)
    assert to_system(6, INTEGER) == 6
    with pytest.raises(ValueError):
        to_system("30deg", LINEAR)
    with pytest.raises(ValueError):
        to_system("6mm", INTEGER)


def test_check_expect_tolerances():
    res = check_expect({"volume_mm3": {"value": 100, "tol_pct": 1}, "mass_g": {"value": 5, "tol": 0.1}},
                       {"volume_mm3": 100.9, "mass_g": None})
    assert [r["ok"] for r in res] == [True, False]


# --------------------------------------------------------------------------- edit
def test_global_change_rebuilds_and_passes(tmp_path):
    part = bush(tmp_path)
    rep = edit(EDIT, doc=part)
    assert rep["ok"] and rep["check"]["ok"], rep["check"]
    g = rep["changes"][0]
    assert (g["kind"], g["name"], g["old"], g["new"]) == ("global", "flange_d", "40mm", "42mm")
    assert part.mm("flange_r@Profile") == pytest.approx(21.0)        # the equation followed the global
    assert rep["measured"]["before"]["volume_mm3"] == pytest.approx(11067.7, abs=0.01)
    assert rep["measured"]["after"]["bbox_mm"]["size"] == pytest.approx([42, 25, 42])
    assert rep["save"] == {"saved": False, "requested": False} and part.saves == 0
    assert open(part.path, encoding="utf-8").read() == "original"


def test_dimension_change_reads_back_in_mm_and_degrees():
    part = bush()
    rep = edit({"dimensions": {"flange_t@Profile": 6, "chamfer_angle@Profile": "40deg"}}, doc=part)
    assert rep["ok"], rep
    t, a = rep["changes"]
    assert (t["old"], t["new"], t["read_back"], t["unit"]) == (5.0, 6.0, 6.0, "mm")
    assert a["read_back"] == pytest.approx(40.0) and a["unit"] == "deg"
    assert part.dim("flange_t@Profile").set_calls == [1]                  # this configuration


def test_apply_to_all_configurations():
    part = bush()
    edit({"dimensions": {"length@Profile": 30}, "apply_to": "all"}, doc=part)
    assert part.dim("length@Profile").set_calls == [2]


def test_dimension_driven_by_equation_is_refused_and_not_saved(tmp_path):
    part = bush(tmp_path)
    rep = edit({"dimensions": {"flange_r@Profile": 21}, "save": True}, doc=part)
    assert not rep["ok"]
    assert "driven by equation" in rep["changes"][0]["error"]
    assert rep["check"]["failed_changes"] == ["flange_r@Profile"]
    assert rep["save"]["saved"] is False and "checks failed" in rep["save"]["error"] and part.saves == 0
    assert part.mm("flange_r@Profile") == pytest.approx(20.0)


def test_value_overridden_after_rebuild_is_caught():
    part = bush()
    part.overrides["length@Profile"] = 25.0               # e.g. a design table puts it back
    rep = edit({"dimensions": {"length@Profile": 30}}, doc=part)
    assert not rep["ok"] and "after the rebuild" in rep["changes"][0]["error"]


def test_unknown_names_are_reported():
    rep = edit({"dimensions": {"nope@Profile": 1}, "globals": {"nope": 1}, "equations": {"x@Profile": "1"}}, doc=bush())
    errors = {c["name"]: c["error"] for c in rep["changes"]}
    assert "no dimension" in errors["nope@Profile"] and "no global variable" in errors["nope"]
    assert "no equation" in errors["x@Profile"] and rep["check"]["ok"] is False


def test_read_only_and_refused_dimensions():
    part = bush()
    part.dim("D1@Revolve1").ReadOnly = True
    part.dim("length@Profile").refuse = True
    rep = edit({"dimensions": {"D1@Revolve1": 180, "length@Profile": 30}}, doc=part)
    errors = [c["error"] for c in rep["changes"]]
    assert "read-only" in errors[0] and "refused" in errors[1]


def test_bad_expression_is_not_accepted():
    rep = edit({"equations": {"bore_r@Profile": '"nonexistent" / 2'}}, doc=bush())
    assert "did not accept" in rep["changes"][0]["error"]


def test_rebuild_error_fails_and_revert_restores(tmp_path):
    part = bush(tmp_path)
    spec = {"globals": {"bore_d": "26mm"}, "on_failure": "revert", "save": True}
    rep = edit(spec, doc=part)
    assert not rep["ok"] and rep["check"]["rebuild_errors"] == ["Revolve1"]
    assert rep["reverted"] and rep["revert_problems"] == []
    assert '"bore_d" = 16mm' in part.eq.texts and part.mm("bore_r@Profile") == pytest.approx(8.0)
    assert rep["measured"]["after_revert"]["volume_mm3"] == pytest.approx(rep["measured"]["before"]["volume_mm3"])
    assert part.saves == 0 and not [f for f in os.listdir(tmp_path) if ".bak" in f]     # no save, no backup


def test_failed_expect_keeps_changes_by_default():
    rep = edit({"globals": {"flange_d": "42mm"}, "expect": {"volume_mm3": {"value": 1, "tol": 1}}}, doc=bush())
    assert rep["check"]["failed_expect"] == ["volume_mm3"] and "reverted" not in rep
    assert "still in the open part" in rep["check"]["next"]


def test_mass_without_material_warns():
    rep = edit({"expect": {"mass_g": {"value": 11.07, "tol": 0.01}}}, doc=bush())
    assert rep["ok"] and any("default density" in w for w in rep["warnings"])


def test_invalid_spec_is_refused_before_touching_the_part():
    part = bush()
    rep = edit({"dimensions": {"D1": 3}}, doc=part)
    assert rep["ok"] is False and rep["problems"] and part.rebuilds == 1


# --------------------------------------------------------------------------- saving
def test_save_backs_up_first(tmp_path):
    part = bush(tmp_path)
    rep = edit(dict(EDIT, save=True), doc=part)
    assert rep["ok"] and rep["check"]["saved"], rep["save"]
    bak = rep["check"]["backup"]
    assert os.path.basename(bak) == "ACME1-MEC-2101.bak.SLDPRT"
    assert open(bak, encoding="utf-8").read() == "original"
    assert open(part.path, encoding="utf-8").read() == "original saved"


def test_save_override_and_backup_dir(tmp_path, monkeypatch):
    part = bush(tmp_path)
    monkeypatch.setenv("SWDRAW_BACKUP_DIR", str(tmp_path / "baks"))
    rep = edit(EDIT, doc=part, save=True)                   # the caller overrides save: false
    assert rep["check"]["saved"] and rep["check"]["backup"].startswith(str(tmp_path / "baks"))
    rep = edit(dict(EDIT, save=True), doc=part, save=False)
    assert rep["save"]["requested"] is False and part.saves == 1


def test_backup_never_overwrites(tmp_path):
    import datetime as dt
    p = tmp_path / "A.SLDPRT"
    assert backup_path(str(p)) == str(tmp_path / "A.bak.SLDPRT")
    (tmp_path / "A.bak.SLDPRT").write_text("old")
    got = backup_path(str(p), now=dt.datetime(2026, 10, 18, 9, 30, 0))
    assert got == str(tmp_path / "A.bak-20261018-093000.SLDPRT")


@pytest.mark.parametrize("setup,needle", [
    (lambda part: setattr(part, "dirty", True), "unsaved changes"),
    (lambda part: setattr(part, "read_only", True), "read-only"),
    (lambda part: setattr(part, "path", ""), "never been saved"),
])
def test_save_refused(tmp_path, setup, needle):
    part = bush(tmp_path)
    setup(part)
    rep = edit(dict(EDIT, save=True), doc=part)
    assert not rep["check"]["saved"] and needle in rep["save"]["error"] and part.saves == 0
    assert rep["ok"] is False


def test_unsaved_changes_can_be_allowed(tmp_path):
    part = bush(tmp_path)
    part.dirty = True
    rep = edit(dict(EDIT, save=True, allow_unsaved_changes=True), doc=part)
    assert rep["check"]["saved"] and rep["warnings"]


# --------------------------------------------------------------------------- configurations, design table
def test_configuration_is_activated():
    part = bush()
    part.configs = ["Default", "Long"]
    rep = edit({"configuration": "Long"}, doc=part)
    assert rep["ok"] and part.active == "Long"
    assert rep["changes"][0] == {"kind": "configuration", "name": "Long", "old": "Default", "new": "Long"}
    rep = edit({"configuration": "Short"}, doc=part)
    assert "no such configuration" in rep["changes"][0]["error"]


def test_design_table_row_set_and_activated():
    part = bush()
    part.configs = ["Default", "Long"]
    part.design = FakeDesignTable(part, ["length@Profile"], [["Default", 25], ["Long", 40]])
    rep = edit({"design_table": {"row": "Long", "set": {"length@Profile": 45}}}, doc=part)
    assert rep["ok"], rep
    cell = rep["changes"][0]
    assert (cell["name"], cell["old"], cell["new"]) == ("Long/length@Profile", "40", 45)
    assert part.active == "Long" and part.mm("length@Profile") == pytest.approx(45.0)
    rep = edit({"design_table": {"row": "Long", "set": {"nope": 1}}}, doc=part)
    assert rep["changes"][0]["error"] == "no such column"


# --------------------------------------------------------------------------- lower-level helpers
def test_feature_errors_accepts_tuple_returns():
    class F:
        Name, next = "Cut1", None

        def GetErrorCode2(self, warn):
            return (7, True)

        def GetTypeName2(self):
            return "Cut"

        def GetNextFeature(self):
            return None

        def GetFirstSubFeature(self):
            return None

    class Doc:
        def FirstFeature(self):
            return F()

    assert P.feature_errors(Doc()) == [{"feature": "Cut1", "type": "Cut", "code": 7, "warning": True}]


def test_equation_falls_back_to_property_put(monkeypatch):
    part = bush()
    calls = []

    class OldMgr:                    # no SetEquationAndConfigurationOption (older SolidWorks)
        texts = part.eq.texts

        def Equation(self, i):
            return self.texts[i]

    def fake_put(obj, name, i, text):
        calls.append(name)
        obj.texts[i] = text
    monkeypatch.setattr(com, "put", fake_put)
    monkeypatch.setattr(P, "equation_mgr", lambda doc: OldMgr())
    assert P.set_equation(part, 0, '"flange_d" = 41mm') == "Equation" and calls == ["Equation"]


def test_equation_names_match_without_quotes_or_part_suffix():
    eqs = [{"lhs": "D1@Sketch1@ACME1-MEC-2101.Part", "global": False, "index": 0}]
    assert P.find_equation(eqs, "d1@sketch1") is eqs[0]
    assert P.split_equation('"flange_d" = 40mm') == ("flange_d", "40mm")
    assert P.split_equation("nonsense") == (None, None)


# --------------------------------------------------------------------------- inspect
def test_inspect_lists_everything_and_the_stub_round_trips():
    part = bush()
    rep = inspect(part)
    names = {d["name"]: d for d in rep["dimensions"]}
    assert len(names) == len(rep["dimensions"]) == 8 and not [n for n in names if n.endswith("@Revolve1") and n != "D1@Revolve1"]
    assert names["chamfer_angle@Profile"]["kind"] == "angular"
    assert names["flange_r@Profile"]["driven_by_equation"] and not names["length@Profile"]["driven_by_equation"]
    assert names["D1@Revolve1"]["unit"] == "deg" and names["D1@Revolve1"]["value"] == pytest.approx(360)
    assert [g["name"] for g in rep["globals"]] == ["flange_d", "body_d", "bore_d"]
    assert len(rep["equations"]) == 3 and rep["feature_errors"] == []
    assert rep["configurations"] == {"active": "Default", "names": ["Default"]}
    stub = rep["spec"]
    assert stub["globals"]["flange_d"] == "40mm" and "flange_r@Profile" not in stub["dimensions"]
    assert stub["save"] is False and validate_edit_spec(stub) == []
    again = edit(stub, doc=part)                          # current values in, nothing changes
    assert again["ok"], again["check"]
    assert again["measured"]["after"]["volume_mm3"] == pytest.approx(rep["measured"]["volume_mm3"])


# --------------------------------------------------------------------------- CLI and MCP
def run_cli(capsys, *argv):
    code = cli.main(list(argv))
    return code, runner.extract_result(capsys.readouterr().out)


def test_cli_model_validate(capsys):
    code, res = run_cli(capsys, "model", "validate", "--spec", os.path.join(EX, "bush.edit.yaml"))
    assert code == 0 and res == {"ok": True, "problems": []}


def test_cli_model_edit_and_inspect(capsys, monkeypatch, tmp_path):
    part = bush(tmp_path)
    monkeypatch.setattr(P, "open_part", lambda path=None: part)
    code, res = run_cli(capsys, "model", "edit", "--spec", os.path.join(EX, "bush.edit.yaml"))
    assert code == 0 and res["check"]["ok"] and not res["check"]["saved"]
    code, res = run_cli(capsys, "model", "edit", "--spec", os.path.join(EX, "bush.edit.yaml"), "--save")
    assert not res["check"]["saved"] and "unsaved changes" in res["save"]["error"]   # the first run's edit
    part = bush(tmp_path)
    code, res = run_cli(capsys, "model", "edit", "--spec", os.path.join(EX, "bush.edit.yaml"), "--save")
    assert res["check"]["saved"]
    code, res = run_cli(capsys, "model", "inspect", "--args", json.dumps({"out": str(tmp_path / "stub.edit.yaml")}))
    assert code == 0 and res["spec_file"] == str(tmp_path / "stub.edit.yaml")
    assert validate_edit_spec(load_file(res["spec_file"])) == []


def test_mcp_model_validate():
    pytest.importorskip("mcp")
    server = importlib.import_module("mcp_server.server")
    res = server.swdraw_model_validate(os.path.join(EX, "bush.edit.yaml"))
    assert res == {"ok": True, "problems": []}


def test_edit_template_is_valid():
    tpl = load_file(os.path.join(ROOT, "subskills", "part-editing", "edit_template.yaml"))
    assert validate_edit_spec(tpl) == []
