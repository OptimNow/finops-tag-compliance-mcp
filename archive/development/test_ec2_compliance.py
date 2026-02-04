#!/usr/bin/env python3
"""Simple test script to check EC2 tag compliance via the MCP server."""

import json
import urllib.request

def test_compliance():
    url = "http://localhost:8080/mcp/tools/call"
    payload = {
        "name": "check_tag_compliance",
        "arguments": {
            "resource_types": ["ec2"]
        }
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(json.dumps(result, indent=2))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}")
        print(e.read().decode('utf-8'))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_compliance()
