"""
Market SIGMET Hazard Intelligence Engine — Pure Domain Service
================================================================
Evaluates active METAR telemetry across ALL 11 stations against severe hazard thresholds.
Emits authoritative Market SIGMETs ONLY when a severe weather anomaly or crisis hazard is active.

In aviation, SIGMETs are NOT daily routine reports; they are severe weather advisories.
If all 11 METAR stations report benign/normal conditions, evaluate_market_sigmets() returns an empty list.

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
from backend.modules.entry_decision.domain.services.dxy_metar_service import get_dxy_market_metar


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
    operational_action: str  # Taxonomy code e.g. MKT_BLOCK_CRISIS, MKT_TRIM_TACTICAL
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
            "================================================================================\n"
        )


def _check_overflow_sigmet(station: str, metar: Any, now_str: str) -> Optional[MarketSIGMET]:
    """
    Evaluates empirical ±3σ statistical tail overflows across D1, D2, and D3 dimensions.
    Emits OVERFLOW_MULTI (Black Swan), OVERFLOW_EXTREMO (> 4σ), or OVERFLOW_MODERADO (3σ < depth ≤ 4σ).
    """
    flag = getattr(metar, "overflow_flag", None)
    if not flag:
        return None
    d1 = getattr(metar, "sigma_depth_d1", None)
    d2 = getattr(metar, "sigma_depth_d2", None)
    d3 = getattr(metar, "sigma_depth_d3", None)
    depths = [abs(d) for d in (d1, d2, d3) if d is not None]
    max_depth = max(depths) if depths else 0.0

    as_of = str(getattr(metar, "as_of_date", "")).replace("-", "")

    from backend.modules.entry_decision.domain.rules.sigma_overflow import classify_overflow_tier

    if flag == "MULTI":
        return MarketSIGMET(
            sigmet_id=f"SIGMET-OVERFLOW-{station}-{as_of}-MULTI",
            timestamp_utc=now_str,
            as_of_date=getattr(metar, "as_of_date", ""),
            hazard_type="OVERFLOW_MULTI",
            severity="CRITICAL",
            station=station,
            title=f"{station} Multi-Dimensional σ-Overflow (Black Swan Anomaly)",
            description=f"{station} breached ±3σ across multiple dimensions (D1={d1}, D2={d2}, D3={d3}). Systemic Black Swan anomaly.",
            operational_action="MKT_MACRO_CIRCUIT_BREAKER",
            is_active=True,
            telemetry_snapshot={"sigma_depth_d1": d1, "sigma_depth_d2": d2, "sigma_depth_d3": d3, "overflow_flag": flag}
        )

    tier, hazard_type, severity = classify_overflow_tier(max_depth)
    if tier == 5:
        return MarketSIGMET(
            sigmet_id=f"SIGMET-BLOWOFF-{station}-{as_of}-T5-SYSTEMIC",
            timestamp_utc=now_str,
            as_of_date=getattr(metar, "as_of_date", ""),
            hazard_type=hazard_type,
            severity=severity,
            station=station,
            title=f"{station} Systemic Blow-Off ({max_depth:.1f}σ ≥ 10σ)",
            description=f"{station} breached systemic survival limit with extreme depth {max_depth:.1f}σ ({flag}).",
            operational_action="MKT_MACRO_CIRCUIT_BREAKER",
            is_active=True,
            telemetry_snapshot={"sigma_depth_d1": d1, "sigma_depth_d2": d2, "sigma_depth_d3": d3, "overflow_flag": flag, "tier": tier}
        )
    elif tier == 4:
        return MarketSIGMET(
            sigmet_id=f"SIGMET-BLOWOFF-{station}-{as_of}-T4-EXTREME",
            timestamp_utc=now_str,
            as_of_date=getattr(metar, "as_of_date", ""),
            hazard_type=hazard_type,
            severity=severity,
            station=station,
            title=f"{station} Extreme Blow-Off ({max_depth:.1f}σ ≥ 7σ)",
            description=f"{station} breached catastrophic limit with depth {max_depth:.1f}σ ({flag}).",
            operational_action="MKT_MACRO_CIRCUIT_BREAKER",
            is_active=True,
            telemetry_snapshot={"sigma_depth_d1": d1, "sigma_depth_d2": d2, "sigma_depth_d3": d3, "overflow_flag": flag, "tier": tier}
        )
    elif tier == 3:
        return MarketSIGMET(
            sigmet_id=f"SIGMET-BLOWOFF-{station}-{as_of}-T3-SEVERE",
            timestamp_utc=now_str,
            as_of_date=getattr(metar, "as_of_date", ""),
            hazard_type=hazard_type,
            severity=severity,
            station=station,
            title=f"{station} Severe Blow-Off ({max_depth:.1f}σ ≥ 5σ)",
            description=f"{station} breached emergency limit with depth {max_depth:.1f}σ ({flag}).",
            operational_action="MKT_BLOCK_CRISIS",
            is_active=True,
            telemetry_snapshot={"sigma_depth_d1": d1, "sigma_depth_d2": d2, "sigma_depth_d3": d3, "overflow_flag": flag, "tier": tier}
        )
    elif tier == 2:
        return MarketSIGMET(
            sigmet_id=f"SIGMET-OVERFLOW-{station}-{as_of}-T2-EXTREMO",
            timestamp_utc=now_str,
            as_of_date=getattr(metar, "as_of_date", ""),
            hazard_type=hazard_type,
            severity=severity,
            station=station,
            title=f"{station} Extreme σ-Overflow ({max_depth:.1f}σ ≥ 4σ)",
            description=f"{station} breached extreme statistical limits with depth {max_depth:.1f}σ ({flag}).",
            operational_action="MKT_BLOCK_CRISIS",
            is_active=True,
            telemetry_snapshot={"sigma_depth_d1": d1, "sigma_depth_d2": d2, "sigma_depth_d3": d3, "overflow_flag": flag, "tier": tier}
        )
    elif tier == 1:
        return MarketSIGMET(
            sigmet_id=f"SIGMET-OVERFLOW-{station}-{as_of}-T1-MODERADO",
            timestamp_utc=now_str,
            as_of_date=getattr(metar, "as_of_date", ""),
            hazard_type=hazard_type,
            severity=severity,
            station=station,
            title=f"{station} Moderate σ-Overflow ({max_depth:.1f}σ ≥ 3σ)",
            description=f"{station} breached statistical tail limit with depth {max_depth:.1f}σ ({flag}).",
            operational_action="MKT_HOLD_STABLE",
            is_active=True,
            telemetry_snapshot={"sigma_depth_d1": d1, "sigma_depth_d2": d2, "sigma_depth_d3": d3, "overflow_flag": flag, "tier": tier}
        )
    return None


def evaluate_sigmets_from_metar_dicts(
    metar_dicts: Dict[str, Dict[str, Any]],
    family_report: Optional[Dict[str, Any]] = None,
    as_of_date: Optional[str] = None,
) -> List[MarketSIGMET]:
    """
    Evaluate SIGMET hazards from pre-computed METAR station dicts (from compositor results).
    Avoids re-calling 11 METAR services when the data is already available.

    Args:
        metar_dicts: Dict mapping station code → METAR .to_dict() result.
                     Keys: "vix", "vvix", "pcr", "fg", "sv5_turbulence", "skew",
                           "credit", "yield_curve", "rotation", "bsi", "dxy"
        family_report: Optional family sequence dict from ConvergenceReport.family_sequence.
        as_of_date: Optional target date string (YYYY-MM-DD).
    """
    from types import SimpleNamespace

    now_str = as_of_date + "T00:00:00Z" if as_of_date else "UNKNOWN"
    sigmets: List[MarketSIGMET] = []

    def _ns(d: Dict[str, Any]) -> SimpleNamespace:
        """Wrap dict so _check_overflow_sigmet can use getattr."""
        return SimpleNamespace(**d)

    # ── Station threshold checks (same logic as evaluate_market_sigmets) ──

    # 1. VIX
    vix = metar_dicts.get("vix")
    if vix:
        try:
            vix_val = vix.get("vix_index_value", 0.0)
            sigma_d1 = vix.get("sigma_depth_d1")
            if vix_val >= 28.0 or (sigma_d1 is not None and sigma_d1 >= 5.0):
                sigmets.append(MarketSIGMET(
                    sigmet_id=f"SIGMET-VIX-{str(vix.get('as_of_date','')).replace('-','')}-001",
                    timestamp_utc=now_str, as_of_date=vix.get("as_of_date", ""),
                    hazard_type="SIGMET_VOLATILITY_CRISIS_SPIKE", severity="CRITICAL",
                    station="VIX", title="VIX Extreme Panic Spike (>= 28.0)",
                    description=f"VIX index level ({vix_val:.2f}) breached extreme panic threshold (28.0). Systemic risk veto active.",
                    operational_action="MKT_MACRO_CIRCUIT_BREAKER", is_active=True,
                    telemetry_snapshot={"vix": vix_val, "vix_d3": vix.get("vix_velocity_3d")}
                ))
            ovf = _check_overflow_sigmet("VIX", _ns(vix), now_str)
            if ovf:
                sigmets.append(ovf)
        except Exception as e:
            _log_station_failure("VIX", e)

    # 2. VVIX
    vvix = metar_dicts.get("vvix")
    if vvix:
        try:
            vvix_val = vvix.get("vvix_index_value", 0.0)
            if vvix_val >= 120.0:
                sigmets.append(MarketSIGMET(
                    sigmet_id=f"SIGMET-VVIX-{str(vvix.get('as_of_date','')).replace('-','')}-001",
                    timestamp_utc=now_str, as_of_date=vvix.get("as_of_date", ""),
                    hazard_type="SIGMET_VOL_OF_VOL_INSTABILITY", severity="WARNING",
                    station="VVIX", title="VVIX Vol-of-Vol Regime Transition (>= 120.0)",
                    description=f"VVIX index level ({vvix_val:.2f}) indicates severe option tail-pricing turbulence.",
                    operational_action="MKT_HOLD_STABLE", is_active=True,
                    telemetry_snapshot={"vvix": vvix_val, "vvix_d3": vvix.get("vvix_velocity_3d")}
                ))
            ovf = _check_overflow_sigmet("VVIX", _ns(vvix), now_str)
            if ovf:
                sigmets.append(ovf)
        except Exception as e:
            _log_station_failure("VVIX", e)

    # 3. PCR
    pcr = metar_dicts.get("pcr")
    if pcr:
        try:
            pcr_val = pcr.get("pcr_index_value", 0.0)
            if pcr_val >= 1.20:
                sigmets.append(MarketSIGMET(
                    sigmet_id=f"SIGMET-PCR-{str(pcr.get('as_of_date','')).replace('-','')}-001",
                    timestamp_utc=now_str, as_of_date=pcr.get("as_of_date", ""),
                    hazard_type="SIGMET_PUT_OPTION_PANIC_SQUEEZE", severity="WARNING",
                    station="PCR", title="CBOE Put/Call Ratio Extreme Panic (>= 1.20)",
                    description=f"PCR ratio ({pcr_val:.2f}) shows extreme retail/institutional put buying.",
                    operational_action="MKT_HOLD_STABLE", is_active=True,
                    telemetry_snapshot={"pcr": pcr_val, "pcr_d3": pcr.get("pcr_velocity_3d")}
                ))
            ovf = _check_overflow_sigmet("PCR", _ns(pcr), now_str)
            if ovf:
                sigmets.append(ovf)
        except Exception as e:
            _log_station_failure("PCR", e)

    # 4. FG
    fg = metar_dicts.get("fg")
    if fg:
        try:
            fg_val = fg.get("fg_index_value", 50.0)
            if fg_val <= 15.0:
                sigmets.append(MarketSIGMET(
                    sigmet_id=f"SIGMET-FG-{str(fg.get('as_of_date','')).replace('-','')}-001",
                    timestamp_utc=now_str, as_of_date=fg.get("as_of_date", ""),
                    hazard_type="SIGMET_EXTREME_RETAIL_FEAR_CAPITULATION", severity="WARNING",
                    station="FG", title="CNN Fear & Greed Extreme Capitulation (<= 15.0)",
                    description=f"Fear & Greed score ({fg_val:.1f}) indicates extreme market sentiment capitulation.",
                    operational_action="MKT_BUY_DIP_TACTICAL", is_active=True,
                    telemetry_snapshot={"fg": fg_val, "fg_d3": fg.get("fg_velocity_3d")}
                ))
            ovf = _check_overflow_sigmet("FG", _ns(fg), now_str)
            if ovf:
                sigmets.append(ovf)
        except Exception as e:
            _log_station_failure("FG", e)

    # 5. SV5_TURBULENCE
    turb = metar_dicts.get("sv5_turbulence")
    if turb:
        try:
            turb_val = turb.get("turbulence_index_value", 0.0)
            if turb_val >= 10.0:
                sigmets.append(MarketSIGMET(
                    sigmet_id=f"SIGMET-TURB-{str(turb.get('as_of_date','')).replace('-','')}-001",
                    timestamp_utc=now_str, as_of_date=turb.get("as_of_date", ""),
                    hazard_type="SIGMET_INSTITUTIONAL_VOLUME_TURBULENCE", severity="CRITICAL",
                    station="SV5_TURBULENCE", title="Institutional Volume Turbulence Crisis (>= 10.0)",
                    description=f"Volume turbulence ({turb_val:.2f}) in HIGH/CRISIS territory (>= 10.0). Institutional participation is erratic.",
                    operational_action="MKT_BLOCK_CRISIS", is_active=True,
                    telemetry_snapshot={"turbulence": turb_val, "turbulence_d3": turb.get("turbulence_velocity_3d")}
                ))
            ovf = _check_overflow_sigmet("SV5_TURBULENCE", _ns(turb), now_str)
            if ovf:
                sigmets.append(ovf)
        except Exception as e:
            _log_station_failure("SV5_TURBULENCE", e)

    # 6. SKEW
    skew = metar_dicts.get("skew")
    if skew:
        try:
            skew_val = skew.get("skew_index_value", 0.0)
            if skew_val >= 145.0:
                sigmets.append(MarketSIGMET(
                    sigmet_id=f"SIGMET-SKEW-{str(skew.get('as_of_date','')).replace('-','')}-001",
                    timestamp_utc=now_str, as_of_date=skew.get("as_of_date", ""),
                    hazard_type="SIGMET_TAIL_RISK_SKEW_SPIKE", severity="WARNING",
                    station="SKEW", title="Extreme CBOE SKEW Tail Risk Hedging",
                    description=f"SKEW index level ({skew_val:.2f}) indicates aggressive institutional OTM Put buying for tail protection.",
                    operational_action="MKT_HOLD_STABLE", is_active=True,
                    telemetry_snapshot={"skew": skew_val, "skew_d3": skew.get("skew_velocity_3d")}
                ))
            ovf = _check_overflow_sigmet("SKEW", _ns(skew), now_str)
            if ovf:
                sigmets.append(ovf)
        except Exception as e:
            _log_station_failure("SKEW", e)

    # 7. CREDIT
    credit = metar_dicts.get("credit")
    if credit:
        try:
            credit_bin = credit.get("credit_bin", "")
            credit_ratio = credit.get("credit_ratio_value", 0.0)
            credit_d3 = credit.get("credit_velocity_3d", 0.0)
            if credit_bin == "EXTREME_STRESS" or credit_d3 <= -0.0130:
                sigmets.append(MarketSIGMET(
                    sigmet_id=f"SIGMET-CREDIT-{str(credit.get('as_of_date','')).replace('-','')}-001",
                    timestamp_utc=now_str, as_of_date=credit.get("as_of_date", ""),
                    hazard_type="SIGMET_CREDIT_FREEZE_SHOCK", severity="CRITICAL",
                    station="CREDIT", title="Corporate Credit Freeze (HYG/LQD Compression)",
                    description=f"Credit ratio ({credit_ratio:.4f}) in EXTREME_STRESS zone with deteriorating velocity (Δ3d = {credit_d3:+.4f}).",
                    operational_action="MKT_BLOCK_CRISIS", is_active=True,
                    telemetry_snapshot={"credit_ratio": credit_ratio, "credit_d3": credit_d3}
                ))
            ovf = _check_overflow_sigmet("CREDIT", _ns(credit), now_str)
            if ovf:
                sigmets.append(ovf)
        except Exception as e:
            _log_station_failure("CREDIT", e)

    # 8. YIELD CURVE
    yc = metar_dicts.get("yield_curve")
    if yc:
        try:
            spread = yc.get("spread_value", 0.0)
            if spread < -0.624:
                sigmets.append(MarketSIGMET(
                    sigmet_id=f"SIGMET-CURVE-{str(yc.get('as_of_date','')).replace('-','')}-001",
                    timestamp_utc=now_str, as_of_date=yc.get("as_of_date", ""),
                    hazard_type="SIGMET_CURVE_DEEP_INVERSION", severity="CRITICAL",
                    station="YIELD_CURVE", title="Deep Yield Curve Inversion (P05 — Bottom 5%)",
                    description=f"Yield curve spread ({spread:+.4f}%) in DEEP_INVERSION (< -0.624, P05). Severe macro recession signal.",
                    operational_action="MKT_TRIM_TACTICAL", is_active=True,
                    telemetry_snapshot={"spread": spread}
                ))
            ovf = _check_overflow_sigmet("YIELD_CURVE", _ns(yc), now_str)
            if ovf:
                sigmets.append(ovf)
        except Exception as e:
            _log_station_failure("YIELD_CURVE", e)

    # 9. ROTATION
    rot = metar_dicts.get("rotation")
    if rot:
        try:
            rot_val = rot.get("rotation_index_value", 0.0)
            if rot_val <= -2.0851:
                sigmets.append(MarketSIGMET(
                    sigmet_id=f"SIGMET-ROTATION-{str(rot.get('as_of_date','')).replace('-','')}-001",
                    timestamp_utc=now_str, as_of_date=rot.get("as_of_date", ""),
                    hazard_type="SIGMET_DEFENSIVE_FLIGHT_TO_SAFETY", severity="WARNING",
                    station="ROTATION", title="Defensive Sector Rotation (P15 — Bottom 15%)",
                    description=f"Sector rotation index ({rot_val:.4f}) in EXTREME_DEFENSIVE/DEFENSIVE_ROTATION zone (< -2.085, P15).",
                    operational_action="MKT_TRIM_TACTICAL", is_active=True,
                    telemetry_snapshot={"rotation_index": rot_val, "rotation_d3": rot.get("rotation_velocity_3d")}
                ))
            ovf = _check_overflow_sigmet("ROTATION", _ns(rot), now_str)
            if ovf:
                sigmets.append(ovf)
        except Exception as e:
            _log_station_failure("ROTATION", e)

    # 10. BSI
    bsi = metar_dicts.get("bsi")
    if bsi:
        try:
            bsi_bin = bsi.get("bsi_bin", "")
            bsi_val = bsi.get("bsi_value", 50.0)
            bsi_d3 = bsi.get("bsi_velocity_3d", 0.0)
            if bsi_bin == "BREADTH_WASHED_OUT" or bsi_d3 <= -30.7:
                sigmets.append(MarketSIGMET(
                    sigmet_id=f"SIGMET-BSI-{str(bsi.get('as_of_date','')).replace('-','')}-001",
                    timestamp_utc=now_str, as_of_date=bsi.get("as_of_date", ""),
                    hazard_type="SIGMET_BREADTH_WASHED_OUT_CRISIS", severity="CRITICAL",
                    station="BSI", title="Tactical Breadth Washed Out (S5TW <= 11%)",
                    description=f"Tactical breadth level ({bsi_val:.1f}%) in BREADTH_WASHED_OUT zone (bottom 2.28%) with shock velocity (Δ3d = {bsi_d3:+.1f}pp).",
                    operational_action="MKT_BLOCK_CRISIS", is_active=True,
                    telemetry_snapshot={"bsi_value": bsi_val, "bsi_d3": bsi_d3}
                ))
            ovf = _check_overflow_sigmet("BSI", _ns(bsi), now_str)
            if ovf:
                sigmets.append(ovf)
        except Exception as e:
            _log_station_failure("BSI", e)

    # 11. DXY
    dxy = metar_dicts.get("dxy")
    if dxy:
        try:
            dxy_bin = dxy.get("dxy_bin", "")
            dxy_val = dxy.get("dxy_index_value", 0.0)
            if dxy_bin == "EXTREME_STRENGTH":
                sigmets.append(MarketSIGMET(
                    sigmet_id=f"SIGMET-DXY-{str(dxy.get('as_of_date','')).replace('-','')}-001",
                    timestamp_utc=now_str, as_of_date=dxy.get("as_of_date", ""),
                    hazard_type="SIGMET_DOLLAR_LIQUIDITY_CRISIS", severity="CRITICAL",
                    station="DXY", title="Dollar Spike Liquidity Crisis (DXY σ+2 extreme)",
                    description=f"Dollar Index ({dxy_val:.2f}) in EXTREME_STRENGTH zone (σ+2). Flight-to-safety USD surge compresses equity valuations and EM capital flows.",
                    operational_action="MKT_BLOCK_CRISIS", is_active=True,
                    telemetry_snapshot={"dxy": dxy_val, "dxy_d3": dxy.get("dxy_velocity_3d")}
                ))
            ovf = _check_overflow_sigmet("DXY", _ns(dxy), now_str)
            if ovf:
                sigmets.append(ovf)
        except Exception as e:
            _log_station_failure("DXY", e)

    # ── FAMILY-LEVEL SIGMET: Cross-station causal phase hazards ──────────
    if family_report:
        try:
            phase = family_report.get("phase", "NEUTRAL")
            ll_trap = family_report.get("ll_trap_veto", False)
            hh_exit = family_report.get("hh_exit_amplify", False)
            n_floor_trap = family_report.get("n_floor_trap", 0)
            n_floor_structural = family_report.get("n_floor_structural", 0)
            cat1_stress = family_report.get("cat1_stress_ratio", 0)
            cat2_fear = family_report.get("cat2_fear_ratio", 0)
            cat3_cap = family_report.get("cat3_capitulation_ratio", 0)

            if phase == "CAPITULATION_BUILDING" and n_floor_trap >= 2:
                sigmets.append(MarketSIGMET(
                    sigmet_id=f"SIGMET-FAMILY-CAP-{as_of_date or 'LIVE'}-001",
                    timestamp_utc=now_str, as_of_date=as_of_date or "LIVE",
                    hazard_type="SIGMET_CAPITULATION_TRAP_FLOOR", severity="CRITICAL",
                    station="FAMILY",
                    title="Capitulation Building + Trap Floors — Structural Breakdown Risk",
                    description=(
                        f"Cross-station causal phase: {phase}. "
                        f"CAT1_stress={cat1_stress:.0%}, CAT2_fear={cat2_fear:.0%}, CAT3_cap={cat3_cap:.0%}. "
                        f"{n_floor_trap} stations show TRAP floors (P(HL)<0.45). "
                        "This pattern precedes structural breakdowns, not recoveries."
                    ),
                    operational_action="URGENCY_EMERGENCY", is_active=True,
                    telemetry_snapshot={
                        "phase": phase, "n_floor_trap": n_floor_trap,
                        "ll_trap_veto": ll_trap,
                        "cat1_stress": cat1_stress, "cat2_fear": cat2_fear,
                        "cat3_cap": cat3_cap,
                    },
                ))

            elif phase == "CAPITULATION_RESOLVING" and n_floor_structural >= 2:
                sigmets.append(MarketSIGMET(
                    sigmet_id=f"SIGMET-FAMILY-ACCUM-{as_of_date or 'LIVE'}-001",
                    timestamp_utc=now_str, as_of_date=as_of_date or "LIVE",
                    hazard_type="SIGMET_CAPITULATION_RESOLVING_OPPORTUNITY", severity="WARNING",
                    station="FAMILY",
                    title="Capitulation Resolving + Structural Floors — Accumulation Opportunity",
                    description=(
                        f"Cross-station causal phase: {phase}. "
                        f"CAT1_stress={cat1_stress:.0%}, CAT2_fear={cat2_fear:.0%}, CAT3_cap={cat3_cap:.0%}. "
                        f"{n_floor_structural} stations show STRUCTURAL floors (P(HL)>0.55). "
                        "Post-capitulation with structural support — historically favorable for accumulation."
                    ),
                    operational_action="URGENCY_HIGH", is_active=True,
                    telemetry_snapshot={
                        "phase": phase, "n_floor_structural": n_floor_structural,
                        "cat1_stress": cat1_stress, "cat2_fear": cat2_fear,
                        "cat3_cap": cat3_cap,
                    },
                ))

            if hh_exit and phase in ("COMPLACENT_DISTRIBUTION", "NEUTRAL"):
                sigmets.append(MarketSIGMET(
                    sigmet_id=f"SIGMET-FAMILY-CEIL-{as_of_date or 'LIVE'}-001",
                    timestamp_utc=now_str, as_of_date=as_of_date or "LIVE",
                    hazard_type="SIGMET_CEILING_TRAP_DISTRIBUTION", severity="WARNING",
                    station="FAMILY",
                    title="Ceiling Trap + Complacent Distribution — Topping Pattern",
                    description=(
                        f"Phase: {phase}. Ceiling TRAP active (P(HH)>0.55 — Regla de Oro). "
                        "Complacent stations at ceiling with structural exhaustion. "
                        "Historically precedes distribution and correction."
                    ),
                    operational_action="URGENCY_HIGH", is_active=True,
                    telemetry_snapshot={
                        "phase": phase, "hh_exit_amplify": hh_exit,
                        "n_ceiling_trap": family_report.get("n_ceiling_trap", 0),
                    },
                ))
        except Exception as e:
            _log_station_failure("FAMILY", e)

    return sigmets


def evaluate_market_sigmets(as_of_date: Optional[str] = None) -> List[MarketSIGMET]:
    """
    Evaluates active METAR telemetry across ALL 11 stations against severe hazard thresholds.
    Returns a list of active MarketSIGMET objects. If conditions are normal across all stations,
    returns an empty list [].

    This is the standalone entry point that fetches METAR data from scratch.
    For the optimized path (pre-computed data), use evaluate_sigmets_from_metar_dicts().
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sigmets: List[MarketSIGMET] = []

    # 1. Station VIX: Crisis Panic Spike (VIX >= 28.0)
    try:
        vix_metar = get_vix_market_metar(as_of_date=as_of_date)
        if vix_metar.vix_index_value >= 28.0 or (vix_metar.sigma_depth_d1 is not None and vix_metar.sigma_depth_d1 >= 5.0):
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
        ovf = _check_overflow_sigmet("VIX", vix_metar, now_str)
        if ovf:
            sigmets.append(ovf)
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
                    operational_action="MKT_HOLD_STABLE",
                    is_active=True,
                    telemetry_snapshot={"vvix": vvix_metar.vvix_index_value, "vvix_d3": vvix_metar.vvix_velocity_3d}
                )
            )
        ovf = _check_overflow_sigmet("VVIX", vvix_metar, now_str)
        if ovf:
            sigmets.append(ovf)
    except Exception as e:
        _log_station_failure("VVIX", e)

    # 3. Station PCR: Put Option Panic Squeeze (PCR >= 1.20)
    try:
        pcr_metar = get_pcr_market_metar(as_of_date=as_of_date)
        if pcr_metar.pcr_index_value >= 1.20:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-PCR-{pcr_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=pcr_metar.as_of_date,
                    hazard_type="SIGMET_PUT_OPTION_PANIC_SQUEEZE",
                    severity="WARNING",
                    station="PCR",
                    title="CBOE Put/Call Ratio Extreme Panic (>= 1.20)",
                    description=f"PCR ratio ({pcr_metar.pcr_index_value:.2f}) shows extreme retail/institutional put buying.",
                    operational_action="MKT_HOLD_STABLE",
                    is_active=True,
                    telemetry_snapshot={"pcr": pcr_metar.pcr_index_value, "pcr_d3": pcr_metar.pcr_velocity_3d}
                )
            )
        ovf = _check_overflow_sigmet("PCR", pcr_metar, now_str)
        if ovf:
            sigmets.append(ovf)
    except Exception as e:
        _log_station_failure("PCR", e)

    # 4. Station FG: Extreme Retail Fear Capitulation (FG <= 15.0)
    try:
        fg_metar = get_fg_market_metar(as_of_date=as_of_date)
        if fg_metar.fg_index_value <= 15.0:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-FG-{fg_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=fg_metar.as_of_date,
                    hazard_type="SIGMET_EXTREME_RETAIL_FEAR_CAPITULATION",
                    severity="WARNING",
                    station="FG",
                    title="CNN Fear & Greed Extreme Capitulation (<= 15.0)",
                    description=f"Fear & Greed score ({fg_metar.fg_index_value:.1f}) indicates extreme market sentiment capitulation.",
                    operational_action="MKT_BUY_DIP_TACTICAL",
                    is_active=True,
                    telemetry_snapshot={"fg": fg_metar.fg_index_value, "fg_d3": fg_metar.fg_velocity_3d}
                )
            )
        ovf = _check_overflow_sigmet("FG", fg_metar, now_str)
        if ovf:
            sigmets.append(ovf)
    except Exception as e:
        _log_station_failure("FG", e)

    # 5. Station SV5_TURBULENCE: Institutional Volume Turbulence Surge (>= 10.0)
    try:
        turb_metar = get_sv5_turbulence_market_metar(as_of_date=as_of_date)
        if turb_metar.turbulence_index_value >= 10.0:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-TURB-{turb_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=turb_metar.as_of_date,
                    hazard_type="SIGMET_INSTITUTIONAL_VOLUME_TURBULENCE",
                    severity="CRITICAL",
                    station="SV5_TURBULENCE",
                    title="Institutional Volume Turbulence Crisis (>= 10.0)",
                    description=f"Volume turbulence ({turb_metar.turbulence_index_value:.2f}) in HIGH/CRISIS territory (>= 10.0). Institutional participation is erratic.",
                    operational_action="MKT_BLOCK_CRISIS",
                    is_active=True,
                    telemetry_snapshot={"turbulence": turb_metar.turbulence_index_value, "turbulence_d3": turb_metar.turbulence_velocity_3d}
                )
            )
        ovf = _check_overflow_sigmet("SV5_TURBULENCE", turb_metar, now_str)
        if ovf:
            sigmets.append(ovf)
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
                    operational_action="MKT_HOLD_STABLE",
                    is_active=True,
                    telemetry_snapshot={"skew": skew_metar.skew_index_value, "skew_d3": skew_metar.skew_velocity_3d}
                )
            )
        ovf = _check_overflow_sigmet("SKEW", skew_metar, now_str)
        if ovf:
            sigmets.append(ovf)
    except Exception as e:
        _log_station_failure("SKEW", e)

    # 7. Station CREDIT STRESS: Corporate Credit Freeze
    try:
        credit_metar = get_credit_market_metar(as_of_date=as_of_date)
        if credit_metar.credit_bin == "EXTREME_STRESS" or credit_metar.credit_velocity_3d <= -0.0130:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-CREDIT-{credit_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=credit_metar.as_of_date,
                    hazard_type="SIGMET_CREDIT_FREEZE_SHOCK",
                    severity="CRITICAL",
                    station="CREDIT",
                    title="Corporate Credit Freeze (HYG/LQD Compression)",
                    description=f"Credit ratio ({credit_metar.credit_ratio_value:.4f}) in EXTREME_STRESS zone with deteriorating velocity (Δ3d = {credit_metar.credit_velocity_3d:+.4f}).",
                    operational_action="MKT_BLOCK_CRISIS",
                    is_active=True,
                    telemetry_snapshot={"credit_ratio": credit_metar.credit_ratio_value, "credit_d3": credit_metar.credit_velocity_3d}
                )
            )
        ovf = _check_overflow_sigmet("CREDIT", credit_metar, now_str)
        if ovf:
            sigmets.append(ovf)
    except Exception as e:
        _log_station_failure("CREDIT", e)

    # 8. Station YIELD CURVE: Deep Inversion Only (P05)
    try:
        yc_metar = get_yield_curve_market_metar(as_of_date=as_of_date)
        if yc_metar.spread_value < -0.624:
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-CURVE-{yc_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=yc_metar.as_of_date,
                    hazard_type="SIGMET_CURVE_DEEP_INVERSION",
                    severity="CRITICAL",
                    station="YIELD_CURVE",
                    title="Deep Yield Curve Inversion (P05 — Bottom 5%)",
                    description=f"Yield curve spread ({yc_metar.spread_value:+.4f}%) in DEEP_INVERSION (< -0.624, P05). Severe macro recession signal.",
                    operational_action="MKT_TRIM_TACTICAL",
                    is_active=True,
                    telemetry_snapshot={"spread": yc_metar.spread_value}
                )
            )
        ovf = _check_overflow_sigmet("YIELD_CURVE", yc_metar, now_str)
        if ovf:
            sigmets.append(ovf)
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
                    operational_action="MKT_TRIM_TACTICAL",
                    is_active=True,
                    telemetry_snapshot={"rotation_index": rot_metar.rotation_index_value, "rotation_d3": rot_metar.rotation_velocity_3d}
                )
            )
        ovf = _check_overflow_sigmet("ROTATION", rot_metar, now_str)
        if ovf:
            sigmets.append(ovf)
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
                    operational_action="MKT_BLOCK_CRISIS",
                    is_active=True,
                    telemetry_snapshot={"bsi_value": bsi_metar.bsi_value, "bsi_d3": bsi_metar.bsi_velocity_3d}
                )
            )
        ovf = _check_overflow_sigmet("BSI", bsi_metar, now_str)
        if ovf:
            sigmets.append(ovf)
    except Exception as e:
        _log_station_failure("BSI", e)

    # 11. Station DXY: Dollar Spike Liquidity Crisis
    try:
        dxy_metar = get_dxy_market_metar(as_of_date=as_of_date)
        if dxy_metar.dxy_bin == "EXTREME_STRENGTH":
            sigmets.append(
                MarketSIGMET(
                    sigmet_id=f"SIGMET-DXY-{dxy_metar.as_of_date.replace('-','')}-001",
                    timestamp_utc=now_str,
                    as_of_date=dxy_metar.as_of_date,
                    hazard_type="SIGMET_DOLLAR_LIQUIDITY_CRISIS",
                    severity="CRITICAL",
                    station="DXY",
                    title="Dollar Spike Liquidity Crisis (DXY σ+2 extreme)",
                    description=f"Dollar Index ({dxy_metar.dxy_index_value:.2f}) in EXTREME_STRENGTH zone (σ+2). Flight-to-safety USD surge compresses equity valuations and EM capital flows.",
                    operational_action="MKT_BLOCK_CRISIS",
                    is_active=True,
                    telemetry_snapshot={"dxy": dxy_metar.dxy_index_value, "dxy_d3": dxy_metar.dxy_velocity_3d}
                )
            )
        ovf = _check_overflow_sigmet("DXY", dxy_metar, now_str)
        if ovf:
            sigmets.append(ovf)
    except Exception as e:
        _log_station_failure("DXY", e)
    # ── FAMILY-LEVEL SIGMET: Cross-station causal phase hazards ──────────

    try:
        from backend.modules.entry_decision.domain.services.convergence_compositor import ConvergenceCompositor
        compositor = ConvergenceCompositor()
        report = compositor.compute(as_of_date=as_of_date)
        family = report.family_sequence

        if family:
            phase = family.get("phase", "NEUTRAL")
            ll_trap = family.get("ll_trap_veto", False)
            hh_exit = family.get("hh_exit_amplify", False)
            n_floor_trap = family.get("n_floor_trap", 0)
            n_floor_structural = family.get("n_floor_structural", 0)
            cat1_stress = family.get("cat1_stress_ratio", 0)
            cat2_fear = family.get("cat2_fear_ratio", 0)
            cat3_cap = family.get("cat3_capitulation_ratio", 0)

            # SIGMET: Capitulation building with trap floors = dangerous
            if phase == "CAPITULATION_BUILDING" and n_floor_trap >= 2:
                sigmets.append(
                    MarketSIGMET(
                        sigmet_id=f"SIGMET-FAMILY-CAP-{as_of_date or 'LIVE'}-001",
                        timestamp_utc=now_str,
                        as_of_date=as_of_date or "LIVE",
                        hazard_type="SIGMET_CAPITULATION_TRAP_FLOOR",
                        severity="CRITICAL",
                        station="FAMILY",
                        title="Capitulation Building + Trap Floors — Structural Breakdown Risk",
                        description=(
                            f"Cross-station causal phase: {phase}. "
                            f"CAT1_stress={cat1_stress:.0%}, CAT2_fear={cat2_fear:.0%}, CAT3_cap={cat3_cap:.0%}. "
                            f"{n_floor_trap} stations show TRAP floors (P(HL)<0.45). "
                            "This pattern precedes structural breakdowns, not recoveries."
                        ),
                        operational_action="URGENCY_EMERGENCY",
                        is_active=True,
                        telemetry_snapshot={
                            "phase": phase, "n_floor_trap": n_floor_trap,
                            "ll_trap_veto": ll_trap,
                            "cat1_stress": cat1_stress, "cat2_fear": cat2_fear,
                            "cat3_cap": cat3_cap,
                        },
                    )
                )

            # SIGMET: Capitulation resolving with structural floors = accumulation opportunity
            elif phase == "CAPITULATION_RESOLVING" and n_floor_structural >= 2:
                sigmets.append(
                    MarketSIGMET(
                        sigmet_id=f"SIGMET-FAMILY-ACCUM-{as_of_date or 'LIVE'}-001",
                        timestamp_utc=now_str,
                        as_of_date=as_of_date or "LIVE",
                        hazard_type="SIGMET_CAPITULATION_RESOLVING_OPPORTUNITY",
                        severity="WARNING",
                        station="FAMILY",
                        title="Capitulation Resolving + Structural Floors — Accumulation Opportunity",
                        description=(
                            f"Cross-station causal phase: {phase}. "
                            f"CAT1_stress={cat1_stress:.0%}, CAT2_fear={cat2_fear:.0%}, CAT3_cap={cat3_cap:.0%}. "
                            f"{n_floor_structural} stations show STRUCTURAL floors (P(HL)>0.55). "
                            "Post-capitulation with structural support — historically favorable for accumulation."
                        ),
                        operational_action="URGENCY_HIGH",
                        is_active=True,
                        telemetry_snapshot={
                            "phase": phase, "n_floor_structural": n_floor_structural,
                            "cat1_stress": cat1_stress, "cat2_fear": cat2_fear,
                            "cat3_cap": cat3_cap,
                        },
                    )
                )

            # SIGMET: HH exit amplify = ceiling trap across multiple stations
            if hh_exit and phase in ("COMPLACENT_DISTRIBUTION", "NEUTRAL"):
                sigmets.append(
                    MarketSIGMET(
                        sigmet_id=f"SIGMET-FAMILY-CEIL-{as_of_date or 'LIVE'}-001",
                        timestamp_utc=now_str,
                        as_of_date=as_of_date or "LIVE",
                        hazard_type="SIGMET_CEILING_TRAP_DISTRIBUTION",
                        severity="WARNING",
                        station="FAMILY",
                        title="Ceiling Trap + Complacent Distribution — Topping Pattern",
                        description=(
                            f"Phase: {phase}. Ceiling TRAP active (P(HH)>0.55 — Regla de Oro). "
                            "Complacent stations at ceiling with structural exhaustion. "
                            "Historically precedes distribution and correction."
                        ),
                        operational_action="URGENCY_HIGH",
                        is_active=True,
                        telemetry_snapshot={
                            "phase": phase, "hh_exit_amplify": hh_exit,
                            "n_ceiling_trap": family.get("n_ceiling_trap", 0),
                        },
                    )
                )
    except Exception as e:
        _log_station_failure("FAMILY", e)

    return sigmets

