# Configuration Examples

Example configuration files for connecting Claude Desktop to the FinOps Tag Compliance MCP Server.

## `claude_desktop_config_stdio.json`

Configuration for connecting Claude Desktop directly via stdio transport (recommended).

**Setup:**
1. Install the package:
   ```bash
   pip install finops-tag-compliance-mcp
   ```
2. Configure AWS credentials: `aws configure`
3. Copy the contents of this file to your Claude Desktop config:
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Linux:** `~/.config/Claude/claude_desktop_config.json`
4. Restart Claude Desktop

## `aws_tag_policy_example.json`

Example AWS Organizations tag policy that can be imported using the `import_aws_tag_policy` tool.

## Testing with MCP Inspector

```bash
npx @modelcontextprotocol/inspector python -m mcp_server.stdio_server
```

Opens a browser UI to interactively test all 14 tools.

## Troubleshooting

1. **Check JSON syntax** — Use a JSON validator to ensure no syntax errors
2. **Restart Claude Desktop** — Configuration only loads at startup
3. **Test the server** — Run `python -m mcp_server.stdio_server` to verify it starts without errors
4. **Check logs** — Claude Desktop logs show MCP configuration errors:
   - **Windows:** `%APPDATA%\Claude\logs`
   - **macOS:** `~/Library/Logs/Claude`
