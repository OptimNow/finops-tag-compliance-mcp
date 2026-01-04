#!/bin/bash

# FinOps Tag Compliance MCP Server - Persistent Storage Setup
# This script sets up persistent storage for compliance history and audit logs

set -e

echo "🔧 Setting up persistent storage for FinOps MCP Server..."

# Create data directory if it doesn't exist
if [ ! -d "./data" ]; then
    echo "📁 Creating ./data directory..."
    mkdir -p ./data
    echo "✅ Created ./data directory"
else
    echo "✅ ./data directory already exists"
fi

# Set proper permissions
echo "🔒 Setting permissions on ./data directory..."
chmod 755 ./data

# Create .env file from example if it doesn't exist
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from .env.example..."
    cp .env.example .env
    echo "✅ Created .env file"
    echo "💡 You can customize settings in .env file"
else
    echo "✅ .env file already exists"
fi

# Check if docker-compose.yml has the correct volume mount
if grep -q "./data:/app/data" docker-compose.yml; then
    echo "✅ Docker volume mount is configured correctly"
else
    echo "❌ Docker volume mount not found in docker-compose.yml"
    echo "   Please add this to the mcp-server service volumes:"
    echo "   - ./data:/app/data"
    exit 1
fi

echo ""
echo "🎉 Persistent storage setup complete!"
echo ""
echo "📊 Your compliance history will be stored in:"
echo "   - Audit logs: ./data/audit_logs.db"
echo "   - Compliance history: ./data/compliance_history.db"
echo ""
echo "🚀 Next steps:"
echo "   1. Start the server: docker-compose up -d"
echo "   2. Run compliance checks to populate history"
echo "   3. Use get_violation_history tool to view trends"
echo ""
echo "💾 Data persistence:"
echo "   - History survives container restarts"
echo "   - History survives container rebuilds"
echo "   - Backup ./data/ folder to preserve history"
echo ""