#!/bin/bash
# Deploy script for EC2 MCP server
# Run from /opt/tagging-mcp directory with: sudo ./scripts/deploy_ec2.sh

set -e

echo "=== Pulling latest code ==="
git pull

echo "=== Building Docker image ==="
docker build -t mcp-server .

echo "=== Stopping existing container ==="
docker stop mcp-server 2>/dev/null || true
docker rm mcp-server 2>/dev/null || true

echo "=== Starting new container ==="
docker run -d \
  --name mcp-server \
  --network mcp-network \
  -p 8080:8080 \
  --env-file .env \
  -v /opt/tagging-mcp/data:/app/data \
  -v /opt/tagging-mcp/policies:/app/policies \
  mcp-server

echo "=== Waiting for startup ==="
sleep 3

echo "=== Container logs ==="
docker logs mcp-server --tail 30

echo "=== Deploy complete ==="
