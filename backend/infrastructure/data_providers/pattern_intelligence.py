"""
PATTERN RECOGNITION INTELLIGENCE — Los Ojos del Algoritmo
==========================================================
"Ver la estructura visual del precio es la diferencia entre
 tener razón y saber CUÁNDO actuar."

Detecta patrones de velas japonesas y estructuras clásicas de precio
como CUARTA DIMENSIÓN de confirmación dentro del EntryIntelligenceHub.

Implementado en NumPy puro para evitar dependencia de TA-Lib (C extension).
pandas-ta se usa como acelerador opcional si está disponible.

Jerarquía de patrones (por número de velas):
  Single:  Hammer, Shooting Star, Doji, Dragonfly Doji, Gravestone Doji
  Double:  Bullish Engulfing, Bearish Engulfing, Piercing Line, Dark Cloud Cover
  Triple:  Morning Star, Evening Star, Three White Soldiers, Three Black Crows

Estructuras:
  Inside Bar Series  — Coil / VCP de alta calidad
  VCP Tightness      — Volatility Contraction Pattern (Minervini)

Integración con el Hub:
  PatternRecognitionIntelligence.detect(prices_df, put_wall, call_wall)
  → PatternVerdict con sentiment, confirmation_score, y diagnosis.

Reglas de integración (aplicadas en EntryIntelligenceHub):
  VETO    — Patrón bajista cancela FIRE → STALK
  AMPLIFY — Patrón alcista en soporte clave → +25% position scale
  PROMOTE — Patrón alcista fuerte puede elevar STALK → FIRE (si 2+ dims confirman)

Ubicación: infrastructure/data_providers/ (depende de pandas + numpy — librería externa)
"""
import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Intento de importar pandas-ta como acelerador opcional
try:
    import pandas_ta as ta
    _PANDAS_TA_AVAILABLE = True
    logger.debug("PatternIntelligence: pandas-ta disponible ✅")
except ImportError:
    _PANDAS_TA_AVAILABLE = False
    logger.debug("PatternIntelligence: pandas-ta no disponible, usando NumPy puro ✅")


# ═══════════════════════════════════════════════════════════════
# DATACLASS DE RESULTADO
# ═══════════════════════════════════════════════════════════════

@dataclass
class PatternVerdict:
    """Resultado del análisis de patrones de velas y estructuras."""
    ticker: str = ""

    # Patrón primario detectado (última vela o secuencia)
    primary_pattern: str = "NONE"
    # Patrón secundario de confirmación (si existe)
    secondary_pattern: str = "NONE"

    # Sentimiento consolidado
    sentiment: str = "NEUTRAL"         # BULLISH | BEARISH | NEUTRAL
    confirmation_score: float = 0.0    # -1.0 (muy bajista) → +1.0 (muy alcista)

    # Estructuras de consolidación
    is_inside_bar_series: bool = False  # 2+ inside bars consecutivas = coil/spring
    is_vcp_tight: bool = False          # VCP de alta calidad (contracciones sucesivas)

    # Contexto de ubicación
    detected_on_support: bool = False   # ¿El patrón ocurre en zona de soporte clave?
    detected_on_resistance: bool = False

    # Meta
    candles_analyzed: int = 0
    diagnosis: str = ""


# ═══════════════════════════════════════════════════════════════
# MOTOR DE DETECCIÓN
# ═══════════════════════════════════════════════════════════════

class PatternRecognitionIntelligence:
    """
    Detecta patrones de velas japonesas y estructuras de precio.

    Uso desde EntryIntelligenceHub:
        pattern = PatternRecognitionIntelligence()
        verdict = pattern.detect(prices_df, put_wall=150.0, call_wall=165.0)

    El módulo evalúa las ÚLTIMAS 3 velas y las últimas 10 para estructuras.
    """

    # ── Umbrales de detección ────────────────────────────────────
    DOJI_BODY_RATIO = 0.07          # Cuerpo <= 7% del rango total → Doji (evita confundir Hammer pequeño)
    HAMMER_WICK_RATIO = 2.0         # Mecha inferior >= 2x cuerpo
    ENGULFING_MIN_BODY_RATIO = 0.0  # Engulfing clásico: solo requiere envolvimiento completo
    STAR_BODY_RATIO = 0.35          # Cuerpo estrella <= 35% del rango
    INSIDE_BAR_MIN_BARS = 2         # Mínimo 2 inside bars para considerar coil
    VCP_CONTRACTION_RATIO = 0.80    # Cada rango <= 80% del anterior para VCP
    SUPPORT_PROXIMITY_PCT = 0.06    # 6% del precio — soporte puede estar debajo del close actual

    def detect(
        self,
        prices: pd.DataFrame,
        put_wall: float = 0.0,
        call_wall: float = 0.0,
        ticker: str = "",
    ) -> PatternVerdict:
        """
        Ejecuta el análisis completo de patrones.

        Args:
            prices: DataFrame con columnas Open, High, Low, Close, Volume (daily).
            put_wall: Nivel de soporte institucional (de OptionsAwareness).
            call_wall: Nivel de resistencia institucional.
            ticker: Ticker para logging.

        Returns:
            PatternVerdict con el diagnóstico completo.
        """
        verdict = PatternVerdict(ticker=ticker)

        if prices is None or prices.empty or len(prices) < 3:
            verdict.diagnosis = "Datos insuficientes para detectar patrones (<3 barras)"
            return verdict

        # Normalizar columnas MultiIndex
        if isinstance(prices.columns, pd.MultiIndex):
            prices = prices.copy()
            prices.columns = prices.columns.get_level_values(0)

        # Extraer arrays NumPy
        o = prices['Open'].values.astype(float)
        h = prices['High'].values.astype(float)
        l = prices['Low'].values.astype(float)
        c = prices['Close'].values.astype(float)

        verdict.candles_analyzed = len(c)

        # ── Detección de patrones (prioridad: triple > doble > single) ──
        triple = self._detect_three_candle(o, h, l, c)
        if triple != "NONE":
            verdict.primary_pattern = triple
        else:
            double = self._detect_two_candle(o, h, l, c)
            if double != "NONE":
                verdict.primary_pattern = double
            else:
                verdict.primary_pattern = self._detect_single_candle(o, h, l, c)

        # ── Patrón secundario (penúltima vela para contexto) ─────────
        if len(c) >= 4:
            verdict.secondary_pattern = self._detect_single_candle(
                o[:-1], h[:-1], l[:-1], c[:-1]
            )

        # ── Estructuras ──────────────────────────────────────────────
        structure = self._detect_structure(h, l, c)
        verdict.is_inside_bar_series = structure["inside_bar_series"]
        verdict.is_vcp_tight = structure["vcp_tight"]

        # ── Contexto: ¿Patrón en zona institucional? ─────────────────
        current_price = float(c[-1])
        recent_low = float(l[-3:].min())  # Mínimo reciente: precio tocó el soporte esta semana
        if put_wall > 0:
            # Soporte alcanzado si el mínimo reciente está cerca del put_wall
            proximity_low = abs(recent_low - put_wall) / max(put_wall, 0.01)
            proximity_close = abs(current_price - put_wall) / max(current_price, 0.01)
            verdict.detected_on_support = (
                proximity_low <= self.SUPPORT_PROXIMITY_PCT
                or proximity_close <= self.SUPPORT_PROXIMITY_PCT
            )
        if call_wall > 0:
            proximity = abs(current_price - call_wall) / max(current_price, 0.01)
            verdict.detected_on_resistance = proximity <= self.SUPPORT_PROXIMITY_PCT

        # ── Scoring de sentimiento ────────────────────────────────────
        verdict.sentiment, verdict.confirmation_score = self._score_sentiment(
            verdict.primary_pattern,
            verdict.secondary_pattern,
            verdict.is_inside_bar_series,
            verdict.detected_on_support,
        )

        # ── Diagnosis textual ─────────────────────────────────────────
        verdict.diagnosis = self._build_diagnosis(verdict, current_price, put_wall, call_wall)

        logger.info(
            f"PatternIntelligence {ticker}: {verdict.primary_pattern} → "
            f"{verdict.sentiment} (score={verdict.confirmation_score:+.2f}, "
            f"on_support={verdict.detected_on_support})"
        )
        return verdict

    # ═══════════════════════════════════════════════════════════
    # DETECCIÓN SINGLE-CANDLE
    # ═══════════════════════════════════════════════════════════

    def _detect_single_candle(
        self,
        o: np.ndarray,
        h: np.ndarray,
        l: np.ndarray,
        c: np.ndarray,
    ) -> str:
        """Detecta patrón en la última vela del array usando OHLC reales."""
        if len(c) < 1:
            return "NONE"
        return self._classify_single(
            float(o[-1]), float(h[-1]), float(l[-1]), float(c[-1])
        )

    def _classify_single(
        self,
        o: float, h: float, l: float, c: float
    ) -> str:
        """Clasifica una sola vela OHLC."""
        total_range = h - l
        if total_range <= 0:
            return "NONE"

        body = abs(c - o)
        lower_wick = min(o, c) - l
        upper_wick = h - max(o, c)
        body_ratio = body / total_range

        # Doji: cuerpo muy pequeño
        if body_ratio <= self.DOJI_BODY_RATIO:
            if lower_wick >= total_range * 0.6:
                return "DRAGONFLY_DOJI"   # Alcista
            if upper_wick >= total_range * 0.6:
                return "GRAVESTONE_DOJI"  # Bajista
            return "DOJI"

        # Hammer / Hanging Man: mecha inferior larga, cuerpo arriba
        if lower_wick >= self.HAMMER_WICK_RATIO * body and upper_wick <= 0.5 * body:
            if c > o:  # Vela alcista = Hammer (reversión alcista)
                return "HAMMER"
            else:       # Vela bajista = Hanging Man (señal bajista en tendencia)
                return "HANGING_MAN"

        # Shooting Star / Inverted Hammer: mecha superior larga
        if upper_wick >= self.HAMMER_WICK_RATIO * body and lower_wick <= 0.5 * body:
            if c < o:  # Vela bajista = Shooting Star (reversión bajista)
                return "SHOOTING_STAR"
            else:       # Vela alcista = Inverted Hammer (alcista en soporte)
                return "INVERTED_HAMMER"

        # Marubozu alcista: sin mechas, vela grande
        if body_ratio >= 0.85 and c > o:
            return "BULLISH_MARUBOZU"

        # Marubozu bajista
        if body_ratio >= 0.85 and c < o:
            return "BEARISH_MARUBOZU"

        return "NONE"

    # ═══════════════════════════════════════════════════════════
    # DETECCIÓN TWO-CANDLE
    # ═══════════════════════════════════════════════════════════

    def _detect_two_candle(
        self,
        o: np.ndarray,
        h: np.ndarray,
        l: np.ndarray,
        c: np.ndarray,
    ) -> str:
        """Detecta patrones de 2 velas en las últimas 2 barras."""
        if len(c) < 2:
            return "NONE"

        # Vela previa
        po = float(o[-2]); ph = float(h[-2]); pl = float(l[-2]); pc = float(c[-2])
        # Vela actual
        co = float(o[-1]); ch = float(h[-1]); cl = float(l[-1]); cc = float(c[-1])

        prev_body = pc - po
        curr_body = cc - co
        prev_body_size = abs(prev_body)
        curr_body_size = abs(curr_body)

        # ── Bullish Engulfing ─────────────────────────────────────────
        # Vela bajista previa + vela alcista que envuelve completamente
        if (prev_body < 0 and curr_body > 0
                and co <= pc and cc >= po
                and curr_body_size >= prev_body_size * (1 + self.ENGULFING_MIN_BODY_RATIO)):
            return "BULLISH_ENGULFING"

        # ── Bearish Engulfing ─────────────────────────────────────────
        # Vela alcista previa + vela bajista que envuelve completamente
        if (prev_body > 0 and curr_body < 0
                and co >= pc and cc <= po
                and curr_body_size >= prev_body_size * (1 + self.ENGULFING_MIN_BODY_RATIO)):
            return "BEARISH_ENGULFING"

        # ── Piercing Line (alcista) ───────────────────────────────────
        # Vela bajista larga + vela alcista que cierra por encima del midpoint
        prev_mid = (po + pc) / 2
        if (prev_body < 0 and curr_body > 0
                and co < pl                      # Abre por debajo del mínimo previo
                and cc > prev_mid                # Cierra por encima del midpoint
                and cc < po):                    # Pero no cierra por encima del open previo
            return "PIERCING_LINE"

        # ── Dark Cloud Cover (bajista) ────────────────────────────────
        curr_mid = (co + cc) / 2
        if (prev_body > 0 and curr_body < 0
                and co > ph                      # Abre por encima del máximo previo
                and cc < (po + pc) / 2           # Cierra por debajo del midpoint previo
                and cc > po):                    # Pero no por debajo del open previo
            return "DARK_CLOUD_COVER"

        # ── Tweezer Bottom (alcista) ──────────────────────────────────
        # Dos velas con mínimos casi idénticos (soporte fuerte)
        if (abs(pl - cl) / max(pl, 0.01) < 0.003
                and prev_body < 0 and curr_body > 0):
            return "TWEEZER_BOTTOM"

        # ── Tweezer Top (bajista) ─────────────────────────────────────
        if (abs(ph - ch) / max(ph, 0.01) < 0.003
                and prev_body > 0 and curr_body < 0):
            return "TWEEZER_TOP"

        return "NONE"

    # ═══════════════════════════════════════════════════════════
    # DETECCIÓN THREE-CANDLE
    # ═══════════════════════════════════════════════════════════

    def _detect_three_candle(
        self,
        o: np.ndarray,
        h: np.ndarray,
        l: np.ndarray,
        c: np.ndarray,
    ) -> str:
        """Detecta patrones de 3 velas en las últimas 3 barras."""
        if len(c) < 3:
            return "NONE"

        # Velas 1, 2, 3 (de más antigua a más reciente)
        o1, h1, l1, c1 = float(o[-3]), float(h[-3]), float(l[-3]), float(c[-3])
        o2, h2, l2, c2 = float(o[-2]), float(h[-2]), float(l[-2]), float(c[-2])
        o3, h3, l3, c3 = float(o[-1]), float(h[-1]), float(l[-1]), float(c[-1])

        body1 = c1 - o1
        body2 = c2 - o2
        body3 = c3 - o3
        body2_range = h2 - l2

        # ── Morning Star (alcista fuerte) ─────────────────────────────
        # 1: Vela bajista larga | 2: vela pequeña (doji/star) | 3: vela alcista larga
        star_body_ratio = abs(body2) / body2_range if body2_range > 0 else 1.0
        if (body1 < 0                              # Vela 1 bajista
                and star_body_ratio <= self.STAR_BODY_RATIO   # Vela 2 es estrella
                and body3 > 0                      # Vela 3 alcista
                and c3 > (o1 + c1) / 2             # Recupera > mitad de vela 1
                and abs(body1) > abs(body2) * 2):  # Vela 1 claramente dominante
            return "MORNING_STAR"

        # ── Evening Star (bajista fuerte) ─────────────────────────────
        if (body1 > 0
                and star_body_ratio <= self.STAR_BODY_RATIO
                and body3 < 0
                and c3 < (o1 + c1) / 2
                and abs(body1) > abs(body2) * 2):
            return "EVENING_STAR"

        # ── Three White Soldiers (alcista de continuación) ────────────
        if (body1 > 0 and body2 > 0 and body3 > 0   # Todas alcistas
                and c2 > c1 and c3 > c2              # Cierres ascendentes
                and o2 > o1 and o3 > o2              # Opens dentro del cuerpo previo
                and o2 < c1 and o3 < c2):            # Opens dentro del cuerpo previo (gap fill)
            return "THREE_WHITE_SOLDIERS"

        # ── Three Black Crows (bajista de continuación) ───────────────
        if (body1 < 0 and body2 < 0 and body3 < 0
                and c2 < c1 and c3 < c2
                and o2 < o1 and o3 < o2
                and o2 > c1 and o3 > c2):
            return "THREE_BLACK_CROWS"

        return "NONE"

    # ═══════════════════════════════════════════════════════════
    # DETECCIÓN DE ESTRUCTURA
    # ═══════════════════════════════════════════════════════════

    def _detect_structure(
        self,
        h: np.ndarray,
        l: np.ndarray,
        c: np.ndarray,
        lookback: int = 10,
    ) -> dict:
        """
        Detecta estructuras de consolidación en las últimas N barras.

        Returns:
            dict con 'inside_bar_series' y 'vcp_tight'
        """
        result = {"inside_bar_series": False, "vcp_tight": False}
        n = min(lookback, len(h))
        if n < 3:
            return result

        recent_h = h[-n:]
        recent_l = l[-n:]

        # ── Inside Bar Series ─────────────────────────────────────────
        # Cuenta cuántas de las últimas velas están DENTRO del rango de la anterior
        inside_count = 0
        for i in range(1, n):
            if recent_h[i] < recent_h[i - 1] and recent_l[i] > recent_l[i - 1]:
                inside_count += 1
            else:
                inside_count = 0  # Reset si se rompe la serie

        result["inside_bar_series"] = inside_count >= self.INSIDE_BAR_MIN_BARS

        # ── VCP Tightness (Minervini) ─────────────────────────────────
        # El rango de cada vela es <= VCP_CONTRACTION_RATIO * el rango anterior
        ranges = recent_h - recent_l
        if len(ranges) >= 4:
            contractions = 0
            for i in range(1, min(5, len(ranges))):
                if ranges[-i] <= ranges[-(i + 1)] * self.VCP_CONTRACTION_RATIO:
                    contractions += 1
            result["vcp_tight"] = contractions >= 3  # 3+ contracciones sucesivas

        return result

    # ═══════════════════════════════════════════════════════════
    # SCORING DE SENTIMIENTO
    # ═══════════════════════════════════════════════════════════

    # Mapa de patrones → score base (-1.0 a +1.0)
    _PATTERN_SCORES = {
        # Alcistas fuertes
        "MORNING_STAR":         +1.0,
        "THREE_WHITE_SOLDIERS": +0.9,
        "BULLISH_ENGULFING":    +0.85,
        "PIERCING_LINE":        +0.7,
        "TWEEZER_BOTTOM":       +0.65,
        "HAMMER":               +0.6,
        "DRAGONFLY_DOJI":       +0.55,
        "INVERTED_HAMMER":      +0.45,
        "BULLISH_MARUBOZU":     +0.7,
        # Neutros
        "DOJI":                  0.0,
        "NONE":                  0.0,
        # Bajistas fuertes
        "EVENING_STAR":         -1.0,
        "THREE_BLACK_CROWS":    -0.9,
        "BEARISH_ENGULFING":    -0.85,
        "DARK_CLOUD_COVER":     -0.7,
        "TWEEZER_TOP":          -0.65,
        "SHOOTING_STAR":        -0.6,
        "GRAVESTONE_DOJI":      -0.55,
        "HANGING_MAN":          -0.5,
        "BEARISH_MARUBOZU":     -0.7,
    }

    def _score_sentiment(
        self,
        primary: str,
        secondary: str,
        is_inside_bar: bool,
        on_support: bool,
    ) -> tuple[str, float]:
        """
        Calcula sentimiento y score de confirmación combinando todos los factores.

        Returns:
            (sentiment_str, confirmation_score)
        """
        base_score = self._PATTERN_SCORES.get(primary, 0.0)

        # El patrón secundario aporta 20% adicional
        secondary_score = self._PATTERN_SCORES.get(secondary, 0.0)
        score = base_score + secondary_score * 0.20

        # Inside bars = coil → amplifican la señal existente
        if is_inside_bar:
            score *= 1.15

        # Patrón en zona de soporte institucional → +30% de convicción si es alcista
        if on_support and score > 0:
            score *= 1.30
        # Patrón en soporte pero bajista → señal aún más grave
        elif on_support and score < 0:
            score *= 1.10

        # Clampar al rango [-1, +1]
        score = float(np.clip(score, -1.0, 1.0))

        if score >= 0.3:
            sentiment = "BULLISH"
        elif score <= -0.3:
            sentiment = "BEARISH"
        else:
            sentiment = "NEUTRAL"

        return sentiment, round(score, 3)

    # ═══════════════════════════════════════════════════════════
    # DIAGNOSIS TEXTUAL
    # ═══════════════════════════════════════════════════════════

    def _build_diagnosis(
        self,
        v: PatternVerdict,
        current_price: float,
        put_wall: float,
        call_wall: float,
    ) -> str:
        parts = [f"Patrón: {v.primary_pattern}"]

        if v.secondary_pattern != "NONE":
            parts.append(f"(contexto: {v.secondary_pattern})")

        if v.is_inside_bar_series:
            parts.append("📦 Serie Inside Bars — Coil/Spring detectado.")
        if v.is_vcp_tight:
            parts.append("📉 VCP Tight — Compresión de volatilidad Minervini.")

        if v.detected_on_support and put_wall > 0:
            parts.append(f"✅ En Put Wall (soporte ${put_wall:.2f}) — señal amplificada.")
        if v.detected_on_resistance and call_wall > 0:
            parts.append(f"⚠️ En Call Wall (resistencia ${call_wall:.2f}).")

        emoji = "🟢" if v.sentiment == "BULLISH" else ("🔴" if v.sentiment == "BEARISH" else "⚪")
        parts.append(f"{emoji} Sentimiento: {v.sentiment} (score={v.confirmation_score:+.2f})")

        return " | ".join(parts)
