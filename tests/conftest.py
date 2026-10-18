import os
import sys
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def no_com(monkeypatch, tmp_path):
    """Replace the few helpers that need pywin32 with plain-Python stand-ins."""
    from swdraw import com, runner
    monkeypatch.setattr(com, "nothing", lambda: None)
    monkeypatch.setattr(com, "arr8", lambda vals: [float(v) for v in vals])
    monkeypatch.setattr(com, "byref_int", lambda value=0: SimpleNamespace(value=value))
    monkeypatch.setattr(com, "byref_bool", lambda value=False: SimpleNamespace(value=value))
    monkeypatch.delenv("SWDRAW_BACKUP_DIR", raising=False)
    monkeypatch.setenv("SWDRAW_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.delenv("SWDRAW_PROFILES", raising=False)
    monkeypatch.delenv("SWDRAW_ARGS", raising=False)
    runner._ARGS = None
    yield
    runner._ARGS = None
