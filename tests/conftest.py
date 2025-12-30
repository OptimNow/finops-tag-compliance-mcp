"""Pytest configuration and shared fixtures."""

import os
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime


@pytest.fixture
def anyio_backend():
    """Configure anyio backend for async tests."""
    return "asyncio"


# =============================================================================
# Environment and Configuration Fixtures
# =============================================================================

@pytest.fixture
def test_env(monkeypatch):
    """Set up test environment variables."""
    test_vars = {
        "AWS_REGION": "us-east-1",
        "REDIS_URL": "redis://localhost:6379/0",
        "SQLITE_DB_PATH": ":memory:",
        "LOG_LEVEL": "DEBUG",
        "ENVIRONMENT": "test",
    }
    for key, value in test_vars.items():
        monkeypatch.setenv(key, value)
    return test_vars


# =============================================================================
# AWS and External Service Mocks
# =============================================================================

@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client for testing."""
    client = MagicMock()
    client.describe_instances = AsyncMock(return_value={"Reservations": []})
    client.describe_db_instances = AsyncMock(return_value={"DBInstances": []})
    client.list_buckets = AsyncMock(return_value={"Buckets": []})
    client.list_functions = AsyncMock(return_value={"Functions": []})
    client.list_services = AsyncMock(return_value={"serviceArns": []})
    return client


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client for testing."""
    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.exists = AsyncMock(return_value=False)
    return client


@pytest.fixture
def mock_sqlite_connection():
    """Create a mock SQLite connection for testing."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.execute = MagicMock(return_value=cursor)
    cursor.fetchall = MagicMock(return_value=[])
    cursor.fetchone = MagicMock(return_value=None)
    return conn


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def sample_violation_data():
    """Provide sample violation data for testing."""
    return {
        "resource_id": "i-1234567890abcdef0",
        "resource_type": "ec2:instance",
        "region": "us-east-1",
        "violation_type": "missing_required_tag",
        "tag_name": "CostCenter",
        "severity": "error",
        "cost_impact_monthly": 150.00,
    }


@pytest.fixture
def sample_compliance_result():
    """Provide sample compliance result for testing."""
    return {
        "compliance_score": 0.75,
        "total_resources": 100,
        "compliant_resources": 75,
        "violations": [],
        "cost_attribution_gap": 5000.00,
        "scan_timestamp": datetime.now(),
    }


@pytest.fixture
def sample_tagging_policy():
    """Provide sample tagging policy for testing."""
    return {
        "version": "1.0",
        "required_tags": [
            {
                "name": "CostCenter",
                "description": "Department for cost allocation",
                "allowed_values": ["Engineering", "Marketing", "Sales"],
                "applies_to": ["ec2:instance", "rds:db"],
            },
            {
                "name": "Environment",
                "description": "Deployment environment",
                "allowed_values": ["production", "staging", "development"],
                "applies_to": ["ec2:instance", "lambda:function"],
            },
        ],
        "optional_tags": [
            {
                "name": "Project",
                "description": "Project identifier",
            },
        ],
    }


@pytest.fixture
def sample_resource_data():
    """Provide sample AWS resource data for testing."""
    return {
        "ec2_instance": {
            "InstanceId": "i-1234567890abcdef0",
            "InstanceType": "t3.medium",
            "State": {"Name": "running"},
            "Tags": [
                {"Key": "Name", "Value": "test-instance"},
                {"Key": "Environment", "Value": "production"},
            ],
        },
        "rds_instance": {
            "DBInstanceIdentifier": "test-db",
            "DBInstanceClass": "db.t3.micro",
            "Engine": "postgres",
            "TagList": [
                {"Key": "Environment", "Value": "staging"},
            ],
        },
        "s3_bucket": {
            "Name": "test-bucket",
            "CreationDate": datetime.now(),
        },
    }


# =============================================================================
# Pytest Hooks for Test Reporting
# =============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers and settings."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "property: marks tests as property-based tests"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location."""
    for item in items:
        # Mark tests by directory
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "property" in str(item.fspath):
            item.add_marker(pytest.mark.property)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


def pytest_sessionstart(session):
    """Print test session information."""
    print("\n" + "=" * 70)
    print("FinOps Tag Compliance MCP Server - Test Suite")
    print("=" * 70)


def pytest_sessionfinish(session, exitstatus):
    """Print test session summary."""
    print("\n" + "=" * 70)
    if exitstatus == 0:
        print("PASS: All tests passed!")
    else:
        print(f"FAIL: Tests failed with exit status: {exitstatus}")
    print("=" * 70)
