"""
EVENT FLOW INTELLIGENCE — Conciencia Macro + Lectura de Ballenas
==================================================================
"El mercado todo lo sabe con anticipación. Las ballenas dejan huellas."

Este módulo NO bloquea mecánicamente antes de eventos. Lee el FLUJO
del dinero institucional para decidir si el evento es una oportunidad
o una trampa.

Dos componentes:
  1. MacroEventCalendar → Sabe QUÉ evento viene y CUÁNDO
  2. WhaleFlowReader    → Lee QUÉ apuestan las ballenas

Veredictos:
  RIDE_THE_WHALES  — Flujo fuerte + dirección clara = entrar con ellas
  LEAN_WITH_FLOW   — Flujo moderado = entrar con tamaño reducido (70%)
  UNCERTAIN        — Flujo silencioso pre-evento = esperar post-evento
  CONTRA_FLOW      — Flujo contradice tesis = no entrar

Referencia:
  - Los Sweeps institucionales revelan urgencia (83.9% de misses = 0 sweeps)
  - AM/PM divergence en SPY predice caídas con 100% hit rate
  - GEX negativo amplifica movimientos post-anuncio (Gamma Squeeze)
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, UTC
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class MacroEvent:
    """Un evento económico que puede mover el mercado."""
    name: str                          # "FOMC_DECISION", "CPI", "NFP", etc.
    event_date: datetime               # Fecha y hora del evento
    impact_level: int = 1              # 1=NUCLEAR, 2=HIGH, 3=MODERATE
    has_projections: bool = False      # FOMC con Dot Plot / SEP
    description: str = ""

    @property
    def hours_away(self) -> float:
        """Horas hasta el evento desde ahora."""
        delta = self.event_date - datetime.now(UTC)
        return max(0, delta.total_seconds() / 3600)


@dataclass
class WhaleVerdict:
    """Veredicto del flujo de ballenas sobre la dirección del mercado."""
    verdict: str = "UNCERTAIN"          # RIDE_THE_WHALES, LEAN_WITH_FLOW, UNCERTAIN, CONTRA_FLOW
    position_scale: float = 1.0         # Factor de escala para tamaño de posición
    confidence: float = 0.0             # 0-1, confianza en el veredicto

    # Componentes que contribuyeron
    spy_flow_direction: str = "NEUTRAL" # BULLISH, BEARISH, NEUTRAL
    sweep_intensity: str = "NONE"       # EXPLOSIVE, MODERATE, WEAK, NONE
    gex_regime: str = "UNKNOWN"         # PIN, DRIFT, SQUEEZE_UP, SQUEEZE_DOWN
    tide_direction: str = "NEUTRAL"     # BULLISH, BEARISH, NEUTRAL
    am_pm_divergence: bool = False      # Señal de reversión inminente

    # Contexto de evento
    nearest_event: Optional[MacroEvent] = None
    is_event_window: bool = False       # True si hay evento en < 48h
    hours_to_event: float = 999.0

    # Recomendación de stop
    freeze_stops: bool = False          # True si el evento es inminente (< 30 min)
    freeze_duration_min: int = 0        # Minutos de congelamiento

    # Diagnóstico textual
    diagnosis: str = ""


# ═══════════════════════════════════════════════════════════════
# MACRO EVENT CALENDAR
# ═══════════════════════════════════════════════════════════════

class MacroEventCalendar:
    """
    Calendario de eventos macro que mueven el mercado.

    Fuentes (en orden de prioridad):
      1. Finnhub economic_calendar API (si disponible)
      2. Calendario FOMC 2026 hardcoded
      3. Reglas conocidas para CPI/NFP (primer viernes, ~10-14 del mes)
    """

    # FOMC 2026 — Las 8 reuniones del año
    # * = Con Summary of Economic Projections (SEP) + Dot Plot (más volátil)
    FOMC_2026 = [
        {"dates": (date(2026, 1, 27), date(2026, 1, 28)), "sep": False},
        {"dates": (date(2026, 3, 17), date(2026, 3, 18)), "sep": True},
        {"dates": (date(2026, 4, 28), date(2026, 4, 29)), "sep": False},
        {"dates": (date(2026, 6, 16), date(2026, 6, 17)), "sep": True},
        {"dates": (date(2026, 7, 28), date(2026, 7, 29)), "sep": False},
        {"dates": (date(2026, 9, 15), date(2026, 9, 16)), "sep": True},
        {"dates": (date(2026, 10, 27), date(2026, 10, 28)), "sep": False},
        {"dates": (date(2026, 12, 8), date(2026, 12, 9)), "sep": True},
    ]

    # Hora estándar de anuncios (Eastern Time, representada en UTC)
    FOMC_HOUR_UTC = 18  # 2:00 PM ET = 18:00 UTC
    DATA_HOUR_UTC = 12  # 8:30 AM ET ≈ 12:30 UTC (simplificado)

    def __init__(self):
        from modules.flow_intelligence.infrastructure.finnhub_adapter import FinnhubCalendarAdapter
        self._finnhub_adapter = FinnhubCalendarAdapter()
        self._cached_events: list[MacroEvent] = []
        self._cache_date: Optional[date] = None

    def get_upcoming_events(
        self,
        days_ahead: int = 5,
        reference_date: Optional[date] = None,
    ) -> list[MacroEvent]:
        """
        Obtiene los eventos macro de los próximos N días.

        Returns:
            Lista de MacroEvent ordenados por fecha, más cercano primero.
        """
        today = reference_date or date.today()

        # Usar cache si es del mismo día
        if self._cache_date == today and self._cached_events:
            return self._cached_events

        events = []

        # 1. Intentar Finnhub via adapter
        if self._finnhub_adapter.is_available:
            events.extend(self._fetch_finnhub_events(today, days_ahead))

        # 2. Siempre agregar FOMC hardcoded (más confiable)
        events.extend(self._get_fomc_events(today, days_ahead))

        # 3. Agregar CPI/NFP estimados si Finnhub no los cubrió
        if not any(e.name in ("CPI", "NFP", "PCE") for e in events):
            events.extend(self._estimate_data_releases(today, days_ahead))

        # Deduplicar por nombre + fecha
        seen = set()
        unique_events = []
        for e in events:
            key = (e.name, e.event_date.date())
            if key not in seen:
                seen.add(key)
                unique_events.append(e)

        # Ordenar por fecha
        unique_events.sort(key=lambda e: e.event_date)

        self._cached_events = unique_events
        self._cache_date = today

        if unique_events:
            nearest = unique_events[0]
            logger.info(
                f"MacroEventCalendar: {len(unique_events)} eventos en próximos {days_ahead}d. "
                f"Más cercano: {nearest.name} en {nearest.hours_away:.0f}h "
                f"(impacto nivel {nearest.impact_level})"
            )

        return unique_events

    def get_nearest_event(self, reference_date: Optional[date] = None) -> Optional[MacroEvent]:
        """Obtiene el evento más cercano."""
        events = self.get_upcoming_events(days_ahead=5, reference_date=reference_date)
        return events[0] if events else None

    def _fetch_finnhub_events(self, today: date, days_ahead: int) -> list[MacroEvent]:
        """Obtiene eventos de Finnhub via infrastructure adapter."""
        events = []
        try:
            end_date = today + timedelta(days=days_ahead)
            raw_events = self._finnhub_adapter.fetch_events(today, end_date)
            for item in raw_events:
                event_name = item.get("event", "").upper()
                impact = self._classify_event_impact(event_name)
                if impact is None:
                    continue

                event_date_str = item.get("time", item.get("date", ""))
                try:
                    event_dt = datetime.fromisoformat(event_date_str).replace(tzinfo=UTC)
                except (ValueError, TypeError):
                    continue

                events.append(MacroEvent(
                    name=self._normalize_event_name(event_name),
                    event_date=event_dt,
                    impact_level=impact,
                    description=event_name,
                ))
        except Exception as e:
            logger.warning(f"Error processing Finnhub events: {e}")
        return events

    def _get_fomc_events(self, today: date, days_ahead: int) -> list[MacroEvent]:
        """Obtiene FOMC events del calendario hardcoded."""
        events = []
        end_date = today + timedelta(days=days_ahead)

        for fomc in self.FOMC_2026:
            decision_day = fomc["dates"][1]  # Día 2 = decisión
            if today <= decision_day <= end_date:
                events.append(MacroEvent(
                    name="FOMC_DECISION",
                    event_date=datetime(
                        decision_day.year, decision_day.month, decision_day.day,
                        self.FOMC_HOUR_UTC, 0, tzinfo=UTC,
                    ),
                    impact_level=1,  # NUCLEAR
                    has_projections=fomc["sep"],
                    description=f"FOMC Decision {'+ SEP/Dot Plot' if fomc['sep'] else ''}",
                ))

            # También detectar el día 1 (inicio de reunión)
            meeting_day1 = fomc["dates"][0]
            if today <= meeting_day1 <= end_date and meeting_day1 != decision_day:
                events.append(MacroEvent(
                    name="FOMC_MEETING_START",
                    event_date=datetime(
                        meeting_day1.year, meeting_day1.month, meeting_day1.day,
                        9, 0, tzinfo=UTC,
                    ),
                    impact_level=3,  # MODERATE — el mercado está nervioso
                    description="FOMC Meeting Day 1 — Mercado en espera",
                ))

        return events

    def _estimate_data_releases(self, today: date, days_ahead: int) -> list[MacroEvent]:
        """Estima fechas de CPI/NFP basado en patrones conocidos."""
        events = []
        end_date = today + timedelta(days=days_ahead)

        for month_offset in range(2):
            check_month = today.month + month_offset
            check_year = today.year + (check_month - 1) // 12
            check_month = ((check_month - 1) % 12) + 1

            # NFP: Primer viernes del mes
            first_day = date(check_year, check_month, 1)
            days_until_friday = (4 - first_day.weekday()) % 7
            nfp_date = first_day + timedelta(days=days_until_friday)
            if today <= nfp_date <= end_date:
                events.append(MacroEvent(
                    name="NFP",
                    event_date=datetime(
                        nfp_date.year, nfp_date.month, nfp_date.day,
                        self.DATA_HOUR_UTC, 30, tzinfo=UTC,
                    ),
                    impact_level=1,  # NUCLEAR
                    description="Non-Farm Payrolls",
                ))

            # CPI: Típicamente entre el 10-14 del mes (estimamos el 12)
            cpi_date = date(check_year, check_month, 12)
            # Ajustar si cae en fin de semana
            while cpi_date.weekday() >= 5:
                cpi_date += timedelta(days=1)
            if today <= cpi_date <= end_date:
                events.append(MacroEvent(
                    name="CPI",
                    event_date=datetime(
                        cpi_date.year, cpi_date.month, cpi_date.day,
                        self.DATA_HOUR_UTC, 30, tzinfo=UTC,
                    ),
                    impact_level=1,  # NUCLEAR
                    description="Consumer Price Index (estimated date)",
                ))

        return events

    @staticmethod
    def _classify_event_impact(event_name: str) -> Optional[int]:
        """Clasifica el impacto de un evento por nombre."""
        event_upper = event_name.upper()

        # NUCLEAR (Nivel 1)
        nuclear_keywords = [
            "FOMC", "FED FUNDS", "INTEREST RATE", "FEDERAL RESERVE",
            "NON-FARM", "NONFARM", "NFP", "PAYROLL",
            "CPI", "CONSUMER PRICE INDEX",
        ]
        for kw in nuclear_keywords:
            if kw in event_upper:
                return 1

        # HIGH (Nivel 2)
        high_keywords = [
            "PCE", "PERSONAL CONSUMPTION",
            "FOMC MINUTES", "FED MINUTES",
            "ISM", "PMI", "PURCHASING MANAGER",
        ]
        for kw in high_keywords:
            if kw in event_upper:
                return 2

        # MODERATE (Nivel 3)
        moderate_keywords = [
            "RETAIL SALES", "GDP", "GROSS DOMESTIC",
            "INITIAL CLAIMS", "JOBLESS",
            "DURABLE GOODS", "HOUSING",
        ]
        for kw in moderate_keywords:
            if kw in event_upper:
                return 3

        return None  # No relevante

    @staticmethod
    def _normalize_event_name(event_name: str) -> str:
        """Normaliza nombres de eventos para deduplicación."""
        upper = event_name.upper()
        if "FOMC" in upper or "FED FUNDS" in upper or "INTEREST RATE" in upper:
            return "FOMC_DECISION"
        if "NON-FARM" in upper or "NONFARM" in upper or "NFP" in upper or "PAYROLL" in upper:
            return "NFP"
        if "CPI" in upper or "CONSUMER PRICE" in upper:
            return "CPI"
        if "PCE" in upper or "PERSONAL CONSUMPTION" in upper:
            return "PCE"
        if "ISM" in upper or "PMI" in upper:
            return "ISM_PMI"
        if "FOMC MINUTES" in upper or "FED MINUTES" in upper:
            return "FOMC_MINUTES"
        if "RETAIL" in upper:
            return "RETAIL_SALES"
        if "GDP" in upper:
            return "GDP"
        return event_name.upper().replace(" ", "_")[:30]


# ═══════════════════════════════════════════════════════════════
# WHALE FLOW READER
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# UNIFIED INTERFACE
# ═══════════════════════════════════════════════════════════════

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
