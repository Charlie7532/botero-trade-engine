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
Supports dirty_range propagation from OHLCVProvider revisions.
"""
from datetime import datetime, date, UTC
import logging
from typing import Optional

import pandas as pd

from backend.daemons.vault_providers import register_provider
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.rules.volume_breadth_calculator import (
    calculate_all_volume_breadth,
)

logger = logging.getLogger(__name__)


class VolumeBreadthProvider:
    """Vault provider for volume breadth indicators (SV5TH, SV5TW, SV5FI)."""

    name = "volume_breadth"
    categories = ["volume_breadth"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        """Calculate all three volume breadth indicators from SP500 OHLCV data."""
        force = kwargs.get("force", False)
        dirty_snap = store.load_mcp_latest("ohlcv/dirty_range", "PENDING")
        has_dirty = dirty_snap is not None and isinstance(dirty_snap, dict) and "dirty_from" in dirty_snap

        last_sv5tw = store.bars_last_date("SV5TW", "1d")
        last_spy = store.bars_last_date("SPY", "1d")

        if not force and not has_dirty and last_sv5tw and last_spy and last_sv5tw >= last_spy:
            logger.info(f"📊 Volume Breadth already up to date ({last_sv5tw} >= SPY {last_spy}) — skipping")
            return {"status": "skipped", "reason": "already_up_to_date"}

        dirty_from = None
        if has_dirty:
            try:
                dirty_from = pd.to_datetime(dirty_snap["dirty_from"]).date()
            except Exception:
                dirty_from = None

        res = self._compute_volume_breadth(store, dirty_from=dirty_from, force=force)
        if res.get("status") == "ok" and has_dirty:
            store.save_mcp_snapshot("ohlcv/dirty_range", "CONSUMED_SV5", {
                "timestamp": datetime.now(UTC).isoformat(),
                "dirty_from": str(dirty_from),
            })
        return res

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        """Volume breadth requires ALL SP500 tickers — falls back to run_full."""
        return self._compute_volume_breadth(store)

    def _compute_volume_breadth(
        self,
        store: TimescaleDataStore,
        dirty_from: Optional[date] = None,
        force: bool = False,
    ) -> dict:
        """Core volume breadth calculation logic with dirty range propagation."""
        try:
            last_spy = store.bars_last_date("SPY", "1d")
            if not last_spy:
                logger.warning("VolumeBreadth: SPY date not found")
                return {"status": "error", "reason": "no_spy_date"}

            last_sv5tw = store.bars_last_date("SV5TW", "1d")
            if not force and not dirty_from and last_sv5tw and last_sv5tw >= last_spy:
                logger.info(f"📊 Volume Breadth already up to date ({last_sv5tw} >= SPY {last_spy}) — skipping")
                return {"status": "skipped", "reason": "already_up_to_date"}

            # Determine recalculation date range
            if dirty_from and dirty_from <= last_spy:
                conn = store._conn()
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            """SELECT time::date FROM market.ohlcv_bars 
                               WHERE ticker = 'SPY' AND timeframe = '1d' AND time::date >= %s AND time::date <= %s
                               ORDER BY time ASC""",
                            (dirty_from, last_spy),
                        )
                        recalc_dates = [r[0] for r in cur.fetchall()]
                finally:
                    store._put(conn)
            else:
                recalc_dates = [last_spy]

            if not recalc_dates:
                recalc_dates = [last_spy]

            logger.info(f"📊 Calculating volume breadth for {len(recalc_dates)} date(s): {recalc_dates[0]} to {recalc_dates[-1]}")

            last_results = {}
            for target_date in recalc_dates:
                effective_date = pd.Timestamp(target_date).tz_localize("UTC").normalize() if not hasattr(target_date, "tzinfo") or not target_date.tzinfo else pd.Timestamp(target_date).tz_convert("UTC").normalize()

                # Load historical volume up to target_date
                conn = store._conn()
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            """SELECT b.ticker, b.time::date, b.volume
                               FROM market.ohlcv_bars b
                               JOIN market.ticker_metadata m ON b.ticker = m.ticker
                               WHERE b.timeframe = '1d'
                                 AND b.time <= %s
                                 AND b.time >= %s - INTERVAL '300 days'
                                 AND m.asset_type = 'STOCK'
                                 AND 'SP500' = ANY(m.index_membership)
                                 AND m.update_source = 'vault_ohlcv_bars'
                                 AND b.volume > 0
                               ORDER BY b.ticker, b.time""",
                            (target_date, target_date),
                        )
                        vols = {}
                        for tkr, _, vol in cur.fetchall():
                            vols.setdefault(tkr, []).append(float(vol))
                finally:
                    store._put(conn)

                if not vols:
                    logger.warning(f"VolumeBreadth: no SP500 volume data available for {target_date}")
                    continue

                results = calculate_all_volume_breadth(vols)
                sv5th = results.get("structural")
                sv5fi = results.get("intermediate")
                sv5tw = results.get("tactical")

                n_constituents = len(vols)
                snapshot = {
                    "sv5th": sv5th, "sv5fi": sv5fi, "sv5tw": sv5tw,
                    "tickers_counted": n_constituents,
                    "as_of_date": effective_date.strftime("%Y-%m-%d"),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                store.save_mcp_snapshot("macro/volume_breadth", "SP500", snapshot)

                for ticker, value in [("SV5TH", sv5th), ("SV5FI", sv5fi), ("SV5TW", sv5tw)]:
                    if value is not None:
                        store.upsert_ohlcv_bar(
                            ticker=ticker, timeframe="1d", time=effective_date,
                            open=value, high=value, low=value, close=value,
                            volume=n_constituents,
                            overwrite=True,
                        )

                last_results = {"status": "ok", "sv5th": sv5th, "sv5fi": sv5fi, "sv5tw": sv5tw, "date": str(target_date)}
                sv5th_str = f"{sv5th:.1f}%" if sv5th is not None else "N/A"
                sv5fi_str = f"{sv5fi:.1f}%" if sv5fi is not None else "N/A"
                sv5tw_str = f"{sv5tw:.1f}%" if sv5tw is not None else "N/A"
                logger.info(
                    f"📊 Volume Breadth [{target_date}]: SV5TH={sv5th_str} SV5FI={sv5fi_str} "
                    f"SV5TW={sv5tw_str} ({n_constituents} SP500 tickers)"
                )

            return last_results

        except Exception as e:
            logger.warning(f"Volume Breadth vault failed (non-critical): {e}")
            return {"status": "error", "error": str(e)}


register_provider(VolumeBreadthProvider())
