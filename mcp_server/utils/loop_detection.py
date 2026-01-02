"""Loop detection utility for preventing repeated tool calls.

Requirements: 15.4
"""

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

    def _generate_call_signature(self, tool_name: str, parameters: dict) -> str:
        normalized_params = json.dumps(parameters, sort_keys=True, default=str)
        signature_input = f"{tool_name}:{normalized_params}"
        signature_hash = hashlib.sha256(signature_input.encode()).hexdigest()
        return signature_hash[:16]

    def _get_loop_key(self, session_id: str, call_signature: str) -> str:
        return f"{self.LOOP_KEY_PREFIX}{session_id}:{call_signature}"

    async def _get_call_count_redis(self, session_id: str, call_signature: str) -> int:
        if not self._cache or not self._cache._connected or not self._cache._client:
            return 0
        try:
            key = self._get_loop_key(session_id, call_signature)
            count = await self._cache.get(key)
            return int(count) if count is not None else 0
        except Exception as e:
            logger.warning(f"Failed to get call count from Redis: {e}")
            return 0

    async def _increment_call_count_redis(self, session_id: str, call_signature: str) -> int:
        if not self._cache or not self._cache._connected or not self._cache._client:
            return 0
        try:
            key = self._get_loop_key(session_id, call_signature)
            new_count = await self._cache._client.incr(key)
            if new_count == 1:
                await self._cache._client.expire(key, timedelta(seconds=self._sliding_window_seconds))
            return new_count
        except Exception as e:
            logger.warning(f"Failed to increment call count in Redis: {e}")
            return 0

    def _get_call_count_local(self, session_id: str, call_signature: str) -> int:
        key = f"{session_id}:{call_signature}"
        if key not in self._local_history:
            return 0
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=self._sliding_window_seconds)
        recent_calls = [(sig, ts) for sig, ts in self._local_history[key] if ts > cutoff]
        self._local_history[key] = recent_calls
        return len(recent_calls)

    def _increment_call_count_local(self, session_id: str, call_signature: str) -> int:
        key = f"{session_id}:{call_signature}"
        now = datetime.utcnow()
        if key not in self._local_history:
            self._local_history[key] = []
        self._local_history[key].append((call_signature, now))
        cutoff = now - timedelta(seconds=self._sliding_window_seconds)
        self._local_history[key] = [(sig, ts) for sig, ts in self._local_history[key] if ts > cutoff]
        return len(self._local_history[key])

    async def get_call_count(self, session_id: str, tool_name: str, parameters: dict) -> int:
        if not session_id:
            return 0
        call_signature = self._generate_call_signature(tool_name, parameters)
        if self._cache:
            count = await self._get_call_count_redis(session_id, call_signature)
            if count > 0:
                return count
        return self._get_call_count_local(session_id, call_signature)

    async def check_for_loop(self, session_id: str, tool_name: str, parameters: dict) -> tuple[bool, int]:
        current_count = await self.get_call_count(session_id, tool_name, parameters)
        is_loop = current_count >= self._max_identical_calls
        return is_loop, current_count

    async def record_call(self, session_id: str, tool_name: str, parameters: dict) -> tuple[bool, int]:
        if not session_id:
            return False, 0
        call_signature = self._generate_call_signature(tool_name, parameters)
        is_loop, current_count = await self.check_for_loop(session_id, tool_name, parameters)
        if is_loop:
            await self._record_loop_event(session_id, tool_name, call_signature, current_count)
            if self._cache:
                await self._increment_stats_redis(session_id)
            else:
                self._increment_stats_local(session_id)
            logger.warning(f"Loop detected for session {session_id}: Tool '{tool_name}' called {current_count} times")
            raise LoopDetectedError(
                tool_name=tool_name, call_signature=call_signature,
                call_count=current_count, max_calls=self._max_identical_calls, session_id=session_id
            )
        if self._cache:
            new_count = await self._increment_call_count_redis(session_id, call_signature)
        else:
            new_count = self._increment_call_count_local(session_id, call_signature)
        return False, new_count

    async def _record_loop_event(self, session_id: str, tool_name: str, call_signature: str, call_count: int) -> None:
        event = LoopDetectionEvent(
            timestamp=datetime.utcnow(), session_id=session_id, tool_name=tool_name,
            call_signature=call_signature, call_count=call_count, max_calls=self._max_identical_calls,
            correlation_id=get_correlation_id()
        )
        self._total_loops_detected += 1
        self._last_loop_event = event
        if tool_name not in self._loop_events_by_tool:
            self._loop_events_by_tool[tool_name] = 0
        self._loop_events_by_tool[tool_name] += 1
        self._loop_events_history.append(event)
        if len(self._loop_events_history) > 100:
            self._loop_events_history = self._loop_events_history[-100:]

    async def reset_session(self, session_id: str) -> bool:
        if not session_id:
            return False
        if self._cache and self._cache._connected and self._cache._client:
            try:
                pattern = f"{self.LOOP_KEY_PREFIX}{session_id}:*"
                keys = []
                async for key in self._cache._client.scan_iter(match=pattern):
                    keys.append(key)
                if keys:
                    await self._cache._client.delete(*keys)
                return True
            except Exception as e:
                logger.warning(f"Failed to reset loop detection in Redis: {e}")
        keys_to_delete = [k for k in self._local_history.keys() if k.startswith(f"{session_id}:")]
        for key in keys_to_delete:
            del self._local_history[key]
        return bool(keys_to_delete)

    async def _increment_stats_redis(self, session_id: str) -> int:
        if not self._cache or not self._cache._connected or not self._cache._client:
            return 0
        try:
            key = f"{self.STATS_KEY_PREFIX}{session_id}"
            new_count = await self._cache._client.incr(key)
            if new_count == 1:
                await self._cache._client.expire(key, timedelta(seconds=self._sliding_window_seconds))
            return new_count
        except Exception as e:
            logger.warning(f"Failed to increment loop stats in Redis: {e}")
            return 0

    def _increment_stats_local(self, session_id: str) -> int:
        key = f"stats:{session_id}"
        if key not in self._local_stats:
            self._local_stats[key] = 0
        self._local_stats[key] += 1
        return self._local_stats[key]

    async def get_loop_detection_stats(self, session_id: Optional[str] = None) -> dict:
        stats = {
            "enabled": True, "max_identical_calls": self._max_identical_calls,
            "sliding_window_seconds": self._sliding_window_seconds,
            "loops_detected_total": self._total_loops_detected, "active_sessions": 0,
            "loops_by_tool": dict(self._loop_events_by_tool),
            "last_loop_detected_at": None, "last_loop_tool_name": None, "last_loop_session_id": None,
        }
        if self._last_loop_event:
            stats["last_loop_detected_at"] = self._last_loop_event.timestamp.isoformat()
            stats["last_loop_tool_name"] = self._last_loop_event.tool_name
            stats["last_loop_session_id"] = self._last_loop_event.session_id
        if session_id:
            if self._cache and self._cache._connected and self._cache._client:
                try:
                    key = f"{self.STATS_KEY_PREFIX}{session_id}"
                    count = await self._cache._client.get(key)
                    stats["loops_detected_this_session"] = int(count) if count else 0
                except Exception:
                    stats["loops_detected_this_session"] = 0
            else:
                stats["loops_detected_this_session"] = self._local_stats.get(f"stats:{session_id}", 0)
        else:
            stats["active_sessions"] = len([k for k in self._local_stats.keys() if k.startswith("stats:")])
        return stats

    def get_recent_loop_events(self, limit: int = 10) -> list[dict]:
        events = self._loop_events_history[-limit:] if self._loop_events_history else []
        return [event.to_dict() for event in reversed(events)]

    def get_loop_frequency_by_tool(self) -> dict[str, int]:
        return dict(self._loop_events_by_tool)


_loop_detector: Optional[LoopDetector] = None


def get_loop_detector() -> Optional[LoopDetector]:
    return _loop_detector


def set_loop_detector(detector: LoopDetector) -> None:
    global _loop_detector
    _loop_detector = detector


async def check_and_record_call(tool_name: str, parameters: dict, session_id: Optional[str] = None) -> tuple[bool, int]:
    detector = get_loop_detector()
    if not detector:
        return False, 0
    if not session_id:
        session_id = get_correlation_id()
    if not session_id:
        return False, 0
    return await detector.record_call(session_id, tool_name, parameters)
