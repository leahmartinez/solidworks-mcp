"""swdraw: spec-driven SolidWorks drawings with self-checking dimensions, revisions,
reference-safe renumbering, folder tidy and a drawing register.

Short helper aliases for writing your own scripts::

    import swdraw as sw
    dwg = sw.active()
    for v in sw.views(dwg): ...
    sw.result({"ok": True})
"""
from .com import active, app, arr8, byref_int, call, find_view, invoke, nothing, open_doc, views  # noqa: F401
from .runner import args, log, result  # noqa: F401

__version__ = "0.2.0"
