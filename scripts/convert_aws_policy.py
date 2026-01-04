# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

#!/usr/bin/env python3
"""
Convert AWS Organizations Tag Policy to FinOps MCP Server Policy Format

This script converts AWS Organizations tag policies (the native AWS format)
into the custom format used by the FinOps Tag Compliance MCP Server.

Usage:
    python scripts/convert_aws_policy.py <input_file> [output_file]
    
    input_file: Path to AWS Organizations tag policy JSON file
    output_file: Path to save converted policy (default: policies/tagging_policy.json)

Example:
    python scripts/convert_aws_policy.py aws_tag_policy.json
    python scripts/convert_aws_policy.py aws_tag_policy.json policies/my_policy.json
"""

import json
import sys
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional


def parse_enforced_for(enforced_for: List[str]) -> List[str]:
    """
    Convert AWS enforced_for format to our applies_to format.
    
    AWS format: ["secretsmanager:ALL_SUPPORTED", "ec2:instance"]
    Our format: ["secretsmanager:secret", "ec2:instance"]
    """
    applies_to = []
    
    for resource in enforced_for:
        if ":ALL_SUPPORTED" in resource:
            # For ALL_SUPPORTED, we need to expand to known resource types
            service = resource.split(":")[0]
            # Map common services to their resource types
            service_mappings = {
                "ec2": ["ec2:instance", "ec2:volume", "ec2:snapshot"],
                "s3": ["s3:bucket"],
                "rds": ["rds:db"],
                "lambda": ["lambda:function"],
                "ecs": ["ecs:service", "ecs:task"],
                "secretsmanager": ["secretsmanager:secret"],
            }
            applies_to.extend(service_mappings.get(service, [f"{service}:resource"]))
        else:
            applies_to.append(resource)
    
    return applies_to


def extract_tag_values(tag_value_config: Any) -> Optional[List[str]]:
    """
    Extract allowed tag values from AWS policy format.
    
    AWS uses @@assign operator with array of values.
    """
    if not tag_value_config:
        return None
    
    if isinstance(tag_value_config, dict):
        values = tag_value_config.get("@@assign", [])
    elif isinstance(tag_value_config, list):
        values = tag_value_config
    else:
        return None
    
    # Remove wildcards for now (our format doesn't support them yet)
    # Convert "300*" to just "300" or remove it
    clean_values = []
    for val in values:
        if isinstance(val, str):
            # Remove trailing wildcards
            clean_val = val.rstrip("*")
            if clean_val and clean_val not in clean_values:
                clean_values.append(clean_val)
    
    return clean_values if clean_values else None


def convert_aws_policy_to_mcp_format(aws_policy: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert AWS Organizations tag policy to MCP server format.
    
    Args:
        aws_policy: AWS Organizations tag policy (with "tags" key)
    
    Returns:
        MCP server policy format
    """
    tags_section = aws_policy.get("tags", {})
    
    required_tags = []
    optional_tags = []
    
    for policy_key, tag_config in tags_section.items():
        # Extract tag key (with proper capitalization)
        tag_key_config = tag_config.get("tag_key", {})
        if isinstance(tag_key_config, dict):
            tag_name = tag_key_config.get("@@assign", policy_key)
        else:
            tag_name = policy_key
        
        # Extract tag values
        tag_value_config = tag_config.get("tag_value", {})
        allowed_values = extract_tag_values(tag_value_config)
        
        # Extract enforced_for (which resources this applies to)
        enforced_for_config = tag_config.get("enforced_for", {})
        if isinstance(enforced_for_config, dict):
            enforced_for = enforced_for_config.get("@@assign", [])
        else:
            enforced_for = enforced_for_config or []
        
        applies_to = parse_enforced_for(enforced_for) if enforced_for else [
            "ec2:instance", "rds:db", "s3:bucket", "lambda:function"
        ]
        
        # Build tag definition
        tag_def = {
            "name": tag_name,
            "description": f"Converted from AWS Organizations tag policy - {policy_key}",
            "allowed_values": allowed_values,
            "validation_regex": None,
            "applies_to": applies_to
        }
        
        # Determine if required or optional based on enforced_for
        if enforced_for:
            required_tags.append(tag_def)
        else:
            # If no enforcement, treat as optional
            optional_tags.append({
                "name": tag_name,
                "description": tag_def["description"],
                "allowed_values": allowed_values
            })
    
    # Build MCP policy
    mcp_policy = {
        "version": "1.0",
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "required_tags": required_tags,
        "optional_tags": optional_tags,
        "tag_naming_rules": {
            "case_sensitivity": False,
            "allow_special_characters": False,
            "max_key_length": 128,
            "max_value_length": 256
        }
    }
    
    return mcp_policy


def main():
    if len(sys.argv) < 2:
        print("Error: Missing input file")
        print(__doc__)
        sys.exit(1)
    
    input_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("policies/tagging_policy.json")
    
    # Validate input file exists
    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)
    
    # Read AWS policy
    try:
        with open(input_file, 'r') as f:
            aws_policy = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in input file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading input file: {e}")
        sys.exit(1)
    
    # Validate it's an AWS tag policy
    if "tags" not in aws_policy:
        print("Error: Input file doesn't appear to be an AWS Organizations tag policy")
        print("Expected a 'tags' key at the root level")
        sys.exit(1)
    
    # Convert
    print(f"Converting AWS tag policy from {input_file}...")
    mcp_policy = convert_aws_policy_to_mcp_format(aws_policy)
    
    # Create output directory if needed
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Write output
    try:
        with open(output_file, 'w') as f:
            json.dump(mcp_policy, f, indent=2)
        print(f"✓ Successfully converted policy to {output_file}")
        print(f"  - {len(mcp_policy['required_tags'])} required tags")
        print(f"  - {len(mcp_policy['optional_tags'])} optional tags")
    except Exception as e:
        print(f"Error writing output file: {e}")
        sys.exit(1)
    
    # Print summary
    print("\nSummary:")
    print("--------")
    for tag in mcp_policy['required_tags']:
        values_str = f" (values: {', '.join(tag['allowed_values'])})" if tag['allowed_values'] else ""
        print(f"  • {tag['name']}{values_str}")
        print(f"    Applies to: {', '.join(tag['applies_to'])}")


if __name__ == "__main__":
    main()
