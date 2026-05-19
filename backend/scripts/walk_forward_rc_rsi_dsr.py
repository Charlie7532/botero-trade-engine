"""
walk_forward_rc_rsi_dsr.py — DSR Validation for RC + RSI with 20yr Deep History
=================================================================================
Tests whether RegressionChannelAdapter and RSISignalAdapter maintain their alpha
across 20+ years including GFC 2008 and COVID 2020.

Uses the same Walk-Forward framework as walk_forward_dsr_v2.py:
  Train=2yr, Test=6mo, Purge=10d | 32 tickers | 20yr+ history
"""
import sys
import numpy as np
import pandas as pd
from scipy.stats import norm
from pathlib import Path

_root = Path("/root/botero-trade")
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.simulation.infrastructure.signal_adapters import (
    RSISignalAdapter, RegressionChannelAdapter,
)
from backend.scripts.calibrate_passports import QUALITY_TICKERS

import logging
logging.getLogger("backend.modules").setLevel(logging.ERROR)
logging.getLogger("backend.modules.quality_swing").setLevel(logging.ERROR)

EXTENDED_TICKERS = list(QUALITY_TICKERS) + ["SPY", "QQQ"]


def deflated_sharpe_ratio(observed_sr, all_sharpes, T):
    N = len(all_sharpes)
    if N <= 1 or T <= 1:
        return 0.0
    gamma = 0.5772
    sr_std = max(np.std(all_sharpes, ddof=1), 0.01)
    z_inv = norm.ppf(1.0 - 1.0 / N) if N > 1 else 0
    z_inv_e = norm.ppf(1.0 - 1.0 / (N * np.e)) if N > 1 else 0
    e_max_sr = sr_std * ((1 - gamma) * z_inv + gamma * z_inv_e)
    se_sr = np.sqrt(1.0 / T)
    if se_sr <= 0:
        return 0.0
    return norm.cdf((observed_sr - e_max_sr) / se_sr)


def walk_forward(events, min_date, max_date, label, train_days=731, test_days=183, purge_days=10):
    """Run walk-forward on a list of event dicts with 'date' and 'ret_10d'."""
    oos_returns = []
    n_folds = 0
    window_start = min_date

    while True:
        train_end = window_start + pd.Timedelta(days=train_days)
        test_start = train_end + pd.Timedelta(days=purge_days)
        test_end = test_start + pd.Timedelta(days=test_days)

        if test_end > max_date:
            break

        train_events = [e for e in events if window_start <= e["date"] < train_end]
        test_events = [e for e in events if test_start <= e["date"] < test_end]

        if len(train_events) >= 3 and len(test_events) >= 1:
            for e in test_events:
                oos_returns.append(e["ret_10d"])
            n_folds += 1

        window_start += pd.Timedelta(days=test_days)

    return oos_returns, n_folds


def grade_result(wr, n_oos):
    if wr >= 70 and n_oos >= 30:
        return "[VALIDATED] A"
    elif wr >= 60 and n_oos >= 30:
        return "[VALIDATED] B"
    elif wr >= 55 and n_oos >= 20:
        return "[VALIDATED] C"
    elif wr >= 50 and n_oos >= 10:
        return "[HYPOTHESIS] D"
    elif wr < 50:
        return "REJECT"
    else:
        return "[HYPOTHESIS] D"


def main():
    store = TimescaleDataStore()

    print("=" * 120)
    print(f"{'WALK-FORWARD DSR — RC + RSI WITH 20yr DEEP HISTORY':^120}")
    print(f"{'Train=2yr, Test=6mo, Purge=10d | 32 tickers | GFC+COVID+2022':^120}")
    print("=" * 120)

    # ── Phase 1: Generate signals for all tickers ──
    print("\n  Phase 1: Generating RC + RSI signals for all tickers...")

    rc_adapter = RegressionChannelAdapter()
    rsi_adapter = RSISignalAdapter()

    rc_events = []
    rsi_events = []

    for ti, ticker in enumerate(EXTENDED_TICKERS):
        print(f"    [{ti+1}/{len(EXTENDED_TICKERS)}] {ticker}...", flush=True)
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or ohlc.empty or len(ohlc) < 250:
            continue

        closes = ohlc["close"].values
        opens = ohlc["open"].values
        highs = ohlc["high"].values
        lows = ohlc["low"].values

        # Generate RC signals
        try:
            rc_df = rc_adapter.generate(ohlc)
            rc_signals = rc_df["signal"].values
            rc_conf = rc_df["confidence"].values if "confidence" in rc_df.columns else np.ones(len(rc_df))

            for i in range(200, len(ohlc) - 11):
                if rc_signals[i] == 0:
                    continue

                exec_price = opens[i+1] + (highs[i+1] - lows[i+1]) * 0.10
                if exec_price <= 0:
                    continue
                ret_10d = (closes[min(i+10, len(closes)-1)] - exec_price) / exec_price * 100

                # Determine regime
                from backend.modules.simulation.infrastructure.signal_adapters import RSISignalAdapter as _RSI
                price_window = closes[:i+1]
                slope = _RSI._linreg_slope(price_window, 200)
                if slope > 0.01:
                    regime = "BULL"
                elif slope < -0.01:
                    regime = "BEAR"
                else:
                    regime = "FLAT"

                rc_events.append({
                    "date": ohlc.index[i],
                    "ticker": ticker,
                    "ret_10d": ret_10d,
                    "signal": int(rc_signals[i]),
                    "confidence": float(rc_conf[i]) if i < len(rc_conf) else 0.0,
                    "regime": regime,
                })
        except Exception as e:
            print(f"      RC error for {ticker}: {e}")

        # Generate RSI signals
        try:
            rsi_df = rsi_adapter.generate(ohlc)
            rsi_signals = rsi_df["signal"].values
            rsi_conf = rsi_df["confidence"].values if "confidence" in rsi_df.columns else np.ones(len(rsi_df))

            for i in range(200, len(ohlc) - 11):
                if rsi_signals[i] != 1:
                    continue

                exec_price = opens[i+1] + (highs[i+1] - lows[i+1]) * 0.10
                if exec_price <= 0:
                    continue
                ret_10d = (closes[min(i+10, len(closes)-1)] - exec_price) / exec_price * 100

                price_window = closes[:i+1]
                slope_long = _RSI._linreg_slope(price_window, 120)
                if slope_long > 0.02:
                    regime = "BULL"
                elif slope_long < -0.02:
                    regime = "BEAR"
                else:
                    regime = "FLAT"

                rsi_events.append({
                    "date": ohlc.index[i],
                    "ticker": ticker,
                    "ret_10d": ret_10d,
                    "confidence": float(rsi_conf[i]) if i < len(rsi_conf) else 0.0,
                    "regime": regime,
                })
        except Exception as e:
            print(f"      RSI error for {ticker}: {e}")

    store.close()

    # Sort by date
    rc_events.sort(key=lambda x: x["date"])
    rsi_events.sort(key=lambda x: x["date"])

    all_dates = [e["date"] for e in rc_events + rsi_events]
    if not all_dates:
        print("  No events found!")
        return
    min_date = min(all_dates)
    max_date = max(all_dates)
    total_years = (max_date - min_date).days / 365.25

    print(f"\n  RC events: {len(rc_events):,} | RSI events: {len(rsi_events):,}")
    print(f"  Range: {min_date.strftime('%Y-%m-%d')} → {max_date.strftime('%Y-%m-%d')} ({total_years:.1f}yr)")

    # ── Phase 2: Walk-Forward DSR ──
    print(f"\n  Phase 2: Walk-Forward DSR Results")
    print(f"\n  {'Setup':<50} | {'N_OOS':>5} | {'WR_OOS':>6} | {'Sharpe':>7} | {'Folds':>5} | Grade")
    print(f"  {'-'*50}-+-{'-'*5}-+-{'-'*6}-+-{'-'*7}-+-{'-'*5}-+-{'-'*15}")

    all_sharpes = []

    # ── RC Setups ──
    rc_setups = [
        ("RC_ALL (entries)",       [e for e in rc_events if e["signal"] == 1]),
        ("RC_BULL",                [e for e in rc_events if e["signal"] == 1 and e["regime"] == "BULL"]),
        ("RC_BEAR",                [e for e in rc_events if e["signal"] == 1 and e["regime"] == "BEAR"]),
        ("RC_FLAT",                [e for e in rc_events if e["signal"] == 1 and e["regime"] == "FLAT"]),
        ("RC_HIGH_CONF (>0.5)",    [e for e in rc_events if e["signal"] == 1 and e["confidence"] > 0.5]),
        ("RC_TRIM (signal=-1)",    [e for e in rc_events if e["signal"] == -1]),
    ]

    for label, subset in rc_setups:
        if len(subset) < 5:
            print(f"  {label:<50} | {'N/A':>5} | {'N/A':>6} | {'N/A':>7} | {'N/A':>5} | SKIP (N={len(subset)})")
            continue

        oos_ret, n_folds = walk_forward(subset, min_date, max_date, label)
        if len(oos_ret) < 5:
            print(f"  {label:<50} | {len(oos_ret):>5} | {'N/A':>6} | {'N/A':>7} | {n_folds:>5} | INSUFFICIENT")
            continue

        oos = np.array(oos_ret)
        wr = (oos > 0).mean() * 100
        sharpe = oos.mean() / max(oos.std(), 0.01)
        all_sharpes.append(sharpe)
        g = grade_result(wr, len(oos))

        # For TRIM: invert logic (we want WR < 50% to confirm anti-signal)
        if "TRIM" in label:
            g = "ANTI-CONFIRMED" if wr < 50 else "ANTI-FAILED"

        print(f"  {label:<50} | {len(oos):>5} | {wr:>5.1f}% | {sharpe:>+6.3f} | {n_folds:>5} | {g}")

    print()

    # ── RSI Setups ──
    rsi_setups = [
        ("RSI_ALL",                [e for e in rsi_events]),
        ("RSI_BULL",               [e for e in rsi_events if e["regime"] == "BULL"]),
        ("RSI_BEAR",               [e for e in rsi_events if e["regime"] == "BEAR"]),
        ("RSI_FLAT",               [e for e in rsi_events if e["regime"] == "FLAT"]),
        ("RSI_HIGH_CONF (>0.5)",   [e for e in rsi_events if e["confidence"] > 0.5]),
        ("RSI_HIGH_CONF (>0.7)",   [e for e in rsi_events if e["confidence"] > 0.7]),
    ]

    for label, subset in rsi_setups:
        if len(subset) < 5:
            print(f"  {label:<50} | {'N/A':>5} | {'N/A':>6} | {'N/A':>7} | {'N/A':>5} | SKIP (N={len(subset)})")
            continue

        oos_ret, n_folds = walk_forward(subset, min_date, max_date, label)
        if len(oos_ret) < 5:
            print(f"  {label:<50} | {len(oos_ret):>5} | {'N/A':>6} | {'N/A':>7} | {n_folds:>5} | INSUFFICIENT")
            continue

        oos = np.array(oos_ret)
        wr = (oos > 0).mean() * 100
        sharpe = oos.mean() / max(oos.std(), 0.01)
        all_sharpes.append(sharpe)
        g = grade_result(wr, len(oos))
        print(f"  {label:<50} | {len(oos):>5} | {wr:>5.1f}% | {sharpe:>+6.3f} | {n_folds:>5} | {g}")

    # ── Phase 3: Per-ticker breakdown for top signals ──
    print(f"\n  Phase 3: Per-Ticker Breakdown (RC_ALL)")
    print(f"  {'Ticker':<8} | {'N':>4} | {'WR':>6} | {'Avg':>8}")
    print(f"  {'-'*8}-+-{'-'*4}-+-{'-'*6}-+-{'-'*8}")

    rc_entries = [e for e in rc_events if e["signal"] == 1]
    ticker_stats = {}
    for e in rc_entries:
        ticker_stats.setdefault(e["ticker"], []).append(e["ret_10d"])

    for ticker in sorted(ticker_stats.keys(), key=lambda t: -(np.array(ticker_stats[t]) > 0).mean()):
        rets = np.array(ticker_stats[ticker])
        if len(rets) < 5:
            continue
        wr = (rets > 0).mean() * 100
        print(f"  {ticker:<8} | {len(rets):>4} | {wr:>5.1f}% | {rets.mean():>+7.2f}%")

    print(f"\n  Phase 3: Per-Ticker Breakdown (RSI_ALL)")
    print(f"  {'Ticker':<8} | {'N':>4} | {'WR':>6} | {'Avg':>8}")
    print(f"  {'-'*8}-+-{'-'*4}-+-{'-'*6}-+-{'-'*8}")

    ticker_stats_rsi = {}
    for e in rsi_events:
        ticker_stats_rsi.setdefault(e["ticker"], []).append(e["ret_10d"])

    for ticker in sorted(ticker_stats_rsi.keys(), key=lambda t: -(np.array(ticker_stats_rsi[t]) > 0).mean()):
        rets = np.array(ticker_stats_rsi[ticker])
        if len(rets) < 5:
            continue
        wr = (rets > 0).mean() * 100
        print(f"  {ticker:<8} | {len(rets):>4} | {wr:>5.1f}% | {rets.mean():>+7.2f}%")

    # Save events
    log_dir = _root / "backend/scripts/logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rc_events).to_csv(log_dir / "rc_dsr_events.csv", index=False)
    pd.DataFrame(rsi_events).to_csv(log_dir / "rsi_dsr_events.csv", index=False)
    print(f"\n  Events saved to: {log_dir}")


if __name__ == "__main__":
    main()
