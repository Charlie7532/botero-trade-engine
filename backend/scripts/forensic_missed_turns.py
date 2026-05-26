#!/usr/bin/env python3
"""
Forensia de Giros Perdidos — ¿Cuáles no detectamos y por qué?
===============================================================
Para cada turning point del zigzag 5%:
  1. ¿Nuestro modelo disparó señal en los N bars previos?
  2. Si NO → ¿por qué? ¿Qué features estaban en qué estado?
  3. ¿Era POSIBLE detectarlo o era un giro imprevisto?

Clasificación de giros perdidos:
  - DETECTABLE: Features mostraban patrón pero no alcanzaron threshold
  - PARTIALLY: Algunas señales presentes, no suficientes
  - UNPREDICTABLE: Ninguna feature anticipó el giro (evento exógeno)
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


def banner(t):
    print(f"\n{'═' * 100}")
    print(f"  {t}")
    print(f"{'═' * 100}")


def section(t):
    print(f"\n  ── {t} ──")


def main():
    banner("FORENSIA DE GIROS PERDIDOS")
    store = TimescaleDataStore()

    zz = pd.read_sql("""
        SELECT * FROM engine.zigzag_points
        WHERE min_swing_pct = 0.05
        ORDER BY ticker, timestamp
    """, store.engine)
    tape = pd.read_sql("SELECT * FROM engine.signal_tape ORDER BY ticker, timestamp", store.engine)

    # Detection parameters
    LOOK_BACK = 5      # bars before turn to check for signal
    THR_STRONG = 0.60   # strong signal threshold
    THR_WEAK = 0.50     # weak signal threshold

    # For MIN (bottom): we should have fired p_long_entry, p_trend_reversal, p_bounce_height
    # For MAX (top): we should have fired p_short_entry, p_swing_exit, p_trend_reversal

    LONG_HEADS = ['p_long_entry', 'p_trend_reversal', 'p_bounce_height', 'p_short_cover']
    SHORT_HEADS = ['p_short_entry', 'p_swing_exit', 'p_trend_reversal', 'p_pullback_depth']

    FEATURES = ['fear_level', 'rsi_value', 'kalman_velocity', 'sigma_wave',
                'compression_ratio', 'vol_up_down_ratio', 'tide_slope',
                'current_slope', 'wave_slope']

    results = []

    for _, tp_row in zz.iterrows():
        tk_tape = tape[tape['ticker'] == tp_row['ticker']].sort_values('timestamp').reset_index(drop=True)
        time_diff = (tk_tape['timestamp'] - tp_row['timestamp']).abs()
        if len(time_diff) == 0 or time_diff.min() > pd.Timedelta(days=3):
            continue
        center = time_diff.idxmin()

        if center < LOOK_BACK:
            continue

        # Window: N bars before the turn
        window = tk_tape.iloc[center - LOOK_BACK: center + 1]

        heads = LONG_HEADS if tp_row['tp_type'] == 'MIN' else SHORT_HEADS

        # Check if ANY head fired strong (>= THR_STRONG) in the window
        strong_fired = False
        weak_fired = False
        max_p_values = {}
        for h in heads:
            if h in window.columns:
                max_p = window[h].max()
                max_p_values[h] = max_p
                if max_p >= THR_STRONG:
                    strong_fired = True
                if max_p >= THR_WEAK:
                    weak_fired = True

        # Classify
        if strong_fired:
            classification = 'DETECTED'
        elif weak_fired:
            classification = 'PARTIAL'
        else:
            classification = 'MISSED'

        # Feature state at center (turn point)
        feat_state = {}
        bar_at_turn = tk_tape.iloc[center]
        for f in FEATURES:
            if f in tk_tape.columns:
                feat_state[f] = bar_at_turn[f]

        # Swing magnitude (how much was the subsequent move)
        swing_ret = tp_row['swing_return']
        swing_days = tp_row['swing_days']

        results.append({
            'ticker': tp_row['ticker'],
            'timestamp': tp_row['timestamp'],
            'tp_type': tp_row['tp_type'],
            'classification': classification,
            'swing_return': swing_ret,
            'swing_days': swing_days,
            **{f'max_p_{h}': max_p_values.get(h) for h in heads},
            **{f'feat_{f}': feat_state.get(f) for f in FEATURES},
        })

    rdf = pd.DataFrame(results)

    # ═══════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════
    banner("1. COBERTURA GENERAL")

    for tp in ['MIN', 'MAX']:
        sub = rdf[rdf['tp_type'] == tp]
        total = len(sub)
        det = (sub['classification'] == 'DETECTED').sum()
        par = (sub['classification'] == 'PARTIAL').sum()
        mis = (sub['classification'] == 'MISSED').sum()

        label = "PISOS (MIN)" if tp == 'MIN' else "TECHOS (MAX)"
        print(f"\n  {label}: {total} giros totales")
        print(f"    ✅ DETECTED (P≥{THR_STRONG}):  {det:>4d} ({det/total*100:5.1f}%)")
        print(f"    🟡 PARTIAL  (P≥{THR_WEAK}):    {par:>4d} ({par/total*100:5.1f}%)")
        print(f"    🔴 MISSED   (P<{THR_WEAK}):     {mis:>4d} ({mis/total*100:5.1f}%)")

    # ═══════════════════════════════════════════════════════════
    # PER TICKER
    # ═══════════════════════════════════════════════════════════
    banner("2. COBERTURA POR TICKER")

    for tp in ['MIN', 'MAX']:
        label = "PISOS" if tp == 'MIN' else "TECHOS"
        section(f"{label}")
        print(f"  {'Ticker':>6s} │ {'Total':>5s} │ {'Det':>4s} │ {'Part':>4s} │ {'Miss':>4s} │ {'Det%':>5s} │ {'Miss%':>5s} │ {'AvgSwing':>9s}")
        print(f"  {'─'*65}")

        for tk in sorted(rdf['ticker'].unique()):
            sub = rdf[(rdf['ticker'] == tk) & (rdf['tp_type'] == tp)]
            total = len(sub)
            if total < 5:
                continue
            det = (sub['classification'] == 'DETECTED').sum()
            par = (sub['classification'] == 'PARTIAL').sum()
            mis = (sub['classification'] == 'MISSED').sum()
            avg_sw = sub['swing_return'].abs().mean() * 100
            print(f"  {tk:>6s} │ {total:>5d} │ {det:>4d} │ {par:>4d} │ {mis:>4d} │ "
                  f"{det/total*100:>4.0f}% │ {mis/total*100:>4.0f}% │ {avg_sw:>+8.1f}%")

    # ═══════════════════════════════════════════════════════════
    # MISSED TURNS: WHY?
    # ═══════════════════════════════════════════════════════════
    banner("3. ANÁLISIS DE GIROS PERDIDOS — ¿POR QUÉ?")

    missed = rdf[rdf['classification'] == 'MISSED'].copy()

    section("3a. ¿Los giros perdidos son más pequeños?")
    for tp in ['MIN', 'MAX']:
        det = rdf[(rdf['tp_type'] == tp) & (rdf['classification'] == 'DETECTED')]
        mis = rdf[(rdf['tp_type'] == tp) & (rdf['classification'] == 'MISSED')]
        if len(det) > 10 and len(mis) > 10:
            label = "PISOS" if tp == 'MIN' else "TECHOS"
            print(f"    {label}:")
            print(f"      Detected swings: {det['swing_return'].abs().mean()*100:+.1f}% avg, "
                  f"{det['swing_days'].median():.0f}d median")
            print(f"      Missed swings:   {mis['swing_return'].abs().mean()*100:+.1f}% avg, "
                  f"{mis['swing_days'].median():.0f}d median")

    section("3b. Feature profile de giros PERDIDOS vs DETECTADOS")
    for tp in ['MIN', 'MAX']:
        label = "PISOS" if tp == 'MIN' else "TECHOS"
        det = rdf[(rdf['tp_type'] == tp) & (rdf['classification'] == 'DETECTED')]
        mis = rdf[(rdf['tp_type'] == tp) & (rdf['classification'] == 'MISSED')]
        if len(det) < 20 or len(mis) < 20:
            continue

        print(f"\n    {label}:")
        print(f"    {'Feature':>22s} │ {'Detected':>9s} │ {'Missed':>9s} │ {'Delta':>9s} │ Interpretation")
        print(f"    {'─'*70}")

        for f in FEATURES:
            col = f'feat_{f}'
            if col not in rdf.columns:
                continue
            d_val = det[col].mean()
            m_val = mis[col].mean()
            if np.isnan(d_val) or np.isnan(m_val):
                continue
            delta = m_val - d_val
            pooled = np.sqrt((det[col].std()**2 + mis[col].std()**2) / 2)
            d_cohen = delta / pooled if pooled > 0 else 0

            if abs(d_cohen) > 0.3:
                interp = f"★★ d={d_cohen:+.2f}"
            elif abs(d_cohen) > 0.15:
                interp = f"★  d={d_cohen:+.2f}"
            else:
                interp = f"   d={d_cohen:+.2f}"

            print(f"    {f:>22s} │ {d_val:>9.3f} │ {m_val:>9.3f} │ {delta:>+8.3f} │ {interp}")

    # ═══════════════════════════════════════════════════════════
    # HH/HL CONTEXT
    # ═══════════════════════════════════════════════════════════
    banner("4. CONTEXTO ESTRUCTURAL DE GIROS PERDIDOS")

    section("4a. ¿Los perdidos ocurren más en HH/HL o LH/LL?")
    # For each missed turn, determine if it was HH/HL/LH/LL
    for tp in ['MIN', 'MAX']:
        tp_sub = zz[(zz['tp_type'] == tp) & (zz['min_swing_pct'] == 0.05)]
        for tk in sorted(rdf['ticker'].unique()):
            tkz = tp_sub[tp_sub['ticker'] == tk].sort_values('timestamp').reset_index(drop=True)
            for i in range(1, len(tkz)):
                ts = tkz.iloc[i]['timestamp']
                match = rdf[(rdf['ticker'] == tk) & (rdf['timestamp'] == ts) & (rdf['tp_type'] == tp)]
                if len(match) == 0:
                    continue
                idx = match.index[0]
                if tp == 'MIN':
                    pattern = 'HL' if tkz.iloc[i]['price'] > tkz.iloc[i-1]['price'] else 'LL'
                else:
                    pattern = 'HH' if tkz.iloc[i]['price'] > tkz.iloc[i-1]['price'] else 'LH'
                rdf.loc[idx, 'structure'] = pattern

    for tp in ['MIN', 'MAX']:
        label = "PISOS" if tp == 'MIN' else "TECHOS"
        sub = rdf[(rdf['tp_type'] == tp) & rdf['structure'].notna()]
        if len(sub) < 20:
            continue
        print(f"\n    {label}:")
        print(f"    {'Pattern':>8s} │ {'Total':>5s} │ {'Detected':>8s} │ {'Missed':>8s} │ {'MissRate':>8s}")
        print(f"    {'─'*50}")
        for pat in sorted(sub['structure'].unique()):
            ps = sub[sub['structure'] == pat]
            total = len(ps)
            det = (ps['classification'] == 'DETECTED').sum()
            mis = (ps['classification'] == 'MISSED').sum()
            print(f"    {pat:>8s} │ {total:>5d} │ {det:>8d} │ {mis:>8d} │ {mis/total*100:>6.1f}%")

    # ═══════════════════════════════════════════════════════════
    # WORST MISSES
    # ═══════════════════════════════════════════════════════════
    banner("5. PEORES GIROS PERDIDOS — Los que más dolieron")

    section("5a. Biggest missed MIN (dejamos de comprar en el piso)")
    missed_min = missed[missed['tp_type'] == 'MIN'].dropna(subset=['swing_return'])
    missed_min = missed_min.sort_values('swing_return', ascending=False)
    print(f"  {'Ticker':>6s} │ {'Date':>12s} │ {'NextUp%':>8s} │ {'Days':>5s} │ {'fear':>5s} │ {'rsi':>5s} │ {'kalman':>7s}")
    print(f"  {'─'*60}")
    for _, r in missed_min.head(20).iterrows():
        ts = pd.Timestamp(r['timestamp']).strftime('%Y-%m-%d')
        fear = f"{r.get('feat_fear_level', np.nan):.2f}" if not np.isnan(r.get('feat_fear_level', np.nan)) else "n/a"
        rsi = f"{r.get('feat_rsi_value', np.nan):.0f}" if not np.isnan(r.get('feat_rsi_value', np.nan)) else "n/a"
        kal = f"{r.get('feat_kalman_velocity', np.nan):+.3f}" if not np.isnan(r.get('feat_kalman_velocity', np.nan)) else "n/a"
        print(f"  {r['ticker']:>6s} │ {ts:>12s} │ {r['swing_return']*100:>+7.1f}% │ {r.get('swing_days', 0):>5.0f} │ {fear:>5s} │ {rsi:>5s} │ {kal:>7s}")

    section("5b. Biggest missed MAX (dejamos de vender en el techo)")
    missed_max = missed[missed['tp_type'] == 'MAX'].dropna(subset=['swing_return'])
    missed_max = missed_max.sort_values('swing_return', ascending=True)
    print(f"  {'Ticker':>6s} │ {'Date':>12s} │ {'NextDn%':>8s} │ {'Days':>5s} │ {'fear':>5s} │ {'rsi':>5s} │ {'kalman':>7s}")
    print(f"  {'─'*60}")
    for _, r in missed_max.head(20).iterrows():
        ts = pd.Timestamp(r['timestamp']).strftime('%Y-%m-%d')
        fear = f"{r.get('feat_fear_level', np.nan):.2f}" if not np.isnan(r.get('feat_fear_level', np.nan)) else "n/a"
        rsi = f"{r.get('feat_rsi_value', np.nan):.0f}" if not np.isnan(r.get('feat_rsi_value', np.nan)) else "n/a"
        kal = f"{r.get('feat_kalman_velocity', np.nan):+.3f}" if not np.isnan(r.get('feat_kalman_velocity', np.nan)) else "n/a"
        print(f"  {r['ticker']:>6s} │ {ts:>12s} │ {r['swing_return']*100:>+7.1f}% │ {r.get('swing_days', 0):>5.0f} │ {fear:>5s} │ {rsi:>5s} │ {kal:>7s}")

    # ═══════════════════════════════════════════════════════════
    # DETECTABILITY CLASSIFICATION
    # ═══════════════════════════════════════════════════════════
    banner("6. CLASIFICACIÓN DE DETECTABILIDAD")
    print("  ¿Era POSIBLE detectar los giros perdidos?")

    # A missed turn is DETECTABLE if at least 3 features were at extreme levels
    for tp in ['MIN', 'MAX']:
        label = "PISOS" if tp == 'MIN' else "TECHOS"
        mis = missed[missed['tp_type'] == tp].copy()
        if len(mis) < 5:
            continue

        # For each missed turn, count how many features were "extreme"
        # Extreme = outside 1 std from overall mean
        means = {}
        stds = {}
        for f in FEATURES:
            col = f'feat_{f}'
            if col in rdf.columns:
                means[f] = rdf[col].mean()
                stds[f] = rdf[col].std()

        detectable_count = 0
        partially_count = 0
        unpredictable_count = 0

        for idx, r in mis.iterrows():
            extreme_count = 0
            for f in FEATURES:
                col = f'feat_{f}'
                if col in mis.columns and f in means:
                    val = r[col]
                    if np.isnan(val):
                        continue
                    z_score = abs(val - means[f]) / stds[f] if stds[f] > 0 else 0
                    if z_score > 1.0:
                        extreme_count += 1

            if extreme_count >= 4:
                detectable_count += 1
                rdf.loc[idx, 'detectability'] = 'DETECTABLE'
            elif extreme_count >= 2:
                partially_count += 1
                rdf.loc[idx, 'detectability'] = 'PARTIAL_SIGNAL'
            else:
                unpredictable_count += 1
                rdf.loc[idx, 'detectability'] = 'UNPREDICTABLE'

        total_missed = len(mis)
        print(f"\n    {label} PERDIDOS ({total_missed} total):")
        print(f"      🟡 DETECTABLE (≥4 features extremas): {detectable_count} ({detectable_count/total_missed*100:.0f}%)")
        print(f"      🟠 PARTIAL (2-3 features extremas):   {partially_count} ({partially_count/total_missed*100:.0f}%)")
        print(f"      🔴 UNPREDICTABLE (<2 extremas):       {unpredictable_count} ({unpredictable_count/total_missed*100:.0f}%)")
        print(f"      → Margen de mejora potencial: {(detectable_count + partially_count)/total_missed*100:.0f}% de los perdidos tenían señales")

    store.close()
    banner("FORENSIA DE GIROS PERDIDOS COMPLETA")


if __name__ == "__main__":
    main()
