"""
Market SIGMET REST Router — FastAPI API Boundary
================================================
Exposes zero-fallback Market SIGMET services for VIX, VVIX, Fear & Greed, Put/Call Ratio, and SV5_Turbulence.
Reads exclusively from Neon Vault using pure domain services.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from backend.modules.entry_decision.domain.services.vix_sigmet_service import (
    get_vix_market_sigmet,
    StrictDataPolicyError as VIXStrictError
)
from backend.modules.entry_decision.domain.services.vvix_sigmet_service import (
    get_vvix_market_sigmet,
    StrictDataPolicyError as VVIXStrictError
)
from backend.modules.entry_decision.domain.services.pcr_sigmet_service import (
    get_pcr_market_sigmet,
    StrictDataPolicyError as PCRStrictError
)
from backend.modules.entry_decision.domain.services.fg_sigmet_service import (
    get_fg_market_sigmet,
    StrictDataPolicyError as FGStrictError
)
from backend.modules.entry_decision.domain.services.sv5_turbulence_sigmet_service import (
    get_sv5_turbulence_market_sigmet,
    StrictDataPolicyError as TurbStrictError
)
from backend.modules.entry_decision.domain.services.skew_sigmet_service import (
    get_skew_market_sigmet,
    StrictDataPolicyError as SKEWStrictError
)

router = APIRouter(prefix="/sigmet", tags=["Market SIGMET Intelligence"])


@router.get("/vix")
async def get_vix_sigmet(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns authoritative 3-Day Fast Kinematic VIX Market SIGMET.
    Strict Data Policy: Zero Fallbacks. Raises 404 if date is missing or unupdated in Vault.
    """
    try:
        sigmet = get_vix_market_sigmet(as_of_date=as_of_date)
        return sigmet.to_dict()
    except VIXStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vvix")
async def get_vvix_sigmet(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns authoritative 3-Day Fast Kinematic VVIX Market SIGMET.
    Strict Data Policy: Zero Fallbacks. Raises 404 if date is missing or unupdated in Vault.
    """
    try:
        sigmet = get_vvix_market_sigmet(as_of_date=as_of_date)
        return sigmet.to_dict()
    except VVIXStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pcr")
async def get_pcr_sigmet(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns authoritative Put/Call Ratio Market SIGMET.
    Strict Data Policy: Zero Fallbacks. Raises 404 if date is missing or unupdated in Vault.
    """
    try:
        sigmet = get_pcr_market_sigmet(as_of_date=as_of_date)
        return sigmet.to_dict()
    except PCRStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fg")
async def get_fg_sigmet(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns authoritative Fear & Greed Market SIGMET.
    Strict Data Policy: Zero Fallbacks. Raises 404 if date is missing or unupdated in Vault.
    """
    try:
        sigmet = get_fg_market_sigmet(as_of_date=as_of_date)
        return sigmet.to_dict()
    except FGStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sv5-turbulence")
async def get_sv5_turbulence_sigmet(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns authoritative Institutional Volume Turbulence (SV5_TURBULENCE) Market SIGMET.
    Strict Data Policy: Zero Fallbacks. Raises 404 if date is missing or unupdated in Vault.
    """
    try:
        sigmet = get_sv5_turbulence_market_sigmet(as_of_date=as_of_date)
        return sigmet.to_dict()
    except TurbStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/skew")
async def get_skew_sigmet(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns authoritative 3-Day Fast Kinematic CBOE SKEW (Tail Risk) Market SIGMET.
    Strict Data Policy: Zero Fallbacks. Raises 404 if date is missing or unupdated in Vault.
    """
    try:
        sigmet = get_skew_market_sigmet(as_of_date=as_of_date)
        return sigmet.to_dict()
    except SKEWStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

