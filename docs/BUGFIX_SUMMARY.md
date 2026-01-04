# Bug Fix Summary - find_untagged_resources

## Date: January 4, 2026

## Issue
The `find_untagged_resources` tool was failing with error:
```
'TagPolicy' object has no attribute 'get'
```

## Root Cause
The `_get_required_tags_for_resource()` function in `mcp_server/tools/find_untagged_resources.py` was treating the `TagPolicy` Pydantic model as a dictionary.

**Problem Code**:
```python
def _get_required_tags_for_resource(policy: dict, resource_type: str) -> list[str]:
    required_tags = []
    for tag in policy.get("required_tags", []):  # ❌ .get() doesn't work on Pydantic models
        applies_to = tag.get("applies_to", [])
        required_tags.append(tag["name"])
    return required_tags
```

## Solution
Changed the function to access Pydantic model attributes directly:

**Fixed Code**:
```python
def _get_required_tags_for_resource(policy: TagPolicy, resource_type: str) -> list[str]:
    required_tags = []
    for tag in policy.required_tags:  # ✅ Direct attribute access
        applies_to = tag.applies_to
        required_tags.append(tag.name)
    return required_tags
```

## Files Changed
1. `mcp_server/tools/find_untagged_resources.py`
   - Updated `_get_required_tags_for_resource()` function
   - Added `from ..models.policy import TagPolicy` import
   - Changed type hint from `dict` to `TagPolicy`

## How to Apply Fix

### If Running Locally (Docker)
```bash
# Rebuild the Docker image
docker-compose down
docker-compose build --no-cache mcp-server
docker-compose up -d
```

### If Running on EC2
```bash
# SSH into the instance
ssh -i your-key.pem ec2-user@YOUR_INSTANCE_IP

# Pull latest code
cd /opt/finops-mcp
git pull origin main

# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Verification
After applying the fix, test the tool:

```
"Find untagged resources costing more than $50/month"
```

Expected behavior:
- Tool should successfully scan all resource types (EC2, RDS, S3, Lambda, ECS)
- No more `'TagPolicy' object has no attribute 'get'` error
- Returns list of untagged resources with cost estimates

## Related Issues
This bug was discovered during UAT testing. It was masked by IAM permission issues that prevented most resource types from being scanned. Once IAM permissions were fixed, the bug became apparent.

## Commits
- Fix commit: `3722e2e` - "fix: Resolve TagPolicy attribute error in find_untagged_resources"
- IAM policy: `81a811d` - "feat: Add complete IAM policy file MCP_Tagging_Policy.json"

## Status
✅ **FIXED** - Deployed in commit 3722e2e

---

**Last Updated**: January 4, 2026
