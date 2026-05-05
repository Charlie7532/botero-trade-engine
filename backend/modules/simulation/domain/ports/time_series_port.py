"""
Time-Series Port — Backward Compatibility Re-export
======================================================
CANONICAL LOCATION: backend.modules.shared.domain.ports.time_series_port

All new code should import from the shared module directly.
"""
from backend.modules.shared.domain.ports.time_series_port import TimeSeriesPort

__all__ = ["TimeSeriesPort"]
