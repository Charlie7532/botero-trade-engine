"""
Calendar Data Port — Interface for economic event calendar providers.

Implementations: FinnhubCalendarAdapter (infrastructure/)
"""
from abc import ABC, abstractmethod
from datetime import date


class CalendarDataPort(ABC):
    """Interface for fetching economic calendar events."""

    @abstractmethod
    def fetch_events(self, start_date: date, end_date: date) -> list[dict]:
        """
        Fetch economic calendar events for a date range.

        Returns:
            List of event dicts with 'event', 'time'/'date', and impact info.
        """
        ...

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Whether this calendar source is currently available."""
        ...
