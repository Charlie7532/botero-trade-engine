"""
Market METAR REST Router — FastAPI API Boundary
===============================================
Exposes zero-fallback Market METAR services for all 11 registered stations:
VIX, VVIX, PCR, F&G, SV5_Turbulence, SKEW, Credit, Yield Curve, Rotation, BSI, DXY.
Reads exclusively from Neon Vault using pure domain services.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from backend.modules.entry_decision.domain.exceptions import StrictDataPolicyError
from backend.modules.entry_decision.domain.services.vix_metar_service import get_vix_market_metar
from backend.modules.entry_decision.domain.services.vvix_metar_service import get_vvix_market_metar
from backend.modules.entry_decision.domain.services.pcr_metar_service import get_pcr_market_metar
from backend.modules.entry_decision.domain.services.fg_metar_service import get_fg_market_metar
from backend.modules.entry_decision.domain.services.sv5_turbulence_metar_service import get_sv5_turbulence_market_metar
from backend.modules.entry_decision.domain.services.skew_metar_service import get_skew_market_metar
from backend.modules.entry_decision.domain.services.credit_metar_service import get_credit_market_metar
from backend.modules.entry_decision.domain.services.yield_curve_metar_service import get_yield_curve_market_metar
from backend.modules.entry_decision.domain.services.rotation_metar_service import get_rotation_market_metar
from backend.modules.entry_decision.domain.services.bsi_metar_service import get_bsi_market_metar
from backend.modules.entry_decision.domain.services.dxy_metar_service import get_dxy_market_metar

router = APIRouter(prefix="/metar", tags=["Market METAR Multi-Station Telemetry"])

# ── Station code → (snapshot_key, live_compute_fn) mapping ──
_STATION_MAP = {
    "vix": ("vix/sigmet", get_vix_market_metar),
    "vvix": ("vvix/sigmet", get_vvix_market_metar),
    "pcr": ("pcr/sigmet", get_pcr_market_metar),
    "fg": ("fg/sigmet", get_fg_market_metar),
    "sv5_turbulence": ("sv5_turbulence/sigmet", get_sv5_turbulence_market_metar),
    "skew": ("skew/sigmet", get_skew_market_metar),
    "credit": ("credit/sigmet", get_credit_market_metar),
    "yield_curve": ("yield_curve/sigmet", get_yield_curve_market_metar),
    "rotation": ("rotation/sigmet", get_rotation_market_metar),
    "bsi": ("bsi/sigmet", get_bsi_market_metar),
    "dxy": ("dxy/sigmet", get_dxy_market_metar),
}


def _get_station_metar(station_code: str, as_of_date: Optional[str] = None) -> dict:
    """Read daemon-persisted snapshot; fall back to live compute if needed.

    - No as_of_date: read cached snapshot. Fall back to live if no snapshot.
    - With as_of_date: always live compute (historical query).
    """
    snap_key, live_fn = _STATION_MAP[station_code]

    if as_of_date:
        # Historical query — must live-compute
        metar = live_fn(as_of_date=as_of_date)
        return metar.to_dict()

    # Try cached snapshot first
    from backend.modules.shared.infrastructure.shared_store import get_shared_store
    store = get_shared_store()
    snapshot = store.load_mcp_latest(snap_key, "MARKET")
    if snapshot and isinstance(snapshot, dict) and snapshot.get("state_key"):
        return snapshot

    # No snapshot — live fallback
    metar = live_fn()
    return metar.to_dict()


@router.get("/vix")
async def get_vix_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic VIX Market METAR."""
    try:
        return _get_station_metar("vix", as_of_date)
    except StrictDataPolicyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vvix")
async def get_vvix_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic VVIX Market METAR."""
    try:
        return _get_station_metar("vvix", as_of_date)
    except StrictDataPolicyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pcr")
async def get_pcr_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative Put/Call Ratio Market METAR."""
    try:
        return _get_station_metar("pcr", as_of_date)
    except StrictDataPolicyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fg")
async def get_fg_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative Fear & Greed Market METAR."""
    try:
        return _get_station_metar("fg", as_of_date)
    except StrictDataPolicyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sv5-turbulence")
async def get_sv5_turbulence_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative Institutional Volume Turbulence (SV5_TURBULENCE) Market METAR."""
    try:
        return _get_station_metar("sv5_turbulence", as_of_date)
    except StrictDataPolicyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/skew")
async def get_skew_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic CBOE SKEW (Tail Risk) Market METAR."""
    try:
        return _get_station_metar("skew", as_of_date)
    except StrictDataPolicyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/credit")
async def get_credit_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic High Yield Corporate Credit Stress Market METAR."""
    try:
        return _get_station_metar("credit", as_of_date)
    except StrictDataPolicyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/yield-curve")
async def get_yield_curve_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic Macro Yield Curve Spread (TNX - IRX) Market METAR."""
    try:
        return _get_station_metar("yield_curve", as_of_date)
    except StrictDataPolicyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rotation")
async def get_rotation_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic Sector Rotation Intelligence Market METAR."""
    try:
        return _get_station_metar("rotation", as_of_date)
    except StrictDataPolicyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bsi")
async def get_bsi_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic Breadth Shock Index (S5TW) Market METAR."""
    try:
        return _get_station_metar("bsi", as_of_date)
    except StrictDataPolicyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dxy")
async def get_dxy_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic DXY (US Dollar Index) Market METAR."""
    try:
        return _get_station_metar("dxy", as_of_date)
    except StrictDataPolicyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all")
async def get_all_metar_stations(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns an aggregated dictionary of all 11 registered Market METAR stations."""
    results = {}
    for name in _STATION_MAP:
        try:
            results[name] = _get_station_metar(name, as_of_date)
        except StrictDataPolicyError as e:
            results[name] = {
                "status": "METAR_NOT_AVAILABLE",
                "detail": str(e)
            }
        except Exception as e:
            results[name] = {
                "status": "ERROR",
                "detail": str(e)
            }

    active = sum(
        1 for v in results.values()
        if "metar_id" in v
    )

    return {
        "registered_count": len(_STATION_MAP),
        "active_count": active,
        "metars": results
    }


@router.get("/convergence")
async def get_convergence_report(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns authoritative Multi-Station Convergence Report.
    Includes Bullish Score, Weighted Composite EV, Rarity Audit (N<10),
    Cross-Station Signals (Distribution Battle, Floor Veto, Confirmed Dip),
    and Unified Guidance with explicit Horizon (1D, 3D, 5D, WAIT).
    """
    try:
        from backend.modules.entry_decision.domain.services.convergence_compositor import ConvergenceCompositor
        compositor = ConvergenceCompositor()
        report = compositor.compute(as_of_date=as_of_date)
        return report.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/weather")
async def get_unified_weather(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Unified Market Weather endpoint — single compositor call, zero redundancy.

    Returns consolidated:
    - METAR convergence (11 stations)
    - TAF dispersion cones (composite + per-station)
    - SIGMET hazard bulletins (severe weather only)
    - NOTAM operational disruptions

    This is the primary operational endpoint. Individual station endpoints
    (/metar/vix, /sigmet/active, /taf/composite) remain available for
    targeted queries but invoke their own pipelines independently.
    """
    import time as _time
    t0 = _time.time()

    try:
        from backend.modules.entry_decision.domain.services.convergence_compositor import ConvergenceCompositor
        from backend.modules.entry_decision.domain.services.market_sigmet_hazard_service import (
            evaluate_sigmets_from_metar_dicts,
        )
        from backend.modules.entry_decision.domain.services.taf_service import (
            compute_composite_taf_from_summaries,
        )
        from backend.modules.entry_decision.domain.services.notam_incident_service import (
            evaluate_operational_notams,
        )

        # ── Single compositor call ──────────────────────────────────────
        compositor = ConvergenceCompositor()
        report = compositor.compute(as_of_date=as_of_date)

        # ── SIGMET from pre-computed METAR snapshots ────────────────────
        sigmets = evaluate_sigmets_from_metar_dicts(
            metar_dicts=report.metar_snapshots,
            family_report=report.family_sequence,
            as_of_date=report.as_of_date,
        )

        # ── TAF from station summaries ──────────────────────────────────
        taf_composite = compute_composite_taf_from_summaries(report.station_summaries)
        taf_composite["as_of_date"] = report.as_of_date
        taf_composite["timestamp_utc"] = report.timestamp_utc

        # ── NOTAM (independent — reads Vault freshness directly) ────────
        try:
            notams = evaluate_operational_notams(as_of_date=as_of_date)
            notam_data = [n.to_dict() for n in notams]
        except Exception:
            notam_data = []

        t1 = _time.time()

        return {
            "as_of_date": report.as_of_date,
            "timestamp_utc": report.timestamp_utc,
            "execution_time_ms": round((t1 - t0) * 1000, 2),
            "metar": report.to_dict(),
            "taf": taf_composite,
            "sigmet": {
                "status": "CLEAR" if len(sigmets) == 0 else "HAZARD_WARNING",
                "active_sigmet_count": len(sigmets),
                "sigmets": [s.to_dict() for s in sigmets],
            },
            "notam": notam_data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

