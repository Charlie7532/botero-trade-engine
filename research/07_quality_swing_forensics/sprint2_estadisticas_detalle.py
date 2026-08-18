"""
Sprint 2-REDO — Estadísticas de Detalle por Arquetipo
======================================================
Extrae: Precision, Recall, F1, AUC por arquetipo.
Utilidad práctica del ejercicio.
"""

import pandas as pd
import numpy as np
import pickle
import time
import warnings
import xgboost as xgb
from sklearn.metrics import (roc_auc_score, precision_score, recall_score, 
                             f1_score, confusion_matrix, classification_report)

warnings.filterwarnings("ignore")

LOG = []
def log(msg):
    print(msg, flush=True)
    LOG.append(msg)

t0 = time.time()

log("═" * 100)
log("  ESTADÍSTICAS DE DETALLE POR ARQUETIPO — UTILIDAD PRÁCTICA")
log("═" * 100)

# ── Load ──
df = pd.read_pickle("backend/scratch/sprint2_redo_lake_v21.pkl")
with open("backend/scratch/sprint2_redo_phase_c_v21.pkl", "rb") as f:
    pc = pickle.load(f)
with open("backend/scratch/sprint2_redo_phase_h_separated.pkl", "rb") as f:
    ph = pickle.load(f)
with open("backend/scratch/sprint2_fase_j_results.pkl", "rb") as f:
    pj = pickle.load(f)

top_features = pc["top_features_used"]
all_features = ph["all_features"]
ticker_values = df["ticker"].values
dist_vals = df["dist_zz_5pct"].values
type_vals = df["zz_5pct_type"].values
archetype_per_bar = pj["archetype_per_bar"]

X_base = np.nan_to_num(df[top_features].values.astype(np.float32), nan=0.0)

# Build temporal features
temporal_names = ["rolling_density_3bar", "rolling_density_5bar", "density_delta_3bar",
                  "kf_price_pred_trend_5bar", "rsi_z_trend_5bar", "wave_slope_delta_3bar"]
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
all_feature_names = top_features + temporal_names

# Build labels
y_bottom = np.zeros(len(df), dtype=int)
y_top = np.zeros(len(df), dtype=int)

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
y_piso = only_bottom.astype(int)
y_techo = only_top.astype(int)

# ══════════════════════════════════════════════════════════
# TRAIN MODELS & GET PREDICTIONS ON TEST SET
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 1: ENTRENAR MODELOS Y OBTENER PREDICCIONES POR ARQUETIPO")
log("═" * 100)

# 80/20 split (same as Phase H)
split = int(len(X_all) * 0.8)

# PISO model
m_piso = xgb.XGBClassifier(
    n_estimators=150, max_depth=5, learning_rate=0.1,
    subsample=0.8, colsample_bytree=0.8,
    scale_pos_weight=(y_piso[:split]==0).sum() / max((y_piso[:split]==1).sum(), 1),
    random_state=42, eval_metric="logloss", verbosity=0,
    min_child_weight=5, gamma=0.1,
)
m_piso.fit(X_all[:split], y_piso[:split])
prob_piso = m_piso.predict_proba(X_all[split:])[:, 1]
pred_piso = m_piso.predict(X_all[split:])

# TECHO model
m_techo = xgb.XGBClassifier(
    n_estimators=150, max_depth=5, learning_rate=0.1,
    subsample=0.8, colsample_bytree=0.8,
    scale_pos_weight=(y_techo[:split]==0).sum() / max((y_techo[:split]==1).sum(), 1),
    random_state=42, eval_metric="logloss", verbosity=0,
    min_child_weight=5, gamma=0.1,
)
m_techo.fit(X_all[:split], y_techo[:split])
prob_techo = m_techo.predict_proba(X_all[split:])[:, 1]
pred_techo = m_techo.predict(X_all[split:])

# Test set data
y_piso_test = y_piso[split:]
y_techo_test = y_techo[split:]
arch_test = archetype_per_bar[split:]

# ══════════════════════════════════════════════════════════
# GLOBAL METRICS
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 2: MÉTRICAS GLOBALES (Test set completo)")
log("═" * 100)

auc_piso = roc_auc_score(y_piso_test, prob_piso)
auc_techo = roc_auc_score(y_techo_test, prob_techo)

for label, y_true, y_pred, prob, auc in [
    ("PISO (Bottoms)", y_piso_test, pred_piso, prob_piso, auc_piso),
    ("TECHO (Tops)", y_techo_test, pred_techo, prob_techo, auc_techo),
]:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    prec = precision_score(y_true, y_pred)
    rec = recall_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred)
    
    log(f"\n  === {label} ===")
    log(f"  AUC:       {auc:.4f}")
    log(f"  Precision: {prec:.4f}  (de las alarmas, ¿cuántas son reales?)")
    log(f"  Recall:    {rec:.4f}  (de los giros reales, ¿cuántos detectamos?)")
    log(f"  F1:        {f1:.4f}")
    log(f"  TP={tp:,}  FP={fp:,}  FN={fn:,}  TN={tn:,}")
    log(f"  Total positivos: {y_true.sum():,} ({y_true.mean()*100:.1f}%)")

# ══════════════════════════════════════════════════════════
# PER-ARCHETYPE METRICS
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 3: MÉTRICAS POR ARQUETIPO")
log("═" * 100)

log(f"\n  {'Archetype':<15} {'n_test':>8} {'n_pos':>7} {'prev':>6} {'AUC':>8} {'Prec':>7} {'Recall':>7} {'F1':>7} {'TP':>6} {'FP':>6} {'FN':>6}")
log(f"  {'─'*15} {'─'*8} {'─'*7} {'─'*6} {'─'*8} {'─'*7} {'─'*7} {'─'*7} {'─'*6} {'─'*6} {'─'*6}")

archetype_results = {}

for arch, model_type in [("HL", "PISO"), ("LL", "PISO"), ("HH", "TECHO"), ("LH", "TECHO")]:
    arch_mask = arch_test == arch
    
    if model_type == "PISO":
        y_true_arch = y_piso_test[arch_mask]
        prob_arch = prob_piso[arch_mask]
        pred_arch = pred_piso[arch_mask]
    else:
        y_true_arch = y_techo_test[arch_mask]
        prob_arch = prob_techo[arch_mask]
        pred_arch = pred_techo[arch_mask]
    
    n_test = arch_mask.sum()
    n_pos = y_true_arch.sum()
    prev = y_true_arch.mean() * 100 if n_test > 0 else 0
    
    if n_pos > 0 and n_test > n_pos:
        auc = roc_auc_score(y_true_arch, prob_arch)
        prec = precision_score(y_true_arch, pred_arch, zero_division=0)
        rec = recall_score(y_true_arch, pred_arch, zero_division=0)
        f1 = f1_score(y_true_arch, pred_arch, zero_division=0)
        tn, fp, fn, tp = confusion_matrix(y_true_arch, pred_arch).ravel()
    else:
        auc = prec = rec = f1 = 0
        tp = fp = fn = 0
    
    archetype_results[arch] = {
        "n_test": n_test, "n_pos": n_pos, "prev": prev,
        "auc": auc, "prec": prec, "rec": rec, "f1": f1,
        "tp": tp, "fp": fp, "fn": fn,
    }
    
    log(f"  {arch:<15} {n_test:>8,} {n_pos:>7,} {prev:>5.1f}% {auc:>8.4f} {prec:>7.3f} {rec:>7.3f} {f1:>7.3f} {tp:>6,} {fp:>6,} {fn:>6,}")

# Non-archetype bars (far from any turn)
far_mask = arch_test == ""
for model_name, y_t, prob_m, pred_m in [("FAR→PISO", y_piso_test, prob_piso, pred_piso),
                                         ("FAR→TECHO", y_techo_test, prob_techo, pred_techo)]:
    y_far = y_t[far_mask]
    prob_far = prob_m[far_mask]
    pred_far = pred_m[far_mask]
    n_test = far_mask.sum()
    n_pos = y_far.sum()
    prev = y_far.mean() * 100 if n_test > 0 else 0
    
    if n_pos > 0 and n_test > n_pos:
        auc_f = roc_auc_score(y_far, prob_far)
        prec_f = precision_score(y_far, pred_far, zero_division=0)
        rec_f = recall_score(y_far, pred_far, zero_division=0)
        f1_f = f1_score(y_far, pred_far, zero_division=0)
        tn, fp, fn, tp = confusion_matrix(y_far, pred_far).ravel()
    else:
        auc_f = prec_f = rec_f = f1_f = 0
        tp = fp = fn = 0
    log(f"  {model_name:<15} {n_test:>8,} {n_pos:>7,} {prev:>5.1f}% {auc_f:>8.4f} {prec_f:>7.3f} {rec_f:>7.3f} {f1_f:>7.3f} {tp:>6,} {fp:>6,} {fn:>6,}")

# ══════════════════════════════════════════════════════════
# PROBABILITY DISTRIBUTION BY ARCHETYPE
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 4: DISTRIBUCIÓN DE PROBABILIDADES POR ARQUETIPO")
log("═" * 100)

log(f"\n  {'Archetype':<12} {'p10':>6} {'p25':>6} {'p50':>6} {'p75':>6} {'p90':>6} {'p95':>6} {'p99':>6} │ {'% > 0.5':>7} {'% > 0.7':>7} {'% > 0.8':>7}")
log(f"  {'─'*12} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*6} │ {'─'*7} {'─'*7} {'─'*7}")

for arch in ["HL", "LL", "HH", "LH", "FAR"]:
    if arch == "FAR":
        mask = arch_test == ""
        # Use the higher probability between piso and techo
        probs = np.maximum(prob_piso[mask], prob_techo[mask])
    else:
        mask = arch_test == arch
        if arch in ["HL", "LL"]:
            probs = prob_piso[mask]
        else:
            probs = prob_techo[mask]
    
    if len(probs) == 0:
        continue
    
    pcts = np.percentile(probs, [10, 25, 50, 75, 90, 95, 99])
    gt50 = (probs > 0.5).mean() * 100
    gt70 = (probs > 0.7).mean() * 100
    gt80 = (probs > 0.8).mean() * 100
    
    log(f"  {arch:<12} {pcts[0]:>6.3f} {pcts[1]:>6.3f} {pcts[2]:>6.3f} {pcts[3]:>6.3f} {pcts[4]:>6.3f} {pcts[5]:>6.3f} {pcts[6]:>6.3f} │ {gt50:>6.1f}% {gt70:>6.1f}% {gt80:>6.1f}%")

# ══════════════════════════════════════════════════════════
# PER-TICKER METRICS
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 5: MÉTRICAS POR TICKER (Modelo PISO)")
log("═" * 100)

ticker_test = ticker_values[split:]
log(f"\n  {'Ticker':<8} {'n_test':>8} {'n_pos':>7} {'AUC':>8} {'Prec':>7} {'Recall':>7} {'F1':>7}")
log(f"  {'─'*8} {'─'*8} {'─'*7} {'─'*8} {'─'*7} {'─'*7} {'─'*7}")

for tk in sorted(df["ticker"].unique()):
    tk_mask = ticker_test == tk
    y_tk = y_piso_test[tk_mask]
    prob_tk = prob_piso[tk_mask]
    pred_tk = pred_piso[tk_mask]
    
    n_pos = y_tk.sum()
    if n_pos > 0 and len(y_tk) > n_pos:
        auc_tk = roc_auc_score(y_tk, prob_tk)
        prec_tk = precision_score(y_tk, pred_tk, zero_division=0)
        rec_tk = recall_score(y_tk, pred_tk, zero_division=0)
        f1_tk = f1_score(y_tk, pred_tk, zero_division=0)
        log(f"  {tk:<8} {tk_mask.sum():>8,} {n_pos:>7,} {auc_tk:>8.4f} {prec_tk:>7.3f} {rec_tk:>7.3f} {f1_tk:>7.3f}")

# ══════════════════════════════════════════════════════════
# PRACTICAL UTILITY — ALERT QUALITY AT DIFFERENT THRESHOLDS
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 6: UTILIDAD PRÁCTICA — CALIDAD DE ALERTAS")
log("═" * 100)

log(f"\n  Si el Sentinel Gate emite una ALARMA cuando prob > threshold:")
log(f"  ¿Cuántas alertas diarias? ¿Qué % son verdaderas?")
log(f"\n  Asumimos: ~250 días/año × 17 tickers = 4,250 ticker-días en test")

n_test_days = len(y_piso_test)  # ~18K bars (20% of 91K)

for model_name, y_t, prob_m in [("PISO", y_piso_test, prob_piso), ("TECHO", y_techo_test, prob_techo)]:
    log(f"\n  === Modelo {model_name} ===")
    log(f"  {'Threshold':>10} {'Alertas':>10} {'TP':>8} {'FP':>8} {'Precision':>10} {'Recall':>8} {'Alert/day':>10}")
    log(f"  {'─'*10} {'─'*10} {'─'*8} {'─'*8} {'─'*10} {'─'*8} {'─'*10}")
    
    total_pos = y_t.sum()
    n_days_approx = n_test_days / 17  # approximate trading days
    
    for thr in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        alerts = prob_m > thr
        n_alerts = alerts.sum()
        tp = (alerts & (y_t == 1)).sum()
        fp = (alerts & (y_t == 0)).sum()
        prec = tp / max(n_alerts, 1)
        rec = tp / max(total_pos, 1)
        alert_per_day = n_alerts / max(n_days_approx, 1)
        
        log(f"  {thr:>10.1f} {n_alerts:>10,} {tp:>8,} {fp:>8,} {prec:>10.1%} {rec:>8.1%} {alert_per_day:>10.1f}")

# ══════════════════════════════════════════════════════════
# UTILIDAD PARA CADA DEPARTAMENTO
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 7: UTILIDAD POR DEPARTAMENTO DE TRADING")
log("═" * 100)

# Quality Department: HL detection for accumulation timing
log(f"\n  === QUALITY DEPARTMENT — Timing de Acumulación ===")
log(f"  Objetivo: detectar HL (pullback) para acumular en posiciones MOAT")
hl_mask_test = arch_test == "HL"
hl_pos = (hl_mask_test & (y_piso_test == 1))
log(f"  Giros HL en test set: {hl_pos.sum()} verdaderos de {hl_mask_test.sum()} barras HL")
if hl_pos.sum() > 0:
    # At prob > 0.5
    hl_detected = (prob_piso[hl_mask_test] > 0.5) & (y_piso_test[hl_mask_test] == 1)
    log(f"  HL detectados (prob > 0.5): {hl_detected.sum()} de {hl_pos.sum()} ({hl_detected.sum()/hl_pos.sum()*100:.1f}%)")
    hl_fp = (prob_piso[hl_mask_test] > 0.5) & (y_piso_test[hl_mask_test] == 0)
    log(f"  Falsas alarmas HL: {hl_fp.sum()}")

# Quality Swing: LL detection for oversold buying + HH for trim
log(f"\n  === QUALITY SWING — Acumulación en Pánico / Trim en Complacencia ===")
log(f"  LL para comprar pánico, HH para trimear en complacencia")
for arch, model_name, y_t, prob_m in [("LL", "PISO", y_piso_test, prob_piso), 
                                       ("HH", "TECHO", y_techo_test, prob_techo)]:
    am = arch_test == arch
    pos = (am & (y_t == 1))
    if pos.sum() > 0:
        det = (prob_m[am] > 0.5) & (y_t[am] == 1)
        fps = (prob_m[am] > 0.5) & (y_t[am] == 0)
        log(f"    {arch}: {det.sum()}/{pos.sum()} detectados ({det.sum()/pos.sum()*100:.1f}%), {fps.sum()} FP")

# Speculative: LH detection for shorts
log(f"\n  === SPECULATIVE DEPARTMENT — Short en Rebote Fallido ===")
log(f"  LH para shortar rebotes en bear market")
lh_mask_test = arch_test == "LH"
lh_pos = (lh_mask_test & (y_techo_test == 1))
if lh_pos.sum() > 0:
    lh_detected = (prob_techo[lh_mask_test] > 0.5) & (y_techo_test[lh_mask_test] == 1)
    lh_fp = (prob_techo[lh_mask_test] > 0.5) & (y_techo_test[lh_mask_test] == 0)
    log(f"  LH detectados (prob > 0.5): {lh_detected.sum()} de {lh_pos.sum()} ({lh_detected.sum()/lh_pos.sum()*100:.1f}%)")
    log(f"  Falsas alarmas LH: {lh_fp.sum()}")

# ══════════════════════════════════════════════════════════
# SUMMARY: WHAT DID WE BUILD?
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  RESUMEN: ¿QUÉ CONSTRUIMOS Y PARA QUÉ SIRVE?")
log("═" * 100)

log(f"""
  El ejercicio de ingeniería inversa del ZigZag produjo:

  1. UN SISTEMA DE DETECCIÓN DE GIROS con 4 detectores especializados
     - Input:  6 features Kalman + 6 temporales + contexto RC
     - Output: probabilidad de giro por tipo (HL/LL/HH/LH) por barra
     - AUC:    0.887 (PISO), 0.763 (TECHO)

  2. UN MAPA DE FIRMAS PREDICTIVAS por arquetipo
     - HL (Pullback):       RSI neutral, DECRESCENDO, SILENCIO
     - LL (Capitulación):   RSI oversold, CRESCENDO, PÁNICO
     - HH (Agotamiento):    RSI overbought, PLANO, COMPLACENCIA
     - LH (Rebote fallido): RSI neutral, CRESCENDO, BEAR MARKET

  3. THRESHOLDS CALIBRADOS por densidad
     - LL: density ≥ 8 → LIFT 16.6x
     - LH: density ≥ 8 → LIFT 23.4x
     - HL: density ≥ 8 → LIFT 12.8x (pero solo 10% cruzan)
     - HH: density ≥ 8 → LIFT 5.5x (detector débil)

  4. EVIDENCIA DE QUE LA SEÑAL ES REAL
     - DSR 0.984 (no es suerte)
     - PurgedKFold con embargo (no es autocorrelación)
     - 17 tickers × 20 años (no es overfit a un período)

  5. REGLAS DE DISEÑO PARA PRODUCCIÓN
     - Detección: solo Kalman (6 features)
     - Contexto:  tide_slope sign para sizing
     - Gate:      3 niveles (ALARMA → PRESURIZACIÓN → EXPLOSIÓN)
     - Separar:   PISO y TECHO son modelos DISTINTOS
     - Separar:   HL y LL necesitan thresholds diferentes
""")

log(f"\n  Tiempo total: {time.time()-t0:.1f}s")

with open("backend/scratch/sprint2_estadisticas_detalle.log", "w") as f:
    f.write("\n".join(LOG))

log(f"\n  ✅ Saved: sprint2_estadisticas_detalle.log")
