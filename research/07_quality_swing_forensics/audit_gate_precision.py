#!/usr/bin/env python3
"""
FORENSE DE PRECISIÓN DE LOS ML HEADS vs ZIGZAG GROUND TRUTH
=============================================================
Responde las preguntas del Architect:

1. ¿Qué precisión tiene la señal respecto al zigzag?
2. ¿Con qué asertividad? (Precision, Recall, F1)
3. ¿El tramo que predice, de qué magnitud es el retorno?
4. ¿En qué tipo de entradas está funcionando?
5. ¿Cuántas no capturó? (False negatives / missed turns)
6. ¿Cuando falla, de qué magnitud es el tramo?
7. ¿Qué estadística proporciona?

Cruza los ML heads entrenados (long_entry, zz_bottom_detector, short_entry,
zz_top_detector) contra los zigzag breakpoints para medir eficacia real.

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scratch/audit_gate_precision.py
"""
import sys, os, warnings, pickle, json
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

MODELS_DIR = root / "backend" / "models"


def p(t):
    print(f"\n{'='*110}\n  {t}\n{'='*110}")


def sp(t):
    print(f"\n  ── {t} ──")


def load_head(head_name):
    """Load a trained XGBoost head and its config from the pickle dict."""
    pkl_path = MODELS_DIR / f"head_{head_name}_v2.pkl"
    cfg_path = MODELS_DIR / f"head_{head_name}_config.json"
    if not pkl_path.exists():
        print(f"  ⚠️ PKL not found: {pkl_path}")
        return None, None, None
    with open(pkl_path, 'rb') as f:
        bundle = pickle.load(f)

    # Bundle is a dict: {model, feature_cols, head, threshold, dsr, version}
    model = bundle['model']
    features = bundle.get('feature_cols', [])
    threshold = bundle.get('threshold', 0.5)
    dsr = bundle.get('dsr', 0.0)

    cfg = {}
    if cfg_path.exists():
        with open(cfg_path, 'r') as f:
            cfg = json.load(f)
    cfg['features'] = features
    cfg['optimal_threshold'] = threshold
    cfg['dsr'] = dsr

    return model, cfg, features


def main():
    store = TimescaleDataStore()
    ps = TickerProfileStore()

    p("FORENSE DE PRECISIÓN — ML Heads vs Zigzag Ground Truth")

    sp("Cargando Feature Lake, Zigzag y Modelos")
    df, _, _ = load_feature_lake(store, ps)
    print(f"  Feature Lake base: {len(df):,d} observations, {len(df.columns)} cols")

    # Expand with derived features (atr_ratio, sigma_high, overnight_gap, etc.)
    from backend.scripts._lib.feature_optimizer import expand_feature_lake
    derived = expand_feature_lake(df)
    print(f"  Derived features added: {len(derived)} cols → total {len(df.columns)} cols")

    zz = pd.read_sql(
        text("SELECT ticker, timestamp, tp_type, price, swing_return, swing_days "
             "FROM engine.zigzag_points "
             "WHERE min_swing_pct = 0.05 "
             "ORDER BY ticker, timestamp"),
        store.engine
    )
    print(f"  Zigzag points: {len(zz):,d} turns")

    # Pre-group by ticker
    ticker_dfs = {tk: grp.sort_values('timestamp').reset_index(drop=True)
                  for tk, grp in df.groupby('ticker')}

    # ═══════════════════════════════════════════════════════════════
    # MARK ground truth: which bars are "near" a zigzag turn
    # ═══════════════════════════════════════════════════════════════
    sp("Marcando ground truth: barras cerca de breakpoints del zigzag")

    # For each bar in feature lake, mark if it's within N bars of a zigzag turn
    PROXIMITY_WINDOWS = [1, 2, 3, 5]

    df['zz_near_bottom'] = 0  # 1 if within 3 bars of a MIN
    df['zz_near_top'] = 0
    df['zz_bottom_distance'] = 999  # bars to nearest MIN
    df['zz_top_distance'] = 999
    df['zz_swing_return'] = np.nan  # return of the swing from this bottom
    df['zz_swing_days'] = np.nan

    for ticker in df['ticker'].unique():
        tk_mask = df['ticker'] == ticker
        tk_idx = df[tk_mask].index
        tk_ts = df.loc[tk_idx, 'timestamp'].values

        tk_zz = zz[zz['ticker'] == ticker]
        bottoms = tk_zz[tk_zz['tp_type'] == 'MIN']
        tops = tk_zz[tk_zz['tp_type'] == 'MAX']

        for _, zz_row in bottoms.iterrows():
            zz_ts = zz_row['timestamp']
            diffs = np.abs((tk_ts - np.datetime64(zz_ts)).astype('timedelta64[D]').astype(int))
            min_diff = diffs.min()
            if min_diff <= 5:
                nearest_idx = tk_idx[diffs.argmin()]
                # Mark bars within proximity window
                for w in PROXIMITY_WINDOWS:
                    nearby = tk_idx[(diffs <= w)]
                    df.loc[nearby, 'zz_near_bottom'] = 1

                # Mark exact distance
                for i, idx in enumerate(tk_idx):
                    if diffs[i] <= 5:
                        if diffs[i] < df.at[idx, 'zz_bottom_distance']:
                            df.at[idx, 'zz_bottom_distance'] = int(diffs[i])
                            if pd.notna(zz_row['swing_return']):
                                df.at[idx, 'zz_swing_return'] = float(zz_row['swing_return'])
                            if pd.notna(zz_row['swing_days']):
                                df.at[idx, 'zz_swing_days'] = float(zz_row['swing_days'])

        for _, zz_row in tops.iterrows():
            zz_ts = zz_row['timestamp']
            diffs = np.abs((tk_ts - np.datetime64(zz_ts)).astype('timedelta64[D]').astype(int))
            if diffs.min() <= 5:
                for w in PROXIMITY_WINDOWS:
                    nearby = tk_idx[(diffs <= w)]
                    df.loc[nearby, 'zz_near_top'] = 1
                for i, idx in enumerate(tk_idx):
                    if diffs[i] <= 5:
                        if diffs[i] < df.at[idx, 'zz_top_distance']:
                            df.at[idx, 'zz_top_distance'] = int(diffs[i])

    near_bottoms = (df['zz_near_bottom'] == 1).sum()
    near_tops = (df['zz_near_top'] == 1).sum()
    print(f"  Bars near bottoms (±3d): {near_bottoms:,d}")
    print(f"  Bars near tops (±3d): {near_tops:,d}")

    # ═══════════════════════════════════════════════════════════════
    # LOAD & SCORE EACH ML HEAD
    # ═══════════════════════════════════════════════════════════════
    HEADS_TO_AUDIT = [
        ('long_entry', 'BOTTOM', 'LONG'),
        ('zz_bottom_detector', 'BOTTOM', 'LONG'),
        ('short_entry', 'TOP', 'SHORT'),
        ('zz_top_detector', 'TOP', 'SHORT'),
        ('swing_exit', 'TOP', 'LONG'),
        ('short_cover', 'BOTTOM', 'SHORT'),
    ]

    for head_name, turn_type, side in HEADS_TO_AUDIT:
        p(f"HEAD: {head_name} (detecta {turn_type}s, side={side})")

        model, cfg, features = load_head(head_name)
        if model is None:
            print(f"  ⚠️ Model not found: {head_name}")
            continue

        # Get features for this head
        threshold = cfg.get('optimal_threshold', 0.5)
        dsr = cfg.get('dsr', 0.0)
        print(f"  Features: {len(features)} | Threshold: {threshold:.3f} | DSR: {dsr:.3f}")
        print(f"  Features: {features}")
        print(f"  Config: {cfg.get('description', 'N/A')}")

        # Check feature availability
        available = [f for f in features if f in df.columns]
        missing = [f for f in features if f not in df.columns]
        if missing:
            print(f"  ⚠️ Missing features: {missing}")
        if len(available) < len(features) * 0.7:
            print(f"  ❌ Too many missing features ({len(missing)}/{len(features)}). Skipping.")
            continue

        # Score all observations
        X = df[available].fillna(0).values
        try:
            probas = model.predict_proba(X)[:, 1]
        except Exception as e:
            print(f"  ❌ Prediction failed: {e}")
            continue

        df[f'{head_name}_prob'] = probas
        df[f'{head_name}_signal'] = (probas >= threshold).astype(int)

        total_signals = df[f'{head_name}_signal'].sum()
        print(f"  Total signals fired: {total_signals:,d} / {len(df):,d} ({total_signals/len(df)*100:.1f}%)")

        # ── PRECISION vs ZIGZAG ──
        sp(f"PRECISIÓN vs Zigzag {turn_type}s")

        if turn_type == 'BOTTOM':
            gt_col = 'zz_near_bottom'
            dist_col = 'zz_bottom_distance'
        else:
            gt_col = 'zz_near_top'
            dist_col = 'zz_top_distance'

        fired = df[df[f'{head_name}_signal'] == 1]
        gt_positive = df[df[gt_col] == 1]

        # True Positives: signal fired AND near a zigzag turn
        tp = fired[fired[gt_col] == 1]
        # False Positives: signal fired but NOT near a turn
        fp = fired[fired[gt_col] == 0]
        # False Negatives: near a turn but signal did NOT fire
        fn = gt_positive[gt_positive[f'{head_name}_signal'] == 0]

        precision = len(tp) / max(len(fired), 1)
        recall = len(tp) / max(len(gt_positive), 1)
        f1 = 2 * precision * recall / max(precision + recall, 0.001)

        print(f"\n  ┌─────────────────────────────────────────────────┐")
        print(f"  │ MÉTRICAS DE CLASIFICACIÓN vs Zigzag (±3 bars)   │")
        print(f"  ├─────────────────────────────────────────────────┤")
        print(f"  │ Señales disparadas (Total):     {total_signals:>10,d}      │")
        print(f"  │ True Positives (aciertos):       {len(tp):>10,d}      │")
        print(f"  │ False Positives (falsas):        {len(fp):>10,d}      │")
        print(f"  │ False Negatives (no capturó):    {len(fn):>10,d}      │")
        print(f"  │ Turns totales en el zigzag:      {len(gt_positive):>10,d}      │")
        print(f"  ├─────────────────────────────────────────────────┤")
        print(f"  │ PRECISION (cuando dispara, acierta):  {precision:>7.1%}   │")
        print(f"  │ RECALL (de todos los turns, capturó):  {recall:>7.1%}   │")
        print(f"  │ F1 Score:                              {f1:>7.3f}   │")
        print(f"  └─────────────────────────────────────────────────┘")

        # ── DISTANCIA AL BREAKPOINT ──
        sp("Distancia temporal al breakpoint cuando dispara")
        if len(tp) > 0:
            distances = tp[dist_col]
            print(f"  Media: {distances.mean():.1f} bars | Mediana: {distances.median():.0f} bars")
            print(f"  En t=0 (exacto):    {(distances == 0).sum():5d} ({(distances==0).mean()*100:.1f}%)")
            print(f"  En t±1 (1 bar):     {(distances <= 1).sum():5d} ({(distances<=1).mean()*100:.1f}%)")
            print(f"  En t±2 (2 bars):    {(distances <= 2).sum():5d} ({(distances<=2).mean()*100:.1f}%)")
            print(f"  En t±3 (3 bars):    {(distances <= 3).sum():5d} ({(distances<=3).mean()*100:.1f}%)")

        # ── MAGNITUD DEL TRAMO CUANDO ACIERTA ──
        sp("Magnitud del retorno cuando ACIERTA (True Positives)")
        if turn_type == 'BOTTOM' and len(tp) > 0:
            tp_with_ret = tp[tp['zz_swing_return'].notna()]
            if len(tp_with_ret) > 0:
                ret = tp_with_ret['zz_swing_return']
                print(f"  N con retorno: {len(tp_with_ret):,d}")
                print(f"  Retorno medio del tramo:    {ret.mean():+.2%}")
                print(f"  Retorno mediana:             {ret.median():+.2%}")
                print(f"  P25={ret.quantile(0.25):+.2%}  P75={ret.quantile(0.75):+.2%}")
                print(f"  Win Rate (swing > 0):        {(ret > 0).mean()*100:.1f}%")
                days = tp_with_ret['zz_swing_days']
                if days.notna().sum() > 0:
                    print(f"  Duración media del tramo:    {days.mean():.0f} días")

        # ── MAGNITUD CUANDO FALLA (False Positives) ──
        sp("Magnitud cuando FALLA (False Positives — señal sin turn)")
        if len(fp) > 0:
            # For false positives, compute forward 20d return
            fp_returns = []
            for _, row in fp.iterrows():
                ticker = row['ticker']
                tk_df = ticker_dfs.get(ticker)
                if tk_df is None:
                    continue
                ts = row['timestamp']
                time_diffs = np.abs(
                    (tk_df['timestamp'].values - np.datetime64(ts)).astype('timedelta64[D]').astype(int)
                )
                anchor = time_diffs.argmin()
                if time_diffs[anchor] > 3 or anchor + 20 >= len(tk_df):
                    continue
                entry_price = float(row['price'])
                fwd_price = float(tk_df.iloc[anchor + 20]['price'])
                fp_returns.append(fwd_price / entry_price - 1)

            if fp_returns:
                fp_ret = np.array(fp_returns)
                print(f"  N con forward 20d: {len(fp_ret):,d} (de {len(fp):,d} FP)")
                print(f"  Retorno 20d medio:    {fp_ret.mean():+.2%}")
                print(f"  Retorno 20d mediana:  {np.median(fp_ret):+.2%}")
                print(f"  Win Rate (20d > 0):    {(fp_ret > 0).mean()*100:.1f}%")
                print(f"  MDD P10 estimate:      {np.percentile(fp_ret, 10):+.2%}")

        # ── DESGLOSE POR TICKER ──
        sp("Desglose por ticker (Top 5 y Bottom 5)")
        ticker_stats = []
        for ticker in df['ticker'].unique():
            tk = df[df['ticker'] == ticker]
            tk_fired = tk[tk[f'{head_name}_signal'] == 1]
            tk_gt = tk[tk[gt_col] == 1]
            tk_tp = tk_fired[tk_fired[gt_col] == 1]
            if len(tk_fired) > 0:
                tk_prec = len(tk_tp) / len(tk_fired)
            else:
                tk_prec = 0
            tk_rec = len(tk_tp) / max(len(tk_gt), 1)
            ticker_stats.append({
                'ticker': ticker, 'signals': len(tk_fired), 'tp': len(tk_tp),
                'fp': len(tk_fired) - len(tk_tp), 'precision': tk_prec,
                'recall': tk_rec, 'gt_turns': len(tk_gt),
            })
        ticker_stats.sort(key=lambda x: -x['precision'])
        print(f"\n  {'Ticker':>8s} │ {'Signals':>8s} │ {'TP':>5s} │ {'FP':>5s} │ {'Precision':>10s} │ {'Recall':>8s} │ {'Turns':>6s}")
        print("  " + "-" * 75)
        for ts in ticker_stats[:5]:
            print(f"  {ts['ticker']:>8s} │ {ts['signals']:>8d} │ {ts['tp']:>5d} │ {ts['fp']:>5d} │ {ts['precision']:>10.1%} │ {ts['recall']:>8.1%} │ {ts['gt_turns']:>6d}")
        if len(ticker_stats) > 5:
            print("  " + "." * 75)
            for ts in ticker_stats[-3:]:
                print(f"  {ts['ticker']:>8s} │ {ts['signals']:>8d} │ {ts['tp']:>5d} │ {ts['fp']:>5d} │ {ts['precision']:>10.1%} │ {ts['recall']:>8.1%} │ {ts['gt_turns']:>6d}")

        # ── SEÑALES POR RÉGIMEN DE TENDENCIA (Tide) ──
        sp("Señales por régimen de tendencia (tide_slope)")
        if 'tide_slope' in df.columns:
            for regime, cond in [("TIDE_UP", df['tide_slope'] > 0), ("TIDE_DOWN", df['tide_slope'] <= 0)]:
                reg_data = df[cond]
                reg_fired = reg_data[reg_data[f'{head_name}_signal'] == 1]
                reg_gt = reg_data[reg_data[gt_col] == 1]
                reg_tp = reg_fired[reg_fired[gt_col] == 1]
                reg_prec = len(reg_tp) / max(len(reg_fired), 1)
                reg_rec = len(reg_tp) / max(len(reg_gt), 1)
                print(f"  {regime:12s} │ Signals: {len(reg_fired):6d} │ TP: {len(reg_tp):5d} │ Prec: {reg_prec:6.1%} │ Recall: {reg_rec:6.1%}")

        # ── SEÑALES POR LAS 8 FIRMAS DE PENDIENTE RC ──
        sp("Señales por las 8 firmas de pendiente RC (Tide/Curr/Wave ±)")
        if all(c in df.columns for c in ['tide_slope', 'current_slope', 'wave_slope']):
            df['_tide_sign'] = np.where(df['tide_slope'] > 0, '+', '-')
            df['_curr_sign'] = np.where(df['current_slope'] > 0, '+', '-')
            df['_wave_sign'] = np.where(df['wave_slope'] > 0, '+', '-')
            df['_rc_signature'] = 'T(' + df['_tide_sign'] + ') C(' + df['_curr_sign'] + ') W(' + df['_wave_sign'] + ')'

            sig_stats = []
            for sig_name in sorted(df['_rc_signature'].unique()):
                sig_data = df[df['_rc_signature'] == sig_name]
                sig_fired = sig_data[sig_data[f'{head_name}_signal'] == 1]
                sig_gt = sig_data[sig_data[gt_col] == 1]
                sig_tp = sig_fired[sig_fired[gt_col] == 1]
                sig_prec = len(sig_tp) / max(len(sig_fired), 1)
                sig_rec = len(sig_tp) / max(len(sig_gt), 1)
                sig_stats.append((sig_name, len(sig_data), len(sig_fired), len(sig_tp), sig_prec, sig_rec, len(sig_gt)))

            print(f"\n  {'Firma RC':>22s} │ {'Obs':>7s} │ {'Signals':>8s} │ {'TP':>5s} │ {'Precision':>10s} │ {'Recall':>8s} │ {'Turns':>6s}")
            print("  " + "-" * 85)
            for s in sorted(sig_stats, key=lambda x: -x[4]):
                marker = '  ★' if s[0] == 'T(+) C(-) W(-)' else ''
                print(f"  {s[0]:>22s} │ {s[1]:>7,d} │ {s[2]:>8d} │ {s[3]:>5d} │ {s[4]:>10.1%} │ {s[5]:>8.1%} │ {s[6]:>6d}{marker}")

        # ── SEÑALES POR ZONA VWAP SIGMA TIDE ──
        sp("Señales por zona de riesgo VWAP (vwap_sigma_tide)")
        if 'vwap_sigma_tide' in df.columns:
            zones = [
                ('CRISIS (< -1.5)', df['vwap_sigma_tide'] < -1.5),
                ('DANGER (-1.5,-0.5)', (df['vwap_sigma_tide'] >= -1.5) & (df['vwap_sigma_tide'] < -0.5)),
                ('NEUTRAL (-0.5,0.5)', (df['vwap_sigma_tide'] >= -0.5) & (df['vwap_sigma_tide'] < 0.5)),
                ('SAFE (> 0.5)', df['vwap_sigma_tide'] >= 0.5),
            ]
            print(f"\n  {'Risk Zone':>25s} │ {'Signals':>8s} │ {'TP':>5s} │ {'Precision':>10s} │ {'Recall':>8s} │ {'Turns':>6s}")
            print("  " + "-" * 80)
            for zone_name, zone_mask in zones:
                z_data = df[zone_mask]
                z_fired = z_data[z_data[f'{head_name}_signal'] == 1]
                z_gt = z_data[z_data[gt_col] == 1]
                z_tp = z_fired[z_fired[gt_col] == 1]
                z_prec = len(z_tp) / max(len(z_fired), 1)
                z_rec = len(z_tp) / max(len(z_gt), 1)
                print(f"  {zone_name:>25s} │ {len(z_fired):>8d} │ {len(z_tp):>5d} │ {z_prec:>10.1%} │ {z_rec:>8.1%} │ {len(z_gt):>6d}")

        # ── COMBINED: Sweet Spot vs Danger (Tide × VWAP) ──
        sp("COMBINED: Tide Regime × VWAP Zone (Sweet Spot Analysis)")
        if all(c in df.columns for c in ['tide_slope', 'vwap_sigma_tide']):
            combos = [
                ('★ SWEET SPOT: T(+) & VWAP<tide', (df['tide_slope'] > 0) & (df['vwap_sigma_tide'] < 0)),
                ('SAFE BULL: T(+) & VWAP>0.5', (df['tide_slope'] > 0) & (df['vwap_sigma_tide'] >= 0.5)),
                ('NEUTRAL BULL: T(+) & VWAP∈[-0.5,0.5]', (df['tide_slope'] > 0) & (df['vwap_sigma_tide'] >= -0.5) & (df['vwap_sigma_tide'] < 0.5)),
                ('DANGER BEAR: T(-) & VWAP<-0.5', (df['tide_slope'] <= 0) & (df['vwap_sigma_tide'] < -0.5)),
                ('CRISIS BEAR: T(-) & VWAP<-1.5', (df['tide_slope'] <= 0) & (df['vwap_sigma_tide'] < -1.5)),
            ]
            print(f"\n  {'Combined Regime':>40s} │ {'Signals':>8s} │ {'TP':>5s} │ {'Precision':>10s} │ {'Recall':>8s}")
            print("  " + "-" * 85)
            for combo_name, combo_mask in combos:
                c_data = df[combo_mask]
                c_fired = c_data[c_data[f'{head_name}_signal'] == 1]
                c_gt = c_data[c_data[gt_col] == 1]
                c_tp = c_fired[c_fired[gt_col] == 1]
                c_prec = len(c_tp) / max(len(c_fired), 1)
                c_rec = len(c_tp) / max(len(c_gt), 1)
                print(f"  {combo_name:>40s} │ {len(c_fired):>8d} │ {len(c_tp):>5d} │ {c_prec:>10.1%} │ {c_rec:>8.1%}")

    # ═══════════════════════════════════════════════════════════════
    # SÍNTESIS
    # ═══════════════════════════════════════════════════════════════
    p("SÍNTESIS — RESPUESTAS AL ARCHITECT")
    print("""
  Las métricas de arriba responden CADA pregunta planteada:

  1. PRECISIÓN respecto al zigzag → Precision column
     (cuando el ML head dispara, ¿cuántas veces hay un turn real dentro de ±3 bars?)

  2. ASERTIVIDAD → F1 Score = balance precision/recall

  3. MAGNITUD del retorno del tramo → "swing_return" de los True Positives
     (el retorno real desde el bottom hasta el next top del zigzag)

  4. TIPO de entradas donde funciona → Desglose por ticker y por régimen

  5. CUÁNTAS NO CAPTURÓ → False Negatives (turns que existieron sin señal)
     Recall = % de turns capturados

  6. CUANDO FALLA → Forward 20d return de los False Positives
     (qué pasa si entramos en una señal falsa)

  7. ESTADÍSTICA completa → Precision, Recall, F1, WR, MDD, desglose per-ticker
""")

    store.close()
    ps.close()
    p("FORENSE COMPLETO")


if __name__ == "__main__":
    main()
