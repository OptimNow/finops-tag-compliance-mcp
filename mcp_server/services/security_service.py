"""Security monitoring service for the MCP server.

This module provides security event logging and monitoring capabilities
to detect and respond to potential security threats like unauthorized
tool access attempts, injection attacks, and suspicious patterns.

Security events are logged to a separate security log stream for
dedicated monitoring and alerting.

Requirements: 16.4
"""

import logging
import json
import os
from datetime import datetime
from typing import Optional
from collections import defaultdict
import asyncio

from ..clients.cache import RedisCache

# Standard application logger
logger = logging.getLogger(__name__)

# Dedicated security logger for security events
# This logger can be configured to send to a separate log stream
security_logger = logging.getLogger("security")


def configure_security_logging(
    log_group: Optional[str] = None,
    log_stream: Optional[str] = None,
    region: str = "us-east-1",
) -> None:
    """
    Configure dedicated security logging to a separate CloudWatch log stream.
    
    This sets up a separate logger for security events that can be monitored
    independently from application logs.
    
    Args:
        log_group: CloudWatch log group name (default: /finops/mcp-server)
        log_stream: CloudWatch log stream name (default: security)
        region: AWS region for CloudWatch
    
    Requirements: 16.4
    """
    # Check if CloudWatch logging is enabled
    cloudwatch_enabled = os.getenv("CLOUDWATCH_ENABLED", "false").lower() == "true"
    
    # Get configuration from environment or use defaults
    log_group = os.getenv("CLOUDWATCH_LOG_GROUP", log_group or "/finops/mcp-server")
    log_stream = os.getenv("SECURITY_LOG_STREAM", log_stream or "security")
    region = os.getenv("AWS_REGION", region)
    
    # Configure the security logger
    security_logger.setLevel(logging.WARNING)
    
    # Add console handler for security events
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    formatter = logging.Formatter(
        "%(asctime)s - SECURITY - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(formatter)
    
    # Avoid duplicate handlers
    if not security_logger.handlers:
        security_logger.addHandler(console_handler)
    
    # Add CloudWatch handler if enabled
    if cloudwatch_enabled:
        try:
            from ..utils.cloudwatch_logger import CloudWatchHandler, CorrelationIDFilter
            
            cloudwatch_handler = CloudWatchHandler(
                log_group=log_group,
                log_stream=log_stream,
                region=region,
            )
            cloudwatch_handler.setLevel(logging.WARNING)
            cloudwatch_handler.setFormatter(formatter)
            
            # Add correlation ID filter
            correlation_filter = CorrelationIDFilter()
            cloudwatch_handler.addFilter(correlation_filter)
            
            security_logger.addHandler(cloudwatch_handler)
            logger.info(
                f"Security CloudWatch logging configured: group={log_group}, stream={log_stream}"
            )
        except Exception as e:
            logger.warning(f"Failed to configure security CloudWatch logging: {e}")


class SecurityEvent:
    """Represents a security event."""
    
    def __init__(
        self,
        event_type: str,
        severity: str,
        message: str,
        details: Optional[dict] = None,
        session_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ):
        """
        Initialize a security event.
        
        Args:
            event_type: Type of security event (e.g., "unknown_tool", "injection_attempt")
            severity: Severity level ("low", "medium", "high", "critical")
            message: Human-readable description of the event
            details: Additional event details
            session_id: Session ID if available
            tool_name: Tool name if applicable
            timestamp: Event timestamp (defaults to now)
        """
        self.event_type = event_type
        self.severity = severity
        self.message = message
        self.details = details or {}
        self.session_id = session_id
        self.tool_name = tool_name
        self.timestamp = timestamp or datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert event to dictionary for logging."""
        return {
            "event_type": self.event_type,
            "severity": self.severity,
            "message": self.message,
            "details": self.details,
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "timestamp": self.timestamp.isoformat(),
        }


class SecurityService:
    """
    Security monitoring service for the MCP server.
    
    Provides centralized security event logging, rate limiting for
    suspicious activity, and security metrics collection.
    
    Requirements: 16.4
    """
    
    def __init__(
        self,
        redis_cache: Optional[RedisCache] = None,
        max_unknown_tool_attempts: int = 10,
        window_seconds: int = 60,
    ):
        """
        Initialize the security service.
        
        Args:
            redis_cache: Optional Redis cache for distributed rate limiting
            max_unknown_tool_attempts: Maximum unknown tool attempts per session before blocking
            window_seconds: Time window for rate limiting (seconds)
        """
        self.redis_cache = redis_cache
        self.max_unknown_tool_attempts = max_unknown_tool_attempts
        self.window_seconds = window_seconds
        
        # Track unknown tool attempts per session (in-memory fallback)
        self._unknown_tool_attempts: dict[str, list[datetime]] = defaultdict(list)
        
        # Security event counters
        self._event_counts: dict[str, int] = defaultdict(int)
        self._events_by_severity: dict[str, int] = defaultdict(int)
        
        # Recent security events (keep last 100)
        self._recent_events: list[SecurityEvent] = []
        self._max_recent_events = 100
        
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        
        # Redis keys
        self._redis_prefix = "security:"
        self._redis_attempts_key = f"{self._redis_prefix}attempts:"
        self._redis_events_key = f"{self._redis_prefix}events"
        self._redis_metrics_key = f"{self._redis_prefix}metrics"
    
    async def log_security_event(
        self,
        event_type: str,
        severity: str,
        message: str,
        details: Optional[dict] = None,
        session_id: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> SecurityEvent:
        """
        Log a security event.
        
        Args:
            event_type: Type of security event
            severity: Severity level ("low", "medium", "high", "critical")
            message: Human-readable description
            details: Additional event details
            session_id: Session ID if available
            tool_name: Tool name if applicable
        
        Returns:
            The created SecurityEvent
        
        Requirements: 16.4
        """
        event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            message=message,
            details=details,
            session_id=session_id,
            tool_name=tool_name,
        )
        
        async with self._lock:
            # Update counters
            self._event_counts[event_type] += 1
            self._events_by_severity[severity] += 1
            
            # Add to recent events
            self._recent_events.append(event)
            if len(self._recent_events) > self._max_recent_events:
                self._recent_events.pop(0)
        
        # Store in Redis if available
        if self.redis_cache:
            try:
                # Store event in Redis list (keep last 100)
                event_json = json.dumps(event.to_dict())
                await self.redis_cache.lpush(self._redis_events_key, event_json)
                await self.redis_cache.ltrim(self._redis_events_key, 0, self._max_recent_events - 1)
                
                # Update metrics in Redis
                await self.redis_cache.hincrby(f"{self._redis_metrics_key}:types", event_type, 1)
                await self.redis_cache.hincrby(f"{self._redis_metrics_key}:severity", severity, 1)
            except Exception as e:
                logger.warning(f"Failed to store security event in Redis: {e}")
        
        # Log to dedicated security log stream
        # This goes to a separate CloudWatch log stream for security monitoring
        log_level = logging.CRITICAL if severity == "critical" else logging.WARNING
        security_logger.log(
            log_level,
            f"SECURITY EVENT [{severity.upper()}]: {event_type} - {message}",
            extra={
                "security_event": event.to_dict(),
                "event_type": event_type,
                "severity": severity,
                "session_id": session_id,
                "tool_name": tool_name,
            }
        )
        
        # Also log to application logger for general visibility
        logger.warning(
            f"Security event logged: {event_type} ({severity})",
            extra={
                "event_type": event_type,
                "severity": severity,
                "session_id": session_id,
            }
        )
        
        return event
    
    async def check_unknown_tool_rate_limit(
        self,
        session_id: str,
        tool_name: str,
    ) -> tuple[bool, int, int]:
        """
        Check if a session has exceeded the rate limit for unknown tool attempts.
        
        Args:
            session_id: Session ID to check
            tool_name: Name of the unknown tool being attempted
        
        Returns:
            Tuple of (is_blocked, current_count, max_attempts)
            - is_blocked: True if the session should be blocked
            - current_count: Current number of attempts in the window
            - max_attempts: Maximum allowed attempts
        
        Requirements: 16.4
        """
        now = datetime.utcnow()
        cutoff = datetime.fromtimestamp(now.timestamp() - self.window_seconds)
        
        # Try Redis first for distributed rate limiting
        if self.redis_cache:
            try:
                key = f"{self._redis_attempts_key}{session_id}"
                
                # Add current timestamp to sorted set
                await self.redis_cache.zadd(key, {str(now.timestamp()): now.timestamp()})
                
                # Remove old entries outside the window
                await self.redis_cache.zremrangebyscore(key, 0, cutoff.timestamp())
                
                # Count attempts in window
                current_count = await self.redis_cache.zcard(key)
                
                # Set expiry on the key
                await self.redis_cache.expire(key, self.window_seconds)
                
                is_blocked = current_count > self.max_unknown_tool_attempts
                
                if is_blocked:
                    # Log rate limit exceeded
                    await self.log_security_event(
                        event_type="rate_limit_exceeded",
                        severity="high",
                        message=f"Session exceeded unknown tool attempt limit: {current_count}/{self.max_unknown_tool_attempts}",
                        details={
                            "tool_name": tool_name,
                            "attempts_in_window": current_count,
                            "window_seconds": self.window_seconds,
                        },
                        session_id=session_id,
                        tool_name=tool_name,
                    )
                
                return is_blocked, current_count, self.max_unknown_tool_attempts
            
            except Exception as e:
                logger.warning(f"Redis rate limit check failed, falling back to in-memory: {e}")
        
        # Fallback to in-memory tracking
        async with self._lock:
            # Get attempts for this session
            attempts = self._unknown_tool_attempts[session_id]
            
            # Remove old attempts outside the window
            attempts = [t for t in attempts if t > cutoff]
            self._unknown_tool_attempts[session_id] = attempts
            
            # Add current attempt
            attempts.append(now)
            
            current_count = len(attempts)
            is_blocked = current_count > self.max_unknown_tool_attempts
            
            if is_blocked:
                # Log rate limit exceeded
                await self.log_security_event(
                    event_type="rate_limit_exceeded",
                    severity="high",
                    message=f"Session exceeded unknown tool attempt limit: {current_count}/{self.max_unknown_tool_attempts}",
                    details={
                        "tool_name": tool_name,
                        "attempts_in_window": current_count,
                        "window_seconds": self.window_seconds,
                    },
                    session_id=session_id,
                    tool_name=tool_name,
                )
            
            return is_blocked, current_count, self.max_unknown_tool_attempts
    
    async def log_unknown_tool_attempt(
        self,
        tool_name: str,
        session_id: Optional[str] = None,
        parameters: Optional[dict] = None,
    ) -> SecurityEvent:
        """
        Log an attempt to invoke an unknown tool.
        
        Args:
            tool_name: Name of the unknown tool
            session_id: Session ID if available
            parameters: Tool parameters (sanitized)
        
        Returns:
            The created SecurityEvent
        
        Requirements: 16.4
        """
        return await self.log_security_event(
            event_type="unknown_tool_attempt",
            severity="medium",
            message=f"Attempt to invoke unknown tool: {tool_name}",
            details={
                "tool_name": tool_name,
                "has_parameters": parameters is not None,
                "parameter_count": len(parameters) if parameters else 0,
            },
            session_id=session_id,
            tool_name=tool_name,
        )
    
    async def log_injection_attempt(
        self,
        tool_name: str,
        violation_type: str,
        field_name: str,
        session_id: Optional[str] = None,
    ) -> SecurityEvent:
        """
        Log a detected injection attempt.
        
        Args:
            tool_name: Name of the tool being invoked
            violation_type: Type of security violation
            field_name: Field where injection was detected
            session_id: Session ID if available
        
        Returns:
            The created SecurityEvent
        
        Requirements: 16.4
        """
        return await self.log_security_event(
            event_type="injection_attempt",
            severity="high",
            message=f"Injection attempt detected in tool '{tool_name}', field '{field_name}'",
            details={
                "tool_name": tool_name,
                "violation_type": violation_type,
                "field_name": field_name,
            },
            session_id=session_id,
            tool_name=tool_name,
        )
    
    async def log_validation_bypass_attempt(
        self,
        tool_name: str,
        violation_type: str,
        session_id: Optional[str] = None,
    ) -> SecurityEvent:
        """
        Log an attempt to bypass validation.
        
        Args:
            tool_name: Name of the tool being invoked
            violation_type: Type of security violation
            session_id: Session ID if available
        
        Returns:
            The created SecurityEvent
        
        Requirements: 16.4
        """
        return await self.log_security_event(
            event_type="validation_bypass_attempt",
            severity="high",
            message=f"Validation bypass attempt detected for tool '{tool_name}'",
            details={
                "tool_name": tool_name,
                "violation_type": violation_type,
            },
            session_id=session_id,
            tool_name=tool_name,
        )
    
    async def get_security_metrics(self) -> dict:
        """
        Get security metrics for monitoring.
        
        Returns:
            Dictionary containing security metrics
        
        Requirements: 16.4
        """
        return {
            "total_events": sum(self._event_counts.values()),
            "events_by_type": dict(self._event_counts),
            "events_by_severity": dict(self._events_by_severity),
            "recent_events_count": len(self._recent_events),
            "rate_limit_config": {
                "max_unknown_tool_attempts": self.max_unknown_tool_attempts,
                "window_seconds": self.window_seconds,
            },
            "redis_enabled": self.redis_cache is not None,
        }
    
    async def get_recent_events(
        self,
        limit: int = 20,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Get recent security events with optional filtering.
        
        Args:
            limit: Maximum number of events to return
            event_type: Optional filter by event type
            session_id: Optional filter by session ID
        
        Returns:
            List of recent security events as dictionaries
        
        Requirements: 16.4
        """
        events = self._recent_events.copy()
        
        # Apply filters
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if session_id:
            events = [e for e in events if e.session_id == session_id]
        
        # Return most recent events up to limit
        return [event.to_dict() for event in events[-limit:]]
    
    async def get_recent_events_from_redis(self, limit: int = 20) -> list[dict]:
        """
        Get recent security events from Redis.
        
        Args:
            limit: Maximum number of events to return
        
        Returns:
            List of recent security events as dictionaries
        
        Requirements: 16.4
        """
        if not self.redis_cache:
            return self.get_recent_events(limit)
        
        try:
            # Get events from Redis list
            events_json = await self.redis_cache.lrange(self._redis_events_key, 0, limit - 1)
            return [json.loads(event) for event in events_json]
        except Exception as e:
            logger.warning(f"Failed to get events from Redis: {e}")
            return self.get_recent_events(limit)
    
    async def reset_session(self, session_id: str) -> None:
        """
        Reset rate limiting for a session.
        
        Args:
            session_id: Session ID to reset
        """
        async with self._lock:
            if session_id in self._unknown_tool_attempts:
                del self._unknown_tool_attempts[session_id]


# Global security service instance
_security_service: Optional[SecurityService] = None


def get_security_service() -> Optional[SecurityService]:
    """Get the global security service instance."""
    return _security_service


def set_security_service(service: SecurityService) -> None:
    """Set the global security service instance."""
    global _security_service
    _security_service = service
