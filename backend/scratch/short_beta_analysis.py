"""
Short_entry viability × Beta vs SPY
====================================
Which tickers have the best short edge AND highest beta?
High-beta tickers amplify SPY drops → better short candidates.
"""
import sys; sys.path.insert(0, '/root/botero-trade')
from dotenv import load_dotenv; load_dotenv('/root/botero-trade/.env')
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
import pandas as pd, numpy as np

store = TimescaleDataStore()

# Load OHLCV for beta calculation
ohlcv = pd.read_sql("""
    SELECT ticker, time, close 
    FROM market.ohlcv_bars 
    WHERE timeframe='1d' AND ticker IN (
        'SPY','QQQ','AAPL','MSFT','AMZN','COST','HD','HON',
        'IBM','JNJ','JPM','MCD','MRK','PEP','PG','WMT','XOM'
    )
    ORDER BY ticker, time
""", store.engine)

# Compute daily returns
ohlcv['ret'] = ohlcv.groupby('ticker')['close'].pct_change()

# SPY returns as benchmark
spy_ret = ohlcv[ohlcv['ticker'] == 'SPY'][['time', 'ret']].rename(columns={'ret': 'spy_ret'})

# Compute Beta for each ticker (last 5 years ~ 1260 trading days)
cutoff = spy_ret['time'].max() - pd.Timedelta(days=5*365)
spy_recent = spy_ret[spy_ret['time'] >= cutoff]

print(f"{'═' * 95}")
print(f"  SHORT_ENTRY VIABILITY × BETA vs SPY")
print(f"{'═' * 95}")

# Load short_entry performance from tape
tape = pd.read_sql("SELECT * FROM engine.signal_tape ORDER BY ticker, timestamp", store.engine)
bear_flat = tape[tape['regime'].isin(['BEAR', 'FLAT']) & tape['fwd_return_10d'].notna()].copy()

results = []
for ticker in sorted(ohlcv['ticker'].unique()):
    if ticker == 'SPY':
        continue
    
    tk_ret = ohlcv[ohlcv['ticker'] == ticker][['time', 'ret']].rename(columns={'ret': 'tk_ret'})
    merged = tk_ret.merge(spy_recent, on='time', how='inner').dropna()
    
    if len(merged) < 200:
        continue
    
    # Beta = Cov(tk, spy) / Var(spy)
    cov = merged['tk_ret'].cov(merged['spy_ret'])
    var_spy = merged['spy_ret'].var()
    beta = cov / var_spy if var_spy > 0 else 1.0
    
    # Correlation
    corr = merged['tk_ret'].corr(merged['spy_ret'])
    
    # Annualized vol
    ann_vol = merged['tk_ret'].std() * np.sqrt(252) * 100
    
    # Short_entry performance at P>0.60 in BEAR+FLAT
    short_data = bear_flat[(bear_flat['ticker'] == ticker) & (bear_flat['p_short_entry'] >= 0.60)]
    n_short = len(short_data)
    ret_10d = short_data['fwd_return_10d'].mean() * 100 if n_short > 5 else None
    ret_20d = short_data['fwd_return_20d'].mean() * 100 if n_short > 5 else None
    pneg = (short_data['fwd_return_10d'] < 0).mean() * 100 if n_short > 5 else None
    max_dd = short_data['fwd_max_dd_10d'].mean() * 100 if n_short > 5 else None
    
    # Short_entry at P>0.70
    short70 = bear_flat[(bear_flat['ticker'] == ticker) & (bear_flat['p_short_entry'] >= 0.70)]
    n70 = len(short70)
    ret70 = short70['fwd_return_10d'].mean() * 100 if n70 > 5 else None
    
    results.append({
        'ticker': ticker, 'beta': beta, 'corr': corr, 'ann_vol': ann_vol,
        'n_short_60': n_short, 'ret_10d_60': ret_10d, 'ret_20d_60': ret_20d,
        'pneg_60': pneg, 'max_dd_60': max_dd,
        'n_short_70': n70, 'ret_10d_70': ret70,
    })

rdf = pd.DataFrame(results).sort_values('beta', ascending=False)

# Table 1: Beta ranking
print(f"\n  ── Beta vs SPY (5y) — ranked by beta ──")
print(f"  {'Ticker':>6s} │ {'Beta':>5s} │ {'Corr':>5s} │ {'Vol%':>5s} │ {'N@0.6':>6s} │ {'Ret10d':>7s} │ {'Ret20d':>7s} │ {'P(neg)':>7s} │ {'MaxDD':>7s} │ {'N@0.7':>5s} │ {'R10@0.7':>8s}")
print(f"  {'─'*95}")
for _, r in rdf.iterrows():
    r10 = f"{r['ret_10d_60']:+6.2f}%" if r['ret_10d_60'] is not None else "   n/a"
    r20 = f"{r['ret_20d_60']:+6.2f}%" if r['ret_20d_60'] is not None else "   n/a"
    pn = f"{r['pneg_60']:5.1f}%" if r['pneg_60'] is not None else "  n/a"
    dd = f"{r['max_dd_60']:+6.2f}%" if r['max_dd_60'] is not None else "   n/a"
    r70 = f"{r['ret_10d_70']:+6.2f}%" if r['ret_10d_70'] is not None else "    n/a"
    
    # Categorize
    if r['beta'] >= 1.2:
        cat = "🔴 HIGH-β"
    elif r['beta'] >= 0.9:
        cat = "🟡 MID-β"
    else:
        cat = "🟢 LOW-β"
    
    print(f"  {r['ticker']:>6s} │ {r['beta']:5.2f} │ {r['corr']:5.2f} │ {r['ann_vol']:4.1f}% │ {r['n_short_60']:>6d} │ {r10:>7s} │ {r20:>7s} │ {pn:>7s} │ {dd:>7s} │ {r['n_short_70']:>5d} │ {r70:>8s} │ {cat}")

# Analysis: does Beta predict short edge?
print(f"\n  ── Correlación Beta → Short Edge ──")
valid_r = rdf[rdf['ret_10d_60'].notna()]
corr_beta_ret = valid_r['beta'].corr(valid_r['ret_10d_60'])
corr_beta_pneg = valid_r['beta'].corr(valid_r['pneg_60'])
print(f"    corr(Beta, Ret_10d_short): r = {corr_beta_ret:+.4f}")
print(f"    corr(Beta, P(neg)_short):  r = {corr_beta_pneg:+.4f}")

# Best short candidates: high beta + strong short signal
print(f"\n  ── BEST SHORT CANDIDATES (Beta > 1.0 AND Ret_10d < -2.5%) ──")
best = valid_r[(valid_r['beta'] > 1.0) & (valid_r['ret_10d_60'] < -2.5)]
for _, r in best.sort_values('ret_10d_60').iterrows():
    print(f"    {r['ticker']:>6s}: β={r['beta']:.2f}  ret_10d={r['ret_10d_60']:+.2f}%  ret_20d={r['ret_20d_60']:+.2f}%  P(neg)={r['pneg_60']:.1f}%")

# Defensive shorts: low beta but still work
print(f"\n  ── DEFENSIVE SHORTS (Beta < 0.9 AND still viable) ──")
defensive = valid_r[(valid_r['beta'] < 0.9) & (valid_r['ret_10d_60'] < -1.5)]
for _, r in defensive.sort_values('ret_10d_60').iterrows():
    print(f"    {r['ticker']:>6s}: β={r['beta']:.2f}  ret_10d={r['ret_10d_60']:+.2f}%  ret_20d={r['ret_20d_60']:+.2f}%  P(neg)={r['pneg_60']:.1f}%")

store.close()
print(f"\n{'═' * 95}")
print(f"  ANALYSIS COMPLETE")
print(f"{'═' * 95}")
