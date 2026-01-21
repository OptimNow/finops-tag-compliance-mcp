"""Unit tests for Redis cache wrapper."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from mcp_server.clients.cache import CacheError, RedisCache


class TestRedisCacheInitialization:
    """Test RedisCache initialization and connection."""

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_create_with_valid_url(self, mock_redis):
        """Test creation with valid Redis URL."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_redis.return_value = mock_client

        cache = await RedisCache.create(redis_url="redis://localhost:6379/0")

        assert cache.redis_url == "redis://localhost:6379/0"
        assert cache.default_ttl == 3600
        assert await cache.is_connected()

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_create_with_custom_ttl(self, mock_redis):
        """Test creation with custom TTL."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_redis.return_value = mock_client

        cache = await RedisCache.create(redis_url="redis://localhost:6379/0", default_ttl=7200)

        assert cache.default_ttl == 7200

    def test_init_with_empty_url(self):
        """Test initialization with empty URL raises error."""
        with pytest.raises(CacheError, match="redis_url cannot be empty"):
            RedisCache(redis_url="")

    @patch("mcp_server.clients.cache.logger")
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_create_connection_failure(self, mock_redis, mock_logger):
        """Test creation when Redis connection fails."""
        mock_redis.side_effect = RedisConnectionError("Connection refused")

        cache = await RedisCache.create(redis_url="redis://localhost:6379/0")

        assert not await cache.is_connected()

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_is_connected_when_connected(self, mock_redis):
        """Test is_connected returns True when connected."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()

        assert await cache.is_connected()

    @patch("mcp_server.clients.cache.logger")
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_is_connected_when_disconnected(self, mock_redis, mock_logger):
        """Test is_connected returns False when disconnected."""
        mock_redis.side_effect = RedisConnectionError("Connection refused")

        cache = await RedisCache.create()

        assert not await cache.is_connected()


class TestRedisCacheGet:
    """Test RedisCache get operations."""

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_get_existing_key(self, mock_redis):
        """Test getting an existing key from cache."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        test_data = {"key": "value", "number": 42}
        mock_client.get = AsyncMock(return_value=json.dumps(test_data))
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()
        result = await cache.get("test_key")

        assert result == test_data
        mock_client.get.assert_called_once_with("test_key")

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_get_nonexistent_key(self, mock_redis):
        """Test getting a non-existent key returns None."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()
        result = await cache.get("nonexistent_key")

        assert result is None

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_get_with_empty_key(self, mock_redis):
        """Test getting with empty key raises error."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()

        with pytest.raises(CacheError, match="key cannot be empty"):
            await cache.get("")

    @patch("mcp_server.clients.cache.logger")
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_get_when_disconnected(self, mock_redis, mock_logger):
        """Test getting when cache is disconnected returns None."""
        mock_redis.side_effect = RedisConnectionError("Connection refused")

        cache = await RedisCache.create()
        result = await cache.get("test_key")

        assert result is None

    @patch("mcp_server.clients.cache.logger")
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_get_with_corrupted_json(self, mock_redis, mock_logger):
        """Test getting corrupted JSON data returns None and deletes key."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_client.get = AsyncMock(return_value="invalid json {")
        mock_client.delete = AsyncMock()
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()
        result = await cache.get("corrupted_key")

        assert result is None
        mock_client.delete.assert_called_once_with("corrupted_key")

    @patch("mcp_server.clients.cache.logger")
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_get_connection_error(self, mock_redis, mock_logger):
        """Test get handles connection errors gracefully."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RedisConnectionError("Connection lost"))
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()
        result = await cache.get("test_key")

        assert result is None
        assert not await cache.is_connected()


class TestRedisCacheSet:
    """Test RedisCache set operations."""

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_set_with_default_ttl(self, mock_redis):
        """Test setting a value with default TTL."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_client.setex = AsyncMock()
        mock_redis.return_value = mock_client

        cache = await RedisCache.create(default_ttl=3600)
        test_data = {"key": "value"}
        result = await cache.set("test_key", test_data)

        assert result is True
        mock_client.setex.assert_called_once()
        call_args = mock_client.setex.call_args
        assert call_args[0][0] == "test_key"
        assert json.loads(call_args[0][2]) == test_data

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_set_with_custom_ttl(self, mock_redis):
        """Test setting a value with custom TTL."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_client.setex = AsyncMock()
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()
        test_data = {"key": "value"}
        result = await cache.set("test_key", test_data, ttl=7200)

        assert result is True
        mock_client.setex.assert_called_once()

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_set_with_empty_key(self, mock_redis):
        """Test setting with empty key raises error."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()

        with pytest.raises(CacheError, match="key cannot be empty"):
            await cache.set("", {"data": "value"})

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_set_with_non_serializable_value(self, mock_redis):
        """Test setting non-serializable value raises error."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()

        # Create an object that can't be JSON serialized
        class NonSerializable:
            pass

        with pytest.raises(CacheError, match="Cannot serialize value"):
            await cache.set("test_key", NonSerializable())

    @patch("mcp_server.clients.cache.logger")
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_set_when_disconnected(self, mock_redis, mock_logger):
        """Test setting when cache is disconnected returns False."""
        mock_redis.side_effect = RedisConnectionError("Connection refused")

        cache = await RedisCache.create()
        result = await cache.set("test_key", {"data": "value"})

        assert result is False

    @patch("mcp_server.clients.cache.logger")
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_set_connection_error(self, mock_redis, mock_logger):
        """Test set handles connection errors gracefully."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_client.setex = AsyncMock(side_effect=RedisConnectionError("Connection lost"))
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()
        result = await cache.set("test_key", {"data": "value"})

        assert result is False
        assert not await cache.is_connected()


class TestRedisCacheDelete:
    """Test RedisCache delete operations."""

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_delete_existing_key(self, mock_redis):
        """Test deleting an existing key."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_client.delete = AsyncMock(return_value=1)
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()
        result = await cache.delete("test_key")

        assert result is True
        mock_client.delete.assert_called_once_with("test_key")

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_delete_nonexistent_key(self, mock_redis):
        """Test deleting a non-existent key returns False."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_client.delete = AsyncMock(return_value=0)
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()
        result = await cache.delete("nonexistent_key")

        assert result is False

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_delete_with_empty_key(self, mock_redis):
        """Test deleting with empty key raises error."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()

        with pytest.raises(CacheError, match="key cannot be empty"):
            await cache.delete("")

    @patch("mcp_server.clients.cache.logger")
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_delete_when_disconnected(self, mock_redis, mock_logger):
        """Test deleting when cache is disconnected returns False."""
        mock_redis.side_effect = RedisConnectionError("Connection refused")

        cache = await RedisCache.create()
        result = await cache.delete("test_key")

        assert result is False


class TestRedisCacheExists:
    """Test RedisCache exists operations."""

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_exists_for_existing_key(self, mock_redis):
        """Test exists returns True for existing key."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_client.exists = AsyncMock(return_value=1)
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()
        result = await cache.exists("test_key")

        assert result is True

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_exists_for_nonexistent_key(self, mock_redis):
        """Test exists returns False for non-existent key."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_client.exists = AsyncMock(return_value=0)
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()
        result = await cache.exists("nonexistent_key")

        assert result is False

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_exists_with_empty_key(self, mock_redis):
        """Test exists with empty key raises error."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()

        with pytest.raises(CacheError, match="key cannot be empty"):
            await cache.exists("")

    @patch("mcp_server.clients.cache.logger")
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_exists_when_disconnected(self, mock_redis, mock_logger):
        """Test exists when cache is disconnected returns False."""
        mock_redis.side_effect = RedisConnectionError("Connection refused")

        cache = await RedisCache.create()
        result = await cache.exists("test_key")

        assert result is False


class TestRedisCacheClear:
    """Test RedisCache clear operations."""

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_clear_cache(self, mock_redis):
        """Test clearing the cache."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_client.flushdb = AsyncMock()
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()
        result = await cache.clear()

        assert result is True
        mock_client.flushdb.assert_called_once()

    @patch("mcp_server.clients.cache.logger")
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_clear_when_disconnected(self, mock_redis, mock_logger):
        """Test clearing when cache is disconnected returns False."""
        mock_redis.side_effect = RedisConnectionError("Connection refused")

        cache = await RedisCache.create()
        result = await cache.clear()

        assert result is False


class TestRedisCacheClose:
    """Test RedisCache close operations."""

    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_close_connection(self, mock_redis):
        """Test closing the Redis connection."""
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_client.close = AsyncMock()
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()
        await cache.close()

        mock_client.close.assert_called_once()
        assert not await cache.is_connected()
