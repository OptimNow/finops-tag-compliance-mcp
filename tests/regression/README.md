# Regression Test Suite (promptfoo)

Non-regression tests for the 8 MCP tools using [promptfoo](https://promptfoo.dev).

## Quick Start

```bash
# 1. Install promptfoo (one-time)
npm install -g promptfoo

# 2. Start the MCP server (in a separate terminal)
cd /path/to/finops-tag-compliance-mcp
python run_server.py

# 3. Run tests
cd tests/regression
promptfoo eval

# 4. View results in browser
promptfoo view
```

## What's Tested

| Tool | Tests | What's Checked |
|------|-------|----------------|
| `check_tag_compliance` | 4 | Response structure, score range, violation format, severity filter, multi-region metadata |
| `find_untagged_resources` | 4 | Resource list, cost inclusion, resource structure, region filter |
| `validate_resource_tags` | 3 | ARN validation, result structure, count consistency |
| `get_cost_attribution_gap` | 3 | Spend fields, group_by breakdown, math consistency |
| `suggest_tags` | 2 | Suggestion structure, confidence scores |
| `get_tagging_policy` | 4 | Policy shape, required tag structure, known tags, idempotency |
| `generate_compliance_report` | 4 | JSON/Markdown/CSV formats, recommendations |
| `get_violation_history` | 4 | Data points, grouping (day/week/month), structure |
| Error handling | 4 | Invalid tool, invalid params, edge cases |
| Performance | 2 | Latency for no-AWS-call tools |

**Total: 34 test cases**

## Architecture

```
tests/regression/
  promptfooconfig.yaml   # Test definitions and assertions
  mcp_provider.py        # Custom provider calling POST /mcp/tools/call
  README.md              # This file
```

The custom provider (`mcp_provider.py`) translates promptfoo test cases into
HTTP calls to the MCP server's `/mcp/tools/call` endpoint.

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `MCP_SERVER_URL` | `http://localhost:8080` | MCP server base URL |
| `MCP_API_KEY` | (empty) | API key for authentication |
| `MCP_TIMEOUT` | `120` | Request timeout in seconds |

### Testing against production

```bash
MCP_SERVER_URL=https://mcp.optimnow.io MCP_API_KEY=your-key promptfoo eval
```

### Testing against dev server

```bash
MCP_SERVER_URL=http://54.224.243.105:8080 promptfoo eval
```

## Assertion Types Used

- **`is-json`** - Response is valid JSON
- **`javascript`** - Custom JS assertions for structure/value validation
- **`latency`** - Response time thresholds

## Adding New Tests

When adding a new MCP tool (Phase 2+), add test cases following this pattern:

```yaml
- description: "new_tool_name - basic functionality"
  vars:
    tool_call: |
      {"name": "new_tool_name", "arguments": {"param1": "value1"}}
  assert:
    - type: is-json
    - type: javascript
      value: |
        const data = JSON.parse(output);
        return data.expected_field !== undefined;
```

## CI Integration

Add to your CI pipeline:

```yaml
# GitHub Actions example
- name: Run regression tests
  run: |
    npx promptfoo@latest eval --config tests/regression/promptfooconfig.yaml
  env:
    MCP_SERVER_URL: ${{ secrets.MCP_SERVER_URL }}
    MCP_API_KEY: ${{ secrets.MCP_API_KEY }}
```

promptfoo returns exit code 1 if any assertions fail, making it CI-friendly.
