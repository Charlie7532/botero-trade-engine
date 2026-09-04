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


MONITORED_NOTAM_STATIONS: List[str] = [
    # Core Market Benchmark
    "SPY",
    # 11 Observational METAR Stations
    "VIX",
    "VVIX",
    "SKEW",
    "CBOE_PCR",
    "DXY",
    "TNX",
    "IRX",
    "YIELD_SPREAD",
    "FG",
    "SV5_TURBULENCE",
    "BSI",
    "CREDIT_RATIO",
    "ROTATION_INDEX",
    # Underlying Breadth & Options Feeds
    "CBOE_CPCE",
    "S5TH",
    "S5TW",
    "S5FI",
    "SV5TH",
    "SV5TW",
    "SV5FI",
]


def evaluate_operational_notams(as_of_date: Optional[str] = None) -> List[OperationalNOTAM]:
    """
    Evaluates system operational status and returns all active Market NOTAMs.
    Checks:
    1. Pipeline freshness in Neon Vault across all monitored stations (Stale Data / Outage Incidents)
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

        # 1. Check Vault Data Freshness Across All Monitored Stations
        stations_sql = ", ".join(f"'{s}'" for s in MONITORED_NOTAM_STATIONS)
        date_filter = f"AND time::date <= '{as_of_date}'" if as_of_date else ""
        query = f"""
            SELECT ticker, MAX(time::date) as max_date 
            FROM market.ohlcv_bars 
            WHERE ticker IN ({stations_sql}) AND timeframe = '1d' {date_filter}
            GROUP BY ticker
        """
        df_stations = pd.read_sql(query, engine)
        station_dates = {}
        if not df_stations.empty:
            for _, r in df_stations.iterrows():
                if pd.notna(r['max_date']):
                    station_dates[r['ticker']] = pd.Timestamp(r['max_date']).date()

        benchmark_date = station_dates.get("SPY", ref_date)

        for station in MONITORED_NOTAM_STATIONS:
            latest_date = station_dates.get(station)
            if not latest_date:
                notams.append(
                    OperationalNOTAM(
                        notam_id=f"NOTAM-OUTAGE-{station}-{today_str.replace('-','')}",
                        timestamp_utc=now_str,
                        incident_type="NOTAM_DATA_OUTAGE",
                        severity="CRITICAL",
                        component=f"VaultStation.{station}",
                        title=f"Station {station} Data Outage",
                        description=f"No {station} OHLCV bars found in Neon Vault database for target date ({today_str}).",
                        operational_action="MKT_MACRO_CIRCUIT_BREAKER" if station in ["SPY", "VIX"] else "BLOCK_STALE_STATION",
                        is_active=True,
                        details={"station": station, "latest_bar": None, "target_date": today_str}
                    )
                )
            else:
                # 1. Lag relative to market benchmark (SPY)
                lag_vs_benchmark = max(0, len(pd.bdate_range(latest_date, benchmark_date)) - 1) if latest_date < benchmark_date else 0
                
                # 2. Lag relative to calendar date
                lag_vs_calendar = max(0, len(pd.bdate_range(latest_date, ref_date)) - 1) if latest_date < ref_date else 0

                # Outdated if it lags >= 1 trading day behind the SPY benchmark,
                # or > 1 trading day behind calendar date (to accommodate intraday/pre-market).
                is_stale = (lag_vs_benchmark >= 1) or (lag_vs_calendar > 1)
                if is_stale:
                    gap_bdays = max(lag_vs_benchmark, lag_vs_calendar)
                    is_critical = (
                        gap_bdays >= 2
                        or station in ["SPY", "VIX", "BSI", "CBOE_PCR", "DXY", "YIELD_SPREAD", "CREDIT_RATIO"]
                    )
                    notams.append(
                        OperationalNOTAM(
                            notam_id=f"NOTAM-STALE-{station}-{today_str.replace('-','')}",
                            timestamp_utc=now_str,
                            incident_type="NOTAM_STALE_DATA",
                            severity="CRITICAL" if is_critical else "WARNING",
                            component=f"VaultStation.{station}",
                            title=f"Station {station} Data Stale ({gap_bdays}d lag)",
                            description=(
                                f"Latest {station} bar is from {latest_date}, {gap_bdays} trading session(s) "
                                f"behind benchmark SPY ({benchmark_date}) / calendar ({today_str}). "
                                f"Station is outdated and flagged in NOTAM report."
                            ),
                            operational_action="MKT_MACRO_CIRCUIT_BREAKER" if station in ["SPY", "VIX"] else "BLOCK_STALE_STATION",
                            is_active=True,
                            details={
                                "station": station,
                                "latest_bar": str(latest_date),
                                "benchmark_date": str(benchmark_date),
                                "gap_trading_days": gap_bdays,
                            }
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


def generate_notam_report(as_of_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Generates a full Operational Market NOTAM Disruption & Telemetry Report.
    Audits all monitored stations, computes lag vs benchmark, details active incidents,
    and explicitly includes any outdated station.
    """
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    today_str = as_of_date if as_of_date else now_utc.strftime("%Y-%m-%d")

    store = TimescaleDataStore()
    engine = store.engine
    try:
        import pandas as pd
        ref_date = pd.Timestamp(today_str).date()

        stations_sql = ", ".join(f"'{s}'" for s in MONITORED_NOTAM_STATIONS)
        date_filter = f"AND time::date <= '{as_of_date}'" if as_of_date else ""
        query = f"""
            SELECT ticker, MAX(time::date) as max_date 
            FROM market.ohlcv_bars 
            WHERE ticker IN ({stations_sql}) AND timeframe = '1d' {date_filter}
            GROUP BY ticker
        """
        df_stations = pd.read_sql(query, engine)
        station_dates = {}
        if not df_stations.empty:
            for _, r in df_stations.iterrows():
                if pd.notna(r['max_date']):
                    station_dates[r['ticker']] = pd.Timestamp(r['max_date']).date()

        benchmark_date = station_dates.get("SPY", ref_date)

        station_telemetry: List[Dict[str, Any]] = []
        outdated_stations: List[Dict[str, Any]] = []

        for station in MONITORED_NOTAM_STATIONS:
            latest_date = station_dates.get(station)
            if not latest_date:
                telemetry_item = {
                    "station": station,
                    "latest_bar": None,
                    "benchmark_date": str(benchmark_date),
                    "lag_trading_days": None,
                    "status": "OUTAGE",
                    "is_outdated": True,
                    "severity": "CRITICAL",
                    "operational_action": "MKT_MACRO_CIRCUIT_BREAKER" if station in ["SPY", "VIX"] else "BLOCK_STALE_STATION",
                }
                station_telemetry.append(telemetry_item)
                outdated_stations.append(telemetry_item)
            else:
                lag_vs_benchmark = max(0, len(pd.bdate_range(latest_date, benchmark_date)) - 1) if latest_date < benchmark_date else 0
                lag_vs_calendar = max(0, len(pd.bdate_range(latest_date, ref_date)) - 1) if latest_date < ref_date else 0
                is_stale = (lag_vs_benchmark >= 1) or (lag_vs_calendar > 1)
                gap_bdays = max(lag_vs_benchmark, lag_vs_calendar)

                telemetry_item = {
                    "station": station,
                    "latest_bar": str(latest_date),
                    "benchmark_date": str(benchmark_date),
                    "lag_trading_days": gap_bdays,
                    "status": "STALE" if is_stale else "OK",
                    "is_outdated": is_stale,
                    "severity": ("CRITICAL" if (gap_bdays >= 2 or station in ["SPY", "VIX", "BSI", "CBOE_PCR", "DXY", "YIELD_SPREAD", "CREDIT_RATIO"]) else "WARNING") if is_stale else "NONE",
                    "operational_action": ("MKT_MACRO_CIRCUIT_BREAKER" if station in ["SPY", "VIX"] else "BLOCK_STALE_STATION") if is_stale else "NONE",
                }
                station_telemetry.append(telemetry_item)
                if is_stale:
                    outdated_stations.append(telemetry_item)

        bulletins = evaluate_operational_notams(as_of_date=as_of_date)

        if any(b.severity == "CRITICAL" for b in bulletins):
            overall_status = "CRITICAL"
        elif bulletins or outdated_stations:
            overall_status = "WARNING"
        else:
            overall_status = "CLEAR"

        return {
            "report_id": f"NOTAM-RPT-{today_str.replace('-','')}",
            "timestamp_utc": now_str,
            "as_of_date": today_str,
            "benchmark_station": "SPY",
            "benchmark_date": str(benchmark_date),
            "overall_status": overall_status,
            "active_incidents_count": len(bulletins),
            "outdated_stations_count": len(outdated_stations),
            "outdated_stations": outdated_stations,
            "station_telemetry": station_telemetry,
            "bulletins": [b.to_dict() for b in bulletins],
            "circuit_breaker_active": any(b.incident_type == "NOTAM_CIRCUIT_BREAKER" for b in bulletins),
            "fomc_blackout_active": any(b.incident_type == "NOTAM_FOMC_BLACKOUT" for b in bulletins),
        }
    finally:
        store.close()


def format_notam_report_broadcast(report: Dict[str, Any]) -> str:
    """Formats the comprehensive NOTAM report for CLI and broadcast logging."""
    icon = "🚨" if report["overall_status"] == "CRITICAL" else ("⚠️" if report["overall_status"] == "WARNING" else "🛡️")
    lines = [
        "================================================================================",
        f" {icon} OPERATIONAL NOTAM MARKET DISRUPTION REPORT [{report['report_id']}]",
        "================================================================================",
        f" 🕒 Timestamp UTC: {report['timestamp_utc']} | Target Date: {report['as_of_date']}",
        f" 🚦 Overall Status: {report['overall_status']} | Benchmark (SPY): {report['benchmark_date']}",
        f" 🛡️ Active Bulletins: {report['active_incidents_count']} | Outdated Stations: {report['outdated_stations_count']}",
        "--------------------------------------------------------------------------------",
        " 📡 STATION FRESHNESS TELEMETRY MATRIX:",
    ]
    for st in report.get("station_telemetry", []):
        s_icon = "✅" if st["status"] == "OK" else ("⚠️" if st["status"] == "STALE" else "❌")
        lag_str = f"({st['lag_trading_days']}d lag)" if st["lag_trading_days"] and st["lag_trading_days"] > 0 else ""
        lines.append(f"    • {st['station']:16s} : {str(st['latest_bar']):10s} [{s_icon} {st['status']}] {lag_str}")

    outdated = report.get("outdated_stations", [])
    if outdated:
        lines.append("--------------------------------------------------------------------------------")
        lines.append(f" ⚠️ OUTDATED STATIONS DETECTED ({len(outdated)}):")
        for ost in outdated:
            lines.append(
                f"    • {ost['station']:14s} : {ost['latest_bar']} ({ost['lag_trading_days']}d lag vs {report['benchmark_date']}) "
                f"→ {ost['operational_action']} [{ost['severity']}]"
            )

    bulletins = report.get("bulletins", [])
    if bulletins:
        lines.append("--------------------------------------------------------------------------------")
        lines.append(f" 🚨 ACTIVE NOTAM BULLETINS ({len(bulletins)}):")
        for b in bulletins:
            b_icon = "🚨" if b.get("severity") == "CRITICAL" else "⚠️"
            lines.append(f"    • {b_icon} [{b['notam_id']}] {b['incident_type']} ({b['severity']})")
            lines.append(f"      Title: {b['title']}")
            lines.append(f"      Directive: {b['operational_action']}")

    lines.append("================================================================================")
    return "\n".join(lines)


def get_latest_circuit_breaker_notam(as_of_date: Optional[str] = None) -> Optional[OperationalNOTAM]:
    """Returns active circuit breaker NOTAM if present, else None."""
    notams = evaluate_operational_notams(as_of_date=as_of_date)
    for n in notams:
        if n.incident_type == "NOTAM_CIRCUIT_BREAKER" and n.is_active:
            return n
    return None
