@echo off
REM FinOps Tag Compliance MCP Server - Persistent Storage Setup (Windows)
REM This script sets up persistent storage for compliance history and audit logs

echo 🔧 Setting up persistent storage for FinOps MCP Server...

REM Create data directory if it doesn't exist
if not exist "data" (
    echo 📁 Creating data directory...
    mkdir data
    echo ✅ Created data directory
) else (
    echo ✅ data directory already exists
)

REM Create .env file from example if it doesn't exist
if not exist ".env" (
    echo 📝 Creating .env file from .env.example...
    copy .env.example .env
    echo ✅ Created .env file
    echo 💡 You can customize settings in .env file
) else (
    echo ✅ .env file already exists
)

echo.
echo 🎉 Persistent storage setup complete!
echo.
echo 📊 Your compliance history will be stored in:
echo    - Audit logs: ./data/audit_logs.db
echo    - Compliance history: ./data/compliance_history.db
echo.
echo 🚀 Next steps:
echo    1. Start the server: docker-compose up -d
echo    2. Run compliance checks to populate history
echo    3. Use get_violation_history tool to view trends
echo.
echo 💾 Data persistence:
echo    - History survives container restarts
echo    - History survives container rebuilds
echo    - Backup ./data/ folder to preserve history
echo.
pause