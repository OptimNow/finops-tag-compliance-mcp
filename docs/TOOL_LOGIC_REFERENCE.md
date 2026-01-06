# Tool Logic Reference

This document describes the internal logic used by each of the 8 MCP tools. Understanding how these tools work can help you interpret results and troubleshoot unexpected behavior.

---

## 1. check_tag_compliance

**Purpose**: Scan resources and calculate a compliance score.

**Logic Flow**:
1. **Caching**: Generates a cache key from query parameters (resource types, filters, severity). Returns cached results if available (1-hour TTL by default). Use `force_refresh=True` to bypass cache.
2. **Resource Scanning**: Fetches resources from AWS for each specified resource type.
3. **Filtering**: Applies region and account filters to narrow results.
4. **Policy Validation**: For each resource, validates tags against the tagging policy:
   - Checks for missing required tags
   - Validates tag values against allowed value lists
   - Validates tag values against regex patterns
5. **Score Calculation**: `Compliance Score = Compliant Resources ÷ Total Resources`
6. **Severity Filtering**: Filters violations by severity if requested (`errors_only`, `warnings_only`, or `all`).

**Key Details**:
- Cache key is a SHA256 hash of normalized query parameters
- Resources without violations are counted as compliant
- Cost attribution gap is the sum of cost impacts from all violations

---

## 2. find_untagged_resources

**Purpose**: Find resources with no tags or missing required tags.

**Logic Flow**:
1. **Resource Fetching**: Fetches all resources of specified types from AWS.
2. **Required Tag Detection**: For each resource, determines which required tags apply based on the `applies_to` field in the policy.
3. **Missing Tag Check**: 
   - If resource has no tags → all required tags are missing
   - If resource has some tags → checks which required tags are absent
4. **Cost Estimation** (only when `include_costs=True`):
   - **EC2/RDS**: Uses actual per-resource costs from AWS Cost Explorer
   - **S3/Lambda/ECS**: Uses service average (service total ÷ resource count) since AWS doesn't provide per-resource granularity
5. **Cost Threshold Filtering**: If `min_cost_threshold` is set, excludes resources below that cost.
6. **Age Calculation**: Calculates resource age in days from creation date.

**Cost Source Types**:
- `actual`: Per-resource cost from Cost Explorer (EC2, RDS)
- `service_average`: Service total divided by resource count (S3, Lambda, ECS)
- `estimated`: Fallback when cost data unavailable

---

## 3. validate_resource_tags

**Purpose**: Validate specific resources by ARN against the tagging policy.

**Logic Flow**:
1. **ARN Parsing**: Extracts service, region, account, and resource ID from each ARN.
   - Format: `arn:aws:service:region:account:resource`
   - S3 buckets have empty region/account fields
2. **Resource Type Mapping**: Maps AWS service to internal resource type:
   - `ec2` + `instance/` → `ec2:instance`
   - `rds` + `db:` → `rds:db`
   - `s3` → `s3:bucket`
   - `lambda` + `function:` → `lambda:function`
   - `ecs` + `service/` → `ecs:service`
3. **Tag Fetching**: Retrieves current tags from AWS for each resource.
4. **Policy Validation**: Validates tags against policy rules:
   - **Missing Required Tag** (Severity: Error)
   - **Invalid Value** - not in allowed values list (Severity: Error)
   - **Invalid Format** - doesn't match regex pattern (Severity: Error)

**Validation Rules Applied**:
- Only required tags that apply to the resource type are checked
- Allowed values are case-sensitive
- Regex patterns use Python's `re.match()` (anchored at start)

---

## 4. get_cost_attribution_gap

**Purpose**: Calculate the financial impact of tagging gaps.

**Logic Flow**:
1. **Resource Fetching**: Fetches all resources of specified types.
2. **Cost Data Retrieval**: Gets costs from AWS Cost Explorer:
   - Per-resource costs (where available)
   - Service-level totals
3. **Cost Mapping**:
   - **EC2/RDS**: Uses actual per-resource costs from Cost Explorer
   - **S3/Lambda/ECS**: Distributes service total evenly among resources (estimate)
4. **Compliance Check**: For each resource, validates tags against policy.
5. **Attribution Calculation**:
   - **Attributable Spend**: Sum of costs for compliant resources
   - **Non-Attributable Spend**: Sum of costs for non-compliant resources
   - **Gap**: Total Spend - Attributable Spend
   - **Gap Percentage**: (Gap ÷ Total Spend) × 100
6. **Breakdown Generation**: Groups results by dimension (resource_type, region, or account).

**Notes for $0 Spend Cases**:
- "No resources found for this type"
- "X resource(s) found but $0 cost reported - may need Cost Allocation Tags or resources are in free tier"
- "All X resource(s) are properly tagged"

---

## 5. suggest_tags

**Purpose**: Suggest tag values for a resource based on patterns and context.

**Three Suggestion Strategies**:

**Strategy 1: Pattern Matching**
Scans resource name, VPC name, IAM role, and ARN for keywords:

| Tag | Patterns Detected |
|-----|-------------------|
| Environment | `prod`, `prd`, `production`, `live`, `main` → production |
|             | `stag`, `stg`, `staging`, `preprod`, `uat` → staging |
|             | `dev`, `develop`, `sandbox` → development |
|             | `test`, `tst`, `qa` → test |
| CostCenter | `eng`, `engineering`, `tech`, `platform`, `devops` → Engineering |
|            | `mkt`, `marketing`, `campaign`, `analytics` → Marketing |
|            | `sales`, `crm`, `revenue` → Sales |
|            | `ops`, `operations`, `support` → Operations |
|            | `fin`, `finance`, `billing`, `payment` → Finance |
| DataClassification | `public`, `cdn`, `static`, `assets` → public |
|                    | `internal`, `private`, `corp` → internal |
|                    | `confidential`, `sensitive`, `pii` → confidential |
|                    | `restricted`, `secret`, `hipaa`, `pci` → restricted |

**Strategy 2: Similar Resource Analysis**
- Finds resources in the same VPC or of the same type
- Counts tag value occurrences
- Suggests the most common value
- Confidence based on consistency ratio and sample size

**Strategy 3: Context Inference**
- **Application**: Extracts from resource name (e.g., `app-name-prod` → `app-name`)
- **Owner**: Infers team from IAM role name (e.g., `platform-team-role` → `platform-team@example.com`)

**Confidence Scores**:
| Source | Confidence |
|--------|------------|
| VPC name | 0.85 |
| IAM role | 0.80 |
| Resource name | 0.75 |
| Resource ARN | 0.65 |
| Similar resources | 0.10-0.95 (varies) |
| Application inference | 0.60 |
| Owner inference | 0.45 |

---

## 6. get_tagging_policy

**Purpose**: Return the current tagging policy configuration.

**Logic Flow**:
1. **Policy Loading**: Reads policy from `policies/tagging_policy.json`.
2. **Validation**: Validates structure using Pydantic models.
3. **Caching**: Policy is cached in memory after first load.

**Policy Structure**:
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
  "optional_tags": [
    {
      "name": "Project",
      "description": "Project identifier"
    }
  ]
}
```

**Key Fields**:
- `allowed_values`: If set, tag value must be in this list
- `validation_regex`: If set, tag value must match this pattern
- `applies_to`: Resource types this tag applies to (empty = all types)

---

## 7. generate_compliance_report

**Purpose**: Generate a comprehensive compliance report with rankings and recommendations.

**Logic Flow**:
1. **Summary Calculation**: Computes total resources, compliant count, violation count.
2. **Violation Ranking by Count**: Groups violations by tag name, counts occurrences, sorts descending.
3. **Violation Ranking by Cost**: Groups violations by tag name, sums cost impacts, sorts descending.
4. **Recommendation Generation**: Analyzes patterns and generates prioritized recommendations.

**Recommendation Rules**:
| Condition | Priority | Recommendation |
|-----------|----------|----------------|
| Top cost violation > $1,000/month | High | Address missing '[tag]' tags |
| Top count violation > 10 resources | High | Fix widespread '[tag]' violations |
| Compliance score < 50% | High | Implement automated tagging policies |
| Resource type with most violations > 5 | Medium | Focus tagging efforts on [type] resources |
| Cost attribution gap > $5,000/month | High | Reduce cost attribution gap |
| Cost attribution gap > $1,000/month | Medium | Improve cost attribution |
| Compliance score ≥ 90% | Low | Maintain excellent compliance |

**Output Formats**:
- **JSON**: Full structured data
- **CSV**: Multiple sections (summary, violations by count, violations by cost, recommendations)
- **Markdown**: Formatted document with tables and sections

---

## 8. get_violation_history

**Purpose**: Show how compliance has changed over time.

**Logic Flow**:
1. **Data Storage**: Compliance scan results are stored in SQLite database (`compliance_history.db`).
2. **Query Execution**: Retrieves historical data based on `days_back` parameter (1-90 days).
3. **Grouping**: Aggregates data by period:
   - **Day**: `DATE(timestamp)`
   - **Week**: `DATE(timestamp, 'weekday 0', '-6 days')` (week starting Monday)
   - **Month**: `DATE(timestamp, 'start of month')`
4. **Aggregation**: For each period, calculates:
   - Average compliance score
   - Sum of total resources
   - Sum of compliant resources
   - Sum of violation count
5. **Trend Analysis**: Compares earliest and latest scores:
   - `latest > earliest` → Improving
   - `latest < earliest` → Declining
   - `latest = earliest` → Stable

**Database Schema**:
```sql
CREATE TABLE compliance_scans (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    compliance_score REAL NOT NULL,
    total_resources INTEGER NOT NULL,
    compliant_resources INTEGER NOT NULL,
    violation_count INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

**Note**: History is populated automatically when compliance scans are run. If no scans have been stored, history will be empty.
