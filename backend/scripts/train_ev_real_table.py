#!/usr/bin/env python3
"""
Train Real Point-in-Time Expected Value (EV) Probability Table
===============================================================
Computes the forward pivot expected value model for quality_swing with:
  1. Real Point-in-Time Returns: (price(t_pivot) / close(t)) - 1
     Erasing all 'Ghost Return' bias from retrospective swing returns.
  2. Maximum Swing Horizon Gate: days_to_pivot <= 120 days.
     Ensures historical data gaps or missing future pivots do not contaminate calculations.
  3. Hierarchy of Rollups:
     - L3: Full 3D State (T_slope | C_slope | sigma_vwap_wave) - 180 states
     - L2: Mid-Macro (T_slope | C_slope) - 36 states
     - L1: Macro Marea (T_slope) - 6 states
     - L0: Global Baseline
  4. Explicit Zigzag Scales: zz25 (2.5%), zz50 (5.0%), zz75 (7.5%)
  5. Raw Numerical Fatigue Buckets: run_length buckets (1, 2, 3-4, 5-7, 8-10, 11+)
     Without hardcoded qualitative labels (evaluation done flexibly in domain).

Reads from Vault: engine.channel_snapshots + market.ohlcv_bars + engine.zigzag_points.
Output: backend/modules/quality_swing/domain/rules/rc_ev_probability_table.json
"""
import os, sys, json, time, math, logging, bisect
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Configuration — Thresholds matching rc_slope_classifier.py
# ═══════════════════════════════════════════════════════════════
ZIGZAG_LEVELS = [0.025, 0.05, 0.075]
ZIGZAG_LABEL = {0.025: "zz25", 0.05: "zz50", 0.075: "zz75"}
MAX_HORIZON_DAYS = 120  # Maximum days to next pivot for swing validity

OUTPUT_PATH = root_dir / "backend/modules/quality_swing/domain/rules/rc_ev_probability_table.json"

SLOPE_TH = {
    "T": {"+": (0.0456, 0.0983), "-": (0.0263, 0.0765)},
    "C": {"+": (0.0845, 0.1749), "-": (0.0613, 0.1583)},
}

SIGMA_BINS = [
    (-999, -1.0, "<<"),
    (-1.0, -0.3, "<"),
    (-0.3,  0.3, "~"),
    ( 0.3,  1.0, ">"),
    ( 1.0,  999, ">>"),
]

RUN_BUCKETS = [
    (0, 1, "1"),
    (1, 2, "2"),
    (2, 4, "3-4"),
    (4, 7, "5-7"),
    (7, 10, "8-10"),
    (10, 9999, "11+"),
]


# ═══════════════════════════════════════════════════════════════
# State Classification
# ═══════════════════════════════════════════════════════════════

def classify_slope(value: float, channel: str) -> str:
    """Classify slope into +++/++/+/-/--/--- for T or C channels."""
    th = SLOPE_TH[channel]
    if value >= 0:
        p33, p66 = th["+"]
        if value >= p66: return f"{channel}+++"
        elif value >= p33: return f"{channel}++"
        else: return f"{channel}+"
    else:
        p33, p66 = th["-"]
        av = abs(value)
        if av >= p66: return f"{channel}---"
        elif av >= p33: return f"{channel}--"
        else: return f"{channel}-"


def classify_sigma(value: float) -> str:
    """Classify σ_vwap_wave into <</</ ~/>/>>."""
    for lo, hi, label in SIGMA_BINS:
        if lo <= value < hi:
            return label
    return ">>"


# ═══════════════════════════════════════════════════════════════
# Data Loading & Real Return Computation
# ═══════════════════════════════════════════════════════════════

CACHE_DIR = root_dir / "backend/scratch/cache"
CACHE_SNAP_PATH = CACHE_DIR / "snapshots_ohlcv_cache.parquet"


def load_all_data(store: TimescaleDataStore, use_cache: bool = True):
    """Load channel_snapshots + market.ohlcv_bars with local Parquet caching."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    if use_cache and CACHE_SNAP_PATH.exists():
        logger.info(f"Loading merged snapshots from local Parquet cache: {CACHE_SNAP_PATH}")
        df = pd.read_parquet(CACHE_SNAP_PATH)
        zigzags = {}
        for level in ZIGZAG_LEVELS:
            zz_cache = CACHE_DIR / f"zigzag_{ZIGZAG_LABEL[level]}.parquet"
            if zz_cache.exists():
                logger.info(f"Loading zigzag points for {ZIGZAG_LABEL[level]} from Parquet cache...")
                zz = pd.read_parquet(zz_cache)
            else:
                logger.info(f"Loading engine.zigzag_points for level {level*100:.1f}% from DB...")
                zz = pd.read_sql(f"""
                    SELECT ticker, timestamp, tp_type, price
                    FROM engine.zigzag_points
                    WHERE min_swing_pct = {level}
                    ORDER BY ticker, timestamp
                """, store.engine)
                zz['timestamp'] = pd.to_datetime(zz['timestamp'], utc=True)
                zz = zz.drop_duplicates(subset=['ticker', 'timestamp'])
                zz.to_parquet(zz_cache, compression='zstd')
            zigzags[level] = zz
        return df, zigzags

    logger.info("Loading channel_snapshots from DB...")
    cs_df = pd.read_sql("""
        SELECT ticker, timestamp, tide_slope, current_slope, vwap_sigma_wave
        FROM engine.channel_snapshots
        WHERE timeframe = '1d'
          AND tide_slope IS NOT NULL
          AND current_slope IS NOT NULL
          AND vwap_sigma_wave IS NOT NULL
    """, store.engine)

    logger.info("Loading market.ohlcv_bars from DB...")
    ohlcv_df = pd.read_sql("""
        SELECT ticker, time AS timestamp, close
        FROM market.ohlcv_bars
        WHERE timeframe = '1d' AND close > 0
    """, store.engine)

    logger.info("Deduplicating and merging snapshots + ohlcv_bars...")
    cs_df['timestamp'] = pd.to_datetime(cs_df['timestamp'], utc=True)
    ohlcv_df['timestamp'] = pd.to_datetime(ohlcv_df['timestamp'], utc=True)

    cs_df = cs_df.drop_duplicates(subset=['ticker', 'timestamp'])
    ohlcv_df = ohlcv_df.drop_duplicates(subset=['ticker', 'timestamp'])

    df = pd.merge(cs_df, ohlcv_df, on=['ticker', 'timestamp'], how='inner')

    # Classify states
    df['T'] = df['tide_slope'].apply(lambda x: classify_slope(x, 'T'))
    df['C'] = df['current_slope'].apply(lambda x: classify_slope(x, 'C'))
    df['svw'] = df['vwap_sigma_wave'].apply(classify_sigma)
    df['state_l3'] = (df['T'] + '|' + df['C'] + '|' + df['svw']).astype('category')
    df['state_l2'] = (df['T'] + '|' + df['C']).astype('category')
    df['state_l1'] = df['T'].astype('category')

    # Compute run_length per ticker
    df = df.sort_values(['ticker', 'timestamp']).reset_index(drop=True)
    df['prev_state'] = df.groupby('ticker')['state_l3'].shift(1)
    df['state_change'] = df['state_l3'] != df['prev_state']
    df['run_group'] = df.groupby('ticker')['state_change'].cumsum()
    df['run_length'] = df.groupby(['ticker', 'run_group']).cumcount() + 1

    logger.info(f"  Loaded {len(df):,} clean merged snapshots across {df['ticker'].nunique()} tickers")
    df.to_parquet(CACHE_SNAP_PATH, compression='zstd')

    # Load zigzag points by level
    zigzags = {}
    for level in ZIGZAG_LEVELS:
        zz_cache = CACHE_DIR / f"zigzag_{ZIGZAG_LABEL[level]}.parquet"
        logger.info(f"Loading engine.zigzag_points for level {level*100:.1f}% from DB...")
        zz = pd.read_sql(f"""
            SELECT ticker, timestamp, tp_type, price
            FROM engine.zigzag_points
            WHERE min_swing_pct = {level}
            ORDER BY ticker, timestamp
        """, store.engine)
        zz['timestamp'] = pd.to_datetime(zz['timestamp'], utc=True)
        zz = zz.drop_duplicates(subset=['ticker', 'timestamp'])
        zz.to_parquet(zz_cache, compression='zstd')
        zigzags[level] = zz
        logger.info(f"  {len(zz):,} pivots for level {ZIGZAG_LABEL[level]}")

    return df, zigzags


def compute_real_forward_labels(snap_df: pd.DataFrame, zz_df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized forward-label matching per ticker with 120-day horizon gate.
    
    Computes REAL POINT-IN-TIME RETURN: (price(t_pivot) / close(t)) - 1.
    """
    zz_by_ticker = {tk: group for tk, group in zz_df.groupby('ticker')}

    ticker_dfs = []
    for ticker, tdf in snap_df.groupby('ticker'):
        tzz = zz_by_ticker.get(ticker)
        if tzz is None or len(tzz) == 0:
            continue

        tdf = tdf.sort_values('timestamp')
        tzz = tzz.sort_values('timestamp')

        zz_ts = tzz['timestamp'].values
        zz_type = tzz['tp_type'].values
        zz_price = tzz['price'].values

        snap_ts = tdf['timestamp'].values
        snap_close = tdf['close'].values
        snap_l3 = tdf['state_l3'].values
        snap_l2 = tdf['state_l2'].values
        snap_l1 = tdf['state_l1'].values
        snap_rl = tdf['run_length'].values

        # Vectorized searchsorted
        indices = np.searchsorted(zz_ts, snap_ts, side='right')
        valid_mask = indices < len(zz_ts)

        valid_snap_ts = snap_ts[valid_mask]
        valid_close = snap_close[valid_mask]
        valid_l3 = snap_l3[valid_mask]
        valid_l2 = snap_l2[valid_mask]
        valid_l1 = snap_l1[valid_mask]
        valid_rl = snap_rl[valid_mask]
        
        target_idx = indices[valid_mask]
        target_ts = zz_ts[target_idx]
        target_type = zz_type[target_idx]
        target_price = zz_price[target_idx]

        # Calculate exact days to pivot
        days_delta = ((target_ts - valid_snap_ts) / np.timedelta64(1, 'D')).astype(float)
        
        # Horizon Gate: filter out pivots beyond 120 days
        horizon_mask = (days_delta > 0) & (days_delta <= MAX_HORIZON_DAYS)

        h_valid_snap_ts = valid_snap_ts[horizon_mask]
        h_valid_close = valid_close[horizon_mask]
        h_valid_l3 = valid_l3[horizon_mask]
        h_valid_l2 = valid_l2[horizon_mask]
        h_valid_l1 = valid_l1[horizon_mask]
        h_valid_rl = valid_rl[horizon_mask]
        h_target_type = target_type[horizon_mask]
        h_target_price = target_price[horizon_mask]
        h_days_delta = days_delta[horizon_mask]

        if len(h_days_delta) == 0:
            continue

        real_returns = (h_target_price / h_valid_close) - 1.0
        speeds = real_returns / np.maximum(h_days_delta, 1.0)

        ticker_dfs.append(pd.DataFrame({
            'ticker': ticker,
            'timestamp': h_valid_snap_ts,
            'state_l3': h_valid_l3,
            'state_l2': h_valid_l2,
            'state_l1': h_valid_l1,
            'run_length': h_valid_rl,
            'next_type': h_target_type,
            'real_return': real_returns,
            'next_days': h_days_delta,
            'next_speed': speeds,
        }))

    if not ticker_dfs:
        return pd.DataFrame()
    return pd.concat(ticker_dfs, ignore_index=True)


# ═══════════════════════════════════════════════════════════════
# Metrics Summarizer
# ═══════════════════════════════════════════════════════════════

def summarize_df_level(sdf: pd.DataFrame) -> dict | None:
    """Summarize real return metrics and fatigue buckets for a subset of forward labels."""
    n = len(sdf)
    if n == 0:
        return None

    p_min = float((sdf['next_type'] == 'MIN').mean())
    p_max = float(1.0 - p_min)

    min_rets = sdf[sdf['next_type'] == 'MIN']['real_return']
    max_rets = sdf[sdf['next_type'] == 'MAX']['real_return']

    e_ret_min = float(min_rets.mean()) if len(min_rets) > 0 else 0.0
    e_ret_max = float(max_rets.mean()) if len(max_rets) > 0 else 0.0
    ev = p_min * e_ret_min + p_max * e_ret_max

    std_ret = float(sdf['real_return'].std()) if n > 1 else 0.0
    sharpe = float(ev / std_ret) if std_ret > 0 else 0.0
    e_days = float(sdf['next_days'].mean())
    e_speed = float(sdf['next_speed'].abs().mean())

    # Raw fatigue buckets
    fatigue_buckets = {}
    for lo, hi, label in RUN_BUCKETS:
        bdf = sdf[(sdf['run_length'] > lo) & (sdf['run_length'] <= hi)]
        bn = len(bdf)
        if bn < 5:
            continue
        bp_min = float((bdf['next_type'] == 'MIN').mean())
        bp_max = float(1.0 - bp_min)

        b_min_rets = bdf[bdf['next_type'] == 'MIN']['real_return']
        b_max_rets = bdf[bdf['next_type'] == 'MAX']['real_return']

        be_ret_min = float(b_min_rets.mean()) if len(b_min_rets) > 0 else 0.0
        be_ret_max = float(b_max_rets.mean()) if len(b_max_rets) > 0 else 0.0
        be_ev = bp_min * be_ret_min + bp_max * be_ret_max

        fatigue_buckets[label] = {
            "n": bn,
            "p_min": round(bp_min, 4),
            "p_max": round(bp_max, 4),
            "e_ret_min": round(be_ret_min, 6),
            "e_ret_max": round(be_ret_max, 6),
            "ev": round(be_ev, 6),
        }

    return {
        "n": n,
        "p_min": round(p_min, 4),
        "p_max": round(p_max, 4),
        "e_ret_min": round(e_ret_min, 6),
        "e_ret_max": round(e_ret_max, 6),
        "ev": round(ev, 6),
        "std_return": round(std_ret, 6),
        "sharpe": round(sharpe, 4),
        "e_days": round(e_days, 2),
        "e_speed": round(e_speed, 6),
        "fatigue_buckets": fatigue_buckets,
    }


# ═══════════════════════════════════════════════════════════════
# Main Training Workflow
# ═══════════════════════════════════════════════════════════════

def main():
    logger.info("Starting Real EV Probability Table Training (Horizon-Gated)...")
    store = TimescaleDataStore()
    
    snap_df, zigzags = load_all_data(store)

    # Precompute forward labels per level
    level_fwd = {}
    for level in ZIGZAG_LEVELS:
        lbl = ZIGZAG_LABEL[level]
        logger.info(f"Computing real point-in-time forward labels for {lbl} ({level*100:.1f}%)...")
        fwd_df = compute_real_forward_labels(snap_df, zigzags[level])
        level_fwd[lbl] = fwd_df
        logger.info(f"  Generated {len(fwd_df):,} valid horizon-gated forward labels for {lbl}")

    # Build L0 Global Baseline
    logger.info("Summarizing L0 (Global Baseline)...")
    l0_levels = {}
    for lbl in ZIGZAG_LABEL.values():
        res = summarize_df_level(level_fwd[lbl])
        if res:
            l0_levels[lbl] = res

    # Build L1 (Macro Tide) Rollups
    logger.info("Summarizing L1 (Macro Tide - 6 states)...")
    l1_states = {}
    all_l1_keys = sorted(snap_df['state_l1'].unique())
    for k1 in all_l1_keys:
        l1_levels = {}
        for lbl in ZIGZAG_LABEL.values():
            sdf = level_fwd[lbl][level_fwd[lbl]['state_l1'] == k1]
            res = summarize_df_level(sdf)
            if res:
                l1_levels[lbl] = res
        if l1_levels:
            l1_states[k1] = {"levels": l1_levels}

    # Build L2 (Mid-Macro Tide x Current) Rollups
    logger.info("Summarizing L2 (Mid-Macro Tide x Current - 36 states)...")
    l2_states = {}
    all_l2_keys = sorted(snap_df['state_l2'].unique())
    for k2 in all_l2_keys:
        l2_levels = {}
        for lbl in ZIGZAG_LABEL.values():
            sdf = level_fwd[lbl][level_fwd[lbl]['state_l2'] == k2]
            res = summarize_df_level(sdf)
            if res:
                l2_levels[lbl] = res
        if l2_levels:
            l2_states[k2] = {"levels": l2_levels}

    # Build L3 (Full 3D State)
    logger.info("Summarizing L3 (Full 3D State - 180 states)...")
    l3_states = {}
    all_l3_keys = sorted(snap_df['state_l3'].unique())
    for k3 in all_l3_keys:
        l3_levels = {}
        total_n = 0
        for lbl in ZIGZAG_LABEL.values():
            sdf = level_fwd[lbl][level_fwd[lbl]['state_l3'] == k3]
            res = summarize_df_level(sdf)
            if res:
                l3_levels[lbl] = res
                total_n = max(total_n, res["n"])
        if l3_levels:
            l3_states[k3] = {
                "n_total": total_n,
                "levels": l3_levels
            }

    _documentation = {
        "model_purpose": "Point-in-Time Real Expected Value (EV) Raw Probability Table for quality_swing",
        "return_formula": "Real Return = (Price(t_pivot_next) / Close(t)) - 1. Zero Ghost Return bias.",
        "horizon_gate": "Maximum horizon = 120 days. Eliminates truncated or missing future swings.",
        "state_hierarchy": {
            "L3": "Full 3D State: T_slope|C_slope|vwap_sigma_wave (180 granular micro/macro states)",
            "L2": "Mid-Macro State: T_slope|C_slope (36 mid-term trend states)",
            "L1": "Macro State: T_slope (6 macro tide trend states)",
            "L0": "Global Baseline: Aggregated market baseline across all observations"
        },
        "field_glossary": {
            "n": "Sample size for this state/level combination",
            "p_min": "P(next pivot = MIN). Empirical probability of next pivot being a low",
            "p_max": "P(next pivot = MAX). Empirical probability of next pivot being a high",
            "ev": "Real Expected Value: P(min)*E[ret_min] + P(max)*E[ret_max]",
            "e_ret_min": "Expected real drawdown % to next MIN pivot",
            "e_ret_max": "Expected real upside gain % to next MAX pivot",
            "std_return": "Standard deviation of real returns across observations",
            "sharpe": "Real EV / std_return. Risk-adjusted return ratio",
            "e_days": "Expected calendar days to next pivot",
            "e_speed": "Real return speed per calendar day",
            "fatigue_buckets": "Raw performance metrics grouped by run_length (1, 2, 3-4, 5-7, 8-10, 11+ bars)"
        },
        "rare_event_policy": "States with extreme deviation (vwap_sigma_wave = << or >>) represent mean-reversion spring stretch. Samples n >= 1 are preserved without artificial fallback degradation to maintain tail asymmetry."
    }

    # Assemble Output JSON
    output_data = {
        "version": "v2_ev_real_forward_2026-07-25",
        "model_type": "real_point_in_time_expected_value",
        "return_formula": "(price_pivot_next / close_bar_t) - 1",
        "max_horizon_days": MAX_HORIZON_DAYS,
        "dimensions": "T_slope|C_slope|sigma_vwap_wave",
        "n_states_l3": len(l3_states),
        "n_states_l2": len(l2_states),
        "n_states_l1": len(l1_states),
        "n_tickers": int(snap_df['ticker'].nunique()),
        "n_total_observations": len(snap_df),
        "_documentation": _documentation,
        "l0_global": {"levels": l0_levels},
        "l1_macro": l1_states,
        "l2_mid_macro": l2_states,
        "l3_states": l3_states,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output_data, f, indent=2)

    logger.info(f"🎉 Successfully generated {OUTPUT_PATH}")
    logger.info(f"   L3 States: {len(l3_states)} | L2 States: {len(l2_states)} | L1 States: {len(l1_states)}")


if __name__ == "__main__":
    main()
