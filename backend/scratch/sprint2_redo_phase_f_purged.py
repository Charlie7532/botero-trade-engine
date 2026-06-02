"""
Sprint 2-REDO — Fase F: PurgedKFold — AUC Real sin Leakage Temporal
=====================================================================
Objetivo: ¿El AUC 0.736 es real o inflado por autocorrelación temporal?
           Obtener AUC corregido con embargo de 10 barras.
           Comparar XGBoost vs LightGBM.

Input:  sprint2_redo_lake_v21.pkl, sprint2_redo_phase_c_v21.pkl
Output: sprint2_redo_phase_f_purged.pkl, .log
"""

import pandas as pd
import numpy as np
import pickle
import time
import warnings
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score

warnings.filterwarnings("ignore")

LOG = []
def log(msg):
    print(msg)
    LOG.append(msg)

t0 = time.time()

log("═" * 100)
log("  FASE F: PURGEDKFOLD — AUC REAL SIN LEAKAGE TEMPORAL")
log("═" * 100)

# ── 1. Load ──
log("\n=== 1. CARGA ===")
df = pd.read_pickle("backend/scratch/sprint2_redo_lake_v21.pkl")
with open("backend/scratch/sprint2_redo_phase_c_v21.pkl", "rb") as f:
    pc = pickle.load(f)

top_features = pc["top_features_used"]
X_all = df[top_features].values.astype(np.float32)
y_all = df["hit_zz_5pct"].values.astype(int)
tickers_all = df["ticker"].values
X_all = np.nan_to_num(X_all, nan=0.0)

log(f"  Data: {X_all.shape[0]:,} × {X_all.shape[1]}")

# ── 2. Implement PurgedKFold ──
log("\n=== 2. PURGEDKFOLD (embargo=10 barras, 5 folds temporales per-ticker) ===")

def purged_kfold_per_ticker(df, n_folds=5, embargo=10):
    """PurgedKFold: split each ticker into temporal folds with embargo gap.
    Uses POSITIONAL indices (iloc-style) since df.index may be timestamps."""
    folds = [[] for _ in range(n_folds)]
    ticker_values = df["ticker"].values
    
    for tk in sorted(df["ticker"].unique()):
        positions = np.where(ticker_values == tk)[0]  # Positional indices
        n = len(positions)
        
        # Split into n_folds temporal chunks
        fold_size = n // n_folds
        for fold_i in range(n_folds):
            start = fold_i * fold_size
            end = start + fold_size if fold_i < n_folds - 1 else n
            folds[fold_i].extend(positions[start:end].tolist())
    
    # Generate train/test pairs with embargo
    for test_fold in range(n_folds):
        test_idx = np.array(folds[test_fold])
        
        # Train = all other folds
        train_candidates = []
        for fold_i in range(n_folds):
            if fold_i != test_fold:
                train_candidates.extend(folds[fold_i])
        train_candidates = np.array(train_candidates)
        
        # Remove embargo zone per-ticker
        test_tickers_arr = ticker_values[test_idx]
        train_tickers_arr = ticker_values[train_candidates]
        
        purged_train = []
        for tk in sorted(df["ticker"].unique()):
            tk_mask_test = test_tickers_arr == tk
            tk_mask_train = train_tickers_arr == tk
            
            if not tk_mask_test.any() or not tk_mask_train.any():
                purged_train.extend(train_candidates[tk_mask_train].tolist())
                continue
            
            tk_test_pos = test_idx[tk_mask_test]  # Positional indices in test
            tk_train_pos = train_candidates[tk_mask_train]  # Positional in train
            
            # All positions for this ticker (for searchsorted)
            tk_all_pos = np.where(ticker_values == tk)[0]
            
            # Build embargo set: positions within ±embargo of test boundaries
            embargo_set = set()
            for pos in tk_test_pos:
                rank = np.searchsorted(tk_all_pos, pos)
                for e in range(-embargo, embargo + 1):
                    r = rank + e
                    if 0 <= r < len(tk_all_pos):
                        embargo_set.add(tk_all_pos[r])
            
            # Keep only train positions NOT in embargo zone
            for pos in tk_train_pos:
                if pos not in embargo_set:
                    purged_train.append(pos)
        
        purged_train = np.array(purged_train)
        yield purged_train, test_idx

# ── 3. XGBoost with PurgedKFold ──
import xgboost as xgb

log("\n=== 3. XGBOOST CON PURGEDKFOLD ===")

results_purged = []
for fold_i, (train_idx, test_idx) in enumerate(purged_kfold_per_ticker(df, n_folds=5, embargo=10)):
    X_train = X_all[train_idx]
    X_test = X_all[test_idx]
    y_train = y_all[train_idx]
    y_test = y_all[test_idx]
    
    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=(y_train == 0).sum() / max((y_train == 1).sum(), 1),
        random_state=42, eval_metric="logloss", verbosity=0,
    )
    model.fit(X_train, y_train)
    
    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = model.predict(X_test)
    
    auc = roc_auc_score(y_test, y_prob)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    
    results_purged.append({"fold": fold_i+1, "auc": auc, "prec": prec, "rec": rec, "f1": f1,
                           "train_n": len(X_train), "test_n": len(X_test)})
    
    # Sanity: verify no leakage — train and test must not overlap
    assert len(set(train_idx) & set(test_idx)) == 0, f"LEAKAGE in fold {fold_i+1}!"
    
    log(f"  Fold {fold_i+1}: train={len(X_train):,} test={len(X_test):,} "
        f"AUC={auc:.4f} P={prec:.3f} R={rec:.3f} F1={f1:.3f}")

auc_purged_mean = np.mean([r["auc"] for r in results_purged])
auc_purged_std = np.std([r["auc"] for r in results_purged])

log(f"\n  XGBoost PurgedKFold: AUC = {auc_purged_mean:.4f} ± {auc_purged_std:.4f}")
log(f"  XGBoost GroupKFold:  AUC = 0.736 (reported earlier)")
log(f"  Delta: {0.736 - auc_purged_mean:+.4f}")
log(f"  → {'✅ Señal genuina' if auc_purged_mean >= 0.65 else '⚠️ Señal más débil de lo reportado'}")

# ── 4. LightGBM with PurgedKFold ──
log("\n=== 4. LIGHTGBM CON PURGEDKFOLD ===")
import lightgbm as lgb

results_lgb = []
for fold_i, (train_idx, test_idx) in enumerate(purged_kfold_per_ticker(df, n_folds=5, embargo=10)):
    X_train = X_all[train_idx]
    X_test = X_all[test_idx]
    y_train = y_all[train_idx]
    y_test = y_all[test_idx]
    
    model_lgb = lgb.LGBMClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=(y_train == 0).sum() / max((y_train == 1).sum(), 1),
        random_state=42, verbose=-1,
    )
    model_lgb.fit(X_train, y_train)
    
    y_prob = model_lgb.predict_proba(X_test)[:, 1]
    y_pred = model_lgb.predict(X_test)
    
    auc = roc_auc_score(y_test, y_prob)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    
    results_lgb.append({"fold": fold_i+1, "auc": auc, "prec": prec, "rec": rec, "f1": f1})
    
    log(f"  Fold {fold_i+1}: AUC={auc:.4f} P={prec:.3f} R={rec:.3f} F1={f1:.3f}")

auc_lgb_mean = np.mean([r["auc"] for r in results_lgb])
auc_lgb_std = np.std([r["auc"] for r in results_lgb])

log(f"\n  LightGBM PurgedKFold: AUC = {auc_lgb_mean:.4f} ± {auc_lgb_std:.4f}")
log(f"  XGBoost PurgedKFold:  AUC = {auc_purged_mean:.4f} ± {auc_purged_std:.4f}")
log(f"  → {'LightGBM gana' if auc_lgb_mean > auc_purged_mean else 'XGBoost gana'}")

# ── 5. AUC by Feature Family ──
log("\n=== 5. AUC POR FAMILIA DE FEATURES ===")

kalman_feats = [f for f in top_features if f.startswith("kf_")]
canal_feats = [f for f in top_features if not f.startswith("kf_")]

kalman_idx = [top_features.index(f) for f in kalman_feats]
canal_idx = [top_features.index(f) for f in canal_feats]

for label, feat_idx in [("Solo Kalman", kalman_idx), ("Solo Canal", canal_idx)]:
    aucs = []
    for fold_i, (train_idx, test_idx) in enumerate(purged_kfold_per_ticker(df, n_folds=5, embargo=10)):
        X_tr = X_all[train_idx][:, feat_idx]
        X_te = X_all[test_idx][:, feat_idx]
        y_tr = y_all[train_idx]
        y_te = y_all[test_idx]
        
        m = xgb.XGBClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            random_state=42, eval_metric="logloss", verbosity=0,
            scale_pos_weight=(y_tr == 0).sum() / max((y_tr == 1).sum(), 1),
        )
        m.fit(X_tr, y_tr)
        y_p = m.predict_proba(X_te)[:, 1]
        aucs.append(roc_auc_score(y_te, y_p))
    
    log(f"  {label} ({len(feat_idx)} feats): AUC = {np.mean(aucs):.4f} ± {np.std(aucs):.4f}")

# ── 6. Deflated Sharpe Ratio ──
log("\n=== 6. DEFLATED SHARPE RATIO ===")
from scipy.stats import norm

def compute_dsr(sharpe, n_trials, T, skew=0, kurtosis=3):
    """Deflated Sharpe Ratio (López de Prado)."""
    sr0 = np.sqrt(2 * np.log(n_trials))  # Expected max SR under H0
    numerator = (sharpe - sr0) * np.sqrt(T - 1)
    denominator = np.sqrt(1 - skew * sharpe + (kurtosis - 1) / 4 * sharpe**2)
    return norm.cdf(numerator / denominator) if denominator > 0 else 0

# Treat AUC - 0.5 as "return" and compute SR-like metric
auc_returns = [r["auc"] - 0.5 for r in results_purged]
sharpe_like = np.mean(auc_returns) / np.std(auc_returns) if np.std(auc_returns) > 0 else 0

# n_trials = number of models we've tried (XGBoost + LightGBM + various configs)
n_trials = 5  # Conservative estimate
T = len(results_purged)

dsr = compute_dsr(sharpe_like, n_trials, T)

log(f"  Sharpe-like (AUC excess): {sharpe_like:.3f}")
log(f"  DSR (n_trials={n_trials}, T={T}): {dsr:.3f}")
log(f"  → {'✅ Significativo' if dsr > 0.5 else '⚠️ No significativo'}")

# ── 7. Summary ──
log("\n" + "═" * 100)
log("  RESUMEN FASE F")
log("═" * 100)
log(f"\n  AUC GroupKFold (reportado):    0.736")
log(f"  AUC PurgedKFold (XGBoost):    {auc_purged_mean:.4f} ± {auc_purged_std:.4f}")
log(f"  AUC PurgedKFold (LightGBM):   {auc_lgb_mean:.4f} ± {auc_lgb_std:.4f}")
log(f"  Delta por leakage temporal:   {0.736 - auc_purged_mean:+.4f}")
log(f"  DSR:                          {dsr:.3f}")
log(f"  Tiempo: {time.time()-t0:.1f}s")

# ── 8. Save ──
results = {
    "purged_xgb": results_purged,
    "purged_lgb": results_lgb,
    "auc_purged_xgb": auc_purged_mean,
    "auc_purged_xgb_std": auc_purged_std,
    "auc_purged_lgb": auc_lgb_mean,
    "auc_purged_lgb_std": auc_lgb_std,
    "auc_groupkfold": 0.736,
    "dsr": dsr,
    "sharpe_like": sharpe_like,
}

with open("backend/scratch/sprint2_redo_phase_f_purged.pkl", "wb") as f:
    pickle.dump(results, f)

with open("backend/scratch/sprint2_redo_phase_f_purged.log", "w") as f:
    f.write("\n".join(LOG))

log(f"\n  ✅ Saved: sprint2_redo_phase_f_purged.pkl + .log")
