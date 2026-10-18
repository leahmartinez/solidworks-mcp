"""Thin late-binding helpers around the SolidWorks COM API.

Everything that touches ``win32com``/``pythoncom`` is imported lazily, so the rest of the package
(and the test-suite) can be imported on machines without SolidWorks or pywin32.
"""
from __future__ import annotations

import os
from typing import Any, Iterable, List, Optional

_APP = None

# swDocumentTypes_e
DOC_PART, DOC_ASSEMBLY, DOC_DRAWING = 1, 2, 3
_EXT_TYPE = {".sldprt": DOC_PART, ".sldasm": DOC_ASSEMBLY, ".slddrw": DOC_DRAWING}


def _pythoncom():
    import pythoncom  # noqa: WPS433 (deferred import on purpose)
    return pythoncom


def _variant(vt, value):
    from win32com.client import VARIANT
    return VARIANT(vt, value)


# --------------------------------------------------------------------------- application / documents
def app():
    """Return the running SolidWorks instance (late bound), starting it only if none is running."""
    global _APP
    if _APP is not None:
        return _APP
    import win32com.client as w
    import win32com.client.dynamic as dyn
    try:
        raw = w.GetActiveObject("SldWorks.Application")
    except Exception:
        raw = w.Dispatch("SldWorks.Application")
    _APP = dyn.Dispatch(raw)
    return _APP


def set_app(obj) -> None:
    """Inject an application object (used by tests and by hosts that already hold one)."""
    global _APP
    _APP = obj


def active():
    """The active document, or raise if nothing is open."""
    doc = call(app(), "ActiveDoc")
    if doc is None:
        raise RuntimeError("No active SolidWorks document.")
    return doc


def doc_type_for(path: str) -> int:
    ext = os.path.splitext(path)[1].lower()
    if ext not in _EXT_TYPE:
        raise ValueError(f"Not a SolidWorks part, assembly or drawing: {path}")
    return _EXT_TYPE[ext]


def get_open(path: str):
    """Return an already-open document by full path, or None."""
    return app().GetOpenDocumentByName(path)


def open_doc(path: str, silent: bool = True):
    """Open (or return the already-open) document. Raises with the SolidWorks error code on failure."""
    doc = get_open(path)
    if doc is not None:
        return doc
    errors, warnings = byref_int(), byref_int()
    doc = app().OpenDoc6(path, doc_type_for(path), 1 if silent else 0, "", errors, warnings)
    if doc is None:
        raise RuntimeError(f"OpenDoc6 failed for {path} (errors={errors.value}, warnings={warnings.value})")
    return doc


# --------------------------------------------------------------------------- calling conventions
#: Extra classes treated as COM objects by ``call`` (tests register their fakes here).
EXTRA_DISPATCH_TYPES: list = []


def _dispatch_types() -> tuple:
    types = list(EXTRA_DISPATCH_TYPES)
    try:
        from win32com.client import CDispatch
        types.append(CDispatch)
    except Exception:
        pass
    try:
        from win32com.client.dynamic import CDispatch as DynDispatch
        types.append(DynDispatch)
    except Exception:
        pass
    return tuple(types)


def is_com_object(value) -> bool:
    types = _dispatch_types()
    return bool(types) and isinstance(value, types)


def call(obj, name: str, *args):
    """Read a property or call a method by name.

    With late binding pywin32 cannot always tell zero-argument methods from properties, so this
    accepts either. A property that returns a COM object (``ActiveDoc``, ``SelectionManager``,
    ``ModelToViewTransform`` ...) comes back as a ``CDispatch``, which is itself callable; it is
    returned as-is, never called. Bound methods are called with ``args``; plain values are returned.
    """
    attr = getattr(obj, name)
    if is_com_object(attr):
        return invoke(obj, name, *args) if args else attr
    if callable(attr):
        return attr(*args)
    if args:
        return invoke(obj, name, *args)
    return attr


def invoke(obj, name: str, *args):
    """Call a COM method explicitly through ``IDispatch::Invoke``.

    Some calls (``InsertGtol``, ``InsertDatumTag2``) only work this way under late binding.
    """
    pythoncom = _pythoncom()
    import win32com.client as w
    ole = obj._oleobj_
    dispid = ole.GetIDsOfNames(name)
    res = ole.Invoke(dispid, 0, pythoncom.DISPATCH_METHOD, True, *args)
    if res is not None and type(res).__name__ == "PyIDispatch":
        res = w.Dispatch(res)
    return res


def has_member(obj, name: str) -> bool:
    try:
        obj._oleobj_.GetIDsOfNames(name)
        return True
    except Exception:
        return False


def nothing():
    """A typed null object: pass this where the API expects ``Nothing`` (plain ``None`` gives a type mismatch)."""
    return _variant(_pythoncom().VT_DISPATCH, None)


def byref_int(value: int = 0):
    """A by-reference long, e.g. for the errors/warnings arguments of ``OpenDoc6``."""
    p = _pythoncom()
    return _variant(p.VT_BYREF | p.VT_I4, value)


def byref_bool(value: bool = False):
    """A by-reference bool, e.g. the IsWarning argument of ``Feature.GetErrorCode2``."""
    p = _pythoncom()
    return _variant(p.VT_BYREF | p.VT_BOOL, value)


def put(obj, name: str, *args) -> None:
    """Set a property that takes arguments (``EquationMgr.Equation(i) = text``).

    Late binding has no syntax for this, so it goes through ``IDispatch::Invoke`` as a property put;
    the last argument is the value.
    """
    pythoncom = _pythoncom()
    ole = obj._oleobj_
    ole.Invoke(ole.GetIDsOfNames(name), 0, pythoncom.DISPATCH_PROPERTYPUT, False, *args)


def arr8(values: Iterable[float]):
    """A SAFEARRAY of doubles (view positions, scale ratios)."""
    p = _pythoncom()
    return _variant(p.VT_ARRAY | p.VT_R8, [float(v) for v in values])


def set_prop(obj, name: str, value) -> bool:
    """Set a COM property; logs and returns False on failure instead of raising."""
    try:
        setattr(obj, name, value)
        return True
    except Exception as exc:
        from .runner import log
        log(f"  set {name} failed: {exc}")
        return False


# --------------------------------------------------------------------------- drawing traversal
def views(dwg) -> List[Any]:
    """All views of the current sheet. Item 0 is the sheet itself (title block / sheet format)."""
    out = []
    v = call(dwg, "GetFirstView")
    guard = 0
    while v is not None and guard < 1000:
        out.append(v)
        v = call(v, "GetNextView")
        guard += 1
    return out


def view_name(view) -> str:
    return str(call(view, "GetName2"))


def find_view(dwg, name: str, prefix: bool = False) -> Optional[Any]:
    """Find a view by exact name, or by prefix (``Section View A`` matches ``Section View A-A``)."""
    for v in views(dwg):
        n = view_name(v)
        if n == name or (prefix and n.startswith(name)):
            return v
    return None


def iter_chain(first, next_name: str, limit: int = 2000):
    """Iterate a GetFirstX / GetNext linked list safely."""
    o, n = first, 0
    while o is not None and n < limit:
        yield o
        o = call(o, next_name)
        n += 1


def notes(view):
    return list(iter_chain(call(view, "GetFirstNote"), "GetNext"))


def display_dims(view):
    return list(iter_chain(call(view, "GetFirstDisplayDimension5"), "GetNext5"))


def gtols(view):
    return list(iter_chain(call(view, "GetFirstGTOL"), "GetNext"))
