import logging
from datetime import datetime, date, timedelta, UTC
from typing import Optional

from backend.modules.flow_intelligence.domain.entities.whale_events import MacroEvent

logger = logging.getLogger(__name__)

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

    def __init__(self, external_events_fetcher=None):
        self._external_fetcher = external_events_fetcher  # Optional CalendarDataPort
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

        # 1. Fetch external events if a fetcher is injected
        if self._external_fetcher is not None:
            try:
                end_date = today + timedelta(days=days_ahead)
                raw_events = self._external_fetcher.fetch_events(today, end_date)
                events.extend(self._parse_external_events(raw_events))
            except Exception as e:
                logger.warning(f"Error fetching external calendar events: {e}")

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

    def _parse_external_events(self, raw_events: list[dict]) -> list[MacroEvent]:
        """Parses raw event dicts from any external calendar source."""
        events = []
        try:
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
            logger.warning(f"Error processing external events: {e}")
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
