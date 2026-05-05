import logging
from datetime import date
from typing import Optional

from backend.modules.flow_intelligence.domain.entities.whale_events import WhaleVerdict, MacroEvent
from backend.modules.flow_intelligence.domain.rules.macro_calendar import MacroEventCalendar

logger = logging.getLogger(__name__)

class WhaleFlowReader:
    """
    Lee el flujo institucional (ballenas) y emite un veredicto
    sobre la dirección esperada del mercado.

    No predice el mercado — lee lo que las ballenas ya están
    haciendo con su propio dinero.

    Inputs (todos opcionales, cada uno suma evidencia):
      - SPY Macro Gate: cum_delta, am_pm_divergence
      - UW Sweeps: sweep count, call/put ratio
      - Market Tide: premium flow direction + acceleration
      - GEX Regime: PIN/DRIFT/SQUEEZE

    Output: WhaleVerdict con veredicto + escala de posición
    """

    def read_flow(
        self,
        # SPY Macro Gate (from UW Intelligence)
        spy_cum_delta: float = 0.0,
        spy_signal: str = "NEUTRAL",
        spy_scale: float = 1.0,
        am_pm_diverges: bool = False,
        spy_confidence: float = 0.5,
        # UW Market Sentiment
        sweep_call_pct: float = 50.0,
        total_sweeps: int = 0,
        market_breadth_pct: float = 50.0,
        sentiment_regime: str = "NEUTRAL",
        # Market Tide
        tide_direction: str = "NEUTRAL",
        tide_accelerating: bool = False,
        tide_net_premium: float = 0.0,
        # GEX Regime (from Options Awareness)
        gex_regime: str = "UNKNOWN",
        gex_net: float = 0.0,
        # Event context
        nearest_event: Optional[MacroEvent] = None,
    ) -> WhaleVerdict:
        """
        Analiza todas las señales de flujo y emite un veredicto.

        La lógica es un sistema de puntos con 3 ejes:
          1. Dirección del flujo (bullish/bearish)
          2. Intensidad del flujo (fuerte/débil)
          3. Consenso entre señales (acuerdo/divergencia)
        """
        verdict = WhaleVerdict()

        # ── Eje 1: Dirección del Flujo ──────────────────────────
        direction_score = 0  # -4 a +4

        # SPY Delta (peso máximo — es el dinero real de SPY)
        if spy_cum_delta > 500_000:
            direction_score += 2
        elif spy_cum_delta > 50_000:
            direction_score += 1
        elif spy_cum_delta < -500_000:
            direction_score -= 2
        elif spy_cum_delta < -50_000:
            direction_score -= 1

        # Sweep direction
        if sweep_call_pct > 65 and total_sweeps > 5:
            direction_score += 1
        elif sweep_call_pct < 35 and total_sweeps > 5:
            direction_score -= 1

        # Market Tide
        if tide_direction == "BULLISH" and tide_accelerating:
            direction_score += 1
        elif tide_direction == "BEARISH" and tide_accelerating:
            direction_score -= 1

        # AM/PM divergence (contrarian — strongest warning signal)
        if am_pm_diverges:
            # La mañana y la tarde están en desacuerdo — peligro
            direction_score = int(direction_score * 0.5)  # Halve conviction
            verdict.am_pm_divergence = True

        # ── Eje 2: Intensidad ───────────────────────────────────
        intensity_signals = 0  # 0-4

        if total_sweeps > 10:
            intensity_signals += 2
            verdict.sweep_intensity = "EXPLOSIVE"
        elif total_sweeps > 3:
            intensity_signals += 1
            verdict.sweep_intensity = "MODERATE"
        elif total_sweeps > 0:
            verdict.sweep_intensity = "WEAK"
        else:
            verdict.sweep_intensity = "NONE"

        if abs(tide_net_premium) > 5_000_000:
            intensity_signals += 1
        if spy_confidence > 0.7:
            intensity_signals += 1

        # ── Eje 3: Consenso ─────────────────────────────────────
        signals_agree = 0
        total_signals = 0

        bullish_signals = [
            spy_cum_delta > 0,
            sweep_call_pct > 55,
            tide_direction == "BULLISH",
            sentiment_regime == "BULL",
        ]
        bearish_signals = [not s for s in bullish_signals]

        bullish_count = sum(bullish_signals)
        bearish_count = sum(bearish_signals)
        consensus = max(bullish_count, bearish_count) / 4.0

        # ── Determinar flujo SPY ────────────────────────────────
        if direction_score >= 2:
            verdict.spy_flow_direction = "BULLISH"
        elif direction_score <= -2:
            verdict.spy_flow_direction = "BEARISH"
        else:
            verdict.spy_flow_direction = "NEUTRAL"

        verdict.gex_regime = gex_regime
        verdict.tide_direction = tide_direction

        # ── Event context ───────────────────────────────────────
        if nearest_event:
            verdict.nearest_event = nearest_event
            verdict.hours_to_event = nearest_event.hours_away
            verdict.is_event_window = nearest_event.hours_away < 48

            # Freeze stops si evento nuclear en < 30 min
            if nearest_event.impact_level == 1 and nearest_event.hours_away < 0.5:
                verdict.freeze_stops = True
                verdict.freeze_duration_min = 30

        # ── VEREDICTO FINAL ─────────────────────────────────────
        abs_direction = abs(direction_score)

        if abs_direction >= 3 and intensity_signals >= 2 and consensus > 0.7:
            # Flujo explosivo, dirección clara, señales alineadas
            verdict.verdict = "RIDE_THE_WHALES"
            verdict.position_scale = 1.0
            verdict.confidence = min(1.0, consensus * 0.8 + intensity_signals * 0.1)
            verdict.diagnosis = (
                f"Flujo institucional EXPLOSIVO. Dirección={'BULL' if direction_score > 0 else 'BEAR'}. "
                f"{total_sweeps} sweeps, delta SPY={spy_cum_delta:+,.0f}. "
                f"Las ballenas saben. Entrar con ellas."
            )

        elif abs_direction >= 2 and intensity_signals >= 1:
            # Flujo claro pero no explosivo
            verdict.verdict = "LEAN_WITH_FLOW"
            verdict.position_scale = 0.70
            verdict.confidence = min(0.8, consensus * 0.6 + intensity_signals * 0.1)
            verdict.diagnosis = (
                f"Flujo institucional moderado. Dirección={'BULL' if direction_score > 0 else 'BEAR'}. "
                f"Entrar con tamaño reducido (70%)."
            )

        elif abs_direction <= 1 and intensity_signals <= 1:
            # Flujo silencioso — nadie sabe
            verdict.verdict = "UNCERTAIN"
            verdict.position_scale = 0.40 if verdict.is_event_window else 0.60
            verdict.confidence = 0.3
            event_ctx = ""
            if verdict.is_event_window:
                event_ctx = f" Evento {nearest_event.name} en {verdict.hours_to_event:.0f}h."
            verdict.diagnosis = (
                f"Flujo institucional SILENCIOSO. Sin convicción direccional.{event_ctx} "
                f"Esperar post-evento o reducir tamaño a {verdict.position_scale*100:.0f}%."
            )

        else:
            # Señales contradictorias
            verdict.verdict = "CONTRA_FLOW"
            verdict.position_scale = 0.0
            verdict.confidence = 0.2
            verdict.diagnosis = (
                f"Señales CONTRADICTORIAS. AM/PM diverge={am_pm_diverges}. "
                f"SPY delta={spy_cum_delta:+,.0f} vs sweeps={sweep_call_pct:.0f}% calls. "
                f"No entrar. Preparar setup contrarian post-evento."
            )

        # GEX amplification warning
        if gex_regime in ("SQUEEZE_UP", "SQUEEZE_DOWN") and verdict.is_event_window:
            verdict.diagnosis += (
                f" ⚡ GEX NEGATIVO ({gex_regime}): Los dealers amplificarán "
                f"el movimiento post-anuncio. Stops deben ser más anchos."
            )

        logger.info(
            f"WhaleFlow: {verdict.verdict} (scale={verdict.position_scale:.0%}, "
            f"conf={verdict.confidence:.0%}) — {verdict.diagnosis[:80]}..."
        )

        return verdict

class EventFlowIntelligence:
    """
    Interfaz unificada que combina el Calendario Macro
    y la Lectura de Flujo de Ballenas.

    Uso típico:
        efi = EventFlowIntelligence()
        verdict = efi.assess(
            spy_cum_delta=800_000,
            total_sweeps=12,
            sweep_call_pct=72,
            gex_regime="PIN",
        )
        if verdict.verdict == "RIDE_THE_WHALES":
            # Entrar con tamaño completo
            ...
    """

    def __init__(self):
        self.calendar = MacroEventCalendar()
        self.flow_reader = WhaleFlowReader()

    def assess(self, reference_date: Optional[date] = None, **flow_kwargs) -> WhaleVerdict:
        """
        Evaluación completa: calendario + flujo.

        Pasa todos los kwargs de flujo directamente al WhaleFlowReader.
        Automáticamente inyecta el evento más cercano.
        """
        nearest_event = self.calendar.get_nearest_event(reference_date)
        flow_kwargs["nearest_event"] = nearest_event
        return self.flow_reader.read_flow(**flow_kwargs)

    def get_events(self, days_ahead: int = 5, reference_date: Optional[date] = None) -> list[MacroEvent]:
        """Acceso directo al calendario."""
        return self.calendar.get_upcoming_events(days_ahead, reference_date)
