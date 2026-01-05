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
        message: Optional[str] = None
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