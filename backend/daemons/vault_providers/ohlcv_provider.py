"""
OHLCV Provider — Stock/ETF daily bar updates
================================================
Sources: yfinance (primary)
Updates only tickers with update_source = 'vault_ohlcv_bars'.
"""
import logging
import os
from datetime import datetime, timedelta, time as dtime, UTC
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import yfinance as yf

from backend.daemons.vault_providers import register_provider
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)

# Partial-bar guard (audit 2026-10-04 / 2026-10-06)
_ET = ZoneInfo("America/New_York")
SESSION_FINAL_ET = dtime(18, 0)   # a session's daily bar is FINAL only after 18:00 ET of that date
OVERLAP_DAYS = 7                  # calendar days re-fetched each run to heal bars stored before final

# Reuse the daemon's daily guard
from backend.daemons.data_vault_daemon import _already_vaulted_today



# Ticker translation map for external feeds (Yahoo Finance, etc.)
# Vault canonical symbol -> External provider downloadable symbol
SOURCE_TICKER_MAP = {
    "TNX": "^TNX",       # 10-Year Treasury Yield Index
    "IRX": "^IRX",       # 13-Week Treasury Bill Index
    "DXY": "DX-Y.NYB",   # US Dollar Index (ICE)
    "SPX": "^GSPC",      # S&P 500 Index
    "NDQ": "^IXIC",      # Nasdaq Composite
    "SKEW": "^SKEW",     # CBOE SKEW
    "TRIN": "^TRIN",     # Arms TRIN
    "BK": "BNY",         # The Bank of New York Mellon rebranded ticker (May 2026)
    "SATS": "ECHO",      # EchoStar rebranded ticker (June 2026)
}


class OHLCVProvider:
    """Vault provider for OHLCV bar updates."""

    name = "ohlcv"
    categories = ["ohlcv"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        """Update all tickers with update_source='vault_ohlcv_bars' or retry pending."""
        pending_retries = kwargs.get("retry_tickers", [])
        if _already_vaulted_today(store, "ohlcv/update", "BATCH_DONE"):
            if pending_retries:
                logger.info(f"🔄 OHLCV batch done today, but retrying {len(pending_retries)} pending failed tickers: {pending_retries}")
                return self.retry_tickers(store, pending_retries)
            logger.info("📈 OHLCV bars already updated today — skipping")
            return {"status": "skipped", "reason": "already_today", "failed": {}}

        tickers = kwargs.get("tickers")
        if not tickers:
            tickers = self._get_tickers(store)

        stats = self._update_tickers(store, tickers)

        if stats["updated"] > 0:
            store.save_mcp_snapshot("ohlcv/update", "BATCH_DONE", {
                "timestamp": datetime.now(UTC).isoformat(),
                "tickers_updated": stats["updated"],
                "tickers_enriched": stats["enriched"],
                "failed_count": len(stats.get("failed", {})),
            })

        logger.info(
            f"📈 OHLCV vault: {stats['updated']} tickers updated, "
            f"{len(stats.get('failed', {}))} failed"
        )
        return {"status": "ok", **stats}

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        """Update a SINGLE ticker on-demand (VRR)."""
        stats = self._update_tickers(store, [ticker])
        return {"status": "ok", **stats}

    def retry_tickers(self, store: TimescaleDataStore, tickers: list[str]) -> dict:
        """Explicitly retry a list of previously failed tickers."""
        if not tickers:
            return {"status": "ok", "updated": 0, "enriched": 0, "failed": {}}
        stats = self._update_tickers(store, tickers)
        return {"status": "ok", **stats}

    def _get_tickers(self, store: TimescaleDataStore) -> list[str]:
        """Pull tickers eligible for OHLCV updates."""
        conn = store._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT ticker FROM market.ticker_metadata
                    WHERE update_source = 'vault_ohlcv_bars'
                      AND (industry IS DISTINCT FROM 'INDICATOR')
                    ORDER BY ticker
                """)
                tickers = [row[0] for row in cur.fetchall()]
                # Guarantee critical macro indicators are always included
                for macro_tk in ["TNX", "IRX", "DXY"]:
                    if macro_tk not in tickers:
                        tickers.append(macro_tk)
                return sorted(list(set(tickers)))
        finally:
            store._put(conn)

    def _update_tickers(self, store: TimescaleDataStore, tickers: list[str]) -> dict:
        """Core update logic — shared between run_full and run_ticker."""
        stats = {"updated": 0, "enriched": 0, "failed": {}}

        try:
            import yfinance as yf
            import pandas as pd
        except ImportError:
            return {"updated": 0, "enriched": 0, "failed": {}}

        min_dirty_date = None
        revised_tickers_count = 0

        batch_size = 20
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            for ticker in batch:
                download_sym = SOURCE_TICKER_MAP.get(ticker, ticker)
                try:
                    last = store.bars_last_date(ticker, "1d")
                    if not last:
                        continue

                    # State-governed window:
                    # If there are PRELIMINARY bars, rewind to the oldest non-final bar.
                    # Otherwise, use standard OVERLAP_DAYS.
                    oldest_prelim = store.bars_oldest_non_final_date(ticker, "1d")
                    if oldest_prelim:
                        start_date = min(oldest_prelim - timedelta(days=1), last - timedelta(days=OVERLAP_DAYS))
                    else:
                        start_date = last - timedelta(days=OVERLAP_DAYS)

                    start_str = start_date.strftime("%Y-%m-%d")
                    df = yf.download(download_sym, start=start_str, interval="1d",
                                     progress=False, auto_adjust=True)
                    if not df.empty:
                        if isinstance(df.columns, pd.MultiIndex):
                            df = df.xs(download_sym, level=1, axis=1)
                        df.columns = [c.lower() for c in df.columns]
                        required = ["open", "high", "low", "close", "volume"]
                        available = [c for c in required if c in df.columns]
                        df = df[available].copy()
                        if df.index.tz is not None:
                            df.index = df.index.tz_convert("UTC")
                        else:
                            df.index = df.index.tz_localize("UTC")
                        df.index = df.index.normalize()
                        df.index.name = "timestamp"
                        df.dropna(subset=["open", "high", "low", "close"], inplace=True)
                        df = df[~df.index.duplicated(keep="last")]
                        df = _drop_unfinished_session(df)
                        df = _tag_bar_status(df)

                    last_ts = pd.Timestamp(last).tz_localize("UTC")
                    new = df[df.index > last_ts] if not df.empty else df
                    revised = _revised_bars(store, ticker, df[df.index <= last_ts]) if not df.empty else df

                    if new.empty and revised.empty:
                        last_date = last.date() if hasattr(last, 'date') else last
                        ref_date = datetime.now(UTC).date()
                        if last_date < ref_date:
                            bdays = max(0, len(pd.bdate_range(last_date, ref_date)) - 1)
                            if bdays > 1:
                                stats["failed"][ticker] = f"No data from feed ({download_sym}), {bdays}d lag"
                        continue

                    if not revised.empty:
                        rev_min_dt = revised.index.min().date()
                        min_dirty_date = rev_min_dt if min_dirty_date is None else min(min_dirty_date, rev_min_dt)
                        revised_tickers_count += 1
                        store.save_bars(ticker, "1d", revised, overwrite=True)
                        _invalidate_snapshots_from(store, ticker, revised.index.min())
                        logger.info(f"  {ticker}: overwrote {len(revised)} revised bar(s) from {revised.index.min().date()}")
                    if not new.empty:
                        store.save_bars(ticker, "1d", new)
                        logger.info(f"  {ticker}: inserted {len(new)} new bar(s) up to {new.index.max().date()}")
                    stats["updated"] += 1

                except Exception as e:
                    stats["failed"][ticker] = str(e)
                    logger.warning(f"  {ticker} ({download_sym}) OHLCV update failed: {e}")

        if min_dirty_date is not None:
            store.save_mcp_snapshot("ohlcv/dirty_range", "PENDING", {
                "dirty_from": min_dirty_date.isoformat(),
                "timestamp": datetime.now(UTC).isoformat(),
                "tickers_revised_count": revised_tickers_count,
            })
            logger.info(f"🚨 Recorded dirty range for downstream breadth propagation from {min_dirty_date}")

        return stats


def _drop_unfinished_session(df):
    """Drop future-dated bars beyond today's calendar date in New York."""
    if df.empty:
        return df
    now_et = datetime.now(_ET)
    today_et = now_et.date()
    return df[df.index.date <= today_et]


def _tag_bar_status(df):
    """Tag each bar as 'FINAL' or 'PRELIMINARY' based on market session timing."""
    if df.empty:
        return df
    df = df.copy()
    now_et = datetime.now(_ET)
    today_et = now_et.date()
    is_after_final = now_et.time() >= SESSION_FINAL_ET

    statuses = []
    for ts in df.index:
        bar_date = ts.date()
        if bar_date < today_et:
            statuses.append("FINAL")
        elif bar_date == today_et:
            statuses.append("FINAL" if is_after_final else "PRELIMINARY")
        else:
            statuses.append("PRELIMINARY")
    df["bar_status"] = statuses
    return df


def _revised_bars(store: TimescaleDataStore, ticker: str, fresh):
    """Fresh bars already stored that require revision/overwrite.

    Triggers an overwrite if:
    1. The stored bar has bar_status == 'PRELIMINARY' (consolidation of partial session).
    2. The fresh volume differs from stored volume (excluding uniform splits).
    3. The fresh close differs from stored close by > 0.05% without an overarching split.
    """
    if fresh.empty:
        return fresh

    min_date = fresh.index.min().date()
    conn = store._conn()
    stored_rows = {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT time, close, volume, bar_status 
                   FROM market.ohlcv_bars 
                   WHERE ticker = %s AND timeframe = '1d' AND time >= %s""",
                (ticker.upper(), min_date),
            )
            for t, c, v, st in cur.fetchall():
                ts = pd.Timestamp(t).tz_convert("UTC").normalize() if t.tzinfo else pd.Timestamp(t).tz_localize("UTC").normalize()
                stored_rows[ts] = {"close": float(c), "volume": int(v) if v is not None else 0, "status": st}
    finally:
        store._put(conn)

    if not stored_rows:
        return fresh.iloc[0:0]

    common = [ts for ts in fresh.index if ts in stored_rows]
    if not common:
        return fresh.iloc[0:0]

    # Calculate price ratios to detect potential stock splits
    price_ratios = []
    for ts in common:
        s_c = stored_rows[ts]["close"]
        f_c = float(fresh.at[ts, "close"])
        if s_c > 0:
            price_ratios.append(f_c / s_c)

    # Median ratio across the window (if e.g. 0.5 or 2.0 with tight variance -> uniform split/dividend)
    median_ratio = float(np.median(price_ratios)) if price_ratios else 1.0
    is_uniform_rescaling = len(price_ratios) >= 2 and all(abs(r - median_ratio) < 0.001 for r in price_ratios) and abs(median_ratio - 1.0) > 0.01

    changed = []
    for ts in common:
        st_data = stored_rows[ts]
        f_vol = int(fresh.at[ts, "volume"])
        f_close = float(fresh.at[ts, "close"])
        s_vol = st_data["volume"]
        s_close = st_data["close"]
        s_status = st_data["status"]

        # Case 1: Was PRELIMINARY -> must be overwritten with consolidated data
        if s_status == "PRELIMINARY":
            changed.append(ts)
            continue

        # Case 2: Volume revised
        if f_vol != s_vol and not is_uniform_rescaling:
            changed.append(ts)
            continue

        # Case 3: Price revised (idiosyncratic, not uniform split)
        if s_close > 0:
            ratio = f_close / s_close
            # If not a uniform rescaling across all bars, any price difference > 0.05% is a revision
            if not is_uniform_rescaling and abs(ratio - 1.0) > 0.0005:
                changed.append(ts)
                continue

    return fresh.loc[changed]


def _invalidate_snapshots_from(store: TimescaleDataStore, ticker: str, ts) -> None:
    """Delete channel snapshots from ts on, so the incremental snapshot provider recomputes them."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM engine.channel_snapshots WHERE ticker = %s AND timeframe = '1d' AND timestamp >= %s",
                (ticker.upper(), ts.to_pydatetime()),
            )
        conn.commit()
    finally:
        store._put(conn)



# Auto-register on import
register_provider(OHLCVProvider())
