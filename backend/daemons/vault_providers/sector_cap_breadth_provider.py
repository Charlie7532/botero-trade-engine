"""
Sector Cap Breadth Provider — Vault Daemon
==============================================
Calculates per-sector breadth indicators weighted by market capitalization
(S5CAP_XLK_TH, S5CAP_XLK_FI, S5CAP_XLK_TW, etc.) from constituent closes.

MUST run AFTER sector_breadth_provider (Tier 3d) to use latest closes.
"""
import logging
import os
import json
from datetime import datetime, UTC
import numpy as np

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.domain.constants.sectors import (
    SECTOR_ETFS,
    canonicalize,
)

logger = logging.getLogger(__name__)

# Reverse map: sector_name -> etf
_SECTOR_TO_ETF = {v: k for k, v in SECTOR_ETFS.items()}

# Cache file path
CACHE_FILE = os.path.join(os.path.dirname(__file__), "mcap_cache.json")

class SectorCapBreadthProvider:
    """Calculates and stores cap-weighted sector breadth (33 indicators)."""

    name = "sector_cap_breadth"
    categories = ["sector_cap_breadth"]

    def run_full(self, store) -> dict:
        """Run full sector cap breadth calculation."""
        if _already_vaulted_today(store, "macro/sector_cap_breadth", "BATCH_DONE"):
            logger.info("📊 Sector Cap Breadth already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today"}
        return _compute_and_store(store)

    def run_ticker(self, store, ticker: str) -> dict:
        """Sector cap breadth is a collective metric — always recalculates all."""
        return _compute_and_store(store)


def _compute_and_store(store) -> dict:
    """Core logic: load SP500 closes by sector, compute cap-weighted breadth, write bars."""
    now = datetime.now(UTC)
    today_str = now.strftime("%Y-%m-%d")

    # Load market caps from cache
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            mcap_cache = json.load(f)
    else:
        mcap_cache = {}

    # Load closes grouped by sector (need 250 days for 200-DMA)
    by_sector, sector_map = store.load_sp500_closes_by_sector(days=300)

    if not by_sector:
        logger.warning("SectorCapBreadthProvider: no sector data from vault")
        return {"status": "no_data"}

    written = 0
    skipped = 0

    for sector_raw, closes_dict in by_sector.items():
        sector = canonicalize(sector_raw)
        etf = _SECTOR_TO_ETF.get(sector)
        if not etf:
            continue

        n_constituents = len(closes_dict)
        if n_constituents < 10:
            skipped += 1
            continue

        # Calculate relative weights inside this sector using the cache
        total_mcap = sum(mcap_cache.get(t, 10_000_000_000) for t in closes_dict.keys())
        if total_mcap <= 0:
            total_mcap = 10_000_000_000 * len(closes_dict)
        
        weights = {t: mcap_cache.get(t, 10_000_000_000) / total_mcap for t in closes_dict.keys()}

        # 3 Timeframes: 200d (TH), 50d (FI), 20d (TW)
        timeframes = [("structural", 200, "TH"), ("intermediate", 50, "FI"), ("tactical", 20, "TW")]

        for scale_name, ma_length, suffix in timeframes:
            indicator_ticker = f"S5CAP_{etf}_{suffix}"
            
            # Compute weighted breadth
            weighted_above = 0.0
            total_weight = 0.0
            
            for ticker, closes in closes_dict.items():
                if len(closes) < ma_length:
                    continue
                ma = float(np.mean(closes[-ma_length:]))
                current = closes[-1]
                w = weights.get(ticker, 0.0)
                total_weight += w
                if ma > 0 and current > ma:
                    weighted_above += w

            # Normalize weights if some constituents were skipped due to history
            if total_weight > 0:
                breadth_pct = round((weighted_above / total_weight) * 100, 1)
            else:
                breadth_pct = None

            if breadth_pct is None:
                continue

            # Write as OHLCV bar
            store.upsert_ohlcv_bar(
                ticker=indicator_ticker,
                timeframe="1d",
                time=today_str,
                open=breadth_pct,
                high=breadth_pct,
                low=breadth_pct,
                close=breadth_pct,
                volume=n_constituents,
            )
            written += 1

    # Mark as done for today
    store.save_mcp_snapshot("macro/sector_cap_breadth", "BATCH_DONE", {
        "written": written, "skipped": skipped,
        "timestamp": datetime.now(UTC).isoformat(),
    })

    logger.info(
        f"✅ SectorCapBreadthProvider: wrote {written} cap-weighted breadth bars, "
        f"skipped {skipped} sectors"
    )
    return {"status": "ok", "written": written, "skipped": skipped}


# Register
register_provider(SectorCapBreadthProvider())
