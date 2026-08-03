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


@dataclass(frozen=True)
class MarketSIGMET:
    sigmet_id: str
    timestamp_utc: str
    as_of_date: str
    hazard_type: str  # e.g. SIGMET_VOLATILITY_TURBULENCE, SIGMET_TAIL_RISK_SKEW
    severity: str      # "CRITICAL", "WARNING"
    station: str       # "VIX", "VVIX", "PCR", "FG", "SV5_TURBULENCE", "SKEW", "CREDIT", "YIELD_CURVE", "ROTATION"
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
            f" 🌩️ Hazard Station: {self.station} | Severity: {self.severity}\n"
            "--------------------------------------------------------------------------------\n"
            f" 📌 Title: {self.title}\n"
            f" 📝 Description: {self.description}\n"
            f" 🎯 Operational Directive: {self.operational_action}\n"
            "================================================================================"
        )


def evaluate_market_sigmets(as_of_date: Optional[str] = None) -> List[MarketSIGMET]:
    """
    Evaluates current METAR observations across ALL 9 stations and returns active SIGMET bulletins.
    Returns empty list [] if all 9 stations report normal / non-hazardous conditions.
    """
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    sigmets: List[MarketSIGMET] = []

    # 1. Station VIX: Implied Volatility Crisis (VIX >= 28.0)
    try:
        vix_metar = get_vix_market_metar(as_of_date=as_of_date)
        if vix_metar.vix_index_value >= 28.0:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-VOL-{vix_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=vix_metar.as_of_date,
                    hazard_type="SIGMET_VOLATILITY_PANIC_SHOCK",
                    severity="CRITICAL",
                    station="VIX",
                    title="Extreme Volatility Spike (VIX >= 28.0)",
                    description=f"VIX close ({vix_metar.vix_index_value:.2f}) indicates severe market panic. High tail risk active.",
                    operational_action="STK_BLOCK_CRISIS",
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
                    title="Extreme Vol-of-Vol Instability (VVIX >= 120.0)",
                    description=f"VVIX level ({vvix_metar.vvix_index_value:.2f}) signals imminent regime transition in options pricing.",
                    operational_action="STK_HOLD_STABLE",
                    is_active=True,
                    telemetry_snapshot={"vvix": vvix_metar.vvix_index_value, "vvix_d3": vvix_metar.vvix_velocity_3d}
                )
            )
    except Exception as e:
        _log_station_failure("VVIX", e)

    # 3. Station CBOE_PCR: Derivatives Hedging Panic (PCR >= 1.10)
    try:
        pcr_metar = get_pcr_market_metar(as_of_date=as_of_date)
        if pcr_metar.pcr_index_value >= 1.10:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-PCR-{pcr_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=pcr_metar.as_of_date,
                    hazard_type="SIGMET_PUT_CALL_HEDGING_PANIC",
                    severity="WARNING",
                    station="CBOE_PCR",
                    title="Extreme Put/Call Option Hedging Spike (PCR >= 1.10)",
                    description=f"Equity PCR ({pcr_metar.pcr_index_value:.2f}) indicates extreme institutional Put hedging surge.",
                    operational_action="STK_BUY_DIP_TACTICAL",
                    is_active=True,
                    telemetry_snapshot={"pcr": pcr_metar.pcr_index_value, "pcr_d3": pcr_metar.pcr_velocity_3d}
                )
            )
    except Exception as e:
        _log_station_failure("CBOE_PCR", e)

    # 4. Station FEAR & GREED: Sentiment Panic Capitulation (F&G <= 15.0)
    try:
        fg_metar = get_fg_market_metar(as_of_date=as_of_date)
        if fg_metar.fg_index_value <= 15.0:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-FG-{fg_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=fg_metar.as_of_date,
                    hazard_type="SIGMET_EXTREME_FEAR_CAPITULATION",
                    severity="WARNING",
                    station="FG",
                    title="Extreme Sentiment Capitulation (Fear & Greed <= 15)",
                    description=f"Fear & Greed score ({fg_metar.fg_index_value:.1f}) hit extreme panic capitulation zone.",
                    operational_action="STK_BUY_DIP_TACTICAL",
                    is_active=True,
                    telemetry_snapshot={"fg": fg_metar.fg_index_value}
                )
            )
    except Exception as e:
        _log_station_failure("FG", e)

    # 5. Station SV5_TURBULENCE: Volume Turbulence Crisis (SV5_TURBULENCE >= 10.0 and Δ3d > 0.0)
    try:
        turb_metar = get_sv5_turbulence_market_metar(as_of_date=as_of_date)
        if turb_metar.turbulence_index_value >= 10.0 and turb_metar.turbulence_velocity_3d > 0.0:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-TURB-{turb_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=turb_metar.as_of_date,
                    hazard_type="SIGMET_VOLUME_TURBULENCE_CRISIS",
                    severity="WARNING",
                    station="SV5_TURBULENCE",
                    title="Institutional Volume Turbulence Surge",
                    description=f"SV5_TURBULENCE ({turb_metar.turbulence_index_value:.2f}) is accelerating (Δ3d = {turb_metar.turbulence_velocity_3d:+.2f}). Institutional liquidity degradation detected.",
                    operational_action="STK_TRIM_TACTICAL",
                    is_active=True,
                    telemetry_snapshot={"turbulence": turb_metar.turbulence_index_value, "d3": turb_metar.turbulence_velocity_3d}
                )
            )
    except Exception as e:
        _log_station_failure("SV5_TURBULENCE", e)

    # 6. Station SKEW: Tail Risk Spike (SKEW >= 145.0)
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
    # Thresholds: credit_edges[1]=0.5035 (P15=CREDIT_STRESS_HIGH upper edge)
    #             credit_speed_edges[1]=-0.009552 (P15=FAST_CREDIT_DETERIORATION)
    try:
        credit_metar = get_credit_market_metar(as_of_date=as_of_date)
        if credit_metar.credit_ratio_value <= 0.5035 and credit_metar.credit_velocity_3d <= -0.009552:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-CREDIT-{credit_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=credit_metar.as_of_date,
                    hazard_type="SIGMET_CREDIT_FREEZE_SHOCK",
                    severity="CRITICAL",
                    station="CREDIT",
                    title="Corporate Credit Freeze (HYG/TLT Compression)",
                    description=f"Credit ratio ({credit_metar.credit_ratio_value:.4f}) in EXTREME_CREDIT_FREEZE/STRESS_HIGH (P15) with deteriorating velocity (Δ3d = {credit_metar.credit_velocity_3d:+.6f}).",
                    operational_action="STK_BLOCK_CRISIS",
                    is_active=True,
                    telemetry_snapshot={"credit_ratio": credit_metar.credit_ratio_value, "credit_d3": credit_metar.credit_velocity_3d}
                )
            )
    except Exception as e:
        _log_station_failure("CREDIT", e)

    # 8. Station YIELD CURVE: Deep Inversion Only (P05)
    # Threshold: yield_edges[0]=-0.624 (P05=DEEP_INVERSION)
    # Prevents chronic firing during prolonged moderate inversions
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
    # Threshold: rotation_edges[1]=-2.0851 (P15=DEFENSIVE_ROTATION upper edge)
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

    return sigmets
