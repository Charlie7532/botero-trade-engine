#!/usr/bin/env python3
"""
AUDITORÍA INTEGRAL DEL ENTRENADOR
==================================
Antes de re-entrenar NADA, verificamos:

1. FEATURE LAKE: duplicados, NaN, completitud
2. ZIGZAG POINTS: cálculo correcto, cobertura, consistencia
3. LABELING: cada label function produce resultados sanos
4. FEATURE CONSISTENCY: 56 vs 63 features, qué usa cada head
5. OHLCV CACHE: timestamps alineados con feature lake
"""
import sys, warnings, gc
from pathlib import Path
warnings.filterwarnings("ignore")
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend" / "scripts"))
from dotenv import load_dotenv; load_dotenv(root / ".env")

import numpy as np
import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore
from sqlalchemy import text

errors = []
warnings_list = []

def p(t): print(f"\n{'='*95}\n  {t}\n{'='*95}")
def ok(t): print(f"  ✅ {t}")
def warn(t): warnings_list.append(t); print(f"  ⚠️  {t}")
def fail(t): errors.append(t); print(f"  ❌ {t}")

store = TimescaleDataStore()
ps = TickerProfileStore()

# ═══════════════════════════════════════════════════════
p("1. FEATURE LAKE INTEGRITY")
# ═══════════════════════════════════════════════════════
from unified_pretrainer_v2 import load_feature_lake, ALL_FEATURES, DB_FEATURES, COMPUTED_FEATURES, PHASE1_FEATURES, DELTA_SOURCES

df, ohlcv_cache, profiles = load_feature_lake(store, ps)

# 1a. Duplicates
print(f"\n  ── 1a. Duplicate detection ──")
dupes = df.duplicated(subset=['ticker', 'timestamp'], keep=False)
n_dupes = dupes.sum()
if n_dupes > 0:
    fail(f"DUPLICATES: {n_dupes} duplicate (ticker, timestamp) rows!")
    dupe_examples = df[dupes].groupby('ticker').size()
    for tk, cnt in dupe_examples.items():
        print(f"    {tk}: {cnt} duplicates")
else:
    ok(f"0 duplicates in {len(df):,d} rows")

# 1b. NaN coverage per feature family
print(f"\n  ── 1b. NaN coverage ──")
DELTA_FEATURES = [f'd_{s}' for s in DELTA_SOURCES]
feature_groups = {
    'DB_FEATURES': DB_FEATURES,
    'COMPUTED': COMPUTED_FEATURES,
    'PHASE1': PHASE1_FEATURES,
    'DELTAS': DELTA_FEATURES,
}

for group_name, cols in feature_groups.items():
    present = [c for c in cols if c in df.columns]
    missing_cols = [c for c in cols if c not in df.columns]
    if missing_cols:
        fail(f"{group_name}: {len(missing_cols)} columns MISSING: {missing_cols}")
    
    if present:
        nan_pct = df[present].isna().mean() * 100
        high_nan = nan_pct[nan_pct > 5]
        if len(high_nan) > 0:
            warn(f"{group_name}: {len(high_nan)} columns with >5% NaN:")
            for col, pct in high_nan.items():
                print(f"    {col}: {pct:.1f}% NaN")
        else:
            ok(f"{group_name}: {len(present)} columns, all <5% NaN")

# 1c. Ticker distribution
print(f"\n  ── 1c. Ticker distribution ──")
tk_counts = df['ticker'].value_counts()
print(f"  Total: {len(df):,d} rows, {len(tk_counts)} tickers")
min_tk = tk_counts.min()
max_tk = tk_counts.max()
if min_tk < 100:
    warn(f"Min ticker count: {min_tk} (ticker: {tk_counts.idxmin()})")
else:
    ok(f"Min count: {min_tk:,d}, Max: {max_tk:,d}, Ratio: {max_tk/min_tk:.1f}x")
for tk, cnt in tk_counts.items():
    print(f"    {tk:>6s}: {cnt:,d}")

# 1d. Timestamp range
print(f"\n  ── 1d. Temporal coverage ──")
for tk in ['SPY', 'AAPL', 'MSFT']:
    tk_df = df[df['ticker'] == tk]
    if len(tk_df) > 0:
        ts_min = tk_df['timestamp'].min()
        ts_max = tk_df['timestamp'].max()
        ok(f"{tk}: {str(ts_min)[:10]} → {str(ts_max)[:10]} ({len(tk_df):,d} bars)")

# ═══════════════════════════════════════════════════════
p("2. ZIGZAG POINTS INTEGRITY")
# ═══════════════════════════════════════════════════════
zz = pd.read_sql(text(
    "SELECT * FROM engine.zigzag_points WHERE min_swing_pct=0.05 ORDER BY ticker, timestamp"),
    store.engine)
zz['timestamp'] = pd.to_datetime(zz['timestamp']).dt.tz_localize(None)

print(f"  Total zigzag points: {len(zz):,d}")
print(f"  MIN (bottoms): {(zz['tp_type']=='MIN').sum():,d}")
print(f"  MAX (tops): {(zz['tp_type']=='MAX').sum():,d}")

# 2a. Alternation check (MIN-MAX-MIN-MAX)
print(f"\n  ── 2a. Alternation check ──")
alt_errors = 0
for tk in zz['ticker'].unique():
    tk_zz = zz[zz['ticker'] == tk].sort_values('timestamp')
    types = tk_zz['tp_type'].values
    for i in range(1, len(types)):
        if types[i] == types[i-1]:
            alt_errors += 1
            if alt_errors <= 3:
                print(f"    {tk}: consecutive {types[i]} at idx {i}")

if alt_errors > 0:
    fail(f"ALTERNATION VIOLATED: {alt_errors} consecutive same-type points")
else:
    ok(f"All tickers have proper MIN-MAX alternation")

# 2b. Zigzag coverage per ticker
print(f"\n  ── 2b. ZZ coverage per ticker ──")
zz_tickers = set(zz['ticker'].unique())
fl_tickers = set(df['ticker'].unique())
missing_zz = fl_tickers - zz_tickers
if missing_zz:
    fail(f"Tickers in feature lake WITHOUT zigzag: {missing_zz}")
else:
    ok(f"All {len(fl_tickers)} feature lake tickers have zigzag points")

for tk in sorted(zz_tickers):
    tk_zz = zz[zz['ticker'] == tk]
    n_min = (tk_zz['tp_type'] == 'MIN').sum()
    n_max = (tk_zz['tp_type'] == 'MAX').sum()
    span = f"{str(tk_zz['timestamp'].min())[:10]} → {str(tk_zz['timestamp'].max())[:10]}"
    print(f"    {tk:>6s}: {n_min:>3d} bottoms, {n_max:>3d} tops ({span})")

# 2c. Zigzag price validation
print(f"\n  ── 2c. ZZ price sanity ──")
bad_prices = 0
for tk in zz['ticker'].unique():
    tk_zz = zz[zz['ticker'] == tk].sort_values('timestamp')
    ohlc = ohlcv_cache.get(tk)
    if ohlc is None:
        continue
    for _, zp in tk_zz.iterrows():
        ts = zp['timestamp']
        if ts in ohlc.index:
            actual_close = ohlc.loc[ts, 'close']
            zz_price = zp['price']
            pct_diff = abs(zz_price - actual_close) / actual_close * 100
            if pct_diff > 5:
                bad_prices += 1
                if bad_prices <= 3:
                    print(f"    {tk} {str(ts)[:10]}: ZZ={zz_price:.2f} vs OHLCV={actual_close:.2f} ({pct_diff:.1f}%)")

if bad_prices > 0:
    warn(f"{bad_prices} zigzag prices differ >5% from OHLCV close")
else:
    ok(f"All zigzag prices match OHLCV within 5%")

# 2d. Swing size validation (5% threshold)
print(f"\n  ── 2d. Minimum swing size ──")
small_swings = 0
for tk in zz['ticker'].unique():
    tk_zz = zz[zz['ticker'] == tk].sort_values('timestamp')
    prices = tk_zz['price'].values
    for i in range(1, len(prices)):
        swing = abs(prices[i] / prices[i-1] - 1) * 100
        if swing < 4.0:  # Slightly below 5% threshold
            small_swings += 1

if small_swings > 0:
    warn(f"{small_swings} swings < 4% (near threshold)")
else:
    ok(f"All swings ≥ 4% (consistent with 5% threshold)")

# ═══════════════════════════════════════════════════════
p("3. LABELING INTEGRITY")
# ═══════════════════════════════════════════════════════
from unified_pretrainer_v2 import (
    label_long_entry, label_swing_exit, label_pullback_depth,
    label_trend_reversal, label_short_entry, label_zz_turning_point,
    HEAD_CONFIGS
)

# 3a. long_entry label
print(f"\n  ── 3a. long_entry labeling ──")
labels_le = label_long_entry(df, ohlcv_cache, horizon=20)
n_valid = (~np.isnan(labels_le)).sum()
pos_rate = labels_le[~np.isnan(labels_le)].mean()
if 0.4 < pos_rate < 0.8:
    ok(f"long_entry: {n_valid:,d} valid, pos_rate={pos_rate:.3f} (expected ~0.60-0.70)")
else:
    warn(f"long_entry: pos_rate={pos_rate:.3f} — outside expected range")

# 3b. zigzag labels
print(f"\n  ── 3b. Zigzag labeling ──")
for tp_type, expected_name in [('MIN', 'zz_bottom'), ('MAX', 'zz_top')]:
    labels_zz = label_zz_turning_point(df, store, tp_type=tp_type, proximity_window=3)
    n_valid_zz = (~np.isnan(labels_zz)).sum()
    pos_rate_zz = labels_zz[~np.isnan(labels_zz)].mean()
    
    if 0.05 < pos_rate_zz < 0.25:
        ok(f"{expected_name}: {n_valid_zz:,d} valid, pos_rate={pos_rate_zz:.3f} (expected ~0.12)")
    else:
        warn(f"{expected_name}: pos_rate={pos_rate_zz:.3f} — outside 5-25% range")
    
    # Check: are positive labels actually near zigzag points?
    pos_idx = np.where(labels_zz == 1)[0]
    if len(pos_idx) > 0:
        pos_timestamps = df.iloc[pos_idx]['timestamp'].values
        tp_zz = zz[zz['tp_type'] == tp_type]
        # Sample 20 positive labels and check they're near a ZZ point
        sample_size = min(20, len(pos_idx))
        np.random.seed(42)
        sample_idx = np.random.choice(pos_idx, sample_size, replace=False)
        near_count = 0
        for si in sample_idx:
            row = df.iloc[si]
            row_ts = pd.Timestamp(row['timestamp'])
            if row_ts.tzinfo is not None:
                row_ts = row_ts.tz_localize(None)
            tk_zz = tp_zz[tp_zz['ticker'] == row['ticker']]
            if len(tk_zz) > 0:
                dists = abs((tk_zz['timestamp'] - row_ts).dt.days)
                min_dist = dists.min()
                if min_dist <= 3:
                    near_count += 1
        
        pct_near = near_count / sample_size * 100
        if pct_near >= 90:
            ok(f"{expected_name}: {pct_near:.0f}% of positive labels are within 3 bars of ZZ point")
        else:
            fail(f"{expected_name}: only {pct_near:.0f}% of positive labels near ZZ point — LABELING BUG?")

# ═══════════════════════════════════════════════════════
p("4. OHLCV CACHE ↔ FEATURE LAKE ALIGNMENT")
# ═══════════════════════════════════════════════════════
print(f"  OHLCV cache: {len(ohlcv_cache)} tickers")
for tk in sorted(ohlcv_cache.keys()):
    ohlc = ohlcv_cache[tk]
    fl_ts = set(df[df['ticker'] == tk]['timestamp'].values)
    ohlc_ts = set(ohlc.index.values)
    
    # How many feature lake timestamps exist in OHLCV?
    overlap = fl_ts & ohlc_ts
    pct = len(overlap) / max(len(fl_ts), 1) * 100
    
    if pct < 90:
        warn(f"{tk}: only {pct:.0f}% FL timestamps found in OHLCV ({len(overlap)}/{len(fl_ts)})")
    else:
        ok(f"{tk}: {pct:.0f}% aligned ({len(overlap):,d}/{len(fl_ts):,d})")

# ═══════════════════════════════════════════════════════
p("5. FEATURE SET CONSISTENCY")
# ═══════════════════════════════════════════════════════
import pickle
DELTA_FEATURES_LIST = [f'd_{s}' for s in DELTA_SOURCES]
features_56 = DB_FEATURES + COMPUTED_FEATURES + DELTA_FEATURES_LIST
features_63 = features_56 + PHASE1_FEATURES

print(f"  56-feature set: {len(features_56)}")
print(f"  63-feature set: {len(features_63)}")
print(f"  ALL_FEATURES: {len(ALL_FEATURES)}")

if len(features_63) != len(ALL_FEATURES):
    fail(f"63 computed ({len(features_63)}) != ALL_FEATURES ({len(ALL_FEATURES)})")
elif set(features_63) != set(ALL_FEATURES):
    fail(f"63 computed != ALL_FEATURES (set mismatch)")
else:
    ok(f"63-feature set matches ALL_FEATURES exactly")

# Check each model's features are a subset of available
for pkl_path in sorted(Path('backend/models').glob('head_*_v2.pkl')):
    data = pickle.load(open(pkl_path, 'rb'))
    name = pkl_path.stem.replace('head_','').replace('_v2','')
    model_cols = set(data['feature_cols'])
    available = set(ALL_FEATURES)
    
    missing = model_cols - available
    if missing:
        fail(f"{name}: model uses features NOT in ALL_FEATURES: {sorted(missing)}")
    else:
        in_56 = model_cols.issubset(set(features_56))
        label = "56-set" if in_56 else "63-set"
        ok(f"{name}: {len(model_cols)} features ({label})")

# ═══════════════════════════════════════════════════════
p("AUDIT SUMMARY")
# ═══════════════════════════════════════════════════════
print(f"  ❌ ERRORS: {len(errors)}")
for e in errors:
    print(f"    → {e}")
print(f"  ⚠️  WARNINGS: {len(warnings_list)}")
for w in warnings_list:
    print(f"    → {w}")

if len(errors) == 0:
    print(f"\n  ★★★ PRETRAINER INTEGRITY: VERIFIED ★★★")
else:
    print(f"\n  ✖ PRETRAINER INTEGRITY: {len(errors)} ISSUES — FIX BEFORE RETRAINING")

store.close()
ps.close()
