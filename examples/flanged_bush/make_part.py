"""Create the example part (revolve) and a drawing with a front and an isometric view.

    python examples/flanged_bush/make_part.py --args '{"out": "~/swdraw-example"}'

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


def profile(p):
    """Half-section (radius, y) in mm, closed, counter-clockwise from the bore at the bottom face."""
    rb, rf, ro, c = p["bore_d"] / 2, p["flange_d"] / 2, p["body_d"] / 2, p["chamfer"]
    return [(rb, 0.0), (rf, 0.0), (rf, p["flange_t"]), (ro, p["flange_t"]), (ro, p["length"]),
            (rb + c, p["length"]), (rb, p["length"] - c), (rb, 0.0)]


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
    skm.CreateCenterLine(0, 0, 0, 0, p["length"] / 1000.0, 0)
    pts = profile(p)
    for (r1, y1), (r2, y2) in zip(pts, pts[1:]):
        skm.CreateLine(r1 / 1000.0, y1 / 1000.0, 0, r2 / 1000.0, y2 / 1000.0, 0)
    skm.AddToDB = False
    skm.InsertSketch(True)
    part.ClearSelection2(True)
    sketch = part.FeatureByPositionReverse(0)       # the sketch just closed, whatever the template named it
    if sketch is None or not sketch.Select2(False, 0):
        raise SystemExit("Could not select the profile sketch.")
    feat = part.FeatureManager.FeatureRevolve2(True, True, False, False, False, False, 0, 0, 2 * math.pi, 0,
                                               False, False, 0, 0, 0, 0, 0, True, True, True)
    if feat is None:
        raise SystemExit("Revolve failed; check the sketch is closed and has one centreline.")
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
