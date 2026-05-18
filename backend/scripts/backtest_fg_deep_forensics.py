"""
F&G Deep Forensics — Purified Second Pass (López de Prado Methodology)
======================================================================
Explores anomalies and hidden patterns from first backtest results,
correcting for statistical deliriums:
  1. Overlapping Returns: Adjusted effective N for t-statistics.
  2. Mean Reversion: Measured only from the onset of a regime.
  3. Base Rate Fallacy: Divergences compared against conditional base rates.
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

def calc_adjusted_tstat(vals: pd.Series, horizon: int) -> float:
    """
    T-statistic adjusted for overlapping returns (López de Prado).
    N_eff = N / horizon — each non-overlapping window is one independent obs.
    This is more conservative than N/(horizon/2) but statistically honest.
    """
    vals = vals.dropna()
    if len(vals) < 3:
        return 0.0
    n_eff = max(3.0, len(vals) / float(horizon))
    std = vals.std()
    if std > 0:
        return vals.mean() / (std / np.sqrt(n_eff))
    return 0.0


def calc_event_tstat(vals: pd.Series, min_gap_days: int = 20) -> tuple[float, int]:
    """
    T-stat for discrete events. Filters to non-overlapping events
    by requiring min_gap_days between observations.
    Returns (t_stat, n_independent_events).
    """
    vals = vals.dropna().sort_index()
    if len(vals) < 3:
        return 0.0, len(vals)
    # Filter to non-overlapping
    kept = [vals.index[0]]
    for idx in vals.index[1:]:
        if (idx - kept[-1]).days >= min_gap_days:
            kept.append(idx)
    independent = vals.loc[kept]
    n = len(independent)
    if n < 3:
        return 0.0, n
    std = independent.std()
    if std > 0:
        return independent.mean() / (std / np.sqrt(n)), n
    return 0.0, n

def main():
    start = date(2011, 1, 1)

    logger.info("═══ F&G Deep Forensics (Purified) — Loading ═══")
    fg_df = load_from_vault("FG", start)
    spy_df = load_from_vault("SPY", start)
    qqq_df = load_from_vault("QQQ", start)
    pcr_df = load_from_vault("CBOE_PCR", start)

    fg = fg_df["close"].rename("fg")
    spy = spy_df["close"].rename("spy")
    qqq = qqq_df["close"].rename("qqq") if qqq_df is not None else None
    pcr = pcr_df["close"].rename("pcr") if pcr_df is not None and not pcr_df.empty else None

    common = fg.index.intersection(spy.index)
    if qqq is not None:
        common = common.intersection(qqq.index)
    if pcr is not None:
        common = common.intersection(pcr.index)
    logger.info(f"  Common: {len(common)} dates\n")

    fg = fg.reindex(common)
    spy = spy.reindex(common)
    if qqq is not None:
        qqq = qqq.reindex(common)
    if pcr is not None:
        pcr = pcr.reindex(common)

    # Build master DataFrame
    df = pd.DataFrame({"fg": fg, "spy": spy})
    if qqq is not None:
        df["qqq"] = qqq
    if pcr is not None:
        df["pcr"] = pcr

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

    # ═══════════════════════════════════════════════════════════
    # 1. GRANULAR REGIME TABLE (Adjusted T-Stats)
    # ═══════════════════════════════════════════════════════════
    print("=" * 80)
    print("1. GRANULAR REGIME TABLE — SPY Ret20d by F&G 10-point bucket (Adjusted T-Stats)")
    print("=" * 80)
    for regime, group in df.groupby("regime", observed=True):
        vals = group["spy_ret20d"].dropna()
        if len(vals) < 5:
            continue
        wr = (vals > 0).mean() * 100
        t = calc_adjusted_tstat(vals, horizon=20)
        mdd = group["spy_mdd20d"].dropna().mean()
        mfe = group["spy_mfe20d"].dropna().mean()
        print(f"  F&G {str(regime):8s}: N={len(vals):4d}  Mean={vals.mean():+6.2f}%  "
              f"Median={vals.median():+6.2f}%  WR={wr:5.1f}%  t_adj={t:+5.2f}  "
              f"MDD={mdd:+5.2f}%  MFE={mfe:+5.2f}%")

    # ═══════════════════════════════════════════════════════════
    # 2. DURATION EFFECT
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
    # 3. THE GREED PARADOX
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("3. THE GREED PARADOX — Decomposition of F&G > 75 returns")
    print("=" * 80)
    greed_zone = df[df["fg"] > 75].copy()
    if len(greed_zone) > 0:
        greed_zone["spy_mom20"] = greed_zone["spy"].pct_change(20) * 100
        print(f"  N = {len(greed_zone)} days in greed zone")
        print(f"  SPY momentum (prior 20d): {greed_zone['spy_mom20'].mean():+.2f}%")
        print(f"  SPY Ret20d forward:       {greed_zone['spy_ret20d'].dropna().mean():+.2f}%")
        
        print("\n  GREED by SPY drawdown context:")
        for dd_label, lo, hi in [("At highs (DD>-2%)", -2, 0), ("Mild DD (-5 to -2%)", -5, -2),
                                  ("Correction (<-5%)", -99, -5)]:
            mask = (greed_zone["spy_dd_from_high"] >= lo) & (greed_zone["spy_dd_from_high"] < hi)
            sub = greed_zone.loc[mask, "spy_ret20d"].dropna()
            if len(sub) >= 3:
                wr = (sub > 0).mean() * 100
                print(f"    {dd_label:25s}: N={len(sub):4d}  Mean={sub.mean():+6.2f}%  WR={wr:.1f}%")

    # ═══════════════════════════════════════════════════════════
    # 4. REGIME TRANSITION SIGNALS (Events only)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("4. REGIME TRANSITIONS — Cross-threshold events (Non-overlapping)")
    print("=" * 80)

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
            # Use non-overlapping event t-stat (min 20d gap between events)
            t, n_indep = calc_event_tstat(vals, min_gap_days=20)
            print(f"  {label}")
            print(f"    N_raw={len(vals):4d}  N_indep={n_indep}  Mean={vals.mean():+6.2f}%  WR={wr:.1f}%  t_event={t:+.2f}")

    # ═══════════════════════════════════════════════════════════
    # 5. MEAN-REVERSION SPEED (Corrected to measure from onset)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("5. MEAN-REVERSION — How fast does F&G return to 50? (From Regime Onset)")
    print("=" * 80)
    
    # We only want the FIRST day of entering the zone to avoid downward bias
    enter_ext_fear = (df["fg"] < 15) & (df["fg"].shift(1) >= 15)
    enter_fear     = (df["fg"] >= 15) & (df["fg"] < 25) & (
        (df["fg"].shift(1) >= 25) | (df["fg"].shift(1) < 15)
    )
    enter_greed    = (df["fg"] >= 75) & (df["fg"] < 85) & (df["fg"].shift(1) < 75)
    enter_ext_greed= (df["fg"] >= 85) & (df["fg"].shift(1) < 85)

    for zone, mask in [("EXTREME_FEAR (<15)", enter_ext_fear), 
                       ("FEAR (15-25)", enter_fear),
                       ("GREED (75-85)", enter_greed), 
                       ("EXTREME_GREED (>85)", enter_ext_greed)]:
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
                  f"P75={np.percentile(arr,75):.0f}d  Events={len(arr)}")

    # ═══════════════════════════════════════════════════════════
    # 6. PULLBACK CONFIRMATION (Adjusted T-Stats)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("6. PULLBACK CONFIRMATION — When SPY is in drawdown AND F&G < thresholds")
    print("=" * 80)
    in_pullback = df["spy_dd_from_high"] < -3  # SPY > 3% off highs
    print(f"  {'Condition':40s} {'N':>5s} {'Ret20d':>8s} {'WR':>6s} {'t_adj':>6s}")
    print(f"  {'─' * 40} {'─'*5:>5s} {'─'*8:>8s} {'─'*6:>6s} {'─'*6:>6s}")

    conditions = [
        ("SPY in pullback (DD > -3%)", in_pullback),
        ("Pullback + F&G < 40", in_pullback & (df["fg"] < 40)),
        ("Pullback + F&G < 20", in_pullback & (df["fg"] < 20)),
        ("Pullback + F&G < 15", in_pullback & (df["fg"] < 15)),
        ("Pullback + F&G FALLING", in_pullback & (df["fg_roc5"] < -5)),
    ]

    for label, mask in conditions:
        vals = df.loc[mask, "spy_ret20d"].dropna()
        if len(vals) >= 3:
            wr = (vals > 0).mean() * 100
            t = calc_adjusted_tstat(vals, horizon=20)
            print(f"  {label:40s} {len(vals):5d} {vals.mean():+7.2f}% {wr:5.1f}% {t:+5.2f}")

    # ═══════════════════════════════════════════════════════════
    # 7. DIVERGENCES VS BASE RATE (The True Test of Edge)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("7. DIVERGENCES vs BASE RATE — Does disagreement add Alpha?")
    print("=" * 80)

    # 20d rolling changes (backward looking context)
    spy_ret20_past = df["spy"].pct_change(20) * 100
    fg_chg20_past = df["fg"].diff(20)

    # Base conditions
    base_spy_up = spy_ret20_past > 2
    base_spy_dn = spy_ret20_past < -2

    # Divergence types
    # BEARISH DIV: SPY rising but F&G falling (Smart money taking profit / retail buying top?)
    bear_div = base_spy_up & (fg_chg20_past < -5)
    # CONFIRMING BULL: SPY rising + F&G rising
    confirm_bull = base_spy_up & (fg_chg20_past > 5)

    # BULLISH DIV: SPY falling but F&G rising (Smart money buying / retail exhausted?)
    bull_div = base_spy_dn & (fg_chg20_past > 5)
    # CONFIRMING BEAR: SPY falling + F&G falling
    confirm_bear = base_spy_dn & (fg_chg20_past < -5)

    print(f"\n  [UPTREND CONTEXT (SPY rose >2% in past 20d)]")
    # Base rate calculation
    base_up_vals = df.loc[base_spy_up, "spy_ret20d"].dropna()
    bu_wr = (base_up_vals > 0).mean() * 100
    print(f"  Base Rate (SPY Up): N={len(base_up_vals):4d}  Fwd Ret20d={base_up_vals.mean():+5.2f}%  WR={bu_wr:5.1f}%")

    for label, mask in [
        ("CONFIRM BULL (F&G↑)", confirm_bull),
        ("BEARISH DIV  (F&G↓)", bear_div),
    ]:
        vals = df.loc[mask, "spy_ret20d"].dropna()
        if len(vals) >= 3:
            wr = (vals > 0).mean() * 100
            diff_mean = vals.mean() - base_up_vals.mean()
            # Welch's t-test against base rate (N_eff = N/horizon for overlap)
            n_eff_vals = max(3, len(vals) / 20.0)
            n_eff_base = max(3, len(base_up_vals) / 20.0)
            var_vals = vals.var() / n_eff_vals if len(vals) > 1 else 0
            var_base = base_up_vals.var() / n_eff_base if len(base_up_vals) > 1 else 0
            t_diff = diff_mean / np.sqrt(var_vals + var_base) if (var_vals + var_base) > 0 else 0
            
            print(f"    {label:20s}: N={len(vals):4d}  Ret={vals.mean():+5.2f}% (vs base {diff_mean:+.2f}%)  WR={wr:5.1f}%  t_adj={t_diff:+.2f}")


    print(f"\n  [DOWNTREND CONTEXT (SPY fell <-2% in past 20d)]")
    base_dn_vals = df.loc[base_spy_dn, "spy_ret20d"].dropna()
    bd_wr = (base_dn_vals > 0).mean() * 100
    print(f"  Base Rate (SPY Dn): N={len(base_dn_vals):4d}  Fwd Ret20d={base_dn_vals.mean():+5.2f}%  WR={bd_wr:5.1f}%")

    for label, mask in [
        ("CONFIRM BEAR (F&G↓)", confirm_bear),
        ("BULLISH DIV  (F&G↑)", bull_div),
    ]:
        vals = df.loc[mask, "spy_ret20d"].dropna()
        if len(vals) >= 3:
            wr = (vals > 0).mean() * 100
            diff_mean = vals.mean() - base_dn_vals.mean()
            n_eff_vals = max(3, len(vals) / 20.0)
            n_eff_base = max(3, len(base_dn_vals) / 20.0)
            var_vals = vals.var() / n_eff_vals if len(vals) > 1 else 0
            var_base = base_dn_vals.var() / n_eff_base if len(base_dn_vals) > 1 else 0
            t_diff = diff_mean / np.sqrt(var_vals + var_base) if (var_vals + var_base) > 0 else 0
            
            print(f"    {label:20s}: N={len(vals):4d}  Ret={vals.mean():+5.2f}% (vs base {diff_mean:+.2f}%)  WR={wr:5.1f}%  t_adj={t_diff:+.2f}")

    # ═══════════════════════════════════════════════════════════
    # 8. VELOCITY EXTREMES (Restored — adjusted t-stats)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("8. VELOCITY EXTREMES — 5d ROC distribution (adj t-stats)")
    print("=" * 80)
    for label, lo, hi in [("Crash (<-20pts/5d)", -999, -20), ("Sharp drop (-20 to -10)", -20, -10),
                           ("Normal drop (-10 to -3)", -10, -3), ("Stable (-3 to +3)", -3, 3),
                           ("Normal rise (+3 to +10)", 3, 10), ("Sharp rise (+10 to +20)", 10, 20),
                           ("Spike (>+20pts/5d)", 20, 999)]:
        mask = (df["fg_roc5"] >= lo) & (df["fg_roc5"] < hi)
        sub = df.loc[mask, "spy_ret20d"].dropna()
        if len(sub) >= 3:
            wr = (sub > 0).mean() * 100
            t = calc_adjusted_tstat(sub, horizon=20)
            print(f"  {label:25s}: N={len(sub):4d}  Mean={sub.mean():+6.2f}%  "
                  f"WR={wr:.1f}%  t_adj={t:+.2f}")

    # ═══════════════════════════════════════════════════════════
    # 9. MULTI-HORIZON DECAY (Restored — Welch + adjusted N)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("9. SIGNAL DECAY — Extreme fear (<20) at multiple horizons")
    print("=" * 80)
    fear_mask = df["fg"] < 20
    baseline_mask = (df["fg"] >= 40) & (df["fg"] <= 60)
    print(f"  {'Horizon':>10s} {'Fear Mean':>10s} {'Base Mean':>10s} {'Diff':>8s} {'t_adj':>8s}")
    for h in [5, 10, 20, 40, 60]:
        col = f"spy_ret{h}d"
        fear_vals = df.loc[fear_mask, col].dropna()
        base_vals = df.loc[baseline_mask, col].dropna()
        if len(fear_vals) < 5:
            continue
        diff = fear_vals.mean() - base_vals.mean()
        # Adjusted Welch: N_eff = N / horizon
        n_eff_f = max(3, len(fear_vals) / float(h))
        n_eff_b = max(3, len(base_vals) / float(h))
        var_f = fear_vals.var() / n_eff_f
        var_b = base_vals.var() / n_eff_b
        t = diff / np.sqrt(var_f + var_b) if (var_f + var_b) > 0 else 0
        print(f"  {h:8d}d  {fear_vals.mean():+8.2f}%  {base_vals.mean():+8.2f}%  "
              f"{diff:+6.2f}%  {t:+6.2f} {'✅' if abs(t) > 1.96 else '❌'}")

    # ═══════════════════════════════════════════════════════════
    # 10. QQQ/SPY BETA (Restored)
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
            s = spy_ret.reindex(common_idx).mean()
            q = qqq_ret.reindex(common_idx).mean()
            beta = q / s if abs(s) > 0.01 else 0
            print(f"  {label:12s}: SPY={s:+5.2f}%  QQQ={q:+5.2f}%  Beta={beta:.2f}x  N={len(common_idx)}")

    # ═══════════════════════════════════════════════════════════
    # 11. RISK/REWARD ASYMMETRY (Restored)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("11. RISK/REWARD ASYMMETRY — MFE vs MDD by F&G zone")
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
    # 12. FAILURE ANALYSIS — When F&G < 20 FAILS to bounce
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("12. FAILURE ANALYSIS — When capitulation buy FAILS (Ret20d < 0)")
    print("=" * 80)
    fear_entries = df[df["fg"] < 20].copy()
    losers = fear_entries[fear_entries["spy_ret20d"] < 0]
    winners = fear_entries[fear_entries["spy_ret20d"] > 0]
    if len(losers) > 0:
        print(f"  Total fear signals: {len(fear_entries.dropna(subset=['spy_ret20d']))}")
        print(f"  Winners: {len(winners.dropna(subset=['spy_ret20d']))}  |  Losers: {len(losers.dropna(subset=['spy_ret20d']))}")
        print(f"\n  LOSER PROFILE (what was different?):")
        # SPY drawdown at signal
        print(f"    SPY DD from high:  Losers={losers['spy_dd_from_high'].mean():+.1f}%  vs Winners={winners['spy_dd_from_high'].mean():+.1f}%")
        # F&G velocity
        print(f"    F&G velocity(5d):  Losers={losers['fg_roc5'].mean():+.1f}  vs Winners={winners['fg_roc5'].mean():+.1f}")
        # F&G level
        print(f"    F&G level:         Losers={losers['fg'].mean():.1f}  vs Winners={winners['fg'].mean():.1f}")
        # Consecutive days in fear
        print(f"    Consec fear days:  Losers={losers['consec_fear'].mean():.1f}  vs Winners={winners['consec_fear'].mean():.1f}")
        # MDD suffered
        print(f"    MDD20d suffered:   Losers={losers['spy_mdd20d'].dropna().mean():.2f}%  vs Winners={winners['spy_mdd20d'].dropna().mean():.2f}%")
        
        # Date-by-date losers
        print(f"\n  LOSER DATES (for Black Swan identification):")
        for _, row in losers.dropna(subset=["spy_ret20d"]).iterrows():
            print(f"    {row.name.date()}: F&G={row['fg']:.0f}  SPY_DD={row['spy_dd_from_high']:.1f}%  "
                  f"Ret20d={row['spy_ret20d']:+.2f}%  Consec={row['consec_fear']:.0f}d")
            if len(losers.dropna(subset=["spy_ret20d"])) > 20:
                break  # Limit output

    # ═══════════════════════════════════════════════════════════
    # 13. VIX CORRELATION — F&G vs VIX behavior
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("13. VIX CONTEXT — F&G extremes and VIX behavior")
    print("=" * 80)
    # Load VIX from macro_data if available
    try:
        from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
        store = TimescaleDataStore()
        vix_df = store.load_bars("VIX", "1d", start=start)
        store.close()
        if vix_df is not None and not vix_df.empty:
            vix = vix_df["close"].rename("vix")
            vix_common = df.index.intersection(vix.index)
            df_vix = df.reindex(vix_common).copy()
            df_vix["vix"] = vix.reindex(vix_common)
            
            # Correlation
            corr = df_vix["fg"].corr(df_vix["vix"])
            print(f"  F&G vs VIX correlation: {corr:+.3f} (expected: strongly negative)")
            
            # VIX at F&G extremes
            for label, lo, hi in [("F&G < 15", 0, 15), ("F&G 15-25", 15, 25),
                                   ("F&G 45-55", 45, 55), ("F&G > 75", 75, 101)]:
                mask = (df_vix["fg"] >= lo) & (df_vix["fg"] < hi)
                if mask.sum() > 3:
                    vix_vals = df_vix.loc[mask, "vix"]
                    print(f"    {label:12s}: VIX mean={vix_vals.mean():.1f}  "
                          f"median={vix_vals.median():.1f}  max={vix_vals.max():.1f}  N={mask.sum()}")
        else:
            print("  VIX data not available in Vault")
    except Exception as e:
        print(f"  VIX analysis skipped: {e}")

    # ═══════════════════════════════════════════════════════════
    # 14. PUT/CALL RATIO × F&G CONVERGENCE
    # ═══════════════════════════════════════════════════════════
    if "pcr" in df.columns:
        print("\n" + "=" * 80)
        print("14. PUT/CALL RATIO — Convergence with F&G")
        print("=" * 80)

        # PCR features
        pcr_mean60 = df["pcr"].rolling(60, min_periods=20).mean()
        pcr_std60 = df["pcr"].rolling(60, min_periods=20).std()
        df["pcr_zscore"] = (df["pcr"] - pcr_mean60) / pcr_std60.replace(0, np.nan)
        df["pcr_roc5"] = df["pcr"].diff(5)

        # Correlation matrix
        corr_fg_pcr = df["fg"].corr(df["pcr"])
        print(f"  F&G vs PCR correlation: {corr_fg_pcr:+.3f}")
        print(f"  PCR stats: mean={df['pcr'].mean():.3f} median={df['pcr'].median():.3f} std={df['pcr'].std():.3f}")

        # PCR by F&G regime
        print(f"\n  PCR levels at each F&G regime:")
        for label, lo, hi in [("F&G < 15", 0, 15), ("F&G 15-25", 15, 25),
                               ("F&G 25-45", 25, 45), ("F&G 45-55", 45, 55),
                               ("F&G 55-75", 55, 75), ("F&G > 75", 75, 101)]:
            mask = (df["fg"] >= lo) & (df["fg"] < hi)
            if mask.sum() > 3:
                pcr_vals = df.loc[mask, "pcr"]
                print(f"    {label:12s}: PCR mean={pcr_vals.mean():.3f}  "
                      f"median={pcr_vals.median():.3f}  N={mask.sum()}")

        # PCR extreme signals: does PCR > 1.2 predict bounces?
        print(f"\n  PCR extremes → SPY forward returns:")
        print(f"  {'PCR Zone':25s} {'N':>5s} {'Ret20d':>8s} {'WR':>6s} {'t_adj':>6s}")
        for label, lo, hi in [("PCR < 0.7 (bullish)", 0, 0.7),
                               ("PCR 0.7-0.9 (neutral)", 0.7, 0.9),
                               ("PCR 0.9-1.1 (mild fear)", 0.9, 1.1),
                               ("PCR 1.1-1.3 (fear)", 1.1, 1.3),
                               ("PCR > 1.3 (panic)", 1.3, 99)]:
            mask = (df["pcr"] >= lo) & (df["pcr"] < hi)
            vals = df.loc[mask, "spy_ret20d"].dropna()
            if len(vals) >= 5:
                wr = (vals > 0).mean() * 100
                t = calc_adjusted_tstat(vals, horizon=20)
                print(f"  {label:25s} {len(vals):5d} {vals.mean():+7.2f}% {wr:5.1f}% {t:+5.2f}")

        # F&G + PCR convergence: when BOTH signal fear
        print(f"\n  F&G + PCR CONVERGENCE signals:")
        print(f"  {'Signal':45s} {'N':>5s} {'Ret20d':>8s} {'WR':>6s} {'t_adj':>6s}")
        convergence_signals = [
            ("F&G < 20 + PCR > 1.0 (double fear)", (df["fg"] < 20) & (df["pcr"] > 1.0)),
            ("F&G < 20 + PCR > 1.2 (panic convergence)", (df["fg"] < 20) & (df["pcr"] > 1.2)),
            ("F&G < 20 + PCR < 0.8 (DIVERGENCE: fear+complacent)", (df["fg"] < 20) & (df["pcr"] < 0.8)),
            ("F&G > 75 + PCR < 0.7 (double greed)", (df["fg"] > 75) & (df["pcr"] < 0.7)),
            ("F&G > 75 + PCR > 1.0 (DIVERGENCE: greed+hedging)", (df["fg"] > 75) & (df["pcr"] > 1.0)),
        ]
        for label, mask in convergence_signals:
            vals = df.loc[mask, "spy_ret20d"].dropna()
            if len(vals) >= 3:
                wr = (vals > 0).mean() * 100
                t = calc_adjusted_tstat(vals, horizon=20)
                print(f"  {label:45s} {len(vals):5d} {vals.mean():+7.2f}% {wr:5.1f}% {t:+5.2f}")

        # ═══════════════════════════════════════════════════════════
        # 15. PCR AS BLACK SWAN EARLY WARNING
        # ═══════════════════════════════════════════════════════════
        print("\n" + "=" * 80)
        print("15. PCR BLACK SWAN WARNING — Does PCR spike BEFORE crashes?")
        print("=" * 80)

        # Lead/lag: PCR change vs SPY forward return
        pcr_chg = df["pcr"].diff()
        spy_fwd = df["spy"].pct_change(20).shift(-20) * 100
        print(f"  PCR daily change vs SPY 20d forward return:")
        for lag in [-10, -5, -3, -1, 0, 1, 3, 5, 10]:
            if lag < 0:
                corr = pcr_chg.corr(spy_fwd.shift(lag))
                desc = f"PCR leads SPY by {abs(lag)}d"
            elif lag == 0:
                corr = pcr_chg.corr(spy_fwd)
                desc = "Same day"
            else:
                corr = pcr_chg.corr(spy_fwd.shift(lag))
                desc = f"PCR lags SPY by {lag}d"
            marker = " ◄" if abs(corr) > 0.05 else ""
            print(f"    lag={lag:+3d}d  corr={corr:+.4f}  {desc}{marker}")

        # PCR spike (z > 2) as warning signal
        pcr_spike = df["pcr_zscore"] > 2.0
        pcr_crash = df["pcr_zscore"] < -2.0
        print(f"\n  PCR z-score spikes → SPY outcomes:")
        for label, mask in [("PCR z > +2 (panic hedging)", pcr_spike),
                            ("PCR z < -2 (extreme complacency)", pcr_crash)]:
            vals = df.loc[mask, "spy_ret20d"].dropna()
            if len(vals) >= 3:
                wr = (vals > 0).mean() * 100
                t = calc_adjusted_tstat(vals, horizon=20)
                print(f"    {label:35s}: N={len(vals):4d}  Ret20d={vals.mean():+5.2f}%  WR={wr:.1f}%  t={t:+.2f}")

    print("\n═══ Deep Forensics Complete ═══")


if __name__ == "__main__":
    main()
