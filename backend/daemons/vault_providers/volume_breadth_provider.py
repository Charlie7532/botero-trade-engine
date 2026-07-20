"""
Volume Breadth Provider — SV5TH / SV5FI / SV5TW
====================================================
Calculates % of SP500 constituents with volume MA crossovers.
Nested design:
    SV5TW: EMA(5, vol)  > SMA(20, vol)   (tactical)
    SV5FI: SMA(20, vol) > SMA(50, vol)    (intermediate)
    SV5TH: SMA(50, vol) > SMA(200, vol)   (structural)

EXECUTION ORDER: MUST run AFTER OHLCVProvider to use fresh volumes.
Source: Computed from OHLCV bars (not external API).
"""
import logging
from datetime import datetime, UTC

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)


class VolumeBreadthProvider:
    """Vault provider for volume breadth indicators (SV5TH, SV5TW, SV5FI)."""

    name = "volume_breadth"
    categories = ["volume_breadth"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        """Calculate all three volume breadth indicators from SP500 OHLCV data."""
        if _already_vaulted_today(store, "macro/volume_breadth", "SP500"):
            logger.info("📊 Volume Breadth already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today"}

        return self._compute_volume_breadth(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        """Volume breadth requires ALL SP500 tickers — falls back to run_full."""
        return self._compute_volume_breadth(store)

    def _compute_volume_breadth(self, store: TimescaleDataStore) -> dict:
        """Core volume breadth calculation logic."""
        try:
            from backend.modules.shared.domain.rules.volume_breadth_calculator import (
                calculate_all_volume_breadth,
            )

            all_volumes = store.load_all_latest_volumes(days=300, sp500_only=True)
            if not all_volumes:
                logger.warning("VolumeBreadth: no SP500 volume data available")
                return {"status": "error", "reason": "no_data"}

            results = calculate_all_volume_breadth(all_volumes)

            sv5th = results.get("structural")
            sv5fi = results.get("intermediate")
            sv5tw = results.get("tactical")

            if sv5th is None and sv5fi is None and sv5tw is None:
                logger.warning("VolumeBreadth: insufficient history for MA calculation")
                return {"status": "error", "reason": "insufficient_history"}

            n_constituents = len(all_volumes)
            snapshot = {
                "sv5th": sv5th, "sv5fi": sv5fi, "sv5tw": sv5tw,
                "tickers_counted": n_constituents,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            store.save_mcp_snapshot("macro/volume_breadth", "SP500", snapshot)

            now = datetime.now(UTC)
            for ticker, value in [("SV5TH", sv5th), ("SV5FI", sv5fi), ("SV5TW", sv5tw)]:
                if value is not None:
                    store.upsert_ohlcv_bar(
                        ticker=ticker, timeframe="1d", time=now,
                        open=value, high=value, low=value, close=value,
                        volume=n_constituents,
                    )

            sv5th_str = f"{sv5th:.1f}%" if sv5th is not None else "N/A"
            sv5fi_str = f"{sv5fi:.1f}%" if sv5fi is not None else "N/A"
            sv5tw_str = f"{sv5tw:.1f}%" if sv5tw is not None else "N/A"
            logger.info(
                f"📊 Volume Breadth vault: SV5TH={sv5th_str} SV5FI={sv5fi_str} "
                f"SV5TW={sv5tw_str} ({n_constituents} SP500 tickers)"
            )
            return {"status": "ok", "sv5th": sv5th, "sv5fi": sv5fi, "sv5tw": sv5tw}

        except Exception as e:
            logger.warning(f"Volume Breadth vault failed (non-critical): {e}")
            return {"status": "error", "error": str(e)}


register_provider(VolumeBreadthProvider())
