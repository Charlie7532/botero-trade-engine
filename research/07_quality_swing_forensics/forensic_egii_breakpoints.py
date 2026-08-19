#!/usr/bin/env python3
"""
Forensic EGII Breakpoint Analysis — Reverse Engineering of Zigzag Turns
========================================================================
For each confirmed zigzag breakpoint (bottom/top), extracts the feature
signature at multiple time offsets (t-7, t-3, t-1, t=0, t+1, t+3) and
classifies by:
  1. Slope regime (8 combinations of Tide/Current/Wave +/-)
  2. RSI quadrant at the breakpoint
  3. Structural context (Higher Low vs Lower Low)

This reveals WHAT XGBoost sees at each structural turn, per regime.

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python research/07_quality_swing_forensics/forensic_egii_breakpoints.py
"""
import sys, os, warnings
from pathlib import Path
import pandas as pd
import numpy as np
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

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
TIME_OFFSETS = [-7, -5, -3, -1, 0, 1, 3]  # bars relative to breakpoint
OFFSET_NAMES = {-7: "t-7", -5: "t-5", -3: "t-3", -1: "t-1", 0: "t=0", 1: "t+1", 3: "t+3"}

# Key features to profile at each breakpoint
KEY_FEATURES = [
    # RC Slopes (the "forces")
    'tide_slope', 'current_slope', 'wave_slope',
    # RC Accelerations
    'tide_accel', 'current_accel', 'wave_accel',
    # Sigma positions (where is price in the channel?)
    'sigma_tide', 'sigma_current', 'sigma_wave',
    # VWAP Sigmas (where is price relative to VWAPs in standard deviations)
    'vwap_sigma_tide', 'vwap_sigma_current', 'vwap_sigma_wave',
    # VWAP Spreads
    'vwap_spread_tide_current', 'vwap_spread_tide_wave', 'vwap_spread_current_wave',
    # Momentum / Oscillators
    'rsi_value', 'rsi_conviction',
    # Volatility
    'compression_ratio', 'fear_level',
    # Volume dynamics
    'vol_up_down_ratio', 'kalman_velocity',
    # TSI (Trend Strength Index)
    'tsi_tide', 'tsi_current', 'tsi_wave',
    # Key deltas (bar-over-bar changes)
    'd_tide_slope', 'd_wave_accel', 'd_rsi_value', 'd_sigma_wave',
    # Derived / forensic
    'slope_decel_wave', 'complacency_index',
    # VWAP positions
    'below_all_vwaps_int', 'above_all_vwaps_int',
]


def p(t):
    print(f"\n{'='*95}\n  {t}\n{'='*95}")


def sp(t):
    print(f"\n  ── {t} ──")


def classify_rsi(rsi):
    """Classify RSI into actionable quadrants."""
    if rsi < 25:
        return "EXTREME_OVERSOLD"
    elif rsi < 35:
        return "OVERSOLD"
    elif rsi < 45:
        return "WEAK"
    elif rsi < 55:
        return "NEUTRAL"
    elif rsi < 65:
        return "STRONG"
    elif rsi < 75:
        return "OVERBOUGHT"
    else:
        return "EXTREME_OVERBOUGHT"


def classify_slope_regime(tide, current, wave):
    """Classify the 8 slope combinations."""
    t = '+' if tide > 0 else '-'
    c = '+' if current > 0 else '-'
    w = '+' if wave > 0 else '-'
    return f"Tide({t}) Curr({c}) Wave({w})"


def classify_structural_context(zz_df, idx, tp_type):
    """Determine if this turn is Higher Low/Lower Low or Higher High/Lower High."""
    ticker = zz_df.iloc[idx]['ticker']
    price = float(zz_df.iloc[idx]['price'])

    # Find previous turn of the same type
    prev_same = None
    for j in range(idx - 1, -1, -1):
        if zz_df.iloc[j]['ticker'] == ticker and zz_df.iloc[j]['tp_type'] == tp_type:
            prev_same = float(zz_df.iloc[j]['price'])
            break

    if prev_same is None:
        return "FIRST"

    if tp_type == 'MIN':
        return "HIGHER_LOW" if price > prev_same else "LOWER_LOW"
    else:
        return "HIGHER_HIGH" if price > prev_same else "LOWER_HIGH"


def main():
    store = TimescaleDataStore()
    ps = TickerProfileStore()

    p("PHASE 0: Loading Feature Lake + Zigzag Points")
    df, _, _ = load_feature_lake(store, ps)
    print(f"  Feature Lake: {len(df):,d} observations, {len(df.columns)} columns")

    # Load zigzag points
    zz = pd.read_sql(
        text("SELECT ticker, timestamp, tp_type, price, swing_return, swing_days "
             "FROM engine.zigzag_points "
             "WHERE min_swing_pct = 0.05 "
             "ORDER BY ticker, timestamp"),
        store.engine
    )
    print(f"  Zigzag points: {len(zz):,d} turns")

    # Validate features exist
    available = [f for f in KEY_FEATURES if f in df.columns]
    missing = [f for f in KEY_FEATURES if f not in df.columns]
    if missing:
        print(f"  ⚠️ Missing features (will skip): {missing}")
    print(f"  Profiling {len(available)} features at {len(TIME_OFFSETS)} time offsets")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 1: Extract feature snapshots at each breakpoint
    # ═══════════════════════════════════════════════════════════════
    p("PHASE 1: Extracting Feature Signatures at Zigzag Breakpoints")

    # Optimization: Pre-group feature lake by ticker to avoid O(N^2) pandas filtering inside loop
    print("  Pre-grouping Feature Lake by ticker...")
    ticker_dfs = {tk: grp.reset_index(drop=True) for tk, grp in df.groupby('ticker')}

    records = []
    skipped = 0

    for zz_idx in range(len(zz)):
        row = zz.iloc[zz_idx]
        ticker = row['ticker']
        ts = row['timestamp']
        tp_type = row['tp_type']
        price = float(row['price'])

        # Get this ticker's feature lake slice
        tk_df = ticker_dfs.get(ticker)
        if tk_df is None or len(tk_df) < 20:
            skipped += 1
            continue

        # Find the closest bar to the zigzag timestamp
        time_diffs = np.abs(
            (tk_df['timestamp'].values - np.datetime64(ts)).astype('timedelta64[D]').astype(int)
        )
        anchor = time_diffs.argmin()
        if time_diffs[anchor] > 3:  # Must be within 3 days
            skipped += 1
            continue


        # Classify structural context
        struct = classify_structural_context(zz, zz_idx, tp_type)

        # Extract features at each time offset
        for offset in TIME_OFFSETS:
            bar_idx = anchor + offset
            if bar_idx < 0 or bar_idx >= len(tk_df):
                continue

            bar = tk_df.iloc[bar_idx]

            # Slope regime at THIS bar
            tide_s = float(bar.get('tide_slope', 0))
            curr_s = float(bar.get('current_slope', 0))
            wave_s = float(bar.get('wave_slope', 0))
            regime = classify_slope_regime(tide_s, curr_s, wave_s)

            # RSI quadrant
            rsi_val = float(bar.get('rsi_value', 50))
            rsi_quad = classify_rsi(rsi_val)

            rec = {
                'ticker': ticker,
                'zz_timestamp': ts,
                'tp_type': tp_type,
                'zz_price': price,
                'structural_context': struct,
                'offset': offset,
                'offset_name': OFFSET_NAMES[offset],
                'slope_regime': regime,
                'rsi_quadrant': rsi_quad,
            }

            # Add all feature values
            for feat in available:
                rec[feat] = float(bar.get(feat, 0))

            records.append(rec)

    result = pd.DataFrame(records)
    print(f"  Extracted {len(result):,d} feature snapshots ({skipped} turns skipped)")
    print(f"  Unique turns profiled: {result['zz_timestamp'].nunique():,d}")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 2: Statistical Profile — BOTTOMS by Slope Regime
    # ═══════════════════════════════════════════════════════════════
    p("PHASE 2: BOTTOM BREAKPOINTS — Feature Signatures by Slope Regime")

    bottoms = result[result['tp_type'] == 'MIN']

    for offset in TIME_OFFSETS:
        offset_data = bottoms[bottoms['offset'] == offset]
        if len(offset_data) == 0:
            continue

        sp(f"BOTTOMS at {OFFSET_NAMES[offset]} ({len(offset_data):,d} observations)")

        # Group by slope regime
        print(f"\n  {'Slope Regime':35s} │ {'N':>5s} │ {'RSI':>6s} │ {'σ_tide':>7s} │ {'σ_curr':>7s} │ {'σ_wave':>7s} │ {'wave_ac':>7s} │ {'TSI_t':>6s} │ {'fear':>6s} │ {'Compr':>6s} │ {'<VWAPs':>6s}")
        print("  " + "-" * 130)

        grouped = offset_data.groupby('slope_regime')
        for regime, grp in sorted(grouped, key=lambda x: -len(x[1])):
            n = len(grp)
            rsi = grp['rsi_value'].mean() if 'rsi_value' in grp else 0
            st = grp['sigma_tide'].mean() if 'sigma_tide' in grp else 0
            sc = grp['sigma_current'].mean() if 'sigma_current' in grp else 0
            sw = grp['sigma_wave'].mean() if 'sigma_wave' in grp else 0
            wa = grp['wave_accel'].mean() if 'wave_accel' in grp else 0
            tsi = grp['tsi_tide'].mean() if 'tsi_tide' in grp else 0
            fear = grp['fear_level'].mean() if 'fear_level' in grp else 0
            comp = grp['compression_ratio'].mean() if 'compression_ratio' in grp else 0
            bvwap = grp['below_all_vwaps_int'].mean() * 100 if 'below_all_vwaps_int' in grp else 0

            print(f"  {regime:35s} │ {n:5d} │ {rsi:6.1f} │ {st:+7.2f} │ {sc:+7.2f} │ {sw:+7.2f} │ {wa:+7.4f} │ {tsi:6.1f} │ {fear:6.2f} │ {comp:6.3f} │ {bvwap:5.1f}%")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 2b: BOTTOM BREAKPOINTS — VWAP Sigmas and Spreads
    # ═══════════════════════════════════════════════════════════════
    p("PHASE 2b: BOTTOM BREAKPOINTS — VWAP Sigmas & Spreads by Slope Regime")

    for offset in [0, -3, -7]:
        offset_data = bottoms[bottoms['offset'] == offset]
        if len(offset_data) == 0:
            continue

        sp(f"VWAP Profiles at {OFFSET_NAMES[offset]} ({len(offset_data):,d} observations)")

        # Group by slope regime
        print(f"\n  {'Slope Regime':35s} │ {'N':>5s} │ {'v_σ_tide':>8s} │ {'v_σ_curr':>8s} │ {'v_σ_wave':>8s} │ {'v_sp_tc':>8s} │ {'v_sp_tw':>8s} │ {'v_sp_cw':>8s}")
        print("  " + "-" * 115)

        grouped = offset_data.groupby('slope_regime')
        for regime, grp in sorted(grouped, key=lambda x: -len(x[1])):
            n = len(grp)
            vst = grp['vwap_sigma_tide'].mean() if 'vwap_sigma_tide' in grp else 0
            vsc = grp['vwap_sigma_current'].mean() if 'vwap_sigma_current' in grp else 0
            vsw = grp['vwap_sigma_wave'].mean() if 'vwap_sigma_wave' in grp else 0
            vsp_tc = grp['vwap_spread_tide_current'].mean() if 'vwap_spread_tide_current' in grp else 0
            vsp_tw = grp['vwap_spread_tide_wave'].mean() if 'vwap_spread_tide_wave' in grp else 0
            vsp_cw = grp['vwap_spread_current_wave'].mean() if 'vwap_spread_current_wave' in grp else 0

            print(f"  {regime:35s} │ {n:5d} │ {vst:+8.2f} │ {vsc:+8.2f} │ {vsw:+8.2f} │ {vsp_tc:+8.4f} │ {vsp_tw:+8.4f} │ {vsp_cw:+8.4f}")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 3: RSI Quadrant Distribution at Breakpoints
    # ═══════════════════════════════════════════════════════════════
    p("PHASE 3: RSI Quadrant Distribution at BOTTOM Breakpoints")

    for offset in [0, -1, -3, -7]:
        offset_data = bottoms[bottoms['offset'] == offset]
        if len(offset_data) == 0:
            continue

        sp(f"RSI Distribution at {OFFSET_NAMES[offset]}")

        # Cross-tab: RSI Quadrant × Slope Regime
        print(f"\n  {'RSI Quadrant':22s} │ {'Total':>6s} │ {'%':>6s} │ {'Tide+ Curr- Wave-':>18s} │ {'Tide- Curr- Wave-':>18s} │ {'Tide+ Curr+ Wave-':>18s}")
        print("  " + "-" * 110)

        total = len(offset_data)
        for quad in ["EXTREME_OVERSOLD", "OVERSOLD", "WEAK", "NEUTRAL", "STRONG", "OVERBOUGHT", "EXTREME_OVERBOUGHT"]:
            q_data = offset_data[offset_data['rsi_quadrant'] == quad]
            n = len(q_data)
            pct = n / total * 100 if total > 0 else 0

            # Count in key regimes
            sweet = len(q_data[q_data['slope_regime'] == 'Tide(+) Curr(-) Wave(-)'])
            knife = len(q_data[q_data['slope_regime'] == 'Tide(-) Curr(-) Wave(-)'])
            pull = len(q_data[q_data['slope_regime'] == 'Tide(+) Curr(+) Wave(-)'])

            print(f"  {quad:22s} │ {n:6d} │ {pct:5.1f}% │ {sweet:18d} │ {knife:18d} │ {pull:18d}")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 4: Structural Context (HL vs LL) × Slope Regime
    # ═══════════════════════════════════════════════════════════════
    p("PHASE 4: Structural Context at BOTTOM t=0 — Higher Low vs Lower Low")

    t0_bottoms = bottoms[bottoms['offset'] == 0]

    print(f"\n  {'Slope Regime':35s} │ {'Total':>5s} │ {'HL':>5s} │ {'LL':>5s} │ {'HL%':>6s} │ {'RSI_HL':>7s} │ {'RSI_LL':>7s} │ {'σw_HL':>7s} │ {'σw_LL':>7s}")
    print("  " + "-" * 120)

    for regime, grp in sorted(t0_bottoms.groupby('slope_regime'), key=lambda x: -len(x[1])):
        hl = grp[grp['structural_context'] == 'HIGHER_LOW']
        ll = grp[grp['structural_context'] == 'LOWER_LOW']
        n = len(grp)
        n_hl = len(hl)
        n_ll = len(ll)
        hl_pct = n_hl / n * 100 if n > 0 else 0

        rsi_hl = hl['rsi_value'].mean() if len(hl) > 0 and 'rsi_value' in hl else 0
        rsi_ll = ll['rsi_value'].mean() if len(ll) > 0 and 'rsi_value' in ll else 0
        sw_hl = hl['sigma_wave'].mean() if len(hl) > 0 and 'sigma_wave' in hl else 0
        sw_ll = ll['sigma_wave'].mean() if len(ll) > 0 and 'sigma_wave' in ll else 0

        print(f"  {regime:35s} │ {n:5d} │ {n_hl:5d} │ {n_ll:5d} │ {hl_pct:5.1f}% │ {rsi_hl:7.1f} │ {rsi_ll:7.1f} │ {sw_hl:+7.2f} │ {sw_ll:+7.2f}")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 5: TOP BREAKPOINTS — Feature Signatures by Slope Regime
    # ═══════════════════════════════════════════════════════════════
    p("PHASE 5: TOP BREAKPOINTS — Feature Signatures by Slope Regime")

    tops = result[result['tp_type'] == 'MAX']

    for offset in [0, -1, -3, -7]:
        offset_data = tops[tops['offset'] == offset]
        if len(offset_data) == 0:
            continue

        sp(f"TOPS at {OFFSET_NAMES[offset]} ({len(offset_data):,d} observations)")

        print(f"\n  {'Slope Regime':35s} │ {'N':>5s} │ {'RSI':>6s} │ {'σ_tide':>7s} │ {'σ_curr':>7s} │ {'σ_wave':>7s} │ {'wave_ac':>7s} │ {'TSI_t':>6s} │ {'fear':>6s} │ {'Compr':>6s} │ {'>VWAPs':>6s}")
        print("  " + "-" * 130)

        grouped = offset_data.groupby('slope_regime')
        for regime, grp in sorted(grouped, key=lambda x: -len(x[1])):
            n = len(grp)
            rsi = grp['rsi_value'].mean() if 'rsi_value' in grp else 0
            st = grp['sigma_tide'].mean() if 'sigma_tide' in grp else 0
            sc = grp['sigma_current'].mean() if 'sigma_current' in grp else 0
            sw = grp['sigma_wave'].mean() if 'sigma_wave' in grp else 0
            wa = grp['wave_accel'].mean() if 'wave_accel' in grp else 0
            tsi = grp['tsi_tide'].mean() if 'tsi_tide' in grp else 0
            fear = grp['fear_level'].mean() if 'fear_level' in grp else 0
            comp = grp['compression_ratio'].mean() if 'compression_ratio' in grp else 0
            avwap = grp['above_all_vwaps_int'].mean() * 100 if 'above_all_vwaps_int' in grp else 0

            print(f"  {regime:35s} │ {n:5d} │ {rsi:6.1f} │ {st:+7.2f} │ {sc:+7.2f} │ {sw:+7.2f} │ {wa:+7.4f} │ {tsi:6.1f} │ {fear:6.2f} │ {comp:6.3f} │ {avwap:5.1f}%")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 6: Temporal Evolution — How Features MOVE from t-7 to t=0
    # ═══════════════════════════════════════════════════════════════
    p("PHASE 6: Temporal Evolution of Key Features (t-7 → t=0) — BOTTOMS")

    # For the sweet spot regime, show how features evolve
    sweet_spot = bottoms[bottoms['slope_regime'] == 'Tide(+) Curr(-) Wave(-)']
    knife = bottoms[bottoms['slope_regime'] == 'Tide(-) Curr(-) Wave(-)']

    evolution_features = ['rsi_value', 'wave_accel', 'sigma_wave', 'sigma_current',
                          'vwap_sigma_wave', 'vwap_sigma_current', 'vwap_spread_current_wave',
                          'd_sigma_wave',
                          'fear_level', 'compression_ratio', 'below_all_vwaps_int',
                          'tsi_wave', 'slope_decel_wave', 'complacency_index']

    for label, subset in [("★ SWEET SPOT Tide(+) Curr(-) Wave(-)", sweet_spot),
                          ("⚠️ KNIFE Tide(-) Curr(-) Wave(-)", knife)]:
        sp(f"Temporal Evolution: {label} ({subset['zz_timestamp'].nunique()} turns)")

        print(f"\n  {'Feature':25s} │ {'t-7':>8s} │ {'t-5':>8s} │ {'t-3':>8s} │ {'t-1':>8s} │ {'t=0':>8s} │ {'t+1':>8s} │ {'t+3':>8s} │ {'Δ(t-7→0)':>10s}")
        print("  " + "-" * 120)

        for feat in evolution_features:
            if feat not in subset.columns:
                continue
            vals = []
            for off in TIME_OFFSETS:
                off_data = subset[subset['offset'] == off]
                if len(off_data) > 0 and feat in off_data.columns:
                    vals.append(off_data[feat].mean())
                else:
                    vals.append(np.nan)

            delta = vals[-3] - vals[0] if not np.isnan(vals[0]) and not np.isnan(vals[-3]) else np.nan  # t=0 is index 4
            # t=0 is at index 4 (offsets: -7,-5,-3,-1,0,1,3)
            delta_str = f"{delta:+10.4f}" if not np.isnan(delta) else "    N/A   "

            line = f"  {feat:25s} │"
            for v in vals:
                if np.isnan(v):
                    line += f" {'N/A':>8s} │"
                else:
                    line += f" {v:>8.3f} │"
            line += f" {delta_str}"
            print(line)

    # ═══════════════════════════════════════════════════════════════
    # PHASE 7: RSI × Trend Coherence Principle (Architect's Quadrant Rule)
    # ═══════════════════════════════════════════════════════════════
    p("PHASE 7: RSI × Trend Coherence — The Architect's Quadrant Rule")

    t0_all = result[result['offset'] == 0]

    sp("BOTTOMS (t=0): RSI in Oversold + Tide Alcista = ¿Señal de Compra?")

    # Bottoms where RSI < 35 AND Tide > 0 (the "pullback buy" quadrant)
    t0_bot = t0_all[t0_all['tp_type'] == 'MIN']
    pullback_buy = t0_bot[(t0_bot['rsi_value'] < 35) & (t0_bot['tide_slope'] > 0)]
    knife_catch = t0_bot[(t0_bot['rsi_value'] < 35) & (t0_bot['tide_slope'] < 0)]
    total_oversold = t0_bot[t0_bot['rsi_value'] < 35]

    print(f"\n  BOTTOMS con RSI < 35 en t=0:")
    print(f"    Total:                     {len(total_oversold):5d}")
    print(f"    Con Tide ALCISTA (compra):  {len(pullback_buy):5d} ({len(pullback_buy)/max(len(total_oversold),1)*100:.1f}%)")
    print(f"    Con Tide BAJISTA (cuchillo):{len(knife_catch):5d} ({len(knife_catch)/max(len(total_oversold),1)*100:.1f}%)")

    if len(pullback_buy) > 0 and 'sigma_wave' in pullback_buy.columns:
        print(f"\n    ── Perfil del Pullback Buy (Tide+, RSI<35) ──")
        print(f"    RSI medio:        {pullback_buy['rsi_value'].mean():.1f}")
        print(f"    σ_wave medio:     {pullback_buy['sigma_wave'].mean():+.2f}")
        print(f"    σ_current medio:  {pullback_buy['sigma_current'].mean():+.2f}")
        print(f"    wave_accel medio: {pullback_buy['wave_accel'].mean():+.4f}")
        print(f"    fear_level medio: {pullback_buy['fear_level'].mean():.3f}")
        print(f"    TSI_tide medio:   {pullback_buy['tsi_tide'].mean():.1f}")

    if len(knife_catch) > 0 and 'sigma_wave' in knife_catch.columns:
        print(f"\n    ── Perfil del Knife Catch (Tide-, RSI<35) ──")
        print(f"    RSI medio:        {knife_catch['rsi_value'].mean():.1f}")
        print(f"    σ_wave medio:     {knife_catch['sigma_wave'].mean():+.2f}")
        print(f"    σ_current medio:  {knife_catch['sigma_current'].mean():+.2f}")
        print(f"    wave_accel medio: {knife_catch['wave_accel'].mean():+.4f}")
        print(f"    fear_level medio: {knife_catch['fear_level'].mean():.3f}")
        print(f"    TSI_tide medio:   {knife_catch['tsi_tide'].mean():.1f}")

    sp("TOPS (t=0): RSI in Overbought + Tide Bajista = ¿Señal de Corto?")

    t0_top = t0_all[t0_all['tp_type'] == 'MAX']
    dist_sell = t0_top[(t0_top['rsi_value'] > 65) & (t0_top['tide_slope'] < 0)]
    trend_ext = t0_top[(t0_top['rsi_value'] > 65) & (t0_top['tide_slope'] > 0)]
    total_overbought = t0_top[t0_top['rsi_value'] > 65]

    print(f"\n  TOPS con RSI > 65 en t=0:")
    print(f"    Total:                     {len(total_overbought):5d}")
    print(f"    Con Tide BAJISTA (corto):   {len(dist_sell):5d} ({len(dist_sell)/max(len(total_overbought),1)*100:.1f}%)")
    print(f"    Con Tide ALCISTA (extensión):{len(trend_ext):5d} ({len(trend_ext)/max(len(total_overbought),1)*100:.1f}%)")

    if len(dist_sell) > 0 and 'sigma_wave' in dist_sell.columns:
        print(f"\n    ── Perfil del Distribution Sell (Tide-, RSI>65) ──")
        print(f"    RSI medio:        {dist_sell['rsi_value'].mean():.1f}")
        print(f"    σ_wave medio:     {dist_sell['sigma_wave'].mean():+.2f}")
        print(f"    σ_current medio:  {dist_sell['sigma_current'].mean():+.2f}")
        print(f"    wave_accel medio: {dist_sell['wave_accel'].mean():+.4f}")
        print(f"    TSI_tide medio:   {dist_sell['tsi_tide'].mean():.1f}")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 8: Feature Discriminative Power — HL vs LL at t=0
    # ═══════════════════════════════════════════════════════════════
    p("PHASE 8: Feature Discriminative Power — Higher Low vs Lower Low at t=0")

    sp("Which features BEST separate HL from LL at the exact breakpoint?")

    hl_data = t0_bot[t0_bot['structural_context'] == 'HIGHER_LOW']
    ll_data = t0_bot[t0_bot['structural_context'] == 'LOWER_LOW']

    if len(hl_data) > 10 and len(ll_data) > 10:
        print(f"\n  Higher Low: {len(hl_data):,d} turns  |  Lower Low: {len(ll_data):,d} turns\n")
        print(f"  {'Feature':25s} │ {'HL Mean':>10s} │ {'LL Mean':>10s} │ {'Δ(HL-LL)':>10s} │ {'t-stat':>8s} │ {'Signal':>8s}")
        print("  " + "-" * 90)

        from scipy import stats as sp_stats

        discriminators = []
        for feat in available:
            hl_vals = hl_data[feat].dropna()
            ll_vals = ll_data[feat].dropna()
            if len(hl_vals) < 10 or len(ll_vals) < 10:
                continue

            hl_mean = hl_vals.mean()
            ll_mean = ll_vals.mean()
            delta = hl_mean - ll_mean

            # Welch's t-test
            t_stat, p_val = sp_stats.ttest_ind(hl_vals, ll_vals, equal_var=False)

            discriminators.append({
                'feature': feat,
                'hl_mean': hl_mean,
                'll_mean': ll_mean,
                'delta': delta,
                't_stat': t_stat,
                'p_val': p_val,
                'abs_t': abs(t_stat),
            })

        # Sort by absolute t-stat (most discriminative first)
        discriminators.sort(key=lambda x: -x['abs_t'])

        for d in discriminators[:25]:  # Top 25
            sig = "★★★" if d['p_val'] < 0.001 else ("★★" if d['p_val'] < 0.01 else ("★" if d['p_val'] < 0.05 else "  "))
            print(f"  {d['feature']:25s} │ {d['hl_mean']:>10.4f} │ {d['ll_mean']:>10.4f} │ {d['delta']:>+10.4f} │ {d['t_stat']:>+8.2f} │ {sig:>8s}")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 9: Summary Statistics
    # ═══════════════════════════════════════════════════════════════
    p("PHASE 9: Summary — Breakpoint Census")

    print(f"\n  Total zigzag turns profiled: {result['zz_timestamp'].nunique():,d}")
    print(f"  Total feature snapshots:     {len(result):,d}")
    print(f"  Tickers covered:             {result['ticker'].nunique()}")

    print(f"\n  Turns by type:")
    for tp, grp in result[result['offset'] == 0].groupby('tp_type'):
        n = len(grp)
        print(f"    {tp}: {n:,d}")

    print(f"\n  Structural context distribution (bottoms, t=0):")
    for ctx, grp in t0_bot.groupby('structural_context'):
        n = len(grp)
        pct = n / len(t0_bot) * 100
        print(f"    {ctx}: {n:,d} ({pct:.1f}%)")

    store.close()
    ps.close()

    p("FORENSIC ANALYSIS COMPLETE")
    print("  Results above provide the empirical foundation for EGII training.")
    print("  Next: Use these signatures to calibrate the Sentinel Gate thresholds.")


if __name__ == "__main__":
    main()
