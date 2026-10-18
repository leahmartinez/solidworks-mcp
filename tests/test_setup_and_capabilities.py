"""Client registration (dry run and apply against temp files) and generated capabilities."""
import importlib.util
import json
import os
import sys

import pytest

from swdraw import clients

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import tomllib
except ImportError:  # Python 3.10
    tomllib = None


def test_desktop_dry_run_changes_nothing(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}))
    plan = clients.setup("claude-desktop", config_path=str(cfg), uv="uv")
    assert plan["applied"] is False and json.loads(cfg.read_text())["mcpServers"].keys() == {"other"}


def test_desktop_apply_keeps_other_servers_and_backs_up(tmp_path):
    cfg = tmp_path / "Claude" / "claude_desktop_config.json"
    cfg.parent.mkdir()
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}))
    plan = clients.setup("claude-desktop", apply=True, config_path=str(cfg), uv="uv", output_dir=str(tmp_path / "o"))
    data = json.loads(cfg.read_text())
    assert set(data["mcpServers"]) == {"other", "swdraw"} and data["theme"] == "dark"
    sw = data["mcpServers"]["swdraw"]
    assert sw["command"] == "uv" and sw["args"][:3] == ["run", "--directory", clients.ROOT]
    assert sw["args"][-1] == "mcp_server/server.py" and "SWDRAW_OUTPUT_DIR" in sw["env"]
    assert os.path.isfile(plan["backup"])


def test_desktop_creates_missing_config(tmp_path):
    cfg = tmp_path / "new" / "claude_desktop_config.json"
    clients.setup("claude-desktop", apply=True, config_path=str(cfg), uv="uv")
    assert "swdraw" in json.loads(cfg.read_text())["mcpServers"]


@pytest.mark.skipif(tomllib is None, reason="tomllib needs Python 3.11+")
def test_codex_append_then_replace(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('model = "x"\n\n[mcp_servers.other]\ncommand = "o"\n')
    clients.setup("codex", apply=True, config_path=str(cfg), uv="C:\\tools\\uv.exe", output_dir="~/out")
    clients.setup("codex", apply=True, config_path=str(cfg), uv="uv")      # second run replaces, not duplicates
    text = cfg.read_text()
    data = tomllib.loads(text)
    assert text.count("[mcp_servers.swdraw]") == 1
    assert data["model"] == "x" and data["mcp_servers"]["other"]["command"] == "o"
    assert data["mcp_servers"]["swdraw"]["command"] == "uv"
    assert data["mcp_servers"]["swdraw"]["env"]["PYTHONUTF8"] == "1"


def test_codex_escapes_windows_paths():
    if tomllib is None:
        pytest.skip("tomllib needs Python 3.11+")
    sec = clients.codex_section({"command": "C:\\a b\\uv.exe", "args": ["--directory", "C:\\x\\y"]}, {"K": 'v"q'})
    d = tomllib.loads(sec)["mcp_servers"]["swdraw"]
    assert d["command"] == "C:\\a b\\uv.exe" and d["args"][1] == "C:\\x\\y" and d["env"]["K"] == 'v"q'


def test_claude_code_command_shape():
    plan = clients.setup("claude-code", uv="uv", output_dir="/tmp/o")
    argv = plan["command"]
    assert argv[:5] == ["claude", "mcp", "add", "--scope", "user"]
    i = argv.index("--")
    assert argv[i - 1] == "swdraw" and argv[i + 1] == "uv" and "-e" in argv[:i]


def test_skill_install(tmp_path):
    dest = tmp_path / "skills" / "swdraw"
    plan = clients.setup("claude-code", skill=True, skill_dest=str(dest), uv="uv")
    assert "SKILL.md" in plan["skill_files"] and not dest.exists()       # dry run
    clients.install_skill(str(dest))
    assert (dest / "SKILL.md").is_file() and (dest / "references" / "drawing-spec.md").is_file()
    assert (dest / "subskills" / "engineering-drawing" / "SKILL.md").is_file()


def test_unknown_client():
    with pytest.raises(ValueError):
        clients.setup("vscode")


def _generator():
    spec = importlib.util.spec_from_file_location("gen", os.path.join(ROOT, "scripts", "generate_capabilities.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_capabilities_yaml_is_up_to_date():
    pytest.importorskip("mcp")
    gen = _generator()
    with open(os.path.join(ROOT, "capabilities.yaml"), encoding="utf-8") as fh:
        assert fh.read() == gen.render(), "run scripts/generate_capabilities.py"


def test_manifest_lists_every_server_tool():
    pytest.importorskip("mcp")
    import asyncio
    sys.path.insert(0, ROOT)
    from mcp_server import server
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as fh:
        listed = {t["name"] for t in json.load(fh)["tools"]}
    assert listed == names


def test_skill_references_exist():
    text = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
    import re
    for path in set(re.findall(r"`((?:references|subskills)/[\w./-]+)`", text)):
        assert os.path.exists(os.path.join(ROOT, path)), path
