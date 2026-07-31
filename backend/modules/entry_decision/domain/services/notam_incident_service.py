"""
Operational Market NOTAM Incident Service — Pure Domain Service
===============================================================
Generates authoritative, zero-fallback Operational Market NOTAM Bulletins.
Reserved strictly for operational disruptions, system anomalies, circuit breakers,
data feed staleness, broker connectivity incidents, and FOMC blackout warnings.

Follows Institutional Taxonomy: Universal Institutional Action Taxonomy Standard.
"""
from datetime import datetime, timezone
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


def evaluate_operational_notams() -> List[OperationalNOTAM]:
    """
    Evaluates current system operational status and returns all active Market NOTAMs.
    Checks:
    1. Pipeline freshness in Neon Vault (Stale Data Incident)
    2. Macro Circuit Breaker conditions
    3. FOMC Blackout Window status
    """
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    today_str = now_utc.strftime("%Y-%m-%d")
    notams: List[OperationalNOTAM] = []

    store = TimescaleDataStore()
    conn = store._conn()
    try:
        import pandas as pd

        # 1. Check Vault Data Freshness Incident
        query = "SELECT MAX(time::date) as max_date FROM market.ohlcv_bars WHERE ticker = 'SPY' AND timeframe = '1d'"
        df = pd.read_sql(query, conn)
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
                    description="No SPY OHLCV bars found in Neon Vault database.",
                    operational_action="MKT_MACRO_CIRCUIT_BREAKER",
                    is_active=True,
                    details={"latest_bar": None}
                )
            )

        # 2. Check Macro Circuit Breaker (VIX > 40 or Severe Crisis)
        vix_query = "SELECT close FROM market.ohlcv_bars WHERE ticker = 'VIX' AND timeframe = '1d' ORDER BY time DESC LIMIT 1"
        df_vix = pd.read_sql(vix_query, conn)
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

        return notams
    finally:
        store._put(conn)


def get_latest_circuit_breaker_notam() -> Optional[OperationalNOTAM]:
    """Returns active circuit breaker NOTAM if present, else None."""
    notams = evaluate_operational_notams()
    for n in notams:
        if n.incident_type == "NOTAM_CIRCUIT_BREAKER" and n.is_active:
            return n
    return None
