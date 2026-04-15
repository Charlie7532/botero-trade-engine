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
    Motor Fraccional de Fricción y Volumen.
    Implementa el Scaling-In (Tanteo de Terreno) y Scaling-Out (Distribución de Beneficios).
    Nunca entra "All-in" ciegamente. Requiere altísima probabilidad LSTM para la primera sonda,
    y convicción (dirección ganadora) para escalar al Core.
    """
    def __init__(self, probe_fraction: float = 0.33, trigger_threshold: float = 0.90):
        """
        probe_fraction: Fracción del Kelly Risk a usar en la primera entrada (ej. 1/3 del poder).
        trigger_threshold: Certeza mínima exigida a la red neuronal LSTM para abrir una posición.
        """
        self.probe_fraction = probe_fraction
        self.trigger_threshold = trigger_threshold

    def evaluate_execution(self, context: TradeContext, volatility_bbw: float) -> dict:
        """
        Calcula la orden exacta a enviar al Creador de Mercado o Simulador.
        Retorna: dict con 'action', 'size_pct' a añadir/restar, 'reason'.
        """
        lstm_prob = context.lstm_probability
        
        # 1. ESTADO [FLAT] -> Búsqueda del Francotirador
        if context.current_state == PositionState.FLAT:
            if lstm_prob >= self.trigger_threshold:
                # Entrar con Sonda Limitada (Ej: Si el Kelly Risk da 10%, entramos con 3.3%)
                sonde_size = context.target_kelly_pct * self.probe_fraction
                logger.info(f"[{context.ticker}] FRANCOTIRADOR LSTM {lstm_prob*100:.1f}% -> DISPARO PROBE ({sonde_size*100:.2f}% Cuenta)")
                return {'action': 'BUY_PROBE', 'target_pct': sonde_size, 'reason': 'LSTM_Trigger_90_Plus', 'new_state': PositionState.PROBING}
            else:
                # El 89% de las veces el mercado no amerita operar. Conservar pólvora.
                return {'action': 'HOLD_CASH', 'target_pct': 0.0, 'reason': 'Low_Probability', 'new_state': PositionState.FLAT}
                
        # 2. ESTADO [PROBING] -> Ampliar posiciones (Scaling-In) o Abortar Sonda
        elif context.current_state == PositionState.PROBING:
            # Si entramos en territorio positivo (Confirmación real, Price Action nos da la razón) 
            # y el LSTM sigue respaldando fuerte
            if context.current_price > context.average_entry and lstm_prob >= 0.85:
                # Ejecutar Scaling-In añadiendo el bloque Core (Subiendo hasta aprox 66% o 100% del Kelly)
                core_size = context.target_kelly_pct * (1.0 - self.probe_fraction)
                logger.info(f"[{context.ticker}] CONFIRMACIÓN SCALING-IN -> Añadiendo Core ({core_size*100:.2f}% Cuenta)")
                return {'action': 'BUY_CORE', 'target_pct': core_size, 'reason': 'Confirmation_ScaleIn', 'new_state': PositionState.SCALING_IN}
            
            # Si el modelo LSTM pierde fe repentinamente por debajo del 50%, cerrar Sonda anticipadamente
            if lstm_prob < 0.50:
                logger.warning(f"[{context.ticker}] FALLO MARCO TEMPORAL LSTM -> Abortando Sonda. Cerrando Venta.")
                return {'action': 'SELL_ABORT', 'target_pct': -context.current_exposure_pct, 'reason': 'LSTM_Reversal_Abort', 'new_state': PositionState.FLAT}
                
            return {'action': 'HOLD_POSITION', 'target_pct': 0.0, 'reason': 'Waiting_Confirmation', 'new_state': context.current_state}

        # 3. ESTADO [SCALING_IN] -> Distribución Volátil de Retirada Parcial (Scale-Out)
        elif context.current_state in [PositionState.SCALING_IN, PositionState.SCALING_OUT]:
            # Scale out en tramos si el activo se expandió agresivamente (Mucha Volatilidad BBW + Ganancias previas)
            # O si el LSTM detecta agotamiento fraccional
            if lstm_prob < 0.50 or volatility_bbw > 10.0:  # Si la banda de Bollinger Relative es altísima y extrema o la red pierde la confianza
                # Vender fragmentadamente en vez de Dump Total (Un tercio del riesgo base meta)
                sell_block = min(context.current_exposure_pct, context.target_kelly_pct * 0.33)
                
                if context.current_exposure_pct - sell_block > 0.01:
                    logger.info(f"[{context.ticker}] AGOTAMIENTO MACRO -> Scale-Out Táctico ({sell_block*100:.2f}%)")
                    return {'action': 'SELL_SCALE_OUT', 'target_pct': -sell_block, 'reason': 'Volatility_Distribution', 'new_state': PositionState.SCALING_OUT}
                else:
                    # Cerrar lo mínimo que queda
                    logger.info(f"[{context.ticker}] CIERRE TOTAL -> Dumping Final")
                    return {'action': 'SELL_CLOSE', 'target_pct': -context.current_exposure_pct, 'reason': 'Full_Distribution', 'new_state': PositionState.FLAT}
                    
            return {'action': 'HOLD_POSITION', 'target_pct': 0.0, 'reason': 'Riding_Trend', 'new_state': context.current_state}

        return {'action': 'UNKNOWN', 'target_pct': 0.0, 'reason': 'Error', 'new_state': context.current_state}
