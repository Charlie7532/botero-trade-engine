"""
TimescaleDB Data Store — Backward Compatibility Re-export
============================================================
CANONICAL LOCATION: backend.modules.shared.infrastructure.timescale_data_store

All new code should import from the shared module directly.
"""
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

__all__ = ["TimescaleDataStore"]
