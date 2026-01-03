# Requirements: Agent Safety Enhancements (Intent Disambiguation)

## Introduction

This document captures requirements for enhancing the FinOps Tag Compliance MCP Server with intent disambiguation and approval mechanisms. These features address the "intent failure" problem where agents execute based on underspecified requests, potentially causing costly mistakes even with read-only operations.

**Why does this matter?** Even read-only FinOps operations can waste money (API calls, compute time) and mislead users if the agent guessed wrong about intent. A user saying "check my compliance" could mean EC2 in one region or all resources across all regions - a 100x difference in cost and time.

This builds on Phase 1's foundation (budget enforcement, loop detection, audit logging) by adding proactive intent clarification before execution.

**Scope:** These enhancements apply to all MCP tools, with special focus on high-cost operations like full account scans and Cost Explorer queries.

## Glossary

- **Intent**: The user's actual goal, including priorities, tradeoffs, what "done" means, and what would be regrettable
- **Context**: The text the user provides (which may be ambiguous or underspecified)
- **Intent_Commit**: A structured statement of what the agent believes the user wants, written before execution
- **Clarification_Loop**: A back-and-forth where the agent asks questions to resolve ambiguity before executing
- **Cost_Threshold**: A dollar or resource limit that triggers mandatory approval before execution
- **High_Stakes_Operation**: An operation that is expensive (API costs, time) or has broad impact (full account scan)

## Requirements

### Requirement 1: Intent Commit Pattern

**User Story:** As a user, I want the agent to tell me what it's about to do before it does it, so that I can catch misunderstandings before they waste time and money.

#### Acceptance Criteria

1. WHEN a tool is about to be invoked with ambiguous parameters, THE MCP_Server SHALL generate an intent commit describing what will be executed
2. THE intent commit SHALL include: target resources (types, regions, accounts), estimated scope (resource count), expected outcome, and potential regrettable scenarios
3. WHEN the intent commit is generated, THE MCP_Server SHALL return it to the agent for user confirmation before proceeding
4. THE MCP_Server SHALL log the intent commit in audit logs alongside the eventual execution
5. WHEN user confirms the intent, THE MCP_Server SHALL proceed with execution and reference the confirmed intent in logs

---

### Requirement 2: Ambiguity Detection

**User Story:** As a system, I need to detect when user requests are underspecified, so that I can trigger clarification loops instead of guessing.

#### Acceptance Criteria

1. THE MCP_Server SHALL detect ambiguous requests based on missing required context (region, resource type, time period)
2. WHEN resource_types parameter is omitted or set to "all", THE MCP_Server SHALL flag the request as ambiguous
3. WHEN a compliance check would scan more than 500 resources, THE MCP_Server SHALL flag it as high-stakes
4. WHEN a Cost Explorer query spans more than 30 days, THE MCP_Server SHALL flag it as high-stakes
5. THE MCP_Server SHALL maintain a configurable list of ambiguity triggers per tool

---

### Requirement 3: Clarification Loop

**User Story:** As a user, I want the agent to ask me clarifying questions when my request is vague, so that I get exactly what I need without wasting resources.

#### Acceptance Criteria

1. WHEN an ambiguous request is detected, THE MCP_Server SHALL return a clarification prompt instead of executing
2. THE clarification prompt SHALL include: what's ambiguous, suggested options, and estimated impact of each option
3. WHEN multiple ambiguities exist, THE MCP_Server SHALL prioritize the most impactful one first
4. THE MCP_Server SHALL support multi-turn clarification (ask follow-up questions if needed)
5. WHEN all ambiguities are resolved, THE MCP_Server SHALL generate an intent commit for final approval

---

### Requirement 4: Cost and Risk Thresholds

**User Story:** As an operator, I want to enforce cost and risk thresholds, so that expensive operations require explicit approval.

#### Acceptance Criteria

1. THE MCP_Server SHALL support configurable cost thresholds via environment variables (e.g., MAX_RESOURCES_WITHOUT_APPROVAL=500)
2. WHEN estimated resource count exceeds the threshold, THE MCP_Server SHALL require explicit approval before execution
3. WHEN estimated API cost exceeds a dollar threshold, THE MCP_Server SHALL require explicit approval
4. THE MCP_Server SHALL estimate costs based on: resource count × API call cost + Cost Explorer query cost
5. WHEN a threshold is exceeded, THE MCP_Server SHALL return a structured approval request with cost breakdown

---

### Requirement 5: Approval Workflow

**User Story:** As a user, I want a simple way to approve or reject high-stakes operations, so that I maintain control without friction.

#### Acceptance Criteria

1. WHEN approval is required, THE MCP_Server SHALL return a structured approval request (not an error)
2. THE approval request SHALL include: operation summary, estimated cost, estimated time, and approval token
3. WHEN the user provides the approval token, THE MCP_Server SHALL execute the operation
4. WHEN the user rejects or ignores the approval request, THE MCP_Server SHALL not execute and log the rejection
5. THE approval token SHALL expire after 5 minutes to prevent stale approvals

---

### Requirement 6: Intent Belief Logging

**User Story:** As an operator, I want to see what the agent believed the user's intent was, so that I can debug "why did it do that?" issues.

#### Acceptance Criteria

1. THE MCP_Server SHALL log the agent's interpretation of user intent before execution
2. THE intent log SHALL include: original user request (if available), inferred parameters, assumptions made, and alternatives considered
3. WHEN execution completes, THE MCP_Server SHALL log whether the outcome matched the stated intent
4. THE intent logs SHALL be queryable by correlation ID for debugging
5. THE MCP_Server SHALL include intent interpretation in audit trail exports

---

### Requirement 7: Dry Run Mode

**User Story:** As a user, I want to see what would happen without actually doing it, so that I can validate my request before committing.

#### Acceptance Criteria

1. THE MCP_Server SHALL support a dry_run parameter on all tools
2. WHEN dry_run is true, THE MCP_Server SHALL return what would be executed without making AWS API calls
3. THE dry run response SHALL include: resources that would be scanned, estimated API calls, estimated cost, and estimated execution time
4. THE MCP_Server SHALL log dry run requests separately from actual executions
5. WHEN dry_run is true, THE MCP_Server SHALL not increment tool call budgets

---

### Requirement 8: Fuzzy Prompt Testing

**User Story:** As a developer, I want to test how the system handles ambiguous prompts, so that I can ensure it disambiguates correctly.

#### Acceptance Criteria

1. THE test suite SHALL include fuzzy/ambiguous prompts for each tool
2. THE tests SHALL verify that ambiguous prompts trigger clarification loops (not immediate execution)
3. THE tests SHALL verify that clarified prompts generate correct intent commits
4. THE tests SHALL measure disambiguation quality (did it ask the right questions?)
5. THE test suite SHALL include adversarial prompts attempting to bypass disambiguation

---

### Requirement 9: AI-Powered Intent Review

**User Story:** As a system, I want to use AI to review intent commits for policy violations and risks, so that I can catch issues before execution.

#### Acceptance Criteria

1. THE MCP_Server SHALL support optional AI-powered intent review via LLM API
2. THE intent review SHALL check for: policy violations, cost risks, scope creep, and consistency with user history
3. WHEN the review detects high risk, THE MCP_Server SHALL escalate to human approval
4. WHEN the review detects low risk, THE MCP_Server SHALL proceed automatically
5. THE MCP_Server SHALL log all AI review decisions and confidence scores

---

### Requirement 10: Scope Estimation

**User Story:** As a user, I want to know how big an operation will be before it runs, so that I can decide if it's worth the cost and time.

#### Acceptance Criteria

1. THE MCP_Server SHALL estimate resource count before scanning (using AWS describe APIs with count-only queries)
2. THE MCP_Server SHALL estimate API call count based on resource count and pagination
3. THE MCP_Server SHALL estimate execution time based on historical averages
4. THE MCP_Server SHALL estimate dollar cost based on AWS API pricing
5. THE scope estimate SHALL be included in intent commits and approval requests

---

### Requirement 11: Progressive Disclosure

**User Story:** As a user, I want to start with a small sample and expand if needed, so that I don't waste resources on unnecessary full scans.

#### Acceptance Criteria

1. WHEN a request would scan more than 1000 resources, THE MCP_Server SHALL suggest starting with a sample
2. THE sample suggestion SHALL include: sample size (e.g., 100 resources), estimated time savings, and option to expand
3. WHEN the user approves the sample, THE MCP_Server SHALL execute on the sample and offer to expand
4. WHEN sample results are returned, THE MCP_Server SHALL include a "scan all" option with updated cost estimate
5. THE MCP_Server SHALL remember user preferences (always sample vs. always full scan) per session

---

### Requirement 12: Regret Prediction

**User Story:** As a system, I want to predict what might be regrettable about an operation, so that I can warn users proactively.

#### Acceptance Criteria

1. THE MCP_Server SHALL identify potentially regrettable scenarios based on operation type and scope
2. THE regret predictions SHALL include: "scanning wrong region", "missing critical resources", "wasting money on stale data"
3. WHEN a regrettable scenario is likely, THE MCP_Server SHALL include it in the intent commit
4. THE MCP_Server SHALL learn from user corrections (when they reject and clarify) to improve predictions
5. THE regret predictions SHALL be configurable per organization (different teams have different regrets)

