import os
import diskcache
import functools
import asyncio
from typing import Any, Optional
from datetime import timedelta

_cache = diskcache.Cache(os.getenv("DISK_CACHE_DIR", "./cache_data"))
_DEFAULT_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))


def get_cached(key: str) -> Optional[Any]:
    return _cache.get(key)


def set_cached(key: str, value: Any, ttl: int = _DEFAULT_TTL):
    _cache.set(key, value, expire=ttl)


def delete_cached(key: str):
    _cache.delete(key)


def cache(ttl: int = _DEFAULT_TTL, key_prefix: str = ""):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = f"{key_prefix or func.__name__}:{args}:{sorted(kwargs.items())}"
            cached = get_cached(cache_key)
            if cached is not None:
                return cached
            result = await func(*args, **kwargs)
            if result is not None:
                set_cached(cache_key, result, ttl)
            return result
        return wrapper
    return decorator
