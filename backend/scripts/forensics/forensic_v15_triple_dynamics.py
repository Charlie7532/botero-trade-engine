#!/usr/bin/env python3
"""
Forensic Lab v15 — TRIPLE LINE DYNAMICS & PATTERN DISCOVERY
==============================================================
The 3 regression lines TELL A STORY. This script reads it.

PART 1: PER-WINDOW SENTIMENT (3 fear readings, not just 1)
  - TIDE 240: macro institutional sentiment
  - CURRENT 60: quarterly sentiment (accumulation/distribution cycle)
  - WAVE 30: short-term sentiment (surfing the wave)
  - How do they conjugate? What STORY do they create?

PART 2: WAVE FLIP EVENT STUDY
  - When wave_slope changes sign rapidly, what happens next?
  - Is it a signal? In how many bars does it resolve?
  - Wave flip + tide direction = ?

PART 3: DIVERGENCE PATTERNS
  - Regression σ vs VWAP σ tension per window
  - When they diverge: mean-reversion speed, probability, failure rate
  - Triple agreement (all 3 tensions same sign) → strongest signal?

PART 4: TREND CHANGE DETECTION
  - Slope sign changes across timeframes
  - When wave flips but tide holds → pullback (buy)
  - When current flips against tide → regime transition (danger)
  - When tide flips → everything changes

PART 5: SIGMA CROSS EVENTS
  - When sigma crosses -1.5 → entry territory
  - When vwap_sigma crosses 0 → institutional level reached
  - How many bars to target? What WR?

Uses production compute_channel_snapshot().
Uses store.load_bars() exclusively (Vault-first).
"""

import os, sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import pandas as pd
import numpy as np
from scipy import stats

from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def p(t): print(f"\n{'='*95}\n  {t}\n{'='*95}")
def sp(t): print(f"\n  ── {t} ──")

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD",
    "HON", "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP",
    "PG", "WMT", "XOM",
]


# ═══════════════════════════════════════════════════════════
# DATA: Compute ChannelSnapshot at EVERY bar for each ticker
# ═══════════════════════════════════════════════════════════

# Window presets per timeframe.
# Daily: 240/60/cycle(8-50)  — the default, validated in v13/v14.
# 5min:  78 bars/day → proportional scaling.
#   TIDE  = 240 days × 78 = 18720 (too many, impractical)
#   → Use 780 bars (~10 days) as 5min TIDE
#   CURRENT = 60 bars (~1 day)  but cycle is different intraday
#   → Use 156 bars (~2 days) as 5min CURRENT
#   WAVE = adaptive cycle, but cap at 5min-appropriate range
WINDOW_PRESETS = {
    "1d": {"tide": 240, "current": 60, "wave": None, "min_bars": 300},
    "5min": {"tide": 780, "current": 156, "wave": None, "min_bars": 850},
}


def compute_all_snapshots(timeframe: str = "1d"):
    """Compute ChannelSnapshot at every valid bar for all tickers.

    Args:
        timeframe: Vault timeframe to load. "1d" or "5min".
                   Windows are automatically scaled per timeframe.
    """
    if timeframe not in WINDOW_PRESETS:
        raise ValueError(f"Unsupported timeframe: {timeframe}. Use: {list(WINDOW_PRESETS.keys())}")

    preset = WINDOW_PRESETS[timeframe]
    tide_w = preset["tide"]
    current_w = preset["current"]
    wave_w = preset["wave"]  # None = auto-detect cycle
    min_bars = preset["min_bars"]

    print(f"\n  Timeframe: {timeframe}")
    print(f"  Windows: TIDE={tide_w}, CURRENT={current_w}, WAVE={'auto' if wave_w is None else wave_w}")
    print(f"  Min bars required: {min_bars}")

    store = TimescaleDataStore()
    all_data = {}

    for ticker in TICKERS:
        ohlc = store.load_bars(ticker, timeframe)
        if ohlc is None or len(ohlc) < min_bars:
            print(f"    {ticker}: SKIP ({len(ohlc) if ohlc is not None else 0} bars < {min_bars} min)")
            continue

        # Validate: ensure loaded data matches expected timeframe frequency
        if len(ohlc) > 2:
            median_gap = ohlc.index.to_series().diff().dropna().median()
            if timeframe == "1d" and median_gap < pd.Timedelta("6h"):
                print(f"    ⚠️ {ticker}: Data looks like intraday (median gap={median_gap}), expected daily. SKIP.")
                continue
            if timeframe == "5min" and median_gap > pd.Timedelta("1h"):
                print(f"    ⚠️ {ticker}: Data looks like daily (median gap={median_gap}), expected 5min. SKIP.")
                continue

        close = ohlc["close"].values.astype(float)
        high = ohlc["high"].values.astype(float)
        low = ohlc["low"].values.astype(float)
        volume = ohlc["volume"].values.astype(float)
        dates = ohlc.index

        start_idx = tide_w + 10  # Need enough bars for tide regression + buffer
        records = []
        for idx in range(start_idx, len(ohlc)):
            snap = compute_channel_snapshot(
                close, high, low, volume, idx,
                tide_window=tide_w,
                current_window=current_w,
                wave_window=wave_w,
            )
            if snap is None:
                continue

            # Forward returns (if we have enough future data)
            ret_5d = ret_10d = ret_20d = np.nan
            if idx + 5 < len(close):
                ret_5d = (close[idx + 5] / close[idx] - 1) * 100
            if idx + 10 < len(close):
                ret_10d = (close[idx + 10] / close[idx] - 1) * 100
            if idx + 20 < len(close):
                ret_20d = (close[idx + 20] / close[idx] - 1) * 100

            is_win_10d = 1 if ret_10d is not None and ret_10d > 0 else 0

            rec = {
                "ticker": ticker, "date": dates[idx], "idx": idx,
                "price": close[idx],
                "ret_5d": ret_5d, "ret_10d": ret_10d, "ret_20d": ret_20d,
                "is_win_10d": is_win_10d,
                "timeframe": timeframe,
            }
            # Add all snapshot fields
            d = snap.to_dict()
            for k, v in d.items():
                if isinstance(v, str):
                    rec[k] = v
                elif isinstance(v, (bool, np.bool_)):
                    rec[k] = int(v)
                elif isinstance(v, (int, float, np.integer, np.floating)):
                    rec[k] = float(v)

            records.append(rec)

        df = pd.DataFrame(records)
        all_data[ticker] = df
        print(f"    {ticker}: {len(records)} snapshots ({timeframe}), {len(ohlc)} total bars")

    store.close()
    combined = pd.concat(all_data.values(), ignore_index=True)
    print(f"\n  Total: {len(combined)} bar-snapshots across {len(all_data)} tickers ({timeframe})")
    return combined


# ═══════════════════════════════════════════════════════════
# PART 1: PER-WINDOW SENTIMENT — 3 Fear Readings
# ═══════════════════════════════════════════════════════════

def classify_per_window_sentiment(slope):
    """Classify sentiment from a single slope value."""
    if slope > 0.05: return "STRONG_BULL"
    if slope > 0.02: return "BULL"
    if slope > 0.005: return "LEAN_BULL"
    if slope > -0.005: return "NEUTRAL"
    if slope > -0.02: return "LEAN_BEAR"
    if slope > -0.05: return "BEAR"
    return "STRONG_BEAR"


def part1_triple_sentiment(df):
    p("PART 1: TRIPLE SENTIMENT — 3 Fear Readings, 1 Story")

    # Classify each window's sentiment
    df["sent_tide"] = df["tide_slope"].apply(classify_per_window_sentiment)
    df["sent_current"] = df["current_slope"].apply(classify_per_window_sentiment)
    df["sent_wave"] = df["wave_slope"].apply(classify_per_window_sentiment)

    # Create narrative combos
    df["narrative"] = df["sent_tide"] + " / " + df["sent_current"] + " / " + df["sent_wave"]

    sp("Sentiment Distribution by Window")
    for window, col in [("TIDE(240)", "sent_tide"), ("CURRENT(60)", "sent_current"), ("WAVE(cycle)", "sent_wave")]:
        print(f"\n    {window}:")
        vc = df[col].value_counts()
        for label, count in vc.items():
            pct = count / len(df) * 100
            sub = df[df[col] == label]
            wr = sub["is_win_10d"].mean() * 100
            avg_ret = sub["ret_10d"].dropna().mean()
            print(f"      {label:<14s}: {pct:>5.1f}% (N={count:>5d}) | WR_10d={wr:>5.1f}% | Avg_Ret_10d={avg_ret:>+5.2f}%")

    sp("Top 10 Narrative Combos (Tide / Current / Wave) → WR")
    narrative_counts = df["narrative"].value_counts()
    top_narratives = narrative_counts[narrative_counts >= 50].index[:20]

    results = []
    for narr in top_narratives:
        sub = df[df["narrative"] == narr]
        wr = sub["is_win_10d"].mean() * 100
        avg_ret = sub["ret_10d"].dropna().mean()
        n = len(sub)
        results.append((narr, wr, avg_ret, n))

    results.sort(key=lambda x: -x[1])
    print(f"\n    {'Narrative (Tide / Current / Wave)':<55s} │ {'WR':>6s} │ {'Ret10d':>7s} │ {'N':>5s}")
    print(f"    {'─'*85}")
    for narr, wr, ret, n in results[:10]:
        print(f"    {narr:<55s} │ {wr:>5.1f}% │ {ret:>+6.2f}% │ {n:>5d}")

    print(f"\n    WORST 5 narratives:")
    for narr, wr, ret, n in results[-5:]:
        print(f"    {narr:<55s} │ {wr:>5.1f}% │ {ret:>+6.2f}% │ {n:>5d}")

    # Key patterns
    sp("Key Patterns — What happens when wave DISAGREES with tide?")

    # Wave bearish, tide bullish = PULLBACK
    pullback = df[(df["sent_tide"].isin(["BULL", "STRONG_BULL", "LEAN_BULL"])) &
                  (df["sent_wave"].isin(["BEAR", "STRONG_BEAR", "LEAN_BEAR"]))]
    if len(pullback) > 50:
        wr = pullback["is_win_10d"].mean() * 100
        ret = pullback["ret_10d"].dropna().mean()
        print(f"    PULLBACK (Tide↑ Wave↓): WR={wr:.1f}%, Ret10d={ret:+.2f}%, N={len(pullback)}")

    # Wave bullish, tide bearish = BEAR RALLY
    bear_rally = df[(df["sent_tide"].isin(["BEAR", "STRONG_BEAR", "LEAN_BEAR"])) &
                    (df["sent_wave"].isin(["BULL", "STRONG_BULL", "LEAN_BULL"]))]
    if len(bear_rally) > 50:
        wr = bear_rally["is_win_10d"].mean() * 100
        ret = bear_rally["ret_10d"].dropna().mean()
        print(f"    BEAR RALLY (Tide↓ Wave↑): WR={wr:.1f}%, Ret10d={ret:+.2f}%, N={len(bear_rally)}")

    # All aligned BULL
    all_bull = df[(df["sent_tide"].isin(["BULL", "STRONG_BULL"])) &
                  (df["sent_current"].isin(["BULL", "STRONG_BULL"])) &
                  (df["sent_wave"].isin(["BULL", "STRONG_BULL"]))]
    if len(all_bull) > 50:
        wr = all_bull["is_win_10d"].mean() * 100
        ret = all_bull["ret_10d"].dropna().mean()
        print(f"    ALL ALIGNED BULL (3↑): WR={wr:.1f}%, Ret10d={ret:+.2f}%, N={len(all_bull)}")

    # All aligned BEAR
    all_bear = df[(df["sent_tide"].isin(["BEAR", "STRONG_BEAR"])) &
                  (df["sent_current"].isin(["BEAR", "STRONG_BEAR"])) &
                  (df["sent_wave"].isin(["BEAR", "STRONG_BEAR"]))]
    if len(all_bear) > 50:
        wr = all_bear["is_win_10d"].mean() * 100
        ret = all_bear["ret_10d"].dropna().mean()
        print(f"    ALL ALIGNED BEAR (3↓): WR={wr:.1f}%, Ret10d={ret:+.2f}%, N={len(all_bear)}")


# ═══════════════════════════════════════════════════════════
# PART 2: WAVE FLIP EVENT STUDY
# ═══════════════════════════════════════════════════════════

def part2_wave_flip_events(df):
    p("PART 2: WAVE FLIP EVENT STUDY — When wave_slope changes sign rapidly")

    flips = df[df["wave_flip"] == 1].copy()
    print(f"  Total wave flips: {len(flips)} out of {len(df)} bars ({len(flips)/len(df)*100:.1f}%)")

    # Flip UP vs Flip DOWN
    flip_up = flips[flips["wave_flip_direction"] == 1]  # knife stopped falling
    flip_down = flips[flips["wave_flip_direction"] == -1]  # knife started falling

    sp("Flip Direction Analysis")
    for label, sub in [("FLIP UP (knife stopped)", flip_up), ("FLIP DOWN (knife started)", flip_down)]:
        if len(sub) < 20:
            continue
        wr = sub["is_win_10d"].mean() * 100
        ret5 = sub["ret_5d"].dropna().mean()
        ret10 = sub["ret_10d"].dropna().mean()
        ret20 = sub["ret_20d"].dropna().mean()
        print(f"\n    {label}: N={len(sub)}")
        print(f"      WR_10d={wr:.1f}%")
        print(f"      Ret_5d={ret5:+.2f}%, Ret_10d={ret10:+.2f}%, Ret_20d={ret20:+.2f}%")

    # Flip UP + tide direction
    sp("Flip UP conditioned on Tide direction")
    for tide_sent in ["STRONG_BULL", "BULL", "LEAN_BULL", "NEUTRAL", "LEAN_BEAR", "BEAR", "STRONG_BEAR"]:
        sub = flip_up[flip_up["sent_tide"] == tide_sent]
        if len(sub) < 15:
            continue
        wr = sub["is_win_10d"].mean() * 100
        ret = sub["ret_10d"].dropna().mean()
        print(f"    Flip UP + Tide={tide_sent:<14s}: WR={wr:>5.1f}%, Ret10d={ret:>+5.2f}%, N={len(sub)}")

    # Flip UP + sigma_tide condition
    sp("Flip UP conditioned on sigma_tide position")
    for label, lo, hi in [("Deep Value (σ<-1.5)", -999, -1.5), ("Support (σ -1.5 to -0.5)", -1.5, -0.5),
                           ("Fair Value (σ ±0.5)", -0.5, 0.5), ("Overextended (σ>+1.0)", 1.0, 999)]:
        sub = flip_up[(flip_up["sigma_tide"] >= lo) & (flip_up["sigma_tide"] < hi)]
        if len(sub) < 15:
            continue
        wr = sub["is_win_10d"].mean() * 100
        ret = sub["ret_10d"].dropna().mean()
        print(f"    Flip UP + {label:<30s}: WR={wr:>5.1f}%, Ret10d={ret:>+5.2f}%, N={len(sub)}")

    # What happens AFTER a flip: forward returns time series
    sp("Post-Flip Trajectory (average forward return by day)")
    for label, sub in [("FLIP UP", flip_up), ("FLIP DOWN", flip_down)]:
        if len(sub) < 50:
            continue
        print(f"\n    {label} (N={len(sub)}):")
        for days in [1, 2, 3, 5, 10, 20]:
            col = f"ret_{days}d"
            if col in sub.columns:
                ret = sub[col].dropna().mean()
                print(f"      Day {days:>2d}: {ret:>+5.2f}%")


# ═══════════════════════════════════════════════════════════
# PART 3: TENSION ANALYSIS — Regression σ vs VWAP σ
# ═══════════════════════════════════════════════════════════

def part3_tension_analysis(df):
    p("PART 3: TENSION ANALYSIS — When Price and Volume Disagree")

    # Compute tensions
    df["tension_tide"] = df["sigma_tide"] - df["vwap_sigma_tide"]
    df["tension_current"] = df["sigma_current"] - df["vwap_sigma_current"]
    df["tension_wave"] = df["sigma_wave"] - df["vwap_sigma_wave"]

    sp("Tension Distribution")
    for label, col in [("TIDE", "tension_tide"), ("CURRENT", "tension_current"), ("WAVE", "tension_wave")]:
        vals = df[col].dropna()
        print(f"    {label:<10s}: mean={vals.mean():+.3f}, std={vals.std():.3f}, "
              f"[{vals.quantile(0.05):+.2f}, {vals.quantile(0.95):+.2f}]")

    # Triple agreement: all 3 tensions same sign
    sp("Triple Tension Agreement → WR")
    all_neg = df[(df["tension_tide"] < 0) & (df["tension_current"] < 0) & (df["tension_wave"] < 0)]
    all_pos = df[(df["tension_tide"] > 0) & (df["tension_current"] > 0) & (df["tension_wave"] > 0)]
    mixed = df[~df.index.isin(all_neg.index) & ~df.index.isin(all_pos.index)]

    for label, sub in [("ALL NEGATIVE (institutional support 3/3)", all_neg),
                       ("ALL POSITIVE (price above institutions 3/3)", all_pos),
                       ("MIXED", mixed)]:
        if len(sub) < 50:
            continue
        wr = sub["is_win_10d"].mean() * 100
        ret = sub["ret_10d"].dropna().mean()
        pct = len(sub) / len(df) * 100
        print(f"    {label:<50s}: WR={wr:>5.1f}%, Ret10d={ret:>+5.2f}%, N={len(sub)} ({pct:.1f}%)")

    # Mean reversion speed: when vwap_sigma < -1.5, how many bars to VWAP?
    sp("Mean Reversion Speed — When vwap_sigma_wave < -1.5, bars to cross VWAP")
    deep_below = df[df["vwap_sigma_wave"] < -1.5].copy()
    if len(deep_below) > 20:
        print(f"    Events: N={len(deep_below)}")
        wr5 = deep_below["ret_5d"].dropna().apply(lambda x: x > 0).mean() * 100
        wr10 = deep_below["ret_10d"].dropna().apply(lambda x: x > 0).mean() * 100
        wr20 = deep_below["ret_20d"].dropna().apply(lambda x: x > 0).mean() * 100
        ret5 = deep_below["ret_5d"].dropna().mean()
        ret10 = deep_below["ret_10d"].dropna().mean()
        ret20 = deep_below["ret_20d"].dropna().mean()
        print(f"    P(positive in 5d):  {wr5:>5.1f}%, avg={ret5:>+5.2f}%")
        print(f"    P(positive in 10d): {wr10:>5.1f}%, avg={ret10:>+5.2f}%")
        print(f"    P(positive in 20d): {wr20:>5.1f}%, avg={ret20:>+5.2f}%")

    # Same for vwap_sigma_tide < -1.5
    sp("Mean Reversion Speed — When vwap_sigma_tide < -1.5")
    deep_below_t = df[df["vwap_sigma_tide"] < -1.5].copy()
    if len(deep_below_t) > 20:
        print(f"    Events: N={len(deep_below_t)}")
        for days, col in [(5, "ret_5d"), (10, "ret_10d"), (20, "ret_20d")]:
            vals = deep_below_t[col].dropna()
            wr = (vals > 0).mean() * 100
            print(f"    P(positive in {days}d): {wr:>5.1f}%, avg={vals.mean():>+5.2f}%")

    # Tension EXTREME events
    sp("Extreme Tensions — Strongest institutional support/resistance")
    for label, mask, desc in [
        ("STRONG SUPPORT", (df["tension_tide"] < -1) & (df["tension_wave"] < -0.5),
         "Price far below regression, near VWAP → institutions hold"),
        ("STRONG RESISTANCE", (df["tension_tide"] > 1) & (df["tension_wave"] > 0.5),
         "Price far above regression, far above VWAP → overextended"),
    ]:
        sub = df[mask]
        if len(sub) < 20:
            continue
        wr = sub["is_win_10d"].mean() * 100
        ret = sub["ret_10d"].dropna().mean()
        print(f"\n    {label}: {desc}")
        print(f"      WR_10d={wr:.1f}%, Ret10d={ret:+.2f}%, N={len(sub)}")


# ═══════════════════════════════════════════════════════════
# PART 4: TREND CHANGE — Slope Sign Changes
# ═══════════════════════════════════════════════════════════

def part4_trend_changes(df):
    p("PART 4: TREND CHANGE DETECTION — When slopes change sign")

    # Need to look at consecutive bars per ticker
    for label, slope_col, accel_col, window_name in [
        ("WAVE", "wave_slope", "wave_accel", "~30 bars"),
        ("CURRENT", "current_slope", "current_accel", "60 bars"),
        ("TIDE", "tide_slope", "tide_accel", "240 bars"),
    ]:
        sp(f"{label} ({window_name}) — Slope sign changes")

        # Detect sign changes using acceleration and sign
        # A rapid change = large |accel| + sign flip
        pos = df[slope_col] > 0
        neg = df[slope_col] <= 0

        # Approximate flip: acceleration magnitude tells us speed of change
        large_accel = df[accel_col].abs() > df[accel_col].abs().quantile(0.9)

        # Rapid bullish change = slope recently turned positive + high accel
        rapid_bull = df[(df[slope_col] > 0) & (df[accel_col] > 0) & large_accel]
        rapid_bear = df[(df[slope_col] < 0) & (df[accel_col] < 0) & large_accel]

        for rlabel, sub in [("RAPID BULL CHANGE", rapid_bull), ("RAPID BEAR CHANGE", rapid_bear)]:
            if len(sub) < 30:
                continue
            wr = sub["is_win_10d"].mean() * 100
            ret5 = sub["ret_5d"].dropna().mean()
            ret10 = sub["ret_10d"].dropna().mean()
            ret20 = sub["ret_20d"].dropna().mean()
            print(f"\n    {rlabel}: N={len(sub)}")
            print(f"      WR_10d={wr:.1f}%")
            print(f"      Ret: 5d={ret5:+.2f}%, 10d={ret10:+.2f}%, 20d={ret20:+.2f}%")

    # Cross-timeframe: wave flips but tide holds
    sp("Cross-Timeframe: Wave flips against Tide")

    # Wave turns bearish in bullish tide = PULLBACK ENTRY
    wave_bear_tide_bull = df[(df["wave_slope"] < -0.01) & (df["tide_slope"] > 0.01) &
                             (df["wave_accel"] < 0)]
    if len(wave_bear_tide_bull) > 50:
        wr = wave_bear_tide_bull["is_win_10d"].mean() * 100
        ret = wave_bear_tide_bull["ret_10d"].dropna().mean()
        print(f"    Wave↓ in Bull Tide = PULLBACK: WR={wr:.1f}%, Ret10d={ret:+.2f}%, N={len(wave_bear_tide_bull)}")

    # Current turns bearish while tide is still bullish = WARNING
    current_bear_tide_bull = df[(df["current_slope"] < -0.005) & (df["tide_slope"] > 0.01)]
    if len(current_bear_tide_bull) > 50:
        wr = current_bear_tide_bull["is_win_10d"].mean() * 100
        ret = current_bear_tide_bull["ret_10d"].dropna().mean()
        print(f"    Current↓ in Bull Tide = TRANSITION?: WR={wr:.1f}%, Ret10d={ret:+.2f}%, N={len(current_bear_tide_bull)}")

    # Wave recovers (flips up) after pullback in bull tide = ENTRY SIGNAL
    wave_recovery = df[(df["wave_flip"] == 1) & (df["wave_flip_direction"] == 1) &
                       (df["tide_slope"] > 0.01)]
    if len(wave_recovery) > 30:
        wr = wave_recovery["is_win_10d"].mean() * 100
        ret = wave_recovery["ret_10d"].dropna().mean()
        print(f"    Wave RECOVERY in Bull Tide: WR={wr:.1f}%, Ret10d={ret:+.2f}%, N={len(wave_recovery)}")

        # Conditioned on sigma_tide
        deep = wave_recovery[wave_recovery["sigma_tide"] < -1.0]
        if len(deep) > 10:
            wr_d = deep["is_win_10d"].mean() * 100
            ret_d = deep["ret_10d"].dropna().mean()
            print(f"      + sigma_tide < -1.0: WR={wr_d:.1f}%, Ret10d={ret_d:+.2f}%, N={len(deep)}")


# ═══════════════════════════════════════════════════════════
# PART 5: SIGMA CROSS EVENTS — Entry/Exit Signals
# ═══════════════════════════════════════════════════════════

def part5_sigma_cross_events(df):
    p("PART 5: SIGMA CROSS EVENTS — When price enters/exits zones")

    sp("σ_tide zone transitions → Forward Returns")
    # Bucket sigma_tide into zones
    def sigma_zone(s):
        if s < -2.0: return "DEEP_VALUE"
        if s < -1.0: return "VALUE"
        if s < -0.3: return "LEAN_VALUE"
        if s < 0.3: return "FAIR"
        if s < 1.0: return "LEAN_EXPENSIVE"
        if s < 2.0: return "EXPENSIVE"
        return "EXTREME"

    df["sigma_zone"] = df["sigma_tide"].apply(sigma_zone)

    zone_order = ["DEEP_VALUE", "VALUE", "LEAN_VALUE", "FAIR", "LEAN_EXPENSIVE", "EXPENSIVE", "EXTREME"]
    print(f"\n    {'Zone':<18s} │ {'WR_5d':>6s} │ {'WR_10d':>6s} │ {'WR_20d':>6s} │ {'Ret_10d':>7s} │ {'N':>6s}")
    print(f"    {'─'*70}")
    for zone in zone_order:
        sub = df[df["sigma_zone"] == zone]
        if len(sub) < 30:
            continue
        wr5 = (sub["ret_5d"].dropna() > 0).mean() * 100
        wr10 = sub["is_win_10d"].mean() * 100
        wr20 = (sub["ret_20d"].dropna() > 0).mean() * 100
        ret10 = sub["ret_10d"].dropna().mean()
        print(f"    {zone:<18s} │ {wr5:>5.1f}% │ {wr10:>5.1f}% │ {wr20:>5.1f}% │ {ret10:>+6.2f}% │ {len(sub):>6d}")

    # VWAP sigma zones
    sp("vwap_σ_wave zone transitions → Forward Returns")
    def vwap_zone(s):
        if s < -2.0: return "DEEP_BELOW"
        if s < -1.0: return "BELOW"
        if s < -0.3: return "LEAN_BELOW"
        if s < 0.3: return "AT_VWAP"
        if s < 1.0: return "LEAN_ABOVE"
        if s < 2.0: return "ABOVE"
        return "FAR_ABOVE"

    df["vwap_zone"] = df["vwap_sigma_wave"].apply(vwap_zone)

    vwap_order = ["DEEP_BELOW", "BELOW", "LEAN_BELOW", "AT_VWAP", "LEAN_ABOVE", "ABOVE", "FAR_ABOVE"]
    print(f"\n    {'Zone':<18s} │ {'WR_5d':>6s} │ {'WR_10d':>6s} │ {'WR_20d':>6s} │ {'Ret_10d':>7s} │ {'N':>6s}")
    print(f"    {'─'*70}")
    for zone in vwap_order:
        sub = df[df["vwap_zone"] == zone]
        if len(sub) < 30:
            continue
        wr5 = (sub["ret_5d"].dropna() > 0).mean() * 100
        wr10 = sub["is_win_10d"].mean() * 100
        wr20 = (sub["ret_20d"].dropna() > 0).mean() * 100
        ret10 = sub["ret_10d"].dropna().mean()
        print(f"    {zone:<18s} │ {wr5:>5.1f}% │ {wr10:>5.1f}% │ {wr20:>5.1f}% │ {ret10:>+6.2f}% │ {len(sub):>6d}")

    # Combined: sigma_tide zone + vwap_sigma_wave zone
    sp("COMBINED: σ_tide zone × vwap_σ_wave zone → WR_10d")
    sigma_groups = ["DEEP_VALUE", "VALUE", "LEAN_VALUE", "FAIR"]
    vwap_groups = ["DEEP_BELOW", "BELOW", "LEAN_BELOW", "AT_VWAP"]

    print(f"\n    {'σ_tide \\ vwap_wave':<18s}", end="")
    for v in vwap_groups:
        print(f" │ {v:>12s}", end="")
    print()
    print(f"    {'─'*72}")

    for s in sigma_groups:
        print(f"    {s:<18s}", end="")
        for v in vwap_groups:
            cell = df[(df["sigma_zone"] == s) & (df["vwap_zone"] == v)]
            if len(cell) >= 20:
                wr = cell["is_win_10d"].mean() * 100
                print(f" │ {wr:>5.1f}% N={len(cell):>4d}", end="")
            else:
                n = len(cell)
                print(f" │ {'---':>12s}", end="") if n < 5 else print(f" │ {cell['is_win_10d'].mean()*100:>5.1f}%  N={n:>3d}", end="")
        print()


# ═══════════════════════════════════════════════════════════
# PART 6: FEAR INDEX AUDIT — Current classification vs reality
# ═══════════════════════════════════════════════════════════

def part6_fear_audit(df):
    p("PART 6: FEAR INDEX AUDIT — Does the classification match reality?")

    sp("Current Fear Level Distribution vs Returns")
    fear_labels = ["GREED", "CONFIDENCE", "NEUTRAL", "ANXIETY", "FEAR", "PANIC"]
    print(f"\n    {'Label':<14s} │ {'Level':>5s} │ {'%':>5s} │ {'WR_10d':>6s} │ {'Ret_10d':>7s} │ {'Ret_20d':>7s} │ {'N':>6s}")
    print(f"    {'─'*70}")
    for label in fear_labels:
        sub = df[df["fear_label"] == label]
        if len(sub) < 30:
            continue
        pct = len(sub) / len(df) * 100
        wr = sub["is_win_10d"].mean() * 100
        ret10 = sub["ret_10d"].dropna().mean()
        ret20 = sub["ret_20d"].dropna().mean()
        lvl = int(sub["fear_level"].iloc[0])
        print(f"    {label:<14s} │ {lvl:>5d} │ {pct:>4.1f}% │ {wr:>5.1f}% │ {ret10:>+6.2f}% │ {ret20:>+6.2f}% │ {len(sub):>6d}")

    # Is PANIC really contrarian? Compare PANIC vs GREED
    sp("Contrarian Test: PANIC vs GREED")
    panic = df[df["fear_label"] == "PANIC"]
    greed = df[df["fear_label"] == "GREED"]
    if len(panic) > 30 and len(greed) > 30:
        p_wr = panic["is_win_10d"].mean() * 100
        g_wr = greed["is_win_10d"].mean() * 100
        p_ret = panic["ret_10d"].dropna().mean()
        g_ret = greed["ret_10d"].dropna().mean()
        spread = p_wr - g_wr
        print(f"    PANIC:  WR={p_wr:.1f}%, Ret10d={p_ret:+.2f}%")
        print(f"    GREED:  WR={g_wr:.1f}%, Ret10d={g_ret:+.2f}%")
        print(f"    Spread: {spread:+.1f}pp → {'CONTRARIAN WORKS ✅' if spread > 3 else 'WEAK ⚠️' if spread > 0 else 'INVERTED ✗'}")

    # Proposed: 3 separate fear readings
    sp("PROPOSED: 3-Level Fear (one per window)")
    # Use slopes directly to classify per-window fear
    for window, slope_col, accel_col in [
        ("TIDE(240)", "tide_slope", "tide_accel"),
        ("CURRENT(60)", "current_slope", "current_accel"),
        ("WAVE(cycle)", "wave_slope", "wave_accel"),
    ]:
        print(f"\n    {window}:")
        def window_fear(row):
            s = row[slope_col]
            a = row[accel_col]
            if s < -0.02 and a < 0: return "PANIC"
            if s < -0.01: return "FEAR"
            if s > 0.02 and a > 0: return "GREED"
            if s > 0.01: return "CONFIDENCE"
            return "NEUTRAL"

        df[f"fear_{window[:4].lower()}"] = df.apply(window_fear, axis=1)

        for flabel in ["PANIC", "FEAR", "NEUTRAL", "CONFIDENCE", "GREED"]:
            sub = df[df[f"fear_{window[:4].lower()}"] == flabel]
            if len(sub) < 30:
                continue
            wr = sub["is_win_10d"].mean() * 100
            ret = sub["ret_10d"].dropna().mean()
            pct = len(sub) / len(df) * 100
            print(f"      {flabel:<12s}: WR={wr:>5.1f}%, Ret10d={ret:>+5.2f}%, N={len(sub):>5d} ({pct:.1f}%)")


# ═══════════════════════════════════════════════════════════
# PART 7: SIGMA VELOCITY — Is sigma ITSELF trending?
# López de Prado: "The derivative of position is more
# predictive than position itself"
# ═══════════════════════════════════════════════════════════

def part7_sigma_velocity(df):
    p("PART 7: SIGMA VELOCITY — Momentum in sigma space (López de Prado)")

    # Compute sigma velocity per ticker (change over last N bars)
    # We need consecutive bars, so work per-ticker
    df_sorted = df.sort_values(["ticker", "idx"]).copy()

    for sigma_col, label in [
        ("sigma_tide", "σ_tide"),
        ("vwap_sigma_wave", "vwap_σ_wave"),
        ("vwap_sigma_current", "vwap_σ_current"),
    ]:
        vel_col = f"vel_{sigma_col}"
        accel_sigma_col = f"accel_{sigma_col}"
        df_sorted[vel_col] = df_sorted.groupby("ticker")[sigma_col].diff(5)
        df_sorted[accel_sigma_col] = df_sorted.groupby("ticker")[vel_col].diff(5)

    sp("Sigma Velocity → Forward Returns")
    print(f"\n    {'Sigma Velocity':<28s} │ {'r_pb':>8s} {'p-val':>8s} │ {'Q1 WR':>6s} │ {'Q5 WR':>6s} │ {'Spread':>6s}")
    print(f"    {'─'*80}")

    for sigma_col, label in [
        ("sigma_tide", "σ_tide velocity"),
        ("vwap_sigma_wave", "vwap_σ_wave velocity"),
        ("vwap_sigma_current", "vwap_σ_current velocity"),
    ]:
        vel_col = f"vel_{sigma_col}"
        vals = df_sorted[vel_col].dropna()
        y = df_sorted.loc[vals.index, "is_win_10d"]
        if len(vals) < 100:
            continue
        r, pv = stats.pointbiserialr(y, vals)

        try:
            qs = pd.qcut(df_sorted[vel_col], 5, labels=False, duplicates="drop")
            q1_wr = df_sorted[qs == 0]["is_win_10d"].mean() * 100
            q5_wr = df_sorted[qs == 4]["is_win_10d"].mean() * 100
            spread = q1_wr - q5_wr
        except:
            q1_wr = q5_wr = spread = 0

        sig = "***" if pv < 0.001 else "**" if pv < 0.01 else "*" if pv < 0.05 else ""
        print(f"    {label:<28s} │ {r:>+7.4f} {pv:>7.4f}{sig:>1s} │ {q1_wr:>5.1f}% │ {q5_wr:>5.1f}% │ {spread:>+5.1f}pp")

    # Sigma acceleration (2nd derivative)
    sp("Sigma Acceleration (2nd derivative) → Forward Returns")
    print(f"\n    {'Sigma Accel':<28s} │ {'r_pb':>8s} {'p-val':>8s} │ {'Grade':>12s}")
    print(f"    {'─'*60}")

    for sigma_col in ["sigma_tide", "vwap_sigma_wave", "vwap_sigma_current"]:
        accel_col = f"accel_{sigma_col}"
        vals = df_sorted[accel_col].dropna()
        y = df_sorted.loc[vals.index, "is_win_10d"]
        if len(vals) < 100:
            continue
        r, pv = stats.pointbiserialr(y, vals)
        grade = "★★ STRONG" if abs(r) > 0.1 and pv < 0.01 else "★ MODERATE" if abs(r) > 0.05 and pv < 0.05 else "~ WEAK" if pv < 0.10 else "✗ NONE"
        sig = "***" if pv < 0.001 else "**" if pv < 0.01 else "*" if pv < 0.05 else ""
        print(f"    {sigma_col + ' accel':<28s} │ {r:>+7.4f} {pv:>7.4f}{sig:>1s} │ {grade:>12s}")

    # Key pattern: sigma falling fast (velocity < -0.5) while tide bullish
    sp("Sigma Falling Fast in Bull Tide = Oversold Opportunity?")
    bull_tide = df_sorted[(df_sorted["tide_slope"] > 0.01)]
    for sigma_col, label in [("sigma_tide", "σ_tide"), ("vwap_sigma_wave", "vwap_σ_wave")]:
        vel_col = f"vel_{sigma_col}"
        fast_drop = bull_tide[bull_tide[vel_col] < -0.5]
        if len(fast_drop) > 20:
            wr = fast_drop["is_win_10d"].mean() * 100
            ret = fast_drop["ret_10d"].dropna().mean()
            print(f"    {label} dropping fast + BULL tide: WR={wr:.1f}%, Ret10d={ret:+.2f}%, N={len(fast_drop)}")

    # Copy velocities back to main df
    for col in df_sorted.columns:
        if col.startswith("vel_") or col.startswith("accel_"):
            df[col] = df_sorted[col].values


# ═══════════════════════════════════════════════════════════
# PART 8: CHANNEL COMPRESSION — Volatility Squeeze
# When residual_std shrinks = energy building = breakout imminent
# Mandelbrot: vol clusters. Compression precedes expansion.
# ═══════════════════════════════════════════════════════════

def part8_channel_compression(df):
    p("PART 8: CHANNEL COMPRESSION — Bollinger Squeeze in Regression Space")

    # Channel width ratio: wave_std / tide_std
    # Low ratio = wave channel compressed inside tide channel = squeeze
    df["compression_ratio"] = df["residual_std_wave"] / df["residual_std_tide"].clip(lower=0.01)

    sp("Compression Ratio Distribution & Forward Returns")
    try:
        df["compress_q"] = pd.qcut(df["compression_ratio"], 5, labels=False, duplicates="drop")
        print(f"\n    {'Quintile':<12s} │ {'Range':<20s} │ {'WR_10d':>6s} │ {'Ret_10d':>7s} │ {'Ret_20d':>7s} │ {'N':>5s}")
        print(f"    {'─'*70}")
        for q in sorted(df["compress_q"].dropna().unique()):
            sub = df[df["compress_q"] == q]
            rng = sub["compression_ratio"]
            wr = sub["is_win_10d"].mean() * 100
            ret10 = sub["ret_10d"].dropna().mean()
            ret20 = sub["ret_20d"].dropna().mean()
            print(f"    Q{int(q):<10d} │ [{rng.min():.3f}, {rng.max():.3f}]{'':>4s} │ {wr:>5.1f}% │ {ret10:>+6.2f}% │ {ret20:>+6.2f}% │ {len(sub):>5d}")
    except Exception as e:
        print(f"    Error: {e}")

    # Extreme compression (bottom 10%) + bull tide = breakout setup
    sp("Squeeze Setup: Compression < 10th pctile + Bull Tide")
    p10 = df["compression_ratio"].quantile(0.10)
    squeeze = df[(df["compression_ratio"] < p10) & (df["tide_slope"] > 0.01)]
    if len(squeeze) > 30:
        wr = squeeze["is_win_10d"].mean() * 100
        ret = squeeze["ret_10d"].dropna().mean()
        ret20 = squeeze["ret_20d"].dropna().mean()
        print(f"    Compression < {p10:.3f} + Bull: WR={wr:.1f}%, Ret10d={ret:+.2f}%, Ret20d={ret20:+.2f}%, N={len(squeeze)}")

    # Current_std / tide_std compression
    df["compress_current"] = df["residual_std_current"] / df["residual_std_tide"].clip(lower=0.01)
    r_comp, p_comp = stats.pointbiserialr(
        df["is_win_10d"].loc[df["compress_current"].notna().values],
        df["compress_current"].dropna()
    )
    print(f"\n    Current/Tide compression → WR: r={r_comp:+.4f}, p={p_comp:.4f}")


# ═══════════════════════════════════════════════════════════
# PART 9: INTERACTION EFFECTS — Non-linear Feature Combinations
# López de Prado: "Features interact. The product of two weak
# features can be stronger than either alone."
# ═══════════════════════════════════════════════════════════

def part9_interaction_effects(df):
    p("PART 9: INTERACTION EFFECTS — Non-linear Feature Combinations")

    # Define interaction candidates
    interactions = [
        ("sigma_tide", "vwap_sigma_wave", "Position × VWAP momentum"),
        ("sigma_tide", "tide_accel", "Position × acceleration"),
        ("sigma_tide", "vol_up_down_ratio", "Position × volume confirmation"),
        ("vwap_sigma_wave", "wave_accel", "VWAP position × wave accel"),
        ("spread_tide_current", "tide_accel", "Timeframe divergence × accel"),
        ("sigma_tide", "compression_ratio", "Position × squeeze"),
        ("vwap_sigma_current", "conj_wave_tide", "VWAP current × slope angle"),
        ("tension_tide", "tension_wave", "Macro tension × micro tension"),
    ]

    sp("Interaction Terms → Predictive Power")
    print(f"\n    {'Interaction':<45s} │ {'r_pb':>8s} {'p-val':>8s} │ {'vs A':>6s} │ {'vs B':>6s} │ {'Verdict':>12s}")
    print(f"    {'─'*95}")

    for feat_a, feat_b, desc in interactions:
        if feat_a not in df.columns or feat_b not in df.columns:
            continue

        valid = df[[feat_a, feat_b, "is_win_10d"]].dropna()
        if len(valid) < 100:
            continue

        # Create interaction term
        interaction = valid[feat_a] * valid[feat_b]
        y = valid["is_win_10d"]

        r_int, p_int = stats.pointbiserialr(y, interaction)
        r_a, _ = stats.pointbiserialr(y, valid[feat_a])
        r_b, _ = stats.pointbiserialr(y, valid[feat_b])

        best_parent = max(abs(r_a), abs(r_b))
        if abs(r_int) > best_parent * 1.2 and p_int < 0.01:
            verdict = "★★ SYNERGY"
        elif abs(r_int) > best_parent and p_int < 0.05:
            verdict = "★ BETTER"
        elif abs(r_int) > 0.03 and p_int < 0.10:
            verdict = "~ MARGINAL"
        else:
            verdict = "✗ NO GAIN"

        sig = "***" if p_int < 0.001 else "**" if p_int < 0.01 else "*" if p_int < 0.05 else ""
        print(f"    {desc:<45s} │ {r_int:>+7.4f} {p_int:>7.4f}{sig:>1s} │ {r_a:>+5.3f} │ {r_b:>+5.3f} │ {verdict:>12s}")

    # Conditional analysis: sigma_tide extreme + vwap_sigma_wave extreme
    sp("Conditional: Both sigmas at extremes = SUPER SIGNAL?")
    # Both deeply negative (strong buy)
    both_deep = df[(df["sigma_tide"] < -1.5) & (df["vwap_sigma_wave"] < -1.0)]
    baseline = df["is_win_10d"].mean() * 100
    if len(both_deep) > 20:
        wr = both_deep["is_win_10d"].mean() * 100
        ret = both_deep["ret_10d"].dropna().mean()
        print(f"    σ_tide<-1.5 AND vwap_σ_wave<-1.0: WR={wr:.1f}% (base={baseline:.1f}%), Ret10d={ret:+.2f}%, N={len(both_deep)}")

    # Only sigma_tide extreme (no VWAP confirmation)
    only_sigma = df[(df["sigma_tide"] < -1.5) & (df["vwap_sigma_wave"] >= -0.5)]
    if len(only_sigma) > 20:
        wr = only_sigma["is_win_10d"].mean() * 100
        ret = only_sigma["ret_10d"].dropna().mean()
        print(f"    σ_tide<-1.5 WITHOUT vwap confirm: WR={wr:.1f}% (base={baseline:.1f}%), Ret10d={ret:+.2f}%, N={len(only_sigma)}")

    # Only VWAP extreme (no regression confirmation)
    only_vwap = df[(df["vwap_sigma_wave"] < -1.5) & (df["sigma_tide"] >= -0.5)]
    if len(only_vwap) > 20:
        wr = only_vwap["is_win_10d"].mean() * 100
        ret = only_vwap["ret_10d"].dropna().mean()
        print(f"    vwap_σ_wave<-1.5 WITHOUT σ_tide:  WR={wr:.1f}% (base={baseline:.1f}%), Ret10d={ret:+.2f}%, N={len(only_vwap)}")


# ═══════════════════════════════════════════════════════════
# PART 10: INFORMATION COEFFICIENT STABILITY — López de Prado
# "A feature that works in 3 out of 4 periods is more valuable
# than one that works spectacularly in 1 period."
# Deflated Sharpe Ratio mindset: temporal consistency > magnitude
# ═══════════════════════════════════════════════════════════

def part10_ic_stability(df):
    p("PART 10: IC STABILITY — Feature consistency across time periods")

    periods = [
        (2006, 2010, "2006-10"),
        (2011, 2015, "2011-15"),
        (2016, 2019, "2016-19"),
        (2020, 2022, "2020-22"),
        (2023, 2026, "2023-26"),
    ]

    top_features = [
        "sigma_tide", "vwap_sigma_wave", "vwap_sigma_current",
        "tide_accel", "spread_tide_current", "spread_tide_wave",
        "conj_wave_tide", "fear_level", "vol_up_down_ratio",
        "compression_ratio",
    ]

    # Add velocities if computed
    for vel in ["vel_sigma_tide", "vel_vwap_sigma_wave"]:
        if vel in df.columns:
            top_features.append(vel)

    df["year"] = pd.to_datetime(df["date"]).dt.year

    sp("Per-Period Information Coefficient (point-biserial r)")
    print(f"\n    {'Feature':<28s}", end="")
    for _, _, label in periods:
        print(f" │ {label:>8s}", end="")
    print(f" │ {'Consist':>7s} │ {'Mean|r|':>7s}")
    print(f"    {'─'*100}")

    stability_scores = []
    for feat in top_features:
        if feat not in df.columns:
            continue
        print(f"    {feat:<28s}", end="")
        period_rs = []
        for y_lo, y_hi, _ in periods:
            psub = df[(df["year"] >= y_lo) & (df["year"] <= y_hi)]
            vals = psub[feat].dropna()
            y_f = psub.loc[vals.index, "is_win_10d"]
            if len(vals) < 50:
                print(f" │ {'N/A':>8s}", end="")
                continue
            r, pval = stats.pointbiserialr(y_f, vals)
            period_rs.append(r)
            m = "★" if abs(r) > 0.05 and pval < 0.05 else ""
            print(f" │ {r:>+6.3f}{m:>2s}", end="")

        if len(period_rs) >= 3:
            signs = [np.sign(r) for r in period_rs if abs(r) > 0.02]
            if len(signs) >= 3:
                consistency = max(signs.count(1), signs.count(-1)) / len(signs)
                s = "✅" if consistency >= 0.8 else "⚠️" if consistency >= 0.6 else "🚨"
            else:
                consistency = 0
                s = "~"
            mean_r = np.mean([abs(r) for r in period_rs])
            print(f" │ {s:>7s} │ {mean_r:>7.4f}")
            stability_scores.append((feat, consistency, mean_r))
        else:
            print(f" │ {'?':>7s} │ {'?':>7s}")

    # Per-ticker universality
    sp("Per-Ticker Universality — % of tickers where feature has edge")
    print(f"\n    {'Feature':<28s} │ {'Tickers with edge':>17s} │ {'Median |r|':>10s}")
    print(f"    {'─'*65}")

    for feat in top_features:
        if feat not in df.columns:
            continue
        ticker_rs = []
        positive = 0
        total = 0
        for ticker in df["ticker"].unique():
            sub = df[df["ticker"] == ticker]
            vals = sub[feat].dropna()
            y = sub.loc[vals.index, "is_win_10d"]
            if len(vals) < 30:
                continue
            total += 1
            r, pv = stats.pointbiserialr(y, vals)
            ticker_rs.append(abs(r))
            if abs(r) > 0.03 and pv < 0.20:
                positive += 1

        pct = positive / max(total, 1) * 100
        median_r = np.median(ticker_rs) if ticker_rs else 0
        tag = "✅ UNIVERSAL" if pct >= 70 else "⚠️ PARTIAL" if pct >= 50 else "🚨 FRAGILE"
        print(f"    {feat:<28s} │ {positive}/{total} ({pct:>4.0f}%) {tag:>3s} │ {median_r:>10.4f}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v15 — TRIPLE LINE DYNAMICS & PATTERN DISCOVERY")
    print("  Computing ChannelSnapshot at EVERY bar for 17 tickers...")
    print("  This will take a few minutes (computing ~70K+ snapshots)...")

    df = compute_all_snapshots()

    part1_triple_sentiment(df)
    part2_wave_flip_events(df)
    part3_tension_analysis(df)
    part4_trend_changes(df)
    part5_sigma_cross_events(df)
    part6_fear_audit(df)
    part7_sigma_velocity(df)
    part8_channel_compression(df)
    part9_interaction_effects(df)
    part10_ic_stability(df)

    p("v15 TRIPLE LINE DYNAMICS — 10-PANEL ANALYSIS COMPLETE")
    print("  Expert committee: review patterns for backtest design")
