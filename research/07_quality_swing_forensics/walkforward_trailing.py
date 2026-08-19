#!/usr/bin/env python3
"""
WALK-FORWARD OOS — Cascade Conviction con edges trailing 3 años
================================================================
Compara cascade OOS nuevo (post-regeneración fact stores con tail(756))
vs viejo (+0.348).

MÉTODO (replica decay_check_cascade_conviction.py):
1. d1_bear_5: fracción de votos bajistas (bearish) de estaciones activas.
   Votes vienen de d1_directional_vote(state_key) para cada estación.
2. Z-scores: (d1_bear_5 - μ_train) / σ_train + w_dom × (|prev_leg_return| - μ_dom) / σ_dom
3. Cascades: cascade_50 (zz25→zz50 ±3d), cascade_50to75 (zz50→zz75 ±3d)
4. 26 folds expanding window, refit de μ/σ en cada fold sobre training data.
5. Reporta: IC medio (Spearman), % folds positivos, CI95 bootstrap.

Script: research/07_quality_swing_forensics/walkforward_trailing.py
NO modifica código de producción.
"""
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import timedelta
from scipy.stats import spearmanr

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import (
    STATION_CONFIG, d1_directional_vote, GRUPO_A_PREDICTORS, CALIBRATION_FILE,
)

# ── Load fixed weights from calibration (type_mask) ──────────────────────
with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
    calibration = json.load(f)

type_mask_cfg = calibration.get("type_mask", {})

# ── Load data ────────────────────────────────────────────────────────────
print("═" * 74)
print("CARGANDO DATOS — TimescaleDataStore + ZigzagLegRepository")
print("═" * 74)

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

legs25 = repo.get_confirmed_legs("SPY", "zz25")
legs50 = repo.get_confirmed_legs("SPY", "zz50")
legs75 = repo.get_confirmed_legs("SPY", "zz75")

starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)
starts75 = set(pd.to_datetime(l.start_timestamp).date() for l in legs75)

# ── Build zz25 DataFrame with cascade labels ─────────────────────────────
df25 = pd.DataFrame([
    {"start_timestamp": l.start_timestamp, "start_type": l.start_type,
     "prev_leg_return": l.prev_leg_return} for l in legs25
]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["abs_prev_leg_return"] = df25["prev_leg_return"].abs()
df25["cascade_50"] = df25["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts50 for i in range(-3, 4)))
)
df25["cascade_75"] = df25["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts75 for i in range(-3, 4)))
)

# ── Build zz50 DataFrame with cascade_50to75 label ────────────────────────
df50_legs = pd.DataFrame([
    {"start_timestamp": pd.to_datetime(l.start_timestamp), "prev_leg_return_zz50": l.prev_leg_return}
    for l in legs50
]).dropna().sort_values("start_timestamp").reset_index(drop=True)
df50_legs["abs_prev_leg_return_zz50"] = df50_legs["prev_leg_return_zz50"].abs()

df25_sorted = df25.sort_values("start_timestamp").copy()
df25_sorted["ts"] = pd.to_datetime(df25_sorted["start_timestamp"])
df50_sorted = df50_legs.sort_values("start_timestamp").copy()
df50_sorted["ts"] = pd.to_datetime(df50_sorted["start_timestamp"])

df25_merged = pd.merge_asof(
    df25_sorted,
    df50_sorted[["ts", "abs_prev_leg_return_zz50"]],
    on="ts", direction="backward"
)

df50 = pd.DataFrame([
    {"start_timestamp": l.start_timestamp, "start_type": l.start_type,
     "prev_leg_return": l.prev_leg_return} for l in legs50
]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df50["pivot_date"] = pd.to_datetime(df50["start_timestamp"]).dt.date
df50["abs_prev_leg_return"] = df50["prev_leg_return"].abs()
df50["cascade_50to75"] = df50["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts75 for i in range(-3, 4)))
)

# ── Load indicator series ────────────────────────────────────────────────
indicator_series = {}
for code, cfg in STATION_CONFIG.items():
    df_ind = store.load_bars(cfg["ticker"], "1d")
    if df_ind is not None and not df_ind.empty:
        s = df_ind["close"].copy()
        s.index = [d.date() if hasattr(d, 'date') else d for d in pd.to_datetime(s.index)]
        indicator_series[code] = s

all_dates = set()
for s in indicator_series.values():
    all_dates.update(s.index)
date_features = pd.DataFrame(index=sorted(all_dates))
for code, s in indicator_series.items():
    vel = s.diff(3)
    std_2, std_10 = s.rolling(2).std(), s.rolling(10).std()
    vol = (std_2 / std_10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    date_features[f"{code}_val"] = s
    date_features[f"{code}_vel"] = vel
    date_features[f"{code}_vol"] = vol

adapters = {code: cfg["adapter_cls"]() for code, cfg in STATION_CONFIG.items()}
store.close()

print(f"  zz25 pivots: {len(df25_merged)}")
print(f"  zz50 pivots: {len(df50)}")
print(f"  cascade_50 prevalence: {df25_merged['cascade_50'].mean():.2%}")
print(f"  cascade_75 prevalence: {df25_merged['cascade_75'].mean():.2%}")
print(f"  cascade_50to75 prevalence: {df50['cascade_50to75'].mean():.2%}")

# ── Build observation matrices (point-in-time features, same as decay_check) ──
def build_obs(pivots_df, merge_asof_col=None):
    """Build observation records with d1_bear_5 and domino features.
    EXACT replica of decay_check's build_obs_df()."""
    obs = []
    for _, row in pivots_df.iterrows():
        pd_ = row["pivot_date"]
        if pd_ not in date_features.index:
            continue
        feats = date_features.loc[pd_]

        votes = {}
        for code, adapter in adapters.items():
            val = feats.get(f"{code}_val")
            vel = feats.get(f"{code}_vel", 0.0)
            vol = feats.get(f"{code}_vol", 1.0)
            if pd.isna(val):
                continue
            if pd.isna(vel):
                vel = 0.0
            if pd.isna(vol):
                vol = 1.0
            try:
                method_name = STATION_CONFIG[code]["method"]
                lookup_fn = getattr(adapter, method_name)
                res = lookup_fn(val=float(val), d3_speed=float(vel),
                                vol_norm=float(vol), vol_d3=float(vol))
                if res and res.state_key:
                    votes[code] = d1_directional_vote(res.state_key)
            except Exception:
                continue

        p_type = row.get("start_type", "MIN")
        type_cfg = type_mask_cfg.get(p_type, {
            "w_bear": 0.66, "w_dom": 0.34,
            "w_bear_c75": 0.50, "w_dom_c75": 0.50,
            "stations": ["vix", "bsi", "fg", "credit", "rotation"]
            if p_type == "MIN"
            else ["vix", "bsi", "credit", "rotation"],
        })
        allowed = set(type_cfg.get("stations", GRUPO_A_PREDICTORS))
        m_votes = [v for c, v in votes.items() if c in allowed]
        if not m_votes:
            continue

        # Fractional bear counting
        m_bear = sum(-v for v in m_votes if v < 0)

        rec = {
            "pivot_date": pd_,
            "pivot_type": p_type,
            "abs_prev_leg_return": row["abs_prev_leg_return"],
            "d1_bear_5": m_bear / len(m_votes),
            "w_bear": float(type_cfg.get("w_bear", 0.66)),
            "w_dom": float(type_cfg.get("w_dom", 0.34)),
            "w_bear_c75": float(type_cfg.get("w_bear_c75", 0.50)),
            "w_dom_c75": float(type_cfg.get("w_dom_c75", 0.50)),
        }
        if "abs_prev_leg_return_zz50" in row:
            rec["abs_prev_leg_return_zz50"] = row["abs_prev_leg_return_zz50"]
        for col in ["cascade_50", "cascade_75", "cascade_50to75"]:
            if col in row:
                rec[col] = row[col]
        obs.append(rec)
    return pd.DataFrame(obs)


df_obs_25 = build_obs(df25_merged)
df_obs_50 = build_obs(df50)
df_obs_25 = df_obs_25.sort_values("pivot_date").reset_index(drop=True)
df_obs_50 = df_obs_50.sort_values("pivot_date").reset_index(drop=True)

print(f"\n  Observaciones zz25: {len(df_obs_25)}")
print(f"  Observaciones zz50: {len(df_obs_50)}")

# ── WALK-FORWARD OOS — 26 folds expanding window ────────────────────────
print("\n" + "═" * 74)
print("WALK-FORWARD OOS — 26 folds expanding window (refit μ/σ en training)")
print("═" * 74)

N_FOLDS = 26


def compute_ic(score, target):
    """Spearman IC between score and target."""
    valid = ~np.isnan(score) & ~np.isnan(target)
    s, t = score[valid], target[valid]
    if len(s) < 10 or np.std(s) == 0 or np.std(t) == 0:
        return np.nan
    ic, _ = spearmanr(s, t)
    return float(ic) if not np.isnan(ic) else np.nan


def walkforward_cascade(obs_df, cascade_col, score_fn):
    """
    Expanding-window walk-forward with refit of μ/σ on training data.
    
    score_fn(train_df, test_df) → (test_scores, test_targets)
    """
    n = len(obs_df)
    fold_size = max(n // N_FOLDS, 1)
    fold_ics = []
    fold_details = []

    for i in range(1, N_FOLDS):
        split_idx = i * fold_size
        if split_idx >= n - fold_size:
            break

        train = obs_df.iloc[:split_idx]
        test = obs_df.iloc[split_idx:split_idx + fold_size]

        if len(train) < 30 or len(test) < 10:
            continue

        test_scores, test_targets, fold_n = score_fn(train, test, cascade_col)
        if fold_n < 10:
            continue

        ic_val = compute_ic(test_scores, test_targets)
        if not np.isnan(ic_val):
            fold_ics.append(ic_val)
            fold_details.append({
                "fold": i,
                "train_n": len(train),
                "test_n": fold_n,
                "ic": ic_val,
                "train_start": train["pivot_date"].iloc[0],
                "train_end": train["pivot_date"].iloc[-1],
                "test_start": test["pivot_date"].iloc[0],
                "test_end": test["pivot_date"].iloc[-1],
            })

    return fold_ics, fold_details


def cascade_score_fn(train, test, cascade_col):
    """
    Compute cascade_conviction scores OOS:
    1. Refit μ/σ on training data
    2. Apply to test data
    Returns (scores, targets, n_valid)
    """
    # Refit d1_bear_5 params on training (shared across all cascades)
    d1_train = train["d1_bear_5"].dropna()
    if len(d1_train) < 10:
        return np.array([]), np.array([]), 0
    d1_mean = d1_train.mean()
    d1_std = d1_train.std()
    if d1_std == 0:
        return np.array([]), np.array([]), 0

    # Domino column + params depend on the cascade target
    if cascade_col == "cascade_50":
        dom_col = "abs_prev_leg_return"
    elif cascade_col == "cascade_75":
        dom_col = "abs_prev_leg_return_zz50"
    elif cascade_col == "cascade_50to75":
        dom_col = "abs_prev_leg_return"
    else:
        return np.array([]), np.array([]), 0

    if dom_col not in train.columns:
        return np.array([]), np.array([]), 0
    dom_train = train[dom_col].dropna()
    if len(dom_train) < 10:
        return np.array([]), np.array([]), 0
    dom_mean = dom_train.mean()
    dom_std = dom_train.std()
    if dom_std == 0:
        return np.array([]), np.array([]), 0

    # Apply to test
    test_d1 = test["d1_bear_5"].values.astype(float)
    test_dom = test[dom_col].values.astype(float)

    valid = ~np.isnan(test_d1) & ~np.isnan(test_dom)
    if valid.sum() < 10:
        return np.array([]), np.array([]), 0

    z_bear = (test_d1[valid] - d1_mean) / d1_std
    z_dom = (test_dom[valid] - dom_mean) / dom_std

    if cascade_col == "cascade_50":
        w_bear = test["w_bear"].values[valid]
        w_dom = test["w_dom"].values[valid]
        scores = w_bear * z_bear + w_dom * z_dom
    elif cascade_col == "cascade_75":
        w_bear_c75 = test["w_bear_c75"].values[valid]
        w_dom_c75 = test["w_dom_c75"].values[valid]
        scores = w_bear_c75 * z_bear + w_dom_c75 * z_dom
    elif cascade_col == "cascade_50to75":
        # Fixed weights 0.15/0.85 from decay_check
        scores = 0.15 * z_bear + 0.85 * z_dom
    else:
        return np.array([]), np.array([]), 0

    targets = test[cascade_col].values[valid].astype(float)
    return scores, targets, valid.sum()


def cascade_score_fn_fixed(train, test, cascade_col):
    """
    Fixed-params variant: use the μ/σ from cascade_calibration.json
    (full-sample calibration, NO per-fold refit). This mirrors decay_check
    exactly (which reads d1_mean/d1_std/dom*_mean/dom*_std from the JSON).
    Reported for methodological completeness — this leaks full-sample info
    into the z-scores, so it is NOT a strict OOS measure.
    """
    d1_mean = calibration.get("d1_bear_5", {}).get("mean", 0.5588)
    d1_std = calibration.get("d1_bear_5", {}).get("std", 0.3035)
    dom25_mean = calibration.get("domino_zz25", {}).get("mean", 0.0532)
    dom25_std = calibration.get("domino_zz25", {}).get("std", 0.035)
    dom50_mean = calibration.get("domino_zz50", {}).get("mean", 0.1003)
    dom50_std = calibration.get("domino_zz50", {}).get("std", 0.0643)

    if cascade_col == "cascade_50":
        dom_col = "abs_prev_leg_return"
        dom_mean, dom_std = dom25_mean, dom25_std
    elif cascade_col == "cascade_75":
        dom_col = "abs_prev_leg_return_zz50"
        dom_mean, dom_std = dom50_mean, dom50_std
    elif cascade_col == "cascade_50to75":
        dom_col = "abs_prev_leg_return"
        dom_mean, dom_std = dom50_mean, dom50_std
    else:
        return np.array([]), np.array([]), 0

    if dom_col not in test.columns or d1_std == 0 or dom_std == 0:
        return np.array([]), np.array([]), 0

    test_d1 = test["d1_bear_5"].values.astype(float)
    test_dom = test[dom_col].values.astype(float)
    valid = ~np.isnan(test_d1) & ~np.isnan(test_dom)
    if valid.sum() < 10:
        return np.array([]), np.array([]), 0

    z_bear = (test_d1[valid] - d1_mean) / d1_std
    z_dom = (test_dom[valid] - dom_mean) / dom_std

    if cascade_col == "cascade_50":
        w_bear = test["w_bear"].values[valid]
        w_dom = test["w_dom"].values[valid]
        scores = w_bear * z_bear + w_dom * z_dom
    elif cascade_col == "cascade_75":
        w_bear_c75 = test["w_bear_c75"].values[valid]
        w_dom_c75 = test["w_dom_c75"].values[valid]
        scores = w_bear_c75 * z_bear + w_dom_c75 * z_dom
    else:  # cascade_50to75
        scores = 0.15 * z_bear + 0.85 * z_dom

    targets = test[cascade_col].values[valid].astype(float)
    return scores, targets, valid.sum()


# ── Run walk-forward for all three cascade targets ────────────────────────
print("\n" + "─" * 74)
print("CASCADE 50 — zz25 pivots predicting zz50 cascade (±3d)")
print("─" * 74)

c50_ics, c50_details = walkforward_cascade(df_obs_25, "cascade_50", cascade_score_fn)
c50_ics = np.array([v for v in c50_ics if not np.isnan(v)])

print(f"  Folds válidos: {len(c50_ics)}/{N_FOLDS - 1}")
if len(c50_ics) > 0:
    print(f"  OOS IC mean:   {np.mean(c50_ics):+.4f}")
    print(f"  OOS IC median: {np.median(c50_ics):+.4f}")
    print(f"  OOS IC std:    {np.std(c50_ics):.4f}")
    print(f"  Folds > 0:     {np.sum(c50_ics > 0)}/{len(c50_ics)} ({np.mean(c50_ics > 0) * 100:.0f}%)")
    print(f"  IC min / max:  {np.min(c50_ics):+.4f} / {np.max(c50_ics):+.4f}")

    rng = np.random.default_rng(42)
    bs_means = [np.mean(rng.choice(c50_ics, size=len(c50_ics), replace=True))
                for _ in range(2000)]
    ci = np.percentile(bs_means, [2.5, 97.5])
    print(f"  Bootstrap CI95: [{ci[0]:+.4f}, {ci[1]:+.4f}]")
else:
    print("  ⚠ No valid folds!")

print("\n" + "─" * 74)
print("CASCADE 75 — zz25 pivots predicting zz75 cascade (±3d)")
print("─" * 74)

c75_ics, c75_details = walkforward_cascade(df_obs_25, "cascade_75", cascade_score_fn)
c75_ics = np.array([v for v in c75_ics if not np.isnan(v)])

print(f"  Folds válidos: {len(c75_ics)}/{N_FOLDS - 1}")
if len(c75_ics) > 0:
    print(f"  OOS IC mean:   {np.mean(c75_ics):+.4f}")
    print(f"  OOS IC median: {np.median(c75_ics):+.4f}")
    print(f"  OOS IC std:    {np.std(c75_ics):.4f}")
    print(f"  Folds > 0:     {np.sum(c75_ics > 0)}/{len(c75_ics)} ({np.mean(c75_ics > 0) * 100:.0f}%)")
    print(f"  IC min / max:  {np.min(c75_ics):+.4f} / {np.max(c75_ics):+.4f}")

    rng = np.random.default_rng(43)
    bs_means = [np.mean(rng.choice(c75_ics, size=len(c75_ics), replace=True))
                for _ in range(2000)]
    ci = np.percentile(bs_means, [2.5, 97.5])
    print(f"  Bootstrap CI95: [{ci[0]:+.4f}, {ci[1]:+.4f}]")

print("\n" + "─" * 74)
print("CASCADE 50→75 — zz50 pivots predicting zz75 cascade (±3d)")
print("─" * 74)

c50to75_ics, c50to75_details = walkforward_cascade(df_obs_50, "cascade_50to75", cascade_score_fn)
c50to75_ics = np.array([v for v in c50to75_ics if not np.isnan(v)])

print(f"  Folds válidos: {len(c50to75_ics)}/{N_FOLDS - 1}")
if len(c50to75_ics) > 0:
    print(f"  OOS IC mean:   {np.mean(c50to75_ics):+.4f}")
    print(f"  OOS IC median: {np.median(c50to75_ics):+.4f}")
    print(f"  OOS IC std:    {np.std(c50to75_ics):.4f}")
    print(f"  Folds > 0:     {np.sum(c50to75_ics > 0)}/{len(c50to75_ics)} ({np.mean(c50to75_ics > 0) * 100:.0f}%)")
    print(f"  IC min / max:  {np.min(c50to75_ics):+.4f} / {np.max(c50to75_ics):+.4f}")

    rng = np.random.default_rng(44)
    bs_means = [np.mean(rng.choice(c50to75_ics, size=len(c50to75_ics), replace=True))
                for _ in range(2000)]
    ci = np.percentile(bs_means, [2.5, 97.5])
    print(f"  Bootstrap CI95: [{ci[0]:+.4f}, {ci[1]:+.4f}]")

# ── Also compute in-sample IC for comparison (full data, same as decay_check) ──
print("\n" + "═" * 74)
print("IN-SAMPLE IC (full dataset, misma fórmula decay_check)")
print("═" * 74)

if len(df_obs_25) > 0:
    d1_mean_is = df_obs_25["d1_bear_5"].mean()
    d1_std_is = df_obs_25["d1_bear_5"].std()
    dom25_mean_is = df_obs_25["abs_prev_leg_return"].mean()
    dom25_std_is = df_obs_25["abs_prev_leg_return"].std()
    dom50_mean_is = df_obs_25["abs_prev_leg_return_zz50"].mean()
    dom50_std_is = df_obs_25["abs_prev_leg_return_zz50"].std()

    z_bear_is = (df_obs_25["d1_bear_5"] - d1_mean_is) / d1_std_is
    z_dom25_is = (df_obs_25["abs_prev_leg_return"] - dom25_mean_is) / dom25_std_is
    z_dom50_is = (df_obs_25["abs_prev_leg_return_zz50"] - dom50_mean_is) / dom50_std_is

    c50_is = df_obs_25["w_bear"] * z_bear_is + df_obs_25["w_dom"] * z_dom25_is
    c75_is = df_obs_25["w_bear_c75"] * z_bear_is + df_obs_25["w_dom_c75"] * z_dom50_is

    ic50_is = compute_ic(c50_is.values, df_obs_25["cascade_50"].values)
    ic75_is = compute_ic(c75_is.values, df_obs_25["cascade_75"].values)
    print(f"  cascade_50 IS IC:     {ic50_is:+.4f}")
    print(f"  cascade_75 IS IC:     {ic75_is:+.4f}")

if len(df_obs_50) > 0:
    d1_mean_50_is = df_obs_50["d1_bear_5"].mean()
    d1_std_50_is = df_obs_50["d1_bear_5"].std()
    dom50m_is = df_obs_50["abs_prev_leg_return"].mean()
    dom50s_is = df_obs_50["abs_prev_leg_return"].std()

    z_bear_50_is = (df_obs_50["d1_bear_5"] - d1_mean_50_is) / d1_std_50_is
    z_dom50_is2 = (df_obs_50["abs_prev_leg_return"] - dom50m_is) / dom50s_is
    c50to75_is = 0.15 * z_bear_50_is + 0.85 * z_dom50_is2

    ic50to75_is = compute_ic(c50to75_is.values, df_obs_50["cascade_50to75"].values)
    print(f"  cascade_50to75 IS IC: {ic50to75_is:+.4f}")

# ── COMPARACIÓN vs viejo OOS ──────────────────────────────────────────────
print("\n" + "═" * 74)
print("COMPARACIÓN OOS NUEVO (trailing 3 años) vs VIEJO (+0.348)")
print("═" * 74)

VIEJO_OOS = 0.348  # Old OOS IC (referencia)

if len(c50_ics) > 0:
    nuevo_mean = np.mean(c50_ics)
    delta = nuevo_mean - VIEJO_OOS
    pct_change = (delta / abs(VIEJO_OOS)) * 100 if VIEJO_OOS != 0 else 0
    direction = "MEJORA" if delta > 0 else "DEGRADA"
    print(f"  cascade_50 OOS nuevo:  {nuevo_mean:+.4f}")
    print(f"  cascade_50 OOS viejo:  {VIEJO_OOS:+.4f}")
    print(f"  Δ (nuevo − viejo):     {delta:+.4f}  ({pct_change:+.1f}%)")
    print(f"  Dirección:             {direction}")
    print(f"  Conclusión:            {'✅ NUEVOS EDGES MEJORES' if delta > 0 else '⚠ NUEVOS EDGES PEORES'}")

    # Also report fold-level comparison
    print(f"\n  Folds positivos nuevo: {np.sum(c50_ics > 0)}/{len(c50_ics)} ({np.mean(c50_ics > 0) * 100:.0f}%)")
    print(f"  Folds positivos viejo: ~96% (reportado)")

    # Detailed fold-by-fold breakdown
    print(f"\n  Desglose por fold (cascade_50):")
    print(f"  {'Fold':>5s} {'Train N':>8s} {'Test N':>7s} {'IC':>8s} {'Train Range':>24s} {'Test Range':>24s}")
    print(f"  {'─' * 5} {'─' * 8} {'─' * 7} {'─' * 8} {'─' * 24} {'─' * 24}")
    for d in c50_details:
        print(f"  {d['fold']:>5d} {d['train_n']:>8d} {d['test_n']:>7d} {d['ic']:>+8.4f} "
              f"{str(d['train_start']):>24s} {str(d['test_start']):>24s}")

# ── FIXED-PARAMS variant (espejo decay_check: μ/σ fijos del JSON) ─────────
print("\n" + "═" * 74)
print("WALK-FORWARD OOS — VARIANTE PARÁMETROS FIJOS (μ/σ del calibration JSON)")
print("  (No es OOS estricto: los μ/σ filtran info full-sample a los z-scores)")
print("═" * 74)

for label, obs_df, col in [("cascade_50", df_obs_25, "cascade_50"),
                           ("cascade_75", df_obs_25, "cascade_75"),
                           ("cascade_50to75", df_obs_50, "cascade_50to75")]:
    ics, _ = walkforward_cascade(obs_df, col, cascade_score_fn_fixed)
    ics = np.array([v for v in ics if not np.isnan(v)])
    if len(ics) > 0:
        pos = np.mean(ics > 0) * 100
        print(f"  {label:<16s} OOS IC (fixed params) = {np.mean(ics):+.4f} | "
              f"median {np.median(ics):+.4f} | folds>0 {pos:.0f}% (n={len(ics)})")

print("\n✅ Walk-forward OOS completo.")