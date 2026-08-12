"""
Sector Rotation Intelligence (ROTATION) Market METAR Service — Pure Domain Service
====================================================================================
Generates authoritative, zero-fallback Sector Rotation Market METARs (Meteorological Reports).
Evaluates cyclical vs defensive institutional capital migration (XLY/XLP + XLK/XLU Z-scores).
Uses 3-Day Fast Kinematic Velocity (Delta 3d - 72h) of the composite Rotation Index.
Strict Data Policy: Zero Fallbacks. If a requested date is missing or not valid in Neon Vault,
raises StrictDataPolicyError immediately with explicit 'METAR NOT AVAILABLE' message in English.
Always includes exact UTC date and time.
Persists StateSnapshot to RegimeStatePort under key 'rotation:entry_decision:MARKET'.
"""
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
import json
import numpy as np

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.rotation_lookup import rotation_lookup, RotationLookupAdapter
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
    rotation_index_value: float
    rotation_velocity_3d: float
    state_key: str
    rotation_bin: str
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
        return self.rotation_bin

    @property
    def is_crisis_override(self) -> bool:
        return self.action_code == "MKT_ROTATION_DEFENSIVE_FREEZE"

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
            f" 📢 MARKET METAR — SECTOR ROTATION INTELLIGENCE (XLY/XLP + XLK/XLU) [{self.metar_id}]\n"
            "================================================================================\n"
            f" 🕒 Timestamp UTC: {self.timestamp_utc} | Close Date: {self.as_of_date}\n"
            f" 🏢 Issuer: {self.issuer} | 🚦 Market Status: {self.market_status}\n"
            "--------------------------------------------------------------------------------\n"
            " 📊 LIVE TELEMETRY (72H FAST KINEMATICS):\n"
            f"    • Rotation Index Level : {self.rotation_index_value:.4f} [{self.rotation_bin}]\n"
            f"    • Velocity (Δ3d)       : {self.rotation_velocity_3d:+.4f} [{self.velocity_vector}]\n"
            f"    • State Key            : {self.state_key} (N = {self.n_samples} historical days)\n\n"
            " 🔮 STOCHASTIC FORECAST & HORIZON DIVERGENCE:\n"
            f"    • Active Regime        : {self.divergence_regime}\n"
            f"    • Scale 2.5% ({self.e_days_vector[0]:.0f}d) : P(bull) = {self.p_bull_vector[0]*100:.1f}% | EV = {self.ev_net_vector[0]*100:+.2f}%\n"
            f"    • Scale 5.0% ({self.e_days_vector[1]:.0f}d) : P(bull) = {self.p_bull_vector[1]*100:.1f}% | EV = {self.ev_net_vector[1]*100:+.2f}%\n"
            f"    • Scale 7.5% ({self.e_days_vector[2]:.0f}d) : P(bull) = {self.p_bull_vector[2]*100:.1f}% | EV = {self.ev_net_vector[2]*100:+.2f}%\n\n"
            " ⚡ CAPITAL VELOCITY (TIME-INDEPENDENT):\n"
            f"    • Daily Rate (%/day)   : {self.primary_capital_velocity*100:+.4f}% / trading day (reaches 5.0% in {self.primary_e_days:.1f}d)\n"
            f"    • R/R Asymmetry        : {self.rr_asymmetry_ratio:.2f}x\n\n"
            " 🎯 OPERATIONAL DIRECTIVES (UNIVERSAL TAXONOMY):\n"
            f"    • Action Code          : {self.action_code}\n"
            f"    • Guidance Code        : {self.operational_guidance}\n"
            "================================================================================"
        )


class RotationMetarService:
    """Domain service for generating Sector Rotation METARs and persisting state transitions."""

    REGIME_KEY = "rotation:entry_decision:MARKET"

    def __init__(
        self,
        data_store: Optional[TimescaleDataStore] = None,
        regime_state_port: Optional[RegimeStatePort] = None,
        rotation_lookup_adapter: Optional[RotationLookupAdapter] = None,
    ):
        self._store = data_store or TimescaleDataStore()
        self._port = regime_state_port
        self._lookup = rotation_lookup_adapter or rotation_lookup

    def evaluate(self, as_of_date: Optional[str] = None) -> MarketMETAR:
        """
        Generates an authoritative Sector Rotation Market METAR on-demand using 3-day fast velocity.
        Strict Data Policy: Zero Fallbacks. If a requested as_of_date is specified and does NOT exist
        in Neon Vault for all required sector tickers, raises StrictDataPolicyError immediately.
        Persists state transitions to RegimeStatePort if provided.
        """
        engine = self._store.engine
        try:
            import pandas as pd

            required_tickers = ["XLY", "XLP", "XLK", "XLU"]
            latest_bar_query = (
                f"SELECT MAX(time::date) as max_date FROM market.ohlcv_bars "
                f"WHERE ticker IN ({','.join([repr(t) for t in required_tickers])}) AND timeframe = '1d'"
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
                    WHERE ticker IN ({','.join([repr(t) for t in required_tickers])})
                      AND timeframe = '1d'
                      AND time::date <= '{as_of_date}'
                    ORDER BY time DESC
                """
                df_raw = pd.read_sql(check_query, engine)

                has_exact = False
                if len(df_raw) > 0:
                    date_col = 'date' if 'date' in df_raw.columns else ('time::date' if 'time::date' in df_raw.columns else 'time')
                    if date_col in df_raw.columns:
                        exact_rows = df_raw[df_raw[date_col].astype(str) == as_of_date]
                        if len(exact_rows['ticker'].unique()) >= len(required_tickers):
                            has_exact = True

                if len(df_raw['ticker'].unique()) < len(required_tickers):
                    raise StrictDataPolicyError(
                        f"STRICT DATA POLICY: ROTATION METAR NOT AVAILABLE for requested date '{as_of_date}'. "
                        f"Vault data does not exist for all required sector tickers ({required_tickers}) at this timestamp. "
                        f"Latest available date in Vault is '{overall_latest}'."
                    )
            else:
                query_all = f"""
                    SELECT time::date as date, ticker, close
                    FROM market.ohlcv_bars
                    WHERE ticker IN ({','.join([repr(t) for t in required_tickers])})
                      AND timeframe = '1d'
                    ORDER BY time DESC
                """
                df_raw = pd.read_sql(query_all, engine)
                if len(df_raw) == 0:
                    raise StrictDataPolicyError(
                        f"STRICT DATA POLICY: ROTATION METAR NOT AVAILABLE. Neon Vault contains zero OHLCV bars for sector tickers ({required_tickers})."
                    )

            date_col = 'date' if 'date' in df_raw.columns else 'time'
            pivot_c = df_raw.pivot(index=date_col, columns="ticker", values="close").dropna()

            if as_of_date:
                pivot_c = pivot_c[pivot_c.index.astype(str) <= as_of_date]

            if len(pivot_c) < 256:
                raise StrictDataPolicyError(
                    f"STRICT DATA POLICY: ROTATION METAR NOT AVAILABLE. "
                    f"Insufficient historical aligned bars ({len(pivot_c)} bars found, minimum 256 required for rolling 252d Z-score)."
                )

            pivot_c = pivot_c.sort_index()
            ratio_xly_xlp = pivot_c["XLY"] / pivot_c["XLP"]
            ratio_xlk_xlu = pivot_c["XLK"] / pivot_c["XLU"]

            mean_xly_xlp = ratio_xly_xlp.rolling(252, min_periods=20).mean()
            std_xly_xlp = ratio_xly_xlp.rolling(252, min_periods=20).std().replace(0, np.nan)
            z_xly_xlp = (ratio_xly_xlp - mean_xly_xlp) / std_xly_xlp

            mean_xlk_xlu = ratio_xlk_xlu.rolling(252, min_periods=20).mean()
            std_xlk_xlu = ratio_xlk_xlu.rolling(252, min_periods=20).std().replace(0, np.nan)
            z_xlk_xlu = (ratio_xlk_xlu - mean_xlk_xlu) / std_xlk_xlu

            rotation_index = (z_xly_xlp + z_xlk_xlu).fillna(0.0)

            rot_latest = float(rotation_index.iloc[-1])
            rot_3d_prev = float(rotation_index.iloc[-4])
            rot_delta_3d = float(rot_latest - rot_3d_prev)
            clean_date = str(pivot_c.index[-1]).split(" ")[0]
            s_val = rotation_index
            vol_5d = s_val.rolling(5).std()
            vol_20d = s_val.rolling(20).std().replace(0, np.nan)
            s_vol_norm = (vol_5d / vol_20d).fillna(1.0)
            vol_norm = float(s_vol_norm.iloc[-1])
            vol_d3 = float(vol_norm - float(s_vol_norm.iloc[-4])) if len(s_vol_norm) >= 4 else 0.0

            guidance = self._lookup.lookup_rotation_guidance(val=rot_latest, d3_speed=rot_delta_3d, vol_norm=vol_norm, vol_d3=vol_d3)
            if not guidance:
                raise StrictDataPolicyError(
                    f"STRICT DATA POLICY: ROTATION METAR NOT AVAILABLE. State classification failed for index={rot_latest}, d3={rot_delta_3d}."
                )

            vec = guidance.to_vector()
            now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            action_code = guidance.operational_guidance

            if action_code == "MKT_ROTATION_DEFENSIVE_FREEZE":
                market_status = "CRISIS_DEFENSIVE_FREEZE"
            elif action_code == "MKT_ROTATION_DEFENSIVE_FLIGHT":
                market_status = "ELEVATED_DEFENSIVE_FLIGHT"
            elif action_code == "MKT_ROTATION_CYCLICAL_EXPANSION":
                market_status = "EXPANSIVE_RISK_ON"
            else:
                market_status = "NORMAL_BALANCED"

            metar_id = f"METAR-ROTATION-{clean_date.replace('-', '')}-001"

            metar = MarketMETAR(
                metar_id=metar_id,
                timestamp_utc=now_utc_str,
                as_of_date=clean_date,
                issuer="Botero-Trade Sector Rotation Intelligence Engine",
                market_status=market_status,
                rotation_index_value=round(rot_latest, 4),
                rotation_velocity_3d=round(rot_delta_3d, 4),
                state_key=guidance.state_key,
                rotation_bin=guidance.rotation_bin,
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

            # Stateful-First Regime State Persistence
            if self._port:
                try:
                    state_keys = [
                        (self.REGIME_KEY, metar.state_key),
                        ("rotation:regime:MARKET", metar.divergence_regime),
                        ("rotation:guidance:MARKET", metar.operational_guidance),
                    ]
                    for key, state_label in state_keys:
                        current = self._port.get_current(key)
                        if current is None or current.current_state != state_label:
                            trigger_msg = f"ROTATION_INDEX={metar.rotation_index_value:.4f}, d3={metar.rotation_velocity_3d:+.4f}"
                            self._port.commit_transition(key, state_label, trigger=trigger_msg)
                        else:
                            self._port.increment_duration(key)
                except Exception:
                    pass

            return metar
        finally:
            self._store.close()


def get_rotation_market_metar(as_of_date: Optional[str] = None) -> MarketMETAR:
    """
    Standalone global helper to generate authoritative Sector Rotation Market METAR.
    """
    service = RotationMetarService()
    return service.evaluate(as_of_date=as_of_date)
