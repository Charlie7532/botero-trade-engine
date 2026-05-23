#!/usr/bin/env python3
"""
Forensic Lab v18 — THESIS EXIT + META-LABEL FILTER
======================================================
Two discoveries from v17:
  1. The stop kills 56.6% of trades that would have won
  2. spread_tide_current PREDICTS which entries survive (p=0.0001)

This lab tests:
  A) THESIS-BASED EXITS using ChannelSnapshot (not ATR stops)
     - Exit when sigma_tide returns to fair value (thesis complete)
     - Exit when regime changes (thesis dead)
     - Exit when spread resolves (compression released)
     
  B) META-LABEL FILTER: only enter when DNA says "survivor"
     - spread_tide_current < -1.0
     - sigma_current between -1.5 and -2.5 (not too extreme)
     - vol_up_down_ratio < 0.75 (sellers exhausted)

No ATR stops. No arbitrary barriers. Channel in → Channel out.
"""

import os, sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import pandas as pd
import numpy as np
from scipy import stats

from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def p(t): print(f"\n{'='*95}\n  {t}\n{'='*95}")
def sp(t): print(f"\n  ── {t} ──")

TICKERS = ["AMZN", "MCD", "MRK", "COST", "JPM", "XOM", "MSFT", "AAPL", "SPY"]

MAX_HOLD_BARS = 120  # Máximo 120 bars de paciencia

# ── Exit conditions using ChannelSnapshot ──
def check_thesis_exit(entry_snap, current_snap, bars_held):
    """
    Exit based on THESIS — the reason we entered has changed.
    Returns (exit_reason, None) or (None, None) to hold.
    """
    # 1. THESIS COMPLETE: sigma normalized (back to fair value)
    #    We entered because sigma_tide was < -2.0. If it returns to > 0,
    #    the trade worked. Take the profit.
    if current_snap.sigma_tide > 0:
        return "THESIS_COMPLETE"

    # 2. REGIME CHANGE: the macro environment changed
    #    If we entered in BULL and it flipped to BEAR (or vice versa)
    if entry_snap.regime != current_snap.regime:
        # But only if the new regime is against us
        if current_snap.regime == "BEAR" and entry_snap.regime == "BULL":
            return "REGIME_DETERIORATED"

    # 3. SPREAD RESOLVED: the tide↔current compression released
    #    We entered when spread was very negative (tide > current).
    #    If spread goes positive, the divergence resolved.
    if current_snap.spread_tide_current > 0.5 and entry_snap.spread_tide_current < -0.5:
        return "SPREAD_RESOLVED"

    # 4. SIGMA WAVE FLIP: short-term momentum confirmed profit
    #    Wave sigma went from very negative to positive = momentum reversal complete
    if current_snap.sigma_wave > 1.0 and entry_snap.sigma_wave < -1.0:
        return "WAVE_NORMALIZED"

    # 5. TIME LIMIT: patience exhausted
    if bars_held >= MAX_HOLD_BARS:
        return "TIME_EXIT"

    return None  # HOLD — thesis alive


def run_thesis_backtest(ticker, ohlc, use_meta_filter=False):
    """
    Run backtest with thesis-based exits.
    Optionally apply META-LABEL filter from v17 DNA analysis.
    """
    close = ohlc["close"].values.astype(float)
    high = ohlc["high"].values.astype(float)
    low = ohlc["low"].values.astype(float)
    volume = ohlc["volume"].values.astype(float)

    trades = []
    in_trade = False
    entry_snap = None
    entry_idx = None
    entry_price = None

    for idx in range(250, len(ohlc)):
        snap = compute_channel_snapshot(close, high, low, volume, idx)
        if snap is None:
            continue

        if in_trade:
            # Check thesis exit
            bars_held = idx - entry_idx
            exit_reason = check_thesis_exit(entry_snap, snap, bars_held)

            if exit_reason:
                exit_price = close[idx]
                ret_pct = (exit_price / entry_price - 1) * 100

                trades.append({
                    "ticker": ticker,
                    "entry_time": ohlc.index[entry_idx],
                    "exit_time": ohlc.index[idx],
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "return_pct": ret_pct,
                    "bars_held": bars_held,
                    "exit_reason": exit_reason,
                    # Entry context
                    "entry_sigma_tide": entry_snap.sigma_tide,
                    "entry_sigma_current": entry_snap.sigma_current,
                    "entry_sigma_wave": entry_snap.sigma_wave,
                    "entry_spread_tc": entry_snap.spread_tide_current,
                    "entry_vwap_sigma_wave": entry_snap.vwap_sigma_wave,
                    "entry_current_slope": entry_snap.current_slope,
                    "entry_vol_ratio": entry_snap.vol_up_down_ratio,
                    "entry_regime": entry_snap.regime,
                    "entry_fear": entry_snap.fear_label,
                    # Exit context
                    "exit_sigma_tide": snap.sigma_tide,
                    "exit_sigma_current": snap.sigma_current,
                    "exit_sigma_wave": snap.sigma_wave,
                    "exit_spread_tc": snap.spread_tide_current,
                    "exit_regime": snap.regime,
                    # Deltas (entry → exit)
                    "delta_sigma_tide": snap.sigma_tide - entry_snap.sigma_tide,
                    "delta_sigma_current": snap.sigma_current - entry_snap.sigma_current,
                    "delta_spread_tc": snap.spread_tide_current - entry_snap.spread_tide_current,
                })

                in_trade = False
                continue

        else:
            # Check entry: ALL_EXTREME condition
            if snap.sigma_tide < -2.0 and snap.vwap_sigma_wave < -1.5 and snap.below_all_vwaps:
                # META-LABEL FILTER: only enter if DNA says "survivor"
                if use_meta_filter:
                    # From v17 DNA analysis (p < 0.01):
                    # 1. spread_tide_current must be large negative (winners avg: -1.195)
                    if snap.spread_tide_current > -0.8:
                        continue  # Skip: spread too small = both trends falling
                    # 2. sigma_current should not be TOO extreme (winners: -1.744)
                    if snap.sigma_current < -3.0:
                        continue  # Skip: too extreme = selling not finished
                    # 3. vol_up_down_ratio should be low (winners: 0.709)
                    if snap.vol_up_down_ratio > 0.85:
                        continue  # Skip: too much buying = trapped buyers

                in_trade = True
                entry_snap = snap
                entry_idx = idx
                # Simulate entry on NEXT bar open (entry_delay = 1)
                if idx + 1 < len(ohlc):
                    entry_price = ohlc["open"].values[idx + 1]
                    entry_idx = idx + 1
                else:
                    in_trade = False

    return pd.DataFrame(trades) if trades else None


# ═══════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════

def analyze_results(df, label):
    sp(f"RESULTS: {label}")
    n = len(df)
    wins = (df["return_pct"] > 0).sum()
    losses = (df["return_pct"] <= 0).sum()
    wr = wins / n * 100
    avg_ret = df["return_pct"].mean()
    med_ret = df["return_pct"].median()
    total_ret = df["return_pct"].sum()
    avg_bars = df["bars_held"].mean()

    gross_profit = df[df["return_pct"] > 0]["return_pct"].sum()
    gross_loss = abs(df[df["return_pct"] < 0]["return_pct"].sum())
    pf = gross_profit / max(gross_loss, 0.001)

    # Sharpe (annualized from trade returns)
    ret_std = df["return_pct"].std(ddof=1) if n > 1 else 1
    sharpe = (avg_ret / max(ret_std, 0.001)) * np.sqrt(252 / max(avg_bars, 1))

    print(f"  Trades: {n}   Wins: {wins}   Losses: {losses}")
    print(f"  WR: {wr:.1f}%   PF: {pf:.2f}   Sharpe: {sharpe:+.3f}")
    print(f"  Avg Return: {avg_ret:+.2f}%   Median: {med_ret:+.2f}%   Total: {total_ret:+.1f}%")
    print(f"  Avg Bars Held: {avg_bars:.0f}")

    # Exit reason breakdown
    sp("EXIT REASONS")
    for reason in df["exit_reason"].unique():
        sub = df[df["exit_reason"] == reason]
        sub_wr = (sub["return_pct"] > 0).mean() * 100
        sub_ret = sub["return_pct"].mean()
        sub_bars = sub["bars_held"].mean()
        print(f"    {reason:<22s}: N={len(sub):>4d}, WR={sub_wr:>5.1f}%, Ret={sub_ret:>+6.2f}%, Bars={sub_bars:>4.0f}")

    # Per-ticker breakdown
    sp("PER-TICKER")
    print(f"    {'Ticker':<8s} │ {'N':>4s} │ {'WR':>5s} │ {'PF':>5s} │ {'Avg Ret':>7s} │ {'Sharpe':>7s} │ {'Avg Bars':>8s}")
    print(f"    {'─'*60}")
    for ticker in sorted(df["ticker"].unique()):
        t = df[df["ticker"] == ticker]
        if len(t) < 3:
            continue
        t_wr = (t["return_pct"] > 0).mean() * 100
        t_ret = t["return_pct"].mean()
        t_bars = t["bars_held"].mean()
        t_std = t["return_pct"].std(ddof=1) if len(t) > 1 else 1
        t_sharpe = (t_ret / max(t_std, 0.001)) * np.sqrt(252 / max(t_bars, 1))
        t_gp = t[t["return_pct"] > 0]["return_pct"].sum()
        t_gl = abs(t[t["return_pct"] < 0]["return_pct"].sum())
        t_pf = t_gp / max(t_gl, 0.001)
        print(f"    {ticker:<8s} │ {len(t):>4d} │ {t_wr:>4.1f}% │ {t_pf:>5.2f} │ {t_ret:>+6.2f}% │ {t_sharpe:>+6.3f} │ {t_bars:>7.0f}")

    # Regime breakdown
    sp("PER-REGIME")
    for regime in sorted(df["entry_regime"].dropna().unique()):
        r = df[df["entry_regime"] == regime]
        if len(r) < 3:
            continue
        r_wr = (r["return_pct"] > 0).mean() * 100
        r_ret = r["return_pct"].mean()
        print(f"    {regime:<12s}: WR={r_wr:>5.1f}%, Ret={r_ret:>+6.2f}%, N={len(r)}")

    return {
        "n": n, "wr": wr, "pf": pf, "sharpe": sharpe,
        "avg_ret": avg_ret, "total_ret": total_ret,
    }


def compare_exit_deltas(df):
    """Analyze HOW the snapshot changes from entry to exit for winners vs losers."""
    sp("SNAPSHOT DELTAS: Entry → Exit (Winners vs Losers)")

    wins = df[df["return_pct"] > 0]
    losses = df[df["return_pct"] <= 0]

    if len(wins) < 5 or len(losses) < 5:
        print("  Not enough data")
        return

    deltas = ["delta_sigma_tide", "delta_sigma_current", "delta_spread_tc"]
    exit_fields = ["exit_sigma_tide", "exit_sigma_current", "exit_sigma_wave", "exit_spread_tc"]

    print(f"\n    {'Field':<22s} │ {'Winners':>10s} │ {'Losers':>10s} │ {'Diff':>8s} │ {'p-val':>8s}")
    print(f"    {'─'*65}")

    for field in deltas + exit_fields:
        w = wins[field].dropna()
        l = losses[field].dropna()
        if len(w) < 5 or len(l) < 5:
            continue
        try:
            _, pv = stats.ttest_ind(w, l, equal_var=False)
        except:
            pv = 1.0
        diff = w.mean() - l.mean()
        sig = "★★★" if pv < 0.01 else "★★" if pv < 0.05 else "★" if pv < 0.1 else ""
        print(f"    {field:<22s} │ {w.mean():>+9.3f} │ {l.mean():>+9.3f} │ {diff:>+7.3f} │ {pv:>7.4f} {sig}")


# ═══════════════════════════════════════════════════════════
# WALK-FORWARD VALIDATION
# ═══════════════════════════════════════════════════════════

def walk_forward(all_trades, label):
    sp(f"WALK-FORWARD: {label}")

    df = all_trades.copy()
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)

    periods = [
        ("2006-2012", "2013-2015",
         pd.Timestamp("2013-01-01", tz="UTC"), pd.Timestamp("2015-12-31", tz="UTC")),
        ("2010-2016", "2017-2019",
         pd.Timestamp("2017-01-01", tz="UTC"), pd.Timestamp("2019-12-31", tz="UTC")),
        ("2014-2020", "2021-2023",
         pd.Timestamp("2021-01-01", tz="UTC"), pd.Timestamp("2023-12-31", tz="UTC")),
        ("2016-2022", "2023-2026",
         pd.Timestamp("2023-01-01", tz="UTC"), pd.Timestamp("2026-12-31", tz="UTC")),
    ]

    print(f"\n    {'Period':<16s} │ {'N':>4s} │ {'WR':>5s} │ {'PF':>5s} │ {'Avg Ret':>7s} │ {'Sharpe':>7s}")
    print(f"    {'─'*55}")

    oos_sharpes = []
    for train_label, test_label, test_start, test_end in periods:
        test = df[(df["entry_time"] >= test_start) & (df["entry_time"] <= test_end)]
        if len(test) < 5:
            print(f"    {train_label:<16s} │ {'<5':>4s} │  --- │  --- │    --- │    ---")
            continue
        n = len(test)
        wr = (test["return_pct"] > 0).mean() * 100
        avg_ret = test["return_pct"].mean()
        std_ret = test["return_pct"].std(ddof=1)
        avg_bars = test["bars_held"].mean()
        sharpe = (avg_ret / max(std_ret, 0.001)) * np.sqrt(252 / max(avg_bars, 1))
        gp = test[test["return_pct"] > 0]["return_pct"].sum()
        gl = abs(test[test["return_pct"] < 0]["return_pct"].sum())
        pf = gp / max(gl, 0.001)
        oos_sharpes.append(sharpe)
        mark = "✅" if sharpe > 0.3 else "⚠️" if sharpe > 0 else "❌"
        print(f"    {test_label:<16s} │ {n:>4d} │ {wr:>4.1f}% │ {pf:>5.2f} │ {avg_ret:>+6.2f}% │ {sharpe:>+6.3f}{mark}")

    if oos_sharpes:
        mean_oos = np.mean(oos_sharpes)
        print(f"\n    OOS Mean Sharpe: {mean_oos:+.3f}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v18 — THESIS EXIT + META-LABEL FILTER")
    print("  Channel IN → Channel OUT. No ATR stops.")
    print("  Testing: Raw entries vs DNA-filtered entries")

    store = TimescaleDataStore()

    # ── RUN A: Raw entries, thesis exits ──
    p("RUN A: ALL_EXTREME entries + THESIS exits (no filter, no ATR stop)")
    all_raw = []
    for ticker in TICKERS:
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or len(ohlc) < 300:
            continue
        print(f"  {ticker}...", end=" ", flush=True)
        df = run_thesis_backtest(ticker, ohlc, use_meta_filter=False)
        if df is not None and len(df) > 0:
            all_raw.append(df)
            print(f"{len(df)} trades")
        else:
            print("0 trades")

    if all_raw:
        raw_combined = pd.concat(all_raw, ignore_index=True)
        raw_metrics = analyze_results(raw_combined, "RAW ALL_EXTREME + THESIS EXIT")
        compare_exit_deltas(raw_combined)
        walk_forward(raw_combined, "RAW THESIS")

    # ── RUN B: DNA-filtered entries, thesis exits ──
    p("RUN B: ALL_EXTREME + META-LABEL FILTER + THESIS exits")
    all_filtered = []
    for ticker in TICKERS:
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or len(ohlc) < 300:
            continue
        print(f"  {ticker}...", end=" ", flush=True)
        df = run_thesis_backtest(ticker, ohlc, use_meta_filter=True)
        if df is not None and len(df) > 0:
            all_filtered.append(df)
            print(f"{len(df)} trades")
        else:
            print("0 trades")

    store.close()

    if all_filtered:
        filtered_combined = pd.concat(all_filtered, ignore_index=True)
        filtered_metrics = analyze_results(filtered_combined, "DNA-FILTERED + THESIS EXIT")
        compare_exit_deltas(filtered_combined)
        walk_forward(filtered_combined, "DNA-FILTERED THESIS")

    # ── COMPARISON ──
    if all_raw and all_filtered:
        p("COMPARISON: Raw vs DNA-Filtered")
        print(f"\n    {'Metric':<15s} │ {'Raw':>12s} │ {'Filtered':>12s} │ {'Δ':>10s}")
        print(f"    {'─'*55}")
        for metric in ["n", "wr", "pf", "sharpe", "avg_ret", "total_ret"]:
            r = raw_metrics.get(metric, 0)
            f = filtered_metrics.get(metric, 0)
            fmt = ".1f" if metric in ("wr", "total_ret") else ".2f" if metric in ("pf", "avg_ret") else ".3f" if metric == "sharpe" else "d"
            if metric == "n":
                print(f"    {metric:<15s} │ {r:>12d} │ {f:>12d} │ {f-r:>+10d}")
            else:
                print(f"    {metric:<15s} │ {r:>+12.3f} │ {f:>+12.3f} │ {f-r:>+10.3f}")

    p("v18 — THESIS EXIT + META-LABEL COMPLETE")
    print("  The channel that found the entry, now manages the exit.")
