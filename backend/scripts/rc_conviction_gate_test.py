"""
RC × Conviction Score Cross — The Final Question
==================================================
When RC fires AND conviction is high, does WR actually improve?

Takes:
  - RC trades from ml_features + ml_labels (outcome known)
  - channel_snapshots at the same date/ticker (articulation state)
  - Trained logistic regression to compute conviction score

Measures: WR at different conviction thresholds.
This is the GATE test: does the conviction score separate good RC trades from bad ones?
"""
import os
import sys
import json
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

load_dotenv()
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

# Same features as training
FEATURES = [
    "sigma_tide", "sigma_current", "sigma_wave",
    "conj_wave_tide", "conj_current_tide",
    "tension_tide", "tension_current",
    "compression_ratio",
    "geo_state_norm", "geo_velocity_align", "geo_accel_align",
]
PHASE_COL = "geo_phase_angle"
LABEL_WINDOW = 2


def main():
    print("=" * 70)
    print("  RC × CONVICTION SCORE — The Gate Test")
    print("  Question: When RC fires AND conviction is high, does WR improve?")
    print("=" * 70)
    
    store = TimescaleDataStore()
    conn = store._conn()
    
    # ── Step 1: Load RC trades with outcomes ──
    print("\n[1/5] Loading RC trades from ml_features + ml_labels...")
    rc_trades = pd.read_sql("""
        SELECT f.ticker, f.signal_time, f.signal_name,
               l.label, l.return_pct, l.bars_held,
               l.max_favorable_excursion_pct as mfe,
               l.max_adverse_excursion_pct as mae
        FROM engine.ml_features f
        JOIN engine.ml_labels l ON l.feature_id = f.id
        WHERE f.signal_name = 'regression_channel'
        ORDER BY f.ticker, f.signal_time
    """, conn)
    print(f"  RC trades loaded: {len(rc_trades):,}")
    print(f"  Overall WR: {(rc_trades['label'] == 1).mean():.1%}")
    print(f"  Tickers: {rc_trades['ticker'].nunique()}")
    
    # ── Step 2: Load channel snapshots ──
    print("\n[2/5] Loading channel snapshots...")
    feat_cols = ", ".join(FEATURES + [PHASE_COL])
    cs_df = pd.read_sql(f"""
        SELECT ticker, timestamp, {feat_cols}
        FROM engine.channel_snapshots
        WHERE timeframe = '1d'
        ORDER BY ticker, timestamp
    """, conn)
    print(f"  Snapshots loaded: {len(cs_df):,}")
    
    # ── Step 3: Load zigzag for model training ──
    print("\n[3/5] Loading zigzag 5% for model training...")
    zz_df = pd.read_sql("""
        SELECT DISTINCT ticker, timestamp, tp_type
        FROM engine.zigzag_points
        WHERE min_swing_pct = 0.05
        ORDER BY ticker, timestamp
    """, conn)
    print(f"  Zigzag points: {len(zz_df):,}")
    
    store._put(conn)
    
    # ── Step 4: For each overlapping ticker, train model and score RC trades ──
    cs_tickers = set(cs_df["ticker"].unique())
    rc_tickers = set(rc_trades["ticker"].unique())
    overlap = sorted(cs_tickers & rc_tickers)
    print(f"\n[4/5] Processing {len(overlap)} overlapping tickers...")
    
    all_scored_trades = []
    
    for ticker in overlap:
        # Get this ticker's snapshot data
        tk_cs = cs_df[cs_df["ticker"] == ticker].copy().sort_values("timestamp")
        tk_cs = tk_cs.dropna(subset=FEATURES)
        
        if len(tk_cs) < 200:
            continue
        
        # Label for training: is this bar near a zigzag MIN?
        tk_zz_min = zz_df[(zz_df["ticker"] == ticker) & (zz_df["tp_type"] == "MIN")]
        
        tk_cs["is_turn"] = 0
        for _, turn in tk_zz_min.iterrows():
            ts = turn["timestamp"]
            mask = (tk_cs["timestamp"] >= ts - pd.Timedelta(days=LABEL_WINDOW * 2)) & \
                   (tk_cs["timestamp"] <= ts)
            matching = tk_cs[mask].tail(LABEL_WINDOW + 1)
            tk_cs.loc[matching.index, "is_turn"] = 1
        
        # Prepare features
        tk_cs["phase_sin"] = np.sin(tk_cs[PHASE_COL])
        tk_cs["phase_cos"] = np.cos(tk_cs[PHASE_COL])
        X_cols = FEATURES + ["phase_sin", "phase_cos"]
        
        X = tk_cs[X_cols].values
        y = tk_cs["is_turn"].values
        
        if y.sum() < 20 or (y == 0).sum() < 20:
            continue
        
        # Train on ALL data for this ticker (we're scoring RC trades, not predicting)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        model = LogisticRegression(class_weight="balanced", max_iter=1000, C=1.0)
        model.fit(X_scaled, y)
        
        # Score ALL bars
        tk_cs["conviction"] = model.predict_proba(X_scaled)[:, 1]
        
        # Now match RC trades to snapshots
        tk_rc = rc_trades[rc_trades["ticker"] == ticker].copy()
        
        for idx, trade in tk_rc.iterrows():
            trade_date = trade["signal_time"]
            
            # Find closest snapshot (same day or day before)
            time_diffs = abs(tk_cs["timestamp"] - trade_date)
            closest_idx = time_diffs.idxmin()
            closest_diff = time_diffs[closest_idx]
            
            # Only match if within 2 days
            if closest_diff > pd.Timedelta(days=2):
                continue
            
            conviction = tk_cs.loc[closest_idx, "conviction"]
            
            all_scored_trades.append({
                "ticker": ticker,
                "date": str(trade_date.date()) if hasattr(trade_date, 'date') else str(trade_date),
                "label": int(trade["label"]),
                "return_pct": float(trade["return_pct"]) if trade["return_pct"] is not None else 0.0,
                "mfe": float(trade["mfe"]) if trade["mfe"] is not None else 0.0,
                "mae": float(trade["mae"]) if trade["mae"] is not None else 0.0,
                "conviction": float(conviction),
            })
        
        n_matched = len([t for t in all_scored_trades if t["ticker"] == ticker])
        print(f"  {ticker:6s}: {n_matched} RC trades matched with conviction scores")
    
    # ── Step 5: The moment of truth ──
    print("\n" + "=" * 70)
    print("  [5/5] THE GATE TEST — RC Win Rate by Conviction Level")
    print("=" * 70)
    
    scored_df = pd.DataFrame(all_scored_trades)
    
    if len(scored_df) == 0:
        print("  NO TRADES MATCHED. Check date alignment.")
        store.close()
        return
    
    total_trades = len(scored_df)
    overall_wr = (scored_df["label"] == 1).mean()
    print(f"\n  Matched trades: {total_trades}")
    print(f"  Overall RC WR (these tickers): {overall_wr:.1%}")
    
    # WR by conviction buckets
    print(f"\n  {'Conviction':<20} {'N':>6} {'WR':>8} {'Avg Ret':>10} {'Avg MFE':>10} {'Avg MAE':>10} {'Δ WR':>8}")
    print(f"  {'-'*18:<20} {'-'*6:>6} {'-'*6:>8} {'-'*8:>10} {'-'*8:>10} {'-'*8:>10} {'-'*6:>8}")
    
    buckets = [
        ("ALL trades", scored_df),
        ("Conv < 0.20", scored_df[scored_df["conviction"] < 0.20]),
        ("Conv 0.20-0.40", scored_df[(scored_df["conviction"] >= 0.20) & (scored_df["conviction"] < 0.40)]),
        ("Conv 0.40-0.60", scored_df[(scored_df["conviction"] >= 0.40) & (scored_df["conviction"] < 0.60)]),
        ("Conv 0.60-0.80", scored_df[(scored_df["conviction"] >= 0.60) & (scored_df["conviction"] < 0.80)]),
        ("Conv > 0.80", scored_df[scored_df["conviction"] >= 0.80]),
    ]
    
    for name, subset in buckets:
        if len(subset) == 0:
            continue
        wr = (subset["label"] == 1).mean()
        avg_ret = subset["return_pct"].mean()
        avg_mfe = subset["mfe"].mean()
        avg_mae = subset["mae"].mean()
        delta_wr = wr - overall_wr
        print(f"  {name:<20} {len(subset):>6} {wr:>7.1%} {avg_ret:>+9.2f}% {avg_mfe:>+9.2f}% {avg_mae:>+9.2f}% {delta_wr:>+7.1%}")
    
    # Monotonicity test: does WR increase with conviction?
    print(f"\n  ── Monotonicity Test ──")
    quintiles = pd.qcut(scored_df["conviction"], q=5, duplicates="drop")
    for q_label, group in scored_df.groupby(quintiles, observed=True):
        wr = (group["label"] == 1).mean()
        avg_ret = group["return_pct"].mean()
        print(f"  Q {str(q_label):30s}: N={len(group):>5}, WR={wr:.1%}, AvgRet={avg_ret:+.2f}%")
    
    # Per-ticker breakdown for high conviction
    print(f"\n  ── Per-Ticker: Conv > 0.60 vs Conv < 0.30 ──")
    print(f"  {'Ticker':<8} {'Low(<0.3) N':>10} {'Low WR':>8} {'High(>0.6) N':>12} {'High WR':>8} {'Δ WR':>8}")
    
    for ticker in sorted(scored_df["ticker"].unique()):
        tk = scored_df[scored_df["ticker"] == ticker]
        low = tk[tk["conviction"] < 0.30]
        high = tk[tk["conviction"] > 0.60]
        
        if len(low) < 5 or len(high) < 5:
            continue
        
        wr_low = (low["label"] == 1).mean()
        wr_high = (high["label"] == 1).mean()
        delta = wr_high - wr_low
        
        icon = "✅" if delta > 0.10 else "⚠️" if delta > 0 else "❌"
        print(f"  {icon} {ticker:<6} {len(low):>10} {wr_low:>7.1%} {len(high):>12} {wr_high:>7.1%} {delta:>+7.1%}")
    
    # Final verdict
    high_conv = scored_df[scored_df["conviction"] > 0.60]
    low_conv = scored_df[scored_df["conviction"] < 0.30]
    
    if len(high_conv) > 10 and len(low_conv) > 10:
        wr_high = (high_conv["label"] == 1).mean()
        wr_low = (low_conv["label"] == 1).mean()
        spread = wr_high - wr_low
        
        print(f"\n  ══════════════════════════════════════════════")
        print(f"  RC WR when conviction < 0.30: {wr_low:.1%} (N={len(low_conv)})")
        print(f"  RC WR when conviction > 0.60: {wr_high:.1%} (N={len(high_conv)})")
        print(f"  SPREAD: {spread:+.1%}")
        
        if spread > 0.15:
            print(f"  VERDICT: ✅ CONVICTION SCORE IS A VALID GATE (+{spread:.0%} spread)")
        elif spread > 0.05:
            print(f"  VERDICT: ⚠️ MARGINAL GATE (+{spread:.0%} spread)")
        elif spread > 0:
            print(f"  VERDICT: ⚠️ WEAK — barely any improvement")
        else:
            print(f"  VERDICT: ❌ DOES NOT WORK — conviction doesn't improve RC")
        print(f"  ══════════════════════════════════════════════")
    
    # Save
    outdir = os.path.join(os.path.dirname(__file__), "conviction_training_output")
    os.makedirs(outdir, exist_ok=True)
    outfile = os.path.join(outdir, "rc_gate_test.json")
    with open(outfile, "w") as f:
        json.dump(all_scored_trades, f, indent=2, default=str)
    print(f"\n  Scored trades saved to: {outfile}")
    
    store.close()


if __name__ == "__main__":
    main()
