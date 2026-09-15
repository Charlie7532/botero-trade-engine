"""
TAF (Terminal Market Forecast) API Router
==========================================
Exposes the dispersion cone computation per-station and composite.

Endpoints:
  GET /api/taf/{station}  — Single station TAF cone
  GET /api/taf/composite  — Composite market TAF from all 11 stations
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime

from backend.modules.entry_decision.domain.services.taf_service import (
    compute_taf_cone, compute_composite_taf, TafCone,
)

router = APIRouter(prefix="/api/taf", tags=["TAF — Terminal Market Forecast"])

STATION_LOOKUPS = {
    "vix": ("backend.modules.entry_decision.domain.rules.vix_lookup", "vix_lookup", "lookup_vix_guidance"),
    "vvix": ("backend.modules.entry_decision.domain.rules.vvix_lookup", "vvix_lookup", "lookup_vvix_guidance"),
    "pcr": ("backend.modules.entry_decision.domain.rules.pcr_lookup", "pcr_lookup", "lookup_pcr_guidance"),
    "fg": ("backend.modules.entry_decision.domain.rules.fg_lookup", "fg_lookup", "lookup_fg_guidance"),
    "sv5_turbulence": ("backend.modules.entry_decision.domain.rules.sv5_turbulence_lookup", "sv5_turbulence_lookup", "lookup_sv5_turbulence_guidance"),
    "skew": ("backend.modules.entry_decision.domain.rules.skew_lookup", "skew_lookup", "lookup_skew_guidance"),
    "credit": ("backend.modules.entry_decision.domain.rules.credit_lookup", "credit_lookup", "lookup_credit_guidance"),
    "yield_curve": ("backend.modules.entry_decision.domain.rules.yield_curve_lookup", "yield_curve_lookup", "lookup_yield_curve_guidance"),
    "rotation": ("backend.modules.entry_decision.domain.rules.rotation_lookup", "rotation_lookup", "lookup_rotation_guidance"),
    "bsi": ("backend.modules.entry_decision.domain.rules.bsi_lookup", "bsi_lookup", "lookup_bsi_guidance"),
    "dxy": ("backend.modules.entry_decision.domain.rules.dxy_lookup", "dxy_lookup", "lookup_dxy_guidance"),
}


def _guidance_to_taf(station: str, guidance) -> Optional[TafCone]:
    """Extract TAF cone from a lookup guidance object."""
    if guidance is None:
        return None
    vec = guidance.to_vector()
    zz25 = vec.get("zz25", {})
    zz50 = vec.get("zz50", {})
    zz75 = vec.get("zz75", {})
    div_regime = vec.get("divergence_regime", "NEUTRAL")
    return compute_taf_cone(
        station=station,
        state_key=vec.get("state_key", ""),
        zz25=zz25,
        zz50=zz50,
        zz75=zz75,
        divergence_regime=div_regime,
    )


@router.get("/composite")
async def get_composite_taf(
    as_of_date: Optional[str] = Query(None, description="Date YYYY-MM-DD"),
):
    """Composite market TAF from all 11 stations (current values from Vault)."""
    try:
        from backend.modules.entry_decision.domain.services.convergence_compositor import ConvergenceCompositor
        compositor = ConvergenceCompositor()
        report = compositor.compute(as_of_date=as_of_date)
        
        cones = []
        for station, summary in report.station_summaries.items():
            state_key = summary.get("state_key", "")
            # Extract zz25/50/75 from the station summary
            # The summary doesn't contain full zz data, so we need to call lookups
            mod_path, adapter_name, func_name = STATION_LOOKUPS.get(station, (None, None, None))
            if not mod_path:
                continue
            import importlib
            mod = importlib.import_module(mod_path)
            adapter = getattr(mod, adapter_name)
            # Re-derive from the state's fact store data
            states = adapter.states
            state_data = states.get(state_key, {})
            if not state_data:
                continue
            zz25 = state_data.get("zz25", {})
            zz50 = state_data.get("zz50", {})
            zz75 = state_data.get("zz75", {})
            div = state_data.get("divergence_regime", "NEUTRAL")
            cone = compute_taf_cone(station, state_key, zz25, zz50, zz75, div)
            cones.append(cone)
        
        composite = compute_composite_taf(cones)
        composite["as_of_date"] = report.as_of_date
        composite["timestamp_utc"] = report.timestamp_utc
        return composite
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{station}")
async def get_station_taf(
    station: str,
    val: Optional[float] = Query(None, description="Current indicator value"),
    d3_speed: float = Query(0.0, description="D3 velocity"),
):
    """TAF cone for a single station at a given value."""
    station = station.lower().replace("-", "_")
    if station not in STATION_LOOKUPS:
        raise HTTPException(status_code=404, detail=f"Unknown station: {station}")
    
    mod_path, adapter_name, func_name = STATION_LOOKUPS[station]
    try:
        import importlib
        mod = importlib.import_module(mod_path)
        adapter = getattr(mod, adapter_name)
        func = getattr(adapter, func_name)
        guidance = func(val=val, d3_speed=d3_speed)
        cone = _guidance_to_taf(station, guidance)
        if cone is None:
            raise HTTPException(status_code=404, detail=f"No data for {station} at val={val}")
        return cone.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
