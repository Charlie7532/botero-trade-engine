"""
Sector Breadth Provider — Vault Daemon
==========================================
Calculates per-sector breadth indicators (S5_XLK_TH, S5_XLK_FI, etc.)
from S&P 500 constituent OHLCV data already in the vault.

MUST run AFTER OHLCV and Breadth providers (Tier 3c) to use latest closes.

Writes 33 indicator bars (11 sectors × 3 timeframes) as OHLCV bars
with close = breadth percentage (0-100).
"""
import logging
from datetime import datetime, UTC

from backend.daemons.vault_providers import VaultProvider, register
from backend.modules.shared.domain.rules.macro_trend_calculator import (
    calculate_breadth,
)
from backend.modules.shared.domain.constants.sectors import (
    SECTOR_ETFS,
    SECTOR_BREADTH_TICKERS,
    BREADTH_MA_LENGTHS,
)

logger = logging.getLogger(__name__)

# Reverse map: sector_name -> etf
_SECTOR_TO_ETF = {v: k for k, v in SECTOR_ETFS.items()}

# Map ticker_metadata.sector values to canonical SECTOR_ETFS names.
# ticker_metadata uses Finviz naming; SECTOR_ETFS uses canonical GICS.
_FINVIZ_TO_CANONICAL = {
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Financial Services": "Financials",
    "Basic Materials": "Materials",
}


def _canonicalize(sector_name: str) -> str:
    return _FINVIZ_TO_CANONICAL.get(sector_name, sector_name)


class SectorBreadthProvider(VaultProvider):
    """Calculates and stores per-sector breadth (33 indicators)."""

    categories = ["sector_breadth"]

    def run_full(self, store) -> dict:
        """Run full sector breadth calculation."""
        return _compute_and_store(store)

    def run_ticker(self, store, ticker: str) -> dict:
        """Sector breadth is a collective metric — always recalculates all."""
        return _compute_and_store(store)


def _compute_and_store(store) -> dict:
    """Core logic: load SP500 closes by sector, compute breadth, write bars."""
    now = datetime.now(UTC)
    today_str = now.strftime("%Y-%m-%d")

    # Load closes grouped by sector (need 250 days for 200-DMA)
    by_sector, sector_map = store.load_sp500_closes_by_sector(days=300)

    if not by_sector:
        logger.warning("SectorBreadthProvider: no sector data from vault")
        return {"status": "no_data"}

    written = 0
    skipped = 0

    for sector_raw, closes_dict in by_sector.items():
        sector = _canonicalize(sector_raw)
        etf = _SECTOR_TO_ETF.get(sector)
        if not etf or etf not in SECTOR_BREADTH_TICKERS:
            continue

        tickers_in_sector = SECTOR_BREADTH_TICKERS[etf]
        n_constituents = len(closes_dict)

        if n_constituents < 10:
            logger.debug(
                f"SectorBreadthProvider: {sector} has {n_constituents} tickers, "
                f"need ≥10 — skipping"
            )
            skipped += 1
            continue

        for timeframe_key, indicator_ticker in tickers_in_sector.items():
            ma_length = BREADTH_MA_LENGTHS[timeframe_key]
            breadth_pct = calculate_breadth(closes_dict, ma_length)

            if breadth_pct is None:
                continue

            # Write as OHLCV bar (close = breadth %, OHLCV all same)
            store.upsert_ohlcv_bar(
                ticker=indicator_ticker,
                timeframe="1d",
                time=today_str,
                open=breadth_pct,
                high=breadth_pct,
                low=breadth_pct,
                close=breadth_pct,
                volume=n_constituents,  # Store constituent count as volume
            )
            written += 1

    logger.info(
        f"✅ SectorBreadthProvider: wrote {written} breadth bars, "
        f"skipped {skipped} sectors (insufficient constituents)"
    )
    return {"status": "ok", "written": written, "skipped": skipped}


# Auto-register
register(SectorBreadthProvider())
