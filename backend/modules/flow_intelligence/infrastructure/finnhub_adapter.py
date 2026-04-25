"""
Flow Intelligence — Finnhub Calendar Adapter
=============================================
Infrastructure adapter: this is the ONLY file in this module that touches external APIs.
Domain code in whale_engine.py uses this via dependency injection.
"""
import logging
import os
from datetime import date, datetime, timedelta, UTC
from typing import Optional

logger = logging.getLogger(__name__)


class FinnhubCalendarAdapter:
    """Fetches economic calendar events from the Finnhub API."""

    def __init__(self):
        self._client = None
        self._available = False

    def _try_init(self):
        if self._client is not None:
            return
        try:
            import finnhub
            api_key = os.getenv("FINNHUB_API_KEY", "")
            if api_key:
                self._client = finnhub.Client(api_key=api_key)
                self._available = True
                logger.info("FinnhubCalendarAdapter: connected ✅")
        except (ImportError, Exception) as e:
            logger.info(f"FinnhubCalendarAdapter: not available ({e})")

    @property
    def is_available(self) -> bool:
        self._try_init()
        return self._available

    def fetch_events(self, from_date: date, to_date: date) -> list[dict]:
        """
        Raw event fetch from Finnhub. Returns list of dicts with keys:
        country, event, time/date, impact, etc.
        
        This adapter does NOT classify events — that's domain logic.
        """
        if not self.is_available:
            return []
        try:
            result = self._client.economic_calendar(
                _from=from_date.isoformat(),
                to=to_date.isoformat(),
            )
            # Filter US only at the adapter level (infrastructure concern)
            return [
                item for item in result.get("economicCalendar", [])
                if item.get("country", "") == "US"
            ]
        except Exception as e:
            logger.warning(f"FinnhubCalendarAdapter: fetch error: {e}")
            return []
