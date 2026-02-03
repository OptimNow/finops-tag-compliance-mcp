# Implementation Plan: Production Security for MCP Server

## Overview

This plan implements production security for the FinOps Tag Compliance MCP Server. The implementation is designed to be incremental - each phase can be deployed independently without breaking existing functionality.

**Estimated Total Effort**: 8-12 hours

**Prerequisites**:
- Phase 1 MVP complete and deployed
- AWS account with permissions to create ALB, ACM certificates
- Domain name for HTTPS (optional but recommended)

## Tasks

### Phase A: API Key Authentication (4-5 hours)

- [x] 1. Implement API Key Authentication Middleware
  - [x] 1.1 Create auth middleware module `[Sonnet]`
    - Create `mcp_server/middleware/auth_middleware.py`
    - Implement `APIKeyAuthMiddleware` class
    - Extract and validate Bearer token from Authorization header
    - Support multiple API keys from comma-separated environment variable
    - Skip authentication for /health endpoint
    - _Requirements: 19.1, 19.2, 19.3_

  - [x] 1.2 Add authentication failure logging `[Haiku]`
    - Log failed authentication attempts with client IP
    - Log timestamp and attempted key hash (not full key)
    - Integrate with existing security_service.py
    - _Requirements: 19.5, 23.1_

  - [x] 1.3 Implement WWW-Authenticate response header `[Haiku]`
    - Return proper 401 response with WWW-Authenticate header
    - Include realm and resource_metadata URL per RFC 6750
    - _Requirements: 19.7_

  - [x] 1.4 Add authentication configuration to Settings `[Haiku]`
    - Add `AUTH_ENABLED` boolean setting (default: false)
    - Add `API_KEYS` string setting (comma-separated)
    - Update `mcp_server/config.py`
    - Update `.env.example` with new variables
    - _Requirements: 19.1, 19.4_

  - [x] 1.5 Integrate auth middleware into FastAPI app `[Sonnet]`
    - Add middleware to `mcp_server/main.py`
    - Conditionally enable based on AUTH_ENABLED setting
    - Ensure middleware runs before other middleware
    - _Requirements: 19.1_

  - [x] 1.6 Write unit tests for authentication `[Haiku]`
    - Test valid API key acceptance
    - Test invalid API key rejection (401)
    - Test missing Authorization header rejection
    - Test malformed Authorization header rejection
    - Test /health endpoint bypass
    - _Files: tests/unit/test_auth_middleware.py_
    - _Requirements: 19.1, 19.2, 19.3_

  - [x] 1.7 Write property tests for authentication `[Opus]`
    - **Property 20: Authentication Enforcement**
    - **Validates: Requirements 19.1, 19.2, 19.3**
    - _Files: tests/property/test_auth_middleware.py_

- [x] 2. Checkpoint - Authentication Complete
  - Test with AUTH_ENABLED=false (backward compatible)
  - Test with AUTH_ENABLED=true and valid API key
  - Test with AUTH_ENABLED=true and invalid API key
  - Verify /health endpoint works without authentication

### Phase B: CORS Restriction (1-2 hours)

- [x] 3. Implement Configurable CORS
  - [x] 3.1 Update CORS configuration in main.py `[Sonnet]`
    - Replace hardcoded `allow_origins=["*"]` with configurable list
    - Add `CORS_ALLOWED_ORIGINS` environment variable
    - Default to empty list (block all) when not configured
    - Restrict methods to POST and OPTIONS only
    - Restrict headers to Content-Type, Authorization, X-Correlation-ID
    - _Requirements: 20.1, 20.2, 20.4, 20.5, 20.6_

  - [x] 3.2 Add CORS configuration to Settings `[Haiku]`
    - Add `CORS_ALLOWED_ORIGINS` string setting
    - Parse comma-separated origins into list
    - Update `mcp_server/config.py`
    - Update `.env.example` with new variable
    - _Requirements: 20.4_

  - [x] 3.3 Add CORS violation logging `[Haiku]`
    - Log requests from non-allowed origins
    - Include origin, client IP, and timestamp
    - Integrate with security_service.py
    - _Requirements: 23.3_

  - [x] 3.4 Write unit tests for CORS `[Haiku]`
    - Test allowed origin acceptance
    - Test non-allowed origin rejection
    - Test preflight OPTIONS request handling
    - Test empty allowlist behavior
    - _Files: tests/unit/test_cors_config.py_
    - _Requirements: 20.1, 20.2, 20.3_

  - [x] 3.5 Write property tests for CORS `[Opus]`
    - **Property 21: CORS Restriction**
    - **Validates: Requirements 20.1, 20.2, 20.3**
    - _Files: tests/property/test_cors_config.py_

- [x] 4. Checkpoint - CORS Complete
  - Test with CORS_ALLOWED_ORIGINS="" (blocks all browser requests)
  - Test with specific origins configured
  - Verify bridge script still works (not affected by CORS)

### Phase C: Bridge Authentication Support (1-2 hours)

- [x] 5. Update Bridge Script for Authentication
  - [x] 5.1 Add API key support to bridge script `[Sonnet]`
    - Read `MCP_API_KEY` from environment variable
    - Include Authorization header in all requests to MCP server
    - Never log or expose the API key
    - _Files: scripts/mcp_bridge.py_
    - _Requirements: 22.1, 22.2, 22.3_

  - [x] 5.2 Add HTTPS support to bridge script `[Haiku]`
    - Support https:// URLs in MCP_SERVER_URL
    - Enable TLS certificate verification by default
    - Add `MCP_VERIFY_TLS` option to disable verification (dev only)
    - _Files: scripts/mcp_bridge.py_
    - _Requirements: 22.4, 22.5_

  - [x] 5.3 Update bridge error handling `[Haiku]`
    - Handle 401 Unauthorized responses gracefully
    - Log authentication errors without exposing key
    - Provide helpful error message to user
    - _Files: scripts/mcp_bridge.py_
    - _Requirements: 22.3_

  - [x] 5.4 Update Claude Desktop configuration examples `[Haiku]`
    - Update `examples/claude_desktop_config_remote.json` with API key
    - Add production configuration example with HTTPS
    - Document API key setup in comments
    - _Files: examples/claude_desktop_config_remote.json_
    - _Requirements: 22.1, 22.2_

- [x] 6. Checkpoint - Bridge Authentication Complete
  - Test bridge with API key against authenticated server
  - Test bridge with HTTPS endpoint
  - Test bridge error handling for invalid API key

### Phase D: Infrastructure Updates (2-3 hours)

- [x] 7. Update CloudFormation for Production Security
  - [x] 7.1 Add VPC with public and private subnets `[Sonnet]`
    - Create VPC with CIDR 10.0.0.0/16
    - Create 2 public subnets (for ALB)
    - Create 2 private subnets (for EC2)
    - Create Internet Gateway and NAT Gateway
    - Create route tables for public and private subnets
    - _Files: infrastructure/cloudformation.yaml_
    - _Requirements: 21.1, 21.2_

  - [x] 7.2 Add Application Load Balancer `[Sonnet]`
    - Create ALB in public subnets
    - Create HTTPS listener on port 443
    - Create target group for MCP server on port 8080
    - Configure health check on /health endpoint
    - _Files: infrastructure/cloudformation.yaml_
    - _Requirements: 18.3, 21.2_

  - [x] 7.3 Add ACM certificate parameter `[Haiku]`
    - Add parameter for ACM certificate ARN
    - Reference in HTTPS listener
    - Document certificate creation in deployment guide
    - _Files: infrastructure/cloudformation.yaml_
    - _Requirements: 18.3_

  - [x] 7.4 Update security groups `[Sonnet]`
    - Create ALB security group (443 from 0.0.0.0/0)
    - Update MCP server security group (8080 from ALB SG only)
    - Remove direct public access to EC2
    - _Files: infrastructure/cloudformation.yaml_
    - _Requirements: 21.3_

  - [x] 7.5 Add VPC endpoints for AWS APIs `[Haiku]`
    - Add VPC endpoint for EC2 API
    - Add VPC endpoint for S3 API
    - Add VPC endpoint for Cost Explorer API
    - Add VPC endpoint for Resource Groups Tagging API
    - _Files: infrastructure/cloudformation.yaml_
    - _Requirements: 21.4_

  - [x] 7.6 Add API key to Secrets Manager `[Haiku]`
    - Create Secrets Manager secret for API keys
    - Reference in EC2 user data to set environment variable
    - Document key rotation process
    - _Files: infrastructure/cloudformation.yaml_
    - _Requirements: 19.6_

- [x] 8. Checkpoint - Infrastructure Complete
  - Validate CloudFormation template syntax
  - Review security group rules
  - Verify VPC endpoint configuration

### Phase E: Security Monitoring (1-2 hours)

- [x] 9. Add Security Monitoring and Alerting
  - [x] 9.1 Add CloudWatch metric for authentication failures `[Haiku]`
    - Emit custom metric when authentication fails
    - Include dimensions: client_ip, endpoint
    - _Files: mcp_server/middleware/auth_middleware.py_
    - _Requirements: 23.1_

  - [x] 9.2 Add CloudWatch alarm for auth failures `[Haiku]`
    - Create alarm for >10 failures in 5 minutes
    - Configure SNS notification
    - _Files: infrastructure/cloudformation.yaml_
    - _Requirements: 23.2_

  - [x] 9.3 Add SNS topic for security alerts `[Haiku]`
    - Create SNS topic for security alerts
    - Add email subscription parameter
    - _Files: infrastructure/cloudformation.yaml_
    - _Requirements: 23.5_

  - [x] 9.4 Update security logging `[Haiku]`
    - Ensure client IP is included in all security logs
    - Add structured logging for security events
    - _Files: mcp_server/services/security_service.py_
    - _Requirements: 23.4_

- [x] 10. Checkpoint - Security Monitoring Complete
  - Verify CloudWatch metrics are emitted
  - Test alarm triggers on repeated auth failures
  - Verify SNS notifications are sent

### Phase F: Documentation and Deployment (1 hour)

- [x] 11. Update Documentation
  - [x] 11.1 Update deployment guide `[Haiku]`
    - Add production deployment section
    - Document ACM certificate creation
    - Document API key generation and rotation
    - Document CloudFormation parameters
    - _Files: docs/DEPLOYMENT.md_

  - [x] 11.2 Update security best practices `[Haiku]`
    - Add production deployment checklist
    - Document authentication configuration
    - Document CORS configuration
    - _Files: docs/MCP_SECURITY_BEST_PRACTICES.md_

  - [x] 11.3 Update user manual `[Haiku]`
    - Add section on connecting to production server
    - Document API key configuration in Claude Desktop
    - Add troubleshooting for authentication errors
    - _Files: docs/USER_MANUAL.md_

  - [x] 11.4 Create security configuration reference `[Haiku]`
    - Document all security-related environment variables
    - Document deployment modes (dev, beta, production)
    - Add configuration examples for each mode
    - _Files: docs/SECURITY_CONFIGURATION.md_

- [x] 12. Final Checkpoint - Production Security Complete
  - Run full regression test suite
  - Deploy to test environment with all security features
  - Test end-to-end with Claude Desktop
  - Verify all security features work together
  - Document any issues encountered

### Phase G: OAuth 2.1 Support (Future - 4-6 hours)

**Note**: This phase is optional and can be implemented later when enterprise SSO integration is needed.

- [ ] 13. Implement OAuth 2.1 Support
  - [ ] 13.1 Add OAuth Protected Resource Metadata endpoint `[Sonnet]`
    - Expose /.well-known/oauth-protected-resource
    - Return authorization server URL, scopes, resource URL
    - _Requirements: 24.5_

  - [ ] 13.2 Implement token introspection `[Sonnet]`
    - Add token verifier that calls authorization server
    - Validate token audience matches server URL
    - Extract scopes from token
    - _Requirements: 24.2, 24.3_

  - [ ] 13.3 Add OAuth configuration settings `[Haiku]`
    - Add OAUTH_ENABLED setting
    - Add OAUTH_ISSUER_URL setting
    - Add OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET settings
    - Add OAUTH_REQUIRED_SCOPES setting
    - _Requirements: 24.1, 24.4_

  - [ ] 13.4 Integrate OAuth middleware `[Sonnet]`
    - Add OAuth middleware alongside API key middleware
    - Support both authentication methods
    - Prefer OAuth when both are configured
    - _Requirements: 24.1_

  - [ ] 13.5 Write tests for OAuth support `[Opus]`
    - Test token validation
    - Test audience validation
    - Test scope enforcement
    - _Requirements: 24.1, 24.3, 24.4_

## Notes

- Tasks are designed to be incremental - each phase can be deployed independently
- API key authentication (Phase A) is sufficient for most production use cases
- OAuth 2.1 (Phase G) is optional and can be added later for enterprise SSO
- All changes are backward compatible when security features are disabled
- **Model tags**: `[Haiku]` for boilerplate/simple tasks, `[Sonnet]` for business logic, `[Opus]` for complex reasoning/property tests

## Quick Start for Production Deployment

After completing all tasks, deploy to production with:

```bash
# 1. Generate API key
API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
echo "Generated API key: $API_KEY"

# 2. Create ACM certificate (manual step in AWS Console)
# Note the certificate ARN

# 3. Deploy CloudFormation stack
aws cloudformation deploy \
  --template-file infrastructure/cloudformation.yaml \
  --stack-name tagging-mcp-server-prod \
  --parameter-overrides \
    Environment=prod \
    ACMCertificateArn=arn:aws:acm:us-east-1:123456789012:certificate/xxx \
    APIKeys=$API_KEY \
  --capabilities CAPABILITY_IAM

# 4. Get ALB DNS name
ALB_DNS=$(aws cloudformation describe-stacks \
  --stack-name tagging-mcp-server-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDNS`].OutputValue' \
  --output text)

# 5. Update Claude Desktop config
# Set MCP_SERVER_URL=https://$ALB_DNS
# Set MCP_API_KEY=$API_KEY
```

