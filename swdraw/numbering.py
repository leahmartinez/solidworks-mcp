"""Part numbers of the form PRODUCT-DISCIPLINE-NNNN with block allocation.

With ``block_size: 100``: 2100 is an assembly, 2101-2199 are its parts, 2200 the next assembly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from .config import load_numbering


@dataclass(frozen=True)
class PartNumber:
    product: str
    discipline: str
    number: int

    def format(self, scheme: "Scheme") -> str:
        return scheme.pattern.format(product=self.product, discipline=self.discipline, number=self.number)


class Scheme:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        cfg = cfg if cfg is not None else load_numbering()
        self.cfg = cfg
        self.product = str(cfg.get("product", "PRJ"))
        self.pattern = str(cfg.get("pattern", "{product}-{discipline}-{number:04d}"))
        self.block = int(cfg.get("block_size", 100))
        self.first_block = int(cfg.get("first_block", self.block))
        self.disciplines = dict(cfg.get("disciplines") or {"MEC": "Mechanical"})
        self._re = self._compile()

    def _compile(self):
        rx = re.escape(self.pattern)
        rx = rx.replace(re.escape("{product}"), r"(?P<product>[A-Za-z0-9]+)")
        rx = rx.replace(re.escape("{discipline}"), r"(?P<discipline>[A-Za-z]+)")
        rx = re.sub(r"\\\{number(:[^}]*)?\\\}", r"(?P<number>\\d+)", rx)
        return re.compile("^" + rx + "$")

    # ------------------------------------------------------------------ parse / format
    def parse(self, text: str) -> PartNumber:
        m = self._re.match(text.strip())
        if not m:
            raise ValueError(f"{text!r} does not match {self.pattern}")
        pn = PartNumber(m.group("product"), m.group("discipline").upper(), int(m.group("number")))
        if pn.discipline not in self.disciplines:
            raise ValueError(f"unknown discipline {pn.discipline!r} (allowed: {', '.join(self.disciplines)})")
        return pn

    def format(self, number: int, discipline: str = "MEC", product: Optional[str] = None) -> str:
        if discipline not in self.disciplines:
            raise ValueError(f"unknown discipline {discipline!r}")
        return PartNumber(product or self.product, discipline, int(number)).format(self)

    def is_valid(self, text: str) -> bool:
        try:
            self.parse(text)
            return True
        except ValueError:
            return False

    # ------------------------------------------------------------------ blocks
    def is_assembly(self, number: int) -> bool:
        return number % self.block == 0

    def assembly_of(self, number: int) -> int:
        return (number // self.block) * self.block

    def describe(self, text: str) -> str:
        pn = self.parse(text)
        if self.is_assembly(pn.number):
            return f"assembly (parts {pn.number + 1}-{pn.number + self.block - 1})"
        return f"part of assembly {self.format(self.assembly_of(pn.number), pn.discipline, pn.product)}"

    def next_assembly(self, used: Iterable[str], discipline: str = "MEC") -> str:
        nums = {self.parse(u).number for u in used if self.is_valid(u) and self.parse(u).discipline == discipline}
        n = self.first_block
        while n in nums or any(self.assembly_of(x) == n for x in nums):
            n += self.block
        return self.format(n, discipline)

    def next_part(self, assembly: str, used: Iterable[str]) -> str:
        a = self.parse(assembly)
        if not self.is_assembly(a.number):
            raise ValueError(f"{assembly} is not an assembly number")
        taken = {self.parse(u).number for u in used if self.is_valid(u)
                 and self.parse(u).discipline == a.discipline and self.parse(u).product == a.product}
        for n in range(a.number + 1, a.number + self.block):
            if n not in taken:
                return self.format(n, a.discipline, a.product)
        raise RuntimeError(f"block {assembly} is full")

    def properties(self, kind: str, number: str, description: str = "", revision: str = "A",
                   parent: str = "") -> Dict[str, str]:
        """Custom properties for a part or drawing, from ``part_properties`` / ``drawing_properties``."""
        tmpl = self.cfg.get(f"{kind}_properties") or {}
        ctx = dict(self.cfg.get("properties_static") or {})
        ctx.update(number=number, description=description, revision=revision, parent=parent)
        return {k: str(v).format(**ctx) for k, v in tmpl.items()}

    def file_stem(self, number: str) -> str:
        return str(self.cfg.get("file_name", "{number}")).format(number=number)
