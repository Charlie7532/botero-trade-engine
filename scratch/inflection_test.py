import numpy as np, pandas as pd
from scipy.stats import spearmanr, chi2_contingency
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore(); conn = store._conn()

# Load SPY pivots with cascade labels
legs25 = pd.read_sql("SELECT start_timestamp, start_type, prev_leg_return FROM market.zigzag_legs WHERE ticker='SPY' AND scale='zz25' AND status='CONFIRMED' ORDER BY start_timestamp", conn)
legs50 = pd.read_sql("SELECT start_timestamp, start_type FROM market.zigzag_legs WHERE ticker='SPY' AND scale='zz50' AND status='CONFIRMED'", conn)
starts50 = set(pd.to_datetime(legs50['start_timestamp']).dt.tz_localize(None).dt.date)

legs25['ts'] = pd.to_datetime(legs25['start_timestamp']).dt.tz_localize(None)
legs25['pivot_date'] = legs25['ts'].dt.date
legs25['cascade'] = legs25['pivot_date'].apply(
    lambda d: int(any(d + pd.DateOffset(days=i) in starts50 for i in range(-3,4)))
)
# cascade=1 means CONTINUATION (trend continues). cascade=0 means REVERSAL (exhaustion).
legs25['reversal'] = 1 - legs25['cascade']

# Load VIX + PCR + SKEW with D1, D2, D3
def load_station(ticker):
    df = pd.read_sql(f"SELECT time::date d, close FROM market.ohlcv_bars WHERE ticker='{ticker}' AND timeframe='1d' ORDER BY time", conn)
    df['d'] = pd.to_datetime(df['d']).dt.tz_localize(None)
    return df.set_index('d')['close']

vix = load_station('VIX'); pcr = load_station('CBOE_PCR'); skew = load_station('SKEW')
store.close()

def d1d2d3(s, ts):
    """Return D1(level), D2(3d delta), D3(vol) at timestamp."""
    idx = s.index[s.index <= ts]
    if len(idx) == 0: return np.nan, np.nan, np.nan
    d1 = float(s.loc[idx[-1]])
    d2 = float(s.diff(3).loc[idx[-1]]) if len(s.diff(3).dropna().index[s.diff(3).dropna().index <= ts]) > 0 else np.nan
    d3_raw = (s.rolling(2).std() / s.rolling(10).std()).fillna(1.0)
    idx3 = d3_raw.index[d3_raw.index <= ts]
    d3 = float(d3_raw.loc[idx3[-1]]) if len(idx3) > 0 else np.nan
    return d1, d2, d3

for name, series in [('vix', vix), ('pcr', pcr), ('skew', skew)]:
    vals = [d1d2d3(series, ts) for ts in legs25['ts']]
    legs25[f'{name}_d1'] = [v[0] for v in vals]
    legs25[f'{name}_d2'] = [v[1] for v in vals]
    legs25[f'{name}_d3'] = [v[2] for v in vals]

y_rev = legs25['reversal'].dropna()  # reversal = 1 (trend exhausted)

print("═══ ¿Qué predice AGOTAMIENTO (reversal)? ═══\n")
print(f"{'Indicador':<20} {'D1(ρ)':>8} {'D2(ρ)':>8} {'D3(ρ)':>8}")

for name in ['vix','pcr','skew']:
    r1 = spearmanr(legs25[f'{name}_d1'].dropna(), y_rev[legs25[f'{name}_d1'].notna()])[0]
    r2 = spearmanr(legs25[f'{name}_d2'].dropna(), y_rev[legs25[f'{name}_d2'].notna()])[0]
    r3 = spearmanr(legs25[f'{name}_d3'].dropna(), y_rev[legs25[f'{name}_d3'].notna()])[0]
    print(f"{name.upper():<20} {r1:>+8.4f} {r2:>+8.4f} {r3:>+8.4f}")

# TEST: D1 extreme + D2 flip + D3 spike → reversal?
print("\n═══ INFLEXIÓN: D1 extremo + D2 flip + D3 spike ═══")

# D1 extreme = top/bottom 2.28%
# D2 flip = signo de D2 cambió en los últimos 3d
# D3 spike = vol > P84
for name in ['vix','pcr','skew']:
    d1_hi = legs25[f'{name}_d1'] > legs25[f'{name}_d1'].quantile(0.9772)
    d1_lo = legs25[f'{name}_d1'] < legs25[f'{name}_d1'].quantile(0.0228)
    d3_hi = legs25[f'{name}_d3'] > legs25[f'{name}_d3'].quantile(0.84)
    # D2 flip proxy: |D2| is large (velocity changing significantly)
    d2_change = legs25[f'{name}_d2'].abs() > legs25[f'{name}_d2'].abs().quantile(0.84)
    
    print(f"\n{name.upper()}:")
    combos = [
        ("normal", ~d1_hi),
        ("D1↑↑↑ solo", d1_hi),
        ("D1↑↑↑ + D2 cambio↑↑↑", d1_hi & d2_change),
        ("D1↑↑↑ + D2↑↑↑ + D3↑↑↑", d1_hi & d2_change & d3_hi),
    ]
    print(f"  {'Condición':<30} {'N':>5} {'%Reversal':>10}")
    for label, mask in combos:
        m = mask & y_rev.notna()
        if m.sum() >= 5:
            print(f"  {label:<30} {m.sum():>5} {legs25.loc[m, 'reversal'].mean()*100:>9.1f}%")

# Baseline
print(f"\n  Reversal rate global: {legs25['reversal'].mean()*100:.1f}%")