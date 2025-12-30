#!/bin/bash
# Regression test runner for FinOps Tag Compliance MCP Server
# This is a convenience wrapper around run_tests.py for Unix-like systems

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Run the Python test runner with all arguments passed through
python3 "$SCRIPT_DIR/run_tests.py" "$@"
