"""
Market NOTAM REST Router — FastAPI API Boundary (Operational Incidents & Disruption Bulletins)
============================================================================================
Exposes operational Market NOTAM bulletins for system disruptions, circuit breakers,
and pipeline outages.
"""
from fastapi import APIRouter, HTTPException

from backend.modules.entry_decision.domain.services.notam_incident_service import (
    evaluate_operational_notams,
    get_latest_circuit_breaker_notam
)

router = APIRouter(prefix="/notam", tags=["Market NOTAM Operational Disruption Bulletins"])


@router.get("/incidents")
async def get_operational_notams():
    """
    Returns active operational Market NOTAM bulletins (system disruptions, circuit breakers, outages).
    """
    try:
        notams = evaluate_operational_notams()
        return [n.to_dict() for n in notams]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/circuit-breaker")
async def get_circuit_breaker():
    """
    Returns latest active Macro/Volatility Circuit Breaker NOTAM bulletin.
    """
    try:
        cb = get_latest_circuit_breaker_notam()
        if not cb:
            return {"status": "CLEAR", "message": "No active circuit breaker NOTAM bulletin."}
        return cb.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
