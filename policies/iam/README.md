# IAM Policy for FinOps Tag Compliance MCP Server

This directory contains the complete IAM policy required to run the FinOps Tag Compliance MCP Server.

## Policy File

**`MCP_Tagging_Policy.json`** - Complete IAM policy with all required permissions for Phase 1 MVP

## What This Policy Allows

This policy grants **read-only** access to:

### AWS Resource Services
- **EC2**: Read instances, tags, volumes, and regions
- **RDS**: Read database instances, clusters, and tags
- **S3**: List buckets and read bucket tags
- **Lambda**: List functions and read tags
- **ECS**: List clusters, services, and read tags

### Cost & Tagging Services
- **Cost Explorer**: Read cost data and forecasts
- **Resource Groups Tagging API**: Query resources by tags

### Logging
- **CloudWatch Logs**: Write logs to `/finops/*` log groups

## How to Apply This Policy

### Option 1: Create New Policy and Attach to User

```bash
# 1. Create the IAM policy
aws iam create-policy \
  --policy-name MCP_Tagging_Policy \
  --policy-document file://policies/iam/MCP_Tagging_Policy.json \
  --description "Complete permissions for FinOps Tag Compliance MCP Server"

# 2. Attach to your IAM user (replace YOUR_USERNAME and YOUR_ACCOUNT_ID)
aws iam attach-user-policy \
  --user-name YOUR_USERNAME \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/MCP_Tagging_Policy
```

### Option 2: Create New Policy and Attach to Role (for EC2)

```bash
# 1. Create the IAM policy
aws iam create-policy \
  --policy-name MCP_Tagging_Policy \
  --policy-document file://policies/iam/MCP_Tagging_Policy.json

# 2. Attach to your IAM role (for EC2 instance profile)
aws iam attach-role-policy \
  --role-name YOUR_ROLE_NAME \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/MCP_Tagging_Policy
```

### Option 3: Update Existing Policy

If you already have a policy attached, you can update it:

```bash
# Get the policy ARN
POLICY_ARN=$(aws iam list-policies --query 'Policies[?PolicyName==`MCP_Tagging_Policy`].Arn' --output text)

# Create a new version with updated permissions
aws iam create-policy-version \
  --policy-arn $POLICY_ARN \
  --policy-document file://policies/iam/MCP_Tagging_Policy.json \
  --set-as-default
```

## Verification

After applying the policy, verify permissions work:

```bash
# Test EC2 access
aws ec2 describe-instances --region us-east-1 --max-results 1

# Test RDS access
aws rds describe-db-instances --region us-east-1 --max-records 1

# Test S3 access
aws s3api list-buckets

# Test Lambda access
aws lambda list-functions --region us-east-1 --max-items 1

# Test ECS access
aws ecs list-clusters --region us-east-1

# Test Cost Explorer access (requires Cost Explorer to be enabled)
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-02 \
  --granularity MONTHLY \
  --metrics BlendedCost
```

All commands should succeed without "AccessDenied" errors.

## Security Notes

- This policy follows the **principle of least privilege**
- All permissions are **read-only** (Phase 1 MVP)
- CloudWatch Logs write access is restricted to `/finops/*` log groups only
- No permissions to modify resources (create, update, delete tags)

## Phase 2 Additions

Phase 2 will add write permissions for bulk tagging operations. Those will be in a separate policy file: `MCP_Tagging_Policy_Phase2.json`

## Troubleshooting

If you encounter "AccessDenied" errors:

1. **Verify policy is attached**:
   ```bash
   aws iam list-attached-user-policies --user-name YOUR_USERNAME
   ```

2. **Check CloudTrail** for specific denied actions:
   ```bash
   aws cloudtrail lookup-events \
     --lookup-attributes AttributeKey=EventName,AttributeValue=AccessDenied \
     --max-results 10
   ```

3. **Test individual permissions** using the verification commands above

## Related Documentation

- [IAM Permissions Guide](../../docs/IAM_PERMISSIONS.md) - Detailed setup instructions
- [UAT Protocol](../../docs/UAT_PROTOCOL.md) - Testing procedures
- [Troubleshooting UAT Issues](../../docs/TROUBLESHOOTING_UAT_ISSUES.md) - Common issues and fixes

---

**Last Updated**: January 4, 2026  
**Policy Version**: 1.0 (Phase 1 MVP)
