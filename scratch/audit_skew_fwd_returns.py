"""Forward SPY returns after SKEW LOW_TAIL_RISK signals — max drawdown at 3/6/12 months."""
import sys
sys.path.insert(0, '/root/botero-trade/backend')
sys.path.insert(0, '/root/botero-trade')
import numpy as np
import pandas as pd
from datetime import timedelta

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter

store = TimescaleDataStore()

# Load SPY
spy_raw = store.load_bars("SPY", "1d")["close"].copy()
spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()

# Load SKEW
skew_raw = store.load_bars("SKEW", "1d")["close"].copy()
skew_raw.index = pd.to_datetime(skew_raw.index).normalize()
skew = skew_raw[~skew_raw.index.duplicated(keep="last")].sort_index()

# Align
common_dates = sorted(set(spy.index) & set(skew.index))
spy_aligned = spy.loc[common_dates]
skew_aligned = skew.loc[common_dates]
print(f"Aligned bars: {len(common_dates)} from {common_dates[0].date()} to {common_dates[-1].date()}")

adapter = SkewLookupAdapter()

# Find all LOW_TAIL_RISK bars
low_tail_bars = []
for dt in common_dates:
    val = float(skew_aligned[dt])
    cat = adapter._classify_d1(val)
    if cat == "LOW_TAIL_RISK":
        low_tail_bars.append({"date": dt, "skew": val, "spy": float(spy_aligned[dt])})

print(f"LOW_TAIL_RISK bars: {len(low_tail_bars)}")

# De-cluster: first signal in each window of >=10 trading days
low_tail_bars.sort(key=lambda x: x["date"])
deduped = []
last_date = None
for bar in low_tail_bars:
    if last_date is None or (bar["date"] - last_date).days >= 10:
        deduped.append(bar)
        last_date = bar["date"]

print(f"De-clustered signals (≥10d): {len(deduped)}")

# Count since 2005
since_2005 = [b for b in deduped if b["date"].year >= 2005]
print(f"De-clustered signals since 2005: {len(since_2005)}")
for b in since_2005:
    print(f"  {b['date'].date()}: SKEW={b['skew']:.2f}, SPY={b['spy']:.2f}")

# FORWARD RETURNS + MAX DRAWDOWN analysis
HORIZONS_TRADING = [63, 126, 252]  # ~3mo, ~6mo, ~12mo
HORIZONS_CALENDAR = [90, 180, 365]  # calendar days

spy_dates = sorted(spy_aligned.index)
spy_values = {dt: float(spy_aligned[dt]) for dt in spy_dates}

print(f"\n{'='*100}")
print(f"FORWARD SPY MAX DRAWDOWN AFTER LOW_TAIL_RISK SIGNALS (N={len(deduped)})")
print(f"{'='*100}")
print(f"{'Signal Date':<12} {'SKEW':>7} {'SPY':>8} {'3M Return%':>10} {'6M Return%':>10} {'12M Return%':>10} {'3M MaxDD%':>10} {'6M MaxDD%':>10} {'12M MaxDD%':>10} {'Win/Loss':>8}")

all_results = []
for bar in deduped:
    entry_date = bar["date"]
    entry_price = bar["spy"]
    
    row = {"date": entry_date, "skew": bar["skew"], "spy_entry": entry_price}
    
    for h_days, h_label in [(63, "3M"), (126, "6M"), (252, "12M")]:
        # Find end date (calendar)
        target_date = entry_date + timedelta(days=int(h_days * 1.4))  # trading→calendar, approx
        future_dates = [d for d in spy_dates if d > entry_date]
        
        if len(future_dates) == 0:
            row[f"{h_label}_ret"] = np.nan
            row[f"{h_label}_maxdd"] = np.nan
            continue
            
        # Take next min(h_days, len(future_dates)) trading days
        window_dates = future_dates[:min(h_days, len(future_dates))]
        if len(window_dates) < 5:
            row[f"{h_label}_ret"] = np.nan
            row[f"{h_label}_maxdd"] = np.nan
            continue
            
        peak = entry_price
        max_dd = 0.0
        end_price = spy_values[window_dates[-1]]
        
        for d in window_dates:
            price = spy_values[d]
            peak = max(peak, price)
            dd = (price / peak - 1) * 100
            max_dd = min(max_dd, dd)  # more negative = worse
            
        fwd_ret = (end_price / entry_price - 1) * 100
        row[f"{h_label}_ret"] = fwd_ret
        row[f"{h_label}_maxdd"] = max_dd
    
    all_results.append(row)
    
    print(f"{entry_date.date()}  {bar['skew']:7.2f} {entry_price:8.2f} "
          f"{row.get('3M_ret', np.nan):10.2f} {row.get('6M_ret', np.nan):10.2f} {row.get('12M_ret', np.nan):10.2f} "
          f"{row.get('3M_maxdd', np.nan):10.2f} {row.get('6M_maxdd', np.nan):10.2f} {row.get('12M_maxdd', np.nan):10.2f}")

# Summary stats
print(f"\n{'='*100}")
print("SUMMARY STATISTICS")
print(f"{'='*100}")

for h_label in ["3M", "6M", "12M"]:
    rets = np.array([r[f"{h_label}_ret"] for r in all_results if not np.isnan(r.get(f"{h_label}_ret", np.nan))])
    dds = np.array([r[f"{h_label}_maxdd"] for r in all_results if not np.isnan(r.get(f"{h_label}_maxdd", np.nan))])
    
    if len(rets) > 0:
        wins = (rets > 0).sum()
        wr = 100 * wins / len(rets)
        print(f"\n{h_label} HORIZON (N={len(rets)}):")
        print(f"  Return: mean={rets.mean():.2f}%, median={np.median(rets):.2f}%, "
              f"min={rets.min():.2f}%, max={rets.max():.2f}%")
        print(f"  Win Rate: {wins}/{len(rets)} = {wr:.1f}%")
        print(f"  Max Drawdown: mean={dds.mean():.2f}%, median={np.median(dds):.2f}%, "
              f"worst={dds.min():.2f}%")

# Also check: BLACK_SWAN_PARANOIA forward returns for comparison
print(f"\n{'='*100}")
print("COMPARISON: BLACK_SWAN_PARANOIA (SKEW ≥ 153.65) FORWARD RETURNS")
print(f"{'='*100}")

bs_bars = []
for dt in common_dates:
    val = float(skew_aligned[dt])
    cat = adapter._classify_d1(val)
    if cat == "BLACK_SWAN_PARANOIA":
        bs_bars.append({"date": dt, "skew": val, "spy": float(spy_aligned[dt])})

bs_bars.sort(key=lambda x: x["date"])
bs_deduped = []
last_date = None
for bar in bs_bars:
    if last_date is None or (bar["date"] - last_date).days >= 10:
        bs_deduped.append(bar)
        last_date = bar["date"]

print(f"BLACK_SWAN_PARANOIA de-clustered signals: {len(bs_deduped)}")
for h_label in ["3M", "6M", "12M"]:
    rets = []
    for bar in bs_deduped:
        entry_date = bar["date"]
        entry_price = bar["spy"]
        future_dates = [d for d in spy_dates if d > entry_date]
        if len(future_dates) > 0:
            window_dates = future_dates[:min({"3M":63, "6M":126, "12M":252}[h_label], len(future_dates))]
            if len(window_dates) >= 5:
                ret = (spy_values[window_dates[-1]] / entry_price - 1) * 100
                rets.append(ret)
    
    if rets:
        rets = np.array(rets)
        wins = (rets > 0).sum()
        print(f"  {h_label}: N={len(rets)}, mean={rets.mean():.2f}%, "
              f"median={np.median(rets):.2f}%, win_rate={100*wins/len(rets):.1f}%")