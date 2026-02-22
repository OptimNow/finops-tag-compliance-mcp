#!/bin/bash
# deploy_ecs.sh — Build, push, and deploy MCP server to ECS Fargate
#
# Usage:
#   ./scripts/deploy_ecs.sh                  # Build + push + deploy
#   ./scripts/deploy_ecs.sh --push-only      # Push existing image only
#   ./scripts/deploy_ecs.sh --deploy-only    # Force new deployment (no build)
#
# Environment variables (all have defaults from CloudFormation stack outputs):
#   AWS_REGION       - AWS region (default: us-east-1)
#   AWS_ACCOUNT_ID   - AWS account ID (default: auto-detected via STS)
#   ECR_REPO         - ECR repository name (default: mcp-tagging-prod)
#   ECS_CLUSTER      - ECS cluster name (default: mcp-tagging-cluster-prod)
#   ECS_SERVICE      - ECS service name (default: mcp-tagging-service-prod)
#   IMAGE_TAG        - Docker image tag (default: latest)
#
# Prerequisites:
#   - AWS CLI v2 configured with appropriate permissions
#   - Docker running (for build/push)
#   - ECR repository exists

set -euo pipefail

# Configuration — all overridable via environment variables
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPO="${ECR_REPO:-mcp-tagging-prod}"
ECS_CLUSTER="${ECS_CLUSTER:-mcp-tagging-cluster-prod}"
ECS_SERVICE="${ECS_SERVICE:-mcp-tagging-service-prod}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Auto-detect account ID if not set
if [ -z "${AWS_ACCOUNT_ID:-}" ]; then
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region "${AWS_REGION}")
fi

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"

# Parse arguments
PUSH_ONLY=false
DEPLOY_ONLY=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --push-only)  PUSH_ONLY=true; shift ;;
        --deploy-only) DEPLOY_ONLY=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "=== MCP Tagging Server — ECS Fargate Deploy ==="
echo "Region:  ${AWS_REGION}"
echo "Account: ${AWS_ACCOUNT_ID}"
echo "Cluster: ${ECS_CLUSTER}"
echo "Service: ${ECS_SERVICE}"
echo "ECR:     ${ECR_URI}:${IMAGE_TAG}"
echo ""

# Step 1: ECR Login
echo "[1/4] Logging in to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
echo ""

if [ "$DEPLOY_ONLY" = false ]; then
    # Step 2: Build Docker image
    if [ "$PUSH_ONLY" = false ]; then
        echo "[2/4] Building Docker image..."
        docker build -t "${ECR_REPO}:${IMAGE_TAG}" .
        echo ""
    else
        echo "[2/4] Skipping build (--push-only)"
        echo ""
    fi

    # Step 3: Tag and push to ECR
    echo "[3/4] Pushing to ECR..."
    docker tag "${ECR_REPO}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
    docker push "${ECR_URI}:${IMAGE_TAG}"
    echo ""
else
    echo "[2/4] Skipping build (--deploy-only)"
    echo "[3/4] Skipping push (--deploy-only)"
    echo ""
fi

# Step 4: Force new deployment
echo "[4/4] Forcing new ECS deployment..."
aws ecs update-service \
    --cluster "${ECS_CLUSTER}" \
    --service "${ECS_SERVICE}" \
    --force-new-deployment \
    --region "${AWS_REGION}" \
    --query 'service.{Status:status,Desired:desiredCount,Running:runningCount}' \
    --output table

echo ""
echo "Waiting for service to stabilize..."
aws ecs wait services-stable \
    --cluster "${ECS_CLUSTER}" \
    --services "${ECS_SERVICE}" \
    --region "${AWS_REGION}"

echo ""
echo "=== Deployment complete ==="
echo ""

# Show final status
aws ecs describe-services \
    --cluster "${ECS_CLUSTER}" \
    --services "${ECS_SERVICE}" \
    --region "${AWS_REGION}" \
    --query 'services[0].{Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount,LatestEvent:events[0].message}' \
    --output table

echo ""
echo "Health check: curl -s https://mcp.optimnow.io/health | python -m json.tool"
