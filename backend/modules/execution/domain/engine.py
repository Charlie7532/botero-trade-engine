import logging
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class PositionState(Enum):
    FLAT = 0         # Sin posición
    PROBING = 1      # Sonda inicial inyectada
    SCALING_IN = 2   # Posición Core inyectada por confirmación
    SCALING_OUT = 3  # Distribución parcial de ganancias

@dataclass
class TradeContext:
    ticker: str
    current_price: float
    lstm_probability: float
    target_kelly_pct: float
    current_state: PositionState = PositionState.FLAT
    average_entry: float = 0.0
    current_exposure_pct: float = 0.0

class InstitutionalExecutionEngine:
    """
    Motor de Ejecución Institucional Calibrado.
    
    CALIBRACIÓN EMPÍRICA (Walk-Forward 9 folds, 2017-2025):
    - La LSTM produce probabilidades en rango [0.35, 0.65], NO [0, 1]
    - El threshold óptimo es 0.52 (no 0.90 como estaba antes)
    - Kelly fraccional capped a 3% máximo por trade
    - En capitulación (Level 3+), override al modelo con sizing agresivo
    
    Implementa Scaling-In/Out con 3 estados:
    1. FLAT → PROBING: Entrada con sonda (1/3 del Kelly)
    2. PROBING → SCALING_IN: Confirmación con core (2/3 restante)
    3. SCALING_IN → SCALING_OUT → FLAT: Distribución gradual
    """
    
    # Calibrado con datos OOS reales del Walk-Forward
    DEFAULT_TRIGGER = 0.52      # Probabilidad mínima para abrir (antes era 0.90)
    DEFAULT_CONFIRM = 0.54      # Prob para escalar (antes era 0.85)
    DEFAULT_ABORT = 0.47        # Prob para abortar (antes era 0.50)
    MAX_KELLY_PCT = 0.03        # 3% máximo por trade
    MIN_KELLY_PCT = 0.005       # 0.5% mínimo
    
    def __init__(
        self,
        probe_fraction: float = 0.33,
        trigger_threshold: float = None,
        confirm_threshold: float = None,
        abort_threshold: float = None,
        max_risk_pct: float = None,
    ):
        self.probe_fraction = probe_fraction
        self.trigger_threshold = trigger_threshold or self.DEFAULT_TRIGGER
        self.confirm_threshold = confirm_threshold or self.DEFAULT_CONFIRM
        self.abort_threshold = abort_threshold or self.DEFAULT_ABORT
        self.max_risk_pct = max_risk_pct or self.MAX_KELLY_PCT
        
        logger.info(
            f"ExecutionEngine calibrado: trigger={self.trigger_threshold:.2f}, "
            f"confirm={self.confirm_threshold:.2f}, abort={self.abort_threshold:.2f}, "
            f"max_risk={self.max_risk_pct*100:.1f}%"
        )

    def _cap_kelly(self, raw_kelly_pct: float) -> float:
        """Limita el Kelly entre MIN y MAX para evitar drawdowns catastróficos."""
        return max(self.MIN_KELLY_PCT, min(raw_kelly_pct, self.max_risk_pct))

    def evaluate_execution(
        self,
        context: TradeContext,
        volatility_ratio: float = 1.0,
        capitulation_level: int = 0,
        sector_alignment: str = "unknown",
    ) -> dict:
        """
        Calcula la orden exacta a enviar al broker.
        
        Args:
            context: Estado actual del trade
            volatility_ratio: TS_VolRatio (>1.5 = expansión, <0.7 = compresión)
            capitulation_level: Del CapitulationDetector (0-4)
            sector_alignment: Del SectorFlowEngine (WITH_TIDE, AGAINST_TIDE, etc.)
        """
        lstm_prob = context.lstm_probability
        capped_kelly = self._cap_kelly(context.target_kelly_pct)
        
        # ── CAPITULATION OVERRIDE ──
        # En capitulación Level 3+, el modelo estadístico supera al ML
        # Evidencia: VIX>35 + S5TW<15% → +10.71% a 60 días
        if capitulation_level >= 3 and context.current_state == PositionState.FLAT:
            override_size = self.max_risk_pct  # Usar el máximo permitido
            logger.warning(
                f"[{context.ticker}] 🔥 CAPITULATION OVERRIDE Level {capitulation_level} "
                f"→ PROBE con {override_size*100:.1f}% (bypass LSTM)"
            )
            return {
                'action': 'BUY_PROBE',
                'target_pct': override_size * self.probe_fraction,
                'reason': f'Capitulation_L{capitulation_level}_Override',
                'new_state': PositionState.PROBING,
            }
        
        # ── SECTOR FILTER ──
        # No abrir posiciones en acciones contra la corriente del sector
        if sector_alignment == "AGAINST_TIDE" and context.current_state == PositionState.FLAT:
            return {
                'action': 'HOLD_CASH',
                'target_pct': 0.0,
                'reason': 'Against_Sector_Tide',
                'new_state': PositionState.FLAT,
            }
        
        # 1. ESTADO [FLAT] → Búsqueda del Francotirador
        if context.current_state == PositionState.FLAT:
            if lstm_prob >= self.trigger_threshold:
                sonde_size = capped_kelly * self.probe_fraction
                
                # Bonus de convicción si el sector acompaña
                if sector_alignment == "WITH_TIDE":
                    sonde_size *= 1.2  # +20% sizing con el sector a favor
                    sonde_size = min(sonde_size, self.max_risk_pct * self.probe_fraction)
                
                logger.info(
                    f"[{context.ticker}] PROBE LSTM {lstm_prob*100:.1f}% → "
                    f"Entrada {sonde_size*100:.2f}% (sector={sector_alignment})"
                )
                return {
                    'action': 'BUY_PROBE',
                    'target_pct': sonde_size,
                    'reason': 'LSTM_Trigger',
                    'new_state': PositionState.PROBING,
                }
            else:
                return {
                    'action': 'HOLD_CASH',
                    'target_pct': 0.0,
                    'reason': f'Low_Prob_{lstm_prob:.2f}',
                    'new_state': PositionState.FLAT,
                }
                
        # 2. ESTADO [PROBING] → Scaling-In o Abortar
        elif context.current_state == PositionState.PROBING:
            # Confirmación: precio a favor + LSTM mantiene convicción
            if context.current_price > context.average_entry and lstm_prob >= self.confirm_threshold:
                core_size = capped_kelly * (1.0 - self.probe_fraction)
                logger.info(
                    f"[{context.ticker}] SCALING-IN confirmado → "
                    f"Core {core_size*100:.2f}% (total={capped_kelly*100:.2f}%)"
                )
                return {
                    'action': 'BUY_CORE',
                    'target_pct': core_size,
                    'reason': 'Confirmation_ScaleIn',
                    'new_state': PositionState.SCALING_IN,
                }
            
            # Abortar si la convicción cae
            if lstm_prob < self.abort_threshold:
                logger.warning(
                    f"[{context.ticker}] ABORT sonda — LSTM cayó a {lstm_prob*100:.1f}%"
                )
                return {
                    'action': 'SELL_ABORT',
                    'target_pct': -context.current_exposure_pct,
                    'reason': 'LSTM_Below_Abort',
                    'new_state': PositionState.FLAT,
                }
                
            return {
                'action': 'HOLD_POSITION',
                'target_pct': 0.0,
                'reason': 'Waiting_Confirmation',
                'new_state': context.current_state,
            }

        # 3. ESTADO [SCALING_IN/OUT] → Distribución gradual
        elif context.current_state in [PositionState.SCALING_IN, PositionState.SCALING_OUT]:
            # Scale-out si la volatilidad se expande o el LSTM pierde convicción
            if lstm_prob < self.abort_threshold or volatility_ratio > 2.0:
                sell_block = min(
                    context.current_exposure_pct,
                    capped_kelly * 0.33,
                )
                
                if context.current_exposure_pct - sell_block > 0.005:
                    logger.info(
                        f"[{context.ticker}] Scale-Out táctico {sell_block*100:.2f}%"
                    )
                    return {
                        'action': 'SELL_SCALE_OUT',
                        'target_pct': -sell_block,
                        'reason': 'Vol_Expansion_Distribution',
                        'new_state': PositionState.SCALING_OUT,
                    }
                else:
                    logger.info(f"[{context.ticker}] CIERRE TOTAL")
                    return {
                        'action': 'SELL_CLOSE',
                        'target_pct': -context.current_exposure_pct,
                        'reason': 'Full_Distribution',
                        'new_state': PositionState.FLAT,
                    }
                    
            return {
                'action': 'HOLD_POSITION',
                'target_pct': 0.0,
                'reason': 'Riding_Trend',
                'new_state': context.current_state,
            }

        return {
            'action': 'UNKNOWN',
            'target_pct': 0.0,
            'reason': 'Invalid_State',
            'new_state': context.current_state,
        }
