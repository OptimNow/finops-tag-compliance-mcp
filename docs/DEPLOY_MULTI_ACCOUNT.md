# Multi-Account Deployment Guide
## FinOps Tag Compliance MCP Server - Enterprise AWS Organizations

**Version**: 1.0
**Last Updated**: January 2025
**Status**: Implementation Guide

---

## Overview

This guide explains how to deploy the FinOps Tag Compliance MCP server across multiple AWS accounts within an enterprise organization.

**Current Status (Phase 1)**: Single-account deployment only. Multi-account requires workarounds.

**Phase 2 (Q2 2025)**: Native multi-account support via AWS AssumeRole.

---

## Three Deployment Options

| Option | Availability | Complexity | Cost | Best For |
|--------|-------------|------------|------|----------|
| **Option 1: Multiple Deployments** | Available now | Low | High (N×€40/month) | Phase 1, immediate needs |
| **Option 2: AssumeRole Cross-Account** | Phase 2 (Q2 2025) | Medium | Low (€40/month) | Enterprise, production |
| **Option 3: AWS Organizations API** | Phase 2+ (Q3 2025) | High | Low (€40/month) | Large enterprises (50+ accounts) |

---

## Option 1: Multiple Deployments (Available Now)

### Overview

Deploy one MCP server instance per AWS account. Each instance scans only its own account.

### Architecture

```
Enterprise "ACME Corp" with 5 AWS Accounts:

┌─────────────────────────────────────────────────────────────┐
│ Account 1: Production (123456789012)                        │
│   ┌─────────────────────────────────────────────┐          │
│   │ EC2 Instance: mcp-prod.acme.com             │          │
│   │ MCP Server → Scans Account 1 only           │          │
│   └─────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Account 2: Staging (234567890123)                           │
│   ┌─────────────────────────────────────────────┐          │
│   │ EC2 Instance: mcp-staging.acme.com          │          │
│   │ MCP Server → Scans Account 2 only           │          │
│   └─────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Account 3: Development (345678901234)                       │
│   ┌─────────────────────────────────────────────┐          │
│   │ EC2 Instance: mcp-dev.acme.com              │          │
│   │ MCP Server → Scans Account 3 only           │          │
│   └─────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘

... (repeat for each account)

┌─────────────────────────────────────────────────────────────┐
│ Client Configuration (Claude Desktop)                        │
│                                                              │
│ {                                                            │
│   "mcpServers": {                                            │
│     "finops-prod": {                                         │
│       "command": "python",                                   │
│       "args": ["mcp_bridge.py"],                             │
│       "env": {                                               │
│         "MCP_SERVER_URL": "http://mcp-prod.acme.com:8080"   │
│       }                                                      │
│     },                                                       │
│     "finops-staging": {                                      │
│       "command": "python",                                   │
│       "args": ["mcp_bridge.py"],                             │
│       "env": {                                               │
│         "MCP_SERVER_URL": "http://mcp-staging.acme.com:8080"│
│       }                                                      │
│     },                                                       │
│     "finops-dev": {                                          │
│       "command": "python",                                   │
│       "args": ["mcp_bridge.py"],                             │
│       "env": {                                               │
│         "MCP_SERVER_URL": "http://mcp-dev.acme.com:8080"    │
│       }                                                      │
│     }                                                        │
│   }                                                          │
│ }                                                            │
└─────────────────────────────────────────────────────────────┘
```

### Deployment Steps

**For each AWS account:**

1. **Deploy MCP Server**:
```bash
# Switch to target account
export AWS_PROFILE=acme-production

# Deploy using CloudFormation
aws cloudformation create-stack \
  --stack-name finops-mcp-server \
  --template-body file://infrastructure/cloudformation.yaml \
  --parameters ParameterKey=InstanceType,ParameterValue=t3.medium \
  --capabilities CAPABILITY_IAM

# Get instance public DNS
aws cloudformation describe-stacks \
  --stack-name finops-mcp-server \
  --query 'Stacks[0].Outputs[?OutputKey==`InstancePublicDNS`].OutputValue' \
  --output text
```

2. **Configure DNS (optional but recommended)**:
```bash
# Create Route53 record pointing to each instance
# mcp-prod.acme.com → Production instance IP
# mcp-staging.acme.com → Staging instance IP
# etc.
```

3. **Update Client Configuration**:
```json
// claude_desktop_config.json
{
  "mcpServers": {
    "finops-prod": {
      "command": "python",
      "args": ["C:\\tools\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://mcp-prod.acme.com:8080"
      }
    },
    "finops-staging": {
      "command": "python",
      "args": ["C:\\tools\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://mcp-staging.acme.com:8080"
      }
    }
    // ... add entry for each account
  }
}
```

4. **Using Multiple MCPs in Claude**:
```
User: "Check tagging compliance in production"
Claude uses: finops-prod MCP

User: "Check staging environment"
Claude uses: finops-staging MCP

User: "Compare compliance between prod and staging"
Claude uses: both finops-prod and finops-staging MCPs
```

### Pros & Cons

**Advantages**:
- ✅ Works today (Phase 1)
- ✅ Perfect isolation between accounts
- ✅ No code changes needed
- ✅ Simple to understand and deploy
- ✅ Independent scaling per account

**Disadvantages**:
- ❌ High cost: N accounts × €40/month (5 accounts = €200/month)
- ❌ Complex maintenance: N instances to update/monitor
- ❌ No aggregated reporting across accounts
- ❌ Manual work to compare compliance across accounts
- ❌ Redundant infrastructure

### Cost Analysis

| Accounts | Monthly Cost | Annual Cost | Break-even vs Option 2 |
|----------|-------------|-------------|------------------------|
| 2 | €80 | €960 | Never (always more expensive) |
| 5 | €200 | €2,400 | Never |
| 10 | €400 | €4,800 | Never |
| 20 | €800 | €9,600 | Never |

**Recommendation**: Use Option 1 only for Phase 1 testing or if you have <3 accounts.

---

## Option 2: AssumeRole Cross-Account (Phase 2 - Q2 2025)

### Overview

Single MCP server deployment in a central account. Server assumes IAM roles in other accounts to scan resources.

This is the **recommended approach** for enterprise deployments (5-50 accounts).

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Management Account (111111111111)                            │
│                                                              │
│   ┌──────────────────────────────────────────┐             │
│   │ EC2 Instance: mcp.acme.com               │             │
│   │ MCP Server (Multi-Account Enabled)       │             │
│   │                                          │             │
│   │ IAM Role: MCPServerRole                  │             │
│   │ - sts:AssumeRole permission              │             │
│   └──────────────────────────────────────────┘             │
└────────────────────┬─────────────────────────────────────────┘
                     │
           ┌─────────┴─────────┐
           │    AssumeRole     │
           │   (sts:AssumeRole)│
           └─────────┬─────────┘
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ Account 1   │ │ Account 2   │ │ Account 3   │
│ Production  │ │ Staging     │ │ Development │
│             │ │             │ │             │
│ IAM Role:   │ │ IAM Role:   │ │ IAM Role:   │
│ CrossAccount│ │ CrossAccount│ │ CrossAccount│
│ TagAuditRole│ │ TagAuditRole│ │ TagAuditRole│
│             │ │             │ │             │
│ Trust: Mgmt │ │ Trust: Mgmt │ │ Trust: Mgmt │
│ Account     │ │ Account     │ │ Account     │
└─────────────┘ └─────────────┘ └─────────────┘
```

### Implementation (Phase 2)

**New code in `aws_client.py`**:

```python
class MultiAccountAWSClient:
    """
    AWS client that can scan multiple accounts via AssumeRole.

    Requires:
    - accounts: List of AWS account IDs to scan
    - cross_account_role_name: IAM role name in each account (default: CrossAccountTagAuditRole)
    - external_id: Optional external ID for enhanced security
    """

    def __init__(
        self,
        accounts: List[str],
        region: str = "us-east-1",
        cross_account_role_name: str = "CrossAccountTagAuditRole",
        external_id: Optional[str] = None
    ):
        self.accounts = accounts
        self.region = region
        self.cross_account_role_name = cross_account_role_name
        self.external_id = external_id
        self.sts = boto3.client('sts')

        # Cache assumed role sessions (1 hour TTL)
        self._session_cache: Dict[str, Tuple[boto3.Session, datetime]] = {}

    async def assume_role(self, account_id: str) -> boto3.Session:
        """
        Assume role in target account.

        Args:
            account_id: Target AWS account ID

        Returns:
            boto3.Session with temporary credentials

        Raises:
            AWSAPIError: If role assumption fails
        """
        # Check cache first
        if account_id in self._session_cache:
            session, expires = self._session_cache[account_id]
            if datetime.utcnow() < expires - timedelta(minutes=5):  # 5 min buffer
                return session

        # Assume role
        role_arn = f"arn:aws:iam::{account_id}:role/{self.cross_account_role_name}"

        assume_role_params = {
            'RoleArn': role_arn,
            'RoleSessionName': f'mcp-server-{account_id}',
            'DurationSeconds': 3600  # 1 hour
        }

        if self.external_id:
            assume_role_params['ExternalId'] = self.external_id

        try:
            response = await self._call_with_backoff(
                'sts',
                self.sts.assume_role,
                **assume_role_params
            )
        except AWSAPIError as e:
            raise AWSAPIError(
                f"Failed to assume role in account {account_id}. "
                f"Ensure CrossAccountTagAuditRole exists and trusts management account. "
                f"Error: {str(e)}"
            ) from e

        credentials = response['Credentials']

        session = boto3.Session(
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name=self.region
        )

        # Cache session
        expires = datetime.fromisoformat(credentials['Expiration'].replace('Z', '+00:00'))
        self._session_cache[account_id] = (session, expires)

        return session

    async def scan_all_accounts(
        self,
        resource_types: List[str],
        regions: Optional[List[str]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Scan resources across all configured accounts.

        Args:
            resource_types: List of resource types to scan
            regions: Optional list of regions (defaults to all)

        Returns:
            Dict mapping account_id -> list of resources
        """
        results = {}

        for account_id in self.accounts:
            try:
                session = await self.assume_role(account_id)

                # Create clients for this account
                ec2 = session.client('ec2', region_name=self.region)
                rds = session.client('rds', region_name=self.region)
                s3 = session.client('s3', region_name=self.region)
                # ... other clients

                # Scan resources in this account
                account_resources = await self._scan_account(
                    ec2, rds, s3,
                    resource_types=resource_types,
                    regions=regions
                )

                results[account_id] = account_resources

            except AWSAPIError as e:
                # Log error but continue with other accounts
                logger.error(f"Failed to scan account {account_id}: {e}")
                results[account_id] = {
                    'error': str(e),
                    'resources': []
                }

        return results
```

**New MCP tool parameter**:

```python
# Updated tool signature
async def check_tag_compliance(
    resource_types: Optional[List[str]] = None,
    regions: Optional[List[str]] = None,
    accounts: Optional[List[str]] = None  # NEW: Multi-account support
) -> Dict:
    """
    Check tag compliance across resources.

    Args:
        resource_types: Resource types to check (e.g., ["ec2:instance", "rds:db"])
        regions: AWS regions to scan (defaults to all)
        accounts: AWS account IDs to scan (defaults to current account)

    Returns:
        Compliance report with violations per account
    """
    if accounts is None:
        # Single account mode (Phase 1 behavior)
        return await _check_compliance_single_account(resource_types, regions)
    else:
        # Multi-account mode (Phase 2)
        return await _check_compliance_multi_account(accounts, resource_types, regions)
```

### IAM Setup

**Step 1: Create role in Management Account**

This is the MCP server's IAM role (already exists from Phase 1, just add AssumeRole permission).

```json
// Add to MCPServerRole policy
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeRoleInMemberAccounts",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::*:role/CrossAccountTagAuditRole"
    }
  ]
}
```

**Step 2: Create role in each member account**

Deploy this IAM role in **every account** you want to scan:

```json
// CrossAccountTagAuditRole - Trust Policy
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111111111111:role/MCPServerRole"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "finops-mcp-cross-account-v1"
        }
      }
    }
  ]
}
```

```json
// CrossAccountTagAuditRole - Permissions Policy
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TagComplianceReadAccess",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeTags",
        "ec2:DescribeVolumes",
        "ec2:DescribeRegions",
        "rds:DescribeDBInstances",
        "rds:DescribeDBClusters",
        "rds:ListTagsForResource",
        "s3:ListAllMyBuckets",
        "s3:GetBucketTagging",
        "s3:GetBucketLocation",
        "lambda:ListFunctions",
        "lambda:ListTags",
        "ecs:ListClusters",
        "ecs:ListServices",
        "ecs:DescribeServices",
        "ecs:ListTagsForResource",
        "ce:GetCostAndUsage",
        "ce:GetCostForecast",
        "ce:GetTags",
        "tag:GetResources",
        "tag:GetTagKeys",
        "tag:GetTagValues",
        "opensearch:ListDomainNames",
        "opensearch:DescribeDomain",
        "opensearch:ListTags"
      ],
      "Resource": "*"
    }
  ]
}
```

**Step 3: Automated deployment with CloudFormation StackSets**

For organizations with many accounts, use CloudFormation StackSets to deploy the CrossAccountTagAuditRole automatically:

```bash
# Create StackSet in management account
aws cloudformation create-stack-set \
  --stack-set-name CrossAccountTagAuditRole \
  --template-body file://infrastructure/cross-account-role.yaml \
  --parameters ParameterKey=ManagementAccountId,ParameterValue=111111111111 \
  --capabilities CAPABILITY_NAMED_IAM

# Deploy to all accounts in organization
aws cloudformation create-stack-instances \
  --stack-set-name CrossAccountTagAuditRole \
  --deployment-targets OrganizationalUnitIds=ou-xxxx-yyyyyyyy \
  --regions us-east-1
```

### Configuration

**Environment variables**:

```bash
# .env file for MCP server
MULTI_ACCOUNT_ENABLED=true
AWS_ACCOUNTS=123456789012,234567890123,345678901234,456789012345
CROSS_ACCOUNT_ROLE_NAME=CrossAccountTagAuditRole
CROSS_ACCOUNT_EXTERNAL_ID=finops-mcp-cross-account-v1
```

**Usage in Claude**:

```
User: "Check tag compliance across all accounts"
→ MCP scans accounts: 123456789012, 234567890123, 345678901234, 456789012345

User: "Check compliance in production account only"
→ MCP scans account: 123456789012

User: "Compare compliance between prod and staging"
→ MCP scans accounts: 123456789012, 234567890123
→ Returns side-by-side comparison
```

### Pros & Cons

**Advantages**:
- ✅ Single MCP instance (€40/month regardless of account count)
- ✅ Centralized management and updates
- ✅ Aggregated reporting across accounts
- ✅ Native comparison between accounts
- ✅ Standard AWS practice (Organizations + AssumeRole)
- ✅ Easy to add/remove accounts (just update env var)

**Disadvantages**:
- ❌ Requires Phase 2 (2-3 weeks development)
- ❌ More complex IAM setup (trust relationships)
- ❌ Single point of failure (mitigated by Phase 2 HA)
- ❌ Requires management account access

### Cost Analysis

| Accounts | Monthly Cost | Annual Cost | Savings vs Option 1 |
|----------|-------------|-------------|---------------------|
| 2 | €40 | €480 | €480 (50%) |
| 5 | €40 | €480 | €1,920 (80%) |
| 10 | €40 | €480 | €4,320 (90%) |
| 20 | €40 | €480 | €9,120 (95%) |

**Recommendation**: Use Option 2 for any enterprise with 3+ accounts. ROI is immediate.

---

## Option 3: AWS Organizations API (Phase 2+ - Q3 2025)

### Overview

Automatic discovery of all accounts in AWS Organization. No need to manually configure account list.

### Architecture

Same as Option 2, but with automatic account discovery:

```python
# Automatic discovery
org = boto3.client('organizations')
response = org.list_accounts()

accounts = [
    acc['Id']
    for acc in response['Accounts']
    if acc['Status'] == 'ACTIVE'
]

# Then assume role in each account (same as Option 2)
```

### Additional Requirements

**Management account permissions**:
```json
{
  "Sid": "ListOrganizationAccounts",
  "Effect": "Allow",
  "Action": [
    "organizations:ListAccounts",
    "organizations:DescribeAccount",
    "organizations:DescribeOrganization"
  ],
  "Resource": "*"
}
```

### Pros & Cons

**Advantages**:
- ✅ All benefits of Option 2
- ✅ Zero configuration (auto-discovers accounts)
- ✅ Automatically includes new accounts
- ✅ Automatically excludes closed accounts

**Disadvantages**:
- ❌ Requires Phase 2+ (Q3 2025)
- ❌ Requires AWS Organizations access
- ❌ Scans ALL accounts (may not want this)
- ❌ More complex error handling

**Recommendation**: Use Option 3 only for very large organizations (50+ accounts) where manual configuration is impractical.

---

## Comparison Matrix

| Feature | Option 1 | Option 2 | Option 3 |
|---------|----------|----------|----------|
| **Availability** | Now | Q2 2025 | Q3 2025 |
| **Accounts Supported** | Unlimited | Unlimited | Unlimited |
| **Monthly Cost (10 accounts)** | €400 | €40 | €40 |
| **Setup Complexity** | Low | Medium | High |
| **IAM Complexity** | Low | Medium | High |
| **Maintenance** | High | Low | Very Low |
| **Aggregated Reporting** | Manual | Yes | Yes |
| **Account Auto-Discovery** | No | No | Yes |
| **Single Point of Failure** | No | Yes* | Yes* |
| **Best For** | Testing, <3 accounts | Production, 3-50 accounts | Large orgs, 50+ accounts |

\* Mitigated by Phase 2 high availability (ECS Fargate multi-AZ)

---

## Migration Path

### Phase 1 → Phase 2 Migration

If you started with Option 1 (multiple deployments) and want to migrate to Option 2:

**Step 1: Deploy central MCP server in management account**

```bash
# Deploy in management account
aws cloudformation create-stack \
  --stack-name finops-mcp-server-central \
  --template-body file://infrastructure/cloudformation.yaml \
  --parameters ParameterKey=MultiAccountEnabled,ParameterValue=true
```

**Step 2: Create CrossAccountTagAuditRole in each account**

Use CloudFormation StackSets (see Option 2 setup).

**Step 3: Test multi-account scanning**

```bash
# Test with central server
curl http://mcp-central.acme.com:8080/tools/check_tag_compliance \
  -d '{"accounts": ["123456789012", "234567890123"]}'
```

**Step 4: Update Claude Desktop config**

Remove individual account entries, keep only central:

```json
{
  "mcpServers": {
    "finops-central": {
      "command": "python",
      "args": ["C:\\tools\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://mcp-central.acme.com:8080"
      }
    }
  }
}
```

**Step 5: Decommission individual servers**

```bash
# Delete stacks in each account
for account in prod staging dev; do
  aws cloudformation delete-stack \
    --stack-name finops-mcp-server \
    --profile acme-$account
done
```

**Total migration time**: 1-2 hours
**Downtime**: None (run both during migration)

---

## Recommendations by Organization Size

| Organization Size | Accounts | Recommended Option | Rationale |
|-------------------|----------|--------------------|-----------|
| **Startup** | 1-2 | Option 1 | Simple, low cost (€40-80/month) |
| **Scale-up** | 3-10 | Option 2 (Q2 2025) | Cost effective (€40/month), enterprise-ready |
| **Mid-Market** | 10-50 | Option 2 (Q2 2025) | Best ROI, standard AWS practice |
| **Enterprise** | 50-200 | Option 3 (Q3 2025) | Auto-discovery, zero config |
| **Large Enterprise** | 200+ | Option 3 (Q3 2025) | Only practical option at this scale |

---

## FAQ

**Q: Can I mix options?**
A: Yes. You could use Option 2 for production accounts and Option 1 for isolated sandbox accounts.

**Q: What if I don't have access to the management account?**
A: You can deploy Option 2 from any account. Just ensure that account's role can assume roles in other accounts.

**Q: How do I handle accounts in different regions?**
A: The MCP server region is independent. AssumeRole works across all regions.

**Q: What about accounts in different organizations?**
A: Option 2 works across organizations. Just configure trust relationships appropriately.

**Q: Can I exclude specific accounts?**
A: Yes (Option 2/3). Use blacklist in configuration: `AWS_ACCOUNTS_EXCLUDE=123456789012,234567890123`

**Q: How do I handle account names vs IDs?**
A: Phase 2 will include an account alias resolver. For now, use account IDs only.

---

## Implementation Timeline

| Phase | Feature | Timeline | Status |
|-------|---------|----------|--------|
| Phase 1 | Option 1 only | Now | ✅ Available |
| Phase 2 | Option 2 (AssumeRole) | Q2 2025 (Months 3-4) | 📋 Planned |
| Phase 2+ | Option 3 (Organizations API) | Q3 2025 (Months 5-6) | 📋 Planned |

---

## Getting Help

**For Option 1 (available now)**:
- See deployment guide: `docs/DEPLOYMENT.md`
- CloudFormation template: `infrastructure/cloudformation.yaml`

**For Option 2/3 (Phase 2)**:
- Development timeline: See `docs/ROADMAP.md`
- Phase 2 spec: See `docs/PHASE-2-SPECIFICATION.md`
- Contact: jean@optimnow.io

---

**Document Version**: 1.0
**Author**: OptimNow
**Date**: January 9, 2025
**Next Update**: After Phase 2 implementation (Q2 2025)
