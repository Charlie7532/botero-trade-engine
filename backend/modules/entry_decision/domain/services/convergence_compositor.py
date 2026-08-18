"""
Multi-Station Convergence Compositor — Pure Domain Service
============================================================
Aggregates all 11 Market METAR stations (VIX, VVIX, PCR, FG, SV5_TURBULENCE, SKEW, CREDIT, YIELD_CURVE, ROTATION, BSI, DXY).

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
from backend.modules.entry_decision.domain.services.dxy_metar_service import get_dxy_market_metar, StrictDataPolicyError as DXYError
import json
from pathlib import Path
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

CALIBRATION_FILE = Path(__file__).parent.parent / "rules" / "cascade_calibration.json"

DEFAULT_CALIBRATION = {
    "d1_bear_5": {"mean": 0.490, "std": 0.327},
    "domino_zz25": {"mean": 0.053, "std": 0.035},
    "domino_zz50": {"mean": 0.082, "std": 0.056},
    "tercile_edges": [-0.34, 0.22],
}


def load_cascade_calibration() -> dict:
    """Load cascade calibration JSON from rules directory if available, else return real defaults."""
    if CALIBRATION_FILE.exists():
        try:
            with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_CALIBRATION


GRUPO_A_PREDICTORS = {"vix", "bsi", "fg", "credit", "rotation"}


# ── Station conviction weights (Signal Quality: IC × σ, Grinold & Kahn) ────
# Source: Spearman IC vs forward SPY returns × return volatility at each ZZ
#         horizon, corrected by dimensional redundancy (1/√peers).
# Method: IC at 15 horizons (1d-100d), anchored to ZZ P25/P50/P75 leg durations.
#         SQ = |IC| × σ_returns → captures both predictive power AND move size.
# Verification: Walk-forward AUC, p-values < 0.01 for all significant stations.
#
# Dimensions (each provides unique market info, peers share a discount):
#   volatility (VIX, VVIX), breadth (BSI), sentiment (FG),
#   options_flow (PCR, SKEW), credit_macro (Credit, Yield Curve),
#   microstructure (SV5T), currency (DXY), rotation (Rotation)
#
# Temporal personalities (IC curve shape, 1d-100d sweep):
#   BSI:   peak 24d, ⛰️ pico y decae → SWING indicator
#   VIX:   peak 57d, ⛰️ pico y decae → STRUCTURAL position
#   VVIX:  peak 57d, ⛰️ pico y decae → STRUCTURAL position
#   FG:    peak 80d, ⛰️ pico y decae → MACRO sentiment
#   PCR:   peak 24d, ⛰️ pico y decae → SWING hedging flow
#   Credit: 100d+, 📈 creciente → MACRO credit cycle
#   Yield:  100d+, 📈 creciente → MACRO monetary policy
#   DXY:    100d+, 📈 creciente → MACRO financial conditions
#   SV5T:   100d+, 📈 creciente → MACRO institutional vol
#   Rotation: 100d+, onset 40d → MACRO sector cycle
#   SKEW:   100d+, onset 57d → MACRO late tail risk
STATION_WEIGHTS = {
    "bsi": 1.50,             # SQ=0.367% — Breadth king, unique dimension, peak 24d
    "vix": 1.26,             # SQ=0.438% (×0.707) — Highest raw SQ, peak 57d
    "fg": 1.11,              # SQ=0.273% — Contrarian sentiment, unique dim, peak 80d
    "vvix": 1.05,            # SQ=0.367% (×0.707) — Vol-of-vol, peak 57d
    "yield_curve": 0.98,     # SQ=0.341% (×0.707) — Monetary cycle, still growing at 100d
    "credit": 0.83,          # SQ=0.290% (×0.707) — Credit stress, still growing at 100d
    "sv5_turbulence": 0.72,  # SQ=0.178% — Institutional microstructure, unique dim
    "dxy": 0.66,             # SQ=0.166% — Global fin conditions, unique dim, onset 15d
    "pcr": 0.58,             # SQ=0.207% (×0.707) — Options hedging flow, peak 24d
    "rotation": 0.24,        # SQ=0.064% — Sector rotation, IC not significant at p<0.01
    "skew": 0.15,            # SQ=0.059% (×0.707) — Tail protection, onset 57d
}

# ── Scale factors (IC ratio per ZZ horizon, anchored to leg duration P25/P50/P75) ──
# Method: For each station, compute avg|IC| at [P25, P50, P75] of each ZZ scale's
#         empirical leg duration distribution, then normalize per-station mean=1.0.
# ZZ durations: ZZ25=[1,4,8]d, ZZ50=[4,10,26]d, ZZ75=[8,24,57]d
#
# Universal pattern: ALL stations gain predictive power with horizon.
# SF_ZZ25 < 1.0 < SF_ZZ75 for every station. This contradicts the prior GBM
# which claimed VIX was "purely tactical" (sf_zz75=0.08). The IC says VIX
# is MORE predictive at 24d (IC=+0.113) than at 4d (IC=+0.069).
SCALE_FACTORS = {
    "bsi":            {"zz25": 0.84, "zz50": 1.12, "zz75": 1.03},
    "vix":            {"zz25": 0.73, "zz50": 1.05, "zz75": 1.22},
    "fg":             {"zz25": 0.72, "zz50": 1.06, "zz75": 1.22},
    "vvix":           {"zz25": 0.66, "zz50": 1.03, "zz75": 1.31},
    "yield_curve":    {"zz25": 0.65, "zz50": 1.00, "zz75": 1.35},
    "credit":         {"zz25": 0.63, "zz50": 1.00, "zz75": 1.37},
    "sv5_turbulence": {"zz25": 0.79, "zz50": 1.03, "zz75": 1.17},
    "dxy":            {"zz25": 0.61, "zz50": 0.90, "zz75": 1.49},
    "pcr":            {"zz25": 0.73, "zz50": 1.11, "zz75": 1.17},
    "rotation":       {"zz25": 0.33, "zz50": 0.91, "zz75": 1.76},
    "skew":           {"zz25": 0.27, "zz50": 0.77, "zz75": 1.96},
}

# ── D1 Bin → Directional Vote (for rare stations) ────────────────────────
# These bins carry directional meaning regardless of EV reliability.
# Bearish D1 bins: market stress / panic / crisis
D1_BEARISH_BINS = {
    "CRISIS_SPIKE", "ELEVATED_PANIC",                          # VIX
    "EXTREME_VVIX", "ELEVATED_VVIX",                           # VVIX
    "EXTREME_PUT_PANIC", "HIGH_PUT_PANIC",                     # PCR
    "EXTREME_FEAR", "FEAR",                                    # FG (FEAR synced from fact store)
    "CRISIS_TURBULENCE", "ELEVATED_TURBULENCE",                # SV5
    "BLACK_SWAN_PARANOIA", "TAIL_PARANOIA",                    # SKEW
    "CREDIT_CRISIS", "CREDIT_STRESS", "ELEVATED_CREDIT_STRESS", # Credit
    "DEEP_INVERSION", "MODERATE_INVERSION",                    # Yield Curve
    "DEFENSIVE_CAPITULATION", "DEFENSIVE",                     # Rotation
    "BREADTH_WASHED_OUT",                                    # BSI
    "DOLLAR_SPIKE_CRISIS", "ELEVATED_DOLLAR_STRESS",           # DXY
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
    "DEEP_DOLLAR_CRUSH", "WEAK_DOLLAR",                        # DXY
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

    # Cascade Conviction (Empirically Validated)
    cascade_conviction_50: float          # 0.66 × z(d1_bear_masked) + 0.34 × z(|prev_leg_return_zz25|)
    cascade_conviction_75: float          # 0.50 × z(d1_bear_masked) + 0.50 × z(|prev_leg_return_zz50|)
    cascade_conviction_50to75: float      # 0.15 × z(d1_bear_masked) + 0.85 × z(|prev_leg_return_zz50|)
    cascade_tercile: str                  # "t1_low" | "t2_medium" | "t3_high"
    domino_magnitude: float               # |prev_leg_return| raw
    pivot_type: str                       # "MIN" | "MAX"

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

    def compute(
        self,
        as_of_date: Optional[str] = None,
        prev_leg_return: Optional[float] = None,
        prev_leg_return_zz50: Optional[float] = None,
        pivot_type: Optional[str] = None,
    ) -> ConvergenceReport:
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
            ("dxy", get_dxy_market_metar),
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
        # Scale-differentiated: ev_1d uses zz25 weights, ev_5d uses zz75 weights
        ev1_list, ev5_list = [], []
        ev_weights_1d, ev_weights_5d = [], []
        n_bull_1d, n_bull_5d = 0, 0
        n_buy_dip = 0
        ev_contributing = 0

        # ── Channel 2: Rarity Score ──────────────────────────────────
        rarity_numerator = 0.0
        rarity_denominator = 0.0
        extreme_stations = []

        # ── Channel 3: D1 Directional Votes ──────────────────────────
        n_bullish_vote, n_bearish_vote, n_neutral_vote = 0, 0, 0
        grupo_a_predictors = {"vix", "bsi", "fg", "credit", "rotation"}
        n_grupo_a_bearish = 0
        n_grupo_a_active = 0

        station_summaries = {}
        for code, data in results.items():
            w = STATION_WEIGHTS.get(code, 1.0)
            sf = SCALE_FACTORS.get(code, {"zz25": 1.0, "zz50": 1.0, "zz75": 1.0})
            n = data.get("n_samples", 100) or 100
            state_key = data.get("state_key", "")
            guidance = data.get("operational_guidance", "STK_HOLD_STABLE")

            # Extract EV vectors
            ev_vec = data.get("ev_net_vector", {})
            p_vec = data.get("p_bull_vector", {})
            ev1 = ev_vec.get("zz25", 0.0) if isinstance(ev_vec, dict) else (ev_vec[0] if isinstance(ev_vec, list) and ev_vec else 0.0)
            ev5 = ev_vec.get("zz75", 0.0) if isinstance(ev_vec, dict) else (ev_vec[-1] if isinstance(ev_vec, list) and ev_vec else 0.0)
            p5 = p_vec.get("zz75", 0.5) if isinstance(p_vec, dict) else (p_vec[-1] if isinstance(p_vec, list) and p_vec else 0.5)

            # Channel 1: Scale-differentiated N-attenuated EV
            rf = reliability_factor(n)
            ew_1d = w * sf["zz25"] * rf
            ew_5d = w * sf["zz75"] * rf
            ev1_list.append(ev1)
            ev5_list.append(ev5)
            ev_weights_1d.append(ew_1d)
            ev_weights_5d.append(ew_5d)
            if rf > 0:
                ev_contributing += 1

            # Legacy convergence counters (unattenuated, for backward compat)
            if ev1 > 0: n_bull_1d += 1
            if ev5 > 0: n_bull_5d += 1
            if guidance == "STK_BUY_DIP_TACTICAL": n_buy_dip += 1

            # Channel 2: Rarity
            ra = rarity_amplifier(n)
            rarity_numerator += ra * w

        grupo_a_votes = {}

        for name, metar in results.items():
            st_key = metar.get("state_key", "")
            data = metar.get("data", {})

            # D1 vote
            vote = d1_directional_vote(st_key)
            if vote > 0:
                n_bullish_vote += 1
            elif vote < 0:
                n_bearish_vote += 1

            if name in GRUPO_A_PREDICTORS:
                n_grupo_a_active += 1
                grupo_a_votes[name] = vote
                if vote < 0:
                    n_grupo_a_bearish += 1

            # Rarity score component
            rf = metar.get("reliability_factor", 0.5)
            ra = metar.get("rarity_amplifier", 1.0)
            if ra > 1.0:
                extreme_stations.append(name)
                rarity_numerator += rf * (ra - 1.0)
            rarity_denominator += rf

            # EV weights
            n = data.get("n_raw", 0)
            ew_1d = float(data.get("ev_weight_1d", 0.0))
            ew_5d = float(data.get("ev_weight_5d", 0.0))

            ev_1d = float(data.get("ev_net_1d", 0.0))
            ev_5d = float(data.get("ev_net_5d", 0.0))

            if n >= 10:
                ev_contributing += 1
                ev1_list.append(ev_1d)
                ev5_list.append(ev_5d)
                ev_weights_1d.append(ew_1d)
                ev_weights_5d.append(ew_5d)

            # Legacy directional counters
            if ev_1d > 0: n_bull_1d += 1
            if ev_5d > 0: n_bull_5d += 1

            # Guidance flags
            guidance = metar.get("action_code", "")
            if guidance == "STK_BUY_DIP_TACTICAL":
                n_buy_dip += 1

            # Station summary for report
            sf = metar.get("scale_factors", {"zz25": 1.0, "zz75": 1.0})
            station_summaries[name] = {
                "state_key": st_key,
                "action_code": guidance,
                "n_samples": n,
                "reliability_factor": rf,
                "rarity_amplifier": ra,
                "ev_weight_1d": round(ew_1d, 3),
                "ev_weight_5d": round(ew_5d, 3),
                "scale_factor_zz25": sf.get("zz25", 1.0),
                "scale_factor_zz75": sf.get("zz75", 1.0),
                "divergence_regime": data.get("divergence_regime"),
            }

        # ── Compute composites ───────────────────────────────────────

        # Channel 1: Scale-differentiated N-attenuated EV composite
        comp_ev1 = float(np.average(ev1_list, weights=ev_weights_1d)) if ev_weights_1d else 0.0
        comp_ev5 = float(np.average(ev5_list, weights=ev_weights_5d)) if ev_weights_5d else 0.0

        # Channel 2: Rarity Score
        rarity_score = float(rarity_numerator / rarity_denominator) if rarity_denominator > 0 else 0.0

        # Channel 3: D1 Vote ratios
        bull_vote_ratio = float(n_bullish_vote / active_count)
        bear_vote_ratio = float(n_bearish_vote / active_count)
        d1_bear_5 = float(n_grupo_a_bearish / n_grupo_a_active) if n_grupo_a_active > 0 else 0.0

        # Legacy convergence
        bull_ratio_1d = float(n_bull_1d / active_count)
        bull_ratio_5d = float(n_bull_5d / active_count)

        # ── Channel 4: Cascade Conviction (Empirically Validated & Type-Masked) ─────
        if pivot_type is None or prev_leg_return is None or prev_leg_return_zz50 is None:
            try:
                from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
                store = TimescaleDataStore()
                repo = ZigzagLegRepository(store)
                legs25 = repo.get_confirmed_legs("SPY", "zz25")
                if legs25:
                    if prev_leg_return is None:
                        prev_leg_return = legs25[-1].prev_leg_return
                    if pivot_type is None:
                        pivot_type = legs25[-1].start_type
                legs50 = repo.get_confirmed_legs("SPY", "zz50")
                if prev_leg_return_zz50 is None and legs50:
                    prev_leg_return_zz50 = legs50[-1].prev_leg_return
            except Exception:
                pass

        if pivot_type is None or pivot_type not in ("MIN", "MAX"):
            pivot_type = "MIN"

        calib = load_cascade_calibration()
        type_mask_cfg = calib.get("type_mask", {}).get(pivot_type, {
            "w_bear": 0.66,
            "w_dom": 0.34,
            "w_bear_c75": 0.50,
            "w_dom_c75": 0.50,
            "stations": ["vix", "bsi", "fg", "credit", "rotation"] if pivot_type == "MIN" else ["vix", "bsi", "credit", "rotation"]
        })
        allowed_stations = set(type_mask_cfg.get("stations", ["vix", "bsi", "fg", "credit", "rotation"] if pivot_type == "MIN" else ["vix", "bsi", "credit", "rotation"]))
        w_bear = float(type_mask_cfg.get("w_bear", 0.66))
        w_dom = float(type_mask_cfg.get("w_dom", 0.34))
        w_bear_c75 = float(type_mask_cfg.get("w_bear_c75", 0.50))
        w_dom_c75 = float(type_mask_cfg.get("w_dom_c75", 0.50))

        # Filter station votes for allowed stations according to pivot type
        masked_votes = [vote for code, vote in grupo_a_votes.items() if code in allowed_stations and vote is not None]
        if masked_votes:
            n_masked_bearish = sum(1 for v in masked_votes if v < 0)
            d1_bear_masked = float(n_masked_bearish / len(masked_votes))
        else:
            d1_bear_masked = d1_bear_5

        d1_mean = calib.get("d1_bear_5", {}).get("mean", 0.3299)
        d1_std = calib.get("d1_bear_5", {}).get("std", 0.2856)
        dom25_mean = calib.get("domino_zz25", {}).get("mean", 0.0532)
        dom25_std = calib.get("domino_zz25", {}).get("std", 0.0350)
        dom50_mean = calib.get("domino_zz50", {}).get("mean", 0.1003)
        dom50_std = calib.get("domino_zz50", {}).get("std", 0.0643)
        terc_edges = calib.get("tercile_edges", [-0.356, 0.175])

        val_dom25 = abs(prev_leg_return) if prev_leg_return is not None else dom25_mean
        val_dom50 = abs(prev_leg_return_zz50) if prev_leg_return_zz50 is not None else dom50_mean

        z_bear = (d1_bear_masked - d1_mean) / d1_std if d1_std > 0 else 0.0
        z_dom25 = (val_dom25 - dom25_mean) / dom25_std if dom25_std > 0 else 0.0
        z_dom50 = (val_dom50 - dom50_mean) / dom50_std if dom50_std > 0 else 0.0

        c50 = w_bear * z_bear + w_dom * z_dom25
        c75 = w_bear_c75 * z_bear + w_dom_c75 * z_dom50
        c50to75 = 0.15 * z_bear + 0.85 * z_dom50

        if c50 < terc_edges[0]:
            cascade_tercile = "t1_low"
        elif c50 > terc_edges[1]:
            cascade_tercile = "t3_high"
        else:
            cascade_tercile = "t2_medium"

        # ── Cross-Station Signal Detection ───────────────────────────
        cross_signals = []

        # Signal: Extreme Territory Alert
        if rarity_score >= 0.6:
            cross_signals.append("EXTREME_TERRITORY_ALERT")

        if cascade_tercile == "t3_high":
            cross_signals.append("CASCADE_HIGH_CONVICTION")

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
            cascade_conviction_50=round(c50, 4),
            cascade_conviction_75=round(c75, 4),
            cascade_conviction_50to75=round(c50to75, 4),
            cascade_tercile=cascade_tercile,
            domino_magnitude=round(val_dom25, 6),
            pivot_type=pivot_type,
            unified_guidance=unified_guidance,
            guidance_horizon=guidance_horizon,
            confidence_level=confidence,
            station_summaries=station_summaries,
        )
