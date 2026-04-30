"""
Historical Data Port — Compatibility Layer
=============================================
DEPRECATED: Use TimeSeriesPort for time-series operations
and TradingStatePort for relational state operations.

This file re-exports TimeSeriesPort as HistoricalDataPort
so that existing use cases (oracle_backtest, calibrate_strategy,
pre_trade_gate, etc.) continue to work without modification.

Migration path: gradually replace HistoricalDataPort imports
with TimeSeriesPort in each use case.
"""
from backend.modules.simulation.domain.ports.time_series_port import TimeSeriesPort

# Backward compatibility — existing use cases import HistoricalDataPort
HistoricalDataPort = TimeSeriesPort
