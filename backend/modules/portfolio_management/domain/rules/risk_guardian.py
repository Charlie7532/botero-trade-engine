import logging
from typing import Optional
from datetime import datetime, UTC

logger = logging.getLogger(__name__)

class RiskGuardian:
    """
    Protección de capital con reglas de hierro NO negociables.
    
    Basado en evidencia:
    - Un DD de -20% requiere +25% para recuperar
    - Un DD de -50% requiere +100% para recuperar
    - La asimetría del DD significa que PREVENIR es 10x más 
      importante que GENERAR retorno
    """
    
    def __init__(
        self,
        max_portfolio_dd: float = 0.15,
        max_daily_loss: float = 0.03,
        vix_reduce_threshold: float = 30,
        vix_emergency_threshold: float = 40,
        cooldown_hours: int = 48,
    ):
        self.max_portfolio_dd = max_portfolio_dd
        self.max_daily_loss = max_daily_loss
        self.vix_reduce = vix_reduce_threshold
        self.vix_emergency = vix_emergency_threshold
        self.cooldown_hours = cooldown_hours
        
        # 80/20 Institutional Buckets
        self.core_allocation_limit = 0.80
        self.tactical_allocation_limit = 0.20
        
        self._peak_capital = 0
        self._last_loss_event = None
        self._consecutive_losses = 0
    
    def evaluate(
        self,
        current_capital: float,
        daily_pnl_pct: float,
        strategy_type: str = "CORE",           # "CORE" o "TACTICAL"
        core_exposure: float = 0.0,            # Capital actualmente expuesto en CORE
        tactical_exposure: float = 0.0,        # Capital actualmente expuesto en TACTICAL
        current_vix: float = 17,
        last_trade_won: Optional[bool] = None,
        # ─── Strategy Synthesis V2: Institutional Flow Gates ───
        macro_gate: Optional[dict] = None,     # MacroGate from UW
        market_sentiment: Optional[dict] = None,  # MarketSentiment from UW
    ) -> dict:
        """
        Evalúa el estado de riesgo del portafolio.
        
        Returns:
            Dict con position_scale (0-1), can_trade, alerts
        """
        self._peak_capital = max(self._peak_capital, current_capital)
        current_dd = (current_capital - self._peak_capital) / self._peak_capital
        
        # Track consecutive losses
        if last_trade_won is not None:
            if last_trade_won:
                self._consecutive_losses = 0
            else:
                self._consecutive_losses += 1
        
        position_scale = 1.0  # Por defecto, sizing completo
        can_trade = True
        alerts = []
        
        # 1. Portfolio DD check
        if abs(current_dd) >= self.max_portfolio_dd:
            position_scale = 0.5
            alerts.append(f"🚨 Portfolio DD {current_dd*100:.1f}% ≥ {self.max_portfolio_dd*100:.0f}%. Sizing reducido 50%.")
            
        # 1.5 Estrategia Bucket Check (80/20)
        total_cap = max(current_capital, 1.0)
        core_pct = core_exposure / total_cap
        tactical_pct = tactical_exposure / total_cap
        
        if strategy_type == "CORE" and core_pct >= self.core_allocation_limit:
            can_trade = False
            alerts.append(f"🚫 CORE Bucket Lleno: Exp={core_pct*100:.1f}% / Límite={self.core_allocation_limit*100:.0f}%")
        elif strategy_type == "TACTICAL" and tactical_pct >= self.tactical_allocation_limit:
            can_trade = False
            alerts.append(f"🚫 TACTICAL Bucket Lleno: Exp={tactical_pct*100:.1f}% / Límite={self.tactical_allocation_limit*100:.0f}%")
        
        # Si es TACTICAL y el VIX está alto, podemos prohibir completamente el trade satélite
        if strategy_type == "TACTICAL" and current_vix > self.vix_reduce:
            can_trade = False
            alerts.append(f"🛑 Cancelado TACTICAL por Macro VIX ({current_vix:.0f} > {self.vix_reduce}).")
        
        # 2. Daily loss check
        if abs(daily_pnl_pct) >= self.max_daily_loss and daily_pnl_pct < 0:
            can_trade = False
            self._last_loss_event = datetime.now(UTC)
            alerts.append(f"🚨 Pérdida diaria {daily_pnl_pct*100:.1f}% ≥ {self.max_daily_loss*100:.0f}%. Trading pausado {self.cooldown_hours}h.")
        
        # 3. VIX scaling
        if current_vix >= self.vix_emergency:
            position_scale *= 0.50
            alerts.append(f"⚠️ VIX {current_vix:.0f} ≥ {self.vix_emergency}. Sizing -50%.")
        elif current_vix >= self.vix_reduce:
            position_scale *= 0.70
            alerts.append(f"⚠️ VIX {current_vix:.0f} ≥ {self.vix_reduce}. Sizing -30%.")
        
        # 4. Anti-martingale: reducir en racha perdedora
        if self._consecutive_losses >= 3:
            position_scale *= 0.70
            alerts.append(f"⚠️ {self._consecutive_losses} losses consecutivos. Sizing -30%.")
        
        # 5. Cooldown check
        if self._last_loss_event:
            hours_since = (datetime.now(UTC) - self._last_loss_event).total_seconds() / 3600
            if hours_since < self.cooldown_hours:
                can_trade = False
                alerts.append(f"⏳ Cooldown: {self.cooldown_hours - hours_since:.0f}h restantes.")
        
        # ═══ Strategy Synthesis V2: Institutional Flow Gates ═══
        
        # 6. Macro Flow Gate (SPY delta — ADAPTIVE)
        # Uses graduated scaling from MacroGate.position_scale_factor
        # instead of binary thresholds
        if macro_gate is not None:
            # Support both MacroGate dataclass and dict
            gate_signal = getattr(macro_gate, 'signal', macro_gate.get('signal', 'NEUTRAL') if isinstance(macro_gate, dict) else 'NEUTRAL')
            gate_scale = getattr(macro_gate, 'position_scale_factor', macro_gate.get('position_scale_factor', 1.0) if isinstance(macro_gate, dict) else 1.0)
            gate_score = getattr(macro_gate, 'composite_score', macro_gate.get('composite_score', 0) if isinstance(macro_gate, dict) else 0)
            am_pm_div = getattr(macro_gate, 'am_pm_diverges', macro_gate.get('am_pm_diverges', False) if isinstance(macro_gate, dict) else False)
            confidence = getattr(macro_gate, 'confidence', macro_gate.get('confidence', 0.5) if isinstance(macro_gate, dict) else 0.5)
            
            # Apply adaptive scaling
            position_scale *= gate_scale
            
            if gate_signal == 'EXIT':
                alerts.append(
                    f"🚨 SPY Flow EXIT (score={gate_score:+d}, scale={gate_scale:.2f}). "
                    f"Institutional outflow detected."
                )
            elif gate_signal == 'REDUCE':
                alerts.append(
                    f"⚠️ SPY Flow REDUCE (score={gate_score:+d}, scale={gate_scale:.2f}). "
                    f"{'AM/PM divergence!' if am_pm_div else 'Weakening flow.'}"
                )
            elif gate_signal == 'FULL_IN' and confidence > 0.7:
                alerts.append(
                    f"🟢 SPY Flow FULL IN (score={gate_score:+d}, conf={confidence:.0%}). "
                    f"Institutional accumulation confirmed."
                )
        
        # 7. Market Sentiment Gate (breadth + PCR + sweeps)
        if market_sentiment is not None:
            regime = getattr(market_sentiment, 'regime', market_sentiment.get('regime', 'NEUTRAL') if isinstance(market_sentiment, dict) else 'NEUTRAL')
            sent_score = getattr(market_sentiment, 'sentiment_score', market_sentiment.get('sentiment_score', 0) if isinstance(market_sentiment, dict) else 0)
            breadth = getattr(market_sentiment, 'breadth_pct', market_sentiment.get('breadth_pct', 50) if isinstance(market_sentiment, dict) else 50)
            
            if regime == 'BEAR' and sent_score <= -2:
                position_scale *= 0.85
                alerts.append(
                    f"⚠️ Market Sentiment BEARISH (score={sent_score:+d}, breadth={breadth:.0f}%). "
                    f"Sizing -15%."
                )
            elif regime == 'BULL' and sent_score >= 3 and breadth > 60:
                # Don't exceed 1.0 — only restore if other gates reduced
                position_scale = min(position_scale * 1.05, 1.0)
                alerts.append(
                    f"🟢 Market Sentiment BULLISH (score={sent_score:+d}, breadth={breadth:.0f}%). "
                    f"Sizing confirmed."
                )
        
        return {
            "position_scale": round(max(0.20, min(position_scale, 1.0)), 2),
            "can_trade": can_trade,
            "current_dd": round(current_dd * 100, 2),
            "consecutive_losses": self._consecutive_losses,
            "alerts": alerts,
        }
