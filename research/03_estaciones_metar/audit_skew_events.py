"""SKEW at major market peaks and bottoms - fixed tz."""
import sys
sys.path.insert(0, '/root/botero-trade/backend')
sys.path.insert(0, '/root/botero-trade')
import numpy as np
import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter

store = TimescaleDataStore()
adapter = SkewLookupAdapter()

spy_raw = store.load_bars("SPY", "1d")["close"].copy()
spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()

skew_raw = store.load_bars("SKEW", "1d")["close"].copy()
skew_raw.index = pd.to_datetime(skew_raw.index).normalize()
skew = skew_raw[~skew_raw.index.duplicated(keep="last")].sort_index()

common_dates = sorted(set(spy.index) & set(skew.index))
# Ensure tz-naive
if common_dates and hasattr(common_dates[0], 'tz') and common_dates[0].tz is not None:
    common_dates = [d.tz_localize(None) for d in common_dates]

print("SKEW AT MAJOR MARKET PEAKS (before crashes):")
peaks = [
    (pd.Timestamp("2000-03-24").normalize(), "Dot-com peak"),
    (pd.Timestamp("2007-10-09").normalize(), "Pre-GFC peak"),
    (pd.Timestamp("2020-02-19").normalize(), "Pre-COVID peak"),
    (pd.Timestamp("2022-01-03").normalize(), "Pre-2022 bear peak"),
]
for peak_dt, label in peaks:
    if peak_dt in skew.index:
        s = float(skew[peak_dt])
        cat = adapter._classify_d1(s)
        print(f"  {label} ({peak_dt.date()}): SKEW={s:.2f} → {cat}")
    else:
        nearby = [(abs((d - peak_dt).days), d) for d in common_dates if abs((d - peak_dt).days) <= 5]
        for dist, d in sorted(nearby):
            s = float(skew[d])
            cat = adapter._classify_d1(s)
            print(f"  {label}: nearest={d.date()} ({dist}d away), SKEW={s:.2f} → {cat}")

print("\nSKEW AT MAJOR MARKET BOTTOMS:")
bottoms = [
    (pd.Timestamp("2002-10-09").normalize(), "Dot-com bottom"),
    (pd.Timestamp("2009-03-09").normalize(), "GFC bottom"),
    (pd.Timestamp("2020-03-23").normalize(), "COVID bottom"),
    (pd.Timestamp("2022-10-12").normalize(), "2022 bear bottom"),
]
for bot_dt, label in bottoms:
    if bot_dt in skew.index:
        s = float(skew[bot_dt])
        cat = adapter._classify_d1(s)
        print(f"  {label} ({bot_dt.date()}): SKEW={s:.2f} → {cat}")
    else:
        nearby = [(abs((d - bot_dt).days), d) for d in common_dates if abs((d - bot_dt).days) <= 5]
        for dist, d in sorted(nearby):
            s = float(skew[d])
            cat = adapter._classify_d1(s)
            print(f"  {label}: nearest={d.date()} ({dist}d away), SKEW={s:.2f} → {cat}")

# SKEW before specific crashes — was it high or low?
print("\nSKEW IN WEEKS BEFORE LEHMAN (Sep 15, 2008):")
lehman = pd.Timestamp("2008-09-15").normalize()
for d in common_dates:
    if pd.Timestamp("2008-08-15").normalize() <= d <= lehman:
        s = float(skew[d])
        cat = adapter._classify_d1(s)
        print(f"  {d.date()}: SKEW={s:.2f} → {cat}")

print("\nSKEW IN WEEKS AFTER COVID CRASH BEGAN (Feb 19 - Mar 23, 2020):")
for d in common_dates:
    if pd.Timestamp("2020-02-19").normalize() <= d <= pd.Timestamp("2020-03-23").normalize():
        s = float(skew[d])
        cat = adapter._classify_d1(s)
        print(f"  {d.date()}: SKEW={s:.2f} → {cat}")

# Also: what was the SKEW classification distribution in 2020 crash compared to 2008?
print("\nSKEW D1 BIN DISTRIBUTION DURING 2008 CRASH PERIOD (Sep 1 - Dec 31, 2008):")
from collections import Counter
bins_2008 = Counter()
for d in common_dates:
    if pd.Timestamp("2008-09-01").normalize() <= d <= pd.Timestamp("2008-12-31").normalize():
        s = float(skew[d])
        cat = adapter._classify_d1(s)
        bins_2008[cat] += 1
for label in adapter.labels_d1:
    print(f"  {label}: {bins_2008.get(label, 0)}")

print("\nSKEW D1 BIN DISTRIBUTION DURING 2020 CRASH PERIOD (Feb 19 - Mar 23, 2020):")
bins_2020 = Counter()
for d in common_dates:
    if pd.Timestamp("2020-02-19").normalize() <= d <= pd.Timestamp("2020-03-23").normalize():
        s = float(skew[d])
        cat = adapter._classify_d1(s)
        bins_2020[cat] += 1
for label in adapter.labels_d1:
    print(f"  {label}: {bins_2020.get(label, 0)}")