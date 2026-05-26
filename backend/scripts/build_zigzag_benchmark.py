#!/usr/bin/env python3
"""
Zigzag Benchmark Builder — Fase 11.1
======================================
1. Creates engine.zigzag_points table
2. Computes zigzag at 3%, 5%, 7% for all 17 tickers
3. Stores turning points in BD
4. Forensic: finds ORTHOGONAL dimensions that fire BEFORE the turn
   (the real training signal — not confirmation but anticipation)

Key insight from System Architect:
  "Nuestra entrada tiene un drift — debimos haber detectado la señal
   JUSTO ANTES del punto de inflexión."
  → The zigzag MIN/MAX become the LABEL for future training.
  → Features that move N bars BEFORE the turn are the real predictors.
"""
import sys, os, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from sqlalchemy import text as sa_text

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]
SWING_PCTS = [0.03, 0.05, 0.07]

def p(t):
    print(f"\n{'═' * 95}")
    print(f"  {t}")
    print(f"{'═' * 95}")


# ═══════════════════════════════════════════════════════════════
# ZIGZAG ALGORITHM
# ═══════════════════════════════════════════════════════════════
def zigzag(close: np.ndarray, min_pct: float = 0.03):
    """Detect alternating MIN/MAX with minimum swing >= min_pct.
    
    Returns list of (index, type, value) tuples.
    type is 'MIN' or 'MAX'.
    """
    if len(close) < 2:
        return []
    
    pts = []
    # Initialize: first point is MIN if price goes up first, MAX if down
    last_idx = 0
    last_type = 'MIN' if close[0] < close[min(1, len(close)-1)] else 'MAX'
    last_val = close[0]
    
    for i in range(1, len(close)):
        if last_type == 'MIN':
            if close[i] > last_val * (1 + min_pct):
                # Confirmed MIN — swing up exceeded threshold
                pts.append((last_idx, 'MIN', last_val))
                # Now look for MAX
                best = last_idx + int(np.argmax(close[last_idx:i+1]))
                last_idx, last_type, last_val = best, 'MAX', close[best]
            elif close[i] < last_val:
                # New lower low — update candidate MIN
                last_idx, last_val = i, close[i]
        else:  # MAX
            if close[i] < last_val * (1 - min_pct):
                # Confirmed MAX — swing down exceeded threshold
                pts.append((last_idx, 'MAX', last_val))
                # Now look for MIN
                best = last_idx + int(np.argmin(close[last_idx:i+1]))
                last_idx, last_type, last_val = best, 'MIN', close[best]
            elif close[i] > last_val:
                # New higher high — update candidate MAX
                last_idx, last_val = i, close[i]
    
    return pts


# ═══════════════════════════════════════════════════════════════
# STEP 1: CREATE TABLE + COMPUTE ZIGZAG
# ═══════════════════════════════════════════════════════════════
def build_zigzag_table(store):
    p("STEP 1: CREATE TABLE engine.zigzag_points")
    
    with store.engine.connect() as conn:
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS engine.zigzag_points (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(10) NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
                tp_type VARCHAR(3) NOT NULL,
                price DOUBLE PRECISION NOT NULL,
                min_swing_pct DOUBLE PRECISION NOT NULL,
                swing_return DOUBLE PRECISION,
                swing_days INTEGER,
                swing_speed DOUBLE PRECISION,
                UNIQUE(ticker, timestamp, tp_type, min_swing_pct)
            )
        """))
        conn.execute(sa_text("DELETE FROM engine.zigzag_points"))
        conn.commit()
    print("  Table created and cleared.")
    
    # Load OHLCV
    ohlcv = pd.read_sql("""
        SELECT ticker, time as timestamp, close 
        FROM market.ohlcv_bars 
        WHERE timeframe='1d' ORDER BY ticker, time
    """, store.engine)
    print(f"  OHLCV loaded: {len(ohlcv):,d} rows")
    
    total_points = 0
    
    for ticker in TICKERS:
        tk_data = ohlcv[ohlcv['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
        close = tk_data['close'].values.astype(float)
        timestamps = tk_data['timestamp'].values
        
        if len(close) < 100:
            print(f"  {ticker}: skipped (only {len(close)} bars)")
            continue
        
        for min_sw in SWING_PCTS:
            pts = zigzag(close, min_sw)
            
            rows = []
            for j, (idx, tp_type, val) in enumerate(pts):
                if idx >= len(timestamps):
                    continue
                
                # Compute swing to next point
                swing_ret = None
                swing_days = None
                swing_speed = None
                if j + 1 < len(pts):
                    next_idx, _, next_val = pts[j+1]
                    if next_idx < len(timestamps):
                        swing_ret = next_val / val - 1
                        swing_days = next_idx - idx
                        swing_speed = swing_ret / max(swing_days, 1)
                
                rows.append({
                    'ticker': ticker,
                    'timestamp': pd.Timestamp(timestamps[idx]),
                    'tp_type': tp_type,
                    'price': float(val),
                    'min_swing_pct': min_sw,
                    'swing_return': swing_ret,
                    'swing_days': swing_days,
                    'swing_speed': swing_speed,
                })
            
            if rows:
                df_rows = pd.DataFrame(rows)
                df_rows.to_sql('zigzag_points', store.engine, schema='engine',
                              if_exists='append', index=False)
                total_points += len(rows)
                
                mins = sum(1 for r in rows if r['tp_type'] == 'MIN')
                maxs = sum(1 for r in rows if r['tp_type'] == 'MAX')
                print(f"  {ticker} ({min_sw*100:.0f}%): {mins} MIN + {maxs} MAX = {len(rows)} points")
    
    print(f"\n  TOTAL: {total_points:,d} zigzag points stored")
    return total_points


# ═══════════════════════════════════════════════════════════════
# STEP 2: SUMMARY STATISTICS
# ═══════════════════════════════════════════════════════════════
def zigzag_summary(store):
    p("STEP 2: ZIGZAG SUMMARY BY CALIBRATION")
    
    zz = pd.read_sql("SELECT * FROM engine.zigzag_points ORDER BY ticker, timestamp", store.engine)
    
    for sw in SWING_PCTS:
        sub = zz[zz['min_swing_pct'] == sw]
        mins = sub[sub['tp_type'] == 'MIN']
        maxs = sub[sub['tp_type'] == 'MAX']
        
        print(f"\n  ── Zigzag ≥ {sw*100:.0f}% ──")
        print(f"    Total points: {len(sub):,d}  (MIN: {len(mins):,d}, MAX: {len(maxs):,d})")
        if len(mins) > 0:
            print(f"    UP legs (MIN→MAX):   avg={mins['swing_return'].mean():+.2%}, "
                  f"median={mins['swing_return'].median():+.2%}, "
                  f"days={mins['swing_days'].median():.0f}d median")
        if len(maxs) > 0:
            print(f"    DOWN legs (MAX→MIN): avg={maxs['swing_return'].mean():+.2%}, "
                  f"median={maxs['swing_return'].median():+.2%}, "
                  f"days={maxs['swing_days'].median():.0f}d median")
    
    # Per ticker summary for 5% zigzag
    print(f"\n  ── Per-Ticker: Zigzag 5% ──")
    print(f"  {'Ticker':>6s} │ {'MINs':>5s} │ {'MAXs':>5s} │ {'Avg UP':>8s} │ {'Avg DN':>8s} │ {'Med d(UP)':>9s} │ {'Med d(DN)':>9s}")
    print(f"  {'─'*65}")
    zz5 = zz[zz['min_swing_pct'] == 0.05]
    for tk in TICKERS:
        tkz = zz5[zz5['ticker'] == tk]
        mins = tkz[tkz['tp_type'] == 'MIN']
        maxs = tkz[tkz['tp_type'] == 'MAX']
        if len(mins) < 3:
            continue
        print(f"  {tk:>6s} │ {len(mins):>5d} │ {len(maxs):>5d} │ {mins['swing_return'].mean():>+7.2%} │ "
              f"{maxs['swing_return'].mean():>+7.2%} │ {mins['swing_days'].median():>7.0f}d │ "
              f"{maxs['swing_days'].median():>7.0f}d")


# ═══════════════════════════════════════════════════════════════
# STEP 3: ORTHOGONAL DIMENSION DISCOVERY
# ═══════════════════════════════════════════════════════════════
def orthogonal_discovery(store):
    p("STEP 3: ORTHOGONAL DIMENSION DISCOVERY")
    print("  Which features move BEFORE the turning point?")
    print("  (= the features that should PREDICT, not confirm)")
    
    # Load zigzag 5% turning points
    zz = pd.read_sql("""
        SELECT * FROM engine.zigzag_points 
        WHERE min_swing_pct = 0.05 
        ORDER BY ticker, timestamp
    """, store.engine)
    
    # Load signal tape (has all features)
    tape = pd.read_sql("SELECT * FROM engine.signal_tape ORDER BY ticker, timestamp", store.engine)
    
    # Features to analyze — ONLY what exists in signal_tape
    heads = ['p_long_entry', 'p_swing_exit', 'p_pullback_depth', 'p_trend_reversal',
             'p_short_entry', 'p_short_cover', 'p_bounce_height', 'p_trend_recovery']
    features = ['sigma_tide', 'sigma_current', 'sigma_wave',
                'rsi_value', 'kalman_velocity', 'fear_level',
                'compression_ratio', 'vol_up_down_ratio', 'tide_slope',
                'current_slope', 'wave_slope',
                'd_sigma_wave', 'd_kalman_velocity', 'd_rsi_value',
                'd_compression_ratio', 'd_fear_level', 'd_vol_up_down_ratio',
                'd_tide_slope', 'd_wave_accel']
    
    all_cols = heads + features
    
    # For each turning point type (MIN/MAX), look at bars -10 to 0
    # Find which features reach their extreme BEFORE bar 0
    for tp_type, desc in [('MIN', 'MINIMA (entry long / cover short)'), 
                           ('MAX', 'MAXIMA (exit long / entry short)')]:
        print(f"\n  ══ {desc} ══")
        print(f"  Analyzing when each feature reaches its extreme relative to the turning point...")
        
        tp_sub = zz[zz['tp_type'] == tp_type]
        
        # For each turning point, find the feature values at bars -10 to +5
        lead_lags = {col: [] for col in all_cols}  # bars before turn where feature extremes
        
        for _, tp_row in tp_sub.iterrows():
            tk_tape = tape[tape['ticker'] == tp_row['ticker']].sort_values('timestamp').reset_index(drop=True)
            
            # Find the closest bar in tape to this zigzag timestamp
            time_diff = (tk_tape['timestamp'] - tp_row['timestamp']).abs()
            if time_diff.min() > pd.Timedelta(days=3):
                continue
            center_idx = time_diff.idxmin()
            
            if center_idx < 10 or center_idx + 5 >= len(tk_tape):
                continue
            
            window = tk_tape.iloc[center_idx - 10: center_idx + 6]  # -10 to +5
            
            for col in all_cols:
                if col not in window.columns:
                    continue
                vals = window[col].values.astype(float)
                if np.all(np.isnan(vals)):
                    continue
                
                if tp_type == 'MIN':
                    # At MIN: bullish features should be rising BEFORE the turn
                    # Look for where the feature hits its minimum (= most bearish)
                    extreme_pos = np.nanargmin(vals)
                else:
                    # At MAX: bearish features should be rising BEFORE the turn
                    extreme_pos = np.nanargmax(vals)
                
                # Position relative to turn (turn = index 10 in window)
                lead_lag = extreme_pos - 10  # negative = BEFORE turn, positive = AFTER
                lead_lags[col].append(lead_lag)
        
        # Report: which features lead?
        print(f"\n  {'Feature':>25s} │ {'N':>5s} │ {'Avg Lead':>9s} │ {'P(before)':>9s} │ {'Med Lead':>9s} │ Verdict")
        print(f"  {'─'*80}")
        
        results = []
        for col in all_cols:
            ll = np.array(lead_lags[col])
            if len(ll) < 50:
                continue
            avg_lead = ll.mean()
            p_before = (ll < 0).mean() * 100
            med_lead = np.median(ll)
            results.append((col, len(ll), avg_lead, p_before, med_lead))
        
        # Sort by most leading (most negative avg)
        results.sort(key=lambda x: x[2])
        
        for col, n, avg, pb, med in results:
            if avg < -1:
                verdict = "🟢 LEADS (anticipador)"
            elif avg < 0:
                verdict = "🟡 Slight lead"
            elif avg < 1:
                verdict = "🟠 AT turn"
            else:
                verdict = "�� LAGS (confirmador)"
            
            star = " ★" if pb > 65 else ""
            print(f"  {col:>25s} │ {n:>5d} │ {avg:>+8.2f}d │ {pb:>8.1f}% │ {med:>+8.1f}d │ {verdict}{star}")
        
        # Orthogonality check: which PAIRS of leading features are uncorrelated?
        leading = [r[0] for r in results if r[2] < -1]
        if len(leading) >= 2:
            print(f"\n  ── Orthogonality Matrix (leading features, r < -1d) ──")
            # Sample 2000 rows from tape for correlation
            sample = tape.sample(min(2000, len(tape)), random_state=42)
            print(f"  {'':>25s}", end="")
            for col in leading[:8]:
                print(f" │ {col[:8]:>8s}", end="")
            print()
            
            for col1 in leading[:8]:
                print(f"  {col1:>25s}", end="")
                for col2 in leading[:8]:
                    corr = sample[col1].corr(sample[col2])
                    mark = " " if abs(corr) < 0.3 else "×"
                    print(f" │ {corr:>+7.2f}{mark}", end="")
                print()
            
            # Identify truly orthogonal pairs
            print(f"\n  ── Orthogonal Leading Pairs (|r| < 0.3) ──")
            pairs_found = 0
            for i, c1 in enumerate(leading):
                for c2 in leading[i+1:]:
                    corr = sample[c1].corr(sample[c2])
                    if abs(corr) < 0.3:
                        pairs_found += 1
                        if pairs_found <= 15:
                            print(f"    {c1:>25s} × {c2:<25s}  r={corr:+.3f} ★ ORTHOGONAL")
            print(f"    Total orthogonal pairs: {pairs_found}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    p("ZIGZAG BENCHMARK BUILDER — FASE 11")
    
    store = TimescaleDataStore()
    
    build_zigzag_table(store)
    zigzag_summary(store)
    orthogonal_discovery(store)
    
    store.close()
    
    p("FASE 11.1 + ORTHOGONAL DISCOVERY COMPLETE")

if __name__ == "__main__":
    main()
