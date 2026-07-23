"""
Sector Volume Intensity Provider — Vault Daemon
===================================================
Calculates Volume Breadth Intensity (VBI) sector by sector
using Z-Score normalization of daily volumes of constituents.

MUST run AFTER sector_volume_breadth_provider to use latest volumes.
"""
import logging
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


class SectorVolumeIntensityProvider:
    """Calculates and stores per-sector Volume Breadth Intensity (11 indicators)."""

    name = "sector_volume_intensity"
    categories = ["sector_volume_intensity"]

    def run_full(self, store) -> dict:
        """Run full VBI calculations."""
        if _already_vaulted_today(store, "macro/sector_volume_intensity", "BATCH_DONE"):
            logger.info("📊 Sector Volume Intensity already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today"}
        return _compute_and_store(store)

    def run_ticker(self, store, ticker: str) -> dict:
        """Volume intensity is a collective metric — always recalculates all."""
        return _compute_and_store(store)


def _compute_and_store(store) -> dict:
    """Core logic: load SP500 volumes by sector, compute VBI Z-scores, write bars."""
    now = datetime.now(UTC)
    today_str = now.strftime("%Y-%m-%d")

    # Load constituent volumes by sector (need 30-40 days for 20d standard deviation)
    by_sector, sector_map = store.load_sp500_volumes_by_sector(days=50)

    if not by_sector:
        logger.warning("SectorVolumeIntensityProvider: no sector data from vault")
        return {"status": "no_data"}

    written = 0
    skipped = 0

    for sector_raw, volumes_dict in by_sector.items():
        sector = canonicalize(sector_raw)
        etf = _SECTOR_TO_ETF.get(sector)
        if not etf:
            continue

        n_constituents = len(volumes_dict)
        if n_constituents < 10:
            skipped += 1
            continue

        z_scores = []
        for ticker, volumes in volumes_dict.items():
            if len(volumes) < 20:
                continue
            vol_window = volumes[-20:]
            mean_vol = np.mean(vol_window)
            std_vol = np.std(vol_window)
            current_vol = volumes[-1]
            if std_vol > 0:
                z = (current_vol - mean_vol) / std_vol
                # Robust Winsorization: Clip individual Z-scores to [-3.0, +3.0]
                z_clipped = float(np.clip(z, -3.0, 3.0))
                z_scores.append(z_clipped)

        if not z_scores:
            continue

        vbi_val = round(float(np.mean(z_scores)), 2)
        indicator_ticker = f"VBI_{etf}"

        # Write VBI to ohlcv_bars
        store.upsert_ohlcv_bar(
            ticker=indicator_ticker,
            timeframe="1d",
            time=today_str,
            open=vbi_val,
            high=vbi_val,
            low=vbi_val,
            close=vbi_val,
            volume=n_constituents,
        )
        written += 1

    # Mark as done for today
    store.save_mcp_snapshot("macro/sector_volume_intensity", "BATCH_DONE", {
        "written": written, "skipped": skipped,
        "timestamp": datetime.now(UTC).isoformat(),
    })

    logger.info(
        f"✅ SectorVolumeIntensityProvider: wrote {written} VBI indicators, "
        f"skipped {skipped} sectors"
    )
    return {"status": "ok", "written": written, "skipped": skipped}


# Register
register_provider(SectorVolumeIntensityProvider())
