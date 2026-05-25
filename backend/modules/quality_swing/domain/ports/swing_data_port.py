"""
Swing Data Port — Interface for market data access.

Implementations live in quality_swing/infrastructure/.
"""
from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Optional

import pandas as pd

if TYPE_CHECKING:
    from backend.modules.shared.domain.entities.state_snapshot import StateSnapshot


class SwingDataPort(ABC):
    """Interface for fetching OHLCV data needed by SwingGate."""

    @abstractmethod
    def load_ohlc(
        self,
        ticker: str,
        timeframe: str = "1d",
        start: Optional[date] = None,
    ) -> Optional[pd.DataFrame]:
        """Load OHLCV bars for a ticker.

        Returns DataFrame with columns: open, high, low, close, volume.
        """
        ...

    @abstractmethod
    def load_vol_regime_label(self) -> str:
        """Load current volatility regime label for Quality department.

        Returns one of: NORMAL, COMPLACENT, ELEVATED, CRISIS.
        """
        ...

    def load_vol_regime_state(self) -> Optional["StateSnapshot"]:
        """Load current vol regime as StateSnapshot with temporal context.

        Returns StateSnapshot with current_state, previous_state,
        duration_bars, entered_at, trigger_event.
        Returns None if no regime state persisted yet (caller falls
        back to load_vol_regime_label).

        Default implementation returns None — backward compatible with
        existing adapters that haven't been updated yet.
        """
        return None

