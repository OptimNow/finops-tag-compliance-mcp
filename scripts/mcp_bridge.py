# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

#!/usr/bin/env python3
"""
MCP Bridge Script for Claude Desktop

This script bridges Claude Desktop's stdio-based MCP protocol to the
FinOps Tag Compliance MCP Server's REST API.

Usage:
    Configure in Claude Desktop's config file:
    
    Windows: %APPDATA%\\Claude\\claude_desktop_config.json
    macOS: ~/Library/Application Support/Claude/claude_desktop_config.json
    
    {
      "mcpServers": {
        "finops-tag-compliance": {
          "command": "python",
          "args": ["<path-to-repo>/scripts/mcp_bridge.py"],
          "env": {
            "MCP_SERVER_URL": "http://localhost:8080"
          }
        }
      }
    }
"""

import json
import os
import sys
import traceback
import requests
from typing import Any

# Configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080")
TIMEOUT = 30


def log(msg: str) -> None:
    """Log to stderr (shows in Claude Desktop MCP logs)."""
    print(f"[finops-bridge] {msg}", file=sys.stderr, flush=True)


def send_response(response: dict) -> None:
    """Send a JSON-RPC response to stdout."""
    print(json.dumps(response), flush=True)


def send_error(id: Any, code: int, message: str) -> None:
    """Send a JSON-RPC error response."""
    send_response({
        "jsonrpc": "2.0",
        "id": id,
        "error": {"code": code, "message": message}
    })


def handle_initialize(request: dict) -> dict:
    """Handle the initialize request."""
    log(f"Initializing, server URL: {MCP_SERVER_URL}")
    return {
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "finops-tag-compliance",
                "version": "0.1.0"
            }
        }
    }


def handle_list_tools(request: dict) -> dict:
    """Handle tools/list by calling the REST API."""
    log(f"Listing tools from {MCP_SERVER_URL}/mcp/tools")
    try:
        resp = requests.get(f"{MCP_SERVER_URL}/mcp/tools", timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        tools = data.get("tools", [])
        log(f"Got {len(tools)} tools")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {"tools": tools}
        }
    except requests.RequestException as e:
        log(f"Error listing tools: {e}")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {"code": -32000, "message": f"Server error: {e}"}
        }


def handle_call_tool(request: dict) -> dict:
    """Handle tools/call by calling the REST API."""
    params = request.get("params", {})
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    
    log(f"Calling tool: {tool_name}")
    try:
        resp = requests.post(
            f"{MCP_SERVER_URL}/mcp/tools/call",
            json={"name": tool_name, "arguments": arguments},
            headers={"Content-Type": "application/json"},
            timeout=TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
        log(f"Tool {tool_name} completed")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "content": data.get("content", []),
                "isError": data.get("is_error", False)
            }
        }
    except requests.RequestException as e:
        log(f"Error calling tool {tool_name}: {e}")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {"code": -32000, "message": f"Server error: {e}"}
        }


def main():
    """Main loop: read JSON-RPC requests from stdin, send responses to stdout."""
    log("Bridge started")
    
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            
            try:
                request = json.loads(line)
            except json.JSONDecodeError as e:
                log(f"JSON parse error: {e}")
                send_error(None, -32700, "Parse error")
                continue
            
            method = request.get("method", "")
            log(f"Received method: {method}")
            
            try:
                if method == "initialize":
                    send_response(handle_initialize(request))
                elif method == "notifications/initialized":
                    log("Initialized notification received")
                    # No response needed for notifications
                elif method == "tools/list":
                    send_response(handle_list_tools(request))
                elif method == "tools/call":
                    send_response(handle_call_tool(request))
                else:
                    log(f"Unknown method: {method}")
                    send_error(request.get("id"), -32601, f"Method not found: {method}")
            except Exception as e:
                log(f"Error handling {method}: {e}")
                log(traceback.format_exc())
                send_error(request.get("id"), -32000, str(e))
                
    except Exception as e:
        log(f"Fatal error: {e}")
        log(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
