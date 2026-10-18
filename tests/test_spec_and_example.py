"""The example spec is valid and its pick points really lie on the part it describes."""
import math
import os
import sys


from swdraw.config import load_file
from swdraw.drawing import validate_spec
from swdraw.drawing.context import Pick

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "examples", "flanged_bush")
sys.path.insert(0, EX)
SPEC = load_file(os.path.join(EX, "bush.drawing.yaml"))
PARAMS = load_file(os.path.join(EX, "bush.params.yaml"))


def profile():
    import importlib.util
    spec = importlib.util.spec_from_file_location("make_part", os.path.join(EX, "make_part.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("swdraw", __import__("swdraw"))
    spec.loader.exec_module(mod)
    return mod.profile(PARAMS)


def on_profile(r, y, pts, tol=1e-6):
    for (r1, y1), (r2, y2) in zip(pts, pts[1:]):
        dx, dy = r2 - r1, y2 - y1
        L2 = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((r - r1) * dx + (y - y1) * dy) / L2))
        if math.hypot(r1 + t * dx - r, y1 + t * dy - y) < tol:
            return True
    return False


def test_example_spec_is_valid():
    assert validate_spec(SPEC) == []


def test_profile_is_closed():
    pts = profile()
    assert pts[0] == pts[-1]


def test_every_pick_is_on_the_section_outline():
    pts = profile()
    picks = []
    for d in SPEC["dimensions"]:
        picks += d["pick"]
        for alt in d.get("alternatives", []):
            picks += alt
    picks += [d["edge"] for d in SPEC["gdt"]["datums"] if "edge" in d]
    picks += [f["edge"] for f in SPEC["gdt"]["frames"]]
    picks += [n["edge"] for n in SPEC["leader_notes"]]
    for p in map(Pick.parse, picks):
        assert p.x == 0, "section C is the plane x = 0"
        assert on_profile(abs(p.z), p.y, pts), f"pick {p.xyz()} is not on the part outline"


def test_expected_values_match_parameters():
    want = {"D_FLANGE": PARAMS["flange_d"], "D_BODY": PARAMS["body_d"], "D_BORE": PARAMS["bore_d"],
            "L_OVERALL": PARAMS["length"], "T_FLANGE": PARAMS["flange_t"]}
    got = {d["id"]: d["expect"] for d in SPEC["dimensions"]}
    assert got == want


def test_validate_catches_problems():
    bad = {"dimensions": [{"id": "A", "view": "C", "pick": [[0, 0]], "text_at": [0, 0, 0],
                           "tolerance": {"type": "plusminus"}},
                          {"id": "A", "view": "C", "pick": [[0, 0, 0]], "text_at": [0, 0, 0], "expect": 1}],
           "gdt": {"datums": [{"label": "A", "view": "C", "on_dim": "NOPE"}]},
           "sections": [{"id": "C", "line": [[0, 0, 0], [0, 1, 0]], "at": [0, 0]}]}
    probs = " | ".join(validate_spec(bad))
    for frag in ("expected a model point", "no 'expect'", "unknown tolerance type", "duplicate id",
                 "not a dimension id", "missing 'from_views'"):
        assert frag in probs, frag
