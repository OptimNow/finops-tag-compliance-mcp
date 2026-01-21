# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Budget tracking middleware for MCP tool calls.

This module provides middleware for tracking and enforcing tool-call budgets
per session. It uses Redis to track call counts with TTL for automatic cleanup.

Requirements: 15.3
"""

import logging
from typing import Optional
from datetime import timedelta

from ..clients.cache import RedisCache
from ..utils.correlation import get_correlation_id

logger = logging.getLogger(__name__)

# Default configuration values
DEFAULT_MAX_TOOL_CALLS_PER_SESSION = 100
DEFAULT_SESSION_TTL_SECONDS = 3600  # 1 hour


class BudgetExhaustedError(Exception):
    """Raised when a session's tool-call budget is exhausted."""

    def __init__(
        self, session_id: str, current_count: int, max_calls: int, message: Optional[str] = None
    ):
        self.session_id = session_id
        self.current_count = current_count
        self.max_calls = max_calls
        self.message = message or (
            f"Tool-call budget exhausted for session {session_id}. "
            f"Used {current_count}/{max_calls} calls."
        )
        super().__init__(self.message)


class BudgetTracker:
    """
    Tracks tool-call budgets per session using Redis.

    Each session has a maximum number of tool calls allowed.
    When the budget is exhausted, further calls are rejected
    with a graceful degradation response.

    Requirements: 15.3
    """

    BUDGET_KEY_PREFIX = "budget:session:"

    def __init__(
        self,
        redis_cache: Optional[RedisCache] = None,
        max_calls_per_session: int = DEFAULT_MAX_TOOL_CALLS_PER_SESSION,
        session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    ):
        """
        Initialize the budget tracker.

        Args:
            redis_cache: Redis cache instance for storing budget data
            max_calls_per_session: Maximum tool calls allowed per session
            session_ttl_seconds: TTL for session budget data in Redis
        """
        self._cache = redis_cache
        self._max_calls = max_calls_per_session
        self._session_ttl = session_ttl_seconds
        self._local_counts: dict[str, int] = {}  # Fallback when Redis unavailable

        logger.info(
            f"BudgetTracker initialized: max_calls={max_calls_per_session}, "
            f"session_ttl={session_ttl_seconds}s"
        )

    @property
    def max_calls_per_session(self) -> int:
        """Get the maximum calls allowed per session."""
        return self._max_calls

    @property
    def session_ttl_seconds(self) -> int:
        """Get the session TTL in seconds."""
        return self._session_ttl

    def _get_budget_key(self, session_id: str) -> str:
        """Generate the Redis key for a session's budget."""
        return f"{self.BUDGET_KEY_PREFIX}{session_id}"

    async def get_current_count(self, session_id: str) -> int:
        """
        Get the current tool call count for a session.

        Args:
            session_id: The session identifier

        Returns:
            Current count of tool calls for the session
        """
        if not session_id:
            return 0

        # Try Redis first
        if self._cache:
            try:
                key = self._get_budget_key(session_id)
                cached_value = await self._cache.get(key)
                if cached_value is not None:
                    return int(cached_value)
                return 0
            except Exception as e:
                logger.warning(f"Failed to get budget count from Redis: {e}")

        # Fallback to local storage
        return self._local_counts.get(session_id, 0)

    async def increment_count(self, session_id: str) -> int:
        """
        Increment the tool call count for a session.

        Args:
            session_id: The session identifier

        Returns:
            New count after incrementing
        """
        if not session_id:
            return 0

        # Try Redis first
        if self._cache and self._cache._connected and self._cache._client:
            try:
                key = self._get_budget_key(session_id)
                # Use INCR for atomic increment
                new_count = await self._cache._client.incr(key)
                # Set TTL on first increment
                if new_count == 1:
                    await self._cache._client.expire(key, timedelta(seconds=self._session_ttl))
                return new_count
            except Exception as e:
                logger.warning(f"Failed to increment budget count in Redis: {e}")

        # Fallback to local storage
        current = self._local_counts.get(session_id, 0)
        new_count = current + 1
        self._local_counts[session_id] = new_count
        return new_count

    async def check_budget(self, session_id: str) -> tuple[bool, int, int]:
        """
        Check if a session has remaining budget.

        Args:
            session_id: The session identifier

        Returns:
            Tuple of (has_budget, current_count, max_calls)
        """
        current_count = await self.get_current_count(session_id)
        has_budget = current_count < self._max_calls
        return has_budget, current_count, self._max_calls

    async def consume_budget(self, session_id: str) -> tuple[bool, int, int]:
        """
        Attempt to consume one unit of budget for a session.

        This atomically checks and increments the budget counter.

        Args:
            session_id: The session identifier

        Returns:
            Tuple of (success, new_count, max_calls)

        Raises:
            BudgetExhaustedError: If budget is already exhausted
        """
        # Check current budget
        has_budget, current_count, max_calls = await self.check_budget(session_id)

        if not has_budget:
            logger.warning(
                f"Budget exhausted for session {session_id}: "
                f"{current_count}/{max_calls} calls used"
            )
            raise BudgetExhaustedError(
                session_id=session_id,
                current_count=current_count,
                max_calls=max_calls,
            )

        # Increment the counter
        new_count = await self.increment_count(session_id)

        # Double-check we didn't exceed (race condition protection)
        if new_count > max_calls:
            logger.warning(
                f"Budget exceeded after increment for session {session_id}: "
                f"{new_count}/{max_calls} calls"
            )
            raise BudgetExhaustedError(
                session_id=session_id,
                current_count=new_count,
                max_calls=max_calls,
            )

        logger.debug(
            f"Budget consumed for session {session_id}: " f"{new_count}/{max_calls} calls used"
        )

        return True, new_count, max_calls

    async def get_budget_status(self, session_id: str) -> dict:
        """
        Get detailed budget status for a session.

        Args:
            session_id: The session identifier

        Returns:
            Dictionary with budget status information
        """
        current_count = await self.get_current_count(session_id)
        remaining = max(0, self._max_calls - current_count)
        utilization = (current_count / self._max_calls * 100) if self._max_calls > 0 else 0

        return {
            "session_id": session_id,
            "current_count": current_count,
            "max_calls": self._max_calls,
            "remaining": remaining,
            "utilization_percent": round(utilization, 2),
            "is_exhausted": current_count >= self._max_calls,
        }

    async def reset_budget(self, session_id: str) -> bool:
        """
        Reset the budget for a session.

        Args:
            session_id: The session identifier

        Returns:
            True if reset was successful
        """
        if not session_id:
            return False

        # Try Redis first
        if self._cache:
            try:
                key = self._get_budget_key(session_id)
                await self._cache.delete(key)
                logger.info(f"Budget reset for session {session_id}")
                return True
            except Exception as e:
                logger.warning(f"Failed to reset budget in Redis: {e}")

        # Fallback to local storage
        if session_id in self._local_counts:
            del self._local_counts[session_id]
            logger.info(f"Budget reset for session {session_id} (local)")
            return True

        return False

    async def get_active_session_count(self) -> int:
        """
        Get the count of active sessions with budget tracking.

        Returns:
            Number of active sessions
        """
        # Try Redis first
        if self._cache and self._cache._connected and self._cache._client:
            try:
                # Count keys matching the budget prefix
                keys = []
                async for key in self._cache._client.scan_iter(match=f"{self.BUDGET_KEY_PREFIX}*"):
                    keys.append(key)
                return len(keys)
            except Exception as e:
                logger.warning(f"Failed to count active sessions in Redis: {e}")

        # Fallback to local storage
        return len(self._local_counts)


# Global budget tracker instance
_budget_tracker: Optional[BudgetTracker] = None


def get_budget_tracker() -> Optional[BudgetTracker]:
    """Get the global budget tracker instance."""
    return _budget_tracker


def set_budget_tracker(tracker: BudgetTracker) -> None:
    """Set the global budget tracker instance."""
    global _budget_tracker
    _budget_tracker = tracker


async def check_and_consume_budget(session_id: Optional[str] = None) -> tuple[bool, int, int]:
    """
    Check and consume budget for the current session.

    Uses the correlation ID as session ID if not provided.

    Args:
        session_id: Optional session identifier (uses correlation ID if not provided)

    Returns:
        Tuple of (success, current_count, max_calls)

    Raises:
        BudgetExhaustedError: If budget is exhausted
    """
    tracker = get_budget_tracker()
    if not tracker:
        # No budget tracking configured, allow all calls
        return True, 0, 0

    # Use correlation ID as session ID if not provided
    if not session_id:
        session_id = get_correlation_id()

    if not session_id:
        # No session ID available, allow the call
        logger.debug("No session ID available for budget tracking")
        return True, 0, 0

    return await tracker.consume_budget(session_id)
