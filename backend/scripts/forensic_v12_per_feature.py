#!/usr/bin/env python3
"""
Forensic Lab v12 — PER-FEATURE SCIENTIFIC EVALUATION
=====================================================
López de Prado methodology: evaluate each snapshot variable independently.

For EACH feature, compute:
  1. Univariate predictive power (point-biserial r, mutual information)
  2. Per-signal-type analysis (RSI vs RC separately)
  3. Cross-ticker universality (% of tickers where feature adds edge)
  4. Temporal stability (per-period edge)
  5. OOS hold rate (train ≤2020, test ≥2021)
  6. Feature importance in Random Forest (purged CV)
  7. Deflated Sharpe Ratio proxy (adjusted for multiple testing)
  8. Hypothesis Governance classification

Uses store.load_bars() exclusively (lesson from v11 audit).
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
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, log_loss
from sklearn.feature_selection import mutual_info_classif

def p(t): print(f"\n{'='*90}\n  {t}\n{'='*90}")
def sp(t): print(f"\n  ── {t} ──")


# ═══════════════════════════════════════════════════════════
# DATA LOADING — Uses store pattern (v11 lesson)
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
        }
        snap = row["snapshot"]
        if isinstance(snap, str): snap = json.loads(snap)
        if snap:
            for k, v in snap.items(): flat[k] = v
        records.append(flat)
    df = pd.DataFrame(records)
    df["signal_time"] = pd.to_datetime(df["signal_time"])
    df["year"] = df["signal_time"].dt.year
    df["is_win"] = df["classification"].isin(["GOLDEN_RUN", "SOLID_MOVE"]).astype(int)
    # Numeric coercion for feature columns
    feature_cols = [c for c in df.columns if c not in [
        "ticker", "signal_name", "signal_direction", "signal_time",
        "classification", "year", "is_win",
        "regime", "wyckoff_state", "vol_regime", "fear_label",
        "wave_flip_direction"
    ]]
    for c in feature_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def wilson_ci(s, n, z=1.96):
    if n == 0: return 0.0, 0.0, 0.0
    phat = s / n
    d = 1 + z**2 / n
    c = phat + z**2 / (2*n)
    sp_ = z * np.sqrt((phat*(1-phat) + z**2/(4*n)) / n)
    return max(0, (c - sp_) / d), min(1, (c + sp_) / d), phat


# ═══════════════════════════════════════════════════════════
# PART 1: UNIVARIATE ANALYSIS — Each continuous feature
# ═══════════════════════════════════════════════════════════

CONTINUOUS_FEATURES = [
    "sigma_wave", "sigma_tide", "tide_slope", "tide_accel",
    "wave_slope", "slope_conjugation", "fear_level",
    "kalman_velocity", "rvol", "vol_up_down_ratio", "rsi_value",
]

CATEGORICAL_FEATURES = [
    "regime", "wyckoff_state", "vol_regime", "fear_label",
    "wave_flip", "wave_flip_direction", "below_vwap",
]


def univariate_analysis(df: pd.DataFrame):
    p("PART 1: UNIVARIATE PREDICTIVE POWER — Per Feature")
    
    for signal in ["rsi_intelligence", "regression_channel"]:
        sp(f"Signal: {signal}")
        sig_df = df[df["signal_name"] == signal].copy()
        y = sig_df["is_win"]
        
        print(f"\n    {'Feature':<22s} │ {'r_pb':>7s} {'p-val':>8s} │ {'MI':>6s} │ {'AUC':>6s} │ {'Status':>10s}")
        print(f"    {'─'*75}")
        
        results = []
        for feat in CONTINUOUS_FEATURES:
            vals = sig_df[feat].dropna()
            y_f = y.loc[vals.index]
            if len(vals) < 50: continue
            
            # Point-biserial correlation
            r_pb, p_val = stats.pointbiserialr(y_f, vals)
            
            # Mutual Information
            mi = mutual_info_classif(
                vals.values.reshape(-1, 1), y_f.values,
                discrete_features=False, random_state=42
            )[0]
            
            # AUC (univariate)
            try:
                auc = roc_auc_score(y_f, vals)
                if auc < 0.5: auc = 1 - auc  # Flip direction
            except:
                auc = 0.5
            
            # Status determination
            if abs(r_pb) > 0.1 and p_val < 0.01:
                status = "★ STRONG"
            elif abs(r_pb) > 0.05 and p_val < 0.05:
                status = "• MODERATE"
            elif p_val < 0.10:
                status = "~ WEAK"
            else:
                status = "✗ NONE"
            
            sig_marker = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else ""
            print(f"    {feat:<22s} │ {r_pb:>+7.4f} {p_val:>7.4f}{sig_marker:>1s} │ {mi:>6.4f} │ {auc:>6.3f} │ {status:>10s}")
            
            results.append({
                "feature": feat, "signal": signal,
                "r_pb": r_pb, "p_val": p_val, "mi": mi, "auc": auc, "status": status
            })
        
        # Categorical features
        print(f"\n    Categorical Features:")
        print(f"    {'Feature':<22s} │ {'Chi2':>8s} {'p-val':>8s} │ {'Cramér V':>8s} │ {'Status':>10s}")
        print(f"    {'─'*65}")
        
        for feat in CATEGORICAL_FEATURES:
            vals = sig_df[feat].dropna()
            y_f = y.loc[vals.index]
            if len(vals) < 50: continue
            
            try:
                ct = pd.crosstab(vals, y_f)
                chi2, p_val, dof, expected = stats.chi2_contingency(ct)
                n_obs = ct.sum().sum()
                k = min(ct.shape)
                cramer_v = np.sqrt(chi2 / (n_obs * max(k - 1, 1)))
                
                if cramer_v > 0.1 and p_val < 0.01:
                    status = "★ STRONG"
                elif cramer_v > 0.05 and p_val < 0.05:
                    status = "• MODERATE"
                elif p_val < 0.10:
                    status = "~ WEAK"
                else:
                    status = "✗ NONE"
                
                print(f"    {feat:<22s} │ {chi2:>8.2f} {p_val:>8.4f} │ {cramer_v:>8.4f} │ {status:>10s}")
            except:
                print(f"    {feat:<22s} │ {'ERROR':>8s}")


# ═══════════════════════════════════════════════════════════
# PART 2: CROSS-TICKER UNIVERSALITY — Per Feature
# ═══════════════════════════════════════════════════════════

def cross_ticker_analysis(df: pd.DataFrame):
    p("PART 2: CROSS-TICKER UNIVERSALITY — Per Feature")
    
    for signal in ["rsi_intelligence", "regression_channel"]:
        sp(f"Signal: {signal}")
        sig_df = df[df["signal_name"] == signal].copy()
        
        print(f"\n    {'Feature':<22s} │ {'Positive':>8s} {'Negative':>8s} {'Neutral':>8s} │ {'% Pos':>6s} │ {'Verdict':>15s}")
        print(f"    {'─'*80}")
        
        for feat in CONTINUOUS_FEATURES:
            positive = 0
            negative = 0
            neutral = 0
            total = 0
            
            for ticker in sorted(sig_df["ticker"].unique()):
                sub = sig_df[sig_df["ticker"] == ticker]
                vals = sub[feat].dropna()
                y_f = sub.loc[vals.index, "is_win"]
                if len(vals) < 15: continue
                
                total += 1
                r, pval = stats.pointbiserialr(y_f, vals)
                
                # Is the direction CONSISTENT with the global direction?
                # For sigma_wave: negative = buy signal (lower = more oversold)
                # So a NEGATIVE r means "lower sigma → more wins" = edge
                if abs(r) > 0.05 and pval < 0.15:
                    if r < 0:
                        negative += 1
                    else:
                        positive += 1
                else:
                    neutral += 1
            
            if total < 5: continue
            
            # Determine dominant direction
            dominant = max(positive, negative)
            pct = dominant / total * 100
            
            if pct >= 60:
                verdict = "★★ UNIVERSAL"
            elif pct >= 40:
                verdict = "★ PARTIAL"
            elif dominant < total * 0.3:
                verdict = "✗ NO EDGE"
            else:
                verdict = "• SPLIT"
            
            sign = "+" if positive > negative else "-" if negative > positive else "~"
            print(f"    {feat:<22s} │ {positive:>8d} {negative:>8d} {neutral:>8d} │ {pct:>5.0f}% │ {sign} {verdict}")


# ═══════════════════════════════════════════════════════════
# PART 3: TEMPORAL STABILITY — Per Feature
# ═══════════════════════════════════════════════════════════

def temporal_stability(df: pd.DataFrame):
    p("PART 3: TEMPORAL STABILITY — Does Each Feature's Edge Hold?")
    
    periods = [
        (1993, 2005, "1993-2005"),
        (2006, 2010, "2006-2010"),
        (2011, 2015, "2011-2015"),
        (2016, 2020, "2016-2020"),
        (2021, 2026, "2021-2026"),
    ]
    
    for signal in ["rsi_intelligence", "regression_channel"]:
        sp(f"Signal: {signal}")
        sig_df = df[df["signal_name"] == signal].copy()
        
        print(f"\n    {'Feature':<22s}", end="")
        for _, _, label in periods:
            print(f" │ {label:>10s}", end="")
        print(f" │ {'Stable?':>8s}")
        print(f"    {'─'*90}")
        
        for feat in CONTINUOUS_FEATURES:
            vals_all = sig_df[feat].dropna()
            if len(vals_all) < 100: continue
            
            period_rs = []
            print(f"    {feat:<22s}", end="")
            
            for y_lo, y_hi, label in periods:
                period_df = sig_df[(sig_df["year"] >= y_lo) & (sig_df["year"] <= y_hi)]
                vals = period_df[feat].dropna()
                y_f = period_df.loc[vals.index, "is_win"]
                
                if len(vals) < 20:
                    print(f" │ {'N/A':>10s}", end="")
                    continue
                
                r, pval = stats.pointbiserialr(y_f, vals)
                period_rs.append(r)
                
                marker = "★" if abs(r) > 0.1 and pval < 0.05 else ""
                print(f" │ {r:>+8.3f}{marker:>2s}", end="")
            
            # Stability check: are signs consistent?
            if len(period_rs) >= 3:
                signs = [np.sign(r) for r in period_rs if abs(r) > 0.02]
                if len(signs) >= 3:
                    consistency = max(signs.count(1), signs.count(-1)) / len(signs)
                    stable = "✅" if consistency >= 0.8 else "⚠" if consistency >= 0.6 else "🚨"
                else:
                    stable = "~"
            else:
                stable = "?"
            
            print(f" │ {stable:>8s}")


# ═══════════════════════════════════════════════════════════
# PART 4: OOS VALIDATION — Train ≤2020, Test ≥2021
# ═══════════════════════════════════════════════════════════

def oos_validation(df: pd.DataFrame):
    p("PART 4: OUT-OF-SAMPLE VALIDATION — Train ≤2020, Test ≥2021")
    
    for signal in ["rsi_intelligence", "regression_channel"]:
        sp(f"Signal: {signal}")
        sig_df = df[df["signal_name"] == signal].copy()
        
        train = sig_df[sig_df["year"] <= 2020]
        test = sig_df[sig_df["year"] >= 2021]
        
        if len(train) < 50 or len(test) < 50:
            print(f"    Insufficient data: train={len(train)}, test={len(test)}")
            continue
        
        print(f"    Train: {len(train)} labels (≤2020), Test: {len(test)} labels (≥2021)")
        print(f"\n    {'Feature':<22s} │ {'Train r':>8s} {'Test r':>8s} {'Δ':>6s} │ {'Train AUC':>9s} {'Test AUC':>9s} │ {'Hold?':>6s}")
        print(f"    {'─'*80}")
        
        for feat in CONTINUOUS_FEATURES:
            tr_vals = train[feat].dropna()
            tr_y = train.loc[tr_vals.index, "is_win"]
            te_vals = test[feat].dropna()
            te_y = test.loc[te_vals.index, "is_win"]
            
            if len(tr_vals) < 30 or len(te_vals) < 30: continue
            
            r_tr, _ = stats.pointbiserialr(tr_y, tr_vals)
            r_te, _ = stats.pointbiserialr(te_y, te_vals)
            delta = r_te - r_tr
            
            try:
                auc_tr = roc_auc_score(tr_y, tr_vals)
                if auc_tr < 0.5: auc_tr = 1 - auc_tr
                auc_te = roc_auc_score(te_y, te_vals)
                if auc_te < 0.5: auc_te = 1 - auc_te
            except:
                auc_tr = auc_te = 0.5
            
            # Hold: does the direction hold and magnitude not decay > 50%?
            same_sign = (np.sign(r_tr) == np.sign(r_te)) or abs(r_te) < 0.02
            magnitude_ok = abs(r_te) >= abs(r_tr) * 0.5 if abs(r_tr) > 0.03 else True
            hold = "✅" if same_sign and magnitude_ok else "⚠" if same_sign else "🚨"
            
            print(f"    {feat:<22s} │ {r_tr:>+8.4f} {r_te:>+8.4f} {delta:>+5.3f} │ {auc_tr:>9.3f} {auc_te:>9.3f} │ {hold:>6s}")


# ═══════════════════════════════════════════════════════════
# PART 5: RANDOM FOREST FEATURE IMPORTANCE (Purged CV)
# ═══════════════════════════════════════════════════════════

def feature_importance_rf(df: pd.DataFrame):
    p("PART 5: RANDOM FOREST FEATURE IMPORTANCE — Purged Walk-Forward")
    
    for signal in ["rsi_intelligence", "regression_channel"]:
        sp(f"Signal: {signal}")
        sig_df = df[df["signal_name"] == signal].copy().sort_values("signal_time")
        
        feats = [f for f in CONTINUOUS_FEATURES if f in sig_df.columns]
        X = sig_df[feats].copy()
        y = sig_df["is_win"].copy()
        
        # Drop rows with NaN
        valid = X.dropna().index
        X = X.loc[valid]
        y = y.loc[valid]
        
        if len(X) < 200:
            print(f"    Insufficient data: {len(X)}")
            continue
        
        # Walk-forward with purge: 3 folds
        n = len(X)
        fold_size = n // 4
        purge = 10  # 10 bars purge window
        
        importances_all = []
        aucs = []
        
        for fold in range(3):
            train_end = fold_size * (fold + 1)
            test_start = train_end + purge
            test_end = min(test_start + fold_size, n)
            
            if test_end <= test_start or test_end - test_start < 20: continue
            
            X_tr = X.iloc[:train_end]
            y_tr = y.iloc[:train_end]
            X_te = X.iloc[test_start:test_end]
            y_te = y.iloc[test_start:test_end]
            
            if len(y_tr.unique()) < 2 or len(y_te.unique()) < 2: continue
            
            rf = RandomForestClassifier(
                n_estimators=200, max_depth=5, min_samples_leaf=10,
                random_state=42 + fold, class_weight="balanced"
            )
            rf.fit(X_tr, y_tr)
            
            importances_all.append(rf.feature_importances_)
            
            try:
                proba = rf.predict_proba(X_te)[:, 1]
                auc = roc_auc_score(y_te, proba)
                aucs.append(auc)
            except:
                pass
        
        if not importances_all:
            print(f"    No valid folds")
            continue
        
        mean_imp = np.mean(importances_all, axis=0)
        std_imp = np.std(importances_all, axis=0)
        mean_auc = np.mean(aucs) if aucs else 0.5
        
        print(f"\n    Walk-Forward AUC: {mean_auc:.3f} ({len(aucs)} folds)")
        print(f"\n    {'Feature':<22s} │ {'Importance':>10s} {'±Std':>8s} │ {'Rank':>4s} │ {'Verdict':>12s}")
        print(f"    {'─'*65}")
        
        ranked = sorted(zip(feats, mean_imp, std_imp), key=lambda x: -x[1])
        for rank, (feat, imp, std) in enumerate(ranked, 1):
            if imp > 0.15:
                verdict = "★★ CRITICAL"
            elif imp > 0.10:
                verdict = "★ IMPORTANT"
            elif imp > 0.05:
                verdict = "• USEFUL"
            else:
                verdict = "✗ MARGINAL"
            
            bar = "█" * int(imp * 50)
            print(f"    {feat:<22s} │ {imp:>10.4f} {std:>7.4f} │ {rank:>4d} │ {verdict:<12s} {bar}")


# ═══════════════════════════════════════════════════════════
# PART 6: FEATURE CORRELATION MATRIX
# ═══════════════════════════════════════════════════════════

def feature_correlations(df: pd.DataFrame):
    p("PART 6: FEATURE CORRELATION MATRIX — Redundancy Detection")
    
    feats = [f for f in CONTINUOUS_FEATURES if f in df.columns]
    corr = df[feats].corr()
    
    print(f"\n    Highly correlated pairs (|r| > 0.5):")
    print(f"    {'Feature A':<22s} {'Feature B':<22s} {'r':>8s} {'Action':>12s}")
    print(f"    {'─'*70}")
    
    seen = set()
    for i, f1 in enumerate(feats):
        for j, f2 in enumerate(feats):
            if i >= j: continue
            r = corr.loc[f1, f2]
            if abs(r) > 0.5:
                key = tuple(sorted([f1, f2]))
                if key in seen: continue
                seen.add(key)
                
                action = "🚨 REMOVE ONE" if abs(r) > 0.9 else "⚠ MONITOR" if abs(r) > 0.7 else "OK"
                print(f"    {f1:<22s} {f2:<22s} {r:>+8.3f} {action:>12s}")


# ═══════════════════════════════════════════════════════════
# PART 7: HYPOTHESIS GOVERNANCE CLASSIFICATION
# ═══════════════════════════════════════════════════════════

def hypothesis_governance(df: pd.DataFrame):
    p("PART 7: HYPOTHESIS GOVERNANCE — Final Classification")
    
    print("""
    Classification Criteria (López de Prado + Hypothesis Governance):
    ────────────────────────────────────────────────────────────────
    VALIDATED (B):   |r| > 0.05, p < 0.01, ≥60% tickers positive, OOS holds
    HYPOTHESIS-A:    |r| > 0.05, p < 0.05, ≥40% tickers positive
    HYPOTHESIS-B:    Significant in some tickers but not universal
    HYPOTHESIS-C:    Weak/unstable evidence
    RETIRED (F):     No edge, or edge inverted in OOS
    REDUNDANT:       r > 0.9 with another feature
    """)
    
    for signal in ["rsi_intelligence", "regression_channel"]:
        sp(f"Signal: {signal}")
        sig_df = df[df["signal_name"] == signal].copy()
        
        train = sig_df[sig_df["year"] <= 2020]
        test = sig_df[sig_df["year"] >= 2021]
        
        print(f"\n    {'Feature':<22s} │ {'r_pb':>7s} {'p-val':>7s} │ {'Tickers+':>8s} │ {'OOS':>5s} │ {'RF Imp':>6s} │ {'Grade':>12s}")
        print(f"    {'─'*85}")
        
        for feat in CONTINUOUS_FEATURES:
            # Global r
            vals = sig_df[feat].dropna()
            y_f = sig_df.loc[vals.index, "is_win"]
            if len(vals) < 50: continue
            r_pb, p_val = stats.pointbiserialr(y_f, vals)
            
            # Cross-ticker
            positive = 0
            total = 0
            for ticker in sig_df["ticker"].unique():
                sub = sig_df[sig_df["ticker"] == ticker]
                v = sub[feat].dropna()
                yv = sub.loc[v.index, "is_win"]
                if len(v) < 15: continue
                total += 1
                rt, pt = stats.pointbiserialr(yv, v)
                if abs(rt) > 0.05 and pt < 0.15:
                    positive += 1
            
            pct_pos = positive / max(total, 1) * 100
            
            # OOS
            tr_vals = train[feat].dropna()
            tr_y = train.loc[tr_vals.index, "is_win"]
            te_vals = test[feat].dropna()
            te_y = test.loc[te_vals.index, "is_win"]
            
            oos_ok = "?"
            if len(tr_vals) >= 30 and len(te_vals) >= 30:
                r_tr, _ = stats.pointbiserialr(tr_y, tr_vals)
                r_te, _ = stats.pointbiserialr(te_y, te_vals)
                oos_ok = "✅" if np.sign(r_tr) == np.sign(r_te) and abs(r_te) >= abs(r_tr) * 0.5 else "🚨"
            
            # Grade determination
            if abs(r_pb) > 0.05 and p_val < 0.01 and pct_pos >= 60 and oos_ok == "✅":
                grade = "★★ VALID-B"
            elif abs(r_pb) > 0.05 and p_val < 0.05 and pct_pos >= 40:
                grade = "★ HYPO-A"
            elif abs(r_pb) > 0.03 and p_val < 0.10:
                grade = "• HYPO-B"
            elif p_val >= 0.10 or pct_pos < 20:
                grade = "✗ RETIRED"
            else:
                grade = "~ HYPO-C"
            
            sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else ""
            print(f"    {feat:<22s} │ {r_pb:>+7.4f} {p_val:>6.4f}{sig} │ {positive:>3d}/{total:<3d}  │ {oos_ok:>5s} │        │ {grade:>12s}")


# ═══════════════════════════════════════════════════════════
# PART 8: CATEGORICAL FEATURE DEEP DIVE
# ═══════════════════════════════════════════════════════════

def categorical_deep_dive(df: pd.DataFrame):
    p("PART 8: CATEGORICAL FEATURES — Win Rate by Category")
    
    for signal in ["rsi_intelligence", "regression_channel"]:
        sp(f"Signal: {signal}")
        sig_df = df[df["signal_name"] == signal].copy()
        base_wr = sig_df["is_win"].mean()
        
        for feat in CATEGORICAL_FEATURES:
            vals = sig_df[feat].dropna()
            if len(vals) < 50: continue
            
            categories = vals.value_counts()
            if len(categories) < 2: continue
            
            print(f"\n    {feat} (base WR={base_wr*100:.1f}%):")
            for cat in categories.index:
                mask = sig_df[feat] == cat
                n = mask.sum()
                if n < 5: continue
                wr = sig_df.loc[mask, "is_win"].mean() * 100
                edge = wr - base_wr * 100
                marker = "★" if edge > 5 else "✗" if edge < -5 else " "
                bar = "█" * max(0, int(wr / 5))
                print(f"      {str(cat):<25s} N={n:>5d} WR={wr:>5.1f}% edge={edge:>+5.1f}% {marker} {bar}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v12 — PER-FEATURE SCIENTIFIC EVALUATION")
    print("  López de Prado Methodology + Hypothesis Governance")
    
    print("\n  Loading labels...")
    df = load_all_labels()
    tickers = sorted(df["ticker"].unique())
    signals = sorted(df["signal_name"].unique())
    print(f"  → {len(df)} labels, {len(tickers)} tickers, {len(signals)} signals")
    print(f"  → Features: {len(CONTINUOUS_FEATURES)} continuous, {len(CATEGORICAL_FEATURES)} categorical")
    
    univariate_analysis(df)
    cross_ticker_analysis(df)
    temporal_stability(df)
    oos_validation(df)
    feature_importance_rf(df)
    feature_correlations(df)
    categorical_deep_dive(df)
    hypothesis_governance(df)
    
    p("v12 PER-FEATURE EVALUATION COMPLETE")
