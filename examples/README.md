# Configuration Examples

This directory contains example configuration files for connecting Claude Desktop to the FinOps Tag Compliance MCP Server.

## Two Connection Methods

| Method | Config File | When to Use |
|--------|-------------|-------------|
| **stdio (Recommended)** | `claude_desktop_config_stdio.json` | Local development, single user, MCP Inspector |
| **HTTP + Bridge** | `claude_desktop_config_local.json` / `_remote.json` | Remote EC2 deployment, shared server, Docker |

### Why stdio is recommended for local use

- **No bridge script** -- Claude Desktop connects directly to the MCP server
- **No Docker required** -- Runs as a Python process
- **MCP Inspector compatible** -- Test with `npx @modelcontextprotocol/inspector python -m mcp_server.stdio_server`
- **Standard MCP protocol** -- Uses the official MCP wire format (JSON-RPC over stdin/stdout)

---

## Files

### `claude_desktop_config_stdio.json` (Recommended for local)
**Use this for:** Local development without Docker

Configuration for connecting to the MCP server directly via stdio transport. No bridge script needed.

**Setup:**
1. Clone the repository and install dependencies:
   ```bash
   git clone https://github.com/OptimNow/finops-tag-compliance-mcp.git
   cd finops-tag-compliance-mcp
   pip install -e .
   ```
2. Configure AWS credentials: `aws configure`
3. Copy the contents of this file
4. Edit your Claude Desktop config:
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
5. Update the `cwd` path to your repository location
6. Restart Claude Desktop

### `claude_desktop_config_local.json`
**Use this for:** Local development with Docker (HTTP transport)

Configuration for connecting to a locally-running MCP server via the HTTP bridge.

**Setup:**
1. Start your local MCP server: `docker-compose up -d`
2. Copy the contents of this file
3. Edit your Claude Desktop config (see paths above)
4. Update the path to `mcp_bridge.py` script (located in `scripts/mcp_bridge.py`)
5. Restart Claude Desktop

### `claude_desktop_config_remote.json`
**Use this for:** Production deployment with remote HTTP server

Configuration for connecting to a remote MCP server via the HTTP bridge. Required when the server runs on a different machine (e.g., EC2).

**Setup:**
1. Copy the contents of this file
2. Edit your Claude Desktop config (see paths above)
3. Update the path to `mcp_bridge.py` script (located in `scripts/mcp_bridge.py`)
4. Update `MCP_SERVER_URL` to your deployed server URL
5. Restart Claude Desktop

---

## Testing with MCP Inspector

The stdio transport is compatible with the MCP Inspector developer tool:

```bash
# Launch Inspector UI in your browser
npx @modelcontextprotocol/inspector python -m mcp_server.stdio_server
```

This opens a browser-based interface where you can:
- See all 8 registered tools
- Call tools interactively with test parameters
- Inspect JSON-RPC request/response payloads

---

## Tool Search Optimization (defer_loading)

Both HTTP configurations include **Tool Search** optimization with `defer_loading` settings. The stdio configuration does not need this -- Tool Search is a client-side optimization configured separately.

### Tools That Load Immediately (Always Available)
- `check_tag_compliance` - Primary compliance scanning
- `find_untagged_resources` - Finding untagged resources
- `get_tagging_policy` - Viewing policy configuration

### Tools That Load On-Demand (defer_loading: true)
- `generate_compliance_report` - Generating reports
- `get_violation_history` - Historical compliance data
- `get_cost_attribution_gap` - Cost impact analysis
- `suggest_tags` - ML-powered tag suggestions
- `validate_resource_tags` - Validating specific resources

**Benefits:**
- **85% token cost reduction** for tool definitions
- Faster response times
- Better accuracy in tool selection
- No functionality changes - all tools still available when needed

### Customizing Tool Loading

You can customize which tools are deferred by editing the `defer_loading` setting:

```json
{
  "configs": {
    "tool_name": {
      "enabled": true,
      "defer_loading": true,
      "description": "..."
    }
  }
}
```

**When to keep a tool loaded (defer_loading: false):**
- You use it in >30% of conversations
- It's needed for initial assessment
- Fast response time is critical

**When to defer a tool (defer_loading: true):**
- Used in <30% of conversations
- Specialized or advanced use case
- Cost optimization is priority

## Beta Header

The `"anthropic-beta": "mcp-client-2025-11-20"` header enables the Tool Search feature. This is required for `defer_loading` to work.

**If you're using an older version of Claude Desktop:**
- Remove the `anthropic-beta` line
- Remove the `toolsets` section
- All tools will load normally (no optimization, but still functional)

## Troubleshooting

### Configuration Not Working
1. **Check JSON syntax** - Use a JSON validator to ensure no syntax errors
2. **Restart Claude Desktop** - Configuration only loads at startup
3. **stdio:** Check that `python -m mcp_server.stdio_server` runs without errors
4. **HTTP:** Check file path to `mcp_bridge.py` and verify server URL with `curl http://your-server:8080/health`

### Tools Not Loading
1. **Check enabled flag** - Ensure `"enabled": true` for all tools you want to use
2. **Verify tool names** - Tool names are case-sensitive and must match exactly
3. **Check logs** - Claude Desktop logs show MCP configuration errors
   - **Windows:** `%APPDATA%\Claude\logs`
   - **macOS:** `~/Library/Logs/Claude`

### Slow Tool Loading
If a deferred tool takes 2-3 seconds on first use, this is normal! The tool is being loaded on-demand. Set `defer_loading: false` for tools you use frequently.

## Additional Resources

- **[Tool Search Configuration Guide](../docs/TOOL_SEARCH_CONFIGURATION.md)** - Detailed setup and optimization guide
- **[User Manual](../docs/USER_MANUAL.md)** - How to use the MCP server
- **[Deployment Guide](../docs/DEPLOYMENT.md)** - Deploy the server
- **[README](../README.md)** - Project overview

## Support

- **GitHub Issues:** [OptimNow/finops-tag-compliance-mcp/issues](https://github.com/OptimNow/finops-tag-compliance-mcp/issues)
- **Documentation:** [docs/](../docs/)
