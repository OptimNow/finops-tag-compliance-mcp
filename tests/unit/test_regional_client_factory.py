# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""Unit tests for RegionalClientFactory."""

import pytest
from botocore.config import Config
from unittest.mock import patch, MagicMock

from mcp_server.clients.regional_client_factory import RegionalClientFactory
from mcp_server.clients.aws_client import AWSClient


class TestRegionalClientFactoryInit:
    """Tests for RegionalClientFactory initialization."""
    
    def test_init_with_defaults(self):
        """Test factory initializes with default values."""
        factory = RegionalClientFactory()
        
        assert factory.default_region == "us-east-1"
        assert factory.boto_config is None
        assert factory.get_client_count() == 0
        assert factory.cached_regions == []
    
    def test_init_with_custom_region(self):
        """Test factory initializes with custom default region."""
        factory = RegionalClientFactory(default_region="eu-west-1")
        
        assert factory.default_region == "eu-west-1"
    
    def test_init_with_boto_config(self):
        """Test factory initializes with custom boto3 config."""
        config = Config(
            retries={"max_attempts": 5, "mode": "adaptive"},
            connect_timeout=10,
            read_timeout=30
        )
        factory = RegionalClientFactory(boto_config=config)
        
        assert factory.boto_config is config


class TestRegionalClientFactoryGetClient:
    """Tests for get_client method."""
    
    @patch.object(AWSClient, '__init__', return_value=None)
    def test_get_client_creates_new_client(self, mock_init):
        """Test get_client creates a new client for a new region."""
        factory = RegionalClientFactory()
        
        client = factory.get_client("us-east-1")
        
        assert client is not None
        assert factory.get_client_count() == 1
        assert factory.has_client("us-east-1")
        mock_init.assert_called_once_with(region="us-east-1")
    
    @patch.object(AWSClient, '__init__', return_value=None)
    def test_get_client_reuses_existing_client(self, mock_init):
        """
        Test get_client returns the same instance for the same region.
        
        Validates: Requirements 2.2 - Client reuse within session
        """
        factory = RegionalClientFactory()
        
        # Get client twice for the same region
        client1 = factory.get_client("us-west-2")
        client2 = factory.get_client("us-west-2")
        
        # Should be the exact same object (object identity)
        assert client1 is client2
        assert factory.get_client_count() == 1
        # AWSClient.__init__ should only be called once
        mock_init.assert_called_once_with(region="us-west-2")
    
    @patch.object(AWSClient, '__init__', return_value=None)
    def test_get_client_creates_separate_clients_for_different_regions(self, mock_init):
        """
        Test get_client creates separate clients for different regions.
        
        Validates: Requirements 2.1 - Create clients for each enabled region
        """
        factory = RegionalClientFactory()
        
        client_east = factory.get_client("us-east-1")
        client_west = factory.get_client("us-west-2")
        client_eu = factory.get_client("eu-west-1")
        
        # Should be different objects
        assert client_east is not client_west
        assert client_west is not client_eu
        assert client_east is not client_eu
        
        # Should have 3 cached clients
        assert factory.get_client_count() == 3
        assert set(factory.cached_regions) == {"us-east-1", "us-west-2", "eu-west-1"}
    
    @patch.object(AWSClient, '__init__', return_value=None)
    def test_get_client_multiple_calls_same_region_returns_same_instance(self, mock_init):
        """
        Test multiple calls with same region return identical instance.
        
        This is the core idempotence property (Property 2).
        """
        factory = RegionalClientFactory()
        region = "ap-southeast-1"
        
        # Call get_client 5 times
        clients = [factory.get_client(region) for _ in range(5)]
        
        # All should be the exact same object
        for client in clients[1:]:
            assert client is clients[0]
        
        # Only one client should be created
        assert factory.get_client_count() == 1
        mock_init.assert_called_once()


class TestRegionalClientFactoryClearClients:
    """Tests for clear_clients method."""
    
    @patch.object(AWSClient, '__init__', return_value=None)
    def test_clear_clients_removes_all_cached_clients(self, mock_init):
        """Test clear_clients removes all cached clients."""
        factory = RegionalClientFactory()
        
        # Create some clients
        factory.get_client("us-east-1")
        factory.get_client("us-west-2")
        factory.get_client("eu-west-1")
        
        assert factory.get_client_count() == 3
        
        # Clear all clients
        factory.clear_clients()
        
        assert factory.get_client_count() == 0
        assert factory.cached_regions == []
        assert not factory.has_client("us-east-1")
        assert not factory.has_client("us-west-2")
        assert not factory.has_client("eu-west-1")
    
    @patch.object(AWSClient, '__init__', return_value=None)
    def test_clear_clients_allows_new_client_creation(self, mock_init):
        """Test that after clearing, new clients can be created."""
        factory = RegionalClientFactory()
        
        # Create a client
        client1 = factory.get_client("us-east-1")
        
        # Clear clients
        factory.clear_clients()
        
        # Create a new client for the same region
        client2 = factory.get_client("us-east-1")
        
        # Should be a different instance
        assert client1 is not client2
        assert factory.get_client_count() == 1


class TestRegionalClientFactoryHelperMethods:
    """Tests for helper methods."""
    
    @patch.object(AWSClient, '__init__', return_value=None)
    def test_has_client_returns_true_for_cached_region(self, mock_init):
        """Test has_client returns True for cached regions."""
        factory = RegionalClientFactory()
        factory.get_client("us-east-1")
        
        assert factory.has_client("us-east-1") is True
    
    def test_has_client_returns_false_for_uncached_region(self):
        """Test has_client returns False for uncached regions."""
        factory = RegionalClientFactory()
        
        assert factory.has_client("us-east-1") is False
    
    @patch.object(AWSClient, '__init__', return_value=None)
    def test_cached_regions_returns_all_cached_regions(self, mock_init):
        """Test cached_regions returns list of all cached regions."""
        factory = RegionalClientFactory()
        
        factory.get_client("us-east-1")
        factory.get_client("eu-west-1")
        factory.get_client("ap-northeast-1")
        
        cached = factory.cached_regions
        
        assert len(cached) == 3
        assert set(cached) == {"us-east-1", "eu-west-1", "ap-northeast-1"}


class TestRegionalClientFactoryConfigurationConsistency:
    """Tests for configuration consistency across clients.
    
    Validates: Requirements 2.3 - Apply same boto3 configuration to all clients
    """
    
    @patch.object(AWSClient, '__init__', return_value=None)
    def test_all_clients_created_with_correct_region(self, mock_init):
        """Test all clients are created with the correct region parameter."""
        factory = RegionalClientFactory()
        
        regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
        
        for region in regions:
            factory.get_client(region)
        
        # Verify each client was created with the correct region
        calls = mock_init.call_args_list
        called_regions = [call.kwargs["region"] for call in calls]
        
        assert set(called_regions) == set(regions)
