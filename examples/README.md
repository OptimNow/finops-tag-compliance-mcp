# Configuration Examples

This directory contains example configuration files for connecting Claude Desktop to the FinOps Tag Compliance MCP Server.

## Files

### `claude_desktop_config_local.json`
**Use this for:** Local development with Docker

Configuration for running the MCP server locally via Docker using stdio protocol.

**Setup:**
1. Copy the contents of this file
2. Edit your Claude Desktop config:
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
3. Paste the configuration (or merge with existing config)
4. Update the Docker volume mount path if needed (`~/.aws` → your AWS credentials path)
5. Restart Claude Desktop

### `claude_desktop_config_remote.json`
**Use this for:** Production deployment with remote HTTP server (Recommended)

Configuration for connecting to a remote MCP server via HTTP bridge.

**Setup:**
1. Copy the contents of this file
2. Edit your Claude Desktop config (see paths above)
3. Update the path to `mcp_bridge.py` script (located in `scripts/mcp_bridge.py`)
4. Update `MCP_SERVER_URL` to your deployed server URL
5. Restart Claude Desktop

## Tool Search Optimization (defer_loading)

Both configurations include **Tool Search** optimization with `defer_loading` settings:

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
      "defer_loading": true,  // Set to false to always load this tool
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
3. **Check file path** - Ensure the path to `mcp_bridge.py` is correct
4. **Verify server URL** - Test with `curl http://your-server:8000/health`

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

---

**Built with ❤️ for the FinOps community**
