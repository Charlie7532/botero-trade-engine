"""
F&G Forensic Backtest — SPY/QQQ Correlation
================================================
Validates FG-H01 through FG-H05 using real historical data
from the Neon Vault (FG bars 2011-2026 + SPY/QQQ).

López de Prado methodology:
  - Forward returns with .shift(-N) (no lookahead)
  - Win rate + mean return by F&G regime
  - Velocity analysis (direction matters, not just level)
  - Statistical significance via t-test

Usage:
    python -m backend.scripts.backtest_fg_correlation
"""
import logging
import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def load_from_vault(ticker: str, start: date) -> pd.DataFrame | None:
    """Load OHLCV bars from Neon Vault."""
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()
    df = store.load_bars(ticker, "1d", start=start)
    store.close()
    if df is not None and not df.empty:
        logger.info(f"  Loaded {ticker}: {len(df)} bars ({df.index[0].date()} → {df.index[-1].date()})")
    else:
        logger.warning(f"  {ticker}: no data")
    return df


def compute_fg_features(fg: pd.Series) -> pd.DataFrame:
    """Compute F&G analytical features (regime, velocity, direction)."""
    df = pd.DataFrame(index=fg.index)
    df["fg"] = fg

    # Regime classification
    df["fg_regime"] = pd.cut(
        fg,
        bins=[-1, 15, 25, 45, 55, 75, 85, 101],
        labels=["EXTREME_FEAR", "FEAR", "MILD_FEAR", "NEUTRAL", "MILD_GREED", "GREED", "EXTREME_GREED"],
    )

    # Velocity: 5-day rate of change
    df["fg_roc5"] = fg.diff(5)

    # Z-scored velocity
    roc_mean = df["fg_roc5"].rolling(60, min_periods=20).mean()
    roc_std = df["fg_roc5"].rolling(60, min_periods=20).std()
    df["fg_velocity_z"] = (df["fg_roc5"] - roc_mean) / roc_std.replace(0, np.nan)

    # Direction
    df["fg_direction"] = "STABLE"
    df.loc[df["fg_roc5"] > 3, "fg_direction"] = "RISING"
    df.loc[df["fg_roc5"] < -3, "fg_direction"] = "FALLING"

    # 60d Z-score of level
    fg_mean = fg.rolling(60, min_periods=20).mean()
    fg_std = fg.rolling(60, min_periods=20).std()
    df["fg_zscore"] = (fg - fg_mean) / fg_std.replace(0, np.nan)

    return df


def compute_forward_returns(prices: pd.Series) -> pd.DataFrame:
    """Compute forward returns at multiple horizons."""
    df = pd.DataFrame(index=prices.index)
    for horizon in [5, 10, 20, 40, 60]:
        df[f"ret{horizon}d"] = prices.pct_change(horizon).shift(-horizon) * 100
    # Max drawdown in next 20d
    rolling_min = prices.rolling(20).min().shift(-20)
    df["mdd20d"] = (rolling_min / prices - 1) * 100
    # Max favorable excursion in next 20d
    rolling_max = prices.rolling(20).max().shift(-20)
    df["mfe20d"] = (rolling_max / prices - 1) * 100
    return df


def regime_stats(merged: pd.DataFrame, regime_col: str, ret_col: str) -> pd.DataFrame:
    """Compute stats per regime."""
    rows = []
    for regime, group in merged.groupby(regime_col):
        vals = group[ret_col].dropna()
        if len(vals) < 5:
            continue
        wr = (vals > 0).mean() * 100
        mean = vals.mean()
        median = vals.median()
        std = vals.std()
        t_stat = mean / (std / np.sqrt(len(vals))) if std > 0 else 0
        rows.append({
            "regime": regime,
            "n": len(vals),
            "win_rate": round(wr, 1),
            "mean_ret": round(mean, 2),
            "median_ret": round(median, 2),
            "std": round(std, 2),
            "t_stat": round(t_stat, 2),
            "significant": abs(t_stat) > 1.96,
        })
    return pd.DataFrame(rows)


def main():
    start = date(2011, 1, 1)

    logger.info("═══ F&G Forensic Backtest — Loading from Vault ═══")
    fg_df = load_from_vault("FG", start)
    spy_df = load_from_vault("SPY", start)
    qqq_df = load_from_vault("QQQ", start)

    if fg_df is None or spy_df is None:
        logger.error("Missing FG or SPY data — cannot proceed")
        return

    # Align on common dates
    fg_close = fg_df["close"].rename("fg")
    spy_close = spy_df["close"].rename("spy")
    qqq_close = qqq_df["close"].rename("qqq") if qqq_df is not None else None

    common = fg_close.index.intersection(spy_close.index)
    if qqq_close is not None:
        common = common.intersection(qqq_close.index)
    logger.info(f"\n  Common dates: {len(common)} ({common[0].date()} → {common[-1].date()})")

    # Build features
    fg_features = compute_fg_features(fg_close.reindex(common))
    spy_fwd = compute_forward_returns(spy_close.reindex(common))
    qqq_fwd = compute_forward_returns(qqq_close.reindex(common)) if qqq_close is not None else None

    merged_spy = fg_features.join(spy_fwd, how="inner").dropna(subset=["fg", "ret20d"])
    if qqq_fwd is not None:
        merged_qqq = fg_features.join(qqq_fwd, how="inner", rsuffix="_qqq").dropna(subset=["fg", "ret20d"])

    logger.info(f"  Merged dataset: {len(merged_spy)} observations\n")

    # ═══════════════════════════════════════════════════════════
    # FG-H01: F&G < 20 → SPY Ret20d > 2%
    # ═══════════════════════════════════════════════════════════
    print("=" * 70)
    print("FG-H01: F&G < 20 predicts SPY Ret20d > 2%")
    print("=" * 70)
    fear_mask = merged_spy["fg"] < 20
    fear_ret = merged_spy.loc[fear_mask, "ret20d"]
    neutral_ret = merged_spy.loc[(merged_spy["fg"] >= 40) & (merged_spy["fg"] <= 60), "ret20d"]
    if len(fear_ret) > 0:
        wr = (fear_ret > 0).mean() * 100
        wr2 = (fear_ret > 2).mean() * 100
        print(f"  N = {len(fear_ret)} days with F&G < 20")
        print(f"  Mean Ret20d:   {fear_ret.mean():+.2f}%")
        print(f"  Median Ret20d: {fear_ret.median():+.2f}%")
        print(f"  Win Rate:      {wr:.1f}%")
        print(f"  P(Ret>2%):     {wr2:.1f}%")
        print(f"  Std:           {fear_ret.std():.2f}%")
        t = fear_ret.mean() / (fear_ret.std() / np.sqrt(len(fear_ret))) if fear_ret.std() > 0 else 0
        print(f"  t-stat:        {t:.2f} ({'✅ SIGNIFICANT' if abs(t) > 1.96 else '❌ not significant'})")
        print(f"\n  Baseline (F&G 40-60): Mean={neutral_ret.mean():+.2f}%, WR={(neutral_ret>0).mean()*100:.1f}%, N={len(neutral_ret)}")

    # ═══════════════════════════════════════════════════════════
    # FG-H02: F&G > 80 → SPY Ret20d < 0%
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("FG-H02: F&G > 80 predicts SPY Ret20d < 0%")
    print("=" * 70)
    greed_mask = merged_spy["fg"] > 80
    greed_ret = merged_spy.loc[greed_mask, "ret20d"]
    if len(greed_ret) > 0:
        wr_neg = (greed_ret < 0).mean() * 100
        print(f"  N = {len(greed_ret)} days with F&G > 80")
        print(f"  Mean Ret20d:   {greed_ret.mean():+.2f}%")
        print(f"  Median Ret20d: {greed_ret.median():+.2f}%")
        print(f"  P(Ret<0%):     {wr_neg:.1f}%")
        print(f"  Std:           {greed_ret.std():.2f}%")
        t = greed_ret.mean() / (greed_ret.std() / np.sqrt(len(greed_ret))) if greed_ret.std() > 0 else 0
        print(f"  t-stat:        {t:.2f} ({'✅ SIGNIFICANT' if abs(t) > 1.96 else '❌ not significant'})")

    # ═══════════════════════════════════════════════════════════
    # FG-H03: F&G < 15 + velocity RISING → strong bounce
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("FG-H03: F&G < 15 + velocity rising → SPY Ret20d > 5%")
    print("=" * 70)
    h03_mask = (merged_spy["fg"] < 15) & (merged_spy["fg_direction"] == "RISING")
    h03_ret = merged_spy.loc[h03_mask, "ret20d"]
    h03_wait = merged_spy.loc[(merged_spy["fg"] < 15) & (merged_spy["fg_direction"] == "FALLING"), "ret20d"]
    print(f"  F&G < 15 + RISING:  N={len(h03_ret)}, Mean={h03_ret.mean():+.2f}%, WR={(h03_ret>0).mean()*100:.1f}%" if len(h03_ret) > 0 else "  F&G < 15 + RISING: N=0")
    print(f"  F&G < 15 + FALLING: N={len(h03_wait)}, Mean={h03_wait.mean():+.2f}%, WR={(h03_wait>0).mean()*100:.1f}%" if len(h03_wait) > 0 else "  F&G < 15 + FALLING: N=0")

    # ═══════════════════════════════════════════════════════════
    # FG-H04: F&G velocity < -3σ → more downside before bounce
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("FG-H04: F&G velocity < -3σ → more downside before recovery")
    print("=" * 70)
    panic_mask = merged_spy["fg_velocity_z"] < -3.0
    panic_group = merged_spy.loc[panic_mask]
    if len(panic_group) > 0:
        print(f"  N = {len(panic_group)} panic days (velocity < -3σ)")
        print(f"  MDD next 20d:  {panic_group['mdd20d'].mean():.2f}%")
        print(f"  MFE next 20d:  {panic_group['mfe20d'].mean():+.2f}%")
        print(f"  Ret10d:        {panic_group['ret10d'].mean():+.2f}%")
        print(f"  Ret20d:        {panic_group['ret20d'].mean():+.2f}%")
        print(f"  Ret60d:        {panic_group['ret60d'].mean():+.2f}%")
        print(f"  → Verdict: {'WAIT (more downside coming)' if panic_group['mdd20d'].mean() < -3 else 'BOUNCE likely'}")

    # ═══════════════════════════════════════════════════════════
    # FG-H05: QQQ reacts stronger than SPY at extremes
    # ═══════════════════════════════════════════════════════════
    if qqq_fwd is not None:
        print("\n" + "=" * 70)
        print("FG-H05: QQQ reacts stronger than SPY to F&G extremes")
        print("=" * 70)
        extremes_mask = (merged_spy["fg"] < 20) | (merged_spy["fg"] > 80)

        spy_extreme = merged_spy.loc[extremes_mask, "ret20d"].abs().mean()
        qqq_extreme = merged_qqq.loc[extremes_mask, "ret20d"].abs().mean() if "ret20d" in merged_qqq.columns else 0

        print(f"  SPY |Ret20d| at extremes: {spy_extreme:.2f}%")
        print(f"  QQQ |Ret20d| at extremes: {qqq_extreme:.2f}%")
        print(f"  QQQ/SPY ratio: {qqq_extreme/spy_extreme:.2f}x" if spy_extreme > 0 else "")

        # Fear zone comparison
        fear_spy = merged_spy.loc[merged_spy["fg"] < 20, "ret20d"]
        fear_qqq = merged_qqq.loc[merged_qqq["fg"] < 20, "ret20d"] if "ret20d" in merged_qqq.columns else pd.Series()
        greed_spy = merged_spy.loc[merged_spy["fg"] > 80, "ret20d"]
        greed_qqq = merged_qqq.loc[merged_qqq["fg"] > 80, "ret20d"] if "ret20d" in merged_qqq.columns else pd.Series()

        print(f"\n  FEAR zone (<20):")
        print(f"    SPY: Mean={fear_spy.mean():+.2f}%, WR={(fear_spy>0).mean()*100:.1f}%, N={len(fear_spy)}" if len(fear_spy) > 0 else "    SPY: N=0")
        print(f"    QQQ: Mean={fear_qqq.mean():+.2f}%, WR={(fear_qqq>0).mean()*100:.1f}%, N={len(fear_qqq)}" if len(fear_qqq) > 0 else "    QQQ: N=0")
        print(f"  GREED zone (>80):")
        print(f"    SPY: Mean={greed_spy.mean():+.2f}%, WR={(greed_spy>0).mean()*100:.1f}%, N={len(greed_spy)}" if len(greed_spy) > 0 else "    SPY: N=0")
        print(f"    QQQ: Mean={greed_qqq.mean():+.2f}%, WR={(greed_qqq>0).mean()*100:.1f}%, N={len(greed_qqq)}" if len(greed_qqq) > 0 else "    QQQ: N=0")

    # ═══════════════════════════════════════════════════════════
    # FULL REGIME TABLE — SPY Ret20d by F&G regime
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("FULL REGIME TABLE — SPY Ret20d by F&G level")
    print("=" * 70)
    stats = regime_stats(merged_spy, "fg_regime", "ret20d")
    if not stats.empty:
        print(stats.to_string(index=False))

    # ═══════════════════════════════════════════════════════════
    # DIRECTION × LEVEL MATRIX — SPY Ret20d
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("DIRECTION × LEVEL — SPY Mean Ret20d")
    print("=" * 70)
    for level_label, lo, hi in [("EXTREME_FEAR", 0, 15), ("FEAR", 15, 25), ("NEUTRAL", 40, 60), ("GREED", 75, 85), ("EXTREME_GREED", 85, 101)]:
        level_mask = (merged_spy["fg"] >= lo) & (merged_spy["fg"] < hi)
        for direction in ["FALLING", "STABLE", "RISING"]:
            dir_mask = merged_spy["fg_direction"] == direction
            combined = merged_spy.loc[level_mask & dir_mask, "ret20d"]
            if len(combined) >= 3:
                wr = (combined > 0).mean() * 100
                print(f"  {level_label:15s} + {direction:8s}: N={len(combined):4d}  Mean={combined.mean():+6.2f}%  WR={wr:.0f}%")

    # ═══════════════════════════════════════════════════════════
    # MULTI-HORIZON PROFILE
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("MULTI-HORIZON — Mean Return by F&G zone")
    print("=" * 70)
    for label, lo, hi in [("F&G < 15", 0, 15), ("F&G 15-25", 15, 25), ("F&G 40-60", 40, 60), ("F&G 75-85", 75, 85), ("F&G > 85", 85, 101)]:
        mask = (merged_spy["fg"] >= lo) & (merged_spy["fg"] < hi)
        sub = merged_spy.loc[mask]
        if len(sub) < 5:
            continue
        line = f"  {label:12s} N={len(sub):4d}"
        for h in [5, 10, 20, 40, 60]:
            col = f"ret{h}d"
            if col in sub.columns:
                line += f"  Ret{h:02d}d={sub[col].mean():+5.2f}%"
        print(line)

    print("\n═══ Backtest Complete ═══")


if __name__ == "__main__":
    main()
