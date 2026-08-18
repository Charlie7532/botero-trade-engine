import numpy as np, pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter

store = TimescaleDataStore()
spy = store.load_bars("SPY","1d")["close"].copy(); vix = store.load_bars("VIX","1d")["close"].copy()
spy.index = pd.to_datetime(spy.index); vix.index = pd.to_datetime(vix.index)
common = vix.index.intersection(spy.index)
vix = vix.loc[common]; spy = spy.loc[common]
vix_vel = vix.diff(3); vix_std2=vix.rolling(2).std(); vix_std10=vix.rolling(10).std()
vix_vol = (vix_std2/vix_std10).fillna(1.0)
store.close()

adapter = VIXLookupAdapter()

# Find CRISIS_SPIKE entries (avoid clustering: min 10 days between entries)
entries = []
last_entry = -100
for i in range(10, len(vix)-40):
    vv = vix.values[i]; ve = vix_vel.values[i]; vo = vix_vol.values[i]
    if np.isnan(vv) or np.isnan(ve) or np.isnan(vo): continue
    res = adapter.lookup_vix_guidance(val=vv, d3_speed=ve, vol_norm=vo, vol_d3=0.0)
    if "CRISIS_SPIKE" in res.state_key and i - last_entry >= 10:
        entries.append(i); last_entry = i

print(f"═══ BENCHMARK: Comprar en CRISIS_SPIKE (N={len(entries)}) ═══\n")

# Benchmark: enter at bar_i, hold X days, measure return
for hold in [5, 10, 20, 40]:
    rets = []
    for ei in entries:
        if ei + hold < len(spy):
            r = spy.values[ei + hold] / spy.values[ei] - 1
            rets.append(r)
    rets = np.array(rets)
    if len(rets) < 3: continue
    win = (rets > 0).mean()
    print(f"  Hold {hold:>3}d: media={rets.mean()*100:+.2f}%  mediana={np.median(rets)*100:+.2f}%  P10={np.percentile(rets,10)*100:+.2f}%  P90={np.percentile(rets,90)*100:+.2f}%  min={rets.min()*100:+.2f}%  max={rets.max()*100:+.2f}%  win={win:.0f}%")

# Highlight worst trades
print(f"\n── PEORES TRADES (hold 20d) ──")
trades = [(ei, spy.values[min(ei+20,len(spy)-1)]/spy.values[ei]-1, str(vix.index[ei])[:10]) for ei in entries if ei+20<len(spy)]
trades.sort(key=lambda x: x[1])
for ei, ret, date in trades[:8]:
    print(f"  {date}: {ret*100:+.2f}%  (SPY={spy.values[ei]:.0f}, VIX={vix.values[ei]:.1f})")

# Total return if invested only during signals
print(f"\n── RENDIMIENTO ACUMULADO (entrar en CRISIS_SPIKE, hold 20d) ──")
cum = 1.0
for ei in entries:
    if ei + 20 < len(spy):
        cum *= (1 + spy.values[ei+20]/spy.values[ei] - 1)
print(f"  Retorno compuesto sobre {len(entries)} trades: {cum-1:+.2%}")

# SPY buy-and-hold over same period
first = entries[0]; last = entries[-1]+20
if last < len(spy): spy_bh = spy.values[last]/spy.values[first] - 1
print(f"  SPY buy-and-hold mismo período: {spy_bh:+.2%}")