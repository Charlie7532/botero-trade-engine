"""
Sector Volume Breadth Provider — Vault Daemon
=================================================
Calculates per-sector volume breadth indicators (SV5_XLK_TH, SV5_XLK_FI, etc.)
from S&P 500 constituent OHLCV data already in the vault.

MUST run AFTER OHLCV and VolumeBreadth providers to use latest volumes.

Writes 33 indicator bars (11 sectors × 3 timeframes) as OHLCV bars
with close = volume breadth percentage (0-100).
"""
import logging
from datetime import datetime, UTC

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.domain.rules.volume_breadth_calculator import (
    calculate_volume_breadth,
)
from backend.modules.shared.domain.constants.sectors import (
    SECTOR_ETFS,
    SECTOR_VOLUME_BREADTH_TICKERS,
    VOLUME_BREADTH_MA_CONFIG,
    canonicalize,
)

logger = logging.getLogger(__name__)

# Reverse map: sector_name -> etf
_SECTOR_TO_ETF = {v: k for k, v in SECTOR_ETFS.items()}


class SectorVolumeBreadthProvider:
    """Calculates and stores per-sector volume breadth (33 indicators)."""

    name = "sector_volume_breadth"
    categories = ["sector_volume_breadth"]

    def run_full(self, store) -> dict:
        """Run full sector volume breadth calculation."""
        if _already_vaulted_today(store, "macro/sector_volume_breadth", "BATCH_DONE"):
            logger.info("📊 Sector Volume Breadth already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today"}
        return _compute_and_store(store)

    def run_ticker(self, store, ticker: str) -> dict:
        """Sector volume breadth is a collective metric — always recalculates all."""
        return _compute_and_store(store)


def _compute_and_store(store) -> dict:
    """Core logic: load SP500 volumes by sector, compute volume breadth, write bars."""
    now = datetime.now(UTC)

    # Load volumes grouped by sector (need 300 days for 200-DMA)
    by_sector, sector_map = store.load_sp500_volumes_by_sector(days=300)

    if not by_sector:
        logger.warning("SectorVolumeBreadthProvider: no sector data from vault")
        return {"status": "no_data"}

    written = 0
    skipped = 0

    for sector_raw, volumes_dict in by_sector.items():
        sector = canonicalize(sector_raw)
        etf = _SECTOR_TO_ETF.get(sector)
        if not etf or etf not in SECTOR_VOLUME_BREADTH_TICKERS:
            continue

        tickers_in_sector = SECTOR_VOLUME_BREADTH_TICKERS[etf]
        n_constituents = len(volumes_dict)

        if n_constituents < 10:
            logger.debug(
                f"SectorVolumeBreadthProvider: {sector} has {n_constituents} tickers, "
                f"need ≥10 — skipping"
            )
            skipped += 1
            continue

        for timeframe_key, indicator_ticker in tickers_in_sector.items():
            config = VOLUME_BREADTH_MA_CONFIG[timeframe_key]
            breadth_pct = calculate_volume_breadth(
                volumes_dict,
                fast_length=config["fast"],
                slow_length=config["slow"],
                fast_type=config["fast_type"],
            )

            if breadth_pct is None:
                continue

            # Write as OHLCV bar (close = volume breadth %, OHLCV all same)
            store.upsert_ohlcv_bar(
                ticker=indicator_ticker,
                timeframe="1d",
                time=now,
                open=breadth_pct,
                high=breadth_pct,
                low=breadth_pct,
                close=breadth_pct,
                volume=n_constituents,  # Store constituent count as volume
            )
            written += 1

    # Mark as done for idempotency guard
    store.save_mcp_snapshot("macro/sector_volume_breadth", "BATCH_DONE", {
        "written": written, "skipped": skipped,
        "timestamp": datetime.now(UTC).isoformat(),
    })

    logger.info(
        f"✅ SectorVolumeBreadthProvider: wrote {written} volume breadth bars, "
        f"skipped {skipped} sectors (insufficient constituents)"
    )
    return {"status": "ok", "written": written, "skipped": skipped}


# Auto-register
register_provider(SectorVolumeBreadthProvider())
