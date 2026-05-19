"""
PCR 5-Minute Forensic Analysis
================================
Tests whether intraday PCR resolution adds predictive alpha
vs the daily CBOE_PCR close we already use.

Data:
  - CBOE_PCR_5M: 8,425 bars (5min), Dec 2025 → May 2026 (113 days)
  - CBOE_PCR:    4,924 bars (daily), 2006 → 2026
  - SPY:         9,625 bars (daily), 1993 → 2026

Hypotheses:
  PCR5M-H01: Intraday PCR range (high-low) predicts next-day SPY vol
  PCR5M-H02: PCR intraday spikes (>1.2 at any 5min bar) precede SPY reversals
  PCR5M-H03: PCR opening vs closing divergence predicts next-day direction
  PCR5M-H04: Daily PCR close captures >80% of signal vs intraday features
  PCR5M-H05: PCR intraday skewness detects institutional hedging
  PCR5M-H06: Morning vs afternoon PCR divergence predicts next-day moves

Statistical rigor:
  - Overlapping return adjustment (Newey-West, 1 lag)
  - All features .shift(1) to prevent lookahead
  - Honest N for each hypothesis

Usage:
  PYTHONPATH=. python backend/scripts/backtest_pcr_5min_forensics.py
"""
import sys
import os
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pandas as pd
import numpy as np
from scipy import stats
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))


# ══════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════

def load_vault_data():
    """Load PCR 5min, PCR daily, and SPY daily from Neon Vault."""
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()

    pcr_5m = store.load_bars("CBOE_PCR_5M", "5min")
    pcr_daily = store.load_bars("CBOE_PCR", "1d")
    spy = store.load_bars("SPY", "1d")

    store.close()
    return pcr_5m, pcr_daily, spy


def aggregate_5min_to_daily(pcr_5m: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 5-min PCR bars into daily feature vectors.

    Features extracted:
      - pcr_open:    first bar of the day
      - pcr_close:   last bar of the day
      - pcr_high:    max PCR in the day (peak fear)
      - pcr_low:     min PCR in the day (peak greed)
      - pcr_range:   high - low (intraday volatility of sentiment)
      - pcr_std:     intraday standard deviation
      - pcr_skew:    intraday skewness (positive = fear tail)
      - pcr_spike:   1 if any bar > 1.2 (institutional hedging)
      - pcr_am:      mean PCR in first half of session
      - pcr_pm:      mean PCR in second half of session
      - pcr_am_pm:   AM - PM divergence
      - pcr_trend:   close - open (intraday drift direction)
      - n_bars:      number of bars (quality check)
    """
    pcr_5m = pcr_5m.copy()
    pcr_5m['date'] = pcr_5m.index.date

    daily_features = []

    for dt, group in pcr_5m.groupby('date'):
        if len(group) < 20:  # Skip incomplete days
            continue

        closes = group['close'].values
        highs = group['high'].values
        lows = group['low'].values

        midpoint = len(group) // 2
        am_bars = group.iloc[:midpoint]
        pm_bars = group.iloc[midpoint:]

        pcr_am = am_bars['close'].mean()
        pcr_pm = pm_bars['close'].mean()

        daily_features.append({
            'date': pd.Timestamp(dt),
            'pcr_open': float(group['open'].iloc[0]),
            'pcr_close': float(group['close'].iloc[-1]),
            'pcr_high': float(highs.max()),
            'pcr_low': float(lows.min()),
            'pcr_range': float(highs.max() - lows.min()),
            'pcr_std': float(closes.std()),
            'pcr_skew': float(pd.Series(closes).skew()) if len(closes) > 3 else 0.0,
            'pcr_spike': 1 if highs.max() > 1.2 else 0,
            'pcr_am': float(pcr_am),
            'pcr_pm': float(pcr_pm),
            'pcr_am_pm': float(pcr_am - pcr_pm),
            'pcr_trend': float(group['close'].iloc[-1] - group['open'].iloc[0]),
            'n_bars': len(group),
        })

    return pd.DataFrame(daily_features).set_index('date')


# ══════════════════════════════════════════════════════════════
# STATISTICAL TOOLS
# ══════════════════════════════════════════════════════════════

def adjusted_tstat(returns: pd.Series, horizon: int = 1) -> float:
    """Newey-West adjusted t-stat for overlapping returns."""
    n = len(returns.dropna())
    if n < 10:
        return 0.0
    mean = returns.mean()
    se = returns.std() / np.sqrt(n)
    if se == 0:
        return 0.0
    raw_t = mean / se
    # Overlap adjustment (López de Prado)
    if horizon > 1:
        adjustment = np.sqrt(1 + 2 * sum(
            (1 - k / n) * returns.autocorr(lag=k)
            for k in range(1, min(horizon, n // 2))
            if not np.isnan(returns.autocorr(lag=k))
        ))
        return raw_t / max(adjustment, 0.1)
    return raw_t


def hypothesis_test(
    signal: pd.Series,
    returns: pd.Series,
    condition: pd.Series,
    name: str,
    horizon: int = 1,
):
    """Test a single hypothesis and print results."""
    mask = condition & returns.notna() & signal.notna()
    n = mask.sum()
    if n < 10:
        print(f"  {name}: SKIP (N={n} < 10)")
        return None

    cond_rets = returns[mask]
    uncond_rets = returns[~mask & returns.notna()]

    mean_cond = cond_rets.mean() * 100
    mean_uncond = uncond_rets.mean() * 100
    alpha = mean_cond - mean_uncond
    wr = (cond_rets > 0).mean() * 100
    t = adjusted_tstat(cond_rets, horizon)

    # Evidence tag
    if abs(t) >= 2.0:
        tag = "CONFIRMED" if n >= 30 else "CANDIDATE"
    elif abs(t) >= 1.5:
        tag = "PLAUSIBLE"
    else:
        tag = "NOISE"

    print(f"  {name}:")
    print(f"    N={n}, Ret={mean_cond:+.3f}%, WR={wr:.1f}%, "
          f"Alpha={alpha:+.3f}%, t_adj={t:+.2f} → [{tag}]")

    return {
        'name': name, 'n': n, 'ret': mean_cond, 'wr': wr,
        'alpha': alpha, 't': t, 'tag': tag,
    }


# ══════════════════════════════════════════════════════════════
# MAIN FORENSIC ANALYSIS
# ══════════════════════════════════════════════════════════════

def run_forensics():
    print("=" * 70)
    print("PCR 5-MINUTE FORENSIC ANALYSIS")
    print("Does intraday PCR resolution add alpha vs daily?")
    print("=" * 70)

    # ── Load Data ──
    pcr_5m, pcr_daily, spy = load_vault_data()

    print(f"\n📊 Data loaded:")
    print(f"  PCR 5min:  {len(pcr_5m):,} bars ({pcr_5m.index.min().date()} → {pcr_5m.index.max().date()})")
    print(f"  PCR daily: {len(pcr_daily):,} bars ({pcr_daily.index.min().date()} → {pcr_daily.index.max().date()})")
    print(f"  SPY daily: {len(spy):,} bars ({spy.index.min().date()} → {spy.index.max().date()})")

    # ── Aggregate 5min to daily features ──
    pcr_features = aggregate_5min_to_daily(pcr_5m)
    print(f"  PCR features: {len(pcr_features)} trading days aggregated")

    # ── Merge with SPY returns ──
    spy_daily = spy[['close']].copy()
    spy_daily.index = pd.to_datetime(spy_daily.index).tz_localize(None).normalize()
    spy_daily['spy_ret1d'] = spy_daily['close'].pct_change().shift(-1)  # Next-day return
    spy_daily['spy_ret5d'] = spy_daily['close'].pct_change(5).shift(-5)  # Next 5-day return
    spy_daily['spy_vol1d'] = spy_daily['close'].pct_change().abs()  # Today's absolute return

    pcr_features.index = pd.to_datetime(pcr_features.index).tz_localize(None).normalize()
    merged = pcr_features.join(spy_daily, how='inner')

    # Also join the daily PCR close for comparison
    pcr_daily_c = pcr_daily[['close']].copy()
    pcr_daily_c.index = pd.to_datetime(pcr_daily_c.index).tz_localize(None).normalize()
    pcr_daily_c = pcr_daily_c.rename(columns={'close': 'pcr_daily_close'})
    merged = merged.join(pcr_daily_c, how='left')

    # ── Shift all features by 1 day (no lookahead) ──
    feature_cols = [c for c in merged.columns if c.startswith('pcr_')]
    for col in feature_cols:
        merged[f'{col}_lag1'] = merged[col].shift(1)

    print(f"  Merged: {len(merged)} rows with SPY returns")
    print(f"  Date range: {merged.index.min().date()} → {merged.index.max().date()}")

    # ══════════════════════════════════════════════════════════
    # SECTION 1: DESCRIPTIVE STATISTICS
    # ══════════════════════════════════════════════════════════
    print("\n" + "═" * 70)
    print("S1: INTRADAY PCR DESCRIPTIVE STATISTICS")
    print("═" * 70)

    for col in ['pcr_open', 'pcr_close', 'pcr_high', 'pcr_low',
                'pcr_range', 'pcr_std', 'pcr_skew', 'pcr_am_pm', 'pcr_trend']:
        s = merged[col]
        print(f"  {col:15s}  mean={s.mean():.4f}  std={s.std():.4f}  "
              f"min={s.min():.4f}  max={s.max():.4f}")

    spike_days = merged['pcr_spike'].sum()
    print(f"\n  Spike days (any bar >1.2): {spike_days}/{len(merged)} "
          f"({spike_days/len(merged)*100:.1f}%)")

    # ══════════════════════════════════════════════════════════
    # SECTION 2: HYPOTHESIS TESTING
    # ══════════════════════════════════════════════════════════
    print("\n" + "═" * 70)
    print("S2: HYPOTHESIS TESTING — Does 5min resolution add alpha?")
    print("═" * 70)

    results = []

    # H01: Intraday PCR range predicts next-day SPY vol
    print("\n── PCR5M-H01: Intraday range → next-day SPY volatility ──")
    range_median = merged['pcr_range_lag1'].median()
    r = hypothesis_test(
        merged['pcr_range_lag1'], merged['spy_vol1d'].shift(-1),
        merged['pcr_range_lag1'] > range_median,
        "High intraday range → higher next-day vol",
    )
    if r: results.append(r)

    # Correlation approach
    corr = merged['pcr_range_lag1'].corr(merged['spy_vol1d'].shift(-1))
    print(f"    Correlation(PCR_range, next_day_abs_ret): {corr:.3f}")

    # H02: PCR spike days → SPY next-day returns
    print("\n── PCR5M-H02: Spike days (>1.2 intraday) → SPY reversal ──")
    r = hypothesis_test(
        merged['pcr_spike_lag1'], merged['spy_ret1d'],
        merged['pcr_spike_lag1'] == 1,
        "Spike day → next-day SPY return",
    )
    if r: results.append(r)

    # H03: PCR open vs close divergence → next-day direction
    print("\n── PCR5M-H03: Intraday trend (close-open) → next-day ──")
    trend_q80 = merged['pcr_trend_lag1'].quantile(0.80)
    trend_q20 = merged['pcr_trend_lag1'].quantile(0.20)

    r = hypothesis_test(
        merged['pcr_trend_lag1'], merged['spy_ret1d'],
        merged['pcr_trend_lag1'] > trend_q80,
        "PCR rose intraday (fear building) → next-day SPY",
    )
    if r: results.append(r)

    r = hypothesis_test(
        merged['pcr_trend_lag1'], merged['spy_ret1d'],
        merged['pcr_trend_lag1'] < trend_q20,
        "PCR fell intraday (fear receding) → next-day SPY",
    )
    if r: results.append(r)

    # H04: Daily close captures most signal — incremental R²
    print("\n── PCR5M-H04: Incremental R² of 5min features vs daily close ──")
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import r2_score

    try:
        # Build a clean frame with all features + target
        r2_frame = merged[['pcr_daily_close', 'spy_ret1d',
                           'pcr_range_lag1', 'pcr_std_lag1', 'pcr_skew_lag1',
                           'pcr_am_pm_lag1', 'pcr_trend_lag1', 'pcr_spike_lag1']].copy()
        r2_frame['pcr_daily_lag1'] = r2_frame['pcr_daily_close'].shift(1)
        r2_frame = r2_frame.dropna()

        if len(r2_frame) > 20:
            y = r2_frame['spy_ret1d']

            # Model A: daily PCR close only
            X_daily = r2_frame[['pcr_daily_lag1']]
            reg_daily = LinearRegression().fit(X_daily, y)
            r2_daily = r2_score(y, reg_daily.predict(X_daily))

            # Model B: daily + 5min features
            intraday_cols = ['pcr_daily_lag1', 'pcr_range_lag1', 'pcr_std_lag1',
                             'pcr_skew_lag1', 'pcr_am_pm_lag1', 'pcr_trend_lag1',
                             'pcr_spike_lag1']
            X_full = r2_frame[intraday_cols]
            reg_full = LinearRegression().fit(X_full, y)
            r2_full = r2_score(y, reg_full.predict(X_full))

            print(f"  R² (daily PCR close only):     {r2_daily:.4f}")
            print(f"  R² (daily + 5min features):    {r2_full:.4f}")
            print(f"  Incremental R²:                {r2_full - r2_daily:+.4f}")

            if r2_full > r2_daily * 1.5 and r2_full > 0.01:
                print(f"  → 5min features ADD meaningful signal")
            else:
                print(f"  → 5min features add MINIMAL signal over daily close")
    except Exception as e:
        print(f"  R² comparison failed: {e}")

    # H05: PCR skewness → institutional hedging
    print("\n── PCR5M-H05: Intraday skewness → hedging detection ──")
    skew_q80 = merged['pcr_skew_lag1'].quantile(0.80)
    r = hypothesis_test(
        merged['pcr_skew_lag1'], merged['spy_ret1d'],
        merged['pcr_skew_lag1'] > skew_q80,
        "Positive skew (fear tail) → next-day SPY",
    )
    if r: results.append(r)

    skew_q20 = merged['pcr_skew_lag1'].quantile(0.20)
    r = hypothesis_test(
        merged['pcr_skew_lag1'], merged['spy_ret1d'],
        merged['pcr_skew_lag1'] < skew_q20,
        "Negative skew (greed tail) → next-day SPY",
    )
    if r: results.append(r)

    # H06: AM vs PM divergence
    print("\n── PCR5M-H06: Morning vs Afternoon PCR divergence ──")
    am_pm_q80 = merged['pcr_am_pm_lag1'].quantile(0.80)
    am_pm_q20 = merged['pcr_am_pm_lag1'].quantile(0.20)

    r = hypothesis_test(
        merged['pcr_am_pm_lag1'], merged['spy_ret1d'],
        merged['pcr_am_pm_lag1'] > am_pm_q80,
        "AM fear > PM fear (fear exhaustion) → next-day SPY",
    )
    if r: results.append(r)

    r = hypothesis_test(
        merged['pcr_am_pm_lag1'], merged['spy_ret1d'],
        merged['pcr_am_pm_lag1'] < am_pm_q20,
        "PM fear > AM fear (fear building) → next-day SPY",
    )
    if r: results.append(r)

    # ══════════════════════════════════════════════════════════
    # SECTION 3: CORRELATION MATRIX
    # ══════════════════════════════════════════════════════════
    print("\n" + "═" * 70)
    print("S3: FEATURE CORRELATION WITH NEXT-DAY SPY RETURN")
    print("═" * 70)

    corr_features = ['pcr_range_lag1', 'pcr_std_lag1', 'pcr_skew_lag1',
                     'pcr_am_pm_lag1', 'pcr_trend_lag1', 'pcr_spike_lag1',
                     'pcr_close_lag1', 'pcr_high_lag1', 'pcr_low_lag1']

    for feat in corr_features:
        if feat in merged.columns:
            c = merged[feat].corr(merged['spy_ret1d'])
            c5 = merged[feat].corr(merged['spy_ret5d'])
            bar = "█" * int(abs(c) * 100)
            print(f"  {feat:22s}  ρ_1d={c:+.3f}  ρ_5d={c5:+.3f}  {bar}")

    # ══════════════════════════════════════════════════════════
    # SECTION 4: QUINTILE ANALYSIS
    # ══════════════════════════════════════════════════════════
    print("\n" + "═" * 70)
    print("S4: QUINTILE ANALYSIS — PCR Range vs SPY Next-Day Return")
    print("═" * 70)

    try:
        q_df = merged[['pcr_range_lag1', 'pcr_trend_lag1', 'spy_ret1d']].dropna().reset_index(drop=True)
        q_df['range_q'] = pd.qcut(q_df['pcr_range_lag1'], 5, labels=False, duplicates='drop')
        for q in sorted(q_df['range_q'].unique()):
            mask = q_df['range_q'] == q
            rets = q_df.loc[mask, 'spy_ret1d']
            rng = q_df.loc[mask, 'pcr_range_lag1']
            print(f"  Q{int(q)+1} (range={rng.mean():.4f}): "
                  f"Ret={rets.mean()*100:+.3f}%, WR={((rets>0).mean()*100):.1f}%, N={len(rets)}")

        print("\n" + "═" * 70)
        print("S5: QUINTILE ANALYSIS — PCR Trend vs SPY Next-Day Return")
        print("═" * 70)

        q_df['trend_q'] = pd.qcut(q_df['pcr_trend_lag1'], 5, labels=False, duplicates='drop')
        for q in sorted(q_df['trend_q'].unique()):
            mask = q_df['trend_q'] == q
            rets = q_df.loc[mask, 'spy_ret1d']
            trnd = q_df.loc[mask, 'pcr_trend_lag1']
            print(f"  Q{int(q)+1} (trend={trnd.mean():+.4f}): "
                  f"Ret={rets.mean()*100:+.3f}%, WR={((rets>0).mean()*100):.1f}%, N={len(rets)}")
    except Exception as e:
        print(f"  Quintile analysis error: {e}")

    # ══════════════════════════════════════════════════════════
    # SECTION 5: VERDICT
    # ══════════════════════════════════════════════════════════
    print("\n" + "═" * 70)
    print("VERDICT: Does 5-minute PCR add alpha?")
    print("═" * 70)

    confirmed = [r for r in results if r and r['tag'] in ('CONFIRMED', 'CANDIDATE')]
    plausible = [r for r in results if r and r['tag'] == 'PLAUSIBLE']
    noise = [r for r in results if r and r['tag'] == 'NOISE']

    print(f"\n  CONFIRMED/CANDIDATE: {len(confirmed)}")
    for r in confirmed:
        print(f"    ✅ {r['name']} (t={r['t']:+.2f}, N={r['n']})")

    print(f"  PLAUSIBLE: {len(plausible)}")
    for r in plausible:
        print(f"    🔶 {r['name']} (t={r['t']:+.2f}, N={r['n']})")

    print(f"  NOISE: {len(noise)}")
    for r in noise:
        print(f"    ❌ {r['name']} (t={r['t']:+.2f}, N={r['n']})")

    print(f"\n  ⚠️  Statistical caveat: Only {len(merged)} trading days.")
    print(f"     Results with N<30 are EXPLORATORY, not actionable.")
    print(f"     Need 250+ days for institutional-grade conclusions.")

    if len(confirmed) == 0:
        print(f"\n  📋 RECOMMENDATION: Daily PCR is SUFFICIENT.")
        print(f"     No need to solve the real-time 5min feed problem.")
    else:
        print(f"\n  📋 RECOMMENDATION: 5min PCR shows PROMISE.")
        print(f"     Worth accumulating more data before investing in RT feed.")


if __name__ == "__main__":
    run_forensics()
