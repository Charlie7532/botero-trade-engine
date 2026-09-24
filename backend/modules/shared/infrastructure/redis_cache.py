"""
Redis L1 Cache — Cross-Process Read Acceleration
====================================================
Ephemeral cache layer between consumers and Neon PostgreSQL.
Provides sub-millisecond reads for MCP snapshots, OHLCV bars,
and regime states that would otherwise require 40-150ms WAN
round-trips to the Neon serverless database.

Design:
  - Optional: If REDIS_URL is not set, get_redis_cache() returns None
    and all reads fall through directly to Neon (identical to pre-cache behavior).
  - Graceful degradation: On ConnectionError/TimeoutError, logs warning
    and returns None (cache miss). System never breaks due to Redis.
  - Write-through: Neon is ALWAYS written first. Cache is populated or
    invalidated AFTER the Neon commit succeeds.
  - TTL-based expiration: All keys have configurable TTL. Even if
    invalidation fails, stale data expires automatically.

Clean Architecture: Infrastructure layer only. No domain or port
imports. The TimeSeriesPort interface is unchanged.

Rules: 13 (Vault-First), 16 (Persist-then-Read), 18 (Midnight UTC).
"""
import io
import json
import logging
import os
import threading
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class RedisCache:
    """L1 cache adapter — cross-process, TTL-based, graceful degradation.

    Every public method returns None / does nothing on failure.
    Callers should always treat a None return as a cache miss and
    fall through to the Neon PostgreSQL query.
    """

    def __init__(self, url: str, socket_timeout: float = 2.0):
        import redis as _redis
        self._redis = _redis
        self._client = _redis.Redis.from_url(
            url,
            decode_responses=False,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_timeout,
            retry_on_timeout=False,
        )
        self._available = self._ping()
        if self._available:
            logger.info("Redis L1 cache connected ✓")
        else:
            logger.warning("Redis L1 cache unavailable — all reads go to Neon")

    def _ping(self) -> bool:
        """Check Redis connectivity."""
        try:
            return self._client.ping()
        except Exception:
            return False

    def _reconnect_check(self) -> bool:
        """Periodically retry connection after a failure."""
        if self._available:
            return True
        # Try to reconnect
        self._available = self._ping()
        if self._available:
            logger.info("Redis L1 cache reconnected ✓")
        return self._available

    # ── JSON operations (MCP snapshots, METAR, regime states) ──────────

    def get_json(self, key: str) -> Optional[Any]:
        """Get a JSON-serialized value. Returns None on miss or error."""
        if not self._reconnect_check():
            return None
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except (self._redis.ConnectionError, self._redis.TimeoutError, OSError) as e:
            logger.warning(f"Redis get_json failed ({e}) — falling back to Neon")
            self._available = False
            return None
        except (json.JSONDecodeError, ValueError):
            # Corrupted cache entry — delete and miss
            self._client.delete(key)
            return None

    def set_json(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set a JSON-serialized value with TTL (seconds)."""
        if not self._reconnect_check():
            return
        try:
            raw = json.dumps(value, default=str)
            self._client.setex(key, ttl, raw)
        except (self._redis.ConnectionError, self._redis.TimeoutError, OSError) as e:
            logger.warning(f"Redis set_json failed ({e})")
            self._available = False

    # ── DataFrame operations (OHLCV bars) ──────────────────────────────

    def get_dataframe(self, key: str) -> Optional[pd.DataFrame]:
        """Get a Feather-serialized DataFrame. Returns None on miss or error."""
        if not self._reconnect_check():
            return None
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            buf = io.BytesIO(raw)
            df = pd.read_feather(buf)
            # Restore DatetimeIndex (Feather stores it as a column)
            if "time" in df.columns:
                df = df.set_index("time")
            elif "index" in df.columns:
                df = df.set_index("index")
            return df
        except (self._redis.ConnectionError, self._redis.TimeoutError, OSError) as e:
            logger.warning(f"Redis get_dataframe failed ({e}) — falling back to Neon")
            self._available = False
            return None
        except Exception:
            # Corrupted entry — delete and miss
            try:
                self._client.delete(key)
            except Exception:
                pass
            return None

    def set_dataframe(self, key: str, df: pd.DataFrame, ttl: int = 3600) -> None:
        """Set a DataFrame as Feather bytes with TTL (seconds)."""
        if not self._reconnect_check():
            return
        try:
            buf = io.BytesIO()
            # Reset index so DatetimeIndex is preserved as a column
            df_out = df.reset_index()
            df_out.to_feather(buf)
            self._client.setex(key, ttl, buf.getvalue())
        except (self._redis.ConnectionError, self._redis.TimeoutError, OSError) as e:
            logger.warning(f"Redis set_dataframe failed ({e})")
            self._available = False
        except Exception as e:
            # Feather serialization can fail for exotic dtypes — log and skip
            logger.debug(f"Redis set_dataframe serialization failed ({e})")

    # ── Invalidation ───────────────────────────────────────────────────

    def invalidate(self, key: str) -> None:
        """Delete a single cache key."""
        if not self._reconnect_check():
            return
        try:
            self._client.delete(key)
        except (self._redis.ConnectionError, self._redis.TimeoutError, OSError):
            self._available = False

    def invalidate_pattern(self, pattern: str) -> None:
        """Delete all keys matching a glob pattern (e.g. 'bars:SPY:*')."""
        if not self._reconnect_check():
            return
        try:
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor, match=pattern, count=100)
                if keys:
                    self._client.delete(*keys)
                if cursor == 0:
                    break
        except (self._redis.ConnectionError, self._redis.TimeoutError, OSError):
            self._available = False

    # ── Diagnostics ────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Current availability status (may be stale — call _ping for fresh)."""
        return self._available

    def stats(self) -> dict:
        """Redis server stats for diagnostics."""
        if not self._reconnect_check():
            return {"available": False}
        try:
            info = self._client.info("memory")
            return {
                "available": True,
                "used_memory_human": info.get("used_memory_human", "?"),
                "maxmemory_human": info.get("maxmemory_human", "?"),
                "keys": self._client.dbsize(),
            }
        except Exception:
            return {"available": False}


# ═══════════════════════════════════════════════════════════════════════
# Singleton access — process-wide shared instance
# ═══════════════════════════════════════════════════════════════════════

_instance: Optional[RedisCache] = None
_lock = threading.Lock()


def get_redis_cache() -> Optional[RedisCache]:
    """Return a process-wide shared RedisCache instance.

    Returns None if REDIS_URL is not set — all reads fall through
    to Neon PostgreSQL directly (identical to pre-cache behavior).

    Thread-safe via double-checked locking.
    """
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                url = os.environ.get("REDIS_URL")
                if not url:
                    return None
                try:
                    _instance = RedisCache(url)
                except Exception as e:
                    logger.warning(f"Redis initialization failed ({e}) — running without cache")
                    return None
    return _instance
