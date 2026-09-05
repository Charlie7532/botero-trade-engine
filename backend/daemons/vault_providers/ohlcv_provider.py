"""
OHLCV Provider — Stock/ETF daily bar updates
================================================
Sources: yfinance (primary) + Alpaca (enrichment: vwap, trade_count)
Updates only tickers with update_source = 'vault_ohlcv_bars'.
"""
import logging
import os
from datetime import datetime, timedelta, UTC

from backend.daemons.vault_providers import register_provider
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)

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
            f"{stats['enriched']} enriched with trade_count+vwap, "
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

                    start_str = (last + timedelta(days=1)).strftime("%Y-%m-%d")
                    df = yf.download(download_sym, start=start_str, interval="1d",
                                     progress=False, auto_adjust=True)
                    if df.empty:
                        last_date = last.date() if hasattr(last, 'date') else last
                        ref_date = datetime.now(UTC).date()
                        if last_date < ref_date:
                            bdays = max(0, len(pd.bdate_range(last_date, ref_date)) - 1)
                            if bdays > 1:
                                stats["failed"][ticker] = f"No data from feed ({download_sym}), {bdays}d lag"
                        continue

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
                    df.index.name = "timestamp"
                    df.dropna(subset=["open", "high", "low", "close"], inplace=True)

                    if df.empty:
                        continue

                    store.save_bars(ticker, "1d", df)
                    stats["updated"] += 1

                    # Enrich with Alpaca trade_count + vwap
                    self._enrich_alpaca(store, ticker, df, stats)

                except Exception as e:
                    stats["failed"][ticker] = str(e)
                    logger.warning(f"  {ticker} ({download_sym}) OHLCV update failed: {e}")

        return stats

    def _enrich_alpaca(self, store, ticker, df, stats):
        """Best-effort enrichment with Alpaca trade_count and vwap."""
        import pandas as pd
        api_key = os.environ.get("ALPACA_API_KEY", "")
        if not api_key:
            return
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            client = StockHistoricalDataClient(
                api_key, os.environ.get("ALPACA_SECRET_KEY", "")
            )
            request = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=TimeFrame.Day,
                start=df.index.min(),
                end=df.index.max() + pd.Timedelta(days=1),
                limit=10,
            )
            alpaca_bars = client.get_stock_bars(request)
            if alpaca_bars and ticker in alpaca_bars.data:
                conn = store._conn()
                try:
                    with conn.cursor() as cur:
                        for bar in alpaca_bars.data[ticker]:
                            vwap = float(bar.vwap) if hasattr(bar, 'vwap') and bar.vwap else None
                            tc = int(bar.trade_count) if hasattr(bar, 'trade_count') and bar.trade_count else None
                            if vwap or tc:
                                cur.execute(
                                    """UPDATE market.ohlcv_bars
                                       SET vwap = %s, trade_count = %s
                                       WHERE ticker = %s AND timeframe = '1d'
                                       AND time::date = %s""",
                                    (vwap, tc, ticker, bar.timestamp.date()),
                                )
                    conn.commit()
                    stats["enriched"] += 1
                except Exception:
                    conn.rollback()
                finally:
                    store._put(conn)
        except Exception:
            pass


# Auto-register on import
register_provider(OHLCVProvider())
