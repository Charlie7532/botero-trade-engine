"""
Market SIGMET Hazard Intelligence Engine — Pure Domain Service
================================================================
Evaluates active METAR telemetry across ALL 9 stations against severe hazard thresholds.
Emits authoritative Market SIGMETs ONLY when a severe weather anomaly or crisis hazard is active.

In aviation, SIGMETs are NOT daily routine reports; they are severe weather advisories.
If all 9 METAR stations report benign/normal conditions, evaluate_market_sigmets() returns an empty list.

Follows Institutional Taxonomy: Universal Institutional Action Taxonomy Standard.
"""
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
import json
import logging

logger = logging.getLogger(__name__)


def _log_station_failure(station: str, error: Exception) -> None:
    """Log station evaluation failure instead of silently swallowing exceptions."""
    logger.error(f"SIGMET station {station} evaluation failed: {error}")

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


@dataclass(frozen=True)
class MarketSIGMET:
    sigmet_id: str
    timestamp_utc: str
    as_of_date: str
    hazard_type: str  # e.g. SIGMET_VOLATILITY_TURBULENCE, SIGMET_TAIL_RISK_SKEW
    severity: str      # "CRITICAL", "WARNING"
    station: str       # "VIX", "VVIX", "PCR", "FG", "SV5_TURBULENCE", "SKEW", "CREDIT", "YIELD_CURVE", "ROTATION", "BSI"
    title: str
    description: str
    operational_action: str  # Taxonomy code e.g. STK_BLOCK_CRISIS, STK_TRIM_TACTICAL
    is_active: bool
    telemetry_snapshot: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def format_cli_broadcast(self) -> str:
        icon = "🚨" if self.severity == "CRITICAL" else "⚠️"
        return (
            "================================================================================\n"
            f" {icon} SEVERE MARKET SIGMET HAZARD BULLETIN — {self.hazard_type} [{self.sigmet_id}]\n"
            "================================================================================\n"
            f" 🕒 Timestamp UTC: {self.timestamp_utc} | Close Date: {self.as_of_date}\n"
            f" 🏢 Station: {self.station} | Severity: {self.severity}\n"
            f" 📌 Operational Directive: {self.operational_action}\n"
            "--------------------------------------------------------------------------------\n"
            f" 🎯 Hazard Title: {self.title}\n"
            f" 📝 Details     : {self.description}\n"
            "================================================================================"
        )


def evaluate_market_sigmets(as_of_date: Optional[str] = None) -> List[MarketSIGMET]:
    """
    Evaluates active METAR telemetry across ALL 10 stations against severe hazard thresholds.
    Returns a list of active MarketSIGMET objects. If conditions are normal across all stations,
    returns an empty list [].
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sigmets: List[MarketSIGMET] = []

    # 1. Station VIX: Crisis Panic Spike (VIX >= 28.0)
    try:
        vix_metar = get_vix_market_metar(as_of_date=as_of_date)
        if vix_metar.vix_index_value >= 28.0 or vix_metar.action_code == "MKT_MACRO_CIRCUIT_BREAKER":
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-VIX-{vix_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=vix_metar.as_of_date,
                    hazard_type="SIGMET_VOLATILITY_CRISIS_SPIKE",
                    severity="CRITICAL",
                    station="VIX",
                    title="VIX Extreme Panic Spike (>= 28.0)",
                    description=f"VIX index level ({vix_metar.vix_index_value:.2f}) breached extreme panic threshold (28.0). Systemic risk veto active.",
                    operational_action="MKT_MACRO_CIRCUIT_BREAKER",
                    is_active=True,
                    telemetry_snapshot={"vix": vix_metar.vix_index_value, "vix_d3": vix_metar.vix_velocity_3d}
                )
            )
    except Exception as e:
        _log_station_failure("VIX", e)

    # 2. Station VVIX: Vol-of-Vol Instability (VVIX >= 120.0)
    try:
        vvix_metar = get_vvix_market_metar(as_of_date=as_of_date)
        if vvix_metar.vvix_index_value >= 120.0:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-VVIX-{vvix_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=vvix_metar.as_of_date,
                    hazard_type="SIGMET_VOL_OF_VOL_INSTABILITY",
                    severity="WARNING",
                    station="VVIX",
                    title="VVIX Vol-of-Vol Regime Transition (>= 120.0)",
                    description=f"VVIX index level ({vvix_metar.vvix_index_value:.2f}) indicates severe option tail-pricing turbulence.",
                    operational_action="STK_HOLD_STABLE",
                    is_active=True,
                    telemetry_snapshot={"vvix": vvix_metar.vvix_index_value, "vvix_d3": vvix_metar.vvix_velocity_3d}
                )
            )
    except Exception as e:
        _log_station_failure("VVIX", e)

    # 3. Station PCR: Put Option Panic Squeeze (PCR >= 1.20)
    try:
        pcr_metar = get_pcr_market_metar(as_of_date=as_of_date)
        if pcr_metar.pcr_ratio_value >= 1.20:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-PCR-{pcr_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=pcr_metar.as_of_date,
                    hazard_type="SIGMET_PUT_OPTION_PANIC_SQUEEZE",
                    severity="WARNING",
                    station="PCR",
                    title="CBOE Put/Call Ratio Extreme Panic (>= 1.20)",
                    description=f"PCR ratio ({pcr_metar.pcr_ratio_value:.2f}) shows extreme retail/institutional put buying.",
                    operational_action="STK_HOLD_STABLE",
                    is_active=True,
                    telemetry_snapshot={"pcr": pcr_metar.pcr_ratio_value, "pcr_d3": pcr_metar.pcr_velocity_3d}
                )
            )
    except Exception as e:
        _log_station_failure("PCR", e)

    # 4. Station FG: Extreme Retail Fear Capitulation (FG <= 15.0)
    try:
        fg_metar = get_fg_market_metar(as_of_date=as_of_date)
        if fg_metar.fear_greed_score <= 15.0:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-FG-{fg_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=fg_metar.as_of_date,
                    hazard_type="SIGMET_EXTREME_RETAIL_FEAR_CAPITULATION",
                    severity="WARNING",
                    station="FG",
                    title="CNN Fear & Greed Extreme Capitulation (<= 15.0)",
                    description=f"Fear & Greed score ({fg_metar.fear_greed_score:.1f}) indicates extreme market sentiment capitulation.",
                    operational_action="STK_BUY_DIP_TACTICAL",
                    is_active=True,
                    telemetry_snapshot={"fg": fg_metar.fear_greed_score, "fg_d3": fg_metar.fear_greed_velocity_3d}
                )
            )
    except Exception as e:
        _log_station_failure("FG", e)

    # 5. Station SV5_TURBULENCE: Institutional Volume Turbulence Surge (>= 10.0)
    try:
        turb_metar = get_sv5_turbulence_market_metar(as_of_date=as_of_date)
        if turb_metar.turbulence_value >= 10.0:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-TURB-{turb_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=turb_metar.as_of_date,
                    hazard_type="SIGMET_INSTITUTIONAL_VOLUME_TURBULENCE",
                    severity="CRITICAL",
                    station="SV5_TURBULENCE",
                    title="Institutional Volume Turbulence Crisis (>= 10.0)",
                    description=f"Volume turbulence ({turb_metar.turbulence_value:.2f}) in HIGH/CRISIS territory (>= 10.0). Institutional participation is erratic.",
                    operational_action="STK_BLOCK_CRISIS",
                    is_active=True,
                    telemetry_snapshot={"turbulence": turb_metar.turbulence_value, "turbulence_d3": turb_metar.turbulence_velocity_3d}
                )
            )
    except Exception as e:
        _log_station_failure("SV5_TURBULENCE", e)

    # 6. Station SKEW: Extreme Tail Risk Hedging (SKEW >= 145.0)
    try:
        skew_metar = get_skew_market_metar(as_of_date=as_of_date)
        if skew_metar.skew_index_value >= 145.0:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-SKEW-{skew_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=skew_metar.as_of_date,
                    hazard_type="SIGMET_TAIL_RISK_SKEW_SPIKE",
                    severity="WARNING",
                    station="SKEW",
                    title="Extreme CBOE SKEW Tail Risk Hedging",
                    description=f"SKEW index level ({skew_metar.skew_index_value:.2f}) indicates aggressive institutional OTM Put buying for tail protection.",
                    operational_action="STK_HOLD_STABLE",
                    is_active=True,
                    telemetry_snapshot={"skew": skew_metar.skew_index_value, "skew_d3": skew_metar.skew_velocity_3d}
                )
            )
    except Exception as e:
        _log_station_failure("SKEW", e)

    # 7. Station CREDIT STRESS: Corporate Credit Freeze
    try:
        credit_metar = get_credit_market_metar(as_of_date=as_of_date)
        if credit_metar.credit_bin == "CREDIT_CRISIS" or credit_metar.credit_velocity_3d <= -0.0130:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-CREDIT-{credit_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=credit_metar.as_of_date,
                    hazard_type="SIGMET_CREDIT_FREEZE_SHOCK",
                    severity="CRITICAL",
                    station="CREDIT",
                    title="Corporate Credit Freeze (HYG/LQD Compression)",
                    description=f"Credit ratio ({credit_metar.credit_ratio_value:.4f}) in CREDIT_CRISIS zone with deteriorating velocity (Δ3d = {credit_metar.credit_velocity_3d:+.4f}).",
                    operational_action="STK_BLOCK_CRISIS",
                    is_active=True,
                    telemetry_snapshot={"credit_ratio": credit_metar.credit_ratio_value, "credit_d3": credit_metar.credit_velocity_3d}
                )
            )
    except Exception as e:
        _log_station_failure("CREDIT", e)

    # 8. Station YIELD CURVE: Deep Inversion Only (P05)
    try:
        yc_metar = get_yield_curve_market_metar(as_of_date=as_of_date)
        if yc_metar.yield_spread_value < -0.624:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-CURVE-{yc_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=yc_metar.as_of_date,
                    hazard_type="SIGMET_CURVE_DEEP_INVERSION",
                    severity="CRITICAL",
                    station="YIELD_CURVE",
                    title="Deep Yield Curve Inversion (P05 — Bottom 5%)",
                    description=f"Yield curve spread ({yc_metar.yield_spread_value:+.4f}%) in DEEP_INVERSION (< -0.624, P05). Severe macro recession signal.",
                    operational_action="STK_TRIM_TACTICAL",
                    is_active=True,
                    telemetry_snapshot={"spread": yc_metar.yield_spread_value}
                )
            )
    except Exception as e:
        _log_station_failure("YIELD_CURVE", e)

    # 9. Station SECTOR ROTATION: Defensive Flight-to-Safety
    try:
        rot_metar = get_rotation_market_metar(as_of_date=as_of_date)
        if rot_metar.rotation_index_value <= -2.0851:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-ROTATION-{rot_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=rot_metar.as_of_date,
                    hazard_type="SIGMET_DEFENSIVE_FLIGHT_TO_SAFETY",
                    severity="WARNING",
                    station="ROTATION",
                    title="Defensive Sector Rotation (P15 — Bottom 15%)",
                    description=f"Sector rotation index ({rot_metar.rotation_index_value:.4f}) in EXTREME_DEFENSIVE/DEFENSIVE_ROTATION zone (< -2.085, P15).",
                    operational_action="STK_TRIM_TACTICAL",
                    is_active=True,
                    telemetry_snapshot={"rotation_index": rot_metar.rotation_index_value, "rotation_d3": rot_metar.rotation_velocity_3d}
                )
            )
    except Exception as e:
        _log_station_failure("ROTATION", e)

    # 10. Station BREADTH SHOCK INDEX (BSI / S5TW): Washed Out Capitulation
    try:
        bsi_metar = get_bsi_market_metar(as_of_date=as_of_date)
        if bsi_metar.bsi_bin == "BREADTH_WASHED_OUT" or bsi_metar.bsi_velocity_3d <= -30.7:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-BSI-{bsi_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=bsi_metar.as_of_date,
                    hazard_type="SIGMET_BREADTH_WASHED_OUT_CRISIS",
                    severity="CRITICAL",
                    station="BSI",
                    title="Tactical Breadth Washed Out (S5TW <= 11%)",
                    description=f"Tactical breadth level ({bsi_metar.bsi_value:.1f}%) in BREADTH_WASHED_OUT zone (bottom 2.28%) with shock velocity (Δ3d = {bsi_metar.bsi_velocity_3d:+.1f}pp).",
                    operational_action="STK_BLOCK_CRISIS",
                    is_active=True,
                    telemetry_snapshot={"bsi_value": bsi_metar.bsi_value, "bsi_d3": bsi_metar.bsi_velocity_3d}
                )
            )
    except Exception as e:
        _log_station_failure("BSI", e)

    return sigmets
