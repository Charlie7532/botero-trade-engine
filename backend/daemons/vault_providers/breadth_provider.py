"""
Breadth Provider — S5TH / S5TW / S5FI
=========================================
Calculates % of SP500 constituents above their 200/50/20-DMA.
EXECUTION ORDER: MUST run AFTER OHLCVProvider to use fresh closes.
Source: Computed from OHLCV bars (not external API).
"""
import logging
from datetime import datetime, UTC

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)


class BreadthProvider:
    """Vault provider for breadth indicators (S5TH, S5TW, S5FI)."""

    name = "breadth"
    categories = ["breadth"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        """Calculate all three breadth indicators from SP500 OHLCV data."""
        if _already_vaulted_today(store, "macro/breadth", "SP500"):
            logger.info("📊 Breadth already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today"}

        return self._compute_breadth(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        """Breadth requires ALL SP500 tickers — falls back to run_full."""
        return self._compute_breadth(store)

    def _compute_breadth(self, store: TimescaleDataStore) -> dict:
        """Core breadth calculation logic."""
        try:
            from backend.modules.shared.domain.rules.macro_trend_calculator import calculate_breadth

            all_closes = store.load_all_latest_closes(days=300, sp500_only=True)
            if not all_closes:
                logger.warning("Breadth: no SP500 OHLCV data available")
                return {"status": "error", "reason": "no_data"}

            s5th = calculate_breadth(all_closes, ma_length=200)
            s5tw = calculate_breadth(all_closes, ma_length=20)
            s5fi = calculate_breadth(all_closes, ma_length=50)

            if s5th is None and s5tw is None and s5fi is None:
                logger.warning("Breadth: insufficient history for MA calculation")
                return {"status": "error", "reason": "insufficient_history"}

            n_constituents = len(all_closes)
            snapshot = {
                "s5th": s5th, "s5tw": s5tw, "s5fi": s5fi,
                "tickers_counted": n_constituents,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            store.save_mcp_snapshot("macro/breadth", "SP500", snapshot)

            now = datetime.now(UTC)
            for ticker, value in [("S5TH", s5th), ("S5TW", s5tw), ("S5FI", s5fi)]:
                if value is not None:
                    store.upsert_ohlcv_bar(
                        ticker=ticker, timeframe="1d", time=now,
                        open=value, high=value, low=value, close=value,
                        volume=n_constituents,
                    )

            s5th_str = f"{s5th:.1f}%" if s5th is not None else "N/A"
            s5tw_str = f"{s5tw:.1f}%" if s5tw is not None else "N/A"
            s5fi_str = f"{s5fi:.1f}%" if s5fi is not None else "N/A"
            logger.info(
                f"📊 Breadth vault: S5TH={s5th_str} S5TW={s5tw_str} S5FI={s5fi_str} "
                f"({len(all_closes)} SP500 tickers)"
            )
            return {"status": "ok", "s5th": s5th, "s5tw": s5tw, "s5fi": s5fi}

        except Exception as e:
            logger.warning(f"Breadth vault failed (non-critical): {e}")
            return {"status": "error", "error": str(e)}


register_provider(BreadthProvider())
