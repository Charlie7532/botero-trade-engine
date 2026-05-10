"""
Alert Port — Domain Interface
================================
Abstract port for alert persistence. Infrastructure adapters
implement this to store alerts in PostgreSQL or any other backend.
"""
from abc import ABC, abstractmethod
from typing import Optional
from backend.modules.shared.domain.entities.alert_entities import Alert, InstrumentHealth


class AlertPort(ABC):
    """Interface for alert persistence and retrieval."""

    @abstractmethod
    def save_alert(self, alert: Alert) -> None:
        """Persist a new alert."""
        ...

    @abstractmethod
    def get_active_alerts(
        self,
        category: Optional[str] = None,
        ticker: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> list[Alert]:
        """Retrieve unresolved alerts, optionally filtered."""
        ...

    @abstractmethod
    def acknowledge_alert(self, alert_id: int) -> None:
        """Mark an alert as acknowledged (seen by operator)."""
        ...

    @abstractmethod
    def resolve_alert(self, alert_id: int) -> None:
        """Mark an alert as resolved."""
        ...


class InstrumentHealthPort(ABC):
    """Interface for progressive instrument health tracking.

    Replaces binary InstrumentBlacklistPort with gradual degradation.
    """

    @abstractmethod
    def get_health(self, ticker: str, department: str) -> InstrumentHealth:
        """Get current health status for a ticker/department."""
        ...

    @abstractmethod
    def update_health(self, health: InstrumentHealth) -> None:
        """Persist updated health status."""
        ...

    @abstractmethod
    def get_wounded_or_worse(self, department: str) -> list[InstrumentHealth]:
        """Return all instruments with status WOUNDED or DEATH."""
        ...
