# Resource Type Configuration

This document explains how AWS resource types are categorized and configured for compliance scanning and cost attribution.

## Overview

AWS has hundreds of resource types, but not all are relevant for FinOps tag compliance:

- Some resources generate direct costs (EC2 instances, RDS databases)
- Some resources are taggable but free (VPCs, Security Groups)
- Some services have costs but no taggable resources (Bedrock API usage, Tax)

This configuration allows you to control which resources are scanned and how costs are attributed.

## Configuration File

The configuration is stored in `config/resource_types.json` and loaded at server startup.

### Environment Variable Override

```bash
export RESOURCE_TYPES_CONFIG_PATH=/custom/path/resource_types.json
```

## Resource Categories

### 1. Cost-Generating Resources

Resources that generate direct AWS costs. These are:
- Scanned for tag compliance
- Included in cost attribution gap calculation

**Examples:**
| Resource Type | Typical Cost |
|--------------|--------------|
| `ec2:instance` | $10-500+/month |
| `rds:db` | $15-1000+/month |
| `s3:bucket` | $0.023/GB/month |
| `ec2:natgateway` | ~$32/month + data |
| `ec2:elastic-ip` | $3.65/month (unattached) |

### 2. Free Resources

Resources that are taggable but have no direct cost. These are:
- Excluded from compliance scans by default
- Their costs come from usage (messages, queries, data transfer)

**Examples:**
| Resource Type | Why Free |
|--------------|----------|
| `ec2:vpc` | VPC itself is free; costs come from NAT Gateway, VPN |
| `ec2:subnet` | Free; just a logical grouping |
| `ec2:security-group` | Free; just firewall rules |
| `sns:topic` | Free; costs are per message sent |
| `sqs:queue` | Free; costs are per message |
| `logs:log-group` | Free; costs are on ingestion/storage |
| `cloudwatch:alarm` | Nearly free ($0.10/alarm after first 10) |

### 3. Unattributable Services

Services that have costs but NO taggable resources. These are:
- Excluded from attribution gap calculation
- Reported separately for transparency

**Examples:**
| Service Name | Why Unattributable |
|-------------|-------------------|
| `Claude 3.5 Sonnet (Amazon Bedrock Edition)` | API usage, no resource to tag |
| `Tax` | AWS fees, not a resource |
| `AWS Cost Explorer` | Service fee |
| `AWS Data Transfer` | Cross-service, not tied to specific resources |

## Service Name Mapping

Maps resource types to Cost Explorer service names for cost attribution.

```json
{
  "ec2:instance": "Amazon Elastic Compute Cloud - Compute",
  "rds:db": "Amazon Relational Database Service",
  "s3:bucket": "Amazon Simple Storage Service",
  "ec2:vpc": ""  // Empty = free resource
}
```

## Maintenance Guide

### Adding a New Cost-Generating Resource

1. Edit `config/resource_types.json`
2. Add to appropriate category in `cost_generating_resources`:
   ```json
   "compute": [
     "ec2:instance",
     "new:resource-type"  // Add here
   ]
   ```
3. Add service name mapping:
   ```json
   "service_name_mapping": {
     "new:resource-type": "AWS Service Name From Cost Explorer"
   }
   ```
4. Restart the server

### Adding a New Free Resource

1. Edit `config/resource_types.json`
2. Add to appropriate category in `free_resources`:
   ```json
   "networking": [
     "ec2:vpc",
     "new:free-resource"  // Add here
   ]
   ```
3. Add service name mapping with empty string:
   ```json
   "service_name_mapping": {
     "new:free-resource": ""
   }
   ```

### Adding a New Unattributable Service

1. Edit `config/resource_types.json`
2. Add to appropriate category in `unattributable_services`:
   ```json
   "ai_ml_api_usage": [
     "Claude 3.5 Sonnet (Amazon Bedrock Edition)",
     "New Model Name (Amazon Bedrock Edition)"  // Add here
   ]
   ```

## How to Find Service Names

### From Cost Explorer Console

1. Go to AWS Cost Explorer
2. Group by "Service"
3. Note the exact service name (case-sensitive)

### From AWS CLI

```bash
aws ce get-cost-and-usage \
  --time-period Start=2026-01-01,End=2026-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=DIMENSION,Key=SERVICE
```

## AWS Documentation References

- [Resource Groups Tagging API - Supported Services](https://docs.aws.amazon.com/resourcegroupstagging/latest/APIReference/supported-services.html)
- [AWS Pricing Calculator](https://calculator.aws/)
- [Cost Explorer User Guide](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html)
- [AWS Service Quotas](https://docs.aws.amazon.com/general/latest/gr/aws-service-information.html)

## Troubleshooting

### Resource not appearing in compliance scan

1. Check if it's in `cost_generating_resources`
2. Verify the resource type format matches AWS (e.g., `ec2:instance` not `EC2:Instance`)

### Costs not attributed correctly

1. Check `service_name_mapping` has the exact Cost Explorer service name
2. Verify Cost Allocation Tags are enabled in AWS Billing console
3. Wait 24-48 hours after enabling Cost Allocation Tags

### New Bedrock model costs not separated

1. Add the exact model name to `unattributable_services.ai_ml_api_usage`
2. Find the name in Cost Explorer grouped by "Usage Type"
