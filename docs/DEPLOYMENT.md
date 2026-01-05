# Deployment Guide: Tag Compliance MCP Server

This guide covers deploying the MCP server locally for development/testing and to AWS EC2 for production use.

## Table of Contents

1. [Local Deployment](#local-deployment) - Quick start for testing
2. [AWS Deployment](#aws-deployment) - Production deployment to EC2
3. [Connecting Claude Desktop](#connecting-claude-desktop)
4. [Configuration](#configuration)
5. [Monitoring](#monitoring)
6. [Troubleshooting](#troubleshooting)

---

## Local Deployment

Deploy the MCP server on your local machine for development, testing, or personal use.

### Prerequisites

- Docker Desktop installed and running
- AWS CLI configured with credentials (`aws configure`)
- Python 3.11+ (for the bridge script)
- Git

### Quick Start (5 minutes)

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_ORG/finops-tag-compliance-mcp.git
cd finops-tag-compliance-mcp

# 2. Create environment file
cp .env.example .env

# 3. Start the services
docker-compose up -d

# 4. Verify it's running
curl http://localhost:8080/health
```

### Step-by-Step Instructions

#### Step 1: Clone and Configure

```bash
# Clone the repository
git clone https://github.com/YOUR_ORG/finops-tag-compliance-mcp.git
cd finops-tag-compliance-mcp

# Create your environment file
cp .env.example .env
```

Edit `.env` if needed (defaults work for most cases):

```bash
ENVIRONMENT=development
LOG_LEVEL=INFO
REDIS_URL=redis://redis:6379/0
AWS_REGION=us-east-1
```

#### Step 2: Configure AWS Credentials

The server needs AWS credentials to scan your resources. On your local machine, it uses your `~/.aws` credentials folder.

```bash
# Verify AWS credentials are configured
aws sts get-caller-identity

# If not configured, run:
aws configure
```

#### Step 3: Start the Server

```bash
# Start all services (MCP server + Redis)
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f mcp-server
```

#### Step 4: Verify Installation

```bash
# Health check
curl http://localhost:8080/health

# List available tools
curl http://localhost:8080/mcp/tools

# Test a tool (get tagging policy)
curl -X POST http://localhost:8080/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name": "get_tagging_policy", "arguments": {}}'
```

### Connect Claude Desktop (Local)

Add to your Claude Desktop config:

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "tagging-mcp": {
      "command": "python",
      "args": ["C:\\path\\to\\repo\\scripts\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://localhost:8080"
      }
    }
  }
}
```

Replace `C:\\path\\to\\repo` with your actual repository path.

### Stop/Restart Local Server

```bash
# Stop services
docker-compose down

# Restart services
docker-compose restart

# Rebuild after code changes
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## AWS Deployment

Deploy to AWS EC2 for production use with persistent storage and team access.

### Architecture Overview

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

### Prerequisites

- AWS CLI configured with appropriate credentials
- IAM permissions configured (see [IAM Permissions Guide](IAM_PERMISSIONS.md))
- An existing VPC and subnet
- An EC2 key pair for SSH access

### Option 1: CloudFormation Deployment (Recommended)

#### Step 1: Deploy Infrastructure

```bash
# Deploy the CloudFormation stack
aws cloudformation create-stack \
  --stack-name tagging-mcp-server \
  --template-body file://infrastructure/cloudformation.yaml \
  --parameters \
    ParameterKey=EnvironmentName,ParameterValue=dev \
    ParameterKey=KeyPairName,ParameterValue=YOUR_KEY_PAIR \
    ParameterKey=VpcId,ParameterValue=vpc-xxxxxxxx \
    ParameterKey=SubnetId,ParameterValue=subnet-xxxxxxxx \
    ParameterKey=AllowedCIDR,ParameterValue=YOUR_IP/32 \
  --capabilities CAPABILITY_NAMED_IAM

# Wait for stack creation
aws cloudformation wait stack-create-complete --stack-name tagging-mcp-server

# Get outputs
aws cloudformation describe-stacks --stack-name tagging-mcp-server \
  --query 'Stacks[0].Outputs'
```

#### Step 2: Deploy Application

```bash
# Get the instance IP
INSTANCE_IP=$(aws cloudformation describe-stacks \
  --stack-name tagging-mcp-server \
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

# Build the Docker image
# Note: Use docker build instead of docker-compose build to avoid buildx version issues on Amazon Linux
docker build -t finops-mcp-mcp-server .

# Start the services
docker-compose up -d

# Verify it's running
curl http://localhost:8080/health
```

#### Step 3: Verify Deployment

```bash
# From your local machine
curl http://$INSTANCE_IP:8080/health

# Expected response:
# {"status": "healthy", "version": "0.1.0", "cloud_providers": ["aws"], ...}
```

### Option 2: Manual Deployment

#### Step 1: Create IAM Role

The MCP server requires read-only access to AWS resources. See the [IAM Permissions Guide](IAM_PERMISSIONS.md) for detailed setup.

**Quick Setup** - Create an IAM role with this policy:

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
        "es:ListDomainNames",
        "es:DescribeDomain",
        "es:ListTags",
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

#### Step 2: Launch EC2 Instance

1. Launch a t3.medium instance with Amazon Linux 2023
2. Attach the IAM role created above
3. Configure security group:
   - Inbound: 8080 (MCP), 22 (SSH)
   - Outbound: 443 (AWS APIs), 80 (updates)
4. Use this user data script:

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

#### Step 3: Deploy Application

SSH into the instance and follow Step 2 from Option 1.

### Cost Estimate

| Resource | Monthly Cost (us-east-1) |
|----------|-------------------------|
| t3.medium EC2 | ~$30 |
| 20GB gp3 EBS | ~$2 |
| CloudWatch Logs | ~$1-5 |
| **Total** | **~$35-40/month** |

---

## Connecting Claude Desktop

The MCP server uses REST endpoints, so you need the bridge script to translate between Claude Desktop's stdio protocol and the HTTP API.

### Prerequisites

1. Python 3.11+ installed on your local machine
2. `requests` library: `pip install requests`
3. This repository cloned locally (for `scripts/mcp_bridge.py`)

### Configuration

Add to your Claude Desktop config:

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Linux**: `~/.config/claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "tagging-mcp": {
      "command": "python",
      "args": ["PATH_TO_REPO/scripts/mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://SERVER_ADDRESS:8080"
      }
    }
  }
}
```

### Examples

**Local deployment (Windows)**:
```json
{
  "mcpServers": {
    "tagging-mcp": {
      "command": "python",
      "args": ["C:\\Users\\YourName\\Documents\\GitHub\\finops-tag-compliance-mcp\\scripts\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://localhost:8080"
      }
    }
  }
}
```

**Remote deployment (Windows)**:
```json
{
  "mcpServers": {
    "tagging-mcp": {
      "command": "python",
      "args": ["C:\\Users\\YourName\\Documents\\GitHub\\finops-tag-compliance-mcp\\scripts\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://YOUR_EC2_IP:8080"
      }
    }
  }
}
```

**macOS/Linux**:
```json
{
  "mcpServers": {
    "tagging-mcp": {
      "command": "python3",
      "args": ["/home/yourname/finops-tag-compliance-mcp/scripts/mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://localhost:8080"
      }
    }
  }
}
```

### Verify Connection

After restarting Claude Desktop, test by asking:
- "What tagging policy is configured?"
- "Check tag compliance for my EC2 instances"
- "Find untagged S3 buckets"

---

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

See [Tagging Policy Guide](TAGGING_POLICY_GUIDE.md) for detailed configuration options.

---

## Monitoring

### Health Check

```bash
curl http://SERVER_ADDRESS:8080/health
```

### View Logs

```bash
# Docker logs
docker-compose logs -f mcp-server

# CloudWatch (EC2 deployment)
aws logs tail /finops-mcp-server/dev --follow
```

### Check Container Status

```bash
docker-compose ps
```

---

## Troubleshooting

### Server Not Responding

```bash
# Check if containers are running
docker-compose ps

# Check logs for errors
docker-compose logs mcp-server

# Restart services
docker-compose restart
```

### AWS API Errors

```bash
# Local: Verify AWS credentials
aws sts get-caller-identity

# EC2: Verify IAM role is attached
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/
```

### Redis Connection Issues

```bash
# Check Redis container
docker-compose logs redis

# Test Redis connectivity
docker exec -it finops-redis redis-cli ping
```

### Claude Desktop Not Connecting

1. Verify the bridge script path is correct
2. Check that Python and `requests` are installed
3. Verify the server is running: `curl http://SERVER_ADDRESS:8080/health`
4. Check Claude Desktop logs for errors

### Docker Build Issues on EC2

If you see `compose build requires buildx 0.17 or later`:

```bash
# Use docker build instead of docker-compose build
docker build -t finops-mcp-mcp-server .
docker-compose up -d
```

---

## Updating

### Local

```bash
git pull origin main
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### EC2

```bash
ssh -i your-key.pem ec2-user@$INSTANCE_IP
cd /opt/finops-mcp
git pull origin main
docker-compose down
docker build -t finops-mcp-mcp-server .
docker-compose up -d
```

---

## Cleanup

### Local

```bash
docker-compose down -v  # -v removes volumes
```

### AWS

```bash
aws cloudformation delete-stack --stack-name tagging-mcp-server
aws cloudformation wait stack-delete-complete --stack-name tagging-mcp-server
```

---

## Security Recommendations

1. **Restrict AllowedCIDR**: Only allow your IP or VPN CIDR
2. **Use HTTPS**: Put an ALB with SSL certificate in front for production
3. **Enable VPC Flow Logs**: Monitor network traffic
4. **Rotate credentials**: Use AWS Secrets Manager for any secrets
5. **Enable CloudTrail**: Audit all API calls

---

## Next Steps

- Read the [User Manual](USER_MANUAL.md) for tool usage and example prompts
- Configure your [Tagging Policy](TAGGING_POLICY_GUIDE.md)
- Review [IAM Permissions](IAM_PERMISSIONS.md) for security best practices
