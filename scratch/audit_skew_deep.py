"""Deep dive: forward returns by ALL SKEW D1 bins, timing relative to crashes."""
import sys
sys.path.insert(0, '/root/botero-trade/backend')
sys.path.insert(0, '/root/botero-trade')
import numpy as np
import pandas as pd
from datetime import timedelta
from collections import defaultdict

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter

store = TimescaleDataStore()
adapter = SkewLookupAdapter()

# Load SPY + SKEW
spy_raw = store.load_bars("SPY", "1d")["close"].copy()
spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()

skew_raw = store.load_bars("SKEW", "1d")["close"].copy()
skew_raw.index = pd.to_datetime(skew_raw.index).normalize()
skew = skew_raw[~skew_raw.index.duplicated(keep="last")].sort_index()

common_dates = sorted(set(spy.index) & set(skew.index))
spy_aligned = spy.loc[common_dates]
skew_aligned = skew.loc[common_dates]
spy_dates = sorted(spy_aligned.index)
spy_values = {dt: float(spy_aligned[dt]) for dt in spy_dates}

print(f"Aligned: {len(common_dates)} bars, {common_dates[0].date()} → {common_dates[-1].date()}")

# ═══════════════════════════════════════════════════
# 1. Forward returns by ALL D1 bins
# ═══════════════════════════════════════════════════
print(f"\n{'='*100}")
print("FORWARD SPY RETURNS BY SKEW D1 BIN (de-clustered ≥10d)")
print(f"{'='*100}")
print(f"{'D1 Bin':<25} {'N':>4} {'3M mean':>9} {'3M med':>9} {'3M WR':>7} {'6M mean':>9} {'6M med':>9} {'6M WR':>7} {'12M mean':>9} {'12M med':>9} {'12M WR':>7} {'Worst3M':>9} {'Worst12M':>9}")

all_bin_results = {}
for d1_bin in adapter.labels_d1:
    # Find bars
    bars = []
    for dt in common_dates:
        val = float(skew_aligned[dt])
        cat = adapter._classify_d1(val)
        if cat == d1_bin:
            bars.append({"date": dt, "skew": val, "spy": float(spy_aligned[dt])})
    
    # De-cluster
    bars.sort(key=lambda x: x["date"])
    deduped = []
    last_date = None
    for bar in bars:
        if last_date is None or (bar["date"] - last_date).days >= 10:
            deduped.append(bar)
            last_date = bar["date"]
    
    all_bin_results[d1_bin] = deduped
    
    # Forward returns
    results = {}
    for h_label, h_trading in [("3M", 63), ("6M", 126), ("12M", 252)]:
        rets = []
        for bar in deduped:
            entry_date = bar["date"]
            entry_price = bar["spy"]
            future_dates = [d for d in spy_dates if d > entry_date]
            if len(future_dates) > 0:
                window = future_dates[:min(h_trading, len(future_dates))]
                if len(window) >= 5:
                    ret = (spy_values[window[-1]] / entry_price - 1) * 100
                    rets.append(ret)
        results[h_label] = {"returns": np.array(rets)} if rets else {"returns": np.array([])}
    
    n = len(deduped)
    r3 = results["3M"]["returns"]
    r6 = results["6M"]["returns"] 
    r12 = results["12M"]["returns"]
    
    print(f"{d1_bin:<25} {n:>4} "
          f"{r3.mean():9.2f} {np.median(r3):9.2f} {100*(r3>0).sum()/len(r3):6.1f}% " if len(r3)>0 else f"{'N/A':>36}",
          end="")
    print(f"{r6.mean():9.2f} {np.median(r6):9.2f} {100*(r6>0).sum()/len(r6):6.1f}% " if len(r6)>0 else f"{'N/A':>36}",
          end="")
    print(f"{r12.mean():9.2f} {np.median(r12):9.2f} {100*(r12>0).sum()/len(r12):6.1f}% " if len(r12)>0 else f"{'N/A':>36}",
          end="")
    worst3 = r3.min() if len(r3)>0 else np.nan
    worst12 = r12.min() if len(r12)>0 else np.nan
    print(f"{worst3:9.2f} {worst12:9.2f}")

# ═══════════════════════════════════════════════════
# 2. Bootstrap test: difference between LOW_TAIL_RISK and TAIL_PARANOIA
# ═══════════════════════════════════════════════════
print(f"\n{'='*100}")
print("BOOTSTRAP: LOW_TAIL_RISK vs TAIL_PARANOIA forward returns")
print(f"{'='*100}")

for h_label, h_trading in [("3M", 63), ("6M", 126), ("12M", 252)]:
    low_rets = []
    for bar in all_bin_results["LOW_TAIL_RISK"]:
        future = [d for d in spy_dates if d > bar["date"]]
        if len(future) > 0:
            window = future[:min(h_trading, len(future))]
            if len(window) >= 5:
                low_rets.append((spy_values[window[-1]] / bar["spy"] - 1) * 100)
    
    tp_rets = []
    for bar in all_bin_results["TAIL_PARANOIA"]:
        future = [d for d in spy_dates if d > bar["date"]]
        if len(future) > 0:
            window = future[:min(h_trading, len(future))]
            if len(window) >= 5:
                tp_rets.append((spy_values[window[-1]] / bar["spy"] - 1) * 100)
    
    low_rets = np.array(low_rets)
    tp_rets = np.array(tp_rets)
    
    diff = low_rets.mean() - tp_rets.mean()
    
    # Bootstrap CI
    rng = np.random.default_rng(42)
    diffs = []
    for _ in range(2000):
        l_sample = rng.choice(low_rets, size=len(low_rets), replace=True)
        t_sample = rng.choice(tp_rets, size=len(tp_rets), replace=True)
        diffs.append(l_sample.mean() - t_sample.mean())
    diffs = np.sort(diffs)
    ci_lo = np.percentile(diffs, 2.5)
    ci_hi = np.percentile(diffs, 97.5)
    p_two_tail = min(2 * (diffs < 0).mean(), 2 * (diffs > 0).mean())
    
    print(f"  {h_label}: LOW({len(low_rets)})={low_rets.mean():.2f}% vs PARA({len(tp_rets)})={tp_rets.mean():.2f}% "
          f"→ Δ={diff:.2f}%, CI95=[{ci_lo:.2f}, {ci_hi:.2f}], p={p_two_tail:.3f}")

# ═══════════════════════════════════════════════════
# 3. Does SKEW HIGH precede crashes or low?
# ═══════════════════════════════════════════════════
print(f"\n{'='*100}")
print("SKEW EXTREME EPISODES → NEAREST SPY CRASH (-20% from peak)")
print(f"{'='*100}")

# Find SPY drawdown events >20%
spy_series = spy_aligned.copy()
peak = spy_series.iloc[0]
crash_dates = []
for dt in spy_series.index:
    val = float(spy_series[dt])
    if val > peak:
        peak = val
    dd = (val / peak - 1) * 100
    if dd <= -20:
        # This bar is in a crash
        crash_dates.append(dt)

print(f"  SPY bars with >20% drawdown from peak: {len(crash_dates)}")

# For each de-clustered LOW_TAIL_RISK event, check if a crash followed within 6 months
print(f"\n  LOW_TAIL_RISK signals → did crash follow within 6 months?")
crash_follow_count = 0
for bar in all_bin_results["LOW_TAIL_RISK"]:
    entry = bar["date"]
    cutoff = entry + timedelta(days=180)
    crash_in_window = [d for d in crash_dates if entry <= d <= cutoff]
    if crash_in_window:
        crash_follow_count += 1
        # Get max dd in window
        max_dd = 0
        p = bar["spy"]
        for d in crash_in_window:
            dd = (spy_values[d] / p - 1) * 100
            max_dd = min(max_dd, dd)
        if max_dd < -10:
            print(f"    {entry.date()}: {len(crash_in_window)} crash bars, max DD={max_dd:.1f}%")
print(f"  LOW_TAIL_RISK → crash within 6mo: {crash_follow_count}/{len(all_bin_results['LOW_TAIL_RISK'])}")

# TAIL_PARANOIA → crash follows?
print(f"\n  TAIL_PARANOIA signals → did crash follow within 6 months?")
crash_follow_tp = 0
for bar in all_bin_results["TAIL_PARANOIA"]:
    entry = bar["date"]
    cutoff = entry + timedelta(days=180)
    crash_in_window = [d for d in crash_dates if entry <= d <= cutoff]
    if crash_in_window:
        crash_follow_tp += 1
print(f"  TAIL_PARANOIA → crash within 6mo: {crash_follow_tp}/{len(all_bin_results['TAIL_PARANOIA'])}")

# BLACK_SWAN_PARANOIA → crash follows?
print(f"\n  BLACK_SWAN_PARANOIA signals → did crash follow within 6 months?")
crash_follow_bs = 0
for bar in all_bin_results["BLACK_SWAN_PARANOIA"]:
    entry = bar["date"]
    cutoff = entry + timedelta(days=180)
    crash_in_window = [d for d in crash_dates if entry <= d <= cutoff]
    if crash_in_window:
        crash_follow_bs += 1
print(f"  BLACK_SWAN_PARANOIA → crash within 6mo: {crash_follow_bs}/{len(all_bin_results['BLACK_SWAN_PARANOIA'])}")

# ═══════════════════════════════════════════════════
# 4. Check: is SKEW a leading or lagging indicator?
# ═══════════════════════════════════════════════════
print(f"\n{'='*100}")
print("SKEW VALUE AT SPY PEAK (just before major crashes)")
print(f"{'='*100}")

# Major crash peaks
major_peaks = [
    ("2000-03-24", "Dot-com peak"),
    ("2007-10-09", "Pre-GFC peak"),
    ("2020-02-19", "Pre-COVID peak"),
    ("2022-01-03", "Pre-2022 bear peak"),
]

for peak_str, label in major_peaks:
    peak_dt = pd.Timestamp(peak_str).normalize()
    # Find nearest SKEW bar
    if peak_dt in skew_aligned.index:
        s = float(skew_aligned[peak_dt])
        cat = adapter._classify_d1(s)
        print(f"  {label}: SKEW={s:.2f} → {cat}")
    else:
        # Find nearest
        nearby = [d for d in common_dates if abs((d - peak_dt).days) <= 3]
        for d in nearby:
            s = float(skew_aligned[d])
            cat = adapter._classify_d1(s)
            print(f"  {label}: nearest={d.date()}, SKEW={s:.2f} → {cat}")

# Also check: what was SKEW classification at the BOTTOM of major crashes?
print(f"\n  SKEW AT CRASH BOTTOMS:")
major_bottoms = [
    ("2002-10-09", "Dot-com bottom"),
    ("2009-03-09", "GFC bottom"),
    ("2020-03-23", "COVID bottom"),
    ("2022-10-12", "2022 bear bottom"),
]
for bot_str, label in major_bottoms:
    bot_dt = pd.Timestamp(bot_str).normalize()
    if bot_dt in skew_aligned.index:
        s = float(skew_aligned[bot_dt])
        cat = adapter._classify_d1(s)
        print(f"  {label}: SKEW={s:.2f} → {cat}")
    else:
        nearby = [d for d in common_dates if abs((d - bot_dt).days) <= 3]
        for d in nearby:
            s = float(skew_aligned[d])
            cat = adapter._classify_d1(s)
            print(f"  {label}: nearest={d.date()}, SKEW={s:.2f} → {cat}")