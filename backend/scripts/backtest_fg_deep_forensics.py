"""
F&G Deep Forensics — Second Pass
====================================
Explores anomalies and hidden patterns from first backtest results.
Seeks new hypotheses beyond FG-H01 through FG-H05.

Focus areas:
  1. Duration effect: how long in regime matters?
  2. Regime transitions: cross-regime velocity signals
  3. The GREED paradox (WR 71.1% — why?)
  4. MDD/MFE asymmetry profile
  5. Put/Call + F&G convergence
  6. Mean-reversion speed by zone
  7. Consecutive extreme days
  8. SPY drawdown context at F&G extremes
"""
import logging
import numpy as np
import pandas as pd
from datetime import date, timedelta
from scipy import stats as scipy_stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def load_from_vault(ticker: str, start: date) -> pd.DataFrame | None:
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()
    df = store.load_bars(ticker, "1d", start=start)
    store.close()
    if df is not None and not df.empty:
        logger.info(f"  {ticker}: {len(df)} bars ({df.index[0].date()} → {df.index[-1].date()})")
    return df


def main():
    start = date(2011, 1, 1)

    logger.info("═══ F&G Deep Forensics — Loading ═══")
    fg_df = load_from_vault("FG", start)
    spy_df = load_from_vault("SPY", start)
    qqq_df = load_from_vault("QQQ", start)

    fg = fg_df["close"].rename("fg")
    spy = spy_df["close"].rename("spy")
    qqq = qqq_df["close"].rename("qqq") if qqq_df is not None else None

    common = fg.index.intersection(spy.index)
    if qqq is not None:
        common = common.intersection(qqq.index)
    logger.info(f"  Common: {len(common)} dates\n")

    fg = fg.reindex(common)
    spy = spy.reindex(common)
    if qqq is not None:
        qqq = qqq.reindex(common)

    # Build master DataFrame
    df = pd.DataFrame({"fg": fg, "spy": spy})
    if qqq is not None:
        df["qqq"] = qqq

    # Forward returns
    for h in [5, 10, 20, 40, 60]:
        df[f"spy_ret{h}d"] = df["spy"].pct_change(h).shift(-h) * 100
        if "qqq" in df.columns:
            df[f"qqq_ret{h}d"] = df["qqq"].pct_change(h).shift(-h) * 100

    # MDD and MFE (20d)
    df["spy_mdd20d"] = (df["spy"].rolling(20).min().shift(-20) / df["spy"] - 1) * 100
    df["spy_mfe20d"] = (df["spy"].rolling(20).max().shift(-20) / df["spy"] - 1) * 100

    # F&G features
    df["fg_roc5"] = df["fg"].diff(5)
    df["fg_roc1"] = df["fg"].diff(1)
    fg_mean60 = df["fg"].rolling(60, min_periods=20).mean()
    fg_std60 = df["fg"].rolling(60, min_periods=20).std()
    df["fg_zscore"] = (df["fg"] - fg_mean60) / fg_std60.replace(0, np.nan)

    # SPY drawdown from 52-week high
    spy_52w_high = df["spy"].rolling(252, min_periods=50).max()
    df["spy_dd_from_high"] = (df["spy"] / spy_52w_high - 1) * 100

    # Regime
    df["regime"] = pd.cut(
        df["fg"], bins=[-1, 10, 15, 20, 25, 35, 45, 55, 65, 75, 85, 101],
        labels=["0-10", "10-15", "15-20", "20-25", "25-35", "35-45",
                "45-55", "55-65", "65-75", "75-85", "85-100"],
    )

    # Consecutive days in regime
    is_extreme_fear = df["fg"] < 20
    is_extreme_greed = df["fg"] > 80
    df["consec_fear"] = is_extreme_fear.groupby((~is_extreme_fear).cumsum()).cumsum()
    df["consec_greed"] = is_extreme_greed.groupby((~is_extreme_greed).cumsum()).cumsum()

    # Days since last extreme
    fear_dates = df.index[is_extreme_fear]
    greed_dates = df.index[is_extreme_greed]

    # ═══════════════════════════════════════════════════════════
    # 1. GRANULAR REGIME TABLE (10-point buckets)
    # ═══════════════════════════════════════════════════════════
    print("=" * 80)
    print("1. GRANULAR REGIME TABLE — SPY Ret20d by F&G 10-point bucket")
    print("=" * 80)
    for regime, group in df.groupby("regime", observed=True):
        vals = group["spy_ret20d"].dropna()
        if len(vals) < 5:
            continue
        wr = (vals > 0).mean() * 100
        t = vals.mean() / (vals.std() / np.sqrt(len(vals))) if vals.std() > 0 else 0
        mdd = group["spy_mdd20d"].dropna().mean()
        mfe = group["spy_mfe20d"].dropna().mean()
        print(f"  F&G {str(regime):8s}: N={len(vals):4d}  Mean={vals.mean():+6.2f}%  "
              f"Median={vals.median():+6.2f}%  WR={wr:5.1f}%  t={t:+5.2f}  "
              f"MDD={mdd:+5.2f}%  MFE={mfe:+5.2f}%")

    # ═══════════════════════════════════════════════════════════
    # 2. DURATION EFFECT — Consecutive days in extreme fear
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("2. DURATION EFFECT — Days consecutive in extreme fear (<20)")
    print("=" * 80)
    fear_days = df[df["consec_fear"] > 0].copy()
    if len(fear_days) > 0:
        for bucket_label, lo, hi in [("Day 1-3", 1, 3), ("Day 4-10", 4, 10),
                                      ("Day 11-20", 11, 20), ("Day 21+", 21, 999)]:
            mask = (fear_days["consec_fear"] >= lo) & (fear_days["consec_fear"] <= hi)
            sub = fear_days.loc[mask, "spy_ret20d"].dropna()
            if len(sub) >= 3:
                wr = (sub > 0).mean() * 100
                print(f"  {bucket_label:12s}: N={len(sub):4d}  Mean={sub.mean():+6.2f}%  "
                      f"WR={wr:.1f}%  Median={sub.median():+6.2f}%")

    # ═══════════════════════════════════════════════════════════
    # 3. THE GREED PARADOX — Why GREED has positive returns
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("3. THE GREED PARADOX — Decomposition of F&G > 75 returns")
    print("=" * 80)
    greed_zone = df[df["fg"] > 75].copy()
    if len(greed_zone) > 0:
        # Is the positive return driven by momentum continuation?
        greed_zone["spy_mom20"] = greed_zone["spy"].pct_change(20) * 100
        print(f"  N = {len(greed_zone)} days in greed zone")
        print(f"  SPY momentum (prior 20d): {greed_zone['spy_mom20'].mean():+.2f}%")
        print(f"  SPY Ret20d forward:       {greed_zone['spy_ret20d'].dropna().mean():+.2f}%")
        print(f"  SPY MDD20d:               {greed_zone['spy_mdd20d'].dropna().mean():.2f}%")
        print(f"  SPY MFE20d:               {greed_zone['spy_mfe20d'].dropna().mean():+.2f}%")
        print(f"  → MFE/|MDD| ratio:        {greed_zone['spy_mfe20d'].dropna().mean() / abs(greed_zone['spy_mdd20d'].dropna().mean()):.2f}x")

        # Subgroup by SPY drawdown context
        print("\n  GREED by SPY drawdown context:")
        for dd_label, lo, hi in [("At highs (DD>-2%)", -2, 0), ("Mild DD (-5 to -2%)", -5, -2),
                                  ("Correction (<-5%)", -99, -5)]:
            mask = (greed_zone["spy_dd_from_high"] >= lo) & (greed_zone["spy_dd_from_high"] < hi)
            sub = greed_zone.loc[mask, "spy_ret20d"].dropna()
            if len(sub) >= 3:
                wr = (sub > 0).mean() * 100
                print(f"    {dd_label:25s}: N={len(sub):4d}  Mean={sub.mean():+6.2f}%  WR={wr:.1f}%")

    # ═══════════════════════════════════════════════════════════
    # 4. REGIME TRANSITION SIGNALS
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("4. REGIME TRANSITIONS — Cross-threshold signals")
    print("=" * 80)

    # Cross below 20 (entering extreme fear)
    cross_below_20 = (df["fg"] < 20) & (df["fg"].shift(1) >= 20)
    cross_above_20 = (df["fg"] >= 20) & (df["fg"].shift(1) < 20)
    cross_below_80 = (df["fg"] < 80) & (df["fg"].shift(1) >= 80)
    cross_above_80 = (df["fg"] >= 80) & (df["fg"].shift(1) < 80)

    for label, mask in [("Entering extreme fear (cross below 20)", cross_below_20),
                        ("Exiting extreme fear (cross above 20)", cross_above_20),
                        ("Entering extreme greed (cross above 80)", cross_above_80),
                        ("Exiting extreme greed (cross below 80)", cross_below_80)]:
        vals = df.loc[mask, "spy_ret20d"].dropna()
        if len(vals) >= 3:
            wr = (vals > 0).mean() * 100
            t = vals.mean() / (vals.std() / np.sqrt(len(vals))) if vals.std() > 0 else 0
            print(f"  {label}")
            print(f"    N={len(vals):4d}  Mean={vals.mean():+6.2f}%  WR={wr:.1f}%  t={t:+.2f}")

    # ═══════════════════════════════════════════════════════════
    # 5. F&G × SPY DRAWDOWN MATRIX
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("5. F&G × SPY DRAWDOWN MATRIX — Mean Ret20d")
    print("=" * 80)
    print(f"  {'F&G zone':15s} {'At highs':>12s} {'DD -5 to 0%':>12s} {'DD <-5%':>12s} {'DD <-10%':>12s}")
    for fg_label, fg_lo, fg_hi in [("F&G < 15", 0, 15), ("F&G 15-25", 15, 25),
                                    ("F&G 25-45", 25, 45), ("F&G 45-55", 45, 55),
                                    ("F&G 55-75", 55, 75), ("F&G > 75", 75, 101)]:
        fg_mask = (df["fg"] >= fg_lo) & (df["fg"] < fg_hi)
        cells = []
        for dd_lo, dd_hi in [(-2, 1), (-5, -2), (-99, -5), (-99, -10)]:
            dd_mask = (df["spy_dd_from_high"] >= dd_lo) & (df["spy_dd_from_high"] < dd_hi)
            combined = df.loc[fg_mask & dd_mask, "spy_ret20d"].dropna()
            if len(combined) >= 3:
                cells.append(f"{combined.mean():+5.2f}({len(combined):d})")
            else:
                cells.append(f"   --- ")
        print(f"  {fg_label:15s} {'  '.join(cells)}")

    # ═══════════════════════════════════════════════════════════
    # 6. MEAN-REVERSION SPEED
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("6. MEAN-REVERSION — How fast does F&G return to 50?")
    print("=" * 80)
    for zone, lo, hi in [("EXTREME_FEAR (<15)", 0, 15), ("FEAR (15-25)", 15, 25),
                          ("GREED (75-85)", 75, 85), ("EXTREME_GREED (>85)", 85, 101)]:
        mask = (df["fg"] >= lo) & (df["fg"] < hi)
        entry_idx = df.index[mask]
        if len(entry_idx) < 3:
            continue
        days_to_50 = []
        for idx in entry_idx:
            pos = df.index.get_loc(idx)
            future = df["fg"].iloc[pos:min(pos+120, len(df))]
            cross = future[(future >= 45) & (future <= 55)]
            if len(cross) > 0:
                days_to_50.append(df.index.get_loc(cross.index[0]) - pos)
        if days_to_50:
            arr = np.array(days_to_50)
            print(f"  {zone:25s}: Median={np.median(arr):.0f}d  "
                  f"Mean={arr.mean():.0f}d  P25={np.percentile(arr,25):.0f}d  "
                  f"P75={np.percentile(arr,75):.0f}d  N={len(arr)}")

    # ═══════════════════════════════════════════════════════════
    # 7. ASYMMETRIC RISK/REWARD PROFILE
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("7. RISK/REWARD ASYMMETRY — MFE vs MDD by F&G zone")
    print("=" * 80)
    for label, lo, hi in [("F&G < 15", 0, 15), ("F&G 15-25", 15, 25),
                           ("F&G 40-60", 40, 60), ("F&G 75-85", 75, 85),
                           ("F&G > 85", 85, 101)]:
        mask = (df["fg"] >= lo) & (df["fg"] < hi)
        sub = df.loc[mask]
        if len(sub) < 5:
            continue
        mfe = sub["spy_mfe20d"].dropna().mean()
        mdd = sub["spy_mdd20d"].dropna().mean()
        ratio = mfe / abs(mdd) if abs(mdd) > 0.01 else 0
        print(f"  {label:12s}: MFE={mfe:+5.2f}%  MDD={mdd:+5.2f}%  "
              f"R:R={ratio:.2f}x  N={len(sub)}")

    # ═══════════════════════════════════════════════════════════
    # 8. F&G VELOCITY EXTREMES — New hypothesis mining
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("8. F&G VELOCITY EXTREMES — 5d ROC distribution")
    print("=" * 80)
    for label, lo, hi in [("Crash (<-20pts/5d)", -999, -20), ("Sharp drop (-20 to -10)", -20, -10),
                           ("Normal drop (-10 to -3)", -10, -3), ("Stable (-3 to +3)", -3, 3),
                           ("Normal rise (+3 to +10)", 3, 10), ("Sharp rise (+10 to +20)", 10, 20),
                           ("Spike (>+20pts/5d)", 20, 999)]:
        mask = (df["fg_roc5"] >= lo) & (df["fg_roc5"] < hi)
        sub = df.loc[mask, "spy_ret20d"].dropna()
        if len(sub) >= 3:
            wr = (sub > 0).mean() * 100
            t = sub.mean() / (sub.std() / np.sqrt(len(sub))) if sub.std() > 0 else 0
            print(f"  {label:25s}: N={len(sub):4d}  Mean={sub.mean():+6.2f}%  "
                  f"WR={wr:.1f}%  t={t:+.2f}")

    # ═══════════════════════════════════════════════════════════
    # 9. MULTI-HORIZON DECAY — When does the signal fade?
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("9. SIGNAL DECAY — Extreme fear (<20) at multiple horizons (t-stats)")
    print("=" * 80)
    fear_mask = df["fg"] < 20
    baseline_mask = (df["fg"] >= 40) & (df["fg"] <= 60)
    print(f"  {'Horizon':>10s} {'Fear Mean':>10s} {'Base Mean':>10s} {'Diff':>8s} {'t-stat':>8s}")
    for h in [5, 10, 20, 40, 60]:
        col = f"spy_ret{h}d"
        fear_vals = df.loc[fear_mask, col].dropna()
        base_vals = df.loc[baseline_mask, col].dropna()
        if len(fear_vals) < 5:
            continue
        diff = fear_vals.mean() - base_vals.mean()
        # Welch's t-test
        t, p = scipy_stats.ttest_ind(fear_vals, base_vals, equal_var=False)
        print(f"  {h:8d}d  {fear_vals.mean():+8.2f}%  {base_vals.mean():+8.2f}%  "
              f"{diff:+6.2f}%  {t:+6.2f} {'✅' if abs(t) > 1.96 else '❌'}")

    # ═══════════════════════════════════════════════════════════
    # 10. QQQ vs SPY BETA — At every F&G regime
    # ═══════════════════════════════════════════════════════════
    if "qqq" in df.columns:
        print("\n" + "=" * 80)
        print("10. QQQ/SPY BETA — At each F&G regime (Ret20d)")
        print("=" * 80)
        for label, lo, hi in [("F&G < 15", 0, 15), ("F&G 15-25", 15, 25),
                               ("F&G 25-45", 25, 45), ("F&G 45-55", 45, 55),
                               ("F&G 55-75", 55, 75), ("F&G 75-85", 75, 85),
                               ("F&G > 85", 85, 101)]:
            mask = (df["fg"] >= lo) & (df["fg"] < hi)
            spy_ret = df.loc[mask, "spy_ret20d"].dropna()
            qqq_ret = df.loc[mask, "qqq_ret20d"].dropna()
            common_idx = spy_ret.index.intersection(qqq_ret.index)
            if len(common_idx) < 5:
                continue
            beta = qqq_ret.reindex(common_idx).mean() / spy_ret.reindex(common_idx).mean() if abs(spy_ret.reindex(common_idx).mean()) > 0.01 else 0
            print(f"  {label:12s}: SPY={spy_ret.reindex(common_idx).mean():+5.2f}%  "
                  f"QQQ={qqq_ret.reindex(common_idx).mean():+5.2f}%  "
                  f"Beta={beta:.2f}x  N={len(common_idx)}")
    # ═══════════════════════════════════════════════════════════
    # 11. LEAD/LAG ANALYSIS — Does F&G lead or lag SPY?
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("11. LEAD/LAG — Cross-correlation F&G changes vs SPY returns")
    print("=" * 80)
    fg_chg = df["fg"].diff()
    spy_ret = df["spy"].pct_change() * 100

    print(f"  {'Lag':>6s} {'Corr':>8s}  Interpretation")
    print(f"  {'---':>6s} {'---':>8s}  ---")
    best_lag = 0
    best_corr = 0
    for lag in range(-10, 11):
        if lag < 0:
            # F&G change today vs SPY return {lag} days ago
            corr = fg_chg.corr(spy_ret.shift(-lag))
            interp = f"F&G reacts to SPY {abs(lag)}d AGO" if abs(corr) > 0.1 else ""
        elif lag == 0:
            corr = fg_chg.corr(spy_ret)
            interp = "Same-day correlation"
        else:
            # F&G change today vs SPY return {lag} days LATER
            corr = fg_chg.corr(spy_ret.shift(-lag))
            interp = f"F&G PREDICTS SPY {lag}d LATER" if abs(corr) > 0.05 else ""
        if abs(corr) > abs(best_corr):
            best_corr = corr
            best_lag = lag
        marker = " ◄" if abs(corr) > 0.1 else ""
        print(f"  {lag:+5d}d  {corr:+7.4f}  {interp}{marker}")

    print(f"\n  PEAK: lag={best_lag:+d}d, corr={best_corr:+.4f}")
    if best_lag <= 0:
        print(f"  → F&G is a LAGGING indicator (reacts to SPY {abs(best_lag)}d later)")
    else:
        print(f"  → F&G is a LEADING indicator (predicts SPY {best_lag}d ahead)")

    # ═══════════════════════════════════════════════════════════
    # 12. PULLBACK DETECTION — F&G at SPY pullback events
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("12. PULLBACK TIMING — F&G behavior around SPY drawdowns")
    print("=" * 80)

    # Find pullback bottoms: SPY drops > 5% from local high then recovers
    spy_high20 = df["spy"].rolling(20, min_periods=5).max()
    spy_dd = (df["spy"] / spy_high20 - 1) * 100
    # Identify drawdown troughs (day with lowest local DD that crosses -5%)
    pullback_starts = (spy_dd < -5) & (spy_dd.shift(1) >= -5)
    pullback_events = df.index[pullback_starts]

    if len(pullback_events) > 0:
        print(f"  Found {len(pullback_events)} pullback events (SPY drops > 5%)")
        print()
        # For each pullback, check F&G level and when F&G signaled
        for evt in pullback_events[:15]:  # Show up to 15
            pos = df.index.get_loc(evt)
            fg_at = df["fg"].iloc[pos]
            spy_dd_at = spy_dd.iloc[pos]

            # Check F&G in days before pullback
            fg_5d_before = df["fg"].iloc[max(0,pos-5):pos].mean() if pos >= 5 else np.nan
            fg_10d_before = df["fg"].iloc[max(0,pos-10):pos].mean() if pos >= 10 else np.nan

            # When did F&G first drop below 30 relative to this event?
            search_start = max(0, pos - 20)
            search_window = df["fg"].iloc[search_start:pos+1]
            below_30 = search_window[search_window < 30]
            fg_lead = f"FG<30 at lag {df.index.get_loc(below_30.index[0]) - pos:+d}d" if len(below_30) > 0 else "FG never < 30"

            print(f"  {evt.date()}: SPY DD={spy_dd_at:.1f}%  F&G={fg_at:.0f}  "
                  f"(5d prior avg={fg_5d_before:.0f}, 10d prior avg={fg_10d_before:.0f})  "
                  f"{fg_lead}")

    # ═══════════════════════════════════════════════════════════
    # 13. F&G as PULLBACK CONFIRMATOR — Does F&G < 30 predict bounces?
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("13. PULLBACK CONFIRMATION — When SPY is in drawdown AND F&G < thresholds")
    print("=" * 80)
    in_pullback = df["spy_dd_from_high"] < -3  # SPY > 3% off highs
    print(f"  {'Condition':40s} {'N':>5s} {'Ret20d':>8s} {'WR':>6s} {'t':>6s}")
    print(f"  {'─' * 40} {'─'*5:>5s} {'─'*8:>8s} {'─'*6:>6s} {'─'*6:>6s}")

    conditions = [
        ("SPY in pullback (DD > -3%)", in_pullback),
        ("Pullback + F&G < 40", in_pullback & (df["fg"] < 40)),
        ("Pullback + F&G < 30", in_pullback & (df["fg"] < 30)),
        ("Pullback + F&G < 20", in_pullback & (df["fg"] < 20)),
        ("Pullback + F&G < 15", in_pullback & (df["fg"] < 15)),
        ("Pullback + F&G FALLING", in_pullback & (df["fg_roc5"] < -5)),
        ("Pullback + F&G STABILIZING", in_pullback & (df["fg"] < 30) & (df["fg_roc5"].abs() < 3)),
        ("NO pullback + F&G < 20", ~in_pullback & (df["fg"] < 20)),
    ]

    for label, mask in conditions:
        vals = df.loc[mask, "spy_ret20d"].dropna()
        if len(vals) >= 3:
            wr = (vals > 0).mean() * 100
            t = vals.mean() / (vals.std() / np.sqrt(len(vals))) if vals.std() > 0 else 0
            print(f"  {label:40s} {len(vals):5d} {vals.mean():+7.2f}% {wr:5.1f}% {t:+5.2f}")

    # ═══════════════════════════════════════════════════════════
    # 14. DIVERGENCE ANALYSIS — SPY vs F&G disagreement
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("14. DIVERGENCES — What happens when SPY and F&G disagree?")
    print("=" * 80)

    # 20d rolling changes
    spy_ret20 = df["spy"].pct_change(20) * 100
    fg_chg20 = df["fg"].diff(20)

    # Divergence types
    # BULLISH DIV: SPY falling but F&G rising (smart money accumulating?)
    bull_div = (spy_ret20 < -2) & (fg_chg20 > 5)
    # BEARISH DIV: SPY rising but F&G falling (distribution?)
    bear_div = (spy_ret20 > 2) & (fg_chg20 < -5)
    # CONFIRMING BULL: SPY rising + F&G rising
    confirm_bull = (spy_ret20 > 2) & (fg_chg20 > 5)
    # CONFIRMING BEAR: SPY falling + F&G falling
    confirm_bear = (spy_ret20 < -2) & (fg_chg20 < -5)

    print(f"\n  {'Divergence Type':40s} {'N':>5s} {'Ret20d fwd':>10s} {'WR':>6s} {'t':>6s}")
    print(f"  {'─' * 40} {'─'*5:>5s} {'─'*10:>10s} {'─'*6:>6s} {'─'*6:>6s}")

    for label, mask in [
        ("BULLISH DIV: SPY↓ but F&G↑", bull_div),
        ("BEARISH DIV: SPY↑ but F&G↓", bear_div),
        ("CONFIRM BULL: SPY↑ + F&G↑", confirm_bull),
        ("CONFIRM BEAR: SPY↓ + F&G↓", confirm_bear),
    ]:
        vals = df.loc[mask, "spy_ret20d"].dropna()
        if len(vals) >= 3:
            wr = (vals > 0).mean() * 100
            t = vals.mean() / (vals.std() / np.sqrt(len(vals))) if vals.std() > 0 else 0
            print(f"  {label:40s} {len(vals):5d} {vals.mean():+9.2f}% {wr:5.1f}% {t:+5.2f}")

    # Deeper: Divergence at different F&G levels
    print(f"\n  BULLISH DIVERGENCE breakdown by F&G level:")
    for fg_label, fg_lo, fg_hi in [("F&G < 25", 0, 25), ("F&G 25-40", 25, 40),
                                    ("F&G 40-60", 40, 60)]:
        mask = bull_div & (df["fg"] >= fg_lo) & (df["fg"] < fg_hi)
        vals = df.loc[mask, "spy_ret20d"].dropna()
        if len(vals) >= 3:
            wr = (vals > 0).mean() * 100
            print(f"    {fg_label:15s}: N={len(vals):4d}  Mean={vals.mean():+6.2f}%  WR={wr:.1f}%")

    print(f"\n  BEARISH DIVERGENCE breakdown by F&G level:")
    for fg_label, fg_lo, fg_hi in [("F&G 40-60", 40, 60), ("F&G 60-75", 60, 75),
                                    ("F&G > 75", 75, 101)]:
        mask = bear_div & (df["fg"] >= fg_lo) & (df["fg"] < fg_hi)
        vals = df.loc[mask, "spy_ret20d"].dropna()
        if len(vals) >= 3:
            wr = (vals > 0).mean() * 100
            print(f"    {fg_label:15s}: N={len(vals):4d}  Mean={vals.mean():+6.2f}%  WR={wr:.1f}%")

    # Multi-horizon divergence impact
    print(f"\n  DIVERGENCE multi-horizon:")
    for label, mask in [("BULLISH DIV", bull_div), ("BEARISH DIV", bear_div)]:
        line = f"    {label:15s}"
        for h in [5, 10, 20, 40, 60]:
            col = f"spy_ret{h}d"
            vals = df.loc[mask, col].dropna()
            if len(vals) >= 3:
                line += f"  Ret{h:02d}d={vals.mean():+5.2f}%"
        print(line)

    print("\n═══ Deep Forensics Complete ═══")


if __name__ == "__main__":
    main()
