# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

#!/usr/bin/env python3
"""
MCP Bridge Script for Claude Desktop

This script bridges Claude Desktop's stdio-based MCP protocol to the
Tagging MCP Server's REST API.

Usage:
    Configure in Claude Desktop's config file:

    Windows: %APPDATA%\\Claude\\claude_desktop_config.json
    macOS: ~/Library/Application Support/Claude/claude_desktop_config.json

    Development (no authentication):
    {
      "mcpServers": {
        "tagging-mcp": {
          "command": "python",
          "args": ["<path-to-repo>/scripts/mcp_bridge.py"],
          "env": {
            "MCP_SERVER_URL": "http://localhost:8080"
          }
        }
      }
    }

    Production (with authentication and HTTPS):
    {
      "mcpServers": {
        "tagging-mcp": {
          "command": "python",
          "args": ["<path-to-repo>/scripts/mcp_bridge.py"],
          "env": {
            "MCP_SERVER_URL": "https://your-alb.example.com",
            "MCP_API_KEY": "your-api-key-here"
          }
        }
      }
    }

Environment Variables:
    MCP_SERVER_URL: URL of the MCP server (default: http://localhost:8080)
    MCP_API_KEY: API key for authentication (optional, required for production)
    MCP_VERIFY_TLS: Set to "false" to disable TLS verification (dev only)

Tool Search Optimization (NEW - January 2026):
    Enable Tool Search to reduce token usage by 85% with defer_loading!

    See examples/claude_desktop_config_remote.json for complete configuration
    with Tool Search optimization enabled, or read the detailed guide at:
    docs/TOOL_SEARCH_CONFIGURATION.md

    Key benefits:
    - 85% reduction in token usage for tool definitions
    - Faster response times
    - Better tool selection accuracy
    - No code changes required to this script

Requirements: 22.1, 22.2, 22.3, 22.4, 22.5
"""

import json
import os
import sys
import traceback
import requests
from typing import Any

# Configuration (Requirements: 22.1, 22.2, 22.4)
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080")
MCP_API_KEY = os.getenv("MCP_API_KEY", "")  # Requirement 22.2
MCP_VERIFY_TLS = os.getenv("MCP_VERIFY_TLS", "true").lower() != "false"  # Requirement 22.5
# Timeout increased to 120s to support multi-region scans which can take 50-60s
TIMEOUT = int(os.getenv("MCP_TIMEOUT", "120"))


def log(msg: str) -> None:
    """Log to stderr (shows in Claude Desktop MCP logs).

    Note: Never log the API key or other sensitive information.
    Requirement 22.3
    """
    print(f"[tagging-bridge] {msg}", file=sys.stderr, flush=True)


def get_auth_headers() -> dict:
    """
    Build authentication headers for requests.

    Returns headers dict with Authorization if API key is configured.
    Never logs or exposes the API key.

    Requirements: 22.1, 22.3
    """
    headers = {"Content-Type": "application/json"}
    if MCP_API_KEY:
        headers["Authorization"] = f"Bearer {MCP_API_KEY}"
    return headers


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
    # Log connection info without exposing API key (Requirement 22.3)
    auth_status = "with authentication" if MCP_API_KEY else "without authentication"
    tls_status = "TLS verification enabled" if MCP_VERIFY_TLS else "TLS verification DISABLED"
    log(f"Initializing, server URL: {MCP_SERVER_URL} ({auth_status}, {tls_status})")
    return {
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "tagging-mcp",
                "version": "0.1.0"
            }
        }
    }


def handle_auth_error(request_id: Any, response: requests.Response) -> dict:
    """
    Handle authentication errors gracefully.

    Never exposes the API key in error messages.

    Requirements: 22.3
    """
    if response.status_code == 401:
        log("Authentication failed - check MCP_API_KEY configuration")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32001,
                "message": "Authentication failed. Please check your API key configuration."
            }
        }
    elif response.status_code == 403:
        log("Access forbidden - API key may not have required permissions")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32002,
                "message": "Access forbidden. Your API key may not have the required permissions."
            }
        }
    return None


def handle_list_tools(request: dict) -> dict:
    """
    Handle tools/list by calling the REST API.

    Requirements: 22.1, 22.4, 22.5
    """
    log(f"Listing tools from {MCP_SERVER_URL}/mcp/tools")
    try:
        resp = requests.get(
            f"{MCP_SERVER_URL}/mcp/tools",
            headers=get_auth_headers(),  # Requirement 22.1
            timeout=TIMEOUT,
            verify=MCP_VERIFY_TLS,  # Requirement 22.5
        )

        # Handle authentication errors (Requirement 22.3)
        auth_error = handle_auth_error(request.get("id"), resp)
        if auth_error:
            return auth_error

        resp.raise_for_status()
        data = resp.json()
        tools = data.get("tools", [])
        log(f"Got {len(tools)} tools")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {"tools": tools}
        }
    except requests.exceptions.SSLError as e:
        log(f"TLS/SSL error: {e}")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {
                "code": -32003,
                "message": "TLS certificate verification failed. Check server certificate or set MCP_VERIFY_TLS=false for development."
            }
        }
    except requests.RequestException as e:
        log(f"Error listing tools: {e}")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {"code": -32000, "message": f"Server error: {e}"}
        }


def handle_call_tool(request: dict) -> dict:
    """
    Handle tools/call by calling the REST API.

    Requirements: 22.1, 22.4, 22.5
    """
    params = request.get("params", {})
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    log(f"Calling tool: {tool_name}")
    try:
        resp = requests.post(
            f"{MCP_SERVER_URL}/mcp/tools/call",
            json={"name": tool_name, "arguments": arguments},
            headers=get_auth_headers(),  # Requirement 22.1
            timeout=TIMEOUT,
            verify=MCP_VERIFY_TLS,  # Requirement 22.5
        )

        # Handle authentication errors (Requirement 22.3)
        auth_error = handle_auth_error(request.get("id"), resp)
        if auth_error:
            return auth_error

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
    except requests.exceptions.SSLError as e:
        log(f"TLS/SSL error: {e}")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {
                "code": -32003,
                "message": "TLS certificate verification failed. Check server certificate or set MCP_VERIFY_TLS=false for development."
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
