#!/usr/bin/env python3
"""
Local Testing Script for FinOps Tag Compliance MCP Server

This script provides simple, quick tests you can run locally to verify
the MCP server is working before doing full UAT.

Usage:
    1. Start the server: docker-compose up -d
    2. Run this script: python scripts/local_test.py

Prerequisites:
    - Docker Desktop running
    - Server running on http://localhost:8080
    - pip install requests (if not already installed)
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8080"
MCP_ENDPOINT = f"{BASE_URL}/mcp"

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_header(text: str):
    """Print a section header."""
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}{text}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")


def print_result(test_name: str, passed: bool, details: str = ""):
    """Print test result."""
    status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    print(f"  [{status}] {test_name}")
    if details:
        print(f"         {details}")


def test_health_endpoint():
    """Test 1: Health endpoint returns healthy status."""
    print_header("Test 1: Health Endpoint")
    
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        data = response.json()
        
        # Check status code
        print_result(
            "HTTP 200 response",
            response.status_code == 200,
            f"Got: {response.status_code}"
        )
        
        # Check status field
        print_result(
            "Status is 'healthy'",
            data.get("status") == "healthy",
            f"Got: {data.get('status')}"
        )
        
        # Check required fields
        required_fields = ["status", "version", "timestamp", "cloud_providers"]
        for field in required_fields:
            print_result(
                f"Has '{field}' field",
                field in data,
                f"Value: {data.get(field, 'MISSING')}"
            )
        
        return response.status_code == 200 and data.get("status") == "healthy"
        
    except requests.exceptions.ConnectionError:
        print_result("Server reachable", False, "Connection refused - is the server running?")
        return False
    except Exception as e:
        print_result("Health check", False, str(e))
        return False


def test_root_endpoint():
    """Test 2: Root endpoint returns server info."""
    print_header("Test 2: Root Endpoint")
    
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        data = response.json()
        
        print_result(
            "HTTP 200 response",
            response.status_code == 200
        )
        
        print_result(
            "Has 'name' field",
            "name" in data,
            f"Value: {data.get('name', 'MISSING')}"
        )
        
        print_result(
            "Has 'tools' field",
            "tools" in data,
            f"Tool count: {len(data.get('tools', []))}"
        )
        
        return response.status_code == 200
        
    except Exception as e:
        print_result("Root endpoint", False, str(e))
        return False


def test_mcp_list_tools():
    """Test 3: MCP tools/list returns all 8 tools."""
    print_header("Test 3: MCP Tools List")
    
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }
        
        response = requests.post(
            MCP_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        data = response.json()
        
        print_result(
            "HTTP 200 response",
            response.status_code == 200
        )
        
        # Check for tools in response
        tools = data.get("result", {}).get("tools", [])
        tool_names = [t.get("name") for t in tools]
        
        expected_tools = [
            "check_tag_compliance",
            "find_untagged_resources",
            "validate_resource_tags",
            "get_cost_attribution_gap",
            "suggest_tags",
            "get_tagging_policy",
            "generate_compliance_report",
            "get_violation_history"
        ]
        
        print_result(
            f"Has {len(expected_tools)} tools",
            len(tools) >= len(expected_tools),
            f"Found: {len(tools)} tools"
        )
        
        for tool in expected_tools:
            print_result(
                f"Has '{tool}'",
                tool in tool_names
            )
        
        return len(tools) >= len(expected_tools)
        
    except Exception as e:
        print_result("MCP tools/list", False, str(e))
        return False


def test_get_tagging_policy():
    """Test 4: get_tagging_policy tool returns policy."""
    print_header("Test 4: Get Tagging Policy Tool")
    
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "get_tagging_policy",
                "arguments": {}
            }
        }
        
        response = requests.post(
            MCP_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        data = response.json()
        
        print_result(
            "HTTP 200 response",
            response.status_code == 200
        )
        
        # Check for result
        result = data.get("result", {})
        content = result.get("content", [])
        
        print_result(
            "Has content",
            len(content) > 0,
            f"Content items: {len(content)}"
        )
        
        if content:
            text = content[0].get("text", "")
            policy_data = json.loads(text) if text else {}
            
            print_result(
                "Has required_tags",
                "required_tags" in policy_data,
                f"Count: {len(policy_data.get('required_tags', []))}"
            )
            
            print_result(
                "Has version",
                "version" in policy_data,
                f"Version: {policy_data.get('version', 'MISSING')}"
            )
        
        return response.status_code == 200 and len(content) > 0
        
    except Exception as e:
        print_result("get_tagging_policy", False, str(e))
        return False


def test_check_compliance_mock():
    """Test 5: check_tag_compliance tool (with mock data)."""
    print_header("Test 5: Check Tag Compliance Tool")
    
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "check_tag_compliance",
                "arguments": {
                    "resource_types": ["ec2:instance"]
                }
            }
        }
        
        response = requests.post(
            MCP_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        data = response.json()
        
        print_result(
            "HTTP 200 response",
            response.status_code == 200
        )
        
        # Check for result or error
        if "error" in data:
            error = data["error"]
            # AWS errors are expected if no credentials
            if "AWS" in str(error) or "credentials" in str(error).lower():
                print_result(
                    "Tool executed (AWS credentials needed)",
                    True,
                    "Expected - configure AWS credentials for real data"
                )
                return True
            else:
                print_result("Tool execution", False, str(error))
                return False
        
        result = data.get("result", {})
        content = result.get("content", [])
        
        print_result(
            "Has content",
            len(content) > 0
        )
        
        return response.status_code == 200
        
    except Exception as e:
        print_result("check_tag_compliance", False, str(e))
        return False


def test_metrics_endpoint():
    """Test 6: Metrics endpoint returns Prometheus metrics."""
    print_header("Test 6: Metrics Endpoint")
    
    try:
        response = requests.get(f"{BASE_URL}/metrics", timeout=5)
        
        print_result(
            "HTTP 200 response",
            response.status_code == 200
        )
        
        # Check for Prometheus format
        text = response.text
        has_metrics = "mcp_" in text or "tool_" in text or "# HELP" in text
        
        print_result(
            "Has metrics data",
            has_metrics or len(text) > 0,
            f"Response length: {len(text)} chars"
        )
        
        return response.status_code == 200
        
    except Exception as e:
        print_result("Metrics endpoint", False, str(e))
        return False


def run_all_tests():
    """Run all tests and print summary."""
    print(f"\n{BOLD}FinOps Tag Compliance MCP Server - Local Test Suite{RESET}")
    print(f"Target: {BASE_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    
    results = []
    
    # Run tests
    results.append(("Health Endpoint", test_health_endpoint()))
    results.append(("Root Endpoint", test_root_endpoint()))
    results.append(("MCP Tools List", test_mcp_list_tools()))
    results.append(("Get Tagging Policy", test_get_tagging_policy()))
    results.append(("Check Compliance", test_check_compliance_mock()))
    results.append(("Metrics Endpoint", test_metrics_endpoint()))
    
    # Print summary
    print_header("Test Summary")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
        print(f"  [{status}] {name}")
    
    print(f"\n{BOLD}Results: {passed}/{total} tests passed{RESET}")
    
    if passed == total:
        print(f"\n{GREEN}All tests passed! Server is ready for UAT.{RESET}")
        print(f"\nNext steps:")
        print(f"  1. Configure AWS credentials (if not already done)")
        print(f"  2. Follow UAT_PROTOCOL.md for full acceptance testing")
        print(f"  3. Test with Claude Desktop using the MCP connection")
        return 0
    else:
        print(f"\n{YELLOW}Some tests failed. Check the output above.{RESET}")
        print(f"\nTroubleshooting:")
        print(f"  1. Is Docker running? Check: docker ps")
        print(f"  2. Is the server started? Run: docker-compose up -d")
        print(f"  3. Check logs: docker-compose logs mcp-server")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
