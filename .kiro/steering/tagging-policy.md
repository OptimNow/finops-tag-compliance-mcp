---
inclusion: fileMatch
fileMatchPattern: "**/polic*.json"
---

# Tagging Policy Configuration

This steering applies when working with tagging policy files.

## Policy Schema

```json
{
  "version": "1.0",
  "required_tags": [
    {
      "name": "TagName",
      "description": "What this tag is for",
      "allowed_values": ["Value1", "Value2"],  // Optional
      "validation_regex": "^pattern$",          // Optional
      "applies_to": ["ec2:instance", "rds:db"]
    }
  ],
  "optional_tags": [
    {
      "name": "OptionalTag",
      "description": "What this optional tag is for"
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

## Supported Resource Types
- `ec2:instance`
- `rds:db`
- `s3:bucket`
- `lambda:function`
- `ecs:service`

## Validation Rules

1. **Required tags** - Must be present on applicable resources
2. **Allowed values** - If specified, tag value must match one in the list
3. **Regex patterns** - If specified, tag value must match the pattern
4. **Resource scoping** - Tags only apply to resource types in `applies_to`

## Best Practices

- Start with 2-3 required tags, expand over time
- Use `allowed_values` for controlled vocabularies (CostCenter, Environment)
- Use `validation_regex` for flexible patterns (Owner emails)
- Always include `applies_to` to scope tags appropriately
