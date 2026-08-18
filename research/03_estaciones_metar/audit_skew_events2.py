"""SKEW at major market peaks and bottoms - fixed."""
import sys; sys.path.insert(0, '/root/botero-trade/backend'); sys.path.insert(0, '/root/botero-trade')
import numpy as np, pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter

store = TimescaleDataStore(); adapter = SkewLookupAdapter()

spy_raw = store.load_bars("SPY", "1d")["close"].copy()
skew_raw = store.load_bars("SKEW", "1d")["close"].copy()

# Force tz-naive
spy_raw.index = pd.to_datetime(spy_raw.index).tz_localize(None)
skew_raw.index = pd.to_datetime(skew_raw.index).tz_localize(None)
spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()
skew = skew_raw[~skew_raw.index.duplicated(keep="last")].sort_index()
common_dates = sorted(set(spy.index) & set(skew.index))

def classify(dt):
    s = float(skew[dt])
    return adapter._classify_d1(s), s

print("SKEW AT MAJOR MARKET PEAKS (before crashes):")
peaks = [
    (pd.Timestamp("2000-03-24"), "Dot-com peak"),
    (pd.Timestamp("2007-10-09"), "Pre-GFC peak"),
    (pd.Timestamp("2020-02-19"), "Pre-COVID peak"),
    (pd.Timestamp("2022-01-03"), "Pre-2022 bear peak"),
]
for peak_dt, label in peaks:
    if peak_dt in skew.index:
        cat, s = classify(peak_dt)
        print(f"  {label} ({peak_dt.date()}): SKEW={s:.2f} → {cat}")
    else:
        nearby = [(abs((d - peak_dt).days), d) for d in common_dates if abs((d - peak_dt).days) <= 5]
        for dist, d in sorted(nearby):
            cat, s = classify(d)
            print(f"  {label}: {d.date()} ({dist}d), SKEW={s:.2f} → {cat}")

print("\nSKEW AT MAJOR MARKET BOTTOMS:")
for bot_dt, label in [
    (pd.Timestamp("2002-10-09"), "Dot-com bottom"),
    (pd.Timestamp("2009-03-09"), "GFC bottom"),
    (pd.Timestamp("2020-03-23"), "COVID bottom"),
    (pd.Timestamp("2022-10-12"), "2022 bear bottom"),
]:
    if bot_dt in skew.index:
        cat, s = classify(bot_dt)
        print(f"  {label} ({bot_dt.date()}): SKEW={s:.2f} → {cat}")
    else:
        nearby = [(abs((d - bot_dt).days), d) for d in common_dates if abs((d - bot_dt).days) <= 5]
        for dist, d in sorted(nearby):
            cat, s = classify(d)
            print(f"  {label}: {d.date()} ({dist}d), SKEW={s:.2f} → {cat}")

print("\nSKEW BEFORE LEHMAN (Aug 15 - Sep 15, 2008):")
for d in common_dates:
    if pd.Timestamp("2008-08-15") <= d <= pd.Timestamp("2008-09-15"):
        cat, s = classify(d)
        print(f"  {d.date()}: SKEW={s:.2f} → {cat}")

print("\nSKEW DURING 2008 CRASH (Sep 1 - Dec 31, 2008):")
from collections import Counter
bins = Counter()
for d in common_dates:
    if pd.Timestamp("2008-09-01") <= d <= pd.Timestamp("2008-12-31"):
        cat, _ = classify(d)
        bins[cat] += 1
for label in adapter.labels_d1:
    print(f"  {label}: {bins.get(label, 0)}")

print("\nSKEW DURING 2020 CRASH (Feb 19 - Mar 23, 2020):")
bins = Counter()
for d in common_dates:
    if pd.Timestamp("2020-02-19") <= d <= pd.Timestamp("2020-03-23"):
        cat, _ = classify(d)
        bins[cat] += 1
for label in adapter.labels_d1:
    print(f"  {label}: {bins.get(label, 0)}")