"""
Shared TimescaleDataStore singleton — thread-safe lazy initialization.
===========================================================================
All METAR services, daemons, and domain consumers that need a DataStore
should call `get_shared_store()` instead of `TimescaleDataStore()`.

This eliminates redundant TLS handshakes to Neon PostgreSQL. Each
`TimescaleDataStore()` creates its own `ThreadedConnectionPool` with
a TLS handshake (~200-400ms to Neon). With 11 METAR stations called
in parallel, that's 11 handshakes (~2-4 seconds of pure connection
overhead). A shared pool reduces this to 1 handshake per process.

Clean Architecture: This is infrastructure-level. No domain logic.
"""
import threading
from typing import Optional

_lock = threading.Lock()
_instance: Optional["TimescaleDataStore"] = None


def get_shared_store() -> "TimescaleDataStore":
    """Return a process-wide shared TimescaleDataStore instance.

    Thread-safe. The pool is created on first call and reused thereafter.
    The pool uses ThreadedConnectionPool (min=1, max=10) — enough for
    parallel METAR station fetching without contention.
    """
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                from backend.modules.shared.infrastructure.timescale_data_store import (
                    TimescaleDataStore,
                )
                _instance = TimescaleDataStore(min_conn=1, max_conn=10)
    return _instance
