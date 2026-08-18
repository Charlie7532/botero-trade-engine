"""
Tide Route Guidance — Predictive Waze Navigation DTO for Tide Model
===================================================================
Represents the complete prospective navigation guidance emitted by the Tide model:
  1. Homologated Action Taxonomy Code (STK_T_ACCUMULATE_STRUCTURAL, STK_T_BLOCK_CRISIS, etc.)
  2. Proactive Waze Road Hazard Alarms (HAZARD_CLIFF_FALL_CRISIS, HAZARD_ALPHA_DECAY, etc.)
  3. Current vs Forecast Next Regime (Markov Transition Inference P(S_{t+1} | S_t))
  4. Weighted Expected Value (W-EV) & Risk/Reward Asymmetry (R:R)
  5. Urgency Tags (FIX Protocol Tag 61/848: URGENCY_EMERGENCY, URGENCY_HIGH, etc.)

Clean Architecture: Pure domain entity. Zero dependencies.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

# ── Homologated Action Taxonomy Codes (STK_T_) ──
ACTION_STK_T_ACCUMULATE_STRUCTURAL = "STK_T_ACCUMULATE_STRUCTURAL"
ACTION_STK_T_BUY_DIP_TACTICAL = "STK_T_BUY_DIP_TACTICAL"
ACTION_STK_T_HOLD_STABLE = "STK_T_HOLD_STABLE"
ACTION_STK_T_TRIM_TACTICAL = "STK_T_TRIM_TACTICAL"
ACTION_STK_T_DISTRIBUTE_DECAY = "STK_T_DISTRIBUTE_DECAY"
ACTION_STK_T_EXIT_THESIS_DEATH = "STK_T_EXIT_THESIS_DEATH"
ACTION_STK_T_EXIT_TIME_STOP = "STK_T_EXIT_TIME_STOP"
ACTION_STK_T_BLOCK_CRISIS = "STK_T_BLOCK_CRISIS"

# ── Waze Road Hazard Alarms ──
HAZARD_NONE = "HAZARD_NONE"
HAZARD_CLIFF_FALL_CRISIS = "HAZARD_CLIFF_FALL_CRISIS"       # Acantilado en Ruta (T--- 94.1% persistencia)
HAZARD_ALPHA_DECAY = "HAZARD_ALPHA_DECAY"                   # Constricción / EV decay <= -0.015
HAZARD_OVEREXTENSION = "HAZARD_OVEREXTENSION"               # Tráfico Denso Techo (T+++ 60% EV drop)
HAZARD_STAGNANCY_FREEZE = "HAZARD_STAGNANCY_FREEZE"         # Vehículo Detenido (>90d stagnant)
HAZARD_POTHOLE_TURBULENCE = "HAZARD_POTHOLE_TURBULENCE"     # Bache Cinemático (SNR < 0.8x)

# ── Urgency Tags (FIX Protocol Tag 61/848) ──
URGENCY_EMERGENCY = "URGENCY_EMERGENCY"
URGENCY_HIGH = "URGENCY_HIGH"
URGENCY_NORMAL = "URGENCY_NORMAL"
URGENCY_LOW = "URGENCY_LOW"


@dataclass(frozen=True)
class TideRouteGuidance:
    """Immutable prospective guidance emitted by Predictive Tide Engine."""
    ticker: str
    action_code: str                  # e.g. STK_T_ACCUMULATE_STRUCTURAL
    signal_label: str                 # ACCUMULATE, BUY_DIP, BLOCK, TRIM, etc.
    hazard_alarm: str                 # HAZARD_CLIFF_FALL_CRISIS, HAZARD_NONE, etc.
    
    current_regime: str               # e.g. "T+|C-|<"
    forecast_next_regime: str         # e.g. "T++|C+|~" (Most probable next state)
    transition_probability: float     # P(forecast_next_regime | current_regime) e.g. 0.784
    
    top3_routes: List[Dict[str, Any]] = field(default_factory=list) # Top 3 forecast paths
    weighted_ev: float = 0.0          # Weighted Expected Value W-EV
    rr_asymmetry: float = 1.0         # Risk/Reward Asymmetry R:R
    sharpe: float = 0.0               # Sharpe Ratio
    
    certainty_score: float = 0.5      # Statistical Certainty Score (1 - variance)
    urgency: str = URGENCY_LOW        # URGENCY_EMERGENCY, URGENCY_HIGH, etc.
    recommended_sizing_multiplier: float = 1.0 # Dynamic Sizing (0.0x to 1.5x)
    
    fallback_level: str = "L3"        # "L3", "L2", "L1", "L0"
    is_rare_transition: bool = False
    
    @property
    def is_blocked(self) -> bool:
        return self.action_code == ACTION_STK_T_BLOCK_CRISIS or self.hazard_alarm == HAZARD_CLIFF_FALL_CRISIS

    @property
    def is_actionable_buy(self) -> bool:
        return self.action_code in (ACTION_STK_T_ACCUMULATE_STRUCTURAL, ACTION_STK_T_BUY_DIP_TACTICAL) and not self.is_blocked
