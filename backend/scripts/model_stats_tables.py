#!/usr/bin/env python3
"""
Model Statistical Deep-Dive — Tables by State, Stereotype & Observer
======================================================================
Uses the signal_footprint (91K signals) + zigzag ground truth to produce:

  1. PROBABILITY TABLE STATS: P(bull) by state key → actual outcome
  2. OBSERVER (KALMAN) STATS: How the filter modulates timing
  3. COMBINED MODEL: Table × Observer interaction
  4. TEMPORAL ANALYSIS: When signals fire relative to troughs
  5. PER-TICKER CONSISTENCY: Edge across 17 tickers
  6. HIERARCHICAL LEVEL: L1 vs L2 vs L3 vs L4 quality

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/model_stats_tables.py
"""
import sys, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

TICKERS = [
    "AAPL", "AMZN", "COST", "HD", "HON", "IBM", "JNJ", "JPM",
    "MCD", "MRK", "MSFT", "PEP", "PG", "QQQ", "SPY", "WMT", "XOM",
]
CONF_WINDOW = 5


def banner(title):
    print(f"\n{'═' * 110}")
    print(f"  {title}")
    print(f"{'═' * 110}")


def load_all():
    """Load signal_footprint + zigzag + OHLCV bars."""
    store = TimescaleDataStore()
    conn = store._conn()

    sigs = pd.read_sql("""
        SELECT ticker, timestamp::date as date, action, conviction, p_bull,
               observer_recovery, observer_state, hookup, state_key, level,
               vol_regime, reasoning
        FROM engine.signal_footprint
        ORDER BY ticker, timestamp
    """, conn)

    zz25 = pd.read_sql("SELECT ticker, timestamp::date as date, tp_type, price FROM engine.zigzag_points WHERE min_swing_pct=0.025 ORDER BY ticker, timestamp", conn)
    zz50 = pd.read_sql("SELECT ticker, timestamp::date as date, tp_type, price FROM engine.zigzag_points WHERE min_swing_pct=0.05 ORDER BY ticker, timestamp", conn)
    zz75 = pd.read_sql("SELECT ticker, timestamp::date as date, tp_type, price FROM engine.zigzag_points WHERE min_swing_pct=0.075 ORDER BY ticker, timestamp", conn)

    bars = pd.read_sql("SELECT ticker, time::date as date, close FROM market.ohlcv_bars WHERE timeframe='1d' ORDER BY ticker, time", conn)

    store._put(conn); store.close()
    for d in [sigs, zz25, zz50, zz75, bars]:
        d['date'] = pd.to_datetime(d['date'])
    return sigs, zz25, zz50, zz75, bars


def enrich_with_zigzag(df, zz25, zz50, zz75, bars):
    """Add trough proximity, confluence level, profit-to-peak, side.
    
    VECTORIZED per-ticker using np.searchsorted — 100× faster than iterrows.
    """
    df = df.merge(bars[['ticker', 'date', 'close']], on=['ticker', 'date'], how='left')

    # Build trough map with confluence (per ticker)
    trough_map = {}
    for ticker in TICKERS:
        t25 = zz25[(zz25['ticker'] == ticker) & (zz25['tp_type'] == 'MIN')].sort_values('date')
        d50 = zz50[(zz50['ticker'] == ticker) & (zz50['tp_type'] == 'MIN')]['date'].values.astype('datetime64[D]')
        d75 = zz75[(zz75['ticker'] == ticker) & (zz75['tp_type'] == 'MIN')]['date'].values.astype('datetime64[D]')
        entries_dates = []
        entries_levels = []
        entries_prices = []
        for _, r in t25.iterrows():
            d = np.datetime64(r['date'], 'D')
            has50 = len(d50) > 0 and np.min(np.abs((d50 - d) / np.timedelta64(1, 'D'))) <= CONF_WINDOW
            has75 = len(d75) > 0 and np.min(np.abs((d75 - d) / np.timedelta64(1, 'D'))) <= CONF_WINDOW
            level = 3 if (has50 and has75) else 2 if has50 else 1
            entries_dates.append(d)
            entries_levels.append(level)
            entries_prices.append(float(r['price']))
        trough_map[ticker] = (np.array(entries_dates), np.array(entries_levels), np.array(entries_prices))

    # Build peak map (5% zigzag MAXs, per ticker)
    peak_map = {}
    for ticker in TICKERS:
        peaks = zz50[(zz50['ticker'] == ticker) & (zz50['tp_type'] == 'MAX')].sort_values('date')
        if len(peaks) > 0:
            peak_map[ticker] = (peaks['date'].values.astype('datetime64[D]'),
                                peaks['price'].values.astype(float))
        else:
            peak_map[ticker] = (np.array([], dtype='datetime64[D]'), np.array([]))

    # Vectorized enrichment per ticker
    t_level = np.full(len(df), np.nan)
    t_side = np.empty(len(df), dtype=object)
    t_dist = np.full(len(df), np.nan)
    profit = np.full(len(df), np.nan)

    for ticker in TICKERS:
        tk_mask = df['ticker'].values == ticker
        tk_idx = np.where(tk_mask)[0]
        if len(tk_idx) == 0:
            continue

        tk_dates = df.loc[tk_idx, 'date'].values.astype('datetime64[D]')
        tk_close = df.loc[tk_idx, 'close'].values.astype(float)

        # Trough matching
        trough_dates, trough_levels, trough_prices = trough_map.get(ticker, (np.array([]), np.array([]), np.array([])))
        if len(trough_dates) > 0:
            # For each signal date, find nearest trough
            # Use broadcasting: shape (n_signals, n_troughs)
            diffs = (trough_dates[None, :] - tk_dates[:, None]).astype(float)  # in days
            abs_diffs = np.abs(diffs)
            nearest_idx = abs_diffs.argmin(axis=1)
            nearest_dist_signed = diffs[np.arange(len(tk_dates)), nearest_idx]  # + = trough is AFTER signal
            nearest_abs = abs_diffs[np.arange(len(tk_dates)), nearest_idx]
            nearest_level = trough_levels[nearest_idx]

            t_dist[tk_idx] = nearest_abs
            t_level[tk_idx] = nearest_level
            # side: AFTER = signal fires after trough (trough is before signal → diff ≤ 0)
            for j, i in enumerate(tk_idx):
                t_side[i] = "AFTER" if nearest_dist_signed[j] <= 0 else "BEFORE"

        # Profit to next peak
        pk_dates, pk_prices = peak_map.get(ticker, (np.array([]), np.array([])))
        if len(pk_dates) > 0:
            for j, i in enumerate(tk_idx):
                pi = np.searchsorted(pk_dates, tk_dates[j], side='right')
                if pi < len(pk_prices) and not np.isnan(tk_close[j]) and tk_close[j] > 0:
                    profit[i] = (pk_prices[pi] / tk_close[j] - 1) * 100

        print(f"    {ticker}: {len(tk_idx):,} signals enriched")

    df['trough_level'] = t_level
    df['trough_side'] = t_side
    df['trough_dist'] = t_dist
    df['profit_to_peak'] = profit
    df['near_trough'] = df['trough_dist'] <= 15
    df['at_trough'] = df['trough_dist'] <= 5
    df['is_after'] = df['trough_side'] == 'AFTER'
    return df


# ═══════════════════════════════════════════════════════════════
# TABLE 1: PROBABILITY STATE STATISTICS
# ═══════════════════════════════════════════════════════════════

def table1_probability_states(df):
    banner("TABLE 1: PROBABILITY TABLE — P(bull) BIN → ACTUAL OUTCOME")
    print("  How well does each P(bull) bin predict real market outcomes?")
    print("  Ground truth: zigzag 5% troughs (AFTER = correct timing)")
    print()

    accum = df[df['action'] == 'ACCUMULATE'].copy()

    pbins = [
        (0.65, 0.70, "65-70%"),
        (0.70, 0.75, "70-75%"),
        (0.75, 0.80, "75-80%"),
        (0.80, 0.85, "80-85%"),
        (0.85, 0.90, "85-90%"),
        (0.90, 1.01, "90-100%"),
    ]

    print(f"  {'P(bull)':<12s} │ {'N':>7s} │ {'%AFTER':>7s} │ {'±5d':>6s} │ {'±10d':>6s} │ {'Med Pft':>8s} │ {'Avg Pft':>8s} │ {'WinRate':>8s} │ {'PF':>6s} │ Verdict")
    print(f"  {'─'*105}")

    for lo, hi, label in pbins:
        mask = accum['p_bull'].notna() & (accum['p_bull'] >= lo) & (accum['p_bull'] < hi)
        sub = accum[mask]
        if len(sub) < 30:
            continue
        after = sub['is_after'].mean() * 100
        at5 = (sub['trough_dist'] <= 5).mean() * 100
        at10 = (sub['trough_dist'] <= 10).mean() * 100
        pft = sub['profit_to_peak'].dropna()
        med = pft.median() if len(pft) > 0 else 0
        avg = pft.mean() if len(pft) > 0 else 0
        wr = (pft > 0).mean() * 100 if len(pft) > 0 else 0
        w = pft[pft > 0].sum(); l = abs(pft[pft < 0].sum())
        pf = w / l if l > 0 else 99.9

        verdict = "★★★" if wr > 70 and pf > 2 else "★★" if wr > 60 and pf > 1.5 else "★" if wr > 55 else "—"
        print(f"  {label:<12s} │ {len(sub):>7,} │ {after:>6.1f}% │ {at5:>5.1f}% │ {at10:>5.1f}% │ {med:>+7.1f}% │ {avg:>+7.1f}% │ {wr:>7.1f}% │ {pf:>5.2f} │ {verdict}")


# ═══════════════════════════════════════════════════════════════
# TABLE 2: STATE KEY (STEREOTYPE) STATISTICS
# ═══════════════════════════════════════════════════════════════

def table2_state_keys(df):
    banner("TABLE 2: STATE KEY STEREOTYPES — Top 30 Most Active")
    print("  Each state_key = unique RC configuration (tide×σ_c×σ_w×σVw)")
    print("  Sorted by absolute N of ACCUMULATE signals")
    print()

    accum = df[df['action'] == 'ACCUMULATE'].copy()
    accum = accum[accum['state_key'].notna()]

    groups = accum.groupby('state_key').agg(
        N=('action', 'count'),
        p_bull_mean=('p_bull', 'mean'),
        pct_after=('is_after', 'mean'),
        at_trough_5=('at_trough', 'mean'),
        profit_med=('profit_to_peak', 'median'),
        profit_avg=('profit_to_peak', 'mean'),
        obs_recov_mean=('observer_recovery', 'mean'),
    ).reset_index()
    groups = groups.sort_values('N', ascending=False).head(30)

    print(f"  {'State Key':<28s} │ {'N':>6s} │ {'P(bull)':>8s} │ {'%AFTER':>7s} │ {'±5d':>6s} │ {'Med Pft':>8s} │ {'Obs μ':>7s} │ Verdict")
    print(f"  {'─'*100}")

    for _, r in groups.iterrows():
        pct_after = r['pct_after'] * 100
        at5 = r['at_trough_5'] * 100
        med_pft = r['profit_med'] if not pd.isna(r['profit_med']) else 0
        obs_mean = r['obs_recov_mean'] if not pd.isna(r['obs_recov_mean']) else 0

        verdict = "★★" if pct_after > 60 and med_pft > 3 else "★" if pct_after > 55 else "⚠" if pct_after < 45 else "—"
        print(f"  {r['state_key']:<28s} │ {r['N']:>6,} │ {r['p_bull_mean']:>7.1%} │ {pct_after:>6.1f}% │ {at5:>5.1f}% │ {med_pft:>+7.1f}% │ {obs_mean:>+6.3f} │ {verdict}")


# ═══════════════════════════════════════════════════════════════
# TABLE 3: OBSERVER (KALMAN) FILTER STATISTICS
# ═══════════════════════════════════════════════════════════════

def table3_observer_stats(df):
    banner("TABLE 3: UNIFIED OBSERVER — Kalman Filter Timing Impact")
    print("  How does observer_recovery modulate signal quality?")
    print("  The Observer provides VELOCITY (where you're going)")
    print("  The Table provides POSITION (where you are)")
    print()

    accum = df[df['action'] == 'ACCUMULATE'].copy()

    # 3a. By observer state
    print(f"  ── BY OBSERVER STATE ──")
    print(f"  {'State':<18s} │ {'N':>7s} │ {'%AFTER':>7s} │ {'±5d':>6s} │ {'±10d':>6s} │ {'Med Pft':>8s} │ {'WR':>6s} │ {'PF':>6s} │ Lift")
    print(f"  {'─'*95}")

    baseline_after = accum['is_after'].mean()
    for state in ['RECOVERING', 'STABLE', 'TRANSITIONING', 'DETERIORATING']:
        sub = accum[accum['observer_state'] == state]
        if len(sub) < 30:
            continue
        after = sub['is_after'].mean() * 100
        at5 = (sub['trough_dist'] <= 5).mean() * 100
        at10 = (sub['trough_dist'] <= 10).mean() * 100
        pft = sub['profit_to_peak'].dropna()
        med = pft.median() if len(pft) > 0 else 0
        wr = (pft > 0).mean() * 100 if len(pft) > 0 else 0
        w = pft[pft > 0].sum(); l = abs(pft[pft < 0].sum())
        pf = w / l if l > 0 else 99.9
        lift = after / 100 - baseline_after
        print(f"  {state:<18s} │ {len(sub):>7,} │ {after:>6.1f}% │ {at5:>5.1f}% │ {at10:>5.1f}% │ {med:>+7.1f}% │ {wr:>5.1f}% │ {pf:>5.2f} │ {lift:>+.1%}")

    # 3b. By recovery score threshold
    print(f"\n  ── BY RECOVERY SCORE THRESHOLD ──")
    print(f"  {'Threshold':<20s} │ {'N':>7s} │ {'%select':>7s} │ {'%AFTER':>7s} │ {'Med Pft':>8s} │ {'WR':>6s} │ {'False Alarm':>12s}")
    print(f"  {'─'*85}")

    thresholds = [(-1.0, -0.3, "r < -0.3 (DETER)"),
                  (-0.3, 0.0, "-0.3 ≤ r < 0 (WEAK)"),
                  (0.0, 0.3, "0 ≤ r < 0.3 (CONF)"),
                  (0.3, 1.01, "r ≥ 0.3 (RECOV)")]

    for lo, hi, label in thresholds:
        mask = (accum['observer_recovery'] >= lo) & (accum['observer_recovery'] < hi)
        sub = accum[mask]
        if len(sub) < 30:
            continue
        pct_sel = len(sub) / len(accum) * 100
        after = sub['is_after'].mean() * 100
        pft = sub['profit_to_peak'].dropna()
        med = pft.median() if len(pft) > 0 else 0
        wr = (pft > 0).mean() * 100 if len(pft) > 0 else 0
        fa = (sub['trough_dist'] > 15).mean() * 100
        print(f"  {label:<20s} │ {len(sub):>7,} │ {pct_sel:>6.1f}% │ {after:>6.1f}% │ {med:>+7.1f}% │ {wr:>5.1f}% │ {fa:>11.1f}%")


# ═══════════════════════════════════════════════════════════════
# TABLE 4: COMBINED MODEL (Table × Observer)
# ═══════════════════════════════════════════════════════════════

def table4_combined_model(df):
    banner("TABLE 4: COMBINED MODEL — P(bull) × Observer Interaction")
    print("  The model is: TABLE (where) × OBSERVER (velocity)")
    print("  Matrix: P(bull) bins × Observer state")
    print()

    accum = df[df['action'] == 'ACCUMULATE'].copy()
    accum = accum[accum['p_bull'].notna()]

    p_bins = [(0.65, 0.75, "65-75%"), (0.75, 0.85, "75-85%"), (0.85, 1.01, "85-100%")]
    obs_states = ['DETERIORATING', 'STABLE', 'TRANSITIONING', 'RECOVERING']

    print(f"  {'':>12s}", end="")
    for state in obs_states:
        print(f" │ {state:^18s}", end="")
    print(f" │ {'ALL':^18s}")
    print(f"  {'─'*100}")

    for lo, hi, label in p_bins:
        print(f"  {label:<12s}", end="")
        pmask = (accum['p_bull'] >= lo) & (accum['p_bull'] < hi)
        for state in obs_states:
            sub = accum[pmask & (accum['observer_state'] == state)]
            if len(sub) < 15:
                print(f" │ {'N<15':^18s}", end="")
                continue
            after = sub['is_after'].mean() * 100
            pft = sub['profit_to_peak'].dropna()
            wr = (pft > 0).mean() * 100 if len(pft) > 0 else 0
            med = pft.median() if len(pft) > 0 else 0
            print(f" │ {after:>4.0f}%A {wr:>4.0f}%W {med:>+4.0f}", end="")

        # ALL states for this P(bull) bin
        sub = accum[pmask]
        after = sub['is_after'].mean() * 100
        pft = sub['profit_to_peak'].dropna()
        wr = (pft > 0).mean() * 100 if len(pft) > 0 else 0
        med = pft.median() if len(pft) > 0 else 0
        print(f" │ {after:>4.0f}%A {wr:>4.0f}%W {med:>+4.0f}")

    # Summary row
    print(f"  {'─'*100}")
    print(f"  {'ALL':<12s}", end="")
    for state in obs_states:
        sub = accum[accum['observer_state'] == state]
        if len(sub) < 15:
            print(f" │ {'N<15':^18s}", end="")
            continue
        after = sub['is_after'].mean() * 100
        pft = sub['profit_to_peak'].dropna()
        wr = (pft > 0).mean() * 100 if len(pft) > 0 else 0
        med = pft.median() if len(pft) > 0 else 0
        print(f" │ {after:>4.0f}%A {wr:>4.0f}%W {med:>+4.0f}", end="")
    sub = accum
    after = sub['is_after'].mean() * 100
    pft = sub['profit_to_peak'].dropna()
    wr = (pft > 0).mean() * 100 if len(pft) > 0 else 0
    med = pft.median() if len(pft) > 0 else 0
    print(f" │ {after:>4.0f}%A {wr:>4.0f}%W {med:>+4.0f}")


# ═══════════════════════════════════════════════════════════════
# TABLE 5: TEMPORAL ANALYSIS
# ═══════════════════════════════════════════════════════════════

def table5_temporal(df):
    banner("TABLE 5: TEMPORAL ANALYSIS — When Do Signals Fire Relative to Troughs?")
    print("  Negative = BEFORE trough (early/catching knife)")
    print("  Zero = AT trough (perfect timing)")
    print("  Positive = AFTER trough (confirmed entry)")
    print()

    accum = df[df['action'] == 'ACCUMULATE'].copy()
    accum = accum[accum['trough_dist'].notna()]

    # Add signed distance (negative = before, positive = after)
    accum['signed_dist'] = accum.apply(
        lambda r: -r['trough_dist'] if r['trough_side'] == 'BEFORE' else r['trough_dist'], axis=1)

    # 5a. Distribution histogram
    print(f"  ── TIMING DISTRIBUTION ──")
    bins = [(-100, -15, ">15d BEFORE"), (-15, -10, "10-15d BEFORE"), (-10, -5, "5-10d BEFORE"),
            (-5, -1, "1-5d BEFORE"), (-1, 1, "AT TROUGH (±1d)"), (1, 5, "1-5d AFTER"),
            (5, 10, "5-10d AFTER"), (10, 15, "10-15d AFTER"), (15, 100, ">15d AFTER")]

    print(f"  {'Window':<20s} │ {'N':>7s} │ {'%':>6s} │ {'Med Pft':>8s} │ {'WR':>6s} │ Bar")
    print(f"  {'─'*80}")

    for lo, hi, label in bins:
        mask = (accum['signed_dist'] >= lo) & (accum['signed_dist'] < hi)
        sub = accum[mask]
        if len(sub) < 10:
            continue
        pct = len(sub) / len(accum) * 100
        pft = sub['profit_to_peak'].dropna()
        med = pft.median() if len(pft) > 0 else 0
        wr = (pft > 0).mean() * 100 if len(pft) > 0 else 0
        bar_len = int(pct * 2)
        bar = "█" * bar_len
        print(f"  {label:<20s} │ {len(sub):>7,} │ {pct:>5.1f}% │ {med:>+7.1f}% │ {wr:>5.1f}% │ {bar}")

    # 5b. Timing by Observer state
    print(f"\n  ── TIMING BY OBSERVER STATE ──")
    print(f"  {'Observer State':<18s} │ {'Med Dist':>9s} │ {'%BEFORE':>8s} │ {'%AT±5d':>7s} │ {'%AFTER':>7s} │ {'Timing Verdict':>15s}")
    print(f"  {'─'*75}")

    for state in ['RECOVERING', 'STABLE', 'TRANSITIONING', 'DETERIORATING']:
        sub = accum[accum['observer_state'] == state]
        if len(sub) < 30:
            continue
        med_dist = sub['signed_dist'].median()
        pct_before = (sub['trough_side'] == 'BEFORE').mean() * 100
        pct_at = (sub['trough_dist'] <= 5).mean() * 100
        pct_after = (sub['trough_side'] == 'AFTER').mean() * 100

        if med_dist > 2:
            verdict = "✅ CONFIRMED"
        elif med_dist > -2:
            verdict = "⚡ AT TROUGH"
        else:
            verdict = "⚠️ EARLY"

        print(f"  {state:<18s} │ {med_dist:>+8.1f}d │ {pct_before:>7.1f}% │ {pct_at:>6.1f}% │ {pct_after:>6.1f}% │ {verdict}")

    # 5c. Timing by P(bull) level
    print(f"\n  ── TIMING BY P(BULL) LEVEL ──")
    print(f"  {'P(bull)':<12s} │ {'Med Dist':>9s} │ {'%BEFORE':>8s} │ {'%AT±5d':>7s} │ {'%AFTER':>7s}")
    print(f"  {'─'*55}")

    for lo, hi, label in [(0.65, 0.75, "65-75%"), (0.75, 0.85, "75-85%"), (0.85, 1.01, "85-100%")]:
        sub = accum[(accum['p_bull'] >= lo) & (accum['p_bull'] < hi)]
        if len(sub) < 30:
            continue
        med_dist = sub['signed_dist'].median()
        pct_before = (sub['trough_side'] == 'BEFORE').mean() * 100
        pct_at = (sub['trough_dist'] <= 5).mean() * 100
        pct_after = (sub['trough_side'] == 'AFTER').mean() * 100
        print(f"  {label:<12s} │ {med_dist:>+8.1f}d │ {pct_before:>7.1f}% │ {pct_at:>6.1f}% │ {pct_after:>6.1f}%")


# ═══════════════════════════════════════════════════════════════
# TABLE 6: PER-TICKER CONSISTENCY
# ═══════════════════════════════════════════════════════════════

def table6_per_ticker(df):
    banner("TABLE 6: PER-TICKER EDGE — Consistency Across 17 Tickers")
    print()

    accum = df[df['action'] == 'ACCUMULATE'].copy()

    print(f"  {'Ticker':<8s} │ {'N':>6s} │ {'%AFTER':>7s} │ {'±5d':>6s} │ {'±10d':>6s} │ {'Med Pft':>8s} │ {'Avg Pft':>8s} │ {'WR':>6s} │ {'PF':>6s} │ {'Obs μ':>7s} │ Verdict")
    print(f"  {'─'*110}")

    edge_count = 0
    for ticker in TICKERS:
        sub = accum[accum['ticker'] == ticker]
        if len(sub) < 50:
            continue
        after = sub['is_after'].mean() * 100
        at5 = (sub['trough_dist'] <= 5).mean() * 100
        at10 = (sub['trough_dist'] <= 10).mean() * 100
        pft = sub['profit_to_peak'].dropna()
        med = pft.median() if len(pft) > 0 else 0
        avg = pft.mean() if len(pft) > 0 else 0
        wr = (pft > 0).mean() * 100 if len(pft) > 0 else 0
        w = pft[pft > 0].sum(); l = abs(pft[pft < 0].sum())
        pf = w / l if l > 0 else 99.9
        obs_mean = sub['observer_recovery'].mean()

        if wr > 60 and pf > 1.5:
            verdict = "★★ STRONG"
            edge_count += 1
        elif wr > 55 and pf > 1.2:
            verdict = "★ EDGE"
            edge_count += 1
        elif wr > 50:
            verdict = "~ WEAK"
        else:
            verdict = "✗ NONE"

        print(f"  {ticker:<8s} │ {len(sub):>6,} │ {after:>6.1f}% │ {at5:>5.1f}% │ {at10:>5.1f}% │ {med:>+7.1f}% │ {avg:>+7.1f}% │ {wr:>5.1f}% │ {pf:>5.2f} │ {obs_mean:>+6.3f} │ {verdict}")

    print(f"\n  TICKERS WITH EDGE: {edge_count}/{len(TICKERS)}")

    # TRIM signals summary
    trim = df[df['action'] == 'TRIM'].copy()
    if len(trim) > 100:
        print(f"\n  ── TRIM SIGNALS SUMMARY ──")
        print(f"  Total TRIM: {len(trim):,}")
        for ticker in TICKERS:
            sub = trim[trim['ticker'] == ticker]
            if len(sub) < 10:
                continue
            # Check proximity to zigzag peaks


# ═══════════════════════════════════════════════════════════════
# TABLE 7: HIERARCHICAL LEVEL QUALITY
# ═══════════════════════════════════════════════════════════════

def table7_hierarchical_levels(df):
    banner("TABLE 7: HIERARCHICAL LEVEL — L1 vs L2 vs L3 vs L4 Quality")
    print("  L1 = Full 4D (Tide×σ_c×σ_w×σVw) — max precision")
    print("  L2 = 3D (σ_c×σ_w×σVw) — robust when L1 sparse")
    print("  L3 = 2D (σ_c×σVw) — core pair")
    print("  L4 = 1D (σVw) — ultimate fallback")
    print()

    accum = df[df['action'] == 'ACCUMULATE'].copy()
    accum = accum[accum['level'].notna()]

    print(f"  {'Level':<15s} │ {'N':>7s} │ {'%select':>7s} │ {'%AFTER':>7s} │ {'±5d':>6s} │ {'Med Pft':>8s} │ {'WR':>6s} │ {'PF':>6s} │ Quality")
    print(f"  {'─'*90}")

    for lvl in ['L1_full', 'L2_no_tide', 'L3_sc_svw', 'L4_svw']:
        sub = accum[accum['level'] == lvl]
        if len(sub) < 30:
            continue
        pct = len(sub) / len(accum) * 100
        after = sub['is_after'].mean() * 100
        at5 = (sub['trough_dist'] <= 5).mean() * 100
        pft = sub['profit_to_peak'].dropna()
        med = pft.median() if len(pft) > 0 else 0
        wr = (pft > 0).mean() * 100 if len(pft) > 0 else 0
        w = pft[pft > 0].sum(); l = abs(pft[pft < 0].sum())
        pf = w / l if l > 0 else 99.9

        quality = "HIGH" if wr > 60 and pf > 1.5 else "GOOD" if wr > 55 else "FAIR" if wr > 50 else "POOR"
        print(f"  {lvl:<15s} │ {len(sub):>7,} │ {pct:>6.1f}% │ {after:>6.1f}% │ {at5:>5.1f}% │ {med:>+7.1f}% │ {wr:>5.1f}% │ {pf:>5.2f} │ {quality}")


# ═══════════════════════════════════════════════════════════════
# TABLE 8: MODEL ARCHITECTURE SUMMARY
# ═══════════════════════════════════════════════════════════════

def table8_model_summary(df):
    banner("TABLE 8: MODEL ARCHITECTURE — How Everything Connects")

    accum = df[df['action'] == 'ACCUMULATE'].copy()
    trim = df[df['action'] == 'TRIM'].copy()
    hold = df[df['action'] == 'HOLD'].copy()

    total = len(df)
    print(f"""
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                    QUALITY SWING MODEL ARCHITECTURE                     │
  │                                                                         │
  │  INPUT: 91K daily bars × 17 tickers (2006-2026)                        │
  │                                                                         │
  │  ┌─────────────────────────────────────────────────────────┐           │
  │  │ LAYER 1: POSITION — RC Probability Table               │           │
  │  │   4D lookup: tide × σ_current × σ_wave × σVWAP_wave    │           │
  │  │   → P(bull|state): probability of bullish outcome       │           │
  │  │   Hierarchical: L1(4D) → L2(3D) → L3(2D) → L4(1D)     │           │
  │  │                                                         │           │
  │  │   Decision:                                             │           │
  │  │     P(bull) ≥ 75% → HIGH conviction ACCUMULATE          │           │
  │  │     P(bull) ≥ 65% → MODERATE conviction (needs confirm) │           │
  │  │     P(bull) ≤ 25% → Aggressive TRIM                     │           │
  │  │     P(bull) ≤ 35% → Moderate TRIM                       │           │
  │  └──────────────────────┬──────────────────────────────────┘           │
  │                         │                                               │
  │  ┌──────────────────────▼──────────────────────────────────┐           │
  │  │ LAYER 2: VELOCITY — Unified Kalman Observer             │           │
  │  │   10D multivariate filter: 5 positions + 5 velocities   │           │
  │  │   State: [σ_C, σV_W, τ_W, RSI, conj_WT] + velocities   │           │
  │  │   → recovery_score: cos(vel, recovery_dir) ∈ [-1, +1]   │           │
  │  │                                                         │           │
  │  │   Modulation:                                           │           │
  │  │     r > 0.3  → RECOVERING: ×1.15 conviction boost       │           │
  │  │     r > 0    → CONFIRMED: ×1.0 (direction positive)     │           │
  │  │     r ≤ 0    → UNCONFIRMED: ×0.5 (still falling)        │           │
  │  │     r < -0.3 → DETERIORATING: ×0.3 (near-block)         │           │
  │  └──────────────────────┬──────────────────────────────────┘           │
  │                         │                                               │
  │  ┌──────────────────────▼──────────────────────────────────┐           │
  │  │ LAYER 3: GATES & MODIFIERS                              │           │
  │  │   • VOL_CRISIS → hard block                             │           │
  │  │   • Market Health cascade → BEAR=block, CORR=50%        │           │
  │  │   • F&G contrarian → CAPITULATION_BUY=+75%              │           │
  │  │   • Sentinel TurnSignal → archetype confirmation         │           │
  │  │   • Passport reliability scaling                         │           │
  │  └──────────────────────┬──────────────────────────────────┘           │
  │                         ▼                                               │
  │   OUTPUT: ACCUMULATE ({len(accum):,}) │ TRIM ({len(trim):,}) │ HOLD ({len(hold):,})        │
  │           {len(accum)/total*100:.1f}% of bars          │ {len(trim)/total*100:.1f}%          │ {len(hold)/total*100:.1f}%        │
  └─────────────────────────────────────────────────────────────────────────┘""")

    # Overall system stats
    print(f"\n  ── OVERALL SYSTEM PERFORMANCE ──")
    pft = accum['profit_to_peak'].dropna()
    wr = (pft > 0).mean() * 100 if len(pft) > 0 else 0
    w = pft[pft > 0].sum(); l = abs(pft[pft < 0].sum())
    pf = w / l if l > 0 else 99.9
    after = accum['is_after'].mean() * 100 if len(accum) > 0 else 0
    at5 = (accum['trough_dist'] <= 5).mean() * 100 if len(accum) > 0 else 0

    print(f"    ACCUMULATE signals:     {len(accum):,}")
    print(f"    Fires AFTER trough:     {after:.1f}%")
    print(f"    Within ±5d of trough:   {at5:.1f}%")
    print(f"    Win Rate (profit > 0):  {wr:.1f}%")
    print(f"    Profit Factor:          {pf:.2f}")
    print(f"    Median profit-to-peak:  {pft.median():+.1f}%")
    print(f"    Average profit-to-peak: {pft.mean():+.1f}%")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    banner("MODEL STATISTICAL DEEP-DIVE — Loading Data")
    sigs, zz25, zz50, zz75, bars = load_all()
    print(f"  {len(sigs):,} signals loaded from engine.signal_footprint")
    print(f"  Zigzag: 2.5%={len(zz25):,}  5%={len(zz50):,}  7.5%={len(zz75):,}")

    print("\n  Enriching with zigzag ground truth...")
    df = enrich_with_zigzag(sigs, zz25, zz50, zz75, bars)
    print(f"  Enriched: {len(df):,} signals with trough proximity + profit")

    accum = df[df['action'] == 'ACCUMULATE']
    print(f"  ACCUMULATE: {len(accum):,}")
    print(f"  TRIM:       {len(df[df['action'] == 'TRIM']):,}")
    print(f"  HOLD:       {len(df[df['action'] == 'HOLD']):,}")

    table8_model_summary(df)
    table1_probability_states(df)
    table2_state_keys(df)
    table3_observer_stats(df)
    table4_combined_model(df)
    table5_temporal(df)
    table6_per_ticker(df)
    table7_hierarchical_levels(df)

    banner("AUDIT COMPLETE")


if __name__ == "__main__":
    main()
