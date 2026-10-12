"""Tests for F4.3 Post-Ingesta Zigzag Legs Hook and Invariants.

Verifies:
1. Regression test: [etf for etf, _ in SECTOR_ETFS] raises ValueError, whereas list(SECTOR_ETFS.keys()) yields exactly 13 canonical ETFs.
2. Invariant: len(canonical_etfs) == 13 with non-empty string tickers.
3. Resilience: One ticker failure does not block the other 12 ETFs.
4. Error tracking: Failures are reported with error messages, not silently swallowed.
"""
import pytest
from unittest.mock import MagicMock, patch
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS
from backend.daemons.data_vault_daemon import sync_canonical_rotation_zigzag_legs


def test_canonical_etfs_syntax_regression():
    """A-1: Verify that [etf for etf, _ in SECTOR_ETFS] FAILS with ValueError,

    and that list(SECTOR_ETFS.keys()) succeeds with exactly 13 canonical entities.
    """
    # 1. Reproduce the old bug and assert it raises ValueError
    with pytest.raises(ValueError, match="too many values to unpack"):
        _ = ["SPY", "QQQ"] + [etf for etf, _ in SECTOR_ETFS]

    # 2. Verify the standard repo pattern yields exactly 13 entities
    canonical_etfs = ["SPY", "QQQ"] + list(SECTOR_ETFS.keys())
    assert len(canonical_etfs) == 13
    assert set(canonical_etfs) == {
        "SPY", "QQQ", "XLK", "XLV", "XLF", "XLY", "XLP",
        "XLI", "XLE", "XLU", "XLRE", "XLB", "XLC"
    }
    for sym in canonical_etfs:
        assert isinstance(sym, str) and len(sym) >= 3


def test_sync_canonical_rotation_zigzag_legs_all_succeed():
    """A-2 & A-4: Verify all 13 tickers are synced when no exceptions occur."""
    mock_store = MagicMock()
    with patch("backend.daemons.zigzag_legs_daemon.sync_ticker_zigzag_legs") as mock_sync:
        mock_sync.return_value = 100

        result = sync_canonical_rotation_zigzag_legs(mock_store)

        assert result["total"] == 13
        assert len(result["synced"]) == 13
        assert len(result["failed"]) == 0
        assert mock_sync.call_count == 13


def test_sync_canonical_rotation_zigzag_legs_partial_failure_resilience():
    """Verify that if one ticker fails, the other 12 still sync and failure is recorded."""
    mock_store = MagicMock()

    def mock_sync_side_effect(store, ticker, rebuild=False):
        if ticker == "XLE":
            raise RuntimeError("Database connection glitch for XLE")
        return 50

    with patch("backend.daemons.zigzag_legs_daemon.sync_ticker_zigzag_legs", side_effect=mock_sync_side_effect):
        result = sync_canonical_rotation_zigzag_legs(mock_store)

        assert result["total"] == 13
        assert len(result["synced"]) == 12
        assert "XLE" in result["failed"]
        assert "Database connection glitch" in result["failed"]["XLE"]
        assert "SPY" in result["synced"]
        assert "QQQ" in result["synced"]
