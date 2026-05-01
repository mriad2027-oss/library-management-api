import json
import redis
from typing import Any, Optional
from app.core.config import settings
from app.system.logger import get_logger

logger = get_logger(__name__)

# Initialize Redis client
try:
    redis_client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD or None,
        decode_responses=True,
        socket_connect_timeout=5,
    )
    redis_client.ping()
    logger.info("Redis connection established successfully")
except Exception as e:
    logger.warning(f"Redis connection failed: {e}. Caching will be disabled.")
    redis_client = None


DEFAULT_TTL = 300  # 5 minutes


def _serialize(value: Any) -> str:
    return json.dumps(value, default=str)


def _deserialize(value: str) -> Any:
    return json.loads(value)


def cache_get(key: str) -> Optional[Any]:
    """
    Retrieve a value from Redis cache.
    Returns None if key does not exist or Redis is unavailable.
    """
    if redis_client is None:
        return None
    try:
        raw = redis_client.get(key)
        if raw is None:
            logger.debug(f"Cache MISS — key: {key}")
            return None
        logger.debug(f"Cache HIT  — key: {key}")
        return _deserialize(raw)
    except Exception as e:
        logger.error(f"Cache GET error for key '{key}': {e}")
        return None


def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
    """
    Store a value in Redis cache with a TTL (seconds).
    Returns True on success, False otherwise.
    """
    if redis_client is None:
        return False
    try:
        redis_client.setex(key, ttl, _serialize(value))
        logger.debug(f"Cache SET  — key: {key}, ttl: {ttl}s")
        return True
    except Exception as e:
        logger.error(f"Cache SET error for key '{key}': {e}")
        return False


def cache_delete(key: str) -> bool:
    """
    Delete a single key from the cache.
    """
    if redis_client is None:
        return False
    try:
        result = redis_client.delete(key)
        logger.debug(f"Cache DEL  — key: {key}, deleted: {bool(result)}")
        return bool(result)
    except Exception as e:
        logger.error(f"Cache DELETE error for key '{key}': {e}")
        return False


def cache_delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching a pattern (e.g. 'books:*').
    Returns count of deleted keys.
    """
    if redis_client is None:
        return 0
    try:
        keys = redis_client.keys(pattern)
        if keys:
            count = redis_client.delete(*keys)
            logger.debug(f"Cache DEL pattern '{pattern}' — removed {count} key(s)")
            return count
        return 0
    except Exception as e:
        logger.error(f"Cache DELETE PATTERN error for '{pattern}': {e}")
        return 0


def cache_flush_all() -> bool:
    """
    Flush the entire Redis database. Use with caution (mainly for testing).
    """
    if redis_client is None:
        return False
    try:
        redis_client.flushdb()
        logger.warning("Cache FLUSH ALL executed")
        return True
    except Exception as e:
        logger.error(f"Cache FLUSH ALL error: {e}")
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
