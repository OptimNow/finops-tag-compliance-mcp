# Design: Phase 1 - AWS Tag Compliance MVP

## Overview

This design document describes how we'll build the Phase 1 MVP of the FinOps Tag Compliance MCP Server. The architecture prioritizes simplicity and speed-to-value: a single Docker container running on EC2, with Redis for caching and SQLite for audit logs.

The server exposes 8 MCP tools that transform raw AWS tag data into actionable compliance intelligence. Users interact through AI assistants like Claude, asking natural language questions like "How compliant are my EC2 instances?" and getting back structured, insightful responses.

For the complete infrastructure specifications, deployment guides, and code examples, see [PHASE-1-SPECIFICATION.md](../../../PHASE-1-SPECIFICATION.md).

## Architecture

The system follows a straightforward layered architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Clients                              │
│            (Claude Desktop, ChatGPT, etc.)                  │
└─────────────────────────┬───────────────────────────────────┘
                          │ MCP Protocol (HTTP)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    MCP Server Layer                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              FastAPI Application                     │   │
│  │  - MCP Protocol Handler                              │   │
│  │  - Tool Router (8 tools)                             │   │
│  │  - Health Endpoint                                   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────────┐
│                    Service Layer                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Compliance   │  │    Cost      │  │   Suggestion     │  │
│  │   Service    │  │   Service    │  │    Service       │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   Policy     │  │   Report     │  │    History       │  │
│  │   Service    │  │   Service    │  │    Service       │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────────┐
│                 Infrastructure Layer                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  AWS Client  │  │    Redis     │  │     SQLite       │  │
│  │   (boto3)    │  │    Cache     │  │   Audit Log      │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

The design keeps things intentionally simple for Phase 1. No microservices, no message queues, no complex orchestration. Just clean Python code organized into logical layers.

## Components and Interfaces

### MCP Tool Interface

Each of the 8 tools follows a consistent pattern: receive parameters, validate inputs, call services, format response.

```python
# Tool interface pattern
@mcp.tool()
async def check_tag_compliance(
    resource_types: list[str],
    filters: dict | None = None,
    severity: str = "all"
) -> ComplianceResult:
    """
    Check tag compliance for AWS resources.
    
    Args:
        resource_types: List of resource types to check (e.g., ["ec2:instance", "rds:db"])
        filters: Optional filters for region, account_id
        severity: Filter results by severity ("errors_only", "warnings_only", "all")
    
    Returns:
        ComplianceResult with score, violations, and cost impact
    """
    pass
```

### Service Layer Components

**ComplianceService** - The heart of the system. Orchestrates resource scanning, policy validation, and violation detection.

**CostService** - Integrates with AWS Cost Explorer to attach dollar amounts to resources and calculate attribution gaps.

**SuggestionService** - Analyzes resource patterns (VPC names, IAM users, similar resources) to recommend tag values.

**PolicyService** - Loads and manages the tagging policy configuration. Handles validation rules and allowed values.

**ReportService** - Generates formatted compliance reports in JSON, CSV, and Markdown.

**HistoryService** - Tracks compliance scores over time using SQLite storage.

### AWS Client Interface

A thin wrapper around boto3 that handles credential management (via IAM instance profile), rate limiting, and response caching.

```python
class AWSClient:
    def __init__(self, region: str = "us-east-1"):
        # Uses IAM instance profile - no credentials in code
        self.ec2 = boto3.client('ec2', region_name=region)
        self.rds = boto3.client('rds', region_name=region)
        self.s3 = boto3.client('s3', region_name=region)
        self.lambda_client = boto3.client('lambda', region_name=region)
        self.ecs = boto3.client('ecs', region_name=region)
        self.ce = boto3.client('ce', region_name='us-east-1')
    
    async def get_ec2_instances(self, filters: dict) -> list[Resource]:
        """Fetch EC2 instances with tags"""
        pass
    
    async def get_cost_data(self, resource_ids: list[str], time_period: dict) -> dict:
        """Fetch cost data from Cost Explorer"""
        pass
```

## Data Models

### Core Domain Models

```python
from pydantic import BaseModel
from datetime import datetime
from enum import Enum

class ViolationType(str, Enum):
    MISSING_REQUIRED_TAG = "missing_required_tag"
    INVALID_VALUE = "invalid_value"
    INVALID_FORMAT = "invalid_format"

class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"

class Violation(BaseModel):
    resource_id: str
    resource_type: str
    region: str
    violation_type: ViolationType
    tag_name: str
    severity: Severity
    current_value: str | None = None
    allowed_values: list[str] | None = None
    cost_impact_monthly: float = 0.0

class ComplianceResult(BaseModel):
    compliance_score: float  # 0.0 to 1.0
    total_resources: int
    compliant_resources: int
    violations: list[Violation]
    cost_attribution_gap: float
    scan_timestamp: datetime

class TagSuggestion(BaseModel):
    tag_key: str
    suggested_value: str
    confidence: float  # 0.0 to 1.0
    reasoning: str

class TagPolicy(BaseModel):
    version: str
    last_updated: datetime
    required_tags: list[RequiredTag]
    optional_tags: list[OptionalTag]
    tag_naming_rules: TagNamingRules
```

### Tagging Policy Schema

The policy configuration is the heart of the compliance engine - it defines what "good tagging" looks like for your organization. Customers must provide this configuration before the system can validate anything.

**Why is this important?** Every organization has different tagging needs. A startup might only care about "Environment" and "Owner" tags, while an enterprise might require 10+ tags for cost allocation, compliance, and operations. The policy schema lets you encode your specific rules.

#### Policy Structure

```python
class RequiredTag(BaseModel):
    name: str
    description: str
    allowed_values: list[str] | None = None
    validation_regex: str | None = None
    applies_to: list[str]  # Resource types this tag applies to

class OptionalTag(BaseModel):
    name: str
    description: str
    allowed_values: list[str] | None = None

class TagNamingRules(BaseModel):
    case_sensitivity: bool = False
    allow_special_characters: bool = False
    max_key_length: int = 128
    max_value_length: int = 256
```

#### Building Your Tagging Policy: A Quick Guide

**Step 1: Identify Your Core Tags**

Start with the FinOps Foundation's recommended minimum:
- **CostCenter** - Which team/department pays for this? (Critical for chargebacks)
- **Owner** - Who's responsible if something breaks? (Usually an email)
- **Environment** - Is this production, staging, or dev? (Affects cost allocation and risk)
- **Application** - What app/service does this belong to?

**Step 2: Define Allowed Values**

Don't leave values open-ended. If CostCenter can be anything, you'll end up with "Engineering", "engineering", "Eng", "eng-team" all meaning the same thing.

```json
{
  "name": "CostCenter",
  "allowed_values": ["Engineering", "Marketing", "Sales", "Operations", "Finance"]
}
```

**Step 3: Use Regex for Flexible Validation**

When you can't enumerate all values (like Owner emails), use regex:

```json
{
  "name": "Owner",
  "validation_regex": "^[a-z0-9._%+-]+@yourcompany\\.com$"
}
```

**Step 4: Scope Tags to Resource Types**

Not every tag makes sense for every resource. S3 buckets might need "DataClassification" but Lambda functions probably don't.

```json
{
  "name": "DataClassification",
  "applies_to": ["s3:bucket"],
  "allowed_values": ["public", "internal", "confidential", "restricted"]
}
```

#### Sample Starter Policy

A complete example is provided in [PHASE-1-SPECIFICATION.md](../../../PHASE-1-SPECIFICATION.md#tagging-policy-schema). Here's a minimal version to get started:

```json
{
  "version": "1.0",
  "required_tags": [
    {
      "name": "CostCenter",
      "description": "Department for cost allocation",
      "allowed_values": ["Engineering", "Marketing", "Sales", "Operations"],
      "applies_to": ["ec2:instance", "rds:db", "s3:bucket", "lambda:function"]
    },
    {
      "name": "Environment",
      "description": "Deployment environment",
      "allowed_values": ["production", "staging", "development"],
      "applies_to": ["ec2:instance", "rds:db", "lambda:function"]
    }
  ],
  "optional_tags": [],
  "tag_naming_rules": {
    "case_sensitivity": false
  }
}
```

**Pro tip:** Start with 2-3 required tags and expand over time. Trying to enforce 10 tags on day one will create massive violation counts and overwhelm teams.

### Cache Data Structures

```python
class CachedViolations(BaseModel):
    last_updated: datetime
    ttl_seconds: int
    violations_by_resource: dict[str, list[Violation]]
    violations_by_tag: dict[str, ViolationSummary]

class ViolationSummary(BaseModel):
    missing_count: int
    invalid_count: int
    cost_impact: float
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system - essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Compliance Score Bounds

*For any* set of resources scanned, the compliance score returned SHALL be between 0.0 and 1.0 inclusive, and SHALL equal the ratio of compliant resources to total resources. When total resources is zero, the score SHALL be 1.0 (fully compliant by default).

**Validates: Requirements 1.1**

### Property 2: Violation Detail Completeness

*For any* resource that fails policy validation, the violation object SHALL include: resource ID, resource type, violation type, tag name, and severity. When the violation is an invalid value, the object SHALL also include the current value and list of allowed values. Every validated resource SHALL have a clear compliant/non-compliant boolean status.

**Validates: Requirements 1.2, 3.2, 3.3, 3.4**

### Property 3: Filter Consistency

*For any* compliance check or resource search with filters applied (region, account, severity, cost threshold), all returned results SHALL match the specified filter criteria. No results outside the filter scope SHALL be included.

**Validates: Requirements 1.3, 1.4, 2.3, 2.4**

### Property 4: Resource Metadata Completeness

*For any* untagged resource returned, the result SHALL include: resource ID, resource type, region, current tags (even if empty), monthly cost estimate, and age in days. Resources with no tags or missing required tags SHALL be included in untagged searches.

**Validates: Requirements 2.1, 2.2, 2.5**

### Property 5: Cost Attribution Calculation

*For any* cost attribution analysis, the attribution gap SHALL equal (total cloud spend - attributable spend). The gap percentage SHALL equal (gap / total spend * 100). When grouping is specified, the sum of grouped gaps SHALL equal the total gap.

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 6: Suggestion Quality

*For any* tag suggestion returned, the suggestion SHALL include: tag key, suggested value, confidence score (between 0.0 and 1.0 inclusive), and non-empty reasoning string explaining the basis for the suggestion.

**Validates: Requirements 5.1, 5.2, 5.3**

### Property 7: Policy Structure Completeness

*For any* tagging policy returned, the policy SHALL include: version, last updated timestamp, required tags list, and optional tags list. Each required tag SHALL include: name, description, and applies_to list. Each tag with value restrictions SHALL include allowed_values or validation_regex.

**Validates: Requirements 6.1, 6.2, 6.3, 6.4**

### Property 8: Report Content Completeness

*For any* compliance report generated, the report SHALL include: overall compliance score, total resource count, compliant count, non-compliant count, and top violations ranked by count and cost impact. When recommendations are requested, actionable suggestions SHALL be included.

**Validates: Requirements 7.1, 7.3, 7.4, 7.5**

### Property 9: History Tracking Correctness

*For any* violation history request, the response SHALL include historical compliance scores grouped by the specified interval (day, week, or month). The trend direction SHALL be calculated correctly: "improving" if latest score > earliest score, "declining" if latest < earliest, "stable" otherwise.

**Validates: Requirements 8.1, 8.2, 8.3**

### Property 10: Policy Validation Correctness

*For any* resource validated against a policy: missing required tags SHALL be detected, invalid values (not in allowed list) SHALL be detected, values not matching regex patterns SHALL be detected, and tag requirements SHALL only apply to resource types listed in the tag's applies_to field.

**Validates: Requirements 9.2, 9.3, 9.4, 9.5**

### Property 11: Cache Behavior

*For any* cached violation data, the cache entry SHALL not be returned if its age exceeds the configured TTL. When fresh cached data exists for a query, the cached results SHALL be returned instead of re-scanning.

**Validates: Requirements 11.1, 11.3**

### Property 12: Audit Log Completeness

*For any* tool invocation, an audit log entry SHALL be created containing: timestamp, tool name, parameters, and result status (success/failure). When an error occurs, the error message SHALL be included in the log entry.

**Validates: Requirements 12.1, 12.3, 12.4**

### Property 13: Health Response Completeness

*For any* health check request when the server is healthy, the response SHALL include: status ("healthy"), version string, and list of supported cloud providers (["aws"] for Phase 1).

**Validates: Requirements 13.2**

### Property 14: Tool Budget Enforcement

*For any* agent session with a configured step budget (max tool calls), the MCP Server SHALL reject additional tool calls once the budget is exhausted and return a graceful degradation response explaining the limit was reached. The response SHALL NOT be an error but a structured message indicating budget exhaustion.

**Validates: Requirements 15.3, 15.5**

### Property 15: Loop Detection

*For any* sequence of tool calls within a session, the MCP Server SHALL detect when the same tool is called with identical parameters more than N times (configurable, default 3) and block further identical calls. The blocked call SHALL return a message explaining the loop was detected.

**Validates: Requirements 15.4**

### Property 16: Correlation ID Propagation

*For any* tool invocation, a unique correlation ID SHALL be generated and included in all log entries, audit records, and trace spans related to that invocation. The correlation ID SHALL be returned in the response headers or metadata.

**Validates: Requirements 15.1**

### Property 17: Input Schema Validation

*For any* tool invocation, the input parameters SHALL be validated against the tool's defined JSON schema before execution. Invalid inputs SHALL be rejected with a clear error message indicating which parameter failed validation and why.

**Validates: Requirements 16.3**

### Property 18: Unknown Tool Rejection

*For any* request to invoke a tool that is not registered in the MCP Server, the request SHALL be rejected with an error response. The rejection SHALL be logged with the attempted tool name for security monitoring.

**Validates: Requirements 16.1, 16.4**

## Error Handling

The system uses a consistent error handling strategy across all layers:

**Input Validation Errors** - Return immediately with clear error messages. Don't proceed with invalid inputs.

**AWS API Errors** - Implement exponential backoff for rate limits. Log errors and return partial results when possible.

**Cache Errors** - Fall back to direct AWS API calls if Redis is unavailable. Log the cache miss.

**Policy Loading Errors** - Fail fast at startup if the policy file is invalid or missing.

```python
class TagComplianceError(Exception):
    """Base exception for tag compliance errors"""
    pass

class PolicyValidationError(TagComplianceError):
    """Raised when policy configuration is invalid"""
    pass

class AWSAPIError(TagComplianceError):
    """Raised when AWS API calls fail"""
    pass

class CacheError(TagComplianceError):
    """Raised when cache operations fail"""
    pass
```

## Testing Strategy

Testing follows a dual approach: unit tests for specific behaviors and property-based tests for universal correctness guarantees.

**Unit Tests** focus on:
- Individual service methods with mocked dependencies
- Edge cases like empty resource lists, missing tags, invalid values
- Error handling paths
- Integration points with AWS (using moto for mocking)

**Property-Based Tests** verify the correctness properties defined above using Hypothesis. Each property test runs a minimum of 100 iterations with randomly generated inputs.

```python
# Example property test structure
from hypothesis import given, strategies as st

@given(
    total_resources=st.integers(min_value=0, max_value=10000),
    compliant_resources=st.integers(min_value=0)
)
def test_compliance_score_bounds(total_resources, compliant_resources):
    """
    Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
    Validates: Requirements 1.1
    """
    # Ensure compliant <= total
    compliant = min(compliant_resources, total_resources)
    
    result = calculate_compliance_score(compliant, total_resources)
    
    assert 0.0 <= result <= 1.0
    if total_resources > 0:
        assert result == compliant / total_resources
```

**Integration Tests** run against real AWS accounts (in a test environment) to verify end-to-end behavior. These are marked with `@pytest.mark.integration` and run separately from unit tests.

**Test Coverage Target**: 80% code coverage for unit tests.
