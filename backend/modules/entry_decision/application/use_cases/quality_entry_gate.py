"""
QUALITY ENTRY GATE — USE CASE ORCHESTRATOR (CANONICAL B0 BASELINE)
===================================================================
Clean Architecture: Application Layer (Use Cases)
Module: entry_decision / application / use_cases

Official Institutional Baseline:
  - Canonical Output: 584.52 SPY shares / MaxDD -34.93% (T+0, close 2026-10-20)
  - Mandatory Latency Test: 599.34 SPY shares / MaxDD -40.78% (T+1)

Clean Architecture Decoupling:
  1. Pure Domain Regime Rules → QualityRegimeRules (domain/rules/quality_regime_rules.py)
  2. Pure Domain Allocation Rules → QualityAllocationRules (domain/rules/quality_allocation_rules.py)
  3. Formal Port Contract → QualityEntryGatePort (domain/ports/quality_entry_gate_port.py)
  4. Universal Action DTO → QualityRotationDTO (application/dtos/quality_rotation_dto.py)
  5. Orchestrator Integration → evaluate(ticker) satisfies QualityOrchestrator pipeline.
"""

from typing import Dict, Any, List, Optional
from backend.modules.entry_decision.domain.ports.quality_entry_gate_port import QualityEntryGatePort
from backend.modules.entry_decision.domain.rules.quality_regime_rules import QualityRegimeRules
from backend.modules.entry_decision.domain.rules.quality_allocation_rules import QualityAllocationRules
from backend.modules.entry_decision.application.dtos.quality_rotation_dto import QualityRotationDTO


class QualityEntryGate(QualityEntryGatePort):
    """
    Canonical Quality Entry Gate (B0 Baseline: 584.52 shares / -34.93% MaxDD T+0).
    Orchestrates domain regime transitions, portfolio weights, and ticker validation.
    """

    # Expose canonical domain constants for backward compatibility
    S5_EDGES = QualityRegimeRules.S5_EDGES
    SV5_EDGES = QualityRegimeRules.SV5_EDGES
    LABELS = QualityRegimeRules.LABELS
    TOP_DISTRIBUTION_STATES = QualityRegimeRules.TOP_DISTRIBUTION_STATES
    SV5_STD_VIX_CRASH_THRESHOLD = QualityRegimeRules.SV5_STD_VIX_CRASH_THRESHOLD
    SV5_TURBULENCE_HIGH_THRESHOLD = QualityRegimeRules.SV5_TURBULENCE_HIGH_THRESHOLD
    SV5_TURBULENCE_EXTREME_THRESHOLD = QualityRegimeRules.SV5_TURBULENCE_EXTREME_THRESHOLD
    SV5_SHOCK_HIGH_THRESHOLD = QualityRegimeRules.SV5_SHOCK_HIGH_THRESHOLD
    SV5_SHOCK_EXTREME_THRESHOLD = QualityRegimeRules.SV5_SHOCK_EXTREME_THRESHOLD

    def __init__(
        self,
        min_regime_days: int = 20,
        dist_exit_confirm: int = 2,
        dist_exit_hyst: bool = True,
    ):
        self.min_regime_days = min_regime_days
        self.dist_exit_confirm = dist_exit_confirm
        self.dist_exit_hyst = dist_exit_hyst
        self.exit_count = 0
        self.inv_fi_streak = 0
        self.prev_tw: Optional[float] = None
        self.fgbi_window: List[float] = []
        self.ratio_window: List[float] = []
        self.current_mode = "NORMAL"
        self.days_in_mode = 0

    def _classify_bin(self, v: float, edges: List[float]) -> str:
        return QualityRegimeRules.classify_bin(v, edges)

    def _get_spy_joint_state(
        self,
        th: float,
        fi: float,
        tw: float,
        tw_prev: float,
        v_th: float,
        v_fi: float,
        v_tw: float,
    ) -> str:
        return QualityRegimeRules.get_spy_joint_state(th, fi, tw, tw_prev, v_th, v_fi, v_tw)

    def evaluate_regime(
        self,
        th: float,
        fi: float,
        tw: float,
        v_th: float,
        v_fi: float,
        v_tw: float,
        sec_th: Dict[str, float],
        sec_fi: Dict[str, float],
        sec_tw: Dict[str, float],
        sec_v_tw: Optional[Dict[str, float]] = None,
        fi_velocity: float = 0.0,
        current_mode: str = "NORMAL",
        days_in_mode: int = 25,
        tw_prev: Optional[float] = None,
        fgbi: Optional[float] = None,
        vbi: Optional[float] = None,
        fgbi_peak_15d: Optional[float] = None,
        vix: Optional[float] = None,
        sv5_turbulence: Optional[float] = None,
        sv5_shock: Optional[float] = None,
    ) -> str:
        """
        Classifies the market mode using pure domain rules while maintaining telemetry windows.
        """
        if fgbi is not None:
            self.fgbi_window.append(fgbi)
            if len(self.fgbi_window) > 15:
                self.fgbi_window.pop(0)

        ratio = tw / max(1.0, v_tw)
        self.ratio_window.append(ratio)
        if len(self.ratio_window) > 7:
            self.ratio_window.pop(0)

        effective_tw_prev = tw if tw_prev is None else (self.prev_tw if self.prev_tw is not None else tw)
        self.prev_tw = tw

        new_mode, self.inv_fi_streak, self.exit_count = QualityRegimeRules.evaluate_transition(
            th=th,
            fi=fi,
            tw=tw,
            v_th=v_th,
            v_fi=v_fi,
            v_tw=v_tw,
            sec_th=sec_th,
            sec_fi=sec_fi,
            sec_tw=sec_tw,
            sec_v_tw=sec_v_tw,
            fi_velocity=fi_velocity,
            current_mode=current_mode,
            days_in_mode=days_in_mode,
            tw_prev=effective_tw_prev,
            fgbi=fgbi,
            vbi=vbi,
            fgbi_peak_15d=fgbi_peak_15d,
            vix=vix,
            sv5_turbulence=sv5_turbulence,
            sv5_shock=sv5_shock,
            min_regime_days=self.min_regime_days,
            dist_exit_confirm=self.dist_exit_confirm,
            dist_exit_hyst=self.dist_exit_hyst,
            inv_fi_streak=self.inv_fi_streak,
            exit_count=self.exit_count,
            fgbi_window=self.fgbi_window,
            ratio_window=self.ratio_window,
        )

        if new_mode == self.current_mode:
            self.days_in_mode += 1
        else:
            self.current_mode = new_mode
            self.days_in_mode = 1

        return new_mode

    def calculate_target_weights(
        self,
        mode: str,
        sec_th: Dict[str, float],
        sec_fi: Dict[str, float],
        sec_tw: Dict[str, float],
        avail_sectors: List[str],
        sec_v_fi: Optional[Dict[str, float]] = None,
        sec_v_tw: Optional[Dict[str, float]] = None,
        rs_roc_5d: Optional[Dict[str, float]] = None,
        sec_stage4: Optional[Dict[str, bool]] = None,
        rs_roc_50d: Optional[Dict[str, float]] = None,
        rs_roc_20d: Optional[Dict[str, float]] = None,
        s5cap_fi: Optional[Dict[str, float]] = None,
        sec_vbi: Optional[Dict[str, float]] = None,
        sv5_turbulence: Optional[float] = None,
        sv5_shock: Optional[float] = None,
        vix: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Calculates sector target weights delegating to pure domain allocation rules.
        """
        return QualityAllocationRules.calculate_target_weights(
            mode=mode,
            sec_th=sec_th,
            sec_fi=sec_fi,
            sec_tw=sec_tw,
            avail_sectors=avail_sectors,
            sec_v_fi=sec_v_fi,
            sec_v_tw=sec_v_tw,
            rs_roc_5d=rs_roc_5d,
            sec_stage4=sec_stage4,
            rs_roc_50d=rs_roc_50d,
            rs_roc_20d=rs_roc_20d,
            s5cap_fi=s5cap_fi,
            sec_vbi=sec_vbi,
            sv5_turbulence=sv5_turbulence,
            sv5_shock=sv5_shock,
            vix=vix,
        )

    def evaluate(self, ticker: str, **kwargs: Any) -> QualityRotationDTO:
        """
        Evaluates a ticker for Quality Department admission.
        Provides contract satisfaction for QualityOrchestrator pipeline.
        """
        mode = self.current_mode

        if mode == "CRASH_SISTEMICO":
            return QualityRotationDTO(
                mode=mode,
                ticker=ticker,
                action_code="STK_BLOCK_CRISIS",
                urgency="URGENCY_EMERGENCY",
                final_verdict="BLOCK",
                final_reason="Market in CRASH_SISTEMICO (100% Cash preservation)",
                final_scale=0.0,
            )

        if mode == "DISTRIBUCION_PRE_CRASH":
            defensive_tickers = {"XLP", "XLU", "XLV"}
            if ticker in defensive_tickers:
                return QualityRotationDTO(
                    mode=mode,
                    ticker=ticker,
                    action_code="STK_HOLD_STABLE",
                    urgency="URGENCY_NORMAL",
                    final_verdict="ALLOW",
                    final_reason="Defensive shelter approved in pre-crash distribution",
                    final_scale=0.50,
                )
            return QualityRotationDTO(
                mode=mode,
                ticker=ticker,
                action_code="STK_TRIM_TACTICAL",
                urgency="URGENCY_HIGH",
                final_verdict="STALK",
                final_reason="Pre-crash institutional distribution detected — non-defensives on hold",
                final_scale=0.50,
            )

        if mode == "PISO_GENERACIONAL":
            return QualityRotationDTO(
                mode=mode,
                ticker=ticker,
                action_code="STK_BUY_DIP_TACTICAL",
                urgency="URGENCY_HIGH",
                final_verdict="ALLOW",
                final_reason="Generational floor capitulation — offensive accumulation approved",
                final_scale=1.0,
            )

        return QualityRotationDTO(
            mode=mode,
            ticker=ticker,
            action_code="STK_ACCUMULATE_STRUCTURAL",
            urgency="URGENCY_NORMAL",
            final_verdict="ALLOW",
            final_reason=f"Regime {mode} supports structural quality allocation",
            final_scale=1.0,
        )
