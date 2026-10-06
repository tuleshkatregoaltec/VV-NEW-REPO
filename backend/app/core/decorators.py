import inspect
import json
import logging
from functools import wraps
from typing import Callable

from fastapi.encoders import jsonable_encoder
from fastapi.params import Depends as DependsParam

from app.config import settings
from app.core.cache import RedisCache

logger = logging.getLogger(__name__)

cache = RedisCache(settings.REDIS_URL, settings.REDIS_PASSWORD)


def _is_dependency_parameter(parameter: inspect.Parameter) -> bool:
    return isinstance(parameter.default, DependsParam)


def _build_cache_key(prefix: str, signature: inspect.Signature, *args, **kwargs) -> str:
    ignored_names = {"request", "response"}
    bound_arguments = signature.bind_partial(*args, **kwargs)
    bound_arguments.apply_defaults()

    cacheable_arguments = {}
    for name, parameter in signature.parameters.items():
        if name in ignored_names or _is_dependency_parameter(parameter):
            continue

        value = bound_arguments.arguments.get(name, inspect.Parameter.empty)
        if value is inspect.Parameter.empty or value is None:
            continue

        cacheable_arguments[name] = jsonable_encoder(value)

    if not cacheable_arguments:
        return prefix

    encoded_arguments = json.dumps(
        cacheable_arguments,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{prefix}:{encoded_arguments}"


def cached_endpoint(prefix: str, expire: int = 600):
    """Decorator to cache endpoint responses in Redis with configurable expiration"""

    def decorator(func: Callable):
        signature = inspect.signature(func)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = _build_cache_key(prefix, signature, *args, **kwargs)

            cached_data = await cache.get(cache_key)
            if cached_data is not None:
                return cached_data

            result = await func(*args, **kwargs)

            try:
                await cache.set(cache_key, jsonable_encoder(result), expire=expire)
            except Exception as e:
                logger.error("Cache set error for %s: %s", cache_key, e)

            return result

        return wrapper

    return decorator
