"""
CBOE Volatility of Volatility Index (VVIX) Market SIGMET Service — Pure Domain Service
=====================================================================================
Generates authoritative, zero-fallback VVIX Market SIGMETs.
Uses 3-Day Fast Kinematic Velocity (Delta 3d - 72h) for ultra-fast reaction.
Strict Data Policy: Zero Fallbacks. If a requested date is missing or not valid in Neon Vault,
raises StrictDataPolicyError immediately with explicit 'SIGMET NOT AVAILABLE' message in English.
Always includes exact UTC date and time.
"""
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
import json

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.vvix_lookup import vvix_lookup


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
    vvix_index_value: float
    vvix_velocity_3d: float
    state_key: str
    vvix_bin: str
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
            f" 📢 MARKET SIGMET — CBOE VOLATILITY OF VOLATILITY INDEX (VVIX) [{self.sigmet_id}]\n"
            "================================================================================\n"
            f" 🕒 Timestamp UTC: {self.timestamp_utc} | Close Date: {self.as_of_date}\n"
            f" 🏢 Issuer: {self.issuer} | 🚦 Market Status: {self.market_status}\n"
            "--------------------------------------------------------------------------------\n"
            " 📊 LIVE TELEMETRY (72H FAST KINEMATICS):\n"
            f"    • VVIX Index Level : {self.vvix_index_value:.2f} [{self.vvix_bin}]\n"
            f"    • Velocity (Δ3d)   : {self.vvix_velocity_3d:+.2f} [{self.velocity_vector}]\n"
            f"    • State Key         : {self.state_key} (N = {self.n_samples} historical days)\n\n"
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


def get_vvix_market_sigmet(as_of_date: Optional[str] = None) -> MarketSIGMET:
    """
    Generates an authoritative VVIX Market SIGMET on-demand using 3-day fast velocity.
    Strict Data Policy: Zero Fallbacks. If a requested as_of_date is specified and does NOT exist
    in Neon Vault, raises StrictDataPolicyError immediately.
    """
    store = TimescaleDataStore()
    conn = store._conn()
    try:
        import pandas as pd

        latest_bar_query = "SELECT MAX(time::date) as max_date FROM market.ohlcv_bars WHERE ticker = 'VVIX' AND timeframe = '1d'"
        df_max = pd.read_sql(latest_bar_query, conn)
        overall_latest = str(df_max.iloc[0]['max_date']) if len(df_max) > 0 and pd.notna(df_max.iloc[0]['max_date']) else "UNKNOWN"

        if as_of_date:
            sql_query = f"""
                SELECT time::date as date, close as vvix
                FROM market.ohlcv_bars
                WHERE ticker = 'VVIX'
                  AND timeframe = '1d'
                  AND time <= '{as_of_date}'
                ORDER BY time DESC
                LIMIT 5
            """
            df_vvix = pd.read_sql(sql_query, conn)
            
            if len(df_vvix) < 4 or str(df_vvix.iloc[0]['date']) != as_of_date:
                raise StrictDataPolicyError(
                    f"⚠️ SIGMET NOT AVAILABLE: Data not updated in Neon Vault for the requested date ({as_of_date}). "
                    f"The latest valid bar registered in Vault is ({overall_latest})."
                )
        else:
            sql_query = """
                SELECT time::date as date, close as vvix
                FROM market.ohlcv_bars
                WHERE ticker = 'VVIX'
                  AND timeframe = '1d'
                ORDER BY time DESC
                LIMIT 5
            """
            df_vvix = pd.read_sql(sql_query, conn)
            
            if len(df_vvix) < 4:
                raise StrictDataPolicyError(
                    f"⚠️ SIGMET NOT AVAILABLE: Insufficient historical VVIX bars in Neon Vault "
                    f"to compute 3-day velocity. Required >= 4, found {len(df_vvix)}."
                )
            
        df_vvix = df_vvix.sort_values('date')
        latest_row = df_vvix.iloc[-1]
        t3_row = df_vvix.iloc[-4]
        
        latest_date_str = str(latest_row['date'])

        vvix_val = float(latest_row['vvix'])
        vvix_d3 = float(vvix_val - float(t3_row['vvix']))

        guidance = vvix_lookup.lookup_vvix_guidance(vvix_val=vvix_val, vvix_d3=vvix_d3)
        if not guidance:
            raise StrictDataPolicyError(
                f"⚠️ SIGMET NOT AVAILABLE: Unmapped state key in Fact Store for VVIX={vvix_val}, d3={vvix_d3}."
            )

        vec = guidance.to_vector()
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        clean_date = latest_date_str.replace("-", "")
        sigmet_id = f"SIGMET-VVIX-{clean_date}-001"

        if guidance.operational_guidance == "STK_BLOCK_CRISIS":
            status = "CRISIS_VETO"
        elif guidance.divergence_regime in ("TACTICAL_BOUNCE_ONLY", "TACTICAL_PULLBACK"):
            status = "RESTRICTED"
        else:
            status = "CLEAR"

        return MarketSIGMET(
            sigmet_id=sigmet_id,
            timestamp_utc=now_utc,
            as_of_date=latest_date_str,
            issuer="MarketHealthIntelligence.VVIXVolatilityAdapter",
            market_status=status,
            vvix_index_value=vvix_val,
            vvix_velocity_3d=vvix_d3,
            state_key=guidance.state_key,
            vvix_bin=guidance.vvix_bin,
            velocity_vector=guidance.velocity_vector,
            n_samples=guidance.n,
            divergence_regime=guidance.divergence_regime,
            operational_guidance=guidance.operational_guidance,
            p_bull_vector=vec["p_bull"],
            p_bear_vector=vec["p_bear"],
            ev_net_vector=vec["ev_net"],
            e_days_vector=vec["e_days"],
            ev_per_day_vector=vec["ev_per_day"],
            primary_p_bull=vec["primary_p_bull"],
            primary_ev_net=vec["primary_ev_net"],
            primary_e_days=vec["primary_e_days"],
            primary_capital_velocity=vec["primary_capital_velocity"],
            rr_asymmetry_ratio=guidance.zz50.rr_asymmetry
        )

    finally:
        store._put(conn)
