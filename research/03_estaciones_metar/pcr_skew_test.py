import numpy as np, pandas as pd
from scipy.stats import spearmanr
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore(); conn = store._conn()

tickers = {"skew": "SKEW", "pcr": "CBOE_PCR"}
series = {}
for name, ticker in tickers.items():
    df = pd.read_sql(f"SELECT time::date d, close FROM market.ohlcv_bars WHERE ticker='{ticker}' AND timeframe='1d' ORDER BY time", conn)
    df['d'] = pd.to_datetime(df['d']).dt.tz_localize(None)
    series[name] = df.set_index('d')['close']

pivots = pd.read_sql("SELECT start_timestamp, start_type FROM market.zigzag_legs WHERE ticker='SPY' AND scale='zz25' AND status='CONFIRMED' ORDER BY start_timestamp", conn)
pivots['ts'] = pd.to_datetime(pivots['start_timestamp']).dt.tz_localize(None)
pivots['next_type'] = pivots['start_type'].shift(-1)
pivots['next_bear'] = (pivots['next_type'] == 'MIN').astype(float)

store.close()

def lkp(s, ts):
    idx = s.index[s.index <= ts]
    return float(s.loc[idx[-1]]) if len(idx) > 0 else np.nan

def ic_rho(a, b):
    m = a.notna() & b.notna()
    return spearmanr(a[m], b[m])[0] if m.sum() >= 30 else np.nan

for name, s in series.items():
    d1 = [lkp(s, ts) for ts in pivots['ts']]
    d2 = [lkp(s.diff(3), ts) for ts in pivots['ts']]
    std2 = s.rolling(2).std(); std10 = s.rolling(10).std()
    d3_raw = (std2 / std10).fillna(1.0)
    d3 = [lkp(d3_raw, ts) for ts in pivots['ts']]
    pivots[f'{name}_d1'] = d1; pivots[f'{name}_d2'] = d2; pivots[f'{name}_d3'] = d3

y = pivots['next_bear'].dropna()

print("═══ PCR + SKEW — Predicción de dirección del próximo leg ═══\n")
for name in ["pcr", "skew"]:
    print(f"{name.upper()}:")
    print(f"  D1 (nivel)    → dir: ρ={ic_rho(pivots[f'{name}_d1'], y):+.4f}")
    print(f"  D2 (velocidad) → dir: ρ={ic_rho(pivots[f'{name}_d2'], y):+.4f}")

# Extremes
pcr_hi = pivots['pcr_d1'] > pivots['pcr_d1'].quantile(0.9772)
pcr_lo = pivots['pcr_d1'] < pivots['pcr_d1'].quantile(0.0228)
skew_hi = pivots['skew_d1'] > pivots['skew_d1'].quantile(0.84)
skew_lo = pivots['skew_d1'] < pivots['skew_d1'].quantile(0.16)

print("\n═══ PCR EXTREMO × SKEW — Combinaciones ═══")
print(f"{'Condición':<40} {'N':>5} {'%Bear':>8}")
combos = [
    ("PCR↑↑↑ + SKEW↑↑ (pánico total)", pcr_hi & skew_hi),
    ("PCR↑↑↑ + SKEW↓ (miedo sin pánico)", pcr_hi & skew_lo),
    ("PCR↓↓↓ + SKEW↑↑ (euforia + smart cubierto)", pcr_lo & skew_hi),
    ("PCR↓↓↓ + SKEW↓ (complacencia total)", pcr_lo & skew_lo),
    ("PCR↑↑↑ solo", pcr_hi),
    ("PCR↓↓↓ solo", pcr_lo),
    ("SKEW↑↑ solo", skew_hi),
    ("Línea base", pd.Series(True, index=pivots.index)),
]
for label, mask in combos:
    m = mask & y.notna()
    print(f"{label:<40} {m.sum():>5} {y[m].mean()*100:>7.1f}%")

# PCR D2 direction
pcr_d2_up = pivots['pcr_d2'] > 0
print(f"\n═══ PCR D2 dirección ═══")
for nm, mk in [("D2↑ (pánico acelerando)", pcr_d2_up), ("D2↓ (pánico desacelerando)", ~pcr_d2_up)]:
    m = mk & y.notna()
    print(f"  {nm:<30}: %bear={y[m].mean()*100:.1f}% (N={m.sum()})")