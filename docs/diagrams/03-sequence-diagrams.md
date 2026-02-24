# Sequence diagrams

## 1. Full compliance check workflow

This sequence diagram shows the complete flow for a compliance check, including caching, AWS API calls, and history storage.

```mermaid
sequenceDiagram
    actor User as Claude Desktop
    participant API as FastAPI Server
    participant MW as Middleware Stack
    participant MCP as MCP Handler
    participant Tool as check_tag_compliance
    participant CS as ComplianceService
    participant Cache as Redis Cache
    participant PS as PolicyService
    participant AWS as AWS Client
    participant RGTA as Resource Groups<br/>Tagging API
    participant Cost as Cost Explorer API
    participant HS as HistoryService
    participant DB as SQLite History DB
    participant Audit as AuditService
    participant ADB as SQLite Audit DB

    User->>+API: POST /mcp/tools/call<br/>{tool: "check_tag_compliance", params}

    API->>+MW: Process Request

    MW->>MW: CORS Check
    MW->>MW: Sanitize Input
    MW->>MW: Generate Correlation ID
    MW->>MW: Check Budget (100 calls/hour)
    MW->>MW: Check Loop Detection
    MW->>MW: Security Validation

    MW->>+MCP: Forward Request

    MCP->>MCP: Lookup Tool Definition
    MCP->>MCP: Validate Input Schema

    MCP->>+Tool: Invoke Handler<br/>(resource_types, filters, severity,<br/>store_snapshot, force_refresh)

    Tool->>+CS: check_compliance(params)

    alt Cache Check (force_refresh=false)
        CS->>CS: Generate Cache Key<br/>SHA256(params)
        CS->>+Cache: get(cache_key)
        Cache-->>-CS: Cache Hit / Miss

        alt Cache Hit
            CS-->>Tool: Return Cached ComplianceResult
            Note over CS,Cache: Cache hit - skip AWS calls
        end
    end

    alt Cache Miss or Force Refresh
        CS->>+PS: get_policy()
        PS->>PS: Load tagging_policy.json
        PS-->>-CS: Return TagPolicy

        CS->>+AWS: get_resources(resource_types, filters)
        AWS->>+RGTA: GetResources API Call
        RGTA-->>-AWS: Resource List with Tags

        alt AWS Throttling
            AWS->>AWS: Exponential Backoff Retry
        end

        AWS-->>-CS: List of Resources + Tags

        loop For Each Resource
            CS->>CS: Validate Tags Against Policy
            CS->>CS: Identify Violations
            CS->>CS: Calculate Severity
        end

        CS->>CS: Calculate Compliance Score<br/>(compliant / total * 100)

        CS->>+AWS: Get Cost Data
        AWS->>+Cost: GetCostAndUsage API Call<br/>(for non-compliant resources)
        Cost-->>-AWS: Cost Data
        AWS-->>-CS: Cost Attribution Gap

        CS->>CS: Build ComplianceResult

        CS->>+Cache: set(cache_key, result, ttl=1h)
        Cache-->>-CS: Cache Updated
    end

    CS-->>-Tool: Return ComplianceResult

    alt store_snapshot=true
        Tool->>+HS: store_snapshot(result)
        HS->>+DB: INSERT INTO compliance_history
        DB-->>-HS: Snapshot Stored
        HS-->>-Tool: Success
    end

    Tool->>Tool: Format Response as JSON
    Tool-->>-MCP: Return MCPToolResult

    MCP->>+Audit: log_invocation(tool_name, params, result)
    Audit->>+ADB: INSERT INTO audit_log
    ADB-->>-Audit: Log Stored
    Audit-->>-MCP: Audit Complete

    MCP-->>-MW: Return Response
    MW-->>-API: Forward Response
    API-->>-User: HTTP 200 OK<br/>{compliance_score, violations, cost_gap}

    Note over User,ADB: Total Round Trip: ~2-5 seconds<br/>Cached: ~100-200ms
```

## 2. Tag suggestion workflow

This sequence diagram shows how the system generates intelligent tag suggestions for a resource.

```mermaid
sequenceDiagram
    actor User as Claude Desktop
    participant API as FastAPI Server
    participant MCP as MCP Handler
    participant Tool as suggest_tags
    participant SS as SuggestionService
    participant AWS as AWS Client
    participant EC2 as EC2 API
    participant PS as PolicyService

    User->>+API: POST /mcp/tools/call<br/>{tool: "suggest_tags",<br/>params: {resource_arn}}

    API->>+MCP: Route Request
    MCP->>+Tool: Invoke suggest_tags(resource_arn)

    Tool->>+SS: suggest_tags_for_resource(arn)

    SS->>SS: Parse ARN<br/>(extract service, region, resource_id)

    SS->>+AWS: describe_resource(resource_id)
    AWS->>+EC2: DescribeInstances / DescribeVolumes / etc.
    EC2-->>-AWS: Resource Details + Metadata
    AWS-->>-SS: Resource Info

    SS->>SS: Analyze Resource Name Pattern<br/>(e.g., "web-prod-01")

    par Pattern Analysis
        SS->>SS: Check for Environment Keywords<br/>(prod, dev, staging, test)
        SS->>SS: Check for Team/Owner Keywords<br/>(backend, frontend, platform)
        SS->>SS: Check for Application Keywords
    end

    SS->>+AWS: Find Similar Resources<br/>(same VPC, same subnet, etc.)
    AWS->>+EC2: DescribeInstances with Filters
    EC2-->>-AWS: Similar Resources
    AWS-->>-SS: Similar Resource Tags

    SS->>SS: Analyze Common Tags<br/>on Similar Resources

    SS->>+PS: get_policy()
    PS-->>-SS: Required Tags List

    loop For Each Required Tag
        SS->>SS: Generate Suggestion
        SS->>SS: Calculate Confidence Score<br/>(0.0 - 1.0)
        SS->>SS: Generate Reasoning Text
    end

    SS->>SS: Rank Suggestions by Confidence

    SS-->>-Tool: Return Tag Suggestions<br/>[{tag, value, confidence, reasoning}]

    Tool->>Tool: Format as JSON
    Tool-->>-MCP: Return MCPToolResult
    MCP-->>-API: Forward Response
    API-->>-User: HTTP 200 OK<br/>{suggestions: [...]}

    Note over User,PS: Suggestion Quality Improves<br/>with More Tagged Resources
```

## 3. Cost attribution gap analysis workflow

This sequence diagram shows how cost attribution gaps are calculated.

```mermaid
sequenceDiagram
    actor User as Claude Desktop
    participant API as FastAPI Server
    participant MCP as MCP Handler
    participant Tool as get_cost_attribution_gap
    participant Cost as CostService
    participant CS as ComplianceService
    participant AWS as AWS Client
    participant CE as Cost Explorer API
    participant RGTA as Resource Groups<br/>Tagging API
    participant PS as PolicyService

    User->>+API: POST /mcp/tools/call<br/>{tool: "get_cost_attribution_gap",<br/>params: {resource_types, time_period, group_by}}

    API->>+MCP: Route Request
    MCP->>+Tool: Invoke get_cost_attribution_gap(params)

    Tool->>+Cost: calculate_attribution_gap(params)

    par Get Resources and Costs
        Cost->>+CS: get_resources(resource_types)
        CS->>+AWS: get_resources()
        AWS->>+RGTA: GetResources API Call
        RGTA-->>-AWS: All Resources
        AWS-->>-CS: Resource List
        CS-->>-Cost: Resources with Tags
    and
        Cost->>+AWS: get_cost_data(time_period)
        AWS->>+CE: GetCostAndUsage API Call<br/>(GroupBy: SERVICE, REGION)
        CE-->>-AWS: Cost Data
        AWS-->>-Cost: Aggregated Costs
    end

    Cost->>+PS: get_policy()
    PS-->>-Cost: Required Tags

    loop For Each Resource
        Cost->>Cost: Check Tag Compliance
        alt Resource is Compliant
            Cost->>Cost: Add to attributable_resources
        else Resource is Non-Compliant
            Cost->>Cost: Add to unattributable_resources
        end
    end

    loop For Each Resource
        Cost->>+AWS: get_resource_cost(resource_id, time_period)
        AWS->>+CE: GetCostAndUsage<br/>(Filter by Resource ID)
        CE-->>-AWS: Resource-specific Cost
        AWS-->>-Cost: Cost Amount

        alt Resource is Compliant
            Cost->>Cost: Add to attributable_spend
        else Resource is Non-Compliant
            Cost->>Cost: Add to unattributable_spend
        end
    end

    Cost->>Cost: Calculate Total Spend
    Cost->>Cost: Calculate Attribution Gap<br/>(unattributable / total * 100)

    alt group_by specified
        Cost->>Cost: Group Results by<br/>(resource_type, region, account)

        loop For Each Group
            Cost->>Cost: Calculate Group Metrics<br/>(spend, gap, percentage)
        end
    end

    Cost->>Cost: Build CostAttributionGap Response
    Cost-->>-Tool: Return Gap Analysis

    Tool->>Tool: Format as JSON
    Tool-->>-MCP: Return MCPToolResult
    MCP-->>-API: Forward Response
    API-->>-User: HTTP 200 OK<br/>{total_spend, attribution_gap,<br/>gap_percentage, breakdown}

    Note over User,CE: Cost Explorer API Calls<br/>Can Take 3-10 seconds
```

## 4. Violation history trend analysis workflow

This sequence diagram shows how historical compliance trends are retrieved and analyzed.

```mermaid
sequenceDiagram
    actor User as Claude Desktop
    participant API as FastAPI Server
    participant MCP as MCP Handler
    participant Tool as get_violation_history
    participant HS as HistoryService
    participant DB as SQLite History DB

    User->>+API: POST /mcp/tools/call<br/>{tool: "get_violation_history",<br/>params: {days_back, group_by}}

    API->>+MCP: Route Request
    MCP->>+Tool: Invoke get_violation_history(params)

    Tool->>+HS: get_history(days_back, group_by)

    HS->>HS: Calculate Start Date<br/>(today - days_back)

    HS->>+DB: SELECT * FROM compliance_history<br/>WHERE timestamp >= start_date<br/>ORDER BY timestamp ASC
    DB-->>-HS: Historical Snapshots

    alt No History Found
        HS-->>Tool: Return Empty History
        Note over HS,DB: No data available
    end

    alt group_by = "day"
        HS->>HS: Group by Date (YYYY-MM-DD)
    else group_by = "week"
        HS->>HS: Group by ISO Week Number
    else group_by = "month"
        HS->>HS: Group by Year-Month
    end

    loop For Each Time Period
        HS->>HS: Aggregate Snapshots<br/>(avg compliance_score,<br/>sum violations, sum resources)
        HS->>HS: Identify Most Common Violations
    end

    HS->>HS: Calculate Trend Direction

    alt Latest Score > First Score
        HS->>HS: Trend = IMPROVING
    else Latest Score < First Score
        HS->>HS: Trend = DECLINING
    else Latest Score == First Score
        HS->>HS: Trend = STABLE
    end

    HS->>HS: Calculate Change Percentage<br/>((latest - first) / first * 100)

    HS->>HS: Build History Response<br/>{snapshots, trend, change_percentage}

    HS-->>-Tool: Return ViolationHistory

    Tool->>Tool: Format as JSON
    Tool-->>-MCP: Return MCPToolResult
    MCP-->>-API: Forward Response
    API-->>-User: HTTP 200 OK<br/>{history: [...], trend, change_pct}

    Note over User,DB: Historical Analysis<br/>Enables Tracking Progress
```

## 5. Error handling and retry flow

This sequence diagram shows how the system handles AWS API errors and implements retry logic.

```mermaid
sequenceDiagram
    actor User as Claude Desktop
    participant API as FastAPI Server
    participant Tool as Tool Handler
    participant CS as ComplianceService
    participant AWS as AWS Client
    participant API_AWS as AWS API

    User->>+API: Request Tool Invocation
    API->>+Tool: Invoke Tool
    Tool->>+CS: Execute Service Method
    CS->>+AWS: get_resources()

    AWS->>+API_AWS: API Call (Attempt 1)

    alt Success
        API_AWS-->>-AWS: 200 OK + Data
        AWS-->>CS: Return Resources
    else Throttling Error (429)
        API_AWS-->>AWS: 429 ThrottlingException
        AWS->>AWS: Wait 2s (Exponential Backoff)
        AWS->>+API_AWS: API Call (Attempt 2)

        alt Success
            API_AWS-->>-AWS: 200 OK + Data
            AWS-->>CS: Return Resources
        else Still Throttled
            API_AWS-->>AWS: 429 ThrottlingException
            AWS->>AWS: Wait 4s
            AWS->>+API_AWS: API Call (Attempt 3)

            alt Success
                API_AWS-->>-AWS: 200 OK + Data
                AWS-->>CS: Return Resources
            else Max Retries Exceeded
                API_AWS-->>AWS: 429 ThrottlingException
                AWS-->>-CS: Raise AWSThrottlingError
                CS-->>-Tool: Propagate Error
                Tool-->>-API: Return Error Response
                API-->>-User: HTTP 503 Service Unavailable<br/>{error: "AWS throttling", retry_after: 60}
            end
        end
    else Authorization Error (403)
        API_AWS-->>-AWS: 403 AccessDenied
        AWS-->>-CS: Raise AWSAuthError
        CS-->>-Tool: Propagate Error
        Tool->>Tool: Sanitize Error Message<br/>(remove credentials, paths)
        Tool-->>-API: Return Error Response
        API-->>-User: HTTP 500 Internal Server Error<br/>{error: "AWS access denied"}
    else Network Error
        API_AWS-->>-AWS: Network Timeout
        AWS->>AWS: Wait 2s
        AWS->>+API_AWS: API Call (Attempt 2)

        alt Success
            API_AWS-->>-AWS: 200 OK + Data
            AWS-->>CS: Return Resources
        else Still Failing
            API_AWS-->>-AWS: Network Timeout
            AWS-->>-CS: Raise NetworkError
            CS-->>-Tool: Propagate Error
            Tool-->>-API: Return Error Response
            API-->>-User: HTTP 504 Gateway Timeout
        end
    end

    Note over User,API_AWS: Retry Strategy:<br/>Exponential Backoff<br/>2s, 4s, 8s delays
```

## Key sequence flow insights

### 1. Compliance check flow
- **Duration**: 2-5 seconds (cache miss), 100-200ms (cache hit)
- **Bottlenecks**: AWS API calls, Cost Explorer queries
- **Optimization**: Redis caching reduces AWS API calls by ~80%

### 2. Tag suggestion flow
- **Duration**: 3-7 seconds
- **Complexity**: Analyzes resource metadata, naming patterns, and similar resources
- **Accuracy**: Improves as more resources become tagged

### 3. Cost attribution flow
- **Duration**: 3-10 seconds
- **Cost**: Expensive due to Cost Explorer API calls
- **Grouping**: Allows breakdown by resource type, region, or account

### 4. History flow
- **Duration**: 100-500ms
- **Data Source**: SQLite local database
- **Analysis**: Supports day/week/month grouping for trend analysis

### 5. Error handling flow
- **Retry Logic**: Exponential backoff (2s, 4s, 8s)
- **Max Retries**: 3 attempts
- **Error Sanitization**: Removes sensitive data from user-facing errors

## Timing summary

| Workflow | Average Duration | Cache Impact |
|----------|-----------------|--------------|
| Compliance Check | 2-5s | -90% (cached) |
| Tag Suggestions | 3-7s | N/A |
| Cost Attribution | 3-10s | -50% (partial cache) |
| History Analysis | 100-500ms | N/A |
| Policy Retrieval | 10-50ms | In-memory cache |

## Parallelization opportunities

Several operations can be parallelized:
1. **Resource scanning across regions** - Multiple AWS API calls in parallel
2. **Cost data retrieval** - Batch requests to Cost Explorer
3. **Similar resource analysis** - Multiple EC2 DescribeInstances calls
4. **Multi-tool invocations** - User can call multiple tools simultaneously
