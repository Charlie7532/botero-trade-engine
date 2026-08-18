#!/usr/bin/env python3
"""
Feature Optimizer — Simons Discovery + López de Prado Validation
=================================================================
Phase 0: Expand feature lake with 42 derived features (blind spots)
Phase 1: SFI — Single Feature Importance per head (each feature alone)
Phase 2: Orthogonality clustering (hierarchical, |r| < 0.7)
Phase 3: Sequential Forward Selection with DSR
Phase 4: Cross-reference + dictamen

Usage:
    nohup python backend/scripts/feature_optimizer.py > /dev/null 2>&1 &
    tail -f backend/scratch/optimization_results/progress.log
"""
import sys
import gc
import json
import time
import pickle
import traceback
import warnings
from pathlib import Path
from datetime import datetime, timezone
from io import StringIO

warnings.filterwarnings("ignore")
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend" / "scripts"))

from dotenv import load_dotenv
load_dotenv(root / ".env")

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from unified_pretrainer_v2 import (
    load_feature_lake, HEAD_CONFIGS, ALL_FEATURES,
    DB_FEATURES, COMPUTED_FEATURES, PHASE1_FEATURES, DELTA_SOURCES,
    label_long_entry, label_swing_exit, label_pullback_depth,
    label_trend_reversal, label_short_entry, label_short_cover,
    label_bounce_height, label_trend_recovery, label_zz_turning_point,
    apply_context, purged_walk_forward_cv, compute_dsr,
)
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore

MODELS_DIR = root / "data" / "models"
RESULTS_DIR = root / "backend" / "scratch" / "optimization_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = RESULTS_DIR / "progress.log"


# ═══════════════════════════════════════════════════════════════
# LOGGING — dual output (console + file)
# ═══════════════════════════════════════════════════════════════

def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def log_section(title):
    sep = "=" * 90
    log(sep)
    log(f"  {title}")
    log(sep)


# ═══════════════════════════════════════════════════════════════
# PHASE 0: Expand Feature Lake
# ═══════════════════════════════════════════════════════════════

DERIVED_FEATURES = []  # Will be populated by expand_feature_lake


def safe_div(a, b, fill=0.0):
    """Safe division avoiding inf/nan."""
    result = np.where(np.abs(b) > 1e-8, a / b, fill)
    return np.nan_to_num(result, nan=fill, posinf=fill, neginf=fill)


def expand_feature_lake(df):
    """Generate derived features from existing data. Returns list of new column names."""
    new_features = []

    def add(name, values):
        df[name] = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
        new_features.append(name)

    # ── RATIOS (cross-timeframe divergence) ──
    add('sigma_ratio_tw', safe_div(df['sigma_tide'].values, df['sigma_wave'].values))
    add('slope_ratio_tc', safe_div(df['tide_slope'].values, df['current_slope'].values))
    add('slope_ratio_tw', safe_div(df['tide_slope'].values, df['wave_slope'].values))
    add('tension_ratio_tw', safe_div(df['tension_tide'].values, df['tension_wave'].values))

    # ── SLOPE DIFFERENCES (cross-TF, same instant) ──
    add('slope_diff_tc', df['tide_slope'].values - df['current_slope'].values)
    add('slope_diff_tw', df['tide_slope'].values - df['wave_slope'].values)
    add('slope_diff_cw', df['current_slope'].values - df['wave_slope'].values)

    # ── SLOPES SQUARED (non-linear extreme detection) ──
    add('tide_slope_sq', df['tide_slope'].values ** 2)
    add('current_slope_sq', df['current_slope'].values ** 2)
    add('wave_slope_sq', df['wave_slope'].values ** 2)
    add('slope_energy', np.abs(df['tide_slope'].values) + np.abs(df['current_slope'].values) + np.abs(df['wave_slope'].values))
    add('slope_product_tc', df['tide_slope'].values * df['current_slope'].values)

    # ── ANGULAR ──
    add('slope_phase_tw', np.arctan(df['tide_slope'].values - df['wave_slope'].values))
    add('sigma_phase_tc', np.arctan(df['sigma_tide'].values - df['sigma_current'].values))

    # ── INTERACTIONS ──
    add('rsi_sigma_interact', df['rsi_value'].values * df['sigma_tide'].values)
    add('kalman_slope_conf', df['kalman_velocity'].values * df['tide_slope'].values)
    add('compr_at_extreme', df['compression_ratio'].values * np.abs(df['sigma_tide'].values))
    add('vol_slope_conf', df['vol_up_down_ratio'].values * df['tide_slope'].values)

    # ── VELOCITIES (missing deltas) ──
    for src in ['sigma_tide', 'sigma_current', 'tide_accel', 'current_slope',
                'tension_tide', 'conj_wave_tide', 'vwap_sigma_tide', 'spread_tide_wave']:
        col = f'd2_{src}'  # d2_ prefix to distinguish from existing d_ deltas
        vals = df[src].values.astype(float)
        delta = np.zeros_like(vals)
        # Group by ticker for proper bar-over-bar
        for tk in df['ticker'].unique():
            mask = (df['ticker'] == tk).values
            tk_vals = vals[mask]
            tk_delta = np.diff(tk_vals, prepend=tk_vals[0])
            delta[mask] = tk_delta
        add(col, delta)

    # ── ALIGNMENT ──
    add('triple_alignment', np.sign(df['tide_slope'].values) * np.sign(df['current_slope'].values) * np.sign(df['wave_slope'].values))
    bullish = ((df['sigma_tide'].values > 0).astype(float) +
               (df['sigma_current'].values > 0).astype(float) +
               (df['sigma_wave'].values > 0).astype(float)) / 3.0
    add('bullish_score', bullish)
    add('total_displacement', np.abs(df['sigma_tide'].values) + np.abs(df['sigma_current'].values) + np.abs(df['sigma_wave'].values))

    # ── DISTANCE / EXTREMES ──
    add('price_vwap_div', df['sigma_tide'].values - df['vwap_sigma_tide'].values)
    add('sigma_abs_dist', np.abs(df['sigma_tide'].values))
    add('sigma_squared', df['sigma_tide'].values ** 2)
    sigma_stack = np.stack([df['sigma_tide'].values, df['sigma_current'].values, df['sigma_wave'].values])
    add('sigma_max_tf', np.max(sigma_stack, axis=0))
    add('sigma_min_tf', np.min(sigma_stack, axis=0))

    # ── VOLATILIDAD: ATR (Average True Range) — 14 periodos ──
    if 'high_price' in df.columns and 'low_price' in df.columns:
        high = df['high_price'].values.astype(float)
        low = df['low_price'].values.astype(float)
        close_prev = df.groupby('ticker')['price'].shift(1).bfill().values.astype(float)
        tr = np.maximum(high - low, np.maximum(np.abs(high - close_prev), np.abs(low - close_prev)))

        atr_14 = np.zeros_like(tr)
        for tk in df['ticker'].unique():
            mask = (df['ticker'] == tk).values
            tk_tr = tr[mask]
            tk_atr = pd.Series(tk_tr).rolling(14, min_periods=1).mean().values
            atr_14[mask] = tk_atr

        add('atr_14', atr_14)
        atr_ratio = safe_div(atr_14, df['price'].values.astype(float))
        add('atr_ratio', atr_ratio)
        log(f"  ATR features computed")
    else:
        log(f"  high_price/low_price not in lake — ATR skipped", "WARN")
        atr_ratio = None

    # ── OVERNIGHT SURPRISE GAP ──
    if 'open_price' in df.columns:
        prev_close = df.groupby('ticker')['price'].shift(1).bfill().values.astype(float)
        raw_gap = safe_div(df['open_price'].values.astype(float) - prev_close, prev_close)
        add('overnight_gap', raw_gap)

        # Gap normalizado por volatilidad (Gap en unidades de ATR)
        if atr_ratio is not None:
            gap_atr = safe_div(raw_gap, atr_ratio)
            add('overnight_gap_atr', gap_atr)
            # Interacción Gap vs Tendencia (momentum vs reversión)
            gap_vs_tide = gap_atr * df['tide_slope'].values.astype(float)
            add('overnight_gap_vs_tide', gap_vs_tide)
        log(f"  Overnight gap features computed")
    else:
        log(f"  open_price not in lake — overnight gap skipped", "WARN")

    # ── VOLUME FEATURES (Wyckoff Volume Dynamics) ──
    if 'volume' in df.columns:
        vol = df['volume'].values.astype(float)

        # 1. Volume Ratio (current / MA20) — basic relative volume
        vol_ratio = np.zeros_like(vol)
        vol_sigma = np.zeros_like(vol)
        vol_accel = np.zeros_like(vol)
        vol_trend = np.zeros_like(vol)

        for tk in df['ticker'].unique():
            mask = (df['ticker'] == tk).values
            tk_vol = pd.Series(vol[mask])

            # MA20 y MA5 del volumen
            vol_ma20 = tk_vol.rolling(20, min_periods=1).mean()
            vol_ma5 = tk_vol.rolling(5, min_periods=1).mean()
            vol_std20 = tk_vol.rolling(20, min_periods=2).std().fillna(1.0)

            # Ratio: volumen actual vs su media de 20d
            ratio = safe_div(tk_vol.values, vol_ma20.values)
            vol_ratio[mask] = ratio

            # Sigma: cuántas desviaciones estándar del volumen vs su propia media
            # (Bollinger Band del volumen — mide la "sorpresa" en la actividad)
            vsig = safe_div(tk_vol.values - vol_ma20.values, vol_std20.values)
            vol_sigma[mask] = vsig

            # Aceleración: delta bar-over-bar del ratio de volumen
            # (¿el volumen está AUMENTANDO o DISMINUYENDO su ritmo?)
            ratio_s = pd.Series(ratio)
            vaccel = ratio_s.diff().fillna(0.0).values
            vol_accel[mask] = vaccel

            # Tendencia del volumen: MA5/MA20 — ¿la actividad reciente supera la histórica?
            vtrend = safe_div(vol_ma5.values, vol_ma20.values)
            vol_trend[mask] = vtrend

        add('volume_ratio', vol_ratio)
        add('volume_sigma', vol_sigma)        # Cuántas σ sobre/bajo la media
        add('volume_accel', vol_accel)         # Δ(ratio) bar-over-bar
        add('volume_trend', vol_trend)         # MA5/MA20 del volumen

        # 2. Volume-Price Divergence (Wyckoff core principle)
        # Precio sube (sigma positivo) pero volumen cae (ratio < 1) = distribución
        # Precio baja (sigma negativo) pero volumen sube (ratio > 1) = acumulación
        price_dir = np.sign(df['tide_slope'].values.astype(float))
        vol_dir = np.sign(vol_ratio - 1.0)  # >1 = volumen alto, <1 = volumen bajo
        add('vol_price_divergence', price_dir * vol_dir)  # +1=confirm, -1=diverge

        # 3. Volume Exhaustion (spikes de capitulación/climax)
        # Volumen > 2σ sobre la media → exhaustion/climax volume
        add('volume_exhaustion', (vol_sigma > 2.0).astype(float))

        # 4. Interacciones volumen-estructura
        # Volume × slope (alta actividad confirmando la pendiente = convicción Wyckoff)
        add('volume_slope_confirm', vol_ratio * df['tide_slope'].values.astype(float))

        # Volume × sigma_tide (volumen en extremos de canal = señal de resolución)
        add('volume_at_extreme', vol_ratio * np.abs(df['sigma_tide'].values.astype(float)))

        # Volume accel × wave_slope (aceleración de volumen en dirección de la onda)
        add('vol_accel_wave', vol_accel * df['wave_slope'].values.astype(float))

        log(f"  Volume features computed (Wyckoff dynamics: 10 features)")

        # ── VOL-PRICE CORRELATION (forensic-validated: t=-50.9 at floors) ──
        # These 6 features were selected from the Vol-Price Forencia for Challenger v3.
        # Each was validated for orthogonality, SFI significance, and t-test at extremes.
        n_vp = 0
        close_vals = df['price'].values.astype(float)

        for tk in df['ticker'].unique():
            mask = (df['ticker'] == tk).values
            idx_tk = np.where(mask)[0]
            tk_close = close_vals[mask]
            tk_vol = vol[mask]
            tk_high = df.loc[mask, 'high_price'].values.astype(float) if 'high_price' in df.columns else tk_close
            tk_low = df.loc[mask, 'low_price'].values.astype(float) if 'low_price' in df.columns else tk_close
            n_tk = len(tk_close)

            tk_returns = np.zeros(n_tk)
            tk_returns[1:] = (tk_close[1:] - tk_close[:-1]) / np.where(tk_close[:-1] > 0, tk_close[:-1], 1.0)

            # Rolling volume stats (reuse from above is not possible — we need Series)
            tk_vol_s = pd.Series(tk_vol)
            tk_ret_s = pd.Series(tk_returns)
            tk_vol_ma20 = tk_vol_s.rolling(20, min_periods=1).mean()
            tk_vol_std20 = tk_vol_s.rolling(20, min_periods=2).std().fillna(1.0)
            tk_candle_range = tk_high - tk_low
            tk_candle_range_safe = np.where(tk_candle_range > 0, tk_candle_range, 1e-8)

            # 1. vol_price_corr_20d: Rolling Pearson correlation (vol, returns, 20d)
            #    t=-50.9 at floors ★★★, |r|=0.478 vs rsi → moderate but unique signal
            corr_20d = tk_vol_s.rolling(20, min_periods=20).corr(tk_ret_s).values
            if 'vol_price_corr_20d' not in df.columns:
                df['vol_price_corr_20d'] = 0.0
            df.loc[mask, 'vol_price_corr_20d'] = np.nan_to_num(corr_20d, nan=0.0).astype(np.float32)

            # 2. effort_vs_result_20d: Wyckoff effort/result (log-normalized)
            #    avg_vol / (avg_range × close) — HIGH effort + LOW result = accumulation
            #    SFI ★★, |r|=0.111 → fully orthogonal. Log-normalized to avoid billion-scale values.
            if 'effort_vs_result_20d' not in df.columns:
                df['effort_vs_result_20d'] = 0.0
            tk_vol_ma20_vals = tk_vol_ma20.values
            tk_range_ma20 = pd.Series(tk_candle_range_safe).rolling(20, min_periods=1).mean().values
            raw_effort = safe_div(tk_vol_ma20_vals, tk_range_ma20 * np.where(tk_close > 0, tk_close, 1.0))
            log_effort = np.log1p(np.abs(raw_effort)) * np.sign(raw_effort)
            df.loc[mask, 'effort_vs_result_20d'] = np.nan_to_num(log_effort, nan=0.0).astype(np.float32)

            # 3. climax_vol_ratio: current vol / max(vol, 20d)
            #    SFI ★, |r|=0.101 → orthogonal. Detects volume climax events.
            vol_max_20 = tk_vol_s.rolling(20, min_periods=5).max().values
            climax = safe_div(tk_vol, vol_max_20)
            if 'climax_vol_ratio' not in df.columns:
                df['climax_vol_ratio'] = 0.0
            df.loc[mask, 'climax_vol_ratio'] = np.nan_to_num(climax, nan=0.0).astype(np.float32)

            # 4. vol_return_interaction: vol z-score × return (instantaneous)
            #    t=-9.62 at floors ★★, |r|=0.202 → orthogonal.
            vol_z = safe_div(tk_vol - tk_vol_ma20.values, tk_vol_std20.values)
            vri = vol_z * tk_returns
            if 'vol_return_interaction' not in df.columns:
                df['vol_return_interaction'] = 0.0
            df.loc[mask, 'vol_return_interaction'] = np.nan_to_num(vri, nan=0.0).astype(np.float32)

            # 5. vol_breakout_signal: vol spike × range expansion
            #    |r|=0.028 → MOST orthogonal feature. Detects breakout events.
            range_mean = pd.Series(tk_candle_range_safe).rolling(20, min_periods=1).mean().values
            range_std = pd.Series(tk_candle_range_safe).rolling(20, min_periods=2).std().fillna(1.0).values
            range_z = safe_div(tk_candle_range - range_mean, range_std)
            vbs = vol_z * range_z
            if 'vol_breakout_signal' not in df.columns:
                df['vol_breakout_signal'] = 0.0
            df.loc[mask, 'vol_breakout_signal'] = np.nan_to_num(vbs, nan=0.0).astype(np.float32)

            # 6. vol_price_regime: categorical Wyckoff vol-price state
            #    +2=confirmed rally, +1=suspicious rally, -1=orderly decline, -2=panic, 0=neutral
            #    t=-33.97 at floors ★★★, SFI ★. |r|=0.456 → moderate but unique regime info.
            ret_5d = np.zeros(n_tk)
            ret_5d[5:] = (tk_close[5:] - tk_close[:-5]) / np.where(tk_close[:-5] > 0, tk_close[:-5], 1.0)
            regime = np.zeros(n_tk)
            regime[(vol_z > 1.0) & (ret_5d > 0.01)] = 2.0    # Confirmed rally
            regime[(vol_z < -0.5) & (ret_5d > 0.01)] = 1.0    # Suspicious rally
            regime[(vol_z < -0.5) & (ret_5d < -0.01)] = -1.0  # Orderly decline
            regime[(vol_z > 1.0) & (ret_5d < -0.01)] = -2.0   # Panic selling
            if 'vol_price_regime' not in df.columns:
                df['vol_price_regime'] = 0.0
            df.loc[mask, 'vol_price_regime'] = regime.astype(np.float32)

        # Register the 6 new features
        for vp_feat in ['vol_price_corr_20d', 'effort_vs_result_20d', 'climax_vol_ratio',
                        'vol_return_interaction', 'vol_breakout_signal', 'vol_price_regime']:
            new_features.append(vp_feat)
        n_vp = 6
        log(f"  Vol-Price features computed (Forencia-validated: {n_vp} features)")
    else:
        log(f"  volume not in lake — volume features skipped", "WARN")

    # ── CANDLE STRUCTURE: σ(HIGH/LOW), Close Position, Divergencias ──
    has_hl = 'high_price' in df.columns and 'low_price' in df.columns
    has_reg = 'reg_value_tide' in df.columns and 'residual_std_tide' in df.columns
    if has_hl and has_reg:
        high = df['high_price'].values.astype(float)
        low = df['low_price'].values.astype(float)
        close = df['price'].values.astype(float)
        open_p = df['open_price'].values.astype(float) if 'open_price' in df.columns else close

        # 1. Close Position (Wyckoff): dónde cierra la vela en su rango (0=LOW, 1=HIGH)
        candle_range = np.where(high - low > 0, high - low, np.nan)
        close_pos = (close - low) / candle_range
        add('close_position', np.nan_to_num(close_pos, nan=0.5))

        # Body ratio: |close-open| / range (convicción de la vela)
        body = np.abs(close - open_p)
        add('body_ratio', np.nan_to_num(body / candle_range, nan=0.5))

        # 2. σ(HIGH) y σ(LOW) para cada canal de regresión
        n_candle = 0
        for tf in ['tide', 'current', 'wave']:
            reg_col = f'reg_value_{tf}'
            std_col = f'residual_std_{tf}'
            if reg_col in df.columns and std_col in df.columns:
                center = df[reg_col].values.astype(float)
                std = df[std_col].values.astype(float)
                std_safe = np.where(std > 0, std, np.nan)

                sh = (high - center) / std_safe
                sl = (low - center) / std_safe
                add(f'sigma_high_{tf}', np.nan_to_num(sh, nan=0.0))
                add(f'sigma_low_{tf}', np.nan_to_num(sl, nan=0.0))

                # σ Range: ancho de la vela en unidades σ (expansión = convicción)
                add(f'sigma_range_{tf}', np.nan_to_num(sh - sl, nan=0.0))

                # Divergencia HIGH-CLOSE y CLOSE-LOW (estiramiento intradía)
                sc = df[f'sigma_{tf}'].values.astype(float)
                add(f'div_high_close_{tf}', np.nan_to_num(sh - sc, nan=0.0))
                add(f'div_close_low_{tf}', np.nan_to_num(sc - sl, nan=0.0))
                n_candle += 5

        # 3. VWAP σ(HIGH) y VWAP σ(LOW): extremos relativos al VWAP institucional
        for tf in ['tide', 'current']:
            vwap_col = f'vwap_{tf}'
            std_col = f'residual_std_{tf}'
            if vwap_col in df.columns and std_col in df.columns:
                vwap = df[vwap_col].values.astype(float)
                std = df[std_col].values.astype(float)
                std_safe = np.where(std > 0, std, np.nan)

                vsh = (high - vwap) / std_safe
                vsl = (low - vwap) / std_safe
                add(f'vwap_sigma_high_{tf}', np.nan_to_num(vsh, nan=0.0))
                add(f'vwap_sigma_low_{tf}', np.nan_to_num(vsl, nan=0.0))

                # Institutional rejection: VWAP_σ(extreme) - Price_σ(extreme)
                # Positivo = extremo no llega al VWAP (rechazado)
                # Negativo = extremo SUPERA el VWAP (agresión)
                sc_vwap = df[f'vwap_sigma_{tf}'].values.astype(float)
                sc_price = df[f'sigma_{tf}'].values.astype(float)
                sh_price = np.nan_to_num((high - df[f'reg_value_{tf}'].values.astype(float)) / std_safe, nan=0.0)
                add(f'inst_rejection_high_{tf}', np.nan_to_num(vsh, nan=0.0) - sh_price)
                n_candle += 3

        log(f"  Candle structure features computed ({n_candle + 2} features)")
    else:
        missing = []
        if not has_hl: missing.append('high/low')
        if not has_reg: missing.append('reg_value/residual_std')
        log(f"  Candle structure skipped — missing: {', '.join(missing)}", "WARN")

    # ── VWAP STRUCTURAL (forensic-validated: 2 dictámenes) ──
    # 6 features from VWAP Sigma Spread + VWAP Regression dictámenes.
    # All orthogonal (r≤0.38) with t-stats ≥ 9.8 at zigzag turning points.
    n_vwap_struct = 0
    for tf in ['tide', 'current']:
        vwap_sh = f'vwap_sigma_high_{tf}'
        vwap_sl = f'vwap_sigma_low_{tf}'
        if vwap_sh in df.columns and vwap_sl in df.columns:
            # 1. VWAP σ Spread: σ(HIGH) - σ(LOW) — institutional range width
            #    Pisos: expansión (+0.568), Techos: contracción (0.446)
            #    t=17.9 (tide) / t=9.8 (current) at floors ★★★
            spread = df[vwap_sh].values.astype(float) - df[vwap_sl].values.astype(float)
            add(f'vwap_sigma_spread_{tf}', spread)
            n_vwap_struct += 1

            # 2. Spread Ratio: spread / rolling_MA20(spread) — relative institutional activity
            #    >1 = expanding (accumulation), <1 = contracting (low interest)
            #    t=16.0 (tide) at floors ★★★. Only for tide (current is noisier).
            if tf == 'tide':
                spread_ratio = np.zeros_like(spread)
                for tk in df['ticker'].unique():
                    mask_tk = (df['ticker'] == tk).values
                    tk_spread = pd.Series(spread[mask_tk])
                    tk_ma20 = tk_spread.rolling(20, min_periods=1).mean()
                    spread_ratio[mask_tk] = safe_div(tk_spread.values, tk_ma20.values)
                add('vwap_spread_ratio_tide', spread_ratio)
                n_vwap_struct += 1

    # 3. VWAP in Channel (Current): (VWAP - regression center) / std
    #    t=19.1 at floors ★★★ — THE strongest VWAP signal
    #    Pisos: VWAP rises INTO the channel (institutional buying)
    #    Techos: VWAP stays below (institutions not participating)
    if 'vwap_current' in df.columns and 'reg_value_current' in df.columns and 'residual_std_current' in df.columns:
        vwap_c = df['vwap_current'].values.astype(float)
        reg_c = df['reg_value_current'].values.astype(float)
        std_c = df['residual_std_current'].values.astype(float)
        std_c_safe = np.where(std_c > 0, std_c, 1e-8)
        vinch = (vwap_c - reg_c) / std_c_safe
        add('vwap_in_channel_current', np.nan_to_num(vinch, nan=0.0))
        n_vwap_struct += 1

    # 4. Slope Divergence (Current): current_slope - vwap_slope_current
    #    t=-13.7 at floors ★★★ — price slope DIVERGES from VWAP slope = accumulation
    if 'current_slope' in df.columns and 'vwap_current' in df.columns:
        # Compute vwap_slope_current as bar-over-bar delta of vwap_current
        vwap_slope_c = np.zeros(len(df))
        for tk in df['ticker'].unique():
            mask_tk = (df['ticker'] == tk).values
            tk_vwap = df.loc[mask_tk, 'vwap_current'].values.astype(float)
            slope = np.zeros_like(tk_vwap)
            slope[1:] = tk_vwap[1:] - tk_vwap[:-1]
            vwap_slope_c[mask_tk] = slope
        slope_div = df['current_slope'].values.astype(float) - vwap_slope_c
        add('slope_div_current', slope_div)
        n_vwap_struct += 1

    # 5. VWAP Accel (Tide): Δ(vwap_slope_tide) — VWAP momentum change
    #    t=-10.0, r≤0.38 vs all existing ★★. Only genuinely orthogonal VWAP tide feature.
    if 'vwap_tide' in df.columns:
        vwap_accel = np.zeros(len(df))
        for tk in df['ticker'].unique():
            mask_tk = (df['ticker'] == tk).values
            tk_vwap = df.loc[mask_tk, 'vwap_tide'].values.astype(float)
            slope = np.zeros_like(tk_vwap)
            slope[1:] = tk_vwap[1:] - tk_vwap[:-1]
            accel = np.zeros_like(slope)
            accel[1:] = slope[1:] - slope[:-1]
            vwap_accel[mask_tk] = accel
        add('vwap_accel_tide', vwap_accel)
        n_vwap_struct += 1

    if n_vwap_struct > 0:
        log(f"  VWAP structural features computed (Forencia-validated: {n_vwap_struct} features)")

    log(f"  Generated {len(new_features)} derived features")
    return new_features


# ═══════════════════════════════════════════════════════════════
# LABELING
# ═══════════════════════════════════════════════════════════════

def compute_labels(head_name, df, ohlcv_cache, profiles, store):
    """Compute labels for a head. Returns float numpy array."""
    cfg = HEAD_CONFIGS[head_name]
    if head_name == 'zz_bottom_detector':
        labels = label_zz_turning_point(df, store, tp_type='MIN', proximity_window=3)
    elif head_name == 'zz_top_detector':
        labels = label_zz_turning_point(df, store, tp_type='MAX', proximity_window=3)
    elif head_name in ('trend_reversal', 'trend_recovery'):
        labeler = {'trend_reversal': label_trend_reversal, 'trend_recovery': label_trend_recovery}[head_name]
        labels = labeler(df, ohlcv_cache, profiles, horizon=cfg['horizon'])
    elif head_name == 'long_entry':
        labels = label_long_entry(df, ohlcv_cache, horizon=cfg['horizon'])
    elif head_name == 'short_entry':
        labels = label_short_entry(df, ohlcv_cache, horizon=cfg['horizon'])
    elif head_name == 'swing_exit':
        labels = label_swing_exit(df, ohlcv_cache)
    elif head_name == 'short_cover':
        labels = label_short_cover(df, ohlcv_cache)
    elif head_name == 'pullback_depth':
        labels = label_pullback_depth(df, ohlcv_cache)
    elif head_name == 'bounce_height':
        labels = label_bounce_height(df, ohlcv_cache)
    else:
        raise ValueError(f"Unknown head: {head_name}")
    return np.array(labels, dtype=float)


# ═══════════════════════════════════════════════════════════════
# TRAINING (streamlined for optimizer)
# ═══════════════════════════════════════════════════════════════

def train_quick(df_head, labels, feature_cols, horizon, n_splits=5, mode='dsr'):
    """Train with walk-forward CV. Returns {dsr, importances, auc_sfi} or None.
    
    mode='dsr': full DSR with thresholded spread (for forward selection)
    mode='auc': AUC-based SFI score (for single-feature importance)
    """
    try:
        from xgboost import XGBClassifier

        # Build feature matrix
        feat_data = {}
        for f in feature_cols:
            if f in df_head.columns:
                feat_data[f] = df_head[f].values.astype(np.float32)
            else:
                feat_data[f] = np.zeros(len(df_head), dtype=np.float32)

        X_df = pd.DataFrame(feat_data)
        valid_mask = (~np.isnan(labels)) & X_df.notna().all(axis=1).values
        X_all = X_df[valid_mask].values.astype(np.float32)
        y_all = labels[valid_mask].astype(int)

        if len(y_all) < 200 or y_all.sum() < 20:
            return None

        # Sort temporally
        ts = df_head[valid_mask]['timestamp'].values
        sort_idx = np.argsort(ts)
        X_all = X_all[sort_idx]
        y_all = y_all[sort_idx]

        # Purged Walk-Forward CV
        splits = purged_walk_forward_cv(len(X_all), n_splits=n_splits, purge_gap=horizon)
        fold_sharpes = []
        fold_aucs = []

        for train_idx, test_idx in splits:
            X_tr, y_tr = X_all[train_idx], y_all[train_idx]
            X_te, y_te = X_all[test_idx], y_all[test_idx]

            n_pos = y_tr.sum()
            n_neg = len(y_tr) - n_pos
            sw = max(n_neg / max(n_pos, 1), 1.0)

            model = XGBClassifier(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                min_child_weight=10, subsample=0.8, colsample_bytree=0.7,
                reg_alpha=0.1, reg_lambda=1.0,
                scale_pos_weight=min(sw, 5.0),
                random_state=42, eval_metric='logloss', tree_method='hist',
                verbosity=0,
            )
            model.fit(X_tr, y_tr, verbose=False)

            y_prob = model.predict_proba(X_te)[:, 1]

            # AUC-based metric (no threshold sensitivity)
            try:
                auc = roc_auc_score(y_te, y_prob)
            except ValueError:
                auc = 0.5
            fold_aucs.append(auc)

            # DSR-thresholded metric (for forward selection)
            if mode == 'dsr':
                high_p = y_prob >= 0.65
                low_p = y_prob < 0.35
                wr_h = y_te[high_p].mean() if high_p.sum() > 20 else float('nan')
                wr_l = y_te[low_p].mean() if low_p.sum() > 20 else float('nan')
                spread = wr_h - wr_l if not (np.isnan(wr_h) or np.isnan(wr_l)) else 0.0
                fold_sharpes.append(spread / max(0.01, y_te.std()))

            del model, X_tr, y_tr, X_te, y_te
        gc.collect()

        # Compute metrics based on mode
        auc_sfi = abs(float(np.mean(fold_aucs)) - 0.5)

        if mode == 'dsr':
            dsr = compute_dsr(fold_sharpes)
        else:
            dsr = auc_sfi  # For SFI mode, the "dsr" field carries the AUC-SFI score

        # Final model for importances (only if multiple features)
        importances = {}
        if len(feature_cols) > 1:
            sw = max((len(y_all) - y_all.sum()) / max(y_all.sum(), 1), 1.0)
            final = XGBClassifier(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                min_child_weight=10, subsample=0.8, colsample_bytree=0.7,
                reg_alpha=0.1, reg_lambda=1.0,
                scale_pos_weight=min(sw, 5.0),
                random_state=42, eval_metric='logloss', tree_method='hist',
                verbosity=0,
            )
            final.fit(X_all, y_all, verbose=False)
            importances = dict(zip(feature_cols, final.feature_importances_))
            del final

        del X_all, y_all
        gc.collect()

        return {
            'dsr': float(dsr),
            'auc_sfi': float(auc_sfi),
            'mean_auc': float(np.mean(fold_aucs)),
            'importances': importances,
            'fold_sharpes': fold_sharpes if mode == 'dsr' else [],
            'fold_aucs': fold_aucs,
        }

    except Exception as e:
        log(f"  train_quick error: {e}", "ERROR")
        return None


# ═══════════════════════════════════════════════════════════════
# PHASE 1: Single Feature Importance (AUC-based, no threshold)
# ═══════════════════════════════════════════════════════════════

SFI_THRESHOLD = 0.005  # AUC >= 0.505 or <= 0.495 → 3σ significance with N≈93K

def run_sfi(head_name, df_ctx, labels_ctx, all_feature_names, horizon):
    """Run SFI for one head using AUC-based metric. Returns dict of feature -> auc_sfi_score."""
    sfi = {}
    total = len(all_feature_names)

    for i, feat in enumerate(all_feature_names):
        if feat not in df_ctx.columns:
            sfi[feat] = 0.0
            continue

        try:
            result = train_quick(df_ctx, labels_ctx, [feat], horizon, n_splits=3, mode='auc')
            score = result['auc_sfi'] if result else 0.0
            sfi[feat] = score

            if (i + 1) % 10 == 0 or score > SFI_THRESHOLD:
                viable = " ★" if score > SFI_THRESHOLD else ""
                auc_str = f"AUC={result['mean_auc']:.4f}" if result else "AUC=N/A"
                log(f"    SFI [{i+1}/{total}] {feat:35s} SFI={score:>7.4f} {auc_str}{viable}")
        except Exception as e:
            log(f"    SFI [{i+1}/{total}] {feat}: ERROR {e}", "WARN")
            sfi[feat] = 0.0

    return sfi


# ═══════════════════════════════════════════════════════════════
# PHASE 2: Orthogonality Clustering
# ═══════════════════════════════════════════════════════════════

def cluster_features(df, feature_names, threshold=0.7):
    """Cluster features by correlation. Returns list of clusters."""
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform

    # Compute correlation matrix
    feat_data = df[feature_names].fillna(0).values.astype(np.float32)
    corr = np.corrcoef(feat_data.T)
    corr = np.nan_to_num(corr, nan=0.0)

    # Distance = 1 - |correlation|
    dist = 1.0 - np.abs(corr)
    np.fill_diagonal(dist, 0)
    dist = np.clip(dist, 0, 2)

    # Make symmetric
    dist = (dist + dist.T) / 2

    # Hierarchical clustering
    condensed = squareform(dist, checks=False)
    Z = linkage(condensed, method='ward')
    labels = fcluster(Z, t=threshold, criterion='distance')

    # Group features by cluster
    clusters = {}
    for feat, label in zip(feature_names, labels):
        clusters.setdefault(int(label), []).append(feat)

    return clusters


# ═══════════════════════════════════════════════════════════════
# PHASE 3: Sequential Forward Selection
# ═══════════════════════════════════════════════════════════════

def forward_selection(head_name, df_ctx, labels_ctx, candidates, horizon):
    """Forward selection: add features one by one, keep only if DSR improves."""
    optimal_set = []
    current_dsr = 0.0
    selection_log = []

    for i, feat in enumerate(candidates):
        test_set = optimal_set + [feat]

        try:
            result = train_quick(df_ctx, labels_ctx, test_set, horizon)
            if result is None:
                log(f"    FWD [{i+1}/{len(candidates)}] {feat}: train failed, SKIP")
                selection_log.append({'feature': feat, 'action': 'SKIP', 'reason': 'train_failed'})
                continue

            test_dsr = result['dsr']
            delta = test_dsr - current_dsr

            if delta > 0:
                optimal_set.append(feat)
                current_dsr = test_dsr
                action = 'ADDED'
                symbol = '✅'
            else:
                action = 'REJECTED'
                symbol = '❌'

            log(f"    FWD [{i+1}/{len(candidates)}] {symbol} {action} '{feat}' "
                f"→ DSR={test_dsr:.4f} (Δ={delta:+.4f}) [{len(optimal_set)}f]")

            selection_log.append({
                'feature': feat,
                'action': action,
                'dsr_after': round(test_dsr, 4),
                'delta': round(delta, 4),
                'n_features': len(optimal_set),
            })

        except Exception as e:
            log(f"    FWD [{i+1}/{len(candidates)}] {feat}: ERROR {e}", "WARN")
            selection_log.append({'feature': feat, 'action': 'ERROR', 'reason': str(e)})

        gc.collect()

    return optimal_set, current_dsr, selection_log


# ═══════════════════════════════════════════════════════════════
# CHECKPOINT SAVE
# ═══════════════════════════════════════════════════════════════

def save_checkpoint(name, data):
    """Save intermediate results to disk."""
    path = RESULTS_DIR / f"{name}.json"
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        log(f"  Checkpoint saved: {path.name}")
    except Exception as e:
        log(f"  Checkpoint save failed: {e}", "ERROR")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    start_time = time.time()

    # Clear log
    LOG_FILE.write_text(f"Feature Optimizer — Started {datetime.now(timezone.utc).isoformat()}\n")

    log_section("FEATURE OPTIMIZER — Simons + López de Prado Protocol")
    log(f"Started: {datetime.now(timezone.utc).isoformat()}")

    # ── Load data ──
    log_section("LOADING DATA")
    store = TimescaleDataStore()
    ps = TickerProfileStore()
    df, ohlcv_cache, profiles = load_feature_lake(store, ps)
    log(f"Feature lake: {len(df):,d} rows, {df.shape[1]} columns")

    # ── Phase 0: Expand feature lake ──
    log_section("PHASE 0: Expand Feature Lake (Simons Discovery)")
    new_features = expand_feature_lake(df)
    EXPANDED_FEATURES = list(ALL_FEATURES) + new_features
    log(f"Expanded lake: {len(EXPANDED_FEATURES)} features ({len(ALL_FEATURES)} original + {len(new_features)} derived)")
    save_checkpoint("phase0_features", {
        'original': list(ALL_FEATURES),
        'derived': new_features,
        'total': len(EXPANDED_FEATURES),
    })

    # ── Current production DSRs ──
    log_section("PRODUCTION BASELINES")
    production_dsrs = {}
    production_features = {}
    for pkl_path in sorted(MODELS_DIR.glob('head_*_v2.pkl')):
        data = pickle.load(open(pkl_path, 'rb'))
        name = pkl_path.stem.replace('head_', '').replace('_v2', '')
        production_dsrs[name] = data.get('dsr', 0)
        production_features[name] = len(data.get('feature_cols', []))
        log(f"  {name:>22s}: DSR={data.get('dsr',0):>7.3f} ({production_features[name]}f)")

    # ── Pre-compute labels ──
    log_section("PRE-COMPUTING LABELS")
    all_labels = {}
    # Support CLI filtering: python feature_optimizer.py head1 head2 ...
    if len(sys.argv) > 1:
        heads_to_run = [h for h in sys.argv[1:] if h in HEAD_CONFIGS]
        log(f"  CLI filter: running {len(heads_to_run)} heads: {heads_to_run}")
    else:
        heads_to_run = list(HEAD_CONFIGS.keys())
    for head_name in heads_to_run:
        try:
            t0 = time.time()
            labels = compute_labels(head_name, df, ohlcv_cache, profiles, store)
            n_valid = (~np.isnan(labels)).sum()
            pos_rate = labels[~np.isnan(labels)].mean() if n_valid > 0 else 0
            all_labels[head_name] = labels
            log(f"  {head_name:>22s}: {n_valid:>7,d} valid, pos={pos_rate:.3f} ({time.time()-t0:.1f}s)")
        except Exception as e:
            log(f"  {head_name}: LABELING FAILED: {e}", "ERROR")
            log(traceback.format_exc(), "ERROR")

    # ══════════════════════════════════════════════════════════
    # PHASE 1: Single Feature Importance
    # ══════════════════════════════════════════════════════════
    log_section("PHASE 1: Single Feature Importance (SFI)")
    log(f"Testing {len(EXPANDED_FEATURES)} features × {len(all_labels)} heads")

    sfi_results = {}
    for head_name in all_labels:
        log(f"\n  ── SFI: {head_name.upper()} ──")
        cfg = HEAD_CONFIGS[head_name]
        labels = all_labels[head_name]

        # Apply context
        ctx_mask = apply_context(df, head_name)
        df_ctx = df[ctx_mask].copy()
        labels_ctx = labels[ctx_mask.values]

        t0 = time.time()
        sfi = run_sfi(head_name, df_ctx, labels_ctx, EXPANDED_FEATURES, cfg['horizon'])
        elapsed = time.time() - t0

        # Sort and report top 10
        sorted_sfi = sorted(sfi.items(), key=lambda x: -x[1])
        log(f"\n  Top 10 features for {head_name}:")
        for rank, (feat, dsr) in enumerate(sorted_sfi[:10], 1):
            is_new = "★NEW" if feat in new_features else ""
            log(f"    {rank:>2d}. {feat:35s} DSR={dsr:>7.3f} {is_new}")

        sfi_results[head_name] = sfi
        log(f"  SFI completed for {head_name} in {elapsed:.0f}s")

        # Checkpoint after each head
        save_checkpoint(f"phase1_sfi_{head_name}", {
            'head': head_name,
            'sfi': {k: round(v, 4) for k, v in sorted_sfi},
            'top_10': [{'feature': f, 'dsr': round(d, 4)} for f, d in sorted_sfi[:10]],
            'elapsed_s': round(elapsed, 1),
        })
        gc.collect()

    # Save full SFI matrix
    save_checkpoint("phase1_sfi_matrix", {
        head: {f: round(d, 4) for f, d in sorted(sfi.items(), key=lambda x: -x[1])}
        for head, sfi in sfi_results.items()
    })

    # ══════════════════════════════════════════════════════════
    # PHASE 2+3: Per-Head Clustering → Forward Selection
    # ══════════════════════════════════════════════════════════
    log_section("PHASE 2+3: Per-Head Clustering → Forward Selection")

    all_results = {}
    all_clusters = {}

    for head_name in all_labels:
        log(f"\n{'─'*80}")
        log(f"  ── HEAD: {head_name.upper()} ──")
        cfg = HEAD_CONFIGS[head_name]
        labels = all_labels[head_name]
        sfi = sfi_results.get(head_name, {})

        ctx_mask = apply_context(df, head_name)
        df_ctx = df[ctx_mask].copy()
        labels_ctx = labels[ctx_mask.values]

        # ── Phase 2: Per-head clustering ──
        viable_for_head = [f for f, s in sfi.items() if s > SFI_THRESHOLD]
        log(f"  Viable features (SFI > {SFI_THRESHOLD}): {len(viable_for_head)} / {len(EXPANDED_FEATURES)}")

        if len(viable_for_head) < 3:
            log(f"  Too few viable features ({len(viable_for_head)}). Using all viable directly.", "WARN")
            clusters_head = {i: [f] for i, f in enumerate(viable_for_head)}
        else:
            try:
                clusters_head = cluster_features(df, viable_for_head, threshold=0.7)
                log(f"  Clusters found: {len(clusters_head)} (from {len(viable_for_head)} viable)")
                for cid, members in sorted(clusters_head.items()):
                    log(f"    Cluster {cid}: [{len(members)}f] {members[:5]}{'...' if len(members)>5 else ''}")
            except Exception as e:
                log(f"  Clustering failed: {e}. Using viable list directly.", "WARN")
                clusters_head = {i: [f] for i, f in enumerate(viable_for_head)}

        all_clusters[head_name] = {str(k): v for k, v in clusters_head.items()}

        # ── Phase 3: Forward Selection using per-head clusters ──
        # Select best representative from each cluster (by SFI for this head)
        candidates = []
        for cid, members in clusters_head.items():
            best_feat = max(members, key=lambda f: sfi.get(f, 0))
            best_sfi = sfi.get(best_feat, 0)
            if best_sfi > 0.0:  # Only include clusters with positive SFI
                candidates.append((best_feat, best_sfi))

        # Sort by SFI descending (most discriminative first)
        candidates.sort(key=lambda x: -x[1])
        candidate_names = [c[0] for c in candidates]
        log(f"  Candidates for FWD: {len(candidate_names)} (from {len(clusters_head)} clusters)")
        log(f"  Top 5: {[(c[0], f'{c[1]:.4f}') for c in candidates[:5]]}")

        if len(candidate_names) == 0:
            log(f"  NO viable candidates for {head_name}. Skipping forward selection.", "WARN")
            all_results[head_name] = {
                'optimal_features': [],
                'final_dsr': 0.0,
                'production_dsr': round(production_dsrs.get(head_name, 0), 4),
                'delta_vs_production': round(-production_dsrs.get(head_name, 0), 4),
                'n_features': 0,
                'n_viable_sfi': len(viable_for_head),
                'n_clusters': len(clusters_head),
                'status': '✖ NO CANDIDATES',
                'selection_log': [],
                'elapsed_s': 0,
            }
            save_checkpoint(f"phase3_result_{head_name}", all_results[head_name])
            continue

        # Forward selection (uses DSR mode for multi-feature evaluation)
        t0 = time.time()
        optimal_set, final_dsr, sel_log = forward_selection(
            head_name, df_ctx, labels_ctx, candidate_names, cfg['horizon']
        )
        elapsed = time.time() - t0

        prod_dsr = production_dsrs.get(head_name, 0)
        delta_prod = final_dsr - prod_dsr

        status = "★ GAIN" if final_dsr > prod_dsr else "≈ SAME" if final_dsr >= prod_dsr * 0.95 else "✖ DROP"

        log(f"\n  ★ RESULT {head_name.upper()}: {len(optimal_set)} features, DSR={final_dsr:.4f}")
        log(f"    Production: DSR={prod_dsr:.3f} ({production_features.get(head_name, '?')}f) → Optimized: DSR={final_dsr:.3f} ({len(optimal_set)}f) [{status}]")
        log(f"    Viable SFI: {len(viable_for_head)} | Clusters: {len(clusters_head)} | Candidates: {len(candidate_names)}")
        log(f"    Features: {optimal_set}")
        log(f"    Elapsed: {elapsed:.0f}s")

        all_results[head_name] = {
            'optimal_features': optimal_set,
            'final_dsr': round(final_dsr, 4),
            'production_dsr': round(prod_dsr, 4),
            'delta_vs_production': round(delta_prod, 4),
            'n_features': len(optimal_set),
            'n_viable_sfi': len(viable_for_head),
            'n_clusters': len(clusters_head),
            'status': status,
            'selection_log': sel_log,
            'elapsed_s': round(elapsed, 1),
        }

        save_checkpoint(f"phase3_result_{head_name}", all_results[head_name])
        gc.collect()

    # Save all clusters
    save_checkpoint("phase2_clusters_per_head", all_clusters)

    # ══════════════════════════════════════════════════════════
    # PHASE 4: ANTI-DROP — Interaction Recovery
    # ══════════════════════════════════════════════════════════
    # BUG FIX (2026-05-26): Previous version had two critical bugs:
    #   1. Missing apply_context() — trained on unfiltered data, changing label
    #      distribution (e.g. trend_recovery pos_rate jumped from ~15% to 50.6%)
    #   2. No max-features guard — Strategy B accepted 137 features, causing
    #      XGBoost memorization (DSR=116 with 137f = pure overfit)
    # ══════════════════════════════════════════════════════════
    log_section("PHASE 4: ANTI-DROP (Interaction Recovery)")
    log("  Forward selection is greedy — it misses feature interactions.")
    log("  For any DROP head, try expanded feature sets to recover.")

    for head_name in heads_to_run:
        if head_name not in all_results:
            continue
        r = all_results[head_name]
        prod_dsr = r['production_dsr']
        fwd_dsr = r['final_dsr']

        if fwd_dsr >= prod_dsr:
            log(f"  {head_name:22s}: FWD={fwd_dsr:.3f} ≥ Prod={prod_dsr:.3f} — OK, skip")
            continue

        log(f"\n  ── {head_name.upper()}: DROP detected (FWD={fwd_dsr:.3f} < Prod={prod_dsr:.3f}) ──")

        cfg = HEAD_CONFIGS[head_name]
        # FIX 1: Apply the SAME context filter used in Phase 2+3
        labels = all_labels[head_name]
        ctx_mask = apply_context(df, head_name)
        df_ctx = df[ctx_mask].copy()
        labels_ctx = labels[ctx_mask.values]
        log(f"    Context filter: {ctx_mask.sum():,d} / {len(df):,d} rows")

        # Strategy A: FWD winners + top rejected features (discover pair interactions)
        fwd_winners = r['optimal_features']
        rejected_features = [
            e['feature'] for e in r.get('selection_log', [])
            if e['action'] == 'REJECTED' and e['delta'] > -2.0  # not terrible
        ]
        top_rejected = rejected_features[:15]  # top 15 rejected
        expanded_a = list(dict.fromkeys(fwd_winners + top_rejected))  # preserve order, dedup

        log(f"    Strategy A: FWD({len(fwd_winners)}f) + top-rejected({len(top_rejected)}f) = {len(expanded_a)}f")
        result_a = train_quick(df_ctx, labels_ctx, expanded_a, cfg['horizon'], n_splits=5, mode='dsr')
        dsr_a = result_a['dsr'] if result_a else 0.0
        log(f"    → DSR={dsr_a:.3f}")

        # Strategy B: Top viable SFI features (capped to prevent memorization)
        # FIX 2: Cap at 3x production feature count
        sfi_data = sfi_results.get(head_name, {})
        viable_all = [f for f, s in sorted(sfi_data.items(), key=lambda x: -x[1]) if s > 0.005 and f in EXPANDED_FEATURES]
        prod_n = production_features.get(head_name, 10)
        max_viable = min(len(viable_all), prod_n * 3)
        viable_capped = viable_all[:max_viable]
        log(f"    Strategy B: Top viable SFI features = {len(viable_capped)}f (capped from {len(viable_all)}, max={max_viable})")
        result_b = train_quick(df_ctx, labels_ctx, viable_capped, cfg['horizon'], n_splits=5, mode='dsr')
        dsr_b = result_b['dsr'] if result_b else 0.0
        log(f"    → DSR={dsr_b:.3f}")

        # Strategy C: Top-30 SFI features (balanced interaction space)
        top30 = viable_all[:30]
        log(f"    Strategy C: Top-30 SFI features = {len(top30)}f")
        result_c = train_quick(df_ctx, labels_ctx, top30, cfg['horizon'], n_splits=5, mode='dsr')
        dsr_c = result_c['dsr'] if result_c else 0.0
        log(f"    → DSR={dsr_c:.3f}")

        # Pick the best
        candidates = [
            ('FWD', fwd_dsr, fwd_winners),
            ('FWD+Rejected', dsr_a, expanded_a),
            ('Top-Viable', dsr_b, viable_capped),
            ('Top-30', dsr_c, top30),
        ]
        best_name, best_dsr, best_features = max(candidates, key=lambda x: x[1])

        if best_dsr > fwd_dsr:
            new_status = "★ GAIN" if best_dsr > prod_dsr else "≈ RECOVERED" if best_dsr >= prod_dsr * 0.95 else "↑ IMPROVED"
            log(f"    ★ ANTI-DROP: {best_name} wins with DSR={best_dsr:.3f} ({len(best_features)}f) [{new_status}]")
            all_results[head_name].update({
                'optimal_features': best_features,
                'final_dsr': round(best_dsr, 4),
                'delta_vs_production': round(best_dsr - prod_dsr, 4),
                'n_features': len(best_features),
                'status': new_status,
                'anti_drop_strategy': best_name,
                'anti_drop_candidates': {n: round(d, 4) for n, d, _ in candidates},
            })
            save_checkpoint(f"phase4_antidrop_{head_name}", all_results[head_name])
        else:
            log(f"    No improvement found. Keeping FWD result.")

        gc.collect()

    # ══════════════════════════════════════════════════════════
    # PHASE 5: COMPARATIVE DICTAMEN
    # ══════════════════════════════════════════════════════════
    log_section("PHASE 5: COMPARATIVE DICTAMEN")

    # Table
    log(f"\n  {'Head':>22s} │ {'Prod':>6s} │ {'SFI→FWD':>8s} │ {'Δ':>6s} │ {'Feat':>5s} │ {'Status':>8s}")
    log(f"  {'─'*65}")

    gains = 0
    for head_name in heads_to_run:
        if head_name not in all_results:
            continue
        r = all_results[head_name]
        log(f"  {head_name:>22s} │ {r['production_dsr']:>6.2f} │ {r['final_dsr']:>8.3f} │ {r['delta_vs_production']:>+6.2f} │ {r['n_features']:>5d} │ {r['status']:>8s}")
        if 'GAIN' in r['status']:
            gains += 1

    log(f"\n  Gains: {gains}/{len(all_results)}")

    # Feature universality
    log_section("FEATURE UNIVERSALITY MAP")
    all_optimal = [set(r['optimal_features']) for r in all_results.values() if r['optimal_features']]
    if all_optimal:
        all_feats = set.union(*all_optimal)
        for feat in sorted(all_feats):
            count = sum(1 for s in all_optimal if feat in s)
            is_new = " ★NEW" if feat in new_features else ""
            log(f"  {feat:35s} │ {count:>2d}/{len(all_optimal)} heads{is_new}")

    # Zigzag cross-reference
    zz_heads = {'zz_bottom_detector', 'zz_top_detector'}
    entry_heads = set(all_results.keys()) - zz_heads
    zz_features = set()
    for h in zz_heads:
        if h in all_results:
            zz_features |= set(all_results[h]['optimal_features'])

    entry_features = set()
    for h in entry_heads:
        if h in all_results:
            entry_features |= set(all_results[h]['optimal_features'])

    zz_only = zz_features - entry_features
    if zz_only:
        log(f"\n  ZIGZAG-ONLY features (potential discriminators for entry heads):")
        for f in sorted(zz_only):
            log(f"    → {f}")

    # Save final report
    total_time = time.time() - start_time
    final_report = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'total_time_min': round(total_time / 60, 1),
        'total_features_tested': len(EXPANDED_FEATURES),
        'derived_features_generated': len(new_features),
        'heads': {name: r for name, r in all_results.items()},
        'sfi_matrix': {
            head: {f: round(d, 4) for f, d in sorted(sfi.items(), key=lambda x: -x[1])[:20]}
            for head, sfi in sfi_results.items()
        },
    }
    save_checkpoint("final_report", final_report)

    log_section("★★★ OPTIMIZATION COMPLETE ★★★")
    log(f"Total time: {total_time/60:.1f} min ({total_time/3600:.1f} hrs)")
    log(f"Results: {RESULTS_DIR}")
    log(f"Next: Review dictamen → persist winners to production")

    store.close()
    ps.close()


if __name__ == "__main__":
    main()
