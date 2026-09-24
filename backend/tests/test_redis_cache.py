"""
Unit Tests — Redis L1 Cache Adapter
======================================
Tests RedisCache with a mock Redis client (no real Redis needed).
Tests graceful degradation, JSON operations, invalidation, and singleton.
"""
import io
import json
import os
import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pandas as pd
import pytest


# ── Test RedisCache with mock client ──────────────────────────────────────

class TestRedisCacheJSON:
    """Test JSON get/set operations."""

    def _make_cache(self, mock_client):
        """Create a RedisCache with a mocked Redis client."""
        with patch("redis.Redis.from_url", return_value=mock_client):
            from backend.modules.shared.infrastructure.redis_cache import RedisCache
            cache = RedisCache("redis://fake:6379/0")
        return cache

    def test_get_json_hit(self):
        """Cache hit returns deserialized JSON."""
        mock = MagicMock()
        mock.ping.return_value = True
        data = {"vix": 18.5, "state_key": "2__1__2"}
        mock.get.return_value = json.dumps(data).encode()

        cache = self._make_cache(mock)
        result = cache.get_json("mcp:vix/sigmet:MARKET:latest")

        assert result == data
        mock.get.assert_called_once_with("mcp:vix/sigmet:MARKET:latest")

    def test_get_json_miss(self):
        """Cache miss returns None."""
        mock = MagicMock()
        mock.ping.return_value = True
        mock.get.return_value = None

        cache = self._make_cache(mock)
        result = cache.get_json("mcp:nonexistent:X:latest")

        assert result is None

    def test_set_json_stores_with_ttl(self):
        """set_json calls setex with correct TTL."""
        mock = MagicMock()
        mock.ping.return_value = True

        cache = self._make_cache(mock)
        data = {"score": 42}
        cache.set_json("test:key", data, ttl=120)

        mock.setex.assert_called_once()
        args = mock.setex.call_args
        assert args[0][0] == "test:key"
        assert args[0][1] == 120
        assert json.loads(args[0][2]) == data

    def test_get_json_corrupted_entry(self):
        """Corrupted JSON is deleted and returns None."""
        mock = MagicMock()
        mock.ping.return_value = True
        mock.get.return_value = b"not-valid-json{{"

        cache = self._make_cache(mock)
        result = cache.get_json("corrupted:key")

        assert result is None
        mock.delete.assert_called_once_with("corrupted:key")


class TestRedisCacheGracefulDegradation:
    """Test graceful fallback when Redis is unavailable."""

    def _make_cache(self, mock_client):
        with patch("redis.Redis.from_url", return_value=mock_client):
            from backend.modules.shared.infrastructure.redis_cache import RedisCache
            cache = RedisCache("redis://fake:6379/0")
        return cache

    def test_unavailable_on_init(self):
        """If Redis fails on init ping, cache reports unavailable."""
        mock = MagicMock()
        mock.ping.side_effect = Exception("Connection refused")

        cache = self._make_cache(mock)
        assert not cache.is_available()

    def test_get_json_when_unavailable(self):
        """get_json returns None when Redis is down."""
        mock = MagicMock()
        mock.ping.side_effect = Exception("Connection refused")

        cache = self._make_cache(mock)
        result = cache.get_json("any:key")

        assert result is None

    def test_set_json_when_unavailable(self):
        """set_json is a no-op when Redis is down."""
        mock = MagicMock()
        mock.ping.side_effect = Exception("Connection refused")

        cache = self._make_cache(mock)
        cache.set_json("any:key", {"data": 1})

        mock.setex.assert_not_called()

    def test_connection_error_marks_unavailable(self):
        """ConnectionError during get marks cache as unavailable."""
        import redis as _redis
        mock = MagicMock()
        mock.ping.return_value = True
        mock.get.side_effect = _redis.ConnectionError("Lost connection")

        cache = self._make_cache(mock)
        assert cache.is_available()

        result = cache.get_json("any:key")

        assert result is None
        assert not cache.is_available()


class TestRedisCacheInvalidation:
    """Test cache invalidation."""

    def _make_cache(self, mock_client):
        with patch("redis.Redis.from_url", return_value=mock_client):
            from backend.modules.shared.infrastructure.redis_cache import RedisCache
            cache = RedisCache("redis://fake:6379/0")
        return cache

    def test_invalidate_single_key(self):
        """invalidate() deletes one key."""
        mock = MagicMock()
        mock.ping.return_value = True

        cache = self._make_cache(mock)
        cache.invalidate("bars:SPY:1d")

        mock.delete.assert_called_once_with("bars:SPY:1d")

    def test_invalidate_pattern(self):
        """invalidate_pattern() scans and deletes matching keys."""
        mock = MagicMock()
        mock.ping.return_value = True
        mock.scan.return_value = (0, [b"bars:SPY:1d", b"bars:SPY:1h"])

        cache = self._make_cache(mock)
        cache.invalidate_pattern("bars:SPY:*")

        mock.scan.assert_called_once()
        mock.delete.assert_called_once_with(b"bars:SPY:1d", b"bars:SPY:1h")


class TestRedisCacheDataFrame:
    """Test DataFrame serialization/deserialization."""

    def _make_cache(self, mock_client):
        with patch("redis.Redis.from_url", return_value=mock_client):
            from backend.modules.shared.infrastructure.redis_cache import RedisCache
            cache = RedisCache("redis://fake:6379/0")
        return cache

    def test_dataframe_roundtrip(self):
        """DataFrame survives set→get roundtrip via Feather."""
        stored = {}

        mock = MagicMock()
        mock.ping.return_value = True

        def mock_setex(key, ttl, value):
            stored[key] = value

        def mock_get(key):
            return stored.get(key)

        mock.setex.side_effect = mock_setex
        mock.get.side_effect = mock_get

        cache = self._make_cache(mock)

        # Create a sample OHLCV DataFrame
        dates = pd.date_range("2025-01-01", periods=5, freq="D", tz="UTC")
        df = pd.DataFrame(
            {
                "open": [100.0, 101, 102, 103, 104],
                "high": [105.0, 106, 107, 108, 109],
                "low": [95.0, 96, 97, 98, 99],
                "close": [102.0, 103, 104, 105, 106],
                "volume": [1000, 2000, 3000, 4000, 5000],
            },
            index=dates,
        )
        df.index.name = "time"

        cache.set_dataframe("bars:TEST:1d", df, ttl=3600)
        result = cache.get_dataframe("bars:TEST:1d")

        assert result is not None
        assert len(result) == 5
        assert list(result.columns) == ["open", "high", "low", "close", "volume"]
        assert result.index.name == "time"
        assert result.iloc[0]["close"] == 102.0


class TestRedisCacheSingleton:
    """Test get_redis_cache() singleton behavior."""

    def test_returns_none_without_redis_url(self):
        """No REDIS_URL → returns None (no cache)."""
        import backend.modules.shared.infrastructure.redis_cache as rc_mod

        # Reset singleton
        rc_mod._instance = None

        with patch.dict(os.environ, {}, clear=True):
            # Remove REDIS_URL if present
            os.environ.pop("REDIS_URL", None)
            result = rc_mod.get_redis_cache()

        assert result is None

    def test_returns_instance_with_redis_url(self):
        """REDIS_URL set → returns a RedisCache instance."""
        import backend.modules.shared.infrastructure.redis_cache as rc_mod

        # Reset singleton
        rc_mod._instance = None

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch.dict(os.environ, {"REDIS_URL": "redis://fake:6379/0"}):
            with patch("redis.Redis.from_url", return_value=mock_client):
                result = rc_mod.get_redis_cache()

        assert result is not None
        assert result.is_available()

        # Cleanup: reset singleton for other tests
        rc_mod._instance = None


class TestRegimeStateCacheRoundtrip:
    """Test StateSnapshot serialization/deserialization for cache."""

    def test_snapshot_from_cache_dict(self):
        """StateSnapshot survives asdict → JSON → _snapshot_from_cache_dict."""
        from dataclasses import asdict
        from backend.modules.shared.domain.entities.state_snapshot import StateSnapshot
        from backend.modules.shared.infrastructure.postgres_regime_state import (
            PostgresRegimeStateAdapter,
        )

        now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        original = StateSnapshot(
            key="vol:quality:MARKET",
            current_state="ELEVATED",
            previous_state="CALM",
            entered_at=now,
            closed_at=None,
            duration_bars=5,
            trigger_event="VIX_ZSCORE=2.3",
            metadata={"vix": 28.5},
        )

        # Simulate Redis roundtrip: asdict → JSON dumps → JSON loads → reconstruct
        d = asdict(original)
        json_str = json.dumps(d, default=str)
        d_back = json.loads(json_str)

        reconstructed = PostgresRegimeStateAdapter._snapshot_from_cache_dict(d_back)

        assert reconstructed.key == original.key
        assert reconstructed.current_state == original.current_state
        assert reconstructed.previous_state == original.previous_state
        assert reconstructed.duration_bars == original.duration_bars
        assert reconstructed.trigger_event == original.trigger_event
        assert reconstructed.metadata == original.metadata
        assert reconstructed.closed_at is None
        # entered_at is parsed from ISO string
        assert reconstructed.entered_at.year == 2025
        assert reconstructed.entered_at.month == 6
