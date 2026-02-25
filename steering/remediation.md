# Remediation Workflow

Use this workflow when the user wants to fix tagging gaps, enforce compliance, or automate tag management.

## Tag suggestions

Use `suggest_tags` to get ML-powered tag recommendations for a specific resource:

- Pass a single resource ARN (e.g., `arn:aws:ec2:us-east-1:123456789012:instance/i-abc123`)
- Returns suggested tag key/value pairs with confidence scores and reasoning
- Works best with regional resources (EC2, RDS, Lambda, ECS)
- Known limitation: S3 bucket ARNs (global, no region) may fail

Typical flow:
1. `find_untagged_resources` with `include_costs=true` to identify highest-cost untagged resources
2. `suggest_tags` on each high-priority resource
3. User applies tags manually or via automation

## Cloud Custodian policies

Use `generate_custodian_policy` to create enforcement YAML:

- `dry_run=true` (default) — generates notify-only policies for testing
- `dry_run=false` — generates auto-remediation policies
- `resource_types` — restrict to specific types (e.g., `["ec2:instance"]`)
- `violation_types` — restrict to `"missing_tag"` or `"invalid_value"`
- `target_tags` — restrict to specific tag names (e.g., `["Environment", "Owner"]`)

Always start with `dry_run=true` and recommend the user test before enabling auto-remediation.

## OpenOps workflows

Use `generate_openops_workflow` for automated remediation workflows:

- `remediation_strategy`:
  - `"notify"` — send alerts when violations are found
  - `"auto_tag"` — automatically apply missing tags
  - `"report"` — generate periodic reports
- `threshold` — compliance score threshold that triggers the workflow (e.g., 0.8 for 80%)
- `schedule` — `"daily"`, `"weekly"`, or `"monthly"`
- `target_tags` — specific tags to target

## Compliance audit scheduling

Use `schedule_compliance_audit` to configure recurring checks:

- `schedule` — `"daily"`, `"weekly"`, or `"monthly"`
- `time` — time of day in HH:MM 24-hour format (e.g., `"09:00"`)
- `timezone_str` — IANA timezone (e.g., `"UTC"`, `"US/Eastern"`)
- `recipients` — email addresses for notifications
- `notification_format` — `"email"`, `"slack"`, or `"both"`

This generates a configuration including a cron expression. Actual scheduling requires an external scheduler (e.g., AWS EventBridge, cron).

## Recommended remediation sequence

For a complete remediation implementation:

1. **Assess** — `check_tag_compliance` to understand current state
2. **Prioritize** — `find_untagged_resources` with `include_costs=true` to rank by cost impact
3. **Suggest** — `suggest_tags` on high-cost untagged resources
4. **Enforce** — `generate_custodian_policy` with `dry_run=true` to preview enforcement
5. **Automate** — `generate_openops_workflow` for ongoing remediation
6. **Schedule** — `schedule_compliance_audit` for recurring monitoring
7. **Track** — `get_violation_history` to measure improvement over time
