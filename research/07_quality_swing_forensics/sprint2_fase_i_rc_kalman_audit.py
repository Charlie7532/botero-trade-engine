"""
Sprint 2-REDO — Fase I: Auditoría de Conexión RC ↔ Kalman
===========================================================
¿Las slopes del Regression Channel están siendo INTERPRETADAS por
el Kalman o quedan DESCONECTADAS?

Análisis:
  1. SHAP de RC slopes vs Kalman-conjugation en modelo PISO y TECHO
  2. Correlación cruzada entre slopes crudas y features Kalman
  3. Ablation test: {Kalman full} vs {Kalman full + 3 slopes crudas}
  4. Dirección: ¿el Kalman captura velocidad pero pierde dirección absoluta?
"""

import pandas as pd
import numpy as np
import pickle
import time
import warnings
import xgboost as xgb
import shap
from sklearn.metrics import roc_auc_score
from scipy import stats as sp_stats

warnings.filterwarnings("ignore")

LOG = []
def log(msg):
    print(msg, flush=True)
    LOG.append(msg)

t0 = time.time()

log("═" * 100)
log("  FASE I: AUDITORÍA DE CONEXIÓN RC ↔ KALMAN")
log("═" * 100)

# ── 0. Load data ──
df = pd.read_pickle("data/research/feature_lake/sprint2_redo_lake_v21.pkl")
with open("data/research/feature_lake/sprint2_redo_phase_c_v21.pkl", "rb") as f:
    pc = pickle.load(f)
with open("data/research/feature_lake/sprint2_redo_phase_h_separated.pkl", "rb") as f:
    ph = pickle.load(f)

top_features = pc["top_features_used"]
all_features = ph["all_features"]
ticker_values = df["ticker"].values

log(f"  Lake: {len(df):,} rows × {len(all_features)} features")

# ══════════════════════════════════════════════════════════
# STEP 1: Identify RC and Kalman feature groups
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 1: FEATURE GROUPS — RC vs KALMAN")
log("═" * 100)

# RC slope features (raw regression channel slopes)
rc_slope_features = [f for f in all_features if f in [
    'tide_slope', 'current_slope', 'wave_slope',
    'tide_accel', 'current_accel', 'wave_accel',
    'conj_wave_current', 'conj_wave_tide', 'conj_current_tide',
]]

# Kalman conjugation features (Kalman filtered version of conj_wave_tide)
kf_conj_features = [f for f in all_features if f.startswith('kf_conjugation')]

# All Kalman features
kf_all_features = [f for f in all_features if f.startswith('kf_')]

# Sigma features (position within regression channel)
sigma_features = [f for f in all_features if f.startswith('sigma_') or f.startswith('vwap_sigma_')]

log(f"\n  RC Slope features ({len(rc_slope_features)}): {rc_slope_features}")
log(f"  Kalman Conjugation features ({len(kf_conj_features)}): {kf_conj_features}")
log(f"  All Kalman features ({len(kf_all_features)}): {', '.join(kf_all_features[:10])}...")
log(f"  Sigma features ({len(sigma_features)}): {sigma_features}")

# ══════════════════════════════════════════════════════════
# STEP 2: SHAP rankings from Phase H — where do RC features land?
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 2: SHAP RANKINGS — RC vs KALMAN en Modelo PISO y TECHO")
log("═" * 100)

for model_name, model_key in [("PISO", "piso_a"), ("TECHO", "techo_a")]:
    shap_vals = ph[model_key]["mean_abs_shap"]
    if shap_vals is None:
        log(f"\n  {model_name}: No SHAP data available")
        continue
    
    # Build ranking
    sorted_idx = np.argsort(-shap_vals)
    ranking = {all_features[sorted_idx[i]]: (i+1, shap_vals[sorted_idx[i]]) 
               for i in range(len(sorted_idx))}
    
    log(f"\n  === {model_name} ===")
    log(f"  {'Feature':<35} {'SHAP |value|':>12} {'Rank':>6} {'Group':<15}")
    log(f"  {'─'*35} {'─'*12} {'─'*6} {'─'*15}")
    
    # Show all RC and Kalman features
    target_features = rc_slope_features + kf_conj_features + ['kf_rsi_pred_val', 'kf_price_pred_val', 'kf_price_filt_vel']
    target_features = [f for f in target_features if f in ranking]
    target_features.sort(key=lambda f: ranking[f][0])
    
    for feat in target_features:
        rank, shap_v = ranking[feat]
        if feat in rc_slope_features:
            group = "RC-SLOPE"
        elif feat in kf_conj_features:
            group = "KF-CONJUGATION"
        else:
            group = "KF-OTHER"
        
        marker = "★" if rank <= 15 else " "
        log(f"  {marker} {feat:<33} {shap_v:>12.4f} {rank:>6} {group:<15}")

# ══════════════════════════════════════════════════════════
# STEP 3: CORRELATION — Do Kalman features subsume RC slopes?
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 3: CORRELACIÓN CRUZADA — ¿El Kalman subsume las slopes?")
log("═" * 100)

# Get all feature values
X_base = np.nan_to_num(df[top_features].values.astype(np.float32), nan=0.0)

# Build correlation matrix between RC slopes and Kalman features
rc_in_top = [f for f in rc_slope_features if f in top_features]
kf_in_top = [f for f in kf_all_features if f in top_features]

log(f"\n  RC features in lake: {len(rc_in_top)}")
log(f"  Kalman features in lake: {len(kf_in_top)}")

# Correlation table
log(f"\n  {'RC Feature':<25} {'Kalman Feature':<35} {'Pearson r':>10} {'Interpretation':<20}")
log(f"  {'─'*25} {'─'*35} {'─'*10} {'─'*20}")

correlations = []
for rc_f in rc_in_top:
    rc_idx = top_features.index(rc_f)
    rc_vals = X_base[:, rc_idx]
    
    best_kf = None
    best_r = 0
    for kf_f in kf_in_top:
        kf_idx = top_features.index(kf_f)
        kf_vals = X_base[:, kf_idx]
        r = np.corrcoef(rc_vals, kf_vals)[0, 1]
        if abs(r) > abs(best_r):
            best_r = r
            best_kf = kf_f
    
    if best_kf:
        if abs(best_r) > 0.80:
            interp = "SUBSUMED"
        elif abs(best_r) > 0.50:
            interp = "PARTIAL overlap"
        elif abs(best_r) > 0.30:
            interp = "COMPLEMENTARY"
        else:
            interp = "INDEPENDENT"
        correlations.append((rc_f, best_kf, best_r, interp))
        log(f"  {rc_f:<25} {best_kf:<35} {best_r:>10.3f} {interp:<20}")

# Key question: does conj_wave_tide correlate with kf_conjugation_pred_val?
if 'conj_wave_tide' in top_features and 'kf_conjugation_pred_val' in top_features:
    cwt_idx = top_features.index('conj_wave_tide')
    kcp_idx = top_features.index('kf_conjugation_pred_val')
    r_cwt_kcp = np.corrcoef(X_base[:, cwt_idx], X_base[:, kcp_idx])[0, 1]
    log(f"\n  ★ conj_wave_tide × kf_conjugation_pred_val: r = {r_cwt_kcp:.4f}")
    log(f"    → El Kalman de conjugation {'ABSORBE' if abs(r_cwt_kcp) > 0.80 else 'TRANSFORMA' if abs(r_cwt_kcp) > 0.50 else 'COMPLEMENTA'} la slope cruda")

# Also check: does tide_slope sign (direction) correlate with any Kalman feature?
if 'tide_slope' in top_features:
    ts_idx = top_features.index('tide_slope')
    tide_sign = np.sign(X_base[:, ts_idx])  # +1 = bull, -1 = bear
    log(f"\n  Tide slope sign distribution: +1 (bull) = {(tide_sign > 0).mean()*100:.1f}%, "
        f"-1 (bear) = {(tide_sign < 0).mean()*100:.1f}%, 0 = {(tide_sign == 0).mean()*100:.1f}%")
    
    for kf_f in ['kf_conjugation_pred_val', 'kf_conjugation_filt_vel', 'kf_rsi_pred_val']:
        if kf_f in top_features:
            kf_idx = top_features.index(kf_f)
            r_sign = np.corrcoef(tide_sign, X_base[:, kf_idx])[0, 1]
            log(f"    tide_slope_SIGN × {kf_f}: r = {r_sign:.4f}"
                f" → {'CAPTURES direction' if abs(r_sign) > 0.30 else 'IGNORES direction'}")

# ══════════════════════════════════════════════════════════
# STEP 4: ABLATION — Do slopes add marginal information?
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 4: ABLATION TEST — ¿Las slopes aportan más allá del Kalman?")
log("═" * 100)

# Build temporal features (identical to Phase H)
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
temporal_names = ["rolling_density_3bar", "rolling_density_5bar", "density_delta_3bar",
                  "kf_price_pred_trend_5bar", "rsi_z_trend_5bar", "wave_slope_delta_3bar"]
all_feature_names = top_features + temporal_names

# Build labels (same as Phase H)
y_bottom = np.zeros(len(df), dtype=int)
y_top = np.zeros(len(df), dtype=int)
dist_vals = df["dist_zz_5pct"].values
type_vals = df["zz_5pct_type"].values

for tk in sorted(df["ticker"].unique()):
    mask = ticker_values == tk
    idx = np.where(mask)[0]
    dist = dist_vals[idx]
    tt = type_vals[idx]
    
    last_type, last_pos = None, -999
    for i in range(len(idx)):
        if dist[i] == 0:
            last_type = tt[i]
            last_pos = i
        if dist[i] <= 3 and last_type is not None and abs(i - last_pos) <= 3:
            if last_type == "MIN": y_bottom[idx[i]] = 1
            elif last_type == "MAX": y_top[idx[i]] = 1
    
    next_type, next_pos = None, 999999
    for i in range(len(idx)-1, -1, -1):
        if dist[i] == 0:
            next_type = tt[i]
            next_pos = i
        if dist[i] <= 3 and next_type is not None and abs(i - next_pos) <= 3:
            if next_type == "MIN": y_bottom[idx[i]] = 1
            elif next_type == "MAX": y_top[idx[i]] = 1

only_bottom = (y_bottom == 1) & (y_top == 0)
only_top = (y_top == 1) & (y_bottom == 0)

# PurgedKFold
def purged_kfold(df_in, n_folds=5, embargo=10):
    tv = df_in["ticker"].values
    folds = [[] for _ in range(n_folds)]
    for tk in sorted(df_in["ticker"].unique()):
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
        for tk in sorted(df_in["ticker"].unique()):
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


def eval_auc_purged(X, y, df_in, label):
    """Quick AUC evaluation with PurgedKFold."""
    aucs = []
    for fi, (tr, te) in enumerate(purged_kfold(df_in)):
        X_tr, X_te = X[tr], X[te]
        y_tr, y_te = y[tr], y[te]
        if y_te.sum() == 0 or y_tr.sum() == 0:
            continue
        m = xgb.XGBClassifier(
            n_estimators=150, max_depth=5, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8,
            scale_pos_weight=(y_tr==0).sum() / max((y_tr==1).sum(), 1),
            random_state=42, eval_metric="logloss", verbosity=0,
            min_child_weight=5, gamma=0.1,
        )
        m.fit(X_tr, y_tr)
        yp = m.predict_proba(X_te)[:, 1]
        aucs.append(roc_auc_score(y_te, yp))
    return np.mean(aucs), np.std(aucs)

# Define feature subsets for ablation
kalman_indices = [i for i, f in enumerate(all_feature_names) if f.startswith('kf_')]
rc_slope_indices = [i for i, f in enumerate(all_feature_names) if f in rc_slope_features]
temporal_indices = [i for i, f in enumerate(all_feature_names) if f in temporal_names]

# Create direction feature: sign of tide_slope
tide_slope_idx = top_features.index('tide_slope') if 'tide_slope' in top_features else None
if tide_slope_idx is not None:
    tide_direction = np.sign(X_base[:, tide_slope_idx]).reshape(-1, 1).astype(np.float32)

log(f"\n  Feature subsets:")
log(f"    Kalman features: {len(kalman_indices)} indices")
log(f"    RC slope features: {len(rc_slope_indices)} indices")
log(f"    Temporal features: {len(temporal_indices)} indices")

# Ablation tests for PISO model
y_piso = only_bottom.astype(int)

log(f"\n  --- ABLATION: MODELO PISO ---")
log(f"  Positivos: {y_piso.sum():,} ({y_piso.mean()*100:.1f}%)")

# Test A: Full model (baseline from Phase H)
log(f"\n  Test A: Full model (all {X_all.shape[1]} features) — baseline")
auc_full, std_full = eval_auc_purged(X_all, y_piso, df, "Full")
log(f"    AUC = {auc_full:.4f} ± {std_full:.4f}")

# Test B: Only Kalman features
X_kf_only = X_all[:, kalman_indices]
log(f"\n  Test B: Only Kalman ({len(kalman_indices)} features)")
auc_kf, std_kf = eval_auc_purged(X_kf_only, y_piso, df, "Kalman-only")
log(f"    AUC = {auc_kf:.4f} ± {std_kf:.4f}")

# Test C: Kalman + RC slopes  
kf_rc_indices = sorted(set(kalman_indices + rc_slope_indices))
X_kf_rc = X_all[:, kf_rc_indices]
log(f"\n  Test C: Kalman + RC slopes ({len(kf_rc_indices)} features)")
auc_kf_rc, std_kf_rc = eval_auc_purged(X_kf_rc, y_piso, df, "Kalman+RC")
log(f"    AUC = {auc_kf_rc:.4f} ± {std_kf_rc:.4f}")

# Test D: Kalman + tide_slope_sign (direction only)
if tide_slope_idx is not None:
    X_kf_dir = np.hstack([X_all[:, kalman_indices], tide_direction])
    log(f"\n  Test D: Kalman + tide_slope SIGN ({len(kalman_indices)+1} features)")
    auc_kf_dir, std_kf_dir = eval_auc_purged(X_kf_dir, y_piso, df, "Kalman+Direction")
    log(f"    AUC = {auc_kf_dir:.4f} ± {std_kf_dir:.4f}")

# Summary table
log(f"\n  {'Test':<35} {'AUC':>8} {'±':>6} {'Δ vs Kalman':>12}")
log(f"  {'─'*35} {'─'*8} {'─'*6} {'─'*12}")
log(f"  {'A: Full model (baseline)':<35} {auc_full:>8.4f} {std_full:>6.4f} {auc_full-auc_kf:>+12.4f}")
log(f"  {'B: Only Kalman':<35} {auc_kf:>8.4f} {std_kf:>6.4f} {'(base)':>12}")
log(f"  {'C: Kalman + RC slopes':<35} {auc_kf_rc:>8.4f} {std_kf_rc:>6.4f} {auc_kf_rc-auc_kf:>+12.4f}")
if tide_slope_idx is not None:
    log(f"  {'D: Kalman + tide_sign':<35} {auc_kf_dir:>8.4f} {std_kf_dir:>6.4f} {auc_kf_dir-auc_kf:>+12.4f}")

# ══════════════════════════════════════════════════════════
# STEP 5: Same ablation for TECHO
# ══════════════════════════════════════════════════════════
y_techo = only_top.astype(int)

log(f"\n  --- ABLATION: MODELO TECHO ---")
log(f"  Positivos: {y_techo.sum():,} ({y_techo.mean()*100:.1f}%)")

log(f"\n  Test A: Full model")
auc_full_t, std_full_t = eval_auc_purged(X_all, y_techo, df, "Full-Techo")
log(f"    AUC = {auc_full_t:.4f} ± {std_full_t:.4f}")

log(f"\n  Test B: Only Kalman")
auc_kf_t, std_kf_t = eval_auc_purged(X_kf_only, y_techo, df, "Kalman-only-Techo")
log(f"    AUC = {auc_kf_t:.4f} ± {std_kf_t:.4f}")

log(f"\n  Test C: Kalman + RC slopes")
auc_kf_rc_t, std_kf_rc_t = eval_auc_purged(X_kf_rc, y_techo, df, "Kalman+RC-Techo")
log(f"    AUC = {auc_kf_rc_t:.4f} ± {std_kf_rc_t:.4f}")

if tide_slope_idx is not None:
    log(f"\n  Test D: Kalman + tide_slope SIGN")
    auc_kf_dir_t, std_kf_dir_t = eval_auc_purged(X_kf_dir, y_techo, df, "Kalman+Dir-Techo")
    log(f"    AUC = {auc_kf_dir_t:.4f} ± {std_kf_dir_t:.4f}")

log(f"\n  {'Test':<35} {'AUC':>8} {'±':>6} {'Δ vs Kalman':>12}")
log(f"  {'─'*35} {'─'*8} {'─'*6} {'─'*12}")
log(f"  {'A: Full model (baseline)':<35} {auc_full_t:>8.4f} {std_full_t:>6.4f} {auc_full_t-auc_kf_t:>+12.4f}")
log(f"  {'B: Only Kalman':<35} {auc_kf_t:>8.4f} {std_kf_t:>6.4f} {'(base)':>12}")
log(f"  {'C: Kalman + RC slopes':<35} {auc_kf_rc_t:>8.4f} {std_kf_rc_t:>6.4f} {auc_kf_rc_t-auc_kf_t:>+12.4f}")
if tide_slope_idx is not None:
    log(f"  {'D: Kalman + tide_sign':<35} {auc_kf_dir_t:>8.4f} {std_kf_dir_t:>6.4f} {auc_kf_dir_t-auc_kf_t:>+12.4f}")

# ══════════════════════════════════════════════════════════
# STEP 6: DIRECTIONAL ANALYSIS — Does WITH/AGAINST trend matter?
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 6: ANÁLISIS DIRECCIONAL — ¿WITH_TREND vs AGAINST_TREND?")
log("═" * 100)

if tide_slope_idx is not None:
    tide_vals = X_base[:, tide_slope_idx]
    
    # For PISO True Positives: split by tide direction
    piso_mask = y_piso == 1
    
    piso_with_trend = piso_mask & (tide_vals > 0)    # HL-like: pullback in bull tide
    piso_against = piso_mask & (tide_vals < 0)        # LL-like: capitulation in bear tide
    piso_flat = piso_mask & (tide_vals == 0)
    
    log(f"\n  PISOS por dirección de TIDE:")
    log(f"    WITH_TREND (tide > 0):    {piso_with_trend.sum():,} ({piso_with_trend.sum()/max(piso_mask.sum(),1)*100:.1f}%)")
    log(f"    AGAINST_TREND (tide < 0): {piso_against.sum():,} ({piso_against.sum()/max(piso_mask.sum(),1)*100:.1f}%)")
    log(f"    FLAT (tide ≈ 0):          {piso_flat.sum():,} ({piso_flat.sum()/max(piso_mask.sum(),1)*100:.1f}%)")
    
    # Mean feature values by direction — RC slopes and key Kalman
    log(f"\n  {'Feature':<30} {'WITH_TREND μ':>13} {'AGAINST μ':>10} {'Δ':>8} {'Interpretation':<20}")
    log(f"  {'─'*30} {'─'*13} {'─'*10} {'─'*8} {'─'*20}")
    
    analysis_features = ['tide_slope', 'current_slope', 'wave_slope', 
                         'conj_wave_tide', 'kf_conjugation_pred_val',
                         'kf_rsi_pred_val', 'vwap_sigma_current', 'sigma_tide']
    
    for feat in analysis_features:
        if feat not in top_features:
            continue
        f_idx = top_features.index(feat)
        vals_with = X_base[piso_with_trend, f_idx]
        vals_against = X_base[piso_against, f_idx]
        
        mu_w = vals_with.mean()
        mu_a = vals_against.mean()
        delta = mu_w - mu_a
        
        if abs(delta) > 0.1:
            interp = "DIFFERS"
        else:
            interp = "similar"
        
        log(f"  {feat:<30} {mu_w:>13.4f} {mu_a:>10.4f} {delta:>+8.4f} {interp:<20}")
    
    # Same for TECHO
    techo_mask = y_techo == 1
    techo_with = techo_mask & (tide_vals > 0)     # HH-like: exhaustion in bull tide
    techo_against = techo_mask & (tide_vals < 0)   # LH-like: bounce in bear tide
    
    log(f"\n  TECHOS por dirección de TIDE:")
    log(f"    WITH_TREND (tide > 0):    {techo_with.sum():,} ({techo_with.sum()/max(techo_mask.sum(),1)*100:.1f}%)")
    log(f"    AGAINST_TREND (tide < 0): {techo_against.sum():,} ({techo_against.sum()/max(techo_mask.sum(),1)*100:.1f}%)")

# ══════════════════════════════════════════════════════════
# VEREDICTO
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  VEREDICTO: ¿SLOPES CONECTADAS O DESCONECTADAS?")
log("═" * 100)

delta_piso = auc_kf_rc - auc_kf
delta_techo = auc_kf_rc_t - auc_kf_t

log(f"\n  Δ AUC al agregar slopes al Kalman:")
log(f"    PISO:  {delta_piso:+.4f} ({'APORTA' if delta_piso > 0.005 else 'REDUNDANTE' if delta_piso > -0.005 else 'EMPEORA'})")
log(f"    TECHO: {delta_techo:+.4f} ({'APORTA' if delta_techo > 0.005 else 'REDUNDANTE' if delta_techo > -0.005 else 'EMPEORA'})")

if delta_piso > 0.005 or delta_techo > 0.005:
    log(f"\n  → Las slopes aportan información MARGINAL que el Kalman no captura.")
    log(f"    Incluir tide_slope (dirección) y/o conj_wave_tide (magnitud) en Sentinel Gate v6.")
else:
    log(f"\n  → Las slopes son REDUNDANTES con el Kalman.")
    log(f"    El canal Kalman de conjugation ya INTERPRETA las slopes.")
    log(f"    Usar kf_conjugation_pred_val como proxy suficiente.")

log(f"\n  Tiempo total: {time.time()-t0:.1f}s")

# Save
results = {
    "correlations": correlations,
    "ablation_piso": {"full": auc_full, "kf_only": auc_kf, "kf_rc": auc_kf_rc,
                      "kf_dir": auc_kf_dir if tide_slope_idx else None},
    "ablation_techo": {"full": auc_full_t, "kf_only": auc_kf_t, "kf_rc": auc_kf_rc_t,
                       "kf_dir": auc_kf_dir_t if tide_slope_idx else None},
    "delta_piso": delta_piso,
    "delta_techo": delta_techo,
}

with open("data/research/feature_lake/sprint2_fase_i_results.pkl", "wb") as f:
    pickle.dump(results, f)

with open("data/research/feature_lake/sprint2_fase_i_rc_kalman_audit.log", "w") as f:
    f.write("\n".join(LOG))

log(f"\n  ✅ Saved: sprint2_fase_i_results.pkl + .log")
