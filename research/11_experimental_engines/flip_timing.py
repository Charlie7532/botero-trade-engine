import numpy as np, pandas as pd
from datetime import timedelta

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

store = TimescaleDataStore(); repo = ZigzagLegRepository(store)

# SPY zigzag legs for timing
for scale in ["zz25","zz50","zz75"]:
    legs = repo.get_confirmed_legs("SPY", scale)
    globals()[f"legs_{scale}"] = pd.DataFrame([
        {"start": pd.to_datetime(l.start_timestamp).date(), "end": pd.to_datetime(l.end_timestamp).date(),
         "type": l.start_type} for l in legs
    ])

vix = store.load_bars("VIX","1d")["close"].copy(); spy = store.load_bars("SPY","1d")["close"].copy()
vix.index = pd.to_datetime(vix.index); spy.index = pd.to_datetime(spy.index)
common = vix.index.intersection(spy.index)
vix = vix.loc[common]; spy = spy.loc[common]
vix_vel = vix.diff(3)
vix_std2=vix.rolling(2).std(); vix_std10=vix.rolling(10).std(); vix_vol=(vix_std2/vix_std10).fillna(1.0)
store.close()

# Find VIX ≥ 30 + D2 flip ↓ events
vals=vix.values; vel_vals=vix_vel.values; vol_vals=vix_vol.values; dates=vix.index
events=[]

for i in range(10, len(vals)-20):
    if vals[i] >= 30 and vel_vals[i] < 0:
        # Was D2 positive recently? (flip)
        was_up = any(vel_vals[max(0,i-5):i] > 0)
        if not was_up: continue
        # D2 flip confirmed
        flip_date = dates[i].date()
        d3 = vol_vals[i]
        
        # How many days until next zigzag pivot at each scale?
        times = {}
        for scale in ["zz25","zz50","zz75"]:
            df_legs = globals()[f"legs_{scale}"]
            # Find next pivot after flip_date
            next_pivots = df_legs[df_legs["start"] >= flip_date]
            if len(next_pivots) > 0:
                next_date = next_pivots.iloc[0]["start"]
                days = (next_date - flip_date).days
            
        # SPY forward returns
        if i+20 < len(spy.values):
            spy_ret_5 = spy.values[i+5]/spy.values[i] - 1
            spy_ret_10 = spy.values[i+10]/spy.values[i] - 1
            spy_ret_20 = spy.values[i+20]/spy.values[i] - 1
        else:
            spy_ret_5 = spy_ret_10 = spy_ret_20 = np.nan
        
        events.append({"date":str(flip_date),"d3":d3,"spy_5":spy_ret_5,"spy_10":spy_ret_10,"spy_20":spy_ret_20})

df = pd.DataFrame(events)
print(f"═══ VIX ≥ 30 + D2 flip ↓ (N={len(df)}) ═══\n")
print(f"SPY retornos desde el flip:")
print(f"  5d:  media={df['spy_5'].mean()*100:+.2f}%  mediana={df['spy_5'].median()*100:+.2f}%  P25={df['spy_5'].quantile(0.25)*100:+.2f}%  P75={df['spy_5'].quantile(0.75)*100:+.2f}%  %positivo={(df['spy_5']>0).mean()*100:.0f}%")
print(f"  10d: media={df['spy_10'].mean()*100:+.2f}%  mediana={df['spy_10'].median()*100:+.2f}%  P25={df['spy_10'].quantile(0.25)*100:+.2f}%  P75={df['spy_10'].quantile(0.75)*100:+.2f}%  %positivo={(df['spy_10']>0).mean()*100:.0f}%")
print(f"  20d: media={df['spy_20'].mean()*100:+.2f}%  mediana={df['spy_20'].median()*100:+.2f}%  P25={df['spy_20'].quantile(0.25)*100:+.2f}%  P75={df['spy_20'].quantile(0.75)*100:+.2f}%  %positivo={(df['spy_20']>0).mean()*100:.0f}%")

# D3 split
lo_d3 = df["d3"] < df["d3"].quantile(0.50)
hi_d3 = df["d3"] >= df["d3"].quantile(0.50)
print(f"\n── D3 (volatilidad) split ──")
for label, mask in [("D3 BAJA (calma)", lo_d3), ("D3 ALTA (caos)", hi_d3)]:
    print(f"  {label} (N={mask.sum()}): SPY 5d={df.loc[mask,'spy_5'].mean()*100:+.2f}%  10d={df.loc[mask,'spy_10'].mean()*100:+.2f}%  20d={df.loc[mask,'spy_20'].mean()*100:+.2f}%  %pos5d={(df.loc[mask,'spy_5']>0).mean()*100:.0f}%")