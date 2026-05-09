"""
GuruFocus MCP Bridge — Direct API Access for Daemon Ingestion
================================================================
Infrastructure adapter: calls GuruFocus REST API directly to populate
the Neon vault with fundamental screening data.

This is a DAEMON-LEVEL adapter (used by data_vault_daemon.py and
quality_daemon.py). Module code reads from the vault, not from here.

API: https://api.gurufocus.com/public/user/{endpoint}?token={token}
Auth: GURUFOCUS_API_TOKEN env var.
"""
import logging
import os
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.gurufocus.com/public/user"
RATE_LIMIT_DELAY = 1.5  # seconds between requests (GuruFocus rate limit)


class GuruFocusMCPBridge:
    """Direct GuruFocus API bridge for vault ingestion."""

    def __init__(self, token: str = ""):
        self._token = token or os.getenv("GURUFOCUS_API_TOKEN", "")
        if not self._token:
            logger.warning("GuruFocusMCPBridge: GURUFOCUS_API_TOKEN not set")
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    def _get(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make a GET request to the GuruFocus API."""
        if not self._token:
            return None
        url = f"{BASE_URL}/{self._token}/{endpoint}"
        try:
            resp = self._session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            time.sleep(RATE_LIMIT_DELAY)
            return data
        except requests.RequestException as e:
            logger.warning(f"GuruFocus API error ({endpoint}): {e}")
            return None

    # ── Stock-level endpoints ─────────────────────────────

    def fetch_summary(self, ticker: str) -> Optional[dict]:
        """Fetch comprehensive financial summary (GF Score, GF Value, sector, etc)."""
        return self._get(f"stock/{ticker}/summary")

    def fetch_keyratios(self, ticker: str) -> Optional[dict]:
        """Fetch key ratios (Piotroski, Altman Z, ROIC, margins, growth)."""
        return self._get(f"stock/{ticker}/keyratios")

    def fetch_financials(self, ticker: str, period: str = "annual") -> Optional[dict]:
        """Fetch financial statements (income, balance, cash flow)."""
        return self._get(f"stock/{ticker}/financials", {"type": period})

    def fetch_gurus(self, ticker: str) -> Optional[dict]:
        """Fetch guru/institutional holdings for a stock."""
        return self._get(f"stock/{ticker}/guru")

    def fetch_analyst_estimates(self, ticker: str) -> Optional[dict]:
        """Fetch analyst EPS/revenue estimates."""
        return self._get(f"stock/{ticker}/analyst_estimate")

    def fetch_operating_data(self, ticker: str) -> Optional[dict]:
        """Fetch operating/segment data (SaaS KPIs)."""
        return self._get(f"stock/{ticker}/operating_data")

    def fetch_segments(self, ticker: str) -> Optional[dict]:
        """Fetch revenue segments (business + geographic)."""
        return self._get(f"stock/{ticker}/segment")

    def fetch_indicator(self, ticker: str, indicator: str) -> Optional[dict]:
        """Fetch a specific indicator (e.g. 'wacc')."""
        return self._get(f"stock/{ticker}/indicator/{indicator}")

    def fetch_ownership(self, ticker: str) -> Optional[dict]:
        """Fetch institutional ownership data."""
        return self._get(f"stock/{ticker}/ownership")

    # ── Market-wide endpoints ─────────────────────────────

    def fetch_insider_trades(self, ticker: str) -> Optional[dict]:
        """Fetch insider transactions for a specific stock.

        Returns dict keyed by ticker with list of insider trades.
        Each trade: {position, date, type (P/S), trans_share, price, insider, ...}

        Note: 'insider/cluster' and 'insider/ceo' are WEB-ONLY features,
        NOT available via the REST API. We use per-stock insider data
        and detect clusters computationally.
        """
        return self._get(f"stock/{ticker}/insider")

    def fetch_guru_realtime_picks(self, page: int = 1) -> Optional[dict]:
        """Fetch real-time guru trading activity (Form 4)."""
        return self._get("guru_realtime_picks", {"page": page})

    # ── Composite: Quality Screening ──────────────────────

    def fetch_quality_screening(self, ticker: str) -> Optional[dict]:
        """
        Fetch the data needed for quality screening from the summary endpoint.
        The summary contains general, ratio, company_data — enough for screening.

        This is the method that data_vault_daemon should call instead of
        the non-existent get_quality_summary().
        """
        summary = self.fetch_summary(ticker)
        if not summary:
            return None

        result = {
            "ticker": ticker,
            "source": "gurufocus_api",
        }

        s = summary.get("summary", summary)
        general = s.get("general", {})
        ratio = s.get("ratio", {})
        company_data = s.get("company_data", {})

        # Core identification
        result["company"] = general.get("company", "")
        result["sector"] = general.get("sector", "")
        result["industry"] = general.get("group", "")
        result["market_cap"] = company_data.get("mktcap", 0)
        result["price"] = self._safe_float(general.get("price"))
        result["gf_valuation"] = general.get("gf_valuation", "")
        result["risk_assessment"] = general.get("risk_assessment", "")

        # GF scores — in general section
        result["gf_score"] = self._safe_float(general.get("gf_score"))
        result["rank_financial_strength"] = self._safe_float(general.get("rank_financial_strength"))
        result["rank_profitability"] = self._safe_float(general.get("rank_profitability"))
        result["rank_growth"] = self._safe_float(general.get("rank_growth"))
        result["rank_momentum"] = self._safe_float(general.get("rank_momentum"))
        result["rank_gf_value"] = self._safe_float(general.get("rank_gf_value"))

        # Quality scores — in ratio section
        result["piotroski_f_score"] = self._val(ratio, "F-Score") or self._val(ratio, "fscore")
        result["altman_z_score"] = self._val(ratio, "zscore")
        result["beneish_m_score"] = self._val(ratio, "mscore")

        # Profitability
        result["roic"] = self._safe_float(ratio.get("ROIC (%)"))
        result["roe"] = self._safe_float(ratio.get("ROE (%)"))
        result["roa"] = self._safe_float(ratio.get("ROA (%)"))
        result["gross_margin"] = self._safe_float(ratio.get("Gross Margin (%)"))
        result["operating_margin"] = self._safe_float(ratio.get("Operating margin (%)"))
        result["net_margin"] = self._safe_float(ratio.get("Net-margin (%)"))

        # Valuation
        result["pe_ratio"] = self._safe_float(ratio.get("P/E(ttm)"))
        result["pb_ratio"] = self._safe_float(ratio.get("P/B"))
        result["ps_ratio"] = self._safe_float(ratio.get("P/S"))
        result["peg_ratio"] = self._safe_float(ratio.get("PEG"))
        result["price_to_gf_value"] = self._safe_float(ratio.get("Price-to-GF-Value"))
        result["ev_to_ebitda"] = self._safe_float(ratio.get("EV-to-EBITDA"))

        # Debt / Solvency
        result["debt_to_equity"] = self._safe_float(ratio.get("Debt-to-Equity"))
        result["current_ratio"] = self._safe_float(ratio.get("Current Ratio"))
        result["cash_to_debt"] = self._safe_float(ratio.get("Cash to Debt"))

        # Growth
        result["revenue_growth"] = self._safe_float(ratio.get("Revenue Growth (%)"))
        result["eps_growth"] = self._safe_float(ratio.get("EPS Growth (%)"))
        result["fcf_growth"] = self._safe_float(ratio.get("FCF Growth (%)"))

        # Guru interest
        result["guru_buy_pct"] = self._safe_float(general.get("percentage_of_premiumplus_guru_buys"))
        result["guru_hold_pct"] = self._safe_float(general.get("percentage_of_premiumplus_guru_holds"))

        # Warning signs
        good = company_data.get("good_sign", [])
        warn = company_data.get("warning_sign", [])
        result["good_signs"] = len(good) if isinstance(good, list) else 0
        result["warning_signs"] = len(warn) if isinstance(warn, list) else 0

        return result

    @staticmethod
    def _val(ratio: dict, key: str):
        """Extract value from complex ratio entries like {value: X, status: N}."""
        v = ratio.get(key)
        if isinstance(v, dict):
            return v.get("value", 0)
        return v if v is not None else 0

    @staticmethod
    def _safe_float(v) -> float:
        """Safely convert to float, handling None and complex types."""
        if v is None:
            return 0.0
        if isinstance(v, dict):
            return float(v.get("value", 0) or 0)
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0
