"""
UW Gamma Adapter — Vault-First Options Data from Unusual Whales
==================================================================
Reads pre-fetched UW options data exclusively from the Vault.
NEVER calls UW API directly (Rule 13: Vault-First data access).

Replaces YFinanceOptionsAdapter as the PRIMARY source for:
- Spot GEX (real dealer gamma, not Black-Scholes estimation)
- IV Term Structure (market's own vol surface)
- Vol Stats (IV Rank, variance risk premium)
- Max Pain (dealer-calculated)
- OI per Strike (for wall detection)

Falls back to YFinanceOptionsAdapter if Vault data is missing/stale.

Architecture:
    UW API → UWDataBridge → UWGammaProvider (daemon) → Vault
                                                        ↓
    Domain ← OptionsAwareness ← UWGammaAdapter ← Vault (reads)
"""
import logging
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta
from typing import Optional

import pandas as pd

from backend.modules.options_gamma.domain.ports.options_data_port import OptionsDataPort

logger = logging.getLogger(__name__)

# Maximum age before considering vault data stale
STALE_THRESHOLD = timedelta(hours=4)


@dataclass
class SpotGEXSnapshot:
    """Parsed Spot GEX data from UW — real dealer gamma exposure."""
    ticker: str
    timestamp: str = ""
    # Net exposures per 1% move
    gamma_per_pct_oi: float = 0.0
    charm_per_pct_oi: float = 0.0
    vanna_per_pct_oi: float = 0.0
    # Directional (from flow)
    gamma_per_pct_dir: float = 0.0
    charm_per_pct_dir: float = 0.0
    vanna_per_pct_dir: float = 0.0
    # Per-strike breakdown
    strikes: list = None
    n_strikes: int = 0

    def __post_init__(self):
        if self.strikes is None:
            self.strikes = []


@dataclass
class IVTermStructure:
    """Parsed IV Term Structure from UW."""
    ticker: str
    timestamp: str = ""
    expiries: list = None  # [{expiry, volatility, dte, implied_move_perc}]
    is_backwardation: bool = False  # Short > Long = panic
    ultra_front_iv: float = 0.0  # 0DTE IV — most informative for intraday gamma
    front_iv: float = 0.0        # Nearest DTE > 0
    back_iv: float = 0.0         # Furthest DTE
    term_spread: float = 0.0     # back_iv - front_iv (negative = backwardation)

    def __post_init__(self):
        if self.expiries is None:
            self.expiries = []


@dataclass
class VolStats:
    """Volatility statistics snapshot from UW."""
    ticker: str
    iv: float = 0.0
    iv_high: float = 0.0
    iv_low: float = 0.0
    iv_rank: float = 0.0  # Percentile vs 52-week (0-100)
    rv: float = 0.0
    rv_high: float = 0.0
    rv_low: float = 0.0
    variance_risk_premium: float = 0.0  # IV - RV (>0 = overpriced protection)


# ═══════════════════════════════════════════════════════════
# TYPE CASTING — Project standard (matches GuruFocus/FRED adapters)
# ═══════════════════════════════════════════════════════════

def _safe_float(val, default: float = 0.0) -> float:
    """Safely cast any value to float.

    Handles str, None, "", dict, and non-numeric strings from UW API.
    All UW numeric fields arrive as strings (e.g. "17289266.66").
    Project standard: domain entities use float=0.0 defaults.
    """
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
    if isinstance(val, dict):
        inner = val.get("value", default)
        return _safe_float(inner, default)
    return default


def _safe_int(val, default: int = 0) -> int:
    """Safely cast any value to int.

    Used for share counts, OI, volume — discrete quantities.
    Note: "stock float" (shares available for public trading) is int.
    """
    if val is None:
        return default
    if isinstance(val, int):
        return val
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


class UWGammaAdapter(OptionsDataPort):
    """Vault-first options adapter using Unusual Whales data.

    Reads from market.mcp_snapshots categories:
        uw/spot_gex, uw/greeks, uw/iv_term_structure,
        uw/vol_stats, uw/max_pain, uw/oi_per_strike

    Type casting standard (aligned with GuruFocus/FRED adapters):
        - Prices, ratios, percentages, exposures → float (via _safe_float)
        - Counts, shares, OI, volume → int (via _safe_int)
        - Dates → str in YYYY-MM-DD format
        - Timestamps → str in ISO 8601 format
    """

    def __init__(self):
        self._store = None

    def _get_store(self):
        """Lazy store initialization."""
        if self._store is None:
            from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
            self._store = TimescaleDataStore()
        return self._store

    def _load_fresh(self, category: str, ticker: str) -> Optional[dict | list]:
        """Load from vault, return None if missing or stale."""
        store = self._get_store()
        data, age = store.load_mcp_latest_with_age(category, ticker)
        if data is None:
            return None
        if age and age > STALE_THRESHOLD:
            logger.debug(f"UW Vault {category}/{ticker} stale ({age}) — will try fallback")
            return None
        return data

    # ═══════════════════════════════════════════════════════════
    # OptionsDataPort implementation
    # ═══════════════════════════════════════════════════════════

    def get_options_chain(self, symbol: str, expiration: Optional[str] = None) -> dict:
        """
        Rebuild options chain from UW vault data.
        Combines uw/greeks + uw/max_pain + uw/oi_per_strike.
        Falls back to YFinanceOptionsAdapter if vault data unavailable.
        """
        greeks = self._load_fresh("uw/greeks", symbol)
        if not greeks or not isinstance(greeks, list) or len(greeks) == 0:
            return self._yfinance_fallback().get_options_chain(symbol, expiration)

        # Get current price from vault OHLCV bars
        current_price = self.get_current_price(symbol)

        # Build calls and puts DataFrames from UW Greeks
        calls_data = []
        puts_data = []

        for row in greeks:
            exp = row.get("expiry", "")
            if expiration and exp != expiration:
                continue

            strike = _safe_float(row.get("strike"))
            if strike <= 0:
                continue

            # Call side
            call_iv = _safe_float(row.get("call_volatility"))
            if call_iv > 0:
                calls_data.append({
                    "strike": strike,
                    "impliedVolatility": call_iv,
                    "openInterest": 0,  # Filled from OI data below
                    "volume": 0,
                    "delta": _safe_float(row.get("call_delta")),
                    "gamma": _safe_float(row.get("call_gamma")),
                    "theta": _safe_float(row.get("call_theta")),
                    "vega": _safe_float(row.get("call_vega")),
                    "rho": _safe_float(row.get("call_rho")),
                    "expiration": exp,
                })

            # Put side
            put_iv = _safe_float(row.get("put_volatility"))
            if put_iv > 0:
                puts_data.append({
                    "strike": strike,
                    "impliedVolatility": put_iv,
                    "openInterest": 0,
                    "volume": 0,
                    "delta": _safe_float(row.get("put_delta")),
                    "gamma": _safe_float(row.get("put_gamma")),
                    "theta": _safe_float(row.get("put_theta")),
                    "vega": _safe_float(row.get("put_vega")),
                    "rho": _safe_float(row.get("put_rho")),
                    "expiration": exp,
                })

        # Enrich with OI data
        oi_data = self._load_fresh("uw/oi_per_strike", symbol)
        if oi_data and isinstance(oi_data, list):
            oi_map = {_safe_float(r.get("strike")): r for r in oi_data}
            for c in calls_data:
                oi_row = oi_map.get(c["strike"], {})
                c["openInterest"] = _safe_int(oi_row.get("call_oi"))
            for p in puts_data:
                oi_row = oi_map.get(p["strike"], {})
                p["openInterest"] = _safe_int(oi_row.get("put_oi"))

        if not calls_data and not puts_data:
            return self._yfinance_fallback().get_options_chain(symbol, expiration)

        # Determine expiration from data
        all_exps = sorted(set(
            c.get("expiration", "") for c in calls_data if c.get("expiration")
        ))
        exp = expiration or (all_exps[0] if all_exps else "")

        return {
            "current_price": current_price,
            "expiration": exp,
            "calls": pd.DataFrame(calls_data),
            "puts": pd.DataFrame(puts_data),
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "uw_vault",
        }

    def get_expirations(self, symbol: str) -> list[str]:
        """Get available expiration dates from UW greeks data."""
        greeks = self._load_fresh("uw/greeks", symbol)
        if greeks and isinstance(greeks, list):
            exps = sorted(set(r.get("expiry", "") for r in greeks if r.get("expiry")))
            if exps:
                return exps
        return self._yfinance_fallback().get_expirations(symbol)

    def get_nearest_expiration(self, symbol: str) -> Optional[str]:
        """Get nearest expiration date."""
        exps = self.get_expirations(symbol)
        return exps[0] if exps else None

    def get_current_price(self, symbol: str) -> float:
        """Get current price from vault OHLCV bars."""
        try:
            store = self._get_store()
            df = store.load_bars(symbol, "1d")
            if not df.empty:
                return float(df["close"].iloc[-1])
        except Exception:
            pass
        return self._yfinance_fallback().get_current_price(symbol)

    # ═══════════════════════════════════════════════════════════
    # UW-SPECIFIC: Data not available via OptionsDataPort
    # ═══════════════════════════════════════════════════════════

    def get_spot_gex(self, symbol: str) -> SpotGEXSnapshot:
        """
        Read real Spot GEX from vault (dealer-calculated, not BS estimation).
        This is the PRIMARY source — replaces yfinance chain estimation.
        """
        data = self._load_fresh("uw/spot_gex", symbol)
        if not data or not isinstance(data, list):
            return SpotGEXSnapshot(ticker=symbol)

        snapshot = SpotGEXSnapshot(
            ticker=symbol,
            n_strikes=len(data),
            strikes=data,
        )

        # Aggregate net gamma across all strikes
        for strike in data:
            snapshot.gamma_per_pct_oi += _safe_float(strike.get("call_gamma_oi"))
            snapshot.gamma_per_pct_oi -= _safe_float(strike.get("put_gamma_oi"))
            snapshot.charm_per_pct_oi += _safe_float(strike.get("call_charm_oi"))
            snapshot.charm_per_pct_oi -= _safe_float(strike.get("put_charm_oi"))
            snapshot.vanna_per_pct_oi += _safe_float(strike.get("call_vanna_oi"))
            snapshot.vanna_per_pct_oi -= _safe_float(strike.get("put_vanna_oi"))

        return snapshot

    def get_iv_term_structure(self, symbol: str) -> IVTermStructure:
        """Read IV Term Structure from vault."""
        data = self._load_fresh("uw/iv_term_structure", symbol)
        if not data or not isinstance(data, list):
            return IVTermStructure(ticker=symbol)

        # Sort by DTE
        sorted_exp = sorted(data, key=lambda x: _safe_int(x.get("dte")))

        # 0DTE = ultra_front (most informative for Karsan's intraday gamma)
        dte0_entries = [e for e in sorted_exp if _safe_int(e.get("dte")) == 0]
        ultra_front_iv = _safe_float(dte0_entries[0].get("volatility")) if dte0_entries else 0.0

        # Front = shortest DTE > 0, Back = longest DTE
        front_entries = [e for e in sorted_exp if _safe_int(e.get("dte")) > 0]
        front_iv = _safe_float(front_entries[0].get("volatility")) if front_entries else 0.0
        back_iv = _safe_float(sorted_exp[-1].get("volatility")) if sorted_exp else 0.0

        return IVTermStructure(
            ticker=symbol,
            expiries=[{
                "expiry": e.get("expiry", ""),
                "volatility": _safe_float(e.get("volatility")),
                "dte": _safe_int(e.get("dte")),
                "implied_move_perc": _safe_float(e.get("implied_move_perc")),
            } for e in sorted_exp],
            is_backwardation=front_iv > back_iv and front_iv > 0 and back_iv > 0,
            ultra_front_iv=ultra_front_iv,
            front_iv=front_iv,
            back_iv=back_iv,
            term_spread=back_iv - front_iv,
        )

    def get_vol_stats(self, symbol: str) -> VolStats:
        """Read volatility stats snapshot from vault."""
        data = self._load_fresh("uw/vol_stats", symbol)
        if not data or not isinstance(data, dict):
            return VolStats(ticker=symbol)

        iv = _safe_float(data.get("iv"))
        rv = _safe_float(data.get("rv"))

        return VolStats(
            ticker=symbol,
            iv=iv,
            iv_high=_safe_float(data.get("iv_high")),
            iv_low=_safe_float(data.get("iv_low")),
            iv_rank=_safe_float(data.get("iv_rank")),
            rv=rv,
            rv_high=_safe_float(data.get("rv_high")),
            rv_low=_safe_float(data.get("rv_low")),
            variance_risk_premium=iv - rv,
        )

    def get_max_pain_by_expiry(self, symbol: str) -> list[dict]:
        """Read Max Pain across all expiries from vault."""
        data = self._load_fresh("uw/max_pain", symbol)
        if not data or not isinstance(data, list):
            return []
        return [{
            "expiry": e.get("expiry", ""),
            "max_pain": _safe_float(e.get("max_pain")),
            "close": _safe_float(e.get("close")),
            "distance_pct": (
                (_safe_float(e.get("close")) - _safe_float(e.get("max_pain")))
                / _safe_float(e.get("max_pain"), default=1.0) * 100
                if _safe_float(e.get("max_pain")) > 0 else 0.0
            ),
        } for e in data]

    def get_nope(self, symbol: str) -> list[dict]:
        """Read NOPE (Net Options Pricing Effect) intraday bars from vault."""
        data = self._load_fresh("uw/nope", symbol)
        if not data or not isinstance(data, list):
            return []
        return data

    # ═══════════════════════════════════════════════════════════
    # FALLBACK
    # ═══════════════════════════════════════════════════════════

    def _yfinance_fallback(self) -> OptionsDataPort:
        """Lazy-load YFinanceOptionsAdapter as fallback."""
        from backend.modules.options_gamma.infrastructure.yfinance_adapter import YFinanceOptionsAdapter
        return YFinanceOptionsAdapter()

    def close(self):
        """Release vault connection."""
        if self._store:
            self._store.close()
            self._store = None
