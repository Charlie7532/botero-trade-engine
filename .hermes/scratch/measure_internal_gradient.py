#!/usr/bin/env python3
"""
Test: ¿hay gradiente OCULTO dentro del bin central (p25..p75) de cada dimensión?
Si al partir el centro en su mediana (p50) el EV difiere -> el diseño IMPAR (7) lo oculta -> favorece PAR (6).
Replica EXACTA del trainer: atr_pct ewma(14), slope_norm = slope/atr_pct, match forward zz50, net_return - friction.
"""
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.scripts.trainers.train_tide_ev_real_table import DEFAULT_FRICTION_BPS, MAX_HORIZON_DAYS

# umbrales globales (rc_vol_normalized_thresholds.json) — p25/p50/p75 por dimensión
TH = {
    "T":     (-0.891967, 2.491619, 5.893346),
    "C":     (-3.777905, 2.857450, 9.712965),
    "VWAP":  (-0.8292,   0.3804,   1.3320),
}
FRIC = DEFAULT_FRICTION_BPS
conn = TimescaleDataStore()._conn()

q_tickers = """
    SELECT ticker FROM market.ticker_metadata
    WHERE (industry IS NULL OR UPPER(industry) != 'INDICATOR')
      AND (sector IS NULL OR UPPER(sector) NOT IN (
          'INDICATOR','VOLUME BREADTH','CAP-WEIGHTED BREADTH','OPTIONS FLOW','VOLATILITY','SENTIMENT',
          'SHORT INTEREST','VOLUME INTENSITY','QQQ BREADTH','INDEX','YIELDS','BROAD MARKET','CURRENCY',
          'COMMODITIES','FIXED INCOME','FEAR & GREED','BREADTH'))
      AND ticker NOT IN ('VIX','VVIX','CBOE_PCR','FG','S5TH','S5FI','S5TW')
"""
tickers = pd.read_sql(q_tickers, conn)["ticker"].tolist()
print(f"tickers: {len(tickers)}", flush=True)

zz = pd.read_sql("SELECT ticker,timestamp,tp_type,price FROM engine.zigzag_points WHERE min_swing_pct=0.05 ORDER BY ticker,timestamp", conn)
zz['timestamp'] = pd.to_datetime(zz['timestamp'], utc=True)

# acumuladores por dimensión: [lo_sum, lo_n, hi_sum, hi_n]
acc = {k: [0.0, 0, 0.0, 0] for k in TH}
all_sn_t, all_sn_c, all_sn_v = [], [], []  # para sanity p50

def bucket(vals, rets, p25, p50, p75, a):
    m = (vals > p25) & (vals < p75)
    lo = m & (vals < p50); hi = m & (vals >= p50)
    a[0] += rets[lo].sum(); a[1] += int(lo.sum())
    a[2] += rets[hi].sum(); a[3] += int(hi.sum())

for i in range(0, len(tickers), 50):
    ch = tickers[i:i+50]
    ph = ",".join(f"'{t}'" for t in ch)
    s = pd.read_sql(f"SELECT ticker,timestamp,tide_slope,current_slope,vwap_sigma_wave FROM engine.channel_snapshots WHERE ticker IN ({ph}) AND timeframe='1d' ORDER BY ticker,timestamp", conn)
    b = pd.read_sql(f"SELECT ticker,time AS timestamp,high,low,close FROM market.ohlcv_bars WHERE ticker IN ({ph}) AND timeframe='1d' ORDER BY ticker,time", conn)
    if s.empty or b.empty: continue
    s['timestamp'] = pd.to_datetime(s['timestamp'], utc=True); b['timestamp'] = pd.to_datetime(b['timestamp'], utc=True)
    df = pd.merge(s, b, on=['ticker','timestamp']).dropna(subset=['close','high','low'])
    if df.empty: continue
    df = df.sort_values(['ticker','timestamp'])
    cp = df.groupby('ticker')['close'].shift(1)
    tr = pd.concat([df['high']-df['low'], (df['high']-cp).abs(), (df['low']-cp).abs()], axis=1).max(axis=1)
    ar = tr.groupby(df['ticker']).transform(lambda x: x.ewm(span=14, adjust=False).mean())
    df['atr_pct'] = (ar/df['close']).fillna(0.01).clip(lower=0.005)
    df['snT'] = df['tide_slope']/df['atr_pct']
    df['snC'] = df['current_slope']/df['atr_pct']
    df['snV'] = df['vwap_sigma_wave']
    zt = zz[zz['ticker'].isin(ch)]
    for tk, tdf in df.groupby('ticker'):
        tzz = zt[zt['ticker']==tk].sort_values('timestamp')
        if len(tzz)==0: continue
        zts = tzz['timestamp'].values; zpr = tzz['price'].values
        idx = np.searchsorted(zts, tdf['timestamp'].values, side='right')
        valid = idx < len(zts)
        if not valid.any(): continue
        vts = tdf['timestamp'].values[valid]; vcl = tdf['close'].values[valid]
        tgt = zpr[idx[valid]]; tts = zts[idx[valid]]
        days = ((tts-vts)/np.timedelta64(1,'D')).astype(float)
        hm = (days>0) & (days<=MAX_HORIZON_DAYS)
        ret = (tgt/vcl - 1.0) - FRIC
        vT = tdf['snT'].values[valid][hm]; vC = tdf['snC'].values[valid][hm]; vV = tdf['snV'].values[valid][hm]
        r = ret[hm]
        bucket(vT, r, *TH["T"], acc["T"])
        bucket(vC, r, *TH["C"], acc["C"])
        bucket(vV, r, *TH["VWAP"], acc["VWAP"])
        all_sn_t.append(vT); all_sn_c.append(vC); all_sn_v.append(vV)

at = np.concatenate(all_sn_t); ac = np.concatenate(all_sn_c); av = np.concatenate(all_sn_v)
print("\n=== SANITY: p50 de slope_norm calculado vs umbral ===")
print(f"  T   calc p50={np.median(at):.3f}  umbral={TH['T'][1]}")
print(f"  C   calc p50={np.median(ac):.3f}  umbral={TH['C'][1]}")
print(f"  VWAP calc p50={np.median(av):.3f} umbral={TH['VWAP'][1]}")

print("\n=== GRADIENTE INTERNO del bin central (p25..p75), split en p50 ===")
for k, a in acc.items():
    lo = a[0]/a[1] if a[1] else float('nan')
    hi = a[2]/a[3] if a[3] else float('nan')
    print(f"  {k:5s}: [p25,p50) EV={lo:+.4f} (n={a[1]:,})  |  [p50,p75] EV={hi:+.4f} (n={a[3]:,})  |  Δ={hi-lo:+.4f}")
