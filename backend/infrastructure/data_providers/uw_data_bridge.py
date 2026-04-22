"""
UW DATA BRIDGE — Direct REST API Client for Unusual Whales
============================================================
Fetches live data from Unusual Whales REST API using UW_API_KEY.

This bypasses the MCP server (which only works inside the IDE)
and lets run_botero.py fetch institutional flow data programmatically.

Endpoints used:
  - /api/stock/{ticker}/options-volume  → Flow alerts per ticker
  - /api/etf/spy                       → SPY flow ticks
  - /api/market/market-tide            → Market-wide tide data

All responses are parsed into the format expected by UWIntelligence.
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
        self._rate_limit_remaining = 100
        self._rate_limit_reset = 0
    
    def _request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make a rate-limited request to the UW API."""
        if not self.api_key:
            logger.warning("UW_API_KEY not configured — returning empty data")
            return None
        
        # Respect rate limits
        if self._rate_limit_remaining < 5:
            wait = max(0, self._rate_limit_reset - time.time())
            if wait > 0:
                logger.info(f"UW rate limit: waiting {wait:.0f}s")
                time.sleep(wait)
        
        url = f"{UW_BASE_URL}{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            
            # Track rate limits from headers
            self._rate_limit_remaining = int(
                resp.headers.get("X-RateLimit-Remaining", 100)
            )
            reset = resp.headers.get("X-RateLimit-Reset")
            if reset:
                self._rate_limit_reset = float(reset)
            
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                logger.warning("UW API rate limited — backing off 60s")
                time.sleep(60)
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
    
    # ═══════════════════════════════════════════════════════════
    # SPY FLOW (for MacroGate)
    # ═══════════════════════════════════════════════════════════
    
    def fetch_spy_flow(self) -> list[dict]:
        """
        Fetch SPY options flow for macro gate analysis.
        Returns list of tick dicts compatible with UWIntelligence.parse_spy_macro_gate().
        """
        data = self._request("/api/stock/SPY/options-volume")
        if not data:
            return []
        
        # Normalize to the format UWIntelligence expects
        ticks = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(ticks, list):
            logger.info(f"🐋 SPY flow: {len(ticks)} ticks fetched")
            return ticks
        return []
    
    # ═══════════════════════════════════════════════════════════
    # FLOW ALERTS (per ticker)
    # ═══════════════════════════════════════════════════════════
    
    def fetch_flow_alerts(self, ticker: str = None, limit: int = 100) -> list[dict]:
        """
        Fetch recent options flow alerts.
        If ticker specified, filters for that ticker.
        Returns list compatible with UWIntelligence.parse_flow_alerts().
        """
        params = {"limit": limit}
        if ticker:
            endpoint = f"/api/stock/{ticker}/options-volume"
        else:
            endpoint = "/api/option-trades/flow"
            
        data = self._request(endpoint, params)
        if not data:
            return []
        
        alerts = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(alerts, list):
            logger.info(f"🐋 Flow alerts: {len(alerts)} fetched" + 
                       (f" for {ticker}" if ticker else ""))
            return alerts
        return []
    
    # ═══════════════════════════════════════════════════════════
    # MARKET TIDE (market-wide direction)
    # ═══════════════════════════════════════════════════════════
    
    def fetch_market_tide(self) -> list[dict]:
        """
        Fetch market-wide tide data (call/put flow balance over time).
        Returns list compatible with UWIntelligence.parse_market_tide().
        """
        data = self._request("/api/market/market-tide")
        if not data:
            return []
        
        tide = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(tide, list):
            logger.info(f"🌊 Market tide: {len(tide)} data points")
            return tide
        return []
    
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
        }
    
    def is_configured(self) -> bool:
        """Check if UW API key is set."""
        return bool(self.api_key) and self.api_key != "your-uw-api-key"
