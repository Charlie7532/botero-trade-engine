#!/usr/bin/env python3
"""
ESTUDIO WINS vs LOSSES — SV5T, VIX, BSI, CREDIT (ENTRY #4-7)
==============================================================
Análisis completo de 7 dimensiones por estación meteorológica.
State_key del METAR (D1__D2__D3), CI95 bootstrap 2000.
NO promedia — separa MIN/MAX. D3 = std(2)/std(10).
"""

import pickle, json, sys
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict, Counter

# ─── Bootstrap ──────────────────────────────────────────────
def bootstrap_ci(data, stat_fn=np.mean, n_iter=2000, seed=42):
    rng = np.random.RandomState(seed)
    d = np.asarray(data, float)
    n = len(d)
    if n < 5:
        return stat_fn(d), np.nan, np.nan, n
    stats = np.array([stat_fn(rng.choice(d, n, replace=True)) for _ in range(n_iter)])
    return stat_fn(d), np.percentile(stats, 2.5), np.percentile(stats, 97.5), n

def bootstrap_proportion(wins, n_iter=2000, seed=42):
    rng = np.random.RandomState(seed)
    w = np.asarray(wins, float)
    n = len(w)
    if n < 5:
        return np.mean(w), np.nan, np.nan, n
    props = np.array([rng.choice(w, n, replace=True).mean() for _ in range(n_iter)])
    return np.mean(w), np.percentile(props, 2.5), np.percentile(props, 97.5), n

# ─── Load data ──────────────────────────────────────────────
PROJECT_ROOT = Path('/root/botero-trade')
sys.path.insert(0, str(PROJECT_ROOT / 'backend'))

df = pd.read_pickle(PROJECT_ROOT / 'data/research/pivots/quants_obs.pkl')
df['next_leg_return'] = df['prev_leg_return'].shift(-1)

# Win condition
df['win'] = np.where(df['pivot_type'] == 'MIN', df['next_leg_return'] > 0, df['next_leg_return'] < 0)
# PnL signed correctly
df['pnl'] = np.where(df['pivot_type'] == 'MIN', df['next_leg_return'], -df['next_leg_return'])

STATIONS = {
    'SV5T':  {'prefix': 'sv5_turbulence', 'extreme_d1': 'CRISIS_TURBULENCE', 'ticker': 'SV5_TURBULENCE'},
    'VIX':   {'prefix': 'vix',            'extreme_d1': 'CRISIS_SPIKE',       'ticker': 'VIX'},
    'BSI':   {'prefix': 'bsi',            'extreme_d1': 'BREADTH_WASHED_OUT', 'ticker': 'S5TW'},
    'CREDIT':{'prefix': 'credit',         'extreme_d1': 'CREDIT_STRESS',      'ticker': 'HYG+LQD'},
}


def _fmt_pct(x):
    if np.isnan(x): return 'N/A'
    return f'{x*100:.2f}%'

def _fmt_ci(lo, hi):
    if np.isnan(lo): return 'N/A'
    return f'[{lo*100:.1f}%, {hi*100:.1f}%]'


def analyze_station_full(df, name, cfg):
    """Full 7-dim analysis. Returns structured dict and prints report."""
    pfx = cfg['prefix']
    ext_d1 = cfg['extreme_d1']
    sk_col = f'{pfx}_sk'
    val_col = f'{pfx}_val'
    vel_col = f'{pfx}_vel'
    vol_col = f'{pfx}_vol'

    # ── Masks ──
    sk_s = df[sk_col].fillna('')
    ext_mask = sk_s.str.startswith(ext_d1) & (sk_s != '')
    base_mask = ~sk_s.str.startswith(ext_d1) & (sk_s != '')
    ext_df = df[ext_mask].copy()
    base_df = df[base_mask].copy()

    R = {'station': name, 'extreme_d1': ext_d1}

    for pt in ['MIN', 'MAX']:
        sub = ext_df[ext_df['pivot_type'] == pt].dropna(subset=['next_leg_return'])
        sub_b = base_df[base_df['pivot_type'] == pt].dropna(subset=['next_leg_return'])

        R[f'{pt}_N'] = len(sub)
        if len(sub) < 3:
            R[f'{pt}_insufficient'] = True
            continue

        wins_a = sub['win'].values.astype(float)
        pnl_a = sub['pnl'].values
        
        # ── A. Win Rate + CI95 ──
        wr, wr_lo, wr_hi, _ = bootstrap_proportion(wins_a)
        R[f'{pt}_A_wr'] = wr
        R[f'{pt}_A_ci95'] = [wr_lo, wr_hi]
        bl_w, bl_lo, bl_hi, _ = bootstrap_proportion(sub_b['win'].values.astype(float)) if len(sub_b) >= 5 else (np.nan, np.nan, np.nan, _)
        R[f'{pt}_A_wr_baseline'] = bl_w
        R[f'{pt}_A_wr_delta'] = wr - bl_w if not np.isnan(bl_w) else np.nan

        # ── B. WINS distribution ──
        w_ret = sub.loc[sub['win'], 'pnl'].values
        l_ret = sub.loc[~sub['win'], 'pnl'].values
        R[f'{pt}_B_n'] = len(w_ret)
        R[f'{pt}_B_mean'] = np.mean(w_ret) if len(w_ret) else np.nan
        R[f'{pt}_B_median'] = np.median(w_ret) if len(w_ret) else np.nan
        R[f'{pt}_B_std'] = np.std(w_ret) if len(w_ret) else np.nan
        R[f'{pt}_B_max'] = np.max(w_ret) if len(w_ret) else np.nan
        R[f'{pt}_B_p25'] = np.percentile(w_ret, 25) if len(w_ret) >= 4 else np.nan
        R[f'{pt}_B_p75'] = np.percentile(w_ret, 75) if len(w_ret) >= 4 else np.nan
        if len(w_ret) >= 10:
            R[f'{pt}_B_deciles'] = [np.percentile(w_ret, p) for p in [10, 20, 30, 40, 50, 60, 70, 80, 90]]

        # ── C. LOSSES distribution ──
        R[f'{pt}_C_n'] = len(l_ret)
        R[f'{pt}_C_mean'] = np.mean(l_ret) if len(l_ret) else np.nan
        R[f'{pt}_C_median'] = np.median(l_ret) if len(l_ret) else np.nan
        R[f'{pt}_C_maxloss'] = np.min(l_ret) if len(l_ret) else np.nan
        R[f'{pt}_C_std'] = np.std(l_ret) if len(l_ret) else np.nan
        # Wipeouts >20%
        wipes = l_ret[l_ret < -0.20] if len(l_ret) else np.array([])
        R[f'{pt}_C_wipeouts_n'] = len(wipes)
        R[f'{pt}_C_wipeouts_pct'] = len(wipes) / len(sub) * 100
        R[f'{pt}_C_wipeouts_list'] = wipes.tolist()
        # Distribution of losses
        if len(l_ret) >= 5:
            for pct in [10, 25, 50, 75, 90]:
                R[f'{pt}_C_loss_p{pct}'] = np.percentile(l_ret, pct)

        # ── D. Profit Factor, Kelly, EV ──
        gross_win = np.sum(w_ret) if len(w_ret) else 0
        gross_loss = abs(np.sum(l_ret)) if len(l_ret) else 0
        pf = gross_win / gross_loss if gross_loss > 0 else float('inf')
        R[f'{pt}_D_profit_factor'] = pf
        mw = np.mean(w_ret) if len(w_ret) else 0
        ml = abs(np.mean(l_ret)) if len(l_ret) else 0
        wlr = mw / ml if ml > 0 else float('inf')
        R[f'{pt}_D_avg_win_loss_ratio'] = wlr
        kelly = wr - (1 - wr) / wlr if (ml > 0 and wlr > 0) else -1.0
        R[f'{pt}_D_kelly'] = kelly
        ev, ev_lo, ev_hi, _ = bootstrap_ci(pnl_a)
        R[f'{pt}_D_ev'] = ev
        R[f'{pt}_D_ev_ci95'] = [ev_lo, ev_hi]
        shrp = ev / np.std(pnl_a) if np.std(pnl_a) > 0 else 0
        R[f'{pt}_D_sharpe'] = shrp

        # ── E. Rachas ──
        streaks = []
        ctype, clen = None, 0
        for w in wins_a:
            if w == ctype:
                clen += 1
            else:
                if ctype is not None:
                    streaks.append((int(ctype), clen))
                ctype, clen = w, 1
        if ctype is not None:
            streaks.append((int(ctype), clen))
        w_streaks = [s[1] for s in streaks if s[0] == 1]
        l_streaks = [s[1] for s in streaks if s[0] == 0]
        R[f'{pt}_E_max_win_streak'] = max(w_streaks) if w_streaks else 0
        R[f'{pt}_E_max_loss_streak'] = max(l_streaks) if l_streaks else 0
        R[f'{pt}_E_avg_win_streak'] = np.mean(w_streaks) if w_streaks else 0
        R[f'{pt}_E_avg_loss_streak'] = np.mean(l_streaks) if l_streaks else 0
        R[f'{pt}_E_streaks'] = [(int(s[0]), s[1]) for s in streaks]

        # ── F. Timing vs zigzag ──
        dr = sub['daily_return_pct'].values
        R[f'{pt}_F_pivot_day_mean'] = np.mean(dr)
        R[f'{pt}_F_pivot_day_std'] = np.std(dr)
        R[f'{pt}_F_pivot_day_median'] = np.median(dr)
        # Cost at pivot: |daily_return_pct|
        abs_cost = np.abs(dr)
        R[f'{pt}_F_abs_cost_mean'] = np.mean(abs_cost)
        # Same-day entry %: |return| < 1%
        R[f'{pt}_F_same_day_pct'] = np.mean(abs_cost < 0.01) * 100

        # ── G. Cuchillo cayendo (drawdown >5% antes del pivote) ──
        knife_mask = sub['daily_return_pct'] < -5.0
        knife = sub[knife_mask]
        R[f'{pt}_G_knife_n'] = len(knife)
        R[f'{pt}_G_knife_pct'] = len(knife) / len(sub) * 100

        if len(knife) > 0:
            R[f'{pt}_G_knife_dates'] = [str(d) for d in knife['pivot_date'].values]
            R[f'{pt}_G_knife_daily_ret'] = knife['daily_return_pct'].tolist()
            # Warning signals: what were other stations showing?
            R[f'{pt}_G_knife_vix_val'] = knife['vix_val'].tolist()
            R[f'{pt}_G_knife_vix_vel'] = knife['vix_vel'].tolist() if 'vix_vel' in df.columns else []
            R[f'{pt}_G_knife_vix_vol'] = knife['vix_vol'].tolist() if 'vix_vol' in df.columns else []
            R[f'{pt}_G_knife_bsi_val'] = knife['bsi_val'].tolist()
            R[f'{pt}_G_knife_credit_val'] = knife['credit_val'].tolist()
            R[f'{pt}_G_knife_cascade_50'] = knife['cascade_50'].tolist()
            # D2 velocity of this station at knife events
            if vel_col in df.columns:
                R[f'{pt}_G_knife_vel'] = knife[vel_col].tolist()
            if vol_col in df.columns:
                R[f'{pt}_G_knife_vol'] = knife[vol_col].tolist()

        # ── State_key breakdown ──
        sk_counts = sub[sk_col].value_counts()
        sk_metrics = {}
        for sk, cnt in sk_counts.head(15).items():
            sk_sub = sub[sub[sk_col] == sk]
            if len(sk_sub) < 3:
                continue
            sk_w = sk_sub['win'].mean()
            sk_ev = sk_sub['pnl'].mean()
            sk_metrics[sk] = {'n': cnt, 'wr': sk_w, 'ev': sk_ev, 'pnl_mean': sk_ev}
        R[f'{pt}_state_key_breakdown'] = sk_metrics

    # ── Print report ──
    print(f"\n{'='*70}")
    print(f"  {name} — {cfg['extreme_d1']} ({cfg['ticker']})")
    print(f"{'='*70}")

    for pt in ['MIN', 'MAX']:
        n = R.get(f'{pt}_N', 0)
        if n < 3:
            print(f"\n  {pt}: N={n} — INSUFICIENTE")
            continue

        print(f"\n  ═══ {pt} PIVOTS (N={n}) ═══")
        print(f"  ┌─ A. WIN RATE")
        print(f"  │   WR={R[f'{pt}_A_wr']:.1%}  CI95={_fmt_ci(R[f'{pt}_A_ci95'][0], R[f'{pt}_A_ci95'][1])}")
        print(f"  │   Baseline={R[f'{pt}_A_wr_baseline']:.1%}  Δ={R[f'{pt}_A_wr_delta']:+.1%}")
        print(f"  ├─ B. DISTRIBUCIÓN WINS (n={R[f'{pt}_B_n']})")
        print(f"  │   mean={R[f'{pt}_B_mean']:.3%}  median={R[f'{pt}_B_median']:.3%}")
        print(f"  │   p25={R[f'{pt}_B_p25']:.3%}  p75={R[f'{pt}_B_p75']:.3%}  max={R[f'{pt}_B_max']:.3%}")
        print(f"  ├─ C. DISTRIBUCIÓN LOSSES (n={R[f'{pt}_C_n']})")
        print(f"  │   mean={R[f'{pt}_C_mean']:.3%}  maxloss={R[f'{pt}_C_maxloss']:.3%}")
        print(f"  │   WIPEOUTS >20%: {R[f'{pt}_C_wipeouts_n']} ({R[f'{pt}_C_wipeouts_pct']:.1f}%)")
        if R[f'{pt}_C_wipeouts_list']:
            print(f"  │   → {R[f'{pt}_C_wipeouts_list']}")
        print(f"  ├─ D. MÉTRICAS DE RENTABILIDAD")
        print(f"  │   Profit Factor={R[f'{pt}_D_profit_factor']:.2f}  Kelly={R[f'{pt}_D_kelly']:.3f}")
        print(f"  │   EV={R[f'{pt}_D_ev']:.3%}  CI95={_fmt_ci(R[f'{pt}_D_ev_ci95'][0], R[f'{pt}_D_ev_ci95'][1])}")
        print(f"  │   Sharpe={R[f'{pt}_D_sharpe']:.3f}")
        print(f"  ├─ E. RACHAS")
        print(f"  │   Max win streak={R[f'{pt}_E_max_win_streak']}  max loss={R[f'{pt}_E_max_loss_streak']}")
        print(f"  │   Avg win={R[f'{pt}_E_avg_win_streak']:.1f}  avg loss={R[f'{pt}_E_avg_loss_streak']:.1f}")
        print(f"  ├─ F. TIMING VS ZIGZAG")
        print(f"  │   Pivot day return: mean={R[f'{pt}_F_pivot_day_mean']:.2f}%  median={R[f'{pt}_F_pivot_day_median']:.2f}%")
        print(f"  │   Costo al pivote: |return|={R[f'{pt}_F_abs_cost_mean']:.2f}%")
        print(f"  │   Mismo día (|<1%|): {R[f'{pt}_F_same_day_pct']:.0f}%")
        print(f"  └─ G. CUCHILLO CAYENDO (>5% drawdown)")
        print(f"      N={R[f'{pt}_G_knife_n']} ({R[f'{pt}_G_knife_pct']:.1f}%)")
        if R[f'{pt}_G_knife_n'] > 0:
            for i, dt in enumerate(R[f'{pt}_G_knife_dates'][:5]):
                ret = R[f'{pt}_G_knife_daily_ret'][i]
                vix = R[f'{pt}_G_knife_vix_val'][i] if i < len(R[f'{pt}_G_knife_vix_val']) else '?'
                print(f"      {dt}: ret={ret:.1f}%, VIX={vix}")

        # Top state_keys
        skbd = R[f'{pt}_state_key_breakdown']
        if skbd:
            print(f"\n  ── TOP STATE_KEYS (D1__D2__D3) ──")
            for sk, m in sorted(skbd.items(), key=lambda x: x[1]['n'], reverse=True)[:5]:
                print(f"  {sk}")
                print(f"    n={m['n']}, WR={m['wr']:.1%}, EV={m['ev']:.3%}")

    print()

    return R


# ─── Run all stations ───────────────────────────────────────
all_results = {}
for name, cfg in STATIONS.items():
    all_results[name] = analyze_station_full(df, name, cfg)

# ─── Comparative summary ────────────────────────────────────
print(f"\n{'='*70}")
print(f"  COMPARATIVO — MIN PIVOTS (ENTRY LONG EN EXTREMO FEAR)")
print(f"{'='*70}")
print(f"{'Station':<10} {'N':>4} {'WR':>7} {'CI95':>20} {'Δ vs BL':>8} {'EV':>7} {'PF':>6} {'Kelly':>7} {'MaxLoss':>7} {'Wipe>20%':>9} {'Knife%':>7}")
print(f"{'-'*10} {'-'*4} {'-'*7} {'-'*20} {'-'*8} {'-'*7} {'-'*6} {'-'*7} {'-'*7} {'-'*9} {'-'*7}")
for name, R in all_results.items():
    n = R.get('MIN_N', 0)
    if n < 3: continue
    wr = R['MIN_A_wr']
    ci = R['MIN_A_ci95']
    dlt = R['MIN_A_wr_delta']
    ev = R['MIN_D_ev']
    pf = R['MIN_D_profit_factor']
    kl = R['MIN_D_kelly']
    ml = R['MIN_C_maxloss']
    wo = R['MIN_C_wipeouts_pct']
    kn = R['MIN_G_knife_pct']
    print(f"{name:<10} {n:>4} {wr:>6.1%} [{ci[0]:.1%}, {ci[1]:.1%}] {dlt:>+7.1%} {ev:>6.2%} {pf:>5.2f} {kl:>+6.3f} {ml:>7.3%} {wo:>8.1f}% {kn:>6.1f}%")

print(f"\n{'='*70}")
print(f"  COMPARATIVO — MAX PIVOTS (SHORT EN TECHO CON CRISIS?)")
print(f"{'='*70}")
print(f"{'Station':<10} {'N':>4} {'WR':>7} {'CI95':>20} {'Δ vs BL':>8} {'EV':>7} {'PF':>6} {'Kelly':>7} {'Knife%':>7}")
print(f"{'-'*10} {'-'*4} {'-'*7} {'-'*20} {'-'*8} {'-'*7} {'-'*6} {'-'*7} {'-'*7}")
for name, R in all_results.items():
    n = R.get('MAX_N', 0)
    if n < 3: continue
    wr = R['MAX_A_wr']
    ci = R['MAX_A_ci95']
    dlt = R['MAX_A_wr_delta']
    ev = R['MAX_D_ev']
    pf = R['MAX_D_profit_factor']
    kl = R['MAX_D_kelly']
    kn = R['MAX_G_knife_pct']
    print(f"{name:<10} {n:>4} {wr:>6.1%} [{ci[0]:.1%}, {ci[1]:.1%}] {dlt:>+7.1%} {ev:>6.2%} {pf:>5.2f} {kl:>+6.3f} {kn:>6.1f}%")

# ─── Save ───────────────────────────────────────────────────
def ser(obj):
    if isinstance(obj, (np.integer,)): return int(obj)
    if isinstance(obj, (np.floating,)): return None if np.isnan(obj) else float(obj)
    if isinstance(obj, np.ndarray): return [ser(x) for x in obj]
    if isinstance(obj, list): return [ser(x) for x in obj]
    if isinstance(obj, dict): return {str(k): ser(v) for k, v in obj.items()}
    if isinstance(obj, tuple): return [ser(x) for x in obj]
    return obj

out = PROJECT_ROOT / 'data/research/signals/wins_losses_entry4_7_report.json'
with open(out, 'w') as f:
    json.dump(ser(all_results), f, indent=2, default=str)

print(f"\nFull report saved to: {out}")
print("DONE.")