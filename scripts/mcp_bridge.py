#!/usr/bin/env python3
"""
MCP Bridge Script for Claude Desktop

This script bridges Claude Desktop's stdio-based MCP protocol to the
FinOps Tag Compliance MCP Server's REST API.

Usage:
    Configure in Claude Desktop's config file:
    
    Windows: %APPDATA%\Claude\claude_desktop_config.json
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
import requests
from typing import Any

# Configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080")
TIMEOUT = 30


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
    try:
        resp = requests.get(f"{MCP_SERVER_URL}/mcp/tools", timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {"tools": data.get("tools", [])}
        }
    except requests.RequestException as e:
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
    
    try:
        resp = requests.post(
            f"{MCP_SERVER_URL}/mcp/tools/call",
            json={"name": tool_name, "arguments": arguments},
            headers={"Content-Type": "application/json"},
            timeout=TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "content": data.get("content", []),
                "isError": data.get("is_error", False)
            }
        }
    except requests.RequestException as e:
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {"code": -32000, "message": f"Server error: {e}"}
        }


def main():
    """Main loop: read JSON-RPC requests from stdin, send responses to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            send_error(None, -32700, "Parse error")
            continue
        
        method = request.get("method", "")
        
        if method == "initialize":
            send_response(handle_initialize(request))
        elif method == "notifications/initialized":
            pass  # No response needed for notifications
        elif method == "tools/list":
            send_response(handle_list_tools(request))
        elif method == "tools/call":
            send_response(handle_call_tool(request))
        else:
            send_error(request.get("id"), -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
