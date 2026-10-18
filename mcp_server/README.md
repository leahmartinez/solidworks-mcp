# swdraw MCP server

A stdio MCP server exposing the swdraw tools. Every tool runs `python -m swdraw <command>` in a
fresh subprocess and returns its JSON result, so a COM error or a stuck SolidWorks call can't take
the server down (calls time out after `SWDRAW_TIMEOUT_S`, default 600 s).

## Run it

```powershell
uv run --directory C:\path\to\swdraw --extra mcp --extra preview python mcp_server/server.py
```

Register it with a client in one go: `uv run python -m swdraw setup <claude-code|claude-desktop|codex> --apply`
(see the main README). Or install the `.mcpb` in Claude Desktop.

For a manual client config:

```json
{
  "mcpServers": {
    "swdraw": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\path\\to\\swdraw", "--extra", "mcp", "--extra", "preview",
               "python", "mcp_server/server.py"],
      "env": {"SWDRAW_OUTPUT_DIR": "C:\\Users\\you\\swdraw-output"}
    }
  }
}
```

## Environment

| Variable | Purpose |
|---|---|
| `SWDRAW_OUTPUT_DIR` | traces, JSON results, PDF and PNG exports (default `~/swdraw-output`) |
| `SWDRAW_PROFILES` | folder with your `house_style`, `title_block`, `numbering` profiles |
| `SWDRAW_SCRIPTS_DIR` | the only folder `swdraw_run_script` may run `.py` files from |
| `SWDRAW_TIMEOUT_S` | per-call timeout in seconds |

## Tools

See `../capabilities.yaml` for every tool, its arguments, whether it needs SolidWorks and what it
changes. Pass absolute paths: the server's working directory is the repository folder.

The server supports the MCP Python SDK 1.x (`FastMCP`) and 2.x (`MCPServer`).
