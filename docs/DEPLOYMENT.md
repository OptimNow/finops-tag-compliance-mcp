# Deployment Guide: Tag Compliance MCP Server

This guide covers deploying the MCP server locally and to AWS (development or production).

## Table of Contents

1. [Local Deployment](#1-local-deployment) - Run on your machine
2. [AWS Deployment](#2-aws-deployment)
   - [2.1 Development](#21-development-deployment) - Simple EC2 with public IP
   - [2.2 Production (Secured)](#22-production-secured-deployment) - ALB + HTTPS + API keys
3. [One-Click Tagging Policy Deployment](#3-one-click-tagging-policy-deployment) - Update policies remotely
4. [Connecting Claude Desktop](#4-connecting-claude-desktop)
   - [4.1 Local (stdio)](#41-local-stdio)
   - [4.2 AWS Development (HTTP)](#42-aws-development-http)
   - [4.3 AWS Production (HTTPS + API Key)](#43-aws-production-https--api-key)
   - [4.4 Configuration](#44-configuration)
5. [Monitoring](#5-monitoring)
6. [Updating](#6-updating)
7. [Troubleshooting](#7-troubleshooting)
8. [Cleanup](#8-cleanup)

---

## 1. Local Deployment

Run the MCP server on your local machine for development or personal use.

### Quick Start (stdio - Recommended)

```bash
git clone https://github.com/OptimNow/finops-tag-compliance-mcp.git
cd finops-tag-compliance-mcp
pip install -e .
python -m mcp_server.stdio_server
```

### Quick Start (Docker - HTTP transport)

For Redis caching:

```bash
# Linux/Mac
docker-compose up -d

# Windows
docker-compose -f docker-compose.yml -f docker-compose.windows.yml up -d
```

Server runs on `http://localhost:8080`. Verify: `curl http://localhost:8080/health`

### Prerequisites

- Python 3.11+ and pip
- AWS CLI configured (`aws configure`)
- Docker Desktop (only for HTTP transport)

### Stop/Restart

```bash
docker-compose down      # Stop
docker-compose restart   # Restart
docker-compose down && docker-compose build --no-cache && docker-compose up -d  # Rebuild
```

---

## 2. AWS Deployment

### 2.1 Development Deployment

Simple deployment with EC2 public IP, HTTP access, no authentication. Good for testing.

#### Architecture

```
Internet -> HTTP:8080 -> EC2 (public subnet) -> AWS APIs
```

#### Deploy via CloudFormation (Console)

1. Go to CloudFormation -> Create stack -> With new resources
2. Upload `infrastructure/cloudformation.yaml`
3. Parameters:
   - EnvironmentName: `dev`
   - KeyPairName: Your EC2 key pair
   - VpcId: Your VPC ID
   - SubnetId: A public subnet ID
   - PolicyBucketName: Leave empty for auto-generated name
   - AllowedCIDR: Your IP (e.g., `1.2.3.4/32`) or `0.0.0.0/0` for testing
4. Check "I acknowledge that AWS CloudFormation might create IAM resources"
5. Create stack (5-10 minutes)

#### Deploy Application on EC2

SSH to EC2 and run:

```bash
cd ~
git clone https://github.com/OptimNow/finops-tag-compliance-mcp.git
cd finops-tag-compliance-mcp

docker build -t mcp-server .
docker run -d --name redis -p 6379:6379 redis:7-alpine
docker run -d --name mcp-server -p 8080:8080 \
  -e REDIS_URL=redis://172.17.0.1:6379/0 \
  -e AWS_REGION=us-east-1 \
  -v $(pwd)/policies:/app/policies:ro \
  -v $(pwd)/data:/app/data \
  mcp-server

curl http://localhost:8080/health
```

#### Get Connection Info

```bash
# Elastic IP
aws cloudformation describe-stacks --stack-name tagging-mcp-server \
  --query 'Stacks[0].Outputs[?OutputKey==`ElasticIP`].OutputValue' --output text

# S3 Bucket name
aws cloudformation describe-stacks --stack-name tagging-mcp-server \
  --query 'Stacks[0].Outputs[?OutputKey==`PolicyBucketName`].OutputValue' --output text
```

---

### 2.2 Production (Secured) Deployment

Full security: ALB with HTTPS, API key authentication, EC2 in private subnet, VPC endpoints.

#### Architecture

```
Internet -> HTTPS:443 -> ALB (public) -> HTTP:8080 -> EC2 (private subnet) -> VPC Endpoints -> AWS APIs
```

Features:
- TLS termination at ALB (ACM certificate)
- API key authentication (Secrets Manager)
- EC2 in private subnet (no public IP)
- VPC endpoints for AWS API calls
- CloudWatch alarms for security events
- S3 bucket for tagging policy configuration

#### Prerequisites

1. ACM Certificate for your domain (e.g., `*.yourdomain.com`)
   - Go to Certificate Manager -> Request certificate
   - Add CNAME record to your DNS for validation
   - Wait for status "Issued"

2. DNS access to create CNAME record pointing to ALB

#### Deploy via CloudFormation (Console)

1. Go to CloudFormation -> Create stack -> With new resources
2. Upload `infrastructure/cloudformation-production.yaml`
3. Parameters:
   - ProjectName: `mcp-tagging`
   - Environment: `prod`
   - KeyPairName: Your EC2 key pair
   - ACMCertificateArn: ARN of your certificate
   - AlertEmail: Email for security alerts
   - CORSAllowedOrigins: `https://claude.ai`
   - PolicyBucketName: Leave empty for auto-generated name
4. IMPORTANT: Leave Tags section empty
5. Check "I acknowledge that AWS CloudFormation might create IAM resources"
6. Create stack (10-15 minutes)

#### Configure DNS

After stack creation:

1. Get ALB DNS from CloudFormation Outputs (`LoadBalancerDNS`)
2. Create CNAME record in your DNS provider:
   - Name: `mcp` (creates `mcp.yourdomain.com`)
   - Value: ALB DNS name

#### Connect to EC2 via SSM

The EC2 is in a private subnet - use SSM Session Manager:

Via Console: EC2 -> Instances -> Select instance -> Connect -> Session Manager

Via CLI:
```bash
INSTANCE_ID=$(aws cloudformation describe-stacks --stack-name mcp-tagging-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' --output text)
aws ssm start-session --target $INSTANCE_ID --region us-east-1
```

#### Manual Setup (UserData typically does not execute)

The CloudFormation UserData script typically does not execute on first boot. You need to set up the environment manually via SSM.

**Step 1: Install required packages**

```bash
sudo yum install -y git docker jq
```

**Step 2: Start Docker**

```bash
sudo systemctl start docker
```

```bash
sudo systemctl enable docker
```

```bash
sudo usermod -aG docker ec2-user
```

**Step 3: Create app directory and clone repo**

```bash
sudo mkdir -p /opt/tagging-mcp
```

```bash
cd /opt/tagging-mcp
```

```bash
sudo git clone https://github.com/OptimNow/finops-tag-compliance-mcp.git .
```

```bash
sudo chown -R ec2-user:ec2-user /opt/tagging-mcp
```

**Step 4: Exit and reconnect SSM** (required for docker group to take effect)

Close the SSM session and reconnect via EC2 Console -> Connect -> Session Manager.

#### Deploy Application on EC2

After reconnecting to SSM, run these commands one at a time.

**Step 5: Get the API key**

```bash
aws secretsmanager get-secret-value --secret-id mcp-tagging/prod/api-keys --query SecretString --output text
```

Copy the `primary_key` value from the JSON output (e.g., `TSvlygVknr1XhJ4UUEz6VEW5lrvjgDY6`).

**Step 6: Create the .env file** (replace YOUR_API_KEY with the value from step 5)

```bash
sudo tee /opt/tagging-mcp/.env << 'EOF'
AUTH_ENABLED=true
CORS_ALLOWED_ORIGINS=https://claude.ai
CLOUDWATCH_ENABLED=true
CLOUDWATCH_LOG_GROUP=/mcp-tagging/prod
AWS_REGION=ca-central-1
ENVIRONMENT=production
REDIS_URL=redis://localhost:6379/0
API_KEYS=YOUR_API_KEY
EOF
```

```bash
sudo chmod 600 /opt/tagging-mcp/.env
```

```bash
sudo chown ec2-user:ec2-user /opt/tagging-mcp/.env
```

**Step 7: Temporarily open port 80 outbound** (required for Docker build)

The EC2 Security Group blocks outbound HTTP by default. Docker build needs to download packages from Debian repositories.

1. Go to EC2 Console -> Security Groups
2. Find the EC2 security group (`mcp-tagging-prod-ec2-sg`)
3. Edit Outbound rules -> Add rule:
   - Type: `HTTP`
   - Port: `80`
   - Destination: `0.0.0.0/0`
   - Description: `Temporary - Docker build`
4. Save rules

**Step 8: Build Docker image**

```bash
cd /opt/tagging-mcp
```

```bash
sudo docker build -t mcp-server .
```

**Step 9: Remove temporary outbound rule**

After the build succeeds, go back to Security Groups and remove the HTTP outbound rule you added in Step 7.

**Step 10: Start Redis**

```bash
sudo docker run -d --name redis -p 6379:6379 --restart unless-stopped redis:7-alpine
```

**Step 11: Start MCP Server**

```bash
sudo docker run -d --name mcp-server --network host --env-file /opt/tagging-mcp/.env -v /opt/tagging-mcp/policies:/app/policies:ro -v /opt/tagging-mcp/data:/app/data --restart unless-stopped mcp-server
```

**Step 12: Verify the server is running**

```bash
curl http://localhost:8080/health
```

Expected output: `{"status":"healthy",...}`

#### Verify HTTPS Access

From your local machine:

```bash
curl https://mcp.yourdomain.com/health
```

---

## 3. One-Click Tagging Policy Deployment

Update your tagging policy from your local machine and deploy to EC2 with one command.

### How It Works

```
Local Machine -> S3 Bucket -> EC2 pulls and restarts
```

### Get Your Values

For Development:
```bash
# S3 Bucket
aws cloudformation describe-stacks --stack-name tagging-mcp-server \
  --query 'Stacks[0].Outputs[?OutputKey==`PolicyBucketName`].OutputValue' --output text

# Instance ID
aws cloudformation describe-stacks --stack-name tagging-mcp-server \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' --output text
```

For Production:
```bash
# S3 Bucket
aws cloudformation describe-stacks --stack-name mcp-tagging-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`PolicyConfigBucketName`].OutputValue' --output text

# Instance ID
aws cloudformation describe-stacks --stack-name mcp-tagging-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' --output text
```

### Deploy Policy

Windows:
```powershell
.\scripts\deploy_policy.ps1 -S3Bucket "YOUR_BUCKET" -EC2InstanceId "i-xxxxx" -Region "us-east-1"
```

Mac/Linux:
```bash
./scripts/deploy_policy.sh YOUR_BUCKET i-xxxxx us-east-1
```

### First-Time Setup on EC2

SSH/SSM to EC2 and run once:

```bash
# Dev
mkdir -p /home/ec2-user/finops-tag-compliance-mcp/policies

# Prod
mkdir -p /opt/tagging-mcp/policies
```

---

## 4. Connecting Claude Desktop

### 4.1 Local (stdio)

No bridge needed. Claude Desktop launches the server directly.

Windows (`%APPDATA%\Claude\claude_desktop_config.json`):
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

macOS (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "finops-tagging": {
      "command": "python3",
      "args": ["-m", "mcp_server.stdio_server"],
      "cwd": "/Users/yourname/finops-tag-compliance-mcp"
    }
  }
}
```

### 4.2 AWS Development (HTTP)

Uses HTTP bridge to connect to EC2.

```json
{
  "mcpServers": {
    "finops-tagging-dev": {
      "command": "python",
      "args": ["C:\\path\\to\\scripts\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://YOUR_EC2_ELASTIC_IP:8080"
      }
    }
  }
}
```

Get Elastic IP:
```bash
aws cloudformation describe-stacks --stack-name tagging-mcp-server \
  --query 'Stacks[0].Outputs[?OutputKey==`ElasticIP`].OutputValue' --output text
```

### 4.3 AWS Production (HTTPS + API Key)

Uses HTTPS bridge with API key authentication.

```json
{
  "mcpServers": {
    "finops-tagging-prod": {
      "command": "python",
      "args": ["C:\\path\\to\\scripts\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "https://mcp.yourdomain.com",
        "MCP_API_KEY": "YOUR_API_KEY_HERE"
      }
    }
  }
}
```

Get API key:
```bash
aws secretsmanager get-secret-value --secret-id mcp-tagging/prod/api-keys \
  --query SecretString --output text | jq -r '.primary_key'
```

Test before configuring Claude Desktop:
```powershell
$env:MCP_SERVER_URL="https://mcp.yourdomain.com"
$env:MCP_API_KEY="your-api-key"
python scripts\mcp_bridge.py
# Type: {"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
```

### 4.4 Configuration

#### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Environment name | `development` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `REDIS_URL` | Redis connection | `redis://redis:6379/0` |
| `AWS_REGION` | AWS region | `us-east-1` |
| `AUTH_ENABLED` | Enable API key auth | `false` |
| `API_KEYS` | Comma-separated API keys | - |
| `CORS_ALLOWED_ORIGINS` | Allowed CORS origins | `*` |

#### Tagging Policy

Edit `policies/tagging_policy.json`:

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

See [Tagging Policy Guide](TAGGING_POLICY_GUIDE.md) for details.

---

## 5. Monitoring

### Health Check

```bash
# Local/Dev
curl http://localhost:8080/health

# Production
curl https://mcp.yourdomain.com/health
```

### View Logs

```bash
# Docker
docker logs -f mcp-server

# CloudWatch (Production)
aws logs tail /mcp-tagging/prod --follow
```

### Container Status

```bash
docker ps
```

---

## 6. Updating

### Local

```bash
git pull origin main
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### AWS (Dev or Prod)

SSH/SSM to EC2:

```bash
cd ~/finops-tag-compliance-mcp  # Dev
# or
cd /opt/tagging-mcp             # Prod

git pull origin main
docker stop mcp-server redis
docker rm mcp-server redis
docker build -t mcp-server . --no-cache
docker run -d --name redis -p 6379:6379 redis:7-alpine
docker run -d --name mcp-server [your-options] mcp-server
curl http://localhost:8080/health
```

---

## 7. Troubleshooting

### Server Not Responding

```bash
docker ps                    # Check containers running
docker logs mcp-server       # Check logs
docker restart mcp-server    # Restart
```

### AWS API Errors

```bash
# Local
aws sts get-caller-identity

# EC2
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/
```

### Redis Connection Issues

```bash
docker logs redis
docker exec redis redis-cli ping
```

### Claude Desktop Not Connecting

1. Check bridge script path is correct
2. Verify `pip install requests` was run
3. Test server: `curl http://SERVER:8080/health`
4. Check Claude Desktop logs

### Production: 503 Error

1. Check Target Group health in EC2 Console
2. Verify EC2 security group allows port 8080 from ALB
3. Check container is running via SSM

### Production: Docker Build Fails (Network)

The EC2 is in a private subnet. Docker build needs internet access via NAT Gateway.
If build fails, check NAT Gateway is working:
```bash
curl -I https://github.com
```

### SSM Session Manager Not Working

```bash
sudo systemctl status amazon-ssm-agent
sudo systemctl start amazon-ssm-agent
```

---

## 8. Cleanup

### Local

```bash
docker-compose down -v
```

### AWS Development

```bash
aws cloudformation delete-stack --stack-name tagging-mcp-server
```

### AWS Production

```bash
# Empty S3 bucket first (required)
BUCKET=$(aws cloudformation describe-stacks --stack-name mcp-tagging-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`PolicyConfigBucketName`].OutputValue' --output text)
aws s3 rm s3://$BUCKET --recursive

# Delete stack
aws cloudformation delete-stack --stack-name mcp-tagging-prod
```

---

## Next Steps

- [User Manual](USER_MANUAL.md) - Tool usage and example prompts
- [Tagging Policy Guide](TAGGING_POLICY_GUIDE.md) - Configure your policy
- [IAM Permissions](IAM_PERMISSIONS.md) - Security best practices
