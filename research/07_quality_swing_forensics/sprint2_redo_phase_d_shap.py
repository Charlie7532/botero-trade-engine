"""
Sprint 2-REDO — Fase D: SHAP Interpretabilidad ML
=====================================================
Objetivo: Responder POR QUÉ el modelo clasifica cada barra.
           Descubrir interacciones y thresholds no-lineales.
           Comparar ranking SHAP vs ranking forense (Fase B).

Input:  sprint2_redo_lake_v21.pkl, sprint2_redo_phase_c_v21.pkl
Output: sprint2_redo_phase_d_shap.pkl, .log
"""

import pandas as pd
import numpy as np
import pickle
import time
import warnings
import sys
from collections import defaultdict
from scipy import stats as sp_stats

warnings.filterwarnings("ignore")

LOG = []
def log(msg):
    print(msg)
    LOG.append(msg)

t0 = time.time()

log("═" * 100)
log("  FASE D: SHAP — INTERPRETABILIDAD ML")
log("═" * 100)

# ── 1. Load data ──
log("\n=== 1. CARGA DE DATOS ===")
df = pd.read_pickle("data/research/feature_lake/sprint2_redo_lake_v21.pkl")
with open("data/research/feature_lake/sprint2_redo_phase_c_v21.pkl", "rb") as f:
    pc = pickle.load(f)

top_features = pc["top_features_used"]
log(f"  Lake: {df.shape[0]:,} rows × {df.shape[1]} cols")
log(f"  Top features: {len(top_features)}")

# ── 2. Prepare data ──
log("\n=== 2. PREPARACIÓN ===")
X = df[top_features].values.astype(np.float32)
y = df["hit_zz_5pct"].values.astype(int)
tickers = df["ticker"].values
X = np.nan_to_num(X, nan=0.0)

log(f"  X: {X.shape}, y: {y.shape}")
log(f"  Positive rate: {y.mean()*100:.1f}%")

# ── 3. Train XGBoost (80/20 stratified by ticker) ──
log("\n=== 3. ENTRENAMIENTO XGBOOST ===")
import xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit

# 80/20 split by ticker groups
gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
train_idx, test_idx = next(gss.split(X, y, groups=tickers))

X_train, X_test = X[train_idx], X[test_idx]
y_train, y_test = y[train_idx], y[test_idx]
train_tickers = np.unique(tickers[train_idx])
test_tickers = np.unique(tickers[test_idx])

log(f"  Train: {len(X_train):,} samples, tickers: {list(train_tickers)}")
log(f"  Test:  {len(X_test):,} samples, tickers: {list(test_tickers)}")

model = xgb.XGBClassifier(
    n_estimators=200, max_depth=5, learning_rate=0.1,
    subsample=0.8, colsample_bytree=0.8,
    scale_pos_weight=(y_train == 0).sum() / max((y_train == 1).sum(), 1),
    random_state=42, eval_metric="logloss", verbosity=0,
)
model.fit(X_train, y_train)

from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score
y_prob = model.predict_proba(X_test)[:, 1]
y_pred = model.predict(X_test)
auc = roc_auc_score(y_test, y_prob)
prec = precision_score(y_test, y_pred)
rec = recall_score(y_test, y_pred)
f1 = f1_score(y_test, y_pred)

log(f"  AUC={auc:.4f}  Precision={prec:.3f}  Recall={rec:.3f}  F1={f1:.3f}")

# ── 4. SHAP TreeExplainer ──
log("\n=== 4. SHAP TREEEXPLAINER ===")
import shap

t_shap = time.time()

# Use a subsample for SHAP (full test set can be large)
shap_sample_size = min(5000, len(X_test))
shap_idx = np.random.RandomState(42).choice(len(X_test), shap_sample_size, replace=False)
X_shap = X_test[shap_idx]
y_shap = y_test[shap_idx]

explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_shap)

log(f"  SHAP computed on {shap_sample_size:,} samples in {time.time()-t_shap:.1f}s")
log(f"  shap_values shape: {shap_values.shape}")

# ── 5. SHAP Ranking vs Fase B Ranking ──
log("\n=== 5. SHAP RANKING vs FASE B ===")

# Mean absolute SHAP value per feature
mean_abs_shap = np.abs(shap_values).mean(axis=0)
shap_rank = np.argsort(-mean_abs_shap)

log(f"\n  {'Rank':>4} {'Feature':<35} {'|SHAP| mean':>12} {'Fase B Rank':>12} {'Δ Rank':>8}")
log(f"  {'─'*4} {'─'*35} {'─'*12} {'─'*12} {'─'*8}")

shap_ranking = {}
for rank, idx in enumerate(shap_rank[:30]):
    feat = top_features[idx]
    fase_b_rank = idx + 1  # Phase B rank = original order
    delta = rank + 1 - fase_b_rank
    shap_ranking[feat] = rank + 1
    marker = " ★" if abs(delta) >= 5 else ""
    log(f"  {rank+1:>4} {feat:<35} {mean_abs_shap[idx]:>12.4f} {fase_b_rank:>12} {delta:>+8}{marker}")

# Spearman correlation between rankings
shap_ranks = [shap_ranking.get(f, 30) for f in top_features]
fase_b_ranks = list(range(1, len(top_features) + 1))
rho, p_rho = sp_stats.spearmanr(shap_ranks, fase_b_ranks)
log(f"\n  Spearman ρ (SHAP vs Fase B): {rho:.3f} (p={p_rho:.2e})")
log(f"  → {'✅ CONFIRMADO' if rho > 0.70 else '⚠️ DIVERGENCIA'}: rankings {'coinciden' if rho > 0.70 else 'difieren'}")

# ── 6. SHAP Interaction Values (top 15 only for speed) ──
log("\n=== 6. SHAP INTERACTION VALUES ===")

t_int = time.time()
# Subsample further for interactions (expensive)
int_sample = min(1000, shap_sample_size)
X_int = X_shap[:int_sample]

interaction_values = explainer.shap_interaction_values(X_int)
log(f"  Interaction values computed on {int_sample} samples in {time.time()-t_int:.1f}s")
log(f"  Shape: {interaction_values.shape}")

# Find top interactions (off-diagonal)
n_feat = len(top_features)
mean_interactions = np.abs(interaction_values).mean(axis=0)

# Zero out diagonal (self-interactions)
np.fill_diagonal(mean_interactions, 0)

# Top 10 interactions
flat_idx = np.argsort(-mean_interactions.ravel())
log(f"\n  Top 10 Feature Interactions:")
log(f"  {'Rank':>4} {'Feature A':<30} {'Feature B':<30} {'|Interaction|':>14}")
log(f"  {'─'*4} {'─'*30} {'─'*30} {'─'*14}")

top_interactions = []
seen = set()
count = 0
for idx in flat_idx:
    i, j = divmod(idx, n_feat)
    if i >= j:
        continue
    pair = (min(i,j), max(i,j))
    if pair in seen:
        continue
    seen.add(pair)
    count += 1
    val = mean_interactions[i, j]
    top_interactions.append((top_features[i], top_features[j], val))
    log(f"  {count:>4} {top_features[i]:<30} {top_features[j]:<30} {val:>14.5f}")
    if count >= 10:
        break

# ── 7. SHAP Dependence Analysis (top 5 features) ──
log("\n=== 7. SHAP DEPENDENCE — THRESHOLDS NO-LINEALES ===")

for rank in range(5):
    feat_idx = shap_rank[rank]
    feat_name = top_features[feat_idx]
    feat_vals = X_shap[:, feat_idx]
    feat_shap = shap_values[:, feat_idx]
    
    # Find the threshold where SHAP changes sign
    sorted_idx = np.argsort(feat_vals)
    sorted_vals = feat_vals[sorted_idx]
    sorted_shap = feat_shap[sorted_idx]
    
    # Rolling sign of SHAP
    window = len(sorted_vals) // 10
    rolling_shap = pd.Series(sorted_shap).rolling(window, min_periods=1).mean().values
    
    # Find where rolling_shap crosses zero
    sign_changes = np.where(np.diff(np.sign(rolling_shap)))[0]
    
    if len(sign_changes) > 0:
        # First crossing point
        cross_idx = sign_changes[0]
        threshold_val = sorted_vals[cross_idx]
        
        # SHAP below vs above threshold
        below = feat_shap[feat_vals <= threshold_val]
        above = feat_shap[feat_vals > threshold_val]
        
        log(f"\n  {feat_name}:")
        log(f"    Threshold (SHAP sign change): {threshold_val:.4f}")
        log(f"    SHAP below threshold: mean={below.mean():+.4f} (n={len(below)})")
        log(f"    SHAP above threshold: mean={above.mean():+.4f} (n={len(above)})")
        log(f"    → Feature {'POSITIVA' if above.mean() > below.mean() else 'NEGATIVA'} above threshold")
    else:
        # Monotonic relationship
        q25 = np.percentile(feat_vals, 25)
        q75 = np.percentile(feat_vals, 75)
        low_shap = feat_shap[feat_vals <= q25].mean()
        high_shap = feat_shap[feat_vals >= q75].mean()
        log(f"\n  {feat_name}:")
        log(f"    Relación MONOTÓNICA (sin cruce de zero)")
        log(f"    SHAP en Q25 (val≤{q25:.3f}): {low_shap:+.4f}")
        log(f"    SHAP en Q75 (val≥{q75:.3f}): {high_shap:+.4f}")

# ── 8. SHAP por Arquetipo ──
log("\n=== 8. SHAP POR ARQUETIPO ===")

# Classify test set bars by archetype
dist_col = "dist_zz_5pct"
type_col = "zz_5pct_type"

# For each test ticker, classify archetypes for bars at dist=0
test_df = df.iloc[test_idx].reset_index(drop=True)
shap_test_df = test_df.iloc[shap_idx].reset_index(drop=True)

# Classify archetypes for shap sample
archetypes = []
for tk in shap_test_df["ticker"].unique():
    mask = shap_test_df["ticker"] == tk
    tk_sub = shap_test_df.loc[mask]
    
    # Get full ticker data for archetype classification
    full_mask = df["ticker"] == tk
    full_tk = df.loc[full_mask].reset_index(drop=True)
    
    turn_mask = full_tk[dist_col] == 0
    turn_positions = np.where(turn_mask.values)[0]
    
    prev_min_price = None
    prev_max_price = None
    arch_map = {}
    
    for pos in turn_positions:
        tt = full_tk.at[pos, type_col]
        price = full_tk.at[pos, "price"]
        arch = None
        if tt == "MIN":
            if prev_min_price is not None:
                arch = "HL" if price > prev_min_price else "LL"
            prev_min_price = price
        elif tt == "MAX":
            if prev_max_price is not None:
                arch = "HH" if price > prev_max_price else "LH"
            prev_max_price = price
        if arch:
            ts = full_tk.at[pos, "snapshot_date"]
            arch_map[ts] = arch
    
    # Map to shap sample
    for idx_local in tk_sub.index:
        ts = shap_test_df.at[idx_local, "snapshot_date"]
        dist = shap_test_df.at[idx_local, dist_col]
        # Only classify bars at dist <= 3
        if dist <= 3 and ts in arch_map:
            archetypes.append((idx_local, arch_map[ts]))

# SHAP means by archetype
log(f"\n  Barras clasificadas por arquetipo en sample SHAP: {len(archetypes)}")

arch_shap = defaultdict(list)
for idx_local, arch in archetypes:
    if idx_local < len(shap_values):
        arch_shap[arch].append(shap_values[idx_local])

if arch_shap:
    log(f"\n  {'Feature':<35} {'HH':>10} {'LH':>10} {'HL':>10} {'LL':>10}")
    log(f"  {'─'*35} {'─'*10} {'─'*10} {'─'*10} {'─'*10}")
    
    for rank in range(10):
        feat_idx = shap_rank[rank]
        feat = top_features[feat_idx]
        line = f"  {feat:<35}"
        for arch in ["HH", "LH", "HL", "LL"]:
            if arch in arch_shap and arch_shap[arch]:
                vals = np.array(arch_shap[arch])
                mean_s = vals[:, feat_idx].mean()
                line += f" {mean_s:>+10.4f}"
            else:
                line += f" {'N/A':>10}"
        log(line)
    
    log(f"\n  Samples por arquetipo: " + 
        ", ".join(f"{a}={len(v)}" for a, v in sorted(arch_shap.items())))

# ── 9. Summary ──
log("\n" + "═" * 100)
log("  RESUMEN FASE D")
log("═" * 100)
log(f"\n  XGBoost: AUC={auc:.4f}  P={prec:.3f}  R={rec:.3f}  F1={f1:.3f}")
log(f"  SHAP ranking vs Fase B: Spearman ρ = {rho:.3f} {'✅' if rho > 0.70 else '⚠️'}")
log(f"  Top interaction: {top_interactions[0][0]} × {top_interactions[0][1]} = {top_interactions[0][2]:.5f}")
log(f"  Tiempo total: {time.time()-t0:.1f}s")

# ── 10. Save results ──
results = {
    "model": model,
    "auc": auc, "precision": prec, "recall": rec, "f1": f1,
    "shap_values": shap_values,
    "shap_sample_idx": shap_idx,
    "interaction_values": interaction_values,
    "mean_abs_shap": mean_abs_shap,
    "shap_ranking": shap_ranking,
    "top_interactions": top_interactions,
    "spearman_rho": rho,
    "arch_shap": dict(arch_shap),
    "train_tickers": list(train_tickers),
    "test_tickers": list(test_tickers),
    "top_features": top_features,
}

with open("data/research/feature_lake/sprint2_redo_phase_d_shap.pkl", "wb") as f:
    pickle.dump(results, f)

with open("data/research/feature_lake/sprint2_redo_phase_d_shap.log", "w") as f:
    f.write("\n".join(LOG))

log(f"\n  ✅ Saved: sprint2_redo_phase_d_shap.pkl + .log")
