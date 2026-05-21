#!/usr/bin/env python3
"""
Forensic Lab v11 — DEEP AUDIT & BLIND SPOT DETECTOR
=====================================================
Cross-validates ALL prior forensic results (v1-v10) against raw data.
Finds discrepancies, methodology errors, and blind spots.

AUDIT LAYERS:
  1. DATA INTEGRITY: Are labels correct? Snapshot vs recomputed values.
  2. CLASSIFICATION AUDIT: Do forward returns match classifications?
  3. RULE CONSISTENCY: Same rule → same result when recomputed from scratch?
  4. METHODOLOGY AUDIT: v6/v7 per-signal vs v10 combined — which is correct?
  5. BLIND SPOTS: Features/combos never tested across all versions.
  6. SIGNAL OVERLAP: When RSI and RC fire same day, does snapshot differ?
"""

import os, sys, json, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import pandas as pd
import numpy as np
import psycopg2, psycopg2.extras
from scipy import stats

def p(t): print(f"\n{'='*90}\n  {t}\n{'='*90}")
def sp(t): print(f"\n  ── {t} ──")


# ═══════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════

def load_all_labels() -> pd.DataFrame:
    pg_url = os.environ.get("POSTGRES_URL", "")
    conn = psycopg2.connect(pg_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM engine.entry_forensic_labels WHERE signal_direction = 1")
    rows = cur.fetchall()
    conn.close()
    records = []
    for row in rows:
        flat = {
            "ticker": row["ticker"], "signal_name": row["signal_name"],
            "signal_direction": row["signal_direction"],
            "signal_time": row["signal_time"], "classification": row["classification"],
            "signal_price": row.get("signal_price"),
        }
        snap = row["snapshot"]
        if isinstance(snap, str): snap = json.loads(snap)
        if snap:
            for k, v in snap.items(): flat[f"snap_{k}"] = v
        horizons = row["horizons"]
        if isinstance(horizons, str): horizons = json.loads(horizons)
        if horizons:
            for h_key, h_val in horizons.items():
                if isinstance(h_val, dict):
                    for m, mv in h_val.items(): flat[f"h{h_key}_{m}"] = mv
        records.append(flat)
    df = pd.DataFrame(records)
    df["signal_time"] = pd.to_datetime(df["signal_time"])
    df["year"] = df["signal_time"].dt.year
    df["is_win"] = df["classification"].isin(["GOLDEN_RUN", "SOLID_MOVE"]).astype(int)
    for c in [col for col in df.columns if col.startswith("snap_") or col.startswith("h")]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_ohlcv(ticker: str) -> pd.DataFrame:
    pg_url = os.environ.get("POSTGRES_URL", "")
    conn = psycopg2.connect(pg_url)
    df = pd.read_sql(
        "SELECT time, open, high, low, close, volume FROM market.ohlcv_bars "
        "WHERE ticker = %s ORDER BY time", conn, params=(ticker,))
    conn.close()
    df["time"] = pd.to_datetime(df["time"])
    return df


def wilson_ci(successes, n, z=1.96):
    if n == 0: return 0.0, 0.0, 0.0
    phat = successes / n
    denom = 1 + z**2 / n
    center = phat + z**2 / (2*n)
    spread = z * np.sqrt((phat*(1-phat) + z**2/(4*n)) / n)
    lo = max(0, (center - spread) / denom)
    hi = min(1, (center + spread) / denom)
    return lo, hi, phat


# ═══════════════════════════════════════════════════════════
# AUDIT 1: CLASSIFICATION INTEGRITY
# Are forward returns consistent with classifications?
# ═══════════════════════════════════════════════════════════

def audit_classification(df: pd.DataFrame):
    p("AUDIT 1: CLASSIFICATION INTEGRITY")
    
    # OracleTrainer _classify_entry uses MULTI-CONDITION logic:
    # GOLDEN_RUN:   h10_return >= 3.0 AND h10_max_down > -1.0
    # SOLID_MOVE:   h10_return >= 1.0
    # SLOW_GRIND:   h10_return >= 0.5 (and < 1.0)
    # MISS:         h10_return >= 0.0 and < 0.5
    # TRAP:         h10_max_up >= 1.0 AND h10_return < 0
    # FALSE_SIGNAL: h10_return < 0 AND h10_max_up < 1.0
    
    print("\n  Checking classification vs Oracle _classify_entry rules...")
    
    mismatches = 0
    total_checked = 0
    mismatch_details = []
    
    for _, row in df.iterrows():
        ret = row["h10_return_pct"]
        max_down = row.get("h10_max_down_pct", np.nan)
        max_up = row.get("h10_max_up_pct", np.nan)
        cls = row["classification"]
        
        if pd.isna(ret): continue
        if pd.isna(max_down): max_down = 0.0
        if pd.isna(max_up): max_up = 0.0
        total_checked += 1
        
        # Recompute expected classification using Oracle's exact logic
        if ret >= 3.0 and max_down > -1.0:
            expected = "GOLDEN_RUN"
        elif ret >= 1.0:
            expected = "SOLID_MOVE"
        elif ret >= 0.0:
            expected = "SLOW_GRIND" if ret >= 0.5 else "MISS"
        elif max_up >= 1.0 and ret < 0:
            expected = "TRAP"
        else:
            expected = "FALSE_SIGNAL"
        
        if cls != expected:
            mismatches += 1
    
    print(f"\n  Total labels: {total_checked}")
    print(f"  Mismatches:   {mismatches} ({mismatches/max(total_checked,1)*100:.2f}%)")
    
    if mismatches == 0:
        print("  ✅ All classifications match Oracle _classify_entry logic perfectly.")
    else:
        print(f"  🚨 {mismatches} labels don't match Oracle classification logic!")
        print("  Sampling mismatches...")
        sample_count = 0
        for _, row in df.iterrows():
            ret = row["h10_return_pct"]
            max_down = row.get("h10_max_down_pct", 0.0)
            max_up = row.get("h10_max_up_pct", 0.0)
            cls = row["classification"]
            if pd.isna(ret) or pd.isna(max_down) or pd.isna(max_up): continue
            if ret >= 3.0 and max_down > -1.0: exp = "GOLDEN_RUN"
            elif ret >= 1.0: exp = "SOLID_MOVE"
            elif ret >= 0.0: exp = "SLOW_GRIND" if ret >= 0.5 else "MISS"
            elif max_up >= 1.0 and ret < 0: exp = "TRAP"
            else: exp = "FALSE_SIGNAL"
            if cls != exp:
                print(f"    {row['ticker']:<6s} {str(row['signal_time'])[:10]} ret={ret:>6.2f}% up={max_up:>5.1f}% down={max_down:>6.1f}% DB={cls:<15s} Expected={exp}")
                sample_count += 1
                if sample_count >= 20: break
    
    # Check for NaN returns
    nan_returns = df["h10_return_pct"].isna().sum()
    if nan_returns > 0:
        print(f"\n  ⚠ {nan_returns} labels have NaN h10_return_pct!")


# ═══════════════════════════════════════════════════════════
# AUDIT 2: SNAPSHOT RECOMPUTATION
# Recompute σ_wave and fear_level from raw OHLCV for sample labels
# ═══════════════════════════════════════════════════════════

def audit_snapshot_recompute(df: pd.DataFrame):
    p("AUDIT 2: SNAPSHOT RECOMPUTATION — σ_wave from raw OHLCV")
    
    from backend.modules.price_analysis.application.use_cases.analyze_regression_channel import RegressionChannelIntelligence
    
    rc_intel = RegressionChannelIntelligence()
    
    tickers_to_check = ["AAPL", "COST", "SPY", "JPM", "MRK"]
    
    print(f"\n  Recomputing σ_wave for 5 random labels per ticker...")
    print(f"  {'Ticker':<8s} {'Signal':<12s} {'Date':>12s} │ {'DB σ_wave':>9s} {'Recomp':>9s} {'Δ':>7s} {'Match':>6s}")
    print(f"  {'─'*75}")
    
    total_errors = 0
    total_checked = 0
    deltas = []
    
    for ticker in tickers_to_check:
        ohlcv = load_ohlcv(ticker)
        if ohlcv.empty: continue
        
        # Prepare OHLCV in the format RegressionChannelIntelligence expects
        ohlc = ohlcv.copy()
        ohlc.index = ohlc["time"]
        
        sub = df[df["ticker"] == ticker].sample(n=min(5, len(df[df["ticker"]==ticker])), random_state=42)
        
        # Ensure ohlcv times are tz-naive
        if ohlcv["time"].dt.tz is not None:
            ohlcv["time"] = ohlcv["time"].dt.tz_localize(None)
        
        for _, row in sub.iterrows():
            st = row["signal_time"]
            if hasattr(st, 'tz') and st.tz is not None:
                st = st.tz_localize(None)
            st = pd.Timestamp(st).tz_localize(None) if pd.Timestamp(st).tz else pd.Timestamp(st)
            
            # Find matching bar index
            diffs = np.abs(ohlcv["time"] - st)
            bar_idx = int(diffs.argmin())
            
            if bar_idx < 200: continue
            
            try:
                rc_res = rc_intel.analyze(ohlc, idx=bar_idx)
                recomp_sigma = rc_res.sigma_wave
                db_sigma = row["snap_sigma_wave"]
                
                delta = abs(recomp_sigma - db_sigma) if not (np.isnan(recomp_sigma) or np.isnan(db_sigma)) else float('nan')
                deltas.append(delta)
                total_checked += 1
                
                match = "✅" if delta < 0.01 else "⚠" if delta < 0.1 else "🚨"
                if delta >= 0.01: total_errors += 1
                
                sig_short = row["signal_name"][:10]
                date_str = st.strftime("%Y-%m-%d") if hasattr(st, 'strftime') else str(st)[:10]
                print(f"  {ticker:<8s} {sig_short:<12s} {date_str:>12s} │ {db_sigma:>9.4f} {recomp_sigma:>9.4f} {delta:>7.4f} {match:>6s}")
            except Exception as e:
                print(f"  {ticker:<8s} ERROR: {e}")
    
    valid_deltas = [d for d in deltas if not np.isnan(d)]
    if valid_deltas:
        print(f"\n  Checked: {total_checked}, Errors (Δ≥0.01): {total_errors}")
        print(f"  Mean Δ: {np.mean(valid_deltas):.6f}, Max Δ: {np.max(valid_deltas):.6f}")
        if total_errors == 0:
            print(f"  ✅ All snapshots match recomputation within tolerance.")
        else:
            print(f"  🚨 {total_errors} snapshots diverge from recomputation!")


# ═══════════════════════════════════════════════════════════
# AUDIT 3: SIGNAL OVERLAP — Same day, different snapshots?
# ═══════════════════════════════════════════════════════════

def audit_signal_overlap(df: pd.DataFrame):
    p("AUDIT 3: SIGNAL OVERLAP — RSI vs RC on same day")
    
    print("\n  When RSI and RC fire on the same day, do snapshots agree?")
    print(f"  {'Ticker':<8s} {'Overlap':>7s} {'RSI-only':>8s} {'RC-only':>8s} │ {'σ_wave Δ':>9s} {'fear Δ':>7s} {'tide Δ':>7s}")
    print(f"  {'─'*70}")
    
    for ticker in sorted(df["ticker"].unique()):
        rsi_sub = df[(df["ticker"]==ticker) & (df["signal_name"]=="rsi_intelligence")]
        rc_sub = df[(df["ticker"]==ticker) & (df["signal_name"]=="regression_channel")]
        
        rsi_dates = set(rsi_sub["signal_time"].dt.date)
        rc_dates = set(rc_sub["signal_time"].dt.date)
        overlap = rsi_dates & rc_dates
        only_rsi = rsi_dates - rc_dates
        only_rc = rc_dates - rsi_dates
        
        if len(overlap) < 3: 
            print(f"  {ticker:<8s} {len(overlap):>7d} {len(only_rsi):>8d} {len(only_rc):>8d} │ N/A (too few)")
            continue
        
        # For overlapping dates, compare snapshots
        sigma_deltas = []
        fear_deltas = []
        tide_deltas = []
        
        for dt in overlap:
            rsi_row = rsi_sub[rsi_sub["signal_time"].dt.date == dt].iloc[0]
            rc_row = rc_sub[rc_sub["signal_time"].dt.date == dt].iloc[0]
            
            s_d = abs(rsi_row["snap_sigma_wave"] - rc_row["snap_sigma_wave"]) if not (pd.isna(rsi_row["snap_sigma_wave"]) or pd.isna(rc_row["snap_sigma_wave"])) else np.nan
            f_d = abs(rsi_row["snap_fear_level"] - rc_row["snap_fear_level"]) if not (pd.isna(rsi_row["snap_fear_level"]) or pd.isna(rc_row["snap_fear_level"])) else np.nan
            t_d = abs(rsi_row["snap_tide_slope"] - rc_row["snap_tide_slope"]) if not (pd.isna(rsi_row["snap_tide_slope"]) or pd.isna(rc_row["snap_tide_slope"])) else np.nan
            
            sigma_deltas.append(s_d)
            fear_deltas.append(f_d)
            tide_deltas.append(t_d)
        
        s_mean = np.nanmean(sigma_deltas)
        f_mean = np.nanmean(fear_deltas)
        t_mean = np.nanmean(tide_deltas)
        
        s_flag = "🚨" if s_mean > 0.1 else "⚠" if s_mean > 0.01 else "✅"
        
        print(f"  {ticker:<8s} {len(overlap):>7d} {len(only_rsi):>8d} {len(only_rc):>8d} │ {s_mean:>8.4f}{s_flag} {f_mean:>6.2f}  {t_mean:>6.4f}")
    
    print("\n  NOTE: σ_wave SHOULD differ between RSI and RC signals on the same day")
    print("  because RegressionChannelIntelligence.analyze() uses idx parameter,")
    print("  and the signal fires at a different internal index depending on whether")
    print("  the signal was RSI-triggered or RC-triggered. If they match perfectly,")
    print("  that would actually be suspicious — it would mean idx is the same.")


# ═══════════════════════════════════════════════════════════
# AUDIT 4: FORWARD RETURN VERIFICATION
# Recompute h10 returns from raw OHLCV
# ═══════════════════════════════════════════════════════════

def audit_forward_returns(df: pd.DataFrame):
    p("AUDIT 4: FORWARD RETURN VERIFICATION")
    
    print("\n  Recomputing h10 return from raw OHLCV for sample labels...")
    print(f"  {'Ticker':<8s} {'Date':>12s} {'DB h10':>8s} {'Recomp':>8s} {'Δ':>7s} {'Match':>6s}")
    print(f"  {'─'*55}")
    
    errors = 0
    checked = 0
    
    for ticker in ["AAPL", "COST", "SPY", "JPM", "WMT"]:
        ohlcv = load_ohlcv(ticker)
        if ohlcv.empty: continue
        close = ohlcv["close"].values.astype(float)
        times = ohlcv["time"].values
        
        # Ensure times are tz-naive
        times_naive = pd.DatetimeIndex(times)
        if times_naive.tz is not None:
            times_naive = times_naive.tz_localize(None)
        
        sub = df[df["ticker"]==ticker].sample(n=min(5, len(df[df["ticker"]==ticker])), random_state=42)
        
        for _, row in sub.iterrows():
            st = row["signal_time"]
            if hasattr(st, 'tz') and st.tz is not None:
                st = st.tz_localize(None)
            st = pd.Timestamp(st).tz_localize(None) if pd.Timestamp(st).tz else pd.Timestamp(st)
            
            diffs = np.abs(times_naive - st)
            bar_idx = int(diffs.argmin())
            
            if bar_idx + 10 >= len(close): continue
            
            recomp_ret = (close[bar_idx + 10] - close[bar_idx]) / close[bar_idx] * 100
            db_ret = row["h10_return_pct"]
            
            if np.isnan(db_ret): continue
            
            delta = abs(recomp_ret - db_ret)
            checked += 1
            match = "✅" if delta < 0.05 else "⚠" if delta < 0.5 else "🚨"
            if delta >= 0.05: errors += 1
            
            date_str = st.strftime("%Y-%m-%d") if hasattr(st, 'strftime') else str(st)[:10]
            print(f"  {ticker:<8s} {date_str:>12s} {db_ret:>7.3f}% {recomp_ret:>7.3f}% {delta:>6.3f}% {match:>6s}")
    
    print(f"\n  Checked: {checked}, Errors: {errors}")


# ═══════════════════════════════════════════════════════════
# AUDIT 5: CROSS-VERSION CONSISTENCY
# Compare v10 per-signal results with known v6/v7 patterns
# ═══════════════════════════════════════════════════════════

def audit_cross_version(df: pd.DataFrame):
    p("AUDIT 5: CROSS-VERSION CONSISTENCY")
    
    print("\n  Reproducing v6/v7 findings on current data...")
    print("  (v6/v7 ran with 4 tickers only — checking those same 4)")
    
    # v6 finding: Per-stock σ calibration
    sp("v6 CALIBRATION: Optimal σ bins (per signal)")
    sigma_bins = [
        (-999, -2.0, "σ<-2"),
        (-2.0, -1.5, "σ -2→-1.5"),
        (-1.5, -1.0, "σ -1.5→-1"),
        (-1.0, -0.5, "σ -1→-0.5"),
        (-0.5, 0.0, "σ -0.5→0"),
        (0.0, 0.5, "σ 0→+0.5"),
        (0.5, 1.0, "σ +0.5→+1"),
        (1.0, 999, "σ>+1"),
    ]
    
    for ticker in ["AAPL", "COST", "SPY", "QQQ"]:
        for signal in ["rsi_intelligence", "regression_channel"]:
            sub = df[(df["ticker"]==ticker) & (df["signal_name"]==signal)]
            if len(sub) < 20: continue
            
            sw = sub["snap_sigma_wave"]
            y = sub["is_win"]
            base = y.mean()
            
            print(f"\n    {ticker} × {signal} (N={len(sub)}, base={base*100:.1f}%):")
            for lo, hi, label in sigma_bins:
                mask = (sw >= lo) & (sw < hi)
                n = mask.sum()
                if n < 3: continue
                wr = y[mask].mean() * 100
                edge = wr - base*100
                marker = "★" if edge > 5 else "✗" if edge < -5 else " "
                print(f"      {label:<15s} N={n:>4d} WR={wr:>5.1f}% edge={edge:>+5.1f}% {marker}")
    
    # v7 finding: Volume dryness + fear
    sp("v7 VOLUME: Dryness effect (recomputed for all 17 tickers)")
    
    for ticker in sorted(df["ticker"].unique()):
        ohlcv = load_ohlcv(ticker)
        if ohlcv.empty: continue
        volume = ohlcv["volume"].values.astype(float)
        times = ohlcv["time"].values
        times_idx = pd.DatetimeIndex(times)
        if times_idx.tz is not None:
            times_idx = times_idx.tz_localize(None)
        n_bars = len(volume)
        
        vol_sma20 = np.full(n_bars, np.nan)
        vol_dryness = np.full(n_bars, np.nan)
        for i in range(50, n_bars):
            sma = np.mean(volume[i-20:i])
            vol_sma20[i] = sma
            dry = 0
            for j in range(i, max(i-20, 49), -1):
                if volume[j] < sma * 0.8:
                    dry += 1
                else:
                    break
            vol_dryness[i] = dry
        
        for signal in ["rsi_intelligence", "regression_channel"]:
            sub = df[(df["ticker"]==ticker) & (df["signal_name"]==signal)]
            if len(sub) < 15: continue
            
            enriched_wins = []
            enriched_dry = []
            enriched_sigma = []
            
            for _, row in sub.iterrows():
                st = row["signal_time"]
                if hasattr(st, 'tz') and st.tz is not None:
                    st = st.tz_localize(None)
                st = pd.Timestamp(st).tz_localize(None) if pd.Timestamp(st).tz else pd.Timestamp(st)
                diffs = np.abs(times_idx - st)
                bar_idx = int(diffs.argmin())
                if bar_idx < 55: continue
                
                enriched_wins.append(row["is_win"])
                enriched_dry.append(vol_dryness[bar_idx])
                enriched_sigma.append(row["snap_sigma_wave"])
            
            if len(enriched_wins) < 15: continue
            
            ewins = np.array(enriched_wins)
            edry = np.array(enriched_dry)
            esigma = np.array(enriched_sigma)
            base_wr = ewins.mean()
            
            # Dryness ≥ 2 + σ < -1
            mask_d2s1 = (edry >= 2) & (esigma < -1)
            n_d2s1 = mask_d2s1.sum()
            if n_d2s1 >= 3:
                wr_d2s1 = ewins[mask_d2s1].mean()
                edge = (wr_d2s1 - base_wr) * 100
                lo, hi, _ = wilson_ci(ewins[mask_d2s1].sum(), n_d2s1)
                marker = "★" if edge > 5 else "✗" if edge < -5 else " "
                # Only print if notable
                if abs(edge) > 3:
                    print(f"    {ticker:<8s} {signal[:3]:<4s} Dry≥2+σ<-1: N={n_d2s1:>3d} WR={wr_d2s1*100:>5.1f}% [{lo*100:.0f}-{hi*100:.0f}%] base={base_wr*100:.1f}% edge={edge:>+5.1f}% {marker}")


# ═══════════════════════════════════════════════════════════
# AUDIT 6: BLIND SPOT DETECTION
# What combinations were NEVER tested across v1-v10?
# ═══════════════════════════════════════════════════════════

def audit_blind_spots(df: pd.DataFrame):
    p("AUDIT 6: BLIND SPOT DETECTION")
    
    sp("6A: Classification distribution per ticker×signal (is data balanced?)")
    print(f"  {'Ticker':<8s} {'Signal':<12s} {'GR':>5s} {'SM':>5s} {'SG':>5s} {'MI':>5s} {'TR':>5s} {'FS':>5s} │ {'Balance':>8s}")
    print(f"  {'─'*70}")
    
    for ticker in sorted(df["ticker"].unique()):
        for signal in sorted(df[df["ticker"]==ticker]["signal_name"].unique()):
            sub = df[(df["ticker"]==ticker) & (df["signal_name"]==signal)]
            if len(sub) < 10: continue
            dist = sub["classification"].value_counts()
            gr = dist.get("GOLDEN_RUN", 0)
            sm = dist.get("SOLID_MOVE", 0)
            sg = dist.get("SLOW_GRIND", 0)
            mi = dist.get("MISS", 0)
            tr = dist.get("TRAP", 0)
            fs = dist.get("FALSE_SIGNAL", 0)
            
            n = len(sub)
            wr = (gr + sm) / n
            trap_rate = tr / n
            
            # Balance check
            if trap_rate > 0.35:
                balance = "🚨 TRAP"
            elif wr < 0.35:
                balance = "⚠ LOW"
            elif wr > 0.65:
                balance = "★ HIGH"
            else:
                balance = "OK"
            
            print(f"  {ticker:<8s} {signal[:12]:<12s} {gr:>5d} {sm:>5d} {sg:>5d} {mi:>5d} {tr:>5d} {fs:>5d} │ {balance:>8s}")
    
    sp("6B: Temporal distribution — are labels evenly spread?")
    for ticker in ["AAPL", "COST", "SPY", "QQQ", "JPM", "WMT"]:
        sub = df[df["ticker"]==ticker]
        if len(sub) < 20: continue
        
        decade_dist = sub.groupby(sub["year"] // 10 * 10).agg(
            n=("is_win", "count"),
            wr=("is_win", "mean")
        )
        
        print(f"\n    {ticker}:")
        for decade, row in decade_dist.iterrows():
            bar = "█" * int(row["wr"] * 20)
            marker = " ⚠ REGIME BIAS?" if abs(row["wr"] - sub["is_win"].mean()) > 0.1 else ""
            print(f"      {decade}s: N={row['n']:>4.0f} WR={row['wr']*100:>5.1f}% {bar}{marker}")
    
    sp("6C: Never-tested combos — features that v6-v10 never crossed")
    
    # Check: has anyone tested fear × vol_regime × sigma together?
    combos_never_tested = []
    
    # 1. Fear + KV + σ triple combo
    for ticker in sorted(df["ticker"].unique()):
        for signal in ["rsi_intelligence"]:
            sub = df[(df["ticker"]==ticker) & (df["signal_name"]==signal)]
            if len(sub) < 20: continue
            
            mask = ((sub["snap_fear_level"] >= 2) & 
                    (sub["snap_kalman_velocity"] < -0.1) & 
                    (sub["snap_sigma_wave"] < -1))
            n = mask.sum()
            if n >= 3:
                wr = sub[mask]["is_win"].mean()
                base = sub["is_win"].mean()
                edge = (wr - base) * 100
                lo, hi, _ = wilson_ci(sub[mask]["is_win"].sum(), n)
                marker = "★" if edge > 5 else "✗" if edge < -5 else " "
                combos_never_tested.append((ticker, "Fear+KV+σ<-1", n, wr*100, base*100, edge, lo*100, hi*100, marker))
    
    print(f"\n    TRIPLE COMBO: Fear≥2 + KV<-0.1 + σ<-1 (RSI only):")
    print(f"    {'Ticker':<8s} {'N':>5s} {'WR':>7s} {'CI95':>15s} {'Base':>6s} {'Edge':>6s}")
    positive = 0
    total = 0
    for t, name, n, wr, base, edge, lo, hi, marker in combos_never_tested:
        total += 1
        if edge > 3: positive += 1
        print(f"    {t:<8s} {n:>5d} {wr:>6.1f}% [{lo:.0f}%-{hi:.0f}%] {base:>5.1f}% {edge:>+5.1f}% {marker}")
    if total > 0:
        print(f"    → {positive}/{total} positive ({positive/total*100:.0f}%)")
    
    # 2. Conjugation + Fear (never tested as dual combo in v7)
    combos_2 = []
    for ticker in sorted(df["ticker"].unique()):
        for signal in ["rsi_intelligence"]:
            sub = df[(df["ticker"]==ticker) & (df["signal_name"]==signal)]
            if len(sub) < 20: continue
            
            mask = ((sub["snap_slope_conjugation"] < -0.05) & 
                    (sub["snap_fear_level"] >= 2))
            n = mask.sum()
            if n >= 3:
                wr = sub[mask]["is_win"].mean()
                base = sub["is_win"].mean()
                edge = (wr - base) * 100
                lo, hi, _ = wilson_ci(sub[mask]["is_win"].sum(), n)
                marker = "★" if edge > 5 else "✗" if edge < -5 else " "
                combos_2.append((ticker, n, wr*100, base*100, edge, lo*100, hi*100, marker))
    
    print(f"\n    DUAL COMBO: Conj<-0.05 + Fear≥2 (RSI only):")
    print(f"    {'Ticker':<8s} {'N':>5s} {'WR':>7s} {'CI95':>15s} {'Base':>6s} {'Edge':>6s}")
    positive = 0
    total = 0
    for t, n, wr, base, edge, lo, hi, marker in combos_2:
        total += 1
        if edge > 3: positive += 1
        print(f"    {t:<8s} {n:>5d} {wr:>6.1f}% [{lo:.0f}%-{hi:.0f}%] {base:>5.1f}% {edge:>+5.1f}% {marker}")
    if total > 0:
        print(f"    → {positive}/{total} positive ({positive/total*100:.0f}%)")
    
    # 3. Vol regime + σ (never tested properly)
    combos_3 = []
    for ticker in sorted(df["ticker"].unique()):
        for signal in ["rsi_intelligence"]:
            sub = df[(df["ticker"]==ticker) & (df["signal_name"]==signal)]
            if len(sub) < 20: continue
            
            for regime in ["NORMAL", "COMPLACENT", "ELEVATED"]:
                mask = ((sub["snap_vol_regime"] == regime) & 
                        (sub["snap_sigma_wave"] < -1))
                n = mask.sum()
                if n >= 3:
                    wr = sub[mask]["is_win"].mean()
                    base = sub["is_win"].mean()
                    edge = (wr - base) * 100
                    marker = "★" if edge > 5 else "✗" if edge < -5 else " "
                    combos_3.append((ticker, regime, n, wr*100, base*100, edge, marker))
    
    print(f"\n    DUAL COMBO: VolRegime + σ<-1 (RSI only):")
    print(f"    {'Ticker':<8s} {'Regime':<12s} {'N':>5s} {'WR':>7s} {'Base':>6s} {'Edge':>6s}")
    for t, reg, n, wr, base, edge, marker in combos_3:
        if abs(edge) > 3:
            print(f"    {t:<8s} {reg:<12s} {n:>5d} {wr:>6.1f}% {base:>5.1f}% {edge:>+5.1f}% {marker}")


# ═══════════════════════════════════════════════════════════
# AUDIT 7: OOS TEMPORAL STABILITY — Decade-by-decade
# ═══════════════════════════════════════════════════════════

def audit_temporal_stability(df: pd.DataFrame):
    p("AUDIT 7: TEMPORAL STABILITY — Does the edge decay over time?")
    
    rules = [
        ("Fear≥2 + σ<-1", lambda d: (d["snap_fear_level"] >= 2) & (d["snap_sigma_wave"] < -1)),
        ("σ < -1.5", lambda d: d["snap_sigma_wave"] < -1.5),
        ("KV < -0.1", lambda d: d["snap_kalman_velocity"] < -0.1),
    ]
    
    periods = [
        (1993, 2005, "1993-2005"),
        (2006, 2010, "2006-2010"),
        (2011, 2015, "2011-2015"),
        (2016, 2020, "2016-2020"),
        (2021, 2026, "2021-2026"),
    ]
    
    for signal in ["rsi_intelligence", "regression_channel"]:
        sp(f"TEMPORAL STABILITY: {signal}")
        sig_df = df[df["signal_name"] == signal]
        
        for rule_name, rule_fn in rules:
            print(f"\n    {rule_name}:")
            print(f"    {'Period':<12s} {'N':>5s} {'WR':>7s} {'Edge':>6s}")
            
            for y_lo, y_hi, label in periods:
                period_df = sig_df[(sig_df["year"] >= y_lo) & (sig_df["year"] <= y_hi)]
                if len(period_df) < 20: continue
                
                base = period_df["is_win"].mean()
                try:
                    mask = rule_fn(period_df)
                    rule_sub = period_df[mask]
                    n = len(rule_sub)
                    if n < 3: continue
                    wr = rule_sub["is_win"].mean()
                    edge = (wr - base) * 100
                    marker = "★" if edge > 5 else "✗" if edge < -5 else " "
                    print(f"    {label:<12s} {n:>5d} {wr*100:>6.1f}% {edge:>+5.1f}% {marker}")
                except:
                    pass


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v11 — DEEP AUDIT & BLIND SPOT DETECTOR")
    print("\n  Loading labels...")
    df = load_all_labels()
    tickers = sorted(df["ticker"].unique())
    print(f"  → {len(df)} labels, {len(tickers)} tickers: {', '.join(tickers)}")
    
    audit_classification(df)
    audit_snapshot_recompute(df)
    audit_signal_overlap(df)
    audit_forward_returns(df)
    audit_cross_version(df)
    audit_blind_spots(df)
    audit_temporal_stability(df)
    
    p("v11 DEEP AUDIT COMPLETE")
