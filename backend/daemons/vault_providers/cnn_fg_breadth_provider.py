"""
CNN FG Breadth Provider — FG_STRENGTH & FG_BREADTH
=====================================================
Vault provider for the two CNN Fear & Greed sub-indicators that require
individual SP500 stock data:

  FG_STRENGTH: NYSE 52-week Highs/Lows ratio (Stock Price Strength)
  FG_BREADTH:  McClellan Volume Summation Index (Stock Price Breadth)

EXECUTION ORDER: MUST run AFTER OHLCVProvider and ALONGSIDE BreadthProvider.
Both use the same SP500 closes/volumes — data is already in the Vault.

Tickers persisted as INDICATOR type with sector="Sentiment".
"""
import logging
from datetime import datetime, UTC

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)


class CnnFgBreadthProvider:
    """Vault provider for CNN F&G Strength and Breadth sub-indicators."""

    name = "cnn_fg_breadth"
    categories = ["cnn_fg_breadth"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        """Calculate FG_STRENGTH and FG_BREADTH from SP500 OHLCV data."""
        if _already_vaulted_today(store, "macro/cnn_fg_breadth", "SP500"):
            logger.info("📊 CNN FG Breadth already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today"}

        return self._compute(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        """Requires ALL SP500 tickers — falls back to run_full."""
        return self._compute(store)

    def _compute(self, store: TimescaleDataStore) -> dict:
        """Core computation: load SP500 closes+volumes → compute both indicators."""
        try:
            from backend.modules.shared.domain.rules.cnn_fg_breadth_calculator import (
                calculate_highs_lows_ratio,
                calculate_mcclellan_vsi,
            )

            # Load 400 days to cover 252d lookback for H/L + warmup for McClellan
            all_closes = store.load_all_latest_closes(days=400, sp500_only=True)
            all_volumes = store.load_all_latest_volumes(days=400, sp500_only=True)

            if not all_closes:
                logger.warning("CNN FG Breadth: no SP500 OHLCV data available")
                return {"status": "error", "reason": "no_data"}

            # ── Sub-indicator 2: Stock Price Strength (H/L ratio) ──
            hl_ratio = calculate_highs_lows_ratio(all_closes, lookback=252)

            # ── Sub-indicator 3: McClellan Volume Summation Index ──
            mvsi = calculate_mcclellan_vsi(all_closes, all_volumes)

            n_constituents = len(all_closes)
            now = datetime.now(UTC)

            # Persist as OHLCV bars (single-value indicator convention)
            if hl_ratio is not None:
                store.upsert_ohlcv_bar(
                    ticker="FG_STRENGTH", timeframe="1d", time=now,
                    open=hl_ratio, high=hl_ratio, low=hl_ratio, close=hl_ratio,
                    volume=n_constituents,
                )

            if mvsi is not None:
                store.upsert_ohlcv_bar(
                    ticker="FG_BREADTH", timeframe="1d", time=now,
                    open=mvsi, high=mvsi, low=mvsi, close=mvsi,
                    volume=n_constituents,
                )

            # Persist snapshot for idempotency check
            snapshot = {
                "fg_strength": hl_ratio,
                "fg_breadth": mvsi,
                "tickers_counted": n_constituents,
                "timestamp": now.isoformat(),
            }
            store.save_mcp_snapshot("macro/cnn_fg_breadth", "SP500", snapshot)

            hl_str = f"{hl_ratio:.2f}" if hl_ratio is not None else "N/A"
            mvsi_str = f"{mvsi:.0f}" if mvsi is not None else "N/A"
            logger.info(
                f"📊 CNN FG Breadth vault: FG_STRENGTH={hl_str} FG_BREADTH={mvsi_str} "
                f"({n_constituents} SP500 tickers)"
            )

            return {
                "status": "ok",
                "fg_strength": hl_ratio,
                "fg_breadth": mvsi,
                "n_constituents": n_constituents,
            }

        except Exception as e:
            logger.warning(f"CNN FG Breadth vault failed (non-critical): {e}")
            return {"status": "error", "error": str(e)}


register_provider(CnnFgBreadthProvider())
