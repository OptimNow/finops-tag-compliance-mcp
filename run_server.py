# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

#!/usr/bin/env python3
"""
Main entry point for the FinOps Tag Compliance MCP Server.

This script loads environment variables, initializes all services,
and starts the FastAPI server on the configured port (default: 8080).

Usage:
    python run_server.py
    
Or with uvicorn directly:
    uvicorn mcp_server.main:app --host 0.0.0.0 --port 8080

Requirements: 14.2, 14.5
"""

import logging
import os
import sys

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional

import uvicorn

from mcp_server.config import settings


def configure_logging(log_level: str) -> None:
    """
    Configure logging for the application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    
    # Set uvicorn loggers to the same level
    logging.getLogger("uvicorn").setLevel(numeric_level)
    logging.getLogger("uvicorn.access").setLevel(numeric_level)
    logging.getLogger("uvicorn.error").setLevel(numeric_level)


def print_startup_banner(config: "Settings") -> None:
    """
    Print startup banner with configuration information.
    
    Args:
        config: Application settings
    """
    from mcp_server import __version__
    
    banner = f"""
╔══════════════════════════════════════════════════════════════════╗
║         FinOps Tag Compliance MCP Server v{__version__}              ║
╠══════════════════════════════════════════════════════════════════╣
║  Configuration:                                                  ║
║    Host:        {config.host:<48} ║
║    Port:        {config.port:<48} ║
║    Environment: {config.environment:<48} ║
║    Log Level:   {config.log_level:<48} ║
║    AWS Region:  {config.aws_region:<48} ║
║    Policy:      {config.policy_path:<48} ║
║    Redis:       {config.redis_url:<48} ║
╠══════════════════════════════════════════════════════════════════╣
║  MCP Tools (8):                                                  ║
║    1. check_tag_compliance     5. suggest_tags                   ║
║    2. find_untagged_resources  6. get_tagging_policy             ║
║    3. validate_resource_tags   7. generate_compliance_report     ║
║    4. get_cost_attribution_gap 8. get_violation_history          ║
╠══════════════════════════════════════════════════════════════════╣
║  Endpoints:                                                      ║
║    Health:     http://{config.host}:{config.port}/health                            ║
║    MCP Tools:  http://{config.host}:{config.port}/mcp/tools                         ║
║    Tool Call:  http://{config.host}:{config.port}/mcp/tools/call                    ║
╚══════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def main() -> None:
    """
    Main entry point for the MCP server.
    
    Loads configuration, configures logging, and starts the server.
    
    Requirements: 14.2, 14.5
    """
    # Load settings
    config = settings()
    
    # Configure logging
    configure_logging(config.log_level)
    
    logger = logging.getLogger(__name__)
    
    # Print startup banner
    print_startup_banner(config)
    
    logger.info("Starting FinOps Tag Compliance MCP Server...")
    logger.info(f"Server will listen on {config.host}:{config.port}")
    
    # Validate critical configuration
    if not os.path.exists(config.policy_path):
        logger.warning(
            f"Policy file not found at {config.policy_path}. "
            "Server will start but policy-dependent tools may fail."
        )
    
    # Start the server
    try:
        uvicorn.run(
            "mcp_server.main:app",
            host=config.host,
            port=config.port,
            reload=config.debug,
            log_level=config.log_level.lower(),
            access_log=True,
        )
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
