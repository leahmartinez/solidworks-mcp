"""Load profiles (house style, title block, numbering) and drawing specs from YAML or JSON.

Lookup order for a named profile such as ``house_style``:

1. an explicit path passed by the caller
2. ``$SWDRAW_PROFILES/<name>.yaml`` (or ``.yml`` / ``.json``)
3. the defaults bundled in ``profiles/`` next to the package

Strings in paths may use ``~`` and ``${ENV_VAR}``.
"""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

PACKAGE_PROFILES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")


def expand(path: str) -> str:
    return os.path.expanduser(os.path.expandvars(path))


def load_file(path: str) -> Dict[str, Any]:
    path = expand(path)
    with open(path, encoding="utf-8") as fh:
        if path.lower().endswith((".yaml", ".yml")):
            import yaml
            return yaml.safe_load(fh) or {}
        return json.load(fh)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def find_profile(name: str, explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        p = expand(explicit)
        if not os.path.isfile(p):
            raise FileNotFoundError(f"profile not found: {explicit}")
        return p
    dirs = []
    if os.environ.get("SWDRAW_PROFILES"):
        dirs.append(expand(os.environ["SWDRAW_PROFILES"]))
    dirs.append(PACKAGE_PROFILES)
    for d in dirs:
        for ext in (".yaml", ".yml", ".json"):
            p = os.path.join(d, name + ext)
            if os.path.isfile(p):
                return p
    return None


def load_profile(name: str, explicit: Optional[str] = None, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    p = find_profile(name, explicit)
    data = load_file(p) if p else {}
    return deep_merge(defaults or {}, data)


# --------------------------------------------------------------------------- house style
@dataclass
class HouseStyle:
    font: str = "Arial"
    dimension_height_mm: float = 2.5
    gdt_height_mm: float = 2.5
    view_label_height_mm: float = 3.5
    note_height_pt: float = 8.0
    general_tolerance: str = "ISO 2768-mK"
    #: document text defaults taller than this are treated as labels when restyling
    label_threshold_mm: float = 3.0
    view_label_prefixes: List[str] = field(default_factory=lambda: ["SECTION", "DETAIL", "SCALE", "VIEW"])
    date_format: str = "%d/%m/%Y"

    @property
    def dim_h(self) -> float:
        return self.dimension_height_mm / 1000.0

    @property
    def gdt_h(self) -> float:
        return self.gdt_height_mm / 1000.0

    @property
    def label_h(self) -> float:
        return self.view_label_height_mm / 1000.0

    @classmethod
    def load(cls, explicit: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> "HouseStyle":
        data = load_profile("house_style", explicit)
        data = deep_merge(data, overrides or {})
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def load_title_block(explicit: Optional[str] = None) -> Dict[str, Any]:
    return load_profile("title_block", explicit)


def load_numbering(explicit: Optional[str] = None) -> Dict[str, Any]:
    return load_profile("numbering", explicit)
