"""
ChannelSnapshotPort — Domain Port for Persisted Channel Snapshots
===================================================================
ABC defining the contract for storing/loading ChannelSnapshot data.
Consumed by forensic tools, MetaLabeler, and entry/exit gates.

Clean Architecture: Domain layer. No infrastructure dependencies.
"""
import abc
from datetime import date
from typing import Optional

import pandas as pd

from backend.modules.shared.domain.entities.channel_snapshot import ChannelSnapshot


class ChannelSnapshotPort(abc.ABC):
    """Port for persisting and querying ChannelSnapshot time-series."""

    @abc.abstractmethod
    def save_snapshots_batch(
        self,
        ticker: str,
        timeframe: str,
        timestamps: list,
        snapshots: list[ChannelSnapshot],
        schema_version: int = 1,
    ) -> int:
        """Batch upsert snapshots. Returns number of rows affected."""
        ...

    @abc.abstractmethod
    def load_snapshots(
        self,
        ticker: str,
        timeframe: str = "1d",
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> pd.DataFrame:
        """Load snapshots as DataFrame with timestamp index."""
        ...

    @abc.abstractmethod
    def load_snapshot_at(
        self,
        ticker: str,
        timestamp,
        timeframe: str = "1d",
    ) -> Optional[ChannelSnapshot]:
        """Load a single snapshot at a specific timestamp."""
        ...

    @abc.abstractmethod
    def count_snapshots(self, ticker: str, timeframe: str = "1d") -> int:
        """Count existing snapshots for a ticker."""
        ...
