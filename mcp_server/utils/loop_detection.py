# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Loop detection utility for preventing repeated tool calls."""

import hashlib
import json
import logging
from typing import Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from ..clients.cache import RedisCache
from ..utils.correlation import get_correlation_id

logger = logging.getLogger(__name__)

DEFAULT_MAX_IDENTICAL_CALLS = 3
DEFAULT_SLIDING_WINDOW_SECONDS = 300


@dataclass
class LoopDetectionEvent:
    """Event data for a loop detection occurrence."""

    timestamp: datetime
    session_id: str
    tool_name: str
    call_signature: str
    call_count: int
    max_calls: int
    correlation_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "event_type": "loop_detected",
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "call_signature": self.call_signature,
            "call_count": self.call_count,
            "max_calls": self.max_calls,
            "correlation_id": self.correlation_id,
        }


class LoopDetectedError(Exception):
    """Raised when a loop is detected."""

    def __init__(
        self,
        tool_name: str,
        call_signature: str,
        call_count: int,
        max_calls: int,
        session_id: Optional[str] = None,
        message: Optional[str] = None,
    ):
        self.tool_name = tool_name
        self.call_signature = call_signature
        self.call_count = call_count
        self.max_calls = max_calls
        self.session_id = session_id
        self.message = message or (
            f"Loop detected: Tool '{tool_name}' called {call_count} times "
            f"with identical parameters (max: {max_calls})"
        )
        super().__init__(self.message)


class LoopDetector:
    """Detects loops by tracking tool call signatures per session."""

    LOOP_KEY_PREFIX = "loop:session:"
    STATS_KEY_PREFIX = "loop:stats:"
    GLOBAL_STATS_KEY = "loop:global_stats"
    LOOP_EVENTS_KEY = "loop:events"
    LOOPS_BY_TOOL_KEY = "loop:by_tool"

    def __init__(
        self,
        redis_cache: Optional[RedisCache] = None,
        max_identical_calls: int = DEFAULT_MAX_IDENTICAL_CALLS,
        sliding_window_seconds: int = DEFAULT_SLIDING_WINDOW_SECONDS,
    ):
        self._cache = redis_cache
        self._max_identical_calls = max_identical_calls
        self._sliding_window_seconds = sliding_window_seconds
        self._local_history: dict[str, list[tuple[str, datetime]]] = {}
        self._local_stats: dict[str, int] = {}
        self._total_loops_detected: int = 0
        self._last_loop_event: Optional[LoopDetectionEvent] = None
        self._loop_events_by_tool: dict[str, int] = {}
        self._loop_events_history: list[LoopDetectionEvent] = []
        logger.info(f"LoopDetector initialized: max_identical_calls={max_identical_calls}")

    @property
    def max_identical_calls(self) -> int:
        return self._max_identical_calls

    @property
    def sliding_window_seconds(self) -> int:
        return self._sliding_window_seconds

    def generate_call_signature(self, tool_name: str, parameters: dict) -> str:
        """Generate a unique signature for a tool call."""
        param_str = json.dumps(parameters, sort_keys=True, default=str)
        combined = f"{tool_name}:{param_str}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    async def check_for_loop(
        self,
        session_id: str,
        tool_name: str,
        parameters: dict,
    ) -> tuple[bool, int]:
        """
        Check if this call would create a loop.

        Returns:
            Tuple of (is_loop, call_count)
        """
        signature = self.generate_call_signature(tool_name, parameters)
        key = f"{self.LOOP_KEY_PREFIX}{session_id}:{signature}"

        now = datetime.now()
        cutoff = now - timedelta(seconds=self._sliding_window_seconds)

        # Use Redis if available
        if self._cache and self._cache.is_connected():
            try:
                count_str = await self._cache.get(key)
                count = int(count_str) if count_str else 0
                count += 1
                await self._cache.set(key, str(count), ttl=self._sliding_window_seconds)

                if count > self._max_identical_calls:
                    self._record_loop_event(session_id, tool_name, signature, count)
                    return True, count
                return False, count
            except Exception as e:
                logger.warning(f"Redis error in loop detection: {e}, falling back to local")

        # Fall back to local tracking
        if session_id not in self._local_history:
            self._local_history[session_id] = []

        # Clean old entries
        self._local_history[session_id] = [
            (sig, ts) for sig, ts in self._local_history[session_id] if ts > cutoff
        ]

        # Count matching signatures
        count = sum(1 for sig, _ in self._local_history[session_id] if sig == signature)
        count += 1

        # Add this call
        self._local_history[session_id].append((signature, now))

        if count > self._max_identical_calls:
            self._record_loop_event(session_id, tool_name, signature, count)
            return True, count

        return False, count

    async def record_call(
        self,
        session_id: str,
        tool_name: str,
        parameters: dict,
    ) -> tuple[bool, int]:
        """
        Record a tool call and check for loops.

        This is the primary API for loop detection. It records the call
        and raises LoopDetectedError if a loop is detected.

        Args:
            session_id: The session identifier
            tool_name: Name of the tool being called
            parameters: Tool parameters

        Returns:
            Tuple of (loop_detected, call_count)

        Raises:
            LoopDetectedError: If a loop is detected
        """
        is_loop, call_count = await self.check_for_loop(
            session_id=session_id,
            tool_name=tool_name,
            parameters=parameters,
        )

        if is_loop:
            signature = self.generate_call_signature(tool_name, parameters)
            raise LoopDetectedError(
                tool_name=tool_name,
                call_signature=signature,
                call_count=call_count,
                max_calls=self._max_identical_calls,
                session_id=session_id,
            )

        return is_loop, call_count

    def _record_loop_event(
        self, session_id: str, tool_name: str, signature: str, count: int
    ) -> None:
        """Record a loop detection event."""
        self._total_loops_detected += 1
        self._loop_events_by_tool[tool_name] = self._loop_events_by_tool.get(tool_name, 0) + 1

        event = LoopDetectionEvent(
            timestamp=datetime.now(),
            session_id=session_id,
            tool_name=tool_name,
            call_signature=signature,
            call_count=count,
            max_calls=self._max_identical_calls,
            correlation_id=get_correlation_id(),
        )
        self._last_loop_event = event
        self._loop_events_history.append(event)

        # Keep only last 100 events
        if len(self._loop_events_history) > 100:
            self._loop_events_history = self._loop_events_history[-100:]

        logger.warning(f"Loop detected: {event.to_dict()}")

    async def get_loop_detection_stats(self, session_id: Optional[str] = None) -> dict:
        """Get loop detection statistics."""
        stats = {
            "enabled": True,
            "max_identical_calls": self._max_identical_calls,
            "sliding_window_seconds": self._sliding_window_seconds,
            "loops_detected_total": self._total_loops_detected,
            "loops_by_tool": self._loop_events_by_tool.copy(),
            "active_sessions": len(self._local_history),
            "last_loop_detected_at": (
                self._last_loop_event.timestamp.isoformat() if self._last_loop_event else None
            ),
            "last_loop_tool_name": (
                self._last_loop_event.tool_name if self._last_loop_event else None
            ),
            "last_loop_session_id": (
                self._last_loop_event.session_id if self._last_loop_event else None
            ),
        }
        return stats

    def get_recent_loop_events(self, limit: int = 10) -> list[dict]:
        """Get recent loop detection events."""
        events = self._loop_events_history[-limit:]
        return [e.to_dict() for e in events]

    async def reset_session(self, session_id: str) -> None:
        """Reset loop tracking for a session."""
        if session_id in self._local_history:
            del self._local_history[session_id]

        if self._cache and self._cache.is_connected():
            # Would need to track keys per session to delete from Redis
            pass


# Global loop detector instance
_loop_detector: Optional[LoopDetector] = None


def get_loop_detector() -> Optional[LoopDetector]:
    """Get the global loop detector instance."""
    return _loop_detector


def set_loop_detector(detector: LoopDetector) -> None:
    """Set the global loop detector instance."""
    global _loop_detector
    _loop_detector = detector
