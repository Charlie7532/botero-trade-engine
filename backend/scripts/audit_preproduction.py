#!/usr/bin/env python3
"""
Auditoría Integral — Pre-Production Quality Gate
==================================================
Verifica TODOS los componentes antes de integrar a producción:

1. DATA INTEGRITY: Kalman/RSI backfill — no NaN, no inf, distribuciones sanas
2. MODEL INTEGRITY: 8 v2 heads + 1 v1 fallback cargan correctamente
3. PREDICTION SANITY: Predicciones sobre datos recientes son coherentes
4. CONFIG COHERENCE: Configs JSON matchean los modelos
5. READINESS STATE: training_readiness.json actualizado
6. CROSS-HEAD CONSISTENCY: No hay contradicciones lógicas entre heads

Produces: PASS / FAIL with detailed findings
"""
import os, sys, warnings, json, pickle, time
from pathlib import Path
warnings.filterwarnings("ignore")

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def p(t): print(f"\n{'='*90}\n  {t}\n{'='*90}")
def sp(t): print(f"\n  ── {t} ──")
def ok(t): print(f"    ✅ {t}")
def warn(t): print(f"    ⚠️  {t}")
def fail(t): print(f"    ❌ {t}")

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]

HEADS = [
    "long_entry", "swing_exit", "pullback_depth", "trend_reversal",
    "short_entry", "short_cover", "bounce_height", "trend_recovery",
]

FEATURES = [
    'sigma_tide', 'sigma_current', 'sigma_wave',
    'vwap_sigma_tide', 'vwap_sigma_current', 'vwap_sigma_wave',
    'tension_tide', 'tension_current', 'tension_wave',
    'tide_slope', 'current_slope', 'wave_slope',
    'tide_accel', 'current_accel', 'wave_accel',
    'conj_wave_current', 'conj_wave_tide', 'conj_current_tide',
    'spread_tide_current', 'spread_tide_wave', 'spread_current_wave',
    'vwap_spread_tide_current', 'vwap_spread_tide_wave', 'vwap_spread_current_wave',
    'compression_ratio',
    'fear_level', 'vol_up_down_ratio',
    'wave_flip', 'wave_flip_direction',
    'rsi_value', 'rsi_divergence_strength', 'rsi_conviction',
    'kalman_velocity', 'vol_adj_delta',
    'geo_state_norm', 'geo_velocity_align', 'geo_exit_align',
    'geo_accel_align', 'geo_phase_angle',
]

MODELS_DIR = root_dir / "data" / "models"
findings = {"pass": 0, "warn": 0, "fail": 0}

def check(passed, msg_ok, msg_fail):
    if passed:
        ok(msg_ok)
        findings["pass"] += 1
    else:
        fail(msg_fail)
        findings["fail"] += 1

def check_warn(passed, msg_ok, msg_warn):
    if passed:
        ok(msg_ok)
        findings["pass"] += 1
    else:
        warn(msg_warn)
        findings["warn"] += 1


def audit_data_integrity(store):
    """Check that ALL features are populated with REAL values, not defaults.

    Previous bug: checked `rsi_value != 0` but RSI default = 50.0, not 0.
    Fix: check VARIANCE per ticker. If std=0, it's a constant (fake data).
    """
    p("AUDIT 1: DATA INTEGRITY")

    # ── 1a. Variance-based fake data detection (no more != 0 tricks) ──
    sp("1a. Variance-based data quality (detects defaults)")

    CRITICAL_FIELDS = {
        'rsi_value':                {'default': 50.0, 'expected_std_min': 3.0,  'expected_range': (0, 100)},
        'rsi_divergence_strength':  {'default': 0.0,  'expected_std_min': 0.01, 'expected_range': (-2, 2)},
        'rsi_conviction':           {'default': 0.0,  'expected_std_min': 0.01, 'expected_range': (-1, 1)},
        'kalman_velocity':          {'default': 0.0,  'expected_std_min': 0.01, 'expected_range': (-3, 3)},
        'vol_adj_delta':            {'default': 0.0,  'expected_std_min': 0.01, 'expected_range': (-5, 5)},
        'sigma_tide':               {'default': 0.0,  'expected_std_min': 0.5,  'expected_range': (-5, 5)},
        'sigma_current':            {'default': 0.0,  'expected_std_min': 0.5,  'expected_range': (-6, 6)},
        'sigma_wave':               {'default': 0.0,  'expected_std_min': 0.5,  'expected_range': (-6, 6)},
        'tide_slope':               {'default': 0.0,  'expected_std_min': 0.01, 'expected_range': (-1, 1)},
        'compression_ratio':        {'default': 0.0,  'expected_std_min': 0.05, 'expected_range': (0, 2)},
        'fear_level':               {'default': 2,    'expected_std_min': 0.5,  'expected_range': (0, 5)},
        'geo_state_norm':           {'default': 0.0,  'expected_std_min': 0.3,  'expected_range': (0, 10)},
        'geo_velocity_align':       {'default': 0.0,  'expected_std_min': 0.1,  'expected_range': (-1, 1)},
    }

    fake_data_fields = []

    for field, spec in CRITICAL_FIELDS.items():
        q = f"""
            SELECT ticker,
                   ROUND(STDDEV({field})::numeric, 6) as std_v,
                   ROUND(AVG({field})::numeric, 4) as avg_v,
                   COUNT(*) as n
            FROM engine.channel_snapshots
            WHERE ticker = ANY(%s) AND sigma_tide IS NOT NULL
            GROUP BY ticker ORDER BY ticker
        """
        df = pd.read_sql(q, store.engine, params=(TICKERS,))
        n_constant = (df['std_v'].fillna(0) == 0).sum()

        if n_constant >= 2:
            fail(f"{field}: {n_constant}/17 tickers have std=0 (FAKE DATA, default={spec['default']})")
            findings["fail"] += 1
            fake_fields = df[df['std_v'].fillna(0) == 0]['ticker'].tolist()
            fake_data_fields.append({'field': field, 'tickers': fake_fields})
        elif n_constant == 1:
            warn(f"{field}: 1/17 ticker has std=0")
            findings["warn"] += 1
        else:
            # Check range
            global_avg_std = df['std_v'].mean()
            check(global_avg_std > spec['expected_std_min'],
                  f"{field}: avg_std={global_avg_std:.4f} (real data)",
                  f"{field}: avg_std={global_avg_std:.4f} < {spec['expected_std_min']} — suspicious")

    if fake_data_fields:
        print(f"\n    ╔══ FAKE DATA SUMMARY ══╗")
        for fd in fake_data_fields:
            print(f"    ║ {fd['field']:<30s}: {len(fd['tickers'])} tickers with constants")
        print(f"    ╚{'═'*50}╝")

    # ── 1b. Coverage check (NULL detection) ──
    sp("1b. NULL coverage (all 17 tickers)")
    q = """
        SELECT ticker,
               COUNT(*) as total,
               COUNT(CASE WHEN rsi_value IS NOT NULL THEN 1 END) as rsi_nn,
               COUNT(CASE WHEN kalman_velocity IS NOT NULL THEN 1 END) as kv_nn,
               COUNT(CASE WHEN vol_adj_delta IS NOT NULL THEN 1 END) as vad_nn
        FROM engine.channel_snapshots
        WHERE ticker = ANY(%s)
        GROUP BY ticker ORDER BY ticker
    """
    df = pd.read_sql(q, store.engine, params=(TICKERS,))
    total_rows = df['total'].sum()

    for col_nn, label in [('rsi_nn', 'RSI'), ('kv_nn', 'Kalman'), ('vad_nn', 'VolAdjDelta')]:
        pct = df[col_nn].sum() / total_rows * 100
        check(pct > 99, f"{label}: {df[col_nn].sum():,d}/{total_rows:,d} not-NULL ({pct:.1f}%)",
              f"{label}: only {pct:.1f}% not-NULL")

    # Per-ticker summary
    for _, row in df.iterrows():
        ok(f"{row['ticker']:>6s}: {row['total']:,d} rows, RSI={row['rsi_nn']/row['total']*100:.0f}% KV={row['kv_nn']/row['total']*100:.0f}%")

    # ── 1c. Distribution sanity ──
    sp("1c. Distribution sanity (NaN/Inf detection)")
    q2 = """
        SELECT
            COUNT(CASE WHEN rsi_value = 'NaN'::float OR rsi_value = 'Infinity'::float THEN 1 END) as rsi_bad,
            COUNT(CASE WHEN kalman_velocity = 'NaN'::float OR kalman_velocity = 'Infinity'::float THEN 1 END) as kv_bad,
            AVG(kalman_velocity) as kv_mean,
            STDDEV(kalman_velocity) as kv_std
        FROM engine.channel_snapshots
        WHERE ticker = ANY(%s) AND sigma_tide IS NOT NULL
    """
    stats = pd.read_sql(q2, store.engine, params=(TICKERS,))
    s = stats.iloc[0]
    check(s['rsi_bad'] == 0, "RSI: 0 NaN/Inf values", f"RSI: {s['rsi_bad']} NaN/Inf!")
    check(s['kv_bad'] == 0, "Kalman: 0 NaN/Inf values", f"Kalman: {s['kv_bad']} NaN/Inf!")
    check(abs(s['kv_mean']) < 0.1, f"Kalman mean={s['kv_mean']:.4f} (~0 expected)", f"Kalman mean biased!")
    check(0.05 < s['kv_std'] < 0.5, f"Kalman std={s['kv_std']:.4f} (reasonable)", f"Kalman std abnormal!")

    # ── 1d. Spot-check SPY ──
    sp("1d. Spot-check: SPY last 5 bars")
    q3 = """
        SELECT timestamp, rsi_value, rsi_divergence_strength, rsi_conviction,
               kalman_velocity, vol_adj_delta, sigma_tide, fear_level
        FROM engine.channel_snapshots
        WHERE ticker = 'SPY' AND sigma_tide IS NOT NULL
        ORDER BY timestamp DESC LIMIT 5
    """
    recent = pd.read_sql(q3, store.engine)
    for _, row in recent.iterrows():
        ts = str(row['timestamp'])[:10]
        print(f"    {ts}: RSI={row['rsi_value']:.1f} div={row['rsi_divergence_strength']:.2f} "
              f"conv={row['rsi_conviction']:.2f} KV={row['kalman_velocity']:.4f} "
              f"VAD={row['vol_adj_delta']:.4f} σ={row['sigma_tide']:.2f} fear={row['fear_level']}")
    check(len(recent) == 5, "SPY has recent data", "SPY missing recent data!")


def audit_model_integrity():
    """Check all model files load correctly and have expected structure."""
    p("AUDIT 2: MODEL INTEGRITY")

    # 2a. v2 heads
    sp("2a. v2 heads (8 models)")
    for head in HEADS:
        pkl_path = MODELS_DIR / f"head_{head}_v2.pkl"
        cfg_path = MODELS_DIR / f"head_{head}_config.json"

        # Check files exist
        check(pkl_path.exists(), f"{head}: .pkl exists ({pkl_path.stat().st_size:,d} bytes)", f"{head}: .pkl MISSING!")
        check(cfg_path.exists(), f"{head}: config.json exists", f"{head}: config.json MISSING!")

        if pkl_path.exists() and cfg_path.exists():
            # Load model
            with open(pkl_path, 'rb') as f:
                model = pickle.load(f)
            with open(cfg_path, 'r') as f:
                config = json.load(f)

            # Check config has required fields
            required = ['head', 'dsr', 'threshold', 'best_edge',
                        'n_observations', 'positive_rate', 'feature_importance']
            missing = [k for k in required if k not in config]
            check(len(missing) == 0, f"{head}: config has all required fields", f"{head}: config MISSING {missing}")

            # Check pkl is a dict with 'model' and 'feature_cols'
            check(isinstance(model, dict) and 'model' in model,
                  f"{head}: pkl has 'model' key", f"{head}: pkl missing 'model' key!")
            check('feature_cols' in model,
                  f"{head}: pkl has 'feature_cols' key", f"{head}: pkl missing 'feature_cols' key!")

            # Check feature count — Challenger v2 heads may use 2-13 optimized features
            n_features = len(model.get('feature_cols', []))
            xgb_model_inner = model.get('model')
            expected_n = xgb_model_inner.n_features_in_ if xgb_model_inner else 0
            check(n_features >= 2 and n_features == expected_n,
                  f"{head}: {n_features} features (XGBoost expects {expected_n})",
                  f"{head}: feature mismatch! pkl={n_features} vs XGBoost={expected_n}")

            # Check DSR stored correctly
            dsr = config.get('dsr', 0)
            check_warn(dsr > 1.0, f"{head}: DSR={dsr:.2f}", f"{head}: DSR={dsr:.2f} < 1.0")

            # Try predict on dummy data using actual XGBoost model
            try:
                xgb_model = model['model']
                dummy = np.zeros((1, n_features))
                pred = xgb_model.predict_proba(dummy)
                check(0 <= pred[0][1] <= 1, f"{head}: predict_proba works (P={pred[0][1]:.3f})", f"{head}: predict_proba failed!")
            except Exception as e:
                fail(f"{head}: predict_proba error: {e}")
                findings["fail"] += 1

    # 2b. v1 fallback
    sp("2b. v1 fallback model")
    v1_pkl = MODELS_DIR / "unified_pretrainer_v1.pkl"
    v1_cfg = MODELS_DIR / "unified_pretrainer_config.json"
    check(v1_pkl.exists(), f"v1 model exists ({v1_pkl.stat().st_size:,d} bytes)", "v1 model MISSING!")
    check(v1_cfg.exists(), "v1 config exists", "v1 config MISSING!")

    if v1_pkl.exists():
        with open(v1_pkl, 'rb') as f:
            v1_model = pickle.load(f)
        with open(v1_cfg, 'r') as f:
            v1_config = json.load(f)
        dsr_v1 = v1_config.get('dsr', 0)
        check(dsr_v1 > 2.0, f"v1 DSR={dsr_v1:.2f} (ENTRY model)", f"v1 DSR={dsr_v1:.2f} unexpected")


def audit_prediction_sanity(store):
    """Load recent snapshots and verify predictions make sense."""
    p("AUDIT 3: PREDICTION SANITY")

    sp("3a. Load real features from last bar of each ticker")

    # Load one recent snapshot per ticker
    q = """
        SELECT DISTINCT ON (ticker) ticker, *
        FROM engine.channel_snapshots
        WHERE ticker = ANY(%s) AND sigma_tide IS NOT NULL
        ORDER BY ticker, timestamp DESC
    """
    recent = pd.read_sql(q, store.engine, params=(TICKERS,))
    print(f"    Loaded {len(recent)} snapshots (1 per ticker)")

    # Prepare feature matrix
    from backend.modules.shared.domain.rules.trend_strength import compute_tsi, compute_adi
    from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore
    profile_store = TickerProfileStore()

    # Load all models
    models = {}
    configs = {}
    for head in HEADS:
        pkl_path = MODELS_DIR / f"head_{head}_v2.pkl"
        cfg_path = MODELS_DIR / f"head_{head}_config.json"
        if pkl_path.exists():
            with open(pkl_path, 'rb') as f:
                models[head] = pickle.load(f)
            with open(cfg_path, 'r') as f:
                configs[head] = json.load(f)

    # Build features for each ticker
    sp("3b. Predictions on real latest data")
    predictions = {h: [] for h in HEADS}

    for _, row in recent.iterrows():
        ticker = str(row['ticker'])
        profile = profile_store.load_profile(ticker)

        # Build feature vector
        feat_dict = {}
        for f in FEATURES:
            feat_dict[f] = float(row.get(f, 0) or 0)

        # Add computed features
        if profile is not None:
            feat_dict['tsi_tide'] = compute_tsi(feat_dict.get('tide_slope', 0), profile.tsi_tide_percentiles)
            feat_dict['tsi_current'] = compute_tsi(feat_dict.get('current_slope', 0), profile.tsi_current_percentiles)
            feat_dict['tsi_wave'] = compute_tsi(feat_dict.get('wave_slope', 0), profile.tsi_wave_percentiles)
            feat_dict['adi_tide'] = compute_adi(feat_dict.get('tension_tide', 0), profile.adi_tide_percentiles)
            feat_dict['adi_current'] = compute_adi(feat_dict.get('tension_current', 0), profile.adi_current_percentiles)
            feat_dict['adi_wave'] = compute_adi(feat_dict.get('tension_wave', 0), profile.adi_wave_percentiles)
        else:
            for f in ['tsi_tide', 'tsi_current', 'tsi_wave', 'adi_tide', 'adi_current', 'adi_wave']:
                feat_dict[f] = 50

        # Encode
        regime_map = {'BULL': 2, 'FLAT': 1, 'BEAR': 0}
        feat_dict['regime_encoded'] = regime_map.get(row.get('regime', 'FLAT'), 1)
        feat_dict['below_all_vwaps_int'] = int(row.get('below_all_vwaps', False) or False)
        feat_dict['above_all_vwaps_int'] = int(row.get('above_all_vwaps', False) or False)

        # Predict with each head
        for head in HEADS:
            if head not in models:
                continue
            features_list = models[head]['feature_cols']
            xgb_model = models[head]['model']
            X = np.array([[feat_dict.get(f, 0) for f in features_list]])
            try:
                prob = xgb_model.predict_proba(X)[0][1]
                predictions[head].append((ticker, prob))
            except Exception as e:
                fail(f"{head} prediction failed for {ticker}: {e}")
                findings["fail"] += 1

    # Print prediction matrix
    print(f"\n    {'Ticker':>6s}", end="")
    for h in HEADS:
        short_h = h[:8]
        print(f" {short_h:>9s}", end="")
    print()
    print("    " + "-" * (6 + 10 * len(HEADS)))

    for i, ticker in enumerate(TICKERS):
        print(f"    {ticker:>6s}", end="")
        for head in HEADS:
            preds_for_head = [p for t, p in predictions[head] if t == ticker]
            if preds_for_head:
                prob = preds_for_head[0]
                marker = "★" if prob > configs[head].get('threshold', 0.65) else " "
                print(f"  {prob:.3f}{marker}", end="")
            else:
                print(f"     N/A ", end="")
        print()

    # Sanity checks
    sp("3c. Cross-head logical consistency")

    # Check: if trend_reversal says YES (high P), long_entry should say NO (low P)
    for ticker in TICKERS:
        tr_pred = [p for t, p in predictions.get('trend_reversal', []) if t == ticker]
        le_pred = [p for t, p in predictions.get('long_entry', []) if t == ticker]
        if tr_pred and le_pred:
            tr_p = tr_pred[0]
            le_p = le_pred[0]
            if tr_p > 0.8 and le_p > 0.8:
                warn(f"{ticker}: trend_reversal={tr_p:.2f} AND long_entry={le_p:.2f} both HIGH — logical tension")
            elif tr_p > 0.8 and le_p < 0.3:
                ok(f"{ticker}: trend_reversal HIGH + long_entry LOW — logically consistent")

    # Check: swing_exit and pullback_depth should be somewhat inversely correlated
    se_vals = [p for _, p in predictions.get('swing_exit', [])]
    pd_vals = [p for _, p in predictions.get('pullback_depth', [])]
    if se_vals and pd_vals:
        corr = np.corrcoef(se_vals, pd_vals)[0, 1]
        check_warn(abs(corr) < 0.9, f"swing_exit ↔ pullback_depth correlation: {corr:.3f} (not redundant)",
                   f"swing_exit ↔ pullback_depth correlation: {corr:.3f} — POSSIBLY REDUNDANT")

    # Check: predictions should have variance (not all same value)
    for head in HEADS:
        vals = [p for _, p in predictions.get(head, [])]
        if vals:
            std = np.std(vals)
            check(std > 0.01, f"{head}: prediction std={std:.4f} (model discriminates)",
                  f"{head}: prediction std={std:.4f} — model not discriminating!")


def audit_readiness_state():
    """Check training_readiness.json is up to date."""
    p("AUDIT 4: READINESS STATE")

    path = MODELS_DIR / "training_readiness.json"
    check(path.exists(), "training_readiness.json exists", "training_readiness.json MISSING!")

    if path.exists():
        with open(path) as f:
            state = json.load(f)

        timestamp = state.get('timestamp', 'UNKNOWN')
        print(f"    Last updated: {timestamp}")

        heads_state = state.get('heads', {})
        check(len(heads_state) == 8, f"{len(heads_state)}/8 heads in readiness state", f"Only {len(heads_state)}/8 heads!")

        for head_name, info in heads_state.items():
            grade = info.get('grade', '?')
            n = info.get('n_observations', 0)
            print(f"    {head_name:>20s}: Grade {grade} N={n:,d}")


def audit_config_model_match():
    """Verify that config features match what the model expects."""
    p("AUDIT 5: CONFIG ↔ MODEL FEATURE MATCH")

    for head in HEADS:
        pkl_path = MODELS_DIR / f"head_{head}_v2.pkl"
        cfg_path = MODELS_DIR / f"head_{head}_config.json"

        if not pkl_path.exists() or not cfg_path.exists():
            continue

        with open(pkl_path, 'rb') as f:
            model_dict = pickle.load(f)
        with open(cfg_path, 'r') as f:
            config = json.load(f)

        pkl_features = model_dict.get('feature_cols', [])
        xgb_model = model_dict.get('model')
        model_n_features = xgb_model.n_features_in_ if xgb_model else 0
        cfg_n_features = len(config.get('feature_importance', {}))

        check(len(pkl_features) == model_n_features,
              f"{head}: pkl features ({len(pkl_features)}) == XGBoost expects ({model_n_features})",
              f"{head}: MISMATCH! pkl={len(pkl_features)} vs XGBoost={model_n_features}")
        check(cfg_n_features == model_n_features,
              f"{head}: config importance ({cfg_n_features}) == XGBoost expects ({model_n_features})",
              f"{head}: MISMATCH! config={cfg_n_features} vs XGBoost={model_n_features}")


def main():
    t0 = time.time()
    p("AUDITORÍA INTEGRAL — PRE-PRODUCTION QUALITY GATE")
    print(f"  Models dir: {MODELS_DIR}")
    print(f"  Tickers: {len(TICKERS)}")
    print(f"  Heads: {len(HEADS)}")

    store = TimescaleDataStore()

    audit_data_integrity(store)
    audit_model_integrity()
    audit_config_model_match()
    audit_prediction_sanity(store)
    audit_readiness_state()

    store.close()
    elapsed = time.time() - t0

    p("AUDIT SUMMARY")
    total = findings["pass"] + findings["warn"] + findings["fail"]
    print(f"  ✅ PASS: {findings['pass']}")
    print(f"  ⚠️  WARN: {findings['warn']}")
    print(f"  ❌ FAIL: {findings['fail']}")
    print(f"  Total checks: {total}")
    print(f"  Time: {elapsed:.1f}s")

    if findings["fail"] == 0:
        print(f"\n  ★★★ QUALITY GATE: PASSED ★★★")
        print(f"  All systems nominal. Ready for production integration.")
    else:
        print(f"\n  ✖ QUALITY GATE: FAILED — {findings['fail']} critical issues")


if __name__ == "__main__":
    main()
