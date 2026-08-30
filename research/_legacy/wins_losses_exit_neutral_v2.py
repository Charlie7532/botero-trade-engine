#!/usr/bin/env python3
"""
ESTUDIO WINS vs LOSSES v2 — YIELD (EXIT) + ROTATION, DXY, PCR (NEUTRAL)
=======================================================================
8 dimensiones por estación. ENTRADA: barra de señal (no pivote zigzag).
state_key del METAR (D1×D2×D3). CI95 bootstrap 2000. D3 = std(2)/std(10).

8 DIMENSIONES:
  A. Win rate + CI95
  B. Distribuciones (wins + losses separadas)
  C. Profit factor, Kelly, EV
  D. Rachas (streaks)
  E. Timing vs zigzag
  F. Cuchillo cayendo (intra-trade drawdown)
  G. Calidad N (sample quality)
  H. Neutrality / Exit check (bootstrap CI95)

YIELD = EXIT signal: EXTREME_STEEPNING debe mostrar forward returns negativos.
ROTATION, DXY, PCR = NEUTRAL: |mean| < 1.5% + win rate ≈ 50%.
"""

import sys, json, os
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.yield_curve_lookup import YieldCurveLookupAdapter
from backend.modules.entry_decision.domain.rules.rotation_lookup import RotationLookupAdapter
from backend.modules.entry_decision.domain.rules.dxy_lookup import DXYLookupAdapter
from backend.modules.entry_decision.domain.rules.pcr_lookup import PCRLookupAdapter

# ── Bootstrap utilities ────────────────────────────────────────────
def boot_ci(arr, ci=95, n_boot=2000, seed=42):
    """Bootstrap CI95 for mean. Returns (mean, lo, hi)."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    means = np.array([rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(n_boot)])
    lo = (100 - ci) / 2
    hi = 100 - lo
    return arr.mean(), np.percentile(means, lo), np.percentile(means, hi)

def boot_ci_binary(events, ci=95, n_boot=2000, seed=42):
    """Bootstrap CI95 for a rate (binary events). Returns (rate, lo, hi)."""
    events = np.asarray(events, float)
    n = len(events)
    if n < 3:
        return events.mean(), np.nan, np.nan
    rng = np.random.default_rng(seed)
    rates = np.array([rng.choice(events, size=n, replace=True).mean() for _ in range(n_boot)])
    lo = (100 - ci) / 2
    hi = 100 - lo
    return events.mean(), np.percentile(rates, lo), np.percentile(rates, hi)

def boot_ci_median(arr, ci=95, n_boot=2000, seed=42):
    """Bootstrap CI95 for median."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    meds = np.array([np.median(rng.choice(arr, size=len(arr), replace=True)) for _ in range(n_boot)])
    lo = (100 - ci) / 2
    hi = 100 - lo
    return np.median(arr), np.percentile(meds, lo), np.percentile(meds, hi)

def compute_d2_d3(series):
    """D2 = diff(3d), D3 = std(2d)/std(10d) — pitfall #46 correct formula."""
    d2 = series.diff(3)
    s2 = series.rolling(2).std()
    s10 = series.rolling(10).std()
    d3 = (s2 / s10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    return d2, d3

def streak_analysis(binary_events):
    """Analyze streaks of wins (1) and losses (0)."""
    events = np.asarray(binary_events, dtype=int)
    streaks_win = []
    streaks_loss = []
    current_len = 0
    current_val = None
    for e in events:
        if e == current_val:
            current_len += 1
        else:
            if current_len > 0:
                (streaks_win if current_val == 1 else streaks_loss).append(current_len)
            current_val = e
            current_len = 1
    if current_len > 0:
        (streaks_win if current_val == 1 else streaks_loss).append(current_len)
    return {
        'max_win_streak': max(streaks_win) if streaks_win else 0,
        'max_loss_streak': max(streaks_loss) if streaks_loss else 0,
        'mean_win_streak': np.mean(streaks_win) if streaks_win else 0.0,
        'mean_loss_streak': np.mean(streaks_loss) if streaks_loss else 0.0,
        'loss_streaks': sorted(streaks_loss, reverse=True) if streaks_loss else [],
    }

# ── 8-dimension analysis per station ───────────────────────────────
def analyze_signal_8d(name, signal_mask, spy_daily_ret_pct, spy_prices, dates,
                      forward_horizons=[1, 3, 5, 10, 20],
                      zigzag_pivots=None):
    """
    ENTRADA: barra de señal (forward returns from signal bar).
    Mide 8 dimensiones completas con bootstrap CI95.
    """
    mask = np.asarray(signal_mask, dtype=bool)
    spy_ret = np.asarray(spy_daily_ret_pct)  # daily returns in % (not decimal)
    spy_px = np.asarray(spy_prices)
    event_idx = np.where(mask)[0]
    n_signals = len(event_idx)

    if n_signals == 0:
        return {'error': 'No signals', 'n_signals': 0}

    result = {'n_signals': n_signals, 'n_total_bars': len(spy_ret)}
    result['pct_signals'] = n_signals / max(len(spy_ret), 1) * 100

    # ═══════════════════════════════════════════════════════════════
    # A — WIN RATE + CI95
    # ═══════════════════════════════════════════════════════════════
    wr = {}
    for h in forward_horizons:
        rets_h = np.array([spy_ret[idx:idx+h].sum() if idx+h < len(spy_ret) else np.nan for idx in event_idx])
        valid = rets_h[~np.isnan(rets_h)]
        wins = valid > 0
        if len(wins) >= 3:
            rate, lo, hi = boot_ci_binary(wins)
            wr[h] = {'rate': rate, 'ci95_lo': lo, 'ci95_hi': hi, 'n_valid': len(valid)}
        else:
            wr[h] = {'rate': wins.mean() if len(wins) > 0 else np.nan, 'ci95_lo': np.nan, 'ci95_hi': np.nan, 'n_valid': len(valid)}
    result['win_rate'] = wr

    # ═══════════════════════════════════════════════════════════════
    # B — DISTRIBUCIONES (wins + losses)
    # ═══════════════════════════════════════════════════════════════
    dist = {}
    for h in forward_horizons:
        rets_h = np.array([spy_ret[idx:idx+h].sum() if idx+h < len(spy_ret) else np.nan for idx in event_idx])
        valid = rets_h[~np.isnan(rets_h)]
        wins_arr = valid[valid > 0]
        losses_arr = valid[valid < 0]
        h_dist = {'n_wins': len(wins_arr), 'n_losses': len(losses_arr),
                  'mean': valid.mean(), 'median': np.median(valid),
                  'std': np.std(valid), 'min': valid.min(), 'max': valid.max(),
                  'skew': float(pd.Series(valid).skew()) if len(valid) >= 3 else np.nan}
        if len(valid) >= 5:
            h_dist['p5'] = np.percentile(valid, 5)
            h_dist['p25'] = np.percentile(valid, 25)
            h_dist['p75'] = np.percentile(valid, 75)
            h_dist['p95'] = np.percentile(valid, 95)
        # Wins distribution
        if len(wins_arr) >= 3:
            m, lo, hi = boot_ci_median(wins_arr)
            h_dist['wins_p50'] = m
            h_dist['wins_p50_ci95'] = (lo, hi)
            h_dist['wins_p90'] = np.percentile(wins_arr, 90)
            h_dist['wins_max'] = wins_arr.max()
        # Losses distribution
        if len(losses_arr) >= 3:
            h_dist['losses_p50'] = np.median(losses_arr)
            h_dist['losses_p10'] = np.percentile(losses_arr, 10) if len(losses_arr) >= 10 else losses_arr.min()
            h_dist['losses_min'] = losses_arr.min()
            h_dist['losses_wipeouts'] = (losses_arr < -20).sum()
        dist[h] = h_dist
    result['distributions'] = dist

    # ═══════════════════════════════════════════════════════════════
    # C — PROFIT FACTOR, KELLY, EV
    # ═══════════════════════════════════════════════════════════════
    profit = {}
    for h in forward_horizons:
        rets_h = np.array([spy_ret[idx:idx+h].sum() if idx+h < len(spy_ret) else np.nan for idx in event_idx])
        valid = rets_h[~np.isnan(rets_h)]
        wins_arr = valid[valid > 0]
        losses_arr = valid[valid < 0]
        total_gain = wins_arr.sum()
        total_loss = abs(losses_arr.sum()) if len(losses_arr) > 0 else 0.0
        pf = total_gain / total_loss if total_loss > 0 else (np.inf if total_gain > 0 else np.nan)
        p_win = len(wins_arr) / len(valid) if len(valid) > 0 else 0.0
        avg_win = wins_arr.mean() if len(wins_arr) > 0 else 0.0
        avg_loss = abs(losses_arr.mean()) if len(losses_arr) > 0 else 0.0
        wl_ratio = avg_win / avg_loss if avg_loss > 0 else np.inf
        kelly = p_win - (1 - p_win) / wl_ratio if wl_ratio > 0 else -1.0
        kelly = max(min(kelly, 1.0), -1.0)
        ev, ev_lo, ev_hi = boot_ci(valid) if len(valid) >= 3 else (valid.mean(), np.nan, np.nan)
        profit[h] = {'profit_factor': pf, 'avg_win': avg_win, 'avg_loss': avg_loss,
                      'wl_ratio': wl_ratio, 'kelly': kelly, 'ev': ev,
                      'ev_ci95_lo': ev_lo, 'ev_ci95_hi': ev_hi, 'n_trades': len(valid)}
    result['profit'] = profit

    # ═══════════════════════════════════════════════════════════════
    # D — RACHAS
    # ═══════════════════════════════════════════════════════════════
    h_streak = 5
    streak_events = np.array([1 if idx+h_streak < len(spy_ret) and spy_ret[idx:idx+h_streak].sum() > 0 else 0
                               for idx in event_idx])
    if len(streak_events) >= 3:
        result['streaks'] = streak_analysis(streak_events)
    else:
        result['streaks'] = {'error': 'insufficient events'}

    # ═══════════════════════════════════════════════════════════════
    # E — TIMING vs ZIGZAG
    # ═══════════════════════════════════════════════════════════════
    if zigzag_pivots:
        zz25 = zigzag_pivots.get('zz25', [])
        pivot_dates_set = {str(z['start']).split(' ')[0] for z in zz25}
        signal_dates = [str(dates[i]).split(' ')[0] for i in event_idx]
        n_at_pivot = sum(1 for d in signal_dates if d in pivot_dates_set)
        # Compute timing returns
        at_pivot_mask = np.array([(str(dates[i]).split(' ')[0] in pivot_dates_set) for i in event_idx])
        timing_ret = {}
        for h in [5, 10, 20]:
            rets_at = np.array([spy_ret[idx:idx+h].sum() for idx in event_idx if idx+h < len(spy_ret)
                                and at_pivot_mask[list(event_idx).index(idx)]])
            rets_not = np.array([spy_ret[idx:idx+h].sum() for idx in event_idx if idx+h < len(spy_ret)
                                 and not at_pivot_mask[list(event_idx).index(idx)]])
            timing_ret[f'h{h}_at_pivot'] = {'mean': rets_at.mean() if len(rets_at)>0 else np.nan, 'n': len(rets_at)}
            timing_ret[f'h{h}_not_pivot'] = {'mean': rets_not.mean() if len(rets_not)>0 else np.nan, 'n': len(rets_not)}
        result['timing'] = {'n_signals': n_signals, 'n_at_pivot': n_at_pivot,
                            'pct_at_pivot': n_at_pivot/n_signals*100 if n_signals>0 else 0,
                            'returns': timing_ret}
    else:
        result['timing'] = {'error': 'no zigzag data'}

    # ═══════════════════════════════════════════════════════════════
    # F — CUCHILLO CAYENDO
    # ═══════════════════════════════════════════════════════════════
    knife = {}
    for h in forward_horizons:
        intra_dds = np.array([spy_ret[idx:idx+h].cumsum().min() for idx in event_idx if idx+h < len(spy_ret)])
        valid = intra_dds[~np.isnan(intra_dds)]
        if len(valid) >= 3:
            m, lo, hi = boot_ci(valid)
            knife[h] = {'mean_intra_dd': m, 'ci95_lo': lo, 'ci95_hi': hi,
                        'max_intra_dd': valid.min(), 'p5_intra_dd': np.percentile(valid, 5) if len(valid)>=20 else valid.min(),
                        'pct_never_positive': (valid <= 0).mean()}
        else:
            knife[h] = {'mean_intra_dd': valid.mean() if len(valid)>0 else np.nan, 'max_intra_dd': valid.min() if len(valid)>0 else np.nan}
    result['falling_knife'] = knife

    # ═══════════════════════════════════════════════════════════════
    # G — CALIDAD N
    # ═══════════════════════════════════════════════════════════════
    calidad = {
        'n_signals_total': n_signals,
        'pct_of_bars': n_signals / max(len(spy_ret), 1) * 100,
    }
    # Bootstrap: test reliability via CV of boot means
    rets_20d = np.array([spy_ret[idx:idx+20].sum() if idx+20 < len(spy_ret) else np.nan for idx in event_idx])
    valid20 = rets_20d[~np.isnan(rets_20d)]
    if len(valid20) >= 5:
        rng = np.random.default_rng(42)
        boot_means = np.array([rng.choice(valid20, size=len(valid20), replace=True).mean() for _ in range(2000)])
        calidad['mean_20d'] = valid20.mean()
        calidad['std_boot_means'] = boot_means.std()
        calidad['cv_boot'] = abs(boot_means.std() / valid20.mean()) if abs(valid20.mean()) > 1e-10 else np.inf
        calidad['ci95_width_pct'] = (np.percentile(boot_means, 97.5) - np.percentile(boot_means, 2.5))
        calidad['reliability'] = 'HIGH' if len(valid20) >= 30 else ('MODERATE' if len(valid20) >= 15 else 'LOW')
        calidad['reliable'] = len(valid20) >= 15
    else:
        calidad['reliability'] = 'UNRELIABLE'
        calidad['reliable'] = False
    result['calidad_n'] = calidad

    return result


# ── Station analysis ────────────────────────────────────────────────
def analyze_station(name, tickers, adapter, extreme_d1_list, is_exit=False):
    """
    Load station ticker(s), classify every bar via adapter, analyze.
    Returns full 8-dimension results for each D1 bin + aggregate.
    """
    store = TimescaleDataStore()
    
    # Load station data
    if name == 'YIELD':
        df, dates = load_multi_ticker(store, tickers + ['SPY'])
        if df is None: return None
        df['spread'] = df[tickers[0]] - df[tickers[1]]
        ind_series = df['spread']
    elif name == 'ROTATION':
        df, dates = load_multi_ticker(store, tickers + ['SPY'])
        if df is None: return None
        z1 = zscore_rolling(df[tickers[0]] / df[tickers[1]], 252)
        z2 = zscore_rolling(df[tickers[2]] / df[tickers[3]], 252)
        ind_series = z1 + z2
    else:
        df, dates = load_multi_ticker(store, tickers + ['SPY'])
        if df is None: return None
        ind_series = df[tickers[0]]

    spy_ret_pct = df['SPY'].pct_change().shift(-1) * 100  # forward daily returns in %
    spy_px = df['SPY'].values
    common_dates = df.index

    # Compute D2/D3
    d2, d3 = compute_d2_d3(ind_series)
    valid_mask = ~np.isnan(spy_ret_pct) & ~pd.isna(d2) & ~pd.isna(d3)
    valid_idx = np.where(valid_mask)[0]

    print(f"\n{'='*80}")
    print(f"  {name} — {'EXIT' if is_exit else 'NEUTRAL'} station")
    print(f"{'='*80}")
    print(f"  Bars: {len(df)}, Valid: {len(valid_idx)}")
    
    # D1 distribution
    d1_labels = []
    for i in valid_idx:
        val = float(ind_series.iloc[i])
        vel = float(d2.iloc[i])
        vol = float(d3.iloc[i])
        try:
            g = adapter.lookup_yield_curve_guidance(val=val, d3_speed=vel, vol_norm=vol) if name == 'YIELD' else \
                adapter.lookup_rotation_guidance(val=val, d3_speed=vel, vol_norm=vol) if name == 'ROTATION' else \
                adapter.lookup_dxy_guidance(val=val, d3_speed=vel, vol_norm=vol) if name == 'DXY' else \
                adapter.lookup_pcr_guidance(val=val, d3_speed=vel, vol_norm=vol)
        except Exception:
            d1_labels.append('ERROR')
            continue
        d1_labels.append(g.state_key.split('__')[0] if g else 'UNKNOWN')
    
    d1_counter = Counter(d1_labels)
    print(f"  D1 distribution: {dict(d1_counter)}")
    store.close()
    store2 = TimescaleDataStore()
    zigzag_data = load_spy_zigzags(store2)

    results = {}

    # Analyze by EXTREME D1 bins (for YIELD: EXTREME_STEEPNING)
    if extreme_d1_list:
        extreme_mask = np.zeros(len(df), dtype=bool)
        for i, d1l in zip(valid_idx, d1_labels):
            if d1l in extreme_d1_list:
                extreme_mask[i] = True
        n_extreme = extreme_mask.sum()
        print(f"  EXTREME signals ({', '.join(extreme_d1_list)}): {n_extreme}")
        if n_extreme >= 3:
            r = analyze_signal_8d(f'{name}_EXTREME', extreme_mask, spy_ret_pct.values, spy_px, 
                                  common_dates, zigzag_pivots=zigzag_data)
            results['_aggregate_extreme'] = r
        else:
            print(f"  ⚠️  Too few extreme signals for bootstrap (N={n_extreme}). Showing raw stats only.")

    # Per-D1-bin analysis
    for d1l, count in d1_counter.most_common():
        if count < 5:
            continue
        d1_mask = np.zeros(len(df), dtype=bool)
        for i, lbl in zip(valid_idx, d1_labels):
            if lbl == d1l:
                d1_mask[i] = True
        r = analyze_signal_8d(f'{name}_{d1l}', d1_mask, spy_ret_pct.values, spy_px,
                              common_dates, zigzag_pivots=zigzag_data)
        results[d1l] = r

    store2.close()
    return results


def load_multi_ticker(store, tickers):
    """Load OHLCV for multiple tickers, return aligned common-date DataFrame."""
    dfs = {}
    for t in tickers:
        raw = store.load_bars(t, "1d")
        if raw is None or len(raw) == 0:
            print(f"  ⚠️  No data for {t}")
            return None, None
        raw.index = pd.to_datetime(raw.index).normalize()
        s = raw["close"].copy()
        s = s[~s.index.duplicated(keep="last")].sort_index()
        dfs[t] = s
    common_idx = sorted(set.intersection(*[set(s.index) for s in dfs.values()]))
    if len(common_idx) < 20:
        return None, None
    frame = pd.DataFrame(index=common_idx)
    for t, s in dfs.items():
        frame[t] = s.loc[common_idx]
    return frame, common_idx


def zscore_rolling(series, window=252):
    """Rolling z-score with min_periods=20."""
    mu = series.rolling(window, min_periods=20).mean()
    sigma = series.rolling(window, min_periods=20).std().replace(0, np.nan)
    return (series - mu) / sigma


def load_spy_zigzags(store):
    """Load SPY zigzag legs from DB."""
    conn = store._conn()
    cur = conn.cursor()
    zz = {}
    for scale in ['zz25']:
        cur.execute("""
            SELECT start_timestamp::date as d, end_timestamp::date as e,
                   start_type, end_type
            FROM market.zigzag_legs
            WHERE ticker = 'SPY' AND scale = %s AND status = 'CONFIRMED'
            ORDER BY start_timestamp
        """, [scale])
        zz[scale] = [{'start': r[0], 'end': r[1], 'start_type': r[2], 'end_type': r[3]}
                      for r in cur.fetchall()]
    cur.close()
    conn.close()
    return zz


# ── Print utilities ─────────────────────────────────────────────────
def print_station_report(name, results, is_exit=False):
    """Pretty-print the 8-dimension report."""
    is_neutral_station = not is_exit
    
    print(f"\n{'═'*80}")
    print(f"  {name} REPORT")
    print(f"{'═'*80}")
    
    # Aggregate extreme
    if '_aggregate_extreme' in results:
        _print_dimensions(name + " (extreme D1)", results['_aggregate_extreme'], is_exit)
    
    # Per-D1
    for d1l, r in sorted(results.items(), key=lambda x: -x[1].get('n_signals', 0)):
        if d1l.startswith('_aggregate'):
            continue
        _print_dimensions(f"{name}/{d1l}", r, is_exit)


def _print_dimensions(label, r, is_exit=False):
    """Print all 8 dimensions for one signal set."""
    n = r.get('n_signals', 0)
    if n < 3:
        return
    
    wr = r.get('win_rate', {})
    wr20 = wr.get(20, {})
    dist = r.get('distributions', {}).get(20, {})
    profit = r.get('profit', {}).get(20, {})
    streaks = r.get('streaks', {})
    timing = r.get('timing', {})
    knife = r.get('falling_knife', {}).get(20, {})
    calidad = r.get('calidad_n', {})
    
    print(f"\n  ┌─ {label} (N={n}) {'─'*40}")
    
    # A — Win rate
    print(f"  │ A. WIN RATE: {wr20.get('rate',np.nan):.1%} CI95 [{wr20.get('ci95_lo',np.nan):.1%}, {wr20.get('ci95_hi',np.nan):.1%}] (20d)")
    wr5 = wr.get(5, {})
    wr10 = wr.get(10, {})
    print(f"  │    5d={wr5.get('rate',np.nan):.1%}  10d={wr10.get('rate',np.nan):.1%}")
    
    # B — Distributions
    print(f"  │ B. DISTRIBUTIONS (20d): mean={dist.get('mean',np.nan):.2f}%  median={dist.get('median',np.nan):.2f}%  std={dist.get('std',np.nan):.2f}%")
    if dist.get('wins_p50') is not None:
        print(f"  │    WINS (N={dist.get('n_wins','?')}): P50={dist.get('wins_p50',np.nan):.2f}%  P90={dist.get('wins_p90',np.nan):.2f}%  max={dist.get('wins_max',np.nan):.2f}%")
    if dist.get('losses_p50') is not None:
        print(f"  │    LOSSES (N={dist.get('n_losses','?')}): P50={dist.get('losses_p50',np.nan):.2f}%  P10={dist.get('losses_p10',np.nan):.2f}%  min={dist.get('losses_min',np.nan):.2f}%  wipeouts>20%={dist.get('losses_wipeouts','?')}")
    
    # C — Profit factor
    print(f"  │ C. PROFIT: PF={profit.get('profit_factor',np.nan):.2f}  Kelly={profit.get('kelly',np.nan):.3f}  EV={profit.get('ev',np.nan):.2f}% CI95 [{profit.get('ev_ci95_lo',np.nan):.2f}, {profit.get('ev_ci95_hi',np.nan):.2f}]")
    print(f"  │    avg_win={profit.get('avg_win',np.nan):.2f}%  avg_loss={profit.get('avg_loss',np.nan):.2f}%  W/L={profit.get('wl_ratio',np.nan):.2f}")
    
    # D — Streaks
    print(f"  │ D. RACHAS: max_loss_streak={streaks.get('max_loss_streak','?')}  mean_loss_streak={streaks.get('mean_loss_streak',np.nan):.1f}")
    
    # E — Timing
    print(f"  │ E. TIMING: at_pivot={timing.get('n_at_pivot','?')}/{timing.get('n_signals','?')} ({timing.get('pct_at_pivot',np.nan):.0f}%)")
    tret = timing.get('returns', {})
    if 'h20_at_pivot' in tret:
        print(f"  │    at_pivot 20d: mean={tret['h20_at_pivot'].get('mean',np.nan):.2f}% (N={tret['h20_at_pivot'].get('n','?')})")
        print(f"  │    not_pivot 20d: mean={tret['h20_not_pivot'].get('mean',np.nan):.2f}% (N={tret['h20_not_pivot'].get('n','?')})")
    
    # F — Cuchillo
    print(f"  │ F. CUCHILLO: mean_intra_dd={knife.get('mean_intra_dd',np.nan):.2f}%  max_dd={knife.get('max_intra_dd',np.nan):.2f}%  never_pos={knife.get('pct_never_positive',np.nan):.1%}")
    
    # G — Calidad N
    print(f"  │ G. CALIDAD N: reliability={calidad.get('reliability','?')}  cv_boot={calidad.get('cv_boot',np.nan):.3f}  ci95_width={calidad.get('ci95_width_pct',np.nan):.2f}%")
    
    # H — Neutrality/Exit check
    mean20 = dist.get('mean', np.nan)
    wr20_rate = wr20.get('rate', np.nan)
    ev20, ev_lo, ev_hi = profit.get('ev', np.nan), profit.get('ev_ci95_lo', np.nan), profit.get('ev_ci95_hi', np.nan)
    
    if is_exit:
        # YIELD: exit check = forward negative?
        is_negative = not np.isnan(mean20) and mean20 < 0
        ev_negative = not np.isnan(ev_hi) and ev_hi < 0
        print(f"  │ H. EXIT CHECK: forward mean 20d={mean20:.2f}% → {'EXIT VALID ✓' if is_negative else 'NOT EXIT ✗'}")
        print(f"  │    EV CI95 upper bound: {ev_hi:.2f}% → {'EV negative ✓' if ev_negative else 'EV not negative ✗'}")
    else:
        # NEUTRAL check: |mean| < 1.5% AND WR ≈ 50%
        abs_mean_ok = not np.isnan(mean20) and abs(mean20) < 1.5
        ci_contains_zero = (not np.isnan(ev_lo) and not np.isnan(ev_hi) and ev_lo < 0 < ev_hi)
        wr_not_significant = not np.isnan(wr20_rate) and 0.40 < wr20_rate < 0.60
        neutral = abs_mean_ok and ci_contains_zero and wr_not_significant
        print(f"  │ H. NEUTRAL CHECK: |mean|={abs(mean20):.2f}% → {'<1.5% ✓' if abs_mean_ok else '≥1.5% ✗'} | "
              f"CI95 contains zero: {'YES ✓' if ci_contains_zero else 'NO ✗'} | "
              f"WR={wr20_rate:.1%} → {'≈50% ✓' if wr_not_significant else '≠50% ✗'}")
        print(f"  │    → {'NEUTRAL ✓' if neutral else 'NOT NEUTRAL ✗'}")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    print("╔" + "═" * 78 + "╗")
    print("║" + "  ESTUDIO WINS vs LOSSES v2 — YIELD (EXIT) + ROTATION/DXY/PCR (NEUTRAL)".center(78) + "║")
    print("║" + "  8 dimensiones. ENTRADA: barra de señal. CI95 bootstrap 2000.".center(78) + "║")
    print("╚" + "═" * 78 + "╝")

    all_results = {}

    # ── YIELD (EXIT) ──
    print("\n" + "━" * 80)
    print("  1/4 — YIELD CURVE (EXIT: EXTREME_STEEPNING)")
    print("━" * 80)
    yield_adapter = YieldCurveLookupAdapter()
    yield_results = analyze_station('YIELD', ['TNX', 'IRX'], yield_adapter,
                                    extreme_d1_list=['EXTREME_STEEPNING', 'EXTREME_STEEPNING_UNINVERSION'],
                                    is_exit=True)
    if yield_results:
        print_station_report('YIELD', yield_results, is_exit=True)
        all_results['YIELD'] = yield_results

    # ── ROTATION (NEUTRAL) ──
    print("\n" + "━" * 80)
    print("  2/4 — ROTATION (NEUTRAL)")
    print("━" * 80)
    rot_adapter = RotationLookupAdapter()
    rot_results = analyze_station('ROTATION', ['XLY', 'XLP', 'XLK', 'XLU'], rot_adapter,
                                  extreme_d1_list=None, is_exit=False)
    if rot_results:
        print_station_report('ROTATION', rot_results, is_exit=False)
        all_results['ROTATION'] = rot_results

    # ── DXY (NEUTRAL) ──
    print("\n" + "━" * 80)
    print("  3/4 — DXY (NEUTRAL)")
    print("━" * 80)
    dxy_adapter = DXYLookupAdapter()
    dxy_results = analyze_station('DXY', ['DXY'], dxy_adapter,
                                  extreme_d1_list=None, is_exit=False)
    if dxy_results:
        print_station_report('DXY', dxy_results, is_exit=False)
        all_results['DXY'] = dxy_results

    # ── PCR (NEUTRAL) ──
    print("\n" + "━" * 80)
    print("  4/4 — PCR (NEUTRAL)")
    print("━" * 80)
    pcr_adapter = PCRLookupAdapter()
    pcr_results = analyze_station('PCR', ['CBOE_PCR'], pcr_adapter,
                                  extreme_d1_list=None, is_exit=False)
    if pcr_results:
        print_station_report('PCR', pcr_results, is_exit=False)
        all_results['PCR'] = pcr_results

    # ── FINAL SUMMARY ──
    print("\n" + "═" * 80)
    print("  FINAL SUMMARY")
    print("═" * 80)

    # YIELD EXIT validation
    if 'YIELD' in all_results and '_aggregate_extreme' in all_results['YIELD']:
        yr = all_results['YIELD']['_aggregate_extreme']
        n_yield = yr.get('n_signals', 0)
        mean20 = yr.get('distributions', {}).get(20, {}).get('mean', np.nan)
        pf20 = yr.get('profit', {}).get(20, {}).get('profit_factor', np.nan)
        knife_mean = yr.get('falling_knife', {}).get(20, {}).get('mean_intra_dd', np.nan)
        calidad = yr.get('calidad_n', {})
        print(f"\n  1. YIELD EXTREME_STEEPNING as EXIT:")
        print(f"     N={n_yield}  mean_20d={mean20:.2f}%  PF={pf20:.2f}  cuchillo_20d={knife_mean:.2f}%")
        print(f"     calidad: {calidad.get('reliability','?')} (N reliability)")
        # Summary of per-state results
        for d1l, r in sorted(all_results['YIELD'].items(), key=lambda x: -x[1].get('n_signals',0)):
            if d1l.startswith('_aggregate'): continue
            mean_d1 = r.get('distributions', {}).get(20, {}).get('mean', np.nan)
            n_d1 = r.get('n_signals', 0)
            if 'EXTREME' in d1l.upper():
                print(f"     {d1l}: N={n_d1} mean_20d={mean_d1:.2f}%")
    else:
        print("\n  1. YIELD: No EXTREME_STEEPNING data")

    # ROTATION / DXY / PCR neutrality
    for name in ['ROTATION', 'DXY', 'PCR']:
        if name not in all_results:
            print(f"\n  {name}: No data")
            continue
        results = all_results[name]
        print(f"\n  {name} NEUTRALITY summary (per D1 bin, 20d horizon):")
        neutral_count = 0
        total_bins = 0
        for d1l, r in sorted(results.items(), key=lambda x: -x[1].get('n_signals',0)):
            n_d1 = r.get('n_signals', 0)
            if n_d1 < 5: continue
            total_bins += 1
            mean20 = r.get('distributions', {}).get(20, {}).get('mean', np.nan)
            wr20 = r.get('win_rate', {}).get(20, {}).get('rate', np.nan)
            ev_lo = r.get('profit', {}).get(20, {}).get('ev_ci95_lo', np.nan)
            ev_hi = r.get('profit', {}).get(20, {}).get('ev_ci95_hi', np.nan)
            abs_ok = not np.isnan(mean20) and abs(mean20) < 1.5
            ci_ok = not np.isnan(ev_lo) and not np.isnan(ev_hi) and ev_lo < 0 < ev_hi
            wr_ok = not np.isnan(wr20) and 0.40 < wr20 < 0.60
            is_neutral = abs_ok and ci_ok and wr_ok
            neutral_count += is_neutral
            print(f"    {d1l}: N={n_d1}  mean20={mean20:.2f}%  WR={wr20:.1%}  EV_CI=[{ev_lo:.2f}, {ev_hi:.2f}]  → {'NEUTRAL ✓' if is_neutral else 'NOT NEUTRAL ✗'}")
        if total_bins > 0:
            print(f"    → {neutral_count}/{total_bins} bins neutral")

    print("\nDONE.\n")


if __name__ == "__main__":
    main()