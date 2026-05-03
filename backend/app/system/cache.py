"""
app/system/cache.py
───────────────────
Redis caching layer.

Provides:
• Async  get_redis_client()  – used by books/routes.py and borrow/routes.py
• Sync   cache_get / cache_set / cache_delete / cache_flush_all – used by tests
"""

import json
import logging
from typing import Any, Optional

import redis as redis_sync
import redis.asyncio as aioredis

from app.core.config import settings
from app.system.logger import get_logger

logger = get_logger(__name__)

_REDIS_URL = settings.REDIS_URL  # e.g. redis://localhost:6379

# ── Async client (singleton) – used by FastAPI routes ────────────────────────

_async_redis: Optional[aioredis.Redis] = None


async def get_redis_client() -> Optional[aioredis.Redis]:
    """
    Return a shared async Redis client.
    Returns None gracefully if Redis is unavailable.
    """
    global _async_redis
    if _async_redis is None:
        try:
            client = aioredis.from_url(
                _REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            await client.ping()
            _async_redis = client
            logger.info("Async Redis connection established: %s", _REDIS_URL)
        except Exception as exc:
            logger.warning("Async Redis unavailable (%s). Caching disabled.", exc)
            return None
    return _async_redis


# ── Sync client – used only by tests / non-async helpers ─────────────────────

try:
    _sync_client = redis_sync.from_url(
        _REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2,
    )
    _sync_client.ping()
    logger.info("Sync Redis connection established.")
except Exception as _e:
    logger.warning("Sync Redis unavailable (%s). Sync cache calls are no-ops.", _e)
    _sync_client = None  # type: ignore[assignment]

DEFAULT_TTL = 300  # 5 minutes


def _serialize(value: Any) -> str:
    return json.dumps(value, default=str)


def _deserialize(value: str) -> Any:
    return json.loads(value)


def cache_get(key: str) -> Optional[Any]:
    if _sync_client is None:
        return None
    try:
        raw = _sync_client.get(key)
        if raw is None:
            return None
        return _deserialize(raw)
    except Exception as exc:
        logger.error("Cache GET error key=%s: %s", key, exc)
        return None


def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
    if _sync_client is None:
        return False
    try:
        _sync_client.setex(key, ttl, _serialize(value))
        return True
    except Exception as exc:
        logger.error("Cache SET error key=%s: %s", key, exc)
        return False


def cache_delete(key: str) -> bool:
    if _sync_client is None:
        return False
    try:
        result = _sync_client.delete(key)
        return bool(result)
    except Exception as exc:
        logger.error("Cache DELETE error key=%s: %s", key, exc)
        return False


def cache_delete_pattern(pattern: str) -> int:
    if _sync_client is None:
        return 0
    try:
        keys = _sync_client.keys(pattern)
        if keys:
            return _sync_client.delete(*keys)
        return 0
    except Exception as exc:
        logger.error("Cache DELETE PATTERN error '%s': %s", pattern, exc)
        return 0


def cache_flush_all() -> bool:
    if _sync_client is None:
        return False
    try:
        _sync_client.flushdb()
        logger.warning("Cache FLUSH ALL executed")
        return True
    except Exception as exc:
        logger.error("Cache FLUSH ALL error: %s", exc)
        return False


# ── Convenience key builders ──────────────────────────────────────────────────

def books_list_key() -> str:
    return "books:all"


def book_detail_key(book_id: int) -> str:
    return f"books:{book_id}"


def borrow_list_key() -> str:
    return "borrows:all"


def borrow_detail_key(borrow_id: int) -> str:
    return f"borrows:{borrow_id}"


def user_borrows_key(user_id: int) -> str:
    return f"borrows:user:{user_id}"
