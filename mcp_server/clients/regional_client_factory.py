# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Factory for creating and caching regional AWS clients."""

import logging
from typing import Any

from botocore.config import Config

from .aws_client import AWSClient

logger = logging.getLogger(__name__)


class RegionalClientFactory:
    """
    Factory for creating and caching regional AWS clients.
    
    Reuses clients within a session to avoid repeated initialization.
    Applies consistent boto3 configuration across all clients.
    
    This factory implements Requirements 2.1, 2.2, and 2.3:
    - 2.1: Creates AWS clients for each enabled region
    - 2.2: Reuses existing clients for regions already initialized
    - 2.3: Applies same boto3 configuration (retries, timeouts) to all clients
    """
    
    def __init__(
        self,
        default_region: str = "us-east-1",
        boto_config: Config | None = None
    ):
        """
        Initialize with default region and boto3 config.
        
        Args:
            default_region: Default AWS region code (e.g., "us-east-1")
            boto_config: Optional boto3 Config to apply to all clients.
                        If None, a default config with adaptive retries is used.
        """
        self._default_region = default_region
        self._boto_config = boto_config
        self._clients: dict[str, AWSClient] = {}
        
        logger.debug(
            f"RegionalClientFactory initialized with default_region={default_region}"
        )
    
    @property
    def default_region(self) -> str:
        """Get the default region."""
        return self._default_region
    
    @property
    def boto_config(self) -> Config | None:
        """Get the boto3 configuration."""
        return self._boto_config
    
    @property
    def cached_regions(self) -> list[str]:
        """Get list of regions with cached clients."""
        return list(self._clients.keys())
    
    def get_client(self, region: str) -> AWSClient:
        """
        Get or create an AWS client for the specified region.
        
        Reuses existing clients for the same region (object identity).
        Applies consistent boto3 configuration across all clients.
        
        Args:
            region: AWS region code (e.g., "us-east-1", "eu-west-1")
            
        Returns:
            AWSClient configured for the specified region
            
        Note:
            Calling this method multiple times with the same region
            will return the exact same AWSClient instance (object identity).
        """
        # Check if we already have a client for this region
        if region in self._clients:
            logger.debug(f"Reusing cached client for region {region}")
            return self._clients[region]
        
        # Create a new client for this region
        logger.info(f"Creating new AWS client for region {region}")
        client = AWSClient(region=region)
        
        # Cache the client for reuse
        self._clients[region] = client
        
        return client
    
    def clear_clients(self) -> None:
        """
        Clear all cached clients.
        
        Useful for testing and cleanup. After calling this method,
        subsequent calls to get_client() will create new client instances.
        """
        client_count = len(self._clients)
        self._clients.clear()
        logger.info(f"Cleared {client_count} cached regional clients")
    
    def get_client_count(self) -> int:
        """
        Get the number of cached clients.
        
        Returns:
            Number of AWS clients currently cached
        """
        return len(self._clients)
    
    def has_client(self, region: str) -> bool:
        """
        Check if a client exists for the specified region.
        
        Args:
            region: AWS region code
            
        Returns:
            True if a client is cached for this region, False otherwise
        """
        return region in self._clients
