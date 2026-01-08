# One-Click Policy Deployment Setup

This guide sets up a simple workflow where you edit your tagging policy locally and deploy it to EC2 with a single command.

## How It Works

```
┌─────────────────┐     ┌─────────────┐     ┌─────────────┐
│ Local Machine   │────▶│    S3       │────▶│    EC2      │
│ Edit policy     │     │ (staging)   │     │ Pull & restart
└─────────────────┘     └─────────────┘     └─────────────┘
```

1. You edit `policies/tagging_policy.json` locally
2. Run `.\scripts\deploy_policy.ps1`
3. Script uploads to S3, then tells EC2 to pull it and restart Docker

## One-Time Setup

### Step 1: Create S3 Bucket

```powershell
aws s3 mb s3://finops-mcp-config --region us-east-1
```

### Step 2: Configure EC2 for SSM

Your EC2 instance needs the SSM agent and IAM permissions. Add this to your IAM role:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ssm:UpdateInstanceInformation",
                "ssmmessages:CreateControlChannel",
                "ssmmessages:CreateDataChannel",
                "ssmmessages:OpenControlChannel",
                "ssmmessages:OpenDataChannel"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject"
            ],
            "Resource": "arn:aws:s3:::finops-mcp-config/*"
        }
    ]
}
```

### Step 3: Set Up EC2 Policies Folder

SSH into your EC2 and run once:

```bash
# Create policies folder
mkdir -p /home/ec2-user/mcp-policies

# Copy current policy from container
docker cp finops-mcp-server:/app/policies/tagging_policy.json /home/ec2-user/mcp-policies/

# Restart container with mounted volume
docker rm -f finops-mcp-server
docker run -d -p 8080:8080 --name finops-mcp-server \
  -v /home/ec2-user/mcp-policies:/app/policies \
  finops-mcp-server
```

### Step 4: Update Script Variables

Edit `scripts/deploy_policy.ps1` and set your values:

```powershell
$S3Bucket = "finops-mcp-config"        # Your S3 bucket name
$EC2InstanceId = "i-0dc314272ccf812db" # Your EC2 instance ID
$Region = "us-east-1"                   # Your AWS region
```

## Daily Usage

After setup, deploying a policy update is just:

```powershell
# Edit your policy
notepad policies/tagging_policy.json

# Deploy with one command
.\scripts\deploy_policy.ps1
```

That's it! The script:
1. Validates your JSON
2. Uploads to S3
3. Tells EC2 to pull the new policy
4. Restarts the Docker container

## Troubleshooting

### "Could not send command to EC2"
- Check EC2 has SSM agent running: `sudo systemctl status amazon-ssm-agent`
- Check IAM role has SSM permissions
- Verify instance ID is correct

### "Could not upload to S3"
- Check S3 bucket exists
- Check your local AWS credentials have s3:PutObject permission

### Policy not updating
- SSH to EC2 and check: `cat /home/ec2-user/mcp-policies/tagging_policy.json`
- Check Docker logs: `docker logs finops-mcp-server`
