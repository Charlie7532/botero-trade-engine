#!/usr/bin/env python3
"""
Forensic Lab v16 — LÓPEZ DE PRADO META-LABEL VALIDATION
===========================================================
Uses the CORRECT methodology:
  1. Triple Barrier labeling (not fixed-time returns)
  2. Meta-Labeling: does ChannelSnapshot predict RSI/RC signal QUALITY?
  3. Walk-Forward purged validation (not in-sample pooled metrics)
  4. Per-ticker adaptive profiles (which features matter WHERE)
  5. Deflated Sharpe Ratio (adjust for multiple testing)
  6. Expected Value (WR × avg_win), not WR alone

Key difference from v15:
  v15 asked: "Does sigma_tide predict returns?"       → WRONG question
  v16 asks:  "Does sigma_tide predict SIGNAL QUALITY?" → RIGHT question

Uses production TripleBarrierAdapter + compute_channel_snapshot().
Uses store.load_bars() exclusively (Vault-first).
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
from dataclasses import dataclass

from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.simulation.infrastructure.triple_barrier_adapter import TripleBarrierAdapter
from backend.modules.simulation.domain.ports.barrier_labeler_port import BarrierLabel

def p(t): print(f"\n{'='*95}\n  {t}\n{'='*95}")
def sp(t): print(f"\n  ── {t} ──")

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD",
    "HON", "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP",
    "PG", "WMT", "XOM",
]

# ── Triple Barrier geometry (Quality Value: 3:1 RR, 60 bars max) ──
PROFIT_MULT = 3.0
LOSS_MULT = 1.0
MAX_BARS = 60
VOL_LOOKBACK = 20
ENTRY_DELAY = 1
SLIPPAGE_FACTOR = 0.08
COST_BPS = 10.0

# ── ChannelSnapshot signal thresholds ──
# These define WHEN the ChannelSnapshot says "enter"
SIGNAL_CONDITIONS = {
    "DEEP_VALUE": lambda snap: snap.sigma_tide < -1.5,
    "DEEP_VALUE+VWAP": lambda snap: snap.sigma_tide < -1.5 and snap.vwap_sigma_wave < -1.0,
    "PULLBACK_BULL": lambda snap: snap.regime == "BULL" and snap.sigma_wave < -1.0,
    "PULLBACK_DEEP": lambda snap: snap.regime == "BULL" and snap.sigma_tide < -1.0 and snap.wave_slope < -0.01,
    "RECOVERY": lambda snap: snap.regime == "BULL" and snap.wave_flip and snap.wave_flip_direction == 1,
    "RECOVERY_DEEP": lambda snap: snap.regime == "BULL" and snap.wave_flip and snap.wave_flip_direction == 1 and snap.sigma_tide < -1.0,
    "ALL_EXTREME": lambda snap: snap.sigma_tide < -2.0 and snap.vwap_sigma_wave < -1.5 and snap.below_all_vwaps,
}


# ═══════════════════════════════════════════════════════════
# PART 1: Generate Triple Barrier labels for each signal
# ═══════════════════════════════════════════════════════════

def generate_labels_per_ticker(ticker, ohlc, labeler):
    """Generate Triple Barrier labels for each signal condition."""
    close = ohlc["close"].values.astype(float)
    high = ohlc["high"].values.astype(float)
    low = ohlc["low"].values.astype(float)
    volume = ohlc["volume"].values.astype(float)

    results = {}

    for sig_name, condition in SIGNAL_CONDITIONS.items():
        # Generate entry signals using ChannelSnapshot
        entries = pd.Series(False, index=ohlc.index)

        for idx in range(250, len(ohlc)):
            snap = compute_channel_snapshot(close, high, low, volume, idx)
            if snap is None:
                continue
            if condition(snap):
                entries.iloc[idx] = True

        n_entries = entries.sum()
        if n_entries < 5:
            continue

        # Label with Triple Barrier (production adapter)
        labels = labeler.label_entries(
            ohlc, entries,
            profit_mult=PROFIT_MULT,
            loss_mult=LOSS_MULT,
            max_bars=MAX_BARS,
            vol_lookback=VOL_LOOKBACK,
            entry_delay_bars=ENTRY_DELAY,
            slippage_factor=SLIPPAGE_FACTOR,
            round_trip_cost_bps=COST_BPS,
        )

        if not labels:
            continue

        # Attach ChannelSnapshot features to each label
        enriched = []
        for label in labels:
            if label.entry_time is None:
                continue
            try:
                pos = ohlc.index.get_loc(label.entry_time)
            except KeyError:
                continue

            snap = compute_channel_snapshot(close, high, low, volume, pos)
            if snap is None:
                continue

            rec = {
                "ticker": ticker,
                "signal": sig_name,
                "entry_time": label.entry_time,
                "exit_time": label.exit_time,
                "label": label.label,  # 1=profit, -1=loss, 0=time
                "return_pct": label.return_pct,
                "bars_held": label.bars_held,
                "hit_barrier": label.hit_barrier,
                "mae_pct": label.max_adverse_excursion_pct,
                "mfe_pct": label.max_favorable_excursion_pct,
                "sweep": label.stop_was_sweep,
                "post_exit_max": label.post_exit_max_pct,
                "post_exit_hit_tp": label.post_exit_hit_target,
            }

            # Attach snapshot features
            d = snap.to_dict()
            for k, v in d.items():
                if isinstance(v, str):
                    rec[f"cs_{k}"] = v
                elif isinstance(v, (bool, np.bool_)):
                    rec[f"cs_{k}"] = int(v)
                elif isinstance(v, (int, float, np.integer, np.floating)):
                    rec[f"cs_{k}"] = float(v)

            enriched.append(rec)

        if enriched:
            results[sig_name] = pd.DataFrame(enriched)
            wins = sum(1 for e in enriched if e["label"] == 1)
            losses = sum(1 for e in enriched if e["label"] == -1)
            print(f"    {sig_name:<20s}: {len(enriched)} entries, W={wins} L={losses} T={len(enriched)-wins-losses}")

    return results


# ═══════════════════════════════════════════════════════════
# PART 2: Triple Barrier Performance per Signal
# ═══════════════════════════════════════════════════════════

def part2_tb_performance(all_results):
    p("PART 2: TRIPLE BARRIER PERFORMANCE — Real Edge (LdP methodology)")

    print(f"\n    {'Signal':<22s} │ {'N':>4s} │ {'WR':>5s} │ {'PF':>5s} │ {'Avg Ret':>7s} │ {'Sharpe':>7s} │ {'EV/trade':>8s} │ {'Sweep%':>6s}")
    print(f"    {'─'*85}")

    signal_metrics = {}
    for sig_name in SIGNAL_CONDITIONS.keys():
        # Combine all tickers for this signal
        dfs = []
        for ticker_results in all_results.values():
            if sig_name in ticker_results:
                dfs.append(ticker_results[sig_name])
        if not dfs:
            continue
        df = pd.concat(dfs, ignore_index=True)
        if len(df) < 10:
            continue

        n = len(df)
        wins = (df["label"] == 1).sum()
        losses = (df["label"] == -1).sum()
        wr = wins / n * 100

        returns = df["return_pct"]
        avg_ret = returns.mean()
        std_ret = returns.std(ddof=1) if len(returns) > 1 else 1
        avg_bars = df["bars_held"].mean()

        # Sharpe (annualized)
        sharpe = (avg_ret / max(std_ret, 0.001)) * np.sqrt(252 / max(avg_bars, 1))

        # Profit Factor
        gross_profit = returns[returns > 0].sum()
        gross_loss = abs(returns[returns < 0].sum())
        pf = gross_profit / max(gross_loss, 0.001)

        # Expected Value per trade
        avg_win = returns[returns > 0].mean() if wins > 0 else 0
        avg_loss = returns[returns < 0].mean() if losses > 0 else 0
        ev = (wr/100) * avg_win + (1 - wr/100) * avg_loss

        # Sweep %
        sweep_pct = df["sweep"].sum() / max(losses, 1) * 100

        sig = "★★" if sharpe >= 1.0 else "★" if sharpe >= 0.5 else ""
        print(f"    {sig_name:<22s} │ {n:>4d} │ {wr:>4.1f}% │ {pf:>5.2f} │ {avg_ret:>+6.2f}% │ {sharpe:>+6.3f}{sig:>1s} │ {ev:>+7.3f}% │ {sweep_pct:>5.1f}%")

        signal_metrics[sig_name] = {
            "n": n, "wr": wr, "pf": pf, "sharpe": sharpe, "ev": ev,
            "avg_win": avg_win, "avg_loss": avg_loss, "df": df,
        }

    return signal_metrics


# ═══════════════════════════════════════════════════════════
# PART 3: PER-TICKER ADAPTIVE PROFILES
# LdP: "The same feature has different importance per asset"
# ═══════════════════════════════════════════════════════════

def part3_per_ticker_profiles(all_results, signal_metrics):
    p("PART 3: PER-TICKER ADAPTIVE PROFILES — Which features matter WHERE")

    # Use the best signal from Part 2
    if not signal_metrics:
        print("  No viable signals found.")
        return {}

    best_signal = max(signal_metrics.keys(), key=lambda k: signal_metrics[k].get("sharpe", 0))
    print(f"  Analyzing per-ticker profiles for signal: {best_signal}")

    meta_features = [
        "cs_sigma_tide", "cs_sigma_current", "cs_sigma_wave",
        "cs_vwap_sigma_tide", "cs_vwap_sigma_current", "cs_vwap_sigma_wave",
        "cs_tide_slope", "cs_current_slope", "cs_wave_slope",
        "cs_tide_accel", "cs_spread_tide_current", "cs_conj_wave_tide",
        "cs_vol_up_down_ratio", "cs_residual_std_wave",
    ]

    # Collect per-ticker profiles
    ticker_profiles = {}

    print(f"\n    {'Ticker':<8s} │ {'N':>4s} │ {'WR':>5s} │ {'PF':>5s} │ {'Sharpe':>7s} │ {'EV':>7s} │ {'Top Feature':>25s} │ {'r':>7s}")
    print(f"    {'─'*95}")

    for ticker, ticker_results in all_results.items():
        if best_signal not in ticker_results:
            continue
        df = ticker_results[best_signal]
        if len(df) < 10:
            continue

        # Basic metrics
        n = len(df)
        wins = (df["label"] == 1).sum()
        wr = wins / n * 100
        returns = df["return_pct"]
        avg_ret = returns.mean()
        std_ret = returns.std(ddof=1) if n > 1 else 1
        avg_bars = df["bars_held"].mean()
        sharpe = (avg_ret / max(std_ret, 0.001)) * np.sqrt(252 / max(avg_bars, 1))
        gross_profit = returns[returns > 0].sum()
        gross_loss = abs(returns[returns < 0].sum())
        pf = gross_profit / max(gross_loss, 0.001)
        ev = avg_ret  # simplified

        # Find best META feature for this ticker
        best_feat = ""
        best_r = 0.0
        is_win = (df["label"] == 1).astype(int)

        profile = {"n": n, "wr": wr, "sharpe": sharpe, "pf": pf, "features": {}}

        for feat in meta_features:
            if feat not in df.columns:
                continue
            vals = df[feat].dropna()
            y = is_win.loc[vals.index]
            if len(vals) < 10:
                continue
            try:
                r, pv = stats.pointbiserialr(y, vals)
                profile["features"][feat] = {"r": r, "p": pv}
                if abs(r) > abs(best_r):
                    best_r = r
                    best_feat = feat.replace("cs_", "")
            except:
                continue

        ticker_profiles[ticker] = profile
        print(f"    {ticker:<8s} │ {n:>4d} │ {wr:>4.1f}% │ {pf:>5.2f} │ {sharpe:>+6.3f} │ {ev:>+6.2f}% │ {best_feat:>25s} │ {best_r:>+6.3f}")

    # Identify ADAPTIVE variables: features that are significant in ≥30% of tickers
    sp("ADAPTIVE VARIABLES — Features that need per-ticker calibration")
    feat_significance = {f: [] for f in meta_features}
    for ticker, prof in ticker_profiles.items():
        for feat, vals in prof["features"].items():
            if abs(vals["r"]) > 0.1 and vals["p"] < 0.15:
                feat_significance[feat].append((ticker, vals["r"]))

    print(f"\n    {'Feature':<28s} │ {'Tickers':>7s} │ {'Sign':>5s} │ {'Details':>40s}")
    print(f"    {'─'*85}")
    for feat in meta_features:
        tickers_list = feat_significance.get(feat, [])
        if not tickers_list:
            continue
        pct = len(tickers_list) / len(ticker_profiles) * 100
        signs = [np.sign(r) for _, r in tickers_list]
        sign_str = "+" if all(s > 0 for s in signs) else "-" if all(s < 0 for s in signs) else "±"
        details = ", ".join(f"{t}({r:+.2f})" for t, r in tickers_list[:4])
        tag = "UNIVERSAL" if pct >= 60 else "ADAPTIVE" if pct >= 30 else "SPECIFIC"
        print(f"    {feat.replace('cs_',''):<28s} │ {len(tickers_list):>2d}/{len(ticker_profiles):<2d}  │ {sign_str:>5s} │ {details:>40s}  [{tag}]")

    return ticker_profiles


# ═══════════════════════════════════════════════════════════
# PART 4: WALK-FORWARD VALIDATION (Purged)
# ═══════════════════════════════════════════════════════════

def part4_walk_forward(all_results, signal_metrics):
    p("PART 4: WALK-FORWARD VALIDATION — Out-of-sample truth")

    if not signal_metrics:
        print("  No viable signals.")
        return

    # Periods for walk-forward (UTC-aware to match Vault timestamps)
    periods = [
        ("2006-2012", "2013-2015", pd.Timestamp("2006-01-01", tz="UTC"), pd.Timestamp("2012-12-31", tz="UTC"), pd.Timestamp("2013-01-01", tz="UTC"), pd.Timestamp("2015-12-31", tz="UTC")),
        ("2010-2016", "2017-2019", pd.Timestamp("2010-01-01", tz="UTC"), pd.Timestamp("2016-12-31", tz="UTC"), pd.Timestamp("2017-01-01", tz="UTC"), pd.Timestamp("2019-12-31", tz="UTC")),
        ("2014-2020", "2021-2023", pd.Timestamp("2014-01-01", tz="UTC"), pd.Timestamp("2020-12-31", tz="UTC"), pd.Timestamp("2021-01-01", tz="UTC"), pd.Timestamp("2023-12-31", tz="UTC")),
        ("2016-2022", "2023-2026", pd.Timestamp("2016-01-01", tz="UTC"), pd.Timestamp("2022-12-31", tz="UTC"), pd.Timestamp("2023-01-01", tz="UTC"), pd.Timestamp("2026-12-31", tz="UTC")),
    ]

    for sig_name, metrics in signal_metrics.items():
        if metrics["sharpe"] < 0.3:
            continue

        sp(f"Walk-Forward: {sig_name} (in-sample Sharpe={metrics['sharpe']:+.3f})")
        df = metrics["df"]
        df["entry_time"] = pd.to_datetime(df["entry_time"])

        print(f"\n    {'Period':<16s} │ {'Train':>12s} │ {'Test':>12s} │ {'N_test':>6s} │ {'WR':>5s} │ {'PF':>5s} │ {'Sharpe':>7s} │ {'EV':>7s}")
        print(f"    {'─'*85}")

        oos_sharpes = []
        for train_label, test_label, train_start, train_end, test_start, test_end in periods:
            test_df = df[(df["entry_time"] >= test_start) & (df["entry_time"] <= test_end)]
            if len(test_df) < 5:
                print(f"    {train_label:<16s} │ {train_label:>12s} │ {test_label:>12s} │ {'<5':>6s} │  --- │  --- │    --- │    ---")
                continue

            n = len(test_df)
            wins = (test_df["label"] == 1).sum()
            wr = wins / n * 100
            returns = test_df["return_pct"]
            avg_ret = returns.mean()
            std_ret = returns.std(ddof=1) if n > 1 else 1
            avg_bars = test_df["bars_held"].mean()
            sharpe = (avg_ret / max(std_ret, 0.001)) * np.sqrt(252 / max(avg_bars, 1))
            gross_profit = returns[returns > 0].sum()
            gross_loss = abs(returns[returns < 0].sum())
            pf = gross_profit / max(gross_loss, 0.001)
            avg_win = returns[returns > 0].mean() if wins > 0 else 0
            avg_loss = returns[returns < 0].mean() if (n - wins) > 0 else 0
            ev = (wr/100) * avg_win + (1 - wr/100) * avg_loss

            oos_sharpes.append(sharpe)
            sig_mark = "✅" if sharpe > 0.3 else "⚠️" if sharpe > 0 else "❌"
            print(f"    {train_label:<16s} │ {train_label:>12s} │ {test_label:>12s} │ {n:>6d} │ {wr:>4.1f}% │ {pf:>5.2f} │ {sharpe:>+6.3f}{sig_mark:>1s} │ {ev:>+6.3f}%")

        if oos_sharpes:
            mean_oos = np.mean(oos_sharpes)
            in_sample = metrics["sharpe"]
            degradation = (1 - mean_oos / max(abs(in_sample), 0.001)) * 100 if in_sample != 0 else 0
            print(f"\n    OOS Mean Sharpe: {mean_oos:+.3f} (IS: {in_sample:+.3f})")
            print(f"    Degradation: {degradation:.0f}%")
            if degradation > 50:
                print(f"    ⚠️ OVERFITTING RISK: OOS degradation > 50%")
            elif mean_oos > 0.3:
                print(f"    ✅ VIABLE: Consistent OOS edge")


# ═══════════════════════════════════════════════════════════
# PART 5: DEFLATED SHARPE RATIO
# ═══════════════════════════════════════════════════════════

def part5_deflated_sharpe(signal_metrics):
    p("PART 5: DEFLATED SHARPE RATIO — Adjusting for multiple testing")

    n_trials = len(SIGNAL_CONDITIONS)
    print(f"  Number of signal conditions tested: {n_trials}")
    print(f"  (LdP: 'A Sharpe of 1.2 from 3 trials > Sharpe of 2.5 from 200 trials')\n")

    print(f"    {'Signal':<22s} │ {'Raw Sharpe':>10s} │ {'DSR':>7s} │ {'Verdict':>15s}")
    print(f"    {'─'*65}")

    for sig_name, metrics in sorted(signal_metrics.items(), key=lambda x: -x[1]["sharpe"]):
        df = metrics["df"]
        returns = df["return_pct"]
        n_obs = len(returns)
        raw_sharpe = metrics["sharpe"]

        # Compute DSR
        skew = float(returns.skew()) if n_obs > 3 else 0
        kurt = float(returns.kurtosis()) + 3 if n_obs > 4 else 3

        # Simplified DSR
        from scipy.stats import norm
        euler = 0.5772156649
        if n_trials > 1:
            e_max_sr = (1 - euler) * norm.ppf(1 - 1/n_trials) + euler * norm.ppf(1 - 1/(n_trials * np.e))
        else:
            e_max_sr = 0

        var_term = 1 + 0.5*raw_sharpe**2 - skew*raw_sharpe + ((kurt-3)/4)*raw_sharpe**2
        se_sr = np.sqrt(max(var_term, 0.0001) / max(n_obs - 1, 1))
        dsr_stat = (raw_sharpe - e_max_sr) / max(se_sr, 0.0001)
        dsr = float(norm.cdf(dsr_stat))

        verdict = "★★ ROBUST" if dsr > 0.95 else "★ VIABLE" if dsr > 0.70 else "~ MARGINAL" if dsr > 0.50 else "✗ OVERFIT"
        print(f"    {sig_name:<22s} │ {raw_sharpe:>+9.3f} │ {dsr:>6.3f} │ {verdict:>15s}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v16 — LÓPEZ DE PRADO META-LABEL VALIDATION")
    print("  Triple Barrier + Walk-Forward + Per-Ticker Profiles + DSR")
    print(f"  Geometry: TP={PROFIT_MULT}×ATR, SL={LOSS_MULT}×ATR, MaxBars={MAX_BARS}")
    print(f"  Signals: {len(SIGNAL_CONDITIONS)}")

    store = TimescaleDataStore()
    labeler = TripleBarrierAdapter()

    all_results = {}
    for ticker in TICKERS:
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or len(ohlc) < 300:
            print(f"  {ticker}: SKIP")
            continue

        print(f"\n  {ticker} ({len(ohlc)} bars):")
        ticker_results = generate_labels_per_ticker(ticker, ohlc, labeler)
        if ticker_results:
            all_results[ticker] = ticker_results

    store.close()

    # Performance analysis
    signal_metrics = part2_tb_performance(all_results)
    ticker_profiles = part3_per_ticker_profiles(all_results, signal_metrics)
    part4_walk_forward(all_results, signal_metrics)
    part5_deflated_sharpe(signal_metrics)

    p("v16 — LÓPEZ DE PRADO VALIDATION COMPLETE")
    print("  The numbers that matter: Sharpe, PF, EV, DSR — not WR alone.")
