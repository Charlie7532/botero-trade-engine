"""
DEPRECATED: sv5_turbulence_notam_service.py
============================================
Reclassified to SIGMET protocol. Import from sv5_turbulence_sigmet_service instead.
"""
from backend.modules.entry_decision.domain.services.sv5_turbulence_sigmet_service import (
    get_sv5_turbulence_market_sigmet as get_sv5_turbulence_market_notam,
    MarketSIGMET as MarketNOTAM,
    StrictDataPolicyError
)
