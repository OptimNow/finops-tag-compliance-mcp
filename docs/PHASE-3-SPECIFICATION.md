# Phase 3 Specification: Multi-Cloud Support (AWS + Azure + GCP)

**Version**: 1.0
**Timeline**: Months 5-6 (8 weeks)
**Status**: Ready for Development (after Phase 2 completion)
**Prerequisites**: Phase 2 successfully deployed with stable production traffic

---

## Overview

Phase 3 extends the proven AWS-only MCP server to support Azure and Google Cloud Platform, creating a unified multi-cloud tag governance solution. The infrastructure remains the same (ECS Fargate), but the application gains multi-cloud SDKs and cross-cloud intelligence.

**Key Additions in Phase 3**:
- ✅ Azure SDK integration (azure-mgmt-* packages)
- ✅ GCP SDK integration (google-cloud-* libraries)
- ✅ Unified tagging policy schema (cloud-agnostic + cloud-specific)
- ✅ Cross-cloud tag consistency checking
- ✅ Multi-cloud credential management (Azure Key Vault, GCP Secret Manager integration)
- ✅ Cloud-agnostic compliance reporting
- ✅ Cross-cloud cost attribution gap analysis

**What Stays the Same**:
- Same 15 tools, now with `cloud_provider` parameter
- Same ECS Fargate infrastructure
- Same OAuth 2.0 authentication
- Same approval workflows

---

## Architecture

### Multi-Cloud Architecture Diagram

```
                        ┌──────────────────────────┐
                        │   Route 53 (DNS)         │
                        │   mcp.tagging.company.com│
                        └────────────┬─────────────┘
                                     │
                                     ▼
                        ┌──────────────────────────┐
                        │ Application Load Balancer│
                        │  - SSL/TLS termination   │
                        └────────────┬─────────────┘
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
         ┌─────────────────────┐        ┌─────────────────────┐
         │ ECS Fargate Task 1  │        │ ECS Fargate Task 2  │
         │  ┌───────────────┐  │        │  ┌───────────────┐  │
         │  │ MCP Server    │  │        │  │ MCP Server    │  │
         │  │ ┌───────────┐ │  │        │  │ ┌───────────┐ │  │
         │  │ │AWS SDK    │ │  │        │  │ │AWS SDK    │ │  │
         │  │ │Azure SDK  │ │  │        │  │ │Azure SDK  │ │  │
         │  │ │GCP SDK    │ │  │        │  │ │GCP SDK    │ │  │
         │  │ └───────────┘ │  │        │  │ └───────────┘ │  │
         │  └───────────────┘  │        │  └───────────────┘  │
         └──────────┬──────────┘        └──────────┬──────────┘
                    │                              │
                    └──────────────┬───────────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            ▼                      ▼                      ▼
    ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
    │ ElastiCache     │  │ RDS PostgreSQL   │  │ Secrets Manager  │
    │ (Redis)         │  │ (Multi-AZ)       │  │ - AWS creds      │
    │ - Multi-cloud   │  │ - Multi-cloud    │  │ - Azure creds    │
    │   violation     │  │   audit logs     │  │ - GCP creds      │
    │   cache         │  │                  │  └──────────────────┘
    └─────────────────┘  └──────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
    ┌──────────┐            ┌────────────┐          ┌──────────────┐
    │   AWS    │            │   Azure    │          │     GCP      │
    │ - EC2    │            │ - VMs      │          │ - Compute    │
    │ - RDS    │            │ - SQL DB   │          │ - Cloud SQL  │
    │ - S3     │            │ - Storage  │          │ - Storage    │
    │ - Lambda │            │ - Functions│          │ - Functions  │
    └──────────┘            └────────────┘          └──────────────┘
```

### Container Updates

```dockerfile
# Dockerfile - Phase 3 additions
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements (now includes Azure + GCP SDKs)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY mcp_server/ ./mcp_server/
COPY policies/ ./policies/

# Create directory for SQLite database
RUN mkdir -p /app/data

# Expose MCP server port
EXPOSE 8080

# Run MCP server
CMD ["python", "-m", "mcp_server"]
```

### Updated requirements.txt

```txt
# MCP SDK
mcp-server==1.0.0

# Web framework
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0

# AWS SDK
boto3==1.34.0
botocore==1.34.0

# Azure SDKs
azure-identity==1.15.0
azure-mgmt-compute==30.5.0
azure-mgmt-resource==23.0.1
azure-mgmt-storage==21.1.0
azure-mgmt-sql==4.0.0
azure-mgmt-costmanagement==4.0.1
azure-mgmt-consumption==10.0.0

# GCP SDKs
google-cloud-compute==1.16.0
google-cloud-storage==2.14.0
google-cloud-resource-manager==1.11.0
google-cloud-billing==1.12.0
google-auth==2.27.0

# Caching
redis==5.0.1
hiredis==2.2.3

# Database
psycopg2-binary==2.9.9
aiosqlite==0.19.0

# Utilities
python-dateutil==2.8.2
pyyaml==6.0.1
```

---

## Updated Tools (All 15 Tools Now Multi-Cloud)

All existing 15 tools from Phases 1 and 2 are updated to accept a `cloud_provider` parameter.

### Tool Signature Pattern

```python
@mcp.tool()
async def check_tag_compliance(
    cloud_provider: str,  # "aws" | "azure" | "gcp" | "all"
    filters: dict,
    severity: str = "all"
):
    """
    Check tag compliance across AWS, Azure, GCP, or all clouds.

    Args:
        cloud_provider: Which cloud(s) to check. Use "all" for unified report.
        filters: Cloud-specific filters
        severity: errors_only | warnings_only | all
    """
    if cloud_provider == "aws":
        return await check_aws_compliance(filters, severity)
    elif cloud_provider == "azure":
        return await check_azure_compliance(filters, severity)
    elif cloud_provider == "gcp":
        return await check_gcp_compliance(filters, severity)
    elif cloud_provider == "all":
        aws, azure, gcp = await asyncio.gather(
            check_aws_compliance(filters, severity),
            check_azure_compliance(filters, severity),
            check_gcp_compliance(filters, severity)
        )
        return merge_cross_cloud_results(aws, azure, gcp)
    else:
        raise ValueError(f"Unsupported cloud_provider: {cloud_provider}")
```

### Example: check_tag_compliance (Multi-Cloud)

**AWS Example**:
```json
{
  "cloud_provider": "aws",
  "filters": {
    "resource_types": ["ec2:instance", "rds:db"],
    "regions": ["us-east-1"]
  },
  "severity": "all"
}
```

**Azure Example**:
```json
{
  "cloud_provider": "azure",
  "filters": {
    "resource_types": ["Microsoft.Compute/virtualMachines", "Microsoft.Sql/servers"],
    "subscription_id": "12345678-1234-1234-1234-123456789012",
    "resource_group": "production"
  },
  "severity": "all"
}
```

**GCP Example**:
```json
{
  "cloud_provider": "gcp",
  "filters": {
    "resource_types": ["compute.instances", "sql.instances"],
    "project_id": "my-project-123",
    "zone": "us-central1-a"
  },
  "severity": "all"
}
```

**All Clouds Example**:
```json
{
  "cloud_provider": "all",
  "filters": {},
  "severity": "all"
}
```

**Response (All Clouds)**:
```json
{
  "overall_compliance": 0.69,
  "clouds": {
    "aws": {
      "compliance_score": 0.72,
      "total_resources": 450,
      "violations": 126,
      "cost_impact": 47230.00
    },
    "azure": {
      "compliance_score": 0.68,
      "total_resources": 320,
      "violations": 102,
      "cost_impact": 28940.00
    },
    "gcp": {
      "compliance_score": 0.65,
      "total_resources": 180,
      "violations": 63,
      "cost_impact": 12330.00
    }
  },
  "total_cost_attribution_gap": 88500.00,
  "cross_cloud_inconsistencies": [
    {
      "issue": "Different Environment tag values",
      "aws_values": ["production", "prod"],
      "azure_values": ["Production", "Prod"],
      "gcp_values": ["prod"],
      "recommendation": "Standardize to 'production' across all clouds"
    }
  ]
}
```

---

## New Phase 3 Tools (Cross-Cloud Intelligence)

### 16. cross_cloud_tag_consistency_check

**Purpose**: Identify tag naming and value inconsistencies across clouds

**Parameters**:
```json
{
  "tag_keys": ["Environment", "CostCenter", "Owner"],
  "check_case_sensitivity": true,
  "check_value_variations": true
}
```

**Returns**:
```json
{
  "inconsistencies": [
    {
      "tag_key": "Environment",
      "issue": "case_inconsistency",
      "aws_values": ["production", "staging"],
      "azure_values": ["Production", "Staging"],
      "gcp_values": ["prod", "stage"],
      "affected_resources": 234,
      "recommendation": "Standardize to lowercase: 'production', 'staging'"
    },
    {
      "tag_key": "CostCenter",
      "issue": "naming_inconsistency",
      "aws_key": "CostCenter",
      "azure_key": "cost-center",
      "gcp_key": "costcenter",
      "recommendation": "Standardize to 'CostCenter' (PascalCase) across clouds"
    }
  ]
}
```

### 17. unified_tagging_policy_validator

**Purpose**: Validate a single tagging policy works across all three clouds

**Parameters**:
```json
{
  "policy": {
    "required_tags": [
      {"name": "Environment", "allowed_values": ["production", "staging"]}
    ]
  }
}
```

**Returns**:
```json
{
  "validation_result": {
    "aws": {
      "compatible": true,
      "warnings": []
    },
    "azure": {
      "compatible": true,
      "warnings": ["Azure tags are case-insensitive, may cause confusion"]
    },
    "gcp": {
      "compatible": true,
      "warnings": ["GCP calls them 'labels', not 'tags'"]
    }
  },
  "recommendations": [
    "Use lowercase tag values for cross-cloud consistency",
    "Document that Azure tags are case-insensitive"
  ]
}
```

---

## Unified Tagging Policy Schema (Multi-Cloud)

```json
{
  "version": "2.0",
  "last_updated": "2024-12-15T10:00:00Z",
  "scope": ["aws", "azure", "gcp"],

  "required_tags": [
    {
      "name": "CostCenter",
      "description": "Department or team for cost allocation",
      "allowed_values": ["Engineering", "Marketing", "Sales", "Operations"],
      "validation_regex": "^[A-Z][a-z]+$",
      "applies_to": {
        "aws": ["ec2:instance", "rds:db", "s3:bucket", "lambda:function"],
        "azure": [
          "Microsoft.Compute/virtualMachines",
          "Microsoft.Sql/servers",
          "Microsoft.Storage/storageAccounts"
        ],
        "gcp": [
          "compute.instances",
          "sql.instances",
          "storage.buckets"
        ]
      },
      "cloud_specific": {
        "azure": {
          "note": "Azure tags are case-insensitive"
        },
        "gcp": {
          "note": "GCP calls these 'labels'"
        }
      }
    },
    {
      "name": "Owner",
      "description": "Email of the resource owner",
      "validation_regex": "^[a-z0-9._%+-]+@[a-z0-9.-]+\\.[a-z]{2,}$",
      "applies_to": {
        "aws": ["ec2:instance", "rds:db", "s3:bucket"],
        "azure": [
          "Microsoft.Compute/virtualMachines",
          "Microsoft.Sql/servers"
        ],
        "gcp": [
          "compute.instances",
          "sql.instances"
        ]
      }
    },
    {
      "name": "Environment",
      "description": "Deployment environment",
      "allowed_values": ["production", "staging", "development", "testing"],
      "applies_to": {
        "aws": ["ec2:instance", "rds:db", "lambda:function"],
        "azure": [
          "Microsoft.Compute/virtualMachines",
          "Microsoft.Sql/servers",
          "Microsoft.Web/sites"
        ],
        "gcp": [
          "compute.instances",
          "sql.instances",
          "cloudfunctions.functions"
        ]
      },
      "enforcement": {
        "case_sensitive": false,
        "normalize_to": "lowercase"
      }
    }
  ],

  "optional_tags": [
    {
      "name": "Project",
      "description": "Project or initiative name"
    }
  ],

  "tag_naming_rules": {
    "case_sensitivity": false,
    "allow_special_characters": false,
    "max_key_length": 128,
    "max_value_length": 256,
    "reserved_prefixes": ["aws:", "azure:", "gcp:"]
  },

  "cross_cloud_mappings": {
    "terminology": {
      "aws": "tags",
      "azure": "tags",
      "gcp": "labels"
    },
    "case_handling": {
      "aws": "case-sensitive",
      "azure": "case-insensitive",
      "gcp": "case-sensitive, lowercase recommended"
    }
  }
}
```

**Policy Location**: `/app/policies/tagging_policy_v2.json`

**Key Changes from Phase 1**:
- `scope` field specifies applicable clouds
- `applies_to` is now cloud-specific with resource type mappings
- `cloud_specific` section for cloud-specific notes/overrides
- `cross_cloud_mappings` for terminology and behavior differences

---

## Credential Management (Multi-Cloud)

### AWS IAM Task Role (Same as Phase 2)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AWSReadAccess",
      "Effect": "Allow",
      "Action": [
        "ec2:Describe*",
        "rds:Describe*",
        "s3:GetBucketTagging",
        "lambda:List*",
        "ce:GetCostAndUsage"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AWSWriteAccess",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateTags",
        "rds:AddTagsToResource",
        "s3:PutBucketTagging"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SecretsAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:tagging-mcp/*"
    }
  ]
}
```

### Azure Service Principal Setup

#### Step 1: Create Azure Service Principal

```bash
# Login to Azure
az login

# Create service principal
az ad sp create-for-rbac \
  --name "tagging-mcp-server" \
  --role "Tag Contributor" \
  --scopes /subscriptions/YOUR_SUBSCRIPTION_ID

# Output:
{
  "appId": "12345678-1234-1234-1234-123456789012",
  "displayName": "tagging-mcp-server",
  "password": "generated-password-here",
  "tenant": "87654321-4321-4321-4321-210987654321"
}
```

#### Step 2: Assign Additional Permissions

```bash
# Grant read access to resources
az role assignment create \
  --assignee 12345678-1234-1234-1234-123456789012 \
  --role "Reader" \
  --scope /subscriptions/YOUR_SUBSCRIPTION_ID

# Grant cost management read access
az role assignment create \
  --assignee 12345678-1234-1234-1234-123456789012 \
  --role "Cost Management Reader" \
  --scope /subscriptions/YOUR_SUBSCRIPTION_ID
```

#### Step 3: Store Azure Credentials in AWS Secrets Manager

```bash
aws secretsmanager create-secret \
  --name tagging-mcp/azure-credentials \
  --description "Azure service principal credentials for tag compliance MCP" \
  --secret-string '{
    "client_id": "12345678-1234-1234-1234-123456789012",
    "client_secret": "generated-password-here",
    "tenant_id": "87654321-4321-4321-4321-210987654321",
    "subscription_id": "YOUR_SUBSCRIPTION_ID"
  }'
```

### GCP Service Account Setup

#### Step 1: Create GCP Service Account

```bash
# Set project
gcloud config set project my-project-123

# Create service account
gcloud iam service-accounts create finops-tag-compliance-mcp \
  --display-name "FinOps Tag Compliance MCP" \
  --description "Service account for tag compliance MCP server"

# Output:
# Created service account [finops-tag-compliance-mcp@my-project-123.iam.gserviceaccount.com]
```

#### Step 2: Grant Permissions

```bash
# Grant compute viewer role
gcloud projects add-iam-policy-binding my-project-123 \
  --member "serviceAccount:finops-tag-compliance-mcp@my-project-123.iam.gserviceaccount.com" \
  --role "roles/compute.viewer"

# Grant storage viewer role
gcloud projects add-iam-policy-binding my-project-123 \
  --member "serviceAccount:finops-tag-compliance-mcp@my-project-123.iam.gserviceaccount.com" \
  --role "roles/storage.admin"

# Grant billing viewer role
gcloud projects add-iam-policy-binding my-project-123 \
  --member "serviceAccount:finops-tag-compliance-mcp@my-project-123.iam.gserviceaccount.com" \
  --role "roles/billing.viewer"

# Grant label editor role (for tagging)
gcloud projects add-iam-policy-binding my-project-123 \
  --member "serviceAccount:finops-tag-compliance-mcp@my-project-123.iam.gserviceaccount.com" \
  --role "roles/resourcemanager.tagUser"
```

#### Step 3: Create and Download Service Account Key

```bash
# Create key
gcloud iam service-accounts keys create gcp-key.json \
  --iam-account finops-tag-compliance-mcp@my-project-123.iam.gserviceaccount.com

# Base64 encode for storage
cat gcp-key.json | base64 > gcp-key-base64.txt
```

#### Step 4: Store GCP Credentials in AWS Secrets Manager

```bash
aws secretsmanager create-secret \
  --name finops/mcp/gcp-credentials \
  --description "GCP service account key for tag compliance MCP" \
  --secret-string file://gcp-key.json

# Delete local key file for security
rm gcp-key.json gcp-key-base64.txt
```

### Loading Multi-Cloud Credentials in Code

```python
# mcp_server/cloud_clients.py
import boto3
import json
from functools import lru_cache
from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient
from google.oauth2 import service_account
from googleapiclient import discovery

secrets_client = boto3.client('secretsmanager')

@lru_cache(maxsize=10)
def get_secret(secret_name: str) -> dict:
    """Retrieve secrets from AWS Secrets Manager"""
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

# AWS client (uses IAM role, no explicit credentials)
def get_aws_ec2_client(region='us-east-1'):
    import boto3
    return boto3.client('ec2', region_name=region)

# Azure client
@lru_cache(maxsize=1)
def get_azure_compute_client():
    """Get Azure Compute client using service principal"""
    creds = get_secret('finops/mcp/azure-credentials')

    credential = ClientSecretCredential(
        tenant_id=creds['tenant_id'],
        client_id=creds['client_id'],
        client_secret=creds['client_secret']
    )

    return ComputeManagementClient(
        credential=credential,
        subscription_id=creds['subscription_id']
    )

# GCP client
@lru_cache(maxsize=1)
def get_gcp_compute_client():
    """Get GCP Compute client using service account"""
    creds_json = get_secret('finops/mcp/gcp-credentials')

    credentials = service_account.Credentials.from_service_account_info(
        creds_json,
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )

    return discovery.build('compute', 'v1', credentials=credentials)

# Example usage
ec2 = get_aws_ec2_client('us-east-1')
azure_compute = get_azure_compute_client()
gcp_compute = get_gcp_compute_client()
```

### Credential Rotation

```python
# mcp_server/credential_rotation.py
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def check_credential_expiry():
    """Check if credentials are expiring soon and alert"""

    # Azure service principal secrets typically expire after 1-2 years
    azure_creds = get_secret('finops/mcp/azure-credentials')
    azure_created = azure_creds.get('created_at')
    if azure_created:
        age_days = (datetime.now() - datetime.fromisoformat(azure_created)).days
        if age_days > 600:  # 20 months
            logger.warning("Azure service principal secret is >20 months old, consider rotating")

    # GCP service account keys should be rotated every 90 days
    gcp_creds = get_secret('finops/mcp/gcp-credentials')
    gcp_created = gcp_creds.get('private_key_id_created_at')
    if gcp_created:
        age_days = (datetime.now() - datetime.fromisoformat(gcp_created)).days
        if age_days > 80:  # 80 days warning
            logger.warning("GCP service account key is >80 days old, rotation recommended at 90 days")
```

**Rotation Schedule**:
- **AWS IAM Role**: Auto-rotated by AWS, no action needed
- **Azure Service Principal**: Rotate every 12-24 months
- **GCP Service Account Key**: Rotate every 90 days (recommended)

---

## Cloud-Specific Implementation Details

### AWS Implementation (boto3)

```python
# mcp_server/aws/compliance.py
import boto3

async def check_aws_compliance(filters: dict, severity: str):
    """Check AWS tag compliance"""
    ec2 = boto3.client('ec2', region_name=filters.get('region', 'us-east-1'))

    # Get all EC2 instances
    response = ec2.describe_instances()

    violations = []
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_violations = validate_resource_tags(
                resource_id=instance['InstanceId'],
                tags=instance.get('Tags', []),
                policy=get_tagging_policy()
            )
            violations.extend(instance_violations)

    return {
        'cloud': 'aws',
        'compliance_score': calculate_compliance_score(violations),
        'violations': violations
    }
```

### Azure Implementation (azure-mgmt)

```python
# mcp_server/azure/compliance.py
from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient

async def check_azure_compliance(filters: dict, severity: str):
    """Check Azure tag compliance"""
    azure_creds = get_secret('finops/mcp/azure-credentials')

    credential = ClientSecretCredential(
        tenant_id=azure_creds['tenant_id'],
        client_id=azure_creds['client_id'],
        client_secret=azure_creds['client_secret']
    )

    compute_client = ComputeManagementClient(
        credential=credential,
        subscription_id=azure_creds['subscription_id']
    )

    # Get all VMs
    vms = compute_client.virtual_machines.list_all()

    violations = []
    for vm in vms:
        vm_violations = validate_resource_tags(
            resource_id=vm.id,
            tags=vm.tags or {},
            policy=get_tagging_policy()
        )
        violations.extend(vm_violations)

    return {
        'cloud': 'azure',
        'compliance_score': calculate_compliance_score(violations),
        'violations': violations
    }
```

### GCP Implementation (google-cloud)

```python
# mcp_server/gcp/compliance.py
from google.oauth2 import service_account
from googleapiclient import discovery

async def check_gcp_compliance(filters: dict, severity: str):
    """Check GCP tag compliance (labels)"""
    gcp_creds = get_secret('finops/mcp/gcp-credentials')

    credentials = service_account.Credentials.from_service_account_info(
        gcp_creds,
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )

    compute = discovery.build('compute', 'v1', credentials=credentials)

    project = filters.get('project_id', gcp_creds.get('project_id'))

    # Get all instances across all zones
    result = compute.instances().aggregatedList(project=project).execute()

    violations = []
    for zone, instances_scoped_list in result['items'].items():
        if 'instances' in instances_scoped_list:
            for instance in instances_scoped_list['instances']:
                instance_violations = validate_resource_tags(
                    resource_id=instance['name'],
                    tags=instance.get('labels', {}),
                    policy=get_tagging_policy()
                )
                violations.extend(instance_violations)

    return {
        'cloud': 'gcp',
        'compliance_score': calculate_compliance_score(violations),
        'violations': violations
    }
```

---

## Resource Type Mappings (Cross-Cloud)

```python
# mcp_server/resource_mappings.py

RESOURCE_TYPE_MAPPINGS = {
    'virtual_machine': {
        'aws': 'ec2:instance',
        'azure': 'Microsoft.Compute/virtualMachines',
        'gcp': 'compute.instances'
    },
    'database': {
        'aws': 'rds:db',
        'azure': 'Microsoft.Sql/servers',
        'gcp': 'sql.instances'
    },
    'storage': {
        'aws': 's3:bucket',
        'azure': 'Microsoft.Storage/storageAccounts',
        'gcp': 'storage.buckets'
    },
    'function': {
        'aws': 'lambda:function',
        'azure': 'Microsoft.Web/sites',  # Azure Functions
        'gcp': 'cloudfunctions.functions'
    },
    'container': {
        'aws': 'ecs:service',
        'azure': 'Microsoft.ContainerInstance/containerGroups',
        'gcp': 'run.services'
    }
}

def get_cloud_resource_type(generic_type: str, cloud: str) -> str:
    """Convert generic resource type to cloud-specific type"""
    return RESOURCE_TYPE_MAPPINGS.get(generic_type, {}).get(cloud)

# Example usage
aws_type = get_cloud_resource_type('virtual_machine', 'aws')  # 'ec2:instance'
azure_type = get_cloud_resource_type('virtual_machine', 'azure')  # 'Microsoft.Compute/virtualMachines'
gcp_type = get_cloud_resource_type('virtual_machine', 'gcp')  # 'compute.instances'
```

---

## Testing Strategy (Multi-Cloud)

### Unit Tests

```python
# tests/test_multi_cloud_compliance.py
import pytest
from mcp_server.tools import check_tag_compliance

@pytest.mark.parametrize("cloud_provider", ["aws", "azure", "gcp"])
async def test_compliance_check_all_clouds(cloud_provider):
    """Test compliance checking works for all clouds"""
    result = await check_tag_compliance(
        cloud_provider=cloud_provider,
        filters={},
        severity="all"
    )

    assert result['cloud'] == cloud_provider
    assert 'compliance_score' in result
    assert 0 <= result['compliance_score'] <= 1.0

async def test_cross_cloud_compliance():
    """Test unified compliance check across all clouds"""
    result = await check_tag_compliance(
        cloud_provider="all",
        filters={},
        severity="all"
    )

    assert 'clouds' in result
    assert 'aws' in result['clouds']
    assert 'azure' in result['clouds']
    assert 'gcp' in result['clouds']
    assert 'cross_cloud_inconsistencies' in result
```

### Integration Tests (Requires Real Cloud Accounts)

```python
# tests/integration/test_real_multi_cloud.py
import pytest

@pytest.mark.integration
@pytest.mark.aws
async def test_real_aws_compliance():
    """Test against real AWS account"""
    result = await check_tag_compliance(
        cloud_provider="aws",
        filters={"region": "us-east-1"},
        severity="all"
    )
    assert result['total_resources'] >= 0

@pytest.mark.integration
@pytest.mark.azure
async def test_real_azure_compliance():
    """Test against real Azure subscription"""
    result = await check_tag_compliance(
        cloud_provider="azure",
        filters={"subscription_id": "test-sub-id"},
        severity="all"
    )
    assert result['total_resources'] >= 0

@pytest.mark.integration
@pytest.mark.gcp
async def test_real_gcp_compliance():
    """Test against real GCP project"""
    result = await check_tag_compliance(
        cloud_provider="gcp",
        filters={"project_id": "test-project"},
        severity="all"
    )
    assert result['total_resources'] >= 0
```

---

## Cost Estimate (Phase 3)

| Component | Monthly Cost | Notes |
|-----------|--------------|-------|
| **Compute** | | |
| ECS Fargate (2 tasks, 2 vCPU, 4GB each) | $75 | Same as Phase 2 |
| **Database** | | |
| RDS db.t4g.micro (Multi-AZ) | $30 | Same as Phase 2 |
| RDS storage 20GB | $5 | Same as Phase 2 |
| **Caching** | | |
| ElastiCache cache.t4g.micro | $15 | Same as Phase 2 |
| **Networking** | | |
| Application Load Balancer | $20 | Same as Phase 2 |
| Data transfer (increased for multi-cloud) | $15 | +$5 for cross-cloud API calls |
| **Secrets & Logs** | | |
| Secrets Manager (8 secrets) | $3 | +$1 for Azure/GCP creds |
| CloudWatch Logs (15GB) | $7 | +$2 for increased logging |
| CloudWatch Alarms (12 alarms) | $1 | Same as Phase 2 |
| **Azure Costs** | | |
| Azure API calls | $5 | Pay-per-call pricing |
| **GCP Costs** | | |
| GCP API calls | $5 | Pay-per-call pricing |
| **Total** | **~$181/month** | |

**Annual**: ~$2,172

**Cost increase from Phase 2**: +$18/month (+11%)
**Cost increase from Phase 1**: +$141/month (+353%)

**Value**: Unified multi-cloud tag governance, cross-cloud consistency, single pane of glass

---

## Migration from Phase 2 to Phase 3

### Migration Steps

1. **Week 1**: Add Azure support
   - Deploy updated container with Azure SDKs
   - Store Azure credentials in Secrets Manager
   - Test Azure tools with staging subscription
   - Validate Azure compliance checks

2. **Week 2**: Add GCP support
   - Add GCP SDKs to container
   - Store GCP credentials in Secrets Manager
   - Test GCP tools with staging project
   - Validate GCP compliance checks

3. **Week 3**: Cross-cloud features
   - Implement `cloud_provider="all"` functionality
   - Add cross-cloud consistency checking
   - Test unified compliance reports
   - Validate cross-cloud cost attribution

4. **Week 4**: Production rollout
   - Update tagging policy to v2.0 (multi-cloud)
   - Train users on multi-cloud features
   - Monitor for issues
   - Gather feedback

### Backward Compatibility

**Phase 2 API calls continue to work**:
```python
# This Phase 2 call (no cloud_provider parameter)
check_tag_compliance(filters={"region": "us-east-1"})

# Is equivalent to this Phase 3 call
check_tag_compliance(cloud_provider="aws", filters={"region": "us-east-1"})
```

**Migration Strategy**: Default `cloud_provider="aws"` if not specified, allowing gradual migration.

---

## Success Criteria for Phase 3

### Functional Requirements

✅ All 15 tools working for AWS, Azure, and GCP
✅ Cross-cloud consistency checking functional
✅ Unified compliance reports accurate
✅ Multi-cloud credential management working
✅ All clouds have feature parity

### Non-Functional Requirements

✅ 99.9% uptime maintained
✅ <1.5 second response time for multi-cloud queries
✅ Azure/GCP API calls properly cached
✅ No credential leaks or security incidents
✅ Successful blue/green deployment

### Business Requirements

✅ 50+ active users across multi-cloud teams
✅ 500+ compliance audits per month across all clouds
✅ At least 20% of audits use `cloud_provider="all"`
✅ Measurable cross-cloud consistency improvement
✅ User satisfaction NPS > 60

---

## Known Limitations (Phase 3)

⚠️ **Different tag/label semantics** across clouds (accepted tradeoff)
  - AWS: case-sensitive tags
  - Azure: case-insensitive tags
  - GCP: lowercase labels only

⚠️ **Resource type mappings not exhaustive** - Only covers top 10 resource types per cloud

⚠️ **API rate limits** vary by cloud - caching strategy must adapt

⚠️ **Cost data granularity** differs:
  - AWS: Cost Explorer (hourly granularity)
  - Azure: Cost Management API (daily granularity)
  - GCP: BigQuery billing export (daily granularity)

**These are documented and communicated to users.**

---

## Deliverables Checklist

### Code

- [ ] Azure SDK integration (azure-mgmt-* packages)
- [ ] GCP SDK integration (google-cloud-* packages)
- [ ] All 15 tools updated with `cloud_provider` parameter
- [ ] Cross-cloud consistency checking implemented
- [ ] Unified tagging policy v2.0 schema
- [ ] Resource type mapping table
- [ ] Unit tests for multi-cloud (>80% coverage)
- [ ] Integration tests (AWS + Azure + GCP)

### Infrastructure

- [ ] Azure service principal created and permissions granted
- [ ] GCP service account created and permissions granted
- [ ] Azure credentials stored in AWS Secrets Manager
- [ ] GCP credentials stored in AWS Secrets Manager
- [ ] Updated ECS task definition with new SDKs
- [ ] Credential rotation monitoring enabled

### Documentation

- [ ] Multi-cloud API documentation
- [ ] Azure credential setup guide
- [ ] GCP credential setup guide
- [ ] Cross-cloud consistency guide
- [ ] Unified tagging policy migration guide
- [ ] User guide for multi-cloud features

### Testing

- [ ] Unit tests passing for all clouds
- [ ] Integration tests passing (AWS + Azure + GCP)
- [ ] Cross-cloud consistency tests passing
- [ ] Load testing completed (multi-cloud queries)
- [ ] 10+ beta users testing multi-cloud features

---

## Next Steps After Phase 3

1. **Advanced ML features** - Better tag suggestions using multi-cloud patterns
2. **Policy-as-code** - GitOps workflow for tagging policy updates
3. **Multi-tenancy** - Support multiple organizations in single deployment
4. **Custom integrations** - Webhooks, Slack/Teams notifications
5. **Advanced analytics** - Trend analysis, forecasting, anomaly detection

---

**Document Version**: 1.0
**Last Updated**: December 2024
**Ready for Development**: After Phase 2 completion
**Assigned to**: Kiro (post-Phase 2)
