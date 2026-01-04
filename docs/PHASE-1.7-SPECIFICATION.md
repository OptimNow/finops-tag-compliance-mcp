# Phase 1.7 Specification: Expanded AWS Resource Coverage

**Version**: 1.0  
**Timeline**: Weeks 9-10 (2 weeks)  
**Status**: Planned  
**Prerequisites**: Phase 1 and Phase 1.5 completed

---

## Overview

Phase 1.7 expands resource type coverage from 5 initial types to 50+ AWS resource types, enabling comprehensive tagging compliance across an entire AWS account. This removes a major limitation where users could only check a small subset of their infrastructure.

**Current State (Phase 1)**:
- 5 resource types: EC2 instances, RDS databases, S3 buckets, Lambda functions, ECS services
- Service-specific API calls for each resource type
- Covers ~40% of typical AWS infrastructure

**Target State (Phase 1.7)**:
- 50+ resource types across all major AWS services
- Single unified API (AWS Resource Groups Tagging API)
- Covers ~95% of typical AWS infrastructure
- Backward compatible with existing filters

---

## Problem Statement

### Current Limitations

**Incomplete Coverage**:
- Users have EBS volumes, snapshots, load balancers, DynamoDB tables, etc. that aren't being checked
- Significant cost and compliance blind spots
- Users don't know what they're missing

**Scalability Issues**:
- Adding each new resource type requires custom code
- Service-specific APIs have different pagination, rate limits, error handling
- Maintenance burden grows linearly with resource types

**User Feedback**:
> "I ran a compliance check and got 85% compliant, but then realized it wasn't checking my DynamoDB tables or load balancers. Those are 30% of my AWS bill!"

### Solution

Use **AWS Resource Groups Tagging API** which provides:
- Single API call to discover ALL taggable resources
- Unified pagination and error handling
- Automatic support for new AWS services
- Better performance for large-scale scans

---

## Technical Approach

### AWS Resource Groups Tagging API

**Key API**: `resourcegroupstaggingapi:GetResources`

**Benefits**:
- Returns all taggable resources across all services in one call
- Supports filtering by resource type, tags, regions
- Handles pagination automatically
- AWS maintains the list of supported resource types

**Example Call**:
```python
import boto3

client = boto3.client('resourcegroupstaggingapi', region_name='us-east-1')

response = client.get_resources(
    ResourceTypeFilters=[
        'ec2:instance',
        'rds:db',
        's3:bucket',
        # ... or omit to get ALL resource types
    ],
    TagFilters=[
        {
            'Key': 'Environment',
            'Values': ['production']
        }
    ],
    ResourcesPerPage=100
)

for resource in response['ResourceTagMappingList']:
    print(f"{resource['ResourceARN']}: {resource['Tags']}")
```

### Migration Strategy

**Phase 1: Add Resource Groups API Client**
- Create new `ResourceGroupsTaggingClient` wrapper
- Implement pagination, error handling, rate limiting
- Add caching layer

**Phase 2: Update Compliance Service**
- Add `use_resource_groups_api` flag (default: True)
- Fall back to service-specific APIs if needed
- Maintain backward compatibility

**Phase 3: Update Tools**
- Add "all" option to resource_types parameter
- Update response models to handle new resource types
- Add resource type discovery endpoint

**Phase 4: Performance Optimization**
- Implement parallel region scanning
- Add resource type filtering at API level
- Optimize caching strategy for large accounts

---

## Supported Resource Types

### Compute (8 types)
- `ec2:instance` - EC2 instances
- `ec2:volume` - EBS volumes
- `ec2:snapshot` - EBS snapshots
- `ec2:image` - AMIs
- `autoscaling:autoScalingGroup` - Auto Scaling groups
- `lambda:function` - Lambda functions
- `ecs:service` - ECS services
- `ecs:task-definition` - ECS task definitions

### Storage (6 types)
- `s3:bucket` - S3 buckets
- `elasticfilesystem:file-system` - EFS file systems
- `fsx:file-system` - FSx file systems
- `backup:backup-vault` - AWS Backup vaults
- `glacier:vault` - Glacier vaults
- `storagegateway:gateway` - Storage Gateway

### Database (7 types)
- `rds:db` - RDS databases
- `rds:cluster` - RDS clusters
- `dynamodb:table` - DynamoDB tables
- `elasticache:cluster` - ElastiCache clusters
- `elasticache:replicationgroup` - ElastiCache replication groups
- `docdb:cluster` - DocumentDB clusters
- `neptune:cluster` - Neptune clusters

### Networking (10 types)
- `ec2:vpc` - VPCs
- `ec2:subnet` - Subnets
- `ec2:security-group` - Security groups
- `ec2:network-interface` - ENIs
- `ec2:elastic-ip` - Elastic IPs
- `elasticloadbalancing:loadbalancer` - Classic load balancers
- `elasticloadbalancing:loadbalancer/app` - Application load balancers
- `elasticloadbalancing:loadbalancer/net` - Network load balancers
- `cloudfront:distribution` - CloudFront distributions
- `route53:hostedzone` - Route53 hosted zones

### Application Integration (6 types)
- `sqs:queue` - SQS queues
- `sns:topic` - SNS topics
- `states:stateMachine` - Step Functions
- `events:rule` - EventBridge rules
- `apigateway:restapi` - API Gateway REST APIs
- `apigateway:api` - API Gateway HTTP APIs

### Analytics & Big Data (5 types)
- `kinesis:stream` - Kinesis streams
- `glue:database` - Glue databases
- `glue:table` - Glue tables
- `athena:workgroup` - Athena workgroups
- `emr:cluster` - EMR clusters

### Security & Identity (4 types)
- `secretsmanager:secret` - Secrets Manager secrets
- `kms:key` - KMS keys
- `acm:certificate` - ACM certificates
- `iam:role` - IAM roles (limited tagging support)

### Developer Tools (4 types)
- `codecommit:repository` - CodeCommit repositories
- `codebuild:project` - CodeBuild projects
- `codepipeline:pipeline` - CodePipeline pipelines
- `codedeploy:application` - CodeDeploy applications

**Total**: 50+ resource types (AWS adds more regularly)

---

## API Changes

### Tool Parameter Updates

**Before (Phase 1)**:
```json
{
  "resource_types": ["ec2:instance", "rds:db", "s3:bucket"]
}
```

**After (Phase 1.7)**:
```json
{
  "resource_types": ["ec2:instance", "rds:db", "s3:bucket"],  // Specific types
  // OR
  "resource_types": ["all"],  // All supported types
  // OR
  "resource_types": ["compute"],  // Category filter (ec2, lambda, ecs)
  // OR
  "resource_types": []  // Empty = all types (backward compatible)
}
```

### New Tool: list_supported_resource_types

**Purpose**: Discover which resource types are supported

**Parameters**: None

**Returns**:
```json
{
  "resource_types": [
    {
      "type": "ec2:instance",
      "service": "ec2",
      "category": "compute",
      "description": "EC2 instances",
      "tagging_support": "full"
    },
    {
      "type": "dynamodb:table",
      "service": "dynamodb",
      "category": "database",
      "description": "DynamoDB tables",
      "tagging_support": "full"
    }
  ],
  "total_count": 52,
  "categories": ["compute", "storage", "database", "networking", "application", "analytics", "security", "developer-tools"]
}
```

---

## Implementation Plan

### Week 1: Core Infrastructure

**Day 1-2: Resource Groups API Client**
- Create `mcp_server/clients/resource_groups_client.py`
- Implement `get_resources()` with pagination
- Add error handling and retries
- Write unit tests

**Day 3-4: Service Integration**
- Update `ComplianceService` to use new client
- Add feature flag for gradual rollout
- Maintain backward compatibility
- Write integration tests

**Day 5: Resource Type Registry**
- Create `mcp_server/utils/resource_types.py`
- Define all 50+ resource types with metadata
- Add category groupings
- Implement `list_supported_resource_types` tool

### Week 2: Optimization & Testing

**Day 6-7: Performance Optimization**
- Implement parallel region scanning
- Add intelligent caching (cache by resource type)
- Optimize for large accounts (10,000+ resources)
- Load testing

**Day 8-9: Tool Updates**
- Update all 8 existing tools to support new resource types
- Add "all" and category filters
- Update response models
- Update documentation

**Day 10: Testing & Documentation**
- End-to-end testing with real AWS account
- Update UAT protocol
- Update API documentation
- Update policy generator with new resource types

---

## Performance Considerations

### Caching Strategy

**Problem**: Scanning 10,000+ resources takes time

**Solution**: Multi-level caching
```python
# Level 1: Resource list cache (5 minutes)
cache_key = f"resources:{account_id}:{region}:{resource_types_hash}"

# Level 2: Compliance results cache (15 minutes)
cache_key = f"compliance:{account_id}:{region}:{resource_types_hash}:{policy_hash}"

# Level 3: Resource metadata cache (1 hour)
cache_key = f"resource_meta:{resource_arn}"
```

### Parallel Scanning

**Single Region**: ~5 seconds for 1,000 resources  
**Multi-Region (sequential)**: ~50 seconds for 10 regions  
**Multi-Region (parallel)**: ~8 seconds for 10 regions

```python
import asyncio

async def scan_all_regions(resource_types):
    regions = ['us-east-1', 'us-west-2', 'eu-west-1', ...]
    tasks = [scan_region(region, resource_types) for region in regions]
    results = await asyncio.gather(*tasks)
    return merge_results(results)
```

### Rate Limiting

AWS Resource Groups Tagging API limits:
- **GetResources**: 20 requests/second
- **Burst**: 100 requests

**Strategy**:
- Use exponential backoff
- Implement request queuing
- Cache aggressively

---

## Backward Compatibility

### Existing Code

All existing code continues to work:

```python
# Phase 1 code - still works
result = check_tag_compliance(
    resource_types=["ec2:instance", "rds:db"]
)
```

### New Capabilities

```python
# Phase 1.7 - scan everything
result = check_tag_compliance(
    resource_types=["all"]
)

# Phase 1.7 - category filter
result = check_tag_compliance(
    resource_types=["compute"]  # ec2, lambda, ecs
)

# Phase 1.7 - discover resource types
types = list_supported_resource_types()
```

---

## Testing Strategy

### Unit Tests
- Resource Groups API client
- Resource type registry
- Category filtering logic
- Caching layer

### Integration Tests
- End-to-end compliance check with 50+ resource types
- Performance test with 10,000+ resources
- Multi-region scanning
- Error handling (rate limits, timeouts)

### Property Tests
- Resource type filtering correctness
- Cache consistency
- Pagination correctness

---

## Documentation Updates

### Files to Update

1. **docs/PHASE-1-SPECIFICATION.md**
   - Update resource type list
   - Add "all" option documentation

2. **docs/TAGGING_POLICY_GUIDE.md**
   - Add new resource types to examples
   - Update "applies_to" field documentation

3. **docs/UAT_PROTOCOL.md**
   - Add test cases for new resource types
   - Add "scan all resources" test

4. **docs/POLICY_GENERATOR_PROMPT.md**
   - Update resource type checkboxes
   - Add 50+ resource types

5. **README.md**
   - Update feature list: "50+ AWS resource types"

---

## Success Metrics

### Functional
- ✅ Support 50+ AWS resource types
- ✅ "all" resource type filter works
- ✅ Backward compatible with Phase 1 code
- ✅ New `list_supported_resource_types` tool

### Performance
- ✅ <30 seconds to scan typical account (all resources)
- ✅ <10 seconds for single region
- ✅ No degradation for existing 5 resource types
- ✅ Cache hit rate >80% for repeated scans

### User Experience
- ✅ Users discover resources they didn't know existed
- ✅ Compliance scores more accurate
- ✅ Cost attribution gap reduced by 20%+

---

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Performance degradation | High | Aggressive caching, parallel scanning |
| AWS API rate limits | Medium | Exponential backoff, request queuing |
| Breaking changes | High | Feature flag, gradual rollout |
| Increased AWS costs | Low | Caching reduces API calls by 80% |
| Complexity | Medium | Keep service-specific APIs as fallback |

---

## Future Enhancements (Post-Phase 1.7)

### Phase 2+
- **Resource type recommendations**: "You have DynamoDB tables but aren't checking them"
- **Cost-weighted compliance**: Weight compliance by resource cost
- **Resource dependency mapping**: Show which resources are related
- **Custom resource type groups**: Let users define their own categories

---

## IAM Permissions Required

Add to existing IAM role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ResourceGroupsTaggingAPI",
      "Effect": "Allow",
      "Action": [
        "tag:GetResources",
        "tag:GetTagKeys",
        "tag:GetTagValues"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## Deployment Plan

### Rollout Strategy

**Week 1**: Internal testing
- Deploy to dev environment
- Test with internal AWS accounts
- Validate performance and accuracy

**Week 2**: Beta release
- Enable for 5 beta users
- Gather feedback
- Fix any issues

**Week 3**: General availability
- Enable for all users
- Update documentation
- Announce new capability

### Rollback Plan

If issues arise:
1. Disable feature flag `use_resource_groups_api`
2. Fall back to service-specific APIs
3. Investigate and fix
4. Re-enable gradually

---

**Document Version**: 1.0  
**Last Updated**: January 4, 2025  
**Owner**: FinOps Engineering Team
