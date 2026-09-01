"""
Market METAR REST Router — FastAPI API Boundary
===============================================
Exposes zero-fallback Market METAR services for all 11 registered stations:
VIX, VVIX, PCR, F&G, SV5_Turbulence, SKEW, Credit, Yield Curve, Rotation, BSI, DXY.
Reads exclusively from Neon Vault using pure domain services.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from backend.modules.entry_decision.domain.services.vix_metar_service import (
    get_vix_market_metar,
    StrictDataPolicyError as VIXStrictError
)
from backend.modules.entry_decision.domain.services.vvix_metar_service import (
    get_vvix_market_metar,
    StrictDataPolicyError as VVIXStrictError
)
from backend.modules.entry_decision.domain.services.pcr_metar_service import (
    get_pcr_market_metar,
    StrictDataPolicyError as PCRStrictError
)
from backend.modules.entry_decision.domain.services.fg_metar_service import (
    get_fg_market_metar,
    StrictDataPolicyError as FGStrictError
)
from backend.modules.entry_decision.domain.services.sv5_turbulence_metar_service import (
    get_sv5_turbulence_market_metar,
    StrictDataPolicyError as TurbStrictError
)
from backend.modules.entry_decision.domain.services.skew_metar_service import (
    get_skew_market_metar,
    StrictDataPolicyError as SKEWStrictError
)
from backend.modules.entry_decision.domain.services.credit_metar_service import (
    get_credit_market_metar,
    StrictDataPolicyError as CreditStrictError
)
from backend.modules.entry_decision.domain.services.yield_curve_metar_service import (
    get_yield_curve_market_metar,
    StrictDataPolicyError as YieldCurveStrictError
)
from backend.modules.entry_decision.domain.services.rotation_metar_service import (
    get_rotation_market_metar,
    StrictDataPolicyError as RotationStrictError
)
from backend.modules.entry_decision.domain.services.bsi_metar_service import (
    get_bsi_market_metar,
    StrictDataPolicyError as BSIStrictError
)
from backend.modules.entry_decision.domain.services.dxy_metar_service import (
    get_dxy_market_metar,
    StrictDataPolicyError as DXYStrictError
)

router = APIRouter(prefix="/metar", tags=["Market METAR Multi-Station Telemetry"])


@router.get("/vix")
async def get_vix_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic VIX Market METAR."""
    try:
        metar = get_vix_market_metar(as_of_date=as_of_date)
        return metar.to_dict()
    except VIXStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vvix")
async def get_vvix_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic VVIX Market METAR."""
    try:
        metar = get_vvix_market_metar(as_of_date=as_of_date)
        return metar.to_dict()
    except VVIXStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pcr")
async def get_pcr_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative Put/Call Ratio Market METAR."""
    try:
        metar = get_pcr_market_metar(as_of_date=as_of_date)
        return metar.to_dict()
    except PCRStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fg")
async def get_fg_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative Fear & Greed Market METAR."""
    try:
        metar = get_fg_market_metar(as_of_date=as_of_date)
        return metar.to_dict()
    except FGStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sv5-turbulence")
async def get_sv5_turbulence_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative Institutional Volume Turbulence (SV5_TURBULENCE) Market METAR."""
    try:
        metar = get_sv5_turbulence_market_metar(as_of_date=as_of_date)
        return metar.to_dict()
    except TurbStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/skew")
async def get_skew_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic CBOE SKEW (Tail Risk) Market METAR."""
    try:
        metar = get_skew_market_metar(as_of_date=as_of_date)
        return metar.to_dict()
    except SKEWStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/credit")
async def get_credit_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic High Yield Corporate Credit Stress Market METAR."""
    try:
        metar = get_credit_market_metar(as_of_date=as_of_date)
        return metar.to_dict()
    except CreditStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/yield-curve")
async def get_yield_curve_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic Macro Yield Curve Spread (TNX - IRX) Market METAR."""
    try:
        metar = get_yield_curve_market_metar(as_of_date=as_of_date)
        return metar.to_dict()
    except YieldCurveStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rotation")
async def get_rotation_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic Sector Rotation Intelligence Market METAR."""
    try:
        metar = get_rotation_market_metar(as_of_date=as_of_date)
        return metar.to_dict()
    except RotationStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bsi")
async def get_bsi_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic Breadth Shock Index (S5TW) Market METAR."""
    try:
        metar = get_bsi_market_metar(as_of_date=as_of_date)
        return metar.to_dict()
    except BSIStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dxy")
async def get_dxy_metar(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """Returns authoritative 3-Day Fast Kinematic DXY (US Dollar Index) Market METAR."""
    try:
        metar = get_dxy_market_metar(as_of_date=as_of_date)
        return metar.to_dict()
    except DXYStrictError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all")
@router.get("")
async def get_all_metars(
    as_of_date: Optional[str] = Query(None, description="Target date string YYYY-MM-DD")
):
    """
    Returns an aggregated dictionary of all 11 registered Market METAR stations.
    """
    indicators = {
        "vix": (get_vix_market_metar, VIXStrictError),
        "vvix": (get_vvix_market_metar, VVIXStrictError),
        "pcr": (get_pcr_market_metar, PCRStrictError),
        "fg": (get_fg_market_metar, FGStrictError),
        "sv5_turbulence": (get_sv5_turbulence_market_metar, TurbStrictError),
        "skew": (get_skew_market_metar, SKEWStrictError),
        "credit": (get_credit_market_metar, CreditStrictError),
        "yield_curve": (get_yield_curve_market_metar, YieldCurveStrictError),
        "rotation": (get_rotation_market_metar, RotationStrictError),
        "bsi": (get_bsi_market_metar, BSIStrictError),
        "dxy": (get_dxy_market_metar, DXYStrictError),
    }

    results = {}
    for name, (fn, exc_type) in indicators.items():
        try:
            metar = fn(as_of_date=as_of_date)
            results[name] = metar.to_dict()
        except exc_type as e:
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
        "registered_count": len(indicators),
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

