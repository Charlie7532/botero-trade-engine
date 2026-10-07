"""
Breadth Provider — S5TH / S5TW / S5FI / BSI
===============================================
Calculates % of SP500 constituents above their 200/50/20-DMA.
EXECUTION ORDER: MUST run AFTER OHLCVProvider to use fresh closes.
Source: Computed from OHLCV bars (not external API).
Supports dirty_range propagation from OHLCVProvider revisions.
"""
from datetime import datetime, date, UTC
import logging
from typing import Optional

import pandas as pd

from backend.daemons.vault_providers import register_provider
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.rules.macro_trend_calculator import calculate_breadth

logger = logging.getLogger(__name__)


class BreadthProvider:
    """Vault provider for breadth indicators (S5TH, S5TW, S5FI, BSI)."""

    name = "breadth"
    categories = ["breadth"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        """Calculate all three breadth indicators from SP500 OHLCV data."""
        force = kwargs.get("force", False)
        dirty_snap = store.load_mcp_latest("ohlcv/dirty_range", "PENDING")
        has_dirty = dirty_snap is not None and isinstance(dirty_snap, dict) and "dirty_from" in dirty_snap

        last_s5tw = store.bars_last_date("S5TW", "1d")
        last_spy = store.bars_last_date("SPY", "1d")

        if not force and not has_dirty and last_s5tw and last_spy and last_s5tw >= last_spy:
            logger.info(f"📊 Breadth already up to date ({last_s5tw} >= SPY {last_spy}) — skipping")
            return {"status": "skipped", "reason": "already_up_to_date"}

        dirty_from = None
        if has_dirty:
            try:
                dirty_from = pd.to_datetime(dirty_snap["dirty_from"]).date()
            except Exception:
                dirty_from = None

        res = self._compute_breadth(store, dirty_from=dirty_from, force=force)
        if res.get("status") == "ok" and has_dirty:
            store.save_mcp_snapshot("ohlcv/dirty_range", "CONSUMED_S5", {
                "timestamp": datetime.now(UTC).isoformat(),
                "dirty_from": str(dirty_from),
            })
        return res

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        """Breadth requires ALL SP500 tickers — falls back to run_full."""
        return self._compute_breadth(store)

    def _compute_breadth(
        self,
        store: TimescaleDataStore,
        dirty_from: Optional[date] = None,
        force: bool = False,
    ) -> dict:
        """Core breadth calculation logic with dirty range propagation."""
        try:
            last_spy = store.bars_last_date("SPY", "1d")
            if not last_spy:
                logger.warning("Breadth: SPY date not found")
                return {"status": "error", "reason": "no_spy_date"}

            last_s5tw = store.bars_last_date("S5TW", "1d")
            if not force and not dirty_from and last_s5tw and last_s5tw >= last_spy:
                logger.info(f"📊 Breadth already up to date ({last_s5tw} >= SPY {last_spy}) — skipping")
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

            logger.info(f"📊 Calculating breadth for {len(recalc_dates)} date(s): {recalc_dates[0]} to {recalc_dates[-1]}")

            last_results = {}
            for target_date in recalc_dates:
                effective_date = pd.Timestamp(target_date).tz_localize("UTC").normalize() if not hasattr(target_date, "tzinfo") or not target_date.tzinfo else pd.Timestamp(target_date).tz_convert("UTC").normalize()

                # Load historical closes up to target_date
                conn = store._conn()
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            """SELECT b.ticker, b.time::date, b.close
                               FROM market.ohlcv_bars b
                               JOIN market.ticker_metadata m ON b.ticker = m.ticker
                               WHERE b.timeframe = '1d'
                                 AND b.time <= %s
                                 AND b.time >= %s - INTERVAL '300 days'
                                 AND m.asset_type = 'STOCK'
                                 AND 'SP500' = ANY(m.index_membership)
                                 AND m.update_source = 'vault_ohlcv_bars'
                                 AND b.close > 0
                               ORDER BY b.ticker, b.time""",
                            (target_date, target_date),
                        )
                        closes = {}
                        for tkr, _, close_px in cur.fetchall():
                            closes.setdefault(tkr, []).append(float(close_px))
                finally:
                    store._put(conn)

                if not closes:
                    logger.warning(f"Breadth: no SP500 close data available for {target_date}")
                    continue

                s5th = calculate_breadth(closes, ma_length=200)
                s5tw = calculate_breadth(closes, ma_length=20)
                s5fi = calculate_breadth(closes, ma_length=50)

                n_constituents = len(closes)
                snapshot = {
                    "s5th": s5th, "s5tw": s5tw, "s5fi": s5fi,
                    "tickers_counted": n_constituents,
                    "as_of_date": effective_date.strftime("%Y-%m-%d"),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                store.save_mcp_snapshot("macro/breadth", "SP500", snapshot)

                for ticker, value in [("S5TH", s5th), ("S5TW", s5tw), ("S5FI", s5fi), ("BSI", s5tw)]:
                    if value is not None:
                        store.upsert_ohlcv_bar(
                            ticker=ticker, timeframe="1d", time=effective_date,
                            open=value, high=value, low=value, close=value,
                            volume=n_constituents,
                            overwrite=True,
                        )
                        store.upsert_ticker_metadata(
                            ticker=ticker,
                            sector="Breadth",
                            industry="INDICATOR",
                            market_cap_bucket=None,
                        )

                last_results = {"status": "ok", "s5th": s5th, "s5tw": s5tw, "s5fi": s5fi, "date": str(target_date)}
                s5th_str = f"{s5th:.1f}%" if s5th is not None else "N/A"
                s5fi_str = f"{s5fi:.1f}%" if s5fi is not None else "N/A"
                s5tw_str = f"{s5tw:.1f}%" if s5tw is not None else "N/A"
                logger.info(
                    f"📊 Breadth [{target_date}]: S5TH={s5th_str} S5FI={s5fi_str} "
                    f"S5TW={s5tw_str} ({n_constituents} SP500 tickers)"
                )

            return last_results

        except Exception as e:
            logger.warning(f"Breadth vault failed (non-critical): {e}")
            return {"status": "error", "error": str(e)}


register_provider(BreadthProvider())
