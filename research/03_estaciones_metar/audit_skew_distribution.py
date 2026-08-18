"""Get raw SKEW distribution from DB and analyze."""
import sys
sys.path.insert(0, '/root/botero-trade/backend')
sys.path.insert(0, '/root/botero-trade')
import numpy as np
import pandas as pd
from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

ds = TimescaleDataStore()

# Load SKEW raw bars
bars = ds.get_ohlcv_bars(ticker="SKEW", limit=100000)
print(f"SKEW bars: {len(bars)} rows")
print(f"Date range: {bars.iloc[0]['date']} to {bars.iloc[-1]['date']}")
vals = bars["close"].dropna().values
print(f"Non-null values: {len(vals)}")

print("\n=== SKEW RAW DISTRIBUTION ===")
print(f"  min:    {vals.min():.2f}")
print(f"  P1:     {np.percentile(vals, 1):.2f}")
print(f"  P2.5:   {np.percentile(vals, 2.5):.2f}")
print(f"  P5:     {np.percentile(vals, 5):.2f}")
print(f"  P10:    {np.percentile(vals, 10):.2f}")
print(f"  P25:    {np.percentile(vals, 25):.2f}")
print(f"  P50:    {np.percentile(vals, 50):.2f}")
print(f"  mean:   {vals.mean():.2f}")
print(f"  P75:    {np.percentile(vals, 75):.2f}")
print(f"  P90:    {np.percentile(vals, 90):.2f}")
print(f"  P95:    {np.percentile(vals, 95):.2f}")
print(f"  P97.5:  {np.percentile(vals, 97.5):.2f}")
print(f"  P99:    {np.percentile(vals, 99):.2f}")
print(f"  max:    {vals.max():.2f}")
print(f"  std:    {vals.std():.2f}")

# Histogram bins
print("\n=== HISTOGRAM (distribution by edge bins) ===")
edges = [109.1, 113.483649, 120.435, 136.436351, 153.650508]
labels = ['LOW (<109.1)', 'NORMAL (109.1-113.5)', 'ELEVATED (113.5-120.4)', 
          'HIGH (120.4-136.4)', 'TAIL_PARANOIA (136.4-153.7)', 'BLACK_SWAN (≥153.7)']
prev = float('-inf')
for i, e in enumerate(edges + [float('inf')]):
    if i == 0:
        cnt = np.sum(vals < e)
    elif i == len(edges):
        cnt = np.sum(vals >= prev)
    else:
        cnt = np.sum((vals >= prev) & (vals < e))
    pct = 100 * cnt / len(vals)
    print(f"  {labels[i]}: N={cnt:5d} ({pct:5.2f}%)")
    prev = e

# Classify every bar and count
print("\n=== CLASSIFIED BARS ===")
adapter = SkewLookupAdapter()
from collections import Counter
class_counts = Counter()
low_tail_dates = []
for _, row in bars.iterrows():
    cat = adapter._classify_d1(row["close"])
    class_counts[cat] += 1
    if cat == "LOW_TAIL_RISK":
        low_tail_dates.append(row["date"])

for label in adapter.labels_d1:
    print(f"  {label}: {class_counts.get(label, 0):5d} bars ({100*class_counts.get(label,0)/len(bars):.2f}%)")

print(f"\n=== LOW_TAIL_RISK DATES (N={len(low_tail_dates)}) ===")
for d in low_tail_dates:
    print(f"  {d}")

# Cluster LOW_TAIL_RISK into episodes
print("\n=== LOW_TAIL_RISK EPISODES (clustered, >=10d gap) ===")
if low_tail_dates:
    df = pd.DataFrame({'date': pd.to_datetime(low_tail_dates)}).sort_values('date')
    df['gap'] = df['date'].diff().dt.days
    df['episode'] = (df['gap'] > 10).cumsum()
    for ep, grp in df.groupby('episode'):
        dates = grp['date']
        print(f"  Episode {ep}: {dates.min().date()} to {dates.max().date()}, {len(dates)} bars")