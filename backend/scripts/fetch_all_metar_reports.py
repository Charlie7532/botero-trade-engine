#!/usr/bin/env python3
"""
Fetch All 9 Live METAR Reports from Neon Vault
================================================
Generates real-time Market METAR reports for all 9 indicators.
"""
import sys
import json
import logging
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.entry_decision.domain.services.vix_metar_service import get_vix_market_metar
from backend.modules.entry_decision.domain.services.vvix_metar_service import get_vvix_market_metar
from backend.modules.entry_decision.domain.services.pcr_metar_service import get_pcr_market_metar
from backend.modules.entry_decision.domain.services.fg_metar_service import get_fg_market_metar
from backend.modules.entry_decision.domain.services.sv5_turbulence_metar_service import get_sv5_turbulence_market_metar
from backend.modules.entry_decision.domain.services.skew_metar_service import get_skew_market_metar
from backend.modules.entry_decision.domain.services.credit_metar_service import get_credit_market_metar
from backend.modules.entry_decision.domain.services.yield_curve_metar_service import get_yield_curve_market_metar
from backend.modules.entry_decision.domain.services.rotation_metar_service import get_rotation_market_metar

logging.basicConfig(level=logging.ERROR)

def fetch_all():
    metars = {}
    
    services = [
        ("VIX", get_vix_market_metar),
        ("VVIX", get_vvix_market_metar),
        ("CBOE_PCR", get_pcr_market_metar),
        ("FG", get_fg_market_metar),
        ("SV5_TURBULENCE", get_sv5_turbulence_market_metar),
        ("SKEW", get_skew_market_metar),
        ("CREDIT", get_credit_market_metar),
        ("YIELD_CURVE", get_yield_curve_market_metar),
        ("ROTATION", get_rotation_market_metar),
    ]

    for name, fn in services:
        try:
            s = fn()
            metars[name] = s
        except Exception as e:
            metars[name] = {"error": str(e)}

    print(json.dumps(metars, indent=2, default=str))

if __name__ == "__main__":
    fetch_all()
