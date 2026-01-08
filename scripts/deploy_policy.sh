#!/bin/bash
# deploy_policy.sh
# One-click policy deployment to remote EC2
# Usage: ./scripts/deploy_policy.sh

POLICY_FILE="${1:-policies/tagging_policy.json}"
S3_BUCKET="${2:-finops-mcp-config}"
EC2_INSTANCE_ID="${3:-i-0dc314272ccf812db}"
REGION="${4:-us-east-1}"

echo "========================================"
echo "  FinOps MCP Policy Deployment"
echo "========================================"
echo ""

# Step 1: Validate JSON
echo "[1/4] Validating policy JSON..."
if python3 -c "import json; json.load(open('$POLICY_FILE'))" 2>/dev/null; then
    echo "      OK - Valid JSON"
else
    echo "      FAILED - Invalid JSON"
    exit 1
fi

# Step 2: Upload to S3
echo "[2/4] Uploading to S3..."
if aws s3 cp "$POLICY_FILE" "s3://$S3_BUCKET/policies/tagging_policy.json" --region "$REGION"; then
    echo "      OK - Uploaded to s3://$S3_BUCKET/policies/"
else
    echo "      FAILED - Could not upload to S3"
    exit 1
fi

# Step 3: Trigger EC2 to pull new policy and restart
echo "[3/4] Updating EC2 instance..."
COMMAND_ID=$(aws ssm send-command \
    --instance-ids "$EC2_INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --parameters "commands=[\"aws s3 cp s3://$S3_BUCKET/policies/tagging_policy.json /home/ec2-user/mcp-policies/tagging_policy.json && docker restart finops-mcp-server\"]" \
    --region "$REGION" \
    --query "Command.CommandId" \
    --output text)

if [ -z "$COMMAND_ID" ]; then
    echo "      FAILED - Could not send command to EC2"
    exit 1
fi
echo "      OK - Command sent (ID: $COMMAND_ID)"

# Step 4: Wait for completion
echo "[4/4] Waiting for deployment to complete..."
sleep 5

STATUS=$(aws ssm get-command-invocation \
    --command-id "$COMMAND_ID" \
    --instance-id "$EC2_INSTANCE_ID" \
    --region "$REGION" \
    --query "Status" \
    --output text)

if [ "$STATUS" = "Success" ]; then
    echo "      OK - Policy deployed successfully!"
else
    echo "      Status: $STATUS"
fi

echo ""
echo "========================================"
echo "  Deployment Complete!"
echo "========================================"
