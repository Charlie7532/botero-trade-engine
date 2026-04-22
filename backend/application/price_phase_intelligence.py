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
        # Priority order:
        #   1. BREAKOUT (new high + volume) — must be checked before
        #      exhaustion because a fresh breakout naturally has high RSI
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
        elif (abs(v.distance_to_sma20_atr) < 2.0
                and v.rsi14 >= 30 and v.rsi14 <= 62
                and v.rvol < self.CORRECTION_RVOL_MAX):
            v.phase = "CORRECTION"
            v.volume_confirms = v.rvol < self.CORRECTION_RVOL_MAX
            v.gamma_confirms = gamma_regime == "PIN"
            v.vcp_detected = v.vcp_detected  # Already calculated
            v.diagnosis = (
                f"CORRECCIÓN SANA. Precio cerca de SMA20 ({v.distance_to_sma20_atr:+.1f} ATR). "
                f"RSI={v.rsi14:.0f} (descansando). RVOL={v.rvol:.1f}x (seco). "
                f"{'VCP detectado — contracción de volatilidad.' if v.vcp_detected else ''} "
                f"{'PIN Gamma — dealers sostienen el precio.' if gamma_regime == 'PIN' else ''}"
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

        # Entry price: preferir Put Wall si está disponible y el precio está cerca
        if v.phase in ("CORRECTION", "BREAKOUT"):
            if put_wall > 0 and abs(v.current_price - put_wall) / v.current_price < 0.03:
                # Put Wall cercano → entrar justo por encima
                v.entry_price = round(put_wall * 1.002, 2)  # +0.2% buffer
            elif v.phase == "CORRECTION":
                # Entrar cerca del SMA20
                v.entry_price = round(max(v.sma20, v.current_price * 0.998), 2)
            else:
                # Breakout: entrar al precio actual con buffer
                v.entry_price = round(v.current_price * 1.003, 2)

            # Stop: anclado a Put Wall si disponible, sino ATR
            if put_wall > 0:
                # Debajo del Put Wall con buffer de 0.3×ATR
                v.stop_price = round(put_wall - 0.3 * v.atr14, 2)
            else:
                # Fallback: 2×ATR debajo de entry
                v.stop_price = round(v.entry_price - 2.0 * v.atr14, 2)

            # Target: Call Wall si disponible, sino 3×riesgo
            risk = v.entry_price - v.stop_price
            if call_wall > 0 and call_wall > v.entry_price:
                v.target_price = round(call_wall, 2)
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
