"""
DXY (US Dollar Index) Market METAR Service — 11th METAR Station
===============================================================
Computes authoritative DXY Market METAR telemetry using 3-day fast velocity Δ3d
and volatility magnitude D3.

Zero Fallbacks Policy: Inputs read from Neon Vault.
Follows Clean & Hexagonal Architecture rules.
"""
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.dxy_lookup import (
    dxy_lookup,
    DXYStateGuidance,
)

logger = logging.getLogger(__name__)


class StrictDataPolicyError(Exception):
    """Raised when Neon Vault lacks required DXY bar data."""
    pass


@dataclass(frozen=True)
class DXYMarketMETAR:
    metar_id: str
    timestamp_utc: str
    as_of_date: str
    issuer: str
    market_status: str
    dxy_index_value: float
    dxy_velocity_3d: float
    state_key: str
    dxy_bin: str
    velocity_vector: str
    n_samples: int
    divergence_regime: str
    operational_guidance: str
    p_bull_vector: List[float]
    p_bear_vector: List[float]
    ev_net_vector: List[float]
    e_days_vector: List[float]
    ev_per_day_vector: List[float]
    primary_p_bull: float
    primary_ev_net: float
    primary_e_days: float
    primary_capital_velocity: float
    rr_asymmetry_ratio: float
    zigzag_kinematic: Optional[Dict[str, Any]] = None
    sigma_depth_d1: Optional[float] = None
    sigma_depth_d2: Optional[float] = None
    sigma_depth_d3: Optional[float] = None
    overflow_flag: Optional[str] = None
    e_ret_max_zz75: Optional[float] = None
    e_ret_min_zz75: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Returns full structured METAR payload as a dictionary."""
        return asdict(self)

    def format_cli_broadcast(self) -> str:
        """Formats the METAR into a high-visibility CLI broadcast string."""
        return (
            "================================================================================\n"
            f" 📢 MARKET METAR — DXY US DOLLAR INDEX [{self.metar_id}]\n"
            "================================================================================\n"
            f" 🕒 Timestamp UTC: {self.timestamp_utc} | Close Date: {self.as_of_date}\n"
            f" 🏢 Issuer: {self.issuer} | 🚦 Market Status: {self.market_status}\n"
            "--------------------------------------------------------------------------------\n"
            " 📊 LIVE TELEMETRY (72H FAST KINEMATICS):\n"
            f"    • DXY Index Level : {self.dxy_index_value:.2f} [{self.dxy_bin}]\n"
            f"    • Velocity (Δ3d)  : {self.dxy_velocity_3d:+.2f} [{self.velocity_vector}]\n"
            f"    • State Key        : {self.state_key} (N = {self.n_samples} historical days)\n\n"
            " 🔮 STOCHASTIC FORECAST & HORIZON DIVERGENCE:\n"
            f"    • Active Regime    : {self.divergence_regime}\n"
            f"    • Scale 2.5% ({self.e_days_vector[0]:.0f}d) : P(bull) = {self.p_bull_vector[0]*100:.1f}% | EV = {self.ev_net_vector[0]*100:+.2f}%\n"
            f"    • Scale 5.0% ({self.e_days_vector[1]:.0f}d) : P(bull) = {self.p_bull_vector[1]*100:.1f}% | EV = {self.ev_net_vector[1]*100:+.2f}%\n"
            f"    • Scale 7.5% ({self.e_days_vector[2]:.0f}d) : P(bull) = {self.p_bull_vector[2]*100:.1f}% | EV = {self.ev_net_vector[2]*100:+.2f}%\n\n"
            " ⚡ CAPITAL VELOCITY (TIME-INDEPENDENT):\n"
            f"    • Daily Rate (%/day): {self.primary_capital_velocity*100:+.4f}% / trading day\n"
            f"    • R/R Asymmetry    : {self.rr_asymmetry_ratio:.2f}x\n\n"
            " 🎯 OPERATIONAL DIRECTIVES (UNIVERSAL TAXONOMY):\n"
            f"    • Taxonomy Code    : {self.operational_guidance}\n"
            "================================================================================"
        )


def get_dxy_market_metar(as_of_date: Optional[str] = None) -> DXYMarketMETAR:
    """
    Generates authoritative DXY Market METAR using 3-day velocity Δ3d.
    Reads exclusively from Neon Vault market.ohlcv_bars.
    Raises StrictDataPolicyError if data is missing.
    """
    store = TimescaleDataStore()
    engine = store.engine
    try:
        import pandas as pd
        import numpy as np

        latest_bar_query = "SELECT MAX(time::date) as max_date FROM market.ohlcv_bars WHERE ticker = 'DXY' AND timeframe = '1d'"
        df_max = pd.read_sql(latest_bar_query, engine)
        overall_latest = str(df_max.iloc[0]['max_date']) if len(df_max) > 0 and pd.notna(df_max.iloc[0]['max_date']) else "UNKNOWN"

        if as_of_date:
            sql_query = f"""
                SELECT time::date as date, close as dxy
                FROM market.ohlcv_bars
                WHERE ticker = 'DXY'
                  AND timeframe = '1d'
                  AND time::date <= '{as_of_date}'
                ORDER BY time DESC
                LIMIT 30
            """
            df_dxy = pd.read_sql(sql_query, engine)
            if len(df_dxy) < 4 or str(df_dxy.iloc[0]['date']) != as_of_date:
                raise StrictDataPolicyError(
                    f"⚠️ METAR NOT AVAILABLE: Data not updated in Neon Vault for DXY on date ({as_of_date}). "
                    f"Latest valid bar in Vault: ({overall_latest})."
                )
        else:
            sql_query = """
                SELECT time::date as date, close as dxy
                FROM market.ohlcv_bars
                WHERE ticker = 'DXY'
                  AND timeframe = '1d'
                ORDER BY time DESC
                LIMIT 30
            """
            df_dxy = pd.read_sql(sql_query, engine)
            if len(df_dxy) < 4:
                raise StrictDataPolicyError(
                    f"⚠️ METAR NOT AVAILABLE: Insufficient historical DXY bars in Neon Vault "
                    f"(found {len(df_dxy)}, required >= 4)."
                )

        df_dxy = df_dxy.sort_values('date').reset_index(drop=True)
        latest_row = df_dxy.iloc[-1]
        t3_row = df_dxy.iloc[-4]

        latest_date_str = str(latest_row['date'])
        dxy_val = float(latest_row['dxy'])
        dxy_d3 = float(dxy_val - float(t3_row['dxy']))

        # D3: Station Volatility std(2d)/std(10d) V1.1
        vol_2d = df_dxy['dxy'].rolling(2).std()
        vol_10d = df_dxy['dxy'].rolling(10).std().replace(0, np.nan)
        s_vol_norm = (vol_2d / vol_10d).fillna(1.0)
        vol_norm = float(s_vol_norm.iloc[-1])

        guidance = dxy_lookup.lookup_dxy_guidance(val=dxy_val, d3_speed=dxy_d3, vol_norm=vol_norm)
        if not guidance:
            raise StrictDataPolicyError(
                f"⚠️ METAR NOT AVAILABLE: Unmapped state key in Fact Store for DXY={dxy_val}, d3={dxy_d3}."
            )

        vec = guidance.to_vector()
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        clean_date = latest_date_str.replace("-", "")
        metar_id = f"METAR-DXY-{clean_date}-001"

        if guidance.operational_guidance == "STK_BLOCK_CRISIS":
            status = "CRISIS_VETO"
        elif guidance.divergence_regime in ("TACTICAL_BOUNCE_ONLY", "TACTICAL_PULLBACK"):
            status = "RESTRICTED"
        else:
            status = "CLEAR"

        return DXYMarketMETAR(
            metar_id=metar_id,
            timestamp_utc=now_utc,
            as_of_date=latest_date_str,
            issuer="MarketHealthIntelligence.DXYLiquidityAdapter",
            market_status=status,
            dxy_index_value=dxy_val,
            dxy_velocity_3d=dxy_d3,
            state_key=guidance.state_key,
            dxy_bin=guidance.dxy_bin,
            velocity_vector=guidance.velocity_vector,
            n_samples=guidance.n,
            divergence_regime=guidance.divergence_regime,
            operational_guidance=guidance.operational_guidance,
            p_bull_vector=[guidance.zz25.p_bull, guidance.zz50.p_bull, guidance.zz75.p_bull],
            p_bear_vector=[guidance.zz25.p_bear, guidance.zz50.p_bear, guidance.zz75.p_bear],
            ev_net_vector=[guidance.zz25.ev_net, guidance.zz50.ev_net, guidance.zz75.ev_net],
            e_days_vector=[guidance.zz25.e_days, guidance.zz50.e_days, guidance.zz75.e_days],
            ev_per_day_vector=[guidance.zz25.ev_per_day, guidance.zz50.ev_per_day, guidance.zz75.ev_per_day],
            primary_p_bull=vec["primary_p_bull"],
            primary_ev_net=vec["primary_ev_net"],
            primary_e_days=vec["primary_e_days"],
            primary_capital_velocity=vec["primary_capital_velocity"],
            rr_asymmetry_ratio=guidance.zz50.rr_asymmetry,
            zigzag_kinematic=guidance.zigzag_kinematic,
            sigma_depth_d1=guidance.sigma_depth_d1,
            sigma_depth_d2=guidance.sigma_depth_d2,
            sigma_depth_d3=guidance.sigma_depth_d3,
            overflow_flag=guidance.overflow_flag,
            e_ret_max_zz75=guidance.zz75.e_ret_max,
            e_ret_min_zz75=guidance.zz75.e_ret_min,
        )

    finally:
        store.close()
