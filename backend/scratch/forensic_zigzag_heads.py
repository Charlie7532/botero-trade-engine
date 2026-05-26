"""
FORENSIA PROFUNDA — Zigzag Heads Phase 2
==========================================
Comité: López de Prado, Simons, Druckenmiller
Usa load_feature_lake para tener las 63 features completas.
"""
import sys, warnings, pickle, json, time
from pathlib import Path
warnings.filterwarnings("ignore")
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
from dotenv import load_dotenv; load_dotenv(root / ".env")

import numpy as np
import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore
from sqlalchemy import text

# Reuse the feature engineering from pretrainer
sys.path.insert(0, str(root / "backend" / "scripts"))
from unified_pretrainer_v2 import load_feature_lake, ALL_FEATURES

def banner(t):
    print(f"\n{'═'*100}\n  {t}\n{'═'*100}")
def section(t):
    print(f"\n  ── {t} ──")

store = TimescaleDataStore()
profile_store = TickerProfileStore()

# Load full feature lake (63 features)
df, ohlcv_cache, profiles = load_feature_lake(store, profile_store)
feature_cols = [f for f in ALL_FEATURES if f in df.columns]
print(f"  Feature lake: {len(df):,d} rows, {len(feature_cols)} features")

# Load zigzag
zz = pd.read_sql(text(
    "SELECT * FROM engine.zigzag_points WHERE min_swing_pct=0.05 ORDER BY ticker, timestamp"),
    store.engine)
print(f"  Zigzag: {len(zz):,d} points")

# Load models
model_dir = root / "backend" / "models"
bottom_pkl = pickle.load(open(model_dir / "head_zz_bottom_detector_v2.pkl", "rb"))
top_pkl = pickle.load(open(model_dir / "head_zz_top_detector_v2.pkl", "rb"))

# Score using model's own feature list
for pkl, name in [(bottom_pkl, 'p_zz_bottom'), (top_pkl, 'p_zz_top')]:
    model = pkl['model']
    fcols = pkl['feature_cols']
    available = [f for f in fcols if f in df.columns]
    X = df[available].fillna(0).values
    df[name] = model.predict_proba(X)[:, 1]
    print(f"  Scored {name}: features={len(available)}, mean P={df[name].mean():.3f}")

# ═══════════════════════════════════════════════════════════
banner("1. COBERTURA + TIMING — ¿Detecta ANTES del giro?")
# ═══════════════════════════════════════════════════════════

for tp_type, prob_col, label in [('MIN', 'p_zz_bottom', 'BOTTOM'), ('MAX', 'p_zz_top', 'TOP')]:
    section(f"Giros {label} (zigzag {tp_type})")
    tp_zz = zz[zz['tp_type'] == tp_type]
    
    detected = {t: 0 for t in [0.50, 0.65, 0.80]}
    total = 0
    timing_peak = []
    timing_first = {0.50: [], 0.65: [], 0.80: []}
    
    for _, zz_pt in tp_zz.iterrows():
        tk, ts = zz_pt['ticker'], zz_pt['timestamp']
        tk_df = df[df['ticker'] == tk]
        td = (tk_df['timestamp'] - ts).dt.days
        nearby = tk_df[td.abs() <= 5]
        if len(nearby) == 0:
            continue
        total += 1
        
        max_prob = nearby[prob_col].max()
        for thr in [0.50, 0.65, 0.80]:
            if max_prob >= thr:
                detected[thr] += 1
                crossing = nearby[nearby[prob_col] >= thr]
                if len(crossing) > 0:
                    first_ts = crossing['timestamp'].iloc[0]
                    timing_first[thr].append((first_ts - ts).days)
        
        peak_idx = nearby[prob_col].idxmax()
        timing_peak.append((df.loc[peak_idx, 'timestamp'] - ts).days)
    
    print(f"  Total giros: {total}")
    for thr in [0.50, 0.65, 0.80]:
        d = detected[thr]
        lost = total - d
        print(f"  P≥{thr:.2f}: {d}/{total} ({d/max(total,1)*100:.1f}%) | Perdidos: {lost}")
    
    pk = np.array(timing_peak)
    before = (pk < 0).sum()
    at = (pk == 0).sum()
    after = (pk > 0).sum()
    print(f"\n  TIMING PICO probabilidad vs giro real:")
    print(f"    Media: {pk.mean():+.1f}d | Mediana: {np.median(pk):+.1f}d")
    print(f"    ANTES: {before} ({before/len(pk)*100:.0f}%) │ EN: {at} ({at/len(pk)*100:.0f}%) │ DESPUÉS: {after} ({after/len(pk)*100:.0f}%)")
    
    print(f"\n  TIMING primera señal por threshold:")
    for thr in [0.50, 0.65, 0.80]:
        arr = np.array(timing_first[thr])
        if len(arr) > 0:
            b = (arr < 0).sum()
            a = (arr == 0).sum()
            d = (arr > 0).sum()
            print(f"    P≥{thr}: offset medio={arr.mean():+.1f}d med={np.median(arr):+.0f}d | ANTES:{b}({b/len(arr)*100:.0f}%) EN:{a}({a/len(arr)*100:.0f}%) DESPUÉS:{d}({d/len(arr)*100:.0f}%)")

# ═══════════════════════════════════════════════════════════
banner("2. FALSE POSITIVES — ¿Qué pasa cuando dispara mal?")
# ═══════════════════════════════════════════════════════════

for prob_col, tp_type, label in [('p_zz_bottom', 'MIN', 'BOTTOM'), ('p_zz_top', 'MAX', 'TOP')]:
    section(f"False Positives {label}")
    high = df[df[prob_col] >= 0.80]
    tp_zz = zz[zz['tp_type'] == tp_type]
    
    tp_count, fp_count = 0, 0
    fp_ret5, fp_ret10 = [], []
    
    for _, sig in high.iterrows():
        tk, ts = sig['ticker'], sig['timestamp']
        tk_zz = tp_zz[tp_zz['ticker'] == tk]
        is_tp = len(tk_zz) > 0 and abs((tk_zz['timestamp'] - ts).dt.days).min() <= 3
        
        if is_tp:
            tp_count += 1
        else:
            fp_count += 1
            ohlc = ohlcv_cache.get(tk)
            if ohlc is not None and ts in ohlc.index:
                pos = ohlc.index.get_loc(ts)
                if pos+5 < len(ohlc):
                    fp_ret5.append((ohlc['close'].iloc[pos+5]/ohlc['close'].iloc[pos]-1)*100)
                if pos+10 < len(ohlc):
                    fp_ret10.append((ohlc['close'].iloc[pos+10]/ohlc['close'].iloc[pos]-1)*100)
    
    tot = tp_count + fp_count
    print(f"  P≥0.80: {tot} señales | TP:{tp_count} ({tp_count/max(tot,1)*100:.1f}%) FP:{fp_count} ({fp_count/max(tot,1)*100:.1f}%)")
    
    if fp_ret5:
        r5 = np.array(fp_ret5)
        r10 = np.array(fp_ret10)
        d = "sube" if tp_type == 'MIN' else "baja"
        fav5 = (r5 > 0).mean()*100 if tp_type == 'MIN' else (r5 < 0).mean()*100
        fav10 = (r10 > 0).mean()*100 if tp_type == 'MIN' else (r10 < 0).mean()*100
        print(f"  FP price action ({d}?):")
        print(f"    5d:  mean={r5.mean():+.2f}% med={np.median(r5):+.2f}% favorable={fav5:.0f}%")
        print(f"    10d: mean={r10.mean():+.2f}% med={np.median(r10):+.2f}% favorable={fav10:.0f}%")

# ═══════════════════════════════════════════════════════════
banner("3. FEATURE PROFILE — High P vs Low P")
# ═══════════════════════════════════════════════════════════

key_feats = ['sigma_wave','sigma_tide','sigma_current','vwap_sigma_current','vwap_sigma_wave',
             'rsi_value','compression_ratio','current_accel','d_wave_accel',
             'kalman_velocity','vol_up_down_ratio','slope_decel_wave','slope_decel_current',
             'fear_level','complacency_index','rsi_extreme_zone','rsi_trap_zone']

for prob_col, label in [('p_zz_bottom', 'BOTTOM'), ('p_zz_top', 'TOP')]:
    section(f"Feature profile: {label}")
    high = df[df[prob_col] >= 0.80]
    low = df[df[prob_col] < 0.20]
    print(f"  N high={len(high):,d}  N low={len(low):,d}")
    print(f"  {'Feature':>25s} │ {'High P':>10s} │ {'Low P':>10s} │ {'Delta':>8s} │ {'Sig':>5s}")
    print(f"  {'─'*68}")
    for f in key_feats:
        if f not in df.columns: continue
        hm, lm = high[f].mean(), low[f].mean()
        d = hm - lm
        sig = "★★★" if abs(d) > 1.0 else "★★" if abs(d) > 0.5 else "★" if abs(d) > 0.2 else ""
        print(f"  {f:>25s} │ {hm:>+9.3f} │ {lm:>+9.3f} │ {d:>+7.3f} │ {sig:>5s}")

# ═══════════════════════════════════════════════════════════
banner("4. SIMULACIÓN DE TRADING")
# ═══════════════════════════════════════════════════════════

for prob_col, label, mult in [
    ('p_zz_bottom', 'Comprar en pisos (BOTTOM P≥0.80)', 1),
    ('p_zz_top', 'Vender en techos (TOP P≥0.80)', -1),
]:
    section(f"Simulación: {label}")
    signals = df[df[prob_col] >= 0.80]
    rets = {'5d':[], '10d':[], '20d':[]}
    
    for _, sig in signals.iterrows():
        ohlc = ohlcv_cache.get(sig['ticker'])
        if ohlc is None or sig['timestamp'] not in ohlc.index: continue
        pos = ohlc.index.get_loc(sig['timestamp'])
        entry = ohlc['close'].iloc[pos]
        for h, hz in [('5d',5),('10d',10),('20d',20)]:
            if pos+hz < len(ohlc):
                rets[h].append((ohlc['close'].iloc[pos+hz]/entry-1)*mult*100)
    
    for h in ['5d','10d','20d']:
        r = np.array(rets[h])
        if len(r) > 0:
            wr = (r>0).mean()*100
            sh = r.mean()/max(r.std(),0.01)
            print(f"    {h}: N={len(r):,d}  mean={r.mean():+.2f}%  med={np.median(r):+.2f}%  WR={wr:.0f}%  Sharpe={sh:.2f}")

# ═══════════════════════════════════════════════════════════
banner("5. OVERLAP CON HEADS EXISTENTES")
# ═══════════════════════════════════════════════════════════

# Score existing heads too
for head_name in ['long_entry', 'swing_exit', 'short_entry']:
    pkl_path = model_dir / f"head_{head_name}_v2.pkl"
    if pkl_path.exists():
        hp = pickle.load(open(pkl_path, "rb"))
        fc = [f for f in hp['feature_cols'] if f in df.columns]
        df[f'p_{head_name}'] = hp['model'].predict_proba(df[fc].fillna(0).values)[:, 1]

prob_cols = [c for c in df.columns if c.startswith('p_')]
if len(prob_cols) > 2:
    corr = df[prob_cols].corr()
    for c in ['p_zz_bottom', 'p_zz_top']:
        if c in corr:
            row = corr[c].drop(c).sort_values(key=abs, ascending=False)
            section(f"{c} correlaciones")
            for other, val in row.items():
                print(f"    vs {other:>20s}: {val:+.3f}")

store.close()
profile_store.close()
print("\n  ★ Forensia completa.")
