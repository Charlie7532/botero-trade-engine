import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

class RiskManager:
    """
    Gestor de Riesgos de grado institucional.
    Se asegura de preservar el capital (ej. 100k) mediante topes rígidos, 
    y asignación matemática de capital (Kelly Criterion).
    """

    def __init__(self, initial_capital: float = 100000.0, max_drawdown_pct: float = 0.10):
        self.initial_capital = initial_capital
        self.max_drawdown_pct = max_drawdown_pct
        self.hard_stop_loss_capital = self.initial_capital * (1.0 - self.max_drawdown_pct)
        
        self.current_capital = initial_capital
        self.highest_watermark = initial_capital
        
        # Flags de supervivencia
        self.circuit_breaker_active = False

    def update_capital(self, current_equity: float):
        """Actualiza el capital actual y evalúa si se debe activar el Circuit Breaker"""
        self.current_capital = current_equity
        if self.current_capital > self.highest_watermark:
            self.highest_watermark = self.current_capital
            
        current_drawdown = (self.highest_watermark - self.current_capital) / self.highest_watermark
        logger.info(f"Capital Actual: {self.current_capital} | Drawdown Actual: {current_drawdown:.2%}")

        if self.current_capital <= self.hard_stop_loss_capital or current_drawdown >= self.max_drawdown_pct:
            logger.critical(f"CIRCUIT BREAKER ACTIVADO. Capital: {self.current_capital} (Límite: {self.hard_stop_loss_capital})")
            self.circuit_breaker_active = True

    def is_order_allowed(self, symbol: str, side: str, notional_value: float) -> bool:
        """
        Bloquea cualquier nueva orden si el circuit breaker está activo.
        También previene concentración de portafolio extrema.
        """
        if self.circuit_breaker_active:
            logger.warning(f"Orden BLOQUEADA por Risk Manager: {side} {symbol} - Circuit Breaker Activo.")
            return False
        
        # Lógica adicional: Prevenir que una sola posición exceda el X% del portafolio
        max_position_size = self.current_capital * 0.25 # Máximo 25% del capital por trade
        if notional_value > max_position_size:
            logger.warning(f"Orden de {notional_value} para {symbol} excede el límite de tamaño de posición por asset (25%).")
            return False
            
        return True

    def calculate_kelly_size(self, win_rate: float, win_loss_ratio: float, kelly_fraction: float = 0.5) -> float:
        """
        Calcula la fracción de capital recomendada usando Half-Kelly o Fractional Kelly para escalar.
        Kelly % = W - [(1 - W) / R]
        W = Win probability
        R = Win/Loss ratio (Reward/Risk)
        """
        if win_loss_ratio <= 0:
            return 0.0

        kelly_pct = win_rate - ((1.0 - win_rate) / win_loss_ratio)
        if kelly_pct <= 0:
            return 0.0 # No hay edge estadístico, no apostar
            
        # Fractional kelly (suaviza la volatilidad agresiva)
        allocation_pct = kelly_pct * kelly_fraction
        
        # Max cap para evitar sobre-exposición incluso si kelly da un número alto
        return min(allocation_pct, 0.25)
