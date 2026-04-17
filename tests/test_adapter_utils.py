"""
Tests for adapter_utils: TTLCache, retry, cached_adapter_call.
"""
import time
import pytest
from backend.infrastructure.data_providers.adapter_utils import (
    TTLCache, retry_with_backoff, cached_adapter_call,
    macro_cache, sector_cache, ticker_cache, market_cache,
)


# ═══════════════════════════════════════════════════════════
# TTLCache
# ═══════════════════════════════════════════════════════════

class TestTTLCache:
    def test_set_and_get(self):
        cache = TTLCache(ttl_seconds=60)
        cache.set("key1", {"data": 42})
        assert cache.get("key1") == {"data": 42}

    def test_miss_returns_none(self):
        cache = TTLCache(ttl_seconds=60)
        assert cache.get("nonexistent") is None

    def test_expiry(self):
        cache = TTLCache(ttl_seconds=0)  # Expire immediately
        cache.set("key1", "value")
        time.sleep(0.01)
        assert cache.get("key1") is None

    def test_max_entries_eviction(self):
        cache = TTLCache(ttl_seconds=60, max_entries=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # Should evict oldest ("a")
        assert cache.size == 2
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_invalidate(self):
        cache = TTLCache(ttl_seconds=60)
        cache.set("key1", "val")
        cache.invalidate("key1")
        assert cache.get("key1") is None

    def test_clear(self):
        cache = TTLCache(ttl_seconds=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.size == 0

    def test_stats(self):
        cache = TTLCache(ttl_seconds=60, max_entries=100)
        cache.set("a", 1)
        cache.set("b", 2)
        stats = cache.stats()
        assert stats["total_entries"] == 2
        assert stats["ttl_seconds"] == 60
        assert stats["max_entries"] == 100

    def test_overwrite_existing_key(self):
        cache = TTLCache(ttl_seconds=60)
        cache.set("key1", "old")
        cache.set("key1", "new")
        assert cache.get("key1") == "new"


# ═══════════════════════════════════════════════════════════
# retry_with_backoff
# ═══════════════════════════════════════════════════════════

class TestRetryWithBackoff:
    def test_succeeds_first_try(self):
        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def fn():
            return "ok"
        assert fn() == "ok"

    def test_retries_on_failure(self):
        attempts = []

        @retry_with_backoff(max_retries=2, base_delay=0.01)
        def fn():
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("transient")
            return "recovered"

        assert fn() == "recovered"
        assert len(attempts) == 3

    def test_raises_after_exhausted(self):
        @retry_with_backoff(max_retries=1, base_delay=0.01)
        def fn():
            raise ValueError("permanent")

        with pytest.raises(ValueError, match="permanent"):
            fn()

    def test_only_catches_specified_exceptions(self):
        @retry_with_backoff(max_retries=3, base_delay=0.01, exceptions=(ConnectionError,))
        def fn():
            raise ValueError("not retried")

        with pytest.raises(ValueError):
            fn()


# ═══════════════════════════════════════════════════════════
# cached_adapter_call
# ═══════════════════════════════════════════════════════════

class TestCachedAdapterCall:
    def test_cache_miss_then_hit(self):
        cache = TTLCache(ttl_seconds=60)
        call_count = [0]

        def fetcher(x):
            call_count[0] += 1
            return {"result": x}

        r1 = cached_adapter_call(cache, "test:key", fetcher, "hello")
        r2 = cached_adapter_call(cache, "test:key", fetcher, "hello")
        assert r1 == {"result": "hello"}
        assert r2 == {"result": "hello"}
        assert call_count[0] == 1  # Only called once

    def test_different_keys_call_separately(self):
        cache = TTLCache(ttl_seconds=60)
        call_count = [0]

        def fetcher(x):
            call_count[0] += 1
            return x

        cached_adapter_call(cache, "key:a", fetcher, "a")
        cached_adapter_call(cache, "key:b", fetcher, "b")
        assert call_count[0] == 2


# ═══════════════════════════════════════════════════════════
# Pre-configured caches exist
# ═══════════════════════════════════════════════════════════

class TestPreconfiguredCaches:
    def test_macro_cache_30min(self):
        assert macro_cache._ttl == 1800

    def test_sector_cache_15min(self):
        assert sector_cache._ttl == 900

    def test_ticker_cache_5min(self):
        assert ticker_cache._ttl == 300

    def test_market_cache_10min(self):
        assert market_cache._ttl == 600
