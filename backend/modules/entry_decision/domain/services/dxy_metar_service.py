import numpy as np
"""
US Dollar Index (DXY) Market METAR Service — Pure Domain Service
================================================================
Generates authoritative, zero-fallback DXY Market METARs.
Evaluates Global Sovereign Liquidity, FX Squeeze, & Commodity Inflation Dynamics.
Uses 3-Day Fast Kinematic Velocity (Delta 3d - 72h) and 150-State Gaussian Calibration.
Strict Data Policy: Zero Fallbacks. If a requested date is missing in Neon Vault,
raises StrictDataPolicyError immediately.
"""
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
import json

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.dxy_lookup import dxy_lookup


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
    dxy_index_value: float
    dxy_velocity_3d: float
    state_key: str
    dxy_bin: str
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


def get_dxy_market_metar(as_of_date: Optional[str] = None) -> MarketMETAR:
    """
    Generates an authoritative DXY Market METAR on-demand using 3-day fast velocity.
    Strict Data Policy: Zero Fallbacks.
    """
    store = TimescaleDataStore()
    engine = store.engine
    try:
        import pandas as pd

        latest_bar_query = "SELECT MAX(time::date) as max_date FROM market.ohlcv_bars WHERE ticker IN ('DXY', 'DX-Y.NYB') AND timeframe = '1d'"
        df_max = pd.read_sql(latest_bar_query, engine)
        overall_latest = str(df_max.iloc[0]['max_date']) if len(df_max) > 0 and pd.notna(df_max.iloc[0]['max_date']) else "UNKNOWN"

        if as_of_date:
            target_date = as_of_date
            check_query = f"SELECT COUNT(*) as count FROM market.ohlcv_bars WHERE ticker IN ('DXY', 'DX-Y.NYB') AND timeframe = '1d' AND time::date = '{target_date}'"
            df_check = pd.read_sql(check_query, engine)
            if len(df_check) == 0 or df_check.iloc[0]['count'] == 0:
                raise StrictDataPolicyError(
                    f"STRICT DATA POLICY: DXY METAR NOT AVAILABLE for requested date '{as_of_date}'. "
                    f"Vault data does not exist for this timestamp. Latest available date in Vault is '{overall_latest}'."
                )
        else:
            target_date = overall_latest
            if target_date == "UNKNOWN":
                raise StrictDataPolicyError(
                    "STRICT DATA POLICY: DXY METAR NOT AVAILABLE. Neon Vault contains zero OHLCV bars for ticker 'DXY'."
                )

        query = f"""
            SELECT time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ('DXY', 'DX-Y.NYB') AND timeframe = '1d' AND time::date <= '{target_date}'
            ORDER BY time DESC LIMIT 30
        """
        df_dxy = pd.read_sql(query, engine)
        if len(df_dxy) < 4:
            raise StrictDataPolicyError(
                f"STRICT DATA POLICY: DXY METAR NOT AVAILABLE for date '{target_date}'. "
                f"Insufficient historical bars in Vault ({len(df_dxy)} bars found, minimum 4 required)."
            )

        df_dxy = df_dxy.sort_values("date").reset_index(drop=True)
        dxy_val = float(df_dxy.iloc[-1]['close'])
        t3_val = float(df_dxy.iloc[-4]['close']) if len(df_dxy) >= 4 else dxy_val
        d3_vel = float(dxy_val - t3_val)

        s_val = df_dxy['close']
        vol_2d = s_val.rolling(2).std()
        vol_10d = s_val.rolling(10).std().replace(0, np.nan)
        s_vol_norm = (vol_2d / vol_10d).fillna(1.0)
        vol_norm = float(s_vol_norm.iloc[-1])
        vol_d3 = float(vol_norm - float(s_vol_norm.iloc[-4])) if len(s_vol_norm) >= 4 else 0.0

        guidance = dxy_lookup.lookup_dxy_guidance(val=dxy_val, d3_speed=d3_vel, vol_norm=vol_norm, vol_d3=vol_d3)
        if not guidance:
            raise StrictDataPolicyError(
                f"⚠️ METAR NOT AVAILABLE: Unmapped state key in Fact Store for DXY={dxy_val}, d3={d3_vel}."
            )

        vec = guidance.to_vector()
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        clean_date = str(df_dxy.iloc[-1]['date']).replace("-", "")
        metar_id = f"METAR-DXY-{clean_date}-001"

        if guidance.operational_guidance == "STK_BLOCK_CRISIS":
            status = "DOLLAR_CRISIS_VETO"
        elif guidance.dxy_bin == "ELEVATED_DOLLAR_STRESS":
            status = "DOLLAR_STRESS_WARNING"
        elif guidance.dxy_bin in ("WEAK_DOLLAR", "DEEP_DOLLAR_CRUSH"):
            status = "REFLATIONARY_EASE"
        else:
            status = "BALANCED_DOLLAR"

        return MarketMETAR(
            metar_id=metar_id,
            timestamp_utc=now_utc,
            as_of_date=str(df_dxy.iloc[-1]['date']),
            issuer="Botero-Trade DXY Dollar Intelligence Engine",
            market_status=status,
            dxy_index_value=dxy_val,
            dxy_velocity_3d=d3_vel,
            state_key=guidance.state_key,
            dxy_bin=guidance.dxy_bin,
            velocity_vector=guidance.velocity_vector,
            n_samples=guidance.n,
            divergence_regime=guidance.divergence_regime,
            operational_guidance=guidance.operational_guidance,
            p_bull_vector=[guidance.zz25.p_bull, guidance.zz50.p_bull, guidance.zz75.p_bull],
            p_bear_vector=[guidance.zz25.p_bear, guidance.zz50.p_bear, guidance.zz75.p_bear],
            ev_net_vector=[guidance.zz25.ev_net, guidance.zz50.ev_net, guidance.zz75.ev_net],
            e_days_vector=[2.5, 5.0, 7.5],
            ev_per_day_vector=[guidance.zz25.ev_per_day, guidance.zz50.ev_per_day, guidance.zz75.ev_per_day],
            primary_p_bull=guidance.zz50.p_bull,
            primary_ev_net=guidance.zz50.ev_net,
            primary_e_days=5.0,
            primary_capital_velocity=guidance.zz50.ev_per_day,
            rr_asymmetry_ratio=guidance.zz50.rr_asymmetry,
        )
    finally:
        store.close()
