"""
GuruFocus Fundamental Data Adapter
====================================
Implements FundamentalDataPort by wrapping GuruFocusIntelligence (parser)
with actual MCP data fetching via the GuruFocus cache layer.

This bridges the architectural gap:
  - FundamentalDataPort expects: get_X(ticker) → fetches + returns structured data
  - GuruFocusIntelligence expects: parse_X(ticker, mcp_response) → parse-only

This adapter fetches raw data from the GuruFocus cache/API, then delegates
parsing to GuruFocusIntelligence.
"""
import logging
from typing import Optional

from backend.modules.portfolio_management.domain.ports.fundamental_data_port import FundamentalDataPort
from backend.modules.portfolio_management.infrastructure.gurufocus_adapter import GuruFocusIntelligence

logger = logging.getLogger(__name__)


class GuruFocusFundamentalAdapter(FundamentalDataPort):
    """
    Concrete implementation of FundamentalDataPort using GuruFocus data.

    Wraps the existing GuruFocusIntelligence parser and adds the fetch layer
    that the port contract demands. Data is loaded from the local diskcache
    or (when available) via live MCP tool calls.
    """

    def __init__(self, cache_path: str = ""):
        self._parser = GuruFocusIntelligence()
        self._cache_path = cache_path
        self._db_conn = None
        self._initialized = False

    def _ensure_db(self):
        """Lazy-open sqlite3 connection to the GuruFocus diskcache.db."""
        if self._initialized:
            return
        self._initialized = True
        try:
            import os
            import sqlite3
            self._cache_dir = self._cache_path or os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
                ".cache", "gurufocus"
            )
            db_file = os.path.join(self._cache_dir, "cache.db")
            if os.path.exists(db_file):
                self._db_conn = sqlite3.connect(db_file)
                logger.info(f"GuruFocusFundamentalAdapter: cache loaded from {db_file}")
            else:
                logger.warning(f"GuruFocusFundamentalAdapter: no cache.db at {db_file}")
        except Exception as e:
            logger.warning(f"GuruFocusFundamentalAdapter: cache init failed: {e}")

    def _fetch_cached(self, key: str, default=None):
        """Fetch from diskcache sqlite3 by key.

        diskcache stores small values inline (value column) and large values
        as pickled files on disk (value=NULL, filename column has relative path).
        This method handles both modes.
        """
        self._ensure_db()
        if self._db_conn is None:
            return default
        try:
            import os
            import pickle
            cursor = self._db_conn.cursor()
            cursor.execute("SELECT value, filename FROM Cache WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row is None:
                return default
            value_blob, filename = row
            # Mode 1: inline blob in SQLite
            if value_blob is not None:
                return pickle.loads(value_blob)
            # Mode 2: large value stored as file on disk
            if filename:
                file_path = os.path.join(self._cache_dir, filename)
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        return pickle.loads(f.read())
                logger.debug(f"Cache file missing for {key}: {file_path}")
            return default
        except Exception as e:
            logger.debug(f"Cache miss for {key}: {e}")
            return default

    # ── FundamentalDataPort implementation ──────────────────────

    def get_guru_analysis(self, ticker: str) -> dict:
        raw = self._fetch_cached(f"qgarp:{ticker}", {})
        if raw:
            scorecard = self._parser.parse_qgarp_scorecard(ticker, raw)
            return {"scorecard": scorecard, "raw": raw}
        return {}

    def get_insider_activity(self, ticker: str) -> dict:
        raw = self._fetch_cached(f"insider:{ticker}", {})
        if raw:
            conviction = self._parser.parse_insider_conviction(ticker, raw)
            return {"conviction": conviction}
        return {}

    def get_earnings_calendar(self, ticker: str) -> Optional[dict]:
        return self._fetch_cached(f"earnings:{ticker}", None)

    def get_financial_summary(self, ticker: str) -> dict:
        raw = self._fetch_cached(f"summary:{ticker}", None)
        if not raw:
            return {}
        # Unwrap: cached data is {summary: {ratio: {...}, general: {...}}}
        summary = raw.get("summary", raw)
        ratio = summary.get("ratio", {})

        def _val(key):
            """Extract 'value' from complex ratio entries like {value: X, status: N}."""
            v = ratio.get(key)
            if isinstance(v, dict):
                return v.get("value", 0)
            return v if v is not None else 0

        # Map to the flat keys parse_quality_metrics expects
        flat = {
            "piotroski_f_score": _val("fscore"),
            "altman_z_score": _val("zscore"),
            "beneish_m_score": _val("mscore"),
            "roic": _val("ROIC (%)"),
            "roe": _val("ROE (%)"),
            "gross_margin": _val("Gross Margin (%)"),
            "operating_margin": _val("Operating margin (%)"),
            "debt_to_equity": _val("Debt-to-Equity"),
            "current_ratio": _val("Current Ratio"),
        }
        return self._parser.parse_quality_metrics(ticker, flat)

    def get_financial_statements(self, ticker: str, period_type: str = "annual") -> dict:
        raw = self._fetch_cached(f"financials:{ticker}:{period_type}", None)
        if raw:
            snapshots = self._parser.parse_financial_statements(ticker, raw)
            return {"snapshots": snapshots}
        return {"snapshots": []}

    def get_growth_profile(self, ticker: str) -> dict:
        raw = self._fetch_cached(f"key_ratios:{ticker}", None)
        if raw:
            profile = self._parser.parse_growth_profile(ticker, raw)
            return {
                "revenue_cagr": profile.revenue_cagr,
                "eps_cagr": profile.eps_cagr,
                "fcf_cagr": profile.fcf_cagr,
            }
        return {}

    def get_operating_kpis(self, ticker: str) -> dict:
        raw = self._fetch_cached(f"operating_data:{ticker}", None)
        if raw:
            kpis = self._parser.parse_operating_kpis(ticker, raw)
            return kpis.kpis
        return {}

    def get_segment_breakdown(self, ticker: str) -> dict:
        raw = self._fetch_cached(f"segments:{ticker}", None)
        if raw:
            breakdown = self._parser.parse_segment_breakdown(ticker, raw)
            return {
                "business_segments": breakdown.business_segments,
                "geographic_segments": breakdown.geographic_segments,
            }
        return {}

    def get_wacc(self, ticker: str) -> float:
        raw = self._fetch_cached(f"indicator_value:{ticker}:wacc", None)
        if raw is not None:
            return self._parser.parse_wacc(ticker, raw)
        return 0.0

    def get_full_qgarp(self, ticker: str) -> dict:
        raw = self._fetch_cached(f"qgarp:{ticker}", {})
        if raw:
            analysis = self._parser.parse_full_qgarp(ticker, raw)
            return {
                "intrinsic_value": analysis.intrinsic_value,
                "margin_of_safety": analysis.margin_of_safety,
                "moat_areas": analysis.moat_areas,
                "scorecard": analysis.scorecard,
            }
        return {}

    def get_warning_signs(self, ticker: str) -> dict:
        raw = self._fetch_cached(f"summary:{ticker}", None)
        if raw:
            warnings = self._parser.parse_warning_signs(ticker, raw)
            return {
                "num_good_signs": warnings.num_good_signs,
                "num_warnings_medium": warnings.num_warnings_medium,
                "num_warnings_severe": warnings.num_warnings_severe,
                "net_signal_score": warnings.net_signal_score,
            }
        return {}
