import numpy as np, pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

store = TimescaleDataStore(); repo = ZigzagLegRepository(store)
legs25 = repo.get_confirmed_legs("SPY","zz25")
spy = store.load_bars("SPY","1d")["close"].copy(); vix = store.load_bars("VIX","1d")["close"].copy()
spy.index = pd.to_datetime(spy.index); vix.index = pd.to_datetime(vix.index)
common = vix.index.intersection(spy.index); vix=vix.loc[common]; spy=spy.loc[common]
store.close()

# Zigzag legs: MIN = bottom (buy), MAX = top (sell)
legs = pd.DataFrame([{"start":pd.to_datetime(l.start_timestamp),"type":l.start_type} for l in legs25]).sort_values("start")

# Buy at MIN legs that start near a VIX crisis, sell at the next MAX
# Simpler: measure ALL MIN→MAX round trips (every bullish leg), then see
# which ones started in high VIX

min_legs = legs[legs["type"]=="MIN"].reset_index(drop=True)
max_legs = legs[legs["type"]=="MAX"].reset_index(drop=True)

round_trips = []
for _, mn in min_legs.iterrows():
    # find next MAX after this MIN
    next_max = max_legs[max_legs["start"] > mn["start"]]
    if len(next_max)==0: continue
    mx = next_max.iloc[0]
    buy_date = mn["start"]; sell_date = mx["start"]
    # SPY prices
    if buy_date in spy.index and sell_date in spy.index:
        buy_px = spy.loc[buy_date]; sell_px = spy.loc[sell_date]
        ret = sell_px/buy_px - 1
        days = (sell_date - buy_date).days
        # VIX at buy
        vix_at_buy = vix.loc[:buy_date].iloc[-1] if len(vix.loc[:buy_date])>0 else np.nan
        round_trips.append({"buy_date":buy_date,"sell_date":sell_date,"ret":ret,"days":days,"vix":vix_at_buy})

rt = pd.DataFrame(round_trips).dropna(subset=["vix"])
rt["vix_high"] = rt["vix"] >= 30
rt["vix_crisis"] = rt["vix"] >= 35

print(f"═══ ROUND-TRIP: MIN → MAX (comprar piso, vender techo) ═══\n")
print(f"  Total legs bull: {len(rt)}\n")
for label, mask in [("TODOS los MIN→MAX", pd.Series(True,index=rt.index)),
                     ("VIX ≥ 30 al comprar", rt["vix_high"]),
                     ("VIX ≥ 35 (crisis real)", rt["vix_crisis"])]:
    sub = rt[mask]
    if len(sub) < 3: continue
    print(f"  {label} (N={len(sub)}):")
    print(f"    retorno medio={sub['ret'].mean()*100:+.2f}%  mediana={sub['ret'].median()*100:+.2f}%")
    print(f"    duración media={sub['days'].mean():.1f}d  mediana={sub['days'].median():.0f}d")
    print(f"    win rate={(sub['ret']>0).mean()*100:.0f}%  max={sub['ret'].max()*100:+.1f}%  min={sub['ret'].min()*100:+.1f}%")
    print()

# When does the rebound EXHAUST? Distribution of leg duration for crisis legs
crisis_rt = rt[rt["vix_crisis"]]
print(f"═══ DURACIÓN del rebote post-crisis (VIX≥35) ═══")
print(f"  P25={crisis_rt['days'].quantile(0.25):.0f}d  P50={crisis_rt['days'].median():.0f}d  P75={crisis_rt['days'].quantile(0.75):.0f}d  P90={crisis_rt['days'].quantile(0.9):.0f}d")
print(f"  <5d: {(crisis_rt['days']<5).mean()*100:.0f}%  | 5-15d: {((crisis_rt['days']>=5)&(crisis_rt['days']<15)).mean()*100:.0f}%  | 15-30d: {((crisis_rt['days']>=15)&(crisis_rt['days']<30)).mean()*100:.0f}%  | >30d: {(crisis_rt['days']>=30).mean()*100:.0f}%")

# VIX normalization as exit signal
print(f"\n═══ EXIT: ¿cuándo VIX se normaliza? ═══")
# For crisis MIN legs, when does VIX drop back below 25?
norm_days = []
for _, r in crisis_rt.iterrows():
    buy = r["buy_date"]
    future_vix = vix.loc[buy:]
    below = future_vix[future_vix < 25]
    if len(below) > 0:
        norm_days.append((below.index[0] - buy).days)
if norm_days:
    norm_days = np.array(norm_days)
    print(f"  VIX vuelve <25 en: media={norm_days.mean():.1f}d  mediana={np.median(norm_days):.0f}d  P75={np.percentile(norm_days,75):.0f}d")