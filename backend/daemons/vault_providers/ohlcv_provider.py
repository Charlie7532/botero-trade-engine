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

from backend.daemons.vault_providers import register_provider
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)

# Partial-bar guard (audit 2026-10-04: 2026-09-16 bar persisted intraday for 530/563 tickers,
# median volume 4.3% of the 20d median). Decisions, not measurements:
_ET = ZoneInfo("America/New_York")
SESSION_FINAL_ET = dtime(18, 0)   # a session's daily bar is accepted only after 18:00 ET of that date
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

        batch_size = 20
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            for ticker in batch:
                download_sym = SOURCE_TICKER_MAP.get(ticker, ticker)
                try:
                    last = store.bars_last_date(ticker, "1d")
                    if not last:
                        continue

                    start_str = (last - timedelta(days=OVERLAP_DAYS)).strftime("%Y-%m-%d")
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
                        store.save_bars(ticker, "1d", revised, overwrite=True)
                        _invalidate_snapshots_from(store, ticker, revised.index.min())
                        logger.info(f"  {ticker}: overwrote {len(revised)} revised bar(s) from {revised.index.min().date()}")
                    if not new.empty:
                        store.save_bars(ticker, "1d", new)
                    stats["updated"] += 1

                except Exception as e:
                    stats["failed"][ticker] = str(e)
                    logger.warning(f"  {ticker} ({download_sym}) OHLCV update failed: {e}")

        return stats


def _drop_unfinished_session(df):
    """Drop bars whose session date is today (ET) before SESSION_FINAL_ET, or in the future."""
    now_et = datetime.now(_ET)
    last_final = now_et.date() if now_et.time() >= SESSION_FINAL_ET else now_et.date() - timedelta(days=1)
    return df[df.index.date <= last_final]


def _revised_bars(store: TimescaleDataStore, ticker: str, fresh):
    """Fresh bars already stored whose volume differs from the stored one (partial or revised).

    Volume is the comparison key on purpose: a dividend re-adjustment rescales prices but
    not volume, so it does not trigger an overwrite of recent bars onto a new price scale.
    """
    if fresh.empty:
        return fresh
    stored = store.load_bars(ticker, "1d", start=fresh.index.min().date())
    if stored.empty:
        return fresh.iloc[0:0]
    sidx = stored.index.tz_localize("UTC") if stored.index.tz is None else stored.index.tz_convert("UTC")
    stored_vol = stored["volume"].set_axis(sidx.normalize())
    common = fresh.index.intersection(stored_vol.index)
    changed = [ts for ts in common if int(fresh.at[ts, "volume"]) != int(stored_vol.at[ts])]
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
