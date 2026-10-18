# swdraw MCP server

A stdio MCP server for the swdraw tools. Each tool runs `python -m swdraw <command>` in a new
subprocess and returns the JSON result. A COM error or a stuck SolidWorks call can't take the
server down. Calls time out after `SWDRAW_TIMEOUT_S` (default 600 s).

## Run it

```powershell
uv run --directory C:\path\to\swdraw --extra mcp --extra preview python mcp_server/server.py
```

To register it with a client, run `uv run python -m swdraw setup <claude-code|claude-desktop|codex> --apply`
(see the main README), or install the `.mcpb` in Claude Desktop.

Manual client config:

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
| `SWDRAW_BACKUP_DIR` | where `swdraw_model_edit` copies a part before saving it (default: next to the part) |
| `SWDRAW_TIMEOUT_S` | per-call timeout in seconds |

## Tools

`../capabilities.yaml` lists every tool, its arguments, whether it needs SolidWorks and what it
changes. Use absolute paths, because the server runs from the repo folder.

Works with MCP Python SDK 1.x (`FastMCP`) and 2.x (`MCPServer`).
