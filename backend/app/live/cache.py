import json
import logging
import time
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class LiveCache(Protocol):
    def get(self, key: str) -> dict[str, Any] | None: ...

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None: ...


class InMemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, dict[str, Any]]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        item = self._data.get(key)
        if not item or item[0] <= time.monotonic():
            self._data.pop(key, None)
            return None
        return json.loads(json.dumps(item[1]))

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        self._data[key] = (time.monotonic() + ttl_seconds, json.loads(json.dumps(value)))


class RedisCache:
    """Redis failures degrade to cache misses/no-ops so a Redis outage never breaks the API."""

    def __init__(self, client) -> None:
        self._r = client

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            raw = self._r.get(key)
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.warning("Redis read failed: %s", type(e).__name__)
            return None

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        try:
            self._r.setex(key, ttl_seconds, json.dumps(value))
        except Exception as e:
            logger.warning("Redis write failed: %s", type(e).__name__)


def build_cache(redis_url: str) -> tuple[LiveCache, bool]:
    """Returns (cache, shared). Falls back to in-process memory when Redis is not configured or unreachable."""
    if redis_url:
        try:
            import redis

            client = redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=2)
            client.ping()
            return RedisCache(client), True
        except Exception as e:
            logger.warning("Redis unavailable (%s); using in-memory live cache", type(e).__name__)
    return InMemoryCache(), False
