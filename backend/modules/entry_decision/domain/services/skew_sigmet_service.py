"""
CBOE SKEW Index Market SIGMET Service — Pure Domain Service
===========================================================
Generates authoritative, zero-fallback SKEW Market SIGMETs.
Uses 3-Day Fast Kinematic Velocity (Delta 3d - 72h) for tail-risk evaluation.
Strict Data Policy: Zero Fallbacks. If a requested date is missing or not valid in Neon Vault,
raises StrictDataPolicyError immediately with explicit 'SIGMET NOT AVAILABLE' message in English.
Always includes exact UTC date and time.
"""
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
import json

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.skew_lookup import skew_lookup
from backend.modules.shared.domain.entities.state_snapshot import StateSnapshot
from backend.modules.shared.domain.ports.regime_state_port import RegimeStatePort


class StrictDataPolicyError(Exception):
    """Raised when required market data or Fact Store parameters are missing. Zero Fallbacks allowed."""
    pass


@dataclass(frozen=True)
class MarketSIGMET:
    sigmet_id: str
    timestamp_utc: str
    as_of_date: str
    issuer: str
    market_status: str
    skew_index_value: float
    skew_velocity_3d: float
    state_key: str
    skew_bin: str
    velocity_vector: str
    n_samples: int
    divergence_regime: str
    operational_guidance: str
    p_bull_vector: list
    p_bear_vector: list
    ev_net_vector: list
    e_days_vector: list
    ev_per_day_vector: list
    primary_p_bull: float
    primary_ev_net: float
    primary_e_days: float
    primary_capital_velocity: float
    rr_asymmetry_ratio: float

    def to_dict(self) -> Dict[str, Any]:
        """Returns full structured SIGMET payload as a dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Returns formatted JSON string of the SIGMET."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def format_cli_broadcast(self) -> str:
        """Formats the SIGMET into a high-visibility CLI / Telegram broadcast string."""
        return (
            "================================================================================\n"
            f" 📢 MARKET SIGMET — CBOE SKEW INDEX (TAIL RISK) [{self.sigmet_id}]\n"
            "================================================================================\n"
            f" 🕒 Timestamp UTC: {self.timestamp_utc} | Close Date: {self.as_of_date}\n"
            f" 🏢 Issuer: {self.issuer} | 🚦 Market Status: {self.market_status}\n"
            "--------------------------------------------------------------------------------\n"
            " 📊 LIVE TELEMETRY (72H FAST KINEMATICS):\n"
            f"    • SKEW Index Level : {self.skew_index_value:.2f} [{self.skew_bin}]\n"
            f"    • Velocity (Δ3d)   : {self.skew_velocity_3d:+.2f} [{self.velocity_vector}]\n"
            f"    • State Key        : {self.state_key} (N = {self.n_samples} historical days)\n\n"
            " 🔮 STOCHASTIC FORECAST & HORIZON DIVERGENCE:\n"
            f"    • Active Regime     : {self.divergence_regime}\n"
            f"    • Scale 2.5% ({self.e_days_vector[0]:.0f}d) : P(bull) = {self.p_bull_vector[0]*100:.1f}% | EV = {self.ev_net_vector[0]*100:+.2f}%\n"
            f"    • Scale 5.0% ({self.e_days_vector[1]:.0f}d) : P(bull) = {self.p_bull_vector[1]*100:.1f}% | EV = {self.ev_net_vector[1]*100:+.2f}%\n"
            f"    • Scale 7.5% ({self.e_days_vector[2]:.0f}d) : P(bull) = {self.p_bull_vector[2]*100:.1f}% | EV = {self.ev_net_vector[2]*100:+.2f}%\n\n"
            " ⚡ CAPITAL VELOCITY (TIME-INDEPENDENT):\n"
            f"    • Daily Rate (%/day): {self.primary_capital_velocity*100:+.4f}% / trading day (reaches 5.0% in {self.primary_e_days:.1f}d)\n"
            f"    • R/R Asymmetry     : {self.rr_asymmetry_ratio:.2f}x\n\n"
            " 🎯 OPERATIONAL DIRECTIVES (UNIVERSAL TAXONOMY):\n"
            f"    • Taxonomy Code     : {self.operational_guidance}\n"
            "================================================================================"
        )


def get_skew_market_sigmet(as_of_date: Optional[str] = None) -> MarketSIGMET:
    """
    Generates an authoritative SKEW Market SIGMET on-demand using 3-day fast velocity.
    Strict Data Policy: Zero Fallbacks. If a requested as_of_date is specified and does NOT exist
    in Neon Vault, raises StrictDataPolicyError immediately.
    """
    store = TimescaleDataStore()
    conn = store._conn()
    try:
        import pandas as pd

        latest_bar_query = "SELECT MAX(time::date) as max_date FROM market.ohlcv_bars WHERE ticker = 'SKEW' AND timeframe = '1d'"
        df_max = pd.read_sql(latest_bar_query, conn)
        overall_latest = str(df_max.iloc[0]['max_date']) if len(df_max) > 0 and pd.notna(df_max.iloc[0]['max_date']) else "UNKNOWN"

        if as_of_date:
            target_date = as_of_date
            check_query = f"SELECT COUNT(*) as count FROM market.ohlcv_bars WHERE ticker = 'SKEW' AND timeframe = '1d' AND time::date = '{target_date}'"
            df_check = pd.read_sql(check_query, conn)
            if df_check.iloc[0]['count'] == 0:
                raise StrictDataPolicyError(
                    f"STRICT DATA POLICY: SKEW SIGMET NOT AVAILABLE for requested date '{as_of_date}'. "
                    f"Vault data does not exist for this timestamp. Latest available date in Vault is '{overall_latest}'."
                )
        else:
            target_date = overall_latest
            if target_date == "UNKNOWN":
                raise StrictDataPolicyError(
                    "STRICT DATA POLICY: SKEW SIGMET NOT AVAILABLE. Neon Vault contains zero OHLCV bars for ticker 'SKEW'."
                )

        # Query 10 trading bars up to target_date to compute 3-day velocity
        query = f"""
            SELECT time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker = 'SKEW' AND timeframe = '1d' AND time::date <= '{target_date}'
            ORDER BY time DESC LIMIT 10
        """
        df_skew = pd.read_sql(query, conn)
        if len(df_skew) < 4:
            raise StrictDataPolicyError(
                f"STRICT DATA POLICY: SKEW SIGMET NOT AVAILABLE for date '{target_date}'. "
                f"Insufficient historical bars in Vault ({len(df_skew)} bars found, minimum 4 required for 72h kinematics)."
            )

        df_skew = df_skew.sort_values("date").reset_index(drop=True)
        skew_latest = float(df_skew.iloc[-1]['close'])
        skew_3d_prev = float(df_skew.iloc[-4]['close'])
        skew_delta_3d = float(skew_latest - skew_3d_prev)
        clean_date = str(df_skew.iloc[-1]['date'])

        # Perform pure domain lookup against skew_fact_store.json
        guidance = skew_lookup.lookup_skew_guidance(skew_val=skew_latest, skew_d3=skew_delta_3d)
        if not guidance:
            raise StrictDataPolicyError(
                f"STRICT DATA POLICY: SKEW SIGMET NOT AVAILABLE. State classification failed for SKEW={skew_latest}, d3={skew_delta_3d}."
            )

        vec = guidance.to_vector()
        now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if skew_latest >= 148.0 or (skew_latest >= 140.0 and skew_delta_3d >= 6.67):
            market_status = "CRISIS_TAIL_RISK_EXTREME"
        elif skew_latest >= 137.0:
            market_status = "ELEVATED_TAIL_RISK"
        elif skew_latest <= 110.47:
            market_status = "COMPLACENT"
        else:
            market_status = "NORMAL_OPERATIONAL"

        sigmet_id = f"SIGMET-SKEW-{clean_date.replace('-', '')}-001"

        return MarketSIGMET(
            sigmet_id=sigmet_id,
            timestamp_utc=now_utc_str,
            as_of_date=clean_date,
            issuer="Botero-Trade SKEW Intelligence Engine",
            market_status=market_status,
            skew_index_value=round(skew_latest, 2),
            skew_velocity_3d=round(skew_delta_3d, 2),
            state_key=guidance.state_key,
            skew_bin=guidance.skew_bin,
            velocity_vector=guidance.velocity_vector,
            n_samples=guidance.n,
            divergence_regime=guidance.divergence_regime,
            operational_guidance=guidance.operational_guidance,
            p_bull_vector=vec["p_bull"],
            p_bear_vector=vec["p_bear"],
            ev_net_vector=vec["ev_net"],
            e_days_vector=vec["e_days"],
            ev_per_day_vector=vec["ev_per_day"],
            primary_p_bull=guidance.zz50.p_bull,
            primary_ev_net=guidance.zz50.ev_net,
            primary_e_days=guidance.zz50.e_days,
            primary_capital_velocity=guidance.zz50.ev_per_day,
            rr_asymmetry_ratio=guidance.zz50.rr_asymmetry,
        )
    finally:
        store._put(conn)
