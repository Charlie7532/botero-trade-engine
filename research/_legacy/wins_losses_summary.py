#!/usr/bin/env python3
"""
WINS vs LOSSES — Análisis específico por D1 extremo (NO aggregate)
================================================================
- YIELD EXTREME_STEEPNING como EXIT signal
- ROTATION/DXY/PCR: neutralidad confirmada o refutada por D1 bin
- Métricas: 7 dimensiones, state_key, CI95 bootstrap 2000
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
from collections import Counter
from datetime import datetime

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.yield_curve_lookup import yield_curve_lookup
from backend.modules.entry_decision.domain.rules.rotation_lookup import rotation_lookup
from backend.modules.entry_decision.domain.rules.dxy_lookup import dxy_lookup
from backend.modules.entry_decision.domain.rules.pcr_lookup import pcr_lookup


# ── Bootstrap ──
def bootstrap_ci_mean(values, n_boot=2000, seed=42):
    vals = np.asarray(values, dtype=float)
    rng = np.random.RandomState(seed)
    means = np.array([rng.choice(vals, size=len(vals), replace=True).mean() for _ in range(n_boot)])
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))

def bootstrap_ci_wr(events, n_boot=2000, seed=42):
    ev = np.asarray(events, dtype=float)
    rng = np.random.RandomState(seed)
    rates = np.array([rng.choice(ev, size=len(ev), replace=True).mean() for _ in range(n_boot)])
    return float(np.percentile(rates, 2.5)), float(np.percentile(rates, 97.5))


def load_full_history(store, tickers):
    dfs = {}
    for t in tickers:
        df = store.load_bars(t, "1d")
        if df is not None and len(df) > 0:
            dfs[t] = df["close"].copy()
    common = sorted(set.intersection(*[set(pd.to_datetime(s.index)) for s in dfs.values()]))
    frame = pd.DataFrame(index=common)
    for t, s in dfs.items():
        s.index = pd.to_datetime(s.index)
        frame[t] = s.loc[common]
    return frame


def classify_bars(values, d1_edges, d2_edges, d3_edges, d1_lbl, d2_lbl, d3_lbl):
    n = len(values)
    vel = np.full(n, np.nan)
    for i in range(3, n):
        vel[i] = values[i] - values[i-3]
    vol_norm = np.full(n, 1.0)
    for i in range(10, n):
        std2 = np.std(values[i-1:i+1])
        std10 = np.std(values[i-9:i+1])
        vol_norm[i] = std2 / std10 if std10 > 0 else 1.0

    def c(v, e, l):
        for i, edge in enumerate(e):
            if v < edge:
                return l[i]
        return l[-1]

    d1 = np.array([c(v, d1_edges, d1_lbl) for v in values])
    d2 = np.array([c(v, d2_edges, d2_lbl) if not np.isnan(v) else 'NODATA' for v in vel])
    d3 = np.array([c(v, d3_edges, d3_lbl) for v in vol_norm])
    return d1, d2, d3, vel, vol_norm


def study_d1_signal(name, d1_label, mask, spy_rets, spy_px, dates, zigzag=None):
    """Full 7-dimension analysis for a single D1 label."""
    mask = np.asarray(mask, dtype=bool)
    idx = np.where(mask)[0]
    n = len(idx)
    if n == 0:
        return None

    forward = [1, 3, 5, 10, 20]
    result = {'station': name, 'd1_bin': d1_label, 'n_signals': n}

    # ── Forward returns per horizon ──
    rets = {}
    for h in forward:
        r = []
        for i in idx:
            if i + h < len(spy_rets):
                r.append(spy_rets[i:i+h].sum() * 100)
        rets[h] = np.array(r)

    # ── A. Win rate + CI95 ──
    result['win_rates'] = {}
    for h in forward:
        wins = rets[h] > 0
        wr = wins.mean()
        ci_lo, ci_hi = bootstrap_ci_wr(wins)
        result['win_rates'][h] = {'wr': round(wr, 4), 'ci95': [round(ci_lo, 4), round(ci_hi, 4)]}

    # ── B. Distributions ──
    result['distributions'] = {}
    for h in [5, 10, 20]:
        r = rets[h]
        ci_lo, ci_hi = bootstrap_ci_mean(r) if len(r) >= 10 else (np.nan, np.nan)
        result['distributions'][h] = {
            'mean': round(float(np.mean(r)), 3),
            'median': round(float(np.median(r)), 3),
            'std': round(float(np.std(r)), 3),
            'min': round(float(np.min(r)), 3),
            'max': round(float(np.max(r)), 3),
            'p5': round(float(np.percentile(r, 5)), 3),
            'p95': round(float(np.percentile(r, 95)), 3),
            'skew': round(float(pd.Series(r).skew()), 3) if len(r) >= 3 else np.nan,
            'ci95_mean': [round(ci_lo, 3), round(ci_hi, 3)]
        }

    # ── C. Profit Factor + Kelly (5d) ──
    r5 = rets[5]
    wins_arr = r5[r5 > 0]
    losses_arr = abs(r5[r5 < 0])
    total_gain = float(wins_arr.sum()) if len(wins_arr) > 0 else 0.0
    total_loss = float(losses_arr.sum()) if len(losses_arr) > 0 else 1e-10
    pf = total_gain / total_loss if total_loss > 0 else np.inf
    p_win = len(wins_arr) / len(r5)
    avg_win = float(wins_arr.mean()) if len(wins_arr) > 0 else 0.0
    avg_loss = float(losses_arr.mean()) if len(losses_arr) > 0 else 0.0
    wl = avg_win / avg_loss if avg_loss > 0 else np.inf
    kelly = p_win - (1-p_win)/wl if wl > 0 else -1.0
    result['profit'] = {
        'profit_factor': round(pf, 3),
        'kelly': round(kelly, 3),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'wl_ratio': round(wl, 2),
    }

    # ── D. Rachas (streaks, 5d) ──
    wins5 = (rets[5] > 0).astype(int)
    streaks = []
    curr_len, curr_val = 0, None
    for w in wins5:
        if w == curr_val:
            curr_len += 1
        else:
            if curr_len > 0:
                streaks.append((curr_val, curr_len))
            curr_val, curr_len = w, 1
    if curr_len > 0:
        streaks.append((curr_val, curr_len))
    w_streaks = [s[1] for s in streaks if s[0] == 1]
    l_streaks = [s[1] for s in streaks if s[0] == 0]
    result['streaks'] = {
        'max_win': max(w_streaks) if w_streaks else 0,
        'max_loss': max(l_streaks) if l_streaks else 0,
        'mean_win': round(np.mean(w_streaks), 1) if w_streaks else 0,
        'mean_loss': round(np.mean(l_streaks), 1) if l_streaks else 0,
    }

    # ── E. Timing vs zigzag ──
    if zigzag:
        pivot_set = {str(z['start']).split(' ')[0] for z in zigzag.get('zz25', [])}
        sig_dates = [str(dates[i]).split(' ')[0] for i in idx]
        at_pivot = [d in pivot_set for d in sig_dates]
        n_at = sum(at_pivot)
        # Returns conditional on at-pivot
        rets_at = np.array([rets[10][j] for j, ap in enumerate(at_pivot) if ap and j < len(rets[10])])
        rets_not = np.array([rets[10][j] for j, ap in enumerate(at_pivot) if not ap and j < len(rets[10])])
        result['timing'] = {
            'n_at_pivot': int(n_at),
            'pct_at_pivot': round(n_at/n*100, 1),
            'mean10d_at_pivot': round(float(np.mean(rets_at)), 2) if len(rets_at) > 0 else np.nan,
            'mean10d_not_pivot': round(float(np.mean(rets_not)), 2) if len(rets_not) > 0 else np.nan,
        }

    # ── F. Cuchillo cayendo (intra 20d drawdown) ──
    intra_dds = []
    for i in idx:
        if i + 20 < len(spy_rets):
            cum = np.cumsum(spy_rets[i:i+20]) * 100
            intra_dds.append(cum.min())
    intra_dds = np.array(intra_dds)
    result['falling_knife'] = {
        'mean_dd_20d': round(float(np.mean(intra_dds)), 2),
        'max_dd_20d': round(float(np.min(intra_dds)), 2),
        'p5_dd_20d': round(float(np.percentile(intra_dds, 5)), 2),
        'pct_always_negative': round((intra_dds <= 0).mean() * 100, 1),
    }

    # ── G. Neutrality ──
    r20 = rets[20]
    abs_mean = abs(np.mean(r20))
    wr20 = (r20 > 0).mean()
    result['neutrality'] = {
        'abs_mean_20d': round(abs_mean, 2),
        'wr_20d': round(wr20, 4),
        'is_neutral_abs': abs_mean < 1.5,
        'is_neutral_wr': wr20 < 0.55,
        'fully_neutral': abs_mean < 1.5 and wr20 < 0.55,
    }

    return result


# ── MAIN ──
store = TimescaleDataStore()
print("Cargando datos...")

# SPY zigzag for timing
conn = store._conn()
cur = conn.cursor()
cur.execute("SELECT start_timestamp::date, end_timestamp::date, start_type "
            "FROM market.zigzag_legs WHERE ticker='SPY' AND scale='zz25' "
            "AND status='CONFIRMED' ORDER BY start_timestamp")
zz25 = [{'start': r[0], 'end': r[1], 'start_type': r[2]} for r in cur.fetchall()]
cur.close()
conn.close()
zigzag_data = {'zz25': zz25}

results = {}

# ═══ YIELD CURVE ═══
print("\n🔹 YIELD CURVE — EXTREME_STEEPNING como EXIT")
yf = load_full_history(store, ['TNX', 'IRX', 'SPY'])
yf['spread'] = yf['TNX'] - yf['IRX']
y_adapter = yield_curve_lookup

d1, d2, d3, vel, vol = classify_bars(
    yf['spread'].values, y_adapter.edges_d1, y_adapter.edges_d2,
    y_adapter.edges_d3, y_adapter.labels_d1, y_adapter.labels_d2,
    y_adapter.labels_d3
)
spy_ret = yf['SPY'].pct_change().shift(-1).values
spy_px = yf['SPY'].values

# EXTREME_STEEPNING aggregate
ext_mask = np.array([d1[i] == 'EXTREME_STEEPNING' and d2[i] != 'NODATA' and not np.isnan(spy_ret[i])
                      for i in range(len(d1))])
r = study_d1_signal('YIELD', 'EXTREME_STEEPNING', ext_mask, spy_ret, spy_px, yf.index, zigzag_data)
results['YIELD_EXTREME_STEEPNING'] = r

# Per D2 subset (within EXTREME_STEEPNING)
for d2_cat in sorted(set(d2[ext_mask])):
    sub_mask = ext_mask & (d2 == d2_cat)
    if sub_mask.sum() >= 3:
        r2 = study_d1_signal('YIELD', f'EXTREME_STEEPNING:{d2_cat}', sub_mask, spy_ret, spy_px, yf.index, zigzag_data)
        if r2:
            results[f'YIELD_ES_{d2_cat}'] = r2

# DEEP_INVERSION for contrast
di_mask = np.array([d1[i] == 'DEEP_INVERSION' and d2[i] != 'NODATA' and not np.isnan(spy_ret[i])
                     for i in range(len(d1))])
r_di = study_d1_signal('YIELD', 'DEEP_INVERSION', di_mask, spy_ret, spy_px, yf.index, zigzag_data)
results['YIELD_DEEP_INVERSION'] = r_di

# ═══ ROTATION ═══
print("🔹 ROTATION — neutralidad")
rf = load_full_history(store, ['XLY', 'XLP', 'XLK', 'XLU', 'SPY'])
ratio_cyc = rf['XLY'] / rf['XLP']
ratio_tec = rf['XLK'] / rf['XLU']
z_cyc = (ratio_cyc - ratio_cyc.rolling(252, min_periods=20).mean()) / ratio_cyc.rolling(252, min_periods=20).std().replace(0, np.nan)
z_tec = (ratio_tec - ratio_tec.rolling(252, min_periods=20).mean()) / ratio_tec.rolling(252, min_periods=20).std().replace(0, np.nan)
rot_idx = z_cyc + z_tec
r_adapter = rotation_lookup

d1_r, d2_r, d3_r, _, _ = classify_bars(
    rot_idx.values, r_adapter.edges_d1, r_adapter.edges_d2,
    r_adapter.edges_d3, r_adapter.labels_d1, r_adapter.labels_d2,
    r_adapter.labels_d3
)
spy_ret_r = rf['SPY'].pct_change().shift(-1).values
spy_px_r = rf['SPY'].values

for d1l in sorted(set(d1_r)):
    mask = np.array([d1_r[i] == d1l and d2_r[i] != 'NODATA' and not np.isnan(spy_ret_r[i])
                      for i in range(len(d1_r))])
    if mask.sum() >= 5:
        r_rot = study_d1_signal('ROTATION', d1l, mask, spy_ret_r, spy_px_r, rf.index, zigzag_data)
        if r_rot:
            results[f'ROTATION_{d1l}'] = r_rot

# ═══ DXY ═══
print("🔹 DXY — neutralidad")
df = load_full_history(store, ['DXY', 'SPY'])
dxy_adapter = dxy_lookup
d1_dxy, d2_dxy, d3_dxy, _, _ = classify_bars(
    df['DXY'].values, dxy_adapter.edges_d1, dxy_adapter.edges_d2,
    dxy_adapter.edges_d3, dxy_adapter.labels_d1, dxy_adapter.labels_d2,
    dxy_adapter.labels_d3
)
spy_ret_d = df['SPY'].pct_change().shift(-1).values
spy_px_d = df['SPY'].values

for d1l in sorted(set(d1_dxy)):
    mask = np.array([d1_dxy[i] == d1l and d2_dxy[i] != 'NODATA' and not np.isnan(spy_ret_d[i])
                      for i in range(len(d1_dxy))])
    if mask.sum() >= 5:
        r_d = study_d1_signal('DXY', d1l, mask, spy_ret_d, spy_px_d, df.index, zigzag_data)
        if r_d:
            results[f'DXY_{d1l}'] = r_d

# ═══ PCR ═══
print("🔹 PCR — neutralidad")
pf = load_full_history(store, ['CBOE_PCR', 'SPY'])
pcr_adapter = pcr_lookup
d1_p, d2_p, d3_p, _, _ = classify_bars(
    pf['CBOE_PCR'].values, pcr_adapter.edges_d1, pcr_adapter.edges_d2,
    pcr_adapter.edges_d3, pcr_adapter.labels_d1, pcr_adapter.labels_d2,
    pcr_adapter.labels_d3
)
spy_ret_p = pf['SPY'].pct_change().shift(-1).values
spy_px_p = pf['SPY'].values

for d1l in sorted(set(d1_p)):
    mask = np.array([d1_p[i] == d1l and d2_p[i] != 'NODATA' and not np.isnan(spy_ret_p[i])
                      for i in range(len(d1_p))])
    if mask.sum() >= 5:
        r_p = study_d1_signal('PCR', d1l, mask, spy_ret_p, spy_px_p, pf.index, zigzag_data)
        if r_p:
            results[f'PCR_{d1l}'] = r_p

store.close()

# ── PRINT SUMMARY ──
print("\n" + "="*90)
print("  RESUMEN WINS vs LOSSES — 7 DIMENSIONES")
print("="*90)

for key in sorted(results.keys()):
    r = results[key]
    if r is None:
        continue
    station, d1_bin = r['station'], r['d1_bin']
    n = r['n_signals']
    wr5 = r['win_rates'][5]['wr']
    wr5_ci = r['win_rates'][5]['ci95']
    d20 = r['distributions'][20]
    pf = r['profit']
    st = r['streaks']
    fk = r['falling_knife']
    neut = r['neutrality']

    print(f"\n{'─'*90}")
    print(f"  {station} › {d1_bin}  (N={n})")
    print(f"  {'─'*50}")
    print(f"  A. Win Rate 5d:   {wr5:.1%}  CI95 [{wr5_ci[0]:.1%}, {wr5_ci[1]:.1%}]")
    print(f"     Win Rate 20d:  {r['win_rates'][20]['wr']:.1%}  CI95 [{r['win_rates'][20]['ci95'][0]:.1%}, {r['win_rates'][20]['ci95'][1]:.1%}]")
    print(f"  B. Return 20d:    mean={d20['mean']:.2f}%  med={d20['median']:.2f}%  std={d20['std']:.2f}%")
    print(f"     CI95 mean:     [{d20['ci95_mean'][0]:.2f}%, {d20['ci95_mean'][1]:.2f}%]")
    print(f"     Min/Max:       {d20['min']:.2f}% / {d20['max']:.2f}%  (skew={d20['skew']})")
    print(f"  C. Profit Factor: {pf['profit_factor']:.3f}  Kelly: {pf['kelly']:.3f}")
    print(f"     Avg Win/Loss:  {pf['avg_win']:.2f}% / {pf['avg_loss']:.2f}%  W/L={pf['wl_ratio']:.2f}")
    print(f"  D. Rachas:        max_win={st['max_win']}  max_loss={st['max_loss']}  "
          f"μwin={st['mean_win']}  μloss={st['mean_loss']}")
    if 'timing' in r:
        t = r['timing']
        print(f"  E. Timing:        {t['n_at_pivot']}/{n} ({t['pct_at_pivot']}%) at-pivot")
        print(f"     Return at-pivot: {t.get('mean10d_at_pivot', np.nan)}%  "
              f"not-pivot: {t.get('mean10d_not_pivot', np.nan)}%")
    print(f"  F. Cuchillo 20d:  mean_dd={fk['mean_dd_20d']}%  max_dd={fk['max_dd_20d']}%  "
          f"p5_dd={fk['p5_dd_20d']}%  always_neg={fk['pct_always_negative']}%")
    print(f"  G. Neutrality:    |mean|={neut['abs_mean_20d']}%  WR={neut['wr_20d']:.1%}  "
          f"→ {'NEUTRAL ✓' if neut['fully_neutral'] else 'NOT NEUTRAL ✗'}")

print("\n" + "="*90)
print("  VERDICTO FINAL")
print("="*90)

# YIELD EXIT
yield_r = results.get('YIELD_EXTREME_STEEPNING', {})
print(f"\n  🛑 YIELD EXTREME_STEEPNING como EXIT:")
if yield_r:
    n = yield_r['n_signals']
    wr20 = yield_r['win_rates'][20]
    d20 = yield_r['distributions'][20]
    pf = yield_r['profit']
    fk = yield_r['falling_knife']
    print(f"     N={n} | WR20={wr20['wr']:.1%} CI95[{wr20['ci95'][0]:.1%},{wr20['ci95'][1]:.1%}]")
    print(f"     Return 20d: {d20['mean']:.2f}% CI95[{d20['ci95_mean'][0]:.2f},{d20['ci95_mean'][1]:.2f}]%")
    print(f"     PF={pf['profit_factor']:.3f} Kelly={pf['kelly']:.3f}")
    print(f"     Cuchillo: max_dd={fk['max_dd_20d']}% never_positive={fk['pct_always_negative']}%")

    # Is it a valid EXIT?
    is_exit = (d20['mean'] < 0 and pf['profit_factor'] < 1.0)
    print(f"     → {'EXIT VÁLIDO (retorno negativo, PF<1)' if is_exit else 'EXIT DÉBIL (señal marginal)'}")
    print(f"     → Efecto real: ~{abs(d20['mean']):.2f}% de ventaja vs no salir")
    print(f"     → PERO: CI95 cruza cero [{d20['ci95_mean'][0]:.2f}, {d20['ci95_mean'][1]:.2f}]%")

# DEEP_INVERSION for comparison
di_r = results.get('YIELD_DEEP_INVERSION', {})
if di_r:
    print(f"\n     📎 DEEP_INVERSION (contraste): N={di_r['n_signals']} "
          f"WR20={di_r['win_rates'][20]['wr']:.1%} mean20d={di_r['distributions'][20]['mean']:.2f}%")

# Neutrality verdict
print(f"\n  🟡 ROTATION NEUTRALITY:")
rot_neutral = 0
rot_total = 0
for k, r in results.items():
    if k.startswith('ROTATION_'):
        n = r['neutrality']
        rot_total += 1
        label = '✓' if n['fully_neutral'] else '✗'
        if n['fully_neutral']:
            rot_neutral += 1
        print(f"     {label} {r['d1_bin']}: |mean|={n['abs_mean_20d']}% WR={n['wr_20d']:.1%} N={r['n_signals']}")
print(f"     → {rot_neutral}/{rot_total} estados neutrales")

print(f"\n  🟡 DXY NEUTRALITY:")
dxy_neutral = 0
dxy_total = 0
for k, r in results.items():
    if k.startswith('DXY_'):
        dxy_total += 1
        n = r['neutrality']
        label = '✓' if n['fully_neutral'] else '✗'
        if n['fully_neutral']:
            dxy_neutral += 1
        print(f"     {label} {r['d1_bin']}: |mean|={n['abs_mean_20d']}% WR={n['wr_20d']:.1%} N={r['n_signals']}")
print(f"     → {dxy_neutral}/{dxy_total} estados neutrales")

print(f"\n  🟡 PCR NEUTRALITY:")
pcr_neutral = 0
pcr_total = 0
for k, r in results.items():
    if k.startswith('PCR_'):
        pcr_total += 1
        n = r['neutrality']
        label = '✓' if n['fully_neutral'] else '✗'
        if n['fully_neutral']:
            pcr_neutral += 1
        print(f"     {label} {r['d1_bin']}: |mean|={n['abs_mean_20d']}% WR={n['wr_20d']:.1%} N={r['n_signals']}")
print(f"     → {pcr_neutral}/{pcr_total} estados neutrales")

print("\n  ⚠️ NOTA: La deriva positiva de SPY (~10%/año ≈ +0.4%/20d) infla artificialmente")
print("     los win rates. Comparar con baseline random: WR~55-58% a 20d.")
print("\nDONE.")