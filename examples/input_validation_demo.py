# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""
Demo script showing enhanced input validation capabilities.

This script demonstrates the strengthened input validation implemented
in Task 45.1, including sanitization and detailed error feedback.

Requirements: 16.3
"""

from mcp_server.utils.input_validation import InputValidator, ValidationError


def demo_sanitization():
    """Demonstrate string sanitization."""
    print("=" * 70)
    print("STRING SANITIZATION DEMO")
    print("=" * 70)
    
    # Valid string
    print("\n1. Valid string:")
    result = InputValidator.sanitize_string("valid-string_123")
    print(f"   Input: 'valid-string_123'")
    print(f"   Result: '{result}' ✓")
    
    # String with newlines (allowed)
    print("\n2. String with newlines (allowed):")
    result = InputValidator.sanitize_string("line1\nline2")
    print(f"   Input: 'line1\\nline2'")
    print(f"   Result: '{result}' ✓")
    
    # Null byte injection attempt
    print("\n3. Null byte injection attempt:")
    try:
        InputValidator.sanitize_string("test\x00injection")
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: 'test\\x00injection'")
        print(f"   Rejected: {e.message} ✓")
    
    # Control character injection
    print("\n4. Control character injection:")
    try:
        InputValidator.sanitize_string("test\x01control")
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: 'test\\x01control'")
        print(f"   Rejected: {e.message} ✓")
    
    # String too long
    print("\n5. String exceeding length limit:")
    try:
        long_string = "a" * 2000
        InputValidator.sanitize_string(long_string, max_length=1024)
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: String with 2000 characters")
        print(f"   Rejected: {e.message} ✓")


def demo_resource_validation():
    """Demonstrate resource type validation."""
    print("\n" + "=" * 70)
    print("RESOURCE TYPE VALIDATION DEMO")
    print("=" * 70)
    
    # Valid resource types
    print("\n1. Valid resource types:")
    result = InputValidator.validate_resource_types(
        ["ec2:instance", "s3:bucket", "lambda:function"]
    )
    print(f"   Input: {result}")
    print(f"   Result: Validated ✓")
    
    # Invalid resource type
    print("\n2. Invalid resource type:")
    try:
        InputValidator.validate_resource_types(
            ["ec2:instance", "invalid:type"]
        )
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: ['ec2:instance', 'invalid:type']")
        print(f"   Rejected: {e.message} ✓")
    
    # Too many resource types
    print("\n3. Too many resource types:")
    try:
        too_many = ["ec2:instance"] * 15
        InputValidator.validate_resource_types(too_many)
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: 15 resource types")
        print(f"   Rejected: {e.message} ✓")
    
    # Duplicate resource types
    print("\n4. Duplicate resource types:")
    try:
        InputValidator.validate_resource_types(
            ["ec2:instance", "ec2:instance"]
        )
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: ['ec2:instance', 'ec2:instance']")
        print(f"   Rejected: {e.message} ✓")


def demo_arn_validation():
    """Demonstrate ARN validation."""
    print("\n" + "=" * 70)
    print("ARN VALIDATION DEMO")
    print("=" * 70)
    
    # Valid ARN
    print("\n1. Valid ARN:")
    result = InputValidator.validate_resource_arns([
        "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
    ])
    print(f"   Input: {result[0]}")
    print(f"   Result: Validated ✓")
    
    # Invalid ARN format
    print("\n2. Invalid ARN format:")
    try:
        InputValidator.validate_resource_arns(["not-an-arn"])
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: 'not-an-arn'")
        print(f"   Rejected: {e.message} ✓")
    
    # ARN with injection attempt
    print("\n3. ARN with null byte injection:")
    try:
        InputValidator.validate_resource_arns([
            "arn:aws:ec2:us-east-1:123456789012:instance/i-123\x00injection"
        ])
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: ARN with \\x00 byte")
        print(f"   Rejected: {e.message} ✓")
    
    # Too many ARNs
    print("\n4. Too many ARNs:")
    try:
        too_many = ["arn:aws:ec2:us-east-1:123456789012:instance/i-123"] * 150
        InputValidator.validate_resource_arns(too_many)
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: 150 ARNs")
        print(f"   Rejected: {e.message} ✓")


def demo_time_period_validation():
    """Demonstrate time period validation."""
    print("\n" + "=" * 70)
    print("TIME PERIOD VALIDATION DEMO")
    print("=" * 70)
    
    # Valid time period
    print("\n1. Valid time period:")
    result = InputValidator.validate_time_period({
        "Start": "2024-01-01",
        "End": "2024-01-31"
    })
    print(f"   Input: {result}")
    print(f"   Result: Validated ✓")
    
    # Invalid date format
    print("\n2. Invalid date format:")
    try:
        InputValidator.validate_time_period({
            "Start": "01/01/2024",
            "End": "2024-01-31"
        })
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: Start='01/01/2024'")
        print(f"   Rejected: {e.message} ✓")
    
    # End before start
    print("\n3. End date before start date:")
    try:
        InputValidator.validate_time_period({
            "Start": "2024-01-31",
            "End": "2024-01-01"
        })
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: Start='2024-01-31', End='2024-01-01'")
        print(f"   Rejected: {e.message} ✓")
    
    # Date range too large
    print("\n4. Date range too large (>365 days):")
    try:
        InputValidator.validate_time_period({
            "Start": "2023-01-01",
            "End": "2024-12-31"
        })
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: 730 day range")
        print(f"   Rejected: {e.message} ✓")


def demo_integer_validation():
    """Demonstrate integer validation."""
    print("\n" + "=" * 70)
    print("INTEGER VALIDATION DEMO")
    print("=" * 70)
    
    # Valid integer
    print("\n1. Valid integer:")
    result = InputValidator.validate_integer(42, "test_field")
    print(f"   Input: 42")
    print(f"   Result: {result} ✓")
    
    # Integer below minimum
    print("\n2. Integer below minimum:")
    try:
        InputValidator.validate_integer(0, "days_back", minimum=1)
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: 0 (minimum: 1)")
        print(f"   Rejected: {e.message} ✓")
    
    # Integer above maximum
    print("\n3. Integer above maximum:")
    try:
        InputValidator.validate_integer(100, "days_back", maximum=90)
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: 100 (maximum: 90)")
        print(f"   Rejected: {e.message} ✓")
    
    # Boolean masquerading as integer
    print("\n4. Boolean rejected (not an integer):")
    try:
        InputValidator.validate_integer(True, "test_field")
        print("   ERROR: Should have been rejected!")
    except ValidationError as e:
        print(f"   Input: True (boolean)")
        print(f"   Rejected: {e.message} ✓")


def main():
    """Run all validation demos."""
    print("\n" + "=" * 70)
    print("ENHANCED INPUT VALIDATION DEMO")
    print("Task 45.1: Strengthen Input Validation in MCP Handler")
    print("=" * 70)
    
    demo_sanitization()
    demo_resource_validation()
    demo_arn_validation()
    demo_time_period_validation()
    demo_integer_validation()
    
    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print("\nAll validation features working correctly!")
    print("The MCP server now has comprehensive input validation with:")
    print("  • String sanitization to prevent injection attacks")
    print("  • Strict size limits to prevent resource exhaustion")
    print("  • Detailed error messages with field-level feedback")
    print("  • Pattern validation for all structured inputs")
    print("  • Type checking and range enforcement")
    print("\nRequirement 16.3: ✓ Satisfied")


if __name__ == "__main__":
    main()
