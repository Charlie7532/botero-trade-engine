"""
Compute Market Health — The Compositor

Orchestrates the 6 dimension classifiers + F&G signal layer
to produce a single MarketHealthSnapshot.

All inputs come from the Vault. Zero external API calls.
This is a pure domain use case — no infrastructure dependencies.

Evidence Status: CANDIDATE — composite scoring needs validation.
"""
import logging
from datetime import datetime, UTC
from typing import Optional

import pandas as pd

from backend.modules.market_health.domain.entities.health_snapshot import (
    MarketHealthSnapshot,
)
from backend.modules.market_health.domain.rules.cascade_classifier import (
    classify_cascade,
    compute_cascade_spread,
    detect_narrow_market,
    compute_breadth_participation,
)
from backend.modules.market_health.domain.rules.credit_classifier import (
    classify_credit,
)
from backend.modules.market_health.domain.rules.macro_cycle_classifier import (
    classify_yield_curve,
    extract_fred_regime,
)
from backend.modules.market_health.domain.rules.fg_signal import (
    compute_fg_analytics,
    compute_fg_divergence,
)
from backend.modules.market_health.domain.rules.convergence_scorer import (
    score_convergence,
)

logger = logging.getLogger(__name__)


def compute_market_health(
    # G1: Breadth — from Vault (S5 bars)
    s5fi_df: Optional[pd.DataFrame] = None,
    s5th_df: Optional[pd.DataFrame] = None,
    s5tw_df: Optional[pd.DataFrame] = None,
    # F&G — from Vault (FG bars, 14 years)
    fg_df: Optional[pd.DataFrame] = None,
    # G4: Credit — from Vault (HYG + TLT bars)
    hyg_df: Optional[pd.DataFrame] = None,
    tlt_df: Optional[pd.DataFrame] = None,
    # G2: Vol — from Vault (VIX bars for z-score)
    vix_df: Optional[pd.DataFrame] = None,
    # G6: Macro — from Vault (yields + FRED snapshot)
    yields_10y: Optional[pd.DataFrame] = None,
    yields_3m: Optional[pd.DataFrame] = None,
    fred_snapshot: Optional[dict] = None,
    # Optional injections from other service modules
    rotation_phase: str = "UNKNOWN",
    dominant_rotation: str = "NEUTRAL",
    capitulation_level: int = 0,
    flow_direction: str = "NEUTRAL",
    spy_pct_change_20d: float = 0.0,
) -> MarketHealthSnapshot:
    """Compute the 6D convergence snapshot + F&G contrarian layer.

    All DataFrames expected to have a 'close' column.
    Yields DataFrames expected to have a 'value' column.
    """
    snap = MarketHealthSnapshot(
        timestamp=datetime.now(UTC).isoformat(),
    )

    # ── G1: Breadth Cascade ──────────────────────────────────
    s5tw_val = _last_close(s5tw_df, 50.0)
    s5fi_val = _last_close(s5fi_df, 50.0)
    s5th_val = _last_close(s5th_df, 50.0)

    snap.cascade_state = classify_cascade(s5tw_val, s5fi_val, s5th_val)
    snap.cascade_spread = compute_cascade_spread(s5th_val, s5tw_val)
    snap.breadth_participation = compute_breadth_participation(
        s5tw_val, s5fi_val, s5th_val,
    )

    # Narrow market detection
    s5fi_change = 0.0
    if s5fi_df is not None and len(s5fi_df) >= 20:
        s5fi_change = float(s5fi_df["close"].iloc[-1] - s5fi_df["close"].iloc[-20])
    snap.narrow_market = detect_narrow_market(spy_pct_change_20d, s5fi_change)

    # ── G2: Volatility Regime ────────────────────────────────
    # Vol regime is INJECTED by the daemon provider (which runs
    # VolRegimeClassifier on SPY prices). Here we only compute the
    # dynamic VIX z-score (replacing the hardcoded 20.0/5.0).
    if vix_df is not None and not vix_df.empty and len(vix_df) >= 30:
        try:
            vix_close = vix_df["close"].astype(float)
            vix_now = float(vix_close.iloc[-1])
            vix_mean = float(vix_close.rolling(90, min_periods=30).mean().iloc[-1])
            vix_std = float(vix_close.rolling(90, min_periods=30).std().iloc[-1])
            snap._vix_zscore = (vix_now - vix_mean) / vix_std if vix_std > 0 else 0.0
        except Exception as e:
            logger.debug(f"MH: VIX z-score computation skipped: {e}")
    # vol_regime_quality and vol_regime_speculative stay at defaults
    # unless injected by the provider via the snapshot's fields

    # ── G3: Flow (injected) ──────────────────────────────────
    snap.flow_direction = flow_direction

    # ── G4: Credit Health ────────────────────────────────────
    if hyg_df is not None and tlt_df is not None:
        hyg_prices = hyg_df["close"].tolist() if not hyg_df.empty else []
        tlt_prices = tlt_df["close"].tolist() if not tlt_df.empty else []
        snap.credit_regime, snap.credit_spread_zscore = classify_credit(
            hyg_prices, tlt_prices,
        )

    # ── G5: Rotation (injected) ──────────────────────────────
    snap.rotation_phase = rotation_phase
    snap.dominant_rotation = dominant_rotation
    snap.capitulation_level = capitulation_level

    # ── G6: Macro Cycle ──────────────────────────────────────
    y10_list = _df_to_value_list(yields_10y)
    y3m_list = _df_to_value_list(yields_3m)
    snap.yield_curve_signal = classify_yield_curve(y10_list, y3m_list)
    snap.macro_regime, snap.fed_stance = extract_fred_regime(fred_snapshot)

    # ── Convergence Score (6 dimensions) ─────────────────────
    snap.convergence_score, snap.convergence_direction = score_convergence(
        cascade_state=snap.cascade_state,
        vol_regime_quality=snap.vol_regime_quality,
        flow_direction=snap.flow_direction,
        credit_regime=snap.credit_regime,
        rotation_phase=snap.rotation_phase,
        yield_curve_signal=snap.yield_curve_signal,
        macro_regime=snap.macro_regime,
    )

    # ── F&G Contrarian Signal Layer ──────────────────────────
    if fg_df is not None and not fg_df.empty:
        fg_history = fg_df["close"].tolist()
        # FG-H08: pass SPY drawdown for greed+correction trap detection
        fg_analytics = compute_fg_analytics(
            fg_history,
            spy_dd_pct=spy_pct_change_20d * 100 if spy_pct_change_20d < 0 else 0.0,
        )
        snap.fg_score = fg_analytics["fg_score"]
        snap.fg_regime = fg_analytics["fg_regime"]
        snap.fg_zscore = fg_analytics["fg_zscore"]
        snap.fg_velocity = fg_analytics["fg_velocity"]
        snap.fg_direction = fg_analytics["fg_direction"]
        snap.fg_action = fg_analytics["fg_action"]
        snap.fg_duration = fg_analytics["fg_duration"]
        snap.fg_urgency = fg_analytics["fg_urgency"]

        # Divergence detection (FG-H14 corrected interpretation)
        snap.fg_confirms_internal, snap.fg_divergence_type = compute_fg_divergence(
            snap.fg_regime, snap.convergence_direction,
        )

    logger.info(
        f"MH Snapshot: Cascade={snap.cascade_state} "
        f"Vol={snap.vol_regime_quality} Credit={snap.credit_regime} "
        f"Conv={snap.convergence_score}/6 {snap.convergence_direction} | "
        f"F&G={snap.fg_score:.0f} ({snap.fg_regime}) Action={snap.fg_action} "
        f"Div={snap.fg_divergence_type}"
    )

    return snap


# ── Helpers ──────────────────────────────────────────────────

def _last_close(df: Optional[pd.DataFrame], default: float) -> float:
    """Get last close value from a DataFrame, with fallback."""
    if df is None or df.empty:
        return default
    try:
        return float(df["close"].iloc[-1])
    except (KeyError, IndexError):
        return default


def _df_to_value_list(df: Optional[pd.DataFrame]) -> list[float]:
    """Convert a macro_data DataFrame to a list of values."""
    if df is None or df.empty:
        return []
    col = "value" if "value" in df.columns else "close"
    try:
        return df[col].dropna().tolist()
    except KeyError:
        return []
