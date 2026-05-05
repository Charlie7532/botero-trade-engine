import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, UTC

from backend.modules.portfolio_management.domain.entities.daily_mandate import DailyMandate

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# SHARED STATE — Communication channel between guardians
# ═══════════════════════════════════════════════════════════════

@dataclass
class RiskContext:
    """
    Shared mutable state between QualityRiskGuardian and SpeculativeRiskGuardian.

    When one guardian detects an anomaly, it writes to this context.
    The other guardian reads it on its next evaluation cycle.
    """
    # Market state
    current_vix: float = 17.0
    market_breadth_pct: float = 50.0

    # Cross-guardian alerts
    flow_anomaly: str = ""           # e.g. "VIX_SPIKE", "FLASH_CRASH", ""
    sector_rotation: dict = field(default_factory=dict)  # e.g. {"from": "TECH", "to": "ENERGY"}
    speculative_stress: bool = False  # Speculative guardian signals distress
    quality_pause_scaling: bool = False  # Quality guardian pauses accumulation

    # Portfolio-level
    portfolio_dd_pct: float = 0.0
    daily_pnl_pct: float = 0.0


# ═══════════════════════════════════════════════════════════════
# QUALITY RISK GUARDIAN — Druckenmiller Mode (80% of Capital)
# ═══════════════════════════════════════════════════════════════

class QualityRiskGuardian:
    """
    Protección del departamento QUALITY (Hohn & Munger).

    Filosofía: Paciencia fundamental. Tolera volatilidad si la tesis vive.
    Sólo liquida por rotura de moat o crisis de liquidez macro.
    Stops basados en estructura, no en ruido de precio.
    """

    def __init__(
        self,
        max_portfolio_dd: float = 0.15,
        max_daily_loss: float = 0.03,
        allocation_limit: float = 0.80,
        cooldown_hours: int = 48,
    ):
        self.max_portfolio_dd = max_portfolio_dd
        self.max_daily_loss = max_daily_loss
        self.allocation_limit = allocation_limit
        self.cooldown_hours = cooldown_hours

        self._peak_capital = 0
        self._last_loss_event = None
        self._consecutive_losses = 0

    def evaluate(
        self,
        current_capital: float,
        daily_pnl_pct: float,
        quality_exposure: float = 0.0,
        current_vix: float = 17,
        last_trade_won: Optional[bool] = None,
        context: Optional[RiskContext] = None,
        macro_gate: Optional[dict] = None,
        market_sentiment: Optional[dict] = None,
        daily_mandate: Optional[DailyMandate] = None,
    ) -> dict:
        """
        Evalúa el riesgo para posiciones QUALITY.

        Returns:
            Dict con position_scale (0-1), can_trade, alerts
        """
        self._peak_capital = max(self._peak_capital, current_capital)
        current_dd = (current_capital - self._peak_capital) / self._peak_capital

        if last_trade_won is not None:
            if last_trade_won:
                self._consecutive_losses = 0
            else:
                self._consecutive_losses += 1

        position_scale = 1.0
        can_trade = True
        alerts = []

        # 1. Portfolio DD check
        if abs(current_dd) >= self.max_portfolio_dd:
            position_scale = 0.5
            alerts.append(f"🚨 Portfolio DD {current_dd*100:.1f}% ≥ {self.max_portfolio_dd*100:.0f}%. Sizing reducido 50%.")

        # 2. QUALITY Bucket capacity
        total_cap = max(current_capital, 1.0)
        quality_pct = quality_exposure / total_cap
        
        limit = daily_mandate.quality_budget_pct if daily_mandate else self.allocation_limit
        
        if quality_pct >= limit:
            can_trade = False
            alerts.append(f"🚫 QUALITY Bucket Lleno: Exp={quality_pct*100:.1f}% / Límite CIO={limit*100:.0f}%")

        # 3. Daily loss check
        if abs(daily_pnl_pct) >= self.max_daily_loss and daily_pnl_pct < 0:
            can_trade = False
            self._last_loss_event = datetime.now(UTC)
            alerts.append(f"🚨 Pérdida diaria {daily_pnl_pct*100:.1f}% ≥ {self.max_daily_loss*100:.0f}%. Trading pausado {self.cooldown_hours}h.")

        # 4. VIX — Quality is MORE tolerant (Druckenmiller buys fear)
        if current_vix >= 40:
            position_scale *= 0.60
            alerts.append(f"⚠️ VIX {current_vix:.0f} ≥ 40. QUALITY sizing -40% (pero NO bloqueado — Druckenmiller compra pánico).")
        elif current_vix >= 30:
            position_scale *= 0.80
            alerts.append(f"⚠️ VIX {current_vix:.0f} ≥ 30. QUALITY sizing -20%.")

        # 5. Cooldown check
        if self._last_loss_event:
            hours_since = (datetime.now(UTC) - self._last_loss_event).total_seconds() / 3600
            if hours_since < self.cooldown_hours:
                can_trade = False
                alerts.append(f"⏳ Cooldown: {self.cooldown_hours - hours_since:.0f}h restantes.")

        # 6. Read cross-guardian context
        if context:
            if context.speculative_stress:
                # Speculative department is in trouble — pause scaling-in
                context.quality_pause_scaling = True
                position_scale *= 0.70
                alerts.append("⚠️ Speculative dept bajo estrés. QUALITY pausa scaling-in (-30%).")
            if context.flow_anomaly == "VIX_SPIKE":
                position_scale *= 0.80
                alerts.append(f"⚠️ VIX Spike detectado por Speculative. QUALITY reduce sizing -20%.")
            # Update context with portfolio state
            context.portfolio_dd_pct = current_dd * 100
            context.daily_pnl_pct = daily_pnl_pct

        # 7. Macro Flow Gate (SPY delta — ADAPTIVE)
        if macro_gate is not None:
            gate_signal = getattr(macro_gate, 'signal', macro_gate.get('signal', 'NEUTRAL') if isinstance(macro_gate, dict) else 'NEUTRAL')
            gate_scale = getattr(macro_gate, 'position_scale_factor', macro_gate.get('position_scale_factor', 1.0) if isinstance(macro_gate, dict) else 1.0)
            gate_score = getattr(macro_gate, 'composite_score', macro_gate.get('composite_score', 0) if isinstance(macro_gate, dict) else 0)
            am_pm_div = getattr(macro_gate, 'am_pm_diverges', macro_gate.get('am_pm_diverges', False) if isinstance(macro_gate, dict) else False)
            confidence = getattr(macro_gate, 'confidence', macro_gate.get('confidence', 0.5) if isinstance(macro_gate, dict) else 0.5)

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

        # 8. Market Sentiment Gate (breadth + PCR + sweeps)
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


# ═══════════════════════════════════════════════════════════════
# SPECULATIVE RISK GUARDIAN — Seykota & PTJ Mode (20% of Capital)
# ═══════════════════════════════════════════════════════════════

class SpeculativeRiskGuardian:
    """
    Protección del departamento SPECULATIVE (Eifert & PTJ).

    Filosofía: Zero ego, zero attachment. Stops mecánicos y despiadados.
    Si el VIX está alto, se cierra la puerta completamente.
    Anti-Martingale agresivo. Nunca convierte una pérdida táctica
    en una "inversión a largo plazo".
    """

    def __init__(
        self,
        max_daily_loss: float = 0.02,
        vix_reduce_threshold: float = 25,
        vix_block_threshold: float = 30,
        allocation_limit: float = 0.20,
    ):
        self.max_daily_loss = max_daily_loss
        self.vix_reduce = vix_reduce_threshold
        self.vix_block = vix_block_threshold
        self.allocation_limit = allocation_limit

        self._consecutive_losses = 0
        self._last_loss_event = None

    def evaluate(
        self,
        current_capital: float,
        daily_pnl_pct: float,
        speculative_exposure: float = 0.0,
        current_vix: float = 17,
        last_trade_won: Optional[bool] = None,
        context: Optional[RiskContext] = None,
        daily_mandate: Optional[DailyMandate] = None,
    ) -> dict:
        """
        Evalúa el riesgo para posiciones SPECULATIVE.

        Returns:
            Dict con position_scale (0-1), can_trade, alerts
        """
        if last_trade_won is not None:
            if last_trade_won:
                self._consecutive_losses = 0
            else:
                self._consecutive_losses += 1

        position_scale = 1.0
        can_trade = True
        alerts = []

        # 1. SPECULATIVE Bucket capacity
        total_cap = max(current_capital, 1.0)
        spec_pct = speculative_exposure / total_cap
        
        limit = daily_mandate.speculative_budget_pct if daily_mandate else self.allocation_limit
        
        if spec_pct >= limit:
            can_trade = False
            alerts.append(f"🚫 SPECULATIVE Bucket Lleno: Exp={spec_pct*100:.1f}% / Límite CIO={limit*100:.0f}%")

        # 2. VIX — Speculative is RUTHLESS (Seykota shuts the door)
        if current_vix > self.vix_block:
            can_trade = False
            alerts.append(f"🛑 SPECULATIVE BLOQUEADO por VIX ({current_vix:.0f} > {self.vix_block}). Zero new trades.")
        elif current_vix > self.vix_reduce:
            position_scale *= 0.50
            alerts.append(f"⚠️ VIX {current_vix:.0f} > {self.vix_reduce}. SPECULATIVE sizing -50%.")

        # 3. Daily loss check (tighter than Quality)
        if abs(daily_pnl_pct) >= self.max_daily_loss and daily_pnl_pct < 0:
            can_trade = False
            self._last_loss_event = datetime.now(UTC)
            alerts.append(f"🚨 Pérdida diaria {daily_pnl_pct*100:.1f}% ≥ {self.max_daily_loss*100:.0f}%. SPECULATIVE pausado 24h.")

        # 4. Anti-Martingale — AGGRESSIVE reduction on losing streaks
        if self._consecutive_losses >= 2:
            position_scale *= 0.50
            alerts.append(f"⚠️ {self._consecutive_losses} losses consecutivos. SPECULATIVE sizing -50% (Anti-Martingale).")
        elif self._consecutive_losses >= 1:
            position_scale *= 0.75
            alerts.append(f"⚠️ 1 loss reciente. SPECULATIVE sizing -25%.")

        # 5. Cooldown (shorter than Quality — 24h)
        if self._last_loss_event:
            hours_since = (datetime.now(UTC) - self._last_loss_event).total_seconds() / 3600
            if hours_since < 24:
                can_trade = False
                alerts.append(f"⏳ SPECULATIVE Cooldown: {24 - hours_since:.0f}h restantes.")

        # 6. Write to cross-guardian context
        if context:
            if current_vix > self.vix_block or self._consecutive_losses >= 3:
                context.speculative_stress = True
                context.flow_anomaly = "VIX_SPIKE" if current_vix > self.vix_block else "LOSING_STREAK"
            else:
                context.speculative_stress = False

            # Read: if Quality detected sector rotation, tighten our stops
            if context.sector_rotation:
                alerts.append(
                    f"⚠️ Quality detectó rotación sectorial: {context.sector_rotation}. "
                    f"Ajustando stops especulativos."
                )

        return {
            "position_scale": round(max(0.20, min(position_scale, 1.0)), 2),
            "can_trade": can_trade,
            "consecutive_losses": self._consecutive_losses,
            "alerts": alerts,
        }


# ═══════════════════════════════════════════════════════════════
# RISK ORCHESTRATOR — Dispatches to the correct guardian
# ═══════════════════════════════════════════════════════════════

class RiskOrchestrator:
    """
    Coordina ambos guardianes y mantiene el RiskContext compartido.

    Uso:
        orchestrator = RiskOrchestrator()
        result = orchestrator.evaluate(
            strategy_type="QUALITY",
            current_capital=100000,
            ...
        )
    """

    def __init__(self, **kwargs):
        self.quality = QualityRiskGuardian(**{
            k: v for k, v in kwargs.items()
            if k in QualityRiskGuardian.__init__.__code__.co_varnames
        }) if kwargs else QualityRiskGuardian()

        self.speculative = SpeculativeRiskGuardian(**{
            k: v for k, v in kwargs.items()
            if k in SpeculativeRiskGuardian.__init__.__code__.co_varnames
        }) if kwargs else SpeculativeRiskGuardian()

        self.context = RiskContext()

    def evaluate(
        self,
        current_capital: float,
        daily_pnl_pct: float,
        strategy_type: str = "QUALITY",
        quality_exposure: float = 0.0,
        speculative_exposure: float = 0.0,
        current_vix: float = 17,
        last_trade_won: Optional[bool] = None,
        macro_gate: Optional[dict] = None,
        market_sentiment: Optional[dict] = None,
        daily_mandate: Optional[DailyMandate] = None,
    ) -> dict:
        """
        Evalúa el estado de riesgo del portafolio.
        Backward-compatible interface — dispatches to the correct guardian.

        Returns:
            Dict con position_scale (0-1), can_trade, alerts
        """
        # Update shared context
        self.context.current_vix = current_vix

        if strategy_type == "SPECULATIVE":
            return self.speculative.evaluate(
                current_capital=current_capital,
                daily_pnl_pct=daily_pnl_pct,
                speculative_exposure=speculative_exposure,
                current_vix=current_vix,
                last_trade_won=last_trade_won,
                context=self.context,
                daily_mandate=daily_mandate,
            )
        else:
            return self.quality.evaluate(
                current_capital=current_capital,
                daily_pnl_pct=daily_pnl_pct,
                quality_exposure=quality_exposure,
                current_vix=current_vix,
                last_trade_won=last_trade_won,
                context=self.context,
                macro_gate=macro_gate,
                market_sentiment=market_sentiment,
                daily_mandate=daily_mandate,
            )


# ═══════════════════════════════════════════════════════════════
# BACKWARD COMPATIBILITY — Alias for existing consumers
# ═══════════════════════════════════════════════════════════════

# Existing code that imports RiskGuardian will get the orchestrator
RiskGuardian = RiskOrchestrator
