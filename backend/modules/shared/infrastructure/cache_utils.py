"""
MCP Adapter Utilities — Cache & Retry
=======================================
Shared infrastructure for all MCP data adapters.

Provides:
- TTL cache with configurable expiry
- Retry with exponential backoff
- Structured logging helpers
"""
import logging
import time
import functools
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class TTLCache:
    """
    Simple in-memory TTL cache for MCP responses.
    
    Avoids redundant MCP queries within the same trading cycle.
    
    Usage:
        cache = TTLCache(ttl_seconds=300)  # 5 min
        cache.set("AAPL:qgarp", data)
        result = cache.get("AAPL:qgarp")  # Returns data or None if expired
    """

    def __init__(self, ttl_seconds: int = 300, max_entries: int = 500):
        self._store: dict[str, tuple[Any, float]] = {}
        self._ttl = ttl_seconds
        self._max_entries = max_entries

    def get(self, key: str) -> Optional[Any]:
        """Get value if exists and not expired."""
        if key not in self._store:
            return None
        value, timestamp = self._store[key]
        if time.time() - timestamp > self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any):
        """Set value with current timestamp."""
        # Evict oldest if at capacity
        if len(self._store) >= self._max_entries:
            oldest_key = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest_key]
        self._store[key] = (value, time.time())

    def invalidate(self, key: str):
        """Remove a specific key."""
        self._store.pop(key, None)

    def clear(self):
        """Clear entire cache."""
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)

    def stats(self) -> dict:
        """Cache statistics."""
        now = time.time()
        active = sum(1 for _, (_, ts) in self._store.items() if now - ts <= self._ttl)
        return {
            "total_entries": len(self._store),
            "active_entries": active,
            "expired_entries": len(self._store) - active,
            "ttl_seconds": self._ttl,
            "max_entries": self._max_entries,
        }


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
    on_retry: Callable = None,
):
    """
    Decorator: retry with exponential backoff.
    
    Usage:
        @retry_with_backoff(max_retries=3, base_delay=1.0)
        def fetch_data():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__}: "
                            f"{e}. Waiting {delay:.1f}s..."
                        )
                        if on_retry:
                            on_retry(attempt, e)
                        time.sleep(delay)
            logger.error(
                f"All {max_retries} retries failed for {func.__name__}: {last_exception}"
            )
            raise last_exception
        return wrapper
    return decorator


def cached_adapter_call(
    cache: TTLCache,
    key: str,
    fetch_fn: Callable,
    *args,
    **kwargs,
) -> Any:
    """
    Check cache first, if miss then fetch and store.
    
    Usage:
        result = cached_adapter_call(
            cache, f"{ticker}:qgarp",
            gurufocus.parse_qgarp_scorecard, ticker, raw_data,
        )
    """
    cached = cache.get(key)
    if cached is not None:
        logger.debug(f"Cache HIT: {key}")
        return cached

    logger.debug(f"Cache MISS: {key}")
    result = fetch_fn(*args, **kwargs)
    if result is not None:
        cache.set(key, result)
    return result


# ═══════════════════════════════════════════════════════════
# PRE-CONFIGURED CACHES (shared across adapters)
# ═══════════════════════════════════════════════════════════

# Macro data changes slowly — cache for 30 minutes
macro_cache = TTLCache(ttl_seconds=1800, max_entries=50)

# Sector data — cache for 15 minutes
sector_cache = TTLCache(ttl_seconds=900, max_entries=100)

# Ticker-level data — cache for 5 minutes
ticker_cache = TTLCache(ttl_seconds=300, max_entries=500)

# Market overview — cache for 10 minutes
market_cache = TTLCache(ttl_seconds=600, max_entries=50)
