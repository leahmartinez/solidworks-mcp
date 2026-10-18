"""Shared state and low-level helpers for one drawing-building session."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .. import com
from ..config import HouseStyle
from ..geometry import model_to_sheet, sheet_to_sketch
from ..runner import log

# swSelectType_e values that count as "real geometry" when picking
SEL_EDGE, SEL_VERTEX, SEL_SILHOUETTE = 1, 3, 46
GOOD_TYPES = (SEL_EDGE, SEL_VERTEX, SEL_SILHOUETTE)
KINDS = ("EDGE", "SILHOUETTE", "VERTEX")
NUDGE_M = 0.0002   # 0.2 mm on the sheet


@dataclass
class Pick:
    """A pick point in MODEL millimetres plus what to select there."""
    x: float
    y: float
    z: float
    kind: str = "EDGE"          # EDGE | VERTEX | SILHOUETTE

    @classmethod
    def parse(cls, value) -> "Pick":
        """``[x, y, z]`` (edge), ``[x, y, z, "VERTEX"]`` or ``{at: [x, y, z], kind: vertex}``."""
        if isinstance(value, Pick):
            return value
        if isinstance(value, dict):
            at = value.get("at") or [value["x"], value["y"], value["z"]]
            return cls(float(at[0]), float(at[1]), float(at[2]), str(value.get("kind", "EDGE")).upper())
        seq = list(value)
        kind = str(seq[3]).upper() if len(seq) > 3 else "EDGE"
        return cls(float(seq[0]), float(seq[1]), float(seq[2]), kind)

    def xyz(self) -> Tuple[float, float, float]:
        return self.x, self.y, self.z


@dataclass
class Report:
    steps: Dict[str, Any] = field(default_factory=dict)
    dims: List[Dict[str, Any]] = field(default_factory=list)
    annotations: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        out = {"steps": self.steps, "dims": self.dims, "annotations": self.annotations, "errors": self.errors}
        out.update(self.extra)
        return out


class DrawingContext:
    """Wraps the active drawing with the helpers every step needs."""

    def __init__(self, dwg, style: Optional[HouseStyle] = None, report: Optional[Report] = None):
        self.dwg = dwg
        self.style = style or HouseStyle()
        self.report = report or Report()
        self.state: Dict[str, Any] = {}       # view names created during the run, etc.
        self.regen_pause_s = 0.5

    # ------------------------------------------------------------------ basics
    def clear(self) -> None:
        self.dwg.ClearSelection2(True)

    def rebuild(self) -> None:
        try:
            self.dwg.ForceRebuild3(False)
        except Exception:
            com.call(self.dwg, "EditRebuild3")

    def regen(self) -> None:
        """Make every view's geometry exist and display before picking edges (see references/api-gotchas.md)."""
        self.rebuild()
        for m in ("ViewZoomtofit2", "GraphicsRedraw2"):
            try:
                com.call(self.dwg, m)
            except Exception:
                pass
        if self.regen_pause_s:
            time.sleep(self.regen_pause_s)

    def view(self, name: str, prefix: bool = False):
        return com.find_view(self.dwg, self.state.get("alias:" + name, name), prefix=prefix)

    def alias(self, alias: str, real_name: str) -> None:
        """Let later steps refer to a created view by the spec's id (e.g. ``A`` -> ``Section View A-A``)."""
        self.state["alias:" + alias] = real_name

    # ------------------------------------------------------------------ coordinates
    def to_sheet(self, view, p) -> Tuple[float, float]:
        if not isinstance(p, Pick):
            p = Pick.parse(p)
        a = list(com.call(com.call(view, "ModelToViewTransform"), "ArrayData"))
        return model_to_sheet(a, *p.xyz())

    def to_sketch(self, view, sx: float, sy: float) -> Tuple[float, float, float]:
        return sheet_to_sketch(list(com.call(view, "GetXform")), sx, sy)

    # ------------------------------------------------------------------ selection
    def _sm(self):
        return com.call(self.dwg, "SelectionManager")

    def selected_count(self) -> int:
        return int(self._sm().GetSelectedObjectCount2(-1))

    def select(self, view, pick, append: bool = False) -> bool:
        """Pick geometry at a model point.

        The view is often auto-selected as item 1, so the return value of ``SelectByID2`` is not
        trusted: a pick counts only if the selection count grew AND the newest item is an edge,
        vertex or silhouette. Tries the requested kind first, then the others, each at the exact
        point and 0.2 mm either side.
        """
        p = Pick.parse(pick)
        sx, sy = self.to_sheet(view, p)
        kinds = ["VERTEX"] if p.kind == "VERTEX" else [p.kind] + [k for k in KINDS if k != p.kind]
        for kind in kinds:
            for dx, dy in ((0, 0), (NUDGE_M, 0), (-NUDGE_M, 0), (0, NUDGE_M), (0, -NUDGE_M)):
                before = self.selected_count() if append else 0
                if not append:
                    self.clear()
                ok = self.dwg.Extension.SelectByID2("", kind, sx + dx, sy + dy, 0, append, 0, com.nothing(), 0)
                if not ok:
                    continue
                n = self.selected_count()
                if n > before and int(self._sm().GetSelectedObjectType3(n, -1)) in GOOD_TYPES:
                    return True
                if append:
                    try:
                        self._sm().DeSelect2(n, -1)
                    except Exception:
                        pass
                else:
                    self.clear()
        return False

    def select_by_name(self, name: str, kind: str, append: bool = False) -> bool:
        return bool(self.dwg.Extension.SelectByID2(name, kind, 0, 0, 0, append, 0, com.nothing(), 0))

    def delete_display_dim(self, dd) -> None:
        """Dimensions are easiest to delete by name (GetNameForSelection + DIMENSION)."""
        self.clear()
        name = str(com.call(dd, "GetNameForSelection"))
        if not self.select_by_name(name, "DIMENSION"):
            com.call(dd, "GetAnnotation").Select3(False, com.nothing())
        com.call(self.dwg, "EditDelete")
        self.clear()

    # ------------------------------------------------------------------ text
    def apply_font(self, owner, height_m: Optional[float] = None, pts: Optional[float] = None) -> None:
        """Set typeface and size on a note/dimension/GTol (anything with GetAnnotation)."""
        try:
            ann = com.call(owner, "GetAnnotation")
            tf = ann.GetTextFormat(0)
            tf.TypeFaceName = self.style.font
            if pts:
                tf.CharHeightInPts = pts
            else:
                tf.CharHeight = height_m or self.style.dim_h
            ann.SetTextFormat(0, False, tf)
        except Exception as exc:
            log(f"  font failed: {exc}")

    def place(self, owner, view, at) -> None:
        tx, ty = self.to_sheet(view, at)
        com.call(owner, "GetAnnotation").SetPosition2(tx, ty, 0)


def resolve_view(ctx: DrawingContext, ref: str):
    v = ctx.view(ref)
    if v is None:
        v = ctx.view(ref, prefix=True)
    if v is None:
        raise LookupError(f"view not found: {ref}")
    return v


def as_list(value) -> Sequence:
    if value is None:
        return []
    return value if isinstance(value, (list, tuple)) else [value]
