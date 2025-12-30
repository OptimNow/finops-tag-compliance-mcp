# User Acceptance Testing Protocol

## FinOps Tag Compliance MCP Server - Phase 1 MVP

**Version:** 1.0  
**Date:** _______________  
**Tester:** _______________  
**Environment:** Production / Staging (circle one)

---

## Prerequisites

Before starting UAT, ensure:
- [ ] MCP server is deployed and accessible
- [ ] Claude Desktop is configured to connect to the MCP server
- [ ] You have AWS resources to test against (EC2, RDS, S3, Lambda, or ECS)
- [ ] Some resources are properly tagged, some are missing tags (for realistic testing)
- [ ] Health endpoint returns `{"status": "healthy"}`

---

## Test Scenarios

### Scenario 1: Tag Compliance Check
**Tool:** `check_tag_compliance`  
**User Story:** As a FinOps practitioner, I want to check how well my AWS resources comply with our tagging policy.

#### Test Steps

| Step | Action | Expected Result | Pass/Fail | Notes |
|------|--------|-----------------|-----------|-------|
| 1.1 | Ask Claude: "Check tag compliance for my EC2 instances" | Returns compliance score (0-100%), list of violations | | |
| 1.2 | Ask Claude: "Check compliance for EC2 and RDS in us-east-1" | Returns results filtered to specified region | | |
| 1.3 | Ask Claude: "Show me only critical tagging errors" | Returns only ERROR severity violations | | |
| 1.4 | Verify response time | Results returned within 5 seconds | | |

#### Business Value Validation
- [ ] Can I quickly see my overall compliance posture?
- [ ] Are violations clearly explained with actionable details?
- [ ] Does the compliance score help me prioritize remediation?

**Comments:** _______________________________________________

---

### Scenario 2: Find Untagged Resources
**Tool:** `find_untagged_resources`  
**User Story:** As a DevOps engineer, I want to find all resources that are completely untagged or missing critical tags.

#### Test Steps

| Step | Action | Expected Result | Pass/Fail | Notes |
|------|--------|-----------------|-----------|-------|
| 2.1 | Ask Claude: "Find all untagged resources" | Returns list of resources with no tags or missing required tags | | |
| 2.2 | Ask Claude: "Find untagged resources costing more than $50/month" | Returns only resources exceeding cost threshold | | |
| 2.3 | Ask Claude: "Find untagged resources across all regions" | Returns resources from multiple regions | | |
| 2.4 | Verify each result includes cost estimate | Monthly cost shown for each resource | | |
| 2.5 | Verify each result includes resource age | Age in days shown for each resource | | |

#### Business Value Validation
- [ ] Can I identify the biggest cost leaks from untagged resources?
- [ ] Does the cost information help me prioritize which resources to tag first?
- [ ] Is the resource age helpful for identifying orphaned resources?

**Comments:** _______________________________________________

---

### Scenario 3: Validate Specific Resources
**Tool:** `validate_resource_tags`  
**User Story:** As a developer, I want to validate specific resources against our tagging policy.

#### Test Steps

| Step | Action | Expected Result | Pass/Fail | Notes |
|------|--------|-----------------|-----------|-------|
| 3.1 | Ask Claude: "Validate tags for [specific resource ARN]" | Returns detailed validation results | | |
| 3.2 | Test with a compliant resource | Returns "compliant" status | | |
| 3.3 | Test with a non-compliant resource | Returns specific violations (missing tag, invalid value, wrong format) | | |
| 3.4 | Verify invalid value shows allowed values | When value is wrong, shows what values are allowed | | |

#### Business Value Validation
- [ ] Can I validate resources before/after deployment?
- [ ] Are the violation details specific enough to fix the issue?
- [ ] Does showing allowed values speed up remediation?

**Comments:** _______________________________________________

---

### Scenario 4: Cost Attribution Gap Analysis
**Tool:** `get_cost_attribution_gap`  
**User Story:** As a FinOps practitioner, I want to see the financial impact of our tagging gaps.

#### Test Steps

| Step | Action | Expected Result | Pass/Fail | Notes |
|------|--------|-----------------|-----------|-------|
| 4.1 | Ask Claude: "What's our cost attribution gap?" | Returns total spend, attributable spend, and gap amount | | |
| 4.2 | Ask Claude: "Show cost attribution gap by resource type" | Returns breakdown by EC2, RDS, S3, etc. | | |
| 4.3 | Ask Claude: "Show cost attribution gap for last month" | Returns gap for specified time period | | |
| 4.4 | Verify gap percentage is calculated | Shows gap as both $ amount and % | | |

#### Business Value Validation
- [ ] Can I quantify the financial impact of poor tagging?
- [ ] Is this data compelling enough to present to leadership?
- [ ] Does the breakdown help identify which resource types need attention?

**Comments:** _______________________________________________

---

### Scenario 5: Tag Suggestions
**Tool:** `suggest_tags`  
**User Story:** As a DevOps engineer, I want the system to suggest appropriate tags for untagged resources.

#### Test Steps

| Step | Action | Expected Result | Pass/Fail | Notes |
|------|--------|-----------------|-----------|-------|
| 5.1 | Ask Claude: "Suggest tags for [untagged resource ARN]" | Returns tag suggestions with values | | |
| 5.2 | Verify confidence scores | Each suggestion has confidence 0-1 | | |
| 5.3 | Verify reasoning is provided | Each suggestion explains why it was suggested | | |
| 5.4 | Test with resource in named VPC | Suggestions based on VPC naming pattern | | |

#### Business Value Validation
- [ ] Do the suggestions make sense for the resource?
- [ ] Does the confidence score help me decide whether to accept the suggestion?
- [ ] Does the reasoning help me understand and trust the suggestion?

**Comments:** _______________________________________________

---

### Scenario 6: View Tagging Policy
**Tool:** `get_tagging_policy`  
**User Story:** As a team lead, I want to view our organization's tagging policy.

#### Test Steps

| Step | Action | Expected Result | Pass/Fail | Notes |
|------|--------|-----------------|-----------|-------|
| 6.1 | Ask Claude: "Show me our tagging policy" | Returns complete policy configuration | | |
| 6.2 | Verify required tags are listed | Shows all required tags with descriptions | | |
| 6.3 | Verify allowed values are shown | Tags with value restrictions show allowed values | | |
| 6.4 | Verify resource type applicability | Shows which resource types each tag applies to | | |

#### Business Value Validation
- [ ] Can team members easily understand what tags are required?
- [ ] Is it clear what values are allowed for each tag?
- [ ] Does this reduce questions about tagging requirements?

**Comments:** _______________________________________________

---

### Scenario 7: Generate Compliance Report
**Tool:** `generate_compliance_report`  
**User Story:** As a FinOps practitioner, I want to generate comprehensive compliance reports.

#### Test Steps

| Step | Action | Expected Result | Pass/Fail | Notes |
|------|--------|-----------------|-----------|-------|
| 7.1 | Ask Claude: "Generate a compliance report" | Returns formatted report with summary | | |
| 7.2 | Ask Claude: "Generate compliance report in CSV format" | Returns CSV-formatted data | | |
| 7.3 | Ask Claude: "Generate compliance report with recommendations" | Includes actionable remediation suggestions | | |
| 7.4 | Verify top violations are ranked | Shows violations by count and cost impact | | |

#### Business Value Validation
- [ ] Is the report suitable for sharing with stakeholders?
- [ ] Do the recommendations help prioritize remediation work?
- [ ] Does the format (JSON/CSV/Markdown) meet your needs?

**Comments:** _______________________________________________

---

### Scenario 8: Violation History & Trends
**Tool:** `get_violation_history`  
**User Story:** As a FinOps practitioner, I want to track compliance trends over time.

#### Test Steps

| Step | Action | Expected Result | Pass/Fail | Notes |
|------|--------|-----------------|-----------|-------|
| 8.1 | Ask Claude: "Show me violation history for the past week" | Returns historical compliance scores | | |
| 8.2 | Ask Claude: "Show compliance trend by month" | Returns data grouped by month | | |
| 8.3 | Verify trend direction | Shows "improving", "declining", or "stable" | | |
| 8.4 | Test with 30-day lookback | Returns up to 30 days of history | | |

#### Business Value Validation
- [ ] Can I measure improvement over time?
- [ ] Does the trend indicator help identify regression?
- [ ] Is this data useful for reporting progress to leadership?

**Comments:** _______________________________________________

---

## Overall Assessment

### Summary

| Scenario | Tool | Pass/Fail | Critical Issues |
|----------|------|-----------|-----------------|
| 1 | check_tag_compliance | | |
| 2 | find_untagged_resources | | |
| 3 | validate_resource_tags | | |
| 4 | get_cost_attribution_gap | | |
| 5 | suggest_tags | | |
| 6 | get_tagging_policy | | |
| 7 | generate_compliance_report | | |
| 8 | get_violation_history | | |

### Business Value Assessment

Rate each on a scale of 1-5 (1=Poor, 5=Excellent):

| Criteria | Rating | Comments |
|----------|--------|----------|
| Ease of use through Claude | /5 | |
| Quality of compliance insights | /5 | |
| Actionability of recommendations | /5 | |
| Cost visibility and attribution | /5 | |
| Time saved vs. manual process | /5 | |
| Overall business value | /5 | |

### Issues Found

| Issue # | Severity (High/Med/Low) | Description | Scenario |
|---------|------------------------|-------------|----------|
| 1 | | | |
| 2 | | | |
| 3 | | | |

### Recommendations for Improvement

1. _______________________________________________
2. _______________________________________________
3. _______________________________________________

---

## Sign-Off

### UAT Result: PASS / FAIL (circle one)

**Tester Signature:** _______________________________________________

**Date:** _______________________________________________

**Comments:** _______________________________________________

---

## Appendix: Sample Claude Prompts

Use these natural language prompts to test the MCP tools:

```
# Compliance Check
"How compliant are my EC2 instances with our tagging policy?"
"Check tag compliance for all resources in us-west-2"
"Show me only critical tagging violations"

# Find Untagged
"Find all resources that are missing tags"
"What untagged resources are costing me the most?"
"Show me untagged resources older than 30 days"

# Validate Resources
"Validate the tags on arn:aws:ec2:us-east-1:123456789:instance/i-abc123"
"Is this resource compliant with our tagging policy?"

# Cost Attribution
"What's the financial impact of our tagging gaps?"
"How much spend can't be attributed due to missing tags?"
"Show me the cost attribution gap by service"

# Tag Suggestions
"What tags should I add to this untagged EC2 instance?"
"Suggest tags for arn:aws:ec2:us-east-1:123456789:instance/i-xyz789"

# Policy
"What tags are required by our policy?"
"Show me the allowed values for the Environment tag"

# Reports
"Generate a compliance report for leadership"
"Create a CSV export of all violations"
"Give me a report with remediation recommendations"

# History
"How has our compliance improved over the past month?"
"Show me the compliance trend for the last 90 days"
```
