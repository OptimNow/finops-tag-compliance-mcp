# Requirements: Phase 1 - AWS Tag Compliance MVP

## Introduction

This document captures the requirements for Phase 1 of the FinOps Tag Compliance MCP Server - a focused MVP that tackles the cloud tagging problem head-on, starting with AWS.

**Why does this matter?** Enterprises are hemorrhaging money because they can't track where their cloud spend goes. The culprit? Missing or inconsistent resource tags. We're building an intelligent MCP server that doesn't just read tags - it validates them, shows you the financial damage of violations, and helps you fix them fast.

Phase 1 keeps things simple: AWS only, 8 essential tools, deployed on a single EC2 instance. We prove the concept works, gather feedback, then scale.

For the complete technical vision, see [PHASE-1-SPECIFICATION.md](../../../docs/PHASE-1-SPECIFICATION.md).

## Glossary

- **MCP_Server**: The Model Context Protocol server that exposes tag compliance tools to AI assistants like Claude
- **Tag_Policy**: A JSON configuration defining required tags, allowed values, and validation rules for cloud resources
- **Compliance_Score**: A percentage (0-100%) indicating how many resources meet tagging requirements
- **Cost_Attribution_Gap**: The dollar amount of cloud spend that cannot be allocated to teams/projects due to missing tags
- **Violation**: A resource that fails to meet one or more tagging policy requirements
- **Resource_Type**: Categories of AWS resources (ec2:instance, rds:db, s3:bucket, lambda:function, ecs:service)

## Requirements

### Requirement 1: Tag Compliance Checking

**User Story:** As a FinOps practitioner, I want to check how well my AWS resources comply with our tagging policy, so that I can identify and prioritize remediation efforts.

#### Acceptance Criteria

1. WHEN a user requests a compliance check, THE MCP_Server SHALL scan specified AWS resource types and return a compliance score
2. WHEN violations are found, THE MCP_Server SHALL return details including resource ID, resource type, violation type, and severity
3. WHEN filtering by region or account, THE MCP_Server SHALL only scan resources matching those filters
4. THE MCP_Server SHALL support filtering by severity level (errors only, warnings only, or all)
5. THE MCP_Server SHALL complete compliance checks for up to 1000 resources within 5 seconds

---

### Requirement 2: Untagged Resource Discovery

**User Story:** As a DevOps engineer, I want to find all resources that are completely untagged or missing critical tags, so that I can understand the scope of our tagging problem.

#### Acceptance Criteria

1. WHEN a user searches for untagged resources, THE MCP_Server SHALL return all resources with no tags or missing required tags
2. WHEN results are returned, THE MCP_Server SHALL include the monthly cost estimate for each untagged resource
3. WHEN a minimum cost threshold is specified, THE MCP_Server SHALL only return resources exceeding that threshold
4. THE MCP_Server SHALL support searching across multiple AWS regions in a single request
5. WHEN results are returned, THE MCP_Server SHALL include the resource age in days

---

### Requirement 3: Individual Resource Validation

**User Story:** As a developer, I want to validate specific resources against our tagging policy before or after deployment, so that I can catch compliance issues early.

#### Acceptance Criteria

1. WHEN given one or more resource ARNs, THE MCP_Server SHALL validate each against the tagging policy
2. WHEN a resource has violations, THE MCP_Server SHALL return the specific tag issues (missing, invalid value, wrong format)
3. WHEN a tag has an invalid value, THE MCP_Server SHALL return both the current value and the list of allowed values
4. THE MCP_Server SHALL return a clear compliant/non-compliant status for each resource

---

### Requirement 4: Cost Attribution Gap Analysis

**User Story:** As a FinOps practitioner, I want to see the financial impact of our tagging gaps, so that I can make a business case for remediation and report to leadership.

#### Acceptance Criteria

1. WHEN a user requests cost attribution analysis, THE MCP_Server SHALL calculate total cloud spend vs. attributable spend
2. THE MCP_Server SHALL return the attribution gap as both a dollar amount and percentage
3. WHEN grouping is specified, THE MCP_Server SHALL break down the gap by resource type, region, or account
4. THE MCP_Server SHALL integrate with AWS Cost Explorer to retrieve accurate cost data
5. WHEN time period is specified, THE MCP_Server SHALL calculate the gap for that specific date range

---

### Requirement 5: Intelligent Tag Suggestions

**User Story:** As a DevOps engineer, I want the system to suggest appropriate tags for untagged resources, so that I can fix violations quickly without guessing.

#### Acceptance Criteria

1. WHEN given a resource ARN, THE MCP_Server SHALL analyze patterns and suggest appropriate tag values
2. WHEN suggestions are returned, THE MCP_Server SHALL include a confidence score (0-1) for each suggestion
3. WHEN suggestions are returned, THE MCP_Server SHALL explain the reasoning behind each suggestion
4. THE MCP_Server SHALL base suggestions on patterns like VPC naming, IAM user/role, instance type, and similar resources

---

### Requirement 6: Tagging Policy Retrieval

**User Story:** As a team lead, I want to view our organization's tagging policy, so that I understand what tags are required and what values are allowed.

#### Acceptance Criteria

1. WHEN a user requests the tagging policy, THE MCP_Server SHALL return the complete policy configuration
2. THE MCP_Server SHALL return required tags with their descriptions, allowed values, and validation rules
3. THE MCP_Server SHALL return optional tags with their descriptions
4. THE MCP_Server SHALL indicate which resource types each tag applies to

---

### Requirement 7: Compliance Reporting

**User Story:** As a FinOps practitioner, I want to generate comprehensive compliance reports, so that I can share findings with stakeholders and track progress over time.

#### Acceptance Criteria

1. WHEN a user requests a compliance report, THE MCP_Server SHALL generate a summary with overall compliance score
2. THE MCP_Server SHALL support output formats of JSON, CSV, and Markdown
3. WHEN recommendations are requested, THE MCP_Server SHALL include actionable remediation suggestions
4. THE MCP_Server SHALL include top violations ranked by count and cost impact
5. THE MCP_Server SHALL include total resource counts (compliant vs. non-compliant)

---

### Requirement 8: Violation History Tracking

**User Story:** As a FinOps practitioner, I want to track compliance trends over time, so that I can measure improvement and identify regression.

#### Acceptance Criteria

1. WHEN a user requests violation history, THE MCP_Server SHALL return historical compliance scores
2. THE MCP_Server SHALL support grouping history by day, week, or month
3. THE MCP_Server SHALL calculate and return the trend direction (improving, declining, stable)
4. THE MCP_Server SHALL support looking back up to 90 days of history
5. THE MCP_Server SHALL store compliance scan results in a local SQLite database for historical tracking

---

### Requirement 9: Tagging Policy Validation Engine

**User Story:** As a system, I need to validate resources against configurable policies, so that compliance checking is consistent and customizable.

#### Acceptance Criteria

1. THE MCP_Server SHALL load tagging policy from a JSON configuration file
2. THE MCP_Server SHALL validate tag presence for required tags
3. THE MCP_Server SHALL validate tag values against allowed value lists when specified
4. THE MCP_Server SHALL validate tag values against regex patterns when specified
5. THE MCP_Server SHALL apply tag requirements only to applicable resource types as defined in the policy

---

### Requirement 10: AWS Integration

**User Story:** As a system, I need secure access to AWS resources and cost data, so that I can perform compliance checks without exposing credentials.

#### Acceptance Criteria

1. THE MCP_Server SHALL authenticate to AWS using IAM instance profile (no hardcoded credentials)
2. THE MCP_Server SHALL support read access to EC2, RDS, S3, Lambda, and ECS resources
3. THE MCP_Server SHALL integrate with AWS Cost Explorer for cost data retrieval
4. THE MCP_Server SHALL respect AWS API rate limits and implement appropriate backoff
5. THE MCP_Server SHALL cache AWS API responses in Redis to minimize API calls

---

### Requirement 11: Caching and Performance

**User Story:** As a system, I need to cache compliance data efficiently, so that repeated queries are fast and we don't overwhelm AWS APIs.

#### Acceptance Criteria

1. THE MCP_Server SHALL cache violation data in Redis with a configurable TTL
2. THE MCP_Server SHALL invalidate cache when a new compliance scan is triggered
3. WHEN cached data exists and is fresh, THE MCP_Server SHALL return cached results
4. THE MCP_Server SHALL respond to health check requests within 100 milliseconds

---

### Requirement 12: Audit Logging

**User Story:** As a security administrator, I want all tool invocations logged, so that I can audit who accessed what data and when.

#### Acceptance Criteria

1. THE MCP_Server SHALL log every tool invocation with timestamp, tool name, and parameters
2. THE MCP_Server SHALL store audit logs in SQLite database
3. THE MCP_Server SHALL include the result status (success/failure) in audit logs
4. IF an error occurs, THEN THE MCP_Server SHALL log the error message

---

### Requirement 13: Health and Monitoring

**User Story:** As an operator, I want to monitor the MCP server's health, so that I can ensure it's running properly and troubleshoot issues.

#### Acceptance Criteria

1. THE MCP_Server SHALL expose a health check endpoint at /health
2. WHEN healthy, THE MCP_Server SHALL return status, version, and supported cloud providers
3. THE MCP_Server SHALL log operational metrics to CloudWatch
4. THE MCP_Server SHALL run stable for 7+ days without requiring restart

---

### Requirement 14: Deployment and Configuration

**User Story:** As a DevOps engineer, I want to deploy the MCP server easily, so that I can get it running quickly without complex setup.

#### Acceptance Criteria

1. THE MCP_Server SHALL be packaged as a Docker container
2. THE MCP_Server SHALL be configurable via environment variables
3. THE MCP_Server SHALL include a docker-compose.yml for local development
4. THE MCP_Server SHALL run on a t3.medium EC2 instance with 4GB RAM
5. THE MCP_Server SHALL expose the MCP protocol on port 8080

---

### Requirement 15: Agent Observability and Guardrails

**User Story:** As an operator, I want to track how AI agents consume my MCP tools and enforce usage limits, so that I can optimize cost, detect anomalies, and prevent runaway behavior.

#### Acceptance Criteria

1. THE MCP_Server SHALL include a correlation ID in every tool invocation for end-to-end tracing
2. THE MCP_Server SHALL log tool-call counts and execution time per request
3. THE MCP_Server SHALL enforce tool-call budgets (max calls per session) when configured via environment variable
4. THE MCP_Server SHALL detect and block repeated identical tool calls (loop detection) after N occurrences (configurable, default 3)
5. THE MCP_Server SHALL return a graceful degradation response when budgets are exceeded, explaining the limit was reached
6. THE MCP_Server SHALL classify failure reasons in logs (tool error, timeout, policy violation, budget exceeded)

---

### Requirement 16: Security and Prompt Injection Resistance

**User Story:** As a security administrator, I want the MCP server to resist prompt injection and tool misuse attempts, so that it cannot be tricked into unauthorized actions.

#### Acceptance Criteria

1. THE MCP_Server SHALL only respond to requests for its registered tools (check_tag_compliance, find_untagged_resources, etc.)
2. THE MCP_Server SHALL NOT execute arbitrary code or access resources outside its defined scope
3. THE MCP_Server SHALL validate all tool inputs against their defined schemas before execution
4. THE MCP_Server SHALL log and reject requests that attempt to invoke non-existent or unauthorized tools
5. THE MCP_Server SHALL NOT expose sensitive information (credentials, internal paths) in error messages

---

### Requirement 17: Expanded Resource Coverage via Resource Groups Tagging API

**User Story:** As a FinOps practitioner, I want to check tag compliance across ALL AWS resource types (not just EC2, RDS, S3, Lambda, ECS), so that I can get a complete picture of my organization's tagging posture.

#### Acceptance Criteria

1. THE MCP_Server SHALL use the AWS Resource Groups Tagging API (`tag:GetResources`) as the primary method for resource discovery
2. THE MCP_Server SHALL support 50+ AWS resource types through a single unified API
3. WHEN a user specifies `resource_types: ["all"]`, THE MCP_Server SHALL scan all taggable resources in the account
4. THE MCP_Server SHALL support filtering by specific resource types using AWS resource type strings (e.g., `ec2:instance`, `rds:db`, `elasticache:cluster`)
5. THE MCP_Server SHALL handle pagination for accounts with large numbers of resources (1000+ resources)
6. THE MCP_Server SHALL fall back to individual service APIs only when Resource Groups Tagging API is unavailable or returns incomplete data
7. THE MCP_Server SHALL include the resource ARN, tags, and resource type for each discovered resource
