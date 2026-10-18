"""Keep only live files in a working folder; move everything else to a superseded folder.

Never overwrites a different file: a byte-identical copy already in the destination is merged
(the source is removed), anything else gets a ``(YYYY-MM-DD HHMM)`` suffix from its own mtime.
Office lock files (``~$...``) and folders are skipped unless listed in ``move_folders``.
Dry run is the default.

Arguments::

    working: path to the folder to tidy
    superseded: destination (default: <parent of working>/_Superseded)
    keep: ["*.SLDPRT", "ACME1-MEC-2101.*", "Drawing Register.xlsx"]   # glob patterns, case-insensitive
    move_folders: {"Reference": "<parent>"}    # folder name -> destination directory
    dry_run: true
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import shutil
import time
from typing import Any, Dict, List, Optional, Sequence


def md5(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def is_kept(name: str, keep: Sequence[str]) -> bool:
    low = name.lower()
    return any(fnmatch.fnmatch(low, k.lower()) for k in keep)


def unique_destination(src: str, dst: str) -> str:
    """Destination that does not clobber a different file."""
    if not os.path.exists(dst):
        return dst
    stem, ext = os.path.splitext(dst)
    stamp = time.strftime("%Y-%m-%d %H%M", time.localtime(os.path.getmtime(src)))
    cand = f"{stem} ({stamp}){ext}"
    i = 2
    while os.path.exists(cand):
        cand = f"{stem} ({stamp}) {i}{ext}"
        i += 1
    return cand


def move(src: str, dst: str, dry_run: bool, log: List[str], root: str) -> str:
    rel = lambda p: os.path.relpath(p, root)  # noqa: E731
    if os.path.isfile(dst) and os.path.isfile(src) and md5(src) == md5(dst):
        log.append(f"{rel(src)} == identical copy in {rel(dst)} (merged)")
        if not dry_run:
            os.remove(src)
        return dst
    final = unique_destination(src, dst)
    log.append(f"{rel(src)} -> {rel(final)}")
    if not dry_run:
        os.makedirs(os.path.dirname(final), exist_ok=True)
        shutil.move(src, final)
    return final


def tidy(working: str, keep: Sequence[str], superseded: Optional[str] = None,
         move_folders: Optional[Dict[str, str]] = None, dry_run: bool = True) -> Dict[str, Any]:
    working = os.path.abspath(os.path.expanduser(working))
    root = os.path.dirname(working)
    superseded = os.path.abspath(os.path.expanduser(superseded or os.path.join(root, "_Superseded")))
    move_folders = move_folders or {}
    rep: Dict[str, Any] = {"dry_run": dry_run, "moves": [], "skipped": [], "errors": []}
    if not os.path.isdir(working):
        rep["errors"].append(f"not a folder: {working}")
        return rep
    for name in sorted(os.listdir(working)):
        p = os.path.join(working, name)
        try:
            if os.path.isdir(p):
                if name in move_folders:
                    dest_dir = os.path.abspath(os.path.expanduser(move_folders[name].replace("<parent>", root)))
                    move(p, os.path.join(dest_dir, name), dry_run, rep["moves"], root)
                else:
                    rep["skipped"].append(f"folder {name}")
                continue
            if name.startswith("~$"):
                rep["skipped"].append(f"lock file {name}")
                continue
            if is_kept(name, keep):
                continue
            move(p, os.path.join(superseded, name), dry_run, rep["moves"], root)
        except Exception as exc:     # a locked file must not stop the rest
            rep["errors"].append(f"{name}: {exc.__class__.__name__}: {exc}")
    rep["working_now"] = sorted(os.listdir(working))
    return rep
