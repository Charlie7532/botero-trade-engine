#!/usr/bin/env python3
"""
Forensic Lab v10 — FULL UNIVERSE AUDIT (17 tickers)
====================================================
Runs after Oracle generates labels for all 17 Vault tickers.
Tests ALL forensic discoveries from v1-v9 with:
  1. Base rates per ticker × signal
  2. OOS split (train ≤2020 / test 2021+)
  3. Volume enrichment (CV, dryness, spike, auction)
  4. Cross-ticker consistency (17 tickers, not 4)
  5. Wilson CI for statistical rigor
  6. Feature independence correlation
  7. Hypothesis Governance classification:
     VALIDATED / HYPOTHESIS / CANDIDATE / RETIRED
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
from collections import defaultdict

def p(t): print(f"\n{'='*90}\n  {t}\n{'='*90}")
def sp(t): print(f"\n  ── {t} ──")

# ═══════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════

def wilson_ci(successes, n, z=1.96):
    if n == 0: return 0.0, 0.0, 0.0
    phat = successes / n
    denom = 1 + z**2 / n
    center = phat + z**2 / (2*n)
    spread = z * np.sqrt((phat*(1-phat) + z**2/(4*n)) / n)
    lo = max(0, (center - spread) / denom)
    hi = min(1, (center + spread) / denom)
    return lo, hi, phat


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
            for k, v in snap.items(): flat[f"snap_{k}"] = v
        horizons = row["horizons"]
        if isinstance(horizons, str): horizons = json.loads(horizons)
        if horizons:
            for h_key, h_val in horizons.items():
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


def enrich_volume(ticker: str, entry_df: pd.DataFrame) -> pd.DataFrame:
    """Add vol_cv20, vol_dryness, vol_spike, bar_range_ratio, bar_direction."""
    ohlcv = load_ohlcv(ticker)
    if ohlcv.empty:
        return pd.DataFrame()
    close = ohlcv["close"].values.astype(float)
    volume = ohlcv["volume"].values.astype(float)
    high_arr = ohlcv["high"].values.astype(float)
    low_arr = ohlcv["low"].values.astype(float)
    open_arr = ohlcv["open"].values.astype(float)
    times = ohlcv["time"].values
    n = len(close)

    vol_sma20 = np.full(n, np.nan)
    vol_cv20 = np.full(n, np.nan)
    vol_dryness = np.full(n, np.nan)
    vol_spike = np.full(n, np.nan)
    atr14 = np.full(n, np.nan)

    for i in range(50, n):
        sma = np.mean(volume[i-20:i])
        vol_sma20[i] = sma
        std = np.std(volume[i-20:i])
        vol_cv20[i] = std / sma if sma > 0 else 0
        dry = 0
        for j in range(i, max(i-20, 49), -1):
            if volume[j] < sma * 0.8:
                dry += 1
            else:
                break
        vol_dryness[i] = dry
        prev5 = np.mean(volume[max(0, i-5):i])
        vol_spike[i] = volume[i] / prev5 if prev5 > 0 else 1.0
        if i >= 14:
            trs = []
            for j in range(i-14, i):
                tr = max(high_arr[j] - low_arr[j],
                         abs(high_arr[j] - close[j-1]) if j > 0 else 0,
                         abs(low_arr[j] - close[j-1]) if j > 0 else 0)
                trs.append(tr)
            atr14[i] = np.mean(trs)

    subset = entry_df[entry_df["ticker"] == ticker].copy()
    if len(subset) < 5:
        return pd.DataFrame()

    enriched = []
    for _, row in subset.iterrows():
        st = row["signal_time"]
        if hasattr(st, 'tz') and st.tz is not None:
            st = st.tz_localize(None)
        diffs = np.abs(pd.DatetimeIndex(times) - pd.Timestamp(st))
        bar_idx = int(diffs.argmin())
        if bar_idx < 55: continue
        rec = row.to_dict()
        rec["vol_cv20"] = vol_cv20[bar_idx]
        rec["vol_dryness"] = vol_dryness[bar_idx]
        rec["vol_spike"] = vol_spike[bar_idx]
        rec["atr14"] = atr14[bar_idx]
        bar_range = high_arr[bar_idx] - low_arr[bar_idx]
        rec["bar_range_ratio"] = bar_range / atr14[bar_idx] if atr14[bar_idx] and atr14[bar_idx] > 0 else 1.0
        rec["bar_direction"] = 1 if close[bar_idx] >= open_arr[bar_idx] else -1
        enriched.append(rec)

    return pd.DataFrame(enriched) if enriched else pd.DataFrame()


# ═══════════════════════════════════════════════════════════
# PART 1: BASE RATES — Full universe
# ═══════════════════════════════════════════════════════════

def compute_base_rates(df: pd.DataFrame) -> dict:
    p("PART 1: BASE RATES — Full 17-ticker Universe")
    print(f"\n  {'Ticker':<8s} {'Signal':<25s} {'N':>6s} {'WR':>7s} {'CI_lo':>7s} {'CI_hi':>7s}")
    print(f"  {'─'*65}")

    base_rates = {}
    tickers = sorted(df["ticker"].unique())
    for ticker in tickers:
        for signal in sorted(df[df["ticker"]==ticker]["signal_name"].unique()):
            sub = df[(df["ticker"]==ticker) & (df["signal_name"]==signal)]
            n = len(sub)
            wins = sub["is_win"].sum()
            lo, hi, wr = wilson_ci(wins, n)
            print(f"  {ticker:<8s} {signal:<25s} {n:>6d} {wr*100:>6.1f}% [{lo*100:.0f}%, {hi*100:.0f}%]")
            base_rates[(ticker, signal)] = wr
        # Overall
        sub = df[df["ticker"]==ticker]
        wr_all = sub["is_win"].mean()
        base_rates[(ticker, "ALL")] = wr_all
    
    print(f"\n  {'─'*65}")
    print(f"\n  OVERALL BY TICKER:")
    for ticker in tickers:
        sub = df[df["ticker"]==ticker]
        n = len(sub)
        wr = sub["is_win"].mean()
        lo, hi, _ = wilson_ci(sub["is_win"].sum(), n)
        print(f"  {ticker:<8s} {'ALL':<25s} {n:>6d} {wr*100:>6.1f}% [{lo*100:.0f}%, {hi*100:.0f}%]")

    return base_rates


# ═══════════════════════════════════════════════════════════
# PART 2: OOS VALIDATION — Train ≤2020, Test 2021+
# ═══════════════════════════════════════════════════════════

def oos_validation(df: pd.DataFrame):
    p("PART 2: OUT-OF-SAMPLE VALIDATION (Train ≤2020 / Test 2021+)")
    train = df[df["year"] <= 2020]
    test = df[df["year"] >= 2021]
    print(f"\n  Train: {len(train)} samples ({train['year'].min()}-{train['year'].max()})")
    print(f"  Test:  {len(test)} samples ({test['year'].min()}-{test['year'].max()})")

    # Rules to test — these are the "universal" candidates
    rules = [
        ("σ_wave < -1.5", lambda d: d["snap_sigma_wave"] < -1.5),
        ("σ_wave < -1.0", lambda d: d["snap_sigma_wave"] < -1.0),
        ("Fear ≥ ANXIETY", lambda d: d["snap_fear_level"] >= 3),
        ("Fear ≥ FEAR + σ<-1", lambda d: (d["snap_fear_level"] >= 2) & (d["snap_sigma_wave"] < -1)),
        ("tide_slope > 0.01", lambda d: d["snap_tide_slope"] > 0.01),
        ("tide_slope > 0.01 + σ<-1", lambda d: (d["snap_tide_slope"] > 0.01) & (d["snap_sigma_wave"] < -1)),
        ("KV < -0.1", lambda d: d["snap_kalman_velocity"] < -0.1),
        ("KV < -0.1 + σ<-0.5", lambda d: (d["snap_kalman_velocity"] < -0.1) & (d["snap_sigma_wave"] < -0.5)),
        ("Conjugation < -0.05", lambda d: d["snap_slope_conjugation"] < -0.05),
        ("Conjugation < -0.05 + σ<-1", lambda d: (d["snap_slope_conjugation"] < -0.05) & (d["snap_sigma_wave"] < -1)),
    ]

    # Per ticker
    tickers = sorted(df["ticker"].unique())
    for rule_name, rule_fn in rules:
        sp(f"RULE: {rule_name}")
        print(f"    {'Ticker':<8s} │ {'Train N':>7s} {'Train WR':>9s} │ {'Test N':>6s} {'Test WR':>8s} │ {'Δ':>6s} {'Verdict':>10s}")
        print(f"    {'─'*75}")

        holds = 0
        decays = 0
        total_tested = 0

        for ticker in tickers:
            train_t = train[train["ticker"] == ticker]
            test_t = test[test["ticker"] == ticker]
            if len(train_t) < 10: continue

            try:
                train_mask = rule_fn(train_t)
                test_mask = rule_fn(test_t)
            except Exception:
                continue

            train_sub = train_t[train_mask]
            test_sub = test_t[test_mask]
            tn = len(train_sub)
            tsn = len(test_sub)
            if tn < 5: continue

            tw = train_sub["is_win"].mean() if tn > 0 else 0
            tsw = test_sub["is_win"].mean() if tsn > 0 else 0
            delta = (tsw - tw) * 100 if tsn > 0 else float("nan")

            total_tested += 1
            if tsn < 3:
                verdict = "⚠ LOW N"
            elif tsw >= tw - 0.05:
                verdict = "✅ HOLDS"
                holds += 1
            elif tsw >= tw - 0.15:
                verdict = "⚠ DECAY"
                decays += 1
            else:
                verdict = "🚨 BROKEN"
                decays += 1

            print(f"    {ticker:<8s} │ {tn:>7d} {tw*100:>8.1f}% │ {tsn:>6d} {tsw*100:>7.1f}% │ {delta:>+5.1f}% {verdict:>10s}")

        if total_tested > 0:
            rate = holds / total_tested * 100
            print(f"    → OOS HOLD RATE: {holds}/{total_tested} ({rate:.0f}%)")


# ═══════════════════════════════════════════════════════════
# PART 3: DRAWDOWN TIMING
# ═══════════════════════════════════════════════════════════

def drawdown_timing(df: pd.DataFrame):
    p("PART 3: DRAWDOWN TIMING — Do wins suffer pain first?")
    tickers = sorted(df["ticker"].unique())

    print(f"\n  {'Ticker':<8s} │ {'WR':>6s} │ {'Win DD10':>8s} {'Win ↑10':>7s} {'Timing':>10s} │ {'Loss DD10':>9s} {'R:R':>5s}")
    print(f"  {'─'*75}")

    for ticker in tickers:
        sub = df[df["ticker"]==ticker]
        if len(sub) < 20: continue
        wins = sub[sub["is_win"]==1]
        losses = sub[sub["is_win"]==0]
        wr = sub["is_win"].mean()

        win_dd = wins["h10_max_down_pct"].mean() if len(wins)>0 else 0
        win_up = wins["h10_max_up_pct"].mean() if len(wins)>0 else 0
        loss_dd = losses["h10_max_down_pct"].mean() if len(losses)>0 else 0

        win_bars_down = wins["h10_bars_to_max_down"].mean() if len(wins)>0 else 0
        win_bars_up = wins["h10_bars_to_max_up"].mean() if len(wins)>0 else 0
        dd_first = "⚠ DD 1ST" if win_bars_down < win_bars_up and win_dd < -2 else "✅ UP 1ST"

        rr = abs(win_up / win_dd) if win_dd != 0 else 0
        print(f"  {ticker:<8s} │ {wr*100:>5.1f}% │ {win_dd:>7.2f}% {win_up:>6.2f}% {dd_first:>10s} │ {loss_dd:>8.2f}% {rr:>4.1f}x")


# ═══════════════════════════════════════════════════════════
# PART 4: FEATURE INDEPENDENCE
# ═══════════════════════════════════════════════════════════

def feature_independence(df: pd.DataFrame):
    p("PART 4: FEATURE INDEPENDENCE — Correlation Matrix")
    features = [
        "snap_sigma_wave", "snap_sigma_tide", "snap_fear_level",
        "snap_tide_slope", "snap_kalman_velocity", "snap_rvol",
        "snap_wave_slope", "snap_slope_conjugation", "snap_tide_accel",
        "snap_vol_up_down_ratio",
    ]
    available = [f for f in features if f in df.columns]
    feat_df = df[available].apply(pd.to_numeric, errors="coerce")
    corr = feat_df.corr()

    sp("KEY REDUNDANCY CHECKS (full universe)")
    pairs = [
        ("snap_fear_level", "snap_sigma_wave"),
        ("snap_fear_level", "snap_kalman_velocity"),
        ("snap_sigma_wave", "snap_kalman_velocity"),
        ("snap_tide_slope", "snap_tide_accel"),
        ("snap_wave_slope", "snap_slope_conjugation"),
        ("snap_rvol", "snap_vol_up_down_ratio"),
        ("snap_sigma_wave", "snap_sigma_tide"),
        ("snap_tide_slope", "snap_fear_level"),
    ]
    for f1, f2 in pairs:
        if f1 not in feat_df.columns or f2 not in feat_df.columns: continue
        valid = feat_df[[f1, f2]].dropna()
        if len(valid) < 10: continue
        r, pv = stats.pearsonr(valid[f1], valid[f2])
        n1 = f1.replace("snap_", "")
        n2 = f2.replace("snap_", "")
        status = "🚨 REDUNDANT" if abs(r) > 0.5 else "⚠ PARTIAL" if abs(r) > 0.3 else "✅ INDEPENDENT"
        print(f"    {n1:>22s} × {n2:<22s} r={r:+.3f}  p={pv:.4f}  N={len(valid):>5d}  {status}")


# ═══════════════════════════════════════════════════════════
# PART 5: CROSS-TICKER CONSISTENCY — 17 tickers
# ═══════════════════════════════════════════════════════════

def cross_ticker_snap(df: pd.DataFrame, base_rates: dict):
    """Test rules using snap_ variables across all tickers."""
    p("PART 5A: CROSS-TICKER CONSISTENCY — Snap Features (17 tickers)")

    rules = [
        ("σ < -1.5 (deep floor)", lambda d: d["snap_sigma_wave"] < -1.5),
        ("σ < -1.0 (floor)", lambda d: d["snap_sigma_wave"] < -1.0),
        ("Fear ≥ ANXIETY", lambda d: d["snap_fear_level"] >= 3),
        ("Fear ≥ FEAR + σ<-1", lambda d: (d["snap_fear_level"] >= 2) & (d["snap_sigma_wave"] < -1)),
        ("tide>0 + σ<-1 (pullback)", lambda d: (d["snap_tide_slope"] > 0.01) & (d["snap_sigma_wave"] < -1)),
        ("Conjugation < -0.05", lambda d: d["snap_slope_conjugation"] < -0.05),
        ("KV < -0.1 + σ<-0.5", lambda d: (d["snap_kalman_velocity"] < -0.1) & (d["snap_sigma_wave"] < -0.5)),
    ]

    tickers = sorted(df["ticker"].unique())
    for rule_name, rule_fn in rules:
        print(f"\n  {rule_name}:")
        print(f"    {'Ticker':<8s} {'N':>5s} {'WR':>7s} {'CI95':>15s} {'Edge':>6s}")
        positive = 0
        negative = 0
        total = 0
        for ticker in tickers:
            sub = df[df["ticker"]==ticker]
            if len(sub) < 20: continue
            try:
                mask = rule_fn(sub)
                rule_sub = sub[mask]
                n = len(rule_sub)
                if n < 3: continue
                total += 1
                wins = rule_sub["is_win"].sum()
                lo, hi, wr = wilson_ci(wins, n)
                base = base_rates.get((ticker, "ALL"), 0.5)
                edge = (wr - base) * 100
                marker = "★" if wr > base + 0.03 else "✗" if wr < base - 0.03 else " "
                if wr > base + 0.03: positive += 1
                if wr < base - 0.03: negative += 1
                print(f"    {ticker:<8s} {n:>5d} {wr*100:>6.1f}% [{lo*100:.0f}%-{hi*100:.0f}%] {edge:>+5.1f}% {marker}")
            except Exception:
                pass

        if total >= 3:
            pct = positive / total * 100
            if positive >= total * 0.6:
                print(f"    → ★★ UNIVERSAL POSITIVE ({positive}/{total} = {pct:.0f}%)")
            elif negative >= total * 0.6:
                print(f"    → ✗✗ UNIVERSAL NEGATIVE ({negative}/{total})")
            elif positive >= total * 0.4:
                print(f"    → ★ PARTIAL POSITIVE ({positive}/{total} = {pct:.0f}%)")
            else:
                print(f"    → TICKER-SPECIFIC ({positive}/{total} positive, {negative}/{total} negative)")


def cross_ticker_volume(all_enriched: dict, base_rates: dict):
    """Test volume rules across all tickers."""
    p("PART 5B: CROSS-TICKER CONSISTENCY — Volume Features (17 tickers)")

    rules = [
        ("Low CV + σ<-1", lambda d: (d["vol_cv20"] <= d["vol_cv20"].quantile(0.33)) & (d["snap_sigma_wave"] < -1)),
        ("High CV + σ neutral", lambda d: (d["vol_cv20"] > d["vol_cv20"].quantile(0.67)) & (d["snap_sigma_wave"].between(-0.5, 0.5))),
        ("Drought≥2 + σ<-1", lambda d: (d["vol_dryness"] >= 2) & (d["snap_sigma_wave"] < -1)),
        ("Drought≥2 + σ>0", lambda d: (d["vol_dryness"] >= 2) & (d["snap_sigma_wave"] > 0)),
        ("Balance (quiet+narrow)", lambda d: (d["vol_spike"] < 0.8) & (d["bar_range_ratio"] < 0.8)),
        ("Initiative (loud+wide)", lambda d: (d["vol_spike"] >= 1.2) & (d["bar_range_ratio"] >= 1.2)),
        ("Low CV everywhere", lambda d: d["vol_cv20"] <= d["vol_cv20"].quantile(0.33)),
        ("Drought≥4 (extended)", lambda d: d["vol_dryness"] >= 4),
    ]

    tickers = sorted(all_enriched.keys())
    for rule_name, rule_fn in rules:
        print(f"\n  {rule_name}:")
        print(f"    {'Ticker':<8s} {'N':>5s} {'WR':>7s} {'CI95':>15s} {'Edge':>6s}")
        positive = 0
        negative = 0
        total = 0
        for ticker in tickers:
            edf = all_enriched.get(ticker)
            if edf is None or len(edf) < 20: continue
            try:
                mask = rule_fn(edf)
                sub = edf[mask]
                n = len(sub)
                if n < 3: continue
                total += 1
                wins = sub["is_win"].sum()
                lo, hi, wr = wilson_ci(wins, n)
                base = base_rates.get((ticker, "ALL"), 0.5)
                edge = (wr - base) * 100
                marker = "★" if wr > base + 0.03 else "✗" if wr < base - 0.03 else " "
                if wr > base + 0.03: positive += 1
                if wr < base - 0.03: negative += 1
                print(f"    {ticker:<8s} {n:>5d} {wr*100:>6.1f}% [{lo*100:.0f}%-{hi*100:.0f}%] {edge:>+5.1f}% {marker}")
            except Exception:
                pass

        if total >= 3:
            pct = positive / total * 100
            if positive >= total * 0.6:
                print(f"    → ★★ UNIVERSAL POSITIVE ({positive}/{total} = {pct:.0f}%)")
            elif negative >= total * 0.6:
                print(f"    → ✗✗ UNIVERSAL NEGATIVE ({negative}/{total})")
            elif positive >= total * 0.4:
                print(f"    → ★ PARTIAL POSITIVE ({positive}/{total} = {pct:.0f}%)")
            else:
                print(f"    → TICKER-SPECIFIC ({positive}/{total} positive)")


# ═══════════════════════════════════════════════════════════
# PART 6: HYPOTHESIS GOVERNANCE — Final classification
# ═══════════════════════════════════════════════════════════

def hypothesis_classification(df: pd.DataFrame, all_enriched: dict, base_rates: dict):
    p("PART 6: HYPOTHESIS GOVERNANCE — Feature Classification")
    
    features = [
        # (name, description, rule_fn, requires_volume, min_n)
        ("sigma_wave < -1.5", "Deep floor", lambda d: d["snap_sigma_wave"] < -1.5, False, 20),
        ("sigma_wave < -1.0", "Floor", lambda d: d["snap_sigma_wave"] < -1.0, False, 30),
        ("fear_level >= 3", "High fear", lambda d: d["snap_fear_level"] >= 3, False, 30),
        ("tide_slope > 0.01", "Bull regime", lambda d: d["snap_tide_slope"] > 0.01, False, 30),
        ("slope_conjugation < -0.05", "Deep pullback", lambda d: d["snap_slope_conjugation"] < -0.05, False, 20),
        ("fear + σ<-1", "Fear at floor", lambda d: (d["snap_fear_level"] >= 2) & (d["snap_sigma_wave"] < -1), False, 15),
        ("tide>0 + σ<-1", "Pullback in bull", lambda d: (d["snap_tide_slope"] > 0.01) & (d["snap_sigma_wave"] < -1), False, 15),
        ("Low CV + σ<-1", "Steady vol at floor", lambda d: (d["vol_cv20"] <= d["vol_cv20"].quantile(0.33)) & (d["snap_sigma_wave"] < -1), True, 10),
        ("Drought≥2 + σ<-1", "Dry at floor", lambda d: (d["vol_dryness"] >= 2) & (d["snap_sigma_wave"] < -1), True, 5),
        ("Balance", "Quiet+narrow", lambda d: (d["vol_spike"] < 0.8) & (d["bar_range_ratio"] < 0.8), True, 10),
    ]

    print(f"\n  {'Feature':<30s} │ {'Tickers+':>8s} {'Tickers−':>8s} {'OOS rate':>9s} │ {'STATUS':>12s} {'GRADE':>6s}")
    print(f"  {'─'*90}")

    for name, desc, rule_fn, needs_vol, min_n in features:
        tickers_positive = 0
        tickers_negative = 0
        tickers_total = 0
        oos_holds = 0
        oos_tested = 0

        data_source = all_enriched if needs_vol else {"_ALL_": df}
        if not needs_vol:
            data_source = {}
            for ticker in sorted(df["ticker"].unique()):
                sub = df[df["ticker"]==ticker]
                if len(sub) >= 20:
                    data_source[ticker] = sub

        for ticker, tdf in data_source.items():
            if len(tdf) < 20: continue
            try:
                mask = rule_fn(tdf)
                sub = tdf[mask]
                n = len(sub)
                if n < min_n: continue
                tickers_total += 1
                wr = sub["is_win"].mean()
                base = base_rates.get((ticker, "ALL"), 0.5)
                if wr > base + 0.03: tickers_positive += 1
                if wr < base - 0.03: tickers_negative += 1

                # OOS check
                train_sub = sub[sub["year"] <= 2020]
                test_sub = sub[sub["year"] >= 2021]
                if len(train_sub) >= 5 and len(test_sub) >= 3:
                    oos_tested += 1
                    tw = train_sub["is_win"].mean()
                    tsw = test_sub["is_win"].mean()
                    if tsw >= tw - 0.10:
                        oos_holds += 1
            except Exception:
                pass

        # Classification
        oos_rate = f"{oos_holds}/{oos_tested}" if oos_tested > 0 else "N/A"

        if tickers_total < 3:
            status = "CANDIDATE"
            grade = "—"
        elif tickers_positive >= tickers_total * 0.6 and oos_tested > 0 and oos_holds >= oos_tested * 0.5:
            status = "VALIDATED"
            grade = "B" if tickers_positive >= tickers_total * 0.7 else "C"
        elif tickers_positive >= tickers_total * 0.4:
            status = "HYPOTHESIS"
            grade = "D"
        elif tickers_negative >= tickers_total * 0.5:
            status = "RETIRED"
            grade = "F"
        else:
            status = "HYPOTHESIS"
            grade = "D"

        print(f"  {name:<30s} │ {tickers_positive:>3d}/{tickers_total:<3d}  {tickers_negative:>3d}/{tickers_total:<3d}  {oos_rate:>9s} │ {status:>12s} {grade:>6s}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v10 — FULL UNIVERSE AUDIT (17 TICKERS)")
    print("\n  Loading labels...")
    df = load_all_labels()
    tickers = sorted(df["ticker"].unique())
    print(f"  → {len(df)} labels, {len(tickers)} tickers: {', '.join(tickers)}")
    print(f"  → Years: {df['year'].min()}-{df['year'].max()}")

    # Part 1
    base_rates = compute_base_rates(df)

    # Part 2
    oos_validation(df)

    # Part 3
    drawdown_timing(df)

    # Part 4
    feature_independence(df)

    # Enrich all tickers
    print("\n  Enriching ALL tickers with volume features...")
    all_enriched = {}
    for ticker in tickers:
        print(f"    → {ticker}...", end=" ", flush=True)
        edf = enrich_volume(ticker, df)
        if len(edf) > 0:
            all_enriched[ticker] = edf
            print(f"OK ({len(edf)} samples)")
        else:
            print("SKIP")

    # Part 5
    cross_ticker_snap(df, base_rates)
    cross_ticker_volume(all_enriched, base_rates)

    # Part 6
    hypothesis_classification(df, all_enriched, base_rates)

    p("v10 FULL UNIVERSE AUDIT COMPLETE")
