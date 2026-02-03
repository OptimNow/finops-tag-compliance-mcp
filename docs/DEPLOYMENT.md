# Deployment Guide: Tag Compliance MCP Server

This guide covers deploying the MCP server locally for development/testing and to AWS EC2 for production use.

## Quick Start -- stdio (Recommended for local)

Get up and running in 5 minutes. No Docker required.

```bash
git clone https://github.com/OptimNow/finops-tag-compliance-mcp.git
cd finops-tag-compliance-mcp
pip install -e .
python -m mcp_server.stdio_server   # Runs until terminated
```

Then add to your Claude Desktop config (`%APPDATA%\Claude\claude_desktop_config.json` on Windows, `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "finops-tagging": {
      "command": "python",
      "args": ["-m", "mcp_server.stdio_server"],
      "cwd": "/path/to/finops-tag-compliance-mcp"
    }
  }
}
```

Restart Claude Desktop and ask: *"What tagging policy is configured?"*

**Test with MCP Inspector:**
```bash
npx @modelcontextprotocol/inspector python -m mcp_server.stdio_server
```

**For Docker/HTTP deployment or production EC2**, continue reading below.

---

## Quick Start -- Docker (HTTP transport)

For running with Redis caching or Docker-based workflows:

**Linux/Mac:**
```bash
git clone https://github.com/OptimNow/finops-tag-compliance-mcp.git
cd finops-tag-compliance-mcp
docker-compose up -d
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/OptimNow/finops-tag-compliance-mcp.git
cd finops-tag-compliance-mcp
docker-compose -f docker-compose.yml -f docker-compose.windows.yml up -d
```

Server runs on: `http://localhost:8080`

Verify it's working:
```bash
curl http://localhost:8080/health
```

---

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

- Python 3.11+ and `pip`
- AWS CLI configured with credentials (`aws configure`)
- Git
- Docker Desktop (only for HTTP transport; not needed for stdio)

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

**Note for Windows users:**
- The `.env.example` file is hidden by default. In File Explorer, enable "Show hidden files" (View → Show → Hidden items)
- Or use PowerShell: `Copy-Item .env.example .env` to copy it

#### Step 2: Configure AWS Credentials

The server needs AWS credentials to scan your resources. On your local machine, it uses your `~/.aws` credentials folder.

```bash
# Verify AWS credentials are configured
aws sts get-caller-identity

# If not configured, run:
aws configure
```

#### Step 3: Start the Server

**Linux/Mac:**
```bash
# Start all services (MCP server + Redis)
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f mcp-server
```

**Windows (PowerShell):**
```powershell
# Start all services using Windows-specific configuration
docker-compose -f docker-compose.yml -f docker-compose.windows.yml up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f mcp-server
```

**Important for Windows users:**
- Docker Desktop must have file sharing enabled for your user directory
- Go to: Docker Desktop → Settings → Resources → File Sharing
- Add `C:\Users\YourUsername` (or wherever your `.aws` folder is located)
- Click "Apply & Restart"

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

**Option A: stdio (Recommended -- no bridge needed)**

```json
{
  "mcpServers": {
    "finops-tagging": {
      "command": "python",
      "args": ["-m", "mcp_server.stdio_server"],
      "cwd": "C:\\path\\to\\finops-tag-compliance-mcp"
    }
  }
}
```

Replace the `cwd` path with your actual repository path.

> **Note:** With stdio, Claude Desktop launches the MCP server process directly. No Docker or bridge script needed. Make sure you've run `pip install -e .` in the repository first.

**Option B: HTTP bridge (for Docker deployments)**

```json
{
  "mcpServers": {
    "finops-tagging": {
      "command": "python",
      "args": ["C:\\path\\to\\repo\\scripts\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://localhost:8080"
      }
    }
  }
}
```

Replace `C:\\path\\to\\repo` with your actual repository path. Requires `pip install requests`.

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

# Clean up any existing containers (safe to run even if none exist)
docker stop tagging-redis tagging-mcp-server 2>/dev/null
docker rm tagging-redis tagging-mcp-server 2>/dev/null

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

> **Note**: If you deployed using CloudFormation, the S3 bucket is already created! Skip to Step 3.

If you deployed manually without CloudFormation:
```bash
aws s3 mb s3://finops-mcp-config --region us-east-1
```

#### Step 2: Add SSM and S3 Permissions to EC2 IAM Role

> **Note**: If you deployed using CloudFormation, these permissions are already configured! Skip to Step 3.

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

> **Note**: If you deployed using CloudFormation, the `/home/ec2-user/mcp-policies` folder is already created with a default policy! You just need to restart the container with the volume mount.

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

**"Could not send command to EC2" / "Instances not in a valid state for account"**

This error means the SSM agent on your EC2 instance isn't registered with AWS Systems Manager. 

**Option A: Fix SSM (recommended for future one-click deploys)**

SSH to EC2 and run:
```bash
# Check if SSM agent is installed and running
sudo systemctl status amazon-ssm-agent

# If not running, start it
sudo systemctl start amazon-ssm-agent
sudo systemctl enable amazon-ssm-agent

# If not installed (unlikely on Amazon Linux 2023)
sudo yum install -y amazon-ssm-agent
sudo systemctl start amazon-ssm-agent
sudo systemctl enable amazon-ssm-agent
```

After starting the SSM agent, wait 2-3 minutes for it to register with AWS, then the deploy script should work.

**Option B: Manual workaround (quick fix)**

If you just need to update the policy now, SSH to EC2 and pull from S3 directly (since the S3 upload already succeeded):

```bash
ssh -i your-key.pem ec2-user@YOUR_EC2_IP

# Pull the policy from S3 and restart
aws s3 cp s3://finops-mcp-config/policies/tagging_policy.json /home/ec2-user/mcp-policies/tagging_policy.json
docker restart tagging-mcp-server
```

**"Could not upload to S3"**
- Check S3 bucket exists: `aws s3 ls s3://finops-mcp-config`
- Check your local AWS credentials have `s3:PutObject` permission

**Policy not updating on EC2**
- SSH to EC2 and check: `cat /home/ec2-user/mcp-policies/tagging_policy.json`
- Check Docker logs: `docker logs tagging-mcp-server`
- Verify the volume mount: `docker inspect tagging-mcp-server | grep Mounts -A 10`

---

## Connecting Claude Desktop

There are two ways to connect Claude Desktop to the MCP server:

| Method | When to Use | Bridge Needed? |
|--------|-------------|---------------|
| **stdio** | Local development, single user | No |
| **HTTP bridge** | Remote EC2, shared server, Docker | Yes |

### Prerequisites

1. Python 3.11+ installed on your local machine
2. This repository cloned locally
3. For stdio: `pip install -e .` (in the repository)
4. For HTTP bridge: `pip install requests`

### Configuration

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Linux**: `~/.config/claude/claude_desktop_config.json`

### Option A: stdio (Recommended for local)

Claude Desktop launches the MCP server as a subprocess. No Docker, no bridge, no HTTP.

**Windows:**
```json
{
  "mcpServers": {
    "finops-tagging": {
      "command": "python",
      "args": ["-m", "mcp_server.stdio_server"],
      "cwd": "C:\\Users\\YourName\\Documents\\GitHub\\finops-tag-compliance-mcp"
    }
  }
}
```

**macOS/Linux:**
```json
{
  "mcpServers": {
    "finops-tagging": {
      "command": "python3",
      "args": ["-m", "mcp_server.stdio_server"],
      "cwd": "/home/yourname/finops-tag-compliance-mcp"
    }
  }
}
```

### Option B: HTTP bridge (for remote servers)

Use this when the MCP server runs on a different machine (EC2, Docker, etc.).

**Local Docker deployment (Windows):**
```json
{
  "mcpServers": {
    "finops-tagging": {
      "command": "python",
      "args": ["C:\\Users\\YourName\\Documents\\GitHub\\finops-tag-compliance-mcp\\scripts\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://localhost:8080"
      }
    }
  }
}
```

**Remote EC2 deployment:**
```json
{
  "mcpServers": {
    "finops-tagging": {
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

**macOS/Linux (HTTP bridge):**
```json
{
  "mcpServers": {
    "finops-tagging": {
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
docker build -t tagging-mcp-server . --no-cache
```

Then start containers manually (see EC2 update section below).

### Container Name Conflict

If you see `The container name "/tagging-redis" is already in use`:

```bash
# Remove the old containers first
docker stop tagging-redis tagging-mcp-server 2>/dev/null
docker rm tagging-redis tagging-mcp-server 2>/dev/null

# Then start fresh
docker run -d --name tagging-redis -p 6379:6379 redis:7-alpine
docker run -d --name tagging-mcp-server ...
```

This happens when containers weren't properly removed before redeploying. The `docker-compose down` command may not remove containers that were started with `docker run`.

### Windows: Docker Mount Denied Error

If you see "mounts denied" or "path is not shared from the host" on Windows:

**Error message:**
```
The path /.aws is not shared from the host and is not known to Docker.
You can configure shared paths from Docker -> Preferences... -> Resources -> File Sharing
```

**Solution:**

1. **Enable File Sharing in Docker Desktop:**
   - Open Docker Desktop
   - Go to Settings → Resources → File Sharing
   - Add `C:\Users\YourUsername` to the shared paths list
   - Click "Apply & Restart"

2. **Use the Windows-specific docker-compose file:**
   ```powershell
   # Stop existing containers
   docker-compose down

   # Start with Windows configuration
   docker-compose -f docker-compose.yml -f docker-compose.windows.yml up -d
   ```

3. **Verify the mount path:**
   ```powershell
   # Check that Docker can see your .aws folder
   docker run --rm -v ${env:USERPROFILE}/.aws:/test alpine ls /test
   ```

### Windows: Hidden .env.example File

If you cannot see the `.env.example` file on Windows:

**Solution 1 - Show hidden files:**
1. Open File Explorer
2. Click the "View" tab
3. Check "Hidden items" checkbox
4. You should now see `.env.example`

**Solution 2 - Use PowerShell:**
```powershell
# Copy the file using PowerShell
Copy-Item .env.example .env

# Or check if it exists
Test-Path .env.example
```

### Orphan Containers Running

If you see unexpected containers like `brave_hermann` or other random names:

**Cause:** These are orphan containers from previous runs that weren't properly stopped.

**Solution:**
```bash
# List all containers (running and stopped)
docker ps -a

# Stop and remove all containers
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)

# Or use docker-compose to clean up properly
docker-compose down

# Then start fresh
docker-compose up -d
```

**Prevention:** Always use `docker-compose down` to stop services instead of stopping individual containers.

---

## Updating

### Local

```bash
git pull origin main
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

> **Note**: If you see `compose build requires buildx 0.17 or later`, use plain docker build instead:
> ```bash
> git pull origin main
> docker-compose down
> docker build -t finops-tag-compliance-mcp-mcp-server . --no-cache
> docker-compose up -d
> ```

### EC2

```bash
ssh -i your-key.pem ec2-user@$INSTANCE_IP
cd ~/finops-tag-compliance-mcp
git pull origin main

# Stop and remove existing containers (handles both docker-compose and docker run containers)
docker stop tagging-mcp-server tagging-redis 2>/dev/null
docker rm tagging-mcp-server tagging-redis 2>/dev/null

# Rebuild the image
# Note: Use docker build directly - Amazon Linux's docker-compose may have buildx version issues
docker build -t tagging-mcp-server . --no-cache

# Start Redis
docker run -d --name tagging-redis -p 6379:6379 redis:7-alpine

# Start MCP server
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
docker ps
curl http://localhost:8080/health
```

**Quick one-liner for updates** (after initial setup):
```bash
git pull && docker stop tagging-mcp-server tagging-redis && docker rm tagging-mcp-server tagging-redis && docker build -t tagging-mcp-server . --no-cache && docker run -d --name tagging-redis -p 6379:6379 redis:7-alpine && docker run -d --name tagging-mcp-server -p 8080:8080 -e REDIS_URL=redis://172.17.0.1:6379/0 -e AWS_REGION=us-east-1 -e ENVIRONMENT=production -v $(pwd)/policies:/app/policies:ro -v $(pwd)/data:/app/data -v $(pwd)/logs:/app/logs tagging-mcp-server && sleep 3 && curl http://localhost:8080/health
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

## Production Security Deployment

For production deployments with full security features, use the production CloudFormation template.

### Architecture Overview (Production)

```
┌─────────────────────────────────────────────────────────────────┐
│                        INTERNET                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Application Load Balancer (Public Subnet)           │
│    • TLS termination (ACM certificate)                          │
│    • HTTPS on port 443                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PRIVATE SUBNET                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              MCP Server (EC2)                             │  │
│  │    • API key authentication (AUTH_ENABLED=true)          │  │
│  │    • CORS restriction (CORS_ALLOWED_ORIGINS)             │  │
│  │    • CloudWatch metrics for security alerting            │  │
│  │    • No public IP address                                │  │
│  │    • Inbound from ALB only                               │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              VPC Endpoints                                │  │
│  │    • EC2, S3, CloudWatch, Secrets Manager                │  │
│  │    • No internet routing for AWS API calls               │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Prerequisites

1. ACM certificate for your domain (see below)
2. AWS CLI configured with appropriate permissions
3. Email address for security alerts

### Step 1: Create ACM Certificate (SSL/TLS)

**Why do you need a certificate?**

The production architecture uses an Application Load Balancer (ALB) to provide HTTPS access. Unlike the basic deployment where you access the EC2 directly via HTTP, the production setup encrypts all traffic:

```
Basic:      Internet → HTTP (8080) → EC2 (public IP)
Production: Internet → HTTPS (443) → ALB [certificate] → HTTP (8080) → EC2 (private)
```

The ACM certificate proves to browsers that your domain is legitimate and enables encryption.

**Create the certificate:**

1. Go to **AWS Console → Certificate Manager (ACM)** in your target region (e.g., us-east-1)
2. Click **Request certificate** → **Request a public certificate** → Next
3. Enter your domain name: `mcp.yourdomain.com` (or `*.yourdomain.com` for wildcard)
4. Select **DNS validation** (recommended)
5. Click **Request**

**Validate the certificate:**

ACM needs to verify you own the domain. It provides a CNAME record you must add to your DNS.

- **If your domain is in Route 53**: Click "Create records in Route 53" (automatic)
- **If your domain is elsewhere** (OVH, Gandi, Cloudflare, GoDaddy, etc.):
  1. In ACM, click on your certificate to see the CNAME details
  2. Copy the **CNAME name** (e.g., `_abc123.mcp.yourdomain.com`)
  3. Copy the **CNAME value** (e.g., `_xyz789.acm-validations.aws`)
  4. Go to your DNS provider and create this CNAME record
  5. Wait 5-30 minutes for validation (can take longer depending on DNS propagation)

**Verify validation:**
```bash
# Check if the CNAME is propagated
nslookup _abc123.mcp.yourdomain.com

# Or check certificate status
aws acm describe-certificate --certificate-arn YOUR_CERT_ARN \
  --query 'Certificate.Status'
```

Once status is **"ISSUED"**, copy the certificate ARN for the next step.

### Step 2: Deploy with CloudFormation

**Option A: AWS Console (Recommended for first-time users)**

1. Go to **AWS Console → CloudFormation → Create stack → With new resources**
2. Select **Upload a template file** and upload `infrastructure/cloudformation-production.yaml`
3. Fill in the parameters:
   - **Stack name**: `mcp-tagging-prod`
   - **ProjectName**: `mcp-tagging`
   - **Environment**: `prod`
   - **KeyPairName**: Your EC2 key pair name
   - **ACMCertificateArn**: The ARN of your ACM certificate (from Step 1)
   - **AlertEmail**: Your email for security alerts
   - **CORSAllowedOrigins**: `https://claude.ai` (default)
4. **IMPORTANT**: Leave the **Tags** section empty (tags are defined in the template)
5. Check "I acknowledge that AWS CloudFormation might create IAM resources with custom names"
6. Click **Create stack** and wait for completion (~10-15 minutes)

**Option B: AWS CLI**

```bash
# 1. Get your ACM certificate ARN (create in AWS Console if needed)
ACM_CERT_ARN="arn:aws:acm:us-east-1:123456789012:certificate/xxx"

# 2. Deploy the production stack
aws cloudformation deploy \
  --stack-name mcp-tagging-prod \
  --template-file infrastructure/cloudformation-production.yaml \
  --parameter-overrides \
    ProjectName=mcp-tagging \
    Environment=prod \
    KeyPairName=your-key-pair \
    ACMCertificateArn=$ACM_CERT_ARN \
    AlertEmail=security@example.com \
    CORSAllowedOrigins=https://claude.ai \
  --capabilities CAPABILITY_NAMED_IAM

# 3. Wait for completion
aws cloudformation wait stack-create-complete --stack-name mcp-tagging-prod

# 4. Get outputs
aws cloudformation describe-stacks --stack-name mcp-tagging-prod \
  --query 'Stacks[0].Outputs'
```

### Step 3: Configure DNS (CNAME Record)

After the stack is created, get the ALB DNS name from the CloudFormation outputs:

```bash
ALB_DNS=$(aws cloudformation describe-stacks \
  --stack-name mcp-tagging-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDNS`].OutputValue' \
  --output text)
echo "ALB DNS: $ALB_DNS"
```

Then create a CNAME record at your DNS provider:
- **Type**: CNAME
- **Name/Host**: `mcp` (to create `mcp.yourdomain.com`)
- **Value/Points to**: The ALB DNS name (e.g., `mcp-tagging-alb-prod-xxx.us-east-1.elb.amazonaws.com`)

### Step 4: Connect to EC2 via SSM Session Manager

The EC2 instance is in a private subnet with no public IP. You must use AWS Systems Manager Session Manager to connect.

**Prerequisites: Install SSM Plugin**

- **Windows**: Download and install from https://s3.amazonaws.com/session-manager-downloads/plugin/latest/windows/SessionManagerPluginSetup.exe
- **macOS**: `brew install --cask session-manager-plugin`
- **Linux**: See [AWS documentation](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)

**Connect to the instance:**

```bash
# Get the instance ID from CloudFormation outputs
INSTANCE_ID=$(aws cloudformation describe-stacks \
  --stack-name mcp-tagging-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' \
  --output text)

# Start SSM session
aws ssm start-session --target $INSTANCE_ID --region us-east-1
```

Or use the AWS Console:
1. Go to **EC2 → Instances** → Select your instance
2. Click **Connect** → **Session Manager** tab → **Connect**

### Step 5: Deploy the Application Code

Once connected via SSM, run these commands one at a time (SSM requires single-line commands):

```bash
# 1. Install git (not pre-installed on Amazon Linux 2023)
sudo yum install -y git
```

```bash
# 2. Clone the repository to /opt/tagging-mcp
cd /opt/tagging-mcp && sudo -u ec2-user git clone https://github.com/OptimNow/finops-tag-compliance-mcp.git .
```

```bash
# 3. Checkout the production-security branch (or main for stable release)
cd /opt/tagging-mcp && sudo -u ec2-user git checkout feat/production-security
```

```bash
# 4. Create the .env file manually (UserData may fail to create it)
# First, get the API key from Secrets Manager
API_KEY=$(aws secretsmanager get-secret-value --secret-id mcp-tagging/prod/api-keys --query SecretString --output text | jq -r '.primary_key')
```

```bash
# 5. Create the .env file with all required settings
cat > /opt/tagging-mcp/.env << EOF
AUTH_ENABLED=true
CORS_ALLOWED_ORIGINS=https://claude.ai
TLS_ENABLED=false
CLOUDWATCH_ENABLED=true
CLOUDWATCH_LOG_GROUP=/mcp-tagging/prod
AWS_REGION=us-east-1
ENVIRONMENT=production
REDIS_URL=redis://localhost:6379/0
API_KEYS=$API_KEY
EOF
```

```bash
# 6. Set proper permissions on .env
sudo chmod 600 /opt/tagging-mcp/.env && sudo chown ec2-user:ec2-user /opt/tagging-mcp/.env
```

```bash
# 7. Build the Docker image (may take 2-3 minutes)
cd /opt/tagging-mcp && sudo docker build -t mcp-server .
```

```bash
# 8. Start Redis container for caching
sudo docker run -d --name redis -p 6379:6379 --restart unless-stopped redis:7-alpine redis-server --appendonly yes
```

```bash
# 9. Verify Redis is running
sudo docker ps
```

```bash
# 10. Test Redis connection
sudo docker exec redis redis-cli ping
```

```bash
# 11. Start the MCP server container with host network (to access Redis on localhost)
sudo docker run -d --name mcp-server --network host --env-file /opt/tagging-mcp/.env -v /opt/tagging-mcp/policies:/app/policies:ro -v /opt/tagging-mcp/data:/app/data mcp-server
```

```bash
# 12. Verify both containers are running
sudo docker ps
```

```bash
# 13. Test the health endpoint
curl http://localhost:8080/health
```

The health response should show:
- `"status": "healthy"` or `"degraded"` (degraded is OK if Redis isn't connected yet)
- `"redis_connected": true`
- `"sqlite_connected": true`

**Important Notes:**
- The `.env` file must be created manually because CloudFormation UserData may fail to fetch the API key from Secrets Manager
- Redis runs as a separate container for caching AWS API responses
- The MCP server uses `--network host` to access Redis on localhost

### Step 6: Register EC2 in Target Group (if needed)

The CloudFormation template should automatically register the EC2 instance in the ALB Target Group. However, if you see a 503 error when accessing the ALB, you may need to register it manually:

1. Go to **AWS Console → EC2 → Target Groups**
2. Select `mcp-tagging-tg-prod`
3. Click **Register targets**
4. Select your EC2 instance
5. Click **Include as pending below**
6. Click **Register pending targets**

Wait 30-60 seconds for the health check to pass (status should become "healthy").

### Step 7: Verify the Deployment

**Test health endpoint (from your local machine):**

```bash
# Using the ALB DNS directly
curl https://YOUR_ALB_DNS/health

# Or using your custom domain (after DNS propagation)
curl https://mcp.yourdomain.com/health
```

**Test with API key authentication:**

```bash
# Get the API key from Secrets Manager
API_KEY=$(aws secretsmanager get-secret-value \
  --secret-id mcp-tagging/prod/api-keys \
  --query SecretString --output text | jq -r '.primary_key')

# Test authenticated request
curl -H "Authorization: Bearer $API_KEY" \
  https://mcp.yourdomain.com/health
```

**Test that unauthenticated requests are rejected:**

```bash
# This should return 401 Unauthorized
curl https://mcp.yourdomain.com/mcp/tools
```

### Retrieve API Key from Secrets Manager

**Option A: AWS Console**

1. Go to **AWS Console → Secrets Manager**
2. Search for `mcp-tagging/prod/api-keys`
3. Click on the secret → **Retrieve secret value**
4. Copy the `primary_key` value

**Option B: AWS CLI**

```bash
# Get the secret ARN from CloudFormation outputs
SECRET_ARN=$(aws cloudformation describe-stacks \
  --stack-name mcp-tagging-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`APIKeySecretArn`].OutputValue' \
  --output text)

# Retrieve the API key
API_KEY=$(aws secretsmanager get-secret-value \
  --secret-id $SECRET_ARN \
  --query SecretString \
  --output text | jq -r '.primary_key')

echo "Your API key: $API_KEY"
```

### Configure Claude Desktop (Production)

Add to your Claude Desktop config with the API key:

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "finops-tagging-prod": {
      "command": "python",
      "args": ["C:\\Users\\YourName\\Documents\\GitHub\\finops-tag-compliance-mcp\\scripts\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "https://mcp.optimnow.io",
        "MCP_API_KEY": "YOUR_API_KEY_HERE"
      }
    }
  }
}
```

**Steps:**
1. Replace `C:\\Users\\YourName\\Documents\\GitHub\\` with your actual path to the repository
2. Get your API key from AWS Secrets Manager: `mcp-tagging/prod/api-keys` → `primary_key`
3. Replace `YOUR_API_KEY_HERE` with the actual API key
4. Restart Claude Desktop

**Get the API key via CLI:**
```bash
aws secretsmanager get-secret-value \
  --secret-id mcp-tagging/prod/api-keys \
  --query SecretString --output text | jq -r '.primary_key'
```

**Test the connection** before configuring Claude Desktop:
```powershell
# PowerShell
$env:MCP_SERVER_URL="https://mcp.optimnow.io"
$env:MCP_API_KEY="your-api-key"
python "C:\path\to\scripts\mcp_bridge.py"
# Then type: {"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
```

See also: `examples/claude_desktop_config_production.json` for a complete example configuration.

### Security Features Enabled

| Feature | Configuration | Description |
|---------|--------------|-------------|
| API Key Auth | `AUTH_ENABLED=true` | Bearer token required for all requests |
| CORS Restriction | `CORS_ALLOWED_ORIGINS=https://claude.ai` | Only Claude.ai can make cross-origin requests |
| TLS/HTTPS | ALB with ACM certificate | All traffic encrypted in transit |
| Private Subnet | EC2 in private subnet | No direct internet access |
| VPC Endpoints | EC2, S3, CloudWatch, Secrets Manager | AWS API calls stay within VPC |
| CloudWatch Alarms | Auth failures, CORS violations | SNS alerts for security events |

### Monitor Security Events

```bash
# View recent authentication failures
aws logs filter-log-events \
  --log-group-name /mcp-tagging/prod/security \
  --filter-pattern "authentication_failure"

# Check CloudWatch alarm status
aws cloudwatch describe-alarms \
  --alarm-names mcp-tagging-auth-failures-prod mcp-tagging-cors-violations-prod
```

### Rotate API Keys

```bash
# Generate new key
NEW_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# Update in Secrets Manager
aws secretsmanager update-secret \
  --secret-id $SECRET_ARN \
  --secret-string "{\"primary_key\": \"$NEW_KEY\"}"

# Restart EC2 to pick up new key
INSTANCE_ID=$(aws cloudformation describe-stacks \
  --stack-name mcp-tagging-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' \
  --output text)
aws ec2 reboot-instances --instance-ids $INSTANCE_ID

# Update Claude Desktop config with new key
```

### Production Troubleshooting

**503 Service Temporarily Unavailable**

This means the ALB cannot reach the EC2 instance. Check:

1. **Target Group registration**: Go to EC2 → Target Groups → Check if instance is registered and healthy
2. **Security Group**: Verify the EC2 security group allows inbound on port 8080 from the ALB security group
3. **Container running**: Connect via SSM and run `sudo docker ps` to verify the container is running

**Docker build fails with "Unable to connect to deb.debian.org"**

The Security Group only allows HTTPS (443) outbound by default. For Docker build, you need HTTP (80) temporarily:

1. Go to EC2 → Security Groups → Find the MCP Server security group
2. Add an outbound rule: HTTP (80) to 0.0.0.0/0
3. Run the Docker build
4. **Remove the HTTP rule after build completes** (security best practice)

**Health check shows "redis_connected": false**

Redis container may not be running:

```bash
# Check if Redis is running
sudo docker ps | grep redis

# If not running, start it
sudo docker run -d --name redis -p 6379:6379 --restart unless-stopped redis:7-alpine redis-server --appendonly yes

# Restart MCP server to reconnect
sudo docker restart mcp-server
```

**Cannot connect via SSM Session Manager**

1. Verify the SSM plugin is installed on your local machine
2. Check that the EC2 instance has the `AmazonSSMManagedInstanceCore` policy attached
3. Wait 2-3 minutes after instance launch for SSM agent to register

**UserData script didn't create .env file**

This is a known issue. Create the file manually following Step 5 above.

**Container crashes immediately after starting**

Check the logs:
```bash
sudo docker logs mcp-server
```

Common causes:
- Missing `.env` file
- Invalid environment variables
- Missing volume mounts

---

## Security Recommendations

1. **Restrict AllowedCIDR**: Only allow your IP or VPN CIDR
2. **Use HTTPS**: Put an ALB with SSL certificate in front for production
3. **Enable VPC Flow Logs**: Monitor network traffic
4. **Rotate credentials**: Use AWS Secrets Manager for any secrets
5. **Enable CloudTrail**: Audit all API calls
6. **Enable API Key Authentication**: Set `AUTH_ENABLED=true` and configure `API_KEYS`
7. **Restrict CORS**: Set `CORS_ALLOWED_ORIGINS` to specific origins
8. **Enable CloudWatch Alerting**: Set `CLOUDWATCH_METRICS_ENABLED=true`

See [SECURITY_CONFIGURATION.md](SECURITY_CONFIGURATION.md) for detailed security settings.

---

## Video Demo

Watch a 2-minute demo showing the MCP server in action with Claude Desktop:

[![Watch Demo](https://cdn.loom.com/sessions/thumbnails/ccdf1e1aed4c4236bfa9e81367176376-with-play.gif)](https://www.loom.com/share/ccdf1e1aed4c4236bfa9e81367176376)

**[▶️ Watch the demo on Loom](https://www.loom.com/share/ccdf1e1aed4c4236bfa9e81367176376)**

The demo covers:
- Checking tag compliance across AWS resources
- Identifying untagged resources with cost impact
- Getting ML-powered tag suggestions
- Viewing compliance trends over time

---

## Next Steps

- Read the [User Manual](USER_MANUAL.md) for tool usage and example prompts
- Configure your [Tagging Policy](TAGGING_POLICY_GUIDE.md)
- Review [IAM Permissions](IAM_PERMISSIONS.md) for security best practices
