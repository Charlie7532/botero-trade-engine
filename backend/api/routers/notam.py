"""
Market NOTAM REST Router — FastAPI API Boundary
===============================================
Exposes zero-fallback Market NOTAM services for VIX, Fear & Greed, and Put/Call Ratio.
Reads exclusively from Neon Vault using pure domain services.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from backend.modules.entry_decision.domain.services.vix_notam_service import (
    get_vix_market_notam,
    StrictDataPolicyError as VIXStrictError
)
from backend.modules.entry_decision.domain.services.fg_notam_service import (
    get_fg_market_notam,
    StrictDataPolicyError as FGStrictError
)
from backend.modules.entry_decision.domain.services.pcr_notam_service import (
    get_pcr_market_notam,
    StrictDataPolicyError as PCRStrictError
)
from backend.modules.entry_decision.domain.services.vvix_notam_service import (
    get_vvix_market_notam,
    StrictDataPolicyError as VVIXStrictError
)

router = APIRouter(prefix="/notam", tags=["Market NOTAM Intelligence"])


@router.get("/vix")
async def get_vix_notam(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns authoritative 3-Day Fast Kinematic VIX Market NOTAM.
    Strict Data Policy: Zero Fallbacks. Raises 404 if date is missing or unupdated in Vault.
    """
    try:
        notam = get_vix_market_notam(as_of_date=as_of_date)
        return notam.to_dict()
    except VIXStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fg")
async def get_fg_notam(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns authoritative Fear & Greed Market NOTAM.
    Strict Data Policy: Zero Fallbacks. Raises 404 if date is missing or unupdated in Vault.
    """
    try:
        notam = get_fg_market_notam(as_of_date=as_of_date)
        return notam.to_dict()
    except FGStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pcr")
async def get_pcr_notam(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns authoritative Put/Call Ratio Market NOTAM.
    Strict Data Policy: Zero Fallbacks. Raises 404 if date is missing or unupdated in Vault.
    """
    try:
        notam = get_pcr_market_notam(as_of_date=as_of_date)
        return notam.to_dict()
    except PCRStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vvix")
async def get_vvix_notam(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns authoritative 3-Day Fast Kinematic VVIX Market NOTAM.
    Strict Data Policy: Zero Fallbacks. Raises 404 if date is missing or unupdated in Vault.
    """
    try:
        notam = get_vvix_market_notam(as_of_date=as_of_date)
        return notam.to_dict()
    except VVIXStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

