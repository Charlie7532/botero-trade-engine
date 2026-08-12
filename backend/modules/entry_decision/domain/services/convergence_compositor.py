"""
Multi-Station Convergence Compositor — Pure Domain Service
============================================================
Aggregates all 9 Market METAR stations (VIX, VVIX, PCR, FG, SV5_TURBULENCE, SKEW, CREDIT, YIELD_CURVE, ROTATION).

Dual-Channel Architecture:
  Channel 1 (Statistic): EV composite weighted by reliability_factor(N).
      N >= 30 → weight 1.0 (robust), 10 <= N < 30 → 0.5 (marginal), N < 10 → 0.0 (anecdote)
  Channel 2 (Signal): Rarity Score amplified by rarity_amplifier(N).
      N >= 30 → 0.0 (normal), 10 <= N < 30 → 0.5, N < 10 → 1.0, N < 3 → 1.5
  Channel 3 (D1 Vote): Rare stations contribute directional vote via D1 bin classification,
      not via unreliable EV numbers.

Clean Architecture: Pure Domain Service reading exclusively from Neon Vault via METAR services.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, List, Optional
import numpy as np

from backend.modules.entry_decision.domain.services.vix_metar_service import get_vix_market_metar, StrictDataPolicyError as VIXError
from backend.modules.entry_decision.domain.services.vvix_metar_service import get_vvix_market_metar, StrictDataPolicyError as VVIXError
from backend.modules.entry_decision.domain.services.pcr_metar_service import get_pcr_market_metar, StrictDataPolicyError as PCRError
from backend.modules.entry_decision.domain.services.fg_metar_service import get_fg_market_metar, StrictDataPolicyError as FGError
from backend.modules.entry_decision.domain.services.sv5_turbulence_metar_service import get_sv5_turbulence_market_metar, StrictDataPolicyError as TurbError
from backend.modules.entry_decision.domain.services.skew_metar_service import get_skew_market_metar, StrictDataPolicyError as SKEWError
from backend.modules.entry_decision.domain.services.credit_metar_service import get_credit_market_metar, StrictDataPolicyError as CreditError
from backend.modules.entry_decision.domain.services.yield_curve_metar_service import get_yield_curve_market_metar, StrictDataPolicyError as YieldCurveError
from backend.modules.entry_decision.domain.services.rotation_metar_service import get_rotation_market_metar, StrictDataPolicyError as RotationError
from backend.modules.entry_decision.domain.services.bsi_metar_service import get_bsi_market_metar, StrictDataPolicyError as BSIError
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore


# ── Station conviction weights (forensic-derived) ────────────────────────
STATION_WEIGHTS = {
    "vix": 1.5,
    "sv5_turbulence": 1.5,
    "skew": 1.2,
    "bsi": 1.2,
    "yield_curve": 1.0,
    "credit": 1.0,
    "pcr": 1.0,
    "vvix": 0.8,
    "fg": 0.8,
    "rotation": 0.8,
}

# ── D1 Bin → Directional Vote (for rare stations) ────────────────────────
# These bins carry directional meaning regardless of EV reliability.
# Bearish D1 bins: market stress / panic / crisis
D1_BEARISH_BINS = {
    "CRISIS_SPIKE", "ELEVATED_PANIC",                          # VIX
    "EXTREME_VVIX",                                            # VVIX
    "EXTREME_PUT_PANIC", "HIGH_PUT_PANIC",                     # PCR
    "EXTREME_FEAR",                                            # FG
    "CRISIS_TURBULENCE", "ELEVATED_TURBULENCE",                # SV5
    "BLACK_SWAN_PARANOIA", "TAIL_PARANOIA",                    # SKEW
    "CREDIT_CRISIS", "ELEVATED_CREDIT_STRESS",                 # Credit
    "DEEP_INVERSION",                                          # Yield Curve
    "DEFENSIVE_CAPITULATION", "DEFENSIVE",                     # Rotation
    "BREADTH_WASHED_OUT",                                      # BSI
}

# Bullish D1 bins: complacency / ease / euphoria
D1_BULLISH_BINS = {
    "DEEP_COMPLACENCY", "LOW_VOL",                             # VIX
    "EXTREME_COMPLACENCY", "LOW_VVIX",                         # VVIX
    "EXTREME_CALL_HEAVY", "BULLISH_PCR",                       # PCR
    "EXTREME_GREED", "EUPHORIA",                               # FG
    "QUIET_FLOW", "LOW_TURBULENCE",                            # SV5
    "LOW_TAIL_RISK",                                           # SKEW
    "DEEP_CREDIT_EASE", "CREDIT_EASE",                         # Credit
    "EXTREME_STEEPNING", "STEEPNING_CURVE",                    # Yield Curve
    "AGGRESSIVE_ROTATION", "CYCLICAL_LEADERSHIP",              # Rotation
    "HYPER_EXPANSIVE_BREADTH", "EXPANSIVE_BREADTH",            # BSI
}


# ── Reliability & Rarity Functions ────────────────────────────────────────

def reliability_factor(n: int) -> float:
    """How much to trust the EV statistic based on sample size.
    N >= 30: full trust (1.0). N 10-29: partial (0.5). N < 10: zero (anecdote)."""
    if n >= 30:
        return 1.0
    elif n >= 10:
        return 0.5
    else:
        return 0.0


def rarity_amplifier(n: int) -> float:
    """How loud the ALARM signal should be based on sample rarity.
    N >= 30: no alarm (0.0). N 10-29: moderate (0.5). N < 10: loud (1.0). N < 3: max (1.5)."""
    if n >= 30:
        return 0.0
    elif n >= 10:
        return 0.5
    elif n >= 3:
        return 1.0
    else:
        return 1.5


def d1_directional_vote(state_key: str) -> int:
    """Extract D1 bin from state key and return directional vote.
    Returns +1 (bullish), -1 (bearish), or 0 (neutral)."""
    if not state_key:
        return 0
    d1_bin = state_key.split("__")[0]
    if d1_bin in D1_BEARISH_BINS:
        return -1
    elif d1_bin in D1_BULLISH_BINS:
        return +1
    return 0


# ── Report Dataclass ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class ConvergenceReport:
    timestamp_utc: str
    as_of_date: str
    execution_time_ms: float

    # Station Quorum
    total_stations: int
    active_stations: int
    blind_stations: List[str]

    # Rarity Channel
    extreme_territory_count: int
    extreme_territory_stations: List[str]
    rarity_score: float                    # 0.0 (all normal) to 1.0+ (extreme territory)

    # Directional Convergence (D1 vote-based, includes rare stations)
    bullish_vote_ratio: float              # % stations voting bullish via D1 bin
    bearish_vote_ratio: float              # % stations voting bearish via D1 bin

    # Statistic Channel — EV composite (N-attenuated)
    composite_ev_1d: float                 # Weighted EV from reliable stations only
    composite_ev_5d: float
    ev_contributing_stations: int          # How many stations have N >= 10

    # Legacy convergence (for backward compatibility)
    bullish_convergence_1d: float
    bullish_convergence_5d: float
    composite_p_bull_5d: float

    # Cross-Station Signals
    cross_signals: List[str]

    # Unified Operational Guidance
    unified_guidance: str
    guidance_horizon: str                  # 1D | 3D | 5D | WAIT
    confidence_level: str                  # HIGH | MODERATE | LOW | SPECULATIVE

    # Station Details
    station_summaries: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Compositor ────────────────────────────────────────────────────────────

class ConvergenceCompositor:
    """Pure domain service for multi-station METAR convergence analysis.
    Implements dual-channel architecture: Signal (rarity) vs. Statistic (EV)."""

    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers

    def _fetch_station(self, code: str, fn: Any, as_of_date: Optional[str]) -> tuple:
        try:
            m = fn(as_of_date=as_of_date)
            return (code, m.to_dict(), None)
        except Exception as e:
            return (code, None, str(e))

    def compute(self, as_of_date: Optional[str] = None) -> ConvergenceReport:
        t0 = time.time()

        stations = [
            ("vix", get_vix_market_metar),
            ("vvix", get_vvix_market_metar),
            ("pcr", get_pcr_market_metar),
            ("fg", get_fg_market_metar),
            ("sv5_turbulence", get_sv5_turbulence_market_metar),
            ("skew", get_skew_market_metar),
            ("credit", get_credit_market_metar),
            ("yield_curve", get_yield_curve_market_metar),
            ("rotation", get_rotation_market_metar),
            ("bsi", get_bsi_market_metar),
        ]

        # ── Parallel fetching ────────────────────────────────────────
        results = {}
        blind = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(self._fetch_station, code, fn, as_of_date)
                for code, fn in stations
            ]
            for f in futures:
                code, res, err = f.result()
                if res:
                    results[code] = res
                else:
                    blind.append(f"{code}: {err[:60]}")

        active_count = len(results)
        if active_count == 0:
            raise RuntimeError("No METAR stations were available for convergence calculation.")

        # ── Channel 1: Statistic (N-attenuated EV composite) ─────────
        ev1_list, ev5_list, ev_weights = [], [], []
        n_bull_1d, n_bull_5d = 0, 0
        n_buy_dip = 0
        ev_contributing = 0

        # ── Channel 2: Rarity Score ──────────────────────────────────
        rarity_numerator = 0.0
        rarity_denominator = 0.0
        extreme_stations = []

        # ── Channel 3: D1 Directional Votes ──────────────────────────
        n_bullish_vote, n_bearish_vote, n_neutral_vote = 0, 0, 0

        station_summaries = {}
        for code, data in results.items():
            w = STATION_WEIGHTS.get(code, 1.0)
            n = data.get("n_samples", 100) or 100
            state_key = data.get("state_key", "")
            guidance = data.get("operational_guidance", "STK_HOLD_STABLE")

            # Extract EV vectors
            ev_vec = data.get("ev_net_vector", {})
            p_vec = data.get("p_bull_vector", {})
            ev1 = ev_vec.get("zz25", 0.0) if isinstance(ev_vec, dict) else (ev_vec[0] if isinstance(ev_vec, list) and ev_vec else 0.0)
            ev5 = ev_vec.get("zz75", 0.0) if isinstance(ev_vec, dict) else (ev_vec[-1] if isinstance(ev_vec, list) and ev_vec else 0.0)
            p5 = p_vec.get("zz75", 0.5) if isinstance(p_vec, dict) else (p_vec[-1] if isinstance(p_vec, list) and p_vec else 0.5)

            # Channel 1: N-attenuated EV
            rf = reliability_factor(n)
            effective_ev_weight = w * rf
            ev1_list.append(ev1)
            ev5_list.append(ev5)
            ev_weights.append(effective_ev_weight)
            if rf > 0:
                ev_contributing += 1

            # Legacy convergence counters (unattenuated, for backward compat)
            if ev1 > 0: n_bull_1d += 1
            if ev5 > 0: n_bull_5d += 1
            if guidance == "STK_BUY_DIP_TACTICAL": n_buy_dip += 1

            # Channel 2: Rarity
            ra = rarity_amplifier(n)
            rarity_numerator += ra * w
            rarity_denominator += w
            if n < 10:
                extreme_stations.append(f"{code} (N={n}, key={state_key[:60]})")

            # Channel 3: D1 Vote
            vote = d1_directional_vote(state_key)
            if vote > 0:
                n_bullish_vote += 1
            elif vote < 0:
                n_bearish_vote += 1
            else:
                n_neutral_vote += 1

            station_summaries[code] = {
                "state_key": state_key,
                "d1_bin": state_key.split("__")[0] if state_key else "UNKNOWN",
                "d1_vote": "BULL" if vote > 0 else ("BEAR" if vote < 0 else "NEUTRAL"),
                "guidance": guidance,
                "ev_1d": round(ev1, 5),
                "ev_5d": round(ev5, 5),
                "n_samples": n,
                "reliability_factor": rf,
                "rarity_amplifier": ra,
                "ev_effective_weight": round(effective_ev_weight, 3),
                "divergence_regime": data.get("divergence_regime"),
            }

        # ── Compute composites ───────────────────────────────────────

        # Channel 1: N-attenuated EV composite
        w_sum = sum(ev_weights)
        if w_sum > 0:
            comp_ev1 = float(np.average(ev1_list, weights=ev_weights))
            comp_ev5 = float(np.average(ev5_list, weights=ev_weights))
        else:
            # All stations are rare — EV composite is meaningless
            comp_ev1 = 0.0
            comp_ev5 = 0.0

        # Channel 2: Rarity Score
        rarity_score = float(rarity_numerator / rarity_denominator) if rarity_denominator > 0 else 0.0

        # Channel 3: D1 Vote ratios
        bull_vote_ratio = float(n_bullish_vote / active_count)
        bear_vote_ratio = float(n_bearish_vote / active_count)

        # Legacy convergence
        bull_ratio_1d = float(n_bull_1d / active_count)
        bull_ratio_5d = float(n_bull_5d / active_count)

        # ── Cross-Station Signal Detection ───────────────────────────
        cross_signals = []

        # Signal: Extreme Territory Alert
        if rarity_score >= 0.6:
            cross_signals.append("EXTREME_TERRITORY_ALERT")

        # SPY effort/result check
        try:
            store = TimescaleDataStore()
            df_spy = store.load_bars("SPY", "1d")
            if not df_spy.empty and len(df_spy) >= 4:
                spy_ret_3d = float(df_spy.iloc[-1]['close'] / df_spy.iloc[-4]['close'] - 1.0)
            else:
                spy_ret_3d = 0.0
        except Exception:
            spy_ret_3d = 0.0

        sv5_data = results.get("sv5_turbulence", {})
        sv5_val = sv5_data.get("turbulence_index_value", 0.0)
        sv5_ev_vec = sv5_data.get("ev_net_vector", {})
        sv5_ev5 = sv5_ev_vec.get("zz75", 0.0) if isinstance(sv5_ev_vec, dict) else (sv5_ev_vec[-1] if isinstance(sv5_ev_vec, list) and sv5_ev_vec else 0.0)

        # Signal: Institutional Distribution Battle
        if sv5_val > 12.0 and abs(spy_ret_3d) < 0.005:
            cross_signals.append("INSTITUTIONAL_DISTRIBUTION_BATTLE")

        # Signal: SV5 Floor Veto
        if sv5_ev5 < 0 and n_bull_5d >= 3:
            cross_signals.append("FLOOR_NOT_CONFIRMED__SV5_VETO")

        # Signal: Confirmed Buyable Dip
        if n_buy_dip >= 3 and sv5_ev5 >= 0:
            cross_signals.append("CONFIRMED_BUYABLE_DIP")

        # Signal: D1 Bearish Convergence (majority of D1 bins are bearish)
        if bear_vote_ratio >= 0.50 and active_count >= 4:
            cross_signals.append("D1_BEARISH_CONVERGENCE")

        # ── Unified Guidance (rarity-aware) ──────────────────────────

        # Rarity override: if rarity is extreme, force WAIT
        if rarity_score >= 0.8:
            unified_guidance = "STK_HOLD_STABLE"
            guidance_horizon = "WAIT"
        elif "FLOOR_NOT_CONFIRMED__SV5_VETO" in cross_signals:
            unified_guidance = "STK_HOLD_STABLE"
            guidance_horizon = "WAIT"
        elif "D1_BEARISH_CONVERGENCE" in cross_signals:
            unified_guidance = "STK_HOLD_STABLE"
            guidance_horizon = "WAIT"
        elif "INSTITUTIONAL_DISTRIBUTION_BATTLE" in cross_signals:
            unified_guidance = "STK_TRIM_TACTICAL"
            guidance_horizon = "1D"
        elif "CONFIRMED_BUYABLE_DIP" in cross_signals:
            unified_guidance = "STK_BUY_DIP_TACTICAL"
            guidance_horizon = "5D"
        elif bull_ratio_5d >= 0.70 and ev_contributing >= 3:
            unified_guidance = "STK_ACCUMULATE_STRUCTURAL"
            guidance_horizon = "5D"
        elif bull_ratio_1d >= 0.70 and ev_contributing >= 3:
            unified_guidance = "STK_BUY_DIP_TACTICAL"
            guidance_horizon = "1D"
        else:
            unified_guidance = "STK_HOLD_STABLE"
            guidance_horizon = "3D"

        # ── Confidence (rarity-degraded) ─────────────────────────────
        if rarity_score >= 0.6:
            confidence = "SPECULATIVE"
        elif rarity_score >= 0.4:
            confidence = "LOW"
        elif active_count >= 7 and (bull_ratio_5d >= 0.75 or bull_ratio_5d <= 0.25):
            confidence = "HIGH"
        elif active_count >= 5:
            confidence = "MODERATE"
        else:
            confidence = "LOW"

        # ── Assemble Report ──────────────────────────────────────────
        sample_res = list(results.values())[0]
        as_of = sample_res.get("as_of_date", "UNKNOWN")
        ts_utc = sample_res.get("timestamp_utc", "")

        t1 = time.time()
        exec_ms = round((t1 - t0) * 1000, 2)

        return ConvergenceReport(
            timestamp_utc=ts_utc,
            as_of_date=as_of,
            execution_time_ms=exec_ms,
            total_stations=len(stations),
            active_stations=active_count,
            blind_stations=blind,
            extreme_territory_count=len(extreme_stations),
            extreme_territory_stations=extreme_stations,
            rarity_score=round(rarity_score, 4),
            bullish_vote_ratio=round(bull_vote_ratio, 4),
            bearish_vote_ratio=round(bear_vote_ratio, 4),
            composite_ev_1d=round(comp_ev1, 5),
            composite_ev_5d=round(comp_ev5, 5),
            ev_contributing_stations=ev_contributing,
            bullish_convergence_1d=round(bull_ratio_1d, 4),
            bullish_convergence_5d=round(bull_ratio_5d, 4),
            composite_p_bull_5d=round(0.5 + comp_ev5 * 2.0, 4),
            cross_signals=cross_signals,
            unified_guidance=unified_guidance,
            guidance_horizon=guidance_horizon,
            confidence_level=confidence,
            station_summaries=station_summaries,
        )
