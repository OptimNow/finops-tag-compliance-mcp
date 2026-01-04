# Deployment Guide: FinOps Tag Compliance MCP Server

This guide covers deploying the MCP server to AWS EC2 for Phase 1.

## Prerequisites

- AWS CLI configured with appropriate credentials
- IAM permissions configured (see [IAM Permissions Guide](IAM_PERMISSIONS.md))
- An existing VPC and subnet
- An EC2 key pair for SSH access
- Docker installed locally (for building images)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        AWS Cloud                            │
│  ┌───────────────────────────────────────────────────────┐ │
│  │                    VPC                                 │ │
│  │  ┌─────────────────────────────────────────────────┐  │ │
│  │  │              EC2 (t3.medium)                     │  │ │
│  │  │  ┌─────────────────────────────────────────┐    │  │ │
│  │  │  │           Docker Compose                 │    │  │ │
│  │  │  │  ┌─────────────┐  ┌─────────────────┐   │    │  │ │
│  │  │  │  │ MCP Server  │  │     Redis       │   │    │  │ │
│  │  │  │  │   :8080     │──│     :6379       │   │    │  │ │
│  │  │  │  └─────────────┘  └─────────────────┘   │    │  │ │
│  │  │  └─────────────────────────────────────────┘    │  │ │
│  │  │                     │                            │  │ │
│  │  │              IAM Instance Profile                │  │ │
│  │  └─────────────────────┼───────────────────────────┘  │ │
│  └────────────────────────┼──────────────────────────────┘ │
│                           │                                 │
│  ┌────────────────────────┼──────────────────────────────┐ │
│  │                   AWS Services                         │ │
│  │  EC2 │ RDS │ S3 │ Lambda │ ECS │ Cost Explorer        │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Option 1: CloudFormation Deployment (Recommended)

### Step 1: Deploy Infrastructure

```bash
# Deploy the CloudFormation stack
aws cloudformation create-stack \
  --stack-name finops-mcp-server \
  --template-body file://infrastructure/cloudformation.yaml \
  --parameters \
    ParameterKey=EnvironmentName,ParameterValue=dev \
    ParameterKey=KeyPairName,ParameterValue=YOUR_KEY_PAIR \
    ParameterKey=VpcId,ParameterValue=vpc-xxxxxxxx \
    ParameterKey=SubnetId,ParameterValue=subnet-xxxxxxxx \
    ParameterKey=AllowedCIDR,ParameterValue=YOUR_IP/32 \
  --capabilities CAPABILITY_NAMED_IAM

# Wait for stack creation
aws cloudformation wait stack-create-complete --stack-name finops-mcp-server

# Get outputs
aws cloudformation describe-stacks --stack-name finops-mcp-server \
  --query 'Stacks[0].Outputs'
```

### Step 2: Deploy Application

```bash
# Get the instance IP
INSTANCE_IP=$(aws cloudformation describe-stacks \
  --stack-name finops-mcp-server \
  --query 'Stacks[0].Outputs[?OutputKey==`InstancePublicIP`].OutputValue' \
  --output text)

# SSH into the instance
ssh -i your-key.pem ec2-user@$INSTANCE_IP

# Clone the repository
cd /opt/finops-mcp
git clone https://github.com/YOUR_ORG/finops-tag-compliance-mcp.git .

# Create environment file
cat > .env << 'EOF'
ENVIRONMENT=production
LOG_LEVEL=INFO
REDIS_URL=redis://redis:6379/0
REDIS_TTL=3600
AWS_REGION=us-east-1
EOF

# Start the services
docker-compose up -d

# Verify it's running
curl http://localhost:8080/health
```

### Step 3: Verify Deployment

```bash
# From your local machine
curl http://$INSTANCE_IP:8080/health

# Expected response:
# {"status": "healthy", "version": "1.0.0", "cloud_providers": ["aws"]}
```

## Option 2: Manual Deployment

### Step 1: Create IAM Role

The MCP server requires read-only access to AWS resources. See the [IAM Permissions Guide](IAM_PERMISSIONS.md) for detailed setup instructions.

**Quick Setup**:

Create an IAM role with the following policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeTags",
        "ec2:DescribeRegions",
        "rds:DescribeDBInstances",
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
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

### Step 2: Launch EC2 Instance

1. Launch a t3.medium instance with Amazon Linux 2023
2. Attach the IAM role created above
3. Configure security group:
   - Inbound: 8080 (MCP), 22 (SSH)
   - Outbound: 443 (AWS APIs), 80 (updates)
4. Use the following user data script:

```bash
#!/bin/bash
yum update -y
yum install -y docker git
systemctl start docker
systemctl enable docker
usermod -aG docker ec2-user

curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

mkdir -p /opt/finops-mcp
chown ec2-user:ec2-user /opt/finops-mcp
```

### Step 3: Deploy Application

SSH into the instance and follow Step 2 from Option 1.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Environment name | `development` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `REDIS_TTL` | Cache TTL in seconds | `3600` |
| `AWS_REGION` | Default AWS region | `us-east-1` |
| `POLICY_FILE_PATH` | Path to tagging policy | `/app/policies/tagging_policy.json` |

### Custom Tagging Policy

Edit `policies/tagging_policy.json` to match your organization's requirements:

```json
{
  "version": "1.0",
  "required_tags": [
    {
      "name": "CostCenter",
      "description": "Department for cost allocation",
      "allowed_values": ["Engineering", "Marketing", "Sales"],
      "applies_to": ["ec2:instance", "rds:db", "s3:bucket"]
    }
  ]
}
```

## Connecting Claude Desktop

Add to your Claude Desktop config (`~/.config/claude/config.json`):

```json
{
  "mcpServers": {
    "finops-tag-compliance": {
      "url": "http://YOUR_INSTANCE_IP:8080",
      "transport": "http"
    }
  }
}
```

## Monitoring

### Health Check

```bash
curl http://YOUR_INSTANCE_IP:8080/health
```

### View Logs

```bash
# On the EC2 instance
docker-compose logs -f mcp-server

# Or via CloudWatch
aws logs tail /finops-mcp-server/dev --follow
```

### Check Container Status

```bash
docker-compose ps
```

## Updating

```bash
# SSH into the instance
ssh -i your-key.pem ec2-user@$INSTANCE_IP

cd /opt/finops-mcp

# Pull latest code
git pull origin main

# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Troubleshooting

### MCP Server Not Responding

```bash
# Check if containers are running
docker-compose ps

# Check logs
docker-compose logs mcp-server

# Restart services
docker-compose restart
```

### AWS API Errors

```bash
# Verify IAM role is attached
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/

# Test AWS access
aws sts get-caller-identity
```

### Redis Connection Issues

```bash
# Check Redis container
docker-compose logs redis

# Test Redis connectivity
docker exec -it finops-redis redis-cli ping
```

## Security Recommendations

1. **Restrict AllowedCIDR**: Only allow your IP or VPN CIDR
2. **Use HTTPS**: Put an ALB with SSL certificate in front
3. **Enable VPC Flow Logs**: Monitor network traffic
4. **Rotate credentials**: Use AWS Secrets Manager for any secrets
5. **Enable CloudTrail**: Audit all API calls

## Cost Estimate

| Resource | Monthly Cost (us-east-1) |
|----------|-------------------------|
| t3.medium EC2 | ~$30 |
| 20GB gp3 EBS | ~$2 |
| CloudWatch Logs | ~$1-5 |
| **Total** | **~$35-40/month** |

## Cleanup

```bash
# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name finops-mcp-server

# Wait for deletion
aws cloudformation wait stack-delete-complete --stack-name finops-mcp-server
```
