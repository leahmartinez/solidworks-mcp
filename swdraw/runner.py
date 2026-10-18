"""Arguments in, JSON result out: the contract every swdraw script and tool follows.

A script can be launched three ways and reads its arguments the same way in each:

* ``python -m swdraw <command> --args args.json`` (or ``--args '{"key": 1}'``)
* by a host tool that sets ``SWDRAW_ARGS`` to a JSON string or a path to a JSON file
* imported and called directly with a dict

Results are printed as one JSON object between ``SWDRAW_RESULT_BEGIN`` / ``SWDRAW_RESULT_END``
markers so a host can find them in mixed stdout, and also written to the output folder.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from typing import Any, Dict, Optional

BEGIN, END = "SWDRAW_RESULT_BEGIN", "SWDRAW_RESULT_END"
_ARGS: Optional[Dict[str, Any]] = None


def output_dir() -> str:
    """Where traces, results and exports go (``SWDRAW_OUTPUT_DIR``, default ``~/swdraw-output``)."""
    d = os.path.expanduser(os.environ.get("SWDRAW_OUTPUT_DIR") or "~/swdraw-output")
    os.makedirs(d, exist_ok=True)
    return d


def parse_args_value(value: Optional[str]) -> Dict[str, Any]:
    """Accept a JSON object string, a path to a .json/.yaml file, or nothing."""
    if not value:
        return {}
    value = value.strip()
    if value.startswith("{"):
        return json.loads(value)
    path = os.path.expanduser(value)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"args file not found: {value}")
    with open(path, encoding="utf-8") as fh:
        if path.lower().endswith((".yaml", ".yml")):
            import yaml
            return yaml.safe_load(fh) or {}
        return json.load(fh)


def set_args(values: Dict[str, Any]) -> None:
    global _ARGS
    _ARGS = dict(values)


def args() -> Dict[str, Any]:
    """Arguments for the current run (``--args`` on the command line beats ``SWDRAW_ARGS``)."""
    global _ARGS
    if _ARGS is not None:
        return _ARGS
    raw = None
    argv = sys.argv[1:]
    if "--args" in argv:
        i = argv.index("--args")
        raw = argv[i + 1] if i + 1 < len(argv) else None
    if raw is None:
        raw = os.environ.get("SWDRAW_ARGS")
    _ARGS = parse_args_value(raw)
    return _ARGS


def log(msg: str) -> None:
    """Timestamped line to stderr and to ``<output>/swdraw.log``."""
    line = _dt.datetime.now().strftime("%H:%M:%S ") + str(msg)
    print(line, file=sys.stderr, flush=True)
    try:
        with open(os.path.join(output_dir(), "swdraw.log"), "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _jsonable(obj):
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]
    return str(obj)


def result(obj: Dict[str, Any], name: str = "result") -> Dict[str, Any]:
    """Print the result between markers and save it as ``<output>/<name>.json``."""
    data = _jsonable(obj)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    print(BEGIN)
    print(text)
    print(END, flush=True)
    try:
        with open(os.path.join(output_dir(), f"{name}.json"), "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError:
        pass
    return data


def extract_result(stdout: str) -> Optional[Dict[str, Any]]:
    """Pull the last result object out of a script's stdout."""
    if BEGIN not in stdout:
        return None
    chunk = stdout.rsplit(BEGIN, 1)[1].split(END, 1)[0]
    return json.loads(chunk)
