# Tool search configuration guide

**NEW: January 2026** - Optimize your MCP server usage with Claude's Advanced Tool Use features

---

## Table of contents

1. [What is Tool Search?](#what-is-tool-search)
2. [Benefits](#benefits)
3. [How It Works](#how-it-works)
4. [Quick Start](#quick-start)
5. [Recommended Configuration](#recommended-configuration)
6. [Advanced Configuration](#advanced-configuration)
7. [Troubleshooting](#troubleshooting)
8. [Technical Details](#technical-details)

---

## What is tool search?

**Tool Search** is a new feature in Claude's Advanced Tool Use capabilities that enables **dynamic tool discovery**. Instead of loading all tool definitions upfront (which consumes tokens), Claude discovers and loads tools on-demand only when needed.

### The problem it solves

With the traditional approach, when Claude connects to your MCP server with 8 tools:
- All 8 tool definitions with full JSON schemas are loaded into context immediately
- This consumes ~10-15K tokens just describing the tools
- You pay for this token usage on every API call, even if you only use 1-2 tools

### The solution

With Tool Search enabled:
- Only the most frequently used tools are loaded upfront (~2-3 tools)
- Less common tools are discovered on-demand when needed
- Token usage reduced by **85%** (from ~15K to ~2-3K tokens)
- No changes required to your MCP server code

---

## Benefits

### 1. **Cost savings**
- 85% reduction in token usage for tool definitions
- Example: From 150K to 17K tokens per request in large tool libraries
- For this MCP server: ~10-12K token savings per conversation

### 2. **Better performance**
- **Claude Opus 4.5**: Improved from 79.5% to 88.1% tool selection accuracy
- **Claude Opus 4**: Improved from 49% to 74%
- Faster response times with less context to process

### 3. **Scalability**
- As we add tools in Phase 2+ (16 total tools planned), you won't pay for unused tools
- Multi-cloud support in Phase 3 won't bloat your context
- Your token costs stay constant even as we expand the tool library

### 4. **Zero breaking changes**
- Your MCP server continues to work with both old and new clients
- Purely a client-side optimization
- Users can opt-in gradually

---

## How it works

### Traditional approach (without tool search)

```
Claude Desktop connects → Load ALL 8 tools → Use 1-2 tools → Done
                          (~15K tokens)
```

### With tool search enabled

```
Claude Desktop connects → Load 3 core tools → Use check_tag_compliance → Done
                          (~3K tokens)       (already loaded)

Later in conversation → Need generate_report → Discover tool → Load → Use → Done
                                               (~1K tokens)
```

### Tool discovery process

1. You mark tools with `defer_loading: true` in your client configuration
2. Claude receives a lightweight tool list (names + brief descriptions only)
3. When Claude needs a deferred tool, it searches the tool library
4. The full tool definition is loaded on-demand
5. Claude uses the tool normally

---

## Quick start

### Step 1: Add beta header

If you're using the Claude API directly, add this header to your requests:

```json
{
  "anthropic-beta": "mcp-client-2025-11-20"
}
```

If you're using Claude Desktop, this is handled automatically with the MCP connector configuration.

### Step 2: Configure tool loading

Edit your Claude Desktop MCP configuration file:

**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

**For Remote (HTTP) Mode:**

Create a new configuration file alongside your `mcp_bridge.py` script:

**File: `mcp_toolset_config.json`**

```json
{
  "type": "mcp_toolset",
  "mcp_server_name": "finops-tagging",
  "default_config": {
    "enabled": true,
    "defer_loading": false
  },
  "configs": {
    "generate_compliance_report": {
      "enabled": true,
      "defer_loading": true
    },
    "get_violation_history": {
      "enabled": true,
      "defer_loading": true
    },
    "get_cost_attribution_gap": {
      "enabled": true,
      "defer_loading": true
    },
    "suggest_tags": {
      "enabled": true,
      "defer_loading": true
    },
    "validate_resource_tags": {
      "enabled": true,
      "defer_loading": true
    }
  }
}
```

**Then update your Claude Desktop config to reference it:**

```json
{
  "mcpServers": {
    "finops-tagging": {
      "command": "python",
      "args": ["/path/to/mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://your-server:8080",
        "MCP_TOOLSET_CONFIG": "/path/to/mcp_toolset_config.json"
      }
    }
  }
}
```

**For Local (stdio) Mode:**

```json
{
  "mcpServers": {
    "finops-tagging": {
      "command": "python",
      "args": ["-m", "mcp_server.stdio_server"],
      "cwd": "/path/to/finops-tag-compliance-mcp",
      "toolsetConfig": {
        "type": "mcp_toolset",
        "mcp_server_name": "finops-tagging",
        "default_config": {
          "enabled": true,
          "defer_loading": false
        },
        "configs": {
          "generate_compliance_report": {
            "enabled": true,
            "defer_loading": true
          },
          "get_violation_history": {
            "enabled": true,
            "defer_loading": true
          },
          "get_cost_attribution_gap": {
            "enabled": true,
            "defer_loading": true
          },
          "suggest_tags": {
            "enabled": true,
            "defer_loading": true
          },
          "validate_resource_tags": {
            "enabled": true,
            "defer_loading": true
          }
        }
      }
    }
  }
}
```

### Step 3: Restart Claude Desktop

After updating the configuration, restart Claude Desktop for the changes to take effect.

### Step 4: Verify it's working

Ask Claude:
> "Check tag compliance for my EC2 instances"

You should notice:
- Faster initial response
- Claude still has access to all 8 tools
- No difference in functionality, just better performance

---

## Recommended configuration

### Keep loaded (always available)

These 3 core tools should **NOT** have `defer_loading: true`:

| Tool | Why Keep Loaded |
|------|----------------|
| `check_tag_compliance` | Primary use case, used in ~80% of conversations |
| `find_untagged_resources` | Core functionality, frequently requested |
| `get_tagging_policy` | Referenced frequently to understand requirements |

### Defer loading (load on-demand)

These 5 tools can have `defer_loading: true`:

| Tool | Why Defer | Typical Usage |
|------|-----------|---------------|
| `generate_compliance_report` | Used after initial analysis | ~20% of conversations |
| `get_violation_history` | Historical queries only | ~15% of conversations |
| `get_cost_attribution_gap` | Specific financial analysis | ~25% of conversations |
| `suggest_tags` | ML suggestions (specialized) | ~10% of conversations |
| `validate_resource_tags` | Specific resource validation | ~15% of conversations |

**Token Savings:** ~10-12K tokens per conversation (75-80% reduction)

### Alternative: Conservative configuration

If you want to be more conservative, only defer the least-used tools:

**Keep loaded:**
- `check_tag_compliance`
- `find_untagged_resources`
- `get_tagging_policy`
- `get_cost_attribution_gap` (cost analysis is common)

**Defer loading:**
- `generate_compliance_report`
- `get_violation_history`
- `suggest_tags`
- `validate_resource_tags`

**Token Savings:** ~6-8K tokens per conversation (50-60% reduction)

---

## Advanced configuration

### Configuration by use case

**For Initial Compliance Assessment:**
```json
{
  "configs": {
    "check_tag_compliance": {"enabled": true, "defer_loading": false},
    "find_untagged_resources": {"enabled": true, "defer_loading": false},
    "get_cost_attribution_gap": {"enabled": true, "defer_loading": false},
    "get_tagging_policy": {"enabled": true, "defer_loading": false}
  }
}
```
Use this when you primarily do compliance assessments and cost analysis.

**For Ongoing Monitoring:**
```json
{
  "configs": {
    "check_tag_compliance": {"enabled": true, "defer_loading": false},
    "get_violation_history": {"enabled": true, "defer_loading": false},
    "get_tagging_policy": {"enabled": true, "defer_loading": false}
  }
}
```
Use this when you primarily track compliance trends over time.

**For Remediation Work:**
```json
{
  "configs": {
    "find_untagged_resources": {"enabled": true, "defer_loading": false},
    "suggest_tags": {"enabled": true, "defer_loading": false},
    "validate_resource_tags": {"enabled": true, "defer_loading": false},
    "get_tagging_policy": {"enabled": true, "defer_loading": false}
  }
}
```
Use this when you primarily fix tagging violations.

### Disabling specific tools

You can completely disable tools you never use:

```json
{
  "configs": {
    "suggest_tags": {
      "enabled": false
    }
  }
}
```

This is useful if:
- Your organization doesn't allow ML-powered suggestions
- You want to restrict users to specific workflows
- You're debugging and want to isolate specific tools

---

## Troubleshooting

### "Tool not found" error

**Symptom:** Claude says a tool is not available, even though your server provides it.

**Solution:**
1. Check that `enabled: true` in the tool config
2. Verify the tool name matches exactly (case-sensitive)
3. Restart Claude Desktop after config changes
4. **stdio:** Check that `python -m mcp_server.stdio_server` runs without errors
5. **HTTP:** Check your MCP server is running: `curl http://SERVER:8080/health`

### Tools loading slowly

**Symptom:** First time using a deferred tool takes 2-3 seconds.

**This is normal!** The tool definition is being loaded on-demand. Subsequent uses will be fast.

**To fix:** Move frequently-used tools to `defer_loading: false`.

### Configuration not taking effect

**Symptom:** Changes to `defer_loading` don't seem to work.

**Solution:**
1. **Verify config file path** is correct in your `claude_desktop_config.json`
2. **Restart Claude Desktop** - config is only loaded at startup
3. **Check for JSON syntax errors** - use a JSON validator
4. **Check logs** - Claude Desktop logs show MCP configuration loading

**Log locations:**
- **Windows:** `%APPDATA%\Claude\logs`
- **macOS:** `~/Library/Logs/Claude`

### Beta header not recognized

**Symptom:** Error about unsupported beta feature.

**Solution:**
- Ensure you're using Claude API version 2025-11-20 or later
- Update your Claude Desktop to the latest version
- Check that the beta header is exactly: `"anthropic-beta": "mcp-client-2025-11-20"`

---

## Technical details

### How defer_loading works

When `defer_loading: true`:

1. **Initial handshake:**
   - Claude receives tool name, brief description only (~50 tokens per tool)
   - Full JSON schema is NOT loaded

2. **Tool discovery:**
   - When Claude needs the tool, it uses the Tool Search capability
   - Sends a search query for the tool name
   - Server responds with full tool definition

3. **Tool execution:**
   - Full definition is cached for the conversation
   - Tool is used normally
   - No difference in functionality

### Token usage breakdown

**Without Tool Search (8 tools, all loaded):**
```
Tool definitions: 15,000 tokens
User prompt: 500 tokens
Response: 2,000 tokens
Total: 17,500 tokens
```

**With Tool Search (3 loaded, 5 deferred):**
```
Tool definitions: 3,000 tokens (3 full definitions)
Tool search stubs: 250 tokens (5 lightweight stubs)
User prompt: 500 tokens
Response: 2,000 tokens
Total: 5,750 tokens
```

**Savings:** 11,750 tokens per conversation (67% reduction)

If a deferred tool is used:
```
Additional cost: 1,500 tokens (one-time per tool per conversation)
New total: 7,250 tokens
Still 58% savings!
```

### MCP protocol changes

The Tool Search feature uses an extension to the MCP protocol:

**Standard MCP `tools/list` response:**
```json
{
  "tools": [
    {
      "name": "check_tag_compliance",
      "description": "...",
      "inputSchema": { /* full JSON schema */ }
    }
  ]
}
```

**With defer_loading:**
```json
{
  "tools": [
    {
      "name": "check_tag_compliance",
      "description": "...",
      "defer_loading": true
    }
  ]
}
```

When Claude needs the full definition, it calls `tools/get`:
```json
{
  "method": "tools/get",
  "params": {
    "name": "check_tag_compliance"
  }
}
```

**Your MCP server doesn't need to implement this** - the MCP connector handles the translation automatically.

### Compatibility

**Supported:**
- Claude API version 2025-11-20 or later
- Claude Desktop with MCP support (December 2025+)
- All MCP server implementations (no code changes needed)

**Not supported:**
- Older Claude API versions (will ignore `defer_loading`)
- Custom MCP clients without Tool Search support (will load all tools)

**Graceful degradation:** If Tool Search is not supported, all tools load normally (no errors).

---

## References

- [Anthropic Advanced Tool Use Documentation](https://www.anthropic.com/engineering/advanced-tool-use)
- [Claude Platform Docs: Tool Search Tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- [MCP Connector Documentation](https://platform.claude.com/docs/en/agents-and-tools/mcp-connector)
- [FinOps Tag Compliance MCP Server User Manual](./USER_MANUAL.md)

---

## Feedback & support

Have questions or suggestions about Tool Search configuration?

- **GitHub Issues:** [OptimNow/finops-tag-compliance-mcp/issues](https://github.com/OptimNow/finops-tag-compliance-mcp/issues)
- **Documentation:** [docs/](../)
- **User Manual:** [USER_MANUAL.md](./USER_MANUAL.md)

---

**Built with ❤️ for the FinOps community**
