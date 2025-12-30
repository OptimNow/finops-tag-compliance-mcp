"""
Allow running the MCP server as a Python module.

Usage:
    python -m mcp_server

This is equivalent to running:
    python run_server.py

Requirements: 14.2, 14.5
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import and run the main entry point
from run_server import main

if __name__ == "__main__":
    main()
