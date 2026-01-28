# MCP Security Best Practices

This document provides security guidance for deploying the FinOps Tag Compliance MCP Server, based on lessons learned from real-world MCP security incidents and vulnerabilities discovered in 2025.

## Executive Summary

The Model Context Protocol (MCP) initially shipped without mandatory authentication, prioritizing interoperability over security. This design decision has led to significant security incidents:

- **92% exploit probability** when deploying 10+ MCP plugins (Pynt Security Research)
- **CVE-2025-6514 (CVSS 9.6)**: Critical vulnerability in mcp-remote package allowing arbitrary OS command execution
- **CVE-2025-49596**: Remote code execution vulnerability in MCP Inspector
- **Clawdbot Incident**: Hundreds of users had API keys, credentials, and chat histories exposed due to localhost authentication bypass

OAuth 2.1 support was added to MCP in mid-2025, but thousands of servers deployed without authentication remain in production. This document helps you avoid these pitfalls.

## Threat Model

### What This Server Accesses

The FinOps Tag Compliance MCP Server has **read-only access** to:
- AWS resource metadata (EC2, RDS, S3, Lambda, ECS instances)
- AWS Cost Explorer data
- Resource tags and compliance status

### Potential Impact of Compromise

| Asset | Risk if Exposed |
|-------|-----------------|
| Resource inventory | Attacker learns your infrastructure topology |
| Cost data | Financial information disclosure |
| Tag values | May contain environment names, team names, project codes |
| AWS API patterns | Reconnaissance for further attacks |

While read-only, this information enables targeted attacks against your infrastructure.

---

## Transport Security

### Stdio Transport (Recommended for Local Use)

**Use case**: Claude Desktop, MCP Inspector, local development

**Security model**:
- Communication via stdin/stdout (no network exposure)
- Process-level isolation provided by operating system
- No authentication needed (inherits user's permissions)

**Threats mitigated**:
- No network attack surface
- No remote exploitation possible

**Recommendation**: Use stdio transport for Claude Desktop integration and development.

```bash
# Safe: runs locally, no network exposure
python -m mcp_server.stdio_server
```

### HTTP Transport (Requires Additional Security)

**Use case**: Remote deployment, multi-user access, CI/CD integration

**Security model**:
- Network-accessible REST API on port 8080
- **No built-in authentication** (critical gap)
- **Open CORS policy** (`allow_origins=["*"]`)

**Threats**:
- Unauthorized access from any network client
- Cross-site request forgery from malicious websites
- Man-in-the-middle attacks (no TLS at application level)

**Recommendation**: Never expose HTTP transport directly to the internet. Always deploy behind an authenticating reverse proxy with TLS.

### Stdio-to-HTTP Bridge (Remote Server with Claude Desktop)

**Use case**: Running the MCP server on a remote machine (EC2, cloud VM) while using Claude Desktop locally.

**Why a bridge is needed**: Claude Desktop only supports stdio transport (stdin/stdout communication with a local process). It cannot directly connect to remote HTTP servers. A bridge process translates between the two:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BRIDGE ARCHITECTURE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐      ┌─────────────┐      ┌─────────────────────────────┐ │
│  │    Claude    │      │   Bridge    │      │      Remote EC2 Server      │ │
│  │   Desktop    │◄────►│  (local)    │◄────►│    (MCP HTTP Transport)     │ │
│  │              │ stdio│             │ HTTP │                             │ │
│  └──────────────┘      └─────────────┘      └─────────────────────────────┘ │
│                                                                              │
│  JSON-RPC over         Translator          REST API on port 8080            │
│  stdin/stdout          process             (or behind ALB on 443)           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Security considerations by deployment stage**:

| Stage | Configuration | Security Level |
|-------|---------------|----------------|
| **Development/Testing** | HTTP over internet, security group IP-restricted | Acceptable for testing |
| **Beta (Trusted Users)** | HTTP with IP-restricted security groups | Reasonable for limited trusted access |
| **Production** | HTTPS + Authentication + Private subnet | Required |

**The bridge itself is safe** - it's a simple translator running locally on your machine. The security concern is the **network path between your machine and the remote server**.

**For production with the bridge pattern**:

1. **Add TLS**: Put an ALB or nginx reverse proxy with SSL certificate in front of the server
2. **Add authentication**: Configure API keys or JWT tokens that the bridge includes in requests
3. **Network isolation**: Keep the server in a private subnet, access via VPN or AWS PrivateLink
4. **Restrict access**: Security groups should only allow your VPN CIDR or specific IPs

**Bridge configuration example** (with authentication):
```json
{
  "mcpServers": {
    "finops-tagging": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://your-alb.example.com/mcp",
        "--header", "Authorization: Bearer ${MCP_API_KEY}"
      ],
      "env": {
        "MCP_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

---

## Authentication Requirements

### The Localhost Bypass Vulnerability (Clawdbot Lesson)

A critical vulnerability pattern was discovered in MCP deployments:

1. Server auto-grants localhost (`127.0.0.1`) connections without authentication
2. Server runs behind reverse proxy (nginx, Caddy) on same host
3. Reverse proxy forwards all requests, which appear to come from `127.0.0.1`
4. **Result**: All external requests bypass authentication

**This affected hundreds of real deployments**, exposing credentials and sensitive data.

### Authentication Options

#### Option A: OAuth 2.1 (Recommended for Multi-User)

```
┌─────────────────────────────────────────────────────────────────┐
│                     OAuth 2.1 Flow                               │
├─────────────────────────────────────────────────────────────────┤
│  1. Client redirects to IdP (Okta, Auth0, Azure AD)             │
│  2. User authenticates with IdP                                  │
│  3. IdP returns authorization code                               │
│  4. Client exchanges code for access token                       │
│  5. Client includes token in MCP requests                        │
│  6. MCP server validates token with IdP                          │
└─────────────────────────────────────────────────────────────────┘
```

**Pros**: Standard protocol, integrates with enterprise IdP, token expiration
**Cons**: Complex setup, requires IdP infrastructure

#### Option B: API Key Authentication (Simpler)

```
┌─────────────────────────────────────────────────────────────────┐
│                     API Key Flow                                 │
├─────────────────────────────────────────────────────────────────┤
│  1. Admin generates API key, stores in secrets manager          │
│  2. Client includes key in header: Authorization: Bearer <key>  │
│  3. MCP server validates key against stored value               │
│  4. Rotate keys every 90 days                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Pros**: Simple to implement, no external dependencies
**Cons**: Key rotation burden, no user-level audit trail

#### Option C: Mutual TLS (Highest Security)

```
┌─────────────────────────────────────────────────────────────────┐
│                     mTLS Flow                                    │
├─────────────────────────────────────────────────────────────────┤
│  1. Both client and server have X.509 certificates              │
│  2. TLS handshake validates both certificates                   │
│  3. Server extracts client identity from certificate            │
│  4. No tokens or keys to manage (certificate-based)             │
└─────────────────────────────────────────────────────────────────┘
```

**Pros**: Strongest authentication, no secrets in requests
**Cons**: Certificate infrastructure required, complex client setup

---

## Reverse Proxy Configuration

### Unsafe Configuration (Vulnerable to Localhost Bypass)

```nginx
# DANGEROUS: Trusts all connections as localhost
server {
    listen 80;
    location /mcp/ {
        proxy_pass http://localhost:8080;
        # No authentication!
    }
}
```

### Safe Configuration

```nginx
server {
    # HTTPS only - reject HTTP
    listen 443 ssl;

    # TLS configuration
    ssl_certificate /etc/ssl/certs/mcp-server.crt;
    ssl_certificate_key /etc/ssl/private/mcp-server.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;

    # Authentication BEFORE proxying
    # Option 1: External auth service
    auth_request /auth;

    # Option 2: Basic auth (minimum viable)
    # auth_basic "MCP Server";
    # auth_basic_user_file /etc/nginx/.htpasswd;

    location /mcp/ {
        proxy_pass http://localhost:8080;

        # Clear potentially spoofed headers
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Remove any pre-existing trust headers from client
        proxy_set_header X-Authenticated-User "";
        proxy_set_header X-Internal-Request "";
    }

    # Deny direct access to health endpoint from outside
    location /health {
        allow 10.0.0.0/8;
        allow 172.16.0.0/12;
        allow 192.168.0.0/16;
        deny all;
        proxy_pass http://localhost:8080;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    return 301 https://$server_name$request_uri;
}
```

---

## Network Architecture

### Recommended AWS Deployment

```
┌─────────────────────────────────────────────────────────────────┐
│                        INTERNET                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AWS WAF (Optional)                            │
│            Rate limiting, IP blocking, SQL injection             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Application Load Balancer (Public Subnet)           │
│    • TLS termination (ACM certificate)                          │
│    • OIDC authentication (Cognito, Okta, Auth0)                 │
│    • Access logs to S3                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PRIVATE SUBNET                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              MCP Server (ECS/EC2)                         │  │
│  │    • No public IP address                                 │  │
│  │    • Security group: inbound from ALB only                │  │
│  │    • IAM role with read-only permissions                  │  │
│  │    • CloudWatch agent for logging                         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              ElastiCache Redis (Optional)                 │  │
│  │    • Encryption at rest and in transit                    │  │
│  │    • Security group: inbound from MCP server only         │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              VPC Endpoints (Private Link)                        │
│    • EC2, RDS, S3, Lambda, ECS, Cost Explorer                   │
│    • No internet gateway needed for AWS API calls               │
└─────────────────────────────────────────────────────────────────┘
```

### Security Group Rules

**ALB Security Group**:
```
Inbound:
  - 443/tcp from 0.0.0.0/0 (HTTPS from internet)
Outbound:
  - 8080/tcp to MCP Server security group
```

**MCP Server Security Group**:
```
Inbound:
  - 8080/tcp from ALB security group ONLY
Outbound:
  - 443/tcp to VPC endpoints (AWS APIs)
  - 6379/tcp to Redis security group (if using Redis)
```

---

## CORS Configuration

### Current State (Insecure)

```python
# mcp_server/main.py - CURRENT
CORSMiddleware(
    allow_origins=["*"],        # Any website can call!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This allows any website to make requests to your MCP server from a user's browser.

### Recommended Configuration

```python
# Restrict to known origins
CORSMiddleware(
    allow_origins=[
        "https://claude.ai",                    # Anthropic's Claude
        "https://your-app.example.com",         # Your application
    ],
    allow_credentials=False,   # Disable unless specifically needed
    allow_methods=["POST"],    # MCP only uses POST for tool calls
    allow_headers=["Content-Type", "Authorization", "X-Correlation-ID"],
)
```

### For Internal-Only Deployment

```python
# No CORS needed if not accessed from browsers
# Remove CORSMiddleware entirely, or:
CORSMiddleware(
    allow_origins=[],  # Block all cross-origin requests
)
```

---

## AWS Credential Security

### Current Implementation (Good)

This server uses **read-only IAM permissions**:
- `ec2:Describe*` - Read EC2 instance metadata
- `rds:Describe*` - Read RDS instance metadata
- `s3:ListAllMyBuckets`, `s3:GetBucketTagging` - Read S3 bucket info
- `lambda:ListFunctions`, `lambda:ListTags` - Read Lambda metadata
- `ce:GetCostAndUsage` - Read cost data
- `tag:GetResources` - Read resource tags

**No write permissions** - limits blast radius if compromised.

### Recommendations

1. **Use IAM Instance Profile** (not environment variables)
   ```bash
   # WRONG: Credentials in environment
   AWS_ACCESS_KEY_ID=AKIA...
   AWS_SECRET_ACCESS_KEY=...

   # RIGHT: Instance profile attached to EC2/ECS task
   # Credentials automatically rotated by AWS
   ```

2. **Apply Resource Conditions**
   ```json
   {
     "Effect": "Allow",
     "Action": ["ec2:DescribeInstances"],
     "Resource": "*",
     "Condition": {
       "StringEquals": {
         "aws:RequestedRegion": ["us-east-1", "us-west-2"]
       }
     }
   }
   ```

3. **Enable CloudTrail**
   - Log all API calls made by the MCP server's IAM role
   - Set up alerts for unusual patterns (after-hours access, new regions)

4. **Use VPC Endpoints**
   - AWS API calls stay within AWS network
   - No internet gateway required
   - Reduces exposure and improves latency

---

## Deployment Checklist

### Before Production Deployment

#### Authentication & Authorization
- [ ] Authentication mechanism implemented (OAuth 2.1, API key, or mTLS)
- [ ] Reverse proxy configured with auth BEFORE proxying
- [ ] Localhost bypass vulnerability mitigated

#### Network Security
- [ ] TLS/HTTPS enforced (no plaintext HTTP)
- [ ] Server deployed in private subnet (no public IP)
- [ ] Security groups restrict inbound to load balancer only
- [ ] VPC endpoints configured for AWS API access

#### Application Security
- [ ] CORS restricted to known origins (not `*`)
- [ ] Request sanitization enabled (`REQUEST_SANITIZATION_ENABLED=true`)
- [ ] Budget tracking enabled (`BUDGET_TRACKING_ENABLED=true`)
- [ ] Loop detection enabled (`LOOP_DETECTION_ENABLED=true`)
- [ ] Security monitoring enabled (`SECURITY_MONITORING_ENABLED=true`)

#### Credential Management
- [ ] AWS credentials via instance profile (not env vars or files)
- [ ] No hardcoded secrets in code or config files
- [ ] API keys stored in secrets manager (if using API key auth)
- [ ] Key rotation schedule established (90 days recommended)

#### Monitoring & Logging
- [ ] CloudWatch logging enabled for security events
- [ ] CloudTrail enabled for AWS API audit trail
- [ ] Alerts configured for security events (budget exhausted, injection attempts)
- [ ] Access logs enabled on load balancer

#### Incident Response
- [ ] Runbook documented for credential rotation
- [ ] Contact list for security incidents
- [ ] Backup/restore procedure tested

---

## Incident Response

### If Compromise Suspected

1. **Immediate Actions** (first 15 minutes)
   ```bash
   # Revoke IAM credentials immediately
   aws iam update-access-key --access-key-id AKIA... --status Inactive

   # Or delete the instance profile's role (nuclear option)
   aws iam remove-role-from-instance-profile \
     --instance-profile-name MCP-Server-Profile \
     --role-name MCP-Server-Role
   ```

2. **Isolate the Server**
   ```bash
   # Update security group to block all traffic
   aws ec2 revoke-security-group-ingress \
     --group-id sg-xxx \
     --protocol all \
     --source-group sg-alb
   ```

3. **Preserve Evidence**
   - Snapshot EBS volumes before termination
   - Export CloudWatch logs to S3
   - Export CloudTrail logs for the time period

4. **Investigate**
   - Review CloudWatch logs for unauthorized tool calls
   - Check CloudTrail for unusual AWS API patterns
   - Analyze audit logs (`audit_logs.db`) for correlation IDs
   - Check for data exfiltration (large Cost Explorer queries, full resource listings)

5. **Remediate**
   - Rotate all API keys and credentials
   - Deploy patched/updated server
   - Review and restrict IAM permissions
   - Update security group rules

6. **Report**
   - Document timeline and impact
   - Notify stakeholders per your incident response policy
   - File CVE if vulnerability discovered

---

## Security Configuration Reference

See [SECURITY_CONFIGURATION.md](SECURITY_CONFIGURATION.md) for detailed configuration options including:

- Request sanitization settings
- Budget tracking limits
- Loop detection parameters
- Security monitoring configuration
- Timeout settings

---

## Related Documentation

- [SECURITY_CONFIGURATION.md](SECURITY_CONFIGURATION.md) - Detailed security settings
- [IAM_PERMISSIONS.md](IAM_PERMISSIONS.md) - Required AWS IAM permissions
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment guide
- [AUDIT_LOGGING.md](AUDIT_LOGGING.md) - Audit log configuration
- [CLOUDWATCH_LOGGING.md](CLOUDWATCH_LOGGING.md) - CloudWatch integration

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-01-28 | Initial release based on MCP security incidents |
