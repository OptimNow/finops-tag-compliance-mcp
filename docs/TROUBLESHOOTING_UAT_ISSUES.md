# UAT Troubleshooting Guide

## Issue: find_untagged_resources Tool Errors

### Problem Description

When using the `find_untagged_resources` tool during UAT testing, you may encounter errors. This document explains the two main issues and their solutions.

---

## Issue 1: Code Bug - 'TagPolicy' object has no attribute 'get'

### Error Message
```
Error invoking tool find_untagged_resources: 'TagPolicy' object has no attribute 'get'
```

### Root Cause
The `_get_required_tags_for_resource()` function in `find_untagged_resources.py` was treating the `TagPolicy` Pydantic model as a dictionary and calling `.get()` on it, which doesn't work with Pydantic models.

### Solution
**Fixed in commit 3e9eeb3** - The function now correctly accesses Pydantic model attributes:

**Before (broken)**:
```python
for tag in policy.get("required_tags", []):
    applies_to = tag.get("applies_to", [])
    required_tags.append(tag["name"])
```

**After (fixed)**:
```python
for tag in policy.required_tags:
    applies_to = tag.applies_to
    required_tags.append(tag.name)
```

### Verification
After restarting the Docker containers, the tool should no longer throw this error.

---

## Issue 2: IAM Permission Errors

### Error Messages
You'll see multiple "AccessDenied" errors in the logs:

```
Failed to fetch rds:db: AWS API error: AccessDenied - User is not authorized to perform: rds:ListTagsForResource
Failed to fetch s3:bucket: AWS API error: AccessDenied - User is not authorized to perform: s3:ListAllMyBuckets
Failed to fetch lambda:function: AWS API error: AccessDeniedException - User is not authorized to perform: lambda:ListFunctions
Failed to fetch ecs:service: AWS API error: AccessDeniedException - User is not authorized to perform: ecs:ListClusters
Failed to send log to CloudWatch: User is not authorized to perform: logs:PutLogEvents
```

### Root Cause
Your IAM user (`mcp-bedrock-user`) is missing required permissions to:
1. Read RDS database tags
2. List S3 buckets
3. List Lambda functions
4. List ECS clusters
5. Write logs to CloudWatch

### Solution

You need to add the missing permissions to your IAM user. See the [IAM Permissions Guide](IAM_PERMISSIONS.md) for complete instructions.

**Quick Fix - Add Missing Permissions**:

Create a file `additional-permissions.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MissingReadPermissions",
      "Effect": "Allow",
      "Action": [
        "rds:ListTagsForResource",
        "s3:ListAllMyBuckets",
        "s3:GetBucketTagging",
        "lambda:ListFunctions",
        "lambda:ListTags",
        "ecs:ListClusters",
        "ecs:ListServices",
        "ecs:DescribeServices",
        "ecs:ListTagsForResource"
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
      "Resource": "arn:aws:logs:*:*:log-group:/finops/*"
    }
  ]
}
```

Apply the policy:

```bash
# Create the policy
aws iam create-policy \
  --policy-name FinOpsMCPAdditionalPermissions \
  --policy-document file://additional-permissions.json

# Attach to your IAM user
aws iam attach-user-policy \
  --user-name mcp-bedrock-user \
  --policy-arn arn:aws:iam::382598791951:policy/FinOpsMCPAdditionalPermissions
```

**Alternative - Use Complete Policy**:

Instead of adding permissions piecemeal, you can replace your current policy with the complete one from the [IAM Permissions Guide](IAM_PERMISSIONS.md#custom-iam-policy-least-privilege).

### Verification

After adding permissions, test them:

```bash
# Test RDS access
aws rds describe-db-instances --region us-east-1 --max-records 1

# Test S3 access
aws s3api list-buckets

# Test Lambda access
aws lambda list-functions --region us-east-1 --max-items 1

# Test ECS access
aws ecs list-clusters --region us-east-1
```

All commands should succeed without "AccessDenied" errors.

---

## Expected Behavior After Fixes

Once both issues are resolved:

1. **Code bug fixed**: The tool will no longer crash with the 'TagPolicy' error
2. **IAM permissions fixed**: The tool will successfully scan all resource types (EC2, RDS, S3, Lambda, ECS)
3. **Results**: You'll see untagged resources from all services, not just EC2

### Example Success Output

```
Found 15 untagged resources with total cost $1,234.56/month

Resources:
- 3 EC2 instances (missing CostCenter, Owner)
- 2 RDS databases (missing Environment)
- 5 S3 buckets (completely untagged)
- 3 Lambda functions (missing Application tag)
- 2 ECS services (missing Owner)
```

---

## Partial Success Scenario

**What you're seeing now**: The tool is working for EC2 instances but failing for other resource types.

This is because:
- ✅ EC2 permissions are working (`ec2:DescribeInstances`, `ec2:DescribeTags`)
- ❌ RDS, S3, Lambda, ECS permissions are missing

The tool is designed to continue even if some resource types fail, so you get partial results (EC2 only) instead of a complete failure.

---

## Testing After Fixes

1. **Restart Docker containers** (to pick up code fix):
   ```bash
   docker-compose restart mcp-server
   ```

2. **Add IAM permissions** (see above)

3. **Test in Claude Desktop**:
   ```
   "Find untagged resources costing more than $50/month"
   ```

4. **Check logs** for success:
   ```bash
   docker logs finops-mcp-server --tail 50
   ```

   You should see:
   ```
   Fetched 3 resources of type ec2:instance
   Fetched 2 resources of type rds:db
   Fetched 5 resources of type s3:bucket
   Fetched 3 resources of type lambda:function
   Fetched 2 resources of type ecs:service
   Total resources fetched: 15
   Found 12 untagged resources with total cost $1234.56/month
   ```

---

## Related Documentation

- [IAM Permissions Guide](IAM_PERMISSIONS.md) - Complete IAM setup instructions
- [UAT Protocol](UAT_PROTOCOL.md) - User acceptance testing procedures
- [Deployment Guide](DEPLOYMENT.md) - Server deployment instructions

---

**Last Updated**: January 4, 2026
**Issue Status**: Fixed in commit 3e9eeb3
