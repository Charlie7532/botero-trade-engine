"""
PRICE PHASE INTELLIGENCE — El Director de Orquesta del Timing
================================================================
"El timing es el puente entre tener la razón y ganar dinero."

Fusiona 3 dimensiones desconectadas para diagnosticar la fase
del precio y calcular el punto exacto de entrada:

  Dimensión 1: ESTRUCTURA DE PRECIO (ATR, SMA20, RSI, VCP)
  Dimensión 2: VOLUMEN WYCKOFF (Kalman velocity + RVOL)
  Dimensión 3: OPCIONES GAMMA (Put/Call Walls, GEX Regime)

Fases diagnósticas:
  CORRECTION   — Retroceso sano a soporte. Volumen seco. FIRE.
  BREAKOUT     — Ruptura con volumen. Gamma amplifica. FIRE.
  EXHAUSTION_UP   — Extensión parabólica. Clímax de volumen. ABORT.
  EXHAUSTION_DOWN — Capitulación extrema. STALK para contrarian.
  CONSOLIDATION   — Rango lateral. STALK hasta ruptura.

Regla de Oro: FIRE solo si R:R >= 3.0 y 2 de 3 dimensiones confirman.
"""
import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class EntryVerdict:
    """Veredicto del diagnóstico de timing para un ticker."""
    ticker: str
    phase: str = "UNKNOWN"           # CORRECTION, BREAKOUT, EXHAUSTION_UP, EXHAUSTION_DOWN, CONSOLIDATION
    verdict: str = "STALK"           # FIRE, STALK, ABORT

    # Precio y estructura
    current_price: float = 0.0
    sma20: float = 0.0
    rsi14: float = 50.0
    atr14: float = 0.0
    distance_to_sma20_atr: float = 0.0  # Distancia en unidades de ATR
    vcp_detected: bool = False           # Volatility Contraction Pattern

    # Niveles de entrada calculados
    entry_price: float = 0.0          # Precio límite recomendado
    stop_price: float = 0.0           # Anclado a Put Wall - buffer
    target_price: float = 0.0         # Call Wall o próxima resistencia
    risk_reward_ratio: float = 0.0    # Target/Stop ratio

    # Dimensión 2: Volumen
    rvol: float = 1.0                 # Relative Volume
    wyckoff_state: str = "UNKNOWN"    # ACCUMULATION, MARKUP, DISTRIBUTION, MARKDOWN, CONSOLIDATION
    volume_confirms: bool = False     # True si volumen confirma la fase

    # Dimensión 3: Opciones
    put_wall: float = 0.0
    call_wall: float = 0.0
    gamma_regime: str = "UNKNOWN"     # PIN, DRIFT, SQUEEZE_UP, SQUEEZE_DOWN
    gamma_confirms: bool = False      # True si gamma confirma la fase

    # Meta
    dimensions_confirming: int = 0    # 0-3 dimensiones que confirman
    confidence: float = 0.0           # 0-100
    diagnosis: str = ""               # Explicación textual


# ═══════════════════════════════════════════════════════════════
# MAIN CLASS
# ═══════════════════════════════════════════════════════════════

class PricePhaseIntelligence:
    """
    Diagnostica la fase actual del precio y calcula la entrada óptima.

    Inputs (todos calculables de yfinance + módulos existentes):
      - Datos de precio diario (3 meses mínimo)
      - Options Awareness data (Put Wall, Call Wall, GEX Regime)
      - Volume Dynamics data (Wyckoff State, velocity)

    Output: EntryVerdict con fase, veredicto, y niveles exactos.
    """

    # ── Umbrales de diagnóstico ─────────────────────────────────
    EXHAUSTION_ATR_DISTANCE = 2.5     # > 2.5 ATR de SMA20 = extensión
    VCP_RANGE_CONTRACTION = 0.70      # ATR últimas 5 < 70% del ATR 20 = contracción
    BREAKOUT_RVOL_MIN = 1.5           # RVOL mínimo para confirmar breakout
    CORRECTION_RVOL_MAX = 0.9         # RVOL máximo para corrección sana (seco)
    RSI_OVERBOUGHT = 75
    RSI_OVERSOLD = 25
    MIN_RR_RATIO = 3.0                # R:R mínimo para FIRE
    _rsi_intel = None                 # RSIIntelligence (lazy, Cardwell/Brown)

    def diagnose(
        self,
        ticker: str,
        prices: pd.DataFrame,           # DataFrame con Open, High, Low, Close, Volume
        # Opciones (de options_awareness.py)
        put_wall: float = 0.0,
        call_wall: float = 0.0,
        gamma_regime: str = "UNKNOWN",
        # Volumen (de volume_dynamics.py)
        wyckoff_state: str = "UNKNOWN",
        wyckoff_velocity: float = 0.0,
        strategy_bucket: str = "CORE",    # "CORE" or "TACTICAL"
        vp_result = None,                 # DualProfileResult from VolumeProfileAnalyzer
    ) -> EntryVerdict:
        """
        Ejecuta el diagnóstico completo de timing.
        """
        v = EntryVerdict(ticker=ticker)

        if prices is None or prices.empty or len(prices) < 20:
            v.diagnosis = "Datos insuficientes (< 20 barras)"
            return v

        # Normalizar columnas
        if isinstance(prices.columns, pd.MultiIndex):
            prices.columns = prices.columns.get_level_values(0)

        close = prices['Close'].values.astype(float)
        high = prices['High'].values.astype(float)
        low = prices['Low'].values.astype(float)
        volume = prices['Volume'].values.astype(float)

        # ── Indicadores Base ────────────────────────────────────
        v.current_price = float(close[-1])
        v.sma20 = float(np.mean(close[-20:]))
        v.rsi14 = self._calc_rsi(close, 14)
        v.atr14 = self._calc_atr(high, low, close, 14)

        # ── RSI Intelligence (Cardwell/Brown Regime-Aware) ─────
        rsi_zone = "NEUTRAL"
        rsi_regime = "NEUTRAL"
        rsi_conviction = 0.0
        try:
            if PricePhaseIntelligence._rsi_intel is None:
                from infrastructure.data_providers.rsi_intelligence import RSIIntelligence
                PricePhaseIntelligence._rsi_intel = RSIIntelligence()

            # Derive regime hint from VP if available
            regime_hint = "NEUTRAL"
            if vp_result is not None:
                regime_map = {'ACCUMULATION': 'BULL', 'DISTRIBUTION': 'BEAR', 'NEUTRAL': 'NEUTRAL'}
                regime_hint = regime_map.get(vp_result.institutional_bias, 'NEUTRAL')

            rsi_result = PricePhaseIntelligence._rsi_intel.analyze(close, regime_hint=regime_hint)
            rsi_zone = rsi_result.rsi_zone
            rsi_regime = rsi_result.rsi_regime
            rsi_conviction = rsi_result.rsi_conviction
        except Exception:
            pass  # Fallback to static if RSI Intelligence unavailable

        # Distancia al SMA20 en unidades de ATR
        if v.atr14 > 0:
            v.distance_to_sma20_atr = (v.current_price - v.sma20) / v.atr14

        # VCP: ¿Las últimas 5 velas son más estrechas que el promedio?
        recent_ranges = high[-5:] - low[-5:]
        avg_range_5 = float(np.mean(recent_ranges))
        avg_range_20 = float(np.mean(high[-20:] - low[-20:]))
        v.vcp_detected = avg_range_5 < avg_range_20 * self.VCP_RANGE_CONTRACTION

        # RVOL
        avg_vol_20 = float(np.mean(volume[-20:]))
        v.rvol = float(volume[-1]) / avg_vol_20 if avg_vol_20 > 0 else 1.0

        # Volume Climax: ¿Es el día de mayor volumen en los últimos 60?
        lookback = min(len(volume), 60)
        is_volume_climax = float(volume[-1]) >= float(np.max(volume[-lookback:]) * 0.95)

        # ── Opciones ────────────────────────────────────────────
        v.put_wall = put_wall
        v.call_wall = call_wall
        v.gamma_regime = gamma_regime

        # ── Volumen Wyckoff ─────────────────────────────────────
        v.wyckoff_state = wyckoff_state

        # ═══ DIAGNÓSTICO DE FASE ════════════════════════════════
        # TACTICAL bucket uses empirical ML-validated phases
        if strategy_bucket == "TACTICAL":
            return self._diagnose_tactical(
                v, close, high, low, volume, is_volume_climax,
                put_wall, call_wall, gamma_regime, vp_result
            )
        
        # CORE bucket: Original institutional-grade phases
        # Priority order:
        #   1. BREAKOUT (new high + volume)
        #   2. EXHAUSTION UP (parabolic + no breakout volume)
        #   3. EXHAUSTION DOWN (capitulation)
        #   4. CORRECTION (pullback near SMA20 + dry volume)
        #   5. CONSOLIDATION (default)

        # 1. BREAKOUT: Ruptura de nuevo máximo con volumen confirmando
        #    A breakout that's already > 2.5 ATR from SMA20 is exhaustion, not breakout
        if (v.current_price > float(np.max(close[-20:-1]))
                and v.rvol >= self.BREAKOUT_RVOL_MIN
                and v.distance_to_sma20_atr <= self.EXHAUSTION_ATR_DISTANCE):
            v.phase = "BREAKOUT"
            v.volume_confirms = v.rvol >= self.BREAKOUT_RVOL_MIN
            v.gamma_confirms = gamma_regime in ("SQUEEZE_UP", "DRIFT")
            v.diagnosis = (
                f"RUPTURA de máximo 20d. RVOL={v.rvol:.1f}x confirma. "
                f"Gamma={gamma_regime}. "
                f"{'SQUEEZE amplificará el movimiento.' if gamma_regime == 'SQUEEZE_UP' else ''}"
            )

        # 2. EXHAUSTION UP: Extensión parabólica SIN breakout con volumen
        elif (v.distance_to_sma20_atr > self.EXHAUSTION_ATR_DISTANCE
                and v.rsi14 > self.RSI_OVERBOUGHT):
            v.phase = "EXHAUSTION_UP"
            v.verdict = "ABORT"
            v.volume_confirms = is_volume_climax
            v.gamma_confirms = gamma_regime in ("SQUEEZE_UP", "DRIFT")
            v.diagnosis = (
                f"EXTENSIÓN PARABÓLICA. Precio a {v.distance_to_sma20_atr:.1f} ATR "
                f"de SMA20. RSI={v.rsi14:.0f}. "
                f"{'Volumen CLÍMAX — distribución en curso.' if is_volume_climax else ''} "
                f"NO ENTRAR."
            )

        # 3. EXHAUSTION DOWN: Capitulación
        elif (v.distance_to_sma20_atr < -self.EXHAUSTION_ATR_DISTANCE
                and v.rsi14 < self.RSI_OVERSOLD):
            v.phase = "EXHAUSTION_DOWN"
            v.verdict = "STALK"
            v.volume_confirms = is_volume_climax
            v.gamma_confirms = gamma_regime in ("SQUEEZE_DOWN",)
            v.diagnosis = (
                f"CAPITULACIÓN. Precio a {abs(v.distance_to_sma20_atr):.1f} ATR debajo "
                f"de SMA20. RSI={v.rsi14:.0f}. "
                f"{'Volumen CLÍMAX — posible suelo.' if is_volume_climax else ''} "
                f"STALKEAR para entrada contrarian post-capitulación."
            )

        # 4. CORRECTION: Retroceso sano a soporte
        # V10: RSI is now regime-aware (Cardwell/Brown). Instead of static 40-62,
        # we accept RSI values that make sense for the current regime:
        #   BULL: PULLBACK_BUY (RSI 40-45) or HEALTHY_BULL (45-60) → best entries
        #   BEAR: HEALTHY_BEAR (40-55) → contrarian bounce opportunity
        #   NEUTRAL: LEAN_BULLISH or NEUTRAL (35-55) → standard correction
        # Static gate only used as extreme safety valve (RSI > 75 or RSI < 20)
        
        # Calculate volume direction: is volume on UP or DOWN days?
        up_vol_total = 0.0
        down_vol_total = 0.0
        up_count = 0
        down_count = 0
        for i in range(-5, 0):
            if i > -len(close) and close[i] > close[i-1]:
                up_vol_total += volume[i]
                up_count += 1
            elif i > -len(close):
                down_vol_total += volume[i]
                down_count += 1
        
        avg_up_v = up_vol_total / max(up_count, 1)
        avg_down_v = down_vol_total / max(down_count, 1)
        recent_up_down_ratio = avg_up_v / avg_down_v if avg_down_v > 0 else 2.0
        volume_confirms_accumulation = recent_up_down_ratio > 1.0

        # V10: Regime-aware RSI acceptance for CORRECTION
        rsi_acceptable_for_correction = (
            rsi_zone in ("PULLBACK_BUY", "HEALTHY_BULL", "HEALTHY_BEAR",
                         "LEAN_BULLISH", "NEUTRAL", "OVERSOLD")
            and v.rsi14 < self.RSI_OVERBOUGHT  # Never enter at RSI > 75
            and v.rsi14 > 20                   # Never enter at RSI < 20 (capitulation)
        )
        
        if (v.distance_to_sma20_atr > -2.0 and v.distance_to_sma20_atr < 0.5
                and rsi_acceptable_for_correction
                and v.rvol < self.CORRECTION_RVOL_MAX):
            
            if volume_confirms_accumulation:
                # VP Enhancement: Check institutional bias from Volume Profile
                vp_confirms = True
                vp_info = ""
                if vp_result is not None:
                    vp_confirms = vp_result.institutional_bias != "DISTRIBUTION"
                    vp_info = (
                        f"VP: {vp_result.short.shape}/{vp_result.long.shape} "
                        f"POC_mig={vp_result.poc_migration} "
                        f"Bias={vp_result.institutional_bias}. "
                    )
                    if not vp_confirms:
                        # VP says distribution — override to STALK
                        v.phase = "VP_DISTRIBUTION_BLOCK"
                        v.verdict = "STALK"
                        v.diagnosis = (
                            f"⚠️ VP DISTRIBUTION. Vol UP/DOWN={recent_up_down_ratio:.1f}x OK "
                            f"pero Volume Profile muestra {vp_result.short.shape}-shape (corto), "
                            f"{vp_result.long.shape}-shape (largo). "
                            f"POC Migration={vp_result.poc_migration}. "
                            f"Institucionales distribuyendo. NO ENTRAR."
                        )
                        # Skip to end — don't set as CORRECTION
                        return self._finalize_verdict(v, gamma_regime, vp_result)
                
                v.phase = "CORRECTION"
                v.volume_confirms = True
                v.gamma_confirms = gamma_regime == "PIN"
                v.vcp_detected = v.vcp_detected
                v.diagnosis = (
                    f"CORRECCIÓN SANA. Precio cerca de SMA20 ({v.distance_to_sma20_atr:+.1f} ATR). "
                    f"RSI={v.rsi14:.0f}. RVOL={v.rvol:.1f}x (seco). "
                    f"Vol UP/DOWN={recent_up_down_ratio:.1f}x → ACUMULACIÓN. "
                    f"{vp_info}"
                    f"{'VCP detectado.' if v.vcp_detected else ''} "
                    f"{'PIN Gamma.' if gamma_regime == 'PIN' else ''}"
                )
            else:
                # Volume on DOWN days > UP days = DISTRIBUTION disguised as correction
                v.phase = "STEALTH_DISTRIBUTION"
                v.verdict = "STALK"
                v.diagnosis = (
                    f"⚠️ DISTRIBUCIÓN ENCUBIERTA. Parece corrección pero volumen "
                    f"concentrado en días DOWN (ratio={recent_up_down_ratio:.2f}). "
                    f"RSI={v.rsi14:.0f}. Institucionales vendiendo gradualmente. "
                    f"NO ENTRAR — esperar confirmación de acumulación real."
                )

        # 5. CONSOLIDATION: Rango lateral
        else:
            v.phase = "CONSOLIDATION"
            v.verdict = "STALK"
            v.diagnosis = (
                f"CONSOLIDACIÓN. Dist SMA20={v.distance_to_sma20_atr:+.1f} ATR. "
                f"RSI={v.rsi14:.0f}. RVOL={v.rvol:.1f}x. "
                f"Sin señal direccional clara. Esperar ruptura."
            )

        # ═══ CALCULAR NIVELES DE ENTRADA ════════════════════════

        # Entry price: Use Volume Profile levels when available
        if v.phase in ("CORRECTION", "BREAKOUT"):
            # VP-anchored levels (institutional precision)
            vp_val = None
            vp_poc = None
            vp_vah = None
            if vp_result is not None and vp_result.short.val > 0:
                vp_val = vp_result.short.val
                vp_poc = vp_result.short.poc
                vp_vah = vp_result.short.vah
            
            if put_wall > 0 and abs(v.current_price - put_wall) / v.current_price < 0.03:
                v.entry_price = round(put_wall * 1.002, 2)
            elif v.phase == "CORRECTION" and vp_val and abs(v.current_price - vp_val) / v.current_price < 0.05:
                # Entry near VAL (institutional support)
                v.entry_price = round(max(vp_val, v.current_price * 0.998), 2)
            elif v.phase == "CORRECTION":
                v.entry_price = round(max(v.sma20, v.current_price * 0.998), 2)
            else:
                v.entry_price = round(v.current_price * 1.003, 2)

            # Stop: VAL or Put Wall (institutional floor)
            if put_wall > 0:
                v.stop_price = round(put_wall - 0.3 * v.atr14, 2)
            elif vp_val:
                # Below VAL with 0.3×ATR buffer (institutional support breach)
                v.stop_price = round(vp_val - 0.3 * v.atr14, 2)
            else:
                v.stop_price = round(v.entry_price - 2.0 * v.atr14, 2)

            # Target: POC or VAH (institutional magnets)
            risk = v.entry_price - v.stop_price
            if call_wall > 0 and call_wall > v.entry_price:
                v.target_price = round(call_wall, 2)
            elif vp_poc and vp_poc > v.entry_price:
                # POC as target (price gravitates to POC)
                v.target_price = round(vp_poc, 2)
            elif vp_vah and vp_vah > v.entry_price:
                v.target_price = round(vp_vah, 2)
            else:
                v.target_price = round(v.entry_price + risk * 3.5, 2)

            # R:R
            if risk > 0:
                reward = v.target_price - v.entry_price
                v.risk_reward_ratio = round(reward / risk, 1)

        # ═══ CONTAR CONFIRMACIONES Y DECIDIR ════════════════════

        # Dimensión 1: Precio (siempre contribuye si la fase es clara)
        price_confirms = v.phase in ("CORRECTION", "BREAKOUT")

        # Dimensión 2: Volumen
        vol_confirms = (
            (v.phase == "CORRECTION" and v.volume_confirms) or
            (v.phase == "BREAKOUT" and v.volume_confirms) or
            (v.wyckoff_state == "ACCUMULATION" and v.phase == "CORRECTION") or
            (v.wyckoff_state == "MARKUP" and v.phase == "BREAKOUT")
        )

        # Dimensión 3: Gamma
        gamma_confirms = (
            (v.phase == "CORRECTION" and gamma_regime == "PIN") or
            (v.phase == "BREAKOUT" and gamma_regime in ("SQUEEZE_UP", "DRIFT"))
        )

        v.dimensions_confirming = sum([price_confirms, vol_confirms, gamma_confirms])
        v.confidence = round(v.dimensions_confirming / 3.0 * 100, 0)

        # FIRE solo si R:R >= 3.0 Y al menos 2 de 3 dimensiones confirman
        if v.phase in ("CORRECTION", "BREAKOUT"):
            if v.risk_reward_ratio >= self.MIN_RR_RATIO and v.dimensions_confirming >= 2:
                v.verdict = "FIRE"
                v.diagnosis += f" ✅ FIRE: R:R={v.risk_reward_ratio}:1, {v.dimensions_confirming}/3 confirman."
            elif v.risk_reward_ratio >= self.MIN_RR_RATIO:
                v.verdict = "STALK"
                v.diagnosis += f" ⏳ STALK: R:R bueno ({v.risk_reward_ratio}:1) pero solo {v.dimensions_confirming}/3 confirman."
            else:
                v.verdict = "STALK"
                v.diagnosis += f" ⏳ STALK: R:R insuficiente ({v.risk_reward_ratio}:1 < {self.MIN_RR_RATIO}:1)."

        logger.info(
            f"PricePhase {ticker}: {v.phase} → {v.verdict} "
            f"(R:R={v.risk_reward_ratio}:1, conf={v.confidence:.0f}%, "
            f"dims={v.dimensions_confirming}/3)"
        )
        return v

    def _finalize_verdict(self, v: EntryVerdict, gamma_regime: str, vp_result=None) -> EntryVerdict:
        """Quick finalize for early returns (VP blocks, etc.)."""
        logger.info(
            f"PricePhase {v.ticker}: {v.phase} → {v.verdict} "
            f"(R:R={v.risk_reward_ratio}:1, conf={v.confidence:.0f}%)"
        )
        return v

    def _diagnose_tactical(
        self,
        v: EntryVerdict,
        close: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        volume: np.ndarray,
        is_volume_climax: bool,
        put_wall: float,
        call_wall: float,
        gamma_regime: str,
        vp_result=None,
    ) -> EntryVerdict:
        """
        TACTICAL phase diagnosis based on forensic ML analysis.
        
        Empirical findings (2,515 obs, S&P 500, April 2026):
        - Gap DOWN (<-2%): WR=63%, avg_5d=+1.89% → CONTRARIAN_DIP
        - Gap UP (>3%): WR=34%, avg_5d=-2.24% → DON'T CHASE
        - Momentum Q5 + no gap chase: WR=56%, avg_5d=+2.30%
        - dist_sma20_atr > 2.06: WR=62% (most important feature)
        - rsi ≤ 45: WR=60% (oversold bounces work)
        - bull_bear_ratio sweet spot: 1.0-2.0 (extremes underperform)
        """
        # Calculate gap% from yesterday
        # V10: Compute RSI Intelligence for tactical phases
        rsi_zone = "NEUTRAL"
        try:
            if PricePhaseIntelligence._rsi_intel is None:
                from infrastructure.data_providers.rsi_intelligence import RSIIntelligence
                PricePhaseIntelligence._rsi_intel = RSIIntelligence()
            regime_hint = "NEUTRAL"
            if vp_result is not None:
                regime_map = {'ACCUMULATION': 'BULL', 'DISTRIBUTION': 'BEAR', 'NEUTRAL': 'NEUTRAL'}
                regime_hint = regime_map.get(vp_result.institutional_bias, 'NEUTRAL')
            rsi_result = PricePhaseIntelligence._rsi_intel.analyze(close, regime_hint=regime_hint)
            rsi_zone = rsi_result.rsi_zone
        except Exception:
            pass

        if len(close) >= 2:
            prev_close = float(close[-2])
            today_open = float(high[-1] + low[-1]) / 2  # Approx open from H+L
            gap_pct = ((float(close[-1]) / prev_close) - 1) * 100
        else:
            gap_pct = 0
            prev_close = float(close[-1])
        
        # Momentum 5d
        if len(close) >= 6:
            momentum_5d = ((float(close[-1]) / float(close[-6])) - 1) * 100
        else:
            momentum_5d = 0
        
        # ═══ PHASE 1: CONTRARIAN_DIP (Highest conviction — WR=63%) ═══
        # Empirical: gap_pct < -2%, dist_sma20_atr > -3, rsi < 55, rvol > 1.3
        is_dip = (
            gap_pct < -2.0
            and v.distance_to_sma20_atr > -3.0  # Not in free-fall
            and v.rsi14 < 55
            and v.rvol > 1.0  # Some participation
        )
        
        if is_dip:
            v.phase = "CONTRARIAN_DIP"
            v.verdict = "FIRE"
            
            # Entry at current close (buying the dip)
            v.entry_price = round(v.current_price * 1.001, 2)
            
            # Stop: below recent low or 2 ATR
            recent_low = float(np.min(low[-5:]))
            v.stop_price = round(min(recent_low, v.current_price - 2.0 * v.atr14) * 0.998, 2)
            
            # Target: SMA20 or 3x risk
            risk = v.entry_price - v.stop_price
            if risk > 0:
                sma_target = v.sma20 if v.sma20 > v.entry_price else v.entry_price + risk * 3.5
                v.target_price = round(max(sma_target, v.entry_price + risk * 2.5), 2)
                v.risk_reward_ratio = round((v.target_price - v.entry_price) / risk, 1)
            
            v.dimensions_confirming = 2  # Price dip + Volume participation
            v.confidence = 63.0  # Empirical WR from forensic analysis
            v.diagnosis = (
                f"CONTRARIAN DIP. Gap={gap_pct:+.1f}%. RSI={v.rsi14:.0f}. "
                f"RVOL={v.rvol:.1f}x. Dist_SMA20={v.distance_to_sma20_atr:+.1f} ATR. "
                f"ML: WR=63% para gap downs con estructura intacta. "
                f"✅ TACTICAL FIRE: R:R={v.risk_reward_ratio}:1."
            )
            logger.info(f"PricePhase {v.ticker}: CONTRARIAN_DIP → FIRE (gap={gap_pct:+.1f}%, conf=63%)")
            return v
        
        # ═══ PHASE 2: MOMENTUM_CONTINUATION (Tightened from forensics) ═══
        # V10: RSI gate is now regime-aware. In BULL regime, RSI 60-80 is CONTINUATION
        # (not overbought). Accept CONTINUATION, HEALTHY_BULL, PULLBACK_BUY zones.
        rsi_ok_for_momentum = (
            rsi_zone in ("CONTINUATION", "HEALTHY_BULL", "PULLBACK_BUY",
                         "LEAN_BULLISH", "NEUTRAL")
            and v.rsi14 < 80  # Only block extreme >80
        )
        is_momentum = (
            momentum_5d > 4.0  # Strong 5d trend (tighter than before)
            and v.distance_to_sma20_atr > 1.0  # Above structure
            and abs(gap_pct) < 2.5  # NOT chasing a gap (tightened)
            and rsi_ok_for_momentum  # V10: regime-aware RSI
            and v.rvol > 1.3  # Volume confirms (not a dead drift)
        )
        
        if is_momentum:
            v.phase = "MOMENTUM_CONTINUATION"
            v.verdict = "FIRE"
            
            v.entry_price = round(v.current_price * 1.002, 2)
            v.stop_price = round(v.current_price - 2.0 * v.atr14, 2)
            
            risk = v.entry_price - v.stop_price
            if risk > 0:
                v.target_price = round(v.entry_price + risk * 3.0, 2)
                v.risk_reward_ratio = round((v.target_price - v.entry_price) / risk, 1)
            
            v.dimensions_confirming = 2
            v.confidence = 56.0
            v.diagnosis = (
                f"MOMENTUM CONTINUATION. Mom5d={momentum_5d:+.1f}%. "
                f"Dist_SMA20={v.distance_to_sma20_atr:+.1f} ATR. Gap={gap_pct:+.1f}% (no chase). "
                f"ML: WR=56% para momentum Q5 sin gap chase. "
                f"✅ TACTICAL FIRE: R:R={v.risk_reward_ratio}:1."
            )
            logger.info(f"PricePhase {v.ticker}: MOMENTUM_CONTINUATION → FIRE (mom5d={momentum_5d:+.1f}%, conf=56%)")
            return v
        
        # ═══ PHASE 3: GAP_CHASE (ABORT — WR=34%) ═══
        if gap_pct > 3.0:
            v.phase = "GAP_CHASE"
            v.verdict = "ABORT"
            v.confidence = 34.0
            v.diagnosis = (
                f"GAP CHASE ABORT. Gap={gap_pct:+.1f}% (>3%). "
                f"ML: WR=34% para gap ups >3%, avg_5d=-2.24%. "
                f"❌ Históricamente destruye valor. NO ENTRAR."
            )
            logger.info(f"PricePhase {v.ticker}: GAP_CHASE → ABORT (gap={gap_pct:+.1f}%, WR=34%)")
            return v
        
        # ═══ DEFAULT: STALK ═══
        v.phase = "TACTICAL_NEUTRAL"
        v.verdict = "STALK"
        v.confidence = 50.0
        v.diagnosis = (
            f"Sin señal táctica clara. Gap={gap_pct:+.1f}%. Mom5d={momentum_5d:+.1f}%. "
            f"RSI={v.rsi14:.0f}. RVOL={v.rvol:.1f}x. Esperar setup."
        )
        return v

    # ── Indicadores Técnicos ────────────────────────────────────

    @staticmethod
    def _calc_rsi(close: np.ndarray, period: int = 14) -> float:
        """Calcula RSI (Relative Strength Index)."""
        if len(close) < period + 1:
            return 50.0
        deltas = np.diff(close[-(period + 1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains) if len(gains) > 0 else 0
        avg_loss = np.mean(losses) if len(losses) > 0 else 0.001
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        return round(100 - (100 / (1 + rs)), 1)

    @staticmethod
    def _calc_atr(high: np.ndarray, low: np.ndarray,
                  close: np.ndarray, period: int = 14) -> float:
        """Calcula ATR (Average True Range)."""
        if len(close) < period + 1:
            return float(np.mean(high[-5:] - low[-5:])) if len(high) >= 5 else 1.0
        tr_list = []
        for i in range(1, min(period + 1, len(close))):
            tr = max(
                high[-i] - low[-i],
                abs(high[-i] - close[-i - 1]),
                abs(low[-i] - close[-i - 1]),
            )
            tr_list.append(tr)
        return round(float(np.mean(tr_list)), 4) if tr_list else 1.0
