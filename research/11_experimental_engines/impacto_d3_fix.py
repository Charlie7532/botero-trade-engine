import pandas as pd, numpy as np
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore(); conn = store._conn()
vix = pd.read_sql("SELECT time::date d, close FROM market.ohlcv_bars WHERE ticker='VIX' AND timeframe='1d' ORDER BY time", conn)
vix['d'] = pd.to_datetime(vix['d']).dt.tz_localize(None)
vix = vix.set_index('d')['close']
store.close()

d3_correct = (vix.rolling(2).std() / vix.rolling(10).std()).fillna(1.0)
d3_bug = (vix.rolling(5).std() / vix.rolling(20).std()).fillna(1.0)

edges = np.array([0.2859, 0.4605, 0.7474])

def classify(vals, edges):
    labels = np.zeros(len(vals), dtype=int)
    for i, e in enumerate(edges):
        labels[vals.values > e] = i + 1
    return labels

labels_correct = classify(d3_correct, edges)
labels_bug = classify(d3_bug, edges)

diff = (labels_correct != labels_bug)
n_total = (~d3_correct.isna() & ~d3_bug.isna()).sum()
n_diff = diff.sum()

print(f"Días totales: {n_total}")
print(f"Días con D3 distinto: {n_diff} ({n_diff/n_total*100:.1f}%)")
print(f"\nDistribución con std(2)/std(10) (CORRECTO):")
print(pd.Series(labels_correct).value_counts().sort_index().to_string())
print(f"\nDistribución con std(5)/std(20) (BUG anterior):")
print(pd.Series(labels_bug).value_counts().sort_index().to_string())
