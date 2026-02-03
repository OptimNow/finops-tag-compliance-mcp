# Requirements: Production Security for MCP Server

## Introduction

This document captures the security requirements for deploying the FinOps Tag Compliance MCP Server in production environments. Based on real-world MCP security incidents (CVE-2025-6514, Clawdbot incident) and the official MCP Authorization specification, these requirements ensure the server is protected against unauthorized access, man-in-the-middle attacks, and cross-origin exploits.

**Why does this matter?** The MCP protocol initially shipped without mandatory authentication, leading to a 92% exploit probability when deploying 10+ MCP plugins (Pynt Security Research). Our server exposes AWS infrastructure topology, cost data, and tag values - information that enables targeted attacks if compromised.

**Current State**: The Phase 1 MVP has solid application-level security (input validation, audit logging, loop detection, budget enforcement) but lacks transport-level security (TLS, authentication, CORS restriction).

For security best practices reference, see [MCP_SECURITY_BEST_PRACTICES.md](../../../docs/MCP_SECURITY_BEST_PRACTICES.md).

## Glossary

- **TLS**: Transport Layer Security - cryptographic protocol for secure communication
- **ALB**: Application Load Balancer - AWS service for distributing traffic with TLS termination
- **ACM**: AWS Certificate Manager - service for provisioning SSL/TLS certificates
- **API_Key**: A secret token used to authenticate requests to the MCP server
- **CORS**: Cross-Origin Resource Sharing - browser security mechanism controlling cross-domain requests
- **OAuth_2.1**: Authorization framework standard for secure API access
- **Bearer_Token**: An access token included in HTTP Authorization header
- **mTLS**: Mutual TLS - authentication where both client and server present certificates

## Requirements

### Requirement 18: Transport Security (HTTPS/TLS)

**User Story:** As a security administrator, I want all communication with the MCP server to be encrypted, so that sensitive data cannot be intercepted in transit.

#### Acceptance Criteria

1. THE MCP_Server SHALL only accept HTTPS connections in production mode
2. THE MCP_Server SHALL use TLS 1.2 or higher for all encrypted connections
3. WHEN deployed on AWS, THE MCP_Server SHALL use an Application Load Balancer with ACM certificate for TLS termination
4. THE MCP_Server SHALL redirect HTTP requests to HTTPS when TLS is enabled
5. THE MCP_Server SHALL support configurable TLS mode via environment variable (TLS_ENABLED=true/false)
6. WHEN TLS is enabled, THE MCP_Server SHALL reject plaintext HTTP connections on the MCP endpoint

---

### Requirement 19: API Authentication

**User Story:** As a security administrator, I want the MCP server to authenticate all requests, so that only authorized users can access the tools.

#### Acceptance Criteria

1. THE MCP_Server SHALL support API key authentication via Bearer token in Authorization header
2. THE MCP_Server SHALL validate API keys against a configured list of valid keys
3. WHEN an invalid or missing API key is provided, THE MCP_Server SHALL return HTTP 401 Unauthorized
4. THE MCP_Server SHALL support multiple API keys for different users/applications
5. THE MCP_Server SHALL log authentication failures with client IP and timestamp
6. THE MCP_Server SHALL support API key rotation without server restart (via Redis or config reload)
7. THE MCP_Server SHALL include WWW-Authenticate header in 401 responses per RFC 6750

---

### Requirement 20: CORS Restriction

**User Story:** As a security administrator, I want to restrict which websites can call the MCP server, so that malicious websites cannot make unauthorized requests from users' browsers.

#### Acceptance Criteria

1. THE MCP_Server SHALL restrict CORS origins to a configurable allowlist
2. THE MCP_Server SHALL NOT use wildcard (*) for allowed origins in production mode
3. WHEN a request comes from a non-allowed origin, THE MCP_Server SHALL reject it with appropriate CORS headers
4. THE MCP_Server SHALL support configuring allowed origins via environment variable (CORS_ALLOWED_ORIGINS)
5. THE MCP_Server SHALL restrict allowed methods to POST only for MCP tool calls
6. THE MCP_Server SHALL restrict allowed headers to Content-Type, Authorization, and X-Correlation-ID

---

### Requirement 21: Network Isolation

**User Story:** As a security administrator, I want the MCP server to be deployed in a private subnet, so that it is not directly accessible from the internet.

#### Acceptance Criteria

1. THE MCP_Server SHALL be deployable in a private subnet with no public IP address
2. THE MCP_Server SHALL be accessible only through an Application Load Balancer in a public subnet
3. THE MCP_Server security group SHALL only allow inbound traffic from the ALB security group
4. THE MCP_Server SHALL use VPC endpoints for AWS API calls to avoid internet routing
5. THE MCP_Server SHALL support deployment via updated CloudFormation template

---

### Requirement 22: Bridge Authentication Support

**User Story:** As a user connecting via Claude Desktop, I want the bridge script to support authentication, so that I can securely connect to a production MCP server.

#### Acceptance Criteria

1. THE bridge script SHALL support including an Authorization header in requests to the MCP server
2. THE bridge script SHALL read the API key from an environment variable (MCP_API_KEY)
3. THE bridge script SHALL NOT log or expose the API key in error messages
4. THE bridge script SHALL support connecting to HTTPS endpoints
5. THE bridge script SHALL validate TLS certificates when connecting to HTTPS endpoints

---

### Requirement 23: Security Monitoring and Alerting

**User Story:** As a security administrator, I want to be alerted when security events occur, so that I can respond to potential attacks quickly.

#### Acceptance Criteria

1. THE MCP_Server SHALL log all authentication failures to CloudWatch
2. THE MCP_Server SHALL create CloudWatch alarms for repeated authentication failures (>10 in 5 minutes)
3. THE MCP_Server SHALL log all requests from non-allowed CORS origins
4. THE MCP_Server SHALL include client IP address in all security-related log entries
5. THE MCP_Server SHALL support SNS notifications for security alerts

---

### Requirement 24: OAuth 2.1 Support (Future)

**User Story:** As an enterprise administrator, I want to integrate the MCP server with our identity provider, so that users can authenticate with their corporate credentials.

#### Acceptance Criteria

1. THE MCP_Server SHALL support OAuth 2.1 authorization code flow
2. THE MCP_Server SHALL support token introspection for validating access tokens
3. THE MCP_Server SHALL validate token audience matches the server URL
4. THE MCP_Server SHALL support configurable OAuth scopes (e.g., mcp:tools)
5. THE MCP_Server SHALL expose OAuth Protected Resource Metadata at /.well-known/oauth-protected-resource
6. THE MCP_Server SHALL support Dynamic Client Registration (optional)

**Note**: This requirement is marked as future/optional for initial production deployment. API key authentication (Requirement 19) is sufficient for most use cases.

