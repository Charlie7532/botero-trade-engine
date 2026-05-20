#!/usr/bin/env python3
"""
Forensic Lab v9 REAL — BLIND SPOT AUDIT (6 dimensions)
=======================================================
1. OUT-OF-SAMPLE SPLIT: Train 2006-2020 / Test 2021-2026
2. BASE RATE per ticker × signal (edge vs noise)
3. DRAWDOWN TIMING (corrected: max_down_pct, bars_to_max_down)
4. FEATURE INDEPENDENCE (correlation matrix)
5. RE-AUDIT v8 discoveries with Wilson CI + volume enrichment
6. CROSS-TICKER CONSISTENCY (does the pattern survive across tickers?)
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

def p(t): print(f"\n{'='*80}\n  {t}\n{'='*80}")
def sp(t): print(f"\n  ── {t} ──")


def wilson_ci(successes, n, z=1.96):
    if n == 0: return 0.0, 0.0, 0.0
    phat = successes / n
    denom = 1 + z**2 / n
    center = phat + z**2 / (2*n)
    spread = z * np.sqrt((phat*(1-phat) + z**2/(4*n)) / n)
    lo = (center - spread) / denom
    hi = (center + spread) / denom
    return lo, hi, phat


def load_labels() -> pd.DataFrame:
    pg_url = os.environ.get("POSTGRES_URL", "")
    conn = psycopg2.connect(pg_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM engine.entry_forensic_labels")
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

    subset = entry_df[
        (entry_df["ticker"] == ticker) & (entry_df["signal_direction"] == 1)
    ].copy()
    if len(subset) < 20:
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
        rec["bar_range_ratio"] = bar_range / atr14[bar_idx] if atr14[bar_idx] > 0 else 1.0
        rec["bar_direction"] = 1 if close[bar_idx] >= open_arr[bar_idx] else -1
        enriched.append(rec)

    return pd.DataFrame(enriched) if enriched else pd.DataFrame()


# ═══════════════════════════════════════════════════════════
# PART 1: BASE RATES — Without this, nothing has meaning
# ═══════════════════════════════════════════════════════════

def compute_base_rates(df: pd.DataFrame):
    p("PART 1: BASE RATES (the denominator of edge)")
    longs = df[df["signal_direction"] == 1]

    print(f"\n  {'Ticker':<8s} {'Signal':<25s} {'N':>6s} {'WR':>8s} {'CI_lo':>7s} {'CI_hi':>7s}")
    print(f"  {'─'*70}")

    base_rates = {}
    for ticker in sorted(longs["ticker"].unique()):
        for signal in sorted(longs[longs["ticker"]==ticker]["signal_name"].unique()):
            mask = (longs["ticker"]==ticker) & (longs["signal_name"]==signal)
            sub = longs[mask]
            n = len(sub)
            wins = sub["is_win"].sum()
            lo, hi, wr = wilson_ci(wins, n)
            print(f"  {ticker:<8s} {signal:<25s} {n:>6d} {wr*100:>7.1f}% [{lo*100:.1f}%, {hi*100:.1f}%]")
            base_rates[(ticker, signal)] = wr
        print()

    # Overall per ticker
    print(f"\n  {'Ticker':<8s} {'ALL SIGNALS':<25s} {'N':>6s} {'WR':>8s}")
    print(f"  {'─'*50}")
    for ticker in sorted(longs["ticker"].unique()):
        sub = longs[longs["ticker"]==ticker]
        n = len(sub)
        wr = sub["is_win"].mean()
        base_rates[(ticker, "ALL")] = wr
        print(f"  {ticker:<8s} {'ALL':<25s} {n:>6d} {wr*100:>7.1f}%")

    return base_rates


# ═══════════════════════════════════════════════════════════
# PART 2: OUT-OF-SAMPLE SPLIT
# ═══════════════════════════════════════════════════════════

def oos_validation(df: pd.DataFrame, base_rates: dict):
    p("PART 2: OUT-OF-SAMPLE VALIDATION (Train ≤2020 / Test 2021+)")
    longs = df[df["signal_direction"] == 1]
    train = longs[longs["year"] <= 2020]
    test = longs[longs["year"] >= 2021]

    print(f"\n  Train set: {len(train)} samples ({train['year'].min()}-{train['year'].max()})")
    print(f"  Test set:  {len(test)} samples ({test['year'].min()}-{test['year'].max()})")

    # Test the key rules in both splits
    rules = [
        ("SPY Fear≥ANX + σ<-1", lambda d: (d["ticker"]=="SPY") & (d["snap_fear_level"]>=3) & (d["snap_sigma_wave"]<-1)),
        ("SPY σ<-1.5", lambda d: (d["ticker"]=="SPY") & (d["snap_sigma_wave"]<-1.5)),
        ("AAPL σ<-1.5", lambda d: (d["ticker"]=="AAPL") & (d["snap_sigma_wave"]<-1.5)),
        ("COST Fear≥ANX", lambda d: (d["ticker"]=="COST") & (d["snap_fear_level"]>=3)),
        ("QQQ σ<-1", lambda d: (d["ticker"]=="QQQ") & (d["snap_sigma_wave"]<-1)),
        ("SPY tide_slope>0 + σ<-1", lambda d: (d["ticker"]=="SPY") & (d["snap_tide_slope"]>0.01) & (d["snap_sigma_wave"]<-1)),
        ("AAPL tide_slope>0 + σ<-2", lambda d: (d["ticker"]=="AAPL") & (d["snap_tide_slope"]>0.01) & (d["snap_sigma_wave"]<-2)),
        ("COST tide_slope>0", lambda d: (d["ticker"]=="COST") & (d["snap_tide_slope"]>0.01)),
        ("SPY KV<-0.1 + σ<-0.5", lambda d: (d["ticker"]=="SPY") & (d["snap_kalman_velocity"]<-0.1) & (d["snap_sigma_wave"]<-0.5)),
        ("AAPL Fear≥FEAR + σ<-1", lambda d: (d["ticker"]=="AAPL") & (d["snap_fear_level"]>=2) & (d["snap_sigma_wave"]<-1)),
    ]

    print(f"\n  {'Rule':<35s} │ {'Train N':>7s} {'Train WR':>9s} │ {'Test N':>6s} {'Test WR':>9s} │ {'Δ':>6s} {'Verdict':>10s}")
    print(f"  {'─'*100}")

    for name, rule_fn in rules:
        train_mask = rule_fn(train)
        test_mask = rule_fn(test)
        train_sub = train[train_mask]
        test_sub = test[test_mask]

        tn, tw = len(train_sub), train_sub["is_win"].mean() if len(train_sub) > 0 else 0
        tsn, tsw = len(test_sub), test_sub["is_win"].mean() if len(test_sub) > 0 else 0

        delta = (tsw - tw) * 100 if tn > 0 and tsn > 0 else float("nan")
        if tsn < 3:
            verdict = "⚠ LOW N"
        elif tsw >= tw - 0.05:
            verdict = "✅ HOLDS"
        elif tsw >= tw - 0.15:
            verdict = "⚠ DECAY"
        else:
            verdict = "🚨 BROKEN"

        print(f"  {name:<35s} │ {tn:>7d} {tw*100:>8.1f}% │ {tsn:>6d} {tsw*100:>8.1f}% │ {delta:>+5.1f}% {verdict:>10s}")


# ═══════════════════════════════════════════════════════════
# PART 3: DRAWDOWN TIMING — Corrected
# ═══════════════════════════════════════════════════════════

def drawdown_timing(df: pd.DataFrame):
    p("PART 3: DRAWDOWN TIMING — Do wins suffer pain first?")
    longs = df[df["signal_direction"] == 1]

    print(f"\n  {'Ticker':<8s} {'Signal':<22s} │ {'WR':>6s} │ {'Win DD10':>8s} {'Win ↑10':>7s} {'DD first?':>10s} │ {'Loss DD10':>8s}")
    print(f"  {'─'*95}")

    for ticker in ["COST", "SPY", "AAPL", "QQQ"]:
        for signal in longs[longs["ticker"]==ticker]["signal_name"].unique():
            sub = longs[(longs["ticker"]==ticker) & (longs["signal_name"]==signal)]
            if len(sub) < 10: continue

            wins = sub[sub["is_win"]==1]
            losses = sub[sub["is_win"]==0]
            wr = sub["is_win"].mean()

            win_dd = wins["h10_max_down_pct"].mean() if len(wins)>0 else 0
            win_up = wins["h10_max_up_pct"].mean() if len(wins)>0 else 0
            loss_dd = losses["h10_max_down_pct"].mean() if len(losses)>0 else 0

            # Timing: does the drawdown happen BEFORE the upside?
            win_bars_down = wins["h10_bars_to_max_down"].mean() if len(wins)>0 else 0
            win_bars_up = wins["h10_bars_to_max_up"].mean() if len(wins)>0 else 0
            dd_first = "⚠ DD FIRST" if win_bars_down < win_bars_up and win_dd < -2 else "✅ UP FIRST"

            print(f"  {ticker:<8s} {signal:<22s} │ {wr*100:>5.1f}% │ {win_dd:>7.2f}% {win_up:>6.2f}% {dd_first:>10s} │ {loss_dd:>7.2f}%")

    # Specific patterns: what about our extreme σ entries?
    sp("DRAWDOWN AT σ EXTREMES (the pain before the gain)")
    for ticker in ["COST", "SPY", "AAPL", "QQQ"]:
        sub = longs[(longs["ticker"]==ticker) & (longs["snap_sigma_wave"] < -1.5)]
        wins = sub[sub["is_win"]==1]
        if len(wins) < 5: continue

        dd = wins["h10_max_down_pct"].mean()
        up = wins["h10_max_up_pct"].mean()
        bars_dd = wins["h10_bars_to_max_down"].mean()
        bars_up = wins["h10_bars_to_max_up"].mean()
        # h20 for longer view
        dd20 = wins["h20_max_down_pct"].mean()
        up20 = wins["h20_max_up_pct"].mean()
        bars_dd20 = wins["h20_bars_to_max_down"].mean()
        bars_up20 = wins["h20_bars_to_max_up"].mean()

        print(f"\n    {ticker} σ<-1.5 WINS (N={len(wins)}):")
        print(f"      h10: DD={dd:+.2f}% (bar {bars_dd:.0f}) → UP={up:+.2f}% (bar {bars_up:.0f})")
        print(f"      h20: DD={dd20:+.2f}% (bar {bars_dd20:.0f}) → UP={up20:+.2f}% (bar {bars_up20:.0f})")
        marker = "⚠ SIGNAL LATE" if bars_dd < bars_up and dd < -3 else "✅ TIMING OK"
        print(f"      Verdict: {marker}")


# ═══════════════════════════════════════════════════════════
# PART 4: FEATURE INDEPENDENCE — Correlation matrix
# ═══════════════════════════════════════════════════════════

def feature_independence(df: pd.DataFrame):
    p("PART 4: FEATURE INDEPENDENCE — Are we double-counting?")
    longs = df[df["signal_direction"] == 1]

    features = [
        "snap_sigma_wave", "snap_sigma_tide", "snap_fear_level",
        "snap_tide_slope", "snap_kalman_velocity", "snap_rvol",
        "snap_wave_slope", "snap_slope_conjugation", "snap_tide_accel",
        "snap_vol_up_down_ratio",
    ]
    available = [f for f in features if f in longs.columns]
    feat_df = longs[available].apply(pd.to_numeric, errors="coerce")

    corr = feat_df.corr()
    print(f"\n  CORRELATION MATRIX (|r| > 0.3 highlighted):")
    print(f"\n  {'':>20s}", end="")
    short_names = [f.replace("snap_", "")[:10] for f in available]
    for sn in short_names:
        print(f" {sn:>10s}", end="")
    print()

    for i, f1 in enumerate(available):
        sn1 = f1.replace("snap_", "")[:10]
        print(f"  {sn1:>20s}", end="")
        for j, f2 in enumerate(available):
            r = corr.loc[f1, f2]
            marker = "★" if abs(r) > 0.5 and i != j else "·" if abs(r) > 0.3 and i != j else " "
            print(f" {r:>+8.2f}{marker}", end=" ")
        print()

    # Specifically: are fear_level and sigma_wave correlated?
    sp("KEY REDUNDANCY CHECKS")
    pairs = [
        ("snap_fear_level", "snap_sigma_wave"),
        ("snap_fear_level", "snap_kalman_velocity"),
        ("snap_sigma_wave", "snap_kalman_velocity"),
        ("snap_tide_slope", "snap_tide_accel"),
        ("snap_wave_slope", "snap_slope_conjugation"),
        ("snap_rvol", "snap_vol_up_down_ratio"),
    ]
    for f1, f2 in pairs:
        if f1 not in feat_df.columns or f2 not in feat_df.columns: continue
        valid = feat_df[[f1, f2]].dropna()
        r, pv = stats.pearsonr(valid[f1], valid[f2])
        name1 = f1.replace("snap_", "")
        name2 = f2.replace("snap_", "")
        status = "🚨 REDUNDANT" if abs(r) > 0.5 else "⚠ PARTIAL" if abs(r) > 0.3 else "✅ INDEPENDENT"
        print(f"    {name1:>22s} × {name2:<22s} r={r:+.3f}  p={pv:.4f}  {status}")


# ═══════════════════════════════════════════════════════════
# PART 5: RE-AUDIT V8 DISCOVERIES WITH VOLUME ENRICHMENT
# ═══════════════════════════════════════════════════════════

def reaudit_v8(all_enriched: dict, base_rates: dict):
    p("PART 5: RE-AUDIT V8 DISCOVERIES (Volume-enriched, Wilson CI)")

    v8_rules = {
        # ticker: [(name, mask_fn, base_key)]
        "AAPL": [
            ("Low CV + σ<-1.5", lambda d: (d["vol_cv20"] <= d["vol_cv20"].quantile(0.33)) & (d["snap_sigma_wave"] < -1.5)),
            ("Low CV + σ>+0.5", lambda d: (d["vol_cv20"] <= d["vol_cv20"].quantile(0.33)) & (d["snap_sigma_wave"] > 0.5)),
            ("Drought≥6 (DEATH)", lambda d: d["vol_dryness"] >= 6),
            ("Drought + σ<-1 (floor)", lambda d: (d["vol_dryness"] >= 1) & (d["snap_sigma_wave"] < -1)),
            ("Drought + σ>0 (ceiling)", lambda d: (d["vol_dryness"] >= 1) & (d["snap_sigma_wave"] > 0)),
            ("Drought + FEAR", lambda d: (d["vol_dryness"] >= 1) & (d["snap_fear_level"] == 2)),
            ("Drought + ANXIETY+", lambda d: (d["vol_dryness"] >= 1) & (d["snap_fear_level"] >= 3)),
            ("Balance (quiet+narrow)", lambda d: (d["vol_spike"] < 0.8) & (d["bar_range_ratio"] < 0.8)),
            ("Initiative + σ<-1 + RED", lambda d: (d["vol_spike"]>=1.2) & (d["bar_range_ratio"]>=1.2) & (d["snap_sigma_wave"]<-1) & (d["bar_direction"]<0)),
            ("High vol + σ<-1.5 + GREEN", lambda d: (d["vol_spike"]>=1.2) & (d["snap_sigma_wave"]<-1.5) & (d["bar_direction"]>0)),
        ],
        "COST": [
            ("Low CV all zones", lambda d: d["vol_cv20"] <= d["vol_cv20"].quantile(0.33)),
            ("Mild drought (1-2)", lambda d: (d["vol_dryness"] >= 1) & (d["vol_dryness"] <= 2)),
            ("Drought + σ≥+1 (ceiling)", lambda d: (d["vol_dryness"] >= 1) & (d["snap_sigma_wave"] >= 1)),
            ("Balance + σ≥0", lambda d: (d["vol_spike"] < 0.8) & (d["bar_range_ratio"] < 0.8) & (d["snap_sigma_wave"]>=0)),
            ("Drought → Balance", lambda d: (d["vol_dryness"]>=2) & (d["vol_spike"]<0.8) & (d["bar_range_ratio"]<0.8)),
        ],
        "SPY": [
            ("Med CV (sweet spot)", lambda d: (d["vol_cv20"]>d["vol_cv20"].quantile(0.33)) & (d["vol_cv20"]<=d["vol_cv20"].quantile(0.67))),
            ("Balance (quiet+narrow)", lambda d: (d["vol_spike"]<0.8) & (d["bar_range_ratio"]<0.8)),
            ("Compression BULL", lambda d: (d["vol_spike"]>=1.2) & (d["bar_range_ratio"]<0.8) & (d["snap_tide_slope"]>0.01)),
            ("Drought + KV falling", lambda d: (d["vol_dryness"]>=1) & (d["snap_kalman_velocity"]<-0.1)),
            ("Quiet + BUY FLOW + σ≥0", lambda d: (d["vol_spike"]<0.7) & (d["snap_vol_up_down_ratio"]>1.2) & (d["bar_direction"]>0) & (d["snap_sigma_wave"]>=0)),
            ("Drought → Balance", lambda d: (d["vol_dryness"]>=2) & (d["vol_spike"]<0.8) & (d["bar_range_ratio"]<0.8)),
        ],
        "QQQ": [
            ("Drought≥3 (exhaustion buy)", lambda d: d["vol_dryness"] >= 3),
            ("Drought + σ<-1 (floor)", lambda d: (d["vol_dryness"]>=1) & (d["snap_sigma_wave"]<-1)),
            ("Drought + σ≥+1 (ceiling)", lambda d: (d["vol_dryness"]>=1) & (d["snap_sigma_wave"]>=1)),
            ("Initiative BULL", lambda d: (d["vol_spike"]>=1.2) & (d["bar_range_ratio"]>=1.2) & (d["snap_tide_slope"]>0.01)),
            ("Drought → Balance", lambda d: (d["vol_dryness"]>=2) & (d["vol_spike"]<0.8) & (d["bar_range_ratio"]<0.8)),
        ],
    }

    for ticker, rules in v8_rules.items():
        edf = all_enriched.get(ticker)
        if edf is None or len(edf) < 20:
            print(f"\n  ⚠ {ticker}: insufficient enriched data")
            continue

        sp(f"V8 RE-AUDIT: {ticker}")
        base_wr = base_rates.get((ticker, "ALL"), 0.5)
        print(f"    Base Rate (ALL signals): {base_wr*100:.1f}%")

        # OOS split for volume rules
        train = edf[edf["year"] <= 2020]
        test = edf[edf["year"] >= 2021]

        print(f"\n    {'Rule':<35s} │ {'N':>4s} {'WR':>6s} {'CI95':>15s} {'Edge':>6s} │ {'OOS_N':>5s} {'OOS_WR':>7s} {'Verdict':>10s}")
        print(f"    {'─'*105}")

        for name, rule_fn in rules:
            try:
                for signal in edf["signal_name"].unique():
                    sig_df = edf[edf["signal_name"] == signal]
                    if len(sig_df) < 10: continue

                    mask = rule_fn(sig_df)
                    sub = sig_df[mask]
                    n = len(sub)
                    if n < 3: continue

                    wins = sub["is_win"].sum()
                    lo, hi, wr = wilson_ci(wins, n)
                    edge = (wr - base_wr) * 100

                    # OOS
                    train_sig = train[train["signal_name"]==signal]
                    test_sig = test[test["signal_name"]==signal]
                    oos_n, oos_wr = 0, 0
                    if len(test_sig) > 0:
                        try:
                            oos_mask = rule_fn(test_sig)
                            oos_sub = test_sig[oos_mask]
                            oos_n = len(oos_sub)
                            oos_wr = oos_sub["is_win"].mean() if oos_n > 0 else 0
                        except Exception:
                            pass

                    # Verdict
                    if n < 8:
                        verdict = "⚠ LOW N"
                    elif lo < base_wr:
                        verdict = "⚠ CI WEAK"
                    elif oos_n >= 3 and oos_wr >= wr - 0.10:
                        verdict = "★ ROBUST"
                    elif oos_n >= 3 and oos_wr < wr - 0.10:
                        verdict = "🚨 DECAY"
                    elif oos_n < 3:
                        verdict = "? NO OOS"
                    else:
                        verdict = "✅ OK"

                    sig_short = signal[:8]
                    print(f"    {name:<28s} {sig_short:>6s} │ {n:>4d} {wr*100:>5.1f}% [{lo*100:.0f}%-{hi*100:.0f}%] {edge:>+5.1f}% │ {oos_n:>5d} {oos_wr*100:>6.1f}% {verdict:>10s}")
            except Exception as e:
                print(f"    {name:<35s} │ ERROR: {e}")


# ═══════════════════════════════════════════════════════════
# PART 6: CROSS-TICKER CONSISTENCY
# ═══════════════════════════════════════════════════════════

def cross_ticker_consistency(all_enriched: dict):
    p("PART 6: CROSS-TICKER CONSISTENCY — Does the pattern survive?")

    universal_rules = [
        ("Balance (quiet+narrow)", lambda d: (d["vol_spike"]<0.8) & (d["bar_range_ratio"]<0.8)),
        ("Initiative (loud+wide)", lambda d: (d["vol_spike"]>=1.2) & (d["bar_range_ratio"]>=1.2)),
        ("Low CV + σ<-1", lambda d: (d["vol_cv20"]<=d["vol_cv20"].quantile(0.33)) & (d["snap_sigma_wave"]<-1)),
        ("High CV + σ neutral", lambda d: (d["vol_cv20"]>d["vol_cv20"].quantile(0.67)) & (d["snap_sigma_wave"].between(-0.5, 0.5))),
        ("Drought≥2 + σ<-1", lambda d: (d["vol_dryness"]>=2) & (d["snap_sigma_wave"]<-1)),
        ("Drought≥2 + σ>0", lambda d: (d["vol_dryness"]>=2) & (d["snap_sigma_wave"]>0)),
    ]

    for rule_name, rule_fn in universal_rules:
        print(f"\n  {rule_name}:")
        print(f"    {'Ticker':<8s} {'N':>5s} {'WR':>7s} {'CI95':>15s}")
        consistent_up = 0
        consistent_dn = 0
        total = 0
        for ticker in ["COST", "SPY", "AAPL", "QQQ"]:
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
                marker = "★" if wr > 0.55 else "✗" if wr < 0.45 else " "
                if wr > 0.55: consistent_up += 1
                if wr < 0.45: consistent_dn += 1
                print(f"    {ticker:<8s} {n:>5d} {wr*100:>6.1f}% [{lo*100:.0f}%-{hi*100:.0f}%] {marker}")
            except Exception:
                pass

        if total >= 3:
            if consistent_up >= 3:
                print(f"    → UNIVERSAL POSITIVE PATTERN ({consistent_up}/{total} tickers) ★★")
            elif consistent_dn >= 3:
                print(f"    → UNIVERSAL NEGATIVE PATTERN ({consistent_dn}/{total} tickers) ✗✗")
            elif consistent_up >= 2:
                print(f"    → PARTIAL PATTERN ({consistent_up}/{total} positive)")
            else:
                print(f"    → TICKER-SPECIFIC (no universal consistency)")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v9 REAL — 6-DIMENSION BLIND SPOT AUDIT")
    print("\n  Loading labels...")
    df = load_labels()
    print(f"  → {len(df)} labels, years {df['year'].min()}-{df['year'].max()}")

    # Part 1: Base rates
    base_rates = compute_base_rates(df)

    # Part 2: OOS validation
    oos_validation(df, base_rates)

    # Part 3: Drawdown timing
    drawdown_timing(df)

    # Part 4: Feature independence
    feature_independence(df)

    # Enrich all tickers for parts 5-6
    print("\n  Enriching tickers with volume features...")
    all_enriched = {}
    for ticker in ["COST", "SPY", "AAPL", "QQQ"]:
        print(f"    → {ticker}...", end=" ", flush=True)
        edf = enrich_volume(ticker, df)
        if len(edf) > 0:
            all_enriched[ticker] = edf
            print(f"OK ({len(edf)} samples)")
        else:
            print("SKIP")

    # Part 5: Re-audit v8
    reaudit_v8(all_enriched, base_rates)

    # Part 6: Cross-ticker
    cross_ticker_consistency(all_enriched)

    p("v9 REAL AUDIT COMPLETE")
