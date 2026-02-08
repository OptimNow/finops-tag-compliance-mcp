"""Custom promptfoo provider for FinOps Tag Compliance MCP Server.

This provider sends tool calls to the MCP HTTP API endpoint and returns
the results in a format promptfoo can evaluate with assertions.

It supports two modes:
  1. HTTP mode (default): Calls POST /mcp/tools/call on the running server
  2. Stdio mode: Spawns the MCP server as a subprocess (future)

Usage in promptfooconfig.yaml:
  providers:
    - id: "python:tests/regression/mcp_provider.py"

Environment variables:
  MCP_SERVER_URL: Base URL of the MCP server (default: http://localhost:8080)
  MCP_API_KEY:    API key for authentication (optional)
  MCP_TIMEOUT:    Request timeout in seconds (default: 120)
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error


# Configuration from environment
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8080")
MCP_API_KEY = os.environ.get("MCP_API_KEY", "")
MCP_TIMEOUT = int(os.environ.get("MCP_TIMEOUT", "120"))


def call_api(prompt: str, options: dict, context: dict) -> dict:
    """Promptfoo provider entry point.

    Args:
        prompt: The rendered prompt string (we use this as JSON tool call spec).
        options: Provider options from the config (e.g., config.tool_name).
        context: Additional context from promptfoo (vars, etc.).

    Returns:
        dict with 'output' key containing the tool response.
    """
    # Parse the tool call from the prompt (rendered from the test case)
    try:
        tool_call = json.loads(prompt)
    except json.JSONDecodeError:
        return {
            "output": json.dumps({
                "error": "invalid_prompt",
                "message": f"Prompt is not valid JSON: {prompt[:200]}",
            }),
        }

    tool_name = tool_call.get("name", "")
    arguments = tool_call.get("arguments", {})

    # Build the HTTP request
    url = f"{MCP_SERVER_URL}/mcp/tools/call"
    payload = json.dumps({"name": tool_name, "arguments": arguments}).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if MCP_API_KEY:
        headers["Authorization"] = f"Bearer {MCP_API_KEY}"

    # Make the request
    start_time = time.time()
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=MCP_TIMEOUT) as resp:
            response_body = resp.read().decode("utf-8")
            elapsed_ms = (time.time() - start_time) * 1000

        response_data = json.loads(response_body)

        # Extract the tool result from the MCP response envelope
        # Response format: {"content": [{"type": "text", "text": "..."}], "is_error": false}
        content = response_data.get("content", [])
        is_error = response_data.get("is_error", False)

        # Get the text content from the first content block
        tool_output = ""
        if content and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    tool_output = block.get("text", "")
                    break

        # Try to parse as JSON for structured assertions
        try:
            parsed_output = json.loads(tool_output)
        except (json.JSONDecodeError, TypeError):
            parsed_output = tool_output

        # Build the result
        result = {
            "output": json.dumps(parsed_output) if isinstance(parsed_output, dict) else str(parsed_output),
            "metadata": {
                "tool_name": tool_name,
                "is_error": is_error,
                "elapsed_ms": round(elapsed_ms, 2),
                "http_status": 200,
            },
        }

        # If the MCP server reported an error, include it
        if is_error:
            result["error"] = f"MCP tool error: {tool_output[:500]}"

        return result

    except urllib.error.HTTPError as e:
        elapsed_ms = (time.time() - start_time) * 1000
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            pass

        return {
            "output": json.dumps({
                "error": "http_error",
                "status_code": e.code,
                "message": error_body[:500] if error_body else str(e),
            }),
            "error": f"HTTP {e.code}: {error_body[:200]}",
            "metadata": {
                "tool_name": tool_name,
                "http_status": e.code,
                "elapsed_ms": round(elapsed_ms, 2),
            },
        }

    except urllib.error.URLError as e:
        return {
            "output": json.dumps({
                "error": "connection_error",
                "message": f"Cannot connect to MCP server at {MCP_SERVER_URL}: {e.reason}",
            }),
            "error": f"Connection error: {e.reason}",
        }

    except Exception as e:
        return {
            "output": json.dumps({
                "error": "provider_error",
                "message": str(e),
            }),
            "error": str(e),
        }
