# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

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
