#!/usr/bin/env python3
"""
V3 Fact Table Engine — Shared Pure-Math Engine for METAR Stations
=============================================================================
Provides standardized Dual-Layer V3 calculations:
  1. Standard Layer (forward bar returns 1d/3d/5d with Bayesian Shrinkage m=10)
  2. Kinematic Layer (SPY physical ZigZag legs with Bayesian Shrinkage m=10)
  3. Structural Momentum (MIN->MIN / MAX->MAX accumulated returns + terciles)
  4. Rule 24 Gaussian Sigma Scale Calibration [-2σ, -1σ, μ, +1σ, +2σ]
  5. Zero Look-Ahead Bias via Expanding Window Ranks for D1
  6. Confidence Tier Classification (ROBUST, HIGH, MODERATE, LOW, ANECDOTAL)

Authoritative reference: generate_dxy_fact_table.py (Station 11 benchmark)
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable, Any

import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("V3FactTableEngine")

# ── Gaussian Scale Calibration Standard (Rule 24) ───────────────────────────
PERCENTILES_D1_GAUSS = [0.0228, 0.1587, 0.5000, 0.8413, 0.9772]  # 6 bins
PERCENTILES_D2_GAUSS = [0.0228, 0.1587, 0.8413, 0.9772]          # 5 bins
PERCENTILES_D3_GAUSS = [0.0228, 0.1587, 0.8413, 0.9772]          # 5 bins

LABELS_D2_STANDARD = [
    "FAST_CRUSH_3D",
    "DECELERATING_DOWN_3D",
    "STABLE_CONTINUATION_3D",
    "ACCELERATING_UP_3D",
    "FAST_SPIKE_3D",
]

LABELS_D3_STANDARD = [
    "VOL_EXTREME_SQUEEZE",
    "VOL_MODERATE_COMPRESSION",
    "VOL_NEUTRAL_BASELINE",
    "VOL_ACCELERATING_EXPANSION",
    "VOL_PEAK_DECELERATION",
]

M_WEIGHT = 10.0  # Laplace shrinkage weight m=10
ZZ_PRIORS = {
    "zz25": {"p0": 0.50, "ev0": 0.0},
    "zz50": {"p0": 0.50, "ev0": 0.0},
    "zz75": {"p0": 0.50, "ev0": 0.0},
}


def classify_value(val: float, edges: list, labels: list) -> str:
    """Classify a numerical value using percentile edges into standard labels."""
    if pd.isna(val):
        return labels[2] if len(labels) > 2 else labels[0]
    for idx, e in enumerate(edges):
        if val < e:
            return labels[idx]
    return labels[-1]


def bayesian_shrink_p(n_pos: int, n_tot: int, p0: float = 0.50, m: float = M_WEIGHT) -> float:
    """Laplace Bayesian Shrinkage for Win Probability p_bull."""
    return float((n_pos + m * p0) / (n_tot + m))


def bayesian_shrink_ev(ev_sample: float, n_tot: int, ev0: float = 0.0, m: float = M_WEIGHT) -> float:
    """Laplace Bayesian Shrinkage for Expected Value (EV)."""
    credibility = float(n_tot / (n_tot + m))
    return float(credibility * ev_sample + (1.0 - credibility) * ev0)


def confidence_tier(n_tot: int) -> str:
    """Classify sample size into statistical confidence tier."""
    if n_tot >= 21:
        return "ROBUST"
    elif n_tot >= 11:
        return "HIGH"
    elif n_tot >= 6:
        return "MODERATE"
    elif n_tot >= 3:
        return "LOW"
    elif n_tot >= 1:
        return "ANECDOTAL"
    return "NONE"


def compute_standard_scale_metrics(df_group: pd.DataFrame, fwd_col: str, m_weight: float = M_WEIGHT) -> dict:
    """Compute Standard Layer metrics (forward bar returns) with Laplace Shrinkage."""
    returns = df_group[fwd_col].dropna().values
    n_tot = len(returns)
    days = 1.0 if fwd_col == "fwd_1d" else (3.0 if fwd_col == "fwd_3d" else 5.0)

    if n_tot == 0:
        return {
            "n_raw": 0, "p_bull": 0.50, "p_bear": 0.50,
            "e_ret_max": 0.015, "e_ret_min": -0.015, "ev_net": 0.0,
            "e_days": days, "ev_per_day": 0.0, "rr_asymmetry": 1.0,
            "confidence_tier": "NONE"
        }

    p0, ev0 = 0.50, 0.0
    n_pos = int(np.sum(returns > 0))
    p_bayesian = bayesian_shrink_p(n_pos, n_tot, p0, m_weight)
    ev_sample = float(np.mean(returns))
    ev_shrunk = bayesian_shrink_ev(ev_sample, n_tot, ev0, m_weight)

    pos_rets = returns[returns > 0]
    neg_rets = returns[returns < 0]
    e_ret_max = float(np.mean(pos_rets)) if len(pos_rets) > 0 else 0.015
    e_ret_min = float(np.mean(neg_rets)) if len(neg_rets) > 0 else -0.015
    rr_asym = float(abs(e_ret_max / e_ret_min)) if abs(e_ret_min) > 1e-6 else 1.0

    return {
        "n_raw": n_tot,
        "p_bull": round(p_bayesian, 4),
        "p_bear": round(1.0 - p_bayesian, 4),
        "e_ret_max": round(e_ret_max, 4),
        "e_ret_min": round(e_ret_min, 4),
        "ev_net": round(ev_shrunk, 6),
        "e_days": days,
        "ev_per_day": round(ev_shrunk / days, 6),
        "rr_asymmetry": round(rr_asym, 4),
        "confidence_tier": confidence_tier(n_tot)
    }


def compute_zigzag_scale_metrics(matched_legs: pd.DataFrame, scale: str, m_weight: float = M_WEIGHT) -> dict:
    """Compute Kinematic Layer metrics (physical ZigZag legs) with Bayesian regularization."""
    priors = ZZ_PRIORS.get(scale, {"p0": 0.50, "ev0": 0.0})
    p0, ev0 = priors["p0"], priors["ev0"]

    if matched_legs.empty:
        return {
            "n_pos": 0, "n_neg": 0, "p_bull": p0, "p_bear": round(1.0 - p0, 4),
            "e_ret_max": 0.02, "e_ret_min": -0.02, "ev_net": ev0,
            "e_days": 10.0, "ftt_bull_days": 10.0, "ftt_bear_days": 10.0,
            "ev_per_day": 0.0, "rr_asymmetry": 1.0,
            "confidence_tier": "NONE", "zigzag_pure_vault": True
        }

    pos_legs = matched_legs[matched_legs["start_type"] == "MIN"]
    neg_legs = matched_legs[matched_legs["start_type"] == "MAX"]

    n_pos = len(pos_legs)
    n_neg = len(neg_legs)
    n_tot = n_pos + n_neg

    p_bull_bayesian = bayesian_shrink_p(n_pos, n_tot, p0, m_weight)
    p_bear_bayesian = round(1.0 - p_bull_bayesian, 4)

    e_max = float(pos_legs["log_return"].mean()) if n_pos > 0 else 0.02
    e_min = float(neg_legs["log_return"].mean()) if n_neg > 0 else -0.02

    e_days = float(matched_legs["duration_bars"].median()) if n_tot > 0 else 10.0
    ftt_bull_days = float(pos_legs["duration_bars"].median()) if n_pos > 0 else e_days
    ftt_bear_days = float(neg_legs["duration_bars"].median()) if n_neg > 0 else e_days

    # Use SAMPLE proportions for raw EV (not shrunk p_bull) — single shrinkage only
    # Matches DXY benchmark: ev_raw = (n_pos/n_tot * e_max + n_neg/n_tot * e_min)
    raw_ev = (n_pos / n_tot * e_max + n_neg / n_tot * e_min) if n_tot > 0 else 0.0
    ev_net_shrunk = bayesian_shrink_ev(raw_ev, n_tot, ev0, m_weight)

    ev_per_day = ev_net_shrunk / max(e_days, 1.0)
    abs_min = abs(e_min) if abs(e_min) > 1e-6 else 1e-6
    rr_asymmetry = e_max / abs_min

    return {
        "n_pos": int(n_pos),
        "n_neg": int(n_neg),
        "p_bull": round(p_bull_bayesian, 4),
        "p_bear": p_bear_bayesian,
        "e_ret_max": round(e_max, 4),
        "e_ret_min": round(e_min, 4),
        "ev_net": round(ev_net_shrunk, 4),
        "e_days": round(e_days, 1),
        "ftt_bull_days": round(ftt_bull_days, 1),
        "ftt_bear_days": round(ftt_bear_days, 1),
        "ev_per_day": round(ev_per_day, 6),
        "rr_asymmetry": round(rr_asymmetry, 4),
        "confidence_tier": confidence_tier(n_tot),
        "zigzag_pure_vault": True,
    }


def compute_structural_momentum(matched_legs: pd.DataFrame, all_scale_legs: pd.DataFrame, scale: str) -> Optional[dict]:
    """Compute Structural Momentum (MIN->MIN / MAX->MAX accumulated returns + terciles)."""
    min_legs_thresh = 3 if scale == "zz75" else 6
    if len(matched_legs) < min_legs_thresh:
        return None

    result = {}
    for leg_type, start_type in [("up_legs", "MIN"), ("down_legs", "MAX")]:
        sub = matched_legs[matched_legs["start_type"] == start_type]
        if sub.empty:
            continue

        accum_rets = []
        for idx, row in sub.iterrows():
            leg_id = row["leg_id"]
            next_same = all_scale_legs[
                (all_scale_legs["start_type"] == start_type) &
                (all_scale_legs["leg_id"] > leg_id)
            ]
            if not next_same.empty:
                next_row = next_same.iloc[0]
                P0 = row["start_price"]
                P2 = next_row["start_price"]
                if P0 > 0:
                    accum_ret = np.log(P2 / P0) * 100.0
                    accum_rets.append(accum_ret)

        if not accum_rets:
            continue

        arr = np.array(accum_rets)
        n_acc = len(arr)
        n_pos = int(np.sum(arr > 0))

        p_up_shrunk = bayesian_shrink_p(n_pos, n_acc, 0.50, M_WEIGHT)
        ev_sample = float(np.mean(arr))
        ev_shrunk = bayesian_shrink_ev(ev_sample, n_acc, 0.0, M_WEIGHT)

        edges = np.quantile(arr, [0.3333, 0.6667]) if n_acc >= 3 else [float(np.min(arr)), float(np.max(arr))]

        momentum_data = {
            "n_measured": n_acc,
            "p_continuation": round(p_up_shrunk, 4),
            "ev_structural_pct": round(ev_shrunk, 4),
            "mean_accum_ret": round(float(np.mean(arr)), 4),
            "median_accum_ret": round(float(np.median(arr)), 4),
            "terciles_pct": {
                "t1_weak": round(float(np.mean(arr[arr <= edges[0]])), 4) if np.sum(arr <= edges[0]) > 0 else 0.0,
                "t2_neutral": round(float(np.mean(arr[(arr > edges[0]) & (arr <= edges[1])])), 4) if np.sum((arr > edges[0]) & (arr <= edges[1])) > 0 else 0.0,
                "t3_strong": round(float(np.mean(arr[arr > edges[1]])), 4) if np.sum(arr > edges[1]) > 0 else 0.0,
            },
            "accum_edges": [round(float(edges[0]), 4), round(float(edges[1]), 4)],
        }
        result[leg_type] = momentum_data

    return result if result else None


def compute_domino_stats(
    matched_legs: pd.DataFrame,
    all_scale_legs: pd.DataFrame,
    scale: str,
    next_scale_legs: Optional[pd.DataFrame] = None,
) -> Optional[dict]:
    """Compute domino effect statistics from prev_leg_return for matched legs.

    Returns dict with:
      mean_prev_return: Bayesian-shrunk mean of |prev_leg_return|
      median_prev_return: Median of |prev_leg_return|
      mean_prev_duration: Mean of prev_leg_duration
      p_negative_prev: Fraction with prev_leg_return < 0 (Bayesian shrunk)
      p_extreme_prev: Fraction with |prev_leg_return| > P90 of full population
      terciles_domino: {t1_small, t2_medium, t3_large} → cascade stats
    """
    if "prev_leg_return" not in matched_legs.columns:
        return None

    sub = matched_legs.dropna(subset=["prev_leg_return"]).copy()
    min_n = 3 if scale == "zz75" else 6
    if len(sub) < min_n:
        return None

    abs_returns = sub["prev_leg_return"].abs().values
    signed_returns = sub["prev_leg_return"].values
    n_total = len(abs_returns)

    # Calculate is_cascade if not present
    if "is_cascade" not in sub.columns:
        if next_scale_legs is not None and not next_scale_legs.empty:
            s_dts = pd.to_datetime(sub["start_timestamp"]) if "start_timestamp" in sub.columns else pd.to_datetime(sub["start_date"])
            next_dts = pd.to_datetime(next_scale_legs["start_timestamp"]) if "start_timestamp" in next_scale_legs.columns else pd.to_datetime(next_scale_legs["start_date"])
            next_types = next_scale_legs["start_type"].values

            is_cascade_vals = []
            for s_dt, s_type in zip(s_dts, sub["start_type"].values):
                diffs = (next_dts - s_dt).abs()
                match = any((diffs <= pd.Timedelta(days=3)) & (next_types == s_type))
                is_cascade_vals.append(float(match))
            sub["is_cascade"] = is_cascade_vals
        else:
            if "theoretical_return_pct" in sub.columns:
                sub["is_cascade"] = (sub["theoretical_return_pct"].abs() >= 7.5).astype(float)
            else:
                sub["is_cascade"] = 0.5

    # Population P90 for extreme threshold
    all_prev = all_scale_legs.dropna(subset=["prev_leg_return"])["prev_leg_return"].abs()
    p90 = float(all_prev.quantile(0.90)) if len(all_prev) >= 10 else float(np.percentile(abs_returns, 90))

    n_neg = int(np.sum(signed_returns < 0))
    n_extreme = int(np.sum(abs_returns > p90))

    mean_abs = float(np.mean(abs_returns))
    mean_abs_shrunk = bayesian_shrink_ev(mean_abs, n_total, float(all_prev.mean()) if len(all_prev) > 0 else 0.05, M_WEIGHT)

    result = {
        "n_measured": n_total,
        "mean_prev_return": round(mean_abs_shrunk, 6),
        "median_prev_return": round(float(np.median(abs_returns)), 6),
        "mean_prev_duration": round(float(sub["prev_leg_duration"].dropna().mean()), 1) if "prev_leg_duration" in sub.columns and sub["prev_leg_duration"].notna().any() else None,
        "p_negative_prev": round(bayesian_shrink_p(n_neg, n_total, 0.50, M_WEIGHT), 4),
        "p_extreme_prev": round(bayesian_shrink_p(n_extreme, n_total, 0.10, M_WEIGHT), 4),
        "extreme_threshold_p90": round(p90, 6),
    }

    # Terciles of |prev_leg_return| → cascade stats
    if n_total >= 9:
        edges = np.quantile(abs_returns, [0.3333, 0.6667])
        tercile_labels = ["t1_small", "t2_medium", "t3_large"]
        masks = [
            abs_returns <= edges[0],
            (abs_returns > edges[0]) & (abs_returns <= edges[1]),
            abs_returns > edges[1],
        ]
        terciles = {}
        for label, mask in zip(tercile_labels, masks):
            t_sub = sub[mask]
            n_t = len(t_sub)
            if n_t > 0:
                terciles[label] = {
                    "n": n_t,
                    "mean_abs_return": round(float(abs_returns[mask].mean()), 6),
                    "cascade_rate": round(float(t_sub["is_cascade"].mean()), 4),
                }
        result["terciles_domino"] = terciles
        result["tercile_edges"] = [round(float(edges[0]), 6), round(float(edges[1]), 6)]

    return result


def determine_guidance_and_regime(
    zz25: dict, zz50: dict, zz75: dict, d1: str, n_state: int,
    pivot_name: Optional[str] = None, pivot_overrides: Optional[dict] = None
) -> Tuple[str, str]:
    """Determine universal 4D action taxonomy and divergence regime with pivot overrides."""
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

    if composite_ev <= -0.008 or pb_3d <= 0.42 or "CRISIS" in d1 or "SPIKE" in d1 or "PARANOIA" in d1:
        guidance = "STK_BLOCK_CRISIS"
    elif composite_ev >= 0.008 and pb_3d >= 0.58 and n_state >= 10:
        guidance = "STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION"
    elif composite_ev >= 0.003 and pb_3d >= 0.52:
        guidance = "STK_BUY_DIP_TACTICAL"
    elif composite_ev <= -0.003:
        guidance = "STK_TRIM_TACTICAL"
    else:
        guidance = "STK_HOLD_STABLE"

    # Station-specific pivot overrides (Domain Physics)
    if pivot_name and pivot_overrides and pivot_name in pivot_overrides:
        override = pivot_overrides[pivot_name]
        if "guidance" in override:
            candidate = override["guidance"]
            # Don't upgrade to MAX_CONVICTION with anecdotal evidence (N<10)
            if candidate == "STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION" and n_state < 10:
                pass  # Keep original guidance — insufficient sample for max conviction
            else:
                guidance = candidate
        if "regime" in override:
            divergence_regime = override["regime"]

    return guidance, divergence_regime


def load_spy_and_station_bars(store: TimescaleDataStore, ticker: str) -> Tuple[pd.DataFrame, pd.Series]:
    """Load SPY and station bars from Neon Vault."""
    conn = store._conn()
    try:
        if ticker == "CREDIT_RATIO":
            df_bars = pd.read_sql("""
                SELECT time::date as date, ticker, close
                FROM market.ohlcv_bars
                WHERE ticker IN ('SPY', 'HYG', 'LQD') AND timeframe = '1d'
                ORDER BY time, ticker
            """, conn)
            pivot_c = df_bars.pivot(index='date', columns='ticker', values='close').dropna()
            station_series = (pivot_c['HYG'] / pivot_c['LQD']).dropna()
            spy_c = pivot_c['SPY'].loc[station_series.index]
        else:
            df_bars = pd.read_sql(f"""
                SELECT time::date as date, ticker, close
                FROM market.ohlcv_bars
                WHERE ticker IN ('SPY', '{ticker}') AND timeframe = '1d'
                ORDER BY time, ticker
            """, conn)
            pivot_c = df_bars.pivot(index='date', columns='ticker', values='close').dropna()
            station_series = pivot_c[ticker]
            spy_c = pivot_c['SPY']

        common = station_series.index.intersection(spy_c.index)
        station_series = station_series.loc[common]
        spy_c = spy_c.loc[common]

        spy_df = pd.DataFrame({"close": spy_c}, index=common)
        spy_df["fwd_1d"] = spy_df["close"].pct_change(1).shift(-1)
        spy_df["fwd_3d"] = spy_df["close"].pct_change(3).shift(-3)
        spy_df["fwd_5d"] = spy_df["close"].pct_change(5).shift(-5)
        spy_df["date_str"] = spy_df.index.astype(str)

        return spy_df, station_series
    finally:
        store._put(conn)


def build_v3_dual_layer_fact_store(
    station_name: str,
    ticker: str,
    model_purpose: str,
    d1_labels: List[str],
    pivot_fn: Optional[Callable[[pd.DataFrame], pd.Series]] = None,
    pivot_overrides: Optional[dict] = None,
    intermarket_notes: Optional[dict] = None,
    output_path: Optional[Path] = None,
) -> dict:
    """
    Main Orchestrator to build a V3 Dual-Layer Fact Store for any METAR station.
    """
    logger.info(f"=== Generating V3 Dual-Layer Fact Store: {station_name.upper()} ({ticker}) ===")
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store=store)

    spy_df, station_series = load_spy_and_station_bars(store, ticker)

    common = station_series.index
    n_days = len(common)
    start_date = common.min()
    end_date = common.max()
    logger.info(f"Aligned population: {start_date} to {end_date} ({n_days} trading days / {n_days/252:.2f} years)")

    ind_df = pd.DataFrame({"val": station_series}, index=common)
    ind_df["d2_velocity"] = ind_df["val"].diff(3)

    vol_2d = ind_df["val"].rolling(2).std()
    vol_10d = ind_df["val"].rolling(10).std().replace(0, np.nan)
    ind_df["vol_norm"] = (vol_2d / vol_10d).fillna(1.0)

    # D1 Expanding rank (zero look-ahead bias)
    d1_expanding_rank = ind_df["val"].expanding(min_periods=252).rank(pct=True)

    calib_df = ind_df[pd.to_datetime(ind_df.index) >= pd.to_datetime("2011-02-01")] if station_name.lower() == "skew" else ind_df

    d1_edges_doc = [float(x) for x in calib_df["val"].quantile(PERCENTILES_D1_GAUSS)]
    # FIX P0.1 (auditoría 22-Ago-2026): D2/D3 se binneaban contra cuantiles de TODA
    # la historia (look-ahead: información del futuro filtrando hacia atrás).
    # Corrección: expanding percentile rank, idéntico a D1 (zero look-ahead).
    # Los edges globales se conservan SOLO como documentación de referencia.
    d2_edges = [float(x) for x in calib_df["d2_velocity"].dropna().quantile(PERCENTILES_D2_GAUSS)]
    d3_vol_edges = [float(x) for x in calib_df["vol_norm"].dropna().quantile(PERCENTILES_D3_GAUSS)]
    d2_expanding_rank = ind_df["d2_velocity"].expanding(min_periods=252).rank(pct=True)
    d3_expanding_rank = ind_df["vol_norm"].expanding(min_periods=252).rank(pct=True)

    ind_df["bin_d1"] = d1_expanding_rank.apply(
        lambda r: classify_value(r, PERCENTILES_D1_GAUSS, d1_labels) if pd.notna(r) else d1_labels[2]
    )
    ind_df["bin_d2"] = d2_expanding_rank.apply(
        lambda r: classify_value(r, PERCENTILES_D2_GAUSS, LABELS_D2_STANDARD) if pd.notna(r) else LABELS_D2_STANDARD[2]
    )
    ind_df["bin_d3"] = d3_expanding_rank.apply(
        lambda r: classify_value(r, PERCENTILES_D3_GAUSS, LABELS_D3_STANDARD) if pd.notna(r) else LABELS_D3_STANDARD[2]
    )

    if pivot_fn is not None:
        ind_df["pivot"] = pivot_fn(ind_df)
        ind_df["state_key"] = ind_df["bin_d1"] + "__" + ind_df["bin_d2"] + "__" + ind_df["bin_d3"]
    else:
        ind_df["pivot"] = "STABLE_CONTINUATION"
        ind_df["state_key"] = ind_df["bin_d1"] + "__" + ind_df["bin_d2"] + "__" + ind_df["bin_d3"]

    ind_df["date_str"] = ind_df.index.astype(str)

    df_merged = pd.merge(ind_df, spy_df[["date_str", "fwd_1d", "fwd_3d", "fwd_5d"]], on="date_str", how="inner")

    # Load SPY ZigZag legs
    scale_dfs = {}
    for scale in ["zz25", "zz50", "zz75"]:
        df_legs = repo.get_confirmed_legs_with_indicators("SPY", scale=scale)
        if not df_legs.empty:
            df_legs = df_legs.sort_values("start_timestamp").reset_index(drop=True)
            df_legs["start_date"] = pd.to_datetime(df_legs["start_timestamp"]).dt.date
        scale_dfs[scale] = df_legs

    # Build States
    state_groups = df_merged.groupby("state_key")
    final_states = {}

    for state_k, df_group in state_groups:
        n_state = len(df_group)
        val_stats = df_group["val"].values
        d1_cat = df_group["bin_d1"].iloc[0]
        pivot_name = df_group["pivot"].iloc[0] if "pivot" in df_group.columns else None
        dates_set = set(df_group["date_str"].values)

        state_doc = {
            "n": int(n_state),
            "stats": {
                "min": round(float(np.min(val_stats)), 4),
                "max": round(float(np.max(val_stats)), 4),
                "mean": round(float(np.mean(val_stats)), 4),
                "std": round(float(np.std(val_stats)), 4) if n_state > 1 else 0.0,
            },
        }

        zz25_std = compute_standard_scale_metrics(df_group, "fwd_1d")
        zz50_std = compute_standard_scale_metrics(df_group, "fwd_3d")
        zz75_std = compute_standard_scale_metrics(df_group, "fwd_5d")

        guidance, divergence_regime = determine_guidance_and_regime(
            zz25_std, zz50_std, zz75_std, d1_cat, n_state, pivot_name, pivot_overrides
        )

        state_doc["divergence_regime"] = divergence_regime
        state_doc["operational_guidance"] = guidance
        state_doc["zz25"] = zz25_std
        state_doc["zz50"] = zz50_std
        state_doc["zz75"] = zz75_std

        # Kinematic Layer
        dates_as_dates = {pd.Timestamp(ds).date() for ds in dates_set if pd.notna(ds)}
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

            next_scale = "zz50" if scale == "zz25" else ("zz75" if scale == "zz50" else None)
            next_scale_legs = scale_dfs.get(next_scale) if next_scale else None
            domino = compute_domino_stats(matched_legs, df_scale_legs, scale, next_scale_legs=next_scale_legs)
            if domino is not None:
                zz_metrics["prev_leg_domino"] = domino

            kinematic[scale] = zz_metrics

        if kinematic:
            state_doc["zigzag_kinematic"] = kinematic

        final_states[state_k] = state_doc

    final_states = {k: v for k, v in final_states.items() if v["n"] > 0}

    fact_store = {
        "_documentation": {
            "model_purpose": f"METAR Station: {station_name.upper()} ({ticker}) — Harmonized V3 Dual-Layer Architecture.",
            "return_formula": "R_fwd = (Close_{t+k} - Close_t) / Close_t for k in [1, 3, 5]; R_net = log(P_end / P_start) * 100 on confirmed Neon Vault ZigZag legs",
            "return_formula_standard": "R_fwd = (Close_{t+k} - Close_t) / Close_t for k in [1, 3, 5] — Bayesian Laplace Shrinkage m=10",
            "return_formula_kinematic": "R_net = log(P_end / P_start) * 100 on pure confirmed Neon Vault ZigZag legs (SPY) — Bayesian Laplace Shrinkage m=10",
            "intermarket_mechanics": intermarket_notes or {},
            "dual_layer_architecture": {
                "standard_layer": "zz25/zz50/zz75 — fwd_1d/3d/5d bar returns with Bayesian Shrinkage m=10 and confidence_tier. Compatible with convergence_compositor.py.",
                "kinematic_layer": "zigzag_kinematic.zz25/zz50/zz75 — Physical ZigZag leg metrics + structural_momentum. Bayesian regularized.",
            },
            "bayesian_smoothing": f"P_smooth = (n_pos + {M_WEIGHT}*P_prior) / (N + {M_WEIGHT}); EV_smooth = credibility*EV_sample + (1-cred)*EV_prior",
            "d1_classification": "Expanding Window Percentile Rank (zero look-ahead bias), mapped to Gaussian sigma bins",
            "velocity_lookback_window": "3 trading days (72h fast response)",
            "volatility_formula": "D3 = std(2d) / std(10d) — V1.1 standard",
            "dimension_thresholds_definition": {
                f"{station_name.lower()}_edges_d1": d1_edges_doc,
                f"{station_name.lower()}_edges_d2": d2_edges,
                f"{station_name.lower()}_edges_d3": d3_vol_edges,
                f"{station_name.lower()}_labels_d1": d1_labels,
                f"{station_name.lower()}_labels_d2": LABELS_D2_STANDARD,
                f"{station_name.lower()}_labels_d3": LABELS_D3_STANDARD,
            },
            "data_sources": {
                "bars": "market.ohlcv_bars (Neon Vault)",
                "zigzag_repository": "market.zigzag_legs (SPY)",
                "start_date": str(start_date),
                "end_date": str(end_date),
                "sample_size_days": int(n_days),
                "years_covered": round(float(n_days / 252.0), 2),
            },
            "state_hierarchy": {
                "L0": "METAR Station Root",
                "L1": "D1 Directional Level (Gaussian σ-edges)",
                "L2": "D2 Velocity (3d Δ)",
                "L3": "D3 Volatility Instability (std 2d / std 10d)"
            },
            "field_glossary": {
                "n": "Sample size in state",
                "p_bull": "Bayesian Laplace smoothed probability of positive forward return",
                "ev": "Bayesian credibility shrunk expected net return (%)",
                "fwd_1d": "Forward 1-day return metrics",
                "fwd_3d": "Forward 3-day return metrics",
                "fwd_5d": "Forward 5-day return metrics",
                "confidence_tier": "Statistical confidence grade (HIGH >=30, MED >=10, LOW <10)"
            },
            "signal_interpretation_policy": "Clean Architecture Standard: pure domain rules iterate over states and emit universal 4D action taxonomy.",
        },
        "station": station_name.upper(),
        "sample_size": len(df_merged),
        "states_populated": len(final_states),
        "states": final_states,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(fact_store, f, indent=2, ensure_ascii=False)
        logger.info(f"🎉 ✅ Fact Store V3 para {station_name.upper()} guardado exitosamente en {output_path}")

    return fact_store
