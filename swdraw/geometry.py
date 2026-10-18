"""Pure coordinate maths (no COM) so it can be unit-tested.

Units: model coordinates in millimetres, sheet coordinates in metres (SolidWorks' API unit).
"""
from __future__ import annotations

import math
from typing import Sequence, Tuple


def model_to_sheet(array_data: Sequence[float], x: float, y: float, z: float) -> Tuple[float, float]:
    """Map a model point (mm) to sheet coordinates (m) using ``View.ModelToViewTransform.ArrayData``.

    ``ArrayData`` is a 16-value MathTransform: a 3x3 rotation (row-vector convention) in 0-8,
    translation in 9-11 and scale in 12::

        sheet_x = sc * (X*a0 + Y*a3 + Z*a6) + a9
        sheet_y = sc * (X*a1 + Y*a4 + Z*a7) + a10
    """
    a = list(array_data)
    X, Y, Z = x / 1000.0, y / 1000.0, z / 1000.0
    sc = a[12]
    sx = sc * (X * a[0] + Y * a[3] + Z * a[6]) + a[9]
    sy = sc * (X * a[1] + Y * a[4] + Z * a[7]) + a[10]
    return sx, sy


def sheet_to_sketch(xform: Sequence[float], sx: float, sy: float) -> Tuple[float, float, float]:
    """Sheet metres to a view's sketch space using ``View.GetXform`` (``[x, y, scale, ...]``).

    Sketch entities in a view (section lines, detail circles) live in this space:
    ``sketch = (sheet - view origin) / view scale``. Returns ``(x, y, scale)``.
    """
    xf = list(xform)
    return (sx - xf[0]) / xf[2], (sy - xf[1]) / xf[2], xf[2]


def up_is_positive(array_data: Sequence[float]) -> bool:
    """True when model +Y maps to sheet +Y (used to reject sections that came out upside down)."""
    return float(list(array_data)[4]) > 0


def revolved_volume(profile: Sequence[Tuple[float, float]]) -> float:
    """Volume of a closed (radius, y) profile revolved about the y axis (mm in, mm³ out)."""
    pts = list(profile)
    total = sum((y2 - y1) * (r1 * r1 + r1 * r2 + r2 * r2) for (r1, y1), (r2, y2) in zip(pts, pts[1:] + pts[:1]))
    return abs(math.pi * total / 3.0)


def revolved_area(profile: Sequence[Tuple[float, float]]) -> float:
    """Surface area of the same solid (mm²): a frustum per profile edge; edges on the axis add nothing."""
    pts = list(profile)
    return sum(math.pi * (r1 + r2) * math.hypot(r2 - r1, y2 - y1)
               for (r1, y1), (r2, y2) in zip(pts, pts[1:] + pts[:1]))


def mm(m: float) -> float:
    return m * 1000.0


def m(mm_value: float) -> float:
    return mm_value / 1000.0
