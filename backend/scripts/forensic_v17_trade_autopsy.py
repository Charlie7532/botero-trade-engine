#!/usr/bin/env python3
"""
Forensic Lab v17 — TRADE AUTOPSY: Every Entry, Every Exit, Every Lesson
==========================================================================
NO summary statistics. NO black boxes. PURE DATA.

For EVERY trade:
  1. WHY did we enter? What regime? What slopes? Where was the floor?
  2. Did we enter too early? How deep was MAE before the trade resolved?
  3. The STOP-LOSS AUTOPSY:
     - Was it a sweep (stop hit but close above entry)?
     - Did the price reach our TP AFTER the stop killed us?
     - How many bars after the stop would we have won?
     - What sigma/slope combination PREDICTED the false stop?
  4. SUCCESSFUL entries: what made them work? Common DNA?
  5. The STOP as adaptive variable: should it be per-ticker? Per-regime?

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

from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.simulation.infrastructure.triple_barrier_adapter import TripleBarrierAdapter

def p(t): print(f"\n{'='*95}\n  {t}\n{'='*95}")
def sp(t): print(f"\n  ── {t} ──")

# Focus on tickers where the channel WORKS (Tier A from v16)
TICKERS = ["AMZN", "MCD", "MRK", "COST", "JPM", "XOM", "MSFT", "AAPL", "SPY"]

# Use ALL_EXTREME — the signal with best OOS Sharpe
SIGNAL_CONDITION = lambda snap: snap.sigma_tide < -2.0 and snap.vwap_sigma_wave < -1.5 and snap.below_all_vwaps

# Test MULTIPLE stop geometries to find the adaptive variable
GEOMETRIES = {
    "TIGHT":  {"profit_mult": 3.0, "loss_mult": 0.5, "max_bars": 60},
    "NORMAL": {"profit_mult": 3.0, "loss_mult": 1.0, "max_bars": 60},
    "WIDE":   {"profit_mult": 3.0, "loss_mult": 2.0, "max_bars": 60},
    "NO_STOP": {"profit_mult": 3.0, "loss_mult": 0, "max_bars": 60},   # Only time and TP
    "THESIS": {"profit_mult": 3.0, "loss_mult": 0, "max_bars": 120},   # Quality: patience
}


def generate_forensic_trades(ticker, ohlc, labeler):
    """Generate detailed forensic trade records with ChannelSnapshot context."""
    close = ohlc["close"].values.astype(float)
    high = ohlc["high"].values.astype(float)
    low = ohlc["low"].values.astype(float)
    volume = ohlc["volume"].values.astype(float)

    # Find ALL entry points first
    entry_mask = pd.Series(False, index=ohlc.index)
    entry_snapshots = {}

    for idx in range(250, len(ohlc)):
        snap = compute_channel_snapshot(close, high, low, volume, idx)
        if snap is None:
            continue
        if SIGNAL_CONDITION(snap):
            entry_mask.iloc[idx] = True
            entry_snapshots[ohlc.index[idx]] = snap

    n_entries = entry_mask.sum()
    if n_entries < 3:
        return None

    # Label with EACH geometry
    geometry_results = {}
    for geo_name, geo in GEOMETRIES.items():
        labels = labeler.label_entries(
            ohlc, entry_mask,
            profit_mult=geo["profit_mult"],
            loss_mult=geo["loss_mult"],
            max_bars=geo["max_bars"],
            vol_lookback=20,
            entry_delay_bars=1,
            slippage_factor=0.08,
            round_trip_cost_bps=10.0,
        )
        geometry_results[geo_name] = {l.entry_time: l for l in labels if l.entry_time}

    # Build enriched forensic records
    records = []
    normal_labels = geometry_results.get("NORMAL", {})

    for entry_time, label in normal_labels.items():
        snap = entry_snapshots.get(entry_time)
        if snap is None:
            continue

        # What would have happened with different stops?
        tight_label = geometry_results.get("TIGHT", {}).get(entry_time)
        wide_label = geometry_results.get("WIDE", {}).get(entry_time)
        nostop_label = geometry_results.get("NO_STOP", {}).get(entry_time)
        thesis_label = geometry_results.get("THESIS", {}).get(entry_time)

        rec = {
            "ticker": ticker,
            "entry_time": entry_time,
            "entry_price": label.entry_price,

            # ── OUTCOME ──
            "result": label.hit_barrier,  # "profit", "loss", "time"
            "label": label.label,         # 1, -1, 0
            "return_pct": label.return_pct,
            "bars_held": label.bars_held,

            # ── FORENSIC: What happened DURING the trade ──
            "mae_pct": label.max_adverse_excursion_pct,    # Deepest drawdown
            "mfe_pct": label.max_favorable_excursion_pct,  # Best unrealized profit
            "mae_mfe_ratio": abs(label.max_adverse_excursion_pct) / max(label.max_favorable_excursion_pct, 0.01),

            # ── STOP AUTOPSY ──
            "sweep": label.stop_was_sweep,
            "post_exit_max_pct": label.post_exit_max_pct,
            "post_exit_hit_tp": label.post_exit_hit_target,
            "post_exit_bars_to_tp": label.post_exit_bars_to_target,

            # ── ALTERNATIVE STOPS (what would have happened?) ──
            "tight_result": tight_label.hit_barrier if tight_label else None,
            "tight_return": tight_label.return_pct if tight_label else None,
            "wide_result": wide_label.hit_barrier if wide_label else None,
            "wide_return": wide_label.return_pct if wide_label else None,
            "nostop_result": nostop_label.hit_barrier if nostop_label else None,
            "nostop_return": nostop_label.return_pct if nostop_label else None,
            "thesis_result": thesis_label.hit_barrier if thesis_label else None,
            "thesis_return": thesis_label.return_pct if thesis_label else None,

            # ── ENTRY CONTEXT: What did the indicators say? ──
            "sigma_tide": snap.sigma_tide,
            "sigma_current": snap.sigma_current,
            "sigma_wave": snap.sigma_wave,
            "vwap_sigma_tide": snap.vwap_sigma_tide,
            "vwap_sigma_current": snap.vwap_sigma_current,
            "vwap_sigma_wave": snap.vwap_sigma_wave,
            "tide_slope": snap.tide_slope,
            "current_slope": snap.current_slope,
            "wave_slope": snap.wave_slope,
            "tide_accel": snap.tide_accel,
            "spread_tide_current": snap.spread_tide_current,
            "fear_level": snap.fear_level,
            "fear_label": snap.fear_label,
            "regime": snap.regime,
            "wave_flip": snap.wave_flip,
            "wave_flip_direction": snap.wave_flip_direction,
            "vol_up_down_ratio": snap.vol_up_down_ratio,
            "below_all_vwaps": snap.below_all_vwaps,
        }
        records.append(rec)

    return pd.DataFrame(records) if records else None


# ═══════════════════════════════════════════════════════════
# AUTOPSY 1: The Stop-Loss Graveyard
# ═══════════════════════════════════════════════════════════

def autopsy1_stop_loss_graveyard(df):
    p("AUTOPSY 1: THE STOP-LOSS GRAVEYARD — Every dead trade, examined")

    losses = df[df["result"] == "loss"].copy()
    wins = df[df["result"] == "profit"].copy()
    total = len(df)

    print(f"  Total trades: {total}")
    print(f"  Wins (hit TP): {len(wins)} ({len(wins)/total*100:.1f}%)")
    print(f"  Losses (hit SL): {len(losses)} ({len(losses)/total*100:.1f}%)")
    print(f"  Time exits: {total - len(wins) - len(losses)} ({(total-len(wins)-len(losses))/total*100:.1f}%)")

    if len(losses) == 0:
        return

    # ── How many stopped-out trades WOULD have won? ──
    sp("WOULD HAVE WON — Trades killed by SL that reached TP eventually")
    would_have_won = losses[losses["post_exit_hit_tp"] == True]
    n_whw = len(would_have_won)
    print(f"  Stopped out then hit TP: {n_whw}/{len(losses)} ({n_whw/len(losses)*100:.1f}%)")
    if n_whw > 0:
        print(f"  Avg bars AFTER stop to reach TP: {would_have_won['post_exit_bars_to_tp'].mean():.0f}")
        print(f"  Max post-exit gain: {would_have_won['post_exit_max_pct'].mean():+.2f}%")

    # ── SWEEPS: Stop hit but close above entry (institutional hunting) ──
    sp("SWEEPS — Institutional stop hunting")
    sweeps = losses[losses["sweep"] == True]
    print(f"  Sweeps detected: {len(sweeps)}/{len(losses)} ({len(sweeps)/len(losses)*100:.1f}%)")
    if len(sweeps) > 0:
        sweep_then_win = sweeps[sweeps["post_exit_hit_tp"] == True]
        print(f"  Sweeps that then hit TP: {len(sweep_then_win)}/{len(sweeps)} ({len(sweep_then_win)/max(len(sweeps),1)*100:.1f}%)")

    # ── What if we had NO STOP? ──
    sp("ALTERNATIVE UNIVERSE — What if the stop didn't exist?")
    for geo_name, col_result, col_return in [
        ("WIDE (2×ATR)", "wide_result", "wide_return"),
        ("NO_STOP (time only)", "nostop_result", "nostop_return"),
        ("THESIS (120 bars)", "thesis_result", "thesis_return"),
    ]:
        subset = losses.dropna(subset=[col_result])
        if len(subset) == 0:
            continue
        alt_wins = (subset[col_result] == "profit").sum()
        alt_losses = (subset[col_result] == "loss").sum()
        alt_time = (subset[col_result] == "time").sum()
        alt_avg_ret = subset[col_return].mean()
        print(f"\n    {geo_name}:")
        print(f"      Of {len(subset)} SL-killed trades:")
        print(f"      → {alt_wins} would WIN ({alt_wins/len(subset)*100:.1f}%)")
        print(f"      → {alt_losses} still lose ({alt_losses/len(subset)*100:.1f}%)")
        print(f"      → {alt_time} time exit ({alt_time/len(subset)*100:.1f}%)")
        print(f"      → Avg return: {alt_avg_ret:+.2f}%")

    # ── The MAE question: how deep did we go before getting stopped? ──
    sp("MAE DEPTH — How deep before the stop killed us?")
    print(f"  Losses avg MAE: {losses['mae_pct'].mean():.2f}%")
    print(f"  Wins avg MAE:   {wins['mae_pct'].mean():.2f}%")
    print(f"  Wins avg MFE:   {wins['mfe_pct'].mean():.2f}%")

    # Was the entry too early? (MAE > 2× the stop level means entered way before bottom)
    deep_mae = losses[losses["mae_pct"] < -3.0]  # Dropped >3% before stop
    print(f"\n  Entries with MAE > 3%: {len(deep_mae)}/{len(losses)} ({len(deep_mae)/len(losses)*100:.1f}%)")
    if len(deep_mae) > 0:
        print(f"    Avg sigma_tide at entry: {deep_mae['sigma_tide'].mean():.2f}")
        print(f"    Avg sigma_wave at entry: {deep_mae['sigma_wave'].mean():.2f}")
        print(f"    → These entries were ANTICIPATED (entered before the selling finished)")


# ═══════════════════════════════════════════════════════════
# AUTOPSY 2: DNA of Successful Entries
# ═══════════════════════════════════════════════════════════

def autopsy2_winning_dna(df):
    p("AUTOPSY 2: DNA OF WINNERS vs LOSERS — What separates them?")

    wins = df[df["label"] == 1].copy()
    losses = df[df["label"] == -1].copy()

    if len(wins) < 5 or len(losses) < 5:
        print("  Insufficient data for comparison.")
        return

    features = [
        ("sigma_tide", "Position in regression channel (240)"),
        ("sigma_current", "Position in regression channel (60)"),
        ("sigma_wave", "Position in regression channel (wave)"),
        ("vwap_sigma_tide", "Distance from institutional VWAP (240)"),
        ("vwap_sigma_current", "Distance from institutional VWAP (60)"),
        ("vwap_sigma_wave", "Distance from institutional VWAP (wave)"),
        ("tide_slope", "Macro trend direction"),
        ("current_slope", "Quarterly trend direction"),
        ("wave_slope", "Short-term trend direction"),
        ("tide_accel", "Macro trend acceleration"),
        ("spread_tide_current", "Timeframe divergence tide↔current"),
        ("vol_up_down_ratio", "Buying vs selling pressure"),
        ("fear_level", "Fear classification (0=GREED, 5=PANIC)"),
    ]

    print(f"\n    {'Feature':<25s} │ {'Winners':>10s} │ {'Losers':>10s} │ {'Diff':>8s} │ {'p-val':>8s} │ {'Verdict':<15s}")
    print(f"    {'─'*95}")

    for feat, desc in features:
        w_vals = wins[feat].dropna()
        l_vals = losses[feat].dropna()
        if len(w_vals) < 5 or len(l_vals) < 5:
            continue

        w_mean = w_vals.mean()
        l_mean = l_vals.mean()
        diff = w_mean - l_mean

        try:
            t_stat, pval = stats.ttest_ind(w_vals, l_vals, equal_var=False)
        except:
            pval = 1.0

        if pval < 0.01:
            verdict = "★★★ STRONG"
        elif pval < 0.05:
            verdict = "★★ SIGNIFICANT"
        elif pval < 0.10:
            verdict = "★ MARGINAL"
        else:
            verdict = "  not signif."

        print(f"    {feat:<25s} │ {w_mean:>+9.3f} │ {l_mean:>+9.3f} │ {diff:>+7.3f} │ {pval:>7.4f} │ {verdict:<15s}")

    # ── Regime breakdown ──
    sp("REGIME AT ENTRY — What regime produces winners?")
    for regime in df["regime"].unique():
        sub = df[df["regime"] == regime]
        if len(sub) < 5:
            continue
        wr = (sub["label"] == 1).mean() * 100
        n = len(sub)
        avg_ret = sub["return_pct"].mean()
        print(f"    {regime:<12s}: WR={wr:>5.1f}%, Ret={avg_ret:>+6.2f}%, N={n:>4d}")

    # ── Fear level breakdown ──
    sp("FEAR LEVEL AT ENTRY — When does fear help?")
    for fl in sorted(df["fear_label"].unique()):
        sub = df[df["fear_label"] == fl]
        if len(sub) < 3:
            continue
        wr = (sub["label"] == 1).mean() * 100
        n = len(sub)
        avg_ret = sub["return_pct"].mean()
        print(f"    {fl:<12s}: WR={wr:>5.1f}%, Ret={avg_ret:>+6.2f}%, N={n:>4d}")

    # ── Slope configuration ──
    sp("SLOPE CONFIGURATION — Pendientes at entry")
    # All slopes negative = falling knife
    all_neg = df[(df["tide_slope"] < 0) & (df["current_slope"] < 0) & (df["wave_slope"] < 0)]
    # Tide positive but wave negative = pullback in uptrend
    pullback = df[(df["tide_slope"] > 0) & (df["wave_slope"] < 0)]
    # All positive = breakout
    all_pos = df[(df["tide_slope"] > 0) & (df["current_slope"] > 0) & (df["wave_slope"] > 0)]

    for name, sub in [("ALL SLOPES ↓ (knife)", all_neg), ("TIDE↑ WAVE↓ (pullback)", pullback), ("ALL SLOPES ↑ (breakout)", all_pos)]:
        if len(sub) < 3:
            print(f"    {name}: N={len(sub)} (too few)")
            continue
        wr = (sub["label"] == 1).mean() * 100
        avg_ret = sub["return_pct"].mean()
        avg_mae = sub["mae_pct"].mean()
        print(f"    {name}: WR={wr:>5.1f}%, Ret={avg_ret:>+6.2f}%, MAE={avg_mae:>+6.2f}%, N={len(sub)}")


# ═══════════════════════════════════════════════════════════
# AUTOPSY 3: The Stop-Loss as Adaptive Variable
# ═══════════════════════════════════════════════════════════

def autopsy3_stop_as_variable(df):
    p("AUTOPSY 3: STOP-LOSS AS ADAPTIVE VARIABLE — Should it change per ticker/regime?")

    sp("GEOMETRY COMPARISON — Same entries, different stops")
    print(f"\n    {'Geometry':<20s} │ {'N':>4s} │ {'Wins':>5s} │ {'Losses':>6s} │ {'Time':>5s} │ {'WR':>5s} │ {'Avg Ret':>7s} │ {'PF':>5s}")
    print(f"    {'─'*75}")

    for geo_name, col_result, col_return in [
        ("TIGHT (0.5×ATR)", "tight_result", "tight_return"),
        ("NORMAL (1.0×ATR)", "result", "return_pct"),
        ("WIDE (2.0×ATR)", "wide_result", "wide_return"),
        ("NO_STOP (time)", "nostop_result", "nostop_return"),
        ("THESIS (120 bars)", "thesis_result", "thesis_return"),
    ]:
        sub = df.dropna(subset=[col_result, col_return])
        if len(sub) == 0:
            continue
        wins = (sub[col_result] == "profit").sum()
        losses = (sub[col_result] == "loss").sum()
        time_exits = (sub[col_result] == "time").sum()
        n = len(sub)
        wr = wins / n * 100
        avg_ret = sub[col_return].mean()
        gross_profit = sub[sub[col_return] > 0][col_return].sum()
        gross_loss = abs(sub[sub[col_return] < 0][col_return].sum())
        pf = gross_profit / max(gross_loss, 0.001)
        print(f"    {geo_name:<20s} │ {n:>4d} │ {wins:>5d} │ {losses:>6d} │ {time_exits:>5d} │ {wr:>4.1f}% │ {avg_ret:>+6.2f}% │ {pf:>5.2f}")

    # ── Per-ticker: which stop works best WHERE? ──
    sp("PER-TICKER OPTIMAL STOP — The adaptive variable")
    print(f"\n    {'Ticker':<8s} │ {'TIGHT':>10s} │ {'NORMAL':>10s} │ {'WIDE':>10s} │ {'NO_STOP':>10s} │ {'THESIS':>10s} │ {'Best':>10s}")
    print(f"    {'─'*85}")

    for ticker in df["ticker"].unique():
        t = df[df["ticker"] == ticker]
        if len(t) < 5:
            continue
        results = {}
        for geo_name, col_result, col_return in [
            ("TIGHT", "tight_result", "tight_return"),
            ("NORMAL", "result", "return_pct"),
            ("WIDE", "wide_result", "wide_return"),
            ("NO_STOP", "nostop_result", "nostop_return"),
            ("THESIS", "thesis_result", "thesis_return"),
        ]:
            sub = t.dropna(subset=[col_result, col_return])
            if len(sub) == 0:
                results[geo_name] = 0
                continue
            avg_ret = sub[col_return].mean()
            results[geo_name] = avg_ret

        best = max(results.keys(), key=lambda k: results[k])
        print(f"    {ticker:<8s} │ {results.get('TIGHT',0):>+9.2f}% │ {results.get('NORMAL',0):>+9.2f}% │ {results.get('WIDE',0):>+9.2f}% │ {results.get('NO_STOP',0):>+9.2f}% │ {results.get('THESIS',0):>+9.2f}% │ {best:>10s}")

    # ── Per-regime: which stop works best in which market condition? ──
    sp("PER-REGIME OPTIMAL STOP — Stop adapts to market")
    for regime in sorted(df["regime"].dropna().unique()):
        r = df[df["regime"] == regime]
        if len(r) < 10:
            continue
        results = {}
        for geo_name, col_result, col_return in [
            ("TIGHT", "tight_result", "tight_return"),
            ("NORMAL", "result", "return_pct"),
            ("WIDE", "wide_result", "wide_return"),
            ("NO_STOP", "nostop_result", "nostop_return"),
            ("THESIS", "thesis_result", "thesis_return"),
        ]:
            sub = r.dropna(subset=[col_result, col_return])
            if len(sub) == 0:
                results[geo_name] = 0
                continue
            results[geo_name] = sub[col_return].mean()
        best = max(results.keys(), key=lambda k: results[k])
        best_ret = results[best]
        normal_ret = results.get("NORMAL", 0)
        improvement = best_ret - normal_ret
        print(f"    {regime:<12s}: Best={best:<8s} ({best_ret:>+6.2f}% vs NORMAL {normal_ret:>+6.2f}%) Δ={improvement:>+5.2f}%, N={len(r)}")


# ═══════════════════════════════════════════════════════════
# AUTOPSY 4: Per-Ticker Trade-by-Trade Examples
# ═══════════════════════════════════════════════════════════

def autopsy4_trade_examples(df):
    p("AUTOPSY 4: TRADE EXAMPLES — The best and worst, dissected")

    # Top 10 best trades
    sp("TOP 10 BEST TRADES — What made them work?")
    best = df.nlargest(10, "return_pct")
    print(f"\n    {'Ticker':<6s} │ {'Date':<12s} │ {'Ret':>6s} │ {'Bars':>4s} │ {'MAE':>6s} │ {'σ_tide':>7s} │ {'vwap_σ_w':>8s} │ {'Regime':<8s} │ {'Slopes':>20s}")
    print(f"    {'─'*100}")
    for _, row in best.iterrows():
        slopes = f"T:{row['tide_slope']:+.2f} C:{row['current_slope']:+.2f} W:{row['wave_slope']:+.2f}"
        date_str = str(row['entry_time'])[:10]
        print(f"    {row['ticker']:<6s} │ {date_str:<12s} │ {row['return_pct']:>+5.1f}% │ {row['bars_held']:>4.0f} │ {row['mae_pct']:>+5.1f}% │ {row['sigma_tide']:>+6.2f} │ {row['vwap_sigma_wave']:>+7.2f} │ {row['regime']:<8s} │ {slopes:>20s}")

    # Top 10 worst trades
    sp("TOP 10 WORST TRADES — What went wrong?")
    worst = df.nsmallest(10, "return_pct")
    print(f"\n    {'Ticker':<6s} │ {'Date':<12s} │ {'Ret':>6s} │ {'Bars':>4s} │ {'MAE':>6s} │ {'Sweep':>5s} │ {'Post TP?':>8s} │ {'σ_tide':>7s} │ {'Regime':<8s}")
    print(f"    {'─'*95}")
    for _, row in worst.iterrows():
        date_str = str(row['entry_time'])[:10]
        sweep = "YES" if row.get("sweep") else "no"
        post_tp = "YES" if row.get("post_exit_hit_tp") else "no"
        print(f"    {row['ticker']:<6s} │ {date_str:<12s} │ {row['return_pct']:>+5.1f}% │ {row['bars_held']:>4.0f} │ {row['mae_pct']:>+5.1f}% │ {sweep:>5s} │ {post_tp:>8s} │ {row['sigma_tide']:>+6.2f} │ {row['regime']:<8s}")

    # Trades where stop killed us but price reached TP
    sp("THE INJUSTICE — Stopped out, then price hit our TP")
    injustice = df[(df["label"] == -1) & (df["post_exit_hit_tp"] == True)]
    if len(injustice) > 0:
        print(f"  {len(injustice)} trades killed by stop that WOULD HAVE WON")
        print(f"  Avg bars to TP after stop: {injustice['post_exit_bars_to_tp'].mean():.0f}")
        print(f"\n    {'Ticker':<6s} │ {'Date':<12s} │ {'SL Ret':>6s} │ {'Post Max':>8s} │ {'Bars→TP':>7s} │ {'Sweep':>5s} │ {'NoStop Ret':>10s}")
        print(f"    {'─'*75}")
        for _, row in injustice.head(15).iterrows():
            date_str = str(row['entry_time'])[:10]
            sweep = "YES" if row.get("sweep") else "no"
            nostop_ret = f"{row['nostop_return']:>+6.2f}%" if pd.notna(row.get('nostop_return')) else "N/A"
            print(f"    {row['ticker']:<6s} │ {date_str:<12s} │ {row['return_pct']:>+5.1f}% │ {row['post_exit_max_pct']:>+7.1f}% │ {row['post_exit_bars_to_tp']:>7.0f} │ {sweep:>5s} │ {nostop_ret:>10s}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v17 — TRADE AUTOPSY: Every Entry, Every Exit")
    print("  Signal: ALL_EXTREME (σ_tide<-2 + vwap_σ_wave<-1.5 + below_all_vwaps)")
    print(f"  Geometries tested: {list(GEOMETRIES.keys())}")
    print(f"  Tickers: {TICKERS}")

    store = TimescaleDataStore()
    labeler = TripleBarrierAdapter()

    all_dfs = []
    for ticker in TICKERS:
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or len(ohlc) < 300:
            print(f"  {ticker}: SKIP")
            continue

        print(f"\n  Processing {ticker} ({len(ohlc)} bars)...")
        df = generate_forensic_trades(ticker, ohlc, labeler)
        if df is not None and len(df) > 0:
            all_dfs.append(df)
            print(f"    → {len(df)} forensic records generated")

    store.close()

    if not all_dfs:
        print("No trades generated!")
        sys.exit(1)

    combined = pd.concat(all_dfs, ignore_index=True)
    print(f"\n  Total forensic records: {len(combined)}")

    autopsy1_stop_loss_graveyard(combined)
    autopsy2_winning_dna(combined)
    autopsy3_stop_as_variable(combined)
    autopsy4_trade_examples(combined)

    p("v17 — TRADE AUTOPSY COMPLETE")
    print("  No black boxes. Every trade examined. Every stop questioned.")
