"""
SPECULATIVE Scanner — Karsan, Eifert & PTJ
=============================================
Selección de activos para el departamento SPECULATIVE.

Criterios: Asimetría ≥5:1 potencial, gamma regime favorable,
flujo institucional unidireccional, volumen inusual.

Este pipeline NO usa fundamentales (QGARP, FCF, Piotroski, moat).
"""
import logging
from dataclasses import dataclass
from datetime import datetime, UTC
from backend.modules.portfolio_management.domain.entities.universe_candidate import MarketRegime

logger = logging.getLogger(__name__)


@dataclass
class SpeculativeCandidate:
    """Un activo que califica para evaluación SPECULATIVE."""
    ticker: str
    regime: MarketRegime
    # Microstructure signals
    gamma_regime: str = "UNKNOWN"       # POSITIVE / NEGATIVE / NEUTRAL
    gex_net: float = 0.0                # Net Gamma Exposure
    max_pain: float = 0.0               # Max Pain level
    max_pain_distance_pct: float = 0.0  # Distance to Max Pain
    put_call_ratio: float = 0.0         # Put/Call OI ratio
    # Flow signals
    sweep_count: int = 0                # Total sweeps detected
    sweep_call_pct: float = 50.0        # % of sweeps that are calls
    flow_net_premium: float = 0.0       # Net premium flow
    flow_direction: str = "NEUTRAL"     # BULLISH / BEARISH / NEUTRAL
    darkpool_aligned: bool = False      # Dark pool confirms flow direction
    # Volume signals
    rvol: float = 1.0                   # Relative volume (vs 20d avg)
    volume_anomaly: bool = False        # Volume > 2x average
    # Scoring
    asymmetry_score: float = 0.0        # Estimated R:R potential
    microstructure_score: float = 0.0   # Composite microstructure score
    selected_at: datetime = None

    def __post_init__(self):
        if self.selected_at is None:
            self.selected_at = datetime.now(UTC)


class SpeculativeScanner:
    """
    Scanner de oportunidades para el departamento SPECULATIVE.

    Filosofía (Karsan + Eifert + PTJ):
    - Busca asimetrías mecánicas: gamma flip, flow unidireccional
    - Cadencia rápida (cada 15 minutos en horario de mercado)
    - Sin fundamentales — puro microestructura y flow
    - Asimetría mínima 5:1 o no hay trade

    Señales que busca:
    1. Gamma regime NEGATIVE + flow bullish = dealers forzados a comprar
    2. Sweep ratio > 70% calls + darkpool aligned = convicción institucional
    3. RVOL > 2x + PCR < 0.7 = acumulación inusual
    4. Max Pain magnet con precio debajo = pull gravitacional alcista
    """

    # Umbrales de activación
    MIN_SWEEP_COUNT = 3           # Mínimo sweeps para considerar
    MIN_CALL_PCT = 60.0           # % calls para sesgo bullish
    MIN_RVOL = 1.5                # RVOL mínimo para interés
    MAX_PCR_BULLISH = 0.8         # PCR debajo de esto = bullish
    MIN_MICRO_SCORE = 30.0        # Score mínimo para pasar

    def scan(
        self,
        regime: MarketRegime,
        flow_alerts: list[dict] = None,
        darkpool_prints: list[dict] = None,
        options_data: dict = None,
        volume_data: dict = None,
        watchlist: list[str] = None,
    ) -> list[SpeculativeCandidate]:
        """
        Escanea el universo buscando oportunidades tácticas.

        Args:
            regime: Régimen macro actual (del CIO).
            flow_alerts: Datos de flow de Unusual Whales (pre-fetched via MCP).
            darkpool_prints: Dark pool prints (pre-fetched via MCP).
            options_data: {ticker: {gamma_regime, gex, max_pain, pcr}} pre-fetched.
            volume_data: {ticker: {rvol, avg_volume}} pre-fetched.
            watchlist: Lista de tickers a monitorear (opcional).

        Returns:
            Lista de SpeculativeCandidates ordenados por microstructure_score.
        """
        logger.info("=" * 60)
        logger.info("SPECULATIVE SCANNER (Karsan + Eifert + PTJ)")
        logger.info(f"Régimen: {regime.value}")
        logger.info("=" * 60)

        # En CRISIS, SPECULATIVE se reduce drásticamente
        if regime == MarketRegime.CRISIS:
            logger.warning("CRISIS regime — Speculative scanning paused")
            return []

        # Extraer tickers con actividad de las fuentes disponibles
        active_tickers = set()
        if watchlist:
            active_tickers.update(watchlist)
        if flow_alerts:
            for alert in flow_alerts:
                sym = alert.get("ticker") or alert.get("symbol", "")
                if sym:
                    active_tickers.add(sym)
        if options_data:
            active_tickers.update(options_data.keys())

        if not active_tickers:
            logger.info("Speculative Scanner: No active tickers to evaluate")
            return []

        logger.info(f"Evaluando {len(active_tickers)} tickers activos...")

        candidates = []
        for ticker in active_tickers:
            candidate = self._evaluate_microstructure(
                ticker=ticker,
                regime=regime,
                flow_alerts=flow_alerts or [],
                darkpool_prints=darkpool_prints or [],
                options_data=options_data or {},
                volume_data=volume_data or {},
            )
            if candidate is not None:
                candidates.append(candidate)

        # Ordenar por microstructure_score descendente
        candidates.sort(key=lambda c: c.microstructure_score, reverse=True)

        logger.info(f"Speculative Scanner → {len(candidates)} opportunities detected")
        for c in candidates:
            logger.info(
                f"  {c.ticker:>6} | µScore={c.microstructure_score:.1f} | "
                f"Gamma={c.gamma_regime} | Sweeps={c.sweep_count}({c.sweep_call_pct:.0f}%C) | "
                f"RVOL={c.rvol:.1f}x | PCR={c.put_call_ratio:.2f} | "
                f"Flow={c.flow_direction}"
            )

        return candidates

    def _evaluate_microstructure(
        self,
        ticker: str,
        regime: MarketRegime,
        flow_alerts: list[dict],
        darkpool_prints: list[dict],
        options_data: dict,
        volume_data: dict,
    ) -> SpeculativeCandidate | None:
        """Evaluate a ticker purely on microstructure signals."""
        candidate = SpeculativeCandidate(ticker=ticker, regime=regime)

        # ── Options / Gamma data ──
        if ticker in options_data:
            opts = options_data[ticker]
            candidate.gamma_regime = opts.get("gamma_regime", "UNKNOWN")
            candidate.gex_net = opts.get("gex_net", 0.0)
            candidate.max_pain = opts.get("max_pain", 0.0)
            candidate.max_pain_distance_pct = opts.get("max_pain_distance_pct", 0.0)
            candidate.put_call_ratio = opts.get("put_call_ratio", 0.0)

        # ── Flow alerts (sweeps) ──
        ticker_alerts = [a for a in flow_alerts if (a.get("ticker") or a.get("symbol", "")) == ticker]
        if ticker_alerts:
            candidate.sweep_count = len(ticker_alerts)
            calls = sum(1 for a in ticker_alerts if a.get("option_type", "").upper() == "CALL")
            total = len(ticker_alerts)
            candidate.sweep_call_pct = (calls / total * 100) if total > 0 else 50.0
            candidate.flow_net_premium = sum(float(a.get("premium", 0)) for a in ticker_alerts)
            if candidate.sweep_call_pct > 65:
                candidate.flow_direction = "BULLISH"
            elif candidate.sweep_call_pct < 35:
                candidate.flow_direction = "BEARISH"

        # ── Dark pool ──
        dp_prints = [p for p in darkpool_prints if (p.get("ticker") or p.get("symbol", "")) == ticker]
        if dp_prints and candidate.flow_direction != "NEUTRAL":
            # Check if dark pool aligns with flow direction
            dp_net = sum(float(p.get("size", 0)) * (1 if p.get("side", "").upper() == "BUY" else -1) for p in dp_prints)
            candidate.darkpool_aligned = (
                (dp_net > 0 and candidate.flow_direction == "BULLISH") or
                (dp_net < 0 and candidate.flow_direction == "BEARISH")
            )

        # ── Volume ──
        if ticker in volume_data:
            candidate.rvol = volume_data[ticker].get("rvol", 1.0)
            candidate.volume_anomaly = candidate.rvol >= 2.0

        # ═══ MICROSTRUCTURE SCORING ═══
        candidate.microstructure_score = self._compute_micro_score(candidate)

        # Minimum threshold
        if candidate.microstructure_score < self.MIN_MICRO_SCORE:
            return None

        return candidate

    def _compute_micro_score(self, c: SpeculativeCandidate) -> float:
        """
        Score SPECULATIVE puro — solo microestructura.
        No incluye fundamentales, valuación, ni moat.
        """
        score = 0.0

        # Gamma Regime (25 pts)
        if c.gamma_regime == "NEGATIVE":
            score += 25.0  # Dealers forced to buy on rally
        elif c.gamma_regime == "NEUTRAL":
            score += 10.0

        # Flow Direction + Sweeps (25 pts)
        if c.sweep_count >= self.MIN_SWEEP_COUNT:
            if c.flow_direction == "BULLISH" and c.sweep_call_pct > 70:
                score += 25.0
            elif c.flow_direction == "BULLISH":
                score += 15.0
            elif c.flow_direction == "BEARISH" and c.sweep_call_pct < 30:
                score += 20.0  # Bearish setups also valid for puts

        # Dark Pool Confirmation (15 pts)
        if c.darkpool_aligned:
            score += 15.0

        # Volume Anomaly (15 pts)
        if c.volume_anomaly:
            score += 15.0
        elif c.rvol >= self.MIN_RVOL:
            score += 8.0

        # PCR Extreme (10 pts)
        if c.put_call_ratio > 0:
            if c.put_call_ratio < 0.5:
                score += 10.0  # Extreme bullish sentiment
            elif c.put_call_ratio < self.MAX_PCR_BULLISH:
                score += 5.0

        # Max Pain Magnet (10 pts)
        if c.max_pain_distance_pct < -3:
            score += 10.0  # Price below max pain = gravitational pull up
        elif c.max_pain_distance_pct < 0:
            score += 5.0

        return score
