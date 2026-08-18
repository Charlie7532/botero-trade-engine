"""
Sprint 2-REDO — Fase J: Segmentación por Arquetipos HL/LL/HH/LH
===================================================================
¿Los sub-tipos de giro tienen firmas distintas?

Análisis:
  1. Clasificar cada giro ZigZag en HL/LL/HH/LH
  2. Distribución de True Positives del modelo H por sub-tipo
  3. SHAP promedio por sub-tipo (del modelo ya entrenado)
  4. Densidad, LIFT y CRESCENDO temporal por sub-tipo
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
log("  FASE J: SEGMENTACIÓN POR ARQUETIPOS — HL vs LL / HH vs LH")
log("═" * 100)

# ── 0. Load data ──
df = pd.read_pickle("backend/scratch/sprint2_redo_lake_v21.pkl")
with open("backend/scratch/sprint2_redo_phase_c_v21.pkl", "rb") as f:
    pc = pickle.load(f)
with open("backend/scratch/sprint2_redo_phase_h_separated.pkl", "rb") as f:
    ph = pickle.load(f)

top_features = pc["top_features_used"]
all_features = ph["all_features"]
ticker_values = df["ticker"].values
dist_vals = df["dist_zz_5pct"].values
type_vals = df["zz_5pct_type"].values

log(f"  Lake: {len(df):,} rows × {len(all_features)} features")

# ══════════════════════════════════════════════════════════
# STEP 1: CLASSIFY TURNS — HL/LL/HH/LH
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 1: CLASIFICAR GIROS EN ARQUETIPOS")
log("═" * 100)

# Extract all zigzag turns with their prices and types
X_base = np.nan_to_num(df[top_features].values.astype(np.float32), nan=0.0)

# Build temporal features (same as Phase H)
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

# For each ticker, find consecutive zigzag turns and classify
# archetype_map: global_idx_of_turn_bar -> archetype string
archetype_per_turn = {}  # key = (ticker, position_in_ticker), value = "HL"/"LL"/"HH"/"LH"
archetype_per_bar = np.full(len(df), "", dtype="U2")  # "" = not near a turn

# Use reg_value_wave as close-price proxy (no DB needed)
# At dist=0 (turn bar), reg_value_wave ≈ close price
# We only need relative comparison (higher/lower) between consecutive turns
wave_price_idx = top_features.index('reg_value_wave') if 'reg_value_wave' in top_features else None
if wave_price_idx is None:
    # Fallback: use vwap_wave which is also close to close price
    wave_price_idx = top_features.index('vwap_wave') if 'vwap_wave' in top_features else None
    log(f"  Using vwap_wave as price proxy (reg_value_wave not found)")
else:
    log(f"  Using reg_value_wave as price proxy for archetype classification")

assert wave_price_idx is not None, "Need reg_value_wave or vwap_wave to classify archetypes"

# Collect turn prices per ticker
turn_stats = {"HL": 0, "LL": 0, "HH": 0, "LH": 0, "FIRST": 0}

for tk in sorted(df["ticker"].unique()):
    mask = ticker_values == tk
    idx = np.where(mask)[0]
    dist = dist_vals[idx]
    tt = type_vals[idx]
    
    # Find all turn bars (dist=0)
    turn_positions = np.where(dist == 0)[0]  # positions within ticker
    
    # Build sequential list of turns with prices
    turns = []
    for tp in turn_positions:
        global_idx = idx[tp]
        turn_type = tt[tp]
        close_price = X_base[global_idx, wave_price_idx]
        
        turns.append({
            "position": tp,
            "global_idx": global_idx,
            "type": turn_type,
            "close": close_price,
        })
    
    # Now classify: compare each turn with the previous turn of the SAME type
    prev_min_price = None
    prev_max_price = None
    
    for t in turns:
        if t["close"] is None or t["close"] == 0:
            turn_stats["FIRST"] += 1
            continue
            
        if t["type"] == "MIN":
            if prev_min_price is not None:
                archetype = "HL" if t["close"] > prev_min_price else "LL"
                archetype_per_turn[(tk, t["position"])] = archetype
                turn_stats[archetype] += 1
                
                # Tag nearby bars (±3) with this archetype
                for offset in range(-3, 4):
                    bar_pos = t["position"] + offset
                    if 0 <= bar_pos < len(idx):
                        archetype_per_bar[idx[bar_pos]] = archetype
            else:
                turn_stats["FIRST"] += 1
            prev_min_price = t["close"]
        
        elif t["type"] == "MAX":
            if prev_max_price is not None:
                archetype = "HH" if t["close"] > prev_max_price else "LH"
                archetype_per_turn[(tk, t["position"])] = archetype
                turn_stats[archetype] += 1
                
                for offset in range(-3, 4):
                    bar_pos = t["position"] + offset
                    if 0 <= bar_pos < len(idx):
                        archetype_per_bar[idx[bar_pos]] = archetype
            else:
                turn_stats["FIRST"] += 1
            prev_max_price = t["close"]

log(f"\n  Turn classification:")
log(f"    Higher Low (HL):   {turn_stats['HL']:,}")
log(f"    Lower Low (LL):    {turn_stats['LL']:,}")
log(f"    Higher High (HH):  {turn_stats['HH']:,}")
log(f"    Lower High (LH):   {turn_stats['LH']:,}")
log(f"    First turn (no prev): {turn_stats['FIRST']:,}")

# Bars tagged with archetype
bars_hl = archetype_per_bar == "HL"
bars_ll = archetype_per_bar == "LL"
bars_hh = archetype_per_bar == "HH"
bars_lh = archetype_per_bar == "LH"

log(f"\n  Bars per archetype (±3 window):")
log(f"    HL bars: {bars_hl.sum():,}")
log(f"    LL bars: {bars_ll.sum():,}")
log(f"    HH bars: {bars_hh.sum():,}")
log(f"    LH bars: {bars_lh.sum():,}")

# ══════════════════════════════════════════════════════════
# STEP 2: SHAP PER ARCHETYPE (using Phase H model)
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 2: SHAP PROMEDIO POR ARQUETIPO")
log("═" * 100)

# Train fresh models to get SHAP values on archetype subsets
# Build labels (same as Phase H)
y_bottom = np.zeros(len(df), dtype=int)
y_top = np.zeros(len(df), dtype=int)

for tk in sorted(df["ticker"].unique()):
    mask = ticker_values == tk
    idx_tk = np.where(mask)[0]
    dist = dist_vals[idx_tk]
    tt = type_vals[idx_tk]
    
    last_type, last_pos = None, -999
    for i in range(len(idx_tk)):
        if dist[i] == 0:
            last_type = tt[i]
            last_pos = i
        if dist[i] <= 3 and last_type is not None and abs(i - last_pos) <= 3:
            if last_type == "MIN": y_bottom[idx_tk[i]] = 1
            elif last_type == "MAX": y_top[idx_tk[i]] = 1
    
    next_type, next_pos = None, 999999
    for i in range(len(idx_tk)-1, -1, -1):
        if dist[i] == 0:
            next_type = tt[i]
            next_pos = i
        if dist[i] <= 3 and next_type is not None and abs(i - next_pos) <= 3:
            if next_type == "MIN": y_bottom[idx_tk[i]] = 1
            elif next_type == "MAX": y_top[idx_tk[i]] = 1

only_bottom = (y_bottom == 1) & (y_top == 0)
only_top = (y_top == 1) & (y_bottom == 0)
y_piso = only_bottom.astype(int)
y_techo = only_top.astype(int)

# Train PISO model on full data for SHAP extraction
log(f"\n  Training PISO model for SHAP extraction...")
m_piso = xgb.XGBClassifier(
    n_estimators=150, max_depth=5, learning_rate=0.1,
    subsample=0.8, colsample_bytree=0.8,
    scale_pos_weight=(y_piso==0).sum() / max((y_piso==1).sum(), 1),
    random_state=42, eval_metric="logloss", verbosity=0,
    min_child_weight=5, gamma=0.1,
)
split = int(len(X_all) * 0.8)
m_piso.fit(X_all[:split], y_piso[:split])

explainer_piso = shap.TreeExplainer(m_piso)

# SHAP for HL subset
hl_indices = np.where(bars_hl)[0]
ll_indices = np.where(bars_ll)[0]

log(f"  Computing SHAP for HL ({len(hl_indices)} bars) and LL ({len(ll_indices)} bars)...")

# Sample if too many
n_shap = 2000
hl_sample = np.random.choice(hl_indices, min(n_shap, len(hl_indices)), replace=False) if len(hl_indices) > 0 else np.array([])
ll_sample = np.random.choice(ll_indices, min(n_shap, len(ll_indices)), replace=False) if len(ll_indices) > 0 else np.array([])

shap_hl = None
shap_ll = None

if len(hl_sample) > 0:
    shap_hl = np.abs(explainer_piso.shap_values(X_all[hl_sample])).mean(axis=0)
if len(ll_sample) > 0:
    shap_ll = np.abs(explainer_piso.shap_values(X_all[ll_sample])).mean(axis=0)

if shap_hl is not None and shap_ll is not None:
    log(f"\n  === PISO: SHAP Comparación HL vs LL ===")
    log(f"  {'Feature':<35} {'SHAP_HL':>10} {'SHAP_LL':>10} {'Δ (LL-HL)':>10} {'Dominant':<12}")
    log(f"  {'─'*35} {'─'*10} {'─'*10} {'─'*10} {'─'*12}")
    
    combined = shap_hl + shap_ll
    top_idx = np.argsort(-combined)[:20]
    
    for rank, idx in enumerate(top_idx):
        feat = all_feature_names[idx]
        s_hl = shap_hl[idx]
        s_ll = shap_ll[idx]
        delta = s_ll - s_hl
        
        if abs(delta) / max(max(s_hl, s_ll), 1e-6) > 0.30:
            dom = "★ LL" if delta > 0 else "★ HL"
        else:
            dom = "SHARED"
        
        log(f"  {feat:<35} {s_hl:>10.4f} {s_ll:>10.4f} {delta:>+10.4f} {dom:<12}")

# Same for TECHO: HH vs LH
log(f"\n  Training TECHO model for SHAP extraction...")
m_techo = xgb.XGBClassifier(
    n_estimators=150, max_depth=5, learning_rate=0.1,
    subsample=0.8, colsample_bytree=0.8,
    scale_pos_weight=(y_techo==0).sum() / max((y_techo==1).sum(), 1),
    random_state=42, eval_metric="logloss", verbosity=0,
    min_child_weight=5, gamma=0.1,
)
m_techo.fit(X_all[:split], y_techo[:split])

explainer_techo = shap.TreeExplainer(m_techo)

hh_indices = np.where(bars_hh)[0]
lh_indices = np.where(bars_lh)[0]

log(f"  Computing SHAP for HH ({len(hh_indices)} bars) and LH ({len(lh_indices)} bars)...")

hh_sample = np.random.choice(hh_indices, min(n_shap, len(hh_indices)), replace=False) if len(hh_indices) > 0 else np.array([])
lh_sample = np.random.choice(lh_indices, min(n_shap, len(lh_indices)), replace=False) if len(lh_indices) > 0 else np.array([])

shap_hh = None
shap_lh = None

if len(hh_sample) > 0:
    shap_hh = np.abs(explainer_techo.shap_values(X_all[hh_sample])).mean(axis=0)
if len(lh_sample) > 0:
    shap_lh = np.abs(explainer_techo.shap_values(X_all[lh_sample])).mean(axis=0)

if shap_hh is not None and shap_lh is not None:
    log(f"\n  === TECHO: SHAP Comparación HH vs LH ===")
    log(f"  {'Feature':<35} {'SHAP_HH':>10} {'SHAP_LH':>10} {'Δ (LH-HH)':>10} {'Dominant':<12}")
    log(f"  {'─'*35} {'─'*10} {'─'*10} {'─'*10} {'─'*12}")
    
    combined_t = shap_hh + shap_lh
    top_idx_t = np.argsort(-combined_t)[:20]
    
    for rank, idx in enumerate(top_idx_t):
        feat = all_feature_names[idx]
        s_hh = shap_hh[idx]
        s_lh = shap_lh[idx]
        delta = s_lh - s_hh
        
        if abs(delta) / max(max(s_hh, s_lh), 1e-6) > 0.30:
            dom = "★ LH" if delta > 0 else "★ HH"
        else:
            dom = "SHARED"
        
        log(f"  {feat:<35} {s_hh:>10.4f} {s_lh:>10.4f} {delta:>+10.4f} {dom:<12}")

# ══════════════════════════════════════════════════════════
# STEP 3: DENSITY AND LIFT PER ARCHETYPE
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 3: DENSIDAD Y LIFT POR ARQUETIPO")
log("═" * 100)

# Compute instant density per bar
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

rd3 = temporal_features[:, 0]  # rolling_density_3bar
far_mask = dist_vals > 10

log(f"\n  {'Archetype':<15} {'n_bars':>8} {'Density μ':>10} {'Density med':>12} {'rd3 μ':>8} {'rd3 med':>10}")
log(f"  {'─'*15} {'─'*8} {'─'*10} {'─'*12} {'─'*8} {'─'*10}")

for arch, arch_mask in [("HL", bars_hl), ("LL", bars_ll), ("HH", bars_hh), ("LH", bars_lh), 
                         ("FAR (neg)", far_mask)]:
    if arch_mask.sum() == 0:
        continue
    d = instant_density[arch_mask]
    r = rd3[arch_mask]
    log(f"  {arch:<15} {arch_mask.sum():>8,} {d.mean():>10.2f} {np.median(d):>12.1f} {r.mean():>8.2f} {np.median(r):>10.1f}")

# LIFT per archetype at density thresholds
log(f"\n  {'Archetype':<12} {'Level':<15} {'% at level':>10} {'% far':>10} {'LIFT':>8}")
log(f"  {'─'*12} {'─'*15} {'─'*10} {'─'*10} {'─'*8}")

far_density = instant_density[far_mask]

for arch, arch_mask in [("HL", bars_hl), ("LL", bars_ll), ("HH", bars_hh), ("LH", bars_lh)]:
    # Only look at bars at the turn (dist=0 within this archetype)
    turn_mask = arch_mask & (dist_vals == 0)
    if turn_mask.sum() == 0:
        continue
    turn_density = instant_density[turn_mask]
    
    for level, thr in [("ALARMA", 2), ("PRESURIZACIÓN", 5), ("EXPLOSIÓN", 8)]:
        pct_turn = (turn_density >= thr).mean() * 100
        pct_far = (far_density >= thr).mean() * 100
        lift = pct_turn / max(pct_far, 0.01)
        marker = "✅" if lift > 2.0 else "⚠️"
        log(f"  {arch:<12} {level:<15} {pct_turn:>9.1f}% {pct_far:>9.1f}% {lift:>7.1f}x {marker}")

# ══════════════════════════════════════════════════════════
# STEP 4: CRESCENDO TEMPORAL PER ARCHETYPE
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 4: CRESCENDO TEMPORAL POR ARQUETIPO")
log("═" * 100)

# For each archetype, compute density by temporal phase
for arch, arch_type, turn_type in [("HL", "HL", "MIN"), ("LL", "LL", "MIN"), 
                                    ("HH", "HH", "MAX"), ("LH", "LH", "MAX")]:
    log(f"\n  === {arch} ===")
    
    phase_density = {"PRECURSOR": [], "APPROACH": [], "INFLECTION": [], "PROPAGATION": []}
    phase_kf_trend = {"PRECURSOR": [], "APPROACH": [], "INFLECTION": [], "PROPAGATION": []}
    
    for tk in sorted(df["ticker"].unique()):
        mask = ticker_values == tk
        idx = np.where(mask)[0]
        dist = dist_vals[idx]
        tt = type_vals[idx]
        
        # Find turns of this archetype
        for i, tp in enumerate(np.where(dist == 0)[0]):
            global_idx = idx[tp]
            if archetype_per_bar[global_idx] != arch_type:
                continue
            
            for phase, lo, hi in [("PRECURSOR", -10, -4), ("APPROACH", -3, -1),
                                   ("INFLECTION", 0, 0), ("PROPAGATION", 1, 3)]:
                for offset in range(lo, hi + 1):
                    bar_pos = tp + offset
                    if 0 <= bar_pos < len(idx):
                        gp = idx[bar_pos]
                        phase_density[phase].append(rd3[gp])
                        phase_kf_trend[phase].append(temporal_features[gp, 3])
    
    log(f"  {'Phase':<15} {'Density μ':>10} {'KF_trend μ':>11} {'n':>8}")
    log(f"  {'─'*15} {'─'*10} {'─'*11} {'─'*8}")
    
    vals_by_phase = {}
    for phase in ["PRECURSOR", "APPROACH", "INFLECTION", "PROPAGATION"]:
        d = np.array(phase_density[phase]) if phase_density[phase] else np.array([0])
        k = np.array(phase_kf_trend[phase]) if phase_kf_trend[phase] else np.array([0])
        vals_by_phase[phase] = d.mean()
        log(f"  {phase:<15} {d.mean():>10.3f} {k.mean():>11.4f} {len(d):>8,}")
    
    ramp = vals_by_phase.get("INFLECTION", 0) - vals_by_phase.get("PRECURSOR", 0)
    if ramp > 0.3:
        log(f"  → ✅ CRESCENDO (ramp = {ramp:+.3f})")
    elif ramp < -0.1:
        log(f"  → 🔻 DECRESCENDO (ramp = {ramp:+.3f})")
    else:
        log(f"  → ➖ PLANO (ramp = {ramp:+.3f})")

# ══════════════════════════════════════════════════════════
# STEP 5: KEY FEATURE MEANS PER ARCHETYPE
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  STEP 5: FEATURE MEANS POR ARQUETIPO (barras en t=0)")
log("═" * 100)

key_features = [
    'kf_rsi_pred_val', 'rsi_value', 'vwap_sigma_current', 'vwap_sigma_tide',
    'sigma_tide', 'sigma_current', 'tide_slope', 'current_slope', 'wave_slope',
    'conj_wave_tide', 'kf_conjugation_pred_val', 'kf_price_pred_val',
    'kf_price_filt_vel', 'compression_ratio', 'fear_level',
]
key_features = [f for f in key_features if f in top_features]

log(f"\n  {'Feature':<30} {'HL μ':>8} {'LL μ':>8} {'Δ':>8} │ {'HH μ':>8} {'LH μ':>8} {'Δ':>8}")
log(f"  {'─'*30} {'─'*8} {'─'*8} {'─'*8} │ {'─'*8} {'─'*8} {'─'*8}")

# Only look at turn bars (dist=0)
for feat in key_features:
    f_idx = top_features.index(feat)
    
    hl_turn = bars_hl & (dist_vals == 0)
    ll_turn = bars_ll & (dist_vals == 0)
    hh_turn = bars_hh & (dist_vals == 0)
    lh_turn = bars_lh & (dist_vals == 0)
    
    mu_hl = X_base[hl_turn, f_idx].mean() if hl_turn.sum() > 0 else 0
    mu_ll = X_base[ll_turn, f_idx].mean() if ll_turn.sum() > 0 else 0
    mu_hh = X_base[hh_turn, f_idx].mean() if hh_turn.sum() > 0 else 0
    mu_lh = X_base[lh_turn, f_idx].mean() if lh_turn.sum() > 0 else 0
    
    d_piso = mu_ll - mu_hl
    d_techo = mu_lh - mu_hh
    
    log(f"  {feat:<30} {mu_hl:>8.3f} {mu_ll:>8.3f} {d_piso:>+8.3f} │ {mu_hh:>8.3f} {mu_lh:>8.3f} {d_techo:>+8.3f}")

# ══════════════════════════════════════════════════════════
# VEREDICTO
# ══════════════════════════════════════════════════════════
log("\n" + "═" * 100)
log("  VEREDICTO: ¿LOS SUB-TIPOS TIENEN FIRMAS DISTINTAS?")
log("═" * 100)

# Count how many features have >30% relative SHAP difference
if shap_hl is not None and shap_ll is not None:
    n_different_piso = 0
    n_total = min(20, len(all_feature_names))
    combined = shap_hl + shap_ll
    top_20 = np.argsort(-combined)[:n_total]
    for idx in top_20:
        delta = abs(shap_ll[idx] - shap_hl[idx])
        max_val = max(shap_hl[idx], shap_ll[idx], 1e-6)
        if delta / max_val > 0.30:
            n_different_piso += 1
    
    log(f"\n  PISO: {n_different_piso}/{n_total} top features tienen SHAP >30% diferente entre HL y LL")
    if n_different_piso >= 5:
        log(f"  → ✅ HL y LL son FENÓMENOS DISTINTOS — necesitan thresholds separados")
    elif n_different_piso >= 2:
        log(f"  → ⚠️ HL y LL tienen FIRMAS PARCIALMENTE DIFERENTES — ajuste fino por sub-tipo")
    else:
        log(f"  → ➖ HL y LL son SIMILARES — un solo threshold basta para pisos")

if shap_hh is not None and shap_lh is not None:
    n_different_techo = 0
    combined_t = shap_hh + shap_lh
    top_20_t = np.argsort(-combined_t)[:n_total]
    for idx in top_20_t:
        delta = abs(shap_lh[idx] - shap_hh[idx])
        max_val = max(shap_hh[idx], shap_lh[idx], 1e-6)
        if delta / max_val > 0.30:
            n_different_techo += 1
    
    log(f"\n  TECHO: {n_different_techo}/{n_total} top features tienen SHAP >30% diferente entre HH y LH")
    if n_different_techo >= 5:
        log(f"  → ✅ HH y LH son FENÓMENOS DISTINTOS — necesitan thresholds separados")
    elif n_different_techo >= 2:
        log(f"  → ⚠️ HH y LH tienen FIRMAS PARCIALMENTE DIFERENTES — ajuste fino por sub-tipo")
    else:
        log(f"  → ➖ HH y LH son SIMILARES — un solo threshold basta para techos")

log(f"\n  Tiempo total: {time.time()-t0:.1f}s")

# Save
results = {
    "turn_stats": turn_stats,
    "archetype_per_bar": archetype_per_bar,
    "shap_hl": shap_hl, "shap_ll": shap_ll,
    "shap_hh": shap_hh, "shap_lh": shap_lh,
    "all_feature_names": all_feature_names,
}

with open("backend/scratch/sprint2_fase_j_results.pkl", "wb") as f:
    pickle.dump(results, f)

with open("backend/scratch/sprint2_fase_j_arquetipos.log", "w") as f:
    f.write("\n".join(LOG))

log(f"\n  ✅ Saved: sprint2_fase_j_results.pkl + .log")
