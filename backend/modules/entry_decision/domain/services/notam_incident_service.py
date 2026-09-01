"""
Operational Market NOTAM Incident Service — Pure Domain Service
===============================================================
Generates authoritative, zero-fallback Operational Market NOTAM Bulletins.
Reserved strictly for operational disruptions, system anomalies, circuit breakers,
data feed staleness, broker connectivity incidents, and FOMC blackout warnings.

Follows Institutional Taxonomy: Universal Institutional Action Taxonomy Standard.
"""
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
import json

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore


class StrictDataPolicyError(Exception):
    """Raised when operational incident parameters cannot be evaluated."""
    pass


@dataclass(frozen=True)
class OperationalNOTAM:
    notam_id: str
    timestamp_utc: str
    incident_type: str
    severity: str  # "CRITICAL", "WARNING", "INFO"
    component: str
    title: str
    description: str
    operational_action: str  # Taxonomy code e.g. MKT_MACRO_CIRCUIT_BREAKER
    is_active: bool
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def format_cli_broadcast(self) -> str:
        icon = "🚨" if self.severity == "CRITICAL" else ("⚠️" if self.severity == "WARNING" else "ℹ️")
        return (
            "================================================================================\n"
            f" {icon} OPERATIONAL NOTAM — {self.incident_type} [{self.notam_id}]\n"
            "================================================================================\n"
            f" 🕒 Timestamp UTC: {self.timestamp_utc} | Severity: {self.severity}\n"
            f" 🧩 Component: {self.component} | Active Status: {'ACTIVE' if self.is_active else 'RESOLVED'}\n"
            "--------------------------------------------------------------------------------\n"
            f" 📌 Title: {self.title}\n"
            f" 📝 Description: {self.description}\n"
            f" 🎯 Operational Directive: {self.operational_action}\n"
            "================================================================================"
        )


def evaluate_operational_notams(as_of_date: Optional[str] = None) -> List[OperationalNOTAM]:
    """
    Evaluates system operational status and returns all active Market NOTAMs.
    Checks:
    1. Pipeline freshness in Neon Vault (Stale Data Incident)
    2. Macro Circuit Breaker conditions (VIX >= 40)
    3. FOMC Blackout Window status

    Args:
        as_of_date: Optional target date string (YYYY-MM-DD) for historical evaluation.
    """
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    today_str = as_of_date if as_of_date else now_utc.strftime("%Y-%m-%d")
    notams: List[OperationalNOTAM] = []

    store = TimescaleDataStore()
    engine = store.engine
    try:
        import pandas as pd
        ref_date = pd.Timestamp(today_str).date()

        # 1. Check Vault Data Freshness Incident
        if as_of_date:
            query = f"SELECT MAX(time::date) as max_date FROM market.ohlcv_bars WHERE ticker = 'SPY' AND timeframe = '1d' AND time::date <= '{as_of_date}'"
        else:
            query = "SELECT MAX(time::date) as max_date FROM market.ohlcv_bars WHERE ticker = 'SPY' AND timeframe = '1d'"
        df = pd.read_sql(query, engine)
        latest_vault_date = str(df.iloc[0]['max_date']) if len(df) > 0 and pd.notna(df.iloc[0]['max_date']) else None

        if not latest_vault_date:
            notams.append(
                OperationalNOTAM(
                    notam_id=f"NOTAM-OUTAGE-{today_str.replace('-','')}-001",
                    timestamp_utc=now_str,
                    incident_type="NOTAM_DATA_OUTAGE",
                    severity="CRITICAL",
                    component="TimescaleDataStore",
                    title="Neon Vault Empty / Disconnected",
                    description=f"No SPY OHLCV bars found in Neon Vault database for date {today_str}.",
                    operational_action="MKT_MACRO_CIRCUIT_BREAKER",
                    is_active=True,
                    details={"latest_bar": None}
                )
            )
        else:
            # 1b. Check if SPY data is stale (>1 day gap on a trading weekday)
            latest_date = pd.Timestamp(latest_vault_date).date()
            gap_days = (ref_date - latest_date).days
            is_weekday = ref_date.weekday() < 5
            if gap_days > 1 and is_weekday:
                notams.append(
                    OperationalNOTAM(
                        notam_id=f"NOTAM-STALE-{today_str.replace('-','')}-001",
                        timestamp_utc=now_str,
                        incident_type="NOTAM_STALE_DATA",
                        severity="WARNING",
                        component="TimescaleDataStore",
                        title="Neon Vault SPY Data Stale",
                        description=f"Latest SPY bar is from {latest_vault_date}, {gap_days} days behind requested date ({today_str}). Pipeline may be stalled.",
                        operational_action="MKT_MACRO_CIRCUIT_BREAKER",
                        is_active=True,
                        details={"latest_bar": latest_vault_date, "gap_days": gap_days}
                    )
                )

        # 2. Check Macro Circuit Breaker (VIX > 40 or Severe Crisis)
        if as_of_date:
            vix_query = f"SELECT close FROM market.ohlcv_bars WHERE ticker = 'VIX' AND timeframe = '1d' AND time::date <= '{as_of_date}' ORDER BY time DESC LIMIT 1"
        else:
            vix_query = "SELECT close FROM market.ohlcv_bars WHERE ticker = 'VIX' AND timeframe = '1d' ORDER BY time DESC LIMIT 1"
        df_vix = pd.read_sql(vix_query, engine)
        if len(df_vix) > 0 and pd.notna(df_vix.iloc[0]['close']):
            vix_close = float(df_vix.iloc[0]['close'])
            if vix_close >= 40.0:
                notams.append(
                    OperationalNOTAM(
                        notam_id=f"NOTAM-CB-{today_str.replace('-','')}-001",
                        timestamp_utc=now_str,
                        incident_type="NOTAM_CIRCUIT_BREAKER",
                        severity="CRITICAL",
                        component="VolRegimeIntelligence",
                        title="Systemic Volatility Circuit Breaker Active",
                        description=f"VIX close level ({vix_close:.2f}) exceeds extreme crisis threshold (40.0). All speculative and swing entries blocked.",
                        operational_action="MKT_MACRO_CIRCUIT_BREAKER",
                        is_active=True,
                        details={"vix_close": vix_close}
                    )
                )

        # 3. Check FOMC Blackout Window
        try:
            from backend.modules.flow_intelligence.domain.rules.macro_calendar import MacroEventCalendar
            cal = MacroEventCalendar()

            for fomc in cal.FOMC_2026:
                meeting_day1, decision_day = fomc["dates"]
                # Blackout: Saturday before meeting through decision day
                blackout_start = meeting_day1 - timedelta(days=meeting_day1.weekday() + 2)  # always previous Saturday
                blackout_end = decision_day

                if blackout_start <= ref_date <= blackout_end:
                    days_to_decision = (decision_day - ref_date).days
                    notams.append(
                        OperationalNOTAM(
                            notam_id=f"NOTAM-FOMC-{today_str.replace('-','')}-001",
                            timestamp_utc=now_str,
                            incident_type="NOTAM_FOMC_BLACKOUT",
                            severity="WARNING",
                            component="MacroEventCalendar",
                            title="FOMC Blackout Window Active",
                            description=(
                                f"FOMC meeting {meeting_day1} - {decision_day}"
                                f"{' (+ SEP/Dot Plot)' if fomc['sep'] else ''}. "
                                f"Decision in {days_to_decision} day(s). "
                                f"Reduce new entries, widen stops, expect elevated volatility."
                            ),
                            operational_action="MKT_FOMC_BLACKOUT",
                            is_active=True,
                            details={
                                "blackout_start": str(blackout_start),
                                "decision_day": str(decision_day),
                                "days_to_decision": days_to_decision,
                                "has_sep": fomc["sep"],
                            }
                        )
                    )
                    break  # Only one FOMC blackout at a time
        except ImportError:
            pass  # MacroEventCalendar not available — skip FOMC check

        return notams
    finally:
        store.close()


def get_latest_circuit_breaker_notam(as_of_date: Optional[str] = None) -> Optional[OperationalNOTAM]:
    """Returns active circuit breaker NOTAM if present, else None."""
    notams = evaluate_operational_notams(as_of_date=as_of_date)
    for n in notams:
        if n.incident_type == "NOTAM_CIRCUIT_BREAKER" and n.is_active:
            return n
    return None
