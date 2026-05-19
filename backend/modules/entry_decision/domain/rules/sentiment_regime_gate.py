"""
Sentiment Regime Gate — Domain Rule for Entry Decisions
========================================================
Classifies market sentiment regime from F&G + VIX + PCR + SPY momentum.

This is a domain rule — pure Python, no infra dependencies.
Follows the same pattern as vol_regime_gate.py.

Inputs come pre-fetched from the Vault (Vault-First architecture).
The gate NEVER calls external APIs or reads from the database directly.

Evidence Status: FG-H15 CONFIRMED (Sentiment Regime > raw F&G, 232% alpha)
Forensic source: backtest_fg_deep_forensics.py, 3,843 days (2011-2026)
"""
import pandas as pd
import numpy as np

from backend.modules.entry_decision.domain.entities.sentiment_regime import (
    SentimentRegime,
    SentimentRegimeState,
)


def classify_sentiment_regime(
    fg_level: float,
    vix_level: float,
    pcr_level: float,
    spy_mom5d: float,
    spy_mom20d: float = 0.0,
    spy_dd_from_high: float = 0.0,
    vix_direction: str = "FLAT",
    pcr_direction: str = "FLAT",
    vix_60d_mean: float = 18.0,
    consec_fear_days: int = 0,
) -> SentimentRegimeState:
    """Classify current market sentiment regime from observable indicators.

    Priority-ordered: first matching condition wins. This order is calibrated
    from forensic evidence — CAPITULATION has highest priority because it
    produces the strongest alpha (+4.29%, WR=75.9%).

    Args:
        fg_level: Current F&G index value (0-100).
        vix_level: Current VIX close.
        pcr_level: Current CBOE equity put/call ratio.
        spy_mom5d: SPY 5-day trailing return (%).
        spy_mom20d: SPY 20-day trailing return (%).
        spy_dd_from_high: SPY drawdown from 52w high (%, negative).
        vix_direction: "RISING" | "FLAT" | "FALLING" (5d ROC).
        pcr_direction: "RISING" | "FLAT" | "FALLING" (5d ROC).
        vix_60d_mean: 60-day rolling mean of VIX.
        consec_fear_days: Consecutive days with F&G < 25.

    Returns:
        SentimentRegimeState with classified regime, urgency, and inputs.
    """
    base = dict(
        fg_level=fg_level,
        vix_level=vix_level,
        pcr_level=pcr_level,
        spy_mom5d=spy_mom5d,
        consec_fear_days=consec_fear_days,
    )

    # ── 1. CAPITULATION: Extreme fear + high VIX + SPY crashing ──
    # Ret=+4.29%, WR=75.9%, N=112
    if fg_level < 20 and vix_level > 25 and spy_mom5d < -2:
        urgency = _compute_urgency(consec_fear_days)
        return SentimentRegimeState(
            regime=SentimentRegime.CAPITULATION, urgency=urgency, **base,
        )

    # ── 2. STRESS: Low F&G + VIX rising + SPY falling ──
    # Ret=+1.43%, WR=67.3%, N=266
    if fg_level < 35 and vix_direction == "RISING" and spy_mom5d < 0:
        return SentimentRegimeState(
            regime=SentimentRegime.STRESS, urgency="LOW", **base,
        )

    # ── 3. RECOVERY: Fear receding + VIX falling + SPY bouncing ──
    # Ret=+1.52%, WR=69.4%, N=206
    if 20 <= fg_level < 40 and vix_direction == "FALLING" and spy_mom5d > 0:
        return SentimentRegimeState(
            regime=SentimentRegime.RECOVERY, urgency="NONE", **base,
        )

    # ── 4. WALL_OF_WORRY: Neutral + SPY rising + VIX above avg ──
    # Ret=+0.36%, WR=66.3%, N=246
    if 30 <= fg_level < 55 and spy_mom20d > 0 and vix_level > vix_60d_mean:
        return SentimentRegimeState(
            regime=SentimentRegime.WALL_OF_WORRY, urgency="NONE", **base,
        )

    # ── 5. DISTRIBUTION: Greed + VIX rising + PCR rising ──
    # Ret=+0.97%, WR=63.3%, N=30 (small sample — monitor)
    if fg_level > 65 and vix_direction == "RISING" and pcr_direction == "RISING":
        return SentimentRegimeState(
            regime=SentimentRegime.DISTRIBUTION, urgency="NONE", **base,
        )

    # ── 6. EUPHORIA: Extreme greed + low VIX + SPY near highs ──
    # Ret=+0.78%, WR=69.8%, N=318
    if fg_level > 75 and vix_level < 18 and spy_dd_from_high > -3:
        return SentimentRegimeState(
            regime=SentimentRegime.EUPHORIA, urgency="NONE", **base,
        )

    # ── 7. COMPLACENCY: Mid-high F&G + very low VIX + low PCR ──
    # Ret=-0.14%, WR=57.3%, N=211 — ONLY negative regime
    if 55 <= fg_level <= 75 and vix_level < 15 and pcr_level < 0.85:
        return SentimentRegimeState(
            regime=SentimentRegime.COMPLACENCY, urgency="NONE", **base,
        )

    # ── 8. NORMAL_BULL: Default — no extreme conditions ──
    # Ret=+0.95%, WR=67.1%, N=2454 (base rate)
    return SentimentRegimeState(
        regime=SentimentRegime.NORMAL_BULL, urgency="NONE", **base,
    )


def _compute_urgency(consec_fear_days: int) -> str:
    """Urgency from consecutive fear days. U-shaped curve from forensics.

    Day 1-10:  WR 60-68% → LOW (sell-off immature)
    Day 11-20: WR 72.6%  → HIGH (exhaustion begins)
    Day 21+:   WR 86.4%  → MAXIMUM (confirmed exhaustion)
    """
    if consec_fear_days >= 21:
        return "MAXIMUM"
    elif consec_fear_days >= 11:
        return "HIGH"
    return "LOW"


def compute_sentiment_regime_snapshot(
    fg_bars: pd.DataFrame,
    vix_bars: pd.DataFrame,
    pcr_bars: pd.DataFrame,
    spy_bars: pd.DataFrame,
) -> SentimentRegimeState:
    """Compute sentiment regime from Vault OHLCV bars.

    Convenience function that extracts the latest values from bar DataFrames
    and delegates to classify_sentiment_regime(). This is the entry point
    used by QualityEntryGate and SpeculativeEntryHub.

    Args:
        fg_bars: F&G bars with 'close' column. Min 5 rows.
        vix_bars: VIX bars with 'close' column. Min 60 rows.
        pcr_bars: CBOE_PCR bars with 'close' column. Min 5 rows.
        spy_bars: SPY bars with 'close' column. Min 60 rows.

    Returns:
        SentimentRegimeState with classified regime.
    """
    if any(df is None or len(df) < 5 for df in [fg_bars, vix_bars, pcr_bars, spy_bars]):
        return SentimentRegimeState()

    # ── Extract latest values ──
    fg_level = float(fg_bars["close"].iloc[-1])
    vix_level = float(vix_bars["close"].iloc[-1])
    pcr_level = float(pcr_bars["close"].iloc[-1])

    spy_close = spy_bars["close"].astype(float)

    # ── SPY momentum ──
    spy_mom5d = float((spy_close.iloc[-1] / spy_close.iloc[-6] - 1) * 100) if len(spy_close) >= 6 else 0.0
    spy_mom20d = float((spy_close.iloc[-1] / spy_close.iloc[-21] - 1) * 100) if len(spy_close) >= 21 else 0.0

    # ── SPY drawdown from high ──
    spy_high = spy_close.rolling(252, min_periods=60).max()
    spy_dd = float((spy_close.iloc[-1] / spy_high.iloc[-1] - 1) * 100) if not np.isnan(spy_high.iloc[-1]) else 0.0

    # ── VIX direction (5d ROC) ──
    vix_close = vix_bars["close"].astype(float)
    vix_roc5 = float(vix_close.iloc[-1] - vix_close.iloc[-6]) if len(vix_close) >= 6 else 0.0
    if vix_roc5 > 2:
        vix_direction = "RISING"
    elif vix_roc5 < -2:
        vix_direction = "FALLING"
    else:
        vix_direction = "FLAT"

    # ── VIX 60d mean ──
    vix_60d_mean = float(vix_close.rolling(60, min_periods=20).mean().iloc[-1])

    # ── PCR direction (5d ROC) ──
    pcr_close = pcr_bars["close"].astype(float)
    pcr_roc5 = float(pcr_close.iloc[-1] - pcr_close.iloc[-6]) if len(pcr_close) >= 6 else 0.0
    if pcr_roc5 > 0.05:
        pcr_direction = "RISING"
    elif pcr_roc5 < -0.05:
        pcr_direction = "FALLING"
    else:
        pcr_direction = "FLAT"

    # ── Consecutive fear days ──
    fg_close = fg_bars["close"].astype(float)
    consec = 0
    for val in reversed(fg_close.values):
        if val < 25:
            consec += 1
        else:
            break

    return classify_sentiment_regime(
        fg_level=fg_level,
        vix_level=vix_level,
        pcr_level=pcr_level,
        spy_mom5d=spy_mom5d,
        spy_mom20d=spy_mom20d,
        spy_dd_from_high=spy_dd,
        vix_direction=vix_direction,
        pcr_direction=pcr_direction,
        vix_60d_mean=vix_60d_mean,
        consec_fear_days=consec,
    )
