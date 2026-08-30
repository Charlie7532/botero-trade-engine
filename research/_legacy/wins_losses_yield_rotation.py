#!/usr/bin/env python3
"""
WINS vs LOSSES — YIELD (EXIT) + ROTATION, DXY, PCR (NEUTRAL)
================================================================
7 dimensiones por estación. state_key del METAR (D1×D2×D3).
NO promediar. CI95 bootstrap 2000. D3 = std(2)/std(10).
"""

import sys, os, json
from collections import defaultdict, Counter
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 300)
from datetime import datetime

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.yield_curve_lookup import yield_curve_lookup
from backend.modules.entry_decision.domain.rules.rotation_lookup import rotation_lookup
from backend.modules.entry_decision.domain.rules.dxy_lookup import dxy_lookup
from backend.modules.entry_decision.domain.rules.pcr_lookup import pcr_lookup

# ── Bootstrap utility ──────────────────────────────────────────────
def bootstrap_ci95(data, stat_fn, n_boot=2000, seed=42):
    """CI95 via bootstrap percentil (no paramétrico)."""
    rng = np.random.RandomState(seed)
    vals = np.asarray(data)
    stats = np.empty(n_boot)
    for i in range(n_boot):
        sample = rng.choice(vals, size=len(vals), replace=True)
        stats[i] = stat_fn(sample)
    lo = np.percentile(stats, 2.5)
    hi = np.percentile(stats, 97.5)
    return lo, hi

def bootstrap_ci95_binary(events, n_boot=2000, seed=42):
    """CI95 for a win rate (binary events)."""
    rng = np.random.RandomState(seed)
    events = np.asarray(events, dtype=float)
    n = len(events)
    rates = np.empty(n_boot)
    for i in range(n_boot):
        sample = rng.choice(events, size=n, replace=True)
        rates[i] = sample.mean()
    return np.percentile(rates, 2.5), np.percentile(rates, 97.5)

def streak_analysis(events):
    """Analyze streaks of wins (1) and losses (0)."""
    events = np.asarray(events)
    streaks = []
    current_len = 0
    current_val = None
    for e in events:
        if e == current_val:
            current_len += 1
        else:
            if current_len > 0:
                streaks.append((current_val, current_len))
            current_val = e
            current_len = 1
    if current_len > 0:
        streaks.append((current_val, current_len))

    win_streaks = [s[1] for s in streaks if s[0] == 1]
    loss_streaks = [s[1] for s in streaks if s[0] == 0]
    return {
        'max_win_streak': max(win_streaks) if win_streaks else 0,
        'max_loss_streak': max(loss_streaks) if loss_streaks else 0,
        'mean_win_streak': np.mean(win_streaks) if win_streaks else 0,
        'mean_loss_streak': np.mean(loss_streaks) if loss_streaks else 0,
        'n_win_streaks': len(win_streaks),
        'n_loss_streaks': len(loss_streaks),
    }


# ── Data loading ───────────────────────────────────────────────────
def load_full_history(store, ticker_list):
    """Load OHLCV bars for a list of tickers, return aligned DataFrame."""
    dfs = {}
    for t in ticker_list:
        df = store.load_bars(t, "1d")
        if df is not None and len(df) > 0:
            dfs[t] = df["close"].copy()
    if not dfs:
        return None, None
    common_idx = None
    for t, s in dfs.items():
        s.index = pd.to_datetime(s.index)
        if common_idx is None:
            common_idx = set(s.index)
        else:
            common_idx &= set(s.index)
    common_idx = sorted(common_idx)
    if len(common_idx) < 20:
        return None, None
    frame = pd.DataFrame(index=common_idx)
    for t, s in dfs.items():
        frame[t] = s.loc[common_idx]
    return frame, common_idx


def load_spy_zigzags(store):
    """Load SPY zigzag legs pivot dates (zz25, zz50, zz75)."""
    conn = store._conn()
    cur = conn.cursor()
    zz = {}
    for scale in ['zz25', 'zz50', 'zz75']:
        cur.execute("""
            SELECT start_timestamp::date as d, end_timestamp::date as e,
                   start_type, end_type,
                   CASE WHEN start_type='MIN' THEN (end_price - start_price) / start_price * 100
                        ELSE (start_price - end_price) / start_price * 100
                   END as ret_pct_abs
            FROM market.zigzag_legs
            WHERE ticker = 'SPY' AND scale = %s AND status = 'CONFIRMED'
            ORDER BY start_timestamp
        """, [scale])
        rows = cur.fetchall()
        zz[scale] = [{'start': r[0], 'end': r[1],
                       'start_type': r[2], 'end_type': r[3],
                       'ret_pct_abs': float(r[4]) if r[4] is not None else 0} for r in rows]
    cur.close()
    conn.close()
    return zz


# ── 7-dimension analysis per state ─────────────────────────────────
def analyze_signal(name, signal_mask, spy_returns, spy_prices, dates,
                   forward_horizons=[1, 3, 5, 10, 20],
                   zigzag_data=None):
    """
    signal_mask: boolean array aligned with spy_returns.
    Returns 7-dimension report.
    """
    results = {}
    mask = np.asarray(signal_mask, dtype=bool)
    spy_rets = np.asarray(spy_returns)
    spy_px = np.asarray(spy_prices)

    # Collect signal events
    event_indices = np.where(mask)[0]
    n_signals = len(event_indices)
    if n_signals == 0:
        return {'error': f'No signals found for {name}', 'n_signals': 0}

    results['n_signals'] = n_signals
    results['n_total_bars'] = len(spy_rets)
    results['pct_signals'] = n_signals / len(spy_rets) * 100

    # ── A. Win rate per horizon + CI95 ──
    win_rates = {}
    ci95_win = {}
    for h in forward_horizons:
        returns_h = []
        for idx in event_indices:
            if idx + h < len(spy_rets):
                ret = spy_rets[idx:idx+h].sum()
                returns_h.append(ret)
            else:
                returns_h.append(np.nan)
        returns_h = np.array(returns_h)
        valid = ~np.isnan(returns_h)
        wins = returns_h[valid] > 0
        wr = wins.mean() if len(wins) > 0 else np.nan
        win_rates[h] = wr
        if len(wins) > 0:
            ci95_win[h] = bootstrap_ci95_binary(wins)
        else:
            ci95_win[h] = (np.nan, np.nan)
    results['win_rate'] = win_rates
    results['ci95_win_rate'] = ci95_win

    # ── B. Distribution of returns ──
    dists = {}
    for h in forward_horizons:
        returns_h = []
        for idx in event_indices:
            if idx + h < len(spy_rets):
                ret = spy_rets[idx:idx+h].sum() * 100  # pct
                returns_h.append(ret)
        returns_h = np.array(returns_h)
        valid = returns_h[~np.isnan(returns_h)]
        dists[h] = {
            'mean': np.mean(valid) if len(valid) > 0 else np.nan,
            'median': np.median(valid) if len(valid) > 0 else np.nan,
            'std': np.std(valid) if len(valid) > 0 else np.nan,
            'min': np.min(valid) if len(valid) > 0 else np.nan,
            'max': np.max(valid) if len(valid) > 0 else np.nan,
            'p5': np.percentile(valid, 5) if len(valid) > 0 else np.nan,
            'p25': np.percentile(valid, 25) if len(valid) > 0 else np.nan,
            'p75': np.percentile(valid, 75) if len(valid) > 0 else np.nan,
            'p95': np.percentile(valid, 95) if len(valid) > 0 else np.nan,
            'skew': float(pd.Series(valid).skew()) if len(valid) >= 3 else np.nan,
        }
        # CI95 for mean
        if len(valid) >= 10:
            lo, hi = bootstrap_ci95(valid, np.mean)
            dists[h]['ci95_mean'] = (lo, hi)
        else:
            dists[h]['ci95_mean'] = (np.nan, np.nan)
    results['distributions'] = dists

    # ── C. Profit factor + Kelly ──
    pf_data = {}
    for h in forward_horizons:
        returns_h = []
        for idx in event_indices:
            if idx + h < len(spy_rets):
                returns_h.append(spy_rets[idx:idx+h].sum() * 100)
        returns_h = np.array(returns_h)
        valid = returns_h[~np.isnan(returns_h)]
        wins_arr = valid[valid > 0]
        losses_arr = valid[valid < 0]
        total_gain = wins_arr.sum() if len(wins_arr) > 0 else 0.0
        total_loss = abs(losses_arr.sum()) if len(losses_arr) > 0 else 1e-10
        pf = total_gain / total_loss if total_loss > 0 else np.inf
        p_win = len(wins_arr) / len(valid) if len(valid) > 0 else 0.0
        p_loss = 1 - p_win
        avg_win = wins_arr.mean() if len(wins_arr) > 0 else 0.0
        avg_loss = abs(losses_arr.mean()) if len(losses_arr) > 0 else 0.0
        # Kelly fraction: f* = p - q/(W/L)  where W/L = avg_win/avg_loss
        wl_ratio = avg_win / avg_loss if avg_loss > 0 else np.inf
        kelly = p_win - p_loss / wl_ratio if wl_ratio > 0 else -1.0
        kelly = max(kelly, -1.0)
        pf_data[h] = {
            'profit_factor': pf,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'wl_ratio': wl_ratio,
            'kelly': kelly,
            'n_trades': len(valid),
        }
    results['profit'] = pf_data

    # ── D. Rachas (streaks) ──
    # Use 5d horizon for streak analysis
    h_streak = 5
    streak_rets = []
    for idx in event_indices:
        if idx + h_streak < len(spy_rets):
            streak_rets.append(1 if spy_rets[idx:idx+h_streak].sum() > 0 else 0)
    if len(streak_rets) >= 2:
        results['streaks'] = streak_analysis(streak_rets)
    else:
        results['streaks'] = {'error': 'insufficient events'}

    # ── E. Timing vs zigzag ──
    if zigzag_data and 'zz25' in zigzag_data:
        zz25_pivots = zigzag_data['zz25']
        pivot_dates_set = set(str(z['start']).split(' ')[0] for z in zz25_pivots)
        # How many signals hit at/near a pivot?
        signal_dates = [str(dates[i]).split(' ')[0] for i in event_indices]
        hits = sum(1 for d in signal_dates if d in pivot_dates_set)
        # For those not at pivot, find distance to nearest pivot
        timing_data = {
            'n_signals': n_signals,
            'n_at_pivot': hits,
            'pct_at_pivot': hits / n_signals * 100 if n_signals > 0 else 0,
        }
        results['timing'] = timing_data

        # compute per-horizon conditional on at-pivot vs not
        at_pivot_mask = np.array([(str(dates[i]).split(' ')[0] in pivot_dates_set) for i in event_indices])
        timing_returns = {}
        for h in [5, 10, 20]:
            rets_at = []
            rets_not = []
            for i, idx in enumerate(event_indices):
                if idx + h < len(spy_rets):
                    r = spy_rets[idx:idx+h].sum() * 100
                    if at_pivot_mask[i]:
                        rets_at.append(r)
                    else:
                        rets_not.append(r)
            timing_returns[f'h{h}_at_pivot'] = {
                'mean': np.mean(rets_at) if rets_at else np.nan,
                'n': len(rets_at),
            }
            timing_returns[f'h{h}_not_pivot'] = {
                'mean': np.mean(rets_not) if rets_not else np.nan,
                'n': len(rets_not),
            }
        results['timing_returns'] = timing_returns
    else:
        results['timing'] = {'error': 'no zigzag data'}

    # ── F. Cuchillo cayendo ──
    # Measure: the minimum return *within* the forward window (intra-trade drawdown)
    knife_data = {}
    for h in forward_horizons:
        intra_dd = []
        for idx in event_indices:
            if idx + h < len(spy_rets):
                cumulative = np.cumsum(spy_rets[idx:idx+h]) * 100
                intra_dd.append(cumulative.min())
        intra_dd = np.array(intra_dd)
        valid = intra_dd[~np.isnan(intra_dd)]
        knife_data[h] = {
            'mean_intra_dd': np.mean(valid) if len(valid) > 0 else np.nan,
            'max_intra_dd': np.min(valid) if len(valid) > 0 else np.nan,  # most negative
            'p5_intra_dd': np.percentile(valid, 5) if len(valid) > 0 else np.nan,
            'pct_never_positive': (valid <= 0).mean() if len(valid) > 0 else np.nan,
        }
    results['falling_knife'] = knife_data

    # ── G. Neutrality check (for ROTATION/DXY/PCR) ──
    # Neutral if |mean return| < 1.5% and win_rate < 55% at 20d
    neutrality = {}
    for h in [10, 20]:
        rets = []
        for idx in event_indices:
            if idx + h < len(spy_rets):
                rets.append(spy_rets[idx:idx+h].sum() * 100)
        rets = np.array(rets)
        valid = rets[~np.isnan(rets)]
        mean_abs = abs(np.mean(valid)) if len(valid) > 0 else np.nan
        wr = (valid > 0).mean() if len(valid) > 0 else np.nan
        # CI95 for mean
        ci95_m = (np.nan, np.nan)
        if len(valid) >= 10:
            ci95_m = bootstrap_ci95(valid, np.mean)
        neutrality[h] = {
            'mean_return': np.mean(valid) if len(valid) > 0 else np.nan,
            'abs_mean': mean_abs,
            'ci95_mean': ci95_m,
            'win_rate': wr,
            'n': len(valid),
            'is_neutral_abs': mean_abs < 1.5,  # |return| < 1.5%
            'is_neutral_wr': wr < 0.55,        # win < 55%
        }
    results['neutrality'] = neutrality

    return results


# ── Station builders ───────────────────────────────────────────────
def classify_all_bars(ind_series, lookup_fn, d1_edges, d2_edges, d3_edges,
                      d1_labels, d2_labels, d3_labels, station_name=''):
    """Classify every bar into D1×D2×D3 using the lookup adapter logic."""
    vals = ind_series.values
    n = len(vals)

    # D2 = Δ3d velocity
    vel = np.empty(n); vel[:] = np.nan
    for i in range(3, n):
        vel[i] = vals[i] - vals[i-3]

    # D3 = std(2)/std(10)
    vol_norm = np.empty(n); vol_norm[:] = 1.0
    for i in range(10, n):
        std2 = np.std(vals[i-1:i+1])
        std10 = np.std(vals[i-9:i+1])
        vol_norm[i] = std2 / std10 if std10 > 0 else 1.0

    d1 = np.array([_classify(v, d1_edges, d1_labels) for v in vals])
    d2 = np.array([_classify(v, d2_edges, d2_labels) if not np.isnan(v) else 'NODATA' for v in vel])
    d3 = np.array([_classify(v, d3_edges, d3_labels) for v in vol_norm])

    state_keys = np.array([f"{d1[i]}__{d2[i]}__{d3[i]}" for i in range(n)])
    return d1, d2, d3, state_keys, vel, vol_norm


def _classify(value, edges, labels):
    for i, e in enumerate(edges):
        if value < e:
            return labels[i]
    return labels[-1]


# ── MAIN ───────────────────────────────────────────────────────────
def main():
    store = TimescaleDataStore()
    print("Loading data...")

    # ── YIELD CURVE (TNX-IRX) ──
    print("\n" + "="*80)
    print("  YIELD CURVE (EXIT: EXTREME_STEEPNING)")
    print("="*80)
    yield_frame, yield_dates = load_full_history(store, ['TNX', 'IRX', 'SPY'])
    if yield_frame is not None:
        yield_frame['spread'] = yield_frame['TNX'] - yield_frame['IRX']
        yield_adapter = yield_curve_lookup

        d1, d2, d3, sk, vel, vol = classify_all_bars(
            yield_frame['spread'],
            None,
            yield_adapter.edges_d1,
            yield_adapter.edges_d2,
            yield_adapter.edges_d3,
            yield_adapter.labels_d1,
            yield_adapter.labels_d2,
            yield_adapter.labels_d3,
            'YIELD'
        )

        # SPY daily returns (forward-looking)
        spy_ret = yield_frame['SPY'].pct_change().shift(-1).values  # next-day return
        spy_px = yield_frame['SPY'].values
        valid_mask = ~np.isnan(spy_ret) & (d2 != 'NODATA')
        valid_idx = np.where(valid_mask)[0]

        print(f"Total bars: {len(yield_frame)}, Valid: {len(valid_idx)}")
        print(f"D1 distribution: {Counter(d1[valid_idx])}")

        # YIELD EXIT signal: EXTREME_STEEPNING (any D2, any D3)
        extreme_mask = np.zeros(len(yield_frame), dtype=bool)
        for i in valid_idx:
            if d1[i] == 'EXTREME_STEEPNING' or d1[i] == 'EXTREME_STEEPNING_UNINVERSION':
                extreme_mask[i] = True
        n_extreme = extreme_mask.sum()
        print(f"EXTREME_STEEPNING signals: {n_extreme}")

        # Analyze
        zigzag_data = load_spy_zigzags(store) if n_extreme > 0 else None
        yield_results = analyze_signal(
            'YIELD_EXTREME_STEEPNING', extreme_mask, spy_ret, spy_px,
            yield_frame.index, zigzag_data=zigzag_data
        )

        # Per-state analysis (no averaging)
        state_results = {}
        unique_states = sorted(set(sk[valid_idx]))
        for state_key in unique_states:
            state_mask = np.zeros(len(yield_frame), dtype=bool)
            for i in valid_idx:
                if sk[i] == state_key:
                    state_mask[i] = True
            if state_mask.sum() >= 5:
                sr = analyze_signal(
                    f'YIELD_{state_key}', state_mask, spy_ret, spy_px,
                    yield_frame.index, zigzag_data=zigzag_data
                )
                state_results[state_key] = sr

        print("\n── YIELD EXTREME_STEEPNING aggregate ──")
        print(json.dumps(yield_results, indent=2, default=str))

        print(f"\nPer-state results: {len(state_results)} states with N≥5")
        for skey, sr in sorted(state_results.items(), key=lambda x: -x[1].get('n_signals',0)):
            wr5 = sr.get('win_rate', {}).get(5, np.nan)
            dist20 = sr.get('distributions', {}).get(20, {})
            print(f"  {skey}: N={sr.get('n_signals')} | WR5={wr5:.2%} | "
                  f"mean20d={dist20.get('mean',np.nan):.2f}% | "
                  f"median20d={dist20.get('median',np.nan):.2f}%")
    else:
        print("No yield data available")

    # ── ROTATION ──
    print("\n" + "="*80)
    print("  ROTATION (NEUTRALITY)")
    print("="*80)
    rot_frame, rot_dates = load_full_history(store, ['XLY', 'XLP', 'XLK', 'XLU', 'SPY'])
    if rot_frame is not None:
        ratio_xly_xlp = rot_frame['XLY'] / rot_frame['XLP']
        ratio_xlk_xlu = rot_frame['XLK'] / rot_frame['XLU']
        z_xly_xlp = (ratio_xly_xlp - ratio_xly_xlp.rolling(252, min_periods=20).mean()) / \
                     ratio_xly_xlp.rolling(252, min_periods=20).std().replace(0, np.nan)
        z_xlk_xlu = (ratio_xlk_xlu - ratio_xlk_xlu.rolling(252, min_periods=20).mean()) / \
                     ratio_xlk_xlu.rolling(252, min_periods=20).std().replace(0, np.nan)
        rot_idx = z_xly_xlp + z_xlk_xlu

        rot_adapter = rotation_lookup
        d1, d2, d3, sk, vel, vol = classify_all_bars(
            rot_idx, None,
            rot_adapter.edges_d1, rot_adapter.edges_d2, rot_adapter.edges_d3,
            rot_adapter.labels_d1, rot_adapter.labels_d2, rot_adapter.labels_d3,
            'ROTATION'
        )

        spy_ret = rot_frame['SPY'].pct_change().shift(-1).values
        spy_px = rot_frame['SPY'].values
        valid_mask = ~np.isnan(spy_ret) & (d2 != 'NODATA')
        valid_idx = np.where(valid_mask)[0]

        print(f"Total bars: {len(rot_frame)}, Valid: {len(valid_idx)}")
        print(f"D1 distribution: {Counter(d1[valid_idx])}")

        # Analyze ALL rotation signals (any D1) to test neutrality
        zigzag_data = load_spy_zigzags(store)
        # Full aggregate
        all_mask = np.zeros(len(rot_frame), dtype=bool)
        all_mask[valid_idx] = True
        rot_results = analyze_signal(
            'ROTATION_ALL', all_mask, spy_ret, spy_px,
            rot_frame.index, zigzag_data=zigzag_data
        )

        # Per D1 state
        rot_state_results = {}
        for d1_label in set(d1[valid_idx]):
            state_mask = np.zeros(len(rot_frame), dtype=bool)
            for i in valid_idx:
                if d1[i] == d1_label:
                    state_mask[i] = True
            if state_mask.sum() >= 5:
                sr = analyze_signal(
                    f'ROT_{d1_label}', state_mask, spy_ret, spy_px,
                    rot_frame.index, zigzag_data=zigzag_data
                )
                rot_state_results[d1_label] = sr

        print("\n── ROTATION neutrality check ──")
        for h in [10, 20]:
            n = rot_results.get('neutrality', {}).get(h, {})
            print(f"  H{h}d: mean={n.get('mean_return',np.nan):.3f}% | "
                  f"WR={n.get('win_rate',np.nan):.2%} | "
                  f"|mean|<1.5% → {n.get('is_neutral_abs', '?')} | "
                  f"WR<55% → {n.get('is_neutral_wr', '?')}")

        print(f"\nPer-D1 neutrality:")
        for d1l, sr in sorted(rot_state_results.items(), key=lambda x: -x[1].get('n_signals',0)):
            n20 = sr.get('neutrality', {}).get(20, {})
            print(f"  {d1l}: N={sr.get('n_signals')} | mean20d={n20.get('mean_return',np.nan):.2f}% | "
                  f"WR20={n20.get('win_rate',np.nan):.2%} | "
                  f"neutral_abs={n20.get('is_neutral_abs','?')} | neutral_wr={n20.get('is_neutral_wr','?')}")
    else:
        print("No rotation data available")

    # ── DXY ──
    print("\n" + "="*80)
    print("  DXY (NEUTRALITY)")
    print("="*80)
    dxy_frame, dxy_dates = load_full_history(store, ['DXY', 'SPY'])
    if dxy_frame is not None:
        dxy_adapter = dxy_lookup
        d1, d2, d3, sk, vel, vol = classify_all_bars(
            dxy_frame['DXY'], None,
            dxy_adapter.edges_d1, dxy_adapter.edges_d2, dxy_adapter.edges_d3,
            dxy_adapter.labels_d1, dxy_adapter.labels_d2, dxy_adapter.labels_d3,
            'DXY'
        )

        spy_ret = dxy_frame['SPY'].pct_change().shift(-1).values
        spy_px = dxy_frame['SPY'].values
        valid_mask = ~np.isnan(spy_ret) & (d2 != 'NODATA')
        valid_idx = np.where(valid_mask)[0]

        print(f"Total bars: {len(dxy_frame)}, Valid: {len(valid_idx)}")
        print(f"D1 distribution: {Counter(d1[valid_idx])}")

        zigzag_data = load_spy_zigzags(store)
        all_mask = np.zeros(len(dxy_frame), dtype=bool)
        all_mask[valid_idx] = True
        dxy_results = analyze_signal(
            'DXY_ALL', all_mask, spy_ret, spy_px,
            dxy_frame.index, zigzag_data=zigzag_data
        )

        dxy_state_results = {}
        for d1_label in set(d1[valid_idx]):
            state_mask = np.zeros(len(dxy_frame), dtype=bool)
            for i in valid_idx:
                if d1[i] == d1_label:
                    state_mask[i] = True
            if state_mask.sum() >= 5:
                sr = analyze_signal(
                    f'DXY_{d1_label}', state_mask, spy_ret, spy_px,
                    dxy_frame.index, zigzag_data=zigzag_data
                )
                dxy_state_results[d1_label] = sr

        print("\n── DXY neutrality check ──")
        for h in [10, 20]:
            n = dxy_results.get('neutrality', {}).get(h, {})
            print(f"  H{h}d: mean={n.get('mean_return',np.nan):.3f}% | "
                  f"WR={n.get('win_rate',np.nan):.2%} | "
                  f"|mean|<1.5% → {n.get('is_neutral_abs', '?')} | "
                  f"WR<55% → {n.get('is_neutral_wr', '?')}")

        print(f"\nPer-D1 neutrality:")
        for d1l, sr in sorted(dxy_state_results.items(), key=lambda x: -x[1].get('n_signals',0)):
            n20 = sr.get('neutrality', {}).get(20, {})
            print(f"  {d1l}: N={sr.get('n_signals')} | mean20d={n20.get('mean_return',np.nan):.2f}% | "
                  f"WR20={n20.get('win_rate',np.nan):.2%} | "
                  f"neutral_abs={n20.get('is_neutral_abs','?')} | neutral_wr={n20.get('is_neutral_wr','?')}")
    else:
        print("No DXY data available")

    # ── PCR ──
    print("\n" + "="*80)
    print("  PCR (NEUTRALITY)")
    print("="*80)
    pcr_frame, pcr_dates = load_full_history(store, ['CBOE_PCR', 'SPY'])
    if pcr_frame is not None:
        pcr_adapter = pcr_lookup
        d1, d2, d3, sk, vel, vol = classify_all_bars(
            pcr_frame['CBOE_PCR'], None,
            pcr_adapter.edges_d1, pcr_adapter.edges_d2, pcr_adapter.edges_d3,
            pcr_adapter.labels_d1, pcr_adapter.labels_d2, pcr_adapter.labels_d3,
            'PCR'
        )

        spy_ret = pcr_frame['SPY'].pct_change().shift(-1).values
        spy_px = pcr_frame['SPY'].values
        valid_mask = ~np.isnan(spy_ret) & (d2 != 'NODATA')
        valid_idx = np.where(valid_mask)[0]

        print(f"Total bars: {len(pcr_frame)}, Valid: {len(valid_idx)}")
        print(f"D1 distribution: {Counter(d1[valid_idx])}")

        zigzag_data = load_spy_zigzags(store)
        all_mask = np.zeros(len(pcr_frame), dtype=bool)
        all_mask[valid_idx] = True
        pcr_results = analyze_signal(
            'PCR_ALL', all_mask, spy_ret, spy_px,
            pcr_frame.index, zigzag_data=zigzag_data
        )

        pcr_state_results = {}
        for d1_label in set(d1[valid_idx]):
            state_mask = np.zeros(len(pcr_frame), dtype=bool)
            for i in valid_idx:
                if d1[i] == d1_label:
                    state_mask[i] = True
            if state_mask.sum() >= 5:
                sr = analyze_signal(
                    f'PCR_{d1_label}', state_mask, spy_ret, spy_px,
                    pcr_frame.index, zigzag_data=zigzag_data
                )
                pcr_state_results[d1_label] = sr

        print("\n── PCR neutrality check ──")
        for h in [10, 20]:
            n = pcr_results.get('neutrality', {}).get(h, {})
            print(f"  H{h}d: mean={n.get('mean_return',np.nan):.3f}% | "
                  f"WR={n.get('win_rate',np.nan):.2%} | "
                  f"|mean|<1.5% → {n.get('is_neutral_abs', '?')} | "
                  f"WR<55% → {n.get('is_neutral_wr', '?')}")

        print(f"\nPer-D1 neutrality:")
        for d1l, sr in sorted(pcr_state_results.items(), key=lambda x: -x[1].get('n_signals',0)):
            n20 = sr.get('neutrality', {}).get(20, {})
            print(f"  {d1l}: N={sr.get('n_signals')} | mean20d={n20.get('mean_return',np.nan):.2f}% | "
                  f"WR20={n20.get('win_rate',np.nan):.2%} | "
                  f"neutral_abs={n20.get('is_neutral_abs','?')} | neutral_wr={n20.get('is_neutral_wr','?')}")

    # ── FINAL SUMMARY ──
    print("\n" + "="*80)
    print("  RESUMEN FINAL")
    print("="*80)

    # YIELD: EXIT signal validation
    print("\n1. YIELD EXTREME_STEEPNING como EXIT:")
    if 'yield_results' in dir() and yield_results.get('n_signals', 0) > 0:
        wr20 = yield_results.get('win_rate', {}).get(20, np.nan)
        ci20 = yield_results.get('ci95_win_rate', {}).get(20, (np.nan, np.nan))
        dist20 = yield_results.get('distributions', {}).get(20, {})
        pf20 = yield_results.get('profit', {}).get(20, {})
        streaks = yield_results.get('streaks', {})
        knife = yield_results.get('falling_knife', {}).get(20, {})

        print(f"   N señales: {yield_results.get('n_signals')}")
        print(f"   Win rate 20d: {wr20:.2%} CI95 [{ci20[0]:.2%}, {ci20[1]:.2%}]")
        print(f"   Return 20d: mean={dist20.get('mean',np.nan):.2f}% med={dist20.get('median',np.nan):.2f}%")
        print(f"   Profit factor: {pf20.get('profit_factor',np.nan):.3f}")
        print(f"   Kelly: {pf20.get('kelly',np.nan):.3f}")
        print(f"   Max loss streak: {streaks.get('max_loss_streak', '?')}")
        print(f"   Cuchillo 20d (mean intra-DD): {knife.get('mean_intra_dd',np.nan):.2f}%")
    else:
        print("   No data")

    # ROTATION/DXY/PCR neutrality summary
    for name, res in [('ROTATION', 'rot_results'), ('DXY', 'dxy_results'), ('PCR', 'pcr_results')]:
        print(f"\n{name} NEUTRALITY:")
        r = locals().get(res, {})
        if r:
            for h in [10, 20]:
                n = r.get('neutrality', {}).get(h, {})
                neutral = n.get('is_neutral_abs', False) and n.get('is_neutral_wr', False)
                print(f"   H{h}d: |mean|={n.get('abs_mean',np.nan):.2f}% WR={n.get('win_rate',np.nan):.2%} "
                      f"→ {'NEUTRAL ✓' if neutral else 'NOT NEUTRAL ✗'}")
        else:
            print(f"   No data")

    store.close()
    print("\nDONE.")


if __name__ == "__main__":
    main()