#!/usr/bin/env python3
"""
Forensia Profunda del Zigzag — López de Prado + Equipo de Data Science
========================================================================
1. Validación del zigzag: alternancia, distribución, sanity checks
2. Estructura de tendencia: HH/HL vs LH/LL, clasificación de tramos
3. Delta entre picos y valles: ¿qué predice la magnitud del siguiente tramo?
4. Features PRE-GIRO: perfil completo N bars antes de cada turning point
5. Predicción de piernas: ¿se puede anticipar la magnitud del siguiente swing?
6. Ortogonalidades adicionales: PCA de features pre-turn
7. Validación cruzada de conclusiones previas

"The goal is not to predict — it is to discover structure."
— Marcos López de Prado
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
from scipy import stats as sp_stats
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore


def banner(t):
    print(f"\n{'═' * 100}")
    print(f"  {t}")
    print(f"{'═' * 100}")


def section(t):
    print(f"\n  ── {t} ──")


def main():
    banner("FORENSIA PROFUNDA DEL ZIGZAG — López de Prado & Equipo")
    store = TimescaleDataStore()

    # Load data
    zz = pd.read_sql("""
        SELECT * FROM engine.zigzag_points
        WHERE min_swing_pct = 0.05
        ORDER BY ticker, timestamp
    """, store.engine)
    tape = pd.read_sql("SELECT * FROM engine.signal_tape ORDER BY ticker, timestamp", store.engine)
    print(f"  Zigzag 5%: {len(zz):,d} points")
    print(f"  Signal tape: {len(tape):,d} rows")

    # ═══════════════════════════════════════════════════════════
    # 1. VALIDACIÓN DEL ZIGZAG
    # ═══════════════════════════════════════════════════════════
    banner("1. VALIDACIÓN DEL ZIGZAG")

    section("1a. Alternancia MIN/MAX")
    violations = 0
    for tk in zz['ticker'].unique():
        tkz = zz[zz['ticker'] == tk].sort_values('timestamp')
        types = tkz['tp_type'].values
        for i in range(1, len(types)):
            if types[i] == types[i-1]:
                violations += 1
    print(f"    Violaciones de alternancia: {violations}")
    print(f"    Status: {'✅ PERFECTO' if violations == 0 else '❌ HAY PROBLEMAS'}")

    section("1b. Distribución de swings")
    for tp in ['MIN', 'MAX']:
        sub = zz[zz['tp_type'] == tp].dropna(subset=['swing_return'])
        pct = sub['swing_return'] * 100
        days = sub['swing_days']
        label = "UP legs (MIN→)" if tp == 'MIN' else "DOWN legs (MAX→)"
        print(f"    {label}:")
        print(f"      N={len(sub):,d}  mean={pct.mean():+.1f}%  std={pct.std():.1f}%  "
              f"P25={pct.quantile(0.25):+.1f}%  P50={pct.median():+.1f}%  P75={pct.quantile(0.75):+.1f}%")
        print(f"      Days: mean={days.mean():.0f}  P25={days.quantile(0.25):.0f}  "
              f"P50={days.median():.0f}  P75={days.quantile(0.75):.0f}")

    section("1c. Swing mínimo verificado")
    for tp in ['MIN', 'MAX']:
        sub = zz[zz['tp_type'] == tp].dropna(subset=['swing_return'])
        abs_ret = sub['swing_return'].abs()
        below_5 = (abs_ret < 0.05).sum()
        print(f"    {tp}: swings < 5% absoluto = {below_5} ({below_5/len(sub)*100:.1f}%)")

    # ═══════════════════════════════════════════════════════════
    # 2. ESTRUCTURA DE TENDENCIA: HH/HL vs LH/LL
    # ═══════════════════════════════════════════════════════════
    banner("2. ESTRUCTURA DE TENDENCIA — Higher/Lower Highs & Lows")

    all_structures = []
    for tk in sorted(zz['ticker'].unique()):
        tkz = zz[zz['ticker'] == tk].sort_values('timestamp').reset_index(drop=True)
        mins = tkz[tkz['tp_type'] == 'MIN'].reset_index(drop=True)
        maxs = tkz[tkz['tp_type'] == 'MAX'].reset_index(drop=True)

        for i in range(1, len(mins)):
            hh_hl = mins.iloc[i]['price'] > mins.iloc[i-1]['price']  # Higher Low
            label = 'HL' if hh_hl else 'LL'
            # Next leg info
            next_leg = mins.iloc[i].get('swing_return')
            all_structures.append({
                'ticker': tk, 'timestamp': mins.iloc[i]['timestamp'],
                'type': 'LOW', 'pattern': label,
                'price': mins.iloc[i]['price'],
                'prev_price': mins.iloc[i-1]['price'],
                'delta_pct': (mins.iloc[i]['price'] / mins.iloc[i-1]['price'] - 1) * 100,
                'next_leg_return': next_leg,
                'next_leg_days': mins.iloc[i].get('swing_days'),
            })

        for i in range(1, len(maxs)):
            hh = maxs.iloc[i]['price'] > maxs.iloc[i-1]['price']
            label = 'HH' if hh else 'LH'
            next_leg = maxs.iloc[i].get('swing_return')
            all_structures.append({
                'ticker': tk, 'timestamp': maxs.iloc[i]['timestamp'],
                'type': 'HIGH', 'pattern': label,
                'price': maxs.iloc[i]['price'],
                'prev_price': maxs.iloc[i-1]['price'],
                'delta_pct': (maxs.iloc[i]['price'] / maxs.iloc[i-1]['price'] - 1) * 100,
                'next_leg_return': next_leg,
                'next_leg_days': maxs.iloc[i].get('swing_days'),
            })

    sdf = pd.DataFrame(all_structures)

    section("2a. Distribución de patrones")
    print(f"  {'Pattern':>8s} │ {'N':>6s} │ {'Delta%':>7s} │ {'NextLeg%':>9s} │ {'NextDays':>8s} │ Significado")
    print(f"  {'─'*75}")
    for pat in ['HL', 'LL', 'HH', 'LH']:
        sub = sdf[sdf['pattern'] == pat].dropna(subset=['next_leg_return'])
        if len(sub) < 10:
            continue
        meaning = {
            'HL': 'Higher Low → uptrend continues',
            'LL': 'Lower Low → downtrend deepens',
            'HH': 'Higher High → uptrend extends',
            'LH': 'Lower High → reversal/weakness',
        }[pat]
        print(f"  {pat:>8s} │ {len(sub):>6,d} │ {sub['delta_pct'].mean():>+6.1f}% │ "
              f"{sub['next_leg_return'].mean()*100:>+8.1f}% │ {sub['next_leg_days'].median():>7.0f}d │ {meaning}")

    section("2b. Secuencias de tendencia")
    # Uptrend = HH + HL, Downtrend = LH + LL
    combo_stats = []
    for tk in sorted(sdf['ticker'].unique()):
        tks = sdf[sdf['ticker'] == tk].sort_values('timestamp')
        for i in range(1, len(tks)):
            prev_pat = tks.iloc[i-1]['pattern']
            curr_pat = tks.iloc[i]['pattern']
            combo = f"{prev_pat}→{curr_pat}"
            combo_stats.append({
                'combo': combo,
                'next_leg': tks.iloc[i].get('next_leg_return'),
            })

    cdf = pd.DataFrame(combo_stats).dropna()
    print(f"\n  {'Sequence':>10s} │ {'N':>5s} │ {'Next Leg':>9s} │ {'P(>0)':>6s} │ Interpretation")
    print(f"  {'─'*65}")
    for combo in sorted(cdf['combo'].unique()):
        sub = cdf[cdf['combo'] == combo]
        if len(sub) < 20:
            continue
        nlr = sub['next_leg'].mean() * 100
        ppos = (sub['next_leg'] > 0).mean() * 100
        if 'HH' in combo and 'HL' in combo:
            interp = "🟢 STRONG UPTREND"
        elif 'LL' in combo and 'LH' in combo:
            interp = "🔴 STRONG DOWNTREND"
        elif 'HL→LH' in combo or 'HH→LH' in combo:
            interp = "🟡 TOPPING"
        elif 'LL→HL' in combo or 'LH→HL' in combo:
            interp = "�� BOTTOMING"
        else:
            interp = ""
        print(f"  {combo:>10s} │ {len(sub):>5d} │ {nlr:>+8.2f}% │ {ppos:>5.1f}% │ {interp}")

    # ═══════════════════════════════════════════════════════════
    # 3. DELTA ENTRE PICOS/VALLES → PREDICCIÓN
    # ═══════════════════════════════════════════════════════════
    banner("3. DELTA ANALYSIS — ¿El tamaño del swing predice el siguiente?")

    section("3a. Autocorrelación de swings")
    for tp, label in [('MIN', 'UP legs'), ('MAX', 'DOWN legs')]:
        for tk in ['SPY', 'QQQ', 'AAPL']:
            tkz = zz[(zz['ticker'] == tk) & (zz['tp_type'] == tp)].dropna(subset=['swing_return'])
            rets = tkz['swing_return'].values
            if len(rets) > 20:
                ac1 = pd.Series(rets).autocorr(lag=1)
                ac2 = pd.Series(rets).autocorr(lag=2)
                print(f"    {tk:>5s} {label}: AC(1)={ac1:+.3f}  AC(2)={ac2:+.3f}  "
                      f"{'→ Predictable' if abs(ac1) > 0.15 else '→ Random'}")

    section("3b. ¿Swings grandes preceden swings grandes? (volatility clustering)")
    for tp in ['MIN', 'MAX']:
        sub = zz[zz['tp_type'] == tp].dropna(subset=['swing_return']).copy()
        sub['abs_swing'] = sub['swing_return'].abs()
        sub['prev_abs_swing'] = sub.groupby('ticker')['abs_swing'].shift(1)
        valid = sub.dropna(subset=['prev_abs_swing'])
        if len(valid) > 50:
            corr = valid['abs_swing'].corr(valid['prev_abs_swing'])
            label = "UP" if tp == 'MIN' else "DOWN"
            print(f"    {label} legs: corr(|swing_t|, |swing_t-1|) = {corr:+.3f} "
                  f"{'★ CLUSTERS' if corr > 0.2 else ''}")

    section("3c. ¿La duración predice el retorno?")
    for tp in ['MIN', 'MAX']:
        sub = zz[zz['tp_type'] == tp].dropna(subset=['swing_return', 'swing_days'])
        corr = sub['swing_days'].corr(sub['swing_return'].abs())
        label = "UP" if tp == 'MIN' else "DOWN"
        print(f"    {label}: corr(days, |return|) = {corr:+.3f}")

    # ═══════════════════════════════════════════════════════════
    # 4. FEATURES PRE-GIRO — Perfil completo
    # ═══════════════════════════════════════════════════════════
    banner("4. FEATURE PROFILE PRE-TURN — ¿Qué ve el modelo antes del giro?")

    FEATURES = ['fear_level', 'rsi_value', 'kalman_velocity', 'sigma_tide',
                'sigma_wave', 'compression_ratio', 'vol_up_down_ratio',
                'tide_slope', 'current_slope', 'wave_slope',
                'p_long_entry', 'p_swing_exit', 'p_pullback_depth',
                'p_short_entry', 'p_short_cover', 'p_bounce_height',
                'p_trend_reversal', 'p_trend_recovery']

    for tp_type, desc in [('MIN', 'ANTES DE MINIMA'), ('MAX', 'ANTES DE MAXIMA')]:
        section(f"4.{tp_type}: Perfil promedio {desc} (bars -5 a -1)")

        tp_sub = zz[zz['tp_type'] == tp_type]
        profiles_at_turn = []
        profiles_normal = []

        for _, tp_row in tp_sub.iterrows():
            tk_tape = tape[tape['ticker'] == tp_row['ticker']].sort_values('timestamp').reset_index(drop=True)
            time_diff = (tk_tape['timestamp'] - tp_row['timestamp']).abs()
            if len(time_diff) == 0 or time_diff.min() > pd.Timedelta(days=3):
                continue
            center = time_diff.idxmin()
            if center < 5:
                continue

            # Pre-turn window: bars -5 to -1
            pre = tk_tape.iloc[center - 5: center]
            for col in FEATURES:
                if col in pre.columns:
                    val = pre[col].mean()
                    if not np.isnan(val):
                        profiles_at_turn.append({'feature': col, 'value': val})

            # Normal window: 50 bars before (baseline)
            if center > 55:
                norm = tk_tape.iloc[center - 55: center - 50]
                for col in FEATURES:
                    if col in norm.columns:
                        val = norm[col].mean()
                        if not np.isnan(val):
                            profiles_normal.append({'feature': col, 'value': val})

        at_df = pd.DataFrame(profiles_at_turn)
        nm_df = pd.DataFrame(profiles_normal)

        print(f"  {'Feature':>22s} │ {'Pre-turn':>9s} │ {'Normal':>9s} │ {'Delta':>9s} │ {'StdDev':>7s} │ Significance")
        print(f"  {'─'*80}")

        for col in FEATURES:
            at_vals = at_df[at_df['feature'] == col]['value']
            nm_vals = nm_df[nm_df['feature'] == col]['value']
            if len(at_vals) < 50 or len(nm_vals) < 50:
                continue
            at_mean = at_vals.mean()
            nm_mean = nm_vals.mean()
            delta = at_mean - nm_mean
            pooled_std = np.sqrt((at_vals.std()**2 + nm_vals.std()**2) / 2)
            effect_size = delta / pooled_std if pooled_std > 0 else 0
            _, pval = sp_stats.mannwhitneyu(at_vals, nm_vals, alternative='two-sided')

            if pval < 0.001 and abs(effect_size) > 0.2:
                sig = f"★★★ d={effect_size:+.2f}"
            elif pval < 0.01:
                sig = f"★★  d={effect_size:+.2f}"
            elif pval < 0.05:
                sig = f"★   d={effect_size:+.2f}"
            else:
                sig = f"ns  d={effect_size:+.2f}"

            print(f"  {col:>22s} │ {at_mean:>9.3f} │ {nm_mean:>9.3f} │ {delta:>+8.3f} │ {pooled_std:>7.3f} │ {sig}")

    # ═══════════════════════════════════════════════════════════
    # 5. NEXT LEG PREDICTION — ¿Qué features predicen la magnitud?
    # ═══════════════════════════════════════════════════════════
    banner("5. NEXT LEG PREDICTION — ¿Qué predice el tamaño del próximo tramo?")

    for tp_type, desc in [('MIN', 'UP LEG after MIN'), ('MAX', 'DOWN LEG after MAX')]:
        section(f"5.{tp_type}: Correlación features @ turn → next leg return")

        tp_sub = zz[zz['tp_type'] == tp_type].dropna(subset=['swing_return'])
        rows = []

        for _, tp_row in tp_sub.iterrows():
            tk_tape = tape[tape['ticker'] == tp_row['ticker']].sort_values('timestamp').reset_index(drop=True)
            time_diff = (tk_tape['timestamp'] - tp_row['timestamp']).abs()
            if len(time_diff) == 0 or time_diff.min() > pd.Timedelta(days=3):
                continue
            center = time_diff.idxmin()
            if center < 1:
                continue

            row = {'next_leg': tp_row['swing_return'], 'next_days': tp_row['swing_days']}
            bar = tk_tape.iloc[center]
            for col in FEATURES:
                if col in tk_tape.columns:
                    row[col] = bar[col]
            rows.append(row)

        pred_df = pd.DataFrame(rows).dropna(subset=['next_leg'])

        print(f"  {'Feature':>22s} │ {'r(return)':>10s} │ {'r(days)':>10s} │ {'r(speed)':>10s} │ Predictive?")
        print(f"  {'─'*75}")

        pred_df['next_speed'] = pred_df['next_leg'] / pred_df['next_days'].clip(lower=1)
        results = []
        for col in FEATURES:
            if col not in pred_df.columns:
                continue
            valid = pred_df[[col, 'next_leg', 'next_days', 'next_speed']].dropna()
            if len(valid) < 50:
                continue
            r_ret = valid[col].corr(valid['next_leg'])
            r_days = valid[col].corr(valid['next_days'])
            r_speed = valid[col].corr(valid['next_speed'])
            predictive = "★" if abs(r_ret) > 0.1 or abs(r_speed) > 0.1 else ""
            results.append((col, r_ret, r_days, r_speed, predictive))

        results.sort(key=lambda x: -abs(x[1]))
        for col, rr, rd, rs, pred in results:
            print(f"  {col:>22s} │ {rr:>+9.4f} │ {rd:>+9.4f} │ {rs:>+9.4f} │ {pred}")

    # ═══════════════════════════════════════════════════════════
    # 6. PCA — Dimensiones latentes pre-giro
    # ═══════════════════════════════════════════════════════════
    banner("6. PCA — Dimensiones Latentes Pre-Giro")

    # Build feature matrix at zigzag points
    pca_rows = []
    for _, tp_row in zz.iterrows():
        tk_tape = tape[tape['ticker'] == tp_row['ticker']].sort_values('timestamp').reset_index(drop=True)
        time_diff = (tk_tape['timestamp'] - tp_row['timestamp']).abs()
        if len(time_diff) == 0 or time_diff.min() > pd.Timedelta(days=3):
            continue
        center = time_diff.idxmin()
        bar = tk_tape.iloc[center]
        row = {'tp_type': tp_row['tp_type']}
        for col in FEATURES:
            if col in tk_tape.columns:
                row[col] = bar[col]
        pca_rows.append(row)

    pca_df = pd.DataFrame(pca_rows)
    feat_cols = [c for c in FEATURES if c in pca_df.columns]
    X = pca_df[feat_cols].dropna()

    if len(X) > 100:
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        pca = PCA(n_components=min(8, len(feat_cols)))
        pca.fit(X_scaled)

        section("6a. Varianza explicada")
        cum = 0
        for i, var in enumerate(pca.explained_variance_ratio_):
            cum += var
            print(f"    PC{i+1}: {var*100:5.1f}%  (cumulative: {cum*100:5.1f}%)")

        section("6b. Composición de las primeras 4 PCs")
        for pc_idx in range(min(4, len(pca.components_))):
            loadings = pd.Series(pca.components_[pc_idx], index=feat_cols)
            top = loadings.abs().nlargest(5)
            components = ", ".join([f"{feat}({loadings[feat]:+.2f})" for feat in top.index])
            print(f"    PC{pc_idx+1} ({pca.explained_variance_ratio_[pc_idx]*100:.1f}%): {components}")

        section("6c. Separación MIN vs MAX en PCA space")
        X_pca = pca.transform(X_scaled)
        types = pca_df.loc[X.index, 'tp_type'].values
        for pc_idx in range(min(4, X_pca.shape[1])):
            min_vals = X_pca[types == 'MIN', pc_idx]
            max_vals = X_pca[types == 'MAX', pc_idx]
            _, pval = sp_stats.mannwhitneyu(min_vals, max_vals, alternative='two-sided')
            effect = (min_vals.mean() - max_vals.mean()) / np.sqrt((min_vals.std()**2 + max_vals.std()**2)/2)
            sep = "★★★" if pval < 0.001 and abs(effect) > 0.3 else "★★" if pval < 0.01 else "ns"
            print(f"    PC{pc_idx+1}: MIN={min_vals.mean():+.3f}  MAX={max_vals.mean():+.3f}  "
                  f"d={effect:+.3f}  p={pval:.4f}  {sep}")

    # ═══════════════════════════════════════════════════════════
    # 7. PLAN DE TRABAJO
    # ═══════════════════════════════════════════════════════════
    banner("7. CONCLUSIONES Y PLAN — López de Prado")

    print("""
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  Las conclusiones y el plan de trabajo se construirán                      │
  │  a partir de los datos anteriores en el dictamen forense.                  │
  │  Los datos hablan — nosotros interpretamos.                               │
  └─────────────────────────────────────────────────────────────────────────────┘
    """)

    store.close()
    banner("FORENSIA COMPLETA")


if __name__ == "__main__":
    main()
