import numpy as np
"""
Institutional Volume Turbulence (SV5_TURBULENCE) Market METAR Service — Pure Domain Service
=============================================================================================
Generates authoritative, zero-fallback SV5_TURBULENCE Market METARs.
Uses 3-Day Fast Kinematic Velocity (Delta 3d - 72h) for ultra-fast reaction.
Strict Data Policy: Zero Fallbacks. If a requested date is missing or not valid in Neon Vault,
raises StrictDataPolicyError immediately with explicit 'METAR NOT AVAILABLE' message in English.
Always includes exact UTC date and time.
"""
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
import json

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.sv5_turbulence_lookup import sv5_turbulence_lookup


class StrictDataPolicyError(Exception):
    """Raised when required market data or Fact Store parameters are missing. Zero Fallbacks allowed."""
    pass


@dataclass(frozen=True)
class MarketMETAR:
    metar_id: str
    timestamp_utc: str
    as_of_date: str
    issuer: str
    market_status: str
    turbulence_index_value: float
    turbulence_velocity_3d: float
    state_key: str
    turbulence_bin: str
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
        """Returns full structured METAR payload as a dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Returns formatted JSON string of the METAR."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def format_cli_broadcast(self) -> str:
        """Formats the METAR into a high-visibility CLI / Telegram broadcast string."""
        return (
            "================================================================================\n"
            f" 📢 MARKET METAR — INSTITUTIONAL VOLUME TURBULENCE (SV5_TURBULENCE) [{self.metar_id}]\n"
            "================================================================================\n"
            f" 🕒 Timestamp UTC: {self.timestamp_utc} | Close Date: {self.as_of_date}\n"
            f" 🏢 Issuer: {self.issuer} | 🚦 Market Status: {self.market_status}\n"
            "--------------------------------------------------------------------------------\n"
            " 📊 LIVE TELEMETRY (72H FAST KINEMATICS):\n"
            f"    • Turbulence Index : {self.turbulence_index_value:.2f} [{self.turbulence_bin}]\n"
            f"    • Velocity (Δ3d)   : {self.turbulence_velocity_3d:+.2f} [{self.velocity_vector}]\n"
            f"    • State Key        : {self.state_key} (N = {self.n_samples} historical days)\n\n"
            " 🔮 STOCHASTIC FORECAST & HORIZON DIVERGENCE:\n"
            f"    • Active Regime    : {self.divergence_regime}\n"
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


def get_sv5_turbulence_market_metar(as_of_date: Optional[str] = None) -> MarketMETAR:
    """
    Generates an authoritative SV5_TURBULENCE Market METAR on-demand using 3-day fast velocity.
    Strict Data Policy: Zero Fallbacks. If a requested as_of_date is specified and does NOT exist
    in Neon Vault, raises StrictDataPolicyError immediately.
    """
    store = TimescaleDataStore()
    engine = store.engine
    try:
        import pandas as pd

        latest_bar_query = "SELECT MAX(time::date) as max_date FROM market.ohlcv_bars WHERE ticker IN ('SV5_TURBULENCE', 'SV5_SHOCK') AND timeframe = '1d'"
        df_max = pd.read_sql(latest_bar_query, engine)
        overall_latest = str(df_max.iloc[0]['max_date']) if len(df_max) > 0 and pd.notna(df_max.iloc[0]['max_date']) else "UNKNOWN"

        if as_of_date:
            sql_query = f"""
                SELECT time::date as date, close as turbulence
                FROM market.ohlcv_bars
                WHERE ticker IN ('SV5_TURBULENCE', 'SV5_SHOCK')
                  AND timeframe = '1d'
                  AND time::date <= '{as_of_date}'
                ORDER BY time DESC
                LIMIT 30
            """
            df_turb = pd.read_sql(sql_query, engine)
            
            if len(df_turb) < 4:
                raise StrictDataPolicyError(
                    f"⚠️ METAR NOT AVAILABLE: Data not updated in Neon Vault for the requested date ({as_of_date}). "
                    f"The latest valid bar registered in Vault is ({overall_latest})."
                )
        else:
            sql_query = """
                SELECT time::date as date, close as turbulence
                FROM market.ohlcv_bars
                WHERE ticker IN ('SV5_TURBULENCE', 'SV5_SHOCK')
                  AND timeframe = '1d'
                ORDER BY time DESC
                LIMIT 30
            """
            df_turb = pd.read_sql(sql_query, engine)
            
            if len(df_turb) < 4:
                raise StrictDataPolicyError(
                    f"⚠️ METAR NOT AVAILABLE: Insufficient historical SV5_TURBULENCE bars in Neon Vault "
                    f"to compute 3-day velocity. Required >= 4, found {len(df_turb)}."
                )
            
        df_turb = df_turb.sort_values('date').reset_index(drop=True)
        latest_row = df_turb.iloc[-1]
        t3_row = df_turb.iloc[-4]
        
        latest_date_str = str(latest_row['date'])

        turb_val = float(latest_row['turbulence'])
        turb_d3 = float(turb_val - float(t3_row['turbulence']))

        # Compute L2 Kinematic Pivot
        last5 = df_turb.tail(5)
        min5 = float(last5.iloc[:, -1].min())
        max5 = float(last5.iloc[:, -1].max())
        prev_val = float(df_turb.iloc[-2].iloc[-1]) if len(df_turb) >= 2 else turb_val
        d1 = float(turb_val - prev_val)

        if turb_val >= max5 - 0.5 and d1 >= 0:
            pivot = "PANIC_SPIKE_CAPITULATION"
        elif prev_val >= max5 - 0.5 and d1 < 0:
            pivot = "VOL_CRUSH_REBOUND"
        elif turb_val <= min5 + 0.5 and d1 <= 0:
            pivot = "COMPLACENCY_FLOOR"
        else:
            pivot = "STABLE_CONTINUATION"

        s_val = df_turb.iloc[:, -1] if 'close' not in df_turb.columns else df_turb['close']
        vol_5d = s_val.rolling(5).std()
        vol_20d = s_val.rolling(20).std().replace(0, np.nan)
        s_vol_norm = (vol_5d / vol_20d).fillna(1.0)
        vol_norm = float(s_vol_norm.iloc[-1])
        vol_d3 = float(vol_norm - float(s_vol_norm.iloc[-4])) if len(s_vol_norm) >= 4 else 0.0

        s_val = df_turb.iloc[:, -1] if 'close' not in df_turb.columns else df_turb['close']
        vol_5d = s_val.rolling(5).std()
        vol_20d = s_val.rolling(20).std().replace(0, np.nan)
        s_vol_norm = (vol_5d / vol_20d).fillna(1.0)
        vol_norm = float(s_vol_norm.iloc[-1])
        vol_d3 = float(vol_norm - float(s_vol_norm.iloc[-4])) if len(s_vol_norm) >= 4 else 0.0

        guidance = sv5_turbulence_lookup.lookup_sv5_turbulence_guidance(val=turb_val, d3_speed=turb_d3, vol_norm=vol_norm, vol_d3=vol_d3)
        if not guidance:
            raise StrictDataPolicyError(
                f"⚠️ METAR NOT AVAILABLE: Unmapped state key in Fact Store for SV5_TURBULENCE={turb_val}, d3={turb_d3}."
            )

        vec = guidance.to_vector()
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        clean_date = latest_date_str.replace("-", "")
        metar_id = f"METAR-SV5TURB-{clean_date}-001"

        if guidance.operational_guidance == "STK_BLOCK_CRISIS":
            status = "CRISIS_VETO"
        elif guidance.divergence_regime in ("TACTICAL_BOUNCE_ONLY", "TACTICAL_PULLBACK"):
            status = "RESTRICTED"
        else:
            status = "CLEAR"

        return MarketMETAR(
            metar_id=metar_id,
            timestamp_utc=now_utc,
            as_of_date=latest_date_str,
            issuer="MarketHealthIntelligence.SV5TurbulenceAdapter",
            market_status=status,
            turbulence_index_value=turb_val,
            turbulence_velocity_3d=turb_d3,
            state_key=guidance.state_key,
            turbulence_bin=guidance.turbulence_bin,
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
        store.close()
