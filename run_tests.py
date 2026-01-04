# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

#!/usr/bin/env python3
"""
Regression test runner for FinOps Tag Compliance MCP Server.

This script provides a convenient way to run the full test suite with various
configurations and reporting options.

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py --unit             # Run unit tests only
    python run_tests.py --property         # Run property tests only
    python run_tests.py --integration      # Run integration tests only
    python run_tests.py --coverage         # Run with coverage report
    python run_tests.py --fast             # Run fast tests (exclude slow/integration)
    python run_tests.py --verbose          # Verbose output
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd: list[str], description: str) -> int:
    """Run a command and return the exit code."""
    print(f"\n{'=' * 70}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'=' * 70}\n")
    
    result = subprocess.run(cmd)
    return result.returncode


def main():
    """Main entry point for the test runner."""
    parser = argparse.ArgumentParser(
        description="Run tests for FinOps Tag Compliance MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    # Test selection options
    parser.add_argument(
        "--unit",
        action="store_true",
        help="Run unit tests only",
    )
    parser.add_argument(
        "--property",
        action="store_true",
        help="Run property-based tests only",
    )
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Run integration tests only",
    )
    
    # Add coverage reporting
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Run with coverage reporting - target 80 percent",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Run fast tests only - exclude slow and integration tests",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--failfast",
        "-x",
        action="store_true",
        help="Stop on first failure",
    )
    parser.add_argument(
        "--pdb",
        action="store_true",
        help="Drop into debugger on failures",
    )
    parser.add_argument(
        "--keyword",
        "-k",
        type=str,
        help="Run tests matching the given keyword expression",
    )
    parser.add_argument(
        "--markers",
        "-m",
        type=str,
        help="Run tests matching the given marker expression",
    )
    
    args = parser.parse_args()
    
    # Build pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Add test path
    cmd.append("tests/")
    
    # Add test selection markers
    markers = []
    if args.unit:
        markers.append("unit")
    if args.property:
        markers.append("property")
    if args.integration:
        markers.append("integration")
    
    if markers:
        marker_expr = " or ".join(markers)
        cmd.extend(["-m", marker_expr])
    elif args.fast:
        # Exclude slow and integration tests
        cmd.extend(["-m", "not slow and not integration"])
    
    # Add custom marker expression if provided
    if args.markers:
        if markers:
            # Combine with existing markers
            cmd[-1] = f"{cmd[-1]} and {args.markers}"
        else:
            cmd.extend(["-m", args.markers])
    
    # Add keyword filter if provided
    if args.keyword:
        cmd.extend(["-k", args.keyword])
    
    # Add verbosity
    if args.verbose:
        cmd.append("-vv")
    else:
        cmd.append("-v")
    
    # Add coverage reporting
    if args.coverage:
        try:
            import pytest_cov  # noqa: F401
            cmd.extend([
                "--cov=mcp_server",
                "--cov-report=html",
                "--cov-report=term-missing",
                "--cov-fail-under=80",
            ])
        except ImportError:
            print("WARNING: pytest-cov not installed. Install with: pip install pytest-cov")
            print("Skipping coverage reporting.\n")
    
    # Add fail-fast option
    if args.failfast:
        cmd.append("-x")
    
    # Add debugger option
    if args.pdb:
        cmd.append("--pdb")
    
    # Add color output
    cmd.append("--color=yes")
    
    # Run the tests
    exit_code = run_command(cmd, "Full Regression Test Suite")
    
    # Print summary
    print(f"\n{'=' * 70}")
    if exit_code == 0:
        print("PASS: All tests passed!")
    else:
        print(f"FAIL: Tests failed with exit code: {exit_code}")
    print(f"{'=' * 70}\n")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
