#!/usr/bin/env python3
"""
AUDITORÍA DE VERIFICACIÓN ESTADÍSTICA — VWAP Sigma Findings
=============================================================
This script is the PROOF that validates or invalidates the Gemini V2
breakpoint forensic findings. It answers the Architect's questions:

  1. Are the t-stats real? (Independent replication + bootstrap CI)
  2. Do they hold out-of-sample? (Temporal split: train 2006-2019, test 2020-2026)
  3. Are they stable per-ticker or driven by 1-2 outliers?
  4. What is the MAGNITUDE of returns (profit/loss) given the signals?
  5. Are the features collinear (redundant) or independent?
  6. Does the IRS composite actually add discriminative power?
  7. What gate thresholds maximize expected value?
  8. Proposed gate architecture — evidence-based

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scratch/audit_vwap_verification.py
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
    print(f"\n{'='*100}\n  {t}\n{'='*100}")


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
    # The VWAP features under audit
    'vwap_sigma_tide', 'vwap_sigma_current', 'vwap_sigma_wave',
    'vwap_spread_tide_current', 'vwap_spread_tide_wave', 'vwap_spread_current_wave',
    # The original top discriminators for comparison
    'below_all_vwaps_int', 'tsi_wave', 'rsi_conviction', 'sigma_tide', 'tsi_current',
    # Other important features
    'rsi_value', 'fear_level', 'wave_slope', 'tsi_tide',
    # Slopes and accels
    'tide_slope', 'current_slope', 'wave_accel',
    # Delta
    'd_sigma_wave', 'd_tide_slope',
]


def extract_breakpoint_snapshots(df, zz, offset=0):
    """Extract feature snapshots at a given offset from each zigzag breakpoint."""
    ticker_dfs = {tk: grp.reset_index(drop=True) for tk, grp in df.groupby('ticker')}
    records = []
    for zz_idx in range(len(zz)):
        row = zz.iloc[zz_idx]
        ticker, ts, tp_type = row['ticker'], row['timestamp'], row['tp_type']
        price = float(row['price'])
        swing_return = float(row['swing_return']) if pd.notna(row['swing_return']) else np.nan
        swing_days = int(row['swing_days']) if pd.notna(row['swing_days']) else np.nan

        tk_df = ticker_dfs.get(ticker)
        if tk_df is None or len(tk_df) < 20:
            continue

        time_diffs = np.abs(
            (tk_df['timestamp'].values - np.datetime64(ts)).astype('timedelta64[D]').astype(int)
        )
        anchor = time_diffs.argmin()
        if time_diffs[anchor] > 3:
            continue

        bar_idx = anchor + offset
        if bar_idx < 0 or bar_idx >= len(tk_df):
            continue

        bar = tk_df.iloc[bar_idx]
        struct = classify_structural_context(zz, zz_idx, tp_type)

        rec = {
            'ticker': ticker, 'zz_timestamp': ts, 'tp_type': tp_type,
            'zz_price': price, 'structural_context': struct,
            'swing_return': swing_return, 'swing_days': swing_days,
        }
        for feat in AUDIT_FEATURES:
            if feat in bar.index:
                rec[feat] = float(bar[feat])
        records.append(rec)

    return pd.DataFrame(records)


def main():
    store = TimescaleDataStore()
    ps = TickerProfileStore()

    p("AUDITORÍA DE VERIFICACIÓN — VWAP Sigma Findings")
    print("  Objetivo: Validar o invalidar los hallazgos de la forencia V2.")
    print("  Estándar: Científico. Prado exige p < 0.001 Y robustez out-of-sample.")

    sp("Cargando Feature Lake y Zigzag Points")
    df, _, _ = load_feature_lake(store, ps)
    print(f"  Feature Lake: {len(df):,d} observations")

    zz = pd.read_sql(
        text("SELECT ticker, timestamp, tp_type, price, swing_return, swing_days "
             "FROM engine.zigzag_points "
             "WHERE min_swing_pct = 0.05 "
             "ORDER BY ticker, timestamp"),
        store.engine
    )
    print(f"  Zigzag points: {len(zz):,d} turns")

    sp("Extrayendo snapshots en t=0")
    snapshots = extract_breakpoint_snapshots(df, zz, offset=0)
    bottoms = snapshots[snapshots['tp_type'] == 'MIN'].copy()
    bottoms = bottoms[bottoms['structural_context'].isin(['HIGHER_LOW', 'LOWER_LOW'])].copy()
    hl = bottoms[bottoms['structural_context'] == 'HIGHER_LOW']
    ll = bottoms[bottoms['structural_context'] == 'LOWER_LOW']
    print(f"  Bottoms clasificados: {len(hl):,d} HL + {len(ll):,d} LL = {len(bottoms):,d}")

    # ═══════════════════════════════════════════════════════════════
    # TEST 1: REPLICACIÓN INDEPENDIENTE DE T-TESTS
    # ═══════════════════════════════════════════════════════════════
    p("TEST 1: Replicación Independiente de Welch's t-test (HL vs LL)")

    available = [f for f in AUDIT_FEATURES if f in bottoms.columns]
    results = []
    for feat in available:
        hl_v = hl[feat].dropna()
        ll_v = ll[feat].dropna()
        if len(hl_v) < 10 or len(ll_v) < 10:
            continue
        t_stat, p_val = sp_stats.ttest_ind(hl_v, ll_v, equal_var=False)
        cohen_d = (hl_v.mean() - ll_v.mean()) / np.sqrt((hl_v.std()**2 + ll_v.std()**2) / 2)
        results.append({
            'feature': feat, 'hl_mean': hl_v.mean(), 'll_mean': ll_v.mean(),
            'delta': hl_v.mean() - ll_v.mean(), 't_stat': t_stat, 'p_val': p_val,
            'cohen_d': cohen_d, 'n_hl': len(hl_v), 'n_ll': len(ll_v),
        })

    results.sort(key=lambda x: -abs(x['t_stat']))

    print(f"\n  {'Feature':30s} │ {'HL Mean':>10s} │ {'LL Mean':>10s} │ {'Δ':>9s} │ {'t-stat':>8s} │ {'Cohen d':>8s} │ {'p-val':>12s} │ Veredicto")
    print("  " + "-" * 135)
    for r in results:
        sig = "✅ CONFIRMADO" if r['p_val'] < 0.001 and abs(r['cohen_d']) > 0.2 else ("🟡 DÉBIL" if r['p_val'] < 0.05 else "❌ NO SIGNIFICATIVO")
        print(f"  {r['feature']:30s} │ {r['hl_mean']:>10.4f} │ {r['ll_mean']:>10.4f} │ {r['delta']:>+9.4f} │ {r['t_stat']:>+8.2f} │ {r['cohen_d']:>+8.3f} │ {r['p_val']:>12.2e} │ {sig}")

    # ═══════════════════════════════════════════════════════════════
    # TEST 2: BOOTSTRAP CONFIDENCE INTERVALS (95%)
    # ═══════════════════════════════════════════════════════════════
    p("TEST 2: Bootstrap 95% CI para las Top 6 Features")

    top_features = [r['feature'] for r in results[:6]]
    n_boot = 5000
    rng = np.random.default_rng(42)

    for feat in top_features:
        hl_v = hl[feat].dropna().values
        ll_v = ll[feat].dropna().values
        boot_deltas = []
        for _ in range(n_boot):
            hl_sample = rng.choice(hl_v, size=len(hl_v), replace=True)
            ll_sample = rng.choice(ll_v, size=len(ll_v), replace=True)
            boot_deltas.append(hl_sample.mean() - ll_sample.mean())
        boot_deltas = np.array(boot_deltas)
        ci_lo, ci_hi = np.percentile(boot_deltas, [2.5, 97.5])
        observed = hl_v.mean() - ll_v.mean()
        excludes_zero = "✅ CI excluye 0" if ci_lo > 0 or ci_hi < 0 else "❌ CI incluye 0"
        print(f"  {feat:30s} │ Δ observado: {observed:+.4f} │ 95% CI: [{ci_lo:+.4f}, {ci_hi:+.4f}] │ {excludes_zero}")

    # ═══════════════════════════════════════════════════════════════
    # TEST 3: OUT-OF-SAMPLE TEMPORAL SPLIT
    # ═══════════════════════════════════════════════════════════════
    p("TEST 3: Robustez Out-of-Sample (Train: 2006-2019 | Test: 2020-2026)")

    bottoms['year'] = pd.to_datetime(bottoms['zz_timestamp']).dt.year
    train = bottoms[bottoms['year'] <= 2019]
    test = bottoms[bottoms['year'] >= 2020]

    print(f"  Train (2006-2019): {len(train):,d} bottoms ({len(train[train['structural_context']=='HIGHER_LOW'])} HL, {len(train[train['structural_context']=='LOWER_LOW'])} LL)")
    print(f"  Test  (2020-2026): {len(test):,d} bottoms ({len(test[test['structural_context']=='HIGHER_LOW'])} HL, {len(test[test['structural_context']=='LOWER_LOW'])} LL)")

    print(f"\n  {'Feature':30s} │ {'Train t-stat':>12s} │ {'Test t-stat':>12s} │ {'Train Cohen':>12s} │ {'Test Cohen':>12s} │ Estabilidad")
    print("  " + "-" * 120)

    for feat in top_features:
        # Train
        hl_tr = train[train['structural_context'] == 'HIGHER_LOW'][feat].dropna()
        ll_tr = train[train['structural_context'] == 'LOWER_LOW'][feat].dropna()
        t_tr, _ = sp_stats.ttest_ind(hl_tr, ll_tr, equal_var=False) if len(hl_tr) > 5 and len(ll_tr) > 5 else (0, 1)
        d_tr = (hl_tr.mean() - ll_tr.mean()) / np.sqrt((hl_tr.std()**2 + ll_tr.std()**2) / 2) if len(hl_tr) > 5 else 0

        # Test
        hl_te = test[test['structural_context'] == 'HIGHER_LOW'][feat].dropna()
        ll_te = test[test['structural_context'] == 'LOWER_LOW'][feat].dropna()
        t_te, _ = sp_stats.ttest_ind(hl_te, ll_te, equal_var=False) if len(hl_te) > 5 and len(ll_te) > 5 else (0, 1)
        d_te = (hl_te.mean() - ll_te.mean()) / np.sqrt((hl_te.std()**2 + ll_te.std()**2) / 2) if len(hl_te) > 5 else 0

        stable = "✅ ESTABLE" if abs(t_te) > 3.0 and np.sign(t_tr) == np.sign(t_te) else "⚠️ DEGRADADO"
        print(f"  {feat:30s} │ {t_tr:>+12.2f} │ {t_te:>+12.2f} │ {d_tr:>+12.3f} │ {d_te:>+12.3f} │ {stable}")

    # ═══════════════════════════════════════════════════════════════
    # TEST 4: ESTABILIDAD PER-TICKER
    # ═══════════════════════════════════════════════════════════════
    p("TEST 4: Estabilidad Per-Ticker (¿Depende de 1-2 Outliers?)")

    sp("vwap_sigma_current (el #1 reportado)")
    feat = 'vwap_sigma_current'
    if feat in bottoms.columns:
        print(f"\n  {'Ticker':>8s} │ {'N_HL':>5s} │ {'N_LL':>5s} │ {'HL Mean':>10s} │ {'LL Mean':>10s} │ {'Δ':>8s} │ {'t-stat':>8s} │ ¿Consistente?")
        print("  " + "-" * 90)
        consistent_count = 0
        total_tickers = 0
        for ticker in sorted(bottoms['ticker'].unique()):
            tk_data = bottoms[bottoms['ticker'] == ticker]
            tk_hl = tk_data[tk_data['structural_context'] == 'HIGHER_LOW'][feat].dropna()
            tk_ll = tk_data[tk_data['structural_context'] == 'LOWER_LOW'][feat].dropna()
            if len(tk_hl) < 5 or len(tk_ll) < 5:
                continue
            total_tickers += 1
            t_s, _ = sp_stats.ttest_ind(tk_hl, tk_ll, equal_var=False)
            delta = tk_hl.mean() - tk_ll.mean()
            consistent = delta > 0  # HL should have higher value
            if consistent:
                consistent_count += 1
            tag = "✅" if consistent and abs(t_s) > 2 else ("🟡" if consistent else "❌")
            print(f"  {ticker:>8s} │ {len(tk_hl):5d} │ {len(tk_ll):5d} │ {tk_hl.mean():>10.4f} │ {tk_ll.mean():>10.4f} │ {delta:>+8.4f} │ {t_s:>+8.2f} │ {tag}")
        print(f"\n  Consistencia: {consistent_count}/{total_tickers} tickers ({consistent_count/max(total_tickers,1)*100:.0f}%)")

    # ═══════════════════════════════════════════════════════════════
    # TEST 5: MAGNITUD DE RETORNOS (¡La pregunta del Architect!)
    # ═══════════════════════════════════════════════════════════════
    p("TEST 5: MAGNITUD DE RETORNOS — ¿Cuánto Ganamos/Perdemos por Señal?")

    sp("Retornos del SIGUIENTE TRAMO (swing_return) según clasificación")
    # swing_return for MIN points = return from this bottom to next TOP
    bot_with_ret = bottoms[bottoms['swing_return'].notna()].copy()

    print(f"\n  {'Contexto':15s} │ {'N':>5s} │ {'Ret Medio':>10s} │ {'Ret Mediana':>10s} │ {'Ret P25':>8s} │ {'Ret P75':>8s} │ {'Días Med':>8s} │ {'Win Rate':>8s}")
    print("  " + "-" * 100)

    for ctx in ['HIGHER_LOW', 'LOWER_LOW']:
        grp = bot_with_ret[bot_with_ret['structural_context'] == ctx]
        if len(grp) < 10:
            continue
        ret = grp['swing_return']
        days = grp['swing_days']
        wr = (ret > 0).mean() * 100
        print(f"  {ctx:15s} │ {len(grp):5d} │ {ret.mean():>+10.2%} │ {ret.median():>+10.2%} │ {ret.quantile(0.25):>+8.2%} │ {ret.quantile(0.75):>+8.2%} │ {days.median():>8.0f} │ {wr:>7.1f}%")

    sp("Retornos CONDICIONADOS por vwap_sigma_tide (umbrales)")
    if 'vwap_sigma_tide' in bot_with_ret.columns:
        thresholds = [(-99, -1.5, "v_σ_tide < -1.5 (Crisis)"),
                      (-1.5, -0.5, "-1.5 < v_σ_tide < -0.5"),
                      (-0.5, 0.0, "-0.5 < v_σ_tide < 0.0"),
                      (0.0, 0.5, "0.0 < v_σ_tide < 0.5"),
                      (0.5, 99, "v_σ_tide > 0.5 (Fuerte)")]

        print(f"\n  {'Umbral vwap_sigma_tide':35s} │ {'N':>5s} │ {'Ret Medio':>10s} │ {'Ret Med':>8s} │ {'%HL':>6s} │ {'Win Rate':>8s} │ {'E[V]':>10s}")
        print("  " + "-" * 110)

        for lo, hi, label in thresholds:
            grp = bot_with_ret[(bot_with_ret['vwap_sigma_tide'] >= lo) & (bot_with_ret['vwap_sigma_tide'] < hi)]
            if len(grp) < 5:
                continue
            ret = grp['swing_return']
            pct_hl = (grp['structural_context'] == 'HIGHER_LOW').mean() * 100
            wr = (ret > 0).mean() * 100
            ev = ret.mean()  # Expected value per trade
            print(f"  {label:35s} │ {len(grp):5d} │ {ret.mean():>+10.2%} │ {ret.median():>+8.2%} │ {pct_hl:>5.1f}% │ {wr:>7.1f}% │ {ev:>+10.2%}")

    sp("Retornos CONDICIONADOS por IRS (Índice de Retención Secular)")
    if 'vwap_sigma_tide' in bot_with_ret.columns and 'vwap_spread_tide_current' in bot_with_ret.columns:
        bot_with_ret['irs'] = bot_with_ret['vwap_sigma_tide'] - bot_with_ret['vwap_spread_tide_current']

        irs_thresholds = [(-99, -2.0, "IRS < -2 (Colapso)"),
                          (-2.0, 0.0, "-2 < IRS < 0 (Debilidad)"),
                          (0.0, 3.0, "0 < IRS < 3 (Soporte)"),
                          (3.0, 6.0, "3 < IRS < 6 (Fuerte)"),
                          (6.0, 99, "IRS > 6 (Ultra Fuerte)")]

        print(f"\n  {'Umbral IRS':35s} │ {'N':>5s} │ {'Ret Medio':>10s} │ {'Ret Med':>8s} │ {'%HL':>6s} │ {'Win Rate':>8s} │ {'E[V]':>10s}")
        print("  " + "-" * 110)

        for lo, hi, label in irs_thresholds:
            grp = bot_with_ret[(bot_with_ret['irs'] >= lo) & (bot_with_ret['irs'] < hi)]
            if len(grp) < 5:
                continue
            ret = grp['swing_return']
            pct_hl = (grp['structural_context'] == 'HIGHER_LOW').mean() * 100
            wr = (ret > 0).mean() * 100
            ev = ret.mean()
            print(f"  {label:35s} │ {len(grp):5d} │ {ret.mean():>+10.2%} │ {ret.median():>+8.2%} │ {pct_hl:>5.1f}% │ {wr:>7.1f}% │ {ev:>+10.2%}")

    # ═══════════════════════════════════════════════════════════════
    # TEST 6: COLLINEARITY AUDIT
    # ═══════════════════════════════════════════════════════════════
    p("TEST 6: Auditoría de Colinealidad entre Features de VWAP")

    vwap_feats = ['vwap_sigma_tide', 'vwap_sigma_current', 'vwap_sigma_wave',
                  'sigma_tide', 'below_all_vwaps_int', 'tsi_wave', 'tsi_current',
                  'rsi_conviction', 'fear_level']
    vwap_available = [f for f in vwap_feats if f in bottoms.columns]

    if len(vwap_available) > 2:
        corr = bottoms[vwap_available].corr()
        print(f"\n  Matriz de Correlación (|r| > 0.70 = ⚠️ ALTA COLINEALIDAD):\n")
        print(f"  {'':30s}", end="")
        for c in vwap_available:
            print(f" {c[:8]:>8s}", end="")
        print()
        print("  " + "-" * (30 + 9 * len(vwap_available)))

        for i, row_feat in enumerate(vwap_available):
            print(f"  {row_feat:30s}", end="")
            for j, col_feat in enumerate(vwap_available):
                r = corr.loc[row_feat, col_feat]
                flag = " ⚠️" if abs(r) > 0.70 and i != j else ""
                print(f" {r:>+7.3f}{flag}", end="")
            print()

    # ═══════════════════════════════════════════════════════════════
    # TEST 7: IRS COMPOSITE VALIDATION
    # ═══════════════════════════════════════════════════════════════
    p("TEST 7: Validación del IRS como Feature Compuesta")

    if 'irs' in bot_with_ret.columns:
        hl_irs = bot_with_ret[bot_with_ret['structural_context'] == 'HIGHER_LOW']['irs'].dropna()
        ll_irs = bot_with_ret[bot_with_ret['structural_context'] == 'LOWER_LOW']['irs'].dropna()
        t_irs, p_irs = sp_stats.ttest_ind(hl_irs, ll_irs, equal_var=False)
        d_irs = (hl_irs.mean() - ll_irs.mean()) / np.sqrt((hl_irs.std()**2 + ll_irs.std()**2) / 2)

        # Compare vs best individual
        hl_vsc = hl[['vwap_sigma_current']].dropna()['vwap_sigma_current']
        ll_vsc = ll[['vwap_sigma_current']].dropna()['vwap_sigma_current']
        t_vsc, _ = sp_stats.ttest_ind(hl_vsc, ll_vsc, equal_var=False)

        print(f"\n  IRS (compuesto):          t-stat = {t_irs:+.2f}  │  Cohen d = {d_irs:+.3f}  │  HL mean = {hl_irs.mean():+.2f}  │  LL mean = {ll_irs.mean():+.2f}")
        print(f"  vwap_sigma_current (solo): t-stat = {t_vsc:+.2f}")
        verdict = "✅ IRS SUPERA al individual" if abs(t_irs) > abs(t_vsc) else "⚠️ IRS NO supera al individual (posible redundancia)"
        print(f"\n  Veredicto: {verdict}")

    # ═══════════════════════════════════════════════════════════════
    # TEST 8: GATE THRESHOLD OPTIMIZATION (Expected Value)
    # ═══════════════════════════════════════════════════════════════
    p("TEST 8: Optimización de Umbrales del Gate — Máximo Valor Esperado")

    sp("Simulación: Si SOLO entramos cuando vwap_sigma_tide > umbral, ¿cuál es el E[V]?")

    if 'vwap_sigma_tide' in bot_with_ret.columns:
        print(f"\n  {'Umbral vwap_σ_tide':>20s} │ {'N Señales':>10s} │ {'E[Retorno]':>10s} │ {'Win Rate':>10s} │ {'%HL':>6s} │ {'Sharpe*':>8s} │ Evaluación")
        print("  " + "-" * 100)

        for threshold in [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0]:
            grp = bot_with_ret[bot_with_ret['vwap_sigma_tide'] >= threshold]
            if len(grp) < 10:
                continue
            ret = grp['swing_return']
            wr = (ret > 0).mean() * 100
            pct_hl = (grp['structural_context'] == 'HIGHER_LOW').mean() * 100
            ev = ret.mean()
            sharpe = ret.mean() / ret.std() if ret.std() > 0 else 0
            if ev > 0.08 and wr > 65:
                tag = "🌟 ÓPTIMO"
            elif ev > 0.05 and wr > 55:
                tag = "✅ BUENO"
            elif ev > 0:
                tag = "🟡 MARGINAL"
            else:
                tag = "❌ NEGATIVO"
            print(f"  {threshold:>+20.1f} │ {len(grp):>10d} │ {ev:>+10.2%} │ {wr:>9.1f}% │ {pct_hl:>5.1f}% │ {sharpe:>+8.3f} │ {tag}")

    sp("Simulación: Trigger en t+1 con d_sigma_wave > umbral (SOLO sobre HL/LL en t=0)")
    sp_t1 = extract_breakpoint_snapshots(df, zz, offset=1)
    bot_t1 = sp_t1[sp_t1['tp_type'] == 'MIN'].copy()
    bot_t1 = bot_t1[bot_t1['structural_context'].isin(['HIGHER_LOW', 'LOWER_LOW'])].copy()

    if 'd_sigma_wave' in bot_t1.columns and len(bot_t1) > 0:
        bot_merged = bot_with_ret[['ticker', 'zz_timestamp', 'swing_return', 'structural_context', 'vwap_sigma_tide']].merge(
            bot_t1[['ticker', 'zz_timestamp', 'd_sigma_wave', 'rsi_conviction']],
            on=['ticker', 'zz_timestamp'], how='inner', suffixes=('', '_t1')
        )
        print(f"\n  Datos con t+1 merge: {len(bot_merged):,d} turns")

        print(f"\n  {'Umbral d_σ_wave (t+1)':>25s} │ {'N':>5s} │ {'E[Ret]':>8s} │ {'WR':>6s} │ {'%HL':>6s} │ Evaluación")
        print("  " + "-" * 80)

        for thr in [-0.5, 0.0, 0.3, 0.5, 1.0]:
            grp = bot_merged[bot_merged['d_sigma_wave'] >= thr]
            if len(grp) < 5:
                continue
            ret = grp['swing_return']
            wr = (ret > 0).mean() * 100
            pct_hl = (grp['structural_context'] == 'HIGHER_LOW').mean() * 100
            ev = ret.mean()
            tag = "🌟" if ev > 0.08 and wr > 65 else ("✅" if ev > 0.05 else "🟡")
            print(f"  {thr:>+25.1f} │ {len(grp):5d} │ {ev:>+8.2%} │ {wr:>5.1f}% │ {pct_hl:>5.1f}% │ {tag}")

    # ═══════════════════════════════════════════════════════════════
    # SÍNTESIS FINAL
    # ═══════════════════════════════════════════════════════════════
    p("SÍNTESIS DE LA AUDITORÍA")
    print("""
  La auditoría valida o invalida cada hallazgo con evidencia empírica.
  Los resultados de arriba son la PRUEBA. No hay opiniones, solo datos.

  PREGUNTAS RESPONDIDAS:
  1. ¿Son reales los t-stats?        → Test 1 (replicación) + Test 2 (bootstrap CI)
  2. ¿Sobreviven out-of-sample?      → Test 3 (split temporal 2019/2020)
  3. ¿Son estables per-ticker?       → Test 4 (consistencia por activo)
  4. ¿Cuánto ganamos/perdemos?       → Test 5 (magnitud de retornos condicionados)
  5. ¿Son redundantes?               → Test 6 (matriz de colinealidad)
  6. ¿El IRS compuesto agrega valor? → Test 7 (comparación vs componentes)
  7. ¿Qué umbrales maximizan E[V]?   → Test 8 (optimización de gates)

  NOTA: swing_return para MIN points = retorno desde este fondo hasta el siguiente techo.
  Es el retorno REAL del tramo que capturaríamos si entramos en este breakpoint.
""")

    store.close()
    ps.close()
    p("AUDITORÍA COMPLETA")


if __name__ == "__main__":
    main()
