#!/usr/bin/env python3
"""
Generate DXY Harmonized V3 Fact Store — 11th METAR Station
==========================================================
Homologated with generate_all_150_state_fact_stores.py so ALL 11 stations
share the same mathematical framework:

  Standard Layer (Compatible with Compositor):
    - fwd_1d / fwd_3d / fwd_5d continuous bar returns → zz25 / zz50 / zz75
    - Bayesian Laplace Shrinkage m=10 against global SPY priors
    - Schema: n_raw, p_bull, p_bear, e_ret_max, e_ret_min, ev_net, e_days, ev_per_day, rr_asymmetry
    - D1: Expanding Window Rank (zero look-ahead bias)

  Kinematic Layer (GAINED in V2, preserved):
    - Physical confirmed ZigZag legs from market.zigzag_legs (SPY)
    - structural_momentum: MIN→MIN / MAX→MAX accumulated returns with full statistical kit
    - prev_leg_domino: Domino effect stats from previous leg returns
    - Bayesian Laplace Shrinkage m=10 applied to p_bull/ev_net in zigzag and momentum
    - confidence_tier per scale and per momentum tercile

Intermarket Mechanics:
  DXY↑ → Commodities↓ → EM Carry Trade Stress → Global Liquidity Squeeze
  DXY↓ → Commodities↑ → Import Inflation → Reflation / EM Capital Surge

Usage:
    python -m backend.scripts.generate_dxy_fact_table
"""
import os
import sys
import json
import logging
from pathlib import Path
import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GenerateDXYFactTable")

OUTPUT_PATH = root_dir / "backend/modules/entry_decision/domain/rules/dxy_fact_store.json"

# ── Gaussian Calibration ──────────────────────────────────────────
PERCENTILES_D1_GAUSS = [0.0228, 0.1587, 0.5000, 0.8413, 0.9772]
PERCENTILES_D2_GAUSS = [0.0228, 0.1587, 0.8413, 0.9772]
PERCENTILES_D3_GAUSS = [0.0228, 0.1587, 0.8413, 0.9772]

D1_BINS = [
    "DEEP_DOLLAR_CRUSH",
    "WEAK_DOLLAR",
    "MODERATE_LOW_DOLLAR",
    "MODERATE_HIGH_DOLLAR",
    "ELEVATED_DOLLAR_STRESS",
    "DOLLAR_SPIKE_CRISIS",
]

D2_BINS = [
    "FAST_CRUSH_3D",
    "DECELERATING_DOWN_3D",
    "STABLE_CONTINUATION_3D",
    "ACCELERATING_UP_3D",
    "FAST_SPIKE_3D",
]

D3_BINS = [
    "VOL_EXTREME_SQUEEZE",
    "VOL_MODERATE_COMPRESSION",
    "VOL_NEUTRAL_BASELINE",
    "VOL_ACCELERATING_EXPANSION",
    "VOL_PEAK_DECELERATION",
]

# ── Bayesian Priors (same as master generator) ────────────────────
PRIORS_BY_HORIZON = {
    "fwd_1d": {"p_bull": 0.535, "ev_net": 0.0004, "days": 1.0},
    "fwd_3d": {"p_bull": 0.550, "ev_net": 0.0012, "days": 3.0},
    "fwd_5d": {"p_bull": 0.565, "ev_net": 0.0020, "days": 5.0},
}

# Zigzag priors: neutral prior for regularization
ZZ_PRIORS = {
    "zz25": {"p_bull": 0.50, "ev_net": 0.0, "e_ret_max": 5.0, "e_ret_min": -5.0},
    "zz50": {"p_bull": 0.50, "ev_net": 0.0, "e_ret_max": 10.0, "e_ret_min": -10.0},
    "zz75": {"p_bull": 0.50, "ev_net": 0.0, "e_ret_max": 15.0, "e_ret_min": -15.0},
}

M_WEIGHT = 10.0  # Bayesian Laplace smoothing weight


def classify_value(val: float, edges: list, labels: list) -> str:
    if pd.isna(val):
        return labels[2]
    for i, edge in enumerate(edges):
        if val < edge:
            return labels[i]
    return labels[-1]


def confidence_tier(n: int) -> str:
    """Classify confidence based on sample size."""
    if n == 0:
        return "NONE"
    elif n <= 2:
        return "ANECDOTAL"
    elif n <= 5:
        return "LOW"
    elif n <= 10:
        return "MODERATE"
    elif n <= 20:
        return "HIGH"
    else:
        return "ROBUST"


def bayesian_shrink_p(n_pos: int, n_tot: int, p0: float, m: float = M_WEIGHT) -> float:
    """Bayesian Laplace Shrinkage for probability."""
    return float((n_pos + m * p0) / (n_tot + m))


def bayesian_shrink_ev(ev_sample: float, n_tot: int, ev0: float, m: float = M_WEIGHT) -> float:
    """Bayesian Shrinkage for expected value."""
    credibility = float(n_tot / (n_tot + m))
    return float(credibility * ev_sample + (1.0 - credibility) * ev0)


# ── Standard Layer: Same as master generator ──────────────────────
def compute_standard_scale_metrics(sub: pd.DataFrame, fwd_col: str) -> dict:
    """
    Compute standard forward-return metrics with Bayesian Laplace Shrinkage.
    Identical to generate_all_150_state_fact_stores.py.
    """
    prior = PRIORS_BY_HORIZON[fwd_col]
    days = prior["days"]
    p0 = prior["p_bull"]
    ev0 = prior["ev_net"]

    sub_valid = sub.dropna(subset=[fwd_col])
    n_tot = len(sub_valid)

    if n_tot == 0:
        return {
            "n_raw": 0, "p_bull": p0, "p_bear": 1.0 - p0,
            "e_ret_max": 0.015, "e_ret_min": -0.015, "ev_net": ev0,
            "e_days": days, "ev_per_day": ev0 / days, "rr_asymmetry": 1.0,
            "confidence_tier": "NONE",
        }

    returns = sub_valid[fwd_col].values
    n_pos = int(np.sum(returns > 0))

    p_bayesian = bayesian_shrink_p(n_pos, n_tot, p0)
    p_bear = 1.0 - p_bayesian

    ev_sample = float(np.mean(returns))
    ev_shrunk = bayesian_shrink_ev(ev_sample, n_tot, ev0)

    pos_rets = returns[returns > 0]
    neg_rets = returns[returns < 0]
    e_ret_max = float(np.mean(pos_rets)) if len(pos_rets) > 0 else 0.015
    e_ret_min = float(np.mean(neg_rets)) if len(neg_rets) > 0 else -0.015
    rr_asym = float(abs(e_ret_max / e_ret_min)) if abs(e_ret_min) > 1e-6 else 1.0

    return {
        "n_raw": n_tot,
        "p_bull": round(p_bayesian, 6),
        "p_bear": round(p_bear, 6),
        "e_ret_max": round(e_ret_max, 6),
        "e_ret_min": round(e_ret_min, 6),
        "ev_net": round(ev_shrunk, 6),
        "e_days": days,
        "ev_per_day": round(float(ev_shrunk / days), 6),
        "rr_asymmetry": round(rr_asym, 4),
        "confidence_tier": confidence_tier(n_tot),
    }


# ── Kinematic Layer: ZigZag legs with Bayesian regularization ────
def compute_zigzag_scale_metrics(matched_legs: pd.DataFrame, scale: str) -> dict:
    """
    Compute physical ZigZag leg metrics with Bayesian Laplace Shrinkage.
    Preserves the V2 gains (n_pos, n_neg, ftt, zigzag_pure_vault) while
    regularizing p_bull and ev_net to prevent N=1 noise.
    """
    prior = ZZ_PRIORS[scale]

    pos_legs = matched_legs[matched_legs["start_type"] == "MIN"]
    neg_legs = matched_legs[matched_legs["start_type"] == "MAX"]

    n_pos = len(pos_legs)
    n_neg = len(neg_legs)
    n_tot = n_pos + n_neg

    if n_tot == 0:
        return {
            "n_pos": 0, "n_neg": 0,
            "p_bull": prior["p_bull"], "p_bear": 1.0 - prior["p_bull"],
            "e_ret_max": prior["e_ret_max"], "e_ret_min": prior["e_ret_min"],
            "ev_net": prior["ev_net"],
            "e_days": 15.0, "ftt_bull_days": 15.0, "ftt_bear_days": 15.0,
            "ev_per_day": 0.0, "rr_asymmetry": 1.0,
            "zigzag_pure_vault": True,
            "confidence_tier": "NONE",
        }

    # Bayesian smoothed probability
    p_bull = bayesian_shrink_p(n_pos, n_tot, prior["p_bull"])
    p_bear = 1.0 - p_bull

    e_max = float(pos_legs["log_return"].mean()) if n_pos > 0 else prior["e_ret_max"]
    e_min = float(neg_legs["log_return"].mean()) if n_neg > 0 else prior["e_ret_min"]

    # Bayesian shrunk EV
    ev_raw = (n_pos / n_tot * e_max + n_neg / n_tot * e_min) if n_tot > 0 else 0.0
    ev_net = bayesian_shrink_ev(ev_raw, n_tot, prior["ev_net"])

    e_days = float(matched_legs["duration_bars"].median())
    ftt_bull_days = float(pos_legs["duration_bars"].median()) if n_pos > 0 else e_days
    ftt_bear_days = float(neg_legs["duration_bars"].median()) if n_neg > 0 else e_days

    ev_per_day = ev_net / max(e_days, 1.0)
    abs_min = abs(e_min) if abs(e_min) > 1e-6 else 1e-6
    rr_asymmetry = e_max / abs_min

    return {
        "n_pos": int(n_pos),
        "n_neg": int(n_neg),
        "p_bull": round(float(p_bull), 4),
        "p_bear": round(float(p_bear), 4),
        "e_ret_max": round(float(e_max), 4),
        "e_ret_min": round(float(e_min), 4),
        "ev_net": round(float(ev_net), 4),
        "e_days": round(float(e_days), 1),
        "ftt_bull_days": round(float(ftt_bull_days), 1),
        "ftt_bear_days": round(float(ftt_bear_days), 1),
        "ev_per_day": round(float(ev_per_day), 6),
        "rr_asymmetry": round(float(rr_asymmetry), 4),
        "zigzag_pure_vault": True,
        "confidence_tier": confidence_tier(n_tot),
    }


# ── Structural Momentum: Bayesian regularized ────────────────────
def compute_structural_momentum(matched_legs: pd.DataFrame, all_scale_legs: pd.DataFrame, scale: str) -> dict:
    """
    Compute MIN→MIN / MAX→MAX accumulated returns with FULL statistical kit
    per momentum tercile. Each tercile is Bayesian-regularized (m=10).
    """
    min_legs_for_sm = 3 if scale == "zz75" else 6
    if len(matched_legs) < min_legs_for_sm:
        return None

    prior = ZZ_PRIORS[scale]

    full_sorted = all_scale_legs.sort_values("start_timestamp").copy()

    all_mins = full_sorted[full_sorted["start_type"] == "MIN"].copy()
    all_maxs = full_sorted[full_sorted["start_type"] == "MAX"].copy()

    all_mins["prev_min_price"] = all_mins["start_price"].shift(1)
    all_mins["accum_ret"] = np.log(all_mins["start_price"] / all_mins["prev_min_price"]) * 100
    all_mins["prev_start_ts"] = all_mins["start_timestamp"].shift(1)
    all_mins["inter_tp_bars"] = (
        pd.to_datetime(all_mins["start_timestamp"]) - pd.to_datetime(all_mins["prev_start_ts"])
    ).dt.days

    all_maxs["prev_max_price"] = all_maxs["start_price"].shift(1)
    all_maxs["accum_ret"] = np.log(all_maxs["start_price"] / all_maxs["prev_max_price"]) * 100
    all_maxs["prev_start_ts"] = all_maxs["start_timestamp"].shift(1)
    all_maxs["inter_tp_bars"] = (
        pd.to_datetime(all_maxs["start_timestamp"]) - pd.to_datetime(all_maxs["prev_start_ts"])
    ).dt.days

    mins_valid = all_mins.dropna(subset=["accum_ret"])
    maxs_valid = all_maxs.dropna(subset=["accum_ret"])

    if len(mins_valid) < 9 or len(maxs_valid) < 9:
        return None

    min_edges = mins_valid["accum_ret"].quantile([0.3333, 0.6667]).values
    max_edges = maxs_valid["accum_ret"].quantile([0.3333, 0.6667]).values

    matched_sorted = matched_legs.sort_values("start_timestamp").copy()
    matched_dates = set(matched_sorted["start_date"].values) if "start_date" in matched_sorted.columns else set()

    if "start_date" not in mins_valid.columns:
        mins_valid["start_date"] = pd.to_datetime(mins_valid["start_timestamp"]).dt.date
    if "start_date" not in maxs_valid.columns:
        maxs_valid["start_date"] = pd.to_datetime(maxs_valid["start_timestamp"]).dt.date

    matched_mins = mins_valid[mins_valid["start_date"].isin(matched_dates)].copy()
    matched_maxs = maxs_valid[maxs_valid["start_date"].isin(matched_dates)].copy()

    if matched_mins.empty and matched_maxs.empty:
        return None

    result = {}

    for leg_type, legs_df, edges, accum_labels, counterpart_df in [
        ("up_legs", matched_mins, min_edges, ["losing", "flat", "gaining"], matched_maxs),
        ("down_legs", matched_maxs, max_edges, ["decaying", "flat", "expanding"], matched_mins),
    ]:
        if len(legs_df) < 2:
            result[leg_type] = None
            continue

        momentum_data = {}
        for idx, label in enumerate(accum_labels):
            if idx == 0:
                mask = legs_df["accum_ret"] < edges[0]
            elif idx == 1:
                mask = (legs_df["accum_ret"] >= edges[0]) & (legs_df["accum_ret"] < edges[1])
            else:
                mask = legs_df["accum_ret"] >= edges[1]

            subset = legs_df[mask]
            n = len(subset)
            if n < 1:
                momentum_data[label] = {"n": int(n), "insufficient": True}
                continue

            # Full Statistical Kit with Bayesian Regularization
            momentum_dates = set(subset["start_date"].values)
            all_legs_on_dates = matched_sorted[matched_sorted["start_date"].isin(momentum_dates)]

            pos_on_dates = all_legs_on_dates[all_legs_on_dates["start_type"] == "MIN"]
            neg_on_dates = all_legs_on_dates[all_legs_on_dates["start_type"] == "MAX"]

            n_pos = len(pos_on_dates)
            n_neg = len(neg_on_dates)
            n_tot = n_pos + n_neg

            # Bayesian smoothed probability
            p_bull = bayesian_shrink_p(n_pos, n_tot, prior["p_bull"]) if n_tot > 0 else prior["p_bull"]
            p_bear = 1.0 - p_bull

            e_ret_max = float(pos_on_dates["log_return"].mean()) if n_pos > 0 else prior["e_ret_max"]
            e_ret_min = float(neg_on_dates["log_return"].mean()) if n_neg > 0 else prior["e_ret_min"]

            # Bayesian shrunk EV
            ev_raw = (n_pos / n_tot * e_ret_max + n_neg / n_tot * e_ret_min) if n_tot > 0 else 0.0
            ev_net = bayesian_shrink_ev(ev_raw, n_tot, prior["ev_net"])

            dur_med = float(subset["duration_bars"].median())
            ev_per_day = ev_net / max(dur_med, 1.0)

            abs_min = abs(e_ret_min) if abs(e_ret_min) > 1e-6 else 1e-6
            rr_asymmetry = e_ret_max / abs_min if e_ret_max != 0 else 1.0

            leg_mean_ret = float(subset["log_return"].mean())
            cap_vel = leg_mean_ret / max(dur_med, 1.0)
            inter_tp = float(subset["inter_tp_bars"].median()) if not subset["inter_tp_bars"].isna().all() else 0.0

            accum_mean = float(subset["accum_ret"].mean())
            accum_median = float(subset["accum_ret"].median())

            momentum_data[label] = {
                "n": int(n),
                "n_pos": int(n_pos),
                "n_neg": int(n_neg),
                "p_bull": round(float(p_bull), 4),
                "p_bear": round(float(p_bear), 4),
                "e_ret_max": round(float(e_ret_max), 4),
                "e_ret_min": round(float(e_ret_min), 4),
                "ev_net": round(float(ev_net), 4),
                "rr_asymmetry": round(float(rr_asymmetry), 4),
                "e_days": round(dur_med, 1),
                "ev_per_day": round(float(ev_per_day), 6),
                "leg_mean_ret": round(leg_mean_ret, 4),
                "cap_vel": round(cap_vel, 4),
                "accum_ret_mean": round(accum_mean, 4),
                "accum_ret_median": round(accum_median, 4),
                "inter_tp_dur_median": round(inter_tp, 1),
                "pct_of_legs": round(n / len(legs_df), 4),
                "confidence_tier": confidence_tier(n),
            }

        momentum_data["accum_edges"] = [round(float(edges[0]), 4), round(float(edges[1]), 4)]
        result[leg_type] = momentum_data

    return result


# ── Guidance & Regime (standard layer) ────────────────────────────
def determine_guidance_and_regime(zz25: dict, zz50: dict, zz75: dict, d1: str, n_state: int):
    """
    Identical logic to generate_all_150_state_fact_stores.py + DXY-specific
    intermarket overrides.
    """
    ev_1d = zz25["ev_net"]
    ev_3d = zz50["ev_net"]
    ev_5d = zz75["ev_net"]

    pb_3d = zz50["p_bull"]

    composite_ev = 0.3 * ev_1d + 0.4 * ev_3d + 0.3 * ev_5d

    if ev_1d > 0 and ev_3d > 0 and ev_5d > 0:
        divergence_regime = "FULL_CONVERGENT_BULL"
    elif ev_1d < 0 and ev_3d < 0 and ev_5d < 0:
        divergence_regime = "FULL_CONVERGENT_BEAR"
    elif ev_1d > 0 and ev_5d < 0:
        divergence_regime = "TACTICAL_REBOUND_IN_BEAR"
    elif ev_1d < 0 and ev_5d > 0:
        divergence_regime = "STRUCTURAL_BULL_PULLBACK"
    else:
        divergence_regime = "MIXED_HORIZON_TRANSITION"

    if composite_ev <= -0.008 or pb_3d <= 0.42 or "CRISIS" in d1 or "SPIKE" in d1:
        guidance = "STK_BLOCK_CRISIS"
    elif composite_ev >= 0.008 and pb_3d >= 0.58 and n_state >= 10:
        guidance = "STK_ACCUMULATE_STRUCTURAL"
    elif composite_ev >= 0.003 and pb_3d >= 0.52:
        guidance = "STK_BUY_DIP_TACTICAL"
    elif composite_ev <= -0.003:
        guidance = "STK_TRIM_TACTICAL"
    else:
        guidance = "STK_HOLD_STABLE"

    # DXY-specific intermarket overrides
    if d1 == "DOLLAR_SPIKE_CRISIS":
        divergence_regime = "GLOBAL_DOLLAR_LIQUIDITY_SQUEEZE"
        guidance = "STK_BLOCK_CRISIS"
    elif d1 == "ELEVATED_DOLLAR_STRESS" and divergence_regime != "FULL_CONVERGENT_BULL":
        guidance = "STK_TRIM_TACTICAL"

    return guidance, divergence_regime


def main():
    logger.info("Loading DXY and SPY full history from Neon Vault...")
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store=store)

    # Load DXY and SPY bars
    conn = store._conn()
    try:
        df_bars = pd.read_sql("""
            SELECT time::date as date, ticker, open, high, low, close
            FROM market.ohlcv_bars
            WHERE ticker IN ('SPY', 'DXY')
              AND timeframe = '1d'
            ORDER BY time, ticker
        """, conn)
    finally:
        store._put(conn)

    pivot_c = df_bars.pivot(index='date', columns='ticker', values='close').dropna()

    common = pivot_c.index
    dxy = pivot_c['DXY'].loc[common]
    spy_c = pivot_c['SPY'].loc[common]

    start_date = common.min()
    end_date = common.max()
    n_days = len(common)
    logger.info(f"Training population: {start_date} to {end_date} ({n_days} trading days / {n_days/252:.2f} years)")

    # ── SPY Forward Returns (Standard Layer) ──────────────────────
    spy_df = pd.DataFrame({"close": spy_c}, index=common)
    spy_df["fwd_1d"] = spy_df["close"].pct_change(1).shift(-1)
    spy_df["fwd_3d"] = spy_df["close"].pct_change(3).shift(-3)
    spy_df["fwd_5d"] = spy_df["close"].pct_change(5).shift(-5)
    spy_df["date_str"] = spy_df.index.astype(str)

    # ── DXY Dimensions ────────────────────────────────────────────
    dxy_df = pd.DataFrame({"val": dxy}, index=common)

    # D2: Velocity Δ3d
    dxy_df["d2_velocity"] = dxy_df["val"].diff(3)

    # D3: Station Volatility std(2d)/std(10d) V1.1
    vol_2d = dxy_df["val"].rolling(2).std()
    vol_10d = dxy_df["val"].rolling(10).std().replace(0, np.nan)
    dxy_df["vol_norm"] = (vol_2d / vol_10d).fillna(1.0)

    # D1: EXPANDING WINDOW RANK — Zero Look-Ahead Bias (same as master generator)
    d1_expanding_rank = dxy_df["val"].expanding(min_periods=252).rank(pct=True)

    # Edges computed from full population for JSON documentation
    d1_edges_doc = [float(x) for x in dxy_df["val"].quantile(PERCENTILES_D1_GAUSS)]
    d2_edges = [float(x) for x in dxy_df["d2_velocity"].dropna().quantile(PERCENTILES_D2_GAUSS)]
    d3_vol_edges = [float(x) for x in dxy_df["vol_norm"].dropna().quantile(PERCENTILES_D3_GAUSS)]

    # D1: Expanding rank mapped to Gaussian sigma bins
    dxy_df["bin_d1"] = d1_expanding_rank.apply(
        lambda r: classify_value(r, PERCENTILES_D1_GAUSS, D1_BINS) if pd.notna(r) else D1_BINS[2]
    )
    dxy_df["bin_d2"] = dxy_df["d2_velocity"].apply(lambda v: classify_value(v, d2_edges, D2_BINS))
    dxy_df["bin_d3"] = dxy_df["vol_norm"].apply(lambda v: classify_value(v, d3_vol_edges, D3_BINS))
    dxy_df["state_key"] = dxy_df["bin_d1"] + "__" + dxy_df["bin_d2"] + "__" + dxy_df["bin_d3"]
    dxy_df["date_str"] = dxy_df.index.astype(str)

    # Merge DXY dimensions with SPY forward returns
    df_merged = pd.merge(dxy_df, spy_df[["date_str", "fwd_1d", "fwd_3d", "fwd_5d"]],
                         on="date_str", how="inner")

    logger.info(f"Aligned training population: {len(df_merged)} days")

    # Load SPY zigzag legs for all 3 scales (Kinematic Layer)
    scale_dfs = {}
    for scale in ["zz25", "zz50", "zz75"]:
        df_legs = repo.get_confirmed_legs_with_indicators("SPY", scale=scale)
        if not df_legs.empty:
            df_legs = df_legs.sort_values("start_timestamp").reset_index(drop=True)
            df_legs["start_date"] = pd.to_datetime(df_legs["start_timestamp"]).dt.date
        scale_dfs[scale] = df_legs
        logger.info(f"  {scale}: {len(df_legs)} confirmed legs loaded")

    # ── Build States ──────────────────────────────────────────────
    state_groups = df_merged.groupby("state_key")
    final_states = {}

    for state_k, df_group in state_groups:
        n_state = len(df_group)
        dxy_vals = df_group["val"].values
        d1_cat = df_group["bin_d1"].iloc[0]
        dates_set = set(df_group["date_str"].values)

        state_doc = {
            "n": int(n_state),
            "stats": {
                "min": round(float(np.min(dxy_vals)), 4),
                "max": round(float(np.max(dxy_vals)), 4),
                "mean": round(float(np.mean(dxy_vals)), 4),
                "std": round(float(np.std(dxy_vals)), 4) if n_state > 1 else 0.0,
            },
        }

        # ── Standard Layer (Compatible with Compositor) ───────────
        zz25_std = compute_standard_scale_metrics(df_group, "fwd_1d")
        zz50_std = compute_standard_scale_metrics(df_group, "fwd_3d")
        zz75_std = compute_standard_scale_metrics(df_group, "fwd_5d")

        guidance, divergence_regime = determine_guidance_and_regime(
            zz25_std, zz50_std, zz75_std, d1_cat, n_state
        )

        state_doc["divergence_regime"] = divergence_regime
        state_doc["operational_guidance"] = guidance

        # Standard layer goes into zz25/zz50/zz75 (compositor-compatible)
        state_doc["zz25"] = zz25_std
        state_doc["zz50"] = zz50_std
        state_doc["zz75"] = zz75_std

        # ── Kinematic Layer (GAINED in V2, preserved) ─────────────
        # Convert dates_set to date objects for zigzag matching
        dates_as_dates = set()
        for ds in dates_set:
            try:
                dates_as_dates.add(pd.Timestamp(ds).date())
            except Exception:
                pass

        kinematic = {}
        for scale in ["zz25", "zz50", "zz75"]:
            df_scale_legs = scale_dfs[scale]
            if df_scale_legs.empty:
                continue

            matched_legs = df_scale_legs[df_scale_legs["start_date"].isin(dates_as_dates)]

            zz_metrics = compute_zigzag_scale_metrics(matched_legs, scale)

            momentum = compute_structural_momentum(matched_legs, df_scale_legs, scale)
            if momentum is not None:
                zz_metrics["structural_momentum"] = momentum

            # Import and call domino stats from the shared engine
            from backend.scripts.v3_fact_table_engine import compute_domino_stats
            next_scale = "zz50" if scale == "zz25" else ("zz75" if scale == "zz50" else None)
            next_scale_legs = scale_dfs.get(next_scale) if next_scale else None
            domino = compute_domino_stats(matched_legs, df_scale_legs, scale, next_scale_legs=next_scale_legs)
            if domino is not None:
                zz_metrics["prev_leg_domino"] = domino

            kinematic[scale] = zz_metrics

        if kinematic:
            state_doc["zigzag_kinematic"] = kinematic

        final_states[state_k] = state_doc

    # Filter out empty states
    final_states = {k: v for k, v in final_states.items() if v["n"] > 0}

    fact_store = {
        "_documentation": {
            "model_purpose": "11th METAR Station: DXY (US Dollar Index) — Harmonized V3 with dual-layer architecture.",
            "return_formula_standard": "R_fwd = (Close_{t+k} - Close_t) / Close_t for k in [1, 3, 5] — Bayesian Laplace Shrinkage m=10",
            "return_formula_kinematic": "R_net = log(P_end / P_start) * 100 on pure confirmed Neon Vault ZigZag legs (SPY) — Bayesian Laplace Shrinkage m=10",
            "intermarket_mechanics": {
                "dxy_up": "Global Liquidity Squeeze + Commodity Deflation + EM Debt Stress + Corporate Margin Compression",
                "dxy_down": "EM Capital Inflow + Commodity Inflation (Oil/Gold Cost-Push) + Reflation + Weaker Import Costs",
                "dxy_vs_rates": "Regime-dependent (not linear): QT→DXY↑TNX↑, Flight-to-safety→DXY↑TNX↓",
            },
            "dual_layer_architecture": {
                "standard_layer": "zz25/zz50/zz75 — fwd_1d/3d/5d bar returns with Bayesian Shrinkage. Compatible with convergence_compositor.py.",
                "kinematic_layer": "zigzag_kinematic.zz25/zz50/zz75 — Physical ZigZag leg metrics + structural_momentum. Bayesian regularized.",
            },
            "bayesian_smoothing": f"P_smooth = (n_pos + {M_WEIGHT}*P_prior) / (N + {M_WEIGHT}); EV_smooth = credibility*EV_sample + (1-cred)*EV_prior",
            "d1_classification": "Expanding Window Percentile Rank (zero look-ahead bias), mapped to Gaussian sigma bins",
            "velocity_lookback_window": "3 trading days (72h fast response)",
            "volatility_formula": "D3 = std(2d) / std(10d) — V1.1 standard",
            "data_sources": {
                "indicator_bars": "market.ohlcv_bars (DXY)",
                "target_bars": "market.ohlcv_bars (SPY)",
                "zigzag_repository": "market.zigzag_legs (Neon Vault, SPY confirmed legs)",
                "start_date": str(start_date),
                "end_date": str(end_date),
                "sample_size_days": int(n_days),
                "years_covered": round(float(n_days / 252.0), 2),
            },
            "state_hierarchy": "L0=Station -> L1=D1(Absolute Level) -> L2=D2(Velocity 72h) -> L3=D3(Vol Magnitude)",
            "dimension_thresholds_definition": {
                "dxy_edges_d1": d1_edges_doc,
                "dxy_edges_d2": d2_edges,
                "dxy_edges_d3": d3_vol_edges,
                "dxy_labels_d1": D1_BINS,
                "dxy_labels_d2": D2_BINS,
                "dxy_labels_d3": D3_BINS,
                "d1_classification_method": "expanding_rank_percentile_zero_lookahead",
            },
            "enhanced_v3_fields": {
                "zigzag_kinematic": {
                    "purpose": "Physical confirmed ZigZag leg metrics per scale, Bayesian regularized.",
                    "structural_momentum": {
                        "purpose": "MIN→MIN (Higher/Lower Lows) and MAX→MAX (Higher/Lower Highs) accumulated returns and inter-turning-point duration.",
                        "up_legs": "MIN→MIN: gaining=Higher Lows, losing=Lower Lows",
                        "down_legs": "MAX→MAX: expanding=Higher Highs, decaying=Lower Highs",
                        "bayesian_regularized": True,
                    },
                },
                "confidence_tier": {
                    "NONE": "N=0 — Bayesian prior only",
                    "ANECDOTAL": "N=1-2 — Context only, no sizing",
                    "LOW": "N=3-5 — Direction reliable, magnitude not. Sizing ×0.5",
                    "MODERATE": "N=6-10 — Normal sizing",
                    "HIGH": "N=11-20 — Strong signal",
                    "ROBUST": "N=21+ — Maximum conviction",
                },
            },
            "field_glossary": {
                "n": "Sample count of daily bars in state",
                "n_raw": "Sample count of forward return observations (standard layer)",
                "n_pos": "Number of bullish MIN->MAX physical legs (kinematic layer)",
                "n_neg": "Number of bearish MAX->MIN physical legs (kinematic layer)",
                "p_bull": "Bayesian smoothed probability of positive return/bullish leg",
                "p_bear": "1.0 - p_bull",
                "e_ret_max": "Average positive return (standard) or average bullish leg log return % (kinematic)",
                "e_ret_min": "Average negative return (standard) or average bearish leg log return % (kinematic)",
                "ev_net": "Bayesian shrunk expected value",
                "e_days": "Duration: 1/3/5 days (standard) or median physical leg duration (kinematic)",
                "ev_per_day": "ev_net / e_days — capital velocity",
                "rr_asymmetry": "|e_ret_max / e_ret_min| — reward/risk ratio",
                "confidence_tier": "Statistical confidence classification based on N",
                "divergence_regime": "Multi-scale horizon divergence regime (standard layer)",
                "operational_guidance": "Sizing code from Universal Institutional Taxonomy",
            },
            "signal_interpretation_policy": "Pure domain adapters interpret probabilities dynamically. Clean Architecture Standard.",
            "schema_version": "V3_HARMONIZED_DUAL_LAYER",
        },
        "station": "DXY",
        "sample_size": len(df_merged),
        "states_populated": len(final_states),
        "states": final_states,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(fact_store, f, indent=2, ensure_ascii=False)

    # Summary statistics
    has_kinematic = sum(1 for s in final_states.values() if "zigzag_kinematic" in s)
    has_sm_25 = sum(1 for s in final_states.values()
                    if "structural_momentum" in s.get("zigzag_kinematic", {}).get("zz25", {}))
    has_sm_50 = sum(1 for s in final_states.values()
                    if "structural_momentum" in s.get("zigzag_kinematic", {}).get("zz50", {}))
    has_sm_75 = sum(1 for s in final_states.values()
                    if "structural_momentum" in s.get("zigzag_kinematic", {}).get("zz75", {}))

    logger.info(f"✅ DXY Harmonized V3 Fact Store generated: {len(final_states)} states -> {OUTPUT_PATH}")
    logger.info(f"   Schema: D1({len(D1_BINS)}) × D2({len(D2_BINS)}) × D3({len(D3_BINS)}) = "
                f"{len(D1_BINS)*len(D2_BINS)*len(D3_BINS)} theoretical, {len(final_states)} populated")
    logger.info(f"   Standard layer: n_raw, p_bull (Bayesian m={M_WEIGHT}), ev_net (shrunk), "
                f"fwd_1d/3d/5d bar returns")
    logger.info(f"   D1: Expanding Window Rank (zero look-ahead bias)")
    logger.info(f"   Kinematic layer: {has_kinematic}/{len(final_states)} states with zigzag data")
    logger.info(f"   Structural momentum: zz25={has_sm_25}, zz50={has_sm_50}, zz75={has_sm_75}")

    store.close()


if __name__ == "__main__":
    main()
