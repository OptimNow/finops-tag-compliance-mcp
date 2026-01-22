"""Property-based tests for Redis cache wrapper."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from mcp_server.clients.cache import RedisCache


# Strategies for generating test data
@st.composite
def cache_keys(draw):
    """Generate valid cache keys."""
    return draw(st.text(min_size=1, max_size=100))


@st.composite
def cache_values(draw):
    """Generate JSON-serializable cache values."""
    return draw(
        st.one_of(
            st.dictionaries(st.text(), st.integers()),
            st.lists(st.integers()),
            st.text(),
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.booleans(),
            st.none(),
        )
    )


@st.composite
def ttl_values(draw):
    """Generate valid TTL values in seconds."""
    return draw(st.integers(min_value=1, max_value=86400))


class TestCacheBehaviorProperties:
    """Property-based tests for cache behavior."""

    @given(key=cache_keys(), value=cache_values(), ttl=ttl_values())
    @settings(max_examples=100)
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_property_11_cache_set_get_roundtrip(self, mock_redis, key, value, ttl):
        """
        Feature: phase-1-aws-mvp, Property 11: Cache Behavior
        Validates: Requirements 11.1, 11.3

        For any valid cache key, value, and TTL, setting a value and then getting it
        should return the same value (round-trip property).
        """
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()

        # Store the value in a dict to simulate Redis behavior
        stored_data = {}

        async def mock_setex(key, ttl_delta, value):
            stored_data[key] = value

        async def mock_get(key):
            return stored_data.get(key)

        mock_client.setex = AsyncMock(side_effect=mock_setex)
        mock_client.get = AsyncMock(side_effect=mock_get)
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()

        # Set the value
        set_result = await cache.set(key, value, ttl=ttl)
        assert set_result is True

        # Get the value back
        retrieved_value = await cache.get(key)

        # The retrieved value should equal the original value
        assert retrieved_value == value

    @given(key=cache_keys(), value=cache_values())
    @settings(max_examples=100)
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_property_11_cache_ttl_expiration(self, mock_redis, key, value):
        """
        Feature: phase-1-aws-mvp, Property 11: Cache Behavior
        Validates: Requirements 11.1, 11.3

        For any cached value, if the TTL has expired, the cache should not return
        the value (simulated by checking that expired entries are not retrieved).
        """
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()

        # Simulate expired cache by returning None
        mock_client.setex = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()

        # Set the value with a short TTL
        set_result = await cache.set(key, value, ttl=1)
        assert set_result is True

        # After expiration, get should return None
        retrieved_value = await cache.get(key)
        assert retrieved_value is None

    @given(key=cache_keys(), value=cache_values())
    @settings(max_examples=100)
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_property_11_cache_delete_removes_value(self, mock_redis, key, value):
        """
        Feature: phase-1-aws-mvp, Property 11: Cache Behavior
        Validates: Requirements 11.1, 11.3

        For any cached value, after deletion, the cache should not return the value.
        """
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()

        stored_data = {}

        async def mock_setex(key, ttl_delta, value):
            stored_data[key] = value

        async def mock_get(key):
            return stored_data.get(key)

        async def mock_delete(key):
            if key in stored_data:
                del stored_data[key]
                return 1
            return 0

        mock_client.setex = AsyncMock(side_effect=mock_setex)
        mock_client.get = AsyncMock(side_effect=mock_get)
        mock_client.delete = AsyncMock(side_effect=mock_delete)
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()

        # Set the value
        await cache.set(key, value)

        # Verify it's there
        retrieved = await cache.get(key)
        assert retrieved == value

        # Delete it
        delete_result = await cache.delete(key)
        assert delete_result is True

        # Verify it's gone
        retrieved_after_delete = await cache.get(key)
        assert retrieved_after_delete is None

    @given(key=cache_keys(), value=cache_values())
    @settings(max_examples=100)
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_property_11_cache_exists_consistency(self, mock_redis, key, value):
        """
        Feature: phase-1-aws-mvp, Property 11: Cache Behavior
        Validates: Requirements 11.1, 11.3

        For any cached value, exists() should return True if the value is in cache,
        and False if it's not.
        """
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()

        stored_data = {}

        async def mock_setex(key, ttl_delta, value):
            stored_data[key] = value

        async def mock_exists(key):
            return 1 if key in stored_data else 0

        async def mock_delete(key):
            if key in stored_data:
                del stored_data[key]
                return 1
            return 0

        mock_client.setex = AsyncMock(side_effect=mock_setex)
        mock_client.exists = AsyncMock(side_effect=mock_exists)
        mock_client.delete = AsyncMock(side_effect=mock_delete)
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()

        # Before setting, key should not exist
        exists_before = await cache.exists(key)
        assert exists_before is False

        # After setting, key should exist
        await cache.set(key, value)
        exists_after_set = await cache.exists(key)
        assert exists_after_set is True

        # After deleting, key should not exist
        await cache.delete(key)
        exists_after_delete = await cache.exists(key)
        assert exists_after_delete is False

    @given(key=cache_keys(), value1=cache_values(), value2=cache_values())
    @settings(max_examples=100)
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_property_11_cache_overwrite_behavior(self, mock_redis, key, value1, value2):
        """
        Feature: phase-1-aws-mvp, Property 11: Cache Behavior
        Validates: Requirements 11.1, 11.3

        For any cache key, setting a new value should overwrite the previous value.
        """
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()

        stored_data = {}

        async def mock_setex(key, ttl_delta, value):
            stored_data[key] = value

        async def mock_get(key):
            return stored_data.get(key)

        mock_client.setex = AsyncMock(side_effect=mock_setex)
        mock_client.get = AsyncMock(side_effect=mock_get)
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()

        # Set first value
        await cache.set(key, value1)
        retrieved1 = await cache.get(key)
        assert retrieved1 == value1

        # Set second value (overwrite)
        await cache.set(key, value2)
        retrieved2 = await cache.get(key)

        # Should get the second value
        assert retrieved2 == value2

    @given(keys=st.lists(cache_keys(), min_size=1, max_size=10, unique=True), value=cache_values())
    @settings(max_examples=100)
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_property_11_cache_multiple_keys_independence(self, mock_redis, keys, value):
        """
        Feature: phase-1-aws-mvp, Property 11: Cache Behavior
        Validates: Requirements 11.1, 11.3

        For any set of cache keys, operations on one key should not affect other keys.
        """
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()

        stored_data = {}

        async def mock_setex(key, ttl_delta, value):
            stored_data[key] = value

        async def mock_get(key):
            return stored_data.get(key)

        async def mock_delete(key):
            if key in stored_data:
                del stored_data[key]
                return 1
            return 0

        mock_client.setex = AsyncMock(side_effect=mock_setex)
        mock_client.get = AsyncMock(side_effect=mock_get)
        mock_client.delete = AsyncMock(side_effect=mock_delete)
        mock_redis.return_value = mock_client

        cache = await RedisCache.create()

        # Set all keys
        for key in keys:
            await cache.set(key, value)

        # Delete the first key
        if keys:
            await cache.delete(keys[0])

        # First key should be gone
        if keys:
            assert await cache.get(keys[0]) is None

        # Other keys should still be there
        for key in keys[1:]:
            assert await cache.get(key) == value

    @given(key=cache_keys(), value=cache_values())
    @settings(max_examples=100, deadline=timedelta(seconds=5))
    @patch("mcp_server.clients.cache.logger")
    @patch("mcp_server.clients.cache.redis.from_url")
    async def test_property_11_cache_graceful_degradation_on_disconnect(
        self, mock_redis, mock_logger, key, value
    ):
        """
        Feature: phase-1-aws-mvp, Property 11: Cache Behavior
        Validates: Requirements 11.1, 11.3

        When cache is disconnected, operations should return False/None gracefully
        without raising exceptions.
        """
        from redis.exceptions import ConnectionError as RedisConnectionError

        mock_redis.side_effect = RedisConnectionError("Connection refused")

        cache = await RedisCache.create()

        # All operations should return False/None without raising
        set_result = await cache.set(key, value)
        assert set_result is False

        get_result = await cache.get(key)
        assert get_result is None

        delete_result = await cache.delete(key)
        assert delete_result is False

        exists_result = await cache.exists(key)
        assert exists_result is False

        clear_result = await cache.clear()
        assert clear_result is False
