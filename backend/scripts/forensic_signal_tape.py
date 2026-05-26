#!/usr/bin/env python3
"""
Forensic Signal Tape Analysis — Fase 3
=========================================
Exhaustive analysis of the 93,776-row signal tape:

  3A: Signal Quality (WR, FPR, FNR per head × ticker × regime)
  3B: Phase Offset (temporal precision, early/late per ticker)
  3C: Per-Ticker Threshold Calibration (optimal P for each head × ticker)
  3D: Precursor Discovery (bar-over-bar deltas before signals)
  3E: Danger Map (constellations preceding worst drawdowns)
  3F: Dual Signal (short_entry as long_exit proxy)
  3G: Adaptive vs Fixed Barriers

Output: Comprehensive forensic report to stdout.
"""
import os, sys, warnings, time
from pathlib import Path

warnings.filterwarnings("ignore")
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

HEADS = [
    'long_entry', 'swing_exit', 'pullback_depth', 'trend_reversal',
    'short_entry', 'short_cover', 'bounce_height', 'trend_recovery',
]
HEAD_COLS = [f'p_{h}' for h in HEADS]

# Head → (fwd_col, direction, threshold, context_filter_desc)
# CRITICAL: Each head is evaluated with ITS OWN label, matching the
# unified_pretrainer_v2.py training configuration exactly.
# Forensic finding: measuring all heads with "fwd_return < 0" was WRONG.
HEAD_EVAL = {
    # LONG-side
    'long_entry':     ('fwd_return_20d',    'positive',    0.80, None),
    'swing_exit':     ('fwd_max_dd_10d',    'below_-2pct', 0.80, 'BULL_sigma_pos'),
    'pullback_depth': ('fwd_max_dd_5d',     'below_-2pct', 0.80, None),
    'trend_reversal': ('fwd_return_20d',    'negative',    0.80, None),
    # SHORT-side
    'short_entry':    ('fwd_return_20d',    'negative',    0.50, 'BEAR_FLAT'),
    'short_cover':    ('fwd_max_runup_10d', 'above_2pct',  0.75, 'BEAR_sigma_neg'),
    'bounce_height':  ('fwd_max_runup_5d',  'above_2pct',  0.80, None),
    'trend_recovery': ('fwd_return_20d',    'positive',    0.80, None),
}


def apply_context_filter(df, context):
    """Apply the training context filter so we measure only where the head trained."""
    if context is None:
        return df
    elif context == 'BULL_sigma_pos':
        return df[(df['regime'] == 'BULL') & (df['sigma_tide'] > 0)]
    elif context == 'BEAR_FLAT':
        return df[df['regime'].isin(['BEAR', 'FLAT'])]
    elif context == 'BEAR_sigma_neg':
        return df[(df['regime'] == 'BEAR') & (df['sigma_tide'] < 0)]
    return df


def load_tape(store):
    """Load full signal tape."""
    q = "SELECT * FROM engine.signal_tape ORDER BY ticker, timestamp"
    df = pd.read_sql(q, store.engine, parse_dates=['timestamp'])
    return df


def evaluate_signal(row, head):
    """Check if a head's prediction was correct given the forward data."""
    fwd_col, direction, _, _ = HEAD_EVAL[head]
    fwd = row.get(fwd_col)
    if fwd is None or pd.isna(fwd):
        return None

    if direction == 'positive':
        return fwd > 0
    elif direction == 'negative':
        return fwd < 0
    elif direction == 'below_-2pct':
        return fwd < -0.02
    elif direction == 'above_2pct':
        return fwd > 0.02
    return None


# ═══════════════════════════════════════════════════════════════════════
#  3A: SIGNAL QUALITY
# ═══════════════════════════════════════════════════════════════════════
def analysis_3a(df):
    print("\n" + "═" * 90)
    print("  3A: SIGNAL QUALITY — Win Rate, False Positive Rate, False Negative Rate")
    print("═" * 90)

    # Per head: overall stats
    print("\n  ── Overall per Head ──")
    print(f"  {'Head':20s} │ {'Thr':>5s} │ {'N>Thr':>7s} │ {'WR%':>6s} │ {'FPR%':>6s} │ {'FNR%':>6s} │ {'Edge':>7s}")
    print(f"  {'─'*20}─┼─{'─'*5}─┼─{'─'*7}─┼─{'─'*6}─┼─{'─'*6}─┼─{'─'*6}─┼─{'─'*7}")

    head_results = {}
    for head in HEADS:
        pcol = f'p_{head}'
        fwd_col, direction, threshold, context = HEAD_EVAL[head]

        # Apply context filter: measure each head IN ITS TRAINING CONTEXT
        contextual = apply_context_filter(df, context)
        mask_valid = contextual[fwd_col].notna()
        valid = contextual[mask_valid].copy()

        ctx_label = f" (context: {context})" if context else " (all data)"

        # Evaluate correctness for each row
        correct = valid.apply(lambda r: evaluate_signal(r, head), axis=1)
        base_rate = correct.mean() * 100

        # Signal triggered (P > threshold)
        triggered = valid[pcol] >= threshold
        n_triggered = triggered.sum()

        if n_triggered > 0:
            wr = correct[triggered].mean() * 100
            fpr = (1 - correct[triggered].mean()) * 100 if n_triggered > 0 else 0
        else:
            wr = 0
            fpr = 0

        # False negatives: event happened but P < threshold
        not_triggered = ~triggered
        events_missed = correct[not_triggered].sum()
        total_events = correct.sum()
        fnr = (events_missed / total_events * 100) if total_events > 0 else 0

        edge = wr - base_rate

        print(f"  {head:20s} │ {threshold:5.2f} │ {n_triggered:>7,} │ {wr:5.1f}% │ {fpr:5.1f}% │ {fnr:5.1f}% │ {edge:+6.1f}%{ctx_label}")

        head_results[head] = {
            'wr': wr, 'fpr': fpr, 'fnr': fnr, 'edge': edge,
            'n_triggered': n_triggered, 'base_rate': base_rate,
        }

    # Per head × regime
    print("\n  ── Per Head × Regime ──")
    for head in HEADS:
        pcol = f'p_{head}'
        fwd_col, direction, threshold, context = HEAD_EVAL[head]
        print(f"\n    {head}:")
        for regime in ['BULL', 'FLAT', 'BEAR']:
            sub = df[(df['regime'] == regime) & df[fwd_col].notna()].copy()
            if len(sub) < 50:
                continue
            correct = sub.apply(lambda r: evaluate_signal(r, head), axis=1)
            triggered = sub[pcol] >= threshold
            n_trig = triggered.sum()
            if n_trig > 5:
                wr = correct[triggered].mean() * 100
                base = correct.mean() * 100
                print(f"      {regime:6s}: N={n_trig:>5,}  WR={wr:5.1f}%  base={base:5.1f}%  edge={wr-base:+5.1f}%")
            else:
                print(f"      {regime:6s}: N={n_trig:>5,}  (insufficient)")

    return head_results


# ═══════════════════════════════════════════════════════════════════════
#  3B: PHASE OFFSET
# ═══════════════════════════════════════════════════════════════════════
def analysis_3b(df):
    print("\n" + "═" * 90)
    print("  3B: PHASE OFFSET — Temporal Precision per Ticker")
    print("═" * 90)

    # For long signals: bars_to_local_min_10d tells "how far from the bottom"
    # For short signals: bars_to_local_max_10d tells "how far from the top"
    long_heads = ['long_entry', 'pullback_depth', 'bounce_height', 'trend_recovery']
    short_heads = ['swing_exit', 'trend_reversal', 'short_entry', 'short_cover']

    print("\n  ── LONG signals: bars to local MIN (lower = better timing) ──")
    print(f"  {'Ticker':>6s} │ ", end="")
    for h in long_heads:
        print(f" {h:>14s} │", end="")
    print()

    tickers = sorted(df['ticker'].unique())
    for ticker in tickers:
        sub = df[df['ticker'] == ticker]
        print(f"  {ticker:>6s} │ ", end="")
        for head in long_heads:
            pcol = f'p_{head}'
            _, _, threshold, _ = HEAD_EVAL[head]
            triggered = sub[sub[pcol] >= threshold]
            if len(triggered) >= 5:
                mean_bars = triggered['bars_to_local_min_10d'].dropna().mean()
                print(f" {mean_bars:>13.1f}d │", end="")
            else:
                print(f" {'n/a':>13s} │", end="")
        print()

    print("\n  ── SHORT signals: bars to local MAX (lower = better timing) ──")
    print(f"  {'Ticker':>6s} │ ", end="")
    for h in short_heads:
        print(f" {h:>14s} │", end="")
    print()

    for ticker in tickers:
        sub = df[df['ticker'] == ticker]
        print(f"  {ticker:>6s} │ ", end="")
        for head in short_heads:
            pcol = f'p_{head}'
            _, _, threshold, _ = HEAD_EVAL[head]
            triggered = sub[sub[pcol] >= threshold]
            if len(triggered) >= 5:
                mean_bars = triggered['bars_to_local_max_10d'].dropna().mean()
                print(f" {mean_bars:>13.1f}d │", end="")
            else:
                print(f" {'n/a':>13s} │", end="")
        print()


# ═══════════════════════════════════════════════════════════════════════
#  3C: PER-TICKER THRESHOLD CALIBRATION
# ═══════════════════════════════════════════════════════════════════════
def analysis_3c(df):
    print("\n" + "═" * 90)
    print("  3C: PER-TICKER THRESHOLD CALIBRATION")
    print("═" * 90)

    tickers = sorted(df['ticker'].unique())
    thresholds_to_try = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]

    for head in HEADS:
        pcol = f'p_{head}'
        fwd_col, _, current_thr, context = HEAD_EVAL[head]

        print(f"\n  ── {head} (current thr={current_thr}) ──")
        print(f"  {'Ticker':>6s} │ {'Optimal':>7s} │ {'N':>6s} │ {'WR%':>6s} │ {'Edge':>7s} │ {'vs Current':>10s}")
        print(f"  {'─'*6}─┼─{'─'*7}─┼─{'─'*6}─┼─{'─'*6}─┼─{'─'*7}─┼─{'─'*10}")

        for ticker in tickers:
            ticker_df = apply_context_filter(df[df['ticker'] == ticker], context)
            sub = ticker_df[ticker_df[fwd_col].notna()].copy()
            correct = sub.apply(lambda r: evaluate_signal(r, head), axis=1)
            base = correct.mean() * 100

            best_thr, best_wr, best_n, best_edge = current_thr, 0, 0, 0
            current_wr = 0

            for thr in thresholds_to_try:
                trig = sub[pcol] >= thr
                n = trig.sum()
                if n < 10:
                    continue
                wr = correct[trig].mean() * 100
                edge = wr - base
                if thr == current_thr:
                    current_wr = wr
                if edge > best_edge and n >= 10:
                    best_thr, best_wr, best_n, best_edge = thr, wr, n, edge

            improvement = best_wr - current_wr if current_wr > 0 else 0
            marker = "★" if improvement > 5 else ""
            print(f"  {ticker:>6s} │ {best_thr:>7.2f} │ {best_n:>6,} │ {best_wr:5.1f}% │ {best_edge:+6.1f}% │ {improvement:+9.1f}% {marker}")


# ═══════════════════════════════════════════════════════════════════════
#  3D: PRECURSOR DISCOVERY
# ═══════════════════════════════════════════════════════════════════════
def analysis_3d(df):
    print("\n" + "═" * 90)
    print("  3D: PRECURSOR DISCOVERY — What moves BEFORE signals fire?")
    print("═" * 90)

    delta_cols = [c for c in df.columns if c.startswith('d_')]
    if not delta_cols:
        print("  ⚠️ No delta columns found in tape")
        return

    for head in HEADS:
        pcol = f'p_{head}'
        _, _, threshold, _ = HEAD_EVAL[head]

        # Find bars where signal crosses threshold
        triggered = df[pcol] >= threshold
        crosses = triggered & (~triggered.shift(1, fill_value=False))

        # Look 1-5 bars BEFORE each cross
        n_crosses = crosses.sum()
        if n_crosses < 20:
            print(f"\n  {head}: only {n_crosses} crosses, skipping")
            continue

        print(f"\n  ── {head} ({n_crosses} threshold crosses) ──")
        print(f"  {'Delta':>25s} │ {'Pre-Cross μ':>12s} │ {'Normal μ':>10s} │ {'t-stat':>8s} │ {'p-val':>8s} │ Sig")
        print(f"  {'─'*25}─┼─{'─'*12}─┼─{'─'*10}─┼─{'─'*8}─┼─{'─'*8}─┼─{'─'*4}")

        cross_indices = df.index[crosses].tolist()

        for dcol in delta_cols:
            # Values 1-3 bars before crosses
            pre_vals = []
            for ci in cross_indices:
                pos = df.index.get_loc(ci)
                for lag in range(1, 4):
                    if pos - lag >= 0:
                        v = df.iloc[pos - lag][dcol]
                        if pd.notna(v):
                            pre_vals.append(float(v))

            if len(pre_vals) < 20:
                continue

            # Compare to normal distribution
            normal_vals = df[~crosses][dcol].dropna().values.astype(float)
            if len(normal_vals) < 100:
                continue

            t_stat, p_val = sp_stats.ttest_ind(pre_vals, normal_vals, equal_var=False)
            sig = "★★★" if p_val < 0.001 else "★★" if p_val < 0.01 else "★" if p_val < 0.05 else ""

            if abs(t_stat) > 1.5:  # Only show meaningful
                print(f"  {dcol:>25s} │ {np.mean(pre_vals):>+12.6f} │ {np.mean(normal_vals):>+10.6f} │ {t_stat:>+8.2f} │ {p_val:>8.4f} │ {sig}")


# ═══════════════════════════════════════════════════════════════════════
#  3E: DANGER MAP
# ═══════════════════════════════════════════════════════════════════════
def analysis_3e(df):
    print("\n" + "═" * 90)
    print("  3E: DANGER MAP — Signal Constellations Before Worst Drawdowns")
    print("═" * 90)

    valid = df[df['fwd_max_dd_10d'].notna()].copy()

    # Define "dangerous" as fwd_max_dd_10d < -5%
    valid['dangerous'] = valid['fwd_max_dd_10d'] < -0.05
    n_dangerous = valid['dangerous'].sum()
    print(f"\n  Dangerous events (DD > 5% in 10d): {n_dangerous:,} ({n_dangerous/len(valid)*100:.1f}%)")

    # Signal profile at dangerous vs normal bars
    print(f"\n  ── Average Signal Profile: Dangerous vs Normal ──")
    print(f"  {'Feature':>25s} │ {'Dangerous μ':>12s} │ {'Normal μ':>10s} │ {'Diff':>8s} │ {'t-stat':>8s}")
    print(f"  {'─'*25}─┼─{'─'*12}─┼─{'─'*10}─┼─{'─'*8}─┼─{'─'*8}")

    features = HEAD_COLS + ['sigma_tide', 'rsi_value', 'kalman_velocity', 'fear_level',
                            'compression_ratio', 'vol_up_down_ratio', 'tide_slope']

    for feat in features:
        dang = valid[valid['dangerous']][feat].dropna()
        norm = valid[~valid['dangerous']][feat].dropna()
        if len(dang) < 20 or len(norm) < 100:
            continue
        t_stat, _ = sp_stats.ttest_ind(dang, norm, equal_var=False)
        diff = dang.mean() - norm.mean()
        if abs(t_stat) > 2:
            print(f"  {feat:>25s} │ {dang.mean():>+12.4f} │ {norm.mean():>+10.4f} │ {diff:>+8.4f} │ {t_stat:>+8.2f}")

    # Constellation analysis: combinations that predict danger
    print(f"\n  ── High-Risk Constellations ──")
    constellations = [
        ("RSI<30 + fear≥4", lambda d: (d['rsi_value'] < 30) & (d['fear_level'] >= 4)),
        ("RSI<30 + KV<0", lambda d: (d['rsi_value'] < 30) & (d['kalman_velocity'] < 0)),
        ("σ_tide<-2 + fear≥4", lambda d: (d['sigma_tide'] < -2) & (d['fear_level'] >= 4)),
        ("P(short)>0.6 + P(long)<0.5", lambda d: (d['p_short_entry'] > 0.6) & (d['p_long_entry'] < 0.5)),
        ("P(reversal)>0.5 + σ<-1", lambda d: (d['p_trend_reversal'] > 0.5) & (d['sigma_tide'] < -1)),
        ("3+ SHORT heads high", lambda d: ((d['p_short_entry'] > 0.5).astype(int) +
                                            (d['p_swing_exit'] > 0.5).astype(int) +
                                            (d['p_trend_reversal'] > 0.3).astype(int) +
                                            (d['p_pullback_depth'] > 0.5).astype(int)) >= 3),
        ("P(long)>0.7 + P(short)>0.5", lambda d: (d['p_long_entry'] > 0.7) & (d['p_short_entry'] > 0.5)),
        ("Compression<0.3 + KV<0", lambda d: (d['compression_ratio'] < 0.3) & (d['kalman_velocity'] < 0)),
    ]

    print(f"  {'Constellation':>35s} │ {'N':>6s} │ {'DD>5%':>6s} │ {'DangR%':>7s} │ {'BaseR%':>7s} │ {'Lift':>6s}")
    print(f"  {'─'*35}─┼─{'─'*6}─┼─{'─'*6}─┼─{'─'*7}─┼─{'─'*7}─┼─{'─'*6}")

    base_rate = valid['dangerous'].mean() * 100
    for name, mask_fn in constellations:
        try:
            mask = mask_fn(valid)
            n = mask.sum()
            if n < 10:
                continue
            dang_rate = valid[mask]['dangerous'].mean() * 100
            lift = dang_rate / base_rate if base_rate > 0 else 0
            marker = "🔴" if lift > 2 else "🟡" if lift > 1.5 else ""
            print(f"  {name:>35s} │ {n:>6,} │ {valid[mask]['dangerous'].sum():>6,} │ {dang_rate:>6.1f}% │ {base_rate:>6.1f}% │ {lift:>5.1f}x {marker}")
        except Exception:
            continue


# ═══════════════════════════════════════════════════════════════════════
#  3F: DUAL SIGNAL (short_entry as long exit)
# ═══════════════════════════════════════════════════════════════════════
def analysis_3f(df):
    print("\n" + "═" * 90)
    print("  3F: DUAL SIGNAL — P(short_entry) as Long Exit Proxy")
    print("═" * 90)

    valid = df[df['fwd_return_10d'].notna()].copy()

    # Compare: when P(short_entry) is high, do long positions lose?
    print(f"\n  ── Forward 10d Return by P(short_entry) quintile ──")
    valid['se_quintile'] = pd.qcut(valid['p_short_entry'], 5, labels=['Q1(low)', 'Q2', 'Q3', 'Q4', 'Q5(high)'])

    for q in ['Q1(low)', 'Q2', 'Q3', 'Q4', 'Q5(high)']:
        sub = valid[valid['se_quintile'] == q]
        mean_ret = sub['fwd_return_10d'].mean() * 100
        median_ret = sub['fwd_return_10d'].median() * 100
        pct_neg = (sub['fwd_return_10d'] < 0).mean() * 100
        print(f"    {q:>10s}: mean={mean_ret:+.2f}%  median={median_ret:+.2f}%  P(loss)={pct_neg:.1f}%  N={len(sub):,}")

    # Compare swing_exit vs short_entry as exit signals
    print(f"\n  ── Comparison: Which is better at detecting tops? ──")
    for head in ['swing_exit', 'short_entry']:
        pcol = f'p_{head}'
        _, _, threshold, _ = HEAD_EVAL[head]
        trig = valid[valid[pcol] >= threshold]
        if len(trig) > 0:
            mean_fwd = trig['fwd_return_10d'].mean() * 100
            pct_neg = (trig['fwd_return_10d'] < 0).mean() * 100
            mean_dd = trig['fwd_max_dd_10d'].mean() * 100
            print(f"    {head:20s} (P≥{threshold}): N={len(trig):>6,}  fwd_10d={mean_fwd:+.2f}%  P(neg)={pct_neg:.1f}%  avg_DD={mean_dd:+.2f}%")

    # Correlation
    corr = valid['p_short_entry'].corr(valid['fwd_return_10d'])
    print(f"\n    Pearson corr(P_short_entry, fwd_10d): r={corr:+.4f}")
    corr2 = valid['p_swing_exit'].corr(valid['fwd_return_10d'])
    print(f"    Pearson corr(P_swing_exit, fwd_10d):  r={corr2:+.4f}")

    winner = "short_entry" if abs(corr) > abs(corr2) else "swing_exit"
    print(f"    → {winner} has stronger forward-return correlation")


# ═══════════════════════════════════════════════════════════════════════
#  3G: ADAPTIVE vs FIXED BARRIERS
# ═══════════════════════════════════════════════════════════════════════
def analysis_3g(df):
    print("\n" + "═" * 90)
    print("  3G: ADAPTIVE vs FIXED BARRIERS")
    print("═" * 90)

    valid = df[df['fwd_return_10d'].notna() & df['expected_return'].notna()].copy()

    # Regression: expected_return vs actual fwd_return_10d
    corr = valid['expected_return'].corr(valid['fwd_return_10d'])
    print(f"\n  Correlation(expected_return, fwd_return_10d): r={corr:+.4f}")

    # Direction accuracy
    same_dir = ((valid['expected_return'] > 0) & (valid['fwd_return_10d'] > 0)) | \
               ((valid['expected_return'] < 0) & (valid['fwd_return_10d'] < 0))
    dir_acc = same_dir.mean() * 100
    print(f"  Direction accuracy (same sign): {dir_acc:.1f}%")

    # Barrier capture: does adaptive barrier capture more of the move?
    valid['fixed_profit'] = 0.03  # Fixed 3%
    valid['fixed_stop'] = -0.02   # Fixed -2%

    # How often does fwd_max_runup hit the barrier?
    fixed_hit_profit = (valid['fwd_max_runup_10d'] >= 0.03).mean() * 100
    adaptive_hit_profit = (valid['fwd_max_runup_10d'] >= valid['barrier_reg_profit']).mean() * 100

    fixed_hit_stop = (valid['fwd_max_dd_10d'] <= -0.02).mean() * 100
    adaptive_hit_stop = (valid['fwd_max_dd_10d'] <= valid['barrier_reg_stop']).mean() * 100

    print(f"\n  ── Barrier Hit Rates ──")
    print(f"    Fixed profit (3%):    {fixed_hit_profit:.1f}% of bars hit")
    print(f"    Adaptive profit:      {adaptive_hit_profit:.1f}% of bars hit")
    print(f"    Fixed stop (-2%):     {fixed_hit_stop:.1f}% of bars hit")
    print(f"    Adaptive stop:        {adaptive_hit_stop:.1f}% of bars hit")

    # Per ticker
    print(f"\n  ── Direction Accuracy per Ticker ──")
    tickers = sorted(valid['ticker'].unique())
    for ticker in tickers:
        sub = valid[valid['ticker'] == ticker]
        same = ((sub['expected_return'] > 0) & (sub['fwd_return_10d'] > 0)) | \
               ((sub['expected_return'] < 0) & (sub['fwd_return_10d'] < 0))
        acc = same.mean() * 100
        print(f"    {ticker:>6s}: {acc:.1f}%")


# ═══════════════════════════════════════════════════════════════════════
#  3H: AMBIGUOUS SIGNALS (bonus — user requested)
# ═══════════════════════════════════════════════════════════════════════
def analysis_3h(df):
    print("\n" + "═" * 90)
    print("  3H: AMBIGUOUS & CONTRADICTORY SIGNALS")
    print("═" * 90)

    valid = df[df['fwd_return_10d'].notna()].copy()

    # Ambiguous: P(long) and P(short) both above 0.5
    both_high = (valid['p_long_entry'] > 0.55) & (valid['p_short_entry'] > 0.55)
    n_both = both_high.sum()
    if n_both > 0:
        sub = valid[both_high]
        print(f"\n  ── P(long)>0.55 AND P(short)>0.55 simultaneously ──")
        print(f"    N = {n_both:,} bars ({n_both/len(valid)*100:.1f}%)")
        print(f"    Fwd 10d mean: {sub['fwd_return_10d'].mean()*100:+.2f}%")
        print(f"    Fwd 10d std:  {sub['fwd_return_10d'].std()*100:.2f}%")
        print(f"    P(positive):  {(sub['fwd_return_10d'] > 0).mean()*100:.1f}%")
        print(f"    Max DD avg:   {sub['fwd_max_dd_10d'].mean()*100:+.2f}%")
        print(f"    Max Runup avg:{sub['fwd_max_runup_10d'].mean()*100:+.2f}%")
        print(f"    → {'DANGEROUS' if sub['fwd_max_dd_10d'].mean() < -0.03 else 'NOISY' if abs(sub['fwd_return_10d'].mean()) < 0.005 else 'DIRECTIONAL'}")

    # Dead zone: all heads near 0.5
    all_near_50 = True
    for h in HEAD_COLS:
        all_near_50 = all_near_50 & (valid[h] > 0.4) & (valid[h] < 0.6)
    n_dead = all_near_50.sum()
    if n_dead > 0:
        sub = valid[all_near_50]
        print(f"\n  ── Dead Zone: ALL 8 heads in [0.4, 0.6] ──")
        print(f"    N = {n_dead:,} bars ({n_dead/len(valid)*100:.1f}%)")
        print(f"    Fwd 10d mean:  {sub['fwd_return_10d'].mean()*100:+.2f}%")
        print(f"    Fwd 10d abs:   {sub['fwd_return_10d'].abs().mean()*100:.2f}%")
        print(f"    Max DD avg:    {sub['fwd_max_dd_10d'].mean()*100:+.2f}%")
        print(f"    → Market often moves ±{sub['fwd_return_10d'].abs().mean()*100:.1f}% even from dead zone")

    # Contradictory by ticker
    print(f"\n  ── Contradictory signals per ticker ──")
    tickers = sorted(valid['ticker'].unique())
    for ticker in tickers:
        sub = valid[(valid['ticker'] == ticker) & both_high]
        if len(sub) > 5:
            fwd = sub['fwd_return_10d'].mean() * 100
            print(f"    {ticker:>6s}: N={len(sub):>5,}  fwd_10d={fwd:+.2f}%")


def main():
    print("=" * 90)
    print("  FORENSIC SIGNAL TAPE ANALYSIS — FASE 3")
    print("  93,776 rows × 50 columns × 7 analyses")
    print("=" * 90)

    t0 = time.time()
    store = TimescaleDataStore()
    df = load_tape(store)
    print(f"  Loaded: {len(df):,} rows, {df['ticker'].nunique()} tickers")

    head_results = analysis_3a(df)
    analysis_3b(df)
    analysis_3c(df)
    analysis_3d(df)
    analysis_3e(df)
    analysis_3f(df)
    analysis_3g(df)
    analysis_3h(df)

    elapsed = time.time() - t0
    print(f"\n{'=' * 90}")
    print(f"  FORENSIC ANALYSIS COMPLETE: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"{'=' * 90}")

    store.close()


if __name__ == "__main__":
    main()
