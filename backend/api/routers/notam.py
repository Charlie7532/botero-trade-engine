from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from backend.modules.entry_decision.domain.services.notam_incident_service import (
    evaluate_operational_notams,
    get_latest_circuit_breaker_notam,
    generate_notam_report,
)

router = APIRouter(prefix="/notam", tags=["Market NOTAM Operational Disruption Bulletins"])


@router.get("/report")
async def get_notam_report_endpoint(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns complete Operational Market NOTAM Disruption & Telemetry Report,
    including station freshness matrix, outdated station audit, and active disruption bulletins.
    """
    try:
        report = generate_notam_report(as_of_date=as_of_date)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/outdated-stations")
async def get_outdated_stations_endpoint(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns list of all outdated or stalled market stations detected in the NOTAM audit.
    """
    try:
        report = generate_notam_report(as_of_date=as_of_date)
        return {
            "timestamp_utc": report["timestamp_utc"],
            "as_of_date": report["as_of_date"],
            "benchmark_station": report["benchmark_station"],
            "benchmark_date": report["benchmark_date"],
            "outdated_count": report["outdated_stations_count"],
            "outdated_stations": report["outdated_stations"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/incidents")
async def get_operational_notams(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns active operational Market NOTAM bulletins (system disruptions, circuit breakers, outages).
    """
    try:
        notams = evaluate_operational_notams(as_of_date=as_of_date)
        return [n.to_dict() for n in notams]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/circuit-breaker")
async def get_circuit_breaker(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns latest active Macro/Volatility Circuit Breaker NOTAM bulletin.
    """
    try:
        cb = get_latest_circuit_breaker_notam(as_of_date=as_of_date)
        if not cb:
            return {"status": "CLEAR", "message": "No active circuit breaker NOTAM bulletin."}
        return cb.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
