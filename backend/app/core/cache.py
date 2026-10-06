import datetime
import json
import logging
from decimal import Decimal
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger("RedisCache")


class RedisCache:
    """Redis-backed cache with JSON serialization and automatic expiration"""

    def __init__(self, redis_url: str, redis_password: str, default_expire: int = 600):
        self.redis_url = redis_url
        self.redis_password = redis_password
        self.default_expire = default_expire
        self.redis = None

        try:
            self.redis = redis.from_url(
                self.redis_url,
                password=self.redis_password,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("Redis client configured for %s", self.redis_url)
        except Exception as e:
            logger.error("Failed to configure Redis client at %s: %s", self.redis_url, str(e))

    @staticmethod
    def _json_default(obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

    def _resolve_expire(self, expire: int | None) -> int:
        resolved = self.default_expire if expire is None else expire
        if resolved <= 0:
            raise ValueError("expire must be a positive integer")
        return resolved

    async def get(self, key: str) -> Any | None:
        """Get a cached JSON value by key, or None if not found."""
        if not self.redis:
            return None

        try:
            value = await self.redis.get(key)
            if value is None:
                logger.debug("Cache miss for key: %s", key)
                return None

            logger.debug("Cache hit for key: %s", key)
            return json.loads(value)
        except Exception as e:
            logger.error("Failed to get cache for key %s: %s", key, str(e))
            return None

    async def set(self, key: str, value: Any, expire: int | None = None):
        """Set a JSON-serializable value in cache."""
        if not self.redis:
            return

        try:
            payload = json.dumps(value, default=self._json_default, allow_nan=False)
            await self.redis.set(key, payload, ex=self._resolve_expire(expire))
            logger.debug("Cache set for key: %s", key)
        except Exception as e:
            logger.error("Failed to set cache for key %s: %s", key, str(e))

    async def delete(self, key: str) -> None:
        """Delete a cached key."""
        if not self.redis:
            return

        try:
            await self.redis.delete(key)
            logger.debug("Cache deleted for key: %s", key)
        except Exception as e:
            logger.error("Failed to delete cache for key %s: %s", key, str(e))

    async def clear(self, pattern: str = "*") -> int:
        """Clear keys matching a pattern using SCAN to avoid blocking Redis."""
        if not self.redis:
            return 0

        try:
            deleted = 0
            batch: list[str] = []

            async for key in self.redis.scan_iter(match=pattern, count=100):
                batch.append(key)
                if len(batch) >= 100:
                    await self.redis.delete(*batch)
                    deleted += len(batch)
                    batch.clear()

            if batch:
                await self.redis.delete(*batch)
                deleted += len(batch)

            if deleted:
                logger.info("Cache cleared for pattern: %s (%d keys removed)", pattern, deleted)
            else:
                logger.debug("Cache clear called for pattern %s but no keys found", pattern)

            return deleted
        except Exception as e:
            logger.error("Failed to clear cache for pattern %s: %s", pattern, str(e))
            return 0

    async def clear_prefix(self, prefix: str) -> int:
        """Clear all keys with the given prefix."""
        return await self.clear(f"{prefix}*")

    async def ping(self) -> bool:
        """Check whether Redis is reachable."""
        if not self.redis:
            return False

        try:
            return bool(await self.redis.ping())
        except Exception as e:
            logger.error("Redis ping failed: %s", str(e))
            return False
