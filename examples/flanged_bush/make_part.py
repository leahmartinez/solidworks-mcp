"""Create the example part (revolve) and a drawing with a front and an isometric view.

    python examples/flanged_bush/make_part.py --args '{"out": "~/swdraw-example"}'

The profile sketch is renamed ``Profile`` and fully defined: horizontal and vertical relations,
named dimensions (``length@Profile``, ``flange_t@Profile``, ``chamfer@Profile`` ...) and global
variables ``flange_d``, ``body_d`` and ``bore_d`` that drive the radii through equations. That is
what ``bush.edit.yaml`` changes.

Optional args: ``out`` (folder), ``part_template``, ``drawing_template`` (default: the templates set
in Tools > Options > Default Templates, or SWDRAW_PART_TEMPLATE / SWDRAW_DRAWING_TEMPLATE).
Then make the drawing active and run::

    python -m swdraw build --spec examples/flanged_bush/bush.drawing.yaml
"""
from __future__ import annotations

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import swdraw as sw                       # noqa: E402
from swdraw.config import load_file       # noqa: E402

PREF_TEMPLATE_PART, PREF_TEMPLATE_DRAWING = 8, 10      # swUserPreferenceStringValue_e
PAPER_USER_DEFINED = 12                                # swDwgPaperSizes_e
PREF_INPUT_DIM_VALUE = 10                              # swUserPreferenceToggle_e.swInputDimValOnCreate
SKETCH = "Profile"
HORIZONTAL, VERTICAL = (0, 2, 4), (1, 3, 6)             # profile segments, see profile()


def profile(p):
    """Half-section (radius, y) in mm, closed, counter-clockwise from the bore at the bottom face."""
    rb, rf, ro, c = p["bore_d"] / 2, p["flange_d"] / 2, p["body_d"] / 2, p["chamfer"]
    return [(rb, 0.0), (rf, 0.0), (rf, p["flange_t"]), (ro, p["flange_t"]), (ro, p["length"]),
            (rb + c, p["length"]), (rb, p["length"] - c), (rb, 0.0)]


def dimension_plan(p):
    """Named sketch dimensions that fully define the profile with the relations below.

    ``select`` lists profile segment indexes (``"axis"`` is the centreline); ``at`` is the text
    position in sketch mm. Radii are measured from the axis; the global variables set them.
    """
    rb, rf, ro, c, ft, L = p["bore_d"] / 2, p["flange_d"] / 2, p["body_d"] / 2, p["chamfer"], p["flange_t"], p["length"]
    return [
        {"name": "bore_r", "select": ["axis", 6], "at": (rb / 2, -4)},
        {"name": "body_r", "select": ["axis", 3], "at": (ro / 2, -8)},
        {"name": "flange_r", "select": ["axis", 1], "at": (rf / 2, -12)},
        {"name": "flange_t", "select": [1], "at": (rf + 5, ft / 2)},
        {"name": "length", "select": [0, 4], "at": (ro + 10, L / 2)},
        {"name": "chamfer", "select": [5], "at": (rb - 4, L - c / 2), "vertical": True},
        {"name": "chamfer_angle", "select": [5, 6], "at": (rb + 0.2, L + 3)},
    ]


def equations(p):
    """Global variables for the diameters, and the equations that turn them into sketch radii."""
    out = [f'"{k}" = {p[k]:g}mm' for k in ("flange_d", "body_d", "bore_d")]
    out += [f'"{r}@{SKETCH}" = "{d}" / 2' for r, d in (("flange_r", "flange_d"), ("body_r", "body_d"),
                                                       ("bore_r", "bore_d"))]
    return out


def define_profile(part, axis, segs, p):
    """Relations and named dimensions on the open sketch, so an edit spec can change the part."""
    app = sw.app()

    def select(items, append=False):
        for i, item in enumerate(items):
            ok = (axis if item == "axis" else segs[item]).Select4(append or i > 0, sw.nothing())
            if not ok:
                return False
        return True

    for idx, rel in [(i, "sgHORIZONTAL2D") for i in HORIZONTAL] + [(i, "sgVERTICAL2D") for i in VERTICAL]:
        part.ClearSelection2(True)
        if select([idx]):
            part.SketchAddConstraints(rel)
    # the axis is the vertical line through the origin; the bottom face lies on the origin too
    for item, rel in (("axis", "sgVERTICAL2D"), ("axis", "sgCOINCIDENT"), (0, "sgCOINCIDENT")):
        part.ClearSelection2(True)
        select([item])
        if rel == "sgCOINCIDENT":
            part.Extension.SelectByID2("Point1@Origin", "EXTSKETCHPOINT", 0, 0, 0, True, 0, sw.nothing(), 0)
        part.SketchAddConstraints(rel)

    made, keep = [], app.GetUserPreferenceToggle(PREF_INPUT_DIM_VALUE)
    app.SetUserPreferenceToggle(PREF_INPUT_DIM_VALUE, False)      # no Modify dialog per dimension
    try:
        for d in dimension_plan(p):
            part.ClearSelection2(True)
            if not select(d["select"]):
                continue
            x, y = d["at"][0] / 1000.0, d["at"][1] / 1000.0
            dd = part.AddVerticalDimension2(x, y, 0) if d.get("vertical") else part.AddDimension2(x, y, 0)
            if dd is not None and sw.com.set_prop(dd.GetDimension2(0), "Name", d["name"]):
                made.append(d["name"])
    finally:
        app.SetUserPreferenceToggle(PREF_INPUT_DIM_VALUE, keep)
        part.ClearSelection2(True)
    return made


def template(kind: str, a) -> str:
    env = os.environ.get(f"SWDRAW_{kind.upper()}_TEMPLATE")
    path = a.get(f"{kind}_template") or env
    if not path:
        path = sw.app().GetUserPreferenceStringValue(PREF_TEMPLATE_PART if kind == "part" else PREF_TEMPLATE_DRAWING)
    if not path or not os.path.isfile(path):
        raise SystemExit(f"No {kind} template found; pass {kind}_template or set SWDRAW_{kind.upper()}_TEMPLATE")
    return path


def main():
    a = sw.args()
    p = load_file(os.path.join(HERE, "bush.params.yaml"))
    out = os.path.expanduser(a.get("out", "~/swdraw-example"))
    os.makedirs(out, exist_ok=True)
    app = sw.app()
    rep = {}

    part = app.NewDocument(template("part", a), 0, 0, 0)
    part.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, sw.nothing(), 0)
    skm = part.SketchManager
    skm.InsertSketch(True)
    skm.AddToDB = True
    axis = skm.CreateCenterLine(0, 0, 0, 0, p["length"] / 1000.0, 0)
    pts = profile(p)
    segs = [skm.CreateLine(r1 / 1000.0, y1 / 1000.0, 0, r2 / 1000.0, y2 / 1000.0, 0)
            for (r1, y1), (r2, y2) in zip(pts, pts[1:])]
    skm.AddToDB = False
    rep["dimensions"] = define_profile(part, axis, segs, p)
    skm.InsertSketch(True)
    part.ClearSelection2(True)
    sketch = part.FeatureByPositionReverse(0)       # the sketch just closed, whatever the template named it
    if sketch is None:
        raise SystemExit("Could not find the profile sketch.")
    sw.com.set_prop(sketch, "Name", SKETCH)
    if not sketch.Select2(False, 0):
        raise SystemExit("Could not select the profile sketch.")
    feat = part.FeatureManager.FeatureRevolve2(True, True, False, False, False, False, 0, 0, 2 * math.pi, 0,
                                               False, False, 0, 0, 0, 0, 0, True, True, True)
    if feat is None:
        raise SystemExit("Revolve failed; check the sketch is closed and has one centreline.")
    mgr = sw.call(part, "GetEquationMgr")       # a dispatch object, not a method, under late binding
    rep["equations"] = [t for t in equations(p) if mgr.Add2(-1, t, True) >= 0]
    part.ForceRebuild3(False)
    cpm = part.Extension.CustomPropertyManager("")
    for k, v in {"PartNo": p["part_no"], "Description": p["description"], "Material": p["material"]}.items():
        cpm.Add3(k, 30, v, 2)
    part_path = os.path.join(out, p["part_no"] + ".SLDPRT")
    rep["part_save_error"] = int(part.SaveAs3(part_path, 0, 1) or 0)
    rep["part"] = part_path
    if rep["part_save_error"] or not os.path.isfile(part_path):
        rep["error"] = "part Save As failed; not creating the drawing"
        sw.result(rep, name="make_part")
        raise SystemExit(1)

    dwg = app.NewDocument(template("drawing", a), PAPER_USER_DEFINED, 0.42, 0.297)
    front = dwg.CreateDrawViewFromModelView3(part_path, "*Front", 0.09, 0.20, 0)
    iso = dwg.CreateDrawViewFromModelView3(part_path, "*Isometric", 0.33, 0.14, 0)
    rep["views"] = [str(sw.call(v, "GetName2")) for v in (front, iso) if v is not None]
    drw_path = os.path.join(out, p["part_no"] + ".SLDDRW")
    rep["drawing_save_error"] = int(dwg.SaveAs3(drw_path, 0, 1) or 0)
    rep["drawing"] = drw_path
    rep["next"] = "With the drawing active: python -m swdraw build --spec examples/flanged_bush/bush.drawing.yaml"
    sw.result(rep, name="make_part")


if __name__ == "__main__":
    main()
