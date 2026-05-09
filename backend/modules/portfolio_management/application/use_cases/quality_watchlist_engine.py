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

        Weights reflect Hohn/Munger priorities:
        - Quality (GF + Piotroski + financial health): 40%
        - Profitability (ROIC, margins): 25%
        - Valuation (Price-to-GF-Value): 20%
        - Growth (ranks): 15%
        """
        score = 0.0

        # Quality dimension (40%)
        gf_pts = min(c.gf_score, 100) * 0.15
        f_pts = min(c.piotroski_f_score / 9, 1.0) * 15
        fin_pts = min(c.rank_financial_strength / 10, 1.0) * 10
        score += gf_pts + f_pts + fin_pts

        # Profitability dimension (25%)
        roic_pts = min(c.roic / 30, 1.0) * 15  # 30% ROIC = full marks
        margin_pts = min(c.net_margin / 25, 1.0) * 10  # 25% net margin = full
        score += roic_pts + margin_pts

        # Valuation dimension (20%)
        if c.price_to_gf_value > 0:
            # Below 1.0 = undervalued, above = overvalued
            val_pts = max(0, min(20, (1.3 - c.price_to_gf_value) * 20))
            score += val_pts

        # Growth dimension (15%)
        growth_pts = min(c.rank_growth / 10, 1.0) * 10
        prof_pts = min(c.rank_profitability / 10, 1.0) * 5
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
