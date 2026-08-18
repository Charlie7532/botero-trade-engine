import numpy as np, pandas as pd
from datetime import timedelta
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter

store = TimescaleDataStore(); repo = ZigzagLegRepository(store)
legs25 = repo.get_confirmed_legs("SPY","zz25")
spy = store.load_bars("SPY","1d")["close"].copy(); vix = store.load_bars("VIX","1d")["close"].copy()
spy.index = pd.to_datetime(spy.index); vix.index = pd.to_datetime(vix.index)
# Align
common = vix.index.intersection(spy.index)
vix = vix.loc[common]; spy = spy.loc[common]
vix_vel = vix.diff(3); vix_std2=vix.rolling(2).std(); vix_std10=vix.rolling(10).std()
vix_vol = (vix_std2/vix_std10).fillna(1.0)
store.close()

adapter = VIXLookupAdapter()

# Find all CRISIS_SPIKE bars
crisis_bars = []
for i in range(10, len(vix)-20):
    vv = vix.values[i]; ve = vix_vel.values[i]; vo = vix_vol.values[i]
    if np.isnan(vv) or np.isnan(ve) or np.isnan(vo): continue
    res = adapter.lookup_vix_guidance(val=vv, d3_speed=ve, vol_norm=vo, vol_d3=0.0)
    if "CRISIS_SPIKE" in res.state_key:
        crisis_bars.append({"date":vix.index[i],"spy":spy.values[i],"d1":res.state_key.split("__")[0]})

print(f"CRISIS_SPIKE bars: {len(crisis_bars)}")

# For each CRISIS_SPIKE bar, find nearest zigzag pivot (zz25)
pivot_dates = [(pd.to_datetime(l.start_timestamp).date(), l.start_type) for l in legs25]

dists = []; rets_from_bar = []; rets_from_pivot = []
for cb in crisis_bars:
    bar_date = cb["date"].date() if hasattr(cb["date"],'date') else pd.to_datetime(cb["date"]).date()
    bar_spy = cb["spy"]
    # Find closest future pivot
    dists_to_future = []
    for pd_d, ptype in pivot_dates:
        d = (pd_d - bar_date).days
        if d >= -2: dists_to_future.append((d, ptype, pd_d))
    if not dists_to_future: continue
    closest = min(dists_to_future, key=lambda x: abs(x[0]))
    dist = closest[0]; pivot_type = closest[1]; pivot_date = closest[2]
    dists.append(dist)
    
    # SPY from bar → bar+20 (positional)
    bar_pos = i
    if bar_pos+20 < len(spy):
        ret_from_bar = spy.values[bar_pos+20] / spy.values[bar_pos] - 1
        rets_from_bar.append(ret_from_bar)
    
    # SPY from PIVOT → pivot+20
    pivot_ts = pd.Timestamp(pivot_date)
    piv_positions = [j for j, dt in enumerate(spy.index) if dt.date() == pivot_date]
    if piv_positions:
        pidx = piv_positions[0]
        if pidx+20 < len(spy):
            ret_from_pivot = spy.values[pidx+20] / spy.values[pidx] - 1
            rets_from_pivot.append(ret_from_pivot)

dists = np.array(dists, dtype=float)
rets_bar = np.array(rets_from_bar)
rets_pivot = np.array(rets_from_pivot)

print(f"\n═══ CRISIS_SPIKE → ¿cuánto antes del zigzag? ═══\n")
print(f"  Días hasta el próximo pivote zz25:")
print(f"    media={dists.mean():.1f}d  mediana={np.median(dists):.0f}d  P25={np.percentile(dists,25):.0f}d  P75={np.percentile(dists,75):.0f}d")
print(f"    %negativo (pivote YA PASÓ): {(dists<0).mean()*100:.0f}%")
print(f"    día 0 (mismo día): {(dists==0).mean()*100:.0f}%")
print(f"    1-3d después: {(dists>=1).mean()*100-(dists>3).mean()*100:.0f}%")
print(f"    >3d después: {(dists>3).mean()*100:.0f}%")
print(f"\n  SPY 20d desde la BARRA CRISIS: media={rets_bar.mean()*100:+.2f}%  mediana={np.median(rets_bar)*100:+.2f}%")
print(f"  SPY 20d desde el PIVOTE zz25:  media={rets_pivot.mean()*100:+.2f}%  mediana={np.median(rets_pivot)*100:+.2f}%")
print(f"  DIFERENCIA perdida por anticiparse: {(rets_pivot.mean()-rets_bar.mean())*100:+.2f}%")

# If pivot is AFTER the bar, what's the drawdown?
after = dists > 0
if after.sum() > 5:
    dd = rets_pivot[after].mean() - rets_bar[after].mean()
    print(f"\n  Comprando {dists[after].mean():.1f}d ANTES del pivote:")
    print(f"    Retorno desde barra: {rets_bar[after].mean()*100:+.2f}%")
    print(f"    Retorno desde pivote: {rets_pivot[after].mean()*100:+.2f}%")
    print(f"    Drawdown evitado esperando al pivote: {dd*100:+.2f}%")