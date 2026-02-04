# Multi-Account AWS Scanning Implementation Plan

## Overview

Add cross-account AWS scanning via STS AssumeRole, allowing the MCP server to scan resources across multiple AWS accounts from a single deployment.

**Design Pattern**: Mirror the existing `multi_region.py` models with parallel `multi_account.py` models.

**Backward Compatible**: Single-account mode remains the default; multi-account is opt-in via configuration.

**Account Source**: Environment variable `AWS_ACCOUNT_IDS` (comma-separated list)

---

## Phase 1: Configuration & Models

### 1.1 Add Configuration Fields
**File**: `mcp_server/config.py`

Add to `CoreSettings` class (after line ~70, near `aws_region`):

```python
# Multi-Account Configuration
multi_account_enabled: bool = Field(
    default=False,
    description="Enable multi-account scanning via AssumeRole",
    validation_alias="MULTI_ACCOUNT_ENABLED",
)
account_ids: str = Field(
    default="",
    description="Comma-separated list of AWS account IDs to scan",
    validation_alias="AWS_ACCOUNT_IDS",
)
assume_role_name: str = Field(
    default="FinOpsTagComplianceReadOnly",
    description="IAM role name to assume in target accounts",
    validation_alias="AWS_ASSUME_ROLE_NAME",
)
assume_role_arn_template: str = Field(
    default="arn:aws:iam::{account_id}:role/{role_name}",
    description="Template for AssumeRole ARN (supports {account_id} and {role_name} placeholders)",
    validation_alias="AWS_ASSUME_ROLE_ARN_TEMPLATE",
)
assume_role_session_duration: int = Field(
    default=3600,
    ge=900,
    le=43200,
    description="AssumeRole session duration in seconds (15 min to 12 hours)",
    validation_alias="AWS_ASSUME_ROLE_SESSION_DURATION",
)
max_concurrent_accounts: int = Field(
    default=5,
    ge=1,
    le=20,
    description="Maximum accounts to scan in parallel",
    validation_alias="MAX_CONCURRENT_ACCOUNTS",
)
account_scan_timeout_seconds: int = Field(
    default=120,
    ge=30,
    le=600,
    description="Timeout for scanning a single account in seconds",
    validation_alias="ACCOUNT_SCAN_TIMEOUT_SECONDS",
)

@property
def account_ids_list(self) -> list[str]:
    """Parse comma-separated account IDs into a list."""
    if not self.account_ids:
        return []
    return [aid.strip() for aid in self.account_ids.split(",") if aid.strip()]
```

### 1.2 Create Multi-Account Models
**New File**: `mcp_server/models/multi_account.py`

```python
"""Multi-account scanning data models.

This module contains Pydantic models for multi-account scanning functionality,
including account scan results, metadata, and aggregated compliance results.
Mirrors the structure of multi_region.py for consistency.
"""

from datetime import datetime
from pydantic import BaseModel, Field
from .violations import Violation


class AccountSummary(BaseModel):
    """Summary of compliance for a single AWS account.

    Provides a high-level overview of tag compliance status for resources
    in a specific AWS account.
    """

    account_id: str = Field(..., description="AWS account ID (12 digits)")
    account_alias: str | None = Field(None, description="AWS account alias if available")
    total_resources: int = Field(..., ge=0, description="Total resources in this account")
    compliant_resources: int = Field(..., ge=0, description="Compliant resources in this account")
    compliance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Compliance score for this account (0.0 to 1.0)"
    )
    violation_count: int = Field(..., ge=0, description="Number of violations in this account")
    cost_attribution_gap: float = Field(
        default=0.0,
        ge=0.0,
        description="Cost attribution gap for this account in USD"
    )


class AccountScanResult(BaseModel):
    """Result from scanning a single AWS account.

    Contains the detailed results of scanning resources in a specific AWS account,
    including success status, resources found, violations, and timing information.
    """

    account_id: str = Field(..., description="AWS account ID")
    account_alias: str | None = Field(None, description="AWS account alias if available")
    success: bool = Field(..., description="Whether the scan succeeded")
    resources: list[dict] = Field(
        default_factory=list,
        description="Resources found in this account"
    )
    violations: list[Violation] = Field(
        default_factory=list,
        description="Violations found in this account"
    )
    compliant_count: int = Field(
        default=0,
        ge=0,
        description="Number of compliant resources"
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if scan failed"
    )
    scan_duration_ms: int = Field(
        default=0,
        ge=0,
        description="Scan duration in milliseconds"
    )
    assumed_role_arn: str | None = Field(
        default=None,
        description="The IAM role ARN that was assumed for this account"
    )


class AccountScanMetadata(BaseModel):
    """Metadata about which accounts were scanned.

    Provides information about the accounts that were attempted during a
    multi-account scan, including which succeeded, failed, or were skipped.
    """

    total_accounts: int = Field(..., ge=0, description="Total accounts attempted")
    successful_accounts: list[str] = Field(
        default_factory=list,
        description="Account IDs scanned successfully"
    )
    failed_accounts: list[str] = Field(
        default_factory=list,
        description="Account IDs that failed to scan"
    )
    skipped_accounts: list[str] = Field(
        default_factory=list,
        description="Account IDs skipped (filtered out)"
    )


class MultiAccountComplianceResult(BaseModel):
    """Aggregated compliance result from multi-account scanning.

    Combines compliance results from scanning resources across multiple AWS accounts
    into a single unified result with overall metrics and per-account breakdowns.
    """

    compliance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall compliance score across all accounts"
    )
    total_resources: int = Field(
        ...,
        ge=0,
        description="Total resources across all accounts"
    )
    compliant_resources: int = Field(
        ...,
        ge=0,
        description="Compliant resources across all accounts"
    )
    violations: list[Violation] = Field(
        default_factory=list,
        description="All violations from all accounts"
    )
    cost_attribution_gap: float = Field(
        default=0.0,
        ge=0.0,
        description="Total cost attribution gap across all accounts in USD"
    )
    scan_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the scan was performed"
    )

    # Multi-account specific fields
    account_metadata: AccountScanMetadata = Field(
        ...,
        description="Metadata about which accounts were scanned"
    )
    account_breakdown: dict[str, AccountSummary] = Field(
        default_factory=dict,
        description="Per-account compliance summary keyed by account ID"
    )
```

### 1.3 Update Existing Models

**File**: `mcp_server/models/resource.py`

Add field after `region` (around line 17):
```python
account_id: str | None = Field(
    None,
    description="AWS account ID where the resource resides"
)
```

**File**: `mcp_server/models/violations.py`

Add field after `region`:
```python
account_id: str | None = Field(
    None,
    description="AWS account ID where the violation occurred"
)
```

**File**: `mcp_server/models/__init__.py`

Add exports:
```python
from .multi_account import (
    AccountSummary,
    AccountScanResult,
    AccountScanMetadata,
    MultiAccountComplianceResult,
)
```

---

## Phase 2: AWS Client Layer

### 2.1 Credential Provider
**New File**: `mcp_server/clients/credential_provider.py`

```python
"""Credential provider for multi-account AWS access via STS AssumeRole.

This module manages cross-account credential acquisition and caching,
automatically refreshing credentials before they expire.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class AssumeRoleError(Exception):
    """Raised when STS AssumeRole fails."""

    def __init__(self, message: str, account_id: str, role_arn: str):
        super().__init__(message)
        self.account_id = account_id
        self.role_arn = role_arn


@dataclass
class AssumedCredentials:
    """Temporary credentials obtained from STS AssumeRole."""

    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime
    account_id: str
    role_arn: str

    def is_expired(self, buffer_minutes: int = 5) -> bool:
        """Check if credentials are expired or about to expire."""
        return datetime.utcnow() >= self.expiration - timedelta(minutes=buffer_minutes)


class CredentialProvider:
    """Manages STS AssumeRole operations with credential caching.

    Credentials are cached per account and automatically refreshed
    when they are within 5 minutes of expiration.

    Usage:
        provider = CredentialProvider(
            role_arn_template="arn:aws:iam::{account_id}:role/{role_name}",
            default_role_name="FinOpsTagComplianceReadOnly",
        )

        creds = await provider.get_credentials("123456789012")
        # Use creds.access_key_id, creds.secret_access_key, creds.session_token
    """

    def __init__(
        self,
        role_arn_template: str = "arn:aws:iam::{account_id}:role/{role_name}",
        default_role_name: str = "FinOpsTagComplianceReadOnly",
        session_duration: int = 3600,
        session_name_prefix: str = "finops-tag-compliance",
    ):
        """Initialize the credential provider.

        Args:
            role_arn_template: Template for role ARN with {account_id} and {role_name} placeholders
            default_role_name: Default role name to assume
            session_duration: Duration of assumed role session in seconds (900-43200)
            session_name_prefix: Prefix for the role session name
        """
        self._role_arn_template = role_arn_template
        self._default_role_name = default_role_name
        self._session_duration = session_duration
        self._session_name_prefix = session_name_prefix
        self._sts_client = boto3.client("sts")
        self._credential_cache: dict[str, AssumedCredentials] = {}
        self._cache_lock = asyncio.Lock()
        self._local_account_id: Optional[str] = None

    async def get_local_account_id(self) -> str:
        """Get the account ID of the local/source account."""
        if self._local_account_id is None:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self._sts_client.get_caller_identity
            )
            self._local_account_id = response["Account"]
        return self._local_account_id

    async def get_credentials(
        self,
        account_id: str,
        role_name: Optional[str] = None,
    ) -> AssumedCredentials:
        """Get credentials for target account, using cache if valid.

        Args:
            account_id: Target AWS account ID
            role_name: Role name to assume (uses default if not specified)

        Returns:
            AssumedCredentials with temporary credentials

        Raises:
            AssumeRoleError: If AssumeRole fails
        """
        role_name = role_name or self._default_role_name
        cache_key = f"{account_id}:{role_name}"

        async with self._cache_lock:
            # Check cache for valid credentials
            if cache_key in self._credential_cache:
                creds = self._credential_cache[cache_key]
                if not creds.is_expired():
                    logger.debug(f"Using cached credentials for account {account_id}")
                    return creds
                else:
                    logger.debug(f"Cached credentials for account {account_id} expired, refreshing")

            # Assume role to get new credentials
            creds = await self._assume_role(account_id, role_name)
            self._credential_cache[cache_key] = creds
            return creds

    async def _assume_role(
        self,
        account_id: str,
        role_name: str,
    ) -> AssumedCredentials:
        """Perform STS AssumeRole operation.

        Args:
            account_id: Target AWS account ID
            role_name: Role name to assume

        Returns:
            AssumedCredentials with temporary credentials

        Raises:
            AssumeRoleError: If AssumeRole fails
        """
        role_arn = self._role_arn_template.format(
            account_id=account_id,
            role_name=role_name,
        )
        # Session name max 64 chars
        session_name = f"{self._session_name_prefix}-{account_id}"[:64]

        logger.info(f"Assuming role {role_arn} for account {account_id}")

        loop = asyncio.get_event_loop()

        try:
            response = await loop.run_in_executor(
                None,
                lambda: self._sts_client.assume_role(
                    RoleArn=role_arn,
                    RoleSessionName=session_name,
                    DurationSeconds=self._session_duration,
                ),
            )

            creds = response["Credentials"]
            assumed = AssumedCredentials(
                access_key_id=creds["AccessKeyId"],
                secret_access_key=creds["SecretAccessKey"],
                session_token=creds["SessionToken"],
                expiration=creds["Expiration"].replace(tzinfo=None),
                account_id=account_id,
                role_arn=role_arn,
            )

            logger.info(f"Successfully assumed role for account {account_id}, expires {assumed.expiration}")
            return assumed

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"Failed to assume role {role_arn}: {error_code} - {error_msg}")
            raise AssumeRoleError(
                f"Failed to assume role: {error_code} - {error_msg}",
                account_id=account_id,
                role_arn=role_arn,
            ) from e

    def clear_cache(self, account_id: Optional[str] = None) -> None:
        """Clear cached credentials.

        Args:
            account_id: If specified, only clear credentials for this account.
                       If None, clear all cached credentials.
        """
        if account_id:
            keys_to_remove = [k for k in self._credential_cache if k.startswith(f"{account_id}:")]
            for key in keys_to_remove:
                del self._credential_cache[key]
            logger.debug(f"Cleared cached credentials for account {account_id}")
        else:
            self._credential_cache.clear()
            logger.debug("Cleared all cached credentials")
```

### 2.2 Extend AWSClient
**File**: `mcp_server/clients/aws_client.py`

Add imports at top:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .credential_provider import AssumedCredentials
```

Add class method after `__init__` (around line 55):
```python
@classmethod
def from_credentials(
    cls,
    credentials: "AssumedCredentials",
    region: str = "us-east-1",
) -> "AWSClient":
    """Create an AWSClient using assumed role credentials.

    This factory method creates a new AWSClient instance that uses
    temporary credentials from an STS AssumeRole operation instead
    of the default credential chain.

    Args:
        credentials: AssumedCredentials from CredentialProvider
        region: AWS region for regional services

    Returns:
        AWSClient configured with assumed role credentials
    """
    # Create a new session with explicit credentials
    session = boto3.Session(
        aws_access_key_id=credentials.access_key_id,
        aws_secret_access_key=credentials.secret_access_key,
        aws_session_token=credentials.session_token,
    )

    # Create instance without calling __init__
    client = cls.__new__(cls)

    config = Config(
        region_name=region,
        retries={"max_attempts": 3, "mode": "adaptive"}
    )

    # Initialize all boto3 clients with the session
    client.region = region
    client.ec2 = session.client("ec2", config=config)
    client.rds = session.client("rds", config=config)
    client.s3 = session.client("s3", config=config)
    client.lambda_ = session.client("lambda", config=config)
    client.ecs = session.client("ecs", config=config)
    client.sts = session.client("sts", config=config)
    client.tagging = session.client("resourcegroupstaggingapi", config=config)
    # Cost Explorer is always us-east-1
    client.ce = session.client("ce", region_name="us-east-1")

    # Set account ID from credentials
    client._account_id = credentials.account_id
    client._assumed_role = True
    client._assumed_role_arn = credentials.role_arn

    # Initialize rate limiting state
    client._last_call_time: dict[str, float] = {}
    client._min_call_interval = 0.1

    return client
```

Add property (if not exists):
```python
@property
def account_id(self) -> str | None:
    """Return the AWS account ID for this client."""
    if self._account_id is None:
        # Lazy fetch if not set
        try:
            response = self.sts.get_caller_identity()
            self._account_id = response["Account"]
        except Exception:
            pass
    return self._account_id
```

### 2.3 AWS Client Pool
**New File**: `mcp_server/clients/aws_client_pool.py`

```python
"""Pool of AWSClient instances for multi-account scanning.

This module manages a pool of AWSClient instances, one per target account,
with automatic credential refresh and client reuse.
"""

import asyncio
import logging
from typing import Optional

from .aws_client import AWSClient
from .credential_provider import CredentialProvider, AssumeRoleError

logger = logging.getLogger(__name__)


class AWSClientPool:
    """Manages a pool of AWSClient instances for multiple AWS accounts.

    The pool maintains one client per account+region combination, reusing
    clients across requests. For the local account (where the server runs),
    no AssumeRole is needed.

    Usage:
        provider = CredentialProvider(...)
        pool = AWSClientPool(credential_provider=provider)
        pool.set_local_client(local_aws_client)

        client = await pool.get_client("123456789012")
        resources = await client.list_ec2_instances()
    """

    def __init__(
        self,
        credential_provider: CredentialProvider,
        default_region: str = "us-east-1",
    ):
        """Initialize the client pool.

        Args:
            credential_provider: Provider for cross-account credentials
            default_region: Default AWS region for clients
        """
        self._credential_provider = credential_provider
        self._default_region = default_region
        self._clients: dict[str, AWSClient] = {}
        self._lock = asyncio.Lock()
        self._local_client: Optional[AWSClient] = None
        self._local_account_id: Optional[str] = None

    def set_local_client(self, client: AWSClient) -> None:
        """Set the local account client (no AssumeRole needed).

        Args:
            client: AWSClient for the local/source account
        """
        self._local_client = client
        self._local_account_id = client.account_id
        logger.info(f"Local client set for account {self._local_account_id}")

    async def get_client(
        self,
        account_id: str,
        region: Optional[str] = None,
    ) -> AWSClient:
        """Get or create an AWSClient for the specified account.

        If the account is the local account, returns the local client.
        Otherwise, assumes the cross-account role and creates a new client.

        Args:
            account_id: Target AWS account ID
            region: AWS region (uses default if not specified)

        Returns:
            AWSClient for the specified account

        Raises:
            AssumeRoleError: If role assumption fails for cross-account
        """
        region = region or self._default_region

        # Check if this is the local account
        if self._local_client and self._local_account_id == account_id:
            logger.debug(f"Using local client for account {account_id}")
            return self._local_client

        cache_key = f"{account_id}:{region}"

        async with self._lock:
            # Check if we have a cached client
            if cache_key in self._clients:
                logger.debug(f"Using cached client for account {account_id} region {region}")
                return self._clients[cache_key]

            # Create new client with assumed credentials
            logger.info(f"Creating new client for account {account_id} region {region}")
            creds = await self._credential_provider.get_credentials(account_id)
            client = AWSClient.from_credentials(creds, region)
            self._clients[cache_key] = client

            return client

    async def get_clients_for_accounts(
        self,
        account_ids: list[str],
        region: Optional[str] = None,
    ) -> dict[str, AWSClient | Exception]:
        """Get clients for multiple accounts, returning errors for failed ones.

        Attempts to get a client for each account in parallel. If role assumption
        fails for an account, the exception is returned instead of a client.

        Args:
            account_ids: List of target AWS account IDs
            region: AWS region (uses default if not specified)

        Returns:
            Dict mapping account_id to either AWSClient or Exception
        """
        async def get_or_error(account_id: str) -> tuple[str, AWSClient | Exception]:
            try:
                client = await self.get_client(account_id, region)
                return (account_id, client)
            except AssumeRoleError as e:
                logger.warning(f"Failed to get client for account {account_id}: {e}")
                return (account_id, e)
            except Exception as e:
                logger.exception(f"Unexpected error getting client for account {account_id}")
                return (account_id, e)

        tasks = [get_or_error(aid) for aid in account_ids]
        results = await asyncio.gather(*tasks)

        return dict(results)

    def clear_clients(self, account_id: Optional[str] = None) -> None:
        """Clear cached clients.

        Args:
            account_id: If specified, only clear clients for this account.
                       If None, clear all clients except the local client.
        """
        if account_id:
            keys_to_remove = [k for k in self._clients if k.startswith(f"{account_id}:")]
            for key in keys_to_remove:
                del self._clients[key]
            logger.debug(f"Cleared cached clients for account {account_id}")
        else:
            self._clients.clear()
            logger.debug("Cleared all cached clients")
```

---

## Phase 3: Cache Isolation

### 3.1 Update Cache Key Generation
**File**: `mcp_server/services/compliance_service.py`

Modify `_generate_cache_key()` method (around line 51-84):

```python
def _generate_cache_key(
    self,
    resource_types: list[str],
    filters: dict | None = None,
    severity: str = "all",
) -> str:
    """Generate a unique cache key for compliance results.

    The key includes account_id to prevent cross-account cache pollution.
    """
    filters = filters or {}

    # Extract account_id from filters or use client's account
    account_id = filters.get("account_id") or self.aws_client.account_id or "default"

    # Build normalized dict for hashing
    normalized = {
        "account_id": account_id,  # NEW: Include account for cache isolation
        "aws_region": self.aws_client.region,
        "resource_types": sorted(resource_types),
        "filters": {k: v for k, v in filters.items() if k not in ("account_id", "account_ids")},
        "severity": severity,
    }

    json_str = json.dumps(normalized, sort_keys=True)
    hash_obj = hashlib.sha256(json_str.encode())
    cache_key = f"compliance:{hash_obj.hexdigest()}"

    return cache_key
```

---

## Phase 4: Multi-Account Service

### 4.1 Create Orchestration Service
**New File**: `mcp_server/services/multi_account_compliance_service.py`

```python
"""Multi-account compliance scanning orchestration.

This service orchestrates tag compliance scanning across multiple AWS accounts,
handling parallel execution, timeouts, and result aggregation.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

from ..clients.aws_client_pool import AWSClientPool
from ..clients.credential_provider import AssumeRoleError
from ..models.multi_account import (
    AccountScanMetadata,
    AccountScanResult,
    AccountSummary,
    MultiAccountComplianceResult,
)
from ..models.violations import Violation
from .compliance_service import ComplianceService
from .policy_service import PolicyService

logger = logging.getLogger(__name__)


class MultiAccountComplianceService:
    """Orchestrates compliance scanning across multiple AWS accounts.

    Scans multiple accounts in parallel with configurable concurrency limits
    and per-account timeouts. Results are aggregated into a single
    MultiAccountComplianceResult with per-account breakdowns.

    Usage:
        service = MultiAccountComplianceService(
            client_pool=pool,
            policy_service=policy_svc,
            max_concurrent=5,
        )

        result = await service.check_compliance_multi_account(
            account_ids=["111111111111", "222222222222"],
            resource_types=["ec2:instance", "rds:db"],
        )
    """

    def __init__(
        self,
        client_pool: AWSClientPool,
        policy_service: PolicyService,
        cache=None,
        max_concurrent: int = 5,
        timeout_seconds: int = 120,
    ):
        """Initialize the multi-account compliance service.

        Args:
            client_pool: Pool of AWS clients for each account
            policy_service: Service for loading tagging policy
            cache: Optional Redis cache for caching results
            max_concurrent: Maximum accounts to scan in parallel
            timeout_seconds: Timeout for scanning each account
        """
        self._client_pool = client_pool
        self._policy_service = policy_service
        self._cache = cache
        self._max_concurrent = max_concurrent
        self._timeout_seconds = timeout_seconds

    async def check_compliance_multi_account(
        self,
        account_ids: list[str],
        resource_types: list[str],
        filters: Optional[dict] = None,
        severity: str = "all",
        force_refresh: bool = False,
    ) -> MultiAccountComplianceResult:
        """Scan multiple accounts for tag compliance.

        Scans each account in parallel (up to max_concurrent) and aggregates
        the results. Failed accounts are tracked in metadata but don't fail
        the entire operation.

        Args:
            account_ids: List of AWS account IDs to scan
            resource_types: Resource types to scan (e.g., ["ec2:instance"])
            filters: Optional filters to apply
            severity: Minimum severity level for violations
            force_refresh: If True, bypass cache

        Returns:
            MultiAccountComplianceResult with aggregated results and per-account breakdown
        """
        logger.info(f"Starting multi-account compliance scan for {len(account_ids)} accounts")

        semaphore = asyncio.Semaphore(self._max_concurrent)

        async def scan_with_semaphore(account_id: str) -> AccountScanResult:
            async with semaphore:
                return await self._scan_single_account(
                    account_id=account_id,
                    resource_types=resource_types,
                    filters=filters,
                    severity=severity,
                    force_refresh=force_refresh,
                )

        # Scan all accounts concurrently (with semaphore limit)
        tasks = [scan_with_semaphore(aid) for aid in account_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        return self._aggregate_results(account_ids, results)

    async def _scan_single_account(
        self,
        account_id: str,
        resource_types: list[str],
        filters: Optional[dict],
        severity: str,
        force_refresh: bool,
    ) -> AccountScanResult:
        """Scan a single account with timeout.

        Args:
            account_id: AWS account ID to scan
            resource_types: Resource types to scan
            filters: Optional filters
            severity: Minimum severity
            force_refresh: Bypass cache

        Returns:
            AccountScanResult with scan results or error
        """
        start_time = time.time()

        try:
            # Get client for this account (30s timeout for credential acquisition)
            client = await asyncio.wait_for(
                self._client_pool.get_client(account_id),
                timeout=30,
            )

            # Create compliance service for this account's client
            compliance_svc = ComplianceService(
                aws_client=client,
                policy_service=self._policy_service,
                cache=self._cache,
            )

            # Run compliance check with timeout
            result = await asyncio.wait_for(
                compliance_svc.check_compliance(
                    resource_types=resource_types,
                    filters=filters,
                    severity=severity,
                    force_refresh=force_refresh,
                ),
                timeout=self._timeout_seconds,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # Add account_id to violations
            violations_with_account = []
            for v in result.violations:
                v_dict = v.model_dump()
                v_dict["account_id"] = account_id
                violations_with_account.append(Violation(**v_dict))

            logger.info(
                f"Account {account_id} scan complete: "
                f"{result.compliant_resources}/{result.total_resources} compliant, "
                f"{len(result.violations)} violations, {duration_ms}ms"
            )

            return AccountScanResult(
                account_id=account_id,
                success=True,
                violations=violations_with_account,
                compliant_count=result.compliant_resources,
                scan_duration_ms=duration_ms,
            )

        except AssumeRoleError as e:
            logger.error(f"Failed to assume role for account {account_id}: {e}")
            return AccountScanResult(
                account_id=account_id,
                success=False,
                error_message=f"AssumeRole failed: {e.role_arn}",
                scan_duration_ms=int((time.time() - start_time) * 1000),
                assumed_role_arn=e.role_arn,
            )

        except asyncio.TimeoutError:
            logger.error(f"Scan timed out for account {account_id} after {self._timeout_seconds}s")
            return AccountScanResult(
                account_id=account_id,
                success=False,
                error_message=f"Scan timed out after {self._timeout_seconds}s",
                scan_duration_ms=self._timeout_seconds * 1000,
            )

        except Exception as e:
            logger.exception(f"Error scanning account {account_id}")
            return AccountScanResult(
                account_id=account_id,
                success=False,
                error_message=str(e),
                scan_duration_ms=int((time.time() - start_time) * 1000),
            )

    def _aggregate_results(
        self,
        account_ids: list[str],
        results: list[AccountScanResult | BaseException],
    ) -> MultiAccountComplianceResult:
        """Aggregate per-account results into unified result.

        Args:
            account_ids: Original list of account IDs
            results: Results from scanning each account

        Returns:
            MultiAccountComplianceResult with aggregated metrics
        """
        successful = []
        failed = []
        all_violations: list[Violation] = []
        total_resources = 0
        total_compliant = 0
        total_cost_gap = 0.0
        account_breakdown: dict[str, AccountSummary] = {}

        for account_id, result in zip(account_ids, results):
            # Handle exceptions from asyncio.gather
            if isinstance(result, BaseException):
                failed.append(account_id)
                logger.error(f"Account {account_id} scan raised exception: {result}")
                continue

            if result.success:
                successful.append(account_id)
                all_violations.extend(result.violations)

                # Calculate resource count from compliant + violations
                resource_count = result.compliant_count + len(result.violations)
                total_resources += resource_count
                total_compliant += result.compliant_count

                # Calculate compliance score for this account
                score = result.compliant_count / max(resource_count, 1) if resource_count > 0 else 1.0

                account_breakdown[account_id] = AccountSummary(
                    account_id=account_id,
                    total_resources=resource_count,
                    compliant_resources=result.compliant_count,
                    compliance_score=score,
                    violation_count=len(result.violations),
                    cost_attribution_gap=0.0,  # Could be populated from cost service
                )
            else:
                failed.append(account_id)

        # Calculate overall compliance score
        compliance_score = total_compliant / max(total_resources, 1) if total_resources > 0 else 1.0

        logger.info(
            f"Multi-account scan complete: {len(successful)}/{len(account_ids)} accounts, "
            f"{total_compliant}/{total_resources} resources compliant, "
            f"score={compliance_score:.2%}"
        )

        return MultiAccountComplianceResult(
            compliance_score=compliance_score,
            total_resources=total_resources,
            compliant_resources=total_compliant,
            violations=all_violations,
            cost_attribution_gap=total_cost_gap,
            scan_timestamp=datetime.utcnow(),
            account_metadata=AccountScanMetadata(
                total_accounts=len(account_ids),
                successful_accounts=successful,
                failed_accounts=failed,
            ),
            account_breakdown=account_breakdown,
        )
```

---

## Phase 5: Integration

### 5.1 Update ServiceContainer
**File**: `mcp_server/container.py`

Add imports at top:
```python
from .clients.credential_provider import CredentialProvider
from .clients.aws_client_pool import AWSClientPool
from .services.multi_account_compliance_service import MultiAccountComplianceService
```

Add instance variables in `__init__` (around line 87):
```python
self._credential_provider: Optional[CredentialProvider] = None
self._aws_client_pool: Optional[AWSClientPool] = None
self._multi_account_compliance_service: Optional[MultiAccountComplianceService] = None
```

Add initialization in `initialize()` after compliance service (after line ~165):
```python
# 6b. Multi-account services (if enabled)
if s.multi_account_enabled and s.account_ids_list:
    try:
        self._credential_provider = CredentialProvider(
            role_arn_template=s.assume_role_arn_template,
            default_role_name=s.assume_role_name,
            session_duration=s.assume_role_session_duration,
        )
        self._aws_client_pool = AWSClientPool(
            credential_provider=self._credential_provider,
            default_region=s.aws_region,
        )
        # Add local client to pool (no AssumeRole needed for local account)
        if self._aws_client:
            self._aws_client_pool.set_local_client(self._aws_client)

        self._multi_account_compliance_service = MultiAccountComplianceService(
            client_pool=self._aws_client_pool,
            policy_service=self._policy_service,
            cache=self._redis_cache,
            max_concurrent=s.max_concurrent_accounts,
            timeout_seconds=s.account_scan_timeout_seconds,
        )
        logger.info(
            f"ServiceContainer: multi-account services initialized "
            f"(accounts={s.account_ids_list})"
        )
    except Exception as e:
        logger.warning(f"ServiceContainer: failed to initialize multi-account services: {e}")
elif s.multi_account_enabled:
    logger.warning("ServiceContainer: multi-account enabled but no account IDs configured")
```

Add accessor properties at the end:
```python
@property
def credential_provider(self) -> Optional[CredentialProvider]:
    return self._credential_provider

@property
def aws_client_pool(self) -> Optional[AWSClientPool]:
    return self._aws_client_pool

@property
def multi_account_compliance_service(self) -> Optional[MultiAccountComplianceService]:
    return self._multi_account_compliance_service
```

### 5.2 Update check_tag_compliance Tool
**File**: `mcp_server/tools/check_tag_compliance.py`

Update function signature and add multi-account logic:

```python
from typing import Optional, Union
from ..models.multi_account import MultiAccountComplianceResult
from ..services.multi_account_compliance_service import MultiAccountComplianceService


async def check_tag_compliance(
    compliance_service: ComplianceService,
    resource_types: list[str],
    filters: dict | None = None,
    severity: str = "all",
    history_service: HistoryService | None = None,
    store_snapshot: bool = False,
    force_refresh: bool = False,
    # Multi-account parameters
    account_ids: list[str] | None = None,
    multi_account_service: MultiAccountComplianceService | None = None,
) -> Union[ComplianceResult, MultiAccountComplianceResult]:
    """Check tag compliance for AWS resources.

    Args:
        compliance_service: Service for single-account compliance checks
        resource_types: List of resource types to check
        filters: Optional filters (region, tags, etc.)
        severity: Minimum severity level
        history_service: Optional history service for snapshots
        store_snapshot: Whether to store result in history
        force_refresh: Bypass cache
        account_ids: Optional list of account IDs for multi-account scan
        multi_account_service: Service for multi-account scanning

    Returns:
        ComplianceResult for single-account or MultiAccountComplianceResult for multi-account
    """
    # Multi-account path
    if account_ids and multi_account_service:
        return await multi_account_service.check_compliance_multi_account(
            account_ids=account_ids,
            resource_types=resource_types,
            filters=filters,
            severity=severity,
            force_refresh=force_refresh,
        )

    # Single-account path (existing logic)
    result = await compliance_service.check_compliance(
        resource_types=resource_types,
        filters=filters,
        severity=severity,
        force_refresh=force_refresh,
    )

    # Store snapshot if requested
    if store_snapshot and history_service:
        await history_service.store_scan(result)

    return result
```

### 5.3 Update stdio_server.py
**File**: `mcp_server/stdio_server.py`

Update the `check_tag_compliance` tool to accept `account_ids`:

```python
@mcp.tool()
async def check_tag_compliance(
    resource_types: list[str],
    filters: dict[str, str] | None = None,
    severity: str = "all",
    store_snapshot: bool = False,
    force_refresh: bool = False,
    account_ids: list[str] | None = None,  # NEW
) -> str:
    """Check tag compliance for AWS resources.

    Args:
        resource_types: Resource types to check (e.g., ["ec2:instance", "rds:db"])
        filters: Optional filters (region, tags)
        severity: Minimum severity (all, critical, high, medium, low)
        store_snapshot: Store result in compliance history
        force_refresh: Bypass cache and fetch fresh data
        account_ids: Optional list of AWS account IDs for cross-account scanning
                    (requires MULTI_ACCOUNT_ENABLED=true and cross-account IAM roles)

    Returns:
        JSON compliance result with score, violations, and resource counts
    """
    # ... existing validation ...

    # Route to multi-account service if account_ids provided
    if account_ids and _container.multi_account_compliance_service:
        result = await _container.multi_account_compliance_service.check_compliance_multi_account(
            account_ids=account_ids,
            resource_types=resource_types,
            filters=filters,
            severity=severity,
            force_refresh=force_refresh,
        )
    else:
        result = await _check(
            compliance_service=_container.compliance_service,
            resource_types=resource_types,
            # ... existing params ...
        )

    return result.model_dump_json(indent=2)
```

---

## Files Summary

### New Files (4)
| File | Purpose |
|------|---------|
| `mcp_server/models/multi_account.py` | Multi-account data models |
| `mcp_server/clients/credential_provider.py` | STS AssumeRole + credential caching |
| `mcp_server/clients/aws_client_pool.py` | Pool of per-account AWS clients |
| `mcp_server/services/multi_account_compliance_service.py` | Multi-account orchestration |

### Modified Files (8)
| File | Changes |
|------|---------|
| `mcp_server/config.py` | Add 7 multi-account config fields + helper property |
| `mcp_server/models/resource.py` | Add `account_id` field |
| `mcp_server/models/violations.py` | Add `account_id` field |
| `mcp_server/models/__init__.py` | Export new multi-account models |
| `mcp_server/clients/aws_client.py` | Add `from_credentials()` factory method |
| `mcp_server/services/compliance_service.py` | Update cache key to include account_id |
| `mcp_server/container.py` | Wire up multi-account services |
| `mcp_server/stdio_server.py` | Add `account_ids` parameter to tool |

---

## Testing Strategy

### Unit Tests
- `tests/unit/test_credential_provider.py`
  - Test AssumeRole success with valid credentials
  - Test AssumeRoleError on ClientError
  - Test credential caching and expiration
  - Test cache refresh before expiration

- `tests/unit/test_aws_client_pool.py`
  - Test local client passthrough
  - Test client creation for new accounts
  - Test client caching
  - Test error handling for failed assumptions

- `tests/unit/test_multi_account_compliance_service.py`
  - Test single account scanning
  - Test parallel scanning with semaphore
  - Test timeout handling
  - Test partial failure (some accounts fail)
  - Test result aggregation

### Integration Tests
- `tests/integration/test_multi_account_scanning.py`
  - Test with moto mocking multiple accounts
  - Test AssumeRole chain
  - Test end-to-end compliance check

### Property Tests
- `tests/property/test_multi_account_aggregation.py`
  - Test compliance score always in [0, 1]
  - Test total_resources = sum of per-account resources
  - Test compliant + violations = total for each account

---

## Verification Steps

1. **Configuration loads correctly**:
   ```bash
   MULTI_ACCOUNT_ENABLED=true AWS_ACCOUNT_IDS=111,222 python -c "from mcp_server.config import settings; print(settings().account_ids_list)"
   ```

2. **Single-account still works** (backward compatible):
   ```bash
   python -m mcp_server.stdio_server
   # Test with MCP Inspector - should work without multi-account config
   ```

3. **Unit tests pass**:
   ```bash
   python run_tests.py --unit
   ```

4. **Integration with MCP Inspector**:
   ```bash
   npx @modelcontextprotocol/inspector python -m mcp_server.stdio_server
   # Call check_tag_compliance with account_ids parameter
   ```

---

## IAM Requirements

Each target account needs a role with trust policy allowing the source account:

**Role Name**: `FinOpsTagComplianceReadOnly` (configurable via `AWS_ASSUME_ROLE_NAME`)

**Trust Policy** (in each target account):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::SOURCE_ACCOUNT_ID:root"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

**Permission Policy**: Same read-only permissions as documented in `docs/IAM_PERMISSIONS.md`
