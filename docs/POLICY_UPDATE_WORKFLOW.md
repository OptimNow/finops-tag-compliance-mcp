# Tagging Policy Update Workflow

**For:** FinOps practitioners using the Tag Compliance MCP Server  
**Purpose:** How to create, update, and deploy tagging policies using the Policy Generator

---

## Overview

The FinOps Tag Compliance MCP Server uses a JSON policy file to define your organization's tagging rules. This guide explains:

1. How to generate a new policy using the Policy Generator
2. How to update your policy without rebuilding Docker
3. The complete workflow from policy creation to deployment

---

## Quick Reference

| Task | Command/Action |
|------|----------------|
| Generate new policy | Use Policy Generator web app or Claude |
| Policy file location | `policies/tagging_policy.json` |
| Apply changes (local Docker) | Policy auto-reloads on next API call |
| Apply changes (EC2) | `docker restart finops-mcp-server` |

---

## The Policy Generator

The Policy Generator is a web-based tool that helps you create tagging policies without writing JSON manually.

### Option 1: Use the Policy Generator Web App

If you have the Policy Generator deployed (see `docs/POLICY_GENERATOR_PROMPT.md`):

1. Open the Policy Generator in your browser
2. Choose "Create from Scratch" or "Import AWS Policy"
3. Fill in your required tags, allowed values, and resource types
4. Click "Download JSON" to save `tagging_policy.json`
5. Copy the file to your `policies/` folder

### Option 2: Use Claude to Generate a Policy

You can ask Claude (or any AI assistant) to generate a policy for you:

**Example prompt:**
```
Generate a tagging policy JSON for my organization with these requirements:
- Required tags: CostCenter (values: Engineering, Marketing, Sales), Owner (email format), Environment (production, staging, dev)
- Optional tags: Project, Team
- Apply to all resource types
- Use the FinOps Tag Compliance MCP Server format
```

### Option 3: Convert from AWS Organizations Tag Policy

If you already have an AWS Organizations tag policy:

```powershell
# Convert AWS policy to MCP format
python scripts/convert_aws_policy.py path/to/aws_policy.json
```

---

## Policy File Structure

Your policy file (`policies/tagging_policy.json`) has this structure:

```json
{
  "version": "1.1",
  "last_updated": "2026-01-08T00:00:00Z",
  "required_tags": [
    {
      "name": "CostCenter",
      "description": "Department for cost allocation",
      "allowed_values": ["Engineering", "Marketing", "Sales"],
      "validation_regex": null,
      "applies_to": []
    }
  ],
  "optional_tags": [
    {
      "name": "Project",
      "description": "Project identifier",
      "allowed_values": null
    }
  ],
  "tag_naming_rules": {
    "case_sensitivity": false,
    "allow_special_characters": false,
    "max_key_length": 128,
    "max_value_length": 256
  }
}
```

**Key fields:**
- `applies_to: []` = applies to ALL resource types (wildcard)
- `allowed_values: null` = any value is accepted
- `validation_regex` = regex pattern for value validation (e.g., email format)

---

## Updating Your Policy

### Local Docker Setup (Recommended for Testing)

When running Docker locally, you can update the policy dynamically without restarting:

**Step 1: Mount a local policies folder**

```powershell
# Create a folder for your policies (if not exists)
mkdir C:\Users\YourName\mcp-policies

# Copy current policy
copy policies\tagging_policy.json C:\Users\YourName\mcp-policies\
```

**Step 2: Run Docker with mounted volume**

```powershell
docker run -d -p 8080:8080 --name finops-mcp-server `
  --env-file .env `
  -v ${HOME}/.aws:/root/.aws:ro `
  -v C:\Users\YourName\mcp-policies:/app/policies `
  finops-mcp-server
```

**Step 3: Update the policy anytime**

Edit `C:\Users\YourName\mcp-policies\tagging_policy.json` with any text editor or your policy generator. Changes take effect on the next API call - no restart needed!

### EC2 Deployment

For EC2 deployments, the policy is baked into the Docker image. To update:

**Option A: Rebuild and redeploy (recommended for production)**
```bash
# On your local machine
# 1. Update policies/tagging_policy.json
# 2. Rebuild image
docker build -t finops-mcp-server .

# 3. Push to ECR or copy to EC2
# 4. Restart container on EC2
```

**Option B: Mount external volume on EC2**
```bash
# On EC2, create a policies folder
mkdir -p /home/ec2-user/mcp-policies
cp /app/policies/tagging_policy.json /home/ec2-user/mcp-policies/

# Run with mounted volume
docker run -d -p 8080:8080 --name finops-mcp-server \
  -v /home/ec2-user/mcp-policies:/app/policies \
  finops-mcp-server
```

---

## Complete Workflow: Policy Generator to Deployment

### Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  1. GENERATE POLICY                                             │
│     ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│     │ Policy Generator│  │ Claude/AI       │  │ AWS Convert  │ │
│     │ Web App         │  │ Assistant       │  │ Script       │ │
│     └────────┬────────┘  └────────┬────────┘  └──────┬───────┘ │
│              │                    │                   │         │
│              └────────────────────┼───────────────────┘         │
│                                   ▼                             │
│                        tagging_policy.json                      │
└─────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. VALIDATE POLICY                                             │
│     • Check JSON syntax (jsonlint.com)                          │
│     • Verify required fields present                            │
│     • Test regex patterns (regex101.com)                        │
└─────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. DEPLOY POLICY                                               │
│     ┌─────────────────────┐    ┌─────────────────────┐         │
│     │ Local Docker        │    │ EC2 Production      │         │
│     │ (mounted volume)    │    │ (rebuild image)     │         │
│     │                     │    │                     │         │
│     │ Just save the file  │    │ docker build        │         │
│     │ Changes auto-apply  │    │ docker push         │         │
│     └─────────────────────┘    │ docker restart      │         │
│                                └─────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. VERIFY POLICY LOADED                                        │
│     • Call get_tagging_policy tool                              │
│     • Check health endpoint                                     │
│     • Run compliance check                                      │
└─────────────────────────────────────────────────────────────────┘
```

### Step-by-Step Instructions

**Step 1: Generate Your Policy**

Using the Policy Generator or Claude, create a policy that matches your organization's needs.

Example request to Claude:
```
Create a tagging policy for my startup with:
- CostCenter: Engineering, Marketing, Sales, Operations
- Owner: must be a valid email
- Environment: production, staging, development
- Optional: Project, Team
```

**Step 2: Save the Policy File**

Save the generated JSON to your policies folder:
- Local: `C:\Users\YourName\mcp-policies\tagging_policy.json`
- Or: `policies/tagging_policy.json` in the project

**Step 3: Validate the Policy**

Before deploying, validate your JSON:

```powershell
# Check JSON syntax
python -c "import json; json.load(open('policies/tagging_policy.json'))"
```

Or use [jsonlint.com](https://jsonlint.com) to validate online.

**Step 4: Deploy**

For local Docker with mounted volume - just save the file, changes apply automatically.

For EC2 or without mounted volume:
```powershell
docker restart finops-mcp-server
```

**Step 5: Verify**

Test that the policy loaded correctly:

```powershell
# Using curl.exe on Windows
curl.exe -X POST http://localhost:8080/mcp/tools/call `
  -H "Content-Type: application/json" `
  -d '{\"name\": \"get_tagging_policy\", \"arguments\": {}}'
```

Or ask Claude Desktop: "Show me our tagging policy"

---

## Dynamic Policy Updates (Advanced)

For organizations that need to update policies frequently:

### Automated Policy Pipeline

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Policy       │───▶│ Git Commit   │───▶│ CI/CD        │
│ Generator    │    │ policies/    │    │ Pipeline     │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │ Deploy to    │
                                        │ EC2/ECS      │
                                        └──────────────┘
```

### Script for Policy Updates

Create a script to automate policy updates:

```powershell
# update_policy.ps1
param(
    [string]$PolicyFile = "policies/tagging_policy.json"
)

# Validate JSON
try {
    $policy = Get-Content $PolicyFile | ConvertFrom-Json
    Write-Host "✓ Policy JSON is valid" -ForegroundColor Green
} catch {
    Write-Host "✗ Invalid JSON: $_" -ForegroundColor Red
    exit 1
}

# Check required fields
if (-not $policy.required_tags) {
    Write-Host "✗ Missing required_tags" -ForegroundColor Red
    exit 1
}

# Update timestamp
$policy.last_updated = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$policy | ConvertTo-Json -Depth 10 | Set-Content $PolicyFile

Write-Host "✓ Policy updated with new timestamp" -ForegroundColor Green

# Restart container if running
$container = docker ps -q -f name=finops-mcp-server
if ($container) {
    docker restart finops-mcp-server
    Write-Host "✓ Container restarted" -ForegroundColor Green
}
```

---

## Troubleshooting

### Policy not loading

**Symptom:** `get_tagging_policy` returns empty or old policy

**Fix:**
1. Check file path is correct
2. Verify JSON is valid
3. Check Docker volume mount: `docker inspect finops-mcp-server`
4. Restart container: `docker restart finops-mcp-server`

### Validation errors

**Symptom:** "Invalid policy format" error

**Fix:**
1. Validate JSON syntax at [jsonlint.com](https://jsonlint.com)
2. Check all required fields are present
3. Verify `applies_to` uses correct format: `service:resource_type`

### Regex not working

**Symptom:** Tags with valid values flagged as violations

**Fix:**
1. Test regex at [regex101.com](https://regex101.com)
2. Remember to escape backslashes in JSON: `\\` not `\`
3. Example email regex: `"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"`

---

## Best Practices

1. **Version control your policies** - Keep `policies/tagging_policy.json` in Git
2. **Test locally first** - Use mounted volumes for easy iteration
3. **Document changes** - Update `last_updated` and add comments
4. **Start simple** - Begin with 3-4 required tags, add more later
5. **Use wildcards** - Set `applies_to: []` to apply to all resources
6. **Validate before deploy** - Always check JSON syntax

---

## Related Documentation

- [Tagging Policy Guide](TAGGING_POLICY_GUIDE.md) - Detailed policy format reference
- [Policy Generator Prompt](POLICY_GENERATOR_PROMPT.md) - Build your own generator
- [Deployment Guide](DEPLOYMENT.md) - Full deployment instructions
- [User Manual](USER_MANUAL.md) - Using the MCP tools

---

**Document Version:** 1.0  
**Last Updated:** January 8, 2026
