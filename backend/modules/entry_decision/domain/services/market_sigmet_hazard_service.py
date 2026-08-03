"""
Market SIGMET Hazard Intelligence Engine — Pure Domain Service
================================================================
Evaluates active METAR telemetry across all 9 stations against extreme hazard thresholds.
Emits authoritative Market SIGMETs ONLY when a severe weather anomaly or crisis hazard is active.

In aviation, SIGMETs are NOT daily routine reports; they are severe weather advisories.
If all 9 METAR stations report benign/normal conditions, evaluate_market_sigmets() returns an empty list.

Follows Institutional Taxonomy: Universal Institutional Action Taxonomy Standard.
"""
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
import json

from backend.modules.entry_decision.domain.services.vix_metar_service import get_vix_market_metar
from backend.modules.entry_decision.domain.services.sv5_turbulence_metar_service import get_sv5_turbulence_market_metar
from backend.modules.entry_decision.domain.services.skew_metar_service import get_skew_market_metar
from backend.modules.entry_decision.domain.services.yield_curve_metar_service import get_yield_curve_market_metar
from backend.modules.entry_decision.domain.services.fg_metar_service import get_fg_market_metar
from backend.modules.entry_decision.domain.services.credit_metar_service import get_credit_market_metar


@dataclass(frozen=True)
class MarketSIGMET:
    sigmet_id: str
    timestamp_utc: str
    as_of_date: str
    hazard_type: str  # e.g. SIGMET_VOLATILITY_TURBULENCE, SIGMET_TAIL_RISK_SKEW
    severity: str      # "CRITICAL", "WARNING"
    station: str       # "VIX", "SV5_TURBULENCE", "SKEW", etc.
    title: str
    description: str
    operational_action: str  # Taxonomy code e.g. STK_BLOCK_CRISIS
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
    Evaluates current METAR observations and returns active SIGMET severe weather bulletins.
    Returns empty list [] if all stations report normal / non-hazardous conditions.
    """
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    today_clean = now_utc.strftime("%Y%m%d")
    sigmets: List[MarketSIGMET] = []

    # 1. Evaluate Volatility Crisis & Volume Turbulence Shock
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
    except Exception:
        pass

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
    except Exception:
        pass

    # 2. Evaluate Tail Risk SKEW Anomaly
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
    except Exception:
        pass

    # 3. Evaluate Macro Yield Curve Inversion Shock
    try:
        yc_metar = get_yield_curve_market_metar(as_of_date=as_of_date)
        if yc_metar.yield_spread_value < 0.0:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-CURVE-{yc_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=yc_metar.as_of_date,
                    hazard_type="SIGMET_CURVE_INVERSION_SHOCK",
                    severity="CRITICAL",
                    station="YIELD_CURVE",
                    title="Yield Curve Inversion (10Y-3M Inverted)",
                    description=f"Yield curve spread ({yc_metar.yield_spread_value:+.4f}%) is inverted. Macro recession signal active.",
                    operational_action="STK_TRIM_TACTICAL",
                    is_active=True,
                    telemetry_snapshot={"spread": yc_metar.yield_spread_value}
                )
            )
    except Exception:
        pass

    # 4. Evaluate Extreme Fear Capitulation
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
    except Exception:
        pass

    return sigmets
