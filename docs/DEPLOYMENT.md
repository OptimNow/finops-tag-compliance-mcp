# Deployment Guide: Tag Compliance MCP Server

This guide covers deploying the MCP server locally for development/testing and to AWS EC2 for production use.

## Table of Contents

1. [Local Deployment](#local-deployment) - Quick start for testing
2. [AWS Deployment](#aws-deployment) - Production deployment to EC2
3. [One-Click Policy Deployment](#one-click-policy-deployment-remote-ec2) - Update policies remotely
4. [Connecting Claude Desktop](#connecting-claude-desktop)
5. [Configuration](#configuration)
6. [Monitoring](#monitoring)
7. [Troubleshooting](#troubleshooting)

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
git clone https://github.com/YOUR_ORG/tagging-mcp-server.git
cd tagging-mcp-server

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
git clone https://github.com/YOUR_ORG/tagging-mcp-server.git
cd tagging-mcp-server

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
- An existing VPC and subnet
- An EC2 key pair for SSH access

> **Note**: IAM permissions are created automatically by CloudFormation. You do NOT need to manually configure IAM roles, policies, or instance profiles. The CloudFormation template creates all required IAM resources including the role, policy, and instance profile with the correct permissions.

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
# Get the Elastic IP (from your local machine)
INSTANCE_IP=$(aws cloudformation describe-stacks \
  --stack-name tagging-mcp-server \
  --query 'Stacks[0].Outputs[?OutputKey==`ElasticIP`].OutputValue' \
  --output text)

# SSH into the instance
ssh -i your-key.pem ec2-user@$INSTANCE_IP
```

Once connected to EC2, run these commands:

```bash
# Clone the repository
cd ~
git clone https://github.com/OptimNow/finops-tag-compliance-mcp.git
cd finops-tag-compliance-mcp

# Build the Docker image
docker build -t tagging-mcp-server .

# Start Redis container
docker run -d --name tagging-redis -p 6379:6379 redis:7-alpine

# Start the MCP server
# Note: We use docker run instead of docker-compose because Amazon Linux's
# docker-compose version doesn't support the buildx features, and the
# docker-compose.yml has Windows-specific volume mounts that don't work on EC2.
# On EC2, the server uses the IAM instance profile for AWS credentials automatically.
docker run -d --name tagging-mcp-server \
  -p 8080:8080 \
  -e REDIS_URL=redis://172.17.0.1:6379/0 \
  -e AWS_REGION=us-east-1 \
  -e ENVIRONMENT=production \
  -e LOG_LEVEL=INFO \
  -v $(pwd)/policies:/app/policies:ro \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  tagging-mcp-server

# Wait for startup and verify
sleep 5
docker ps
curl http://localhost:8080/health
```

> **Why not docker-compose on EC2?** The `docker-compose.yml` is designed for local development on Windows/Mac where it mounts your `~/.aws` credentials folder. On EC2, credentials come from the IAM instance profile automatically, and Amazon Linux's docker-compose has compatibility issues with buildx. Using `docker run` directly is simpler and more reliable.

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

mkdir -p /opt/tagging-mcp
chown ec2-user:ec2-user /opt/tagging-mcp
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

## One-Click Policy Deployment (Remote EC2)

After deploying to EC2, you can set up a one-click workflow to update your tagging policy from your local machine. This lets you edit the policy locally and deploy it to EC2 with a single command.

### How It Works

```
┌─────────────────┐     ┌─────────────┐     ┌─────────────┐
│ Local Machine   │────▶│    S3       │────▶│    EC2      │
│ Edit policy     │     │ (staging)   │     │ Pull & restart
└─────────────────┘     └─────────────┘     └─────────────┘
```

1. You edit `policies/tagging_policy.json` locally
2. Run `.\scripts\deploy_policy.ps1` (Windows) or `./scripts/deploy_policy.sh` (Mac/Linux)
3. Script uploads to S3, tells EC2 to pull it, and restarts Docker

### Setup Steps

#### Step 1: Create S3 Bucket for Policy Staging

```bash
aws s3 mb s3://finops-mcp-config --region us-east-1
```

#### Step 2: Add SSM and S3 Permissions to EC2 IAM Role

The CloudFormation template already includes these permissions. If you deployed manually, add them:

```bash
# Add SSM permissions (allows running commands on EC2 remotely)
aws iam attach-role-policy \
  --role-name tagging-mcp-server-role-dev \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore

# Add S3 read permission for the config bucket
aws iam put-role-policy \
  --role-name tagging-mcp-server-role-dev \
  --policy-name S3ConfigAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::finops-mcp-config/*"
    }]
  }'
```

#### Step 3: Set Up EC2 for External Policy Files

SSH into your EC2 instance and run these commands once:

```bash
# SSH to EC2
ssh -i your-key.pem ec2-user@YOUR_EC2_IP

# Create policies folder on EC2
mkdir -p /home/ec2-user/mcp-policies

# Copy current policy from the running container
docker cp finops-mcp-server:/app/policies/tagging_policy.json /home/ec2-user/mcp-policies/

# Stop and remove the old container
docker rm -f finops-mcp-server

# Restart with mounted volume so policy changes take effect
docker run -d -p 8080:8080 --name finops-mcp-server \
  -v /home/ec2-user/mcp-policies:/app/policies \
  tagging-mcp-server

# Verify it's working
curl http://localhost:8080/health
```

#### Step 4: Update the Deployment Script with Your Values

Edit `scripts/deploy_policy.ps1` (Windows) or `scripts/deploy_policy.sh` (Mac/Linux):

```powershell
# In deploy_policy.ps1, update these values:
$S3Bucket = "finops-mcp-config"        # Your S3 bucket name
$EC2InstanceId = "i-0dc314272ccf812db" # Your EC2 instance ID (from CloudFormation outputs)
$Region = "us-east-1"                   # Your AWS region
```

To get your EC2 instance ID:
```bash
aws cloudformation describe-stacks --stack-name tagging-mcp-server \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' --output text
```

#### Step 5: Test the Deployment

```powershell
# Windows
.\scripts\deploy_policy.ps1

# Mac/Linux
./scripts/deploy_policy.sh
```

You should see:
```
========================================
  FinOps MCP Policy Deployment
========================================

[1/4] Validating policy JSON...
      OK - Valid JSON
[2/4] Uploading to S3...
      OK - Uploaded to s3://finops-mcp-config/policies/
[3/4] Updating EC2 instance...
      OK - Command sent (ID: xxx)
[4/4] Waiting for deployment to complete...
      OK - Policy deployed successfully!

========================================
  Deployment Complete!
========================================
```

### Daily Usage

After setup, updating your policy is just:

```powershell
# 1. Edit your policy locally
notepad policies/tagging_policy.json

# 2. Deploy with one command
.\scripts\deploy_policy.ps1
```

### Troubleshooting

**"Could not send command to EC2"**
- Verify SSM agent is running on EC2: `sudo systemctl status amazon-ssm-agent`
- Check IAM role has `AmazonSSMManagedInstanceCore` policy attached
- Verify instance ID is correct

**"Could not upload to S3"**
- Check S3 bucket exists: `aws s3 ls s3://finops-mcp-config`
- Check your local AWS credentials have `s3:PutObject` permission

**Policy not updating on EC2**
- SSH to EC2 and check: `cat /home/ec2-user/mcp-policies/tagging_policy.json`
- Check Docker logs: `docker logs finops-mcp-server`
- Verify the volume mount: `docker inspect finops-mcp-server | grep Mounts -A 10`

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

**Remote EC2 deployment (Windows)**:
```json
{
  "mcpServers": {
    "tagging-mcp": {
      "command": "python",
      "args": ["C:\\Users\\YourName\\Documents\\GitHub\\finops-tag-compliance-mcp\\scripts\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://YOUR_EC2_ELASTIC_IP:8080"
      }
    }
  }
}
```

> **Note**: Use the Elastic IP from CloudFormation outputs, not the instance's public IP. The Elastic IP stays the same even if you stop/start the EC2 instance. Get it with:
> ```bash
> aws cloudformation describe-stacks --stack-name tagging-mcp-server \
>   --query 'Stacks[0].Outputs[?OutputKey==`ElasticIP`].OutputValue' --output text
> ```
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
# Local (docker-compose)
docker-compose logs -f mcp-server

# EC2 (docker run)
docker logs -f tagging-mcp-server

# CloudWatch (EC2 deployment)
aws logs tail /mcp-tagging/dev --follow
```

### Check Container Status

```bash
# Local
docker-compose ps

# EC2
docker ps
```

---

## Troubleshooting

### Server Not Responding

```bash
# Check if containers are running
docker ps

# Check logs for errors (EC2)
docker logs tagging-mcp-server

# Check logs for errors (Local)
docker-compose logs mcp-server

# Restart on EC2
docker restart tagging-mcp-server tagging-redis
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
docker exec -it tagging-redis redis-cli ping
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
docker build -t tagging-mcp-server .
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
cd ~/finops-tag-compliance-mcp
git pull origin main

# Stop and remove existing containers
docker stop tagging-mcp-server tagging-redis
docker rm tagging-mcp-server tagging-redis

# Rebuild and restart
docker build -t tagging-mcp-server .
docker run -d --name tagging-redis -p 6379:6379 redis:7-alpine
docker run -d --name tagging-mcp-server \
  -p 8080:8080 \
  -e REDIS_URL=redis://172.17.0.1:6379/0 \
  -e AWS_REGION=us-east-1 \
  -e ENVIRONMENT=production \
  -e LOG_LEVEL=INFO \
  -v $(pwd)/policies:/app/policies:ro \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  tagging-mcp-server

# Verify
curl http://localhost:8080/health
```

---

## Cleanup

### Local

```bash
docker-compose down -v  # -v removes volumes
```

### EC2

```bash
# Stop and remove containers
docker stop tagging-mcp-server tagging-redis
docker rm tagging-mcp-server tagging-redis

# Delete CloudFormation stack (removes EC2, security group, IAM role, etc.)
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
