"""
Quality Entry Gate — Pure Domain Decision Engine
=================================================
Orchestrates institutional state vectors into 4-dimensional Universal Taxonomy actions:
  [SCOPE]_[INTENT]_[EXECUTION] + Urgency Tag (FIX Tag 61/848)

Adheres strictly to Rule 20 of AGENTS.md:
  - STK_ACCUMULATE_STRUCTURAL (High-conviction trend accumulation)
  - STK_BUY_DIP_TACTICAL      (Tactical rebound on oversold capitulation)
  - STK_HOLD_STABLE           (Maintain position in neutral regime)
  - STK_TRIM_TACTICAL         (Harvest profit / Tactical trim)
  - STK_DISTRIBUTE_DECAY      (Distribution / Exit on exhaustion or ceiling)
  - STK_EXIT_TIME_STOP        (Time-barrier horizon expiry)
  - STK_BLOCK_CRISIS          (Volatility/Macro crisis veto)

Clean Architecture: Pure domain rule. No I/O, no side effects. Fully unit-testable.
"""
from dataclasses import dataclass
from typing import Optional, List, Tuple

from backend.modules.quality_swing.domain.rules.rc_multiscale_ev_lookup import (
    MultiscaleEVKinematicSignal,
)
from backend.modules.quality_swing.domain.rules.rc_state_probability import (
    DualProbability,
)


@dataclass(frozen=True)
class QualityGateDecision:
    action_code: str          # e.g. STK_ACCUMULATE_STRUCTURAL
    urgency_tag: str          # e.g. URGENCY_HIGH
    conviction_weight: float  # 0.0 - 1.0 position sizing scale factor
    reasoning: str            # Detailed forensic justification
    ev_net_target: float      # Scale-conditional expected return
    rr_asymmetry: float       # Scale-conditional risk-reward ratio
    state_snapshot_key: str   # Snapshot key format: vol:quality:MARKET


def evaluate_quality_entry_gate(
    multiscale_signal: Optional[MultiscaleEVKinematicSignal],
    dual_prob: Optional[DualProbability] = None,
    vol_regime_label: str = "NORMAL",
    sector: Optional[str] = None,
    is_tollkeeper: bool = False,
    holding_days: int = 0,
    window_signals: Optional[List[MultiscaleEVKinematicSignal]] = None,
) -> QualityGateDecision:
    """Evaluate institutional entry gate adhering strictly to Rule 20 Taxonomy."""
    
    # ── 1. EMERGENCY VETO: CRISIS REGIME ──
    if vol_regime_label == "CRISIS":
        return QualityGateDecision(
            action_code="STK_BLOCK_CRISIS",
            urgency_tag="URGENCY_EMERGENCY",
            conviction_weight=0.0,
            reasoning="VOL_CRISIS: Volatility Spike Veto — All stock accumulations blocked",
            ev_net_target=0.0,
            rr_asymmetry=0.0,
            state_snapshot_key="vol:quality:CRISIS_VETO",
        )

    # ── 2. EXPIRATION BARRIER: TIME STOP ──
    if holding_days >= 10:
        return QualityGateDecision(
            action_code="STK_EXIT_TIME_STOP",
            urgency_tag="URGENCY_NORMAL",
            conviction_weight=0.0,
            reasoning=f"TIME_STOP_EXPIRY: Position reached {holding_days}-day vertical barrier — Liquidation mandated to prevent entropy decay",
            ev_net_target=0.0,
            rr_asymmetry=0.0,
            state_snapshot_key="time:quality:VERTICAL_BARRIER_10D",
        )

    if multiscale_signal is None:
        return QualityGateDecision(
            action_code="STK_HOLD_STABLE",
            urgency_tag="URGENCY_LOW",
            conviction_weight=0.0,
            reasoning="NO_SIGNAL: Insufficient kinematic data — Maintain neutral hold",
            ev_net_target=0.0,
            rr_asymmetry=1.0,
            state_snapshot_key="state:quality:NO_SIGNAL",
        )

    # Extract Key Metrics
    p_b = multiscale_signal.p_bull
    ev_n = multiscale_signal.ev_net
    rr_asym = multiscale_signal.rr_asymmetry
    p_techo_75 = multiscale_signal.p_techo_75
    traj = multiscale_signal.kinematic_trajectory
    lookup_key = multiscale_signal.lookup_key

    # Confirm Volumetric Floor Absorption (from DualProbability)
    has_piso_absorption = (dual_prob is not None and dual_prob.piso_dominant and dual_prob.prob_piso >= 0.50)
    has_techo_distribution = (dual_prob is not None and dual_prob.techo_dominant and dual_prob.prob_techo >= 0.50)

    # Confirm Window-based Exhaustion (over m-samples, if provided)
    is_window_exhausting = True
    if window_signals and len(window_signals) >= 2:
        is_window_exhausting = all(s.kinematic_trajectory == "EXHAUSTING" for s in window_signals[-2:])

    # Sector Payoff Multipliers (Factual Empirical Calibration)
    sector_mult = 1.0
    if sector == "Technology":
        sector_mult = 1.5  # High-beta explosive payoff factor
    elif sector in ["Consumer Defensive", "Utilities"]:
        sector_mult = 0.8  # Low-beta steady floor factor

    # ── 3. ACTION PATH: STK_DISTRIBUTE_DECAY ──
    if p_techo_75 >= 0.15 or ev_n <= -0.015 or has_techo_distribution:
        return QualityGateDecision(
            action_code="STK_DISTRIBUTE_DECAY",
            urgency_tag="URGENCY_NORMAL",
            conviction_weight=0.0,
            reasoning=f"DISTRIBUTION_DECAY: Ceiling risk P(techo_75)={p_techo_75:.1%} EV={ev_n:+.4f} key=[{lookup_key}]",
            ev_net_target=ev_n,
            rr_asymmetry=rr_asym,
            state_snapshot_key=f"decay:quality:{lookup_key}",
        )

    # ── 4. ACTION PATH: STK_BUY_DIP_TACTICAL (Oversold Capitulation / High Asymmetry) ──
    # Condition: Extremes of oversold ("<<" or "<") + R:R >= 3.5x + EXHAUSTING
    is_oversold_zone = ("<<" in lookup_key or "<" in lookup_key)
    if is_oversold_zone and rr_asym >= 3.5 and (traj == "EXHAUSTING" and is_window_exhausting):
        urgency = "URGENCY_HIGH" if (has_piso_absorption or is_tollkeeper) else "URGENCY_NORMAL"
        conviction = min(1.0, round(0.7 * (1.2 if is_tollkeeper else 1.0) * sector_mult, 2))
        
        return QualityGateDecision(
            action_code="STK_BUY_DIP_TACTICAL",
            urgency_tag=urgency,
            conviction_weight=conviction,
            reasoning=f"TACTICAL_DIP_OVERSOLD: Asymmetry R:R={rr_asym:.2f}x EV_50={multiscale_signal.ev_net_50:+.4f} traj=[{traj}] key=[{lookup_key}]",
            ev_net_target=multiscale_signal.ev_net_50,
            rr_asymmetry=rr_asym,
            state_snapshot_key=f"dip:quality:{lookup_key}",
        )

    # ── 5. ACTION PATH: STK_ACCUMULATE_STRUCTURAL (Trend Plena / High Probability) ──
    # Condition: High P_bull (>= 71.8% or >= 65% for Tollkeepers) + Megatrend (T+ or T++)
    min_pbull_target = 0.65 if is_tollkeeper else 0.718
    if p_b >= min_pbull_target and ("T+" in lookup_key or "T++" in lookup_key or "T+++" in lookup_key):
        conviction = min(1.0, round(0.85 * (1.15 if is_tollkeeper else 1.0) * (1.2 if has_piso_absorption else 1.0), 2))
        urgency = "URGENCY_HIGH" if p_b >= 0.75 else "URGENCY_NORMAL"

        return QualityGateDecision(
            action_code="STK_ACCUMULATE_STRUCTURAL",
            urgency_tag=urgency,
            conviction_weight=conviction,
            reasoning=f"STRUCTURAL_ACCUMULATION: High P_bull={p_b:.1%} EV_75={multiscale_signal.ev_net_75:+.4f} tollkeeper={is_tollkeeper} key=[{lookup_key}]",
            ev_net_target=multiscale_signal.ev_net_75,
            rr_asymmetry=rr_asym,
            state_snapshot_key=f"accum:quality:{lookup_key}",
        )

    # ── 6. DEFAULT ACTION PATH: STK_HOLD_STABLE ──
    return QualityGateDecision(
        action_code="STK_HOLD_STABLE",
        urgency_tag="URGENCY_LOW",
        conviction_weight=0.0,
        reasoning=f"NEUTRAL_REGIME: P_bull={p_b:.1%} EV={ev_n:+.4f} key=[{lookup_key}] — Maintain position",
        ev_net_target=ev_n,
        rr_asymmetry=rr_asym,
        state_snapshot_key=f"hold:quality:{lookup_key}",
    )
