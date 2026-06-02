"""
Sprint 2-REDO — Fase G: Modelo Temporal — CRESCENDO como Input
================================================================
Objetivo: ¿Un modelo con ventana multi-barra supera al barra-a-barra?
           Capturar CRESCENDO como feature temporal explícita.

Input:  sprint2_redo_lake_v21.pkl, sprint2_redo_phase_c_v21.pkl
Output: sprint2_redo_phase_g_temporal.pkl, .log
"""

import pandas as pd
import numpy as np
import pickle
import time
import warnings
import xgboost as xgb
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score

warnings.filterwarnings("ignore")

LOG = []
def log(msg):
    print(msg)
    LOG.append(msg)

t0 = time.time()

log("═" * 100)
log("  FASE G: MODELO TEMPORAL — CRESCENDO COMO INPUT")
log("═" * 100)

# ── 1. Load ──
log("\n=== 1. CARGA ===")
df = pd.read_pickle("backend/scratch/sprint2_redo_lake_v21.pkl")
with open("backend/scratch/sprint2_redo_phase_c_v21.pkl", "rb") as f:
    pc = pickle.load(f)

top_features = pc["top_features_used"]
log(f"  Lake: {df.shape[0]:,} × {df.shape[1]}")

# ── 2. PurgedKFold implementation (same as Phase F) ──
def purged_kfold_per_ticker(df, n_folds=5, embargo=10):
    """PurgedKFold with positional indices (timestamps in df.index)."""
    folds = [[] for _ in range(n_folds)]
    ticker_values = df["ticker"].values
    
    for tk in sorted(df["ticker"].unique()):
        positions = np.where(ticker_values == tk)[0]
        n = len(positions)
        fold_size = n // n_folds
        for fold_i in range(n_folds):
            start = fold_i * fold_size
            end = start + fold_size if fold_i < n_folds - 1 else n
            folds[fold_i].extend(positions[start:end].tolist())
    
    for test_fold in range(n_folds):
        test_idx = np.array(folds[test_fold])
        train_candidates = []
        for fold_i in range(n_folds):
            if fold_i != test_fold:
                train_candidates.extend(folds[fold_i])
        train_candidates = np.array(train_candidates)
        
        test_tickers_arr = ticker_values[test_idx]
        train_tickers_arr = ticker_values[train_candidates]
        
        purged_train = []
        for tk in sorted(df["ticker"].unique()):
            tk_mask_test = test_tickers_arr == tk
            tk_mask_train = train_tickers_arr == tk
            if not tk_mask_test.any() or not tk_mask_train.any():
                purged_train.extend(train_candidates[tk_mask_train].tolist())
                continue
            tk_test_pos = test_idx[tk_mask_test]
            tk_train_pos = train_candidates[tk_mask_train]
            tk_all_pos = np.where(ticker_values == tk)[0]
            embargo_set = set()
            for pos in tk_test_pos:
                rank = np.searchsorted(tk_all_pos, pos)
                for e in range(-embargo, embargo + 1):
                    r = rank + e
                    if 0 <= r < len(tk_all_pos):
                        embargo_set.add(tk_all_pos[r])
            for pos in tk_train_pos:
                if pos not in embargo_set:
                    purged_train.append(pos)
        
        yield np.array(purged_train), test_idx

# ── 3. Build temporal features ──
log("\n=== 2. CONSTRUCCIÓN DE FEATURES TEMPORALES ===")

X_base = np.nan_to_num(df[top_features].values.astype(np.float32), nan=0.0)
y = df["hit_zz_5pct"].values.astype(int)

# Per-ticker z-scores and density
temporal_features = np.zeros((len(df), 6), dtype=np.float32)
temporal_names = [
    "rolling_density_3bar",
    "rolling_density_5bar",
    "density_delta_3bar",
    "kf_price_pred_trend_5bar",
    "rsi_z_trend_5bar",
    "wave_slope_delta_3bar",
]

for tk in sorted(df["ticker"].unique()):
    mask = df["ticker"] == tk
    idx = np.where(mask.values)[0]
    tk_vals = X_base[idx]
    
    # Compute per-ticker z-scores
    mu = np.nanmean(tk_vals, axis=0)
    sigma = np.nanstd(tk_vals, axis=0)
    sigma[sigma < 1e-8] = 1
    z = np.abs((tk_vals - mu) / sigma)
    density = (z > 2.0).sum(axis=1).astype(np.float32)
    
    # 1. Rolling density (3-bar)
    rd3 = pd.Series(density).rolling(3, min_periods=1).mean().values
    temporal_features[idx, 0] = rd3
    
    # 2. Rolling density (5-bar)
    rd5 = pd.Series(density).rolling(5, min_periods=1).mean().values
    temporal_features[idx, 1] = rd5
    
    # 3. Density delta (vs 3 bars ago)
    dd3 = density - np.roll(density, 3)
    dd3[:3] = 0
    temporal_features[idx, 2] = dd3
    
    # 4. kf_price_pred_val trend (slope of last 5 bars)
    kf_idx = top_features.index("kf_price_pred_val")
    kf_vals = tk_vals[:, kf_idx]
    kf_trend = pd.Series(kf_vals).rolling(5, min_periods=2).apply(
        lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) >= 2 else 0, raw=True
    ).values
    temporal_features[idx, 3] = np.nan_to_num(kf_trend, nan=0.0)
    
    # 5. RSI z-score trend (slope of last 5 bars)
    rsi_idx = top_features.index("rsi_value")
    rsi_vals = tk_vals[:, rsi_idx]
    rsi_z = (rsi_vals - mu[rsi_idx]) / sigma[rsi_idx]
    rsi_trend = pd.Series(rsi_z).rolling(5, min_periods=2).apply(
        lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) >= 2 else 0, raw=True
    ).values
    temporal_features[idx, 4] = np.nan_to_num(rsi_trend, nan=0.0)
    
    # 6. wave_slope delta vs 3 bars ago
    ws_idx = top_features.index("wave_slope")
    ws_vals = tk_vals[:, ws_idx]
    ws_delta = ws_vals - np.roll(ws_vals, 3)
    ws_delta[:3] = 0
    temporal_features[idx, 5] = ws_delta

for i, name in enumerate(temporal_names):
    vals = temporal_features[:, i]
    log(f"  {name:<35} μ={vals.mean():.4f}  σ={vals.std():.4f}  range=[{vals.min():.3f}, {vals.max():.3f}]")

# ── 4. Model A: Baseline (30 features, PurgedKFold) ──
log("\n=== 3. MODELO A: BASELINE (30 features, PurgedKFold) ===")

results_a = []
for fold_i, (train_idx, test_idx) in enumerate(purged_kfold_per_ticker(df, n_folds=5, embargo=10)):
    X_tr, X_te = X_base[train_idx], X_base[test_idx]
    y_tr, y_te = y[train_idx], y[test_idx]
    
    m = xgb.XGBClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=(y_tr == 0).sum() / max((y_tr == 1).sum(), 1),
        random_state=42, eval_metric="logloss", verbosity=0,
    )
    m.fit(X_tr, y_tr)
    y_p = m.predict_proba(X_te)[:, 1]
    auc = roc_auc_score(y_te, y_p)
    results_a.append(auc)
    log(f"  Fold {fold_i+1}: AUC={auc:.4f}")

auc_a = np.mean(results_a)
log(f"  Modelo A (baseline): AUC = {auc_a:.4f} ± {np.std(results_a):.4f}")

# ── 5. Model B: Baseline + 6 temporal features ──
log("\n=== 4. MODELO B: BASELINE + TEMPORAL (36 features, PurgedKFold) ===")

X_b = np.hstack([X_base, temporal_features])

results_b = []
for fold_i, (train_idx, test_idx) in enumerate(purged_kfold_per_ticker(df, n_folds=5, embargo=10)):
    X_tr, X_te = X_b[train_idx], X_b[test_idx]
    y_tr, y_te = y[train_idx], y[test_idx]
    
    m = xgb.XGBClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=(y_tr == 0).sum() / max((y_tr == 1).sum(), 1),
        random_state=42, eval_metric="logloss", verbosity=0,
    )
    m.fit(X_tr, y_tr)
    y_p = m.predict_proba(X_te)[:, 1]
    auc = roc_auc_score(y_te, y_p)
    results_b.append(auc)
    log(f"  Fold {fold_i+1}: AUC={auc:.4f}")

auc_b = np.mean(results_b)
log(f"  Modelo B (temporal): AUC = {auc_b:.4f} ± {np.std(results_b):.4f}")
log(f"  Delta B-A: {auc_b - auc_a:+.4f} ({'✅ MEJORA' if auc_b > auc_a else '❌ NO mejora'})")

# ── 6. Model C: Windowed (5 bars flattened) ──
log("\n=== 5. MODELO C: VENTANA 5 BARRAS (150 features, PurgedKFold) ===")

# Build windowed features per-ticker
n_features = len(top_features)
window_size = 5
X_c = np.zeros((len(df), n_features * window_size), dtype=np.float32)

for tk in sorted(df["ticker"].unique()):
    mask = df["ticker"] == tk
    idx = np.where(mask.values)[0]
    tk_vals = X_base[idx]
    
    for w in range(window_size):
        shifted = np.roll(tk_vals, w, axis=0)
        shifted[:w] = 0  # Pad beginning with zeros
        X_c[idx, w*n_features:(w+1)*n_features] = shifted

results_c = []
for fold_i, (train_idx, test_idx) in enumerate(purged_kfold_per_ticker(df, n_folds=5, embargo=10)):
    X_tr, X_te = X_c[train_idx], X_c[test_idx]
    y_tr, y_te = y[train_idx], y[test_idx]
    
    m = xgb.XGBClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=(y_tr == 0).sum() / max((y_tr == 1).sum(), 1),
        random_state=42, eval_metric="logloss", verbosity=0,
    )
    m.fit(X_tr, y_tr)
    y_p = m.predict_proba(X_te)[:, 1]
    auc = roc_auc_score(y_te, y_p)
    results_c.append(auc)
    log(f"  Fold {fold_i+1}: AUC={auc:.4f}")

auc_c = np.mean(results_c)
log(f"  Modelo C (ventana): AUC = {auc_c:.4f} ± {np.std(results_c):.4f}")
log(f"  Delta C-A: {auc_c - auc_a:+.4f} ({'✅ MEJORA' if auc_c > auc_a else '❌ NO mejora o OVERFITTING'})")

# ── 7. SHAP on Model B (best temporal model) ──
log("\n=== 6. SHAP SOBRE MODELO B (¿features temporales dominan?) ===")
import shap

# Train final Model B
m_final = xgb.XGBClassifier(
    n_estimators=200, max_depth=5, learning_rate=0.1,
    subsample=0.8, colsample_bytree=0.8,
    scale_pos_weight=(y == 0).sum() / max((y == 1).sum(), 1),
    random_state=42, eval_metric="logloss", verbosity=0,
)

# Use first 80% as train, last 20% as test (temporal split)
split = int(len(X_b) * 0.8)
m_final.fit(X_b[:split], y[:split])

# SHAP on subsample of test
shap_n = min(2000, len(X_b) - split)
X_shap_b = X_b[split:split+shap_n]
explainer_b = shap.TreeExplainer(m_final)
shap_b = explainer_b.shap_values(X_shap_b)

mean_abs_shap_b = np.abs(shap_b).mean(axis=0)
all_feat_names = top_features + temporal_names
shap_rank_b = np.argsort(-mean_abs_shap_b)

log(f"\n  {'Rank':>4} {'Feature':<35} {'|SHAP| mean':>12} {'Type':>10}")
log(f"  {'─'*4} {'─'*35} {'─'*12} {'─'*10}")
for rank in range(min(20, len(all_feat_names))):
    idx = shap_rank_b[rank]
    feat = all_feat_names[idx]
    ftype = "TEMPORAL" if feat in temporal_names else "ORIGINAL"
    log(f"  {rank+1:>4} {feat:<35} {mean_abs_shap_b[idx]:>12.4f} {ftype:>10}")

# Count temporal features in top 10
temporal_in_top10 = sum(1 for r in range(10) if all_feat_names[shap_rank_b[r]] in temporal_names)
log(f"\n  Temporal features in top 10 SHAP: {temporal_in_top10}/10")

# ── 8. Summary ──
log("\n" + "═" * 100)
log("  RESUMEN FASE G")
log("═" * 100)
log(f"\n  Modelo A (30 features baseline):    AUC = {auc_a:.4f} ± {np.std(results_a):.4f}")
log(f"  Modelo B (36 features + temporal):  AUC = {auc_b:.4f} ± {np.std(results_b):.4f}  Δ={auc_b-auc_a:+.4f}")
log(f"  Modelo C (150 features ventana):    AUC = {auc_c:.4f} ± {np.std(results_c):.4f}  Δ={auc_c-auc_a:+.4f}")
log(f"  Temporal features in top 10 SHAP: {temporal_in_top10}/10")
log(f"  Tiempo: {time.time()-t0:.1f}s")

# ── 9. Save ──
results = {
    "auc_a_baseline": auc_a,
    "auc_a_std": np.std(results_a),
    "auc_b_temporal": auc_b,
    "auc_b_std": np.std(results_b),
    "auc_c_window": auc_c,
    "auc_c_std": np.std(results_c),
    "results_a": results_a,
    "results_b": results_b,
    "results_c": results_c,
    "temporal_names": temporal_names,
    "shap_rank_b": [all_feat_names[i] for i in shap_rank_b[:20]],
    "temporal_in_top10": temporal_in_top10,
}

with open("backend/scratch/sprint2_redo_phase_g_temporal.pkl", "wb") as f:
    pickle.dump(results, f)

with open("backend/scratch/sprint2_redo_phase_g_temporal.log", "w") as f:
    f.write("\n".join(LOG))

log(f"\n  ✅ Saved: sprint2_redo_phase_g_temporal.pkl + .log")
