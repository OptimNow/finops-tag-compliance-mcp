# State machine diagrams

## 1. Tool invocation lifecycle state machine

This diagram shows the complete lifecycle of an MCP tool invocation, from request to response, including all validation, security, and error handling states.

```mermaid
stateDiagram-v2
    [*] --> RequestReceived: HTTP POST /mcp/tools/call

    RequestReceived --> InputSanitization: Parse JSON
    RequestReceived --> RequestError: Invalid JSON

    InputSanitization --> SecurityValidation: Sanitized
    InputSanitization --> RequestError: Malicious Input Detected

    SecurityValidation --> CorrelationTracking: Security OK
    SecurityValidation --> SecurityBlocked: Security Threat Detected

    CorrelationTracking --> BudgetCheck: Correlation ID Assigned

    BudgetCheck --> LoopDetection: Budget Available
    BudgetCheck --> BudgetExhausted: Budget Exceeded

    LoopDetection --> ToolLookup: No Loop Detected
    LoopDetection --> LoopDetected: Loop Detected

    ToolLookup --> SchemaValidation: Tool Found
    ToolLookup --> UnknownTool: Tool Not Found

    SchemaValidation --> ToolExecution: Schema Valid
    SchemaValidation --> ValidationError: Schema Invalid

    ToolExecution --> ServiceCall: Tool Handler Invoked

    ServiceCall --> CacheCheck: Check Cache
    ServiceCall --> DirectExecution: No Cache

    CacheCheck --> CacheHit: Data in Cache
    CacheCheck --> CacheMiss: No Cache Entry

    CacheHit --> ResultFormatting: Use Cached Data
    CacheMiss --> AWSAPICall: Query AWS

    DirectExecution --> AWSAPICall

    AWSAPICall --> PolicyValidation: AWS Data Retrieved
    AWSAPICall --> AWSError: AWS API Error

    PolicyValidation --> ResultCalculation: Policy Applied

    ResultCalculation --> CacheStorage: Results Computed

    CacheStorage --> HistoryStorage: Cache Updated
    CacheStorage --> ResultFormatting: Cache Failed (Degrade)

    HistoryStorage --> ResultFormatting: History Stored
    HistoryStorage --> ResultFormatting: History Failed (Warn)

    ResultFormatting --> AuditLogging: Format Response

    AuditLogging --> ResponseSuccess: Audit Logged

    ResponseSuccess --> [*]: HTTP 200 OK

    %% Error States
    RequestError --> ErrorResponse: Bad Request
    SecurityBlocked --> SecurityAudit: Log Security Event
    SecurityAudit --> ErrorResponse
    BudgetExhausted --> ErrorResponse: HTTP 429
    LoopDetected --> ErrorResponse: HTTP 429
    UnknownTool --> SecurityService: Log Unknown Tool Attempt
    SecurityService --> ErrorResponse: HTTP 400
    ValidationError --> ErrorResponse: HTTP 400
    AWSError --> ErrorRetry: Retriable Error
    ErrorRetry --> AWSAPICall: Retry with Backoff
    ErrorRetry --> ErrorResponse: Max Retries Exceeded
    AWSError --> ErrorResponse: Non-retriable Error

    ErrorResponse --> ErrorAuditLogging: Log Error
    ErrorAuditLogging --> [*]: HTTP 4xx/5xx

    %% State Notes
    note right of RequestReceived
        Entry point for all
        tool invocations
    end note

    note right of SecurityValidation
        Checks for:
        - SQL injection
        - Command injection
        - Path traversal
    end note

    note right of BudgetCheck
        Default: 100 calls/hour
        per session
    end note

    note right of LoopDetection
        Prevents infinite loops
        3 identical calls in 5 min
    end note

    note right of CacheCheck
        Redis cache with 1hr TTL
        Reduces AWS API calls
    end note

    note right of AuditLogging
        All invocations logged
        to SQLite for compliance
    end note
```

## 2. Resource compliance status state machine

This diagram shows the different states a resource can be in from a compliance perspective.

```mermaid
stateDiagram-v2
    [*] --> Discovered: Resource Found in AWS

    Discovered --> Scanning: Compliance Check Initiated

    Scanning --> TagsRetrieved: Get Resource Tags

    TagsRetrieved --> PolicyEvaluation: Tags Retrieved

    PolicyEvaluation --> FullyCompliant: All Required Tags Present<br/>All Values Valid
    PolicyEvaluation --> PartiallyCompliant: Some Required Tags Present<br/>Some Missing or Invalid
    PolicyEvaluation --> NonCompliant: Required Tags Missing<br/>or Invalid Values
    PolicyEvaluation --> Untagged: No Tags Present

    FullyCompliant --> ReportIncluded: Add to Compliance Report
    PartiallyCompliant --> ViolationLogged: Log Violations
    NonCompliant --> ViolationLogged
    Untagged --> ViolationLogged

    ViolationLogged --> CostImpactCalculated: Calculate Cost Attribution Gap

    CostImpactCalculated --> RemediationSuggested: Generate Tag Suggestions

    RemediationSuggested --> AwaitingRemediation: Waiting for Tag Updates

    AwaitingRemediation --> TagsUpdated: Tags Applied to Resource
    AwaitingRemediation --> Ignored: Marked as Exception

    TagsUpdated --> Scanning: Re-scan for Compliance

    ReportIncluded --> HistoryStored: Store Snapshot
    HistoryStored --> [*]: Compliance Check Complete

    Ignored --> ReportIncluded: Exclude from Violations

    %% Error States
    Scanning --> ScanError: AWS API Error
    TagsRetrieved --> RetrievalError: Failed to Get Tags

    ScanError --> ErrorLogged: Log Error
    RetrievalError --> ErrorLogged
    ErrorLogged --> [*]: Skip Resource

    %% State Notes
    note right of Discovered
        Resources discovered via
        Resource Groups Tagging API
    end note

    note right of PolicyEvaluation
        Checks against
        tagging_policy.json
    end note

    note right of FullyCompliant
        Compliance Score: 100%
        No violations
    end note

    note right of PartiallyCompliant
        Compliance Score: 50-99%
        Some violations
    end note

    note right of NonCompliant
        Compliance Score: 1-49%
        Multiple violations
    end note

    note right of Untagged
        Compliance Score: 0%
        Critical violation
    end note

    note right of CostImpactCalculated
        Uses Cost Explorer API
        to estimate impact
    end note
```

## 3. Cache state machine

This diagram shows the lifecycle of cached data in the Redis cache.

```mermaid
stateDiagram-v2
    [*] --> CacheQuery: Service Requests Data

    CacheQuery --> KeyGeneration: Generate Cache Key

    KeyGeneration --> CacheLookup: SHA256(params)

    CacheLookup --> CacheHit: Key Found
    CacheLookup --> CacheMiss: Key Not Found
    CacheLookup --> CacheError: Redis Unavailable

    CacheHit --> TTLCheck: Check Expiration

    TTLCheck --> ValidData: Within TTL
    TTLCheck --> ExpiredData: Expired

    ValidData --> DataReturned: Return Cached Data
    DataReturned --> [*]: Cache Hit Success

    ExpiredData --> CacheInvalidation: Remove from Cache
    CacheInvalidation --> DataFetch: Fetch Fresh Data

    CacheMiss --> DataFetch
    CacheError --> DataFetch: Degrade Gracefully

    DataFetch --> AWSQuery: Query AWS APIs

    AWSQuery --> DataProcessing: Data Retrieved
    AWSQuery --> FetchError: AWS Error

    DataProcessing --> CacheWrite: Process Results

    CacheWrite --> CacheStored: Data Cached with TTL
    CacheWrite --> WriteError: Cache Write Failed

    CacheStored --> DataReturned: Return Fresh Data
    WriteError --> DataReturned: Return Data (No Cache)

    FetchError --> [*]: Return Error

    %% Force Refresh Path
    CacheQuery --> ForceRefresh: force_refresh=true
    ForceRefresh --> DataFetch: Bypass Cache

    %% State Notes
    note right of KeyGeneration
        Cache key includes:
        - Resource types
        - Filters
        - Severity level
    end note

    note right of TTLCheck
        Default TTL: 1 hour
        Configurable via
        REDIS_TTL env var
    end note

    note right of CacheError
        Graceful degradation
        System continues without cache
    end note

    note right of ForceRefresh
        Allows users to bypass
        cache for fresh data
    end note
```

## 4. Budget tracking state machine

This diagram shows how the session budget is tracked and enforced.

```mermaid
stateDiagram-v2
    [*] --> SessionStart: New Session Initiated

    SessionStart --> BudgetInitialization: Create Session Budget

    BudgetInitialization --> BudgetActive: Set Counter = 0<br/>Max = 100<br/>TTL = 1 hour

    BudgetActive --> ToolInvocation: Tool Called

    ToolInvocation --> BudgetCheck: Check Current Count

    BudgetCheck --> WithinBudget: Count < Max
    BudgetCheck --> BudgetWarning: Count = Max * 0.8
    BudgetCheck --> BudgetExceeded: Count >= Max

    WithinBudget --> CounterIncrement: Proceed with Tool
    BudgetWarning --> CounterIncrement: Proceed with Warning

    CounterIncrement --> ToolExecution: Increment Counter

    ToolExecution --> BudgetUpdate: Update Redis

    BudgetUpdate --> BudgetActive: Tool Complete

    BudgetExceeded --> RateLimited: Return 429 Error

    RateLimited --> AwaitingReset: Cooldown Period

    AwaitingReset --> BudgetReset: TTL Expired

    BudgetReset --> BudgetActive: Reset Counter to 0

    %% Session End
    BudgetActive --> SessionEnd: Session Expires
    SessionEnd --> BudgetCleanup: Remove from Redis
    BudgetCleanup --> [*]: Session Closed

    %% Redis Failure Path
    BudgetCheck --> RedisError: Redis Unavailable
    BudgetUpdate --> RedisError: Write Failed

    RedisError --> FallbackMode: Use In-Memory Tracking
    FallbackMode --> BudgetActive: Degraded Mode

    %% State Notes
    note right of BudgetInitialization
        Session ID used as Redis key
        Defaults: 100 calls/hour
    end note

    note right of BudgetWarning
        Warning at 80% threshold
        Logged but not blocked
    end note

    note right of BudgetExceeded
        HTTP 429 Too Many Requests
        Includes Retry-After header
    end note

    note right of FallbackMode
        Graceful degradation
        Budget tracking continues
        without distributed state
    end note
```

## State transition summary

### Tool invocation states
1. **Request States**: RequestReceived, InputSanitization, SecurityValidation
2. **Validation States**: BudgetCheck, LoopDetection, SchemaValidation
3. **Execution States**: ToolExecution, ServiceCall, AWSAPICall
4. **Caching States**: CacheCheck, CacheHit, CacheMiss, CacheStorage
5. **Finalization States**: ResultFormatting, AuditLogging, ResponseSuccess
6. **Error States**: RequestError, SecurityBlocked, ValidationError, AWSError

### Compliance states
1. **Discovery**: Discovered, Scanning
2. **Evaluation**: PolicyEvaluation
3. **Compliance Levels**: FullyCompliant, PartiallyCompliant, NonCompliant, Untagged
4. **Remediation**: ViolationLogged, RemediationSuggested, AwaitingRemediation

### Cache states
1. **Lookup**: CacheQuery, KeyGeneration, CacheLookup
2. **Hit/Miss**: CacheHit, CacheMiss, TTLCheck
3. **Data Operations**: DataFetch, DataProcessing, CacheWrite
4. **Degradation**: CacheError, WriteError

### Budget states
1. **Active**: BudgetActive, WithinBudget
2. **Warning**: BudgetWarning
3. **Exceeded**: BudgetExceeded, RateLimited
4. **Recovery**: AwaitingReset, BudgetReset

## State machine properties

### Deterministic transitions
All state machines are deterministic - given the same input and current state, they always transition to the same next state.

### Error recovery
Each state machine includes error states with recovery paths, ensuring system resilience.

### Observability
All state transitions are logged to enable debugging and monitoring.

### Idempotency
Many operations (like compliance checks) are idempotent - repeated calls with same parameters produce same results.
