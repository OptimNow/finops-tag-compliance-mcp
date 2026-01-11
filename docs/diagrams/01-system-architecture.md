# System Architecture Diagram

## Overview
This diagram shows the high-level architecture of the FinOps Tag Compliance MCP Server, including all major components, data stores, and external integrations.

```mermaid
graph TB
    subgraph "Client Layer"
        Client[Claude Desktop / AI Assistant]
    end

    subgraph "API Gateway Layer"
        FastAPI[FastAPI Server<br/>Port 8000]
        CORS[CORS Middleware]
        Sanitize[Sanitization Middleware]
        Correlate[Correlation Middleware]
        Budget[Budget Middleware]
        Loop[Loop Detection Middleware]
        Security[Security Middleware]
    end

    subgraph "MCP Protocol Layer"
        MCPHandler[MCP Handler<br/>Tool Registry & Invocation]
        ToolDef[Tool Definitions<br/>8 Tools]
        ToolVal[Input Validation]
    end

    subgraph "Business Logic Layer - Services"
        ComplianceService[Compliance Service<br/>Resource Scanning & Validation]
        PolicyService[Policy Service<br/>Policy Management]
        AuditService[Audit Service<br/>Event Logging]
        HistoryService[History Service<br/>Trend Analysis]
        CostService[Cost Service<br/>Cost Attribution]
        SuggestionService[Suggestion Service<br/>Tag Recommendations]
        SecurityService[Security Service<br/>Threat Monitoring]
        MetricsService[Metrics Service<br/>Performance Metrics]
    end

    subgraph "Tool Handlers"
        T1[check_tag_compliance]
        T2[find_untagged_resources]
        T3[validate_resource_tags]
        T4[get_cost_attribution_gap]
        T5[suggest_tags]
        T6[get_tagging_policy]
        T7[generate_compliance_report]
        T8[get_violation_history]
    end

    subgraph "Integration Layer - Clients"
        AWSClient[AWS Client<br/>boto3 wrapper]
        RedisCache[Redis Cache Client<br/>Async wrapper]
    end

    subgraph "External Systems"
        AWS[AWS Services]
        EC2[EC2 API]
        RDS[RDS API]
        S3[S3 API]
        Lambda[Lambda API]
        CostExplorer[Cost Explorer API]
        ResourceGroups[Resource Groups<br/>Tagging API]
        Redis[(Redis Cache)]
        AuditDB[(SQLite<br/>Audit Logs)]
        HistoryDB[(SQLite<br/>Compliance History)]
        CloudWatch[CloudWatch Logs]
        Prometheus[Prometheus<br/>Metrics Endpoint]
    end

    subgraph "Configuration"
        PolicyFile[tagging_policy.json]
        EnvConfig[Environment Config]
    end

    %% Client to API
    Client -->|HTTP POST| FastAPI
    FastAPI --> CORS
    CORS --> Sanitize
    Sanitize --> Correlate
    Correlate --> Budget
    Budget --> Loop
    Loop --> Security

    %% API to MCP
    Security --> MCPHandler
    MCPHandler --> ToolVal
    ToolVal --> ToolDef

    %% MCP to Tools
    ToolDef --> T1
    ToolDef --> T2
    ToolDef --> T3
    ToolDef --> T4
    ToolDef --> T5
    ToolDef --> T6
    ToolDef --> T7
    ToolDef --> T8

    %% Tools to Services
    T1 --> ComplianceService
    T2 --> ComplianceService
    T3 --> ComplianceService
    T4 --> CostService
    T5 --> SuggestionService
    T6 --> PolicyService
    T7 --> ComplianceService
    T8 --> HistoryService

    %% Services to Clients
    ComplianceService --> AWSClient
    ComplianceService --> RedisCache
    ComplianceService --> PolicyService
    ComplianceService --> CostService
    CostService --> AWSClient
    SuggestionService --> AWSClient
    AuditService --> AuditDB
    HistoryService --> HistoryDB
    SecurityService --> CloudWatch

    %% Clients to External
    AWSClient --> EC2
    AWSClient --> RDS
    AWSClient --> S3
    AWSClient --> Lambda
    AWSClient --> CostExplorer
    AWSClient --> ResourceGroups
    EC2 --> AWS
    RDS --> AWS
    S3 --> AWS
    Lambda --> AWS
    CostExplorer --> AWS
    ResourceGroups --> AWS
    RedisCache --> Redis

    %% Configuration
    PolicyService --> PolicyFile
    FastAPI --> EnvConfig

    %% Observability
    MetricsService --> Prometheus
    AuditService --> CloudWatch
    SecurityService --> Redis

    %% Styling
    classDef clientStyle fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef apiStyle fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef serviceStyle fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef toolStyle fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef dataStyle fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef awsStyle fill:#fff9c4,stroke:#f57f17,stroke-width:2px

    class Client clientStyle
    class FastAPI,CORS,Sanitize,Correlate,Budget,Loop,Security,MCPHandler,ToolDef,ToolVal apiStyle
    class ComplianceService,PolicyService,AuditService,HistoryService,CostService,SuggestionService,SecurityService,MetricsService serviceStyle
    class T1,T2,T3,T4,T5,T6,T7,T8 toolStyle
    class AuditDB,HistoryDB,Redis,PolicyFile dataStyle
    class AWS,EC2,RDS,S3,Lambda,CostExplorer,ResourceGroups,CloudWatch awsStyle
```

## Key Components

### 1. Client Layer
- **Claude Desktop**: AI assistant that invokes MCP tools via HTTP

### 2. API Gateway Layer
- **FastAPI Server**: HTTP server exposing MCP protocol endpoints
- **Middleware Stack**: CORS, sanitization, correlation, budget, loop detection, security

### 3. MCP Protocol Layer
- **MCP Handler**: Manages tool registry and invocation
- **Tool Definitions**: Defines 8 available tools with schemas
- **Input Validation**: Validates all tool inputs

### 4. Business Logic Layer
8 core services handling different aspects:
- Compliance checking and validation
- Policy management
- Audit logging
- Historical trend analysis
- Cost attribution calculation
- Tag suggestion generation
- Security monitoring
- Metrics aggregation

### 5. Tool Handlers
8 MCP tools that map to service functions

### 6. Integration Layer
- **AWS Client**: Wrapper around boto3 with rate limiting
- **Redis Cache Client**: Async cache interface

### 7. External Systems
- **AWS Services**: EC2, RDS, S3, Lambda, Cost Explorer, Resource Groups
- **Data Stores**: Redis (cache), SQLite (audit & history)
- **Observability**: CloudWatch Logs, Prometheus metrics

### 8. Configuration
- **tagging_policy.json**: Defines required and optional tags
- **Environment Config**: Runtime configuration from env vars

## Data Flow Patterns

1. **Synchronous Flow**: Client → FastAPI → MCP Handler → Tool → Service → AWS → Response
2. **Caching Flow**: Service checks Redis before calling AWS
3. **Audit Flow**: All tool invocations logged to SQLite
4. **Security Flow**: Security events logged to CloudWatch and tracked in Redis
5. **Metrics Flow**: Performance metrics aggregated and exposed via Prometheus endpoint
