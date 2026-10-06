from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.core.cache import RedisCache


@pytest.fixture
def cache():
    """RedisCache with a mocked Redis client."""
    c = RedisCache.__new__(RedisCache)
    c.redis = AsyncMock()
    c.default_expire = 600
    return c


# ── get ───────────────────────────────────────────────────────────────────────


async def test_get_cache_hit_deserializes_json(cache):
    cache.redis.get = AsyncMock(return_value='{"count": 42, "name": "test"}')
    result = await cache.get("key")
    assert result == {"count": 42, "name": "test"}


async def test_get_cache_miss_returns_none(cache):
    cache.redis.get = AsyncMock(return_value=None)
    assert await cache.get("key") is None


async def test_get_string_round_trips(cache):
    cache.redis.get = AsyncMock(return_value='"plain string"')
    assert await cache.get("key") == "plain string"


async def test_get_returns_none_when_redis_unavailable(cache):
    cache.redis = None
    assert await cache.get("key") is None


async def test_get_returns_none_on_redis_error(cache):
    cache.redis.get = AsyncMock(side_effect=Exception("connection refused"))
    assert await cache.get("key") is None


# ── set ───────────────────────────────────────────────────────────────────────


async def test_set_serializes_dict(cache):
    cache.redis.set = AsyncMock()
    await cache.set("key", {"value": 123})
    call_args = cache.redis.set.call_args[0]
    assert '"value": 123' in call_args[1]


async def test_set_serializes_decimal(cache):
    cache.redis.set = AsyncMock()
    await cache.set("key", {"price": Decimal("123.45")})
    call_args = cache.redis.set.call_args[0]
    assert "123.45" in call_args[1]


async def test_set_serializes_date(cache):
    cache.redis.set = AsyncMock()
    await cache.set("key", {"date": date(2024, 1, 15)})
    call_args = cache.redis.set.call_args[0]
    assert "2024-01-15" in call_args[1]


async def test_set_serializes_datetime(cache):
    cache.redis.set = AsyncMock()
    await cache.set("key", {"ts": datetime(2024, 1, 15, 12, 0, 0)})
    call_args = cache.redis.set.call_args[0]
    assert "2024-01-15" in call_args[1]


async def test_set_uses_custom_expire(cache):
    cache.redis.set = AsyncMock()
    await cache.set("key", "value", expire=300)
    call_kwargs = cache.redis.set.call_args[1]
    assert call_kwargs["ex"] == 300


async def test_set_uses_default_expire_when_not_specified(cache):
    cache.redis.set = AsyncMock()
    await cache.set("key", "value")
    call_kwargs = cache.redis.set.call_args[1]
    assert call_kwargs["ex"] == 600


async def test_set_json_encodes_strings(cache):
    cache.redis.set = AsyncMock()
    await cache.set("key", "value")
    call_args = cache.redis.set.call_args[0]
    assert call_args[1] == '"value"'


async def test_set_rejects_non_positive_expire(cache):
    cache.redis.set = AsyncMock()
    await cache.set("key", "value", expire=0)
    cache.redis.set.assert_not_called()


async def test_set_is_silent_when_redis_unavailable(cache):
    cache.redis = None
    # Should not raise
    await cache.set("key", {"anything": True})


async def test_set_is_silent_on_redis_error(cache):
    cache.redis.set = AsyncMock(side_effect=Exception("timeout"))
    await cache.set("key", {"anything": True})  # should not raise


# ── delete ────────────────────────────────────────────────────────────────────


async def test_delete_calls_redis_delete(cache):
    cache.redis.delete = AsyncMock()
    await cache.delete("key")
    cache.redis.delete.assert_called_once_with("key")


async def test_delete_is_silent_when_redis_unavailable(cache):
    cache.redis = None
    await cache.delete("key")  # should not raise


# ── clear ─────────────────────────────────────────────────────────────────────


async def test_clear_deletes_matching_keys(cache):
    cache.redis.delete = AsyncMock()
    cache.redis.scan_iter = lambda **kwargs: _async_iter(["key1", "key2"])
    await cache.clear("key*")
    cache.redis.delete.assert_called_once_with("key1", "key2")


async def test_clear_does_nothing_when_no_keys_match(cache):
    cache.redis.delete = AsyncMock()
    cache.redis.scan_iter = lambda **kwargs: _async_iter([])
    await cache.clear("nonexistent*")
    cache.redis.delete.assert_not_called()


async def test_ping_returns_true_on_success(cache):
    cache.redis.ping = AsyncMock(return_value=True)
    assert await cache.ping() is True


async def test_ping_returns_false_on_error(cache):
    cache.redis.ping = AsyncMock(side_effect=Exception("timeout"))
    assert await cache.ping() is False


async def _async_iter(values):
    for value in values:
        yield value
