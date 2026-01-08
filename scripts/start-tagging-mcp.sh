#!/bin/bash
# Start/Restart the Tagging MCP Server
# Usage: ./scripts/start-tagging-mcp.sh

set -e

cd /opt/tagging-mcp

echo "=== Stopping existing containers ==="
docker-compose down

echo "=== Building Docker image ==="
docker build -t tagging-mcp-server .

echo "=== Starting containers ==="
docker-compose up -d

echo "=== Waiting for server to start ==="
sleep 5

echo "=== Health check ==="
curl -s http://localhost:8080/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Status: {d[\"status\"]}'); print(f'Redis: {d[\"redis_connected\"]}'); print(f'SQLite: {d[\"sqlite_connected\"]}')"

echo ""
echo "=== Tagging MCP Server is running ==="
echo "Endpoint: http://100.50.91.35:8080"
