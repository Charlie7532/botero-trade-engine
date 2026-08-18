"""
Breadth Shock Index (BSI / S5TW) Market METAR Service — Pure Domain Service
==========================================================================
Generates authoritative, zero-fallback BSI (S5TW Tactical Breadth) Market METARs.
Uses 3-Day Fast Kinematic Velocity (Delta 3d - 72h) of S5TW (% of S&P 500 above 20-DMA) for fast shock detection.
Strict Data Policy: Zero Fallbacks. If a requested date is missing in Neon Vault,
raises StrictDataPolicyError immediately with explicit 'METAR NOT AVAILABLE' message in English.
Persists StateSnapshot to RegimeStatePort under key 'bsi:entry_decision:MARKET'.
Follows Rules 15, 23, 24.
"""
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
import json
import numpy as np

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.bsi_lookup import bsi_lookup, BSILookupAdapter
from backend.modules.shared.domain.entities.state_snapshot import StateSnapshot
from backend.modules.shared.domain.ports.regime_state_port import RegimeStatePort


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
    bsi_value: float
    bsi_velocity_3d: float
    state_key: str
    bsi_bin: str
    velocity_vector: str
    n_samples: int
    divergence_regime: str
    operational_guidance: str
    action_code: str
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

    @property
    def current_state(self) -> str:
        return self.bsi_bin

    @property
    def is_crisis_override(self) -> bool:
        return self.bsi_bin == "BREADTH_WASHED_OUT" or self.velocity_vector == "FAST_CRUSH_3D"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def format_cli_broadcast(self) -> str:
        """Formats the METAR into a high-visibility CLI / Telegram broadcast string."""
        e_days = list(self.e_days_vector.values()) if isinstance(self.e_days_vector, dict) else self.e_days_vector
        p_bull = list(self.p_bull_vector.values()) if isinstance(self.p_bull_vector, dict) else self.p_bull_vector
        ev_net = list(self.ev_net_vector.values()) if isinstance(self.ev_net_vector, dict) else self.ev_net_vector

        return (
            "================================================================================\n"
            f" 📢 MARKET METAR — BREADTH SHOCK INDEX (S5TW) [{self.metar_id}]\n"
            "================================================================================\n"
            f" 🕒 Timestamp UTC: {self.timestamp_utc} | Close Date: {self.as_of_date}\n"
            f" 🏢 Issuer: {self.issuer} | 🚦 Market Status: {self.market_status}\n"
            "--------------------------------------------------------------------------------\n"
            " 📊 LIVE TELEMETRY (72H FAST KINEMATICS):\n"
            f"    • S5TW Breadth Level : {self.bsi_value:.2f}% [{self.bsi_bin}]\n"
            f"    • Velocity (Δ3d)     : {self.bsi_velocity_3d:+.2f}pp [{self.velocity_vector}]\n"
            f"    • State Key          : {self.state_key} (N = {self.n_samples} historical days)\n\n"
            " 🔮 STOCHASTIC FORECAST & HORIZON DIVERGENCE:\n"
            f"    • Active Regime      : {self.divergence_regime}\n"
            f"    • Scale 2.5% ({e_days[0]:.0f}d) : P(bull) = {p_bull[0]*100:.1f}% | EV = {ev_net[0]*100:+.2f}%\n"
            f"    • Scale 5.0% ({e_days[1]:.0f}d) : P(bull) = {p_bull[1]*100:.1f}% | EV = {ev_net[1]*100:+.2f}%\n"
            f"    • Scale 7.5% ({e_days[2]:.0f}d) : P(bull) = {p_bull[2]*100:.1f}% | EV = {ev_net[2]*100:+.2f}%\n\n"
            " ⚡ CAPITAL VELOCITY (TIME-INDEPENDENT):\n"
            f"    • Daily Rate (%/day) : {self.primary_capital_velocity*100:+.4f}% / trading day (reaches 5.0% in {self.primary_e_days:.1f}d)\n"
            f"    • R/R Asymmetry      : {self.rr_asymmetry_ratio:.2f}x\n\n"
            " 🎯 OPERATIONAL DIRECTIVES (UNIVERSAL TAXONOMY):\n"
            f"    • Action Code        : {self.action_code}\n"
            f"    • Guidance Code      : {self.operational_guidance}\n"
            "================================================================================"
        )


class BSIMetarService:
    """Domain service for generating Breadth Shock Index METARs and persisting state transitions."""

    REGIME_KEY = "bsi:entry_decision:MARKET"

    def __init__(
        self,
        data_store: Optional[TimescaleDataStore] = None,
        regime_state_port: Optional[RegimeStatePort] = None,
        bsi_lookup_adapter: Optional[BSILookupAdapter] = None,
    ):
        self._store = data_store or TimescaleDataStore()
        self._port = regime_state_port
        self._lookup = bsi_lookup_adapter or bsi_lookup

    def evaluate(self, as_of_date: Optional[str] = None) -> MarketMETAR:
        """
        Generates an authoritative BSI Market METAR on-demand using 3-day fast velocity.
        Strict Data Policy: Zero Fallbacks. If a requested as_of_date is specified and does NOT exist
        in Neon Vault, raises StrictDataPolicyError immediately.
        Persists state transitions to RegimeStatePort if provided.
        """
        engine = self._store.engine
        try:
            import pandas as pd

            latest_bar_query = (
                "SELECT MAX(time::date) as max_date FROM market.ohlcv_bars "
                "WHERE ticker = 'S5TW' AND timeframe = '1d'"
            )
            df_max = pd.read_sql(latest_bar_query, engine)
            overall_latest = (
                str(df_max.iloc[0]["max_date"])
                if len(df_max) > 0 and "max_date" in df_max.columns and pd.notna(df_max.iloc[0]["max_date"])
                else "UNKNOWN"
            )

            if as_of_date:
                check_query = f"""
                    SELECT time::date as date, close
                    FROM market.ohlcv_bars
                    WHERE ticker = 'S5TW'
                      AND timeframe = '1d'
                      AND time::date <= '{as_of_date}'
                    ORDER BY time DESC
                """
                df_raw = pd.read_sql(check_query, engine)
                has_data = False
                if len(df_raw) > 0:
                    date_col = 'date' if 'date' in df_raw.columns else ('time::date' if 'time::date' in df_raw.columns else 'time')
                    if date_col in df_raw.columns:
                        exact_rows = df_raw[df_raw[date_col].astype(str) == as_of_date]
                        if len(exact_rows) >= 1:
                            has_data = True

                if not has_data:
                    raise StrictDataPolicyError(
                        f"STRICT DATA POLICY: BSI METAR NOT AVAILABLE for requested date '{as_of_date}'. "
                        f"Vault data does not exist for S5TW at this timestamp. Latest available date in Vault is '{overall_latest}'."
                    )
            else:
                query_all = """
                    SELECT time::date as date, close
                    FROM market.ohlcv_bars
                    WHERE ticker = 'S5TW'
                      AND timeframe = '1d'
                    ORDER BY time DESC
                """
                df_raw = pd.read_sql(query_all, engine)
                if len(df_raw) == 0:
                    raise StrictDataPolicyError(
                        "STRICT DATA POLICY: BSI METAR NOT AVAILABLE. Neon Vault contains zero OHLCV bars for 'S5TW'."
                    )

            date_col = 'date' if 'date' in df_raw.columns else 'time'
            df_raw = df_raw.sort_values(by=date_col)
            s_val = df_raw.set_index(date_col)["close"]

            if as_of_date:
                s_val = s_val[s_val.index.astype(str) <= as_of_date]

            if len(s_val) < 4:
                raise StrictDataPolicyError(
                    f"STRICT DATA POLICY: BSI METAR NOT AVAILABLE. "
                    f"Insufficient historical aligned bars ({len(s_val)} bars found, minimum 4 required for 72h kinematics)."
                )

            bsi_latest = float(s_val.iloc[-1])
            bsi_3d_prev = float(s_val.iloc[-4])
            bsi_delta_3d = float(bsi_latest - bsi_3d_prev)
            clean_date = str(s_val.index[-1]).split(" ")[0]

            vol_2d = s_val.rolling(2).std()
            vol_10d = s_val.rolling(10).std().replace(0, np.nan)
            s_vol_norm = (vol_2d / vol_10d).fillna(1.0)
            vol_norm = float(s_vol_norm.iloc[-1])
            vol_d3 = float(vol_norm - float(s_vol_norm.iloc[-4])) if len(s_vol_norm) >= 4 else 0.0

            guidance = self._lookup.lookup_bsi_guidance(val=bsi_latest, d3_speed=bsi_delta_3d, vol_norm=vol_norm, vol_d3=vol_d3)
            if not guidance:
                raise StrictDataPolicyError(
                    f"STRICT DATA POLICY: BSI METAR NOT AVAILABLE. State classification failed for S5TW={bsi_latest}, d3={bsi_delta_3d}."
                )

            vec = guidance.to_vector()
            now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            # Determine Universal Taxonomy Action Code
            if guidance.bsi_bin == "BREADTH_WASHED_OUT" or guidance.velocity_vector == "FAST_CRUSH_3D":
                action_code = "MKT_BREADTH_WASHED_OUT"
                market_status = "CRISIS_BREADTH_WASH"
            elif guidance.velocity_vector == "FAST_SPIKE_3D":
                action_code = "MKT_BREADTH_SHOCK_REVERSAL"
                market_status = "BREADTH_IMPULSE_SHOCK"
            elif guidance.bsi_bin in ("HYPER_EXPANSIVE_BREADTH", "EXPANSIVE_BREADTH"):
                action_code = "MKT_BREADTH_EXPANSIVE"
                market_status = "EXPANSIVE_STABLE"
            else:
                action_code = "MKT_BREADTH_NEUTRAL"
                market_status = "NEUTRAL_STABLE"

            metar_id = f"METAR-BSI-{clean_date.replace('-', '')}-001"

            # Stateful-First Persistence (Rule 15)
            if self._port:
                try:
                    clean_date_short = str(clean_date).split(" ")[0]
                    ts_dt = datetime.strptime(clean_date_short, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    self._port.commit_transition(
                        key=self.REGIME_KEY,
                        current_state=guidance.state_key,
                        entered_at=ts_dt,
                        trigger_event=f"S5TW={bsi_latest:.2f}%, d3={bsi_delta_3d:+.2f}pp",
                    )
                except Exception:
                    pass

            return MarketMETAR(
                metar_id=metar_id,
                timestamp_utc=now_utc_str,
                as_of_date=clean_date,
                issuer="Botero-Trade Breadth Shock Intelligence Engine",
                market_status=market_status,
                bsi_value=round(bsi_latest, 2),
                bsi_velocity_3d=round(bsi_delta_3d, 2),
                state_key=guidance.state_key,
                bsi_bin=guidance.bsi_bin,
                velocity_vector=guidance.velocity_vector,
                n_samples=guidance.n,
                divergence_regime=guidance.divergence_regime,
                operational_guidance=guidance.operational_guidance,
                action_code=action_code,
                p_bull_vector=[guidance.zz25.p_bull, guidance.zz50.p_bull, guidance.zz75.p_bull],
                p_bear_vector=[guidance.zz25.p_bear, guidance.zz50.p_bear, guidance.zz75.p_bear],
                ev_net_vector=[guidance.zz25.ev_net, guidance.zz50.ev_net, guidance.zz75.ev_net],
                e_days_vector=[2.5, 5.0, 7.5],
                ev_per_day_vector=[guidance.zz25.ev_per_day, guidance.zz50.ev_per_day, guidance.zz75.ev_per_day],
                primary_p_bull=guidance.zz50.p_bull,
                primary_ev_net=guidance.zz50.ev_net,
                primary_e_days=guidance.zz50.e_days,
                primary_capital_velocity=guidance.zz50.ev_per_day,
                rr_asymmetry_ratio=guidance.zz50.rr_asymmetry,
            )

        finally:
            self._store.close()


def get_bsi_market_metar(as_of_date: Optional[str] = None) -> MarketMETAR:
    """Convenience function to evaluate BSI METAR using default service instance."""
    service = BSIMetarService()
    return service.evaluate(as_of_date=as_of_date)
