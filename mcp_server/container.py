# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Service container for dependency wiring and lifecycle management.

This module provides a ServiceContainer that initializes and holds
all service instances, replacing scattered global state and the
service initialization code previously in main.py's lifespan.

The container is protocol-agnostic -- it can be used by the MCP server,
an HTTP server, a CLI tool, a Lambda handler, or any other entry point.

Phase 1.9: Core Library Extraction
"""

import logging
from typing import Optional

from .clients.aws_client import AWSClient
from .clients.cache import RedisCache
from .clients.regional_client_factory import RegionalClientFactory
from .config import CoreSettings, Settings, settings as get_default_settings
from .middleware.budget_middleware import BudgetTracker
from .services.audit_service import AuditService
from .services.compliance_service import ComplianceService
from .services.history_service import HistoryService
from .services.multi_region_scanner import MultiRegionScanner
from .services.policy_service import PolicyService
from .services.region_discovery_service import RegionDiscoveryService
from .services.security_service import (
    SecurityService,
    configure_security_logging,
)
from .utils.loop_detection import LoopDetector

logger = logging.getLogger(__name__)


class ServiceContainer:
    """
    Wires together all services with proper dependency injection.

    Replaces the scattered initialization in main.py lifespan and
    eliminates global singleton patterns (get_budget_tracker,
    get_loop_detector, get_security_service, etc.).

    Usage::

        container = ServiceContainer()          # uses default settings
        await container.initialize()

        # Access services
        result = await some_tool(
            compliance_service=container.compliance_service,
            ...
        )

        # Shutdown
        await container.shutdown()

    Or with custom settings::

        container = ServiceContainer(settings=my_settings)
        await container.initialize()
    """

    def __init__(self, settings: Optional[CoreSettings] = None) -> None:
        """
        Create a ServiceContainer.

        Args:
            settings: Application settings. Accepts either CoreSettings
                      or ServerSettings (which extends CoreSettings).
                      If None, loads from environment variables / .env
                      file via the default ``settings()`` helper.
        """
        self._settings: CoreSettings = settings or get_default_settings()
        self._initialized = False

        # Service instances (populated by initialize())
        self._redis_cache: Optional[RedisCache] = None
        self._audit_service: Optional[AuditService] = None
        self._history_service: Optional[HistoryService] = None
        self._aws_client: Optional[AWSClient] = None
        self._policy_service: Optional[PolicyService] = None
        self._compliance_service: Optional[ComplianceService] = None
        self._security_service: Optional[SecurityService] = None
        self._budget_tracker: Optional[BudgetTracker] = None
        self._loop_detector: Optional[LoopDetector] = None
        self._multi_region_scanner: Optional[MultiRegionScanner] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """
        Initialize all services.

        Services are initialized in dependency order. Each service
        catches its own initialization errors so that partial startup
        is possible (e.g. Redis unavailable → cache is None but
        everything else still works).
        """
        if self._initialized:
            logger.warning("ServiceContainer.initialize() called more than once")
            return

        s = self._settings
        logger.info("ServiceContainer: initializing services")

        # 1. Redis cache
        try:
            self._redis_cache = await RedisCache.create(redis_url=s.redis_url)
            logger.info("ServiceContainer: Redis cache initialized")
        except Exception as e:
            logger.warning(f"ServiceContainer: failed to initialize Redis cache: {e}")
            self._redis_cache = None

        # 2. Audit service (SQLite)
        try:
            self._audit_service = AuditService(db_path=s.audit_db_path)
            logger.info("ServiceContainer: audit service initialized")
        except Exception as e:
            logger.error(f"ServiceContainer: failed to initialize audit service: {e}")
            self._audit_service = None

        # 3. History service (SQLite)
        try:
            self._history_service = HistoryService(db_path=s.history_db_path)
            logger.info(
                f"ServiceContainer: history service initialized "
                f"(db={s.history_db_path})"
            )
        except Exception as e:
            logger.warning(f"ServiceContainer: failed to initialize history service: {e}")
            self._history_service = None

        # 4. AWS client
        try:
            self._aws_client = AWSClient(region=s.aws_region)
            logger.info(f"ServiceContainer: AWS client initialized (region={s.aws_region})")
        except Exception as e:
            logger.warning(f"ServiceContainer: failed to initialize AWS client: {e}")
            self._aws_client = None

        # 5. Policy service
        try:
            self._policy_service = PolicyService(policy_path=s.policy_path)
            logger.info(f"ServiceContainer: policy service initialized (path={s.policy_path})")
        except Exception as e:
            logger.warning(f"ServiceContainer: failed to initialize policy service: {e}")
            self._policy_service = None

        # 6. Compliance service (depends on AWS + policy)
        if self._aws_client and self._policy_service:
            try:
                self._compliance_service = ComplianceService(
                    aws_client=self._aws_client,
                    policy_service=self._policy_service,
                    cache=self._redis_cache,
                )
                logger.info("ServiceContainer: compliance service initialized")
            except Exception as e:
                logger.warning(
                    f"ServiceContainer: failed to initialize compliance service: {e}"
                )
                self._compliance_service = None

        # 6b. Multi-region scanner (depends on AWS + policy + compliance + cache)
        # Requirements: 7.1, 7.2, 7.3
        if s.multi_region_enabled and self._aws_client and self._policy_service:
            try:
                region_discovery = RegionDiscoveryService(
                    ec2_client=self._aws_client.ec2,
                    cache=self._redis_cache,
                    cache_ttl=s.region_cache_ttl_seconds,
                )
                regional_client_factory = RegionalClientFactory()
                
                # Factory function to create ComplianceService for a regional client
                # Captures policy_service and redis_cache from container scope
                def make_compliance_service(aws_client: AWSClient) -> ComplianceService:
                    return ComplianceService(
                        aws_client=aws_client,
                        policy_service=self._policy_service,
                        cache=self._redis_cache,
                    )
                
                self._multi_region_scanner = MultiRegionScanner(
                    region_discovery=region_discovery,
                    client_factory=regional_client_factory,
                    compliance_service_factory=make_compliance_service,
                    max_concurrent_regions=s.max_concurrent_regions,
                    region_timeout_seconds=s.region_scan_timeout_seconds,
                    multi_region_enabled=s.multi_region_enabled,
                    default_region=s.aws_region,
                )
                logger.info(
                    f"ServiceContainer: multi-region scanner initialized "
                    f"(max_concurrent={s.max_concurrent_regions}, "
                    f"timeout={s.region_scan_timeout_seconds}s)"
                )
            except Exception as e:
                logger.warning(
                    f"ServiceContainer: failed to initialize multi-region scanner: {e}"
                )
                self._multi_region_scanner = None
        else:
            if not s.multi_region_enabled:
                logger.info("ServiceContainer: multi-region scanning is disabled")
            self._multi_region_scanner = None

        # 7. Budget tracker (Requirements: 15.3)
        if s.budget_tracking_enabled:
            try:
                self._budget_tracker = BudgetTracker(
                    redis_cache=self._redis_cache,
                    max_calls_per_session=s.max_tool_calls_per_session,
                    session_ttl_seconds=s.session_budget_ttl_seconds,
                )
                logger.info(
                    f"ServiceContainer: budget tracker initialized "
                    f"(max_calls={s.max_tool_calls_per_session}, "
                    f"ttl={s.session_budget_ttl_seconds}s)"
                )
            except Exception as e:
                logger.warning(f"ServiceContainer: failed to initialize budget tracker: {e}")
                self._budget_tracker = None
        else:
            logger.info("ServiceContainer: budget tracking is disabled")

        # 8. Loop detector (Requirements: 15.4)
        if s.loop_detection_enabled:
            try:
                self._loop_detector = LoopDetector(
                    redis_cache=self._redis_cache,
                    max_identical_calls=s.max_identical_calls,
                    sliding_window_seconds=s.loop_detection_window_seconds,
                )
                logger.info(
                    f"ServiceContainer: loop detector initialized "
                    f"(max_identical_calls={s.max_identical_calls}, "
                    f"window={s.loop_detection_window_seconds}s)"
                )
            except Exception as e:
                logger.warning(f"ServiceContainer: failed to initialize loop detector: {e}")
                self._loop_detector = None
        else:
            logger.info("ServiceContainer: loop detection is disabled")

        # 9. Security service (Requirements: 16.4)
        if s.security_monitoring_enabled:
            try:
                configure_security_logging(
                    log_group=s.cloudwatch_log_group,
                    log_stream=s.security_log_stream,
                    region=s.aws_region,
                )
                self._security_service = SecurityService(
                    redis_cache=self._redis_cache,
                    max_unknown_tool_attempts=s.max_unknown_tool_attempts,
                    window_seconds=s.security_event_window_seconds,
                )
                logger.info(
                    f"ServiceContainer: security service initialized "
                    f"(max_unknown_tool_attempts={s.max_unknown_tool_attempts}, "
                    f"window={s.security_event_window_seconds}s)"
                )
            except Exception as e:
                logger.warning(f"ServiceContainer: failed to initialize security service: {e}")
                self._security_service = None
        else:
            logger.info("ServiceContainer: security monitoring is disabled")

        self._initialized = True
        logger.info("ServiceContainer: all services initialized")

    async def shutdown(self) -> None:
        """Clean up connections and resources."""
        logger.info("ServiceContainer: shutting down")
        if self._redis_cache:
            try:
                await self._redis_cache.close()
            except Exception as e:
                logger.warning(f"ServiceContainer: error closing Redis: {e}")
        self._initialized = False
        logger.info("ServiceContainer: shutdown complete")

    # ------------------------------------------------------------------
    # Accessor properties
    # ------------------------------------------------------------------

    @property
    def settings(self) -> CoreSettings:
        return self._settings

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def redis_cache(self) -> Optional[RedisCache]:
        return self._redis_cache

    @property
    def audit_service(self) -> Optional[AuditService]:
        return self._audit_service

    @property
    def history_service(self) -> Optional[HistoryService]:
        return self._history_service

    @property
    def aws_client(self) -> Optional[AWSClient]:
        return self._aws_client

    @property
    def policy_service(self) -> Optional[PolicyService]:
        return self._policy_service

    @property
    def compliance_service(self) -> Optional[ComplianceService]:
        return self._compliance_service

    @property
    def security_service(self) -> Optional[SecurityService]:
        return self._security_service

    @property
    def budget_tracker(self) -> Optional[BudgetTracker]:
        return self._budget_tracker

    @property
    def loop_detector(self) -> Optional[LoopDetector]:
        return self._loop_detector

    @property
    def multi_region_scanner(self) -> Optional[MultiRegionScanner]:
        return self._multi_region_scanner
