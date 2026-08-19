"""
Sprint 2-REDO — Fase H: Modelos Separados — Bottoms vs Tops
==============================================================
Dos fenómenos aislados. Sin contaminación.
Step 0: Diagnóstico de ambigüedad + density por grupo
Step 1-3: Modelo PISO (Estrategia A + B)
Step 4-6: Modelo TECHO (Estrategia A + B)
Step 7: Comparación directa SHAP → ¿1 o 2 detectores?
"""

import pandas as pd
import numpy as np
import pickle
import time
import warnings
import xgboost as xgb
import shap
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score
from sklearn.inspection import permutation_importance
from scipy import stats as sp_stats

warnings.filterwarnings("ignore")

LOG = []
def log(msg):
    print(msg)
    LOG.append(msg)

t0 = time.time()

log("═" * 100)
log("  FASE H: MODELOS SEPARADOS — BOTTOMS vs TOPS")
log("═" * 100)

# ── 0. Load ──
df = pd.read_pickle("data/research/feature_lake/sprint2_redo_lake_v21.pkl")
with open("data/research/feature_lake/sprint2_redo_phase_c_v21.pkl", "rb") as f:
    pc = pickle.load(f)

top_features = pc["top_features_used"]
# Add temporal features
temporal_names = [
    "rolling_density_3bar", "rolling_density_5bar", "density_delta_3bar",
    "kf_price_pred_trend_5bar", "rsi_z_trend_5bar", "wave_slope_delta_3bar",
]

X_base = np.nan_to_num(df[top_features].values.astype(np.float32), nan=0.0)
ticker_values = df["ticker"].values

# Build temporal features (same as Phase G)
temporal_features = np.zeros((len(df), 6), dtype=np.float32)
for tk in sorted(df["ticker"].unique()):
    mask = ticker_values == tk
    idx = np.where(mask)[0]
    tk_vals = X_base[idx]
    mu = np.nanmean(tk_vals, axis=0)
    sigma = np.nanstd(tk_vals, axis=0)
    sigma[sigma < 1e-8] = 1
    z = np.abs((tk_vals - mu) / sigma)
    density = (z > 2.0).sum(axis=1).astype(np.float32)
    
    temporal_features[idx, 0] = pd.Series(density).rolling(3, min_periods=1).mean().values
    temporal_features[idx, 1] = pd.Series(density).rolling(5, min_periods=1).mean().values
    dd3 = density - np.roll(density, 3); dd3[:3] = 0
    temporal_features[idx, 2] = dd3
    
    kf_idx = top_features.index("kf_price_pred_val")
    kf_vals = tk_vals[:, kf_idx]
    kf_trend = pd.Series(kf_vals).rolling(5, min_periods=2).apply(
        lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) >= 2 else 0, raw=True).values
    temporal_features[idx, 3] = np.nan_to_num(kf_trend, nan=0.0)
    
    rsi_idx = top_features.index("rsi_value")
    rsi_z = (tk_vals[:, rsi_idx] - mu[rsi_idx]) / sigma[rsi_idx]
    rsi_trend = pd.Series(rsi_z).rolling(5, min_periods=2).apply(
        lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) >= 2 else 0, raw=True).values
    temporal_features[idx, 4] = np.nan_to_num(rsi_trend, nan=0.0)
    
    ws_idx = top_features.index("wave_slope")
    ws_delta = tk_vals[:, ws_idx] - np.roll(tk_vals[:, ws_idx], 3)
    ws_delta[:3] = 0
    temporal_features[idx, 5] = ws_delta

X_all = np.hstack([X_base, temporal_features])
all_features = top_features + temporal_names
log(f"  Data: {X_all.shape[0]:,} × {X_all.shape[1]} ({len(top_features)} base + {len(temporal_names)} temporal)")

# ══════════════════════════════════════════════════════════
# PASO 0: DIAGNÓSTICO
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  PASO 0: DIAGNÓSTICO — AMBIGÜEDAD Y DENSITY POR GRUPO")
log("═" * 100)

# Build per-bar labels: which turn type is nearest
y_bottom = np.zeros(len(df), dtype=int)
y_top = np.zeros(len(df), dtype=int)
dist_vals = df["dist_zz_5pct"].values
type_vals = df["zz_5pct_type"].values

for tk in sorted(df["ticker"].unique()):
    mask = ticker_values == tk
    idx = np.where(mask)[0]
    dist = dist_vals[idx]
    tt = type_vals[idx]
    
    # Forward pass
    last_type, last_pos = None, -999
    for i in range(len(idx)):
        if dist[i] == 0:
            last_type = tt[i]
            last_pos = i
        if dist[i] <= 3 and last_type is not None and abs(i - last_pos) <= 3:
            if last_type == "MIN": y_bottom[idx[i]] = 1
            elif last_type == "MAX": y_top[idx[i]] = 1
    
    # Backward pass
    next_type, next_pos = None, 999999
    for i in range(len(idx)-1, -1, -1):
        if dist[i] == 0:
            next_type = tt[i]
            next_pos = i
        if dist[i] <= 3 and next_type is not None and abs(i - next_pos) <= 3:
            if next_type == "MIN": y_bottom[idx[i]] = 1
            elif next_type == "MAX": y_top[idx[i]] = 1

# Ambiguity check
both = (y_bottom == 1) & (y_top == 1)
only_bottom = (y_bottom == 1) & (y_top == 0)
only_top = (y_top == 1) & (y_bottom == 0)
neither = (y_bottom == 0) & (y_top == 0)

log(f"\n  Barras near-Bottom SOLO:   {only_bottom.sum():,}")
log(f"  Barras near-Top SOLO:      {only_top.sum():,}")
log(f"  Barras AMBIGUAS (ambos):   {both.sum():,} ({both.sum()/len(df)*100:.1f}%)")
log(f"  Barras lejos de todo:      {neither.sum():,}")
log(f"  → Ambigüedad: {'✅ < 5%, aceptable' if both.mean() < 0.05 else '⚠️ Alta'}")

# Density by group
log(f"\n  Density (rolling_density_3bar) por grupo:")
rd3 = temporal_features[:, 0]
for label, mask in [("Near-Bottom", only_bottom), ("Near-Top", only_top), 
                     ("Ambiguous", both), ("Far (negativo)", neither)]:
    if mask.sum() > 0:
        vals = rd3[mask]
        log(f"    {label:<20}: μ={vals.mean():.3f}  σ={vals.std():.3f}  mediana={np.median(vals):.3f}  n={mask.sum():,}")

# ══════════════════════════════════════════════════════════
# PurgedKFold (positional indices)
# ══════════════════════════════════════════════════════════
def purged_kfold(df, n_folds=5, embargo=10):
    folds = [[] for _ in range(n_folds)]
    tv = df["ticker"].values
    for tk in sorted(df["ticker"].unique()):
        positions = np.where(tv == tk)[0]
        n = len(positions)
        fold_size = n // n_folds
        for fi in range(n_folds):
            s = fi * fold_size
            e = s + fold_size if fi < n_folds - 1 else n
            folds[fi].extend(positions[s:e].tolist())
    
    for tf in range(n_folds):
        test_idx = np.array(folds[tf])
        train_cand = []
        for fi in range(n_folds):
            if fi != tf: train_cand.extend(folds[fi])
        train_cand = np.array(train_cand)
        
        test_tk = tv[test_idx]
        train_tk = tv[train_cand]
        purged = []
        for tk in sorted(df["ticker"].unique()):
            mt = test_tk == tk
            mr = train_tk == tk
            if not mt.any() or not mr.any():
                purged.extend(train_cand[mr].tolist())
                continue
            tp = test_idx[mt]
            rp = train_cand[mr]
            ap = np.where(tv == tk)[0]
            emb = set()
            for p in tp:
                r = np.searchsorted(ap, p)
                for e in range(-embargo, embargo+1):
                    rr = r + e
                    if 0 <= rr < len(ap): emb.add(ap[rr])
            for p in rp:
                if p not in emb: purged.append(p)
        yield np.array(purged), test_idx

# ══════════════════════════════════════════════════════════
# Helper: train + evaluate a model
# ══════════════════════════════════════════════════════════
def run_model(X, y, df, label, do_shap=True, do_perm=True):
    """Train XGBoost with PurgedKFold, SHAP, Permutation."""
    log(f"\n{'─'*80}")
    log(f"  {label}")
    log(f"{'─'*80}")
    log(f"  Positivos: {y.sum():,} ({y.mean()*100:.1f}%)")
    
    # PurgedKFold
    results = []
    all_shap = None
    all_shap_X = None
    
    for fi, (tr, te) in enumerate(purged_kfold(df)):
        X_tr, X_te = X[tr], X[te]
        y_tr, y_te = y[tr], y[te]
        
        if y_te.sum() == 0 or y_tr.sum() == 0:
            log(f"  Fold {fi+1}: SKIPPED (no positives)")
            continue
        
        m = xgb.XGBClassifier(
            n_estimators=150, max_depth=5, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8,
            scale_pos_weight=(y_tr==0).sum() / max((y_tr==1).sum(), 1),
            random_state=42, eval_metric="logloss", verbosity=0,
            min_child_weight=5, gamma=0.1,  # Extra regularization
        )
        m.fit(X_tr, y_tr)
        yp = m.predict_proba(X_te)[:, 1]
        ypred = m.predict(X_te)
        
        auc = roc_auc_score(y_te, yp)
        prec = precision_score(y_te, ypred)
        rec = recall_score(y_te, ypred)
        f1 = f1_score(y_te, ypred)
        
        # Train AUC for overfitting check
        yp_tr = m.predict_proba(X_tr)[:, 1]
        auc_tr = roc_auc_score(y_tr, yp_tr)
        gap = auc_tr - auc
        
        results.append({"fold": fi+1, "auc": auc, "auc_train": auc_tr, "gap": gap,
                        "prec": prec, "rec": rec, "f1": f1})
        log(f"  Fold {fi+1}: AUC={auc:.4f} (train={auc_tr:.4f} gap={gap:.3f}) P={prec:.3f} R={rec:.3f} F1={f1:.3f}")
    
    auc_mean = np.mean([r["auc"] for r in results])
    auc_std = np.std([r["auc"] for r in results])
    gap_mean = np.mean([r["gap"] for r in results])
    log(f"\n  AUC: {auc_mean:.4f} ± {auc_std:.4f}  (gap train-test: {gap_mean:.3f})")
    
    # Final model for SHAP + Perm
    m_final = xgb.XGBClassifier(
        n_estimators=150, max_depth=5, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=(y==0).sum() / max((y==1).sum(), 1),
        random_state=42, eval_metric="logloss", verbosity=0,
        min_child_weight=5, gamma=0.1,
    )
    split = int(len(X) * 0.8)
    m_final.fit(X[:split], y[:split])
    
    # SHAP
    shap_ranking = {}
    mean_abs_shap = None
    if do_shap:
        explainer = shap.TreeExplainer(m_final)
        shap_n = min(3000, len(X) - split)
        sv = explainer.shap_values(X[split:split+shap_n])
        mean_abs_shap = np.abs(sv).mean(axis=0)
        sr = np.argsort(-mean_abs_shap)
        
        log(f"\n  SHAP Top 15:")
        log(f"  {'Rank':>4} {'Feature':<35} {'|SHAP|':>10}")
        log(f"  {'─'*4} {'─'*35} {'─'*10}")
        for rank in range(min(15, len(all_features))):
            idx = sr[rank]
            feat = all_features[idx]
            shap_ranking[feat] = rank + 1
            marker = " ★TEMP" if feat in temporal_names else ""
            log(f"  {rank+1:>4} {feat:<35} {mean_abs_shap[idx]:>10.4f}{marker}")
    
    # Permutation importance
    perm_ranking = {}
    if do_perm:
        X_te_perm = X[split:]
        y_te_perm = y[split:]
        if y_te_perm.sum() > 0:
            pr = permutation_importance(m_final, X_te_perm, y_te_perm,
                                       n_repeats=30, random_state=42, scoring="roc_auc", n_jobs=1)
            pr_rank = np.argsort(-pr.importances_mean)
            
            log(f"\n  Permutation Top 15:")
            log(f"  {'Rank':>4} {'Feature':<35} {'Perm':>10} {'Ess':>5}")
            log(f"  {'─'*4} {'─'*35} {'─'*10} {'─'*5}")
            for rank in range(min(15, len(all_features))):
                idx = pr_rank[rank]
                feat = all_features[idx]
                imp = pr.importances_mean[idx]
                perm_ranking[feat] = rank + 1
                ess = "✅" if imp > 0.003 else "❌"
                log(f"  {rank+1:>4} {feat:<35} {imp:>10.5f} {ess:>5}")
    
    return {
        "auc_mean": auc_mean, "auc_std": auc_std, "gap_mean": gap_mean,
        "results": results, "shap_ranking": shap_ranking, "perm_ranking": perm_ranking,
        "mean_abs_shap": mean_abs_shap,
    }

# ══════════════════════════════════════════════════════════
# PASO 1-3: MODELO PISO
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  MODELO PISO (Bottoms)")
log("═" * 100)

# Estrategia A: Tops son negativos
y_piso_a = only_bottom.astype(int)  # Ambiguous bars excluded from positive
log("\n  === ESTRATEGIA A: Tops son negativos ===")
res_piso_a = run_model(X_all, y_piso_a, df, "PISO — Estrategia A (Tops = negativos)")

# Estrategia B: Tops excluidos
mask_b_piso = ~only_top  # Exclude bars that are ONLY near a top
X_piso_b = X_all[mask_b_piso]
y_piso_b = y_bottom[mask_b_piso]
df_piso_b = df.iloc[np.where(mask_b_piso)[0]].reset_index(drop=True)
log("\n  === ESTRATEGIA B: Tops excluidos ===")
res_piso_b = run_model(X_piso_b, y_piso_b, df_piso_b, "PISO — Estrategia B (Tops excluidos)")

# ══════════════════════════════════════════════════════════
# PASO 4-6: MODELO TECHO
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  MODELO TECHO (Tops)")
log("═" * 100)

# Estrategia A: Bottoms son negativos
y_techo_a = only_top.astype(int)
log("\n  === ESTRATEGIA A: Bottoms son negativos ===")
res_techo_a = run_model(X_all, y_techo_a, df, "TECHO — Estrategia A (Bottoms = negativos)")

# Estrategia B: Bottoms excluidos
mask_b_techo = ~only_bottom
X_techo_b = X_all[mask_b_techo]
y_techo_b = y_top[mask_b_techo]
df_techo_b = df.iloc[np.where(mask_b_techo)[0]].reset_index(drop=True)
log("\n  === ESTRATEGIA B: Bottoms excluidos ===")
res_techo_b = run_model(X_techo_b, y_techo_b, df_techo_b, "TECHO — Estrategia B (Bottoms excluidos)")

# ══════════════════════════════════════════════════════════
# PASO 7: COMPARACIÓN DIRECTA
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  COMPARACIÓN DIRECTA: PISO vs TECHO")
log("═" * 100)

# Compare SHAP rankings (Estrategia A)
if res_piso_a["mean_abs_shap"] is not None and res_techo_a["mean_abs_shap"] is not None:
    shap_piso = res_piso_a["mean_abs_shap"]
    shap_techo = res_techo_a["mean_abs_shap"]
    
    # Spearman between rankings
    rank_piso = np.argsort(-shap_piso)
    rank_techo = np.argsort(-shap_techo)
    
    piso_ranks = [list(rank_piso).index(i) for i in range(len(rank_piso))]
    techo_ranks = [list(rank_techo).index(i) for i in range(len(rank_techo))]
    rho, p_rho = sp_stats.spearmanr(piso_ranks, techo_ranks)
    
    log(f"\n  Spearman ρ (SHAP PISO vs TECHO): {rho:.3f} (p={p_rho:.2e})")
    
    if rho > 0.70:
        log(f"  → ESCENARIO A: Un solo detector basta (rankings similares)")
    elif rho > 0.30:
        log(f"  → ESCENARIO B: Un detector base + ajuste por tipo")
    else:
        log(f"  → ESCENARIO C: Dos detectores completamente distintos")
    
    # Feature comparison table
    log(f"\n  {'Feature':<35} {'SHAP_Piso':>10} {'Rank_P':>7} {'SHAP_Techo':>11} {'Rank_T':>7} {'Δ Rank':>7} {'Interpretación':<20}")
    log(f"  {'─'*35} {'─'*10} {'─'*7} {'─'*11} {'─'*7} {'─'*7} {'─'*20}")
    
    combined_rank = np.argsort(-(shap_piso + shap_techo))
    for i in range(min(20, len(all_features))):
        idx = combined_rank[i]
        feat = all_features[idx]
        sp = shap_piso[idx]
        st = shap_techo[idx]
        rp = piso_ranks[idx] + 1
        rt = techo_ranks[idx] + 1
        delta = rp - rt
        
        if abs(delta) <= 3:
            interp = "UNIVERSAL"
        elif delta > 5:
            interp = "★ TECHO"
        elif delta < -5:
            interp = "★ PISO"
        else:
            interp = "~similar"
        
        log(f"  {feat:<35} {sp:>10.4f} {rp:>7} {st:>11.4f} {rt:>7} {delta:>+7} {interp:<20}")

# ══════════════════════════════════════════════════════════
# PASO 8: CICLO DE VIDA — PRECURSOR → APPROACH → INFLECTION → PROPAGATION
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  PASO 8: CICLO DE VIDA DE LA SEÑAL — ¿El modelo de 4 fases aplica a ambos?")
log("═" * 100)
log("  PRECURSOR (t-10..t-4) → APPROACH (t-3..t-1) → INFLECTION (t=0) → PROPAGATION (t+1..t+3)")

# For each turn type, compute density by phase
for turn_label, turn_type in [("PISO (MIN)", "MIN"), ("TECHO (MAX)", "MAX")]:
    log(f"\n  === {turn_label} ===")
    
    phase_density = {"PRECURSOR": [], "APPROACH": [], "INFLECTION": [], "PROPAGATION": []}
    phase_kf_trend = {"PRECURSOR": [], "APPROACH": [], "INFLECTION": [], "PROPAGATION": []}
    
    for tk in sorted(df["ticker"].unique()):
        mask = ticker_values == tk
        idx = np.where(mask)[0]
        dist = dist_vals[idx]
        tt = type_vals[idx]
        
        # Find turns of this type
        turns = np.where((dist == 0) & (tt == turn_type))[0]
        
        for t_pos in turns:
            for phase, lo, hi in [("PRECURSOR", -10, -4), ("APPROACH", -3, -1),
                                   ("INFLECTION", 0, 0), ("PROPAGATION", 1, 3)]:
                for offset in range(lo, hi + 1):
                    bar_pos = t_pos + offset
                    if 0 <= bar_pos < len(idx):
                        global_pos = idx[bar_pos]
                        phase_density[phase].append(rd3[global_pos])
                        phase_kf_trend[phase].append(temporal_features[global_pos, 3])
    
    log(f"\n  {'Fase':<15} {'Density μ':>10} {'Density med':>12} {'KF_trend μ':>11} {'n':>8}")
    log(f"  {'─'*15} {'─'*10} {'─'*12} {'─'*11} {'─'*8}")
    
    vals_by_phase = {}
    for phase in ["PRECURSOR", "APPROACH", "INFLECTION", "PROPAGATION"]:
        d = np.array(phase_density[phase])
        k = np.array(phase_kf_trend[phase])
        vals_by_phase[phase] = d.mean()
        log(f"  {phase:<15} {d.mean():>10.3f} {np.median(d):>12.3f} {k.mean():>11.4f} {len(d):>8,}")
    
    # Check: is it CRESCENDO (increasing) or PLANO (flat)?
    prec = vals_by_phase["PRECURSOR"]
    infl = vals_by_phase["INFLECTION"]
    ramp = infl - prec
    log(f"\n  Ramp (INFLECTION - PRECURSOR): {ramp:+.3f}")
    if ramp > 0.3:
        log(f"  → ✅ CRESCENDO: densidad CRECE hacia el giro")
    elif ramp < -0.1:
        log(f"  → 🔻 DECRESCENDO: densidad BAJA hacia el giro")
    else:
        log(f"  → ➖ PLANO: densidad estable, NO hay presurización")

# ══════════════════════════════════════════════════════════
# PASO 9: NIVELES DE ACTIVACIÓN — ALARMA → PRESURIZACIÓN → EXPLOSIÓN
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  PASO 9: NIVELES DE ACTIVACIÓN — ¿Los thresholds funcionan igual?")
log("═" * 100)

# Compute point-in-time density for each bar (not rolling — instant z-score count)
instant_density = np.zeros(len(df), dtype=np.float32)
for tk in sorted(df["ticker"].unique()):
    mask = ticker_values == tk
    idx = np.where(mask)[0]
    tk_vals = X_base[idx]
    mu = np.nanmean(tk_vals, axis=0)
    sigma = np.nanstd(tk_vals, axis=0)
    sigma[sigma < 1e-8] = 1
    z = np.abs((tk_vals - mu) / sigma)
    instant_density[idx] = (z > 2.0).sum(axis=1).astype(np.float32)

for turn_label, turn_type in [("PISO (MIN)", "MIN"), ("TECHO (MAX)", "MAX")]:
    log(f"\n  === {turn_label}: Density en t=0 ===")
    
    at_turn_mask = (dist_vals == 0) & (type_vals == turn_type)
    turn_density = instant_density[at_turn_mask]
    far_density = instant_density[dist_vals > 10]
    
    log(f"  {'Nivel':<20} {'Threshold':>10} {'% en giro':>10} {'% lejos':>10} {'LIFT':>8}")
    log(f"  {'─'*20} {'─'*10} {'─'*10} {'─'*10} {'─'*8}")
    
    for level, thr in [("ALARMA", 2), ("PRESURIZACIÓN", 5), ("EXPLOSIÓN", 8)]:
        pct_turn = (turn_density >= thr).mean() * 100
        pct_far = (far_density >= thr).mean() * 100
        lift = pct_turn / max(pct_far, 0.01)
        marker = "✅" if lift > 2.0 else "⚠️" if lift > 1.5 else "❌"
        log(f"  {level:<20} {thr:>10} {pct_turn:>9.1f}% {pct_far:>9.1f}% {lift:>7.1f}x {marker}")
    
    # Distribution stats
    log(f"\n  Density stats: μ={turn_density.mean():.2f}  med={np.median(turn_density):.1f}  "
        f"p25={np.percentile(turn_density,25):.1f}  p75={np.percentile(turn_density,75):.1f}  "
        f"max={turn_density.max():.0f}")

# Summary table
log("\n" + "═" * 100)
log("  RESUMEN FINAL")
log("═" * 100)

log(f"\n  {'Modelo':<40} {'AUC':>8} {'±':>6} {'Gap':>6}")
log(f"  {'─'*40} {'─'*8} {'─'*6} {'─'*6}")
log(f"  {'MEZCLADO (Fase F)':                  <40} {'0.7245':>8} {'0.029':>6} {'—':>6}")
log(f"  {'PISO — Tops negativos (A)':          <40} {res_piso_a['auc_mean']:>8.4f} {res_piso_a['auc_std']:>6.3f} {res_piso_a['gap_mean']:>6.3f}")
log(f"  {'PISO — Tops excluidos (B)':          <40} {res_piso_b['auc_mean']:>8.4f} {res_piso_b['auc_std']:>6.3f} {res_piso_b['gap_mean']:>6.3f}")
log(f"  {'TECHO — Bottoms negativos (A)':      <40} {res_techo_a['auc_mean']:>8.4f} {res_techo_a['auc_std']:>6.3f} {res_techo_a['gap_mean']:>6.3f}")
log(f"  {'TECHO — Bottoms excluidos (B)':      <40} {res_techo_b['auc_mean']:>8.4f} {res_techo_b['auc_std']:>6.3f} {res_techo_b['gap_mean']:>6.3f}")

log(f"\n  Tiempo total: {time.time()-t0:.1f}s")

# Save
results = {
    "piso_a": res_piso_a, "piso_b": res_piso_b,
    "techo_a": res_techo_a, "techo_b": res_techo_b,
    "diagnostics": {
        "n_only_bottom": int(only_bottom.sum()),
        "n_only_top": int(only_top.sum()),
        "n_ambiguous": int(both.sum()),
        "n_far": int(neither.sum()),
    },
    "all_features": all_features,
    "spearman_rho": rho if res_piso_a["mean_abs_shap"] is not None else None,
}

with open("data/research/feature_lake/sprint2_redo_phase_h_separated.pkl", "wb") as f:
    pickle.dump(results, f)

with open("data/research/feature_lake/sprint2_redo_phase_h_separated.log", "w") as f:
    f.write("\n".join(LOG))

log(f"\n  ✅ Saved: sprint2_redo_phase_h_separated.pkl + .log")
