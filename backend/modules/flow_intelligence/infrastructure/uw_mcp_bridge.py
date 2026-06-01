"""
UW DATA BRIDGE — Direct REST API Client for Unusual Whales
============================================================
Fetches live data from Unusual Whales REST API using UW_API_KEY.

This bypasses the MCP server (which only works inside the IDE)
and lets run_botero.py fetch institutional flow data programmatically.

Plan: Monthly API (20,000 daily / 120 per-minute)

Endpoints used:
  ── FLOW (original) ──
  - /api/stock/{ticker}/options-volume  → Flow alerts per ticker
  - /api/option-trades/flow-alerts      → Market-wide flow alerts
  - /api/market/market-tide             → Market-wide tide data
  - /api/stock/{ticker}/flow-recent     → Per-ticker recent flow
  - /api/stock/{ticker}/net-prem-ticks  → Intraday net premium ticks
  - /api/darkpool/{ticker}              → Dark pool prints
  - /api/market/oi-change               → Market OI change
  - /api/market/economic-calendar       → Economic events

  ── GEX / GREEKS (Phase 1 unlock) ──
  - /api/stock/{ticker}/spot-exposures/strike  → Spot GEX by strike (real dealer data)
  - /api/stock/{ticker}/greeks                 → Per-strike Greeks
  - /api/stock/{ticker}/greek-exposure         → Aggregate GEX (historical)
  - /api/stock/{ticker}/greek-exposure/strike   → GEX by strike
  - /api/stock/{ticker}/greek-exposure/expiry   → GEX by expiry (with DTE)

  ── VOLATILITY / IV (Phase 1 unlock) ──
  - /api/stock/{ticker}/volatility/term-structure  → IV Term Structure
  - /api/stock/{ticker}/volatility/stats           → IV/RV snapshot + IV Rank
  - /api/stock/{ticker}/iv-rank                    → IV Rank (1-year percentile)
  - /api/stock/{ticker}/historical-risk-reversal-skew → Put/Call skew history

  ── OPTIONS STRUCTURE (Phase 1 unlock) ──
  - /api/stock/{ticker}/max-pain         → Max Pain per expiry
  - /api/stock/{ticker}/oi-per-strike    → OI distribution by strike
  - /api/stock/{ticker}/oi-per-expiry    → OI distribution by expiry
  - /api/stock/{ticker}/flow-per-expiry  → Flow aggregated by expiry
  - /api/stock/{ticker}/nope             → Net Options Pricing Effect

  ── MARKET STRUCTURE (Phase 1 unlock) ──
  - /api/market/{sector}/sector-tide     → Per-sector net premium flow
  - /api/market/sector-etfs              → Sector ETF performance
  - /api/market/top-net-impact           → Top net premium tickers

  ── SHORTS (Phase 2) ──
  - /api/shorts/{ticker}/interest-float/v2  → Short interest + days to cover

All responses are parsed into the format expected by downstream adapters.
"""
import logging
import os
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

UW_BASE_URL = "https://api.unusualwhales.com"


class UWDataBridge:
    """
    Direct REST client for Unusual Whales API.
    
    Usage:
        bridge = UWDataBridge()
        spy_ticks = bridge.fetch_spy_flow()
        flow_alerts = bridge.fetch_flow_alerts("NVDA")
        tide = bridge.fetch_market_tide()
        
        # Inject into orchestrator:
        orchestrator.inject_whale_data(
            spy_ticks=spy_ticks,
            flow_alerts=flow_alerts,
            tide_data=tide,
        )
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("UW_API_KEY", "")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        })
        # Rate limit tracking (from UW response headers)
        self._daily_limit = 20000
        self._daily_used = 0
        self._minute_remaining = 120
        self._minute_reset_ms = 0
    
    def _request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make a rate-limited request to the UW API."""
        if not self.api_key:
            logger.warning("UW_API_KEY not configured — returning empty data")
            return None
        
        # Per-minute guard
        if self._minute_remaining < 3:
            wait = max(1, self._minute_reset_ms / 1000)
            logger.info(f"UW rate limit: {self._minute_remaining} remaining, waiting {wait:.0f}s")
            time.sleep(wait)
        
        url = f"{UW_BASE_URL}{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            
            # Track rate limits from UW-specific headers
            self._daily_limit = int(resp.headers.get("x-uw-token-req-limit", self._daily_limit))
            self._daily_used = int(resp.headers.get("x-uw-daily-req-count", self._daily_used))
            self._minute_remaining = int(resp.headers.get("x-uw-req-per-minute-remaining", self._minute_remaining))
            self._minute_reset_ms = int(resp.headers.get("x-uw-req-per-minute-reset", 0))
            
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = max(5, self._minute_reset_ms / 1000)
                logger.warning(f"UW API rate limited — waiting {wait:.0f}s")
                time.sleep(wait)
                return None
            elif resp.status_code == 403:
                logger.warning(f"UW API 403 Forbidden: {endpoint} — not in current plan")
                return None
            else:
                logger.error(f"UW API error {resp.status_code}: {resp.text[:200]}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error(f"UW API timeout: {endpoint}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"UW API request failed: {e}")
            return None
    
    def _extract_data(self, raw: Optional[dict]) -> list | dict:
        """Extract 'data' key from response, handling both list and dict payloads."""
        if not raw:
            return []
        payload = raw.get("data", raw) if isinstance(raw, dict) else raw
        return payload
    
    @property
    def usage(self) -> dict:
        """Current API usage stats."""
        return {
            "daily_limit": self._daily_limit,
            "daily_used": self._daily_used,
            "daily_remaining": self._daily_limit - self._daily_used,
            "daily_pct_used": round(self._daily_used / max(1, self._daily_limit) * 100, 1),
            "minute_remaining": self._minute_remaining,
        }
    
    # ═══════════════════════════════════════════════════════════
    # FLOW — Original endpoints
    # ═══════════════════════════════════════════════════════════
    
    def fetch_spy_flow(self) -> list[dict]:
        """
        Fetch SPY options flow for macro gate analysis.
        Returns list of tick dicts compatible with UWIntelligence.parse_spy_macro_gate().
        """
        data = self._request("/api/stock/SPY/options-volume")
        ticks = self._extract_data(data)
        if isinstance(ticks, list):
            logger.info(f"🐋 SPY flow: {len(ticks)} ticks fetched")
            return ticks
        return []
    
    def fetch_flow_alerts(self, ticker: str = None, limit: int = 100) -> list[dict]:
        """
        Fetch recent options flow alerts.
        If ticker specified, filters for that ticker.
        """
        params = {"limit": limit}
        if ticker:
            endpoint = f"/api/stock/{ticker}/options-volume"
        else:
            endpoint = "/api/option-trades/flow-alerts"
            
        data = self._request(endpoint, params)
        alerts = self._extract_data(data)
        if isinstance(alerts, list):
            logger.info(f"🐋 Flow alerts: {len(alerts)} fetched" + 
                       (f" for {ticker}" if ticker else ""))
            return alerts
        return []
    
    def fetch_market_tide(self) -> list[dict]:
        """
        Fetch market-wide tide data (call/put flow balance over time).
        """
        data = self._request("/api/market/market-tide")
        tide = self._extract_data(data)
        if isinstance(tide, list):
            logger.info(f"🌊 Market tide: {len(tide)} data points")
            return tide
        return []
    
    # ═══════════════════════════════════════════════════════════
    # FLOW — V7 Extended endpoints
    # ═══════════════════════════════════════════════════════════

    def fetch_ticker_flow_recent(self, ticker: str, min_premium: int = 50000) -> list[dict]:
        params = {"min_premium": min_premium}
        data = self._request(f"/api/stock/{ticker}/flow-recent", params)
        alerts = self._extract_data(data)
        return alerts if isinstance(alerts, list) else []

    def fetch_ticker_net_prem_ticks(self, ticker: str, date: str = None) -> list[dict]:
        params = {"date": date} if date else {}
        data = self._request(f"/api/stock/{ticker}/net-prem-ticks", params)
        ticks = self._extract_data(data)
        return ticks if isinstance(ticks, list) else []

    def fetch_darkpool_trades(self, ticker: str) -> list[dict]:
        data = self._request(f"/api/darkpool/{ticker}")
        prints = self._extract_data(data)
        return prints if isinstance(prints, list) else []

    def fetch_oi_change(self) -> list[dict]:
        data = self._request("/api/market/oi-change")
        changes = self._extract_data(data)
        return changes if isinstance(changes, list) else []

    def fetch_economic_calendar(self) -> list[dict]:
        data = self._request("/api/market/economic-calendar")
        events = self._extract_data(data)
        return events if isinstance(events, list) else []

    # ═══════════════════════════════════════════════════════════
    # GEX / GREEKS — Phase 1 Critical Unlock
    # ═══════════════════════════════════════════════════════════

    def fetch_greek_exposure(self, ticker: str) -> list[dict]:
        """Aggregate GEX: call/put gamma, delta, charm, vanna (251-day history)."""
        data = self._request(f"/api/stock/{ticker}/greek-exposure")
        result = self._extract_data(data)
        return result if isinstance(result, list) else [result] if isinstance(result, dict) else []

    def fetch_gex_by_strike(self, ticker: str) -> list[dict]:
        """GEX decomposed by strike: call_gex, put_gex, delta, charm, vanna per strike."""
        data = self._request(f"/api/stock/{ticker}/greek-exposure/strike")
        result = self._extract_data(data)
        return result if isinstance(result, list) else []

    def fetch_gex_by_expiry(self, ticker: str) -> list[dict]:
        """GEX by expiry date with DTE — for Charm/Vanna decay scheduling."""
        data = self._request(f"/api/stock/{ticker}/greek-exposure/expiry")
        result = self._extract_data(data)
        return result if isinstance(result, list) else []

    def fetch_spot_gex(self, ticker: str) -> list[dict]:
        """
        Spot GEX (1-min granularity): gamma/charm/vanna per 1% move.
        Decomposed by: _dir (directional), _oi (open interest), _vol (volume).
        This is the REAL dealer gamma exposure, updated every minute.
        """
        data = self._request(f"/api/stock/{ticker}/spot-exposures")
        result = self._extract_data(data)
        if isinstance(result, list):
            logger.info(f"⚡ Spot GEX {ticker}: {len(result)} 1-min bars")
        return result if isinstance(result, list) else []

    def fetch_spot_gex_by_strike(self, ticker: str) -> list[dict]:
        """
        Spot GEX by strike: 37 fields per near-ATM strike.
        Includes bid/ask/oi/vol decomposition for gamma, delta, charm, vanna.
        """
        data = self._request(f"/api/stock/{ticker}/spot-exposures/strike")
        result = self._extract_data(data)
        if isinstance(result, list):
            logger.info(f"⚡ Spot GEX by strike {ticker}: {len(result)} strikes")
        return result if isinstance(result, list) else []

    def fetch_greeks(self, ticker: str) -> list[dict]:
        """
        Per-strike per-expiry Greeks: delta, gamma, vanna, charm, vega, theta, rho.
        Plus implied volatility per contract.
        """
        data = self._request(f"/api/stock/{ticker}/greeks")
        result = self._extract_data(data)
        return result if isinstance(result, list) else []

    # ═══════════════════════════════════════════════════════════
    # VOLATILITY / IV — Phase 1 Critical Unlock
    # ═══════════════════════════════════════════════════════════

    def fetch_iv_term_structure(self, ticker: str) -> list[dict]:
        """
        IV Term Structure across all expiries.
        Returns: date, ticker, expiry, volatility, dte, implied_move_perc, implied_move
        Contango = normal (short < long). Backwardation = panic (short > long).
        """
        data = self._request(f"/api/stock/{ticker}/volatility/term-structure")
        result = self._extract_data(data)
        if isinstance(result, list):
            logger.info(f"📊 IV Term Structure {ticker}: {len(result)} expiries")
        return result if isinstance(result, list) else []

    def fetch_vol_stats(self, ticker: str) -> dict:
        """
        Volatility stats snapshot: IV, IV High/Low (52w), IV Rank, RV, RV Low/High.
        Returns a single dict.
        """
        data = self._request(f"/api/stock/{ticker}/volatility/stats")
        result = self._extract_data(data)
        return result if isinstance(result, dict) else {}

    def fetch_iv_rank(self, ticker: str) -> list[dict]:
        """IV Rank: close, date, volatility, iv_rank_1y (percentile vs 52-week)."""
        data = self._request(f"/api/stock/{ticker}/iv-rank")
        result = self._extract_data(data)
        return result if isinstance(result, list) else []

    def fetch_realized_vol(self, ticker: str) -> list[dict]:
        """Realized vs Implied volatility history (251 days)."""
        data = self._request(f"/api/stock/{ticker}/volatility/realized")
        result = self._extract_data(data)
        return result if isinstance(result, list) else []

    def fetch_risk_reversal_skew(self, ticker: str) -> list[dict]:
        """Historical 25-delta risk reversal skew (128 days)."""
        data = self._request(f"/api/stock/{ticker}/historical-risk-reversal-skew")
        result = self._extract_data(data)
        return result if isinstance(result, list) else []

    # ═══════════════════════════════════════════════════════════
    # OPTIONS STRUCTURE — Phase 1 Critical Unlock
    # ═══════════════════════════════════════════════════════════

    def fetch_max_pain(self, ticker: str) -> list[dict]:
        """
        Max Pain per expiry: close, open, expiry, max_pain, next_upper/lower_strike.
        Magnetic price level from options market structure.
        """
        data = self._request(f"/api/stock/{ticker}/max-pain")
        result = self._extract_data(data)
        if isinstance(result, list):
            logger.info(f"🧲 Max Pain {ticker}: {len(result)} expiries")
        return result if isinstance(result, list) else []

    def fetch_oi_per_strike(self, ticker: str) -> list[dict]:
        """OI distribution by strike: date, strike, call_oi, put_oi."""
        data = self._request(f"/api/stock/{ticker}/oi-per-strike")
        result = self._extract_data(data)
        return result if isinstance(result, list) else []

    def fetch_oi_per_expiry(self, ticker: str) -> list[dict]:
        """OI distribution by expiry: date, expiry, call_oi, put_oi."""
        data = self._request(f"/api/stock/{ticker}/oi-per-expiry")
        result = self._extract_data(data)
        return result if isinstance(result, list) else []

    def fetch_flow_per_expiry(self, ticker: str) -> list[dict]:
        """Flow per expiry: volume, premium, ask/bid side breakdown per expiry."""
        data = self._request(f"/api/stock/{ticker}/flow-per-expiry")
        result = self._extract_data(data)
        return result if isinstance(result, list) else []

    def fetch_nope(self, ticker: str) -> list[dict]:
        """
        Net Options Pricing Effect: intraday NOPE score.
        nope > 0 = delta-driven buying. nope < 0 = delta-driven selling.
        """
        data = self._request(f"/api/stock/{ticker}/nope")
        result = self._extract_data(data)
        return result if isinstance(result, list) else []

    # ═══════════════════════════════════════════════════════════
    # MARKET STRUCTURE — Phase 1 Unlock
    # ═══════════════════════════════════════════════════════════

    def fetch_sector_tide(self, sector: str) -> list[dict]:
        """
        Per-sector net premium flow (intraday bars).
        Sectors: Technology, Healthcare, Financial, Consumer Cyclical, 
                 Industrials, Energy, etc.
        """
        data = self._request(f"/api/market/{sector}/sector-tide")
        result = self._extract_data(data)
        if isinstance(result, list):
            logger.info(f"🌊 Sector Tide {sector}: {len(result)} bars")
        return result if isinstance(result, list) else []

    def fetch_sector_etfs(self) -> list[dict]:
        """
        Sector ETF performance: all sectors with price, volume, options flow.
        Returns 12 sector ETFs (SPY, XLK, XLV, XLF, etc.)
        """
        data = self._request("/api/market/sector-etfs")
        result = self._extract_data(data)
        return result if isinstance(result, list) else []

    def fetch_top_net_impact(self) -> list[dict]:
        """Top 20 tickers by net premium impact (absolute $ flow direction)."""
        data = self._request("/api/market/top-net-impact")
        result = self._extract_data(data)
        return result if isinstance(result, list) else []

    def fetch_etf_tide(self, ticker: str) -> list[dict]:
        """Per-ETF net premium flow with underlying price."""
        data = self._request(f"/api/market/{ticker}/etf-tide")
        result = self._extract_data(data)
        return result if isinstance(result, list) else []

    # ═══════════════════════════════════════════════════════════
    # SHORTS — Phase 2
    # ═══════════════════════════════════════════════════════════

    def fetch_short_interest(self, ticker: str) -> list[dict]:
        """
        Short interest + float data: SI%, days_to_cover, fee_rate, total_float.
        118+ data points (biweekly FINRA reports).
        """
        data = self._request(f"/api/shorts/{ticker}/interest-float/v2")
        result = self._extract_data(data)
        return result if isinstance(result, list) else []

    # ═══════════════════════════════════════════════════════════
    # CONVENIENCE: Fetch all for orchestrator injection
    # ═══════════════════════════════════════════════════════════
    
    def fetch_all(self) -> dict:
        """
        Fetch all UW data needed for the EntryIntelligenceHub.
        
        Returns:
            Dict with spy_ticks, flow_alerts, tide_data ready for
            orchestrator.inject_whale_data(**result)
        """
        spy_ticks = self.fetch_spy_flow()
        flow_alerts = self.fetch_flow_alerts()
        tide_data = self.fetch_market_tide()
        
        return {
            "spy_ticks": spy_ticks,
            "flow_alerts": flow_alerts,
            "tide_data": tide_data,
            # V7: Pass flow_alerts as recent_flow for FlowPersistenceAnalyzer.
            # Per-ticker filtering happens downstream.
            "recent_flow": flow_alerts,
            "darkpool_prints": [],  # Fetched per-ticker during evaluate()
        }
    
    def fetch_gamma_suite(self, ticker: str) -> dict:
        """
        Fetch the full gamma/greeks/IV suite for a ticker.
        Used by the options_gamma module to replace yfinance estimation.
        
        Returns dict with all gamma-related data keyed by type.
        """
        return {
            "spot_gex": self.fetch_spot_gex_by_strike(ticker),
            "greeks": self.fetch_greeks(ticker),
            "gex_by_strike": self.fetch_gex_by_strike(ticker),
            "gex_by_expiry": self.fetch_gex_by_expiry(ticker),
            "max_pain": self.fetch_max_pain(ticker),
            "oi_per_strike": self.fetch_oi_per_strike(ticker),
            "vol_stats": self.fetch_vol_stats(ticker),
            "iv_term_structure": self.fetch_iv_term_structure(ticker),
        }
    
    def is_configured(self) -> bool:
        """Check if UW API key is set."""
        return bool(self.api_key) and self.api_key != "your-uw-api-key"
