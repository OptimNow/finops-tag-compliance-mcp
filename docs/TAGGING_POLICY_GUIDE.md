# Tagging Policy Configuration Guide

**For:** FinOps Tag Compliance MCP Server
**Audience:** FinOps practitioners, cloud engineers, compliance teams

---

## Policy Sources (Priority Order)

On startup, the MCP server determines which tagging policy to use:

| Priority | Source | When |
|----------|--------|------|
| 1 | **Existing file** on EFS | `/mnt/efs/tagging_policy.json` already exists |
| 2 | **AWS Organizations** import | File doesn't exist + `AUTO_IMPORT_AWS_POLICY=true` |
| 3 | **Default policy** | Import fails/disabled + `FALLBACK_TO_DEFAULT_POLICY=true` |

In production (ECS Fargate), the policy lives on EFS at `/mnt/efs/tagging_policy.json`. On first boot, it is auto-imported from your AWS Organizations tag policy.

---

## Create Your Tagging Policy

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

## Deploy Your Policy

### ECS Fargate (Production)

The production server at `https://mcp.optimnow.io` loads its policy from EFS.

**Option A — Auto-import from AWS Organizations (recommended):**

The server automatically imports your AWS Organizations tag policy on first boot. To force a re-import (e.g., after updating your AWS Orgs policy):

1. **Via Claude Desktop** — ask Claude to call the `import_aws_tag_policy` tool:
   ```
   Import my AWS Organizations tagging policy and save it
   ```
   Claude will call the tool, which fetches your AWS Orgs policy, converts it to MCP format, and saves it to `/mnt/efs/tagging_policy.json`.

2. **Via API call:**
   ```bash
   curl -X POST https://mcp.optimnow.io/mcp/tools/call \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -d '{
       "name": "import_aws_tag_policy",
       "arguments": {"save_to_file": true}
     }'
   ```

3. **Via ECS Exec** — delete the cached file and restart:
   ```bash
   TASK_ID=$(aws ecs list-tasks --cluster mcp-tagging-cluster-prod \
     --service mcp-tagging-service-prod --query 'taskArns[0]' --output text)

   # Delete cached policy to force re-import on next restart
   aws ecs execute-command --cluster mcp-tagging-cluster-prod \
     --task $TASK_ID --container mcp-server --interactive \
     --command "rm /mnt/efs/tagging_policy.json"

   # Force new deployment (restarts task, triggers auto-import)
   aws ecs update-service --cluster mcp-tagging-cluster-prod \
     --service mcp-tagging-service-prod --force-new-deployment
   ```

**Option B — Upload a custom policy:**

1. Generate the policy at https://tagpolgenerator.optimnow.io/
2. Upload it to the ECS container via ECS Exec:
   ```bash
   TASK_ID=$(aws ecs list-tasks --cluster mcp-tagging-cluster-prod \
     --service mcp-tagging-service-prod --query 'taskArns[0]' --output text)

   # Copy policy via base64 encoding
   POLICY_B64=$(base64 -w0 policies/tagging_policy.json)
   aws ecs execute-command --cluster mcp-tagging-cluster-prod \
     --task $TASK_ID --container mcp-server --interactive \
     --command "echo $POLICY_B64 | base64 -d > /mnt/efs/tagging_policy.json"
   ```

### Local Development

If you're running the MCP server locally:

1. Save the policy JSON to `policies/tagging_policy.json` in the repository
2. Restart the server: `docker-compose restart` or re-run `python -m mcp_server.stdio_server`
3. Test in Claude Desktop: "Show me my tagging policy"

---

## Refreshing the Policy After AWS Orgs Changes

When you update your AWS Organizations tag policy, the MCP server **does not** automatically sync. You need to manually trigger a re-import:

### Method 1: Use the `import_aws_tag_policy` MCP tool (simplest)

In Claude Desktop, say:
```
Refresh my tagging policy from AWS Organizations
```

This calls the `import_aws_tag_policy` tool which:
1. Fetches the latest policy from AWS Organizations
2. Converts `@@assign` syntax to MCP format (expands `ALL_SUPPORTED` wildcards)
3. Saves to `/mnt/efs/tagging_policy.json`
4. Returns the converted policy for review

You can also list available policies first:
```
List my AWS Organizations tag policies
```

Or import a specific policy by ID:
```
Import AWS Organizations tag policy p-95u05v7n5f
```

### Method 2: Delete cached file + restart

```bash
# Delete the EFS-cached policy
aws ecs execute-command --cluster mcp-tagging-cluster-prod \
  --task $TASK_ID --container mcp-server --interactive \
  --command "rm /mnt/efs/tagging_policy.json"

# Restart — auto-import will re-fetch from AWS Orgs
./scripts/deploy_ecs.sh --deploy-only
```

---

## Verifying Your Policy

After deploying or refreshing, verify the policy loaded correctly:

**In Claude Desktop:**
```
Show me our tagging policy
```

Claude should return your complete policy configuration with all required tags and their rules.

**Direct API call:**
```bash
curl -X POST https://mcp.optimnow.io/mcp/tools/call \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"name": "get_tagging_policy", "arguments": {}}'
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POLICY_PATH` | `policies/tagging_policy.json` | Path to policy file (EFS: `/mnt/efs/tagging_policy.json`) |
| `AUTO_IMPORT_AWS_POLICY` | `true` | Auto-import from AWS Orgs if file doesn't exist |
| `AUTO_IMPORT_POLICY_ID` | *(none)* | Specific AWS Orgs policy ID (e.g., `p-95u05v7n5f`) |
| `FALLBACK_TO_DEFAULT_POLICY` | `true` | Create default policy if import fails |

---

## Converting AWS Organizations Tag Policies

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
1. Check EFS mount: `ls -la /mnt/efs/` via ECS Exec
2. Check container logs for `AutoPolicy:` messages
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
2. Or restart the ECS service: `./scripts/deploy_ecs.sh --deploy-only`
3. Flush Redis cache if needed via ECS Exec: `redis-cli FLUSHALL`

### Auto-import not working

**Cause:** Missing IAM permissions or no AWS Orgs policy

**Fix:**
1. Check IAM role has `organizations:ListPolicies` and `organizations:DescribePolicy`
2. Verify you have a tag policy: `aws organizations list-policies --filter TAG_POLICY`
3. Check container logs for `AutoPolicy:` errors
4. Set `AUTO_IMPORT_POLICY_ID` to your specific policy ID

---

## Best Practices

### Start Small

Don't try to enforce 20 tags on day one. Start with 3-4 critical tags:
- **CostCenter** - for cost allocation
- **Owner** - for accountability
- **Environment** - for risk management

Add more tags as your organization matures.

### Use AWS Organizations as Source of Truth

Keep your tag policy in AWS Organizations and use auto-import. This ensures:
- Single source of truth across all accounts
- Tag enforcement at the Organizations level
- MCP server stays in sync with a simple refresh

### Use Allowed Values Wisely

Only use `allowed_values` when you truly need to restrict options:
- ✅ Environment: `["production", "staging", "development"]` - limited set
- ❌ Application: Don't restrict - too many possible values

### Review Regularly

Set a quarterly reminder to review your tagging policy:
- Are all required tags still necessary?
- Do we need new tags for new compliance requirements?
- Are allowed values still accurate?

---

## Related Documentation

- [Deployment Guide](DEPLOYMENT.md) - How to deploy the MCP server
- [UAT Protocol](PHASE_2_UAT_PROTOCOL.md) - Testing procedures
- [Tagging Policy Generator](https://github.com/OptimNow/tagging-policy-generator) - Technical details and schema

---

**Last Updated:** February 20, 2026
