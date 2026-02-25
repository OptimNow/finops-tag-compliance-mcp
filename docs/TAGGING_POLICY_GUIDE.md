# Tagging policy configuration guide

**For:** FinOps Tag Compliance MCP Server
**Audience:** FinOps practitioners, cloud engineers, compliance teams

---

## Policy sources (priority order)

On startup, the MCP server determines which tagging policy to use:

| Priority | Source | When |
|----------|--------|------|
| 1 | **Existing file** at `POLICY_PATH` | `policies/tagging_policy.json` already exists |
| 2 | **AWS Organizations** import | File doesn't exist + `AUTO_IMPORT_AWS_POLICY=true` |
| 3 | **Default policy** | Import fails/disabled + `FALLBACK_TO_DEFAULT_POLICY=true` |

By default the policy file lives at `policies/tagging_policy.json` in the repository root. This path can be overridden via the `POLICY_PATH` environment variable (e.g., `/mnt/efs/tagging_policy.json` in containerized deployments).

---

## Create your tagging policy

Use the online Tagging Policy Generator to create, edit, and customize your tagging policy:

👉 **https://tagpolgenerator.optimnow.io/**

The generator lets you:
- Define required and optional tags
- Set allowed values and validation rules (regex)
- Specify which resource types each tag applies to
- Import and convert AWS Organizations tag policies
- Export the policy as JSON

For technical details about the policy format and schema, see the [Tagging Policy Generator GitHub repository](https://github.com/OptimNow/tagging-policy-generator).

---

## Deploy your policy

### Local (stdio MCP)

If you're running the MCP server locally via Claude Desktop:

1. Save the policy JSON to `policies/tagging_policy.json` in the repository root
2. Restart the MCP server (restart Claude Desktop, or re-run `python -m mcp_server.stdio_server`)
3. Verify in Claude Desktop: *"Show me my tagging policy"*

**Import from AWS Organizations:**

In Claude Desktop, ask:
```
Import my AWS Organizations tagging policy and save it
```

This calls the `import_aws_tag_policy` tool, which fetches your AWS Orgs policy,
converts it to MCP format, and saves it to `policies/tagging_policy.json`.

### Remote / production server

If you're running the MCP server on a remote host (e.g., ECS Fargate with EFS),
the policy is loaded from the path configured via `POLICY_PATH`
(default: `/mnt/efs/tagging_policy.json` in containerized deployments).

**Option A — Auto-import from AWS Organizations (recommended):**

The server automatically imports your AWS Organizations tag policy on first boot
when `AUTO_IMPORT_AWS_POLICY=true` (the default). To force a re-import:

1. **Via Claude Desktop** — ask Claude to call the `import_aws_tag_policy` tool:
   ```
   Import my AWS Organizations tagging policy and save it
   ```

2. **Via the server's HTTP API** (if your deployment exposes one):
   ```bash
   curl -X POST https://YOUR_SERVER/mcp/tools/call \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -d '{
       "name": "import_aws_tag_policy",
       "arguments": {"save_to_file": true}
     }'
   ```

3. **Via container shell** — delete the cached file and restart:
   ```bash
   # Delete cached policy to force re-import on next restart
   rm /path/to/tagging_policy.json

   # Restart the service to trigger auto-import
   ```

**Option B — Upload a custom policy:**

1. Generate the policy at https://tagpolgenerator.optimnow.io/
2. Copy the JSON file to the server's `POLICY_PATH` location
3. Restart the server

---

## Refreshing the policy after AWS Orgs changes

When you update your AWS Organizations tag policy, the MCP server **does not** automatically sync. You need to manually trigger a re-import.

### Method 1: Use the `import_aws_tag_policy` MCP tool (simplest)

This works for **both local and remote** deployments. In Claude Desktop, say:
```
Refresh my tagging policy from AWS Organizations
```

This calls the `import_aws_tag_policy` tool which:
1. Fetches the latest policy from AWS Organizations
2. Converts `@@assign` syntax to MCP format (expands `ALL_SUPPORTED` wildcards)
3. Saves to `policies/tagging_policy.json` (or the configured `POLICY_PATH`)
4. Returns the converted policy for review

You can also list available policies first:
```
List my AWS Organizations tag policies
```

Or import a specific policy by ID:
```
Import AWS Organizations tag policy p-95u05v7n5f
```

### Method 2: Replace the policy file manually

**Local:** Replace `policies/tagging_policy.json` and restart the server.

**Remote:** Delete or overwrite the cached policy file on the server, then restart
the service. On restart, auto-import will re-fetch from AWS Organizations.

---

## Verifying your policy

After deploying or refreshing, verify the policy loaded correctly.

**In Claude Desktop** (works for both local and remote):
```
Show me our tagging policy
```

Claude should return your complete policy configuration with all required tags and their rules.

**Via HTTP API** (remote deployments only):
```bash
curl -X POST https://YOUR_SERVER/mcp/tools/call \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"name": "get_tagging_policy", "arguments": {}}'
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POLICY_PATH` | `policies/tagging_policy.json` | Path to policy file (EFS: `/mnt/efs/tagging_policy.json`) |
| `AUTO_IMPORT_AWS_POLICY` | `true` | Auto-import from AWS Orgs if file doesn't exist |
| `AUTO_IMPORT_POLICY_ID` | *(none)* | Specific AWS Orgs policy ID (e.g., `p-95u05v7n5f`) |
| `FALLBACK_TO_DEFAULT_POLICY` | `true` | Create default policy if import fails |

---

## Converting AWS Organizations tag policies

The `import_aws_tag_policy` tool converts AWS Organizations format to MCP format:

**AWS Organizations format:**
```json
{
  "tags": {
    "Environment": {
      "tag_key": {"@@assign": "Environment"},
      "tag_value": {"@@assign": ["production", "staging"]},
      "enforced_for": {"@@assign": ["ec2:ALL_SUPPORTED"]}
    }
  }
}
```

**MCP format (after conversion):**
```json
{
  "version": "1.0",
  "required_tags": [
    {
      "name": "Environment",
      "allowed_values": ["production", "staging"],
      "applies_to": ["ec2:instance", "ec2:volume"]
    }
  ]
}
```

Key conversions:
- `@@assign` values → `allowed_values`
- `ALL_SUPPORTED` → expanded to specific resource types
- `ec2:*` wildcards → expanded (`ec2:instance`, `ec2:volume`, etc.)
- `enforced_for` → `applies_to`

---

## Troubleshooting

### "No tagging policy configured"

**Cause:** Policy file not found and auto-import failed

**Fix:**
1. Check that `policies/tagging_policy.json` exists (or the path set in `POLICY_PATH`)
2. Check server logs for `AutoPolicy:` messages
3. Verify IAM role has `organizations:ListPolicies` and `organizations:DescribePolicy` permissions
4. Try manual import: call `import_aws_tag_policy` tool

### "Invalid policy format"

**Cause:** JSON syntax error in policy file

**Fix:**
1. Validate JSON at [jsonlint.com](https://jsonlint.com)
2. Re-import from AWS Organizations
3. Re-export from the generator if using a custom policy

### Policy changes not reflected

**Cause:** Server using cached policy in memory

**Fix:**
1. Call `import_aws_tag_policy` with `save_to_file: true` to overwrite
2. Restart the MCP server (restart Claude Desktop for local, or restart the service for remote)
3. If using Redis caching, flush the cache: `redis-cli FLUSHALL`

### Auto-import not working

**Cause:** Missing IAM permissions or no AWS Orgs policy

**Fix:**
1. Check IAM role has `organizations:ListPolicies` and `organizations:DescribePolicy`
2. Verify you have a tag policy: `aws organizations list-policies --filter TAG_POLICY`
3. Check server logs for `AutoPolicy:` errors
4. Set `AUTO_IMPORT_POLICY_ID` to your specific policy ID

---

## Best practices

### Start small

Don't try to enforce 20 tags on day one. Start with 3-4 critical tags:
- **CostCenter** - for cost allocation
- **Owner** - for accountability
- **Environment** - for risk management

Add more tags as your organization matures.

### Use AWS Organizations as source of truth

Keep your tag policy in AWS Organizations and use auto-import. This ensures:
- Single source of truth across all accounts
- Tag enforcement at the Organizations level
- MCP server stays in sync with a simple refresh

### Use allowed values wisely

Only use `allowed_values` when you truly need to restrict options:
- ✅ Environment: `["production", "staging", "development"]` - limited set
- ❌ Application: Don't restrict - too many possible values

### Review regularly

Set a quarterly reminder to review your tagging policy:
- Are all required tags still necessary?
- Do we need new tags for new compliance requirements?
- Are allowed values still accurate?

---

## Related documentation

- [User Manual](USER_MANUAL.md) - How to use the MCP tools
- [UAT Protocol](UAT_OPEN_SOURCE.md) - Testing procedures
- [IAM Permissions](security/IAM_PERMISSIONS.md) - Required AWS permissions
- [Tagging Policy Generator](https://github.com/OptimNow/tagging-policy-generator) - Technical details and schema

---

**Last Updated:** February 24, 2026
