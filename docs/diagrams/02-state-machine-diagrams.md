# State machine diagrams

## 1. Tool invocation lifecycle state machine

This diagram shows the complete lifecycle of an MCP tool invocation via stdio, from request to response, including validation and error handling states.

```mermaid
stateDiagram-v2
    [*] --> RequestReceived: stdio JSON-RPC message

    RequestReceived --> InputValidation: Parse JSON-RPC
    RequestReceived --> RequestError: Invalid JSON

    InputValidation --> BudgetCheck: Input validated
    InputValidation --> ValidationError: Malicious input detected

    BudgetCheck --> LoopDetection: Budget available
    BudgetCheck --> BudgetExhausted: Budget exceeded

    LoopDetection --> ToolLookup: No loop detected
    LoopDetection --> LoopDetected: Loop detected

    ToolLookup --> SchemaValidation: Tool found
    ToolLookup --> UnknownTool: Tool not found

    SchemaValidation --> ToolExecution: Schema valid
    SchemaValidation --> ValidationError: Schema invalid

    ToolExecution --> ServiceCall: Tool handler invoked

    ServiceCall --> CacheCheck: Check cache
    ServiceCall --> DirectExecution: No cache available

    CacheCheck --> CacheHit: Data in cache
    CacheCheck --> CacheMiss: No cache entry

    CacheHit --> ResultFormatting: Use cached data
    CacheMiss --> AWSAPICall: Query AWS

    DirectExecution --> AWSAPICall

    AWSAPICall --> PolicyValidation: AWS data retrieved
    AWSAPICall --> AWSError: AWS API error

    PolicyValidation --> ResultCalculation: Policy applied

    ResultCalculation --> CacheStorage: Results computed

    CacheStorage --> HistoryStorage: Cache updated
    CacheStorage --> ResultFormatting: Cache unavailable (degrade)

    HistoryStorage --> ResultFormatting: History stored
    HistoryStorage --> ResultFormatting: History failed (warn)

    ResultFormatting --> AuditLogging: Format response

    AuditLogging --> ResponseSuccess: Audit logged

    ResponseSuccess --> [*]: JSON-RPC response

    %% Error States
    RequestError --> ErrorResponse: Bad request
    BudgetExhausted --> ErrorResponse: Budget exceeded
    LoopDetected --> ErrorResponse: Loop detected
    UnknownTool --> ErrorResponse: Unknown tool
    ValidationError --> ErrorResponse: Validation failed
    AWSError --> ErrorRetry: Retriable error
    ErrorRetry --> AWSAPICall: Retry with backoff
    ErrorRetry --> ErrorResponse: Max retries exceeded
    AWSError --> ErrorResponse: Non-retriable error

    ErrorResponse --> ErrorAuditLogging: Log error
    ErrorAuditLogging --> [*]: JSON-RPC error response

    %% State Notes
    note right of RequestReceived
        Entry point for all
        tool invocations via stdio
    end note

    note right of InputValidation
        Checks for:
        - SQL injection
        - Command injection
        - Path traversal
    end note

    note right of BudgetCheck
        Default: 100 calls/session
    end note

    note right of LoopDetection
        Prevents infinite loops
        3 identical calls in 5 min
    end note

    note right of CacheCheck
        Redis cache with 1hr TTL
        Optional — degrades gracefully
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
    [*] --> Discovered: Resource found in AWS

    Discovered --> Scanning: Compliance check initiated

    Scanning --> TagsRetrieved: Get resource tags

    TagsRetrieved --> PolicyEvaluation: Tags retrieved

    PolicyEvaluation --> FullyCompliant: All required tags present<br/>All values valid
    PolicyEvaluation --> PartiallyCompliant: Some required tags present<br/>Some missing or invalid
    PolicyEvaluation --> NonCompliant: Required tags missing<br/>or invalid values
    PolicyEvaluation --> Untagged: No tags present

    FullyCompliant --> ReportIncluded: Add to compliance report
    PartiallyCompliant --> ViolationLogged: Log violations
    NonCompliant --> ViolationLogged
    Untagged --> ViolationLogged

    ViolationLogged --> CostImpactCalculated: Calculate cost attribution gap

    CostImpactCalculated --> RemediationSuggested: Generate tag suggestions

    RemediationSuggested --> AwaitingRemediation: Waiting for tag updates

    AwaitingRemediation --> TagsUpdated: Tags applied to resource
    AwaitingRemediation --> Ignored: Marked as exception

    TagsUpdated --> Scanning: Re-scan for compliance

    ReportIncluded --> HistoryStored: Store snapshot
    HistoryStored --> [*]: Compliance check complete

    Ignored --> ReportIncluded: Exclude from violations

    %% Error States
    Scanning --> ScanError: AWS API error
    TagsRetrieved --> RetrievalError: Failed to get tags

    ScanError --> ErrorLogged: Log error
    RetrievalError --> ErrorLogged
    ErrorLogged --> [*]: Skip resource

    %% State Notes
    note right of Discovered
        Resources discovered via
        Resource Groups Tagging API
        or direct service APIs
    end note

    note right of PolicyEvaluation
        Checks against
        tagging_policy.json
    end note

    note right of FullyCompliant
        Compliance score: 100%
        No violations
    end note

    note right of PartiallyCompliant
        Compliance score: 50-99%
        Some violations
    end note

    note right of NonCompliant
        Compliance score: 1-49%
        Multiple violations
    end note

    note right of Untagged
        Compliance score: 0%
        Critical violation
    end note

    note right of CostImpactCalculated
        Uses Cost Explorer API
        to estimate impact
    end note
```

## 3. Cache state machine

This diagram shows the lifecycle of cached data in the Redis cache (optional).

```mermaid
stateDiagram-v2
    [*] --> CacheQuery: Service requests data

    CacheQuery --> KeyGeneration: Generate cache key

    KeyGeneration --> CacheLookup: SHA256(params)

    CacheLookup --> CacheHit: Key found
    CacheLookup --> CacheMiss: Key not found
    CacheLookup --> CacheUnavailable: Redis not configured

    CacheHit --> TTLCheck: Check expiration

    TTLCheck --> ValidData: Within TTL
    TTLCheck --> ExpiredData: Expired

    ValidData --> DataReturned: Return cached data
    DataReturned --> [*]: Cache hit success

    ExpiredData --> CacheInvalidation: Remove from cache
    CacheInvalidation --> DataFetch: Fetch fresh data

    CacheMiss --> DataFetch
    CacheUnavailable --> DataFetch: Proceed without cache

    DataFetch --> AWSQuery: Query AWS APIs

    AWSQuery --> DataProcessing: Data retrieved
    AWSQuery --> FetchError: AWS error

    DataProcessing --> CacheWrite: Process results

    CacheWrite --> CacheStored: Data cached with TTL
    CacheWrite --> WriteError: Cache write failed

    CacheStored --> DataReturned: Return fresh data
    WriteError --> DataReturned: Return data (no cache)

    FetchError --> [*]: Return error

    %% Force Refresh Path
    CacheQuery --> ForceRefresh: force_refresh=true
    ForceRefresh --> DataFetch: Bypass cache

    %% State Notes
    note right of KeyGeneration
        Cache key includes:
        - Resource types
        - Filters
        - Severity level
        - Scanned regions
    end note

    note right of TTLCheck
        Default TTL: 1 hour
        Configurable via settings
    end note

    note right of CacheUnavailable
        Graceful degradation:
        System works without Redis
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
    [*] --> SessionStart: First tool call in session

    SessionStart --> BudgetInitialization: Create session budget

    BudgetInitialization --> BudgetActive: Set counter = 0<br/>Max = 100<br/>TTL = 1 hour

    BudgetActive --> ToolInvocation: Tool called

    ToolInvocation --> BudgetCheck: Check current count

    BudgetCheck --> WithinBudget: Count less than max
    BudgetCheck --> BudgetWarning: Count at 80% threshold
    BudgetCheck --> BudgetExceeded: Count at max

    WithinBudget --> CounterIncrement: Proceed with tool
    BudgetWarning --> CounterIncrement: Proceed with warning

    CounterIncrement --> ToolExecution: Increment counter

    ToolExecution --> BudgetUpdate: Update counter

    BudgetUpdate --> BudgetActive: Tool complete

    BudgetExceeded --> RateLimited: Return error

    RateLimited --> AwaitingReset: Cooldown period

    AwaitingReset --> BudgetReset: TTL expired

    BudgetReset --> BudgetActive: Reset counter to 0

    %% Session End
    BudgetActive --> SessionEnd: Session expires
    SessionEnd --> BudgetCleanup: Clean up state
    BudgetCleanup --> [*]: Session closed

    %% Redis Failure Path
    BudgetCheck --> StorageError: Redis unavailable
    BudgetUpdate --> StorageError: Write failed

    StorageError --> FallbackMode: Use in-memory tracking
    FallbackMode --> BudgetActive: Degraded mode

    %% State Notes
    note right of BudgetInitialization
        Uses Redis if available,
        falls back to in-memory
        Defaults: 100 calls/hour
    end note

    note right of BudgetWarning
        Warning at 80% threshold
        Logged but not blocked
    end note

    note right of BudgetExceeded
        Returns JSON-RPC error
        to the AI assistant
    end note

    note right of FallbackMode
        Graceful degradation:
        Budget tracking continues
        without distributed state
    end note
```

## State transition summary

### Tool invocation states
1. **Request states**: RequestReceived, InputValidation
2. **Guardrail states**: BudgetCheck, LoopDetection, SchemaValidation
3. **Execution states**: ToolExecution, ServiceCall, AWSAPICall
4. **Caching states**: CacheCheck, CacheHit, CacheMiss, CacheStorage
5. **Finalization states**: ResultFormatting, AuditLogging, ResponseSuccess
6. **Error states**: RequestError, ValidationError, AWSError, BudgetExhausted, LoopDetected

### Compliance states
1. **Discovery**: Discovered, Scanning
2. **Evaluation**: PolicyEvaluation
3. **Compliance levels**: FullyCompliant, PartiallyCompliant, NonCompliant, Untagged
4. **Remediation**: ViolationLogged, RemediationSuggested, AwaitingRemediation

### Cache states
1. **Lookup**: CacheQuery, KeyGeneration, CacheLookup
2. **Hit/Miss**: CacheHit, CacheMiss, TTLCheck
3. **Data operations**: DataFetch, DataProcessing, CacheWrite
4. **Degradation**: CacheUnavailable, WriteError

### Budget states
1. **Active**: BudgetActive, WithinBudget
2. **Warning**: BudgetWarning
3. **Exceeded**: BudgetExceeded, RateLimited
4. **Recovery**: AwaitingReset, BudgetReset

## State machine properties

### Deterministic transitions
All state machines are deterministic — given the same input and current state, they always transition to the same next state.

### Error recovery
Each state machine includes error states with recovery paths, ensuring system resilience.

### Graceful degradation
When Redis is unavailable, the system continues working with in-memory tracking for budgets and without caching for compliance results.

### Idempotency
Many operations (like compliance checks) are idempotent — repeated calls with same parameters produce same results (from cache when available).
