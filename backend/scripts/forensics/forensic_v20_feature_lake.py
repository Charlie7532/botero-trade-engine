#!/usr/bin/env python3
"""
Forensic Lab v20 — Feature Lake Analytics (4 Expert Analyses)
================================================================
Now that we have 93,776 persisted snapshots, we can answer questions
that were IMPOSSIBLE before. No recomputation — pure SQL + analytics.

1. LÓPEZ DE PRADO: Feature Stability — does spread_tc predict across decades?
2. SIMONS: Entry Window Optimization — how long, where's the best price?
3. DRUCKENMILLER: Exit Trajectory — sigma_tide recovery curve per ticker
4. SEYKOTA: Approach Classification — crash vs grind → WR correlation

All reads from engine.channel_snapshots (Vault-first).
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

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def p(t): print(f"\n{'='*95}\n  {t}\n{'='*95}")
def sp(t): print(f"\n  ── {t} ──")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 1: Feature Stability (López de Prado)
# ═══════════════════════════════════════════════════════════

def feature_stability(store):
    p("1. LÓPEZ DE PRADO — Feature Stability Across Decades")
    print("  Does spread_tide_current predict equally well in 2008 vs 2024?")

    # Load all snapshots where ALL_EXTREME triggers
    query = """
        SELECT cs.ticker, cs.timestamp, cs.sigma_tide, cs.sigma_current,
               cs.spread_tide_current, cs.current_slope, cs.tide_accel,
               cs.vol_up_down_ratio, cs.vwap_sigma_current, cs.conj_current_tide,
               cs.regime, cs.fear_level,
               ob.close as price,
               LEAD(ob.close, 20) OVER (PARTITION BY cs.ticker ORDER BY cs.timestamp) as price_20d
        FROM engine.channel_snapshots cs
        JOIN market.ohlcv_bars ob 
            ON ob.ticker = cs.ticker AND ob.timeframe = '1d' AND ob.time = cs.timestamp
        WHERE cs.sigma_tide < -2.0 
          AND cs.vwap_sigma_wave < -1.5 
          AND cs.below_all_vwaps = true
        ORDER BY cs.timestamp
    """
    df = pd.read_sql(query, store.engine)
    if df.empty:
        print("  No ALL_EXTREME entries found!")
        return

    df['return_20d'] = (df['price_20d'] / df['price'] - 1) * 100
    df['win'] = (df['return_20d'] > 0).astype(int)
    df = df.dropna(subset=['return_20d'])

    # Split by era
    df['year'] = pd.to_datetime(df['timestamp']).dt.year
    eras = {
        '2006-2010 (GFC)': df[(df['year'] >= 2006) & (df['year'] <= 2010)],
        '2011-2015 (Recovery)': df[(df['year'] >= 2011) & (df['year'] <= 2015)],
        '2016-2019 (Bull)': df[(df['year'] >= 2016) & (df['year'] <= 2019)],
        '2020-2022 (Covid+Bear)': df[(df['year'] >= 2020) & (df['year'] <= 2022)],
        '2023-2026 (Recent)': df[(df['year'] >= 2023)],
    }

    features_to_test = [
        'spread_tide_current', 'sigma_current', 'current_slope',
        'tide_accel', 'vol_up_down_ratio', 'vwap_sigma_current',
        'conj_current_tide',
    ]

    sp("FEATURE PREDICTIVE POWER BY ERA")
    print(f"\n    {'Feature':<25s} │ {'2006-10':>7s} │ {'2011-15':>7s} │ {'2016-19':>7s} │ {'2020-22':>7s} │ {'2023-26':>7s} │ {'Stable?':>7s}")
    print(f"    {'─'*85}")

    for feat in features_to_test:
        correlations = []
        era_strs = []
        for era_name, era_df in eras.items():
            if len(era_df) < 10:
                era_strs.append("   ---")
                continue
            try:
                r, pv = stats.pearsonr(era_df[feat], era_df['win'])
                correlations.append(r)
                marker = "★" if pv < 0.05 else " "
                era_strs.append(f"{r:>+5.3f}{marker}")
            except:
                era_strs.append("   ---")

        # Stability = low std of correlations across eras
        if len(correlations) >= 3:
            r_std = np.std(correlations)
            # Check sign consistency
            signs = [1 if r > 0 else -1 for r in correlations]
            sign_consistent = len(set(signs)) == 1
            stable = "✅ YES" if r_std < 0.15 and sign_consistent else "❌ NO"
        else:
            stable = "  ???"

        era_str = " │ ".join(era_strs)
        print(f"    {feat:<25s} │ {era_str} │ {stable:>7s}")

    # Per-era WR summary
    sp("WIN RATE BY ERA (ALL_EXTREME entries, 20-day forward return)")
    print(f"\n    {'Era':<25s} │ {'N':>4s} │ {'WR':>6s} │ {'Avg Ret':>8s} │ {'Median':>7s}")
    print(f"    {'─'*60}")
    for era_name, era_df in eras.items():
        if len(era_df) < 5:
            continue
        wr = era_df['win'].mean() * 100
        avg = era_df['return_20d'].mean()
        med = era_df['return_20d'].median()
        print(f"    {era_name:<25s} │ {len(era_df):>4d} │ {wr:>5.1f}% │ {avg:>+7.2f}% │ {med:>+6.2f}%")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 2: Entry Window Optimization (Simons)
# ═══════════════════════════════════════════════════════════

def entry_window_optimization(store):
    p("2. SIMONS — Entry Window Optimization")
    print("  How long is the ALL_EXTREME window? Where's the best price?")

    tickers = ['SPY', 'AAPL', 'AMZN', 'MSFT', 'JPM', 'MRK', 'COST', 'MCD', 'XOM']

    all_windows = []

    for ticker in tickers:
        # Load ALL snapshots for this ticker
        snaps = store.load_snapshots(ticker, "1d")
        if snaps.empty:
            continue

        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or ohlc.empty:
            continue

        # Align price data
        prices = ohlc['close'].reindex(snaps.index, method=None)
        snaps['price'] = prices

        # Find ALL_EXTREME triggers
        extreme_mask = (
            (snaps['sigma_tide'] < -2.0) &
            (snaps['vwap_sigma_wave'] < -1.5) &
            (snaps['below_all_vwaps'] == True)
        )

        # Group consecutive extreme bars into windows
        extreme_dates = snaps.index[extreme_mask].tolist()
        if not extreme_dates:
            continue

        windows = []
        current_window = [extreme_dates[0]]
        for i in range(1, len(extreme_dates)):
            # If gap > 3 trading days, new window
            gap = (extreme_dates[i] - extreme_dates[i-1]).days
            if gap > 5:
                windows.append(current_window)
                current_window = [extreme_dates[i]]
            else:
                current_window.append(extreme_dates[i])
        windows.append(current_window)

        for window in windows:
            if len(window) < 1:
                continue
            w_snaps = snaps.loc[window]
            w_prices = w_snaps['price'].dropna()
            if w_prices.empty:
                continue

            entry_price_first = w_prices.iloc[0]
            best_price = w_prices.min()
            worst_price = w_prices.max()
            deepest_sigma = w_snaps['sigma_tide'].min()

            # Bar index of best price within window
            best_bar_idx = w_prices.values.argmin()

            # Forward return from FIRST bar vs BEST bar (20 days after window closes)
            window_end = window[-1]
            future_idx = snaps.index.get_loc(window_end)
            if future_idx + 20 < len(snaps):
                future_price = snaps['price'].iloc[future_idx + 20]
                if pd.notna(future_price) and pd.notna(entry_price_first):
                    ret_first = (future_price / entry_price_first - 1) * 100
                    ret_best = (future_price / best_price - 1) * 100 if best_price > 0 else 0
                    improvement = ret_best - ret_first

                    all_windows.append({
                        'ticker': ticker,
                        'window_start': window[0],
                        'window_bars': len(window),
                        'best_bar_position': best_bar_idx,
                        'deepest_sigma': deepest_sigma,
                        'price_first': entry_price_first,
                        'price_best': best_price,
                        'price_improvement_pct': (entry_price_first / best_price - 1) * 100,
                        'ret_first_bar': ret_first,
                        'ret_best_bar': ret_best,
                        'ret_improvement': improvement,
                    })

    if not all_windows:
        print("  No windows found!")
        return

    wdf = pd.DataFrame(all_windows)

    sp(f"ENTRY WINDOW STATISTICS ({len(wdf)} windows)")
    print(f"    Avg window duration: {wdf['window_bars'].mean():.1f} bars")
    print(f"    Median window duration: {wdf['window_bars'].median():.0f} bars")
    print(f"    Max window duration: {wdf['window_bars'].max():.0f} bars")
    print(f"    Best price is usually at bar: {wdf['best_bar_position'].median():.0f} (median)")

    sp("PRICE IMPROVEMENT: First Bar vs Best Bar in Window")
    print(f"    Windows where best ≠ first bar: {(wdf['best_bar_position'] > 0).sum()}/{len(wdf)} ({(wdf['best_bar_position'] > 0).mean()*100:.1f}%)")
    print(f"    Avg price improvement: {wdf['price_improvement_pct'].mean():+.2f}%")
    print(f"    Avg return improvement: {wdf['ret_improvement'].mean():+.2f}% (20d forward)")

    sp("OPTIMAL WAIT STRATEGY")
    print(f"\n    {'Wait N bars':>12s} │ {'N':>4s} │ {'Avg Ret':>8s} │ {'WR':>6s} │ {'vs First':>9s}")
    print(f"    {'─'*50}")

    # Test: what if we waited 0, 1, 2, 3, 5 bars?
    first_ret = wdf['ret_first_bar'].mean()
    first_wr = (wdf['ret_first_bar'] > 0).mean() * 100
    print(f"    {'Bar 0 (immed)':>12s} │ {len(wdf):>4d} │ {first_ret:>+7.2f}% │ {first_wr:>5.1f}% │      ---")

    for wait in [1, 2, 3, 5]:
        eligible = wdf[wdf['window_bars'] > wait]
        if len(eligible) < 10:
            continue
        # Approximate: improvement proportional to wait
        waited_rets = eligible['ret_first_bar'] + eligible['price_improvement_pct'] * np.minimum(wait / eligible['best_bar_position'].clip(lower=1), 1.0)
        avg_ret = waited_rets.mean()
        wr = (waited_rets > 0).mean() * 100
        delta = avg_ret - first_ret
        print(f"    {'Bar ' + str(wait):>12s} │ {len(eligible):>4d} │ {avg_ret:>+7.2f}% │ {wr:>5.1f}% │ {delta:>+8.2f}%")

    sp("PER-TICKER WINDOW PROFILE")
    print(f"\n    {'Ticker':>8s} │ {'Windows':>7s} │ {'Avg Dur':>7s} │ {'Best@Bar':>8s} │ {'Price Imp':>9s} │ {'Ret Imp':>8s}")
    print(f"    {'─'*60}")
    for ticker in sorted(wdf['ticker'].unique()):
        t = wdf[wdf['ticker'] == ticker]
        print(f"    {ticker:>8s} │ {len(t):>7d} │ {t['window_bars'].mean():>6.1f}d │ {t['best_bar_position'].median():>7.0f} │ {t['price_improvement_pct'].mean():>+8.2f}% │ {t['ret_improvement'].mean():>+7.2f}%")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 3: Exit Trajectory Mapping (Druckenmiller)
# ═══════════════════════════════════════════════════════════

def exit_trajectory(store):
    p("3. DRUCKENMILLER — Exit Trajectory Mapping")
    print("  How does sigma_tide travel from -2.5 back to 0?")

    tickers = ['SPY', 'AAPL', 'AMZN', 'MSFT', 'JPM', 'MRK', 'COST', 'MCD', 'XOM']

    all_trajectories = []

    for ticker in tickers:
        snaps = store.load_snapshots(ticker, "1d")
        if snaps.empty:
            continue

        # Find entry points where sigma_tide first crosses below -2.0
        sigma = snaps['sigma_tide']
        entries = []
        prev_above = True
        for i in range(1, len(sigma)):
            if sigma.iloc[i] < -2.0 and prev_above:
                entries.append(i)
            prev_above = sigma.iloc[i] >= -2.0

        for entry_idx in entries:
            # Track trajectory until sigma_tide > 0 or max 120 bars
            trajectory = []
            for j in range(entry_idx, min(entry_idx + 120, len(snaps))):
                trajectory.append({
                    'bars_from_entry': j - entry_idx,
                    'sigma_tide': sigma.iloc[j],
                    'sigma_current': snaps['sigma_current'].iloc[j],
                    'spread_tc': snaps['spread_tide_current'].iloc[j],
                    'regime': snaps['regime'].iloc[j],
                })
                if sigma.iloc[j] > 0 and j > entry_idx:
                    break

            if len(trajectory) > 3:
                bars_to_zero = len(trajectory) - 1
                all_trajectories.append({
                    'ticker': ticker,
                    'entry_date': snaps.index[entry_idx],
                    'entry_sigma': sigma.iloc[entry_idx],
                    'bars_to_zero': bars_to_zero,
                    'reached_zero': trajectory[-1]['sigma_tide'] > 0,
                    'trajectory': trajectory,
                })

    if not all_trajectories:
        print("  No trajectories found!")
        return

    tdf = pd.DataFrame(all_trajectories)
    reached = tdf[tdf['reached_zero']]

    sp(f"RECOVERY STATISTICS ({len(tdf)} entries, {len(reached)} reached σ>0)")
    if len(reached) > 0:
        print(f"    Avg bars to σ_tide > 0: {reached['bars_to_zero'].mean():.1f}")
        print(f"    Median bars: {reached['bars_to_zero'].median():.0f}")
        print(f"    Fastest recovery: {reached['bars_to_zero'].min():.0f} bars")
        print(f"    Slowest recovery: {reached['bars_to_zero'].max():.0f} bars")
        print(f"    Recovery rate: {len(reached)/len(tdf)*100:.1f}% (within 120 bars)")

    # Average trajectory curve: sigma_tide at bars 0, 5, 10, 20, 30, 50, 80
    sp("AVERAGE RECOVERY CURVE (σ_tide by bars from entry)")
    checkpoints = [0, 3, 5, 10, 15, 20, 30, 40, 50, 60, 80, 100]
    print(f"\n    {'Bars':>5s} │ {'σ_tide':>8s} │ {'σ_current':>10s} │ {'spread_tc':>10s} │ {'N':>4s} │ {'Visual':>30s}")
    print(f"    {'─'*75}")

    for bar in checkpoints:
        sigmas = []
        sigma_cs = []
        spreads = []
        for t in all_trajectories:
            for point in t['trajectory']:
                if point['bars_from_entry'] == bar:
                    sigmas.append(point['sigma_tide'])
                    sigma_cs.append(point['sigma_current'])
                    spreads.append(point['spread_tc'])
        if len(sigmas) >= 5:
            avg_s = np.mean(sigmas)
            avg_sc = np.mean(sigma_cs)
            avg_sp = np.mean(spreads)
            # Visual bar
            bar_len = int((avg_s + 3) * 5)  # scale: -3 to +1 → 0 to 20
            bar_len = max(0, min(30, bar_len))
            visual = "█" * bar_len + "░" * (30 - bar_len)
            print(f"    {bar:>5d} │ {avg_s:>+7.3f} │ {avg_sc:>+9.3f} │ {avg_sp:>+9.3f} │ {len(sigmas):>4d} │ {visual}")

    # Per-ticker recovery speed
    sp("PER-TICKER RECOVERY SPEED")
    print(f"\n    {'Ticker':>8s} │ {'Entries':>7s} │ {'Reached 0':>9s} │ {'Avg Bars':>8s} │ {'Med Bars':>8s} │ {'Speed':>8s}")
    print(f"    {'─'*60}")
    for ticker in sorted(tdf['ticker'].unique()):
        t = tdf[tdf['ticker'] == ticker]
        tr = t[t['reached_zero']]
        if len(tr) > 0:
            avg_b = tr['bars_to_zero'].mean()
            med_b = tr['bars_to_zero'].median()
            speed = "FAST" if avg_b < 30 else "MEDIUM" if avg_b < 60 else "SLOW"
        else:
            avg_b = med_b = float('nan')
            speed = "---"
        print(f"    {ticker:>8s} │ {len(t):>7d} │ {len(tr):>9d} │ {avg_b:>7.1f} │ {med_b:>7.0f} │ {speed:>8s}")


# ═══════════════════════════════════════════════════════════
# ANALYSIS 4: Approach Classification (Seykota)
# ═══════════════════════════════════════════════════════════

def approach_classification(store):
    p("4. SEYKOTA — Pre-Signal Approach Classification")
    print("  Crash vs Grind: does approach type predict outcome?")

    tickers = ['SPY', 'AAPL', 'AMZN', 'MSFT', 'JPM', 'MRK', 'COST', 'MCD', 'XOM']

    all_approaches = []

    for ticker in tickers:
        snaps = store.load_snapshots(ticker, "1d")
        ohlc = store.load_bars(ticker, "1d")
        if snaps.empty or ohlc is None:
            continue

        prices = ohlc['close'].reindex(snaps.index, method=None)
        sigma = snaps['sigma_tide']

        # Find first bar where sigma_tide < -2.0 (after being above)
        entries = []
        prev_above = True
        for i in range(1, len(sigma)):
            if sigma.iloc[i] < -2.0 and prev_above:
                entries.append(i)
            prev_above = sigma.iloc[i] >= -2.0

        for entry_idx in entries:
            # Look back: how many bars from sigma=-1.0 to sigma=-2.0?
            approach_bars = 0
            for j in range(entry_idx - 1, max(entry_idx - 60, 0), -1):
                if sigma.iloc[j] >= -1.0:
                    approach_bars = entry_idx - j
                    break

            if approach_bars == 0:
                approach_bars = 60  # was already deep

            # Classify approach
            if approach_bars <= 3:
                approach_type = "CRASH"
            elif approach_bars <= 10:
                approach_type = "FAST_DECLINE"
            elif approach_bars <= 25:
                approach_type = "GRIND"
            else:
                approach_type = "SLOW_BLEED"

            # Forward return (20d)
            entry_price = prices.iloc[entry_idx] if entry_idx < len(prices) else None
            future_idx = entry_idx + 20
            future_price = prices.iloc[future_idx] if future_idx < len(prices) else None

            if entry_price and future_price and pd.notna(entry_price) and pd.notna(future_price):
                ret = (future_price / entry_price - 1) * 100
                all_approaches.append({
                    'ticker': ticker,
                    'entry_date': snaps.index[entry_idx],
                    'approach_bars': approach_bars,
                    'approach_type': approach_type,
                    'entry_sigma': sigma.iloc[entry_idx],
                    'return_20d': ret,
                    'win': 1 if ret > 0 else 0,
                    'wave_slope': snaps['wave_slope'].iloc[entry_idx],
                    'wave_accel': snaps['wave_accel'].iloc[entry_idx],
                    'tide_accel': snaps['tide_accel'].iloc[entry_idx],
                })

    if not all_approaches:
        print("  No approaches found!")
        return

    adf = pd.DataFrame(all_approaches)

    sp(f"APPROACH TYPE → OUTCOME ({len(adf)} entries)")
    print(f"\n    {'Approach':>14s} │ {'N':>4s} │ {'WR':>6s} │ {'Avg Ret':>8s} │ {'Med Ret':>8s} │ {'Avg Bars':>8s} │ {'Verdict':>15s}")
    print(f"    {'─'*80}")

    for atype in ['CRASH', 'FAST_DECLINE', 'GRIND', 'SLOW_BLEED']:
        sub = adf[adf['approach_type'] == atype]
        if len(sub) < 5:
            print(f"    {atype:>14s} │ {len(sub):>4d} │   --- │     --- │     --- │     --- │ (too few)")
            continue
        wr = sub['win'].mean() * 100
        avg_ret = sub['return_20d'].mean()
        med_ret = sub['return_20d'].median()
        avg_bars = sub['approach_bars'].mean()
        verdict = "★★★ BEST" if wr > 75 else "★★ GOOD" if wr > 65 else "★ OK" if wr > 55 else "⚠️ WEAK"
        print(f"    {atype:>14s} │ {len(sub):>4d} │ {wr:>5.1f}% │ {avg_ret:>+7.2f}% │ {med_ret:>+7.2f}% │ {avg_bars:>7.1f} │ {verdict:>15s}")

    # Statistical test: does approach type predict outcome?
    sp("STATISTICAL TEST: Approach Type as Predictor")
    # Correlation between approach_bars and outcome
    r, pv = stats.pearsonr(adf['approach_bars'], adf['win'])
    print(f"    Correlation (approach_bars → win): r={r:+.3f}, p={pv:.4f}")
    direction = "CRASH is better" if r < 0 else "GRIND is better"
    sig = "★★★ SIGNIFICANT" if pv < 0.01 else "★★ SIGNIFICANT" if pv < 0.05 else "★ MARGINAL" if pv < 0.10 else "NOT SIGNIFICANT"
    print(f"    Direction: {direction}")
    print(f"    Significance: {sig}")

    # Per-ticker approach patterns
    sp("PER-TICKER: Dominant Approach Type")
    print(f"\n    {'Ticker':>8s} │ {'N':>4s} │ {'CRASH':>6s} │ {'FAST':>6s} │ {'GRIND':>6s} │ {'SLOW':>6s} │ {'Best Type':>14s} │ {'Best WR':>7s}")
    print(f"    {'─'*80}")
    for ticker in sorted(adf['ticker'].unique()):
        t = adf[adf['ticker'] == ticker]
        counts = t['approach_type'].value_counts()

        best_type = None
        best_wr = 0
        type_wrs = {}
        for atype in ['CRASH', 'FAST_DECLINE', 'GRIND', 'SLOW_BLEED']:
            sub = t[t['approach_type'] == atype]
            n = len(sub)
            wr = sub['win'].mean() * 100 if n >= 3 else float('nan')
            type_wrs[atype] = f"{n:>2d}" if n > 0 else " 0"
            if n >= 3 and wr > best_wr:
                best_wr = wr
                best_type = atype

        print(f"    {ticker:>8s} │ {len(t):>4d} │ {type_wrs.get('CRASH', ' 0'):>6s} │ {type_wrs.get('FAST_DECLINE', ' 0'):>6s} │ {type_wrs.get('GRIND', ' 0'):>6s} │ {type_wrs.get('SLOW_BLEED', ' 0'):>6s} │ {(best_type or '---'):>14s} │ {best_wr:>6.1f}%")

    # NEW META-FEATURE recommendation
    sp("META-FEATURE RECOMMENDATION")
    crash_wr = adf[adf['approach_type'] == 'CRASH']['win'].mean() * 100 if len(adf[adf['approach_type'] == 'CRASH']) >= 5 else 0
    grind_wr = adf[adf['approach_type'] == 'GRIND']['win'].mean() * 100 if len(adf[adf['approach_type'] == 'GRIND']) >= 5 else 0
    spread = abs(crash_wr - grind_wr)
    print(f"    CRASH WR: {crash_wr:.1f}% vs GRIND WR: {grind_wr:.1f}% (spread: {spread:.1f}pp)")
    if spread > 10:
        print(f"    ★★★ approach_type IS a strong meta-feature ({spread:.0f}pp WR spread)")
        print(f"    → Add approach_bars as ChannelSnapshot field #42")
    elif spread > 5:
        print(f"    ★★ approach_type IS a moderate meta-feature ({spread:.0f}pp WR spread)")
    else:
        print(f"    ⚠️ approach_type is NOT a strong differentiator ({spread:.0f}pp)")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v20 — FEATURE LAKE ANALYTICS")
    print("  93,776 snapshots. 4 expert analyses. Zero recomputation.")

    store = TimescaleDataStore()

    feature_stability(store)
    entry_window_optimization(store)
    exit_trajectory(store)
    approach_classification(store)

    store.close()

    p("v20 COMPLETE — Feature Lake is operational")
    print("  Every analysis read directly from engine.channel_snapshots.")
    print("  No recomputation. This is what the Feature Lake enables.")
