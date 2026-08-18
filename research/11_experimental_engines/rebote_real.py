import numpy as np, pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore()
vix = store.load_bars("VIX","1d")["close"].copy(); spy = store.load_bars("SPY","1d")["close"].copy()
vix.index = pd.to_datetime(vix.index); spy.index = pd.to_datetime(spy.index)
common = vix.index.intersection(spy.index)
vix = vix.loc[common]; spy = spy.loc[common]
vix_vel = vix.diff(3); vix_vol = (vix.rolling(2).std()/vix.rolling(10).std()).fillna(1.0)
store.close()

vals=vix.values; vel_vals=vix_vel.values; vol_vals=vix_vol.values; spy_vals=spy.values; dates=vix.index

# Find VIX PEAKS: local maximum with VIX >= 30, then measure the REBOUND
results = []
for i in range(10, len(vals)-40):
    if vals[i] < 30: continue
    # Is this a LOCAL PEAK? (VIX >= neighbors within ±3 days)
    window = vals[max(0,i-3):min(len(vals),i+4)]
    if vals[i] < max(window): continue  # not a peak
    
    # This is a VIX SPIKE PEAK. Measure the REBOUND.
    # Entry: at the peak bar
    # Forward returns from this point
    ret_5 = spy_vals[min(i+5,len(spy_vals)-1)] / spy_vals[i] - 1
    ret_10 = spy_vals[min(i+10,len(spy_vals)-1)] / spy_vals[i] - 1
    ret_20 = spy_vals[min(i+20,len(spy_vals)-1)] / spy_vals[i] - 1
    ret_40 = spy_vals[min(i+40,len(spy_vals)-1)] / spy_vals[i] - 1
    
    d3 = vol_vals[i]
    vix_pico = vals[i]
    # Check D2 direction at peak
    d2_dir = "↑" if vel_vals[i] > 0 else "↓"
    
    results.append({"date":str(dates[i])[:10],"vix":vix_pico,"d3":d3,"d2_dir":d2_dir,
                    "ret5":ret_5,"ret10":ret_10,"ret20":ret_20,"ret40":ret_40})

df = pd.DataFrame(results).dropna()
print(f"═══ VIX PEAKS ≥ 30 — REBOTE REAL (N={len(df)}) ═══\n")
print(f"  SPY desde el PICO del VIX:")
print(f"    5d:  {df['ret5'].mean()*100:+.2f}%  mediana={df['ret5'].median()*100:+.2f}%  P25={df['ret5'].quantile(0.25)*100:+.2f}%  P75={df['ret5'].quantile(0.75)*100:+.2f}%")
print(f"    10d: {df['ret10'].mean()*100:+.2f}%  mediana={df['ret10'].median()*100:+.2f}%  P25={df['ret10'].quantile(0.25)*100:+.2f}%  P75={df['ret10'].quantile(0.75)*100:+.2f}%")
print(f"    20d: {df['ret20'].mean()*100:+.2f}%  mediana={df['ret20'].median()*100:+.2f}%  P25={df['ret20'].quantile(0.25)*100:+.2f}%  P75={df['ret20'].quantile(0.75)*100:+.2f}%")
print(f"    40d: {df['ret40'].mean()*100:+.2f}%  mediana={df['ret40'].median()*100:+.2f}%  P25={df['ret40'].quantile(0.25)*100:+.2f}%  P75={df['ret40'].quantile(0.75)*100:+.2f}%")

lo = df["d3"] < df["d3"].median(); hi = df["d3"] >= df["d3"].median()
print(f"\n── D3 split ──")
print(f"  D3 BAJA (N={lo.sum()}): 10d={df.loc[lo,'ret10'].mean()*100:+.2f}%  20d={df.loc[lo,'ret20'].mean()*100:+.2f}%  40d={df.loc[lo,'ret40'].mean()*100:+.2f}%")
print(f"  D3 ALTA (N={hi.sum()}): 10d={df.loc[hi,'ret10'].mean()*100:+.2f}%  20d={df.loc[hi,'ret20'].mean()*100:+.2f}%  40d={df.loc[hi,'ret40'].mean()*100:+.2f}%")