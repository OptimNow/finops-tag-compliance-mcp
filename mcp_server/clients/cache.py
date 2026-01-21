# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Redis cache wrapper with TTL and error handling."""

import json
import logging
from typing import Any, Optional
from datetime import timedelta

import redis.asyncio as redis
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError

logger = logging.getLogger(__name__)


class CacheError(Exception):
    """Raised when cache operations fail."""

    pass


class RedisCache:
    """
    Redis cache wrapper with TTL support and graceful error handling.

    Provides a simple interface for caching data with automatic serialization
    and deserialization. Falls back gracefully when Redis is unavailable.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0", default_ttl: int = 3600):
        """
        Initialize Redis cache client.

        Args:
            redis_url: Redis connection URL (e.g., "redis://localhost:6379/0")
            default_ttl: Default time-to-live in seconds for cached items

        Raises:
            CacheError: If Redis URL is invalid
        """
        if not redis_url:
            raise CacheError("redis_url cannot be empty")

        self.redis_url = redis_url
        self.default_ttl = default_ttl
        self._client: Optional[redis.Redis] = None
        self._connected = False

    @classmethod
    async def create(
        cls, redis_url: str = "redis://localhost:6379/0", default_ttl: int = 3600
    ) -> "RedisCache":
        """
        Create and initialize a Redis cache instance.

        Args:
            redis_url: Redis connection URL (e.g., "redis://localhost:6379/0")
            default_ttl: Default time-to-live in seconds for cached items

        Returns:
            Initialized RedisCache instance

        Raises:
            CacheError: If Redis URL is invalid
        """
        cache = cls(redis_url, default_ttl)
        await cache._connect()
        return cache

    async def _connect(self) -> None:
        """
        Establish connection to Redis.

        Logs connection status but doesn't raise - allows graceful degradation.
        """
        try:
            self._client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
            )
            # Test the connection
            await self._client.ping()
            self._connected = True
            logger.info(f"Connected to Redis at {self.redis_url}")
        except (RedisConnectionError, RedisError) as e:
            self._connected = False
            logger.warning(f"Failed to connect to Redis: {str(e)}. Cache will be unavailable.")
        except Exception as e:
            self._connected = False
            logger.error(f"Unexpected error connecting to Redis: {str(e)}")

    async def is_connected(self) -> bool:
        """
        Check if Redis connection is active.

        Returns:
            True if connected, False otherwise
        """
        if not self._connected or self._client is None:
            return False

        try:
            await self._client.ping()
            return True
        except (RedisConnectionError, RedisError):
            self._connected = False
            return False

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from cache.

        Args:
            key: Cache key to retrieve

        Returns:
            Deserialized value if found, None if not found or cache unavailable

        Raises:
            CacheError: If key is empty
        """
        if not key:
            raise CacheError("key cannot be empty")

        if not self._connected or self._client is None:
            logger.debug(f"Cache miss (unavailable): {key}")
            return None

        try:
            value = await self._client.get(key)

            if value is None:
                logger.debug(f"Cache miss: {key}")
                return None

            # Deserialize JSON
            try:
                deserialized = json.loads(value)
                logger.debug(f"Cache hit: {key}")
                return deserialized
            except json.JSONDecodeError as e:
                logger.error(f"Failed to deserialize cache value for {key}: {str(e)}")
                # Delete corrupted cache entry
                try:
                    await self._client.delete(key)
                except RedisError:
                    pass
                return None

        except (RedisConnectionError, RedisError) as e:
            self._connected = False
            logger.warning(f"Cache get failed for {key}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting cache value for {key}: {str(e)}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Store a value in cache with optional TTL.

        Args:
            key: Cache key to store under
            value: Value to cache (will be JSON serialized)
            ttl: Time-to-live in seconds (uses default_ttl if not specified)

        Returns:
            True if successfully cached, False if cache unavailable

        Raises:
            CacheError: If key is empty or value cannot be serialized
        """
        if not key:
            raise CacheError("key cannot be empty")

        if not self._connected or self._client is None:
            logger.debug(f"Cache set skipped (unavailable): {key}")
            return False

        # Use default TTL if not specified
        if ttl is None:
            ttl = self.default_ttl

        try:
            # Serialize to JSON
            try:
                serialized = json.dumps(value)
            except (TypeError, ValueError) as e:
                raise CacheError(f"Cannot serialize value for key {key}: {str(e)}")

            # Set with TTL
            await self._client.setex(key, timedelta(seconds=ttl), serialized)
            logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
            return True

        except (RedisConnectionError, RedisError) as e:
            self._connected = False
            logger.warning(f"Cache set failed for {key}: {str(e)}")
            return False
        except CacheError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error setting cache value for {key}: {str(e)}")
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete a value from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False if key didn't exist or cache unavailable

        Raises:
            CacheError: If key is empty
        """
        if not key:
            raise CacheError("key cannot be empty")

        if not self._connected or self._client is None:
            logger.debug(f"Cache delete skipped (unavailable): {key}")
            return False

        try:
            result = await self._client.delete(key)
            if result > 0:
                logger.debug(f"Cache deleted: {key}")
                return True
            else:
                logger.debug(f"Cache delete: key not found: {key}")
                return False

        except (RedisConnectionError, RedisError) as e:
            self._connected = False
            logger.warning(f"Cache delete failed for {key}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting cache value for {key}: {str(e)}")
            return False

    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False if not or cache unavailable

        Raises:
            CacheError: If key is empty
        """
        if not key:
            raise CacheError("key cannot be empty")

        if not self._connected or self._client is None:
            return False

        try:
            result = await self._client.exists(key)
            return result > 0

        except (RedisConnectionError, RedisError) as e:
            self._connected = False
            logger.warning(f"Cache exists check failed for {key}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking cache key {key}: {str(e)}")
            return False

    async def clear(self) -> bool:
        """
        Clear all keys from the current Redis database.

        Returns:
            True if successful, False if cache unavailable
        """
        if not self._connected or self._client is None:
            logger.debug("Cache clear skipped (unavailable)")
            return False

        try:
            await self._client.flushdb()
            logger.info("Cache cleared")
            return True

        except (RedisConnectionError, RedisError) as e:
            self._connected = False
            logger.warning(f"Cache clear failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error clearing cache: {str(e)}")
            return False

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            try:
                await self._client.close()
                self._connected = False
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {str(e)}")
