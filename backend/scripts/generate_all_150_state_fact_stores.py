"""
Master Authoritative Generator with Bayesian Shrinkage & Minimum Sample Size Thresholds
========================================================================================
- Data Source: Neon Vault market.ohlcv_bars (Full historical SPY 1993-2026 & VIX 1990-2026)
- Gaussian Normal Sigma percentiles (-2σ, -1σ, μ, +1σ, +2σ)
- Independent 3-horizon expectations (zz25=1d, zz50=3d, zz75=5d)
- Bayesian Laplace Shrinkage (m=10) on probabilities and expected values to prevent N=1 noise
- Enforces N >= 10 minimum sample requirement for high-conviction signals
"""
import pandas as pd
import numpy as np
import json
import logging
from pathlib import Path

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BayesianFactStoreGenerator")

RULES_DIR = Path("backend/modules/entry_decision/domain/rules")

PERCENTILES_D1_GAUSS = [0.0228, 0.1587, 0.5000, 0.8413, 0.9772]
PERCENTILES_D2_GAUSS = [0.0228, 0.1587, 0.8413, 0.9772]
PERCENTILES_D3_GAUSS = [0.0228, 0.1587, 0.8413, 0.9772]

LABELS_D2_STANDARD = ["FAST_CRUSH_3D", "DECELERATING_DOWN_3D", "STABLE_CONTINUATION_3D", "ACCELERATING_UP_3D", "FAST_SPIKE_3D"]
LABELS_D3_STANDARD = ["VOL_EXTREME_SQUEEZE", "VOL_MODERATE_COMPRESSION", "VOL_NEUTRAL_BASELINE", "VOL_ACCELERATING_EXPANSION", "VOL_PEAK_DECELERATION"]

STATIONS_CONFIG = {
    "vix": {
        "ticker": "VIX",
        "labels_d1": ["DEEP_COMPLACENCY", "LOW_VOL", "MODERATE_VOL", "HIGH_VOL", "ELEVATED_PANIC", "CRISIS_SPIKE"]
    },
    "vvix": {
        "ticker": "VVIX",
        "labels_d1": ["EXTREME_COMPLACENCY", "LOW_VVIX", "MODERATE_VVIX", "HIGH_VVIX", "ELEVATED_VVIX", "EXTREME_VVIX"]
    },
    "pcr": {
        "ticker": "CBOE_PCR",
        "labels_d1": ["EXTREME_CALL_HEAVY", "BULLISH_PCR", "NEUTRAL_PCR", "ELEVATED_PCR", "HIGH_PUT_PANIC", "EXTREME_PUT_PANIC"]
    },
    "fg": {
        "ticker": "FG",
        "labels_d1": ["EXTREME_FEAR", "FEAR", "NEUTRAL_FEAR", "GREED", "EXTREME_GREED", "EUPHORIA"]
    },
    "sv5_turbulence": {
        "ticker": "SV5_TURBULENCE",
        "labels_d1": ["QUIET_FLOW", "LOW_TURBULENCE", "MODERATE_TURBULENCE", "HIGH_TURBULENCE", "ELEVATED_TURBULENCE", "CRISIS_TURBULENCE"]
    },
    "skew": {
        "ticker": "SKEW",
        "labels_d1": ["LOW_TAIL_RISK", "NORMAL_TAIL_RISK", "ELEVATED_TAIL_RISK", "HIGH_TAIL_RISK", "TAIL_PARANOIA", "BLACK_SWAN_PARANOIA"]
    },
    "credit": {
        "ticker": "CREDIT_RATIO",
        "labels_d1": ["CREDIT_CRISIS", "CREDIT_STRESS", "ELEVATED_CREDIT_STRESS", "STABLE_CREDIT", "CREDIT_EASE", "DEEP_CREDIT_EASE"]
    },
    "yield_curve": {
        "ticker": "YIELD_SPREAD",
        "labels_d1": ["DEEP_INVERSION", "MODERATE_INVERSION", "FLAT_CURVE", "NORMAL_CURVE", "STEEPNING_CURVE", "EXTREME_STEEPNING"]
    },
    "rotation": {
        "ticker": "ROTATION_INDEX",
        "labels_d1": ["DEFENSIVE_CAPITULATION", "DEFENSIVE", "NEUTRAL_ROTATION", "BALANCED", "CYCLICAL_LEADERSHIP", "AGGRESSIVE_ROTATION"]
    },
    "bsi": {
        "ticker": "S5TW",
        "labels_d1": ["BREADTH_WASHED_OUT", "OVERSOLD_BREADTH", "NEUTRAL_LOW_BREADTH", "NEUTRAL_HIGH_BREADTH", "EXPANSIVE_BREADTH", "HYPER_EXPANSIVE_BREADTH"]
    }
}

PRIORS_BY_HORIZON = {
    "fwd_1d": {"p_bull": 0.535, "ev_net": 0.0004, "days": 1.0},
    "fwd_3d": {"p_bull": 0.550, "ev_net": 0.0012, "days": 3.0},
    "fwd_5d": {"p_bull": 0.565, "ev_net": 0.0020, "days": 5.0}
}

def classify_value(val: float, edges: list, labels: list) -> str:
    if pd.isna(val):
        return labels[2]
    for i, edge in enumerate(edges):
        if val < edge:
            return labels[i]
    return labels[-1]

def compute_bayesian_scale_metrics(sub: pd.DataFrame, fwd_col: str, m_weight: float = 10.0):
    prior = PRIORS_BY_HORIZON[fwd_col]
    days = prior["days"]
    p0 = prior["p_bull"]
    ev0 = prior["ev_net"]
    
    sub_valid = sub.dropna(subset=[fwd_col])
    n_tot = len(sub_valid)
    
    if n_tot == 0:
        return {"n_raw": 0, "p_bull": p0, "p_bear": 1.0 - p0, "e_ret_max": 0.015, "e_ret_min": -0.015, "ev_net": ev0, "e_days": days, "ev_per_day": ev0 / days, "rr_asymmetry": 1.0}
    
    returns = sub_valid[fwd_col].values
    n_pos = int(np.sum(returns > 0))
    
    # Bayesian Laplace Shrinkage for Probability
    p_bayesian = float((n_pos + m_weight * p0) / (n_tot + m_weight))
    p_bear = float(1.0 - p_bayesian)
    
    # Empirical vs Bayesian Shrunk EV
    ev_sample = float(np.mean(returns))
    credibility = float(n_tot / (n_tot + m_weight))
    ev_shrunk = float(credibility * ev_sample + (1.0 - credibility) * ev0)
    
    pos_rets = returns[returns > 0]
    neg_rets = returns[returns < 0]
    e_ret_max = float(np.mean(pos_rets)) if len(pos_rets) > 0 else 0.015
    e_ret_min = float(np.mean(neg_rets)) if len(neg_rets) > 0 else -0.015
    rr_asym = float(abs(e_ret_max / e_ret_min)) if abs(e_ret_min) > 1e-6 else 1.0
    
    return {
        "n_raw": n_tot,
        "p_bull": p_bayesian,
        "p_bear": p_bear,
        "e_ret_max": e_ret_max,
        "e_ret_min": e_ret_min,
        "ev_net": ev_shrunk,
        "e_days": days,
        "ev_per_day": float(ev_shrunk / days),
        "rr_asymmetry": rr_asym
    }

def determine_guidance_and_regime(zz25: dict, zz50: dict, zz75: dict, d1: str, n_state: int):
    ev_1d = zz25["ev_net"]
    ev_3d = zz50["ev_net"]
    ev_5d = zz75["ev_net"]
    
    pb_1d = zz25["p_bull"]
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
        
    # Strict Minimum Sample Rule: If N < 10, cannot issue MAX_CONVICTION
    if composite_ev <= -0.008 or pb_3d <= 0.42 or "CRISIS" in d1 or "PARANOIA" in d1:
        guidance = "STK_BLOCK_CRISIS"
    elif composite_ev >= 0.008 and pb_3d >= 0.58 and n_state >= 10:
        guidance = "STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION"
    elif composite_ev >= 0.003 and pb_3d >= 0.52:
        guidance = "STK_BUY_DIP_TACTICAL"
    elif composite_ev <= -0.003:
        guidance = "STK_TRIM_TACTICAL"
    else:
        guidance = "STK_HOLD_STABLE"
        
    return guidance, divergence_regime

def generate_all():
    store = TimescaleDataStore()
    df_spy = store.load_bars("SPY", "1d")[['close']].sort_index()
    df_spy['date_str'] = df_spy.index.strftime("%Y-%m-%d")
    df_spy['fwd_1d'] = df_spy['close'].pct_change(1).shift(-1)
    df_spy['fwd_3d'] = df_spy['close'].pct_change(3).shift(-3)
    df_spy['fwd_5d'] = df_spy['close'].pct_change(5).shift(-5)

    for name, cfg in STATIONS_CONFIG.items():
        logger.info(f"=== Generating Bayesian Fact Store: {name.upper()} ===")
        ticker = cfg["ticker"]
        if ticker == "CREDIT_RATIO":
            df_hyg = store.load_bars("HYG", "1d")
            df_lqd = store.load_bars("LQD", "1d")
            if df_hyg is not None and df_lqd is not None and not df_hyg.empty and not df_lqd.empty:
                series = (df_hyg['close'] / df_lqd['close']).dropna()
            else:
                df = store.load_bars(ticker, "1d")
                if df is None or df.empty: continue
                series = df['close'].dropna()
        else:
            df = store.load_bars(ticker, "1d")
            if df is None or df.empty: continue
            series = df['close'].dropna()

        df_ind = pd.DataFrame({"val": series})
        df_ind.sort_index(inplace=True)
        df_ind['date_str'] = df_ind.index.strftime("%Y-%m-%d")

        df_ind['d2_velocity'] = df_ind['val'].diff(3)  # D2: 72h kinematic velocity
        
        vol_2d = df_ind['val'].rolling(2).std()
        vol_10d = df_ind['val'].rolling(10).std().replace(0, np.nan)
        df_ind['vol_norm'] = (vol_2d / vol_10d).fillna(1.0)

        d1_labels = cfg["labels_d1"]
        # D1 edges from full population — stored in JSON for runtime lookup adapters
        d1_edges = [float(x) for x in df_ind['val'].quantile(PERCENTILES_D1_GAUSS)]
        d2_edges = [float(x) for x in df_ind['d2_velocity'].dropna().quantile(PERCENTILES_D2_GAUSS)]
        d3_vol_edges = [float(x) for x in df_ind['vol_norm'].dropna().quantile(PERCENTILES_D3_GAUSS)]

        # D1: EXPANDING WINDOW RANK (no look-ahead bias)
        # Each observation is ranked against only data available up to that point
        d1_expanding_rank = df_ind['val'].expanding(min_periods=252).rank(pct=True)
        # Map expanding rank to Gaussian sigma bins: [-2σ, -1σ, μ, +1σ, +2σ]
        d1_rank_edges = PERCENTILES_D1_GAUSS  # [0.0228, 0.1587, 0.5000, 0.8413, 0.9772]
        df_ind['bin_d1'] = d1_expanding_rank.apply(
            lambda r: classify_value(r, d1_rank_edges, d1_labels) if pd.notna(r) else d1_labels[2]
        )
        df_ind['bin_d2'] = df_ind['d2_velocity'].apply(lambda v: classify_value(v, d2_edges, LABELS_D2_STANDARD))
        df_ind['bin_d3'] = df_ind['vol_norm'].apply(lambda v: classify_value(v, d3_vol_edges, LABELS_D3_STANDARD))

        df_ind['state_key'] = df_ind['bin_d1'] + "__" + df_ind['bin_d2'] + "__" + df_ind['bin_d3']

        df_merged = pd.merge(df_ind, df_spy[['date_str', 'fwd_1d', 'fwd_3d', 'fwd_5d']], on='date_str', how='inner')

        states = {}
        grouped = df_merged.groupby('state_key')

        for state_k, sub in grouped:
            n_state = len(sub)
            val_stats = sub['val'].values
            d1_cat = sub['bin_d1'].iloc[0]

            zz25 = compute_bayesian_scale_metrics(sub, 'fwd_1d', m_weight=10.0)
            zz50 = compute_bayesian_scale_metrics(sub, 'fwd_3d', m_weight=10.0)
            zz75 = compute_bayesian_scale_metrics(sub, 'fwd_5d', m_weight=10.0)

            guidance, divergence_regime = determine_guidance_and_regime(zz25, zz50, zz75, d1_cat, n_state)

            state_doc = {
                "n": int(n_state),
                "stats": {
                    "min": float(np.min(val_stats)),
                    "max": float(np.max(val_stats)),
                    "mean": float(np.mean(val_stats)),
                    "std": float(np.std(val_stats)) if n_state > 1 else 0.0
                },
                "divergence_regime": divergence_regime,
                "operational_guidance": guidance,
                "zz25": zz25,
                "zz50": zz50,
                "zz75": zz75
            }
            states[state_k] = state_doc

        doc = {
            "_documentation": {
                "model_purpose": f"Authoritative Bayesian 150-State Fact Store for {name.upper()} with Laplace Shrinkage (m=10) and N>=10 thresholds.",
                "return_formula": "R_fwd = (Close_{t+k} - Close_t) / Close_t for k in [1, 3, 5]",
                "bayesian_smoothing": "P_smooth = (n_pos + 10*P_prior) / (N + 10)",
                "state_hierarchy": "L0=Station -> L1=D1(Absolute Level) -> L2=D2(Velocity 72h) -> L3=D3(Vol Magnitude)",
                "dimension_thresholds_definition": {
                    "d1_edges_gauss_sigma": d1_edges,
                    "d2_edges_gauss_sigma": d2_edges,
                    "d3_vol_edges_gauss_sigma": d3_vol_edges
                },
                "field_glossary": {
                    "n": "Sample count of daily bars in state",
                    "p_bull": "Bayesian smoothed probability of positive return",
                    "ev_net": "Bayesian shrunk mean forward return",
                    "rr_asymmetry": "|Mean positive return / Mean negative return|",
                    "divergence_regime": "FULL_CONVERGENT_BULL | FULL_CONVERGENT_BEAR | TACTICAL_REBOUND_IN_BEAR | STRUCTURAL_BULL_PULLBACK"
                },
                "signal_interpretation_policy": "Clean Architecture Standard: pure domain rules iterate over states and emit universal 4D action taxonomy."
            },
            "station": name.upper(),
            "sample_size": len(df_merged),
            "states_populated": len(states),
            "states": states
        }

        out_path = RULES_DIR / f"{name}_fact_store.json"
        with open(out_path, "w", encoding="utf-8") as fp:
            json.dump(doc, fp, indent=2)
        logger.info(f"✅ Retrained and saved {name}_fact_store.json with Bayesian Shrinkage ({len(states)} states)")

if __name__ == "__main__":
    generate_all()
