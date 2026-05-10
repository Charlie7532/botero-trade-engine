"""
Quality Watchlist Engine — Domain Use Case
=============================================
Scores, ranks, and manages Quality department watchlist candidates.
Applies Hohn/Munger quality gates to GuruFocus screening data.

Pure domain logic — no infrastructure dependencies.
"""
import logging
from datetime import datetime, timezone

from backend.modules.portfolio_management.domain.entities.watchlist_entities import (
    QualityWatchlistCandidate,
)

logger = logging.getLogger(__name__)

# Hohn/Munger quality thresholds
MIN_GF_SCORE = 80
MIN_PIOTROSKI = 6
MIN_ROIC = 12
MAX_DEBT_TO_EQUITY = 2.0
MIN_ALTMAN_Z = 1.81  # Grey zone boundary
MAX_BENEISH_M = -1.78  # Manipulation threshold


class QualityWatchlistEngine:
    """
    Scores and manages Quality watchlist candidates.

    The engine:
    1. Takes screening data (from vault via adapter)
    2. Applies Hohn/Munger quality gates
    3. Computes a composite conviction score
    4. Determines buy zones from GF Value data
    5. Returns ranked candidates for watchlist insertion
    """

    def score_candidate(self, screening: dict) -> QualityWatchlistCandidate:
        """
        Convert raw screening data into a scored watchlist candidate.

        Args:
            screening: Dict from GuruFocusMCPBridge.fetch_quality_screening()
                       or from vault load.
        """
        def _f(key, default=0):
            """Safely extract float from screening data."""
            v = screening.get(key, default)
            try:
                return float(v) if v is not None else default
            except (ValueError, TypeError):
                return default

        candidate = QualityWatchlistCandidate(
            ticker=screening.get("ticker", ""),
            company=screening.get("company", ""),
            sector=screening.get("sector", ""),
            gf_score=_f("gf_score"),
            piotroski_f_score=_f("piotroski_f_score"),
            altman_z_score=_f("altman_z_score"),
            price_to_gf_value=_f("price_to_gf_value"),
            gf_valuation=screening.get("gf_valuation", ""),
            rank_profitability=_f("rank_profitability"),
            rank_growth=_f("rank_growth"),
            rank_financial_strength=_f("rank_financial_strength"),
            roic=_f("roic"),
            roe=_f("roe"),
            net_margin=_f("net_margin"),
            debt_to_equity=_f("debt_to_equity"),
            current_price=_f("price"),
            # Keyratios deep fields (enriched from vault)
            wacc=_f("wacc"),
            operating_margin=_f("operating_margin_ttm"),
            operating_margin_5y_med=_f("operating_margin_5y_med"),
            fcf_margin=_f("fcf_margin_ttm"),
            fcf_margin_5y_med=_f("fcf_margin_5y_med"),
            beneish_m_score=_f("beneish_m", -999.0),
            added_at=datetime.now(timezone.utc),
            last_updated=datetime.now(timezone.utc),
        )

        # Compute conviction score (0-100)
        candidate.conviction_score = self._compute_conviction(candidate)

        # Compute buy zones from GF Value
        price_to_gfv = candidate.price_to_gf_value
        if price_to_gfv > 0 and candidate.current_price > 0:
            fair = candidate.current_price / price_to_gfv
            candidate.fair_value = round(fair, 2)
            candidate.buy_zone_high = round(fair * 0.90, 2)  # 10% below fair
            candidate.buy_zone_low = round(fair * 0.75, 2)   # 25% below fair

        # Classify moat
        candidate.moat_classification = self._classify_moat(candidate)

        # Determine initial status
        if candidate.is_in_buy_zone():
            candidate.status = "BUY_ZONE"
        elif candidate.conviction_score >= 70:
            candidate.status = "WATCHING"
        else:
            candidate.status = "WATCHING"

        return candidate

    def filter_quality_universe(
        self, screenings: list[dict], min_conviction: float = 60
    ) -> list[QualityWatchlistCandidate]:
        """
        Score all candidates and return only those passing quality gates.

        Args:
            screenings: List of screening dicts from vault
            min_conviction: Minimum conviction score to include

        Returns:
            Ranked list of qualified candidates (highest conviction first)
        """
        candidates = []
        for s in screenings:
            c = self.score_candidate(s)
            if c.conviction_score >= min_conviction and self._passes_hard_gates(c):
                candidates.append(c)

        # Sort by conviction descending
        candidates.sort(key=lambda x: x.conviction_score, reverse=True)
        return candidates

    def _compute_conviction(self, c: QualityWatchlistCandidate) -> float:
        """
        Composite conviction score (0-100) using weighted dimensions.

        Recalibrated from Phase 0 pilot study (2026-05-09):
        - ROIC-WACC spread CAPPED at 25 pts (prevents PLTR/NVDA inflation)
        - Moat stability penalty for unstable margin trajectories
        - Operating margin as primary profitability signal

        Weights:
        - Quality signals (GF + Piotroski + financial health): 35%
        - Value creation (ROIC-WACC spread, capped): 25%
        - Valuation (Price-to-GF-Value): 20%
        - Moat stability (margin consistency): 10%
        - Growth (ranks): 10%
        """
        score = 0.0

        # Quality dimension (35%)
        gf_pts = min(c.gf_score, 100) * 0.15
        f_pts = min(c.piotroski_f_score / 9, 1.0) * 12
        fin_pts = min(c.rank_financial_strength / 10, 1.0) * 8
        score += gf_pts + f_pts + fin_pts

        # Value creation dimension (25%) — CAPPED per pilot recalibration
        spread = c.roic_wacc_spread
        # Cap at 25% spread for full marks (prevents 150% ROIC distortion)
        spread_pts = min(max(spread, 0) / 25, 1.0) * 25
        score += spread_pts

        # Valuation dimension (20%)
        if c.price_to_gf_value > 0:
            val_pts = max(0, min(20, (1.3 - c.price_to_gf_value) * 20))
            score += val_pts

        # Moat stability dimension (10%) — NEW from pilot
        if c.operating_margin_5y_med > 0:
            # Reward consistent margins, penalize wild swings
            if c.moat_stable and c.operating_margin >= c.operating_margin_5y_med * 0.85:
                score += 10  # Stable and not decaying
            elif c.moat_stable:
                score += 5   # Stable but slight decay
            # Unstable (TTM > 3x 5Y) = 0 pts — moat unproven
        else:
            score += 5  # No 5Y data = neutral

        # Growth dimension (10%)
        growth_pts = min(c.rank_growth / 10, 1.0) * 7
        prof_pts = min(c.rank_profitability / 10, 1.0) * 3
        score += growth_pts + prof_pts

        return round(min(score, 100), 1)

    def _passes_hard_gates(self, c: QualityWatchlistCandidate) -> bool:
        """Hard disqualification gates — any failure = reject."""
        if c.gf_score < MIN_GF_SCORE:
            return False
        if c.piotroski_f_score < MIN_PIOTROSKI:
            return False
        if c.roic < MIN_ROIC:
            return False
        if c.debt_to_equity > MAX_DEBT_TO_EQUITY and c.debt_to_equity > 0:
            return False
        if c.altman_z_score < MIN_ALTMAN_Z and c.altman_z_score > 0:
            return False
        if not c.beneish_m_safe:
            return False
        if not c.moat_stable:
            return False
        return True

    def _classify_moat(self, c: QualityWatchlistCandidate) -> str:
        """Classify moat strength based on fundamental metrics."""
        strong_signals = 0

        if c.roic >= 20:
            strong_signals += 1
        if c.net_margin >= 20:
            strong_signals += 1
        if c.rank_profitability >= 8:
            strong_signals += 1
        if c.piotroski_f_score >= 8:
            strong_signals += 1
        if c.gf_score >= 90:
            strong_signals += 1

        if strong_signals >= 4:
            return "WIDE"
        elif strong_signals >= 2:
            return "NARROW"
        else:
            return "NONE"
