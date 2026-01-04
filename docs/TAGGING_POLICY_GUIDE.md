# Tagging Policy Configuration Guide

**For:** FinOps Tag Compliance MCP Server  
**Audience:** FinOps practitioners, cloud engineers, compliance teams  
**Version:** 1.0

---

## What is a Tagging Policy?

A tagging policy is your organization's "rulebook" for how cloud resources should be labeled. Think of it like a style guide for writing, but for cloud infrastructure. It defines:

- **Which tags are mandatory** (e.g., every EC2 instance must have a CostCenter tag)
- **Allowed values** (e.g., Environment can only be "production", "staging", "development", or "test")
- **Which resources need which tags** (e.g., S3 buckets need DataClassification, but Lambda functions don't)
- **Validation rules** (e.g., Owner must be a valid email address)

Without a tagging policy, the MCP server doesn't know what "compliant" means for your organization.

---

## Why Tagging Policies Matter

**Cost Attribution**: Tags enable chargeback and showback by mapping cloud spend to departments, projects, or applications.

**Compliance**: Regulatory frameworks (HIPAA, PCI-DSS, SOC2) often require proper labeling of resources containing sensitive data.

**Operational Excellence**: Tags help identify resource owners, automate backups, and manage lifecycle policies.

**Security**: Tags can enforce access controls and identify resources that need special handling.

---

## Policy File Location

The tagging policy is stored at `policies/tagging_policy.json` in the Git repository. This file is mounted into the Docker container when you run `docker-compose up`.

**File path:** `policies/tagging_policy.json`

**Docker mount:** The `docker-compose.yml` file mounts this directory:
```yaml
volumes:
  - ./policies:/app/policies:ro
```

The `:ro` means read-only - the container can read the policy but not modify it.

---

## Converting from AWS Organizations Tag Policies

**If your organization already uses AWS Organizations tag policies**, you can convert them to our format using the provided converter script.

### Quick Conversion

```bash
# Convert AWS policy to our format
python scripts/convert_aws_policy.py path/to/aws_policy.json

# Output will be saved to policies/tagging_policy.json
```

### How to Get Your AWS Tag Policy

**Option 1: AWS Console**
1. Go to AWS Organizations console
2. Navigate to Policies → Tag policies
3. Select your tag policy
4. Copy the JSON from the policy editor
5. Save to a file (e.g., `aws_tag_policy.json`)

**Option 2: AWS CLI**
```bash
# List tag policies
aws organizations list-policies --filter TAG_POLICY

# Get specific policy content
aws organizations describe-policy --policy-id p-xxxxxxxx > aws_tag_policy.json
```

### Conversion Example

**Input (AWS Organizations format):**
```json
{
  "tags": {
    "costcenter": {
      "tag_key": {
        "@@assign": "CostCenter"
      },
      "tag_value": {
        "@@assign": ["Engineering", "Marketing"]
      },
      "enforced_for": {
        "@@assign": ["ec2:instance", "rds:db"]
      }
    }
  }
}
```

**Output (MCP Server format):**
```json
{
  "version": "1.0",
  "last_updated": "2025-01-04T12:00:00Z",
  "required_tags": [
    {
      "name": "CostCenter",
      "description": "Converted from AWS Organizations tag policy - costcenter",
      "allowed_values": ["Engineering", "Marketing"],
      "validation_regex": null,
      "applies_to": ["ec2:instance", "rds:db"]
    }
  ],
  "optional_tags": [],
  "tag_naming_rules": {
    "case_sensitivity": false,
    "allow_special_characters": false,
    "max_key_length": 128,
    "max_value_length": 256
  }
}
```

### Conversion Notes

- **Enforced tags** → Required tags in our format
- **Non-enforced tags** → Optional tags in our format
- **ALL_SUPPORTED** wildcard → Expanded to common resource types
- **Wildcards in values** (e.g., `"300*"`) → Removed (not supported yet)
- **Descriptions** → Auto-generated (you can edit them after conversion)

### After Conversion

1. Review the converted policy at `policies/tagging_policy.json`
2. Edit descriptions to be more meaningful
3. Add `validation_regex` if needed (e.g., email format for Owner tag)
4. Restart Docker containers: `docker-compose restart`
5. Verify: "Show me our tagging policy" in Claude Desktop

---

## Policy File Format

The policy file follows this JSON schema:

```json
{
  "version": "1.0",
  "last_updated": "2025-12-30T00:00:00Z",
  "required_tags": [
    {
      "name": "CostCenter",
      "description": "Department for cost allocation",
      "allowed_values": ["Engineering", "Marketing", "Sales", "Operations"],
      "validation_regex": null,
      "applies_to": ["ec2:instance", "rds:db", "s3:bucket", "lambda:function"]
    },
    {
      "name": "Owner",
      "description": "Email address of the resource owner",
      "allowed_values": null,
      "validation_regex": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
      "applies_to": ["ec2:instance", "rds:db", "s3:bucket"]
    }
  ],
  "optional_tags": [
    {
      "name": "Project",
      "description": "Project identifier"
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

---

## Field Definitions

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | Yes | Policy schema version (currently "1.0") |
| `last_updated` | string (ISO 8601) | Yes | When the policy was last modified |
| `required_tags` | array | Yes | Tags that MUST be present on resources |
| `optional_tags` | array | No | Tags that are allowed but not required |
| `tag_naming_rules` | object | No | Global rules for tag key/value formatting |

### Required Tag Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Tag key name (e.g., "CostCenter") |
| `description` | string | Yes | Human-readable explanation of the tag's purpose |
| `allowed_values` | array or null | No | If set, tag value must match one of these |
| `validation_regex` | string or null | No | If set, tag value must match this regex pattern |
| `applies_to` | array | Yes | Which resource types need this tag (format: `service:resource_type`) |

### Resource Type Format

Resource types use the format `service:resource_type`:

| Service | Resource Type | Format |
|---------|---------------|--------|
| EC2 | Instance | `ec2:instance` |
| RDS | Database | `rds:db` |
| S3 | Bucket | `s3:bucket` |
| Lambda | Function | `lambda:function` |
| ECS | Service | `ecs:service` |

---

## Common Tagging Patterns

### Cost Allocation Tags

These tags enable chargeback and showback:

```json
{
  "name": "CostCenter",
  "description": "Department for cost allocation - used for chargebacks and budget tracking",
  "allowed_values": ["Engineering", "Marketing", "Sales", "Operations", "Finance"],
  "validation_regex": null,
  "applies_to": ["ec2:instance", "rds:db", "s3:bucket", "lambda:function", "ecs:service"]
}
```

### Accountability Tags

These tags identify who owns and manages resources:

```json
{
  "name": "Owner",
  "description": "Email address of the resource owner - who to contact if issues arise",
  "allowed_values": null,
  "validation_regex": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
  "applies_to": ["ec2:instance", "rds:db", "s3:bucket", "lambda:function", "ecs:service"]
}
```

### Environment Tags

These tags separate production from non-production resources:

```json
{
  "name": "Environment",
  "description": "Deployment environment - affects cost allocation and risk assessment",
  "allowed_values": ["production", "staging", "development", "test"],
  "validation_regex": null,
  "applies_to": ["ec2:instance", "rds:db", "lambda:function", "ecs:service"]
}
```

### Application Tags

These tags group resources by application or service:

```json
{
  "name": "Application",
  "description": "Application or service name - for grouping related resources",
  "allowed_values": null,
  "validation_regex": "^[a-z][a-z0-9-]{2,63}$",
  "applies_to": ["ec2:instance", "rds:db", "s3:bucket", "lambda:function", "ecs:service"]
}
```

### Data Classification Tags

These tags identify data sensitivity for compliance:

```json
{
  "name": "DataClassification",
  "description": "Data sensitivity level - for compliance and security",
  "allowed_values": ["public", "internal", "confidential", "restricted"],
  "validation_regex": null,
  "applies_to": ["s3:bucket", "rds:db"]
}
```

---

## Tag Pattern Reference Table

| Tag | Purpose | Typical Values | Applies To |
|-----|---------|----------------|------------|
| CostCenter | Chargeback/showback | Department names | All resources |
| Owner | Accountability | Email addresses | All resources |
| Environment | Risk/cost tier | production, staging, dev, test | Compute resources |
| Application | Grouping | App/service names | All resources |
| DataClassification | Security/compliance | public, internal, confidential, restricted | Storage resources |
| BackupSchedule | DR planning | daily, weekly, monthly, none | Stateful resources |
| Compliance | Regulatory framework | HIPAA, PCI-DSS, SOC2, GDPR | All resources |
| Project | Project tracking | Project codes/names | All resources |

---

## Customizing Your Policy

### Step 1: Edit the Policy File

Open `policies/tagging_policy.json` in your text editor.

### Step 2: Define Required Tags

Add or modify tags in the `required_tags` array to match your organization's standards:

```json
{
  "required_tags": [
    {
      "name": "YourTagName",
      "description": "What this tag is for",
      "allowed_values": ["value1", "value2"],
      "validation_regex": null,
      "applies_to": ["ec2:instance", "rds:db"]
    }
  ]
}
```

### Step 3: Set Allowed Values

For tags with restricted options (like Environment, CostCenter), set `allowed_values`:

```json
"allowed_values": ["production", "staging", "development", "test"]
```

This enforces that only these exact values are valid. Any other value will be flagged as a violation.

### Step 4: Add Validation Rules

For tags that need format validation (like email addresses), use `validation_regex`:

```json
"validation_regex": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
```

**Common regex patterns:**

- Email: `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$`
- Lowercase with hyphens: `^[a-z][a-z0-9-]{2,63}$`
- Date (YYYY-MM-DD): `^\d{4}-\d{2}-\d{2}$`
- AWS Account ID: `^\d{12}$`

### Step 5: Save and Restart

1. Save the file
2. Restart Docker containers: `docker-compose restart`
3. Verify: "Show me our tagging policy" in Claude Desktop

---

## Verifying Policy is Loaded

After starting the server, test that the policy loaded correctly:

### Option 1: Ask Claude Desktop

```
"Show me our tagging policy"
```

Claude should return your complete policy configuration.

### Option 2: Test with Local Script

```bash
python scripts/local_test.py
```

This script calls the `/mcp/tools` endpoint and should list `get_tagging_policy` as an available tool.

### Option 3: Direct API Call

```bash
curl http://localhost:8080/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_tagging_policy",
    "arguments": {}
  }'
```

---

## Troubleshooting

### Error: "No tagging policy configured"

**Cause:** Policy file not found or not mounted into container

**Fix:**
1. Check file exists at `policies/tagging_policy.json` (underscore, not dash)
2. Verify `docker-compose.yml` has correct volume mount: `./policies:/app/policies:ro`
3. Restart containers: `docker-compose restart`

### Error: "Invalid policy format"

**Cause:** JSON syntax error in policy file

**Fix:**
1. Validate JSON at [jsonlint.com](https://jsonlint.com)
2. Check for missing commas, brackets, or quotes
3. Ensure all strings are properly escaped (e.g., `\\` for regex backslashes)

### Policy changes not reflected

**Cause:** Container using cached policy

**Fix:**
1. Restart containers: `docker-compose restart`
2. If still not working, rebuild: `docker-compose down && docker-compose up -d`

### Error: "Policy validation failed"

**Cause:** Policy structure doesn't match expected schema

**Fix:**
1. Compare your policy to the example in this guide
2. Ensure all required fields are present (`name`, `description`, `applies_to`)
3. Check that `applies_to` uses correct format: `service:resource_type`

---

## Policy Validation Checklist

Before deploying a new policy, verify:

- [ ] File exists at `policies/tagging_policy.json`
- [ ] File is valid JSON (no syntax errors)
- [ ] All required tags have `name`, `description`, and `applies_to`
- [ ] `allowed_values` arrays contain valid options
- [ ] `validation_regex` patterns are valid regex (test at [regex101.com](https://regex101.com))
- [ ] `applies_to` uses correct format: `service:resource_type`
- [ ] `last_updated` timestamp is current
- [ ] Docker containers restarted after changes
- [ ] Policy loads successfully (test with "Show me our tagging policy")

---

## Example: Complete Policy for a Startup

```json
{
  "version": "1.0",
  "last_updated": "2025-01-04T00:00:00Z",
  "required_tags": [
    {
      "name": "CostCenter",
      "description": "Department for cost allocation",
      "allowed_values": ["Engineering", "Marketing", "Sales", "Operations"],
      "validation_regex": null,
      "applies_to": ["ec2:instance", "rds:db", "s3:bucket", "lambda:function"]
    },
    {
      "name": "Owner",
      "description": "Email address of the resource owner",
      "allowed_values": null,
      "validation_regex": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
      "applies_to": ["ec2:instance", "rds:db", "s3:bucket", "lambda:function"]
    },
    {
      "name": "Environment",
      "description": "Deployment environment",
      "allowed_values": ["production", "staging", "development"],
      "validation_regex": null,
      "applies_to": ["ec2:instance", "rds:db", "lambda:function"]
    }
  ],
  "optional_tags": [
    {
      "name": "Project",
      "description": "Project identifier"
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

---

## Example: Complete Policy for an Enterprise

```json
{
  "version": "1.0",
  "last_updated": "2025-01-04T00:00:00Z",
  "required_tags": [
    {
      "name": "CostCenter",
      "description": "Department for cost allocation",
      "allowed_values": ["Engineering", "Marketing", "Sales", "Operations", "Finance", "HR", "Legal"],
      "validation_regex": null,
      "applies_to": ["ec2:instance", "rds:db", "s3:bucket", "lambda:function", "ecs:service"]
    },
    {
      "name": "Owner",
      "description": "Email address of the resource owner",
      "allowed_values": null,
      "validation_regex": "^[a-zA-Z0-9._%+-]+@company\\.com$",
      "applies_to": ["ec2:instance", "rds:db", "s3:bucket", "lambda:function", "ecs:service"]
    },
    {
      "name": "Environment",
      "description": "Deployment environment",
      "allowed_values": ["production", "staging", "development", "test", "sandbox"],
      "validation_regex": null,
      "applies_to": ["ec2:instance", "rds:db", "lambda:function", "ecs:service"]
    },
    {
      "name": "Application",
      "description": "Application or service name",
      "allowed_values": null,
      "validation_regex": "^[a-z][a-z0-9-]{2,63}$",
      "applies_to": ["ec2:instance", "rds:db", "s3:bucket", "lambda:function", "ecs:service"]
    },
    {
      "name": "DataClassification",
      "description": "Data sensitivity level",
      "allowed_values": ["public", "internal", "confidential", "restricted"],
      "validation_regex": null,
      "applies_to": ["s3:bucket", "rds:db"]
    },
    {
      "name": "Compliance",
      "description": "Compliance framework",
      "allowed_values": ["HIPAA", "PCI-DSS", "SOC2", "GDPR", "None"],
      "validation_regex": null,
      "applies_to": ["ec2:instance", "rds:db", "s3:bucket"]
    }
  ],
  "optional_tags": [
    {
      "name": "Project",
      "description": "Project identifier"
    },
    {
      "name": "BackupSchedule",
      "description": "Backup schedule",
      "allowed_values": ["daily", "weekly", "monthly", "none"]
    },
    {
      "name": "MaintenanceWindow",
      "description": "Maintenance window for patching"
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

---

## Best Practices

### Start Small

Don't try to enforce 20 tags on day one. Start with 3-4 critical tags:
- CostCenter (for cost allocation)
- Owner (for accountability)
- Environment (for risk management)

Add more tags as your organization matures.

### Use Allowed Values Wisely

Only use `allowed_values` when you truly need to restrict options. For example:
- ✅ Environment: ["production", "staging", "development"] - limited set
- ❌ Application: Don't restrict - too many possible values

### Document Your Tags

The `description` field is critical. Make it clear what each tag is for and how it should be used. This helps developers tag resources correctly.

### Review Regularly

Set a quarterly reminder to review your tagging policy:
- Are all required tags still necessary?
- Do we need new tags for new compliance requirements?
- Are allowed values still accurate?

### Communicate Changes

When you update the policy, notify your team:
- What changed
- Why it changed
- When it takes effect
- How to fix non-compliant resources

---

## Related Documentation

- [UAT Protocol](UAT_PROTOCOL.md) - Testing procedures
- [Phase 1 Specification](PHASE-1-SPECIFICATION.md) - Complete MVP spec
- [Deployment Guide](DEPLOYMENT.md) - How to deploy the MCP server

---

**Document Version:** 1.0  
**Last Updated:** January 4, 2025  
**Maintained By:** FinOps Team
