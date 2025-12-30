@echo off
REM Regression test runner for FinOps Tag Compliance MCP Server
REM This is a convenience wrapper around run_tests.py for Windows

setlocal enabledelayedexpansion

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0

REM Run the Python test runner with all arguments passed through
python "%SCRIPT_DIR%run_tests.py" %*

endlocal
