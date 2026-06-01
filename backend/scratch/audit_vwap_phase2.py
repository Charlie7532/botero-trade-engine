#!/usr/bin/env python3
"""
AUDITORÍA FASE 2 — La Paradoja del swing_return y el Riesgo Real
================================================================
La Fase 1 reveló que TODOS los zigzag bottoms tienen 100% WR y ~13.5% de retorno,
INDEPENDIENTE de su clasificación HL vs LL. Esto es un artefacto:
  - swing_return de un MIN siempre apunta al SIGUIENTE MAX (siempre positivo)
  - El RIESGO REAL está en el SEGUNDO tramo: MAX → siguiente MIN

Esta Fase 2 mide:
  1. Retorno del 2do tramo (después del rebote, ¿cuánto devuelve?)
  2. Retorno NETO de 2 swings (bounce - drawdown = ganancia real?)
  3. Forward returns fijos (5d, 10d, 20d, 40d) desde el breakpoint
  4. d_sigma_wave en t=0 — ¿realmente no discrimina? (p=0.41 en Test 1)
  5. COMBINED GATE: vwap_sigma_tide + d_sigma_wave combinados

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scratch/audit_vwap_phase2.py
"""
import sys, os, warnings
from pathlib import Path
import pandas as pd
import numpy as np
from scipy import stats as sp_stats
from sqlalchemy import text

warnings.filterwarnings("ignore")
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend" / "scripts"))

from dotenv import load_dotenv
load_dotenv(root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore
from unified_pretrainer_v2 import load_feature_lake


def p(t):
    print(f"\n{'='*110}\n  {t}\n{'='*110}")


def sp(t):
    print(f"\n  ── {t} ──")


def classify_structural_context(zz_df, idx, tp_type):
    ticker = zz_df.iloc[idx]['ticker']
    price = float(zz_df.iloc[idx]['price'])
    for j in range(idx - 1, -1, -1):
        if zz_df.iloc[j]['ticker'] == ticker and zz_df.iloc[j]['tp_type'] == tp_type:
            prev = float(zz_df.iloc[j]['price'])
            if tp_type == 'MIN':
                return "HIGHER_LOW" if price > prev else "LOWER_LOW"
            else:
                return "HIGHER_HIGH" if price > prev else "LOWER_HIGH"
    return "FIRST"


AUDIT_FEATURES = [
    'vwap_sigma_tide', 'vwap_sigma_current', 'vwap_sigma_wave',
    'vwap_spread_tide_current', 'vwap_spread_tide_wave', 'vwap_spread_current_wave',
    'below_all_vwaps_int', 'tsi_wave', 'rsi_conviction', 'sigma_tide', 'tsi_current',
    'rsi_value', 'fear_level', 'wave_slope', 'tsi_tide',
    'tide_slope', 'current_slope', 'wave_accel',
    'd_sigma_wave', 'd_tide_slope',
]


def main():
    store = TimescaleDataStore()
    ps = TickerProfileStore()

    p("AUDITORÍA FASE 2 — Riesgo Real y Forward Returns")

    sp("Cargando datos")
    df, _, _ = load_feature_lake(store, ps)

    zz = pd.read_sql(
        text("SELECT ticker, timestamp, tp_type, price, swing_return, swing_days "
             "FROM engine.zigzag_points "
             "WHERE min_swing_pct = 0.05 "
             "ORDER BY ticker, timestamp"),
        store.engine
    )
    print(f"  Feature Lake: {len(df):,d} | Zigzag: {len(zz):,d}")

    # ═══════════════════════════════════════════════════════════════
    # PREPARACIÓN: Enriquecer zigzag con 2do tramo y forward returns
    # ═══════════════════════════════════════════════════════════════
    p("PREPARACIÓN: Enriquecimiento de Zigzag con 2do Tramo y Forward Returns")

    # Pre-group feature lake by ticker
    ticker_dfs = {tk: grp.sort_values('timestamp').reset_index(drop=True)
                  for tk, grp in df.groupby('ticker')}

    records = []
    zz_by_ticker = {tk: grp.reset_index(drop=True)
                    for tk, grp in zz.groupby('ticker')}

    for ticker, tk_zz in zz_by_ticker.items():
        tk_df = ticker_dfs.get(ticker)
        if tk_df is None or len(tk_df) < 50:
            continue

        for i in range(len(tk_zz)):
            row = tk_zz.iloc[i]
            if row['tp_type'] != 'MIN':
                continue

            ts = row['timestamp']
            price = float(row['price'])
            swing1_ret = float(row['swing_return']) if pd.notna(row['swing_return']) else np.nan
            swing1_days = int(row['swing_days']) if pd.notna(row['swing_days']) else np.nan

            # Structural context
            struct = "FIRST"
            for j in range(i - 1, -1, -1):
                if tk_zz.iloc[j]['tp_type'] == 'MIN':
                    prev = float(tk_zz.iloc[j]['price'])
                    struct = "HIGHER_LOW" if price > prev else "LOWER_LOW"
                    break

            if struct == "FIRST":
                continue

            # 2nd swing: find the NEXT MAX (i+1) and the MIN after it (i+2)
            swing2_ret = np.nan
            swing2_days = np.nan
            net_2swing = np.nan
            if i + 2 < len(tk_zz):
                next_max = tk_zz.iloc[i + 1]
                next_min = tk_zz.iloc[i + 2]
                if next_max['tp_type'] == 'MAX' and next_min['tp_type'] == 'MIN':
                    max_price = float(next_max['price'])
                    min2_price = float(next_min['price'])
                    swing2_ret = min2_price / max_price - 1  # The drawdown after bounce
                    swing2_days = int(next_min['swing_days']) if pd.notna(next_min['swing_days']) else np.nan
                    # Net return: if we buy at this MIN and hold through next MAX to next MIN
                    net_2swing = min2_price / price - 1

            # Forward returns from this breakpoint
            time_diffs = np.abs(
                (tk_df['timestamp'].values - np.datetime64(ts)).astype('timedelta64[D]').astype(int)
            )
            anchor = time_diffs.argmin()
            if time_diffs[anchor] > 3:
                continue

            fwd_returns = {}
            for fwd_days in [5, 10, 20, 40, 60]:
                fwd_idx = anchor + fwd_days
                if fwd_idx < len(tk_df):
                    fwd_price = float(tk_df.iloc[fwd_idx]['price'])
                    fwd_returns[f'fwd_{fwd_days}d'] = fwd_price / price - 1

            # Features at t=0
            bar = tk_df.iloc[anchor]
            rec = {
                'ticker': ticker, 'timestamp': ts, 'price': price,
                'structural_context': struct,
                'swing1_ret': swing1_ret, 'swing1_days': swing1_days,
                'swing2_ret': swing2_ret, 'swing2_days': swing2_days,
                'net_2swing': net_2swing,
                **fwd_returns,
            }
            for feat in AUDIT_FEATURES:
                if feat in bar.index:
                    rec[feat] = float(bar[feat])
            records.append(rec)

    enriched = pd.DataFrame(records)
    hl = enriched[enriched['structural_context'] == 'HIGHER_LOW']
    ll = enriched[enriched['structural_context'] == 'LOWER_LOW']
    print(f"  Enriched: {len(enriched):,d} bottoms ({len(hl)} HL + {len(ll)} LL)")

    # ═══════════════════════════════════════════════════════════════
    # TEST A: EL RIESGO REAL — 2do Tramo (Drawdown después del rebote)
    # ═══════════════════════════════════════════════════════════════
    p("TEST A: RIESGO REAL — ¿Cuánto Devolvemos Después del Rebote? (2do Tramo)")

    sp("Swing 1 (bounce) + Swing 2 (drawdown) + Retorno Neto de 2 swings")
    for ctx in ['HIGHER_LOW', 'LOWER_LOW']:
        grp = enriched[(enriched['structural_context'] == ctx) & enriched['swing2_ret'].notna()]
        print(f"\n  {ctx} ({len(grp)} turns):")
        print(f"    Swing 1 (bounce):    media={grp['swing1_ret'].mean():+.2%}  mediana={grp['swing1_ret'].median():+.2%}")
        print(f"    Swing 2 (drawdown):  media={grp['swing2_ret'].mean():+.2%}  mediana={grp['swing2_ret'].median():+.2%}")
        print(f"    Neto 2 swings:       media={grp['net_2swing'].mean():+.2%}  mediana={grp['net_2swing'].median():+.2%}")
        net = grp['net_2swing']
        print(f"    Win Rate (neto > 0): {(net > 0).mean()*100:.1f}%")
        print(f"    P25={net.quantile(0.25):+.2%}  P75={net.quantile(0.75):+.2%}")

    sp("T-test del RIESGO REAL: ¿El 2do tramo castiga más a los LL?")
    hl_s2 = hl['swing2_ret'].dropna()
    ll_s2 = ll['swing2_ret'].dropna()
    if len(hl_s2) > 10 and len(ll_s2) > 10:
        t_s2, p_s2 = sp_stats.ttest_ind(hl_s2, ll_s2, equal_var=False)
        print(f"  swing2_ret:  HL mean={hl_s2.mean():+.2%}  LL mean={ll_s2.mean():+.2%}  t={t_s2:+.2f}  p={p_s2:.2e}")

    hl_net = hl['net_2swing'].dropna()
    ll_net = ll['net_2swing'].dropna()
    if len(hl_net) > 10 and len(ll_net) > 10:
        t_net, p_net = sp_stats.ttest_ind(hl_net, ll_net, equal_var=False)
        print(f"  net_2swing:  HL mean={hl_net.mean():+.2%}  LL mean={ll_net.mean():+.2%}  t={t_net:+.2f}  p={p_net:.2e}")

    # ═══════════════════════════════════════════════════════════════
    # TEST B: FORWARD RETURNS FIJOS (5d, 10d, 20d, 40d, 60d)
    # ═══════════════════════════════════════════════════════════════
    p("TEST B: Forward Returns Fijos desde el Breakpoint (HL vs LL)")

    print(f"\n  {'Horizonte':>12s} │ {'HL Mean':>10s} │ {'LL Mean':>10s} │ {'Δ':>8s} │ {'t-stat':>8s} │ {'HL WR':>6s} │ {'LL WR':>6s} │ {'HL Sharpe':>9s} │ {'LL Sharpe':>9s}")
    print("  " + "-" * 115)

    for fwd in ['fwd_5d', 'fwd_10d', 'fwd_20d', 'fwd_40d', 'fwd_60d']:
        if fwd not in enriched.columns:
            continue
        hl_f = hl[fwd].dropna()
        ll_f = ll[fwd].dropna()
        if len(hl_f) < 10 or len(ll_f) < 10:
            continue
        t_f, _ = sp_stats.ttest_ind(hl_f, ll_f, equal_var=False)
        hl_wr = (hl_f > 0).mean() * 100
        ll_wr = (ll_f > 0).mean() * 100
        hl_sh = hl_f.mean() / hl_f.std() if hl_f.std() > 0 else 0
        ll_sh = ll_f.mean() / ll_f.std() if ll_f.std() > 0 else 0
        print(f"  {fwd:>12s} │ {hl_f.mean():>+10.2%} │ {ll_f.mean():>+10.2%} │ {hl_f.mean()-ll_f.mean():>+8.2%} │ {t_f:>+8.2f} │ {hl_wr:>5.1f}% │ {ll_wr:>5.1f}% │ {hl_sh:>+9.3f} │ {ll_sh:>+9.3f}")

    # ═══════════════════════════════════════════════════════════════
    # TEST C: FORWARD RETURNS CONDICIONADOS POR VWAP_SIGMA_TIDE
    # ═══════════════════════════════════════════════════════════════
    p("TEST C: Forward Returns 20d CONDICIONADOS por vwap_sigma_tide")

    if 'vwap_sigma_tide' in enriched.columns and 'fwd_20d' in enriched.columns:
        thresholds = [(-99, -1.5, "Crisis (v_σ_t < -1.5)"),
                      (-1.5, -0.5, "Débil (-1.5 < v_σ_t < -0.5)"),
                      (-0.5, 0.5, "Neutro (-0.5 < v_σ_t < 0.5)"),
                      (0.5, 99, "Fuerte (v_σ_t > 0.5)")]

        print(f"\n  {'Régimen':35s} │ {'N':>5s} │ {'Fwd 20d':>8s} │ {'WR':>6s} │ {'%HL':>6s} │ {'Net 2sw':>8s} │ {'Net WR':>6s}")
        print("  " + "-" * 95)

        for lo, hi, label in thresholds:
            grp = enriched[(enriched['vwap_sigma_tide'] >= lo) & (enriched['vwap_sigma_tide'] < hi)]
            if len(grp) < 10:
                continue
            fwd = grp['fwd_20d'].dropna()
            net = grp['net_2swing'].dropna()
            pct_hl = (grp['structural_context'] == 'HIGHER_LOW').mean() * 100
            print(f"  {label:35s} │ {len(grp):5d} │ {fwd.mean():>+8.2%} │ {(fwd>0).mean()*100:>5.1f}% │ {pct_hl:>5.1f}% │ {net.mean():>+8.2%} │ {(net>0).mean()*100:>5.1f}%")

    # ═══════════════════════════════════════════════════════════════
    # TEST D: d_sigma_wave — El hallazgo OCULTO
    # ═══════════════════════════════════════════════════════════════
    p("TEST D: d_sigma_wave — ¿Realmente no discrimina? (p=0.41 en Phase 1)")

    sp("d_sigma_wave NO discrimina HL vs LL en t=0 (confirmado p=0.41)")
    sp("PERO: ¿discrimina la VELOCIDAD del rebote DESPUÉS del giro?")

    if 'd_sigma_wave' in enriched.columns and 'fwd_5d' in enriched.columns:
        # Correlación entre d_sigma_wave en t=0 y forward returns
        for fwd in ['fwd_5d', 'fwd_10d', 'fwd_20d']:
            if fwd in enriched.columns:
                valid = enriched[['d_sigma_wave', fwd]].dropna()
                r, p_val = sp_stats.pearsonr(valid['d_sigma_wave'], valid[fwd])
                print(f"  Corr(d_sigma_wave, {fwd}): r={r:+.4f}  p={p_val:.2e}")

    sp("d_sigma_wave en DIFERENTES offsets temporales")
    # Extract d_sigma_wave at t-1 and t+1
    for offset_name, offset_val in [("t-1", -1), ("t=0", 0), ("t+1", 1)]:
        offset_records = []
        for ticker, tk_zz in zz_by_ticker.items():
            tk_df = ticker_dfs.get(ticker)
            if tk_df is None or len(tk_df) < 50:
                continue
            for i in range(len(tk_zz)):
                row = tk_zz.iloc[i]
                if row['tp_type'] != 'MIN':
                    continue
                ts = row['timestamp']
                time_diffs = np.abs(
                    (tk_df['timestamp'].values - np.datetime64(ts)).astype('timedelta64[D]').astype(int)
                )
                anchor = time_diffs.argmin()
                if time_diffs[anchor] > 3:
                    continue
                bar_idx = anchor + offset_val
                if bar_idx < 0 or bar_idx >= len(tk_df):
                    continue
                bar = tk_df.iloc[bar_idx]
                if 'd_sigma_wave' not in bar.index:
                    continue
                # Classify
                struct = "FIRST"
                for j in range(i - 1, -1, -1):
                    if tk_zz.iloc[j]['tp_type'] == 'MIN':
                        prev = float(tk_zz.iloc[j]['price'])
                        struct = "HIGHER_LOW" if float(row['price']) > prev else "LOWER_LOW"
                        break
                if struct == "FIRST":
                    continue
                offset_records.append({
                    'struct': struct, 'd_sigma_wave': float(bar['d_sigma_wave'])
                })

        odf = pd.DataFrame(offset_records)
        if len(odf) > 20:
            hl_d = odf[odf['struct'] == 'HIGHER_LOW']['d_sigma_wave'].dropna()
            ll_d = odf[odf['struct'] == 'LOWER_LOW']['d_sigma_wave'].dropna()
            if len(hl_d) > 5 and len(ll_d) > 5:
                t_d, p_d = sp_stats.ttest_ind(hl_d, ll_d, equal_var=False)
                print(f"  {offset_name}: HL mean={hl_d.mean():+.4f}  LL mean={ll_d.mean():+.4f}  t={t_d:+.2f}  p={p_d:.2e}  {'✅' if p_d < 0.001 else '❌'}")

    # ═══════════════════════════════════════════════════════════════
    # TEST E: COMBINED GATE — vwap_sigma_tide + forward returns
    # ═══════════════════════════════════════════════════════════════
    p("TEST E: COMBINED GATE — Retornos Forward por Régimen de Tendencia")

    if 'vwap_sigma_tide' in enriched.columns and 'tide_slope' in enriched.columns:
        enriched['tide_regime'] = np.where(enriched['tide_slope'] > 0, 'TIDE_UP', 'TIDE_DOWN')
        enriched['vwap_zone'] = np.where(enriched['vwap_sigma_tide'] > 0, 'ABOVE_VWAP_TIDE', 'BELOW_VWAP_TIDE')

        sp("Forward 20d por [Tide Regime × VWAP Zone]")
        print(f"\n  {'Régimen':40s} │ {'N':>5s} │ {'Fwd 20d':>8s} │ {'WR':>6s} │ {'%HL':>6s} │ {'Net2sw':>8s} │ {'Sharpe':>7s}")
        print("  " + "-" * 100)

        for tide_r in ['TIDE_UP', 'TIDE_DOWN']:
            for vwap_z in ['ABOVE_VWAP_TIDE', 'BELOW_VWAP_TIDE']:
                grp = enriched[(enriched['tide_regime'] == tide_r) & (enriched['vwap_zone'] == vwap_z)]
                if len(grp) < 10 or 'fwd_20d' not in grp.columns:
                    continue
                fwd = grp['fwd_20d'].dropna()
                net = grp['net_2swing'].dropna()
                pct_hl = (grp['structural_context'] == 'HIGHER_LOW').mean() * 100
                sh = fwd.mean() / fwd.std() if fwd.std() > 0 else 0
                label = f"{tide_r} + {vwap_z}"
                print(f"  {label:40s} │ {len(grp):5d} │ {fwd.mean():>+8.2%} │ {(fwd>0).mean()*100:>5.1f}% │ {pct_hl:>5.1f}% │ {net.mean():>+8.2%} │ {sh:>+7.3f}")

    # ═══════════════════════════════════════════════════════════════
    # TEST F: MAXIMUM DRAWDOWN AFTER ENTRY
    # ═══════════════════════════════════════════════════════════════
    p("TEST F: Maximum Drawdown en los 20 Días Posteriores al Breakpoint")

    sp("¿Cuánto dolor sufrimos ANTES de capturar el rebote?")
    mdd_records = []
    for _, row in enriched.iterrows():
        ticker = row['ticker']
        ts = row['timestamp']
        tk_df = ticker_dfs.get(ticker)
        if tk_df is None:
            continue
        time_diffs = np.abs(
            (tk_df['timestamp'].values - np.datetime64(ts)).astype('timedelta64[D]').astype(int)
        )
        anchor = time_diffs.argmin()
        if time_diffs[anchor] > 3:
            continue
        entry_price = float(tk_df.iloc[anchor]['price'])
        # Look forward 20 bars
        fwd_slice = tk_df.iloc[anchor:anchor+20]
        if len(fwd_slice) < 5:
            continue
        running_min = fwd_slice['low_price'].min()
        mdd = running_min / entry_price - 1
        mdd_records.append({
            'struct': row['structural_context'],
            'vwap_sigma_tide': row.get('vwap_sigma_tide', np.nan),
            'mdd_20d': mdd,
        })

    mdd_df = pd.DataFrame(mdd_records)
    for ctx in ['HIGHER_LOW', 'LOWER_LOW']:
        grp = mdd_df[mdd_df['struct'] == ctx]
        if len(grp) > 10:
            print(f"\n  {ctx}: Max Drawdown 20d")
            print(f"    Media={grp['mdd_20d'].mean():+.2%}  Mediana={grp['mdd_20d'].median():+.2%}")
            print(f"    P10={grp['mdd_20d'].quantile(0.10):+.2%}  P25={grp['mdd_20d'].quantile(0.25):+.2%}")

    sp("Max Drawdown 20d condicionado por vwap_sigma_tide")
    for ctx in ['HIGHER_LOW', 'LOWER_LOW']:
        grp = mdd_df[mdd_df['struct'] == ctx]
        if 'vwap_sigma_tide' not in grp.columns:
            continue
        for lo, hi, label in [(-99, -0.5, "v_σ_t < -0.5"), (-0.5, 0.5, "v_σ_t ∈ [-0.5,0.5]"), (0.5, 99, "v_σ_t > 0.5")]:
            sub = grp[(grp['vwap_sigma_tide'] >= lo) & (grp['vwap_sigma_tide'] < hi)]
            if len(sub) > 5:
                print(f"  {ctx:15s} │ {label:20s} │ N={len(sub):4d} │ MDD media={sub['mdd_20d'].mean():+.2%} │ MDD P10={sub['mdd_20d'].quantile(0.10):+.2%}")

    # ═══════════════════════════════════════════════════════════════
    # SÍNTESIS FINAL
    # ═══════════════════════════════════════════════════════════════
    p("SÍNTESIS FASE 2 — HALLAZGOS CRÍTICOS")
    print("""
  ESTA FASE RESPONDE LAS PREGUNTAS QUE LA FASE 1 NO PUDO RESPONDER:

  A. ¿El swing_return del siguiente tramo es un espejismo?
     → SÍ. Todos los MIN→MAX son positivos por construcción.
     → El RIESGO REAL está en el 2do tramo (MAX→MIN siguiente).

  B. ¿Los forward returns fijos discriminan HL vs LL?
     → Los datos de arriba lo responden.

  C. ¿El valor REAL de discriminar HL vs LL es retorno o protección?
     → Si HL tiene mejor forward return Y menor drawdown, el valor es DOBLE.
     → Si solo tiene menor drawdown, el valor es protección contra cuchillos.

  D. ¿d_sigma_wave es inútil como discriminador?
     → En t=0 sí (p=0.41). ¿Pero en t+1?

  E. ¿Qué combinación de gate maximiza risk-adjusted return?
     → Los datos cruzados [Tide × VWAP Zone] lo responden.
""")

    store.close()
    ps.close()
    p("AUDITORÍA FASE 2 COMPLETA")


if __name__ == "__main__":
    main()
