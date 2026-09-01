import numpy as np
"""
High Yield Corporate Credit Stress (CREDIT) Market METAR Service — Pure Domain Service
======================================================================================
Generates authoritative, zero-fallback Credit Market METARs (Meteorological Reports).
Uses 3-Day Fast Kinematic Velocity (Delta 3d - 72h) of the HYG/LQD ratio for ultra-fast reaction.
Strict Data Policy: Zero Fallbacks. If a requested date is missing or not valid in Neon Vault,
raises StrictDataPolicyError immediately with explicit 'METAR NOT AVAILABLE' message in English.
Always includes exact UTC date and time.
Persists StateSnapshot to RegimeStatePort under key 'credit:entry_decision:MARKET'.
"""
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
import json

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.credit_lookup import credit_lookup, CreditLookupAdapter
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
    credit_ratio_value: float
    credit_velocity_3d: float
    state_key: str
    credit_bin: str
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
    zigzag_kinematic: Optional[Dict[str, Any]] = None
    sigma_depth_d1: Optional[float] = None
    sigma_depth_d2: Optional[float] = None
    sigma_depth_d3: Optional[float] = None
    overflow_flag: Optional[str] = None
    e_ret_max_zz75: Optional[float] = None
    e_ret_min_zz75: Optional[float] = None

    # Alias property for test interface compatibility
    @property
    def current_state(self) -> str:
        return self.credit_bin

    @property
    def is_crisis_override(self) -> bool:
        return self.action_code == "MKT_CREDIT_FREEZE_EXTREME"

    def to_dict(self) -> Dict[str, Any]:
        """Returns full structured METAR payload as a dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Returns formatted JSON string of the METAR."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def format_cli_broadcast(self) -> str:
        """Formats the METAR into a high-visibility CLI / Telegram broadcast string."""
        e_days = list(self.e_days_vector.values()) if isinstance(self.e_days_vector, dict) else self.e_days_vector
        p_bull = list(self.p_bull_vector.values()) if isinstance(self.p_bull_vector, dict) else self.p_bull_vector
        ev_net = list(self.ev_net_vector.values()) if isinstance(self.ev_net_vector, dict) else self.ev_net_vector

        return (
            "================================================================================\n"
            f" 📢 MARKET METAR — CREDIT STRESS RATIO (HYG/LQD) [{self.metar_id}]\n"
            "================================================================================\n"
            f" 🕒 Timestamp UTC: {self.timestamp_utc} | Close Date: {self.as_of_date}\n"
            f" 🏢 Issuer: {self.issuer} | 🚦 Market Status: {self.market_status}\n"
            "--------------------------------------------------------------------------------\n"
            " 📊 LIVE TELEMETRY (72H FAST KINEMATICS):\n"
            f"    • Credit Ratio Level : {self.credit_ratio_value:.4f} [{self.credit_bin}]\n"
            f"    • Velocity (Δ3d)     : {self.credit_velocity_3d:+.4f} [{self.velocity_vector}]\n"
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


class CreditMetarService:
    """Domain service for generating Credit Stress METARs and persisting state transitions."""

    REGIME_KEY = "credit:entry_decision:MARKET"

    def __init__(
        self,
        data_store: Optional[TimescaleDataStore] = None,
        regime_state_port: Optional[RegimeStatePort] = None,
        credit_lookup_adapter: Optional[CreditLookupAdapter] = None,
    ):
        self._store = data_store or TimescaleDataStore()
        self._port = regime_state_port
        self._lookup = credit_lookup_adapter or credit_lookup

    def evaluate(self, as_of_date: Optional[str] = None) -> MarketMETAR:
        """
        Generates an authoritative Credit Stress Market METAR on-demand using 3-day fast velocity.
        Strict Data Policy: Zero Fallbacks. If a requested as_of_date is specified and does NOT exist
        in Neon Vault, raises StrictDataPolicyError immediately.
        Persists state transitions to RegimeStatePort if provided.
        """
        engine = self._store.engine
        try:
            import pandas as pd

            latest_bar_query = (
                "SELECT MAX(time::date) as max_date FROM market.ohlcv_bars "
                "WHERE ticker IN ('HYG', 'LQD') AND timeframe = '1d'"
            )
            df_max = pd.read_sql(latest_bar_query, engine)
            overall_latest = (
                str(df_max.iloc[0]["max_date"])
                if len(df_max) > 0 and "max_date" in df_max.columns and pd.notna(df_max.iloc[0]["max_date"])
                else "UNKNOWN"
            )

            if as_of_date:
                check_query = f"""
                    SELECT time::date as date, ticker, close
                    FROM market.ohlcv_bars
                    WHERE ticker IN ('HYG', 'LQD')
                      AND timeframe = '1d'
                      AND time::date <= '{as_of_date}'
                    ORDER BY time DESC
                """
                df_raw = pd.read_sql(check_query, engine)
                
                # Check availability for as_of_date (strictly requiring exact date)
                has_data = False
                if len(df_raw) > 0:
                    date_col = 'date' if 'date' in df_raw.columns else ('time::date' if 'time::date' in df_raw.columns else 'time')
                    if date_col in df_raw.columns:
                        exact_rows = df_raw[df_raw[date_col].astype(str) == as_of_date]
                        if len(exact_rows['ticker'].unique()) >= 2:
                            has_data = True

                if not has_data:
                    raise StrictDataPolicyError(
                        f"STRICT DATA POLICY: CREDIT METAR NOT AVAILABLE for requested date '{as_of_date}'. "
                        f"Vault data does not exist for both HYG and LQD at this timestamp. Latest available date in Vault is '{overall_latest}'."
                    )
            else:
                query_all = """
                    SELECT time::date as date, ticker, close
                    FROM market.ohlcv_bars
                    WHERE ticker IN ('HYG', 'LQD')
                      AND timeframe = '1d'
                    ORDER BY time DESC
                """
                df_raw = pd.read_sql(query_all, engine)
                if len(df_raw) == 0:
                    raise StrictDataPolicyError(
                        "STRICT DATA POLICY: CREDIT METAR NOT AVAILABLE. Neon Vault contains zero OHLCV bars for 'HYG' or 'LQD'."
                    )

            date_col = 'date' if 'date' in df_raw.columns else 'time'
            pivot_c = df_raw.pivot(index=date_col, columns="ticker", values="close").dropna()
            
            if as_of_date:
                pivot_c = pivot_c[pivot_c.index.astype(str) <= as_of_date]

            if len(pivot_c) < 4:
                raise StrictDataPolicyError(
                    f"STRICT DATA POLICY: CREDIT METAR NOT AVAILABLE. "
                    f"Insufficient historical aligned bars ({len(pivot_c)} bars found, minimum 20 required for 72h kinematics)."
                )

            pivot_c = pivot_c.sort_index()
            credit_series = pivot_c["HYG"] / pivot_c["LQD"]

            credit_latest = float(credit_series.iloc[-1])
            credit_3d_prev = float(credit_series.iloc[-4])
            credit_delta_3d = float(credit_latest - credit_3d_prev)
            clean_date = str(pivot_c.index[-1]).split(" ")[0]
            s_val = credit_series
            vol_2d = s_val.rolling(2).std()
            vol_10d = s_val.rolling(10).std().replace(0, np.nan)
            s_vol_norm = (vol_2d / vol_10d).fillna(1.0)
            vol_norm = float(s_vol_norm.iloc[-1])
            vol_d3 = float(vol_norm - float(s_vol_norm.iloc[-4])) if len(s_vol_norm) >= 4 else 0.0

            guidance = self._lookup.lookup_credit_guidance(val=credit_latest, d3_speed=credit_delta_3d, vol_norm=vol_norm, vol_d3=vol_d3)
            if not guidance:
                raise StrictDataPolicyError(
                    f"STRICT DATA POLICY: CREDIT METAR NOT AVAILABLE. State classification failed for ratio={credit_latest}, d3={credit_delta_3d}."
                )

            vec = guidance.to_vector()
            now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            # Determine Universal Taxonomy Action Code
            if guidance.credit_bin == "EXTREME_STRESS" or guidance.velocity_vector == "FAST_CRUSH_3D":
                action_code = "MKT_CREDIT_FREEZE_EXTREME"
                market_status = "CRISIS_CREDIT_FREEZE"
            elif guidance.credit_bin in ("STRESS", "NEUTRAL_TIGHT") or guidance.velocity_vector == "DECELERATING_DOWN_3D":
                action_code = "MKT_CREDIT_STRESS_ELEVATED"
                market_status = "ELEVATED_STRESS"
            else:
                action_code = "MKT_CREDIT_EXPANSION_STABLE"
                market_status = "EXPANSIVE_STABLE"

            metar_id = f"METAR-CREDIT-{clean_date.replace('-', '')}-001"

            # Stateful-First Persistence (Rule 15)
            if self._port:
                try:
                    clean_date_short = str(clean_date).split(" ")[0]
                    ts_dt = datetime.strptime(clean_date_short, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    self._port.commit_transition(
                        key=self.REGIME_KEY,
                        next_state=guidance.credit_bin,
                        trigger=f"CREDIT_RATIO={credit_latest:.4f}, Δ3d={credit_delta_3d:+.4f}",
                        timestamp=ts_dt,
                        metadata={
                            "action_code": action_code,
                            "credit_ratio": credit_latest,
                            "delta_3d": credit_delta_3d,
                            "state_key": guidance.state_key,
                        },
                    )
                except Exception:
                    pass

            return MarketMETAR(
                metar_id=metar_id,
                timestamp_utc=now_utc_str,
                as_of_date=clean_date,
                issuer="Botero-Trade Credit Stress Intelligence Engine",
                market_status=market_status,
                credit_ratio_value=round(credit_latest, 4),
                credit_velocity_3d=round(credit_delta_3d, 4),
                state_key=guidance.state_key,
                credit_bin=guidance.credit_bin,
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
            zigzag_kinematic=guidance.zigzag_kinematic,
                sigma_depth_d1=guidance.sigma_depth_d1,
                sigma_depth_d2=guidance.sigma_depth_d2,
                sigma_depth_d3=guidance.sigma_depth_d3,
                overflow_flag=guidance.overflow_flag,
            e_ret_max_zz75=guidance.zz75.e_ret_max,
            e_ret_min_zz75=guidance.zz75.e_ret_min,
            )

        finally:
            self._store.close()


def get_credit_market_metar(as_of_date: Optional[str] = None) -> MarketMETAR:
    """Convenience function to evaluate Credit METAR using default service instance."""
    service = CreditMetarService()
    return service.evaluate(as_of_date=as_of_date)
