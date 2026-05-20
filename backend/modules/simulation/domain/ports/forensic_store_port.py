from abc import ABC, abstractmethod
from backend.modules.simulation.domain.entities.signal_forensic_label import SignalForensicLabel
from backend.modules.simulation.domain.entities.entry_report_card import EntryReportCard
from backend.modules.simulation.domain.entities.exit_report_card import ExitReportCard

class ForensicStorePort(ABC):
    """Port defining the persistence interface for Oracle Forensic Labels and Report Cards."""

    @abstractmethod
    def save_entry_labels(self, labels: list[SignalForensicLabel]) -> None:
        """Persist a list of entry forensic labels to engine.entry_forensic_labels."""
        pass

    @abstractmethod
    def save_exit_labels(self, labels: list[SignalForensicLabel]) -> None:
        """Persist a list of exit forensic labels to engine.exit_forensic_labels."""
        pass

    @abstractmethod
    def save_entry_report_card(self, card: EntryReportCard) -> None:
        """Persist an entry report card to engine.entry_report_cards."""
        pass

    @abstractmethod
    def save_exit_report_card(self, card: ExitReportCard) -> None:
        """Persist an exit report card to engine.exit_report_cards."""
        pass
