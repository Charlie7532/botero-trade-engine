"""
Portfolio Intelligence System — Módulos Core
=============================================
Construido a partir de DATOS, no opiniones.

Hallazgo del backtest de trailing:
- Fixed -10% trailing: PF 4.57, WR 66.7%, EV +7.2% por trade
- ATR puro: PF < 1 (PERDEDOR) en SPX con señales simples
- ATR × 3.5: PF 1.25, mejor que ATR menores

CONCLUSIÓN: El trailing NO debe ser solo ATR. Debe ser ADAPTATIVO:
- En tendencia fuerte (RS > 1.1): trailing wide (3.5×ATR o -10%)
- En tendencia débil (RS < 0.95): trailing tight (2×ATR o -5%)
- El max() de ATR y fixed% evita salir en ruido y en crashes
"""
import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, UTC

logger = logging.getLogger(__name__)


# ================================================================
# RELATIVE STRENGTH MONITOR
# ================================================================

class RelativeStrengthMonitor:
    """
    Mide el rendimiento relativo de cada posición vs SPY y su sector.
    Si una acción gana +5% pero SPY gana +8%, estás PERDIENDO
    en costo de oportunidad.
    
    Métricas:
    - RS_SPY: Return_stock / Return_SPY (>1 = superando)
    - RS_Sector: Return_stock / Return_sector (>1 = líder)
    - RS_Momentum: RS_5d / RS_20d (>1 = acelerando)
    - Alpha_Decay: RS_actual / RS_al_entrar (<0.7 = exit)
    """
    
    def __init__(self):
        self._entry_rs = {}  # Guarda el RS al momento de entrada
    
    def calculate_rs(
        self,
        stock_prices: pd.Series,
        benchmark_prices: pd.Series,
        lookback: int = 20,
    ) -> dict:
        """Calcula Relative Strength de un stock vs benchmark."""
        if len(stock_prices) < lookback or len(benchmark_prices) < lookback:
            return {"rs": 1.0, "rs_momentum": 1.0, "rs_percentile": 50}
        
        # RS = retorno del stock / retorno del benchmark
        stock_ret = stock_prices.iloc[-1] / stock_prices.iloc[-lookback] - 1
        bench_ret = benchmark_prices.iloc[-1] / benchmark_prices.iloc[-lookback] - 1
        
        rs = (1 + stock_ret) / (1 + bench_ret) if bench_ret != -1 else 1.0
        
        # RS Momentum: RS reciente / RS medio
        rs_5d = (stock_prices.iloc[-1] / stock_prices.iloc[-5] - 1) / max(
            bench_ret / 4, 0.001
        ) if len(stock_prices) >= 5 else 1.0
        rs_20d = stock_ret / max(bench_ret, 0.001) if bench_ret != 0 else 1.0
        rs_momentum = rs_5d / rs_20d if rs_20d != 0 else 1.0
        
        return {
            "rs": round(rs, 4),
            "stock_return": round(stock_ret * 100, 2),
            "bench_return": round(bench_ret * 100, 2),
            "outperformance": round((stock_ret - bench_ret) * 100, 2),
            "rs_momentum": round(rs_momentum, 4),
        }
    
    def register_entry(self, ticker: str, rs_at_entry: float):
        """Registra el RS al momento de la entrada para calcular alpha decay."""
        self._entry_rs[ticker] = rs_at_entry
    
    def calculate_alpha_decay(self, ticker: str, current_rs: float) -> float:
        """
        Mide cuánto del edge original queda.
        1.0 = edge intacto, 0.5 = perdió la mitad, 0.0 = edge muerto
        """
        entry_rs = self._entry_rs.get(ticker, current_rs)
        if entry_rs <= 0:
            return 1.0
        decay = current_rs / entry_rs
        return round(max(0, min(decay, 2.0)), 4)
    
    def should_exit(self, ticker: str, current_rs: float) -> dict:
        """
        Evalúa si una posición debe cerrarse por degradación de RS.
        
        Reglas basadas en evidencia:
        - RS < 0.85 por 5+ días: El stock pierde contra el mercado
        - Alpha Decay < 0.70: El edge original desapareció
        - RS Momentum < 0.80: Desaceleración fuerte
        """
        decay = self.calculate_alpha_decay(ticker, current_rs)
        
        if decay < 0.70:
            return {
                "exit": True,
                "urgency": "high",
                "reason": f"Alpha Decay {decay:.2f} < 0.70 — edge muerto",
            }
        elif current_rs < 0.85:
            return {
                "exit": True,
                "urgency": "medium",
                "reason": f"RS {current_rs:.2f} < 0.85 — underperforming mercado",
            }
        elif decay < 0.85:
            return {
                "exit": False,
                "urgency": "watch",
                "reason": f"Alpha Decay {decay:.2f} — monitoreando",
            }
        else:
            return {
                "exit": False,
                "urgency": "none",
                "reason": f"RS {current_rs:.2f}, Decay {decay:.2f} — sano",
            }


# ================================================================
# ADAPTIVE TRAILING STOP
# ================================================================

@dataclass
class AdaptiveTrailingStop:
    """
    Trailing stop que se adapta al régimen del mercado.
    
    EVIDENCIA del backtest (SPX 2017-2025):
    - Fixed -10%: PF 4.57, WR 66.7% (mejor en mercado trending)
    - ATR × 3.5: PF 1.25, WR 52.6% (mejor en mercado choppy)
    - ATR × 1.5-2.5: PF < 1 (PERDEDORES — demasiado tight)
    
    SOLUCIÓN: Usar max(ATR_trailing, fixed_trailing).
    Esto evita salir en correcciones pequeñas (ATR low) 
    Y evita salir en crashes (fixed% cap).
    
    V2 GAMMA-AWARE EXTENSIONS:
    - Put Wall anchoring: stop below institutional support, not obvious technicals
    - VIX dynamic scaling: wider stops in high vol to survive liquidity sweeps
    - Event freeze: don't evaluate stops during post-announcement storm window
    """
    
    # Parámetros calibrados con backtest
    atr_multiplier_trend: float = 3.0    # En tendencia fuerte
    atr_multiplier_chop: float = 2.0     # En mercado lateral
    fixed_floor_pct: float = 0.05        # 5% mínimo absoluto
    fixed_ceiling_pct: float = 0.12      # 12% máximo absoluto
    
    # VIX scaling thresholds
    VIX_NORMAL = 18
    VIX_ELEVATED = 25
    VIX_HIGH = 35
    
    def calculate_stop(
        self,
        highest_since_entry: float,
        current_atr: float,
        rs_vs_spy: float = 1.0,
        # ─── Gamma-Aware Extensions (V2) ───
        put_wall: float = 0.0,        # Put Wall from options_awareness
        vix_current: float = 17.0,    # Current VIX for dynamic scaling
    ) -> float:
        """
        Calcula el nivel de stop adaptativo con conciencia Gamma.
        
        En tendencia fuerte (RS > 1.05): trailing wide (3×ATR)
        En mercado neutro: (2.5×ATR)
        En debilidad (RS < 0.95): trailing tight (2×ATR)
        
        V2: Si put_wall > 0, ancla el stop debajo del Put Wall
        (donde los MMs compran para cubrirse = piso institucional)
        en vez de usar niveles técnicos obvios que todos ven.
        
        V2: Si vix_current > 25, expande el multiplicador ATR
        para sobrevivir las mechas de barrido de liquidez.
        """
        # Adaptar multiplicador al régimen RS
        if rs_vs_spy > 1.05:
            mult = self.atr_multiplier_trend
        elif rs_vs_spy < 0.95:
            mult = self.atr_multiplier_chop
        else:
            mult = (self.atr_multiplier_trend + self.atr_multiplier_chop) / 2
        
        # ── V2: VIX Dynamic Scaling ────────────────────────────
        # En alta volatilidad, las mechas son más largas.
        # Si el stop no respira, la mecha lo mata.
        vix_scale = 1.0
        if vix_current > self.VIX_HIGH:
            vix_scale = 2.0     # Double the ATR multiplier
        elif vix_current > self.VIX_ELEVATED:
            vix_scale = 1.5     # 50% wider
        elif vix_current > self.VIX_NORMAL:
            vix_scale = 1.2     # 20% wider
        
        mult *= vix_scale
        
        atr_stop = highest_since_entry - (mult * current_atr)
        fixed_stop_low = highest_since_entry * (1 - self.fixed_floor_pct)
        fixed_stop_high = highest_since_entry * (1 - self.fixed_ceiling_pct)
        
        # El stop es el MÁS ALTO entre ATR y el floor fijo
        # pero nunca más bajo que el ceiling fijo
        stop = max(atr_stop, fixed_stop_high)
        stop = min(stop, fixed_stop_low)
        
        # ── V2: Put Wall Anchoring ─────────────────────────────
        # If Put Wall is provided and is below the current price,
        # the stop should go BELOW the Put Wall (not at technical levels).
        # The Put Wall is where Market Makers MUST buy to hedge.
        # That's a concrete floor, not a drawing on a chart.
        if put_wall > 0 and put_wall < highest_since_entry:
            gamma_stop = put_wall - (0.3 * current_atr * vix_scale)
            # Use the LOWER of ATR stop and gamma stop
            # (gamma stop is more generous = more survival)
            stop = min(stop, gamma_stop)
        
        return round(stop, 2)
    
    def should_freeze(
        self,
        freeze_stops: bool = False,
        freeze_start_time: Optional[datetime] = None,
        freeze_duration_min: int = 30,
    ) -> bool:
        """
        Determina si el trailing stop debe estar congelado.
        
        During macro event storms (FOMC, CPI), the first 15-30 minutes
        are a liquidity hunt — not a real market move. Freezing the stop
        prevents being swept out by a wick that reverses in minutes.
        
        Args:
            freeze_stops: Flag from EventFlowIntelligence
            freeze_start_time: When the freeze was activated
            freeze_duration_min: How long to freeze (default 30 min)
        
        Returns:
            True if stop should NOT be evaluated right now.
        """
        if not freeze_stops:
            return False
        
        if freeze_start_time is None:
            return True  # Freeze just activated, no start time yet
        
        elapsed = (datetime.now(UTC) - freeze_start_time).total_seconds() / 60
        return elapsed < freeze_duration_min


# ================================================================
# PORTFOLIO OPTIMIZER (HRP-Inspired)
# ================================================================

@dataclass
class PositionAllocation:
    ticker: str
    weight: float          # 0-1
    sector: str
    rs_score: float
    qualifier_grade: str
    conviction: float      # 0-100

class PortfolioOptimizer:
    """
    Optimizador de portafolio con constraints institucionales.
    
    Implementa una versión simplificada de HRP que:
    1. Usa correlaciones rolling para detectar clusters
    2. Aplica inverse-variance weighting dentro de clusters
    3. Respeta constraints duros (max por posición/sector)
    
    Para HRP completo, instalar pypfopt.
    """
    
    MAX_POSITIONS = 8
    MIN_WEIGHT = 0.05      # 5% mínimo por posición
    MAX_WEIGHT = 0.25      # 25% máximo por posición
    MAX_SECTOR = 0.40      # 40% máximo por sector
    MIN_CASH = 0.10        # 10% cash mínimo
    MAX_CORRELATION = 0.75 # No más de 2 stocks con corr > 0.75
    
    def optimize_weights(
        self,
        candidates: list[dict],
        returns_df: Optional[pd.DataFrame] = None,
    ) -> list[PositionAllocation]:
        """
        Calcula pesos óptimos para un conjunto de candidatos.
        
        Args:
            candidates: Lista de dicts con ticker, sector, rs_score, 
                       qualifier_grade, conviction
            returns_df: DataFrame de retornos diarios (optional, para correlación)
        """
        if not candidates:
            return []
        
        # Limitar a MAX_POSITIONS
        candidates = sorted(candidates, key=lambda x: -x.get('conviction', 0))
        candidates = candidates[:self.MAX_POSITIONS]
        
        n = len(candidates)
        available = 1.0 - self.MIN_CASH
        
        # Intento 1: HRP si tenemos datos de retornos
        if returns_df is not None and len(returns_df) > 30:
            weights = self._hrp_weights(candidates, returns_df)
        else:
            # Fallback: Conviction-weighted
            weights = self._conviction_weights(candidates)
        
        # Aplicar constraints
        weights = self._apply_constraints(candidates, weights)
        
        # Escalar a capital disponible
        total = sum(weights.values())
        if total > 0:
            weights = {k: v * available / total for k, v in weights.items()}
        
        allocations = []
        for c in candidates:
            t = c['ticker']
            w = weights.get(t, 0)
            if w >= self.MIN_WEIGHT:
                allocations.append(PositionAllocation(
                    ticker=t,
                    weight=round(w, 4),
                    sector=c.get('sector', 'Unknown'),
                    rs_score=c.get('rs_score', 1.0),
                    qualifier_grade=c.get('qualifier_grade', 'C'),
                    conviction=c.get('conviction', 50),
                ))
        
        return allocations
    
    def _conviction_weights(self, candidates: list[dict]) -> dict:
        """Pesos basados en convicción (fallback sin datos de retornos)."""
        weights = {}
        total_conv = sum(c.get('conviction', 50) for c in candidates)
        if total_conv == 0:
            total_conv = len(candidates) * 50
        
        for c in candidates:
            conv = c.get('conviction', 50)
            weights[c['ticker']] = conv / total_conv
        
        return weights
    
    def _hrp_weights(self, candidates: list[dict], returns_df: pd.DataFrame) -> dict:
        """
        HRP simplificado: inverse-variance con penalización por correlación.
        """
        tickers = [c['ticker'] for c in candidates if c['ticker'] in returns_df.columns]
        if len(tickers) < 2:
            return self._conviction_weights(candidates)
        
        sub = returns_df[tickers].dropna()
        if len(sub) < 30:
            return self._conviction_weights(candidates)
        
        # Varianza de cada activo
        variances = sub.var()
        
        # Inverse variance weights
        inv_var = 1.0 / variances.replace(0, variances.max())
        
        # Penalizar pares con alta correlación
        corr = sub.corr()
        for i, t1 in enumerate(tickers):
            for j, t2 in enumerate(tickers):
                if i < j and abs(corr.loc[t1, t2]) > self.MAX_CORRELATION:
                    # Reducir el peso del que tiene menor convicción
                    c1 = next((c['conviction'] for c in candidates if c['ticker'] == t1), 50)
                    c2 = next((c['conviction'] for c in candidates if c['ticker'] == t2), 50)
                    weaker = t1 if c1 < c2 else t2
                    inv_var[weaker] *= 0.5
                    logger.warning(
                        f"Correlación {t1}/{t2}: {corr.loc[t1, t2]:.2f} > {self.MAX_CORRELATION}. "
                        f"Reduciendo {weaker}."
                    )
        
        total = inv_var.sum()
        weights = {t: (inv_var[t] / total) for t in tickers}
        
        # Agregar tickers sin datos de retornos con peso mínimo
        for c in candidates:
            if c['ticker'] not in weights:
                weights[c['ticker']] = self.MIN_WEIGHT
        
        return weights
    
    def _apply_constraints(self, candidates: list[dict], weights: dict) -> dict:
        """Aplica constraints duros de max por posición y sector."""
        # Max por posición
        for t in weights:
            weights[t] = max(self.MIN_WEIGHT, min(weights[t], self.MAX_WEIGHT))
        
        # Max por sector
        sector_weights = {}
        for c in candidates:
            t = c['ticker']
            s = c.get('sector', 'Unknown')
            sector_weights.setdefault(s, []).append(t)
        
        for sector, tickers in sector_weights.items():
            sector_total = sum(weights.get(t, 0) for t in tickers)
            if sector_total > self.MAX_SECTOR:
                scale = self.MAX_SECTOR / sector_total
                for t in tickers:
                    weights[t] = weights.get(t, 0) * scale
        
        return weights


# ================================================================
# ROTATION ENGINE
# ================================================================

class RotationEngine:
    """
    Decide cuándo rotar posiciones del portafolio.
    
    Regla de oro: Un candidato debe ser 30% MEJOR que la peor
    posición actual para justificar la rotación. Esto evita
    "churning" (sobre-rotación que destruye rendimiento por costos).
    """
    
    ROTATION_THRESHOLD = 1.30  # Candidato debe ser 30% mejor
    
    def __init__(self):
        self.rs_monitor = RelativeStrengthMonitor()
    
    def evaluate_rotation(
        self,
        current_positions: list[dict],
        candidates: list[dict],
    ) -> list[dict]:
        """
        Evalúa si algún candidato justifica reemplazar una posición.
        
        Args:
            current_positions: [{"ticker", "alpha_score", "rs", "decay", ...}]
            candidates: [{"ticker", "alpha_score", "rs", ...}]
        
        Returns:
            Lista de rotaciones recomendadas
        """
        if not current_positions or not candidates:
            return []
        
        rotations = []
        
        # Ordenar posiciones por score (peor primero)
        positions_sorted = sorted(
            current_positions, key=lambda x: x.get('alpha_score', 0)
        )
        
        # Ordenar candidatos por score (mejor primero)
        candidates_sorted = sorted(
            candidates, key=lambda x: -x.get('alpha_score', 0)
        )
        
        for candidate in candidates_sorted:
            cand_score = candidate.get('alpha_score', 0)
            
            for position in positions_sorted:
                pos_score = position.get('alpha_score', 0)
                
                # ¿El candidato es 30% mejor?
                if pos_score > 0 and cand_score / pos_score >= self.ROTATION_THRESHOLD:
                    rotations.append({
                        "action": "ROTATE",
                        "sell": position['ticker'],
                        "sell_score": pos_score,
                        "buy": candidate['ticker'],
                        "buy_score": cand_score,
                        "improvement": f"{(cand_score/pos_score - 1)*100:+.0f}%",
                        "reason": (
                            f"{candidate['ticker']} ({cand_score:.0f}) supera a "
                            f"{position['ticker']} ({pos_score:.0f}) por "
                            f"{(cand_score/pos_score - 1)*100:.0f}%"
                        ),
                    })
                    # No rotar la misma posición dos veces
                    positions_sorted.remove(position)
                    break
        
        return rotations


# ================================================================
# RISK GUARDIAN
# ================================================================

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
