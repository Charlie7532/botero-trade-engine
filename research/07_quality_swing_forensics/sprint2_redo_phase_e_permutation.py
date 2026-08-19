"""
Sprint 2-REDO — Fase E: Permutation Importance — Redundancia
==============================================================
Objetivo: ¿Cuántas de las 30 features son REALMENTE necesarias?
           ¿Cuáles son redundantes? ¿Se puede simplificar el detector?

Input:  sprint2_redo_lake_v21.pkl, sprint2_redo_phase_d_shap.pkl
Output: sprint2_redo_phase_e_permutation.pkl, .log
"""

import pandas as pd
import numpy as np
import pickle
import time
import warnings
from scipy import stats as sp_stats
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score
import xgboost as xgb

warnings.filterwarnings("ignore")

LOG = []
def log(msg):
    print(msg)
    LOG.append(msg)

t0 = time.time()

log("═" * 100)
log("  FASE E: PERMUTATION IMPORTANCE — REDUNDANCIA")
log("═" * 100)

# ── 1. Load ──
log("\n=== 1. CARGA ===")
df = pd.read_pickle("data/research/feature_lake/sprint2_redo_lake_v21.pkl")
with open("data/research/feature_lake/sprint2_redo_phase_d_shap.pkl", "rb") as f:
    phase_d = pickle.load(f)

model = phase_d["model"]
top_features = phase_d["top_features"]
train_tickers = phase_d["train_tickers"]
test_tickers = phase_d["test_tickers"]

X = df[top_features].values.astype(np.float32)
y = df["hit_zz_5pct"].values.astype(int)
tickers = df["ticker"].values
X = np.nan_to_num(X, nan=0.0)

# Recreate train/test split
from sklearn.model_selection import GroupShuffleSplit
gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
train_idx, test_idx = next(gss.split(X, y, groups=tickers))
X_train, X_test = X[train_idx], X[test_idx]
y_train, y_test = y[train_idx], y[test_idx]

log(f"  Train: {len(X_train):,}, Test: {len(X_test):,}")

# ── 2. Permutation Importance ──
log("\n=== 2. PERMUTATION IMPORTANCE (100 repeats) ===")
t_perm = time.time()

result = permutation_importance(
    model, X_test, y_test,
    n_repeats=100, random_state=42,
    scoring="roc_auc", n_jobs=-1,
)

log(f"  Computed in {time.time()-t_perm:.1f}s")

perm_rank = np.argsort(-result.importances_mean)

log(f"\n  {'Rank':>4} {'Feature':<35} {'Perm Importance':>16} {'±std':>10} {'SHAP Rank':>10} {'Essential':>10}")
log(f"  {'─'*4} {'─'*35} {'─'*16} {'─'*10} {'─'*10} {'─'*10}")

essential_features = []
redundant_features = []
for rank, idx in enumerate(perm_rank):
    feat = top_features[idx]
    imp = result.importances_mean[idx]
    std = result.importances_std[idx]
    shap_rank = phase_d["shap_ranking"].get(feat, "?")
    is_essential = imp > 0.005
    marker = "✅" if is_essential else "❌"
    log(f"  {rank+1:>4} {feat:<35} {imp:>16.5f} {std:>10.5f} {shap_rank:>10} {marker:>10}")
    
    if is_essential:
        essential_features.append(feat)
    else:
        redundant_features.append(feat)

log(f"\n  Essential features (perm > 0.005): {len(essential_features)}")
log(f"  Redundant features: {len(redundant_features)}")

# ── 3. Correlation Matrix — Clusters ──
log("\n=== 3. CORRELACIÓN ENTRE TOP 30 — CLUSTERS ===")

corr_matrix = np.corrcoef(X_train.T)

# Find clusters of |r| > 0.80
clusters = []
clustered = set()

for i in range(len(top_features)):
    if i in clustered:
        continue
    cluster = [i]
    for j in range(i+1, len(top_features)):
        if j in clustered:
            continue
        if abs(corr_matrix[i, j]) > 0.80:
            cluster.append(j)
    if len(cluster) > 1:
        clusters.append(cluster)
        clustered.update(cluster)

log(f"  Clusters con |r| > 0.80: {len(clusters)}")
for ci, cluster in enumerate(clusters):
    feats = [top_features[i] for i in cluster]
    log(f"\n  Cluster {ci+1}: {len(feats)} features")
    for i in cluster:
        imp = result.importances_mean[i]
        log(f"    {top_features[i]:<35} perm={imp:.5f}")
    
    # Show correlations within cluster
    for ii in range(len(cluster)):
        for jj in range(ii+1, len(cluster)):
            r = corr_matrix[cluster[ii], cluster[jj]]
            log(f"    r({top_features[cluster[ii]][:20]}, {top_features[cluster[jj]][:20]}) = {r:.3f}")

# ── 4. Reduced Model ──
log("\n=== 4. MODELO REDUCIDO (solo esenciales) ===")

if essential_features:
    ess_idx = [top_features.index(f) for f in essential_features]
    X_train_red = X_train[:, ess_idx]
    X_test_red = X_test[:, ess_idx]
    
    model_red = xgb.XGBClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=(y_train == 0).sum() / max((y_train == 1).sum(), 1),
        random_state=42, eval_metric="logloss", verbosity=0,
    )
    model_red.fit(X_train_red, y_train)
    
    y_prob_full = model.predict_proba(X_test)[:, 1]
    y_prob_red = model_red.predict_proba(X_test_red)[:, 1]
    
    auc_full = roc_auc_score(y_test, y_prob_full)
    auc_red = roc_auc_score(y_test, y_prob_red)
    delta = (auc_full - auc_red) / auc_full * 100
    
    log(f"  Full model ({len(top_features)} features): AUC = {auc_full:.4f}")
    log(f"  Reduced model ({len(essential_features)} features): AUC = {auc_red:.4f}")
    log(f"  Delta: {delta:.1f}% loss")
    log(f"  → {'✅ Reducción viable' if delta < 5 else '⚠️ Pérdida significativa'} (< 5% = OK)")

# ── 5. Summary ──
log("\n" + "═" * 100)
log("  RESUMEN FASE E")
log("═" * 100)
log(f"\n  Features esenciales: {len(essential_features)}/{len(top_features)}")
log(f"  Features redundantes: {len(redundant_features)}")
log(f"  Clusters |r| > 0.80: {len(clusters)}")
if essential_features:
    log(f"  AUC full vs reduced: {auc_full:.4f} vs {auc_red:.4f} (Δ={delta:.1f}%)")
log(f"  Tiempo: {time.time()-t0:.1f}s")

# ── 6. Save ──
results = {
    "permutation_importance": {
        "mean": result.importances_mean,
        "std": result.importances_std,
    },
    "essential_features": essential_features,
    "redundant_features": redundant_features,
    "clusters": [[top_features[i] for i in c] for c in clusters],
    "correlation_matrix": corr_matrix,
    "auc_full": auc_full if essential_features else None,
    "auc_reduced": auc_red if essential_features else None,
    "top_features": top_features,
}

with open("data/research/feature_lake/sprint2_redo_phase_e_permutation.pkl", "wb") as f:
    pickle.dump(results, f)

with open("data/research/feature_lake/sprint2_redo_phase_e_permutation.log", "w") as f:
    f.write("\n".join(LOG))

log(f"\n  ✅ Saved: sprint2_redo_phase_e_permutation.pkl + .log")
