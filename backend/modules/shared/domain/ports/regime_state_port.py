"""
RegimeStatePort — Domain Port for Regime State Persistence
=============================================================
ABC defining the contract for persisting and querying regime
state transitions with full temporal context.

Writers: Daemons and dedicated transition use cases only.
Readers: Gates, entry hubs, risk managers, Oracle Trainer.

Clean Architecture: Domain layer. No infrastructure dependencies.
Precedent: TickerProfilePort (shared/domain/ports/).
"""
import abc
from datetime import datetime
from typing import Optional

from backend.modules.shared.domain.entities.state_snapshot import StateSnapshot


class RegimeStatePort(abc.ABC):
    """Port for regime state persistence and temporal queries.

    Implements Stateful-First design (AGENTS.md Rules 15-16):
    - Every classifier persists transitions via this port
    - Consumers receive StateSnapshot, not raw strings
    - Persist-then-Read: state written to Vault before consumption
    """

    @abc.abstractmethod
    def get_current(
        self, key: str, reference_date: Optional[datetime] = None,
    ) -> Optional[StateSnapshot]:
        """Get the active state for a key.

        Args:
            key: Structured key (e.g. "vol:quality:MARKET").
            reference_date: None = current active state (production).
                           datetime = state active at that date (backtest).

        Returns:
            The StateSnapshot that was active at reference_date, or None
            if no state has been recorded for this key.
        """
        ...

    @abc.abstractmethod
    def commit_transition(
        self,
        key: str,
        next_state: str,
        trigger: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Atomically close current state and open next state.

        MUST execute within a single SQL transaction:
          1. UPDATE ... SET closed_at = ts WHERE key = X AND closed_at IS NULL
          2. INSERT new row with current_state = next_state, duration_bars = 1

        If no active state exists for the key, only step 2 executes
        (first-ever state for this key) with previous_state = None.

        Args:
            key: Structured key.
            next_state: The new regime label.
            trigger: Human-readable cause (e.g. "VIX_ZSCORE=2.3").
            timestamp: Override for backfill. None = NOW().
            metadata: Optional context dict (sensor values at transition).
        """
        ...

    @abc.abstractmethod
    def increment_duration(self, key: str) -> None:
        """Increment duration_bars by 1 for the active state of a key.

        Called daily by daemon for states that did NOT transition.
        Avoids dynamic computation from timestamps (backtest clock bug).
        """
        ...

    @abc.abstractmethod
    def load_history(
        self, key: str, start: datetime, end: datetime,
    ) -> list[StateSnapshot]:
        """Load regime transition history for a key within a date range.

        Used by:
          - Oracle Trainer for per-regime forensic autopsy
          - trade-forensics for decision context reconstruction
          - Backfill verification

        Returns list ordered by entered_at ASC.
        """
        ...
