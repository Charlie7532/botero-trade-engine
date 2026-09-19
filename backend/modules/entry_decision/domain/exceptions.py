"""
Shared Domain Exceptions — METAR Pipeline
==========================================
Exceptions shared across all METAR station services.
Consolidates 11 identical per-service definitions into one canonical source.
"""


class StrictDataPolicyError(Exception):
    """Raised when Vault data is insufficient or unavailable for a METAR station.

    This replaces 11 identical per-service definitions. All METAR services
    and their API router handlers should import from here.
    """
    pass
