import logging
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, UTC

from backend.modules.portfolio_management.domain.rules.relative_strength import RelativeStrengthMonitor
from backend.modules.execution.domain.entities.exit_context import TradeState, MarketContext, ExitDecision

logger = logging.getLogger(__name__)

@dataclass
class AdaptiveTrailingStop:
    """
    Trailing stop que se adapta al régimen del mercado.
    
    EVIDENCIA del backtest (SPX 2017-2025):
    - Fixed -10%: PF 4.57, WR 66.7% (mejor en mercado trending)
    - ATR × 3.5: PF 1.25, WR 52.6% (mejor en mercado choppy)
    - ATR × 1.5-2.5: PF < 1 (PERDEDORES — demasiado tight)
    
    SOLUCIÓN: Usar max(ATR_trailing, fixed_trailing).
    """
    atr_multiplier_trend: float = 3.0
    atr_multiplier_chop: float = 2.0
    fixed_floor_pct: float = 0.05
    fixed_ceiling_pct: float = 0.12
    
    VIX_NORMAL = 18
    VIX_ELEVATED = 25
    VIX_HIGH = 35
    
    def calculate_stop(
        self,
        highest_since_entry: float,
        current_atr: float,
        rs_vs_spy: float = 1.0,
        put_wall: float = 0.0,
        vix_current: float = 17.0,
        flow_persistence_grade: str = "UNKNOWN",
    ) -> float:
        if rs_vs_spy > 1.05:
            mult = self.atr_multiplier_trend
        elif rs_vs_spy < 0.95:
            mult = self.atr_multiplier_chop
        else:
            mult = (self.atr_multiplier_trend + self.atr_multiplier_chop) / 2
        
        vix_scale = 1.0
        if vix_current > self.VIX_HIGH:
            vix_scale = 2.0
        elif vix_current > self.VIX_ELEVATED:
            vix_scale = 1.5
        elif vix_current > self.VIX_NORMAL:
            vix_scale = 1.2
        
        mult *= vix_scale
        
        if flow_persistence_grade == "CONFIRMED_STREAK":
            mult *= 1.15
        elif flow_persistence_grade == "DEAD_SIGNAL":
            mult *= 0.90
        
        atr_stop = highest_since_entry - (mult * current_atr)
        fixed_stop_low = highest_since_entry * (1 - self.fixed_floor_pct)
        fixed_stop_high = highest_since_entry * (1 - self.fixed_ceiling_pct)
        
        stop = max(atr_stop, fixed_stop_high)
        stop = min(stop, fixed_stop_low)
        
        if put_wall > 0 and put_wall < highest_since_entry:
            gamma_stop = put_wall - (0.3 * current_atr * vix_scale)
            stop = min(stop, gamma_stop)
        
        return round(stop, 2)
    
    def should_freeze(
        self,
        freeze_stops: bool = False,
        freeze_start_time: Optional[datetime] = None,
        freeze_duration_min: int = 30,
    ) -> bool:
        if not freeze_stops:
            return False
        if freeze_start_time is None:
            return True
        elapsed = (datetime.now(UTC) - freeze_start_time).total_seconds() / 60
        return elapsed < freeze_duration_min


class ExitEngine:
    """
    Motor unificado que evalúa si un trade debe cerrarse
    y actualiza sus niveles de trailing stop.
    """
    def __init__(self):
        self.trailing = AdaptiveTrailingStop()
        self.rs_monitor = RelativeStrengthMonitor()

    def evaluate_exit(self, state: TradeState, context: MarketContext) -> ExitDecision:
        """
        Evalúa todas las condiciones de salida en orden de prioridad.
        Returns:
            ExitDecision object con should_exit = True si alguna condición se cumple.
        """
        decision = ExitDecision(should_exit=False, new_stop_price=state.current_stop)
        
        # 1. ACTUALIZACIÓN DEL STOP LOSS
        # ----------------------------------------------------
        is_frozen = self.trailing.should_freeze(
            freeze_stops=context.freeze_stops,
            freeze_start_time=context.freeze_start_time
        )
        
        if not is_frozen:
            calculated_stop = self.trailing.calculate_stop(
                highest_since_entry=state.highest_price,
                current_atr=context.current_atr,
                rs_vs_spy=context.rs_vs_spy,
                put_wall=context.put_wall,
                vix_current=context.vix_current,
                flow_persistence_grade=context.flow_persistence_grade
            )
            # El stop solo puede subir
            decision.new_stop_price = max(state.current_stop, calculated_stop)
        
        # 2. EVALUACIÓN DE SALIDAS (EXITS)
        # ----------------------------------------------------
        
        # Exit A: STOP LOSS HIT (La más importante, risk management primero)
        if context.current_price <= decision.new_stop_price:
            decision.should_exit = True
            decision.reason = 'STOP_HIT'
            decision.urgency = 'high'
            return decision

        # Exit B: MA20 REVERSION TARGET
        # Empíricamente validado: Las reversiones a la media natural targetean la MA20.
        if context.current_price >= context.ma20 and state.bars_held >= 2:
            decision.should_exit = True
            decision.reason = 'MA20_REVERSION'
            decision.urgency = 'medium'
            return decision

        # Exit C: RS DECAY (Alpha se agota)
        # Usar el RS Monitor (el mismo del portfolio optimizer)
        rs_decay = context.rs_vs_spy / state.entry_rs if state.entry_rs > 0 else 1.0
        
        # Simular el registro de entrada temporal para usar la lógica compartida
        self.rs_monitor.register_entry(state.ticker, state.entry_rs)
        rs_eval = self.rs_monitor.should_exit(state.ticker, context.rs_vs_spy)
        
        if rs_eval['exit']:
            decision.should_exit = True
            decision.reason = 'RS_DECAY'
            decision.urgency = rs_eval['urgency']
            return decision

        # Exit D: DISTRIBUTION (Kalman confirma techo institucional)
        if context.wyckoff_state == 'DISTRIBUTION' and state.bars_held >= 3:
            decision.should_exit = True
            decision.reason = 'DISTRIBUTION'
            decision.urgency = 'high'
            return decision

        # Exit E: TIMEOUT (Evitar capital muerto)
        if state.bars_held >= context.max_bars:
            decision.should_exit = True
            decision.reason = 'TIMEOUT'
            decision.urgency = 'medium'
            return decision

        return decision
