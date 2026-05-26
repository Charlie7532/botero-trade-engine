"""
WALK-FORWARD VALIDATION — Fase 4 (Memory-Optimized)
=====================================================
López de Prado: train on past, test on future. No peeking.
Optimized for 4GB RAM: processes one head at a time.
"""
import sys, warnings, gc, time
from pathlib import Path
warnings.filterwarnings("ignore")
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend" / "scripts"))
from dotenv import load_dotenv; load_dotenv(root / ".env")

import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore
from sqlalchemy import text
from unified_pretrainer_v2 import load_feature_lake, ALL_FEATURES

store = TimescaleDataStore()
ps = TickerProfileStore()

# Load feature lake
df, ohlcv_cache, profiles = load_feature_lake(store, ps)
feature_cols = [f for f in ALL_FEATURES if f in df.columns]
print(f"  Feature lake: {len(df):,d} rows, {len(feature_cols)} features")

# Load zigzag
zz = pd.read_sql(text(
    "SELECT * FROM engine.zigzag_points WHERE min_swing_pct=0.05 ORDER BY ticker, timestamp"),
    store.engine)

# Normalize timestamps
df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
zz['timestamp'] = pd.to_datetime(zz['timestamp']).dt.tz_localize(None)
df['year'] = df['timestamp'].dt.year

# Pre-extract features as numpy (save memory later)
X_all = df[feature_cols].fillna(0).values.astype(np.float32)
years_arr = df['year'].values
print(f"  X shape: {X_all.shape}, dtype: {X_all.dtype}")

# Label zigzag heads
for tp_type, col in [('MIN', 'label_zz_bottom'), ('MAX', 'label_zz_top')]:
    tp_zz = zz[zz['tp_type'] == tp_type]
    df[col] = 0
    for _, zp in tp_zz.iterrows():
        mask = (df['ticker'] == zp['ticker']) & \
               (abs((df['timestamp'] - zp['timestamp']).dt.days) <= 3)
        df.loc[mask, col] = 1
    print(f"  {col}: {df[col].sum():,d} ({df[col].mean()*100:.1f}%)")

# Label long_entry vectorized
df['label_long'] = 0
for tk in df['ticker'].unique():
    tk_mask = df['ticker'] == tk
    ohlc = ohlcv_cache.get(tk)
    if ohlc is None: continue
    close = ohlc['close']
    fwd = close.shift(-20) / close - 1
    tk_ts = df.loc[tk_mask, 'timestamp']
    mapped = tk_ts.map(lambda t: fwd.get(t, np.nan))
    df.loc[tk_mask, 'label_long'] = (mapped > 0).astype(int).values
print(f"  label_long: {df['label_long'].sum():,d} ({df['label_long'].mean()*100:.1f}%)")

# Free memory
del ohlcv_cache, profiles
gc.collect()

years = sorted(df['year'].unique())
print(f"  Years: {years[0]}-{years[-1]} ({len(years)} years)")

store.close(); ps.close()

# ═══════════════════════════════════════════════════════════
MIN_TRAIN_YEARS = 3
XGB_PARAMS = dict(
    n_estimators=150,  # Reduced for memory
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    eval_metric='logloss',
    use_label_encoder=False,
)

for head_name, label_col in [
    ('zz_bottom_detector', 'label_zz_bottom'),
    ('zz_top_detector', 'label_zz_top'),
    ('long_entry', 'label_long'),
]:
    print(f"\n{'═'*100}")
    print(f"  HEAD: {head_name}")
    print(f"{'═'*100}")
    
    y_all = df[label_col].values
    results = []
    
    for test_year in years:
        if sum(1 for y in years if y < test_year) < MIN_TRAIN_YEARS:
            continue
        
        train_mask = years_arr < test_year
        test_mask = years_arr == test_year
        n_test = test_mask.sum()
        if n_test < 100:
            continue
        
        X_train, y_train = X_all[train_mask], y_all[train_mask]
        X_test, y_test = X_all[test_mask], y_all[test_mask]
        
        pos_rate = y_test.mean() * 100
        
        model = XGBClassifier(**XGB_PARAMS)
        model.fit(X_train, y_train, verbose=False)
        probs = model.predict_proba(X_test)[:, 1]
        
        del model; gc.collect()
        
        for thr in [0.65, 0.80]:
            fired = probs >= thr
            n_fired = fired.sum()
            wr = y_test[fired].mean() * 100 if n_fired > 0 else 0
            edge = wr - pos_rate if n_fired > 0 else 0
            results.append(dict(
                year=test_year, thr=thr, n_train=train_mask.sum(),
                n_test=n_test, n_fired=n_fired, base=pos_rate, wr=wr, edge=edge
            ))
        
        print(f"    {test_year}: train={train_mask.sum():,d} test={n_test:,d} "
              f"P≥.65 fired={results[-2]['n_fired']} edge={results[-2]['edge']:+.1f}% "
              f"P≥.80 fired={results[-1]['n_fired']} edge={results[-1]['edge']:+.1f}%")
    
    rdf = pd.DataFrame(results)
    
    for thr in [0.65, 0.80]:
        td = rdf[rdf['thr'] == thr]
        meaningful = td[td['n_fired'] > 10]
        if len(meaningful) == 0:
            print(f"\n  P≥{thr}: No meaningful samples")
            continue
        
        edges = meaningful['edge'].values
        pos = (edges > 0).sum()
        
        print(f"\n  ── SUMMARY P≥{thr:.2f} ({head_name}) ──")
        print(f"    Years tested: {len(meaningful)}")
        print(f"    Years with +edge: {pos}/{len(edges)} ({pos/len(edges)*100:.0f}%)")
        print(f"    Mean edge: {edges.mean():+.1f}%")
        print(f"    Median edge: {np.median(edges):+.1f}%")
        print(f"    Worst: {edges.min():+.1f}% | Best: {edges.max():+.1f}%")
        
        if edges.std() > 0:
            stab = edges.mean() / edges.std()
            verdict = "STABLE ✅" if stab > 1.0 else "MODERATE ⚠️" if stab > 0.5 else "UNSTABLE ❌"
            print(f"    Stability: {stab:.2f} → {verdict}")

print(f"\n  ★ Walk-forward complete.")
