# Policy Import & Management Workflow

Use this workflow when the user wants to view, import, or manage their tagging policy.

## Viewing the current policy

Call `get_tagging_policy` to display:

- **Required tags** — tags that must be present on resources (violations are errors)
- **Optional tags** — recommended tags (violations are warnings)
- **Validation rules** — allowed values and regex patterns per tag
- **Applies-to** — which resource types each tag rule covers
- **`all_applicable_resource_types`** — the complete deduplicated list of resource types in scope

This tool is the starting point for every compliance workflow. Always call it before scanning.

## Importing from AWS Organizations

Use `import_aws_tag_policy` to convert an AWS Organizations tag policy into MCP format:

### List available policies

Call with no arguments to discover available tag policies:

```
import_aws_tag_policy()
```

Returns a list of policy IDs and names from AWS Organizations.

### Import a specific policy

Call with a policy ID to import and convert:

```
import_aws_tag_policy(policy_id="p-abc12345")
```

- `save_to_file=true` (default) — saves the converted policy to disk
- `output_path` — where to save (default: `policies/tagging_policy.json`)

The imported policy replaces the existing one. The server must be restarted to pick up the change.

### Requirements

Importing from AWS Organizations requires additional IAM permissions:

- `organizations:ListPolicies`
- `organizations:DescribePolicy`

These are NOT included in the default read-only policy. The user must add them if they want to use this feature.

## Manual policy editing

The tagging policy lives at `policies/tagging_policy.json`. Users can edit it directly:

```json
{
  "required_tags": [
    {
      "name": "Environment",
      "description": "Deployment environment",
      "allowed_values": ["production", "staging", "development"],
      "validation_regex": null,
      "applies_to": ["ec2:instance", "rds:db", "s3:bucket"]
    }
  ],
  "optional_tags": [...]
}
```

Key fields:
- `allowed_values` — if set, tag value must be in this list (case-sensitive)
- `validation_regex` — if set, tag value must match this regex
- `applies_to` — resource types this tag applies to (empty list = all types)

Changes take effect on server restart.
