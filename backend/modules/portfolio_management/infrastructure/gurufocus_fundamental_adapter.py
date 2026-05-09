"""
GuruFocus Fundamental Data Adapter — Vault-First
===================================================
Implements FundamentalDataPort by reading pre-vaulted GuruFocus data
from Neon PostgreSQL (market.mcp_snapshots, category='fundamental/screening').

This is a MODULE-LEVEL adapter — it reads from the vault only.
The daemon (data_vault_daemon.py) writes to the vault via GuruFocusMCPBridge.

Architecture: Module Infrastructure → reads vault → returns domain entities.
"""
import logging
from typing import Optional

from backend.modules.portfolio_management.domain.ports.fundamental_data_port import FundamentalDataPort

logger = logging.getLogger(__name__)


class GuruFocusFundamentalAdapter(FundamentalDataPort):
    """
    Concrete implementation of FundamentalDataPort using vault-stored
    GuruFocus screening data from Neon PostgreSQL.

    Replaces the old SQLite diskcache reader with vault-first reads.
    """

    def __init__(self, vault=None):
        self._vault = vault

    def _get_vault(self):
        """Lazy-init vault store."""
        if self._vault is None:
            from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
            self._vault = TimescaleDataStore()
        return self._vault

    def _load_screening(self, ticker: str) -> Optional[dict]:
        """Load the latest fundamental/screening snapshot from the vault."""
        try:
            return self._get_vault().load_mcp_latest("fundamental/screening", ticker)
        except Exception as e:
            logger.debug(f"Vault read failed for {ticker}: {e}")
            return None

    # ── FundamentalDataPort implementation ──────────────────────

    def get_guru_analysis(self, ticker: str) -> dict:
        data = self._load_screening(ticker)
        if not data:
            return {}
        return {
            "gf_score": data.get("gf_score", 0),
            "rank_profitability": data.get("rank_profitability", 0),
            "rank_growth": data.get("rank_growth", 0),
            "rank_financial_strength": data.get("rank_financial_strength", 0),
            "rank_gf_value": data.get("rank_gf_value", 0),
            "guru_buy_pct": data.get("guru_buy_pct", 0),
            "guru_hold_pct": data.get("guru_hold_pct", 0),
        }

    def get_insider_activity(self, ticker: str) -> dict:
        # Insider data requires a separate vault category (fundamental/insiders)
        # For now, return empty — Phase 5 will populate this
        return {}

    def get_earnings_calendar(self, ticker: str) -> Optional[dict]:
        # Earnings calendar requires separate vault category
        return None

    def get_financial_summary(self, ticker: str) -> dict:
        data = self._load_screening(ticker)
        if not data:
            return {}
        return {
            "piotroski_f_score": data.get("piotroski_f_score", 0),
            "altman_z_score": data.get("altman_z_score", 0),
            "beneish_m_score": data.get("beneish_m_score", 0),
            "roic": data.get("roic", 0),
            "roe": data.get("roe", 0),
            "roa": data.get("roa", 0),
            "gross_margin": data.get("gross_margin", 0),
            "operating_margin": data.get("operating_margin", 0),
            "net_margin": data.get("net_margin", 0),
            "debt_to_equity": data.get("debt_to_equity", 0),
            "current_ratio": data.get("current_ratio", 0),
            "gf_valuation": data.get("gf_valuation", ""),
            "risk_assessment": data.get("risk_assessment", ""),
            "price_to_gf_value": data.get("price_to_gf_value", 0),
        }

    def get_financial_statements(self, ticker: str, period_type: str = "annual") -> dict:
        # Full financial statements require a separate vault category
        return {"snapshots": []}

    def get_growth_profile(self, ticker: str) -> dict:
        data = self._load_screening(ticker)
        if not data:
            return {}
        return {
            "revenue_cagr": data.get("revenue_growth", 0),
            "eps_cagr": data.get("eps_growth", 0),
            "fcf_cagr": data.get("fcf_growth", 0),
        }

    def get_operating_kpis(self, ticker: str) -> dict:
        # Operating KPIs require a separate vault category
        return {}

    def get_segment_breakdown(self, ticker: str) -> dict:
        return {}

    def get_wacc(self, ticker: str) -> float:
        return 0.0

    def get_full_qgarp(self, ticker: str) -> dict:
        data = self._load_screening(ticker)
        if not data:
            return {}
        return {
            "gf_score": data.get("gf_score", 0),
            "piotroski_f_score": data.get("piotroski_f_score", 0),
            "pe_ratio": data.get("pe_ratio", 0),
            "pb_ratio": data.get("pb_ratio", 0),
            "peg_ratio": data.get("peg_ratio", 0),
            "price_to_gf_value": data.get("price_to_gf_value", 0),
            "ev_to_ebitda": data.get("ev_to_ebitda", 0),
        }

    def get_warning_signs(self, ticker: str) -> dict:
        data = self._load_screening(ticker)
        if not data:
            return {}
        return {
            "good_signs": data.get("good_signs", 0),
            "warning_signs": data.get("warning_signs", 0),
        }
