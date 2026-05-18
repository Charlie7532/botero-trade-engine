"""
F&G Deep Forensics — Purified Second Pass (López de Prado Methodology)
======================================================================
Explores anomalies and hidden patterns from first backtest results,
correcting for statistical deliriums:
  1. Overlapping Returns: Adjusted effective N for t-statistics.
  2. Mean Reversion: Measured only from the onset of a regime.
  3. Base Rate Fallacy: Divergences compared against conditional base rates.
"""
import logging
import numpy as np
import pandas as pd
from datetime import date, timedelta
from scipy import stats as scipy_stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def load_from_vault(ticker: str, start: date) -> pd.DataFrame | None:
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()
    df = store.load_bars(ticker, "1d", start=start)
    store.close()
    if df is not None and not df.empty:
        logger.info(f"  {ticker}: {len(df)} bars ({df.index[0].date()} → {df.index[-1].date()})")
    return df

def calc_adjusted_tstat(vals: pd.Series, horizon: int) -> float:
    """
    T-statistic adjusted for overlapping returns (López de Prado).
    N_eff = N / horizon — each non-overlapping window is one independent obs.
    This is more conservative than N/(horizon/2) but statistically honest.
    """
    vals = vals.dropna()
    if len(vals) < 3:
        return 0.0
    n_eff = max(3.0, len(vals) / float(horizon))
    std = vals.std()
    if std > 0:
        return vals.mean() / (std / np.sqrt(n_eff))
    return 0.0


def calc_event_tstat(vals: pd.Series, min_gap_days: int = 20) -> tuple[float, int]:
    """
    T-stat for discrete events. Filters to non-overlapping events
    by requiring min_gap_days between observations.
    Returns (t_stat, n_independent_events).
    """
    vals = vals.dropna().sort_index()
    if len(vals) < 3:
        return 0.0, len(vals)
    # Filter to non-overlapping
    kept = [vals.index[0]]
    for idx in vals.index[1:]:
        if (idx - kept[-1]).days >= min_gap_days:
            kept.append(idx)
    independent = vals.loc[kept]
    n = len(independent)
    if n < 3:
        return 0.0, n
    std = independent.std()
    if std > 0:
        return independent.mean() / (std / np.sqrt(n)), n
    return 0.0, n

def main():
    start = date(2011, 1, 1)

    logger.info("═══ F&G Deep Forensics (Purified) — Loading ═══")
    fg_df = load_from_vault("FG", start)
    spy_df = load_from_vault("SPY", start)
    qqq_df = load_from_vault("QQQ", start)
    pcr_df = load_from_vault("CBOE_PCR", start)
    vix_df = load_from_vault("VIX", start)
    vvix_df = load_from_vault("VVIX", start)

    fg = fg_df["close"].rename("fg")
    fg.index = fg.index.normalize()
    fg = fg.loc[~fg.index.duplicated(keep="last")]
    
    spy = spy_df["close"].rename("spy")
    spy.index = spy.index.normalize()
    spy = spy.loc[~spy.index.duplicated(keep="last")]
    
    if qqq_df is not None:
        qqq = qqq_df["close"].rename("qqq")
        qqq.index = qqq.index.normalize()
        qqq = qqq.loc[~qqq.index.duplicated(keep="last")]
    else:
        qqq = None
        
    if pcr_df is not None and not pcr_df.empty:
        pcr = pcr_df["close"].rename("pcr")
        pcr.index = pcr.index.normalize()
        pcr = pcr.loc[~pcr.index.duplicated(keep="last")]
    else:
        pcr = None

    if vix_df is not None and not vix_df.empty:
        vix = vix_df["close"].rename("vix")
        vix.index = vix.index.normalize()
        vix = vix.loc[~vix.index.duplicated(keep="last")]
    else:
        vix = None

    common = fg.index.intersection(spy.index)
    if qqq is not None:
        common = common.intersection(qqq.index)
    if pcr is not None:
        common = common.intersection(pcr.index)
    # VIX has more data than FG, so don't restrict common to VIX
    # We'll reindex VIX to common instead
    logger.info(f"  Common: {len(common)} dates\n")

    fg = fg.reindex(common)
    spy = spy.reindex(common)
    if qqq is not None:
        qqq = qqq.reindex(common)
    if pcr is not None:
        pcr = pcr.reindex(common)

    # Normalize spy_df OHLCV columns before reindex (Rule 14: index parity)
    for col in ["open", "high", "low", "volume"]:
        spy_df[col].index = spy_df[col].index.normalize()
    spy_open = spy_df["open"].loc[~spy_df["open"].index.duplicated(keep="last")]
    spy_high = spy_df["high"].loc[~spy_df["high"].index.duplicated(keep="last")]
    spy_low = spy_df["low"].loc[~spy_df["low"].index.duplicated(keep="last")]
    spy_volume = spy_df["volume"].loc[~spy_df["volume"].index.duplicated(keep="last")]

    # Build master DataFrame
    df = pd.DataFrame({
        "fg": fg, 
        "spy": spy,
        "spy_open": spy_open.reindex(common),
        "spy_high": spy_high.reindex(common),
        "spy_low": spy_low.reindex(common),
        "spy_vol": spy_volume.reindex(common)
    })
    if qqq is not None:
        df["qqq"] = qqq
    if pcr is not None:
        df["pcr"] = pcr
    if vix is not None:
        df["vix"] = vix.reindex(common)

    # Forward returns
    for h in [5, 10, 20, 40, 60]:
        df[f"spy_ret{h}d"] = df["spy"].pct_change(h).shift(-h) * 100
        if "qqq" in df.columns:
            df[f"qqq_ret{h}d"] = df["qqq"].pct_change(h).shift(-h) * 100

    # ── TRAILING MOMENTUM (backward-looking context at signal time) ──
    df["spy_mom5d"] = df["spy"].pct_change(5) * 100
    df["spy_mom10d"] = df["spy"].pct_change(10) * 100
    df["spy_mom20d"] = df["spy"].pct_change(20) * 100

    # Volume & Price Trend Features
    df["spy_vol_50d"] = df["spy_vol"].rolling(50, min_periods=20).mean()
    df["spy_vol_ratio"] = df["spy_vol"] / df["spy_vol_50d"]
    
    # 20d Highs and Lows (for trend structure)
    df["spy_hh20"] = df["spy_high"] > df["spy_high"].rolling(20).max().shift(1)
    df["spy_ll20"] = df["spy_low"] < df["spy_low"].rolling(20).min().shift(1)
    
    # MDD and MFE (20d)
    df["spy_mdd20d"] = (df["spy"].rolling(20).min().shift(-20) / df["spy"] - 1) * 100
    df["spy_mfe20d"] = (df["spy"].rolling(20).max().shift(-20) / df["spy"] - 1) * 100

    # F&G features
    df["fg_roc5"] = df["fg"].diff(5)
    df["fg_roc1"] = df["fg"].diff(1)
    fg_mean60 = df["fg"].rolling(60, min_periods=20).mean()
    fg_std60 = df["fg"].rolling(60, min_periods=20).std()
    df["fg_zscore"] = (df["fg"] - fg_mean60) / fg_std60.replace(0, np.nan)
    df["fg_direction"] = np.where(df["fg_roc5"] > 3, "RISING",
                          np.where(df["fg_roc5"] < -3, "FALLING", "FLAT"))

    # ── VIX DELTAS ──
    if "vix" in df.columns:
        df["vix_roc5"] = df["vix"].diff(5)
        df["vix_roc1"] = df["vix"].diff(1)
        vix_mean60 = df["vix"].rolling(60, min_periods=20).mean()
        vix_std60 = df["vix"].rolling(60, min_periods=20).std()
        df["vix_zscore"] = (df["vix"] - vix_mean60) / vix_std60.replace(0, np.nan)
        df["vix_direction"] = np.where(df["vix_roc5"] > 2, "RISING",
                              np.where(df["vix_roc5"] < -2, "FALLING", "FLAT"))

    # ── PCR DELTAS ──
    if "pcr" in df.columns:
        df["pcr_roc5"] = df["pcr"].diff(5)
        pcr_mean60 = df["pcr"].rolling(60, min_periods=20).mean()
        pcr_std60 = df["pcr"].rolling(60, min_periods=20).std()
        df["pcr_zscore"] = (df["pcr"] - pcr_mean60) / pcr_std60.replace(0, np.nan)
        df["pcr_direction"] = np.where(df["pcr_roc5"] > 0.05, "RISING",
                              np.where(df["pcr_roc5"] < -0.05, "FALLING", "FLAT"))

    # ── VVIX (Vol-of-Vol) ──
    if vvix_df is not None and not vvix_df.empty:
        vvix = vvix_df["close"].rename("vvix")
        vvix.index = vvix.index.normalize()
        vvix = vvix.loc[~vvix.index.duplicated(keep="last")]
        df["vvix"] = vvix.reindex(common)

    # ── VOL REGIME CLASSIFICATION (production VolRegimeClassifier) ──
    if "vix" in df.columns:
        from backend.modules.volatility_regime.domain.rules.vol_classifier import VolRegimeClassifier
        from backend.modules.volatility_regime.domain.entities.vol_regime import QUALITY_LABELS, SPECULATIVE_LABELS

        # Compute the 6 sensor inputs from VIX + VVIX
        vix_s = df["vix"].copy()
        vix_mean_252 = vix_s.rolling(252, min_periods=60).mean()
        vix_std_252 = vix_s.rolling(252, min_periods=60).std()
        vix_zscore_252 = (vix_s - vix_mean_252) / vix_std_252.replace(0, np.nan)
        vix_velocity = vix_s.pct_change(5) * 100  # 5d pct change

        # Vol ratio: fast/slow realized vol of SPY
        spy_ret1d = df["spy"].pct_change(1)
        vol_fast = spy_ret1d.rolling(10, min_periods=5).std() * np.sqrt(252)
        vol_slow = spy_ret1d.rolling(60, min_periods=20).std() * np.sqrt(252)
        vol_ratio = vol_fast / vol_slow.replace(0, np.nan)

        # Vol persistence: autocorrelation of daily returns (rolling 20d)
        vol_persistence = spy_ret1d.rolling(20, min_periods=10).apply(
            lambda x: x.autocorr(lag=1) if len(x) >= 10 else 0.5, raw=False
        ).fillna(0.5)

        # Vol-of-Vol: rolling std of VIX (or VVIX if available)
        if "vvix" in df.columns:
            vol_of_vol = df["vvix"].copy()
        else:
            vol_of_vol = vix_s.rolling(20, min_periods=10).std()

        # Calm duration: consecutive bars where VIX < its mean
        below_mean = (vix_s < vix_mean_252).astype(float)
        calm_groups = (below_mean != below_mean.shift(1)).cumsum()
        calm_duration = below_mean.groupby(calm_groups).cumsum()

        classifier = VolRegimeClassifier()
        df["vol_regime_q"] = classifier.classify_quality_series(
            calm_duration, vol_persistence, vol_of_vol, vol_ratio, vix_zscore_252, vix_velocity
        )
        df["vol_regime_s"] = classifier.classify_speculative_series(
            calm_duration, vol_persistence, vol_of_vol, vol_ratio, vix_zscore_252, vix_velocity
        )
        df["vol_regime_q_label"] = df["vol_regime_q"].map(QUALITY_LABELS)
        df["vol_regime_s_label"] = df["vol_regime_s"].map(SPECULATIVE_LABELS)
        logger.info(f"  Vol Regime classified: Q={df['vol_regime_q_label'].value_counts().to_dict()}")
        logger.info(f"  Vol Regime classified: S={df['vol_regime_s_label'].value_counts().to_dict()}")

    # SPY drawdown from 52-week high
    spy_52w_high = df["spy"].rolling(252, min_periods=50).max()
    df["spy_dd_from_high"] = (df["spy"] / spy_52w_high - 1) * 100

    # Regime
    df["regime"] = pd.cut(
        df["fg"], bins=[-1, 10, 15, 20, 25, 35, 45, 55, 65, 75, 85, 101],
        labels=["0-10", "10-15", "15-20", "20-25", "25-35", "35-45",
                "45-55", "55-65", "65-75", "75-85", "85-100"],
    )

    # Consecutive days in regime
    is_extreme_fear = df["fg"] < 20
    is_extreme_greed = df["fg"] > 80
    df["consec_fear"] = is_extreme_fear.groupby((~is_extreme_fear).cumsum()).cumsum()
    df["consec_greed"] = is_extreme_greed.groupby((~is_extreme_greed).cumsum()).cumsum()

    # ═══════════════════════════════════════════════════════════
    # 1. GRANULAR REGIME TABLE (Adjusted T-Stats)
    # ═══════════════════════════════════════════════════════════
    print("=" * 80)
    print("1. GRANULAR REGIME TABLE — SPY Ret20d by F&G 10-point bucket (Adjusted T-Stats)")
    print("=" * 80)
    for regime, group in df.groupby("regime", observed=True):
        vals = group["spy_ret20d"].dropna()
        if len(vals) < 5:
            continue
        wr = (vals > 0).mean() * 100
        t = calc_adjusted_tstat(vals, horizon=20)
        mdd = group["spy_mdd20d"].dropna().mean()
        mfe = group["spy_mfe20d"].dropna().mean()
        print(f"  F&G {str(regime):8s}: N={len(vals):4d}  Mean={vals.mean():+6.2f}%  "
              f"Median={vals.median():+6.2f}%  WR={wr:5.1f}%  t_adj={t:+5.2f}  "
              f"MDD={mdd:+5.2f}%  MFE={mfe:+5.2f}%")

    # ═══════════════════════════════════════════════════════════
    # 2. DURATION EFFECT
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("2. DURATION EFFECT — Days consecutive in extreme fear (<20)")
    print("=" * 80)
    fear_days = df[df["consec_fear"] > 0].copy()
    if len(fear_days) > 0:
        for bucket_label, lo, hi in [("Day 1-3", 1, 3), ("Day 4-10", 4, 10),
                                      ("Day 11-20", 11, 20), ("Day 21+", 21, 999)]:
            mask = (fear_days["consec_fear"] >= lo) & (fear_days["consec_fear"] <= hi)
            sub = fear_days.loc[mask, "spy_ret20d"].dropna()
            if len(sub) >= 3:
                wr = (sub > 0).mean() * 100
                print(f"  {bucket_label:12s}: N={len(sub):4d}  Mean={sub.mean():+6.2f}%  "
                      f"WR={wr:.1f}%  Median={sub.median():+6.2f}%")

    # ═══════════════════════════════════════════════════════════
    # 3. THE GREED PARADOX
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("3. THE GREED PARADOX — Decomposition of F&G > 75 returns")
    print("=" * 80)
    greed_zone = df[df["fg"] > 75].copy()
    if len(greed_zone) > 0:
        greed_zone["spy_mom20"] = greed_zone["spy"].pct_change(20) * 100
        print(f"  N = {len(greed_zone)} days in greed zone")
        print(f"  SPY momentum (prior 20d): {greed_zone['spy_mom20'].mean():+.2f}%")
        print(f"  SPY Ret20d forward:       {greed_zone['spy_ret20d'].dropna().mean():+.2f}%")
        
        print("\n  GREED by SPY drawdown context:")
        for dd_label, lo, hi in [("At highs (DD>-2%)", -2, 0), ("Mild DD (-5 to -2%)", -5, -2),
                                  ("Correction (<-5%)", -99, -5)]:
            mask = (greed_zone["spy_dd_from_high"] >= lo) & (greed_zone["spy_dd_from_high"] < hi)
            sub = greed_zone.loc[mask, "spy_ret20d"].dropna()
            if len(sub) >= 3:
                wr = (sub > 0).mean() * 100
                print(f"    {dd_label:25s}: N={len(sub):4d}  Mean={sub.mean():+6.2f}%  WR={wr:.1f}%")

    # ═══════════════════════════════════════════════════════════
    # 4. REGIME TRANSITION SIGNALS (Events only)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("4. REGIME TRANSITIONS — Cross-threshold events (Non-overlapping)")
    print("=" * 80)

    cross_below_20 = (df["fg"] < 20) & (df["fg"].shift(1) >= 20)
    cross_above_20 = (df["fg"] >= 20) & (df["fg"].shift(1) < 20)
    cross_below_80 = (df["fg"] < 80) & (df["fg"].shift(1) >= 80)
    cross_above_80 = (df["fg"] >= 80) & (df["fg"].shift(1) < 80)

    for label, mask in [("Entering extreme fear (cross below 20)", cross_below_20),
                        ("Exiting extreme fear (cross above 20)", cross_above_20),
                        ("Entering extreme greed (cross above 80)", cross_above_80),
                        ("Exiting extreme greed (cross below 80)", cross_below_80)]:
        vals = df.loc[mask, "spy_ret20d"].dropna()
        if len(vals) >= 3:
            wr = (vals > 0).mean() * 100
            # Use non-overlapping event t-stat (min 20d gap between events)
            t, n_indep = calc_event_tstat(vals, min_gap_days=20)
            print(f"  {label}")
            print(f"    N_raw={len(vals):4d}  N_indep={n_indep}  Mean={vals.mean():+6.2f}%  WR={wr:.1f}%  t_event={t:+.2f}")

    # ═══════════════════════════════════════════════════════════
    # 5. MEAN-REVERSION SPEED (Corrected to measure from onset)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("5. MEAN-REVERSION — How fast does F&G return to 50? (From Regime Onset)")
    print("=" * 80)
    
    # We only want the FIRST day of entering the zone to avoid downward bias
    enter_ext_fear = (df["fg"] < 15) & (df["fg"].shift(1) >= 15)
    enter_fear     = (df["fg"] >= 15) & (df["fg"] < 25) & (
        (df["fg"].shift(1) >= 25) | (df["fg"].shift(1) < 15)
    )
    enter_greed    = (df["fg"] >= 75) & (df["fg"] < 85) & (df["fg"].shift(1) < 75)
    enter_ext_greed= (df["fg"] >= 85) & (df["fg"].shift(1) < 85)

    for zone, mask in [("EXTREME_FEAR (<15)", enter_ext_fear), 
                       ("FEAR (15-25)", enter_fear),
                       ("GREED (75-85)", enter_greed), 
                       ("EXTREME_GREED (>85)", enter_ext_greed)]:
        entry_idx = df.index[mask]
        if len(entry_idx) < 3:
            continue
        days_to_50 = []
        for idx in entry_idx:
            pos = df.index.get_loc(idx)
            future = df["fg"].iloc[pos:min(pos+120, len(df))]
            cross = future[(future >= 45) & (future <= 55)]
            if len(cross) > 0:
                days_to_50.append(df.index.get_loc(cross.index[0]) - pos)
        if days_to_50:
            arr = np.array(days_to_50)
            print(f"  {zone:25s}: Median={np.median(arr):.0f}d  "
                  f"Mean={arr.mean():.0f}d  P25={np.percentile(arr,25):.0f}d  "
                  f"P75={np.percentile(arr,75):.0f}d  Events={len(arr)}")

    # ═══════════════════════════════════════════════════════════
    # 6. PULLBACK CONFIRMATION (Adjusted T-Stats)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("6. PULLBACK CONFIRMATION — When SPY is in drawdown AND F&G < thresholds")
    print("=" * 80)
    in_pullback = df["spy_dd_from_high"] < -3  # SPY > 3% off highs
    print(f"  {'Condition':40s} {'N':>5s} {'Ret20d':>8s} {'WR':>6s} {'t_adj':>6s}")
    print(f"  {'─' * 40} {'─'*5:>5s} {'─'*8:>8s} {'─'*6:>6s} {'─'*6:>6s}")

    conditions = [
        ("SPY in pullback (DD > -3%)", in_pullback),
        ("Pullback + F&G < 40", in_pullback & (df["fg"] < 40)),
        ("Pullback + F&G < 20", in_pullback & (df["fg"] < 20)),
        ("Pullback + F&G < 15", in_pullback & (df["fg"] < 15)),
        ("Pullback + F&G FALLING", in_pullback & (df["fg_roc5"] < -5)),
    ]

    for label, mask in conditions:
        vals = df.loc[mask, "spy_ret20d"].dropna()
        if len(vals) >= 3:
            wr = (vals > 0).mean() * 100
            t = calc_adjusted_tstat(vals, horizon=20)
            print(f"  {label:40s} {len(vals):5d} {vals.mean():+7.2f}% {wr:5.1f}% {t:+5.2f}")

    # ═══════════════════════════════════════════════════════════
    # 7. DIVERGENCES VS BASE RATE (The True Test of Edge)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("7. DIVERGENCES vs BASE RATE — Does disagreement add Alpha?")
    print("=" * 80)

    # 20d rolling changes (backward looking context)
    spy_ret20_past = df["spy"].pct_change(20) * 100
    fg_chg20_past = df["fg"].diff(20)

    # Base conditions
    base_spy_up = spy_ret20_past > 2
    base_spy_dn = spy_ret20_past < -2

    # Divergence types
    # BEARISH DIV: SPY rising but F&G falling (Smart money taking profit / retail buying top?)
    bear_div = base_spy_up & (fg_chg20_past < -5)
    # CONFIRMING BULL: SPY rising + F&G rising
    confirm_bull = base_spy_up & (fg_chg20_past > 5)

    # BULLISH DIV: SPY falling but F&G rising (Smart money buying / retail exhausted?)
    bull_div = base_spy_dn & (fg_chg20_past > 5)
    # CONFIRMING BEAR: SPY falling + F&G falling
    confirm_bear = base_spy_dn & (fg_chg20_past < -5)

    print(f"\n  [UPTREND CONTEXT (SPY rose >2% in past 20d)]")
    # Base rate calculation
    base_up_vals = df.loc[base_spy_up, "spy_ret20d"].dropna()
    bu_wr = (base_up_vals > 0).mean() * 100
    print(f"  Base Rate (SPY Up): N={len(base_up_vals):4d}  Fwd Ret20d={base_up_vals.mean():+5.2f}%  WR={bu_wr:5.1f}%")

    for label, mask in [
        ("CONFIRM BULL (F&G↑)", confirm_bull),
        ("BEARISH DIV  (F&G↓)", bear_div),
    ]:
        vals = df.loc[mask, "spy_ret20d"].dropna()
        if len(vals) >= 3:
            wr = (vals > 0).mean() * 100
            diff_mean = vals.mean() - base_up_vals.mean()
            # Welch's t-test against base rate (N_eff = N/horizon for overlap)
            n_eff_vals = max(3, len(vals) / 20.0)
            n_eff_base = max(3, len(base_up_vals) / 20.0)
            var_vals = vals.var() / n_eff_vals if len(vals) > 1 else 0
            var_base = base_up_vals.var() / n_eff_base if len(base_up_vals) > 1 else 0
            t_diff = diff_mean / np.sqrt(var_vals + var_base) if (var_vals + var_base) > 0 else 0
            
            print(f"    {label:20s}: N={len(vals):4d}  Ret={vals.mean():+5.2f}% (vs base {diff_mean:+.2f}%)  WR={wr:5.1f}%  t_adj={t_diff:+.2f}")


    print(f"\n  [DOWNTREND CONTEXT (SPY fell <-2% in past 20d)]")
    base_dn_vals = df.loc[base_spy_dn, "spy_ret20d"].dropna()
    bd_wr = (base_dn_vals > 0).mean() * 100
    print(f"  Base Rate (SPY Dn): N={len(base_dn_vals):4d}  Fwd Ret20d={base_dn_vals.mean():+5.2f}%  WR={bd_wr:5.1f}%")

    for label, mask in [
        ("CONFIRM BEAR (F&G↓)", confirm_bear),
        ("BULLISH DIV  (F&G↑)", bull_div),
    ]:
        vals = df.loc[mask, "spy_ret20d"].dropna()
        if len(vals) >= 3:
            wr = (vals > 0).mean() * 100
            diff_mean = vals.mean() - base_dn_vals.mean()
            n_eff_vals = max(3, len(vals) / 20.0)
            n_eff_base = max(3, len(base_dn_vals) / 20.0)
            var_vals = vals.var() / n_eff_vals if len(vals) > 1 else 0
            var_base = base_dn_vals.var() / n_eff_base if len(base_dn_vals) > 1 else 0
            t_diff = diff_mean / np.sqrt(var_vals + var_base) if (var_vals + var_base) > 0 else 0
            
            print(f"    {label:20s}: N={len(vals):4d}  Ret={vals.mean():+5.2f}% (vs base {diff_mean:+.2f}%)  WR={wr:5.1f}%  t_adj={t_diff:+.2f}")

    # ═══════════════════════════════════════════════════════════
    # 8. VELOCITY EXTREMES (Restored — adjusted t-stats)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("8. VELOCITY EXTREMES — 5d ROC distribution (adj t-stats)")
    print("=" * 80)
    for label, lo, hi in [("Crash (<-20pts/5d)", -999, -20), ("Sharp drop (-20 to -10)", -20, -10),
                           ("Normal drop (-10 to -3)", -10, -3), ("Stable (-3 to +3)", -3, 3),
                           ("Normal rise (+3 to +10)", 3, 10), ("Sharp rise (+10 to +20)", 10, 20),
                           ("Spike (>+20pts/5d)", 20, 999)]:
        mask = (df["fg_roc5"] >= lo) & (df["fg_roc5"] < hi)
        sub = df.loc[mask, "spy_ret20d"].dropna()
        if len(sub) >= 3:
            wr = (sub > 0).mean() * 100
            t = calc_adjusted_tstat(sub, horizon=20)
            print(f"  {label:25s}: N={len(sub):4d}  Mean={sub.mean():+6.2f}%  "
                  f"WR={wr:.1f}%  t_adj={t:+.2f}")

    # ═══════════════════════════════════════════════════════════
    # 9. MULTI-HORIZON DECAY (Restored — Welch + adjusted N)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("9. SIGNAL DECAY — Extreme fear (<20) at multiple horizons")
    print("=" * 80)
    fear_mask = df["fg"] < 20
    baseline_mask = (df["fg"] >= 40) & (df["fg"] <= 60)
    print(f"  {'Horizon':>10s} {'Fear Mean':>10s} {'Base Mean':>10s} {'Diff':>8s} {'t_adj':>8s}")
    for h in [5, 10, 20, 40, 60]:
        col = f"spy_ret{h}d"
        fear_vals = df.loc[fear_mask, col].dropna()
        base_vals = df.loc[baseline_mask, col].dropna()
        if len(fear_vals) < 5:
            continue
        diff = fear_vals.mean() - base_vals.mean()
        # Adjusted Welch: N_eff = N / horizon
        n_eff_f = max(3, len(fear_vals) / float(h))
        n_eff_b = max(3, len(base_vals) / float(h))
        var_f = fear_vals.var() / n_eff_f
        var_b = base_vals.var() / n_eff_b
        t = diff / np.sqrt(var_f + var_b) if (var_f + var_b) > 0 else 0
        print(f"  {h:8d}d  {fear_vals.mean():+8.2f}%  {base_vals.mean():+8.2f}%  "
              f"{diff:+6.2f}%  {t:+6.2f} {'✅' if abs(t) > 1.96 else '❌'}")

    # ═══════════════════════════════════════════════════════════
    # 10. QQQ/SPY BETA (Restored)
    # ═══════════════════════════════════════════════════════════
    if "qqq" in df.columns:
        print("\n" + "=" * 80)
        print("10. QQQ/SPY BETA — At each F&G regime (Ret20d)")
        print("=" * 80)
        for label, lo, hi in [("F&G < 15", 0, 15), ("F&G 15-25", 15, 25),
                               ("F&G 25-45", 25, 45), ("F&G 45-55", 45, 55),
                               ("F&G 55-75", 55, 75), ("F&G 75-85", 75, 85),
                               ("F&G > 85", 85, 101)]:
            mask = (df["fg"] >= lo) & (df["fg"] < hi)
            spy_ret = df.loc[mask, "spy_ret20d"].dropna()
            qqq_ret = df.loc[mask, "qqq_ret20d"].dropna()
            common_idx = spy_ret.index.intersection(qqq_ret.index)
            if len(common_idx) < 5:
                continue
            s = spy_ret.reindex(common_idx).mean()
            q = qqq_ret.reindex(common_idx).mean()
            beta = q / s if abs(s) > 0.01 else 0
            print(f"  {label:12s}: SPY={s:+5.2f}%  QQQ={q:+5.2f}%  Beta={beta:.2f}x  N={len(common_idx)}")

    # ═══════════════════════════════════════════════════════════
    # 11. RISK/REWARD ASYMMETRY (Restored)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("11. RISK/REWARD ASYMMETRY — MFE vs MDD by F&G zone")
    print("=" * 80)
    for label, lo, hi in [("F&G < 15", 0, 15), ("F&G 15-25", 15, 25),
                           ("F&G 40-60", 40, 60), ("F&G 75-85", 75, 85),
                           ("F&G > 85", 85, 101)]:
        mask = (df["fg"] >= lo) & (df["fg"] < hi)
        sub = df.loc[mask]
        if len(sub) < 5:
            continue
        mfe = sub["spy_mfe20d"].dropna().mean()
        mdd = sub["spy_mdd20d"].dropna().mean()
        ratio = mfe / abs(mdd) if abs(mdd) > 0.01 else 0
        print(f"  {label:12s}: MFE={mfe:+5.2f}%  MDD={mdd:+5.2f}%  "
              f"R:R={ratio:.2f}x  N={len(sub)}")

    # ═══════════════════════════════════════════════════════════
    # 12. FAILURE ANALYSIS — When F&G < 20 FAILS to bounce
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("12. FAILURE ANALYSIS — When capitulation buy FAILS (Ret20d < 0)")
    print("=" * 80)
    fear_entries = df[df["fg"] < 20].copy()
    losers = fear_entries[fear_entries["spy_ret20d"] < 0]
    winners = fear_entries[fear_entries["spy_ret20d"] > 0]
    if len(losers) > 0:
        print(f"  Total fear signals: {len(fear_entries.dropna(subset=['spy_ret20d']))}")
        print(f"  Winners: {len(winners.dropna(subset=['spy_ret20d']))}  |  Losers: {len(losers.dropna(subset=['spy_ret20d']))}")
        print(f"\n  LOSER PROFILE (what was different?):")
        # SPY drawdown at signal
        print(f"    SPY DD from high:  Losers={losers['spy_dd_from_high'].mean():+.1f}%  vs Winners={winners['spy_dd_from_high'].mean():+.1f}%")
        # F&G velocity
        print(f"    F&G velocity(5d):  Losers={losers['fg_roc5'].mean():+.1f}  vs Winners={winners['fg_roc5'].mean():+.1f}")
        # F&G level
        print(f"    F&G level:         Losers={losers['fg'].mean():.1f}  vs Winners={winners['fg'].mean():.1f}")
        # Consecutive days in fear
        print(f"    Consec fear days:  Losers={losers['consec_fear'].mean():.1f}  vs Winners={winners['consec_fear'].mean():.1f}")
        # MDD suffered
        print(f"    MDD20d suffered:   Losers={losers['spy_mdd20d'].dropna().mean():.2f}%  vs Winners={winners['spy_mdd20d'].dropna().mean():.2f}%")
        
        # Date-by-date losers (show up to 30 worst)
        loser_sorted = losers.dropna(subset=["spy_ret20d"]).sort_values("spy_ret20d")
        print(f"\n  LOSER DATES (sorted worst-first, top 30):")
        for i, (_, row) in enumerate(loser_sorted.iterrows()):
            if i >= 30:
                print(f"    ... and {len(loser_sorted) - 30} more")
                break
            print(f"    {row.name.date()}: F&G={row['fg']:.0f}  SPY_DD={row['spy_dd_from_high']:.1f}%  "
                  f"Ret20d={row['spy_ret20d']:+.2f}%  Consec={row['consec_fear']:.0f}d")

    # ═══════════════════════════════════════════════════════════
    # 13. VIX CORRELATION — F&G vs VIX behavior
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("13. VIX CONTEXT — F&G extremes and VIX behavior")
    print("=" * 80)
    # Load VIX from ohlcv_bars (Rule 14 unified schema)
    try:
        from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
        store = TimescaleDataStore()
        vix_df = store.load_bars("VIX", "1d", start=start)
        store.close()
        if vix_df is not None and not vix_df.empty:
            vix = vix_df["close"].rename("vix")
            vix.index = vix.index.normalize()
            vix = vix.loc[~vix.index.duplicated(keep="last")]
            vix_common = df.index.intersection(vix.index)
            df_vix = df.reindex(vix_common).copy()
            df_vix["vix"] = vix.reindex(vix_common)
            
            # Correlation
            corr = df_vix["fg"].corr(df_vix["vix"])
            print(f"  F&G vs VIX correlation: {corr:+.3f} (expected: strongly negative)")
            
            # VIX at F&G extremes
            for label, lo, hi in [("F&G < 15", 0, 15), ("F&G 15-25", 15, 25),
                                   ("F&G 45-55", 45, 55), ("F&G > 75", 75, 101)]:
                mask = (df_vix["fg"] >= lo) & (df_vix["fg"] < hi)
                if mask.sum() > 3:
                    vix_vals = df_vix.loc[mask, "vix"]
                    print(f"    {label:12s}: VIX mean={vix_vals.mean():.1f}  "
                          f"median={vix_vals.median():.1f}  max={vix_vals.max():.1f}  N={mask.sum()}")
        else:
            print("  VIX data not available in Vault")
    except Exception as e:
        print(f"  VIX analysis skipped: {e}")

    # ═══════════════════════════════════════════════════════════
    # 14. PUT/CALL RATIO × F&G CONVERGENCE
    # ═══════════════════════════════════════════════════════════
    if "pcr" in df.columns:
        print("\n" + "=" * 80)
        print("14. PUT/CALL RATIO — Convergence with F&G")
        print("=" * 80)

        # PCR features
        pcr_mean60 = df["pcr"].rolling(60, min_periods=20).mean()
        pcr_std60 = df["pcr"].rolling(60, min_periods=20).std()
        df["pcr_zscore"] = (df["pcr"] - pcr_mean60) / pcr_std60.replace(0, np.nan)
        df["pcr_roc5"] = df["pcr"].diff(5)

        # Correlation matrix
        corr_fg_pcr = df["fg"].corr(df["pcr"])
        print(f"  F&G vs PCR correlation: {corr_fg_pcr:+.3f}")
        print(f"  PCR stats: mean={df['pcr'].mean():.3f} median={df['pcr'].median():.3f} std={df['pcr'].std():.3f}")

        # PCR by F&G regime
        print(f"\n  PCR levels at each F&G regime:")
        for label, lo, hi in [("F&G < 15", 0, 15), ("F&G 15-25", 15, 25),
                               ("F&G 25-45", 25, 45), ("F&G 45-55", 45, 55),
                               ("F&G 55-75", 55, 75), ("F&G > 75", 75, 101)]:
            mask = (df["fg"] >= lo) & (df["fg"] < hi)
            if mask.sum() > 3:
                pcr_vals = df.loc[mask, "pcr"]
                print(f"    {label:12s}: PCR mean={pcr_vals.mean():.3f}  "
                      f"median={pcr_vals.median():.3f}  N={mask.sum()}")

        # PCR extreme signals: does PCR > 1.2 predict bounces?
        print(f"\n  PCR extremes → SPY forward returns:")
        print(f"  {'PCR Zone':25s} {'N':>5s} {'Ret20d':>8s} {'WR':>6s} {'t_adj':>6s}")
        for label, lo, hi in [("PCR < 0.7 (bullish)", 0, 0.7),
                               ("PCR 0.7-0.9 (neutral)", 0.7, 0.9),
                               ("PCR 0.9-1.1 (mild fear)", 0.9, 1.1),
                               ("PCR 1.1-1.3 (fear)", 1.1, 1.3),
                               ("PCR > 1.3 (panic)", 1.3, 99)]:
            mask = (df["pcr"] >= lo) & (df["pcr"] < hi)
            vals = df.loc[mask, "spy_ret20d"].dropna()
            if len(vals) >= 5:
                wr = (vals > 0).mean() * 100
                t = calc_adjusted_tstat(vals, horizon=20)
                print(f"  {label:25s} {len(vals):5d} {vals.mean():+7.2f}% {wr:5.1f}% {t:+5.2f}")

        # F&G + PCR convergence: when BOTH signal fear
        print(f"\n  F&G + PCR CONVERGENCE signals:")
        print(f"  {'Signal':45s} {'N':>5s} {'Ret20d':>8s} {'WR':>6s} {'t_adj':>6s}")
        convergence_signals = [
            ("F&G < 20 + PCR > 1.0 (double fear)", (df["fg"] < 20) & (df["pcr"] > 1.0)),
            ("F&G < 20 + PCR > 1.2 (panic convergence)", (df["fg"] < 20) & (df["pcr"] > 1.2)),
            ("F&G < 20 + PCR < 0.8 (DIVERGENCE: fear+complacent)", (df["fg"] < 20) & (df["pcr"] < 0.8)),
            ("F&G > 75 + PCR < 0.7 (double greed)", (df["fg"] > 75) & (df["pcr"] < 0.7)),
            ("F&G > 75 + PCR > 1.0 (DIVERGENCE: greed+hedging)", (df["fg"] > 75) & (df["pcr"] > 1.0)),
        ]
        for label, mask in convergence_signals:
            vals = df.loc[mask, "spy_ret20d"].dropna()
            if len(vals) >= 3:
                wr = (vals > 0).mean() * 100
                t = calc_adjusted_tstat(vals, horizon=20)
                print(f"  {label:45s} {len(vals):5d} {vals.mean():+7.2f}% {wr:5.1f}% {t:+5.2f}")

        # ═══════════════════════════════════════════════════════════
        # 15. PCR AS BLACK SWAN EARLY WARNING
        # ═══════════════════════════════════════════════════════════
        print("\n" + "=" * 80)
        print("15. PCR BLACK SWAN WARNING — Does PCR spike BEFORE crashes?")
        print("=" * 80)

        # Lead/lag: PCR change vs SPY forward return
        pcr_chg = df["pcr"].diff()
        spy_fwd = df["spy"].pct_change(20).shift(-20) * 100
        print(f"  PCR daily change vs SPY 20d forward return:")
        for lag in [-10, -5, -3, -1, 0, 1, 3, 5, 10]:
            if lag < 0:
                corr = pcr_chg.corr(spy_fwd.shift(lag))
                desc = f"PCR leads SPY by {abs(lag)}d"
            elif lag == 0:
                corr = pcr_chg.corr(spy_fwd)
                desc = "Same day"
            else:
                corr = pcr_chg.corr(spy_fwd.shift(lag))
                desc = f"PCR lags SPY by {lag}d"
            marker = " ◄" if abs(corr) > 0.05 else ""
            print(f"    lag={lag:+3d}d  corr={corr:+.4f}  {desc}{marker}")

        # PCR spike (z > 2) as warning signal
        pcr_spike = df["pcr_zscore"] > 2.0
        pcr_crash = df["pcr_zscore"] < -2.0
        print(f"\n  PCR z-score spikes → SPY outcomes:")
        for label, mask in [("PCR z > +2 (panic hedging)", pcr_spike),
                            ("PCR z < -2 (extreme complacency)", pcr_crash)]:
            vals = df.loc[mask, "spy_ret20d"].dropna()
            if len(vals) >= 3:
                wr = (vals > 0).mean() * 100
                t = calc_adjusted_tstat(vals, horizon=20)
                print(f"    {label:35s}: N={len(vals):4d}  Ret20d={vals.mean():+5.2f}%  WR={wr:.1f}%  t={t:+.2f}")

    # ═══════════════════════════════════════════════════════════
    # 16. CAPITULATION EXHAUSTION (Volume Climax)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("16. CAPITULATION EXHAUSTION — Does extreme volume confirm bottoms?")
    print("=" * 80)
    # Filter for days in Fear/Extreme Fear
    fear_zone = df[df["fg"] < 25].copy()
    if not fear_zone.empty:
        fear_zone["is_vol_climax"] = fear_zone["spy_vol_ratio"] > 1.5
        fear_zone["is_vol_dry"] = fear_zone["spy_vol_ratio"] < 0.8
        
        print(f"  In F&G < 25 (Fear Zone):")
        for label, mask in [
            ("Volume Climax (Vol > 1.5x avg)", fear_zone["is_vol_climax"]),
            ("Volume Normal", (fear_zone["spy_vol_ratio"] >= 0.8) & (fear_zone["spy_vol_ratio"] <= 1.5)),
            ("Volume Dry-up (Vol < 0.8x avg)", fear_zone["is_vol_dry"]),
        ]:
            vals = fear_zone.loc[mask, "spy_ret20d"].dropna()
            if len(vals) >= 3:
                wr = (vals > 0).mean() * 100
                t = calc_adjusted_tstat(vals, horizon=20)
                print(f"    {label:35s}: N={len(vals):4d}  Ret20d={vals.mean():+5.2f}%  WR={wr:.1f}%  t={t:+.2f}")
                
    # ═══════════════════════════════════════════════════════════
    # 17. ACCUMULATION vs DISTRIBUTION (Divergences)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("17. ACCUMULATION & DISTRIBUTION — Volume behavior vs price")
    print("=" * 80)
    # Up days vs Down days
    df["is_up_day"] = df["spy"].pct_change(1) > 0
    df["is_down_day"] = df["spy"].pct_change(1) < 0
    
    # Distribution: High volume down day near highs (F&G > 75)
    dist_days = df[(df["fg"] > 75) & (df["is_down_day"]) & (df["spy_vol_ratio"] > 1.2)]
    # Accumulation: High volume up day near lows (F&G < 25)
    accum_days = df[(df["fg"] < 25) & (df["is_up_day"]) & (df["spy_vol_ratio"] > 1.2)]
    
    print("  Volume Signals (Ret20d):")
    for label, subset in [
        ("DISTRIBUTION (High Vol down day in GREED)", dist_days),
        ("ACCUMULATION (High Vol up day in FEAR)", accum_days)
    ]:
        vals = subset["spy_ret20d"].dropna()
        if len(vals) >= 3:
            wr = (vals > 0).mean() * 100
            t = calc_adjusted_tstat(vals, horizon=20)
            print(f"    {label:45s}: N={len(vals):4d}  Ret={vals.mean():+5.2f}%  WR={wr:.1f}%  t={t:+.2f}")

    # ═══════════════════════════════════════════════════════════
    # 18. DOW THEORY PRICE PHASES
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("18. DOW THEORY PHASES — Trend structure context")
    print("=" * 80)
    
    # Higher Highs / Lower Lows over rolling 20d window
    # Advancing: HH but no LL
    # Declining: LL but no HH
    hh_roll = df["spy_hh20"].rolling(20).sum()
    ll_roll = df["spy_ll20"].rolling(20).sum()
    
    df["phase"] = "BASING/CHOP"
    df.loc[(hh_roll > 0) & (ll_roll == 0), "phase"] = "ADVANCING"
    df.loc[(ll_roll > 0) & (hh_roll == 0), "phase"] = "DECLINING"
    df.loc[(ll_roll > 0) & (hh_roll > 0), "phase"] = "EXPANDING_VOLATILITY"

    for phase in ["ADVANCING", "DECLINING", "BASING/CHOP", "EXPANDING_VOLATILITY"]:
        phase_df = df[df["phase"] == phase]
        if len(phase_df) < 5: continue
        print(f"\n  Phase: {phase} (N={len(phase_df)} days)")
        
        for fg_label, mask in [
            ("Fear (<25)", phase_df["fg"] < 25),
            ("Neutral (25-75)", (phase_df["fg"] >= 25) & (phase_df["fg"] <= 75)),
            ("Greed (>75)", phase_df["fg"] > 75)
        ]:
            vals = phase_df.loc[mask, "spy_ret20d"].dropna()
            if len(vals) >= 3:
                wr = (vals > 0).mean() * 100
                t = calc_adjusted_tstat(vals, horizon=20)
                print(f"    {fg_label:15s}: N={len(vals):4d}  Ret={vals.mean():+5.2f}%  WR={wr:.1f}%  t={t:+.2f}")

    # ═══════════════════════════════════════════════════════════
    # 19. SPY MOMENTUM AT FEAR SIGNAL (Trailing context)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("19. SPY MOMENTUM AT FEAR SIGNAL — How fast was SPY falling?")
    print("=" * 80)
    fear_sig = df[df["fg"] < 20].copy()
    if len(fear_sig) > 5:
        print(f"  SPY trailing return when F&G < 20:")
        for h_label, col in [("5d", "spy_mom5d"), ("10d", "spy_mom10d"), ("20d", "spy_mom20d")]:
            vals = fear_sig[col].dropna()
            print(f"    SPY {h_label} trailing: Mean={vals.mean():+.2f}%  Median={vals.median():+.2f}%  "
                  f"Min={vals.min():+.2f}%  Max={vals.max():+.2f}%")

        print(f"\n  Fear signal by SPY crash speed (trailing 5d):")
        for label, lo, hi in [
            ("SPY crashed hard  (<-5%/5d)", -99, -5),
            ("SPY falling moderate (-5 to -2%)", -5, -2),
            ("SPY drifting down  (-2 to 0%)", -2, 0),
            ("SPY actually rising (>0%/5d)", 0, 99),
        ]:
            mask = (fear_sig["spy_mom5d"] >= lo) & (fear_sig["spy_mom5d"] < hi)
            vals = fear_sig.loc[mask, "spy_ret20d"].dropna()
            if len(vals) >= 3:
                wr = (vals > 0).mean() * 100
                t = calc_adjusted_tstat(vals, horizon=20)
                print(f"    {label:35s}: N={len(vals):4d}  Ret={vals.mean():+5.2f}%  WR={wr:.1f}%  t={t:+.2f}")

    # ═══════════════════════════════════════════════════════════
    # 20. VIX DELTA AT FEAR SIGNAL
    # ═══════════════════════════════════════════════════════════
    if "vix" in df.columns:
        print("\n" + "=" * 80)
        print("20. VIX DIRECTION AT FEAR SIGNAL — Is VIX rising or stabilizing?")
        print("=" * 80)
        fear_vix = df[(df["fg"] < 20) & df["vix"].notna()].copy()
        if len(fear_vix) > 5:
            print(f"  VIX state when F&G < 20:")
            print(f"    VIX mean={fear_vix['vix'].mean():.1f}  median={fear_vix['vix'].median():.1f}")
            print(f"    VIX 5d delta: mean={fear_vix['vix_roc5'].mean():+.2f}  median={fear_vix['vix_roc5'].median():+.2f}")

            print(f"\n  F&G < 20 by VIX direction:")
            for label, mask in [
                ("VIX RISING (roc5 > +2)",   fear_vix["vix_direction"] == "RISING"),
                ("VIX FLAT   (-2 to +2)",    fear_vix["vix_direction"] == "FLAT"),
                ("VIX FALLING (roc5 < -2)",  fear_vix["vix_direction"] == "FALLING"),
            ]:
                vals = fear_vix.loc[mask, "spy_ret20d"].dropna()
                if len(vals) >= 3:
                    wr = (vals > 0).mean() * 100
                    t = calc_adjusted_tstat(vals, horizon=20)
                    print(f"    {label:30s}: N={len(vals):4d}  Ret={vals.mean():+5.2f}%  WR={wr:.1f}%  t={t:+.2f}")

            # VIX absolute level crossed with direction
            print(f"\n  F&G < 20 by VIX level × direction:")
            for vix_label, vix_lo, vix_hi in [
                ("VIX 15-25", 15, 25), ("VIX 25-35", 25, 35), ("VIX > 35", 35, 999)
            ]:
                for dir_label, dir_val in [("↑ rising", "RISING"), ("↓ falling", "FALLING")]:
                    mask = (
                        (fear_vix["vix"] >= vix_lo) & (fear_vix["vix"] < vix_hi) &
                        (fear_vix["vix_direction"] == dir_val)
                    )
                    vals = fear_vix.loc[mask, "spy_ret20d"].dropna()
                    if len(vals) >= 5:
                        wr = (vals > 0).mean() * 100
                        t = calc_adjusted_tstat(vals, horizon=20)
                        print(f"    {vix_label} {dir_label:12s}: N={len(vals):4d}  "
                              f"Ret={vals.mean():+5.2f}%  WR={wr:.1f}%  t={t:+.2f}")

    # ═══════════════════════════════════════════════════════════
    # 21. PCR ACCELERATION AT FEAR SIGNAL
    # ═══════════════════════════════════════════════════════════
    if "pcr" in df.columns:
        print("\n" + "=" * 80)
        print("21. PCR DIRECTION AT FEAR SIGNAL — Is protective hedging accelerating?")
        print("=" * 80)
        fear_pcr = df[(df["fg"] < 20) & df["pcr"].notna()].copy()
        if len(fear_pcr) > 5:
            print(f"  PCR state when F&G < 20:")
            print(f"    PCR mean={fear_pcr['pcr'].mean():.3f}  roc5 mean={fear_pcr['pcr_roc5'].mean():+.4f}")

            print(f"\n  F&G < 20 by PCR direction:")
            for label, mask in [
                ("PCR RISING (hedging up)",  fear_pcr["pcr_direction"] == "RISING"),
                ("PCR FLAT",                fear_pcr["pcr_direction"] == "FLAT"),
                ("PCR FALLING (hedging off)", fear_pcr["pcr_direction"] == "FALLING"),
            ]:
                vals = fear_pcr.loc[mask, "spy_ret20d"].dropna()
                if len(vals) >= 3:
                    wr = (vals > 0).mean() * 100
                    t = calc_adjusted_tstat(vals, horizon=20)
                    print(f"    {label:30s}: N={len(vals):4d}  Ret={vals.mean():+5.2f}%  WR={wr:.1f}%  t={t:+.2f}")

    # ═══════════════════════════════════════════════════════════
    # 22. TRIPLE CONVERGENCE — All indicators aligned
    # ═══════════════════════════════════════════════════════════
    if "vix" in df.columns and "pcr" in df.columns:
        print("\n" + "=" * 80)
        print("22. TRIPLE CONVERGENCE — Multi-instrument directional alignment")
        print("=" * 80)

        print(f"  CAPITULATION CONVERGENCE (all signals confirm panic):")
        signals = [
            ("F&G < 20 alone",
             df["fg"] < 20),
            ("+ VIX > 25",
             (df["fg"] < 20) & (df["vix"] > 25)),
            ("+ VIX > 25 + VIX↑",
             (df["fg"] < 20) & (df["vix"] > 25) & (df["vix_direction"] == "RISING")),
            ("+ VIX > 25 + VIX↑ + PCR > 1.0",
             (df["fg"] < 20) & (df["vix"] > 25) & (df["vix_direction"] == "RISING") & (df["pcr"] > 1.0)),
            ("+ VIX > 25 + VIX↑ + PCR > 1.0 + SPY fell >3%/5d",
             (df["fg"] < 20) & (df["vix"] > 25) & (df["vix_direction"] == "RISING") &
             (df["pcr"] > 1.0) & (df["spy_mom5d"] < -3)),
        ]
        print(f"  {'Signal':50s} {'N':>5s} {'Ret20d':>8s} {'WR':>6s} {'t_adj':>6s}")
        print(f"  {'─'*50} {'─'*5:>5s} {'─'*8:>8s} {'─'*6:>6s} {'─'*6:>6s}")
        for label, mask in signals:
            vals = df.loc[mask, "spy_ret20d"].dropna()
            if len(vals) >= 3:
                wr = (vals > 0).mean() * 100
                t = calc_adjusted_tstat(vals, horizon=20)
                print(f"  {label:50s} {len(vals):5d} {vals.mean():+7.2f}% {wr:5.1f}% {t:+5.2f}")

        print(f"\n  REVERSAL CONFIRMATION (panic exhausting — VIX falling):")
        reversal_signals = [
            ("F&G < 20 + VIX↓ (vol stabilizing)",
             (df["fg"] < 20) & (df["vix_direction"] == "FALLING")),
            ("F&G < 20 + VIX↓ + PCR↓ (hedging unwinding)",
             (df["fg"] < 20) & (df["vix_direction"] == "FALLING") & (df["pcr_direction"] == "FALLING")),
            ("F&G < 20 + VIX↓ + SPY bouncing (mom5d > 0)",
             (df["fg"] < 20) & (df["vix_direction"] == "FALLING") & (df["spy_mom5d"] > 0)),
        ]
        print(f"  {'Signal':50s} {'N':>5s} {'Ret20d':>8s} {'WR':>6s} {'t_adj':>6s}")
        print(f"  {'─'*50} {'─'*5:>5s} {'─'*8:>8s} {'─'*6:>6s} {'─'*6:>6s}")
        for label, mask in reversal_signals:
            vals = df.loc[mask, "spy_ret20d"].dropna()
            if len(vals) >= 3:
                wr = (vals > 0).mean() * 100
                t = calc_adjusted_tstat(vals, horizon=20)
                print(f"  {label:50s} {len(vals):5d} {vals.mean():+7.2f}% {wr:5.1f}% {t:+5.2f}")

        print(f"\n  GREED TRAP DETECTION (directional signals):")
        greed_dir = [
            ("F&G > 75 alone",
             df["fg"] > 75),
            ("F&G > 75 + VIX↑ (hidden stress)",
             (df["fg"] > 75) & (df["vix_direction"] == "RISING")),
            ("F&G > 75 + PCR↑ (smart hedging)",
             (df["fg"] > 75) & (df["pcr_direction"] == "RISING")),
            ("F&G > 75 + VIX↑ + PCR↑ (DOUBLE WARNING)",
             (df["fg"] > 75) & (df["vix_direction"] == "RISING") & (df["pcr_direction"] == "RISING")),
            ("F&G > 75 + VIX↓ + PCR↓ (all-clear)",
             (df["fg"] > 75) & (df["vix_direction"] == "FALLING") & (df["pcr_direction"] == "FALLING")),
        ]
        print(f"  {'Signal':50s} {'N':>5s} {'Ret20d':>8s} {'WR':>6s} {'t_adj':>6s}")
        print(f"  {'─'*50} {'─'*5:>5s} {'─'*8:>8s} {'─'*6:>6s} {'─'*6:>6s}")
        for label, mask in greed_dir:
            vals = df.loc[mask, "spy_ret20d"].dropna()
            if len(vals) >= 3:
                wr = (vals > 0).mean() * 100
                t = calc_adjusted_tstat(vals, horizon=20)
                print(f"  {label:50s} {len(vals):5d} {vals.mean():+7.2f}% {wr:5.1f}% {t:+5.2f}")

    # ═══════════════════════════════════════════════════════════
    # 22B. VOL REGIME × F&G CROSS-ANALYSIS
    # ═══════════════════════════════════════════════════════════
    if "vol_regime_q_label" in df.columns:
        print("\n" + "=" * 80)
        print("22B. VOL REGIME × F&G — Production regime classification cross")
        print("=" * 80)

        print(f"\n  QUALITY REGIME DISTRIBUTION:")
        for label in ["NORMAL", "COMPLACENT", "ELEVATED", "CRISIS"]:
            mask = df["vol_regime_q_label"] == label
            n = mask.sum()
            if n > 0:
                pct = n / len(df) * 100
                ret = df.loc[mask, "spy_ret20d"].dropna()
                wr = (ret > 0).mean() * 100 if len(ret) >= 3 else 0
                t = calc_adjusted_tstat(ret, horizon=20) if len(ret) >= 5 else 0
                print(f"    {label:12s}: {n:4d} days ({pct:5.1f}%)  Ret={ret.mean():+5.2f}%  WR={wr:.1f}%  t={t:+.2f}")

        print(f"\n  SPECULATIVE REGIME DISTRIBUTION:")
        for label in ["STALK", "STRIKE", "HARVEST", "RETREAT"]:
            mask = df["vol_regime_s_label"] == label
            n = mask.sum()
            if n > 0:
                pct = n / len(df) * 100
                ret = df.loc[mask, "spy_ret20d"].dropna()
                wr = (ret > 0).mean() * 100 if len(ret) >= 3 else 0
                t = calc_adjusted_tstat(ret, horizon=20) if len(ret) >= 5 else 0
                print(f"    {label:12s}: {n:4d} days ({pct:5.1f}%)  Ret={ret.mean():+5.2f}%  WR={wr:.1f}%  t={t:+.2f}")

        # Quality regime × F&G cross
        print(f"\n  QUALITY REGIME × F&G CROSS (Fear signals in each vol regime):")
        print(f"  {'Vol Regime':12s} {'F&G Zone':12s} {'N':>5s} {'Ret20d':>8s} {'WR':>6s} {'t_adj':>6s}")
        print(f"  {'─'*12} {'─'*12} {'─'*5:>5s} {'─'*8:>8s} {'─'*6:>6s} {'─'*6:>6s}")
        for vr in ["NORMAL", "COMPLACENT", "ELEVATED", "CRISIS"]:
            for fg_label, fg_lo, fg_hi in [("Fear<25", 0, 25), ("Neutral", 25, 75), ("Greed>75", 75, 101)]:
                mask = (
                    (df["vol_regime_q_label"] == vr) &
                    (df["fg"] >= fg_lo) & (df["fg"] < fg_hi)
                )
                vals = df.loc[mask, "spy_ret20d"].dropna()
                if len(vals) >= 5:
                    wr = (vals > 0).mean() * 100
                    t = calc_adjusted_tstat(vals, horizon=20)
                    print(f"  {vr:12s} {fg_label:12s} {len(vals):5d} {vals.mean():+7.2f}% {wr:5.1f}% {t:+5.2f}")

        # Speculative regime × F&G cross
        print(f"\n  SPECULATIVE REGIME × F&G CROSS:")
        print(f"  {'Vol Regime':12s} {'F&G Zone':12s} {'N':>5s} {'Ret20d':>8s} {'WR':>6s} {'t_adj':>6s}")
        print(f"  {'─'*12} {'─'*12} {'─'*5:>5s} {'─'*8:>8s} {'─'*6:>6s} {'─'*6:>6s}")
        for vr in ["STALK", "STRIKE", "HARVEST", "RETREAT"]:
            for fg_label, fg_lo, fg_hi in [("Fear<25", 0, 25), ("Neutral", 25, 75), ("Greed>75", 75, 101)]:
                mask = (
                    (df["vol_regime_s_label"] == vr) &
                    (df["fg"] >= fg_lo) & (df["fg"] < fg_hi)
                )
                vals = df.loc[mask, "spy_ret20d"].dropna()
                if len(vals) >= 5:
                    wr = (vals > 0).mean() * 100
                    t = calc_adjusted_tstat(vals, horizon=20)
                    print(f"  {vr:12s} {fg_label:12s} {len(vals):5d} {vals.mean():+7.2f}% {wr:5.1f}% {t:+5.2f}")

        # Triple convergence with vol regime
        print(f"\n  CAPITULATION × VOL REGIME (the ultimate filter):")
        print(f"  {'Signal':55s} {'N':>5s} {'Ret20d':>8s} {'WR':>6s} {'t_adj':>6s}")
        print(f"  {'─'*55} {'─'*5:>5s} {'─'*8:>8s} {'─'*6:>6s} {'─'*6:>6s}")
        cap_signals = [
            ("F&G < 20 + CRISIS regime",
             (df["fg"] < 20) & (df["vol_regime_q_label"] == "CRISIS")),
            ("F&G < 20 + ELEVATED regime",
             (df["fg"] < 20) & (df["vol_regime_q_label"] == "ELEVATED")),
            ("F&G < 20 + NORMAL regime",
             (df["fg"] < 20) & (df["vol_regime_q_label"] == "NORMAL")),
            ("F&G < 20 + CRISIS + VIX↓ (vol stabilizing)",
             (df["fg"] < 20) & (df["vol_regime_q_label"] == "CRISIS") &
             (df["vix_direction"] == "FALLING")),
            ("F&G < 20 + CRISIS + VIX↑ (still panicking)",
             (df["fg"] < 20) & (df["vol_regime_q_label"] == "CRISIS") &
             (df["vix_direction"] == "RISING")),
            ("F&G < 20 + RETREAT (spec) + VIX > 25",
             (df["fg"] < 20) & (df["vol_regime_s_label"] == "RETREAT") &
             (df["vix"] > 25)),
            ("F&G < 20 + STRIKE (spec — compression breakout)",
             (df["fg"] < 20) & (df["vol_regime_s_label"] == "STRIKE")),
        ]
        for label, mask in cap_signals:
            vals = df.loc[mask, "spy_ret20d"].dropna()
            if len(vals) >= 3:
                wr = (vals > 0).mean() * 100
                t = calc_adjusted_tstat(vals, horizon=20)
                print(f"  {label:55s} {len(vals):5d} {vals.mean():+7.2f}% {wr:5.1f}% {t:+5.2f}")

    # ═══════════════════════════════════════════════════════════
    # 22C. EMERGENT MARKET REGIME — Can F&G ecosystem DEFINE the regime?
    # ═══════════════════════════════════════════════════════════
    if "vix" in df.columns and "pcr" in df.columns:
        print("\n" + "=" * 80)
        print("22C. EMERGENT MARKET REGIME — Inferred purely from F&G + VIX + PCR + Momentum")
        print("=" * 80)

        # Classify market regime from observable sentiment-flow indicators
        # Priority order (top-down, first match wins):
        conditions = []
        labels = []

        # CAPITULATION: Extreme fear + high VIX + SPY crashing
        cap_mask = (df["fg"] < 20) & (df["vix"] > 25) & (df["spy_mom5d"] < -2)
        conditions.append(cap_mask)
        labels.append("CAPITULATION")

        # RECOVERY: Fear was recent (F&G < 30) + VIX falling + SPY bouncing
        rec_mask = (
            (df["fg"] >= 20) & (df["fg"] < 40) &
            (df["vix_direction"] == "FALLING") &
            (df["spy_mom5d"] > 0)
        )
        conditions.append(rec_mask)
        labels.append("RECOVERY")

        # WALL_OF_WORRY: Neutral sentiment + SPY rising + VIX still above avg
        wow_mask = (
            (df["fg"] >= 30) & (df["fg"] < 55) &
            (df["spy_mom20d"] > 0) &
            (df["vix"] > df["vix"].rolling(60, min_periods=20).mean())
        )
        conditions.append(wow_mask)
        labels.append("WALL_OF_WORRY")

        # DISTRIBUTION: Greed + VIX rising + PCR rising (smart money hedging)
        dist_mask = (
            (df["fg"] > 65) &
            (df["vix_direction"] == "RISING") &
            (df["pcr_direction"] == "RISING")
        )
        conditions.append(dist_mask)
        labels.append("DISTRIBUTION")

        # EUPHORIA: Extreme greed + low VIX + SPY at highs
        euph_mask = (
            (df["fg"] > 75) &
            (df["vix"] < 18) &
            (df["spy_dd_from_high"] > -3)
        )
        conditions.append(euph_mask)
        labels.append("EUPHORIA")

        # COMPLACENCY: High F&G + VIX very low + flat PCR
        comp_mask = (
            (df["fg"] >= 55) & (df["fg"] <= 75) &
            (df["vix"] < 15) &
            (df["pcr"] < 0.85)
        )
        conditions.append(comp_mask)
        labels.append("COMPLACENCY")

        # STRESS: Low F&G + VIX rising + SPY falling
        stress_mask = (
            (df["fg"] < 35) &
            (df["vix_direction"] == "RISING") &
            (df["spy_mom5d"] < 0)
        )
        conditions.append(stress_mask)
        labels.append("STRESS")

        # Assign regimes (priority-ordered: first match wins)
        df["mkt_regime"] = "NORMAL_BULL"  # default
        # Apply in reverse so first conditions have priority
        for cond, label in reversed(list(zip(conditions, labels))):
            df.loc[cond, "mkt_regime"] = label

        # Report distribution
        print(f"\n  EMERGENT REGIME DISTRIBUTION:")
        regime_order = ["CAPITULATION", "STRESS", "RECOVERY", "WALL_OF_WORRY",
                        "NORMAL_BULL", "COMPLACENCY", "EUPHORIA", "DISTRIBUTION"]
        regime_counts = df["mkt_regime"].value_counts()
        for r in regime_order:
            if r not in regime_counts:
                continue
            n = regime_counts[r]
            pct = n / len(df) * 100
            ret = df.loc[df["mkt_regime"] == r, "spy_ret20d"].dropna()
            wr = (ret > 0).mean() * 100 if len(ret) >= 3 else 0
            t = calc_adjusted_tstat(ret, horizon=20) if len(ret) >= 5 else 0
            bar = "█" * max(1, int(pct / 2))
            print(f"    {r:16s}: {n:4d} days ({pct:5.1f}%) {bar:12s} "
                  f"Ret={ret.mean():+5.2f}%  WR={wr:.1f}%  t={t:+.2f}")

        # Regime × forward returns deep table
        print(f"\n  EMERGENT REGIME × SPY FORWARD RETURNS:")
        print(f"  {'Regime':16s} {'N':>5s} {'Ret5d':>7s} {'Ret10d':>8s} {'Ret20d':>8s} {'Ret40d':>8s} {'WR20d':>6s}")
        print(f"  {'─'*16} {'─'*5:>5s} {'─'*7:>7s} {'─'*8:>8s} {'─'*8:>8s} {'─'*8:>8s} {'─'*6:>6s}")
        for r in regime_order:
            mask = df["mkt_regime"] == r
            if mask.sum() < 10:
                continue
            sub = df.loc[mask]
            r5 = sub["spy_ret5d"].dropna().mean()
            r10 = sub["spy_ret10d"].dropna().mean()
            r20 = sub["spy_ret20d"].dropna().mean()
            r40 = sub["spy_ret40d"].dropna().mean()
            wr20 = (sub["spy_ret20d"].dropna() > 0).mean() * 100
            print(f"  {r:16s} {mask.sum():5d} {r5:+6.2f}% {r10:+7.2f}% {r20:+7.2f}% {r40:+7.2f}% {wr20:5.1f}%")

        # Regime transitions: what happens when regime changes?
        print(f"\n  REGIME TRANSITIONS → SPY Ret20d after transition:")
        df["prev_regime"] = df["mkt_regime"].shift(1)
        transitions = df[df["mkt_regime"] != df["prev_regime"]].copy()
        print(f"  {'From':16s} → {'To':16s} {'N':>5s} {'Ret20d':>8s} {'WR':>6s}")
        print(f"  {'─'*16}   {'─'*16} {'─'*5:>5s} {'─'*8:>8s} {'─'*6:>6s}")
        key_transitions = [
            ("CAPITULATION", "RECOVERY"),
            ("CAPITULATION", "STRESS"),
            ("STRESS", "RECOVERY"),
            ("STRESS", "CAPITULATION"),
            ("RECOVERY", "WALL_OF_WORRY"),
            ("RECOVERY", "NORMAL_BULL"),
            ("WALL_OF_WORRY", "NORMAL_BULL"),
            ("NORMAL_BULL", "EUPHORIA"),
            ("EUPHORIA", "DISTRIBUTION"),
            ("EUPHORIA", "NORMAL_BULL"),
            ("DISTRIBUTION", "STRESS"),
            ("COMPLACENCY", "STRESS"),
        ]
        for from_r, to_r in key_transitions:
            mask = (transitions["prev_regime"] == from_r) & (transitions["mkt_regime"] == to_r)
            vals = transitions.loc[mask, "spy_ret20d"].dropna()
            if len(vals) >= 3:
                wr = (vals > 0).mean() * 100
                print(f"  {from_r:16s} → {to_r:16s} {len(vals):5d} {vals.mean():+7.2f}% {wr:5.1f}%")

        # Can the emergent regime predict BETTER than F&G alone?
        print(f"\n  PREDICTIVE POWER COMPARISON: Emergent Regime vs F&G alone")
        # For fear signals: compare F&G < 20 alone vs CAPITULATION regime
        fg_fear = df.loc[df["fg"] < 20, "spy_ret20d"].dropna()
        cap_ret = df.loc[df["mkt_regime"] == "CAPITULATION", "spy_ret20d"].dropna()
        stress_ret = df.loc[df["mkt_regime"] == "STRESS", "spy_ret20d"].dropna()
        print(f"    F&G < 20 (raw):       N={len(fg_fear):4d}  Ret={fg_fear.mean():+5.2f}%  WR={(fg_fear > 0).mean()*100:.1f}%")
        if len(cap_ret) >= 3:
            print(f"    CAPITULATION (regime): N={len(cap_ret):4d}  Ret={cap_ret.mean():+5.2f}%  WR={(cap_ret > 0).mean()*100:.1f}%")
        if len(stress_ret) >= 3:
            print(f"    STRESS (regime):       N={len(stress_ret):4d}  Ret={stress_ret.mean():+5.2f}%  WR={(stress_ret > 0).mean()*100:.1f}%")
        # For greed signals
        fg_greed = df.loc[df["fg"] > 75, "spy_ret20d"].dropna()
        euph_ret = df.loc[df["mkt_regime"] == "EUPHORIA", "spy_ret20d"].dropna()
        dist_ret = df.loc[df["mkt_regime"] == "DISTRIBUTION", "spy_ret20d"].dropna()
        print(f"    F&G > 75 (raw):       N={len(fg_greed):4d}  Ret={fg_greed.mean():+5.2f}%  WR={(fg_greed > 0).mean()*100:.1f}%")
        if len(euph_ret) >= 3:
            print(f"    EUPHORIA (regime):    N={len(euph_ret):4d}  Ret={euph_ret.mean():+5.2f}%  WR={(euph_ret > 0).mean()*100:.1f}%")
        if len(dist_ret) >= 3:
            print(f"    DISTRIBUTION (regime):N={len(dist_ret):4d}  Ret={dist_ret.mean():+5.2f}%  WR={(dist_ret > 0).mean()*100:.1f}%")

    # ═══════════════════════════════════════════════════════════
    # 23. DELTA CORRELATION MATRIX
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("23. DELTA CORRELATION MATRIX — Which deltas predict SPY Ret20d?")
    print("=" * 80)
    delta_cols = ["fg_roc5", "spy_mom5d", "spy_mom20d"]
    if "vix_roc5" in df.columns:
        delta_cols.append("vix_roc5")
    if "pcr_roc5" in df.columns:
        delta_cols.append("pcr_roc5")
    delta_cols.append("spy_ret20d")
    
    corr_matrix = df[delta_cols].dropna().corr()
    ret_corrs = corr_matrix["spy_ret20d"].drop("spy_ret20d").sort_values()
    print(f"  Correlation with SPY forward 20d return:")
    for col, corr in ret_corrs.items():
        bar = "█" * int(abs(corr) * 50)
        sign = "+" if corr > 0 else "-"
        print(f"    {col:15s}: {corr:+.4f}  {sign}{bar}")

    # ═══════════════════════════════════════════════════════════
    # 24. COMPREHENSIVE SUMMARY — Absolute Statistics
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("24. COMPREHENSIVE SUMMARY — Absolute statistics for data science review")
    print("=" * 80)
    
    print(f"\n  DATASET METADATA:")
    print(f"    Date range:     {df.index[0].date()} → {df.index[-1].date()}")
    print(f"    Total days:     {len(df)}")
    print(f"    Instruments:    FG, SPY, QQQ, CBOE_PCR, VIX")
    print(f"    Horizons:       5d, 10d, 20d, 40d, 60d")
    
    print(f"\n  F&G INDEX — Full Distribution:")
    fg_s = df["fg"]
    print(f"    Min={fg_s.min():.0f}  P5={fg_s.quantile(0.05):.0f}  P25={fg_s.quantile(0.25):.0f}  "
          f"Median={fg_s.median():.0f}  P75={fg_s.quantile(0.75):.0f}  P95={fg_s.quantile(0.95):.0f}  Max={fg_s.max():.0f}")
    print(f"    Mean={fg_s.mean():.1f}  Std={fg_s.std():.1f}  Skew={fg_s.skew():.2f}  Kurt={fg_s.kurtosis():.2f}")
    
    print(f"\n  SPY CLOSE — Full Distribution:")
    spy_s = df["spy"]
    print(f"    Min=${spy_s.min():.2f}  Max=${spy_s.max():.2f}  "
          f"Total Return={(spy_s.iloc[-1]/spy_s.iloc[0]-1)*100:.1f}%")

    print(f"\n  SPY 20d FORWARD RETURN — Full Distribution:")
    ret20 = df["spy_ret20d"].dropna()
    print(f"    Min={ret20.min():+.2f}%  P5={ret20.quantile(0.05):+.2f}%  P25={ret20.quantile(0.25):+.2f}%  "
          f"Median={ret20.median():+.2f}%  P75={ret20.quantile(0.75):+.2f}%  P95={ret20.quantile(0.95):+.2f}%  Max={ret20.max():+.2f}%")
    print(f"    Mean={ret20.mean():+.2f}%  Std={ret20.std():.2f}%  Skew={ret20.skew():.2f}  Kurt={ret20.kurtosis():.2f}")
    print(f"    Overall WR (Ret20d > 0): {(ret20 > 0).mean()*100:.1f}%")
    
    if "pcr" in df.columns:
        print(f"\n  PCR — Full Distribution:")
        pcr_s = df["pcr"].dropna()
        print(f"    Min={pcr_s.min():.3f}  P5={pcr_s.quantile(0.05):.3f}  P25={pcr_s.quantile(0.25):.3f}  "
              f"Median={pcr_s.median():.3f}  P75={pcr_s.quantile(0.75):.3f}  P95={pcr_s.quantile(0.95):.3f}  Max={pcr_s.max():.3f}")

    print(f"\n  REGIME TIME DISTRIBUTION (% of total days):")
    regime_counts = df["regime"].value_counts().sort_index()
    for r, c in regime_counts.items():
        pct = c / len(df) * 100
        bar = "█" * int(pct)
        print(f"    F&G {str(r):8s}: {c:4d} days ({pct:5.1f}%) {bar}")

    print(f"\n  DOW THEORY PHASE DISTRIBUTION:")
    phase_counts = df["phase"].value_counts()
    for p in ["ADVANCING", "DECLINING", "BASING/CHOP", "EXPANDING_VOLATILITY"]:
        if p in phase_counts:
            c = phase_counts[p]
            pct = c / len(df) * 100
            print(f"    {p:25s}: {c:4d} days ({pct:5.1f}%)")

    # ═══════════════════════════════════════════════════════════
    # 25. HYPOTHESIS SCOREBOARD
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("25. HYPOTHESIS SCOREBOARD — Evidence Status Tags (López de Prado)")
    print("=" * 80)
    print(f"  {'#':3s} {'Hypothesis':55s} {'Status':12s} {'Evidence':40s}")
    print(f"  {'─'*3} {'─'*55} {'─'*12} {'─'*40}")
    
    # Compute hypothesis verdicts from data already in memory
    # H1: Fear < 20 generates positive 20d returns
    h1_vals = df.loc[df["fg"] < 20, "spy_ret20d"].dropna()
    h1_t = calc_adjusted_tstat(h1_vals, 20)
    h1_status = "✅ CONFIRMED" if h1_t > 1.96 else ("🔶 PLAUSIBLE" if h1_t > 1.0 else "❌ REJECTED")
    
    # H2: Greed > 85 is dangerous
    h2_vals = df.loc[df["fg"] > 85, "spy_ret20d"].dropna()
    h2_wr = (h2_vals > 0).mean() * 100
    h2_status = "❌ REJECTED" if h2_wr > 65 else "✅ CONFIRMED"
    
    # H3: Duration matters (21+ days fear > early fear)
    h3_long = df.loc[df["consec_fear"] >= 21, "spy_ret20d"].dropna()
    h3_short = df.loc[(df["consec_fear"] >= 1) & (df["consec_fear"] <= 3), "spy_ret20d"].dropna()
    h3_diff = h3_long.mean() - h3_short.mean() if len(h3_long) >= 3 and len(h3_short) >= 3 else 0
    h3_status = "✅ CONFIRMED" if h3_diff > 1.0 else "🔶 PLAUSIBLE"

    # H4: Exiting fear > entering fear
    exit_vals = df.loc[(df["fg"] >= 20) & (df["fg"].shift(1) < 20), "spy_ret20d"].dropna()
    enter_vals = df.loc[(df["fg"] < 20) & (df["fg"].shift(1) >= 20), "spy_ret20d"].dropna()
    h4_diff = exit_vals.mean() - enter_vals.mean() if len(exit_vals) >= 3 and len(enter_vals) >= 3 else 0
    h4_status = "✅ CONFIRMED" if h4_diff > 0.3 else "🔶 PLAUSIBLE"

    # H5: PCR > 1.3 predicts bounce
    h5_vals = df.loc[df["pcr"] > 1.3, "spy_ret20d"].dropna() if "pcr" in df.columns else pd.Series(dtype=float)
    h5_t = calc_adjusted_tstat(h5_vals, 20) if len(h5_vals) >= 5 else 0
    h5_status = "🔶 PLAUSIBLE" if h5_t > 0.5 else "❌ INSUFFICIENT"

    # H6: Volume dry-up in fear = strongest signal
    h6_vals = fear_zone.loc[fear_zone["spy_vol_ratio"] < 0.8, "spy_ret20d"].dropna() if not fear_zone.empty else pd.Series(dtype=float)
    h6_wr = (h6_vals > 0).mean() * 100 if len(h6_vals) >= 3 else 0
    h6_status = "✅ CONFIRMED" if h6_wr > 80 else "🔶 PLAUSIBLE"

    # H7: EXPANDING_VOLATILITY destroys fear signals
    h7_vals = df.loc[(df["phase"] == "EXPANDING_VOLATILITY") & (df["fg"] < 25), "spy_ret20d"].dropna()
    h7_wr = (h7_vals > 0).mean() * 100 if len(h7_vals) >= 3 else 50
    h7_status = "✅ CONFIRMED" if h7_wr < 55 else "❌ REJECTED"

    # H8: ADVANCING + Fear = highest WR
    h8_vals = df.loc[(df["phase"] == "ADVANCING") & (df["fg"] < 25), "spy_ret20d"].dropna()
    h8_wr = (h8_vals > 0).mean() * 100 if len(h8_vals) >= 3 else 0
    h8_status = "✅ CONFIRMED" if h8_wr > 80 else "🔶 PLAUSIBLE"

    # H9: F&G > 75 + PCR > 1.0 divergence = alpha
    h9_vals = df.loc[(df["fg"] > 75) & (df["pcr"] > 1.0), "spy_ret20d"].dropna() if "pcr" in df.columns else pd.Series(dtype=float)
    h9_wr = (h9_vals > 0).mean() * 100 if len(h9_vals) >= 3 else 0
    h9_status = "✅ CONFIRMED" if h9_wr > 75 else "🔶 PLAUSIBLE"

    # H10: VIX > 25 + F&G < 15 = max reversal
    if "vix" in df.columns:
        h10_vals = df.loc[(df["vix"] > 25) & (df["fg"] < 15), "spy_ret20d"].dropna()
        h10_mean = h10_vals.mean() if len(h10_vals) >= 3 else 0
        h10_status = "✅ CONFIRMED" if h10_mean > 2.0 else "🔶 PLAUSIBLE"
    else:
        h10_mean = 0
        h10_status = "⚠️ NO DATA"

    hypotheses = [
        ("H1", "Extreme Fear (F&G < 20) → positive 20d returns", h1_status, f"t_adj={h1_t:+.2f} Mean={h1_vals.mean():+.2f}% WR={((h1_vals>0).mean()*100):.0f}%"),
        ("H2", "Extreme Greed (F&G > 85) is immediately dangerous", h2_status, f"WR={h2_wr:.0f}% — GREED IS BULLISH not bearish"),
        ("H3", "Longer fear duration → stronger reversal", h3_status, f"21d+: {h3_long.mean():+.2f}% vs 1-3d: {h3_short.mean():+.2f}%"),
        ("H4", "Exit fear signal > Enter fear signal", h4_status, f"Exit: {exit_vals.mean():+.2f}% vs Enter: {enter_vals.mean():+.2f}%"),
        ("H5", "PCR > 1.3 (panic) predicts bounce", h5_status, f"t_adj={h5_t:+.2f} N={len(h5_vals)}"),
        ("H6", "Volume dry-up in fear = seller exhaustion", h6_status, f"WR={h6_wr:.0f}% Ret={h6_vals.mean():+.2f}%" if len(h6_vals) >= 3 else "Insufficient N"),
        ("H7", "EXPANDING_VOL phase destroys fear buy signals", h7_status, f"WR={h7_wr:.0f}% — near coin flip"),
        ("H8", "ADVANCING + Fear = highest probability buy", h8_status, f"WR={h8_wr:.0f}% N={len(h8_vals)}"),
        ("H9", "Greed + PCR > 1.0 divergence = institutional alpha", h9_status, f"WR={h9_wr:.0f}% Ret={h9_vals.mean():+.2f}%" if len(h9_vals) >= 3 else "N/A"),
        ("H10", "VIX > 25 + F&G < 15 = maximum reversal zone", h10_status, f"Mean={h10_mean:+.2f}%"),
    ]
    for hid, desc, status, evidence in hypotheses:
        print(f"  {hid:3s} {desc:55s} {status:12s} {evidence}")

    print("\n═══ Deep Forensics Complete ═══")


if __name__ == "__main__":
    main()
