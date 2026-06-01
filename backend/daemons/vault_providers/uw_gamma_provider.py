"""
UW Gamma Provider — Vault Provider for Options Gamma / Vol / Structure Data
=============================================================================
Fetches Phase 1 UW endpoints (Spot GEX, Greeks, IV Term Structure, Max Pain,
OI by Strike, Vol Stats, Sector Tide, Short Interest) via UWDataBridge
and persists to the Vault (market.mcp_snapshots).

Storage Architecture:
    SNAPSHOT DATA (per-cycle, mcp_snapshots):
        uw/spot_gex, uw/greeks, uw/gex_by_expiry, uw/iv_term_structure,
        uw/vol_stats, uw/max_pain, uw/oi_per_strike, uw/nope,
        uw/sector_tide, uw/sector_etfs, uw/top_impact

    HISTORICAL TIME-SERIES (daily, ohlcv_bars — Rule 14):
        UW_GEX_{ticker}:  Net GEX from gex_aggregate (251 days)
        UW_SKEW_{ticker}: 25-delta risk reversal (128 days)
        UW_SI_{ticker}:   Short interest % (118 reports)

    These are stored as pseudo-OHLCV per Rule 14:
        open=high=low=close=value, volume=0

API Budget (with market hours guard):
    ~45 calls/cycle × 78 cycles/day (market hours) = ~3,510 daily (18% of 20K)
"""
import logging
import math
import time
from datetime import date, datetime, timezone, timedelta

import pandas as pd

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)

# Sectors tracked for Sector Tide
TRACKED_SECTORS = [
    "Technology",
    "Financials",
    "Healthcare",
    "Energy",
    "Consumer Cyclical",
]

# Max tickers per cycle (API budget guard)
MAX_TICKERS_PER_CYCLE = 5

# ═══════════════════════════════════════════════════════════
# MARKET HOURS GUARD
# ═══════════════════════════════════════════════════════════

# US Eastern offset: UTC-4 (EDT) or UTC-5 (EST)
# Simplified: use fixed UTC-4 for EDT (March-November).
# During EST (Nov-March), market hours shift by 1h — acceptable tolerance.
_ET_OFFSET = timedelta(hours=-4)


def _is_market_hours() -> bool:
    """Check if current time is within US equity market hours (9:30-16:00 ET).

    Uses simplified EDT offset (UTC-4). Accurate during EDT (Mar-Nov).
    During EST (Nov-Mar), effectively checks 10:30-17:00 UTC which is
    still a reasonable approximation for the guard's purpose.
    """
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc + _ET_OFFSET
    # Market hours: 9:30-16:00 ET
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    # Also check it's a weekday (Mon=0, Sun=6)
    is_weekday = now_et.weekday() < 5
    return is_weekday and market_open <= now_et <= market_close


def _is_extended_hours() -> bool:
    """Check if within extended hours (7:00-20:00 ET) — for vol_stats/SI."""
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc + _ET_OFFSET
    extended_open = now_et.replace(hour=7, minute=0, second=0, microsecond=0)
    extended_close = now_et.replace(hour=20, minute=0, second=0, microsecond=0)
    is_weekday = now_et.weekday() < 5
    return is_weekday and extended_open <= now_et <= extended_close


# Track last off-hours run to enforce 1x/hour cadence
_last_off_hours_run: datetime | None = None
_OFF_HOURS_CADENCE = timedelta(hours=1)


def _should_run_off_hours() -> bool:
    """Off-hours soft guard: allow 1x/hour instead of every cycle."""
    global _last_off_hours_run
    now = datetime.now(timezone.utc)
    if _last_off_hours_run is None:
        _last_off_hours_run = now
        return True
    if now - _last_off_hours_run >= _OFF_HOURS_CADENCE:
        _last_off_hours_run = now
        return True
    return False


# ═══════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════

def _sanitize(obj):
    """Recursively replace NaN/Inf with None for JSONB storage."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def _already_vaulted_today(store: TimescaleDataStore, category: str, ticker: str) -> bool:
    """Check if we already have a snapshot for this category/ticker today."""
    today_str = date.today().isoformat()
    existing = store.load_mcp_snapshot(category, ticker, today_str)
    return existing is not None


def _safe_float(val, default: float = 0.0) -> float:
    """Safely cast API string values to float."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return default
        try:
            return float(val)
        except ValueError:
            return default
    return default


# ═══════════════════════════════════════════════════════════
# HISTORICAL DATA EXPLODER — Rule 14 alignment
# ═══════════════════════════════════════════════════════════

def _explode_gex_to_ohlcv(store: TimescaleDataStore, ticker: str, data: list) -> int:
    """Explode gex_aggregate (251 daily records) into ohlcv_bars.

    Stored as UW_GEX_{ticker} with:
        close = net_gex (call_gamma - put_gamma)
        open  = call_gamma
        high  = call_gamma (same as open)
        low   = put_gamma
        volume = 0

    Also stores charm/vanna/delta in a separate indicator per ticker
    but for now we capture the primary signal: net GEX.
    """
    if not data or not isinstance(data, list):
        return 0

    indicator = f"UW_GEX_{ticker.upper()}"
    rows = []
    for item in data:
        dt = item.get("date")
        if not dt:
            continue
        call_g = _safe_float(item.get("call_gamma"))
        put_g = _safe_float(item.get("put_gamma"))
        net_gex = call_g + put_g  # put_gamma is already negative from API
        rows.append({
            "time": pd.Timestamp(dt),
            "open": call_g,
            "high": call_g,
            "low": put_g,
            "close": net_gex,
            "volume": 0,
        })

    if not rows:
        return 0

    df = pd.DataFrame(rows).set_index("time").sort_index()
    # Remove duplicates (same date)
    df = df[~df.index.duplicated(keep="last")]
    store.save_bars(indicator, "1d", df)

    # Register metadata
    store.upsert_ticker_metadata(
        ticker=indicator,
        sector="Options Flow",
        industry="INDICATOR",
        market_cap_bucket=None,
    )
    return len(df)


def _explode_skew_to_ohlcv(store: TimescaleDataStore, ticker: str, data: list) -> int:
    """Explode risk_reversal (128 daily records) into ohlcv_bars.

    Stored as UW_SKEW_{ticker} with:
        close = risk_reversal value (25-delta skew)
        open=high=low=close (single value indicator)
        volume = 0
    """
    if not data or not isinstance(data, list):
        return 0

    indicator = f"UW_SKEW_{ticker.upper()}"
    rows = []
    for item in data:
        dt = item.get("date")
        if not dt:
            continue
        val = _safe_float(item.get("risk_reversal"))
        rows.append({
            "time": pd.Timestamp(dt),
            "open": val,
            "high": val,
            "low": val,
            "close": val,
            "volume": 0,
        })

    if not rows:
        return 0

    df = pd.DataFrame(rows).set_index("time").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    store.save_bars(indicator, "1d", df)

    store.upsert_ticker_metadata(
        ticker=indicator,
        sector="Options Flow",
        industry="INDICATOR",
        market_cap_bucket=None,
    )
    return len(df)


def _explode_si_to_ohlcv(store: TimescaleDataStore, ticker: str, data: list) -> int:
    """Explode short_interest (118 biweekly reports) into ohlcv_bars.

    Stored as UW_SI_{ticker} with:
        close = si_float (short interest as % of stock float)
        open  = days_to_cover
        high  = fee_rate
        low   = si_float (same as close for easy load_bars access)
        volume = short_interest (number of shares short)

    Note: "stock float" here = shares available for public trading (int),
    distinct from Python float type. si_float is the ratio (0.0-1.0).
    """
    if not data or not isinstance(data, list):
        return 0

    indicator = f"UW_SI_{ticker.upper()}"
    rows = []
    for item in data:
        dt = item.get("market_date") or item.get("date")
        if not dt:
            continue
        si_pct = _safe_float(item.get("si_float"))
        dtc = _safe_float(item.get("days_to_cover"))
        fee = _safe_float(item.get("fee_rate"))
        si_shares = int(_safe_float(item.get("short_interest")))
        rows.append({
            "time": pd.Timestamp(dt),
            "open": dtc,
            "high": fee,
            "low": si_pct,
            "close": si_pct,
            "volume": si_shares,
        })

    if not rows:
        return 0

    df = pd.DataFrame(rows).set_index("time").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    store.save_bars(indicator, "1d", df)

    store.upsert_ticker_metadata(
        ticker=indicator,
        sector="Short Interest",
        industry="INDICATOR",
        market_cap_bucket=None,
    )
    return len(df)


# ═══════════════════════════════════════════════════════════
# MAIN PROVIDER
# ═══════════════════════════════════════════════════════════

class UWGammaProvider:
    """Vault provider for UW options gamma, volatility, and structure data."""

    name = "uw_gamma"
    categories = [
        "uw/spot_gex", "uw/greeks", "uw/gex_aggregate", "uw/gex_by_expiry",
        "uw/iv_term_structure", "uw/vol_stats", "uw/risk_reversal",
        "uw/max_pain", "uw/oi_per_strike", "uw/nope",
        "uw/sector_tide", "uw/sector_etfs", "uw/top_impact",
        "uw/short_interest",
    ]

    def _get_bridge(self):
        """Lazy import to avoid circular deps."""
        from backend.modules.flow_intelligence.infrastructure.uw_mcp_bridge import UWDataBridge
        return UWDataBridge()

    # ═══════════════════════════════════════════════════════════
    # MARKET-LEVEL DATA (~5 API calls)
    # ═══════════════════════════════════════════════════════════

    def _vault_market_data(self, store: TimescaleDataStore, bridge) -> dict:
        """Vault market-level data: sector tides, ETFs, top impact."""
        stats = {"sector_tides": 0, "sector_etfs": False, "top_impact": False}

        # 1. Sector Tide for tracked sectors
        for sector in TRACKED_SECTORS:
            try:
                tide = bridge.fetch_sector_tide(sector)
                if tide:
                    store.save_mcp_snapshot("uw/sector_tide", sector.upper(), _sanitize(tide))
                    stats["sector_tides"] += 1
            except Exception as e:
                logger.debug(f"  Sector tide {sector}: {e}")

        # 2. Sector ETFs snapshot
        try:
            etfs = bridge.fetch_sector_etfs()
            if etfs:
                store.save_mcp_snapshot("uw/sector_etfs", "MARKET", _sanitize(etfs))
                stats["sector_etfs"] = True
        except Exception as e:
            logger.debug(f"  Sector ETFs: {e}")

        # 3. Top Net Impact
        try:
            impact = bridge.fetch_top_net_impact()
            if impact:
                store.save_mcp_snapshot("uw/top_impact", "MARKET", _sanitize(impact))
                stats["top_impact"] = True
        except Exception as e:
            logger.debug(f"  Top impact: {e}")

        return stats

    # ═══════════════════════════════════════════════════════════
    # PER-TICKER DATA (~8 API calls per ticker)
    # ═══════════════════════════════════════════════════════════

    def _vault_ticker_data(self, store: TimescaleDataStore, bridge, ticker: str) -> dict:
        """Vault all gamma/vol/options data for a single ticker."""
        stats = {"endpoints_ok": 0, "endpoints_failed": 0}

        # Per-cycle endpoints (every call)
        per_cycle = [
            ("uw/spot_gex",          lambda: bridge.fetch_spot_gex_by_strike(ticker)),
            ("uw/greeks",            lambda: bridge.fetch_greeks(ticker)),
            ("uw/gex_by_expiry",     lambda: bridge.fetch_gex_by_expiry(ticker)),
            ("uw/iv_term_structure", lambda: bridge.fetch_iv_term_structure(ticker)),
            ("uw/vol_stats",         lambda: bridge.fetch_vol_stats(ticker)),
            ("uw/max_pain",          lambda: bridge.fetch_max_pain(ticker)),
            ("uw/oi_per_strike",     lambda: bridge.fetch_oi_per_strike(ticker)),
            ("uw/nope",              lambda: bridge.fetch_nope(ticker)),
        ]

        for category, fetcher in per_cycle:
            try:
                data = fetcher()
                if data:
                    store.save_mcp_snapshot(category, ticker, _sanitize(data))
                    stats["endpoints_ok"] += 1
                else:
                    stats["endpoints_failed"] += 1
            except Exception as e:
                logger.debug(f"  {ticker} {category}: {e}")
                stats["endpoints_failed"] += 1

        return stats

    def _vault_ticker_daily(self, store: TimescaleDataStore, bridge, ticker: str) -> dict:
        """Vault daily-only data for a single ticker (1x/day guard).

        Historical time-series (gex_aggregate, risk_reversal, short_interest)
        are EXPLODED into ohlcv_bars as per Rule 14, not stored as blobs.
        The raw JSONB snapshot is also saved to mcp_snapshots for full-fidelity access.
        """
        stats = {"daily_ok": 0, "bars_exploded": 0}

        daily_endpoints = [
            ("uw/gex_aggregate",  lambda: bridge.fetch_greek_exposure(ticker),  _explode_gex_to_ohlcv),
            ("uw/risk_reversal",  lambda: bridge.fetch_risk_reversal_skew(ticker), _explode_skew_to_ohlcv),
            ("uw/short_interest", lambda: bridge.fetch_short_interest(ticker), _explode_si_to_ohlcv),
        ]

        for category, fetcher, exploder in daily_endpoints:
            if _already_vaulted_today(store, category, ticker):
                continue
            try:
                data = fetcher()
                if data:
                    # 1. Save raw JSONB snapshot (full fidelity)
                    store.save_mcp_snapshot(category, ticker, _sanitize(data))
                    stats["daily_ok"] += 1

                    # 2. Explode into ohlcv_bars (Rule 14 — time-series for ML/analysis)
                    n_bars = exploder(store, ticker, data)
                    stats["bars_exploded"] += n_bars
                    if n_bars > 0:
                        logger.info(f"  📊 {ticker} {category}: exploded {n_bars} bars to ohlcv_bars")
            except Exception as e:
                logger.debug(f"  {ticker} {category} (daily): {e}")

        return stats

    # ═══════════════════════════════════════════════════════════
    # PUBLIC API — VaultProvider protocol
    # ═══════════════════════════════════════════════════════════

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        """Run full scheduled update cycle.

        SOFT Market hours guard:
            - Market hours (9:30-16:00 ET): full cycle — all endpoints every cycle
            - Extended hours (7:00-20:00 ET): per-cycle + daily endpoints
            - Off-hours: daily endpoints only, 1x/hour cadence
            - Weekends: daily endpoints only, 1x/hour cadence

        This is SOFT — never skips entirely. Vol_stats and short_interest
        remain useful after-hours. Daily endpoints have their own 1x/day
        guard so redundant calls are free.
        """
        bridge = self._get_bridge()
        if not bridge.is_configured():
            logger.warning("UW_API_KEY not configured — skipping UW gamma vault")
            return {"status": "skipped", "reason": "no_api_key"}

        force = kwargs.get("force", False)
        in_market = _is_market_hours()
        in_extended = _is_extended_hours()

        # Soft guard: off-hours runs at 1x/hour cadence (not every 5min cycle)
        if not force and not in_market and not in_extended:
            if not _should_run_off_hours():
                logger.debug("UW Gamma: off-hours, cadence not reached — deferring")
                return {"status": "deferred", "reason": "off_hours_cadence"}

        stats = {
            "status": "ok",
            "market_hours": in_market,
            "extended_hours": in_extended,
            "market": {},
            "tickers_ok": 0,
            "tickers_total": 0,
            "bars_exploded": 0,
            "api_usage": {},
        }

        # 1. Market-level (only during market hours or force)
        if in_market or force:
            stats["market"] = self._vault_market_data(store, bridge)

        # 2. Determine ticker list
        tickers = kwargs.get("tickers")
        if not tickers:
            # Use top impact tickers from the vault (just saved above)
            impact = store.load_mcp_latest("uw/top_impact", "MARKET")
            if impact and isinstance(impact, list):
                tickers = [t["ticker"] for t in impact[:MAX_TICKERS_PER_CYCLE]
                           if isinstance(t, dict) and t.get("ticker")]
            else:
                # Fallback: use core Vault universe
                tickers = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]

        tickers = tickers[:MAX_TICKERS_PER_CYCLE]
        stats["tickers_total"] = len(tickers)

        # 3. Per-ticker data
        for ticker in tickers:
            try:
                # Per-cycle: only during market hours
                if in_market or force:
                    t_stats = self._vault_ticker_data(store, bridge, ticker)
                else:
                    t_stats = {"endpoints_ok": 0, "endpoints_failed": 0}

                # Daily: during market OR extended hours (vol_stats/SI useful after-hours)
                d_stats = self._vault_ticker_daily(store, bridge, ticker)

                if t_stats["endpoints_ok"] > 0 or d_stats.get("daily_ok", 0) > 0:
                    stats["tickers_ok"] += 1
                stats["bars_exploded"] += d_stats.get("bars_exploded", 0)

                logger.info(
                    f"  ⚡ {ticker}: {t_stats['endpoints_ok']}/8 endpoints, "
                    f"{d_stats.get('daily_ok', 0)} daily, "
                    f"{d_stats.get('bars_exploded', 0)} bars exploded"
                )
            except Exception as e:
                logger.warning(f"  {ticker} UW gamma vault failed: {e}")

        stats["api_usage"] = bridge.usage

        mode = "MARKET" if in_market else "EXTENDED" if in_extended else "FORCED"
        logger.info(
            f"⚡ UW Gamma vault [{mode}]: "
            f"{stats['market'].get('sector_tides', 0)} sectors, "
            f"{stats['tickers_ok']}/{stats['tickers_total']} tickers, "
            f"{stats['bars_exploded']} bars exploded, "
            f"API {bridge.usage.get('daily_used', '?')}/{bridge.usage.get('daily_limit', '?')}"
        )

        return stats

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        """Update a SINGLE ticker on-demand (for VRR requests)."""
        bridge = self._get_bridge()
        if not bridge.is_configured():
            return {"status": "skipped", "reason": "no_api_key"}

        t_stats = self._vault_ticker_data(store, bridge, ticker)
        d_stats = self._vault_ticker_daily(store, bridge, ticker)

        return {
            "status": "ok",
            "ticker": ticker,
            **t_stats,
            **d_stats,
        }

    @staticmethod
    def purge_stale_snapshots(store: TimescaleDataStore, ttl_days: int = 30) -> int:
        """Remove UW snapshots older than TTL.

        Per-cycle snapshots (spot_gex, greeks, vol_stats, etc.) accumulate
        ~12K rows/day. After 30 days the historical value is in ohlcv_bars
        (exploded daily data) not in raw JSONB blobs.

        Daily snapshots (gex_aggregate, risk_reversal, short_interest) are
        also cleaned — their data has been exploded to ohlcv_bars.

        Returns number of rows deleted.
        """
        conn = store._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """DELETE FROM market.mcp_snapshots
                       WHERE category LIKE 'uw/%%'
                       AND time < NOW() - INTERVAL '%s days'""",
                    (ttl_days,),
                )
                deleted = cur.rowcount
            conn.commit()
            if deleted > 0:
                logger.info(f"🧹 UW snapshot TTL: purged {deleted} rows older than {ttl_days} days")
            return deleted
        except Exception as e:
            conn.rollback()
            logger.error(f"UW TTL purge failed: {e}")
            return 0
        finally:
            store._put(conn)
