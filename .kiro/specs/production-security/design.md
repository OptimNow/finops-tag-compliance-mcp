# Design: Production Security for MCP Server

## Overview

This document describes the technical design for securing the FinOps Tag Compliance MCP Server for production deployment. The design follows the MCP Authorization specification and addresses vulnerabilities identified in real-world MCP security incidents.

## Architecture

### Current Architecture (Insecure)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CURRENT ARCHITECTURE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐                    ┌─────────────────────────────────────┐ │
│  │    Claude    │      HTTP          │      EC2 Instance (Public IP)       │ │
│  │   Desktop    │◄──────────────────►│    • Port 8080 exposed              │ │
│  │   + Bridge   │   No encryption    │    • No authentication              │ │
│  └──────────────┘   No auth          │    • CORS: allow_origins=["*"]      │ │
│                                      └─────────────────────────────────────┘ │
│                                                                              │
│  RISKS:                                                                      │
│  • Traffic can be intercepted (no TLS)                                      │
│  • Anyone with IP can call server (no auth)                                 │
│  • Any website can make requests (open CORS)                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Target Architecture (Secure)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        TARGET ARCHITECTURE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐      HTTPS         ┌─────────────────────────────────────┐ │
│  │    Claude    │◄──────────────────►│    Application Load Balancer        │ │
│  │   Desktop    │   + Bearer Token   │    • TLS termination (ACM cert)     │ │
│  │   + Bridge   │                    │    • Public subnet                  │ │
│  └──────────────┘                    └──────────────┬──────────────────────┘ │
│                                                     │                        │
│                                                     │ HTTP (internal)        │
│                                                     ▼                        │
│                                      ┌─────────────────────────────────────┐ │
│                                      │    EC2 Instance (Private Subnet)    │ │
│                                      │    • No public IP                   │ │
│                                      │    • API key validation             │ │
│                                      │    • CORS restricted                │ │
│                                      │    • SG: ALB only                   │ │
│                                      └──────────────┬──────────────────────┘ │
│                                                     │                        │
│                                                     │ VPC Endpoints          │
│                                                     ▼                        │
│                                      ┌─────────────────────────────────────┐ │
│                                      │    AWS APIs (EC2, RDS, S3, etc.)    │ │
│                                      │    • No internet routing            │ │
│                                      └─────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Design

### 1. API Key Authentication Middleware

**Location**: `mcp_server/middleware/auth_middleware.py`

**Design**:
```python
class APIKeyAuthMiddleware:
    """
    Validates Bearer tokens in Authorization header against configured API keys.
    
    Flow:
    1. Extract Authorization header from request
    2. Validate format: "Bearer <api_key>"
    3. Check api_key against valid keys (from env or Redis)
    4. If invalid: return 401 with WWW-Authenticate header
    5. If valid: add authenticated user info to request context
    """
    
    def __init__(self, api_keys: list[str], redis_client: Optional[RedisCache] = None):
        self.api_keys = set(api_keys)
        self.redis_client = redis_client  # For dynamic key loading
    
    async def __call__(self, request: Request, call_next):
        # Skip auth for health endpoint
        if request.url.path == "/health":
            return await call_next(request)
        
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return self._unauthorized_response()
        
        api_key = auth_header[7:]  # Remove "Bearer " prefix
        if not self._validate_key(api_key):
            self._log_auth_failure(request)
            return self._unauthorized_response()
        
        return await call_next(request)
```

**Configuration**:
```bash
# Environment variables
API_KEYS=key1,key2,key3  # Comma-separated list
AUTH_ENABLED=true        # Enable/disable authentication
```

### 2. CORS Configuration

**Location**: `mcp_server/main.py`

**Current (Insecure)**:
```python
CORSMiddleware(
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Target (Secure)**:
```python
def get_cors_config() -> dict:
    """Build CORS configuration from environment."""
    allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    
    # Filter empty strings
    allowed_origins = [o.strip() for o in allowed_origins if o.strip()]
    
    # Default to empty list (block all) if not configured
    if not allowed_origins:
        allowed_origins = []
    
    return {
        "allow_origins": allowed_origins,
        "allow_credentials": False,
        "allow_methods": ["POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Correlation-ID"],
    }
```

**Configuration**:
```bash
# Environment variables
CORS_ALLOWED_ORIGINS=https://claude.ai,https://your-app.example.com
```

### 3. Bridge Script Authentication

**Location**: `scripts/mcp_bridge.py`

**Changes**:
```python
# Configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080")
MCP_API_KEY = os.getenv("MCP_API_KEY", "")  # NEW
TIMEOUT = 30

def get_auth_headers() -> dict:
    """Build authentication headers."""
    headers = {"Content-Type": "application/json"}
    if MCP_API_KEY:
        headers["Authorization"] = f"Bearer {MCP_API_KEY}"
    return headers

def handle_call_tool(request: dict) -> dict:
    """Handle tools/call by calling the REST API."""
    params = request.get("params", {})
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    
    log(f"Calling tool: {tool_name}")
    try:
        resp = requests.post(
            f"{MCP_SERVER_URL}/mcp/tools/call",
            json={"name": tool_name, "arguments": arguments},
            headers=get_auth_headers(),  # CHANGED: Include auth headers
            timeout=TIMEOUT,
            verify=True  # CHANGED: Verify TLS certificates
        )
        # ... rest of implementation
```

**Claude Desktop Configuration**:
```json
{
  "mcpServers": {
    "tagging-mcp": {
      "command": "python",
      "args": ["C:\\path\\to\\scripts\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "https://your-alb.example.com",
        "MCP_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

### 4. CloudFormation Updates

**Location**: `infrastructure/cloudformation.yaml`

**New Resources**:

```yaml
# Application Load Balancer
MCPLoadBalancer:
  Type: AWS::ElasticLoadBalancingV2::LoadBalancer
  Properties:
    Name: !Sub "${ProjectName}-alb-${Environment}"
    Scheme: internet-facing
    Type: application
    Subnets:
      - !Ref PublicSubnet1
      - !Ref PublicSubnet2
    SecurityGroups:
      - !Ref ALBSecurityGroup

# HTTPS Listener with ACM Certificate
HTTPSListener:
  Type: AWS::ElasticLoadBalancingV2::Listener
  Properties:
    LoadBalancerArn: !Ref MCPLoadBalancer
    Port: 443
    Protocol: HTTPS
    Certificates:
      - CertificateArn: !Ref ACMCertificateArn
    DefaultActions:
      - Type: forward
        TargetGroupArn: !Ref MCPTargetGroup

# Target Group for MCP Server
MCPTargetGroup:
  Type: AWS::ElasticLoadBalancingV2::TargetGroup
  Properties:
    Name: !Sub "${ProjectName}-tg-${Environment}"
    Port: 8080
    Protocol: HTTP
    VpcId: !Ref VPC
    TargetType: instance
    HealthCheckPath: /health
    HealthCheckIntervalSeconds: 30

# ALB Security Group
ALBSecurityGroup:
  Type: AWS::EC2::SecurityGroup
  Properties:
    GroupDescription: Security group for ALB
    VpcId: !Ref VPC
    SecurityGroupIngress:
      - IpProtocol: tcp
        FromPort: 443
        ToPort: 443
        CidrIp: 0.0.0.0/0

# Updated MCP Server Security Group (ALB only)
MCPServerSecurityGroup:
  Type: AWS::EC2::SecurityGroup
  Properties:
    GroupDescription: Security group for MCP Server
    VpcId: !Ref VPC
    SecurityGroupIngress:
      - IpProtocol: tcp
        FromPort: 8080
        ToPort: 8080
        SourceSecurityGroupId: !Ref ALBSecurityGroup
```

### 5. Security Monitoring

**CloudWatch Alarms**:

```yaml
# Authentication Failure Alarm
AuthFailureAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: !Sub "${ProjectName}-auth-failures-${Environment}"
    AlarmDescription: "Alert when authentication failures exceed threshold"
    MetricName: AuthenticationFailures
    Namespace: !Sub "${ProjectName}/${Environment}"
    Statistic: Sum
    Period: 300  # 5 minutes
    EvaluationPeriods: 1
    Threshold: 10
    ComparisonOperator: GreaterThanThreshold
    AlarmActions:
      - !Ref SecurityAlertTopic

# SNS Topic for Security Alerts
SecurityAlertTopic:
  Type: AWS::SNS::Topic
  Properties:
    TopicName: !Sub "${ProjectName}-security-alerts-${Environment}"
```

## Security Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AUTH_ENABLED` | Enable API key authentication | `false` | No |
| `API_KEYS` | Comma-separated list of valid API keys | `""` | Yes (if AUTH_ENABLED) |
| `CORS_ALLOWED_ORIGINS` | Comma-separated list of allowed origins | `""` | Yes (production) |
| `TLS_ENABLED` | Enable TLS mode (reject HTTP) | `false` | No |

### API Key Management

**Generation**:
```bash
# Generate a secure API key
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Storage**:
- Store API keys in AWS Secrets Manager
- Reference in CloudFormation via `{{resolve:secretsmanager:...}}`
- Rotate every 90 days

**Rotation**:
1. Generate new API key
2. Add to API_KEYS list (both old and new valid)
3. Update clients to use new key
4. Remove old key from API_KEYS list

## Correctness Properties

### Property 20: Authentication Enforcement

**Validates**: Requirements 19.1, 19.2, 19.3

```python
@given(
    api_key=st.text(min_size=1, max_size=100),
    valid_keys=st.lists(st.text(min_size=1, max_size=100), min_size=1, max_size=10)
)
def test_authentication_enforcement(api_key, valid_keys):
    """
    Property: Requests with invalid API keys are always rejected with 401.
    
    For all api_key and valid_keys:
    - If api_key in valid_keys: request succeeds
    - If api_key not in valid_keys: request returns 401
    """
```

### Property 21: CORS Restriction

**Validates**: Requirements 20.1, 20.2, 20.3

```python
@given(
    origin=st.text(min_size=1, max_size=200),
    allowed_origins=st.lists(st.text(min_size=1, max_size=200), min_size=0, max_size=10)
)
def test_cors_restriction(origin, allowed_origins):
    """
    Property: Requests from non-allowed origins are rejected.
    
    For all origin and allowed_origins:
    - If origin in allowed_origins: CORS headers allow request
    - If origin not in allowed_origins: CORS headers block request
    """
```

### Property 22: TLS Enforcement

**Validates**: Requirements 18.1, 18.6

```python
@given(
    tls_enabled=st.booleans(),
    request_scheme=st.sampled_from(["http", "https"])
)
def test_tls_enforcement(tls_enabled, request_scheme):
    """
    Property: When TLS is enabled, HTTP requests are rejected.
    
    For all tls_enabled and request_scheme:
    - If tls_enabled and request_scheme == "http": request rejected
    - If tls_enabled and request_scheme == "https": request allowed
    - If not tls_enabled: both schemes allowed
    """
```

## Deployment Modes

### Mode 1: Development (Current)

```bash
AUTH_ENABLED=false
CORS_ALLOWED_ORIGINS=*
TLS_ENABLED=false
```

- No authentication required
- All CORS origins allowed
- HTTP connections accepted

### Mode 2: Beta Testing

```bash
AUTH_ENABLED=false
CORS_ALLOWED_ORIGINS=
TLS_ENABLED=false
```

- No authentication (IP-restricted via security group)
- CORS disabled (no browser access)
- HTTP connections accepted

### Mode 3: Production

```bash
AUTH_ENABLED=true
API_KEYS=<key1>,<key2>
CORS_ALLOWED_ORIGINS=https://claude.ai
TLS_ENABLED=true
```

- API key authentication required
- CORS restricted to known origins
- HTTPS only (via ALB)

## Migration Path

### Phase 1: Add Authentication Middleware (No Breaking Changes)

1. Implement `auth_middleware.py`
2. Add to FastAPI app with `AUTH_ENABLED=false` default
3. Test with existing deployment
4. No client changes required

### Phase 2: Update CORS Configuration

1. Add `CORS_ALLOWED_ORIGINS` environment variable
2. Update `main.py` to use configurable CORS
3. Test with empty allowlist (blocks browser requests)
4. No client changes required (bridge uses direct HTTP)

### Phase 3: Deploy ALB with TLS

1. Update CloudFormation template
2. Request ACM certificate for domain
3. Deploy new stack with ALB
4. Update bridge to use HTTPS endpoint
5. Update Claude Desktop config with new URL

### Phase 4: Enable Authentication

1. Generate API keys
2. Store in Secrets Manager
3. Update CloudFormation to pass keys to EC2
4. Enable `AUTH_ENABLED=true`
5. Update bridge config with API key
6. Update Claude Desktop config with API key

## Testing Strategy

### Unit Tests

- Test API key validation logic
- Test CORS header generation
- Test authentication failure logging

### Integration Tests

- Test authenticated requests succeed
- Test unauthenticated requests fail with 401
- Test CORS preflight requests
- Test TLS enforcement

### Security Tests

- Test invalid API key rejection
- Test missing Authorization header rejection
- Test malformed Authorization header rejection
- Test CORS bypass attempts
- Test header injection attempts

