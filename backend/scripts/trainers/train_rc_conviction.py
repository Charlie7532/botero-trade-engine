"""
Train RC Conviction Score — Logistic Regression on Zigzag Ground Truth
======================================================================
Takes the 91K channel_snapshots (articulation values) and the zigzag 5%
turning points (mechanical ground truth) and trains a logistic regression
per ticker to produce turn_prob_piso and turn_prob_techo.

Discipline: measure first, interpret after, celebrate never.
"""
import os
import sys
import json
import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, precision_recall_curve
from sklearn.preprocessing import StandardScaler

load_dotenv()
warnings.filterwarnings("ignore", category=FutureWarning)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

# ── Features to use (continuous articulation values) ─────────────────
FEATURES_PISO = [
    "sigma_tide", "sigma_current", "sigma_wave",
    "conj_wave_tide", "conj_current_tide",
    "tension_tide", "tension_current",
    "compression_ratio",
    "geo_state_norm", "geo_velocity_align", "geo_accel_align",
    # phase_angle decomposed into sin/cos for circularity
]
PHASE_ANGLE_COL = "geo_phase_angle"

FEATURES_TECHO = FEATURES_PISO  # Same features, separate model

# ── Configuration ────────────────────────────────────────────────────
ZIGZAG_THRESHOLD = 0.05  # Only 5% zigzag
LABEL_WINDOW = 2         # t=0, t-1, t-2 labeled as "near turn"
MIN_SAMPLES_PER_CLASS = 30


def load_data(store):
    """Load channel_snapshots and zigzag_points from Neon."""
    conn = store._conn()
    
    # Channel snapshots
    cs_cols = FEATURES_PISO + [PHASE_ANGLE_COL, "rsi_value", "rsi_conviction",
                                "kf_price_filt_vel", "kf_price_innovation",
                                "tide_slope", "current_slope", "wave_slope"]
    cs_cols_sql = ", ".join(cs_cols)
    cs_df = pd.read_sql(f"""
        SELECT ticker, timestamp, {cs_cols_sql}
        FROM engine.channel_snapshots
        WHERE timeframe = '1d'
        ORDER BY ticker, timestamp
    """, conn)
    
    # Zigzag points (5% only, deduplicated)
    zz_df = pd.read_sql(f"""
        SELECT DISTINCT ticker, timestamp, tp_type, price, swing_return
        FROM engine.zigzag_points
        WHERE min_swing_pct = {ZIGZAG_THRESHOLD}
        ORDER BY ticker, timestamp
    """, conn)
    
    store._put(conn)
    return cs_df, zz_df


def label_bars(cs_df, zz_df, turn_type="MIN"):
    """Label each bar as near-turn (1) or not (0)."""
    cs_df = cs_df.copy()
    cs_df["is_turn"] = 0
    
    turns = zz_df[zz_df["tp_type"] == turn_type]
    
    for _, turn in turns.iterrows():
        ticker = turn["ticker"]
        ts = turn["timestamp"]
        
        # Label t=0, t-1, t-2
        mask = (
            (cs_df["ticker"] == ticker) & 
            (cs_df["timestamp"] >= ts - timedelta(days=LABEL_WINDOW * 2)) &
            (cs_df["timestamp"] <= ts)
        )
        matching = cs_df[mask].tail(LABEL_WINDOW + 1)
        cs_df.loc[matching.index, "is_turn"] = 1
    
    return cs_df


def prepare_features(df):
    """Prepare feature matrix with sin/cos decomposition of phase angle."""
    X_cols = FEATURES_PISO.copy()
    
    # Decompose phase angle into sin/cos
    df = df.copy()
    df["phase_sin"] = np.sin(df[PHASE_ANGLE_COL])
    df["phase_cos"] = np.cos(df[PHASE_ANGLE_COL])
    X_cols.extend(["phase_sin", "phase_cos"])
    
    # Drop rows with NaN
    mask = df[X_cols].notna().all(axis=1)
    df = df[mask]
    
    return df, X_cols


def train_and_evaluate(df, X_cols, ticker, turn_label):
    """Train logistic regression and evaluate per ticker."""
    ticker_df = df[df["ticker"] == ticker].copy()
    
    if len(ticker_df) < 100:
        return None
    
    positives = ticker_df["is_turn"].sum()
    negatives = len(ticker_df) - positives
    
    if positives < MIN_SAMPLES_PER_CLASS or negatives < MIN_SAMPLES_PER_CLASS:
        return None
    
    X = ticker_df[X_cols].values
    y = ticker_df["is_turn"].values
    
    # ── Walk-forward split: train on first 70%, test on last 30% ──
    split_idx = int(len(ticker_df) * 0.7)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    
    # Check minimum class presence in both splits
    if y_train.sum() < MIN_SAMPLES_PER_CLASS or y_test.sum() < 5:
        return None
    
    # Scale features
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    
    # Train
    model = LogisticRegression(
        class_weight="balanced",
        max_iter=1000,
        C=1.0,
        solver="lbfgs",
    )
    model.fit(X_train_s, y_train)
    
    # Predict probabilities
    prob_train = model.predict_proba(X_train_s)[:, 1]
    prob_test = model.predict_proba(X_test_s)[:, 1]
    
    # ── Metrics (IN-SAMPLE) ──
    auc_train = roc_auc_score(y_train, prob_train) if y_train.sum() > 0 else 0
    
    # ── Metrics (OUT-OF-SAMPLE — what matters) ──
    auc_test = roc_auc_score(y_test, prob_test) if y_test.sum() > 0 else 0
    
    # Distribution separation
    prob_at_turns_test = prob_test[y_test == 1]
    prob_at_noise_test = prob_test[y_test == 0]
    separation = float(np.median(prob_at_turns_test) - np.median(prob_at_noise_test))
    
    # Precision at thresholds (OOS)
    thresholds_report = {}
    for thr in [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70]:
        fired = prob_test > thr
        if fired.sum() == 0:
            continue
        tp = (fired & (y_test == 1)).sum()
        precision = tp / fired.sum()
        recall = tp / y_test.sum() if y_test.sum() > 0 else 0
        thresholds_report[f"P>{thr:.2f}"] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "n_fired": int(fired.sum()),
        }
    
    # Coefficients
    coefs = {}
    for name, coef in zip(X_cols, model.coef_[0]):
        coefs[name] = round(float(coef), 4)
    
    return {
        "ticker": ticker,
        "turn_type": turn_label,
        "n_total": len(ticker_df),
        "n_turns": int(positives),
        "base_rate": round(positives / len(ticker_df), 4),
        "auc_train": round(auc_train, 4),
        "auc_test": round(auc_test, 4),
        "separation": round(separation, 4),
        "median_prob_turns_oos": round(float(np.median(prob_at_turns_test)), 4),
        "median_prob_noise_oos": round(float(np.median(prob_at_noise_test)), 4),
        "thresholds_oos": thresholds_report,
        "coefficients": coefs,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "n_turns_train": int(y_train.sum()),
        "n_turns_test": int(y_test.sum()),
    }


def main():
    print("=" * 70)
    print("  RC CONVICTION SCORE TRAINING — Logistic Regression × Zigzag 5%")
    print("  Discipline: measure first, interpret after, celebrate never.")
    print("=" * 70)
    
    store = TimescaleDataStore()
    
    # ── Load data ──
    print("\n[1/5] Loading data from Neon...")
    cs_df, zz_df = load_data(store)
    
    zz_5 = zz_df[zz_df["swing_return"].notna()]  # Already filtered by threshold in SQL
    print(f"  Channel snapshots: {len(cs_df):,} rows")
    print(f"  Zigzag 5% points: {len(zz_5):,} points")
    
    tickers = sorted(cs_df["ticker"].unique())
    print(f"  Tickers: {len(tickers)}")
    
    # ── Train PISO models ──
    print("\n[2/5] Labeling bars for PISO (MIN turns)...")
    df_piso = label_bars(cs_df, zz_5, "MIN")
    df_piso, X_cols = prepare_features(df_piso)
    n_piso_turns = df_piso["is_turn"].sum()
    print(f"  Labeled {n_piso_turns:,} bars as near-PISO, {len(df_piso) - n_piso_turns:,} as noise")
    
    print("\n[3/5] Training PISO models per ticker...")
    piso_results = []
    for ticker in tickers:
        result = train_and_evaluate(df_piso, X_cols, ticker, "PISO")
        if result:
            piso_results.append(result)
            auc = result["auc_test"]
            sep = result["separation"]
            icon = "✅" if auc > 0.70 else "⚠️" if auc > 0.60 else "❌"
            print(f"  {icon} {ticker:6s}: AUC_oos={auc:.3f}  Sep={sep:+.3f}  "
                  f"turns={result['n_turns_test']}/{result['n_test']}")
    
    # ── Train TECHO models ──
    print("\n[4/5] Training TECHO models per ticker...")
    df_techo = label_bars(cs_df, zz_5, "MAX")
    df_techo, X_cols_t = prepare_features(df_techo)
    
    techo_results = []
    for ticker in tickers:
        result = train_and_evaluate(df_techo, X_cols_t, ticker, "TECHO")
        if result:
            techo_results.append(result)
            auc = result["auc_test"]
            sep = result["separation"]
            icon = "✅" if auc > 0.70 else "⚠️" if auc > 0.60 else "❌"
            print(f"  {icon} {ticker:6s}: AUC_oos={auc:.3f}  Sep={sep:+.3f}  "
                  f"turns={result['n_turns_test']}/{result['n_test']}")
    
    # ── Summary ──
    print("\n" + "=" * 70)
    print("  [5/5] VERDICT — Does it work or not?")
    print("=" * 70)
    
    if piso_results:
        avg_auc_piso = np.mean([r["auc_test"] for r in piso_results])
        avg_sep_piso = np.mean([r["separation"] for r in piso_results])
        n_good_piso = sum(1 for r in piso_results if r["auc_test"] > 0.65)
        print(f"\n  PISO: avg AUC_oos={avg_auc_piso:.3f}, avg separation={avg_sep_piso:+.3f}")
        print(f"  PISO: {n_good_piso}/{len(piso_results)} tickers with AUC > 0.65")
    
    if techo_results:
        avg_auc_techo = np.mean([r["auc_test"] for r in techo_results])
        avg_sep_techo = np.mean([r["separation"] for r in techo_results])
        n_good_techo = sum(1 for r in techo_results if r["auc_test"] > 0.65)
        print(f"\n  TECHO: avg AUC_oos={avg_auc_techo:.3f}, avg separation={avg_sep_techo:+.3f}")
        print(f"  TECHO: {n_good_techo}/{len(techo_results)} tickers with AUC > 0.65")
    
    # ── Save raw results ──
    all_results = {"piso": piso_results, "techo": techo_results}
    
    outdir = os.path.join(os.path.dirname(__file__), "conviction_training_output")
    os.makedirs(outdir, exist_ok=True)
    
    outfile = os.path.join(outdir, f"conviction_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(outfile, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Results saved to: {outfile}")
    
    # ── Per-ticker detail for best/worst ──
    if piso_results:
        best = max(piso_results, key=lambda r: r["auc_test"])
        worst = min(piso_results, key=lambda r: r["auc_test"])
        
        print(f"\n  ── BEST PISO: {best['ticker']} ──")
        print(f"     AUC_oos={best['auc_test']:.3f}, separation={best['separation']:+.3f}")
        print(f"     Coefficients (β):")
        for feat, coef in sorted(best["coefficients"].items(), key=lambda x: abs(x[1]), reverse=True):
            bar = "█" * int(min(abs(coef) * 5, 30))
            sign = "+" if coef > 0 else "-"
            print(f"       {sign} {feat:25s}: {coef:+.4f} {bar}")
        
        if best["thresholds_oos"]:
            print(f"     Precision at thresholds (OOS):")
            for thr, vals in best["thresholds_oos"].items():
                print(f"       {thr}: precision={vals['precision']:.1%}, "
                      f"recall={vals['recall']:.1%}, N={vals['n_fired']}")
        
        print(f"\n  ── WORST PISO: {worst['ticker']} ──")
        print(f"     AUC_oos={worst['auc_test']:.3f}, separation={worst['separation']:+.3f}")
    
    # Overall verdict
    if piso_results and techo_results:
        overall_auc = np.mean([r["auc_test"] for r in piso_results + techo_results])
        print(f"\n  ══════════════════════════════════════════════")
        if overall_auc > 0.70:
            print(f"  VERDICT: AUC {overall_auc:.3f} > 0.70 → OPERABLE")
            print(f"  The articulations SEPARATE turns from noise.")
        elif overall_auc > 0.60:
            print(f"  VERDICT: AUC {overall_auc:.3f} ∈ [0.60, 0.70] → MARGINAL")
            print(f"  Weak signal. May work as GATE but not as detector.")
        else:
            print(f"  VERDICT: AUC {overall_auc:.3f} < 0.60 → DOES NOT WORK")
            print(f"  The articulations do NOT separate turns from noise.")
            print(f"  Back to the drawing board.")
        print(f"  ══════════════════════════════════════════════")
    
    store.close()


if __name__ == "__main__":
    main()
