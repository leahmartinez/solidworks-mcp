"""Edit specs: load, validate and convert values. Pure: runs without SolidWorks.

An edit spec (``*.edit.yaml``) names a part, the values to change and what the part should
measure afterwards::

    part: C:/work/ACME1-MEC-2101.SLDPRT     # optional; the active part otherwise
    configuration: Default                  # activate before changing anything
    apply_to: this                          # dimensions: this configuration (default) or all
    design_table: {row: Large, set: {D1@Sketch1: 42}}
    globals: {flange_d: 42mm}               # global variables, written as given
    equations: {"bore_r@Profile": '"bore_d" / 2'}   # right-hand side, by left-hand side
    dimensions: {length@Profile: 30}        # mm, degrees or a count; or "1.5in", "30deg"
    expect:
      volume_mm3: {value: 11711.7, tol: 1}
      mass_g: {value: 104.2, tol_pct: 0.5}
      surface_area_mm2: {value: 4000, tol: 5}
      bbox_mm: {value: [42, 25, 42], tol: 0.01}   # sizes along model X, Y, Z
    save: false                             # true: back up the file, then save
    backup_dir: ~/swdraw-backups            # default: next to the part (<name>.bak.SLDPRT)
    on_failure: keep                        # keep (look at it in SolidWorks) or revert
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from ..config import load_file

KEYS = {"part", "configuration", "apply_to", "design_table", "globals", "equations", "dimensions",
        "expect", "save", "backup_dir", "on_failure", "allow_unsaved_changes"}
EXPECT_KEYS = {"volume_mm3", "mass_g", "surface_area_mm2", "bbox_mm"}
CHANGE_KEYS = ("configuration", "design_table", "globals", "equations", "dimensions")

# value kinds, from swDimensionParamType_e
LINEAR, ANGULAR, INTEGER = "linear", "angular", "integer"
_TO_SI = {"mm": 0.001, "cm": 0.01, "m": 1.0, "in": 0.0254, "ft": 0.3048,
          "deg": math.pi / 180.0, "rad": 1.0}
_UNIT_KIND = {"mm": LINEAR, "cm": LINEAR, "m": LINEAR, "in": LINEAR, "ft": LINEAR,
              "deg": ANGULAR, "rad": ANGULAR}
_NUM_UNIT = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([a-zA-Z]*)\s*$")
_DEFAULT_UNIT = {LINEAR: "mm", ANGULAR: "deg"}


def load_spec(path: str) -> Dict[str, Any]:
    return load_file(path)


def parse_quantity(value) -> Tuple[float, Optional[str]]:
    """``42`` -> (42.0, None); ``"1.5in"`` -> (1.5, "in"). Raises ValueError otherwise."""
    if isinstance(value, bool):
        raise ValueError(f"not a number: {value!r}")
    if isinstance(value, (int, float)):
        return float(value), None
    m = _NUM_UNIT.match(str(value))
    if not m:
        raise ValueError(f"not a number with an optional unit: {value!r}")
    unit = m.group(2).lower() or None
    if unit is not None and unit not in _TO_SI:
        raise ValueError(f"unknown unit {m.group(2)!r} in {value!r} (use {', '.join(_TO_SI)})")
    return float(m.group(1)), unit


def to_system(value, kind: str) -> float:
    """A spec value to SolidWorks system units (m, rad, or a plain count)."""
    num, unit = parse_quantity(value)
    if kind == INTEGER:
        if unit:
            raise ValueError(f"{value!r}: a count takes no unit")
        return num
    unit = unit or _DEFAULT_UNIT[kind]
    if _UNIT_KIND[unit] != kind:
        raise ValueError(f"{value!r} is {_UNIT_KIND[unit]}, but this dimension is {kind}")
    return num * _TO_SI[unit]


def from_system(value: float, kind: str) -> float:
    """System units back to what a spec uses: mm, degrees, or the count."""
    if kind == INTEGER:
        return value
    return value / _TO_SI[_DEFAULT_UNIT[kind]]


def unit_of(kind: str) -> str:
    return _DEFAULT_UNIT.get(kind, "")


def tolerance(entry: Dict[str, Any], expected: float) -> float:
    """Absolute tolerance from ``tol`` or ``tol_pct``."""
    if "tol" in entry:
        return abs(float(entry["tol"]))
    return abs(float(expected)) * abs(float(entry["tol_pct"])) / 100.0


def validate_edit_spec(spec: Dict[str, Any]) -> List[str]:
    """Return a list of problems (empty = OK)."""
    probs: List[str] = []
    if not isinstance(spec, dict):
        return ["the spec must be a mapping"]
    for k in spec:
        if k not in KEYS:
            probs.append(f"unknown key {k!r} (valid: {', '.join(sorted(KEYS))})")
    part = spec.get("part")
    if part is not None and not str(part).lower().endswith(".sldprt"):
        probs.append(f"part: {part!r} is not a .SLDPRT file")
    if spec.get("apply_to", "this") not in ("this", "all"):
        probs.append("apply_to: use 'this' (the active configuration) or 'all'")
    if spec.get("on_failure", "keep") not in ("keep", "revert"):
        probs.append("on_failure: use 'keep' or 'revert'")
    if spec.get("configuration") is not None and not isinstance(spec["configuration"], str):
        probs.append("configuration: give the configuration name")

    dims = spec.get("dimensions") or {}
    if not isinstance(dims, dict):
        probs.append("dimensions: expected a mapping of full name to value")
        dims = {}
    for name, value in dims.items():
        if "@" not in str(name):
            probs.append(f"dimensions.{name}: use the full name, e.g. D1@Sketch1")
        try:
            parse_quantity(value)
        except ValueError as exc:
            probs.append(f"dimensions.{name}: {exc}")

    for key in ("globals", "equations"):
        block = spec.get(key) or {}
        if not isinstance(block, dict):
            probs.append(f"{key}: expected a mapping of name to value")
            continue
        for name, value in block.items():
            if '"' in str(name):
                probs.append(f"{key}.{name}: give the name without quotes")
            if value is None or isinstance(value, (bool, list, dict)) or str(value).strip() == "":
                probs.append(f"{key}.{name}: needs a number or an expression")

    dt = spec.get("design_table")
    if dt is not None:
        if not isinstance(dt, dict) or not dt.get("row"):
            probs.append("design_table: needs 'row' (the configuration name in the table)")
        elif not isinstance(dt.get("set") or {}, dict):
            probs.append("design_table.set: expected a mapping of column header to value")
        if isinstance(dt, dict) and spec.get("configuration") and spec["configuration"] != dt.get("row"):
            probs.append("design_table.row and configuration differ; the row is activated, so drop one")

    exp = spec.get("expect") or {}
    if not isinstance(exp, dict):
        probs.append("expect: expected a mapping")
        exp = {}
    for k, e in exp.items():
        w = f"expect.{k}"
        if k not in EXPECT_KEYS:
            probs.append(f"{w}: unknown check (valid: {', '.join(sorted(EXPECT_KEYS))})")
            continue
        if not isinstance(e, dict) or "value" not in e:
            probs.append(f"{w}: use {{value: ..., tol: ...}}")
            continue
        if "tol" not in e and "tol_pct" not in e:
            probs.append(f"{w}: needs 'tol' (absolute) or 'tol_pct'")
        v = e["value"]
        if k == "bbox_mm":
            if not (isinstance(v, (list, tuple)) and len(v) == 3 and all(_is_num(x) for x in v)):
                probs.append(f"{w}: value is the three sizes [x, y, z] in mm")
        elif not _is_num(v):
            probs.append(f"{w}: value must be a number")
        for t in ("tol", "tol_pct"):
            if t in e and not _is_num(e[t]):
                probs.append(f"{w}: {t} must be a number")
    return probs


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_expect(expect: Dict[str, Any], measured: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compare ``measured`` (from ``part.measure``) with the spec's ``expect`` block."""
    out = []
    for key, e in (expect or {}).items():
        want = e["value"]
        if key == "bbox_mm":
            got = (measured.get("bbox_mm") or {}).get("size")
            tols = [tolerance(e, w) for w in want]
            ok = got is not None and all(abs(g - w) <= t for g, w, t in zip(got, want, tols))
            out.append({"check": key, "expect": list(want), "tol": tols, "actual": got, "ok": ok})
            continue
        got = measured.get(key)
        tol = tolerance(e, want)
        ok = got is not None and abs(float(got) - float(want)) <= tol
        out.append({"check": key, "expect": want, "tol": tol, "actual": got, "ok": ok})
    return out
