# Tagging Policy Configuration Guide

**For:** FinOps Tag Compliance MCP Server  
**Audience:** FinOps practitioners, cloud engineers, compliance teams

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

### Local Deployment

If you're running the MCP server locally with Docker:

1. Save the policy JSON from the generator to `policies/tagging_policy.json` in your repository
2. Restart Docker: `docker-compose restart`
3. Test in Claude Desktop: "Show me my tagging policy"

### Remote EC2 Deployment

If your MCP server is deployed on EC2:

1. Save the policy JSON from the generator to `policies/tagging_policy.json` in your local repository

2. Run the deploy script:
   ```powershell
   # Windows
   .\scripts\deploy_policy.ps1
   ```

3. Verify the policy is in S3:
   ```bash
   aws s3 ls s3://finops-mcp-config/policies/
   ```

4. Test in Claude Desktop: "Show me my tagging policy"

> **Note:** If the deploy script fails with SSM errors, see the [Deployment Guide troubleshooting section](DEPLOYMENT.md#troubleshooting) for manual workarounds.

---

## Converting AWS Organizations Tag Policies

If you already have an AWS Organizations tag policy, you can convert it to the MCP format:

1. Go to https://tagpolgenerator.optimnow.io/
2. Use the **Import** feature to upload your AWS Organizations policy
3. Review and edit the converted policy
4. Export and deploy using the steps above

---

## Verifying Your Policy

After deploying, verify the policy loaded correctly:

**In Claude Desktop:**
```
Show me our tagging policy
```

Claude should return your complete policy configuration with all required tags and their rules.

**Direct API call (local):**
```bash
curl http://localhost:8080/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name": "get_tagging_policy", "arguments": {}}'
```

---

## Troubleshooting

### "No tagging policy configured"

**Cause:** Policy file not found or not mounted into container

**Fix:**
1. Check file exists at `policies/tagging_policy.json`
2. For local: Verify `docker-compose.yml` has the volume mount
3. For EC2: Verify the policy was pulled from S3
4. Restart the container

### "Invalid policy format"

**Cause:** JSON syntax error in policy file

**Fix:**
1. Validate JSON at [jsonlint.com](https://jsonlint.com)
2. Check for missing commas, brackets, or quotes
3. Re-export from the generator if needed

### Policy changes not reflected

**Cause:** Container using cached policy

**Fix:**
1. Local: `docker-compose restart`
2. EC2: `docker restart tagging-mcp-server`
3. Flush Redis cache if needed: `docker exec tagging-redis redis-cli FLUSHALL`

---

## Best Practices

### Start Small

Don't try to enforce 20 tags on day one. Start with 3-4 critical tags:
- **CostCenter** - for cost allocation
- **Owner** - for accountability  
- **Environment** - for risk management

Add more tags as your organization matures.

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
- [UAT Protocol](UAT_PROTOCOL.md) - Testing procedures
- [Tagging Policy Generator](https://github.com/OptimNow/tagging-policy-generator) - Technical details and schema

---

**Last Updated:** January 9, 2025
