# IAM Permissions Guide

## FinOps Tag Compliance MCP Server - AWS IAM Setup

This guide covers the IAM permissions required for the MCP server to scan AWS resources and check tag compliance.

---

## Overview

The MCP server requires **read-only** access to AWS resources in Phase 1. The principle of least privilege is followed - the server can only read resource metadata and tags, not modify anything.

**Phase 1 (Current)**: Read-only access to EC2, RDS, S3, Lambda, ECS, Cost Explorer
**Phase 2 (Future)**: Additional write permissions for bulk tagging operations

---

## Quick Start

### Option 1: AWS Managed Policy (Fastest)

For testing and development, use the AWS-managed `ReadOnlyAccess` policy:

```bash
# For IAM User
aws iam attach-user-policy \
  --user-name YOUR_USERNAME \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess

# For IAM Role (EC2 Instance Profile)
aws iam attach-role-policy \
  --role-name YOUR_ROLE_NAME \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
```

**Pros**: Quick setup, covers all services
**Cons**: Broader permissions than needed (includes read access to IAM, Secrets Manager, etc.)

### Option 2: Custom Policy (Recommended)

For production or security-conscious environments, use a custom policy with only required permissions.

---

## Custom IAM Policy (Least Privilege)

### Policy Document

Create a file `finops-mcp-policy.json`:

```json
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
        "tag:GetTagValues"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogsWrite",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:log-group:/finops/tag-compliance/*"
    }
  ]
}
```

### Apply the Policy

**For IAM User (Local Development)**:

```bash
# Create the policy
aws iam create-policy \
  --policy-name FinOpsTagCompliancePolicy \
  --policy-document file://finops-mcp-policy.json \
  --description "Read-only access for FinOps Tag Compliance MCP Server"

# Attach to your IAM user
aws iam attach-user-policy \
  --user-name YOUR_USERNAME \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/FinOpsTagCompliancePolicy
```

**For IAM Role (EC2 Instance Profile)**:

```bash
# Create trust policy for EC2
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the role
aws iam create-role \
  --role-name FinOpsTagComplianceRole \
  --assume-role-policy-document file://trust-policy.json \
  --description "Role for FinOps Tag Compliance MCP Server on EC2"

# Create and attach the policy
aws iam create-policy \
  --policy-name FinOpsTagCompliancePolicy \
  --policy-document file://finops-mcp-policy.json

aws iam attach-role-policy \
  --role-name FinOpsTagComplianceRole \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/FinOpsTagCompliancePolicy

# Create instance profile
aws iam create-instance-profile \
  --instance-profile-name FinOpsTagComplianceProfile

# Add role to instance profile
aws iam add-role-to-instance-profile \
  --instance-profile-name FinOpsTagComplianceProfile \
  --role-name FinOpsTagComplianceRole
```

---

## Permission Breakdown

### EC2 Permissions

| Permission | Purpose |
|------------|---------|
| `ec2:DescribeInstances` | List EC2 instances and their tags |
| `ec2:DescribeTags` | Get all tags across EC2 resources |
| `ec2:DescribeVolumes` | Check EBS volume tags |
| `ec2:DescribeRegions` | List available AWS regions |

### RDS Permissions

| Permission | Purpose |
|------------|---------|
| `rds:DescribeDBInstances` | List RDS database instances |
| `rds:DescribeDBClusters` | List RDS Aurora clusters |
| `rds:ListTagsForResource` | Get tags for RDS resources |

### S3 Permissions

| Permission | Purpose |
|------------|---------|
| `s3:ListAllMyBuckets` | List all S3 buckets in account |
| `s3:GetBucketTagging` | Get tags for each bucket |
| `s3:GetBucketLocation` | Determine bucket region |

### Lambda Permissions

| Permission | Purpose |
|------------|---------|
| `lambda:ListFunctions` | List Lambda functions |
| `lambda:ListTags` | Get tags for Lambda functions |

### ECS Permissions

| Permission | Purpose |
|------------|---------|
| `ecs:ListClusters` | List ECS clusters |
| `ecs:ListServices` | List ECS services |
| `ecs:DescribeServices` | Get service details |
| `ecs:ListTagsForResource` | Get tags for ECS resources |

### Cost Explorer Permissions

| Permission | Purpose |
|------------|---------|
| `ce:GetCostAndUsage` | Calculate cost attribution gap |
| `ce:GetCostForecast` | Estimate future costs |
| `ce:GetTags` | Get cost allocation tags |

### Resource Groups Tagging API

| Permission | Purpose |
|------------|---------|
| `tag:GetResources` | Query resources by tags (Phase 1.7) |
| `tag:GetTagKeys` | List all tag keys in use |
| `tag:GetTagValues` | List all tag values for a key |

### CloudWatch Logs (Optional)

| Permission | Purpose |
|------------|---------|
| `logs:CreateLogGroup` | Create log group for MCP server |
| `logs:CreateLogStream` | Create log stream |
| `logs:PutLogEvents` | Write logs to CloudWatch |

---

## Testing IAM Permissions

After setting up IAM permissions, verify they work:

### Test Script

```bash
#!/bin/bash
# test-iam-permissions.sh

echo "Testing IAM permissions for FinOps MCP Server..."
echo ""

# Test EC2
echo "✓ Testing EC2 access..."
aws ec2 describe-instances --region us-east-1 --max-results 1 > /dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "  ✓ EC2 access: OK"
else
  echo "  ✗ EC2 access: FAILED"
fi

# Test RDS
echo "✓ Testing RDS access..."
aws rds describe-db-instances --region us-east-1 --max-records 1 > /dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "  ✓ RDS access: OK"
else
  echo "  ✗ RDS access: FAILED"
fi

# Test S3
echo "✓ Testing S3 access..."
aws s3api list-buckets > /dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "  ✓ S3 access: OK"
else
  echo "  ✗ S3 access: FAILED"
fi

# Test Lambda
echo "✓ Testing Lambda access..."
aws lambda list-functions --region us-east-1 --max-items 1 > /dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "  ✓ Lambda access: OK"
else
  echo "  ✗ Lambda access: FAILED"
fi

# Test Cost Explorer
echo "✓ Testing Cost Explorer access..."
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-02 \
  --granularity MONTHLY \
  --metrics BlendedCost > /dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "  ✓ Cost Explorer access: OK"
else
  echo "  ✗ Cost Explorer access: FAILED (may need to enable Cost Explorer)"
fi

echo ""
echo "Testing complete!"
```

Run the test:

```bash
chmod +x test-iam-permissions.sh
./test-iam-permissions.sh
```

### Manual Testing

```bash
# Test identity
aws sts get-caller-identity

# Test EC2 access
aws ec2 describe-instances --region us-east-1 --max-results 5

# Test RDS access
aws rds describe-db-instances --region us-east-1 --max-records 5

# Test S3 access
aws s3api list-buckets

# Test Lambda access
aws lambda list-functions --region us-east-1 --max-items 5

# Test Cost Explorer access (requires Cost Explorer to be enabled)
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-02 \
  --granularity MONTHLY \
  --metrics BlendedCost
```

---

## Troubleshooting

### "Access Denied" Errors

**Symptom**: MCP server returns "Access Denied" or "UnauthorizedOperation"

**Solutions**:
1. Verify IAM policy is attached: `aws iam list-attached-user-policies --user-name YOUR_USERNAME`
2. Check CloudTrail for specific denied actions
3. Ensure you're testing in the correct AWS region
4. For EC2 instances, verify the instance profile is attached: `aws ec2 describe-instances --instance-ids i-xxxxx --query 'Reservations[0].Instances[0].IamInstanceProfile'`

### "Unable to locate credentials"

**Symptom**: MCP server can't find AWS credentials

**Solutions**:
1. **Local Docker**: Verify `~/.aws/credentials` exists and contains valid credentials
2. **EC2 Instance**: Verify IAM instance profile is attached to the EC2 instance
3. Restart Docker containers after configuring credentials: `docker-compose restart`
4. Check Docker logs: `docker logs finops-mcp-server --tail 50`

### Cost Explorer Not Enabled

**Symptom**: `ce:GetCostAndUsage` returns "Cost Explorer is not enabled"

**Solution**:
1. Enable Cost Explorer in AWS Console: Billing → Cost Explorer → Enable
2. Wait 24 hours for data to populate
3. Alternatively, skip cost-related tools during UAT

### "0 resources found"

**Symptom**: MCP server returns empty results despite having resources

**Possible Causes**:
1. **Wrong region**: Specify the correct region in tool parameters
2. **No resources**: Verify resources exist: `aws ec2 describe-instances --region us-east-1`
3. **Permission issue**: Check CloudTrail for denied API calls
4. **Credential issue**: Verify `aws sts get-caller-identity` returns expected account

---

## Security Best Practices

### 1. Use IAM Roles for EC2 (Not IAM Users)

For production deployments on EC2, always use IAM roles with instance profiles instead of IAM user credentials.

**Why**: IAM roles automatically rotate credentials and don't require storing secrets.

### 2. Restrict by Region (Optional)

Add a condition to limit access to specific regions:

```json
{
  "Condition": {
    "StringEquals": {
      "aws:RequestedRegion": ["us-east-1", "us-west-2"]
    }
  }
}
```

### 3. Use Resource Tags for Access Control (Optional)

Limit access to resources with specific tags:

```json
{
  "Condition": {
    "StringEquals": {
      "ec2:ResourceTag/Environment": "production"
    }
  }
}
```

### 4. Enable CloudTrail

Monitor all API calls made by the MCP server:

```bash
aws cloudtrail create-trail \
  --name finops-mcp-audit \
  --s3-bucket-name your-cloudtrail-bucket

aws cloudtrail start-logging --name finops-mcp-audit
```

### 5. Use AWS Organizations SCPs (Optional)

For multi-account setups, use Service Control Policies to enforce permission boundaries.

---

## Phase 2 Permissions (Future)

Phase 2 will add write permissions for bulk tagging operations:

```json
{
  "Sid": "TagWriteAccess",
  "Effect": "Allow",
  "Action": [
    "ec2:CreateTags",
    "ec2:DeleteTags",
    "rds:AddTagsToResource",
    "rds:RemoveTagsFromResource",
    "s3:PutBucketTagging",
    "lambda:TagResource",
    "lambda:UntagResource",
    "ecs:TagResource",
    "ecs:UntagResource"
  ],
  "Resource": "*"
}
```

**Note**: Phase 1 is read-only. Write permissions are not required for UAT.

---

## Summary

| Environment | Recommended Approach | IAM Entity |
|-------------|---------------------|------------|
| **Local Development** | Custom IAM Policy | IAM User |
| **UAT Testing** | Custom IAM Policy or ReadOnlyAccess | IAM User |
| **Production (EC2)** | Custom IAM Policy | IAM Role + Instance Profile |
| **Production (ECS)** | Custom IAM Policy | IAM Task Role |

**Minimum Required Permissions**: EC2, RDS, S3, Lambda, ECS read access
**Optional Permissions**: Cost Explorer (for cost attribution gap tool), CloudWatch Logs (for logging)

---

## Related Documentation

- [UAT Protocol](UAT_PROTOCOL.md) - User acceptance testing guide
- [Deployment Guide](DEPLOYMENT.md) - EC2 deployment instructions
- [Phase 1 Specification](PHASE-1-SPECIFICATION.md) - Complete Phase 1 requirements
- [Security Configuration](SECURITY_CONFIGURATION.md) - Security best practices

---

**Last Updated**: January 2026
**Version**: 1.0
