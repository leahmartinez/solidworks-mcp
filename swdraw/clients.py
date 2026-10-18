"""Register the swdraw MCP server (and skill) with AI clients.

    python -m swdraw setup claude-code              # show what would change
    python -m swdraw setup claude-code --apply      # do it
    python -m swdraw setup claude-desktop --apply
    python -m swdraw setup codex --apply
    python -m swdraw setup claude-code --skill --apply   # also install SKILL.md + references for Claude Code

Every client runs the same command: ``uv run --directory <repo> --extra mcp --extra preview python
mcp_server/server.py``. uv creates the environment on first run. Config files are backed up to
``<file>.bak`` before they are changed. If you installed the ``.mcpb`` extension in Claude Desktop,
don't also register it there with this command; you would get the tools twice.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "swdraw"
CLIENTS = ("claude-code", "claude-desktop", "codex")
SKILL_PARTS = ("SKILL.md", "SUBSKILLS.md", "capabilities.yaml", "references", "subskills")


def server_command(root: str = ROOT, uv: Optional[str] = None) -> Dict[str, Any]:
    uv = uv or shutil.which("uv") or "uv"
    return {"command": uv,
            "args": ["run", "--directory", root, "--extra", "mcp", "--extra", "preview",
                     "python", "mcp_server/server.py"]}


def env_block(output_dir: Optional[str], profiles: Optional[str], scripts: Optional[str]) -> Dict[str, str]:
    env = {"PYTHONUTF8": "1"}
    for k, v in (("SWDRAW_OUTPUT_DIR", output_dir), ("SWDRAW_PROFILES", profiles), ("SWDRAW_SCRIPTS_DIR", scripts)):
        if v:
            env[k] = os.path.abspath(os.path.expanduser(v))
    return env


def home() -> str:
    return os.path.expanduser("~")


def desktop_config_path() -> str:
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA", os.path.join(home(), "AppData", "Roaming")),
                            "Claude", "claude_desktop_config.json")
    if sys.platform == "darwin":
        return os.path.join(home(), "Library", "Application Support", "Claude", "claude_desktop_config.json")
    return os.path.join(home(), ".config", "Claude", "claude_desktop_config.json")


def codex_config_path() -> str:
    return os.path.join(os.environ.get("CODEX_HOME", os.path.join(home(), ".codex")), "config.toml")


def claude_skills_dir() -> str:
    return os.path.join(home(), ".claude", "skills", NAME)


def _backup(path: str) -> Optional[str]:
    if os.path.isfile(path):
        bak = path + ".bak"
        shutil.copy2(path, bak)
        return bak
    return None


# --------------------------------------------------------------------------- per client
def plan_desktop(cmd: Dict[str, Any], env: Dict[str, str], path: Optional[str] = None) -> Dict[str, Any]:
    path = path or desktop_config_path()
    cfg: Dict[str, Any] = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read().strip()
        cfg = json.loads(text) if text else {}
    servers = cfg.setdefault("mcpServers", {})
    existed = NAME in servers
    servers[NAME] = dict(cmd, env=env)
    return {"client": "claude-desktop", "path": path, "replaces_existing": existed,
            "new_content": json.dumps(cfg, indent=2) + "\n",
            "note": "Restart Claude Desktop afterwards. Skip this if you installed swdraw.mcpb."}


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def codex_section(cmd: Dict[str, Any], env: Dict[str, str]) -> str:
    args = ", ".join(_toml_str(a) for a in cmd["args"])
    envs = ", ".join(f"{k} = {_toml_str(v)}" for k, v in env.items())
    return (f"[mcp_servers.{NAME}]\ncommand = {_toml_str(cmd['command'])}\nargs = [{args}]\n"
            f"env = {{ {envs} }}\nstartup_timeout_sec = 60\n")


def plan_codex(cmd: Dict[str, Any], env: Dict[str, str], path: Optional[str] = None) -> Dict[str, Any]:
    path = path or codex_config_path()
    text = open(path, encoding="utf-8").read() if os.path.isfile(path) else ""
    section = codex_section(cmd, env)
    pat = re.compile(r"(?ms)^\[mcp_servers\." + NAME + r"\]\n.*?(?=^\[|\Z)")
    existed = bool(pat.search(text))
    if existed:
        new = pat.sub(lambda _m: section + "\n", text, count=1)   # a plain string would unescape "\\"
    else:
        new = (text.rstrip() + "\n\n" if text.strip() else "") + section
    return {"client": "codex", "path": path, "replaces_existing": existed, "new_content": new}


def plan_claude_code(cmd: Dict[str, Any], env: Dict[str, str]) -> Dict[str, Any]:
    argv = ["claude", "mcp", "add", "--scope", "user"]
    for k, v in env.items():
        argv += ["-e", f"{k}={v}"]
    argv += [NAME, "--", cmd["command"]] + cmd["args"]
    return {"client": "claude-code", "command": argv,
            "note": "Runs `claude mcp add`; needs the Claude Code CLI on PATH. "
                    "If swdraw is already registered: `claude mcp remove swdraw --scope user` first."}


def plan_skill(dest: Optional[str] = None) -> Dict[str, Any]:
    dest = dest or claude_skills_dir()
    return {"skill_dest": dest, "skill_files": [p for p in SKILL_PARTS if os.path.exists(os.path.join(ROOT, p))]}


def install_skill(dest: str) -> List[str]:
    os.makedirs(dest, exist_ok=True)
    done = []
    for part in SKILL_PARTS:
        src = os.path.join(ROOT, part)
        if not os.path.exists(src):
            continue
        dst = os.path.join(dest, part)
        if os.path.isdir(src):
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        done.append(dst)
    return done


def setup(client: str, apply: bool = False, skill: bool = False, output_dir: Optional[str] = None,
          profiles: Optional[str] = None, scripts: Optional[str] = None, uv: Optional[str] = None,
          config_path: Optional[str] = None, skill_dest: Optional[str] = None) -> Dict[str, Any]:
    if client not in CLIENTS:
        raise ValueError(f"client must be one of {CLIENTS}")
    cmd = server_command(uv=uv)
    env = env_block(output_dir, profiles, scripts)
    if client == "claude-desktop":
        plan = plan_desktop(cmd, env, config_path)
    elif client == "codex":
        plan = plan_codex(cmd, env, config_path)
    else:
        plan = plan_claude_code(cmd, env)
    if skill:
        plan.update(plan_skill(skill_dest))
    plan["applied"] = False
    if not apply:
        plan["next"] = "Dry run. Re-run with --apply to make these changes."
        return plan
    if "path" in plan:
        os.makedirs(os.path.dirname(plan["path"]), exist_ok=True)
        plan["backup"] = _backup(plan["path"])
        with open(plan["path"], "w", encoding="utf-8") as fh:
            fh.write(plan["new_content"])
    if "command" in plan:
        p = subprocess.run(plan["command"], capture_output=True, text=True)
        plan["exit_code"], plan["output"] = p.returncode, (p.stdout + p.stderr)[-2000:]
        if p.returncode:
            plan["error"] = "claude mcp add failed; see output"
    if skill:
        plan["skill_installed"] = install_skill(plan["skill_dest"])
    plan["applied"] = "error" not in plan
    plan.pop("new_content", None)
    return plan
