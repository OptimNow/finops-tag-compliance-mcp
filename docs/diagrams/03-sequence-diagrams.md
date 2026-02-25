# Sequence diagrams

## 1. Full compliance check workflow

This sequence diagram shows the complete flow for a compliance check via stdio, including multi-region scanning, caching, AWS API calls, and history storage.

```mermaid
sequenceDiagram
    actor User as Claude Desktop
    participant MCP as FastMCP stdio server
    participant Guard as Guardrails<br/>(Budget + Loop)
    participant Tool as check_tag_compliance
    participant Scanner as MultiRegionScanner
    participant CS as ComplianceService
    participant Cache as Redis Cache<br/>(optional)
    participant PS as PolicyService
    participant AWS as AWS Client
    participant RGTA as Resource Groups<br/>Tagging API
    participant Cost as Cost Explorer API
    participant HS as HistoryService
    participant DB as SQLite History DB
    participant Audit as AuditService
    participant ADB as SQLite Audit DB

    User->>+MCP: JSON-RPC request<br/>{tool: "check_tag_compliance", params}

    MCP->>MCP: Parse JSON-RPC
    MCP->>MCP: Validate input schema

    MCP->>+Guard: Check guardrails
    Guard->>Guard: Budget check (100 calls/session)
    Guard->>Guard: Loop detection (3 identical/5 min)
    Guard-->>-MCP: Guardrails passed

    MCP->>+Tool: Invoke handler<br/>(resource_types, filters, severity,<br/>store_snapshot, force_refresh)

    Tool->>+Scanner: scan_all_regions(params)

    Scanner->>Scanner: Discover enabled regions<br/>(via EC2 DescribeRegions)

    par Parallel region scanning
        Scanner->>+CS: check_compliance(region_1)
    and
        Scanner->>+CS: check_compliance(region_2)
    and
        Scanner->>+CS: check_compliance(region_N)
    end

    Note over CS: Each region follows same flow:

    alt Cache check (force_refresh=false)
        CS->>CS: Generate cache key<br/>SHA256(params + region)
        CS->>+Cache: get(cache_key)
        Cache-->>-CS: Cache hit / miss

        alt Cache hit
            CS-->>Scanner: Return cached result
            Note over CS,Cache: Cache hit — skip AWS calls
        end
    end

    alt Cache miss or force refresh
        CS->>+PS: get_policy()
        PS->>PS: Load tagging_policy.json
        PS-->>-CS: Return TagPolicy

        CS->>+AWS: get_resources(resource_types, filters)
        AWS->>+RGTA: GetResources API call
        RGTA-->>-AWS: Resource list with tags

        alt AWS throttling
            AWS->>AWS: Exponential backoff retry
        end

        AWS-->>-CS: List of resources + tags

        loop For each resource
            CS->>CS: Validate tags against policy
            CS->>CS: Identify violations
            CS->>CS: Calculate severity
        end

        CS->>CS: Calculate compliance score<br/>(compliant / total * 100)

        CS->>+Cache: set(cache_key, result, ttl=1h)
        Cache-->>-CS: Cache updated
    end

    CS-->>-Scanner: Return regional result
    CS-->>-Scanner: Return regional result
    CS-->>-Scanner: Return regional result

    Scanner->>Scanner: Aggregate regional results<br/>into MultiRegionComplianceResult

    Scanner-->>-Tool: Return aggregated result

    alt store_snapshot=true
        Tool->>+HS: store_snapshot(result)
        HS->>+DB: INSERT INTO compliance_history
        DB-->>-HS: Snapshot stored
        HS-->>-Tool: Success
    end

    Tool->>+Audit: log_invocation(tool_name, params, result)
    Audit->>+ADB: INSERT INTO audit_log
    ADB-->>-Audit: Log stored
    Audit-->>-Tool: Audit complete

    Tool->>Tool: Format response as JSON
    Tool-->>-MCP: Return tool result

    MCP-->>-User: JSON-RPC response<br/>{compliance_score, violations,<br/>regional_breakdown}

    Note over User,ADB: Total: ~3-10 seconds (multi-region)<br/>Cached: ~100-200ms
```

## 2. Tag suggestion workflow

This sequence diagram shows how the system generates intelligent tag suggestions for a resource.

```mermaid
sequenceDiagram
    actor User as Claude Desktop
    participant MCP as FastMCP stdio server
    participant Tool as suggest_tags
    participant SS as SuggestionService
    participant AWS as AWS Client
    participant EC2 as EC2 API
    participant PS as PolicyService

    User->>+MCP: JSON-RPC request<br/>{tool: "suggest_tags",<br/>params: {resource_arn}}

    MCP->>+Tool: Invoke suggest_tags(resource_arn)

    Tool->>+SS: suggest_tags_for_resource(arn)

    SS->>SS: Parse ARN<br/>(extract service, region, resource_id)

    SS->>+AWS: describe_resource(resource_id)
    AWS->>+EC2: DescribeInstances / DescribeVolumes / etc.
    EC2-->>-AWS: Resource details + metadata
    AWS-->>-SS: Resource info

    SS->>SS: Analyze resource name pattern<br/>(e.g., "web-prod-01")

    par Pattern analysis
        SS->>SS: Check for environment keywords<br/>(prod, dev, staging, test)
        SS->>SS: Check for team/owner keywords<br/>(backend, frontend, platform)
        SS->>SS: Check for application keywords
    end

    SS->>+AWS: Find similar resources<br/>(same VPC, same subnet, etc.)
    AWS->>+EC2: DescribeInstances with filters
    EC2-->>-AWS: Similar resources
    AWS-->>-SS: Similar resource tags

    SS->>SS: Analyze common tags<br/>on similar resources

    SS->>+PS: get_policy()
    PS-->>-SS: Required tags list

    loop For each required tag
        SS->>SS: Generate suggestion
        SS->>SS: Calculate confidence score<br/>(0.0 - 1.0)
        SS->>SS: Generate reasoning text
    end

    SS->>SS: Rank suggestions by confidence

    SS-->>-Tool: Return tag suggestions<br/>[{tag, value, confidence, reasoning}]

    Tool->>Tool: Format as JSON
    Tool-->>-MCP: Return tool result
    MCP-->>-User: JSON-RPC response<br/>{suggestions: [...]}

    Note over User,PS: Suggestion quality improves<br/>with more tagged resources
```

## 3. Cost attribution gap analysis workflow

This sequence diagram shows how cost attribution gaps are calculated.

```mermaid
sequenceDiagram
    actor User as Claude Desktop
    participant MCP as FastMCP stdio server
    participant Tool as get_cost_attribution_gap
    participant Cost as CostService
    participant CS as ComplianceService
    participant AWS as AWS Client
    participant CE as Cost Explorer API
    participant RGTA as Resource Groups<br/>Tagging API
    participant PS as PolicyService

    User->>+MCP: JSON-RPC request<br/>{tool: "get_cost_attribution_gap",<br/>params: {resource_types, time_period, group_by}}

    MCP->>+Tool: Invoke get_cost_attribution_gap(params)

    Tool->>+Cost: calculate_attribution_gap(params)

    par Get resources and costs
        Cost->>+CS: get_resources(resource_types)
        CS->>+AWS: get_resources()
        AWS->>+RGTA: GetResources API call
        RGTA-->>-AWS: All resources
        AWS-->>-CS: Resource list
        CS-->>-Cost: Resources with tags
    and
        Cost->>+AWS: get_cost_data(time_period)
        AWS->>+CE: GetCostAndUsage API call<br/>(GroupBy: SERVICE, REGION)
        CE-->>-AWS: Cost data
        AWS-->>-Cost: Aggregated costs
    end

    Cost->>+PS: get_policy()
    PS-->>-Cost: Required tags

    loop For each resource
        Cost->>Cost: Check tag compliance
        alt Resource is compliant
            Cost->>Cost: Add to attributable spend
        else Resource is non-compliant
            Cost->>Cost: Add to unattributable spend
        end
    end

    Cost->>Cost: Calculate total spend
    Cost->>Cost: Calculate attribution gap<br/>(unattributable / total * 100)

    alt group_by specified
        Cost->>Cost: Group results by<br/>(resource_type, region, account)

        loop For each group
            Cost->>Cost: Calculate group metrics<br/>(spend, gap, percentage)
        end
    end

    Cost->>Cost: Build CostAttributionGap response
    Cost-->>-Tool: Return gap analysis

    Tool->>Tool: Format as JSON
    Tool-->>-MCP: Return tool result
    MCP-->>-User: JSON-RPC response<br/>{total_spend, attribution_gap,<br/>gap_percentage, breakdown}

    Note over User,CE: Cost Explorer API calls<br/>can take 3-10 seconds
```

## 4. Violation history trend analysis workflow

This sequence diagram shows how historical compliance trends are retrieved and analyzed.

```mermaid
sequenceDiagram
    actor User as Claude Desktop
    participant MCP as FastMCP stdio server
    participant Tool as get_violation_history
    participant HS as HistoryService
    participant DB as SQLite History DB

    User->>+MCP: JSON-RPC request<br/>{tool: "get_violation_history",<br/>params: {days_back, group_by}}

    MCP->>+Tool: Invoke get_violation_history(params)

    Tool->>+HS: get_history(days_back, group_by)

    HS->>HS: Calculate start date<br/>(today - days_back)

    HS->>+DB: SELECT * FROM compliance_history<br/>WHERE timestamp >= start_date<br/>ORDER BY timestamp ASC
    DB-->>-HS: Historical snapshots

    alt No history found
        HS-->>Tool: Return empty history
        Note over HS,DB: No data available
    end

    alt group_by = "day"
        HS->>HS: Group by date (YYYY-MM-DD)
    else group_by = "week"
        HS->>HS: Group by ISO week number
    else group_by = "month"
        HS->>HS: Group by year-month
    end

    loop For each time period
        HS->>HS: Aggregate snapshots<br/>(avg compliance_score,<br/>sum violations, sum resources)
        HS->>HS: Identify most common violations
    end

    HS->>HS: Calculate trend direction

    alt Latest score > first score
        HS->>HS: Trend = IMPROVING
    else Latest score < first score
        HS->>HS: Trend = DECLINING
    else Latest score == first score
        HS->>HS: Trend = STABLE
    end

    HS->>HS: Calculate change percentage<br/>((latest - first) / first * 100)

    HS->>HS: Build history response<br/>{snapshots, trend, change_percentage}

    HS-->>-Tool: Return ViolationHistory

    Tool->>Tool: Format as JSON
    Tool-->>-MCP: Return tool result
    MCP-->>-User: JSON-RPC response<br/>{history: [...], trend, change_pct}

    Note over User,DB: Historical analysis<br/>enables tracking progress
```

## 5. Error handling and retry flow

This sequence diagram shows how the system handles AWS API errors and implements retry logic.

```mermaid
sequenceDiagram
    actor User as Claude Desktop
    participant MCP as FastMCP stdio server
    participant Tool as Tool handler
    participant CS as ComplianceService
    participant AWS as AWS Client
    participant API_AWS as AWS API

    User->>+MCP: JSON-RPC request
    MCP->>+Tool: Invoke tool
    Tool->>+CS: Execute service method
    CS->>+AWS: get_resources()

    AWS->>+API_AWS: API call (attempt 1)

    alt Success
        API_AWS-->>-AWS: 200 OK + data
        AWS-->>CS: Return resources
    else Throttling error (429)
        API_AWS-->>AWS: ThrottlingException
        AWS->>AWS: Wait 2s (exponential backoff)
        AWS->>+API_AWS: API call (attempt 2)

        alt Success
            API_AWS-->>-AWS: 200 OK + data
            AWS-->>CS: Return resources
        else Still throttled
            API_AWS-->>AWS: ThrottlingException
            AWS->>AWS: Wait 4s
            AWS->>+API_AWS: API call (attempt 3)

            alt Success
                API_AWS-->>-AWS: 200 OK + data
                AWS-->>CS: Return resources
            else Max retries exceeded
                API_AWS-->>AWS: ThrottlingException
                AWS-->>-CS: Raise AWSThrottlingError
                CS-->>-Tool: Propagate error
                Tool->>Tool: Sanitize error message<br/>(remove credentials, paths)
                Tool-->>-MCP: Return error result
                MCP-->>-User: JSON-RPC error response<br/>{error: "AWS rate limit exceeded"}
            end
        end
    else Authorization error (403)
        API_AWS-->>-AWS: AccessDenied
        AWS-->>-CS: Raise AWSAuthError
        CS-->>-Tool: Propagate error
        Tool->>Tool: Sanitize error message
        Tool-->>-MCP: Return error result
        MCP-->>-User: JSON-RPC error response<br/>{error: "AWS access denied"}
    else Network error
        API_AWS-->>-AWS: Network timeout
        AWS->>AWS: Wait 2s
        AWS->>+API_AWS: API call (attempt 2)

        alt Success
            API_AWS-->>-AWS: 200 OK + data
            AWS-->>CS: Return resources
        else Still failing
            API_AWS-->>-AWS: Network timeout
            AWS-->>-CS: Raise NetworkError
            CS-->>-Tool: Propagate error
            Tool-->>-MCP: Return error result
            MCP-->>-User: JSON-RPC error response<br/>{error: "AWS connection failed"}
        end
    end

    Note over User,API_AWS: Retry strategy:<br/>Exponential backoff<br/>2s, 4s, 8s delays
```

## Key sequence flow insights

### 1. Compliance check flow
- **Duration**: 3-10 seconds (multi-region, cache miss), 100-200ms (cache hit)
- **Bottlenecks**: AWS API calls, Cost Explorer queries, number of regions
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
- **Data source**: SQLite local database
- **Analysis**: Supports day/week/month grouping for trend analysis

### 5. Error handling flow
- **Retry logic**: Exponential backoff (2s, 4s, 8s)
- **Max retries**: 3 attempts
- **Error sanitization**: Removes sensitive data from user-facing errors

## Timing summary

| Workflow | Average duration | Cache impact |
|----------|-----------------|--------------|
| Compliance check (multi-region) | 3-10s | -90% (cached) |
| Compliance check (single region) | 2-5s | -90% (cached) |
| Tag suggestions | 3-7s | N/A |
| Cost attribution | 3-10s | -50% (partial cache) |
| History analysis | 100-500ms | N/A |
| Policy retrieval | 10-50ms | In-memory cache |

## Parallelization opportunities

Several operations can be parallelized:
1. **Multi-region scanning** — Compliance checks run in parallel across regions (default: 5 concurrent)
2. **Resource and cost data retrieval** — Fetched in parallel during cost attribution
3. **Similar resource analysis** — Multiple DescribeInstances calls for tag suggestions
