# Component Diagram

## 1. High-Level Component Architecture

This diagram shows the major logical components and their dependencies.

```mermaid
graph TB
    subgraph "Presentation Layer"
        HTTP[HTTP API<br/>FastAPI Endpoints]
        MCP[MCP Protocol Handler<br/>Tool Registry]
    end

    subgraph "Application Layer - Tools"
        T1[Check Compliance Tool]
        T2[Find Untagged Tool]
        T3[Validate Tags Tool]
        T4[Cost Gap Tool]
        T5[Suggest Tags Tool]
        T6[Get Policy Tool]
        T7[Generate Report Tool]
        T8[History Tool]
    end

    subgraph "Business Logic Layer - Services"
        CS[Compliance Service<br/>• Scan resources<br/>• Validate tags<br/>• Calculate scores]
        PS[Policy Service<br/>• Load policy<br/>• Validate structure<br/>• Check applicability]
        CostS[Cost Service<br/>• Query Cost Explorer<br/>• Calculate gaps<br/>• Group by dimensions]
        SS[Suggestion Service<br/>• Analyze patterns<br/>• Find similar resources<br/>• Generate suggestions]
        HS[History Service<br/>• Store snapshots<br/>• Query trends<br/>• Calculate changes]
        AS[Audit Service<br/>• Log invocations<br/>• Track metrics<br/>• Store events]
        SecS[Security Service<br/>• Monitor threats<br/>• Track violations<br/>• Rate limit]
        MS[Metrics Service<br/>• Aggregate stats<br/>• Generate metrics<br/>• Export Prometheus]
    end

    subgraph "Integration Layer - Clients"
        AWSC[AWS Client<br/>• Resource Groups API<br/>• Cost Explorer API<br/>• EC2/RDS/S3/Lambda APIs<br/>• Rate limiting<br/>• Retry logic]
        CacheC[Cache Client<br/>• Redis operations<br/>• TTL management<br/>• Graceful degradation]
    end

    subgraph "Data Layer"
        Redis[(Redis<br/>• Compliance cache<br/>• Budget tracking<br/>• Loop detection<br/>• Security events)]
        AuditDB[(SQLite - Audit<br/>• Tool invocations<br/>• Parameters<br/>• Results<br/>• Errors)]
        HistoryDB[(SQLite - History<br/>• Compliance snapshots<br/>• Timestamps<br/>• Scores<br/>• Violations)]
        PolicyFile[Policy Config<br/>tagging_policy.json]
    end

    subgraph "External Systems"
        AWS[AWS Services<br/>• EC2<br/>• RDS<br/>• S3<br/>• Lambda<br/>• ECS<br/>• OpenSearch]
        CE[Cost Explorer]
        RGTA[Resource Groups<br/>Tagging API]
        CW[CloudWatch Logs]
    end

    subgraph "Cross-Cutting Concerns"
        Middleware[Middleware Stack<br/>• CORS<br/>• Sanitization<br/>• Correlation<br/>• Budget enforcement<br/>• Loop detection<br/>• Security checks]
        Utils[Utilities<br/>• Input validation<br/>• Error sanitization<br/>• Logging<br/>• Correlation IDs]
        Config[Configuration<br/>• Environment vars<br/>• Settings<br/>• Defaults]
    end

    %% HTTP to MCP
    HTTP --> Middleware
    Middleware --> MCP

    %% MCP to Tools
    MCP --> T1
    MCP --> T2
    MCP --> T3
    MCP --> T4
    MCP --> T5
    MCP --> T6
    MCP --> T7
    MCP --> T8

    %% Tools to Services
    T1 --> CS
    T2 --> CS
    T3 --> CS
    T4 --> CostS
    T5 --> SS
    T6 --> PS
    T7 --> CS
    T8 --> HS

    %% Service Dependencies
    CS --> PS
    CS --> CostS
    CS --> AWSC
    CS --> CacheC
    CostS --> AWSC
    SS --> AWSC
    SS --> PS
    HS --> HistoryDB
    AS --> AuditDB
    AS --> CW
    SecS --> Redis
    SecS --> CW
    MS --> AS

    %% Client to External
    AWSC --> AWS
    AWSC --> CE
    AWSC --> RGTA
    CacheC --> Redis

    %% Services to Audit
    CS -.->|Log| AS
    CostS -.->|Log| AS
    SS -.->|Log| AS
    HS -.->|Log| AS

    %% Config Dependencies
    PS --> PolicyFile
    HTTP --> Config
    AWSC --> Config
    CacheC --> Config

    %% Utils Dependencies
    MCP --> Utils
    Middleware --> Utils
    CS --> Utils

    %% Security Dependencies
    Middleware --> SecS

    %% Styling
    classDef presentation fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef tools fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef services fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef clients fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef data fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef external fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    classDef crosscut fill:#e0f2f1,stroke:#004d40,stroke-width:2px

    class HTTP,MCP presentation
    class T1,T2,T3,T4,T5,T6,T7,T8 tools
    class CS,PS,CostS,SS,HS,AS,SecS,MS services
    class AWSC,CacheC clients
    class Redis,AuditDB,HistoryDB,PolicyFile data
    class AWS,CE,RGTA,CW external
    class Middleware,Utils,Config crosscut
```

## 2. Component Dependency Matrix

This table shows which components depend on each other.

| Component | Depends On | Used By |
|-----------|-----------|---------|
| **HTTP API** | Middleware, Config | External Clients |
| **MCP Handler** | Utils, Middleware | HTTP API |
| **Tools (8)** | Services, MCP Handler | MCP Handler |
| **Compliance Service** | Policy Service, Cost Service, AWS Client, Cache Client, Utils | Tools 1, 2, 3, 7 |
| **Policy Service** | Policy File, Config | Compliance Service, Suggestion Service, Tools |
| **Cost Service** | AWS Client, Utils | Compliance Service, Tool 4 |
| **Suggestion Service** | AWS Client, Policy Service | Tool 5 |
| **History Service** | History DB | Tool 8, Compliance Service |
| **Audit Service** | Audit DB, CloudWatch | All Services (logging) |
| **Security Service** | Redis, CloudWatch | Middleware |
| **Metrics Service** | Audit Service | Monitoring Systems |
| **AWS Client** | AWS Services, Config | All Services that need AWS data |
| **Cache Client** | Redis, Config | Compliance Service, Security Service |
| **Middleware Stack** | Utils, Security Service, Config | HTTP API |
| **Utilities** | - | All Components |
| **Configuration** | Environment Variables | All Components |

## 3. Component Interfaces

### Presentation Layer Components

```mermaid
classDiagram
    class FastAPIServer {
        +GET /health
        +GET /metrics
        +GET /mcp/tools
        +POST /mcp/tools/call
        -lifespan_handler()
        -setup_middleware()
    }

    class MCPHandler {
        +list_tools() ToolDefinition[]
        +invoke_tool(name, params) MCPToolResult
        -validate_input(tool, params)
        -lookup_tool(name) ToolHandler
    }

    FastAPIServer --> MCPHandler
```

### Service Layer Components

```mermaid
classDiagram
    class ComplianceService {
        +check_compliance(params) ComplianceResult
        -generate_cache_key(params) string
        -validate_resource_tags(resource, policy) Violation[]
        -calculate_compliance_score(results) float
    }

    class PolicyService {
        +get_policy() TagPolicy
        +load_policy(path) TagPolicy
        -validate_policy_structure(policy)
        +is_tag_applicable(tag, resource_type) bool
    }

    class CostService {
        +calculate_attribution_gap(params) CostAttributionGap
        +get_resource_costs(resources, period) CostData
        -group_costs_by_dimension(costs, dimension) dict
    }

    class SuggestionService {
        +suggest_tags_for_resource(arn) TagSuggestion[]
        -analyze_naming_pattern(name) dict
        -find_similar_resources(resource) Resource[]
        -calculate_confidence(suggestion) float
    }

    class HistoryService {
        +store_snapshot(result) bool
        +get_history(days_back, group_by) ViolationHistory
        -calculate_trend(snapshots) TrendDirection
        -group_by_period(snapshots, period) dict
    }

    class AuditService {
        +log_invocation(tool, params, result)
        +get_metrics() Metrics
        -store_audit_log(log_entry)
    }

    class SecurityService {
        +check_security_threat(request) bool
        +log_security_event(event)
        +is_rate_limited(session) bool
    }

    class MetricsService {
        +generate_prometheus_metrics() string
        +get_tool_metrics() dict
        +get_error_rates() dict
    }

    ComplianceService --> PolicyService
    ComplianceService --> CostService
    SuggestionService --> PolicyService
```

### Integration Layer Components

```mermaid
classDiagram
    class AWSClient {
        +get_resources(resource_types, filters) Resource[]
        +get_cost_data(time_period) CostData
        +describe_resource(arn) ResourceDetails
        -exponential_backoff_retry(func, max_retries)
        -initialize_clients()
    }

    class CacheClient {
        +get(key) any
        +set(key, value, ttl) bool
        +delete(key) bool
        -handle_connection_error()
        -reconnect() bool
    }

    class AWSClient {
        -ec2_client
        -rds_client
        -s3_client
        -lambda_client
        -cost_explorer_client
        -resource_groups_client
    }
```

## 4. Component Communication Patterns

```mermaid
graph LR
    subgraph "Synchronous Communication"
        A[Tool] -->|Direct Call| B[Service]
        B -->|Return Value| A
    end

    subgraph "Asynchronous Communication"
        C[Service] -->|Log Event| D[Audit Service]
        E[Service] -->|Log Security Event| F[CloudWatch]
    end

    subgraph "Cached Communication"
        G[Service] -->|Check Cache| H[Redis]
        H -->|Cache Miss| G
        G -->|Query| I[AWS]
        I -->|Data| G
        G -->|Store| H
    end

    subgraph "Error Handling"
        J[Service] -->|API Call| K[AWS Client]
        K -->|Error| L[Retry Logic]
        L -->|Max Retries| M[Error Response]
        L -->|Success| K
    end
```

## 5. Component Deployment Units

Components are grouped into deployment units:

```mermaid
graph TB
    subgraph "Single Container"
        subgraph "Web Server Process"
            FastAPI[FastAPI Application]
            Uvicorn[Uvicorn ASGI Server]
        end

        subgraph "Application Code"
            MCP[MCP Handler]
            Tools[Tool Handlers]
            Services[Service Layer]
            Clients[Client Layer]
            Utils[Utilities]
        end

        subgraph "In-Process Storage"
            PolicyCache[Policy Cache<br/>In-Memory]
            ConfigCache[Config Cache<br/>In-Memory]
        end
    end

    subgraph "External Dependencies"
        Redis[(Redis Container)]
        SQLite[(SQLite Files<br/>Volume Mount)]
        AWS[AWS Services<br/>External]
    end

    Uvicorn --> FastAPI
    FastAPI --> MCP
    MCP --> Tools
    Tools --> Services
    Services --> Clients
    Services --> Utils

    Services --> PolicyCache
    FastAPI --> ConfigCache

    Clients --> Redis
    Services --> SQLite
    Clients --> AWS
```

## Component Characteristics

### Stateless Components
These components maintain no state between requests:
- FastAPI Server
- MCP Handler
- Tool Handlers
- Utility functions

### Stateful Components
These components maintain state or cached data:
- Policy Service (in-memory cache)
- Configuration (loaded once at startup)
- Redis Cache Client (connection pool)
- AWS Client (client initialization, connection pools)

### Persistence Components
These components interact with persistent storage:
- Audit Service → SQLite Audit DB
- History Service → SQLite History DB
- Cache Client → Redis
- Policy Service → tagging_policy.json file

### External Integration Components
These components communicate with external systems:
- AWS Client → AWS APIs
- CloudWatch Logger → CloudWatch Logs
- Metrics Service → Prometheus scraper

## Component Scalability Considerations

| Component | Scalability | Notes |
|-----------|-------------|-------|
| HTTP API | Horizontal | Stateless, load balancer ready |
| MCP Handler | Horizontal | No shared state |
| Tool Handlers | Horizontal | Independent execution |
| Services | Horizontal | Most are stateless |
| AWS Client | Vertical | Rate limited by AWS quotas |
| Redis Cache | Horizontal | Can use Redis Cluster |
| SQLite DBs | Vertical | Consider migration to managed DB for scale |
| Policy Service | Horizontal | In-memory cache, file system read |

## Component Testing Strategy

```mermaid
graph TB
    subgraph "Unit Tests"
        UT1[Service Tests<br/>Mock dependencies]
        UT2[Client Tests<br/>Mock external APIs]
        UT3[Utility Tests<br/>Pure functions]
    end

    subgraph "Integration Tests"
        IT1[Tool Tests<br/>Real services]
        IT2[API Tests<br/>Real HTTP calls]
        IT3[AWS Tests<br/>LocalStack]
    end

    subgraph "E2E Tests"
        E2E1[Full Workflow Tests<br/>Real components]
        E2E2[Error Scenario Tests<br/>Fault injection]
    end

    UT1 --> IT1
    UT2 --> IT1
    UT3 --> IT1
    IT1 --> E2E1
    IT2 --> E2E1
    IT3 --> E2E2
```

## Component Responsibilities Summary

### Clear Separation of Concerns

1. **Presentation Layer**: HTTP protocol, MCP protocol, request/response formatting
2. **Application Layer**: Tool definitions, input validation, tool orchestration
3. **Business Logic Layer**: Domain logic, compliance checking, cost analysis
4. **Integration Layer**: External system communication, rate limiting, retries
5. **Data Layer**: Persistence, caching, configuration
6. **Cross-Cutting**: Logging, monitoring, security, error handling

This architecture follows **Clean Architecture** principles with clear dependency rules:
- Dependencies point inward (presentation → application → business logic → data)
- Inner layers have no knowledge of outer layers
- Business logic is independent of frameworks and external systems
