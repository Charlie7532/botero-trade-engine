"""
Market SIGMET REST Router — FastAPI API Boundary (Severe Weather Hazard Bulletins)
===================================================================================
Exposes severe market weather hazard bulletins (SIGMETs).
In aviation, SIGMETs are NOT routine daily reports — they are issued ONLY when severe
market hazards (volatility panic, extreme SKEW tail risk, curve inversion) are active.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from backend.modules.entry_decision.domain.services.market_sigmet_hazard_service import (
    evaluate_market_sigmets
)

router = APIRouter(prefix="/sigmet", tags=["Market SIGMET Severe Weather Hazard Bulletins"])


@router.get("/active")
@router.get("/all")
@router.get("")
async def get_active_market_sigmets(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns active severe weather Market SIGMET bulletins (hazards, panic shocks, extreme anomalies).
    If no severe weather hazards are active, returns an empty list with status: CLEAR.
    """
    try:
        sigmets = evaluate_market_sigmets(as_of_date=as_of_date)
        return {
            "status": "CLEAR" if len(sigmets) == 0 else "HAZARD_WARNING",
            "active_sigmet_count": len(sigmets),
            "sigmets": [s.to_dict() for s in sigmets]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
