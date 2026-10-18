"""A small fake of the SolidWorks API, enough to exercise selection, dimensioning, tolerances,
notes and custom properties on a drawing, and parameters, equations, configurations, rebuild errors
and mass properties on a part, without SolidWorks.

Geometry is registered per view at MODEL points; the fake maps them to the sheet with the same
ArrayData maths as the real API, and SelectByID2 hits whatever is within 0.05 mm of the pick.
A miss selects the view itself (as SolidWorks often does) so the "count grew and newest item is
geometry" guard is tested.
"""
from __future__ import annotations

import math
import re
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple

from swdraw.geometry import model_to_sheet

SEL_VIEW = 12
HIT_M = 0.00005


def identity_array(tx=0.1, ty=0.1, scale=1.0) -> List[float]:
    """Front-view-like transform: model X -> sheet x, model Y -> sheet y."""
    return [1, 0, 0, 0, 1, 0, 0, 0, 1, tx, ty, 0, scale, 0, 0, 0]


def section_array(tx=0.2, ty=0.1, scale=1.0) -> List[float]:
    """Section-like transform: model Z -> sheet x, model Y -> sheet y."""
    return [0, 0, 0, 0, 1, 0, 1, 0, 0, tx, ty, 0, scale, 0, 0, 0]


class FakeTextFormat:
    def __init__(self, face="Century Gothic", h=0.0035, bold=False):
        self.TypeFaceName, self.CharHeight, self.Bold = face, h, bold
        self.CharHeightInPts = None


class FakeAnnotation:
    def __init__(self, owner):
        self.owner = owner
        self.position = None
        self.tf = FakeTextFormat()

    def GetTextFormat(self, i):
        return self.tf

    def SetTextFormat(self, i, use_doc, tf):
        self.tf = tf
        return True

    def SetPosition2(self, x, y, z):
        self.position = (x, y)
        return True

    def GetPosition(self):
        return list(self.position or (0.0, 0.0)) + [0.0]

    def Select3(self, append, data):
        return self.owner.dwg._select_obj(self.owner, append)

    def Select2(self, append, mark):
        return self.owner.dwg._select_obj(self.owner, append)


class FakeTolerance:
    def __init__(self):
        self.Type = 0
        self._lo = self._hi = 0.0
        self.calls = []

    def SetValues2(self, lo, hi, a, b):
        self.calls.append("SetValues2")
        self._lo, self._hi = lo, hi
        return True

    def GetMaxValue(self):
        return self._hi

    def GetMinValue(self):
        return self._lo


class FakeDimension:
    def __init__(self, value_m):
        self.SystemValue = value_m
        self.Tolerance = FakeTolerance()
        self.arc = {}

    def SetArcEndCondition(self, i, c):
        self.arc[i] = c
        return True


class FakeDisplayDim:
    _n = 0

    def __init__(self, dwg, view, value_m):
        FakeDisplayDim._n += 1
        self.dwg, self.view = dwg, view
        self.name = f"D{FakeDisplayDim._n}@{view.name}"
        self.dim = FakeDimension(value_m)
        self.ann = FakeAnnotation(self)
        self.text = {}
        self.precision = None
        self.Diametric = False

    def GetDimension2(self, i):
        return self.dim

    def GetAnnotation(self):
        return self.ann

    def GetNameForSelection(self):
        return self.name

    def SetText(self, where, txt):
        self.text[where] = txt

    def SetPrecision3(self, a, b, c, d):
        self.precision = a


class FakeNote:
    def __init__(self, dwg, text, pos_m=(0.0, 0.0), name="Note"):
        self.dwg, self.text, self.name = dwg, text, name
        self.ann = FakeAnnotation(self)
        self.ann.position = pos_m
        self.next: Optional["FakeNote"] = None

    def GetText(self):
        return self.text

    def SetText(self, t):
        self.text = t
        return True

    def GetAnnotation(self):
        return self.ann

    def GetNext(self):
        return self.next

    def GetName(self):
        return self.name


class FakeView:
    def __init__(self, dwg, name, array, xform=None):
        self.dwg, self.name = dwg, name
        self.ModelToViewTransform = SimpleNamespace(ArrayData=array)
        self.xform = xform or [array[9], array[10], array[12]]
        self.next = None
        self.notes: List[FakeNote] = []
        self.dims: List[FakeDisplayDim] = []
        self.ReferencedDocument = None

    def GetName2(self):
        return self.name

    def GetXform(self):
        return self.xform

    def GetNextView(self):
        return self.next

    def _link(self, items):
        for a, b in zip(items, items[1:] + [None]):
            a.next = b
        return items[0] if items else None

    def GetFirstNote(self):
        return self._link(self.notes)

    def GetFirstDisplayDimension5(self):
        return None

    def GetFirstGTOL(self):
        return None

    def GetAnnotations(self):
        return [n.ann for n in self.notes]


class FakeCPM:
    def __init__(self, store):
        self.store = store

    def Add3(self, name, typ, value, how):
        self.store[name] = value
        return 0

    def Get6(self, name, cached, a, b, c, d):
        v = self.store.get(name, "")
        return (0, v, v, True, False)


class FakePart:
    """A referenced model with its own custom properties."""

    def __init__(self):
        self.props: Dict[str, str] = {}
        self.Extension = SimpleNamespace(CustomPropertyManager=lambda config: FakeCPM(self.props))


class FakeExtension:
    def __init__(self, dwg):
        self.dwg = dwg

    def SelectByID2(self, name, kind, x, y, z, append, mark, callout, opt):
        return self.dwg._select_point(name, kind, x, y, append)

    def CustomPropertyManager(self, config):
        return FakeCPM(self.dwg.props)


class FakeSelMgr:
    def __init__(self, dwg):
        self.dwg = dwg

    def GetSelectedObjectCount2(self, mark):
        return len(self.dwg.selection)

    def GetSelectedObjectType3(self, i, mark):
        return self.dwg.selection[i - 1][0]

    def DeSelect2(self, i, mark):
        del self.dwg.selection[i - 1]
        return True


class FakeDrawing:
    def __init__(self):
        self.sheet = FakeView(self, "Sheet1", identity_array(0, 0))
        self._views: List[FakeView] = [self.sheet]
        self.Extension = FakeExtension(self)
        self.SelectionManager = FakeSelMgr(self)
        self.selection: List[Tuple[int, object]] = []
        self.geometry: List[Tuple[FakeView, float, float, str, str]] = []
        self.measure: Dict[Tuple[str, ...], float] = {}
        self.dims: List[FakeDisplayDim] = []
        self.deleted: List[object] = []
        self.inserted_notes: List[FakeNote] = []
        self.props: Dict[str, str] = {}
        self.rebuilds = 0

    # ------------------------------------------------------------------ setup helpers
    def add_view(self, name, array) -> FakeView:
        v = FakeView(self, name, array)
        self._views[-1].next = v
        self._views.append(v)
        return v

    def add_geometry(self, view, model_xyz, gid, kind="EDGE"):
        sx, sy = model_to_sheet(view.ModelToViewTransform.ArrayData, *model_xyz)
        self.geometry.append((view, sx, sy, kind, gid))

    # ------------------------------------------------------------------ API surface
    def GetType(self):
        return 3

    def GetFirstView(self):
        return self._views[0]

    def ClearSelection2(self, all_):
        self.selection = []
        return True

    def ForceRebuild3(self, top):
        self.rebuilds += 1
        return True

    def EditRebuild3(self):
        self.rebuilds += 1
        return True

    def GraphicsRedraw2(self):
        return True

    def ViewZoomtofit2(self):
        return True

    def ActivateView(self, name):
        return True

    def EditDelete(self):
        for _t, obj in self.selection:
            self.deleted.append(obj)
            if obj in self.dims:
                self.dims.remove(obj)
            for v in self._views:
                if obj in v.notes:
                    v.notes.remove(obj)
        self.selection = []
        return True

    def AddDimension2(self, x, y, z):
        ids = tuple(sorted(str(o) for t, o in self.selection if t != SEL_VIEW))
        if ids not in self.measure:
            return None
        view = next(v for (v, *_rest) in self.geometry)
        dd = FakeDisplayDim(self, view, self.measure[ids])
        dd.ann.position = (x, y)
        self.dims.append(dd)
        return dd

    def InsertNote(self, text):
        n = FakeNote(self, text)
        self.inserted_notes.append(n)
        self.sheet.notes.append(n)
        return n

    # ------------------------------------------------------------------ selection engine
    def _select_point(self, name, kind, x, y, append):
        if not append:
            self.selection = []
        if name:
            if kind == "DIMENSION":
                for d in self.dims:
                    if d.name == name:
                        self.selection.append((14, d))
                        return True
            return False
        for (v, sx, sy, k, gid) in self.geometry:
            if k == kind and abs(sx - x) < HIT_M and abs(sy - y) < HIT_M:
                self.selection.append(({"EDGE": 1, "VERTEX": 3, "SILHOUETTE": 46}[k], gid))
                return True
        self.selection.append((SEL_VIEW, "view"))     # SolidWorks picked the view instead
        return True

    def _select_obj(self, obj, append):
        if not append:
            self.selection = []
        self.selection.append((0, obj))
        return True


# =========================================================================== part (model) API
# A fake part: dimensions on features, an equation manager that really evaluates its equations on
# rebuild, configurations, a design table, mass properties from a caller-supplied model, rebuild
# errors from a caller-supplied rule, and Save3.
DIM_LINEAR, DIM_ANGULAR, DIM_INTEGER = 1, 2, 3
_EQ = re.compile(r'^\s*"([^"]+)"\s*=\s*(.*?)\s*$')


class FakeModelDim:
    """IDimension. ``SystemValue`` is in metres, radians or a count."""

    def __init__(self, name, value_si, kind=DIM_LINEAR, read_only=False):
        self.Name, self.SystemValue, self.kind, self.ReadOnly = name, value_si, kind, read_only
        self.refuse = False
        self.set_calls = []

    def GetType(self):
        return self.kind

    def SetSystemValue3(self, value, which, names):
        self.set_calls.append(which)
        if self.refuse:
            return 1
        self.SystemValue = value
        return 0


class FakeModelDisplayDim:
    def __init__(self, dim):
        self.dim = dim

    def GetDimension2(self, i):
        return self.dim


class FakeFeature:
    def __init__(self, name, type_name, dims=()):
        self.Name, self.type_name = name, type_name
        self.display = [FakeModelDisplayDim(d) for d in dims]
        self.subs: List["FakeFeature"] = []
        self.next = self.next_sub = None
        self.error = (0, False)

    @property
    def dims(self):
        return [dd.dim for dd in self.display]

    def GetTypeName2(self):
        return self.type_name

    def GetErrorCode2(self, warn):
        warn.value = self.error[1]
        return self.error[0]

    def GetFirstDisplayDimension(self):
        return self.display[0] if self.display else None

    def GetNextDisplayDimension(self, dd):
        i = self.display.index(dd)
        return self.display[i + 1] if i + 1 < len(self.display) else None

    def GetNextFeature(self):
        return self.next

    def GetFirstSubFeature(self):
        return self.subs[0] if self.subs else None

    def GetNextSubFeature(self):
        return self.next_sub


class FakeEquationMgr:
    def __init__(self, part, texts=()):
        self.part, self.texts = part, list(texts)
        self.calls = []

    def GetCount(self):
        return len(self.texts)

    def Equation(self, i):
        return self.texts[i]

    def GlobalVariable(self, i):
        return "@" not in _EQ.match(self.texts[i]).group(1)

    def Value(self, i):
        return self.part.evaluate(_EQ.match(self.texts[i]).group(2))

    def SetEquationAndConfigurationOption(self, i, text, opt, names):
        self.calls.append(opt)
        try:
            self.part.evaluate(_EQ.match(text).group(2))
        except Exception:
            return 1                                    # SolidWorks rejects a bad expression
        self.texts[i] = text
        self.part.dirty = True
        return 0

    def EvaluateAll(self):
        self.part.apply_equations()
        return 1


class FakeDesignTable:
    """Rows of ``[configuration, value, ...]`` under ``headers`` (dimension full names, mm)."""

    def __init__(self, part, headers, rows):
        self.part, self.headers, self.rows = part, list(headers), [list(r) for r in rows]

    def GetTotalRowCount(self):
        return len(self.rows)

    def GetTotalColumnCount(self):
        return len(self.headers)

    def GetHeaderText(self, c):
        return self.headers[c - 1]

    def GetEntryText(self, r, c):
        return str(self.rows[r - 1][c])

    def EditTable2(self, b):
        return True

    def SetEntryValue(self, r, c, alias, text):
        self.rows[r - 1][c] = float(text)
        return True

    def UpdateTable(self, how, update_model):
        self.part.apply_design_table()
        return True

    def row_for(self, config):
        return next((r for r in self.rows if r[0] == config), None)


class FakeConfigMgr:
    def __init__(self, part):
        self.part = part

    @property
    def ActiveConfiguration(self):
        return SimpleNamespace(Name=self.part.active)


class FakeModelPart:
    """``model(part)`` returns {volume_mm3, surface_area_mm2, bbox: (min_xyz, max_xyz)} in mm;
    ``errors(part)`` returns {feature name: (code, is_warning)} for the current values."""

    def __init__(self, path="", configs=("Default",), model=None, errors=None, equations=()):
        self.path = path
        self.features: List[FakeFeature] = []
        self.eq = FakeEquationMgr(self, equations)
        self.configs, self.active = list(configs), configs[0]
        self.ConfigurationManager = FakeConfigMgr(self)
        self.model, self.error_rule = model, errors
        self.design: Optional[FakeDesignTable] = None
        self.dirty = self.read_only = False
        self.saves = self.rebuilds = 0
        self.density_kg_m3 = 1000.0
        self.MaterialIdName = ""
        self.overrides: Dict[str, float] = {}             # dimension -> mm, re-applied on every rebuild
        self.Extension = SimpleNamespace(CreateMassProperty=self._mass)

    # ------------------------------------------------------------------ setup helpers
    def add_feature(self, feat, parent=None):
        if parent is None:
            if self.features:
                self.features[-1].next = feat
            self.features.append(feat)
        else:
            if parent.subs:
                parent.subs[-1].next_sub = feat
            parent.subs.append(feat)
        return feat

    def all_features(self):
        for f in self.features:
            yield f
            yield from f.subs

    def dim(self, full_name):
        for f in self.all_features():
            for d in f.dims:
                if f"{d.Name}@{f.Name}".lower() == full_name.lower():
                    return d
        return None

    def mm(self, full_name):
        d = self.dim(full_name)
        return d.SystemValue * (180 / math.pi if d.kind == DIM_ANGULAR else 1000.0)

    # ------------------------------------------------------------------ equations
    def evaluate(self, expr):
        def sub(m):
            name = m.group(1)
            if "@" in name:
                return repr(self.mm(name))
            for t in self.eq.texts:
                lhs, rhs = _EQ.match(t).groups()
                if lhs.lower() == name.lower():
                    return "(" + repr(self.evaluate(rhs)) + ")"
            raise KeyError(name)
        py = re.sub(r'"([^"]+)"', sub, str(expr))
        py = re.sub(r"(\d)\s*mm\b", r"\1", py)
        return float(eval(py, {"__builtins__": {}}, {}))

    def apply_equations(self):
        for t in self.eq.texts:
            lhs, rhs = _EQ.match(t).groups()
            if "@" in lhs:
                self.dim(lhs).SystemValue = self.evaluate(rhs) / 1000.0

    def apply_design_table(self):
        row = self.design.row_for(self.active) if self.design else None
        if row:
            for h, v in zip(self.design.headers, row[1:]):
                self.dim(h).SystemValue = float(v) / 1000.0

    # ------------------------------------------------------------------ API surface
    def GetType(self):
        return 1

    def GetPathName(self):
        return self.path

    def GetSaveFlag(self):
        return self.dirty

    def IsOpenedReadOnly(self):
        return self.read_only

    def FirstFeature(self):
        return self.features[0] if self.features else None

    def Parameter(self, name):
        return self.dim(name)

    def GetEquationMgr(self):
        return self.eq

    def GetConfigurationNames(self):
        return tuple(self.configs)

    def ShowConfiguration2(self, name):
        if name not in self.configs:
            return False
        self.active = name
        self.apply_design_table()
        return True

    def GetDesignTable(self):
        return self.design

    def ForceRebuild3(self, top_only):
        self.rebuilds += 1
        self.dirty = True
        self.apply_equations()
        for name, v in self.overrides.items():
            self.dim(name).SystemValue = v / 1000.0
        errs = self.error_rule(self) if self.error_rule else {}
        for f in self.all_features():
            f.error = errs.get(f.Name, (0, False))
        return True

    def _measured(self):
        if self.model:
            return self.model(self)
        return {"volume_mm3": 0, "surface_area_mm2": 0, "bbox": ((0, 0, 0), (0, 0, 0))}

    def _mass(self):
        m = self._measured()
        vol = m["volume_mm3"] / 1e9
        return SimpleNamespace(Volume=vol, Mass=vol * self.density_kg_m3, SurfaceArea=m["surface_area_mm2"] / 1e6,
                               UseSystemUnits=False)

    def GetPartBox(self, exact):
        lo, hi = self._measured()["bbox"]
        return tuple(v / 1000.0 for v in list(lo) + list(hi))

    def Save3(self, options, errors, warnings):
        self.saves += 1
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(" saved")
        self.dirty = False
        errors.value = 0
        return True
