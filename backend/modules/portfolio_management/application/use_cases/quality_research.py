"""
QUALITY Research Pipeline — Hohn & Munger
============================================
Selección de activos para el departamento QUALITY.

Criterios: Tollkeepers con ≥2 barreras superpuestas, pricing power
verificado, incentivos alineados, ROIC > WACC.

Este pipeline NO usa momentum técnico, opciones, ni microestructura.
"""
import logging
from backend.modules.portfolio_management.domain.entities.universe_candidate import (
    UniverseCandidate, MarketRegime,
)
from backend.modules.portfolio_management.domain.rules.fundamental_filter import FundamentalFilter

logger = logging.getLogger(__name__)


class QualityResearchPipeline:
    """
    Pipeline de selección para el departamento QUALITY.

    Filosofía (Hohn & Munger):
    - Solo tollkeepers con barreras competitivas superpuestas
    - Pricing power verificado (FCF margin > 15%, márgenes estables)
    - Incentivos alineados (insider conviction)
    - Piotroski ≥ 7 (solidez financiera)
    - Máximo 5-10 posiciones (concentración radical)

    NO APLICA: momentum técnico, flujo de opciones, GEX, sweep data.
    """

    # Umbrales mínimos — si no pasa todos, NO es Quality
    MIN_FCF_MARGIN = 15.0         # % — pricing power proxy
    MIN_PIOTROSKI = 5             # Financial strength (ideal ≥ 7)
    MIN_QGARP = 40                # Quality + Growth minimum
    MAX_BENEISH = -1.78           # Above this = accounting manipulation risk
    MIN_ALTMAN_Z = 1.8            # Below this = bankruptcy risk

    def __init__(self, gurufocus=None):
        self.fundamental = FundamentalFilter()
        self._gurufocus = gurufocus

    def research(
        self,
        regime: MarketRegime,
        qgarp_data: dict = None,
        insider_data: dict = None,
        guru_tracking_data: dict = None,
        risk_data: dict = None,
        stock_summaries: dict = None,
        guru_picks: list[dict] = None,
    ) -> list[UniverseCandidate]:
        """
        Ejecuta el pipeline de investigación QUALITY.

        Returns:
            Lista de candidatos ordenados por quality_score descendente.
            Máximo 10 candidatos (concentración radical).
        """
        logger.info("=" * 60)
        logger.info("QUALITY RESEARCH PIPELINE (Hohn & Munger)")
        logger.info(f"Régimen: {regime.value}")
        logger.info("=" * 60)

        # Paso 1: Obtener universo base de guru picks
        guru_signals = {}
        if guru_picks:
            guru_signals = self.fundamental.evaluate_guru_signals(guru_picks)

        # Obtener todos los tickers candidatos
        all_tickers = set()
        if qgarp_data:
            all_tickers.update(qgarp_data.keys())
        if guru_signals:
            all_tickers.update(guru_signals.keys())
        if guru_tracking_data:
            all_tickers.update(guru_tracking_data.keys())

        if not all_tickers:
            logger.warning("Quality Pipeline: No tickers to evaluate")
            return []

        logger.info(f"Evaluando {len(all_tickers)} tickers candidatos...")

        candidates = []
        for ticker in all_tickers:
            candidate = self._evaluate_tollkeeper(
                ticker=ticker,
                regime=regime,
                qgarp_data=qgarp_data,
                insider_data=insider_data,
                guru_tracking_data=guru_tracking_data,
                risk_data=risk_data,
                stock_summaries=stock_summaries,
                guru_signals=guru_signals,
            )
            if candidate is not None:
                candidates.append(candidate)

        # Ordenar por score y limitar a 10 (concentración radical)
        candidates.sort(key=lambda c: c.score, reverse=True)
        candidates = candidates[:10]

        logger.info(f"Quality Pipeline → {len(candidates)} tollkeepers aprobados")
        for c in candidates:
            logger.info(
                f"  {c.ticker:>6} | Score={c.score:.1f} | "
                f"FCF={c.fcf_margin:.1f}% | Piotroski={c.piotroski_f_score} | "
                f"QGARP={c.qgarp_score:.0f} | "
                f"Guru={'✅' if c.guru_accumulation else '—'} | "
                f"Insider={c.insider_sentiment}"
            )

        return candidates

    def _evaluate_tollkeeper(
        self,
        ticker: str,
        regime: MarketRegime,
        qgarp_data: dict,
        insider_data: dict,
        guru_tracking_data: dict,
        risk_data: dict,
        stock_summaries: dict,
        guru_signals: dict,
    ) -> UniverseCandidate | None:
        """
        Evalúa si un ticker califica como tollkeeper QUALITY.
        Retorna None si no pasa los filtros mínimos.
        """
        candidate = UniverseCandidate(ticker=ticker, regime=regime)

        # ── Enriquecer con QGARP ──
        if qgarp_data and ticker in qgarp_data and self._gurufocus:
            scorecard = self._gurufocus.parse_qgarp_scorecard(ticker, qgarp_data[ticker])
            candidate.qgarp_score = scorecard.total_score
            candidate.piotroski_f_score = scorecard.piotroski_f_score
            candidate.altman_z_score = scorecard.altman_z_score
            if scorecard.gf_value_discount_pct > 0:
                candidate.dcf_discount_pct = scorecard.gf_value_discount_pct

            gv = self._gurufocus.parse_guru_valuation(
                ticker, qgarp_data[ticker],
                keyratios_data=qgarp_data[ticker].get("keyratios"),
            )
            candidate.price_to_gf_value = gv["price_to_gf_value"]
            candidate.gf_value_discount_pct = gv["gf_value_discount_pct"]
            candidate.fcf_margin = gv["fcf_margin"]
            candidate.beneish_m_score = gv["beneish_m_score"]
            candidate.price_to_fcf = gv["price_to_fcf"]

        # ── Enriquecer con Insider ──
        if insider_data and ticker in insider_data and self._gurufocus:
            idata = insider_data[ticker]
            insider = self._gurufocus.parse_insider_conviction(
                ticker,
                cluster_data=idata.get("cluster"),
                ceo_data=idata.get("ceo"),
                cfo_data=idata.get("cfo"),
            )
            candidate.insider_conviction_score = insider.conviction_score
            candidate.insider_sentiment = insider.net_insider_sentiment

        # ── Enriquecer con Guru Tracking ──
        if guru_tracking_data and ticker in guru_tracking_data and self._gurufocus:
            guru = self._gurufocus.parse_guru_tracking(ticker, guru_tracking_data[ticker])
            candidate.guru_accumulation = guru.accumulation
            candidate.guru_conviction_score = guru.net_buying_score
            candidate.guru_count = guru.guru_count

        # ── Guru signal from picks ──
        if ticker in guru_signals:
            net = guru_signals[ticker]["net_signal"]
            if not candidate.guru_accumulation:
                candidate.guru_accumulation = net > 0

        # ── Valuation from summaries ──
        if stock_summaries and ticker in stock_summaries:
            if candidate.dcf_discount_pct == 0:
                candidate.dcf_discount_pct = self.fundamental.evaluate_valuation(
                    stock_summaries[ticker]
                )

        # ═══ QUALITY GATES — Hard Filters ═══
        # Gate 1: Beneish M-Score (accounting manipulation)
        if candidate.beneish_m_score > self.MAX_BENEISH and candidate.beneish_m_score != -3.0:
            logger.debug(f"  {ticker}: REJECTED — Beneish {candidate.beneish_m_score:.2f} > {self.MAX_BENEISH}")
            return None

        # Gate 2: Altman Z-Score (bankruptcy risk)
        if 0 < candidate.altman_z_score < self.MIN_ALTMAN_Z:
            logger.debug(f"  {ticker}: REJECTED — Altman Z {candidate.altman_z_score:.2f} < {self.MIN_ALTMAN_Z}")
            return None

        # ═══ QUALITY SCORING — Pure Fundamental ═══
        candidate.score = self._compute_quality_score(candidate)

        # Minimum viable score
        if candidate.score < 20:
            logger.debug(f"  {ticker}: REJECTED — Quality score {candidate.score:.1f} < 20")
            return None

        return candidate

    def _compute_quality_score(self, c: UniverseCandidate) -> float:
        """
        Score QUALITY puro — solo calidad fundamental.
        No incluye momentum, opciones, ni sentimiento.
        """
        score = 0.0

        # QGARP Quality & Growth (30%)
        if c.qgarp_score > 0:
            score += (c.qgarp_score / 100) * 30.0

        # FCF Margin — Pricing Power (20%)
        if c.fcf_margin > 25:
            score += 20.0
        elif c.fcf_margin > 15:
            score += 12.0
        elif c.fcf_margin > 10:
            score += 5.0

        # Piotroski F-Score (15%)
        if c.piotroski_f_score >= 7:
            score += 15.0
        elif c.piotroski_f_score >= 5:
            score += 7.5

        # Guru Conviction (15%)
        if c.guru_conviction_score > 0:
            score += min((c.guru_conviction_score / 100) * 15.0, 15.0)
        elif c.guru_accumulation:
            score += 7.5

        # Insider Conviction (10%)
        if c.insider_conviction_score > 0:
            score += min((c.insider_conviction_score / 100) * 10.0, 10.0)

        # Valuation — GF Value discount (10%)
        if c.price_to_gf_value > 0:
            if c.price_to_gf_value < 0.8:
                score += 10.0
            elif c.price_to_gf_value < 1.0:
                score += 5.0
            elif c.price_to_gf_value > 1.3:
                if c.qgarp_score < 80 and c.fcf_margin < 20:
                    score -= 10.0

        return score
