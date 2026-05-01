"""
TRADE AUTOPSY: Análisis Post-Mortem Institucional de Cada Trade
================================================================
"No es suficiente contar victorias y derrotas. Hay que saber POR QUÉ
perdimos y si la derrota era evitable." — Van Tharp, Trade Your Way
to Financial Freedom.

Este módulo implementa la Capa 1 del Sistema de Inteligencia:
análisis automatizado de MFE/MAE para clasificar errores SIN necesitar
un modelo ML entrenado (funciona desde el trade #1).

Métricas centrales (Sweeney, 1995):
  MFE: Maximum Favorable Excursion — ¿cuánto llegó a ganar el trade?
  MAE: Maximum Adverse Excursion  — ¿cuánto llegó a perder el trade?
  Entry Efficiency: PnL / MFE     — ¿capturamos el movimiento?
  Edge Ratio: MFE / |MAE|         — ¿había un edge real?

Clases de Error Heurísticas (Rule-Based, no requiere ML):
  SIN_EDGE:        Edge Ratio < 1.0 → no había oportunidad real
  ENTRADA_TARDIA:  Entry Efficiency < 0.30 → capturamos < 30% del MFE
  STOP_TIGHT:      MAE > 1.5x el stop inicial → stop demasiado ajustado
  FALSO_BREAKOUT:  Bars to MFE < 3 → pico solo duró 3 barras
  TIMING_PERFECTO: Entry Eff > 0.70 + Edge Ratio > 2.0 → excelente
"""
import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional

logger = logging.getLogger(__name__)


from backend.modules.simulation.domain.entities.simulation_models import TradeAutopsyResult


class TradeAutopsy:
    """
    Motor de Análisis Post-Mortem para Trades.

    Recibe los datos crudos del trade (precios de entrada/salida,
    serie de precios durante la vida del trade, stop inicial) y
    produce un diagnóstico detallado con clasificación heurística.

    Uso típico:
        autopsy = TradeAutopsy()
        result = autopsy.analyze(
            trade_id="BT-001",
            ticker="AAPL",
            entry_price=175.50,
            exit_price=180.00,
            initial_stop=170.00,
            price_series=[175.5, 176.2, 178.0, 182.5, 181.0, 180.0],
            exit_reason="TRAILING_STOP",
        )
        print(result.error_class)   # "TIMING_PERFECTO" o "ENTRADA_TARDIA"
        print(result.diagnosis)     # Texto explicativo
    """

    def analyze(
        self,
        trade_id: str,
        ticker: str,
        entry_price: float,
        exit_price: float,
        initial_stop: float,
        price_series: list[float],
        exit_reason: str = "",
        direction: str = "LONG",
        atr: float = 1.0,  # V7: Entry ATR
    ) -> TradeAutopsyResult:
        """
        Ejecuta la autopsia completa de un trade.

        Args:
            trade_id:      ID del trade (del Journal)
            ticker:        Símbolo de la acción
            entry_price:   Precio de entrada
            exit_price:    Precio de salida
            initial_stop:  Precio del stop loss inicial
            price_series:  Lista de precios (close) durante la vida del trade.
                           Índice 0 = barra de entrada, último = barra de salida.
            exit_reason:   Razón de salida del trade (STOP_HIT, TAKE_PROFIT, etc.)
            direction:     LONG o SHORT

        Returns:
            TradeAutopsyResult con todas las métricas y diagnóstico.
        """
        if not price_series or len(price_series) < 2:
            return TradeAutopsyResult(
                trade_id=trade_id, ticker=ticker,
                error_class="INSUFFICIENT_DATA",
                diagnosis="Trade con menos de 2 barras de datos — análisis imposible.",
            )

        prices = np.array(price_series, dtype=float)
        n_bars = len(prices)
        is_long = direction.upper() == "LONG"

        # ── 1. Calcular MFE y MAE ────────────────────────────────
        if is_long:
            mfe_price = float(np.max(prices))
            mae_price = float(np.min(prices))
            mfe_pct = (mfe_price / entry_price - 1.0) * 100
            mae_pct = (mae_price / entry_price - 1.0) * 100  # Negativo para de las longs
            bars_to_mfe = int(np.argmax(prices))
            bars_to_mae = int(np.argmin(prices))
        else:
            # SHORT: favorable es cuando baja, adverso cuando sube
            mfe_price = float(np.min(prices))
            mae_price = float(np.max(prices))
            mfe_pct = (1.0 - mfe_price / entry_price) * 100
            mae_pct = (1.0 - mae_price / entry_price) * 100  # Negativo para shorts
            bars_to_mfe = int(np.argmin(prices))
            bars_to_mae = int(np.argmax(prices))

        pnl_pct = (exit_price / entry_price - 1.0) * 100 if is_long else \
                  (1.0 - exit_price / entry_price) * 100
        was_winner = pnl_pct > 0

        # ── 2. Métricas Derivadas ─────────────────────────────────
        # Entry Efficiency: qué % del movimiento favorable capturamos
        entry_efficiency = pnl_pct / mfe_pct if mfe_pct > 0.01 else 0.0

        # Stop Efficiency: qué tan calibrado estaba el stop
        stop_distance = abs(entry_price - initial_stop) / entry_price * 100
        stop_efficiency = abs(mae_pct) / stop_distance if stop_distance > 0.01 else 0.0

        # Edge Ratio: calidad del edge (MFE / |MAE|)
        edge_ratio = mfe_pct / abs(mae_pct) if abs(mae_pct) > 0.01 else mfe_pct * 10
        
        # V7: Volatility-Normalized Edge Ratio
        # Normalizamos la distancia absoluta recorrida dividiéndola por el ATR
        mfe_abs = abs(mfe_price - entry_price)
        mae_abs = abs(mae_price - entry_price)
        mfe_atr = mfe_abs / atr if atr > 0.01 else 0.0
        mae_atr = mae_abs / atr if atr > 0.01 else 0.0
        normalized_edge_ratio = mfe_atr / mae_atr if mae_atr > 0.01 else mfe_atr * 10

        # V7: Monte Carlo Permutation Testing
        # ¿Pudimos haber obtenido este Edge Ratio entrando al azar ese mismo día?
        mc_p_value = 0.0
        if n_bars > 10 and atr > 0.01:
            random_edges = []
            for _ in range(1000): # 1000 iteraciones como pide la ciencia de datos
                # Pick a random entry point in the series
                rand_idx = np.random.randint(0, n_bars - 2)
                rand_entry = prices[rand_idx]
                rand_future = prices[rand_idx:]
                if len(rand_future) < 2: continue
                
                if is_long:
                    r_mfe_abs = float(np.max(rand_future)) - rand_entry
                    r_mae_abs = rand_entry - float(np.min(rand_future))
                else:
                    r_mfe_abs = rand_entry - float(np.min(rand_future))
                    r_mae_abs = float(np.max(rand_future)) - rand_entry
                    
                r_mfe_atr = r_mfe_abs / atr
                r_mae_atr = r_mae_abs / atr
                r_edge = r_mfe_atr / r_mae_atr if r_mae_atr > 0.01 else r_mfe_atr * 10
                random_edges.append(r_edge)
                
            if random_edges:
                # El p-value es la probabilidad de que una entrada ALEATORIA 
                # tuviera un Edge Ratio MEJOR que nuestra entrada algorítmica.
                # Si p > 0.05, el trade fue pura suerte (Beta).
                mc_p_value = sum(1 for e in random_edges if e > normalized_edge_ratio) / len(random_edges)

        # MFE Timing: ¿el pico fue temprano o tardío?
        mfe_timing = bars_to_mfe / n_bars if n_bars > 0 else 0.0

        # ── 3. Clasificación Heurística del Error ─────────────────
        error_class, diagnosis, lesson = self._classify_error(
            was_winner=was_winner,
            entry_efficiency=entry_efficiency,
            stop_efficiency=stop_efficiency,
            edge_ratio=edge_ratio,
            mfe_timing=mfe_timing,
            mfe_pct=mfe_pct,
            mae_pct=mae_pct,
            pnl_pct=pnl_pct,
            bars_to_mfe=bars_to_mfe,
            n_bars=n_bars,
            exit_reason=exit_reason,
        )

        return TradeAutopsyResult(
            trade_id=trade_id,
            ticker=ticker,
            mfe_pct=round(mfe_pct, 3),
            mae_pct=round(mae_pct, 3),
            mfe_price=mfe_price,
            mae_price=mae_price,
            bars_to_mfe=bars_to_mfe,
            bars_to_mae=bars_to_mae,
            total_bars=n_bars,
            entry_efficiency=round(entry_efficiency, 3),
            stop_efficiency=round(stop_efficiency, 3),
            edge_ratio=round(edge_ratio, 3),
            normalized_edge_ratio=round(normalized_edge_ratio, 3),
            mc_p_value=round(mc_p_value, 4),
            mfe_timing=round(mfe_timing, 3),
            error_class=error_class,
            diagnosis=diagnosis,
            actionable_lesson=lesson,
            pnl_pct=round(pnl_pct, 3),
            was_winner=was_winner,
            exit_reason=exit_reason,
        )

    def _classify_error(
        self,
        was_winner: bool,
        entry_efficiency: float,
        stop_efficiency: float,
        edge_ratio: float,
        mfe_timing: float,
        mfe_pct: float,
        mae_pct: float,
        pnl_pct: float,
        bars_to_mfe: int,
        n_bars: int,
        exit_reason: str,
    ) -> tuple[str, str, str]:
        """
        Clasifica el trade en una categoría de error usando reglas heurísticas.

        Orden de prioridad (el primer match gana):
        1. Sin edge real
        2. Falso breakout
        3. Stop demasiado tight (root cause más específico)
        4. Entrada tardía
        5. Timing perfecto (acierto)
        6. Victoria normal
        7. Derrota normal
        """
        # ── WINNERS ───────────────────────────────────────────────
        if was_winner:
            if entry_efficiency >= 0.70 and edge_ratio >= 2.0:
                return (
                    "TIMING_PERFECTO",
                    f"Excelente ejecución. Capturamos {entry_efficiency*100:.0f}% del MFE "
                    f"({mfe_pct:.1f}%) con edge ratio {edge_ratio:.1f}x.",
                    "Replicar las condiciones de entrada de este trade.",
                )
            if entry_efficiency >= 0.50:
                return (
                    "BUENA_EJECUCION",
                    f"Sólida ejecución. Entry Efficiency {entry_efficiency*100:.0f}%. "
                    f"MFE fue {mfe_pct:.1f}%, capturamos {pnl_pct:.1f}%.",
                    "Considerar trailing stop más agresivo para capturar más MFE.",
                )
            # Winner pero con baja entry_efficiency → dejamos mucho en la mesa
            return (
                "GANANCIA_DESPERDICIADA",
                f"Ganamos {pnl_pct:.1f}% pero el MFE fue {mfe_pct:.1f}% "
                f"(capturamos solo {entry_efficiency*100:.0f}%). "
                f"El pico favorable fue en la barra {bars_to_mfe} de {n_bars}.",
                "El trailing stop se activó demasiado temprano, o la salida fue prematura. "
                "Evaluar ajustar trailing multiplier.",
            )

        # ── LOSERS ────────────────────────────────────────────────

        # Sin edge real: el movimiento adverso fue mayor que el favorable
        if edge_ratio < 1.0:
            return (
                "SIN_EDGE",
                f"No había edge real en este trade. El MFE ({mfe_pct:.1f}%) "
                f"nunca superó al MAE ({mae_pct:.1f}%). Edge ratio: {edge_ratio:.2f}x. "
                f"El precio nunca se movió suficientemente a nuestro favor.",
                "Revisar la tesis de entrada. El scanner identificó una oportunidad "
                "que realmente no existía. Verificar si el sector estaba en distribución.",
            )

        # Falso breakout: pico favorable muy temprano y luego crash
        if bars_to_mfe < 3 and n_bars > 5 and mfe_pct > 0.5:
            return (
                "FALSO_BREAKOUT",
                f"Falso breakout. El precio subió {mfe_pct:.1f}% en solo "
                f"{bars_to_mfe} barras pero luego revertió completamente. "
                f"El trade duró {n_bars} barras total.",
                "Esta es una trampa de liquidez. El volumen inicial puede haber "
                "sido de corto interés (short squeeze) y no institucional. "
                "Validar con Kalman velocity: si la aceleración era negativa al entrar, evitar.",
            )

        # Stop demasiado ajustado: el MAE superó ampliamente el stop
        # (checked BEFORE entrada_tardia because tight stop is the root cause
        #  when the trade would have recovered had the stop been wider)
        if stop_efficiency > 1.5:
            return (
                "STOP_TIGHT",
                f"El stop loss estaba demasiado ajustado. El MAE ({mae_pct:.1f}%) "
                f"fue {stop_efficiency:.1f}x el stop distance. "
                f"Nos sacaron del trade prematuramente antes de la recuperación.",
                "Aumentar el multiplicador ATR del stop (de 2.0 a 2.5 o 3.0) "
                "para este régimen de volatilidad. Verificar si VIX estaba "
                "por encima de 25 al momento del trade.",
            )

        # Entrada tardía: capturamos poquísimo del movimiento disponible
        if entry_efficiency < 0.30 and mfe_pct > 1.0:
            return (
                "ENTRADA_TARDIA",
                f"Entramos demasiado tarde. MFE fue {mfe_pct:.1f}% pero capturamos "
                f"solo {entry_efficiency*100:.0f}% de ese recorrido. "
                f"El pico fue en barra {bars_to_mfe} de {n_bars}.",
                "El bus ya había salido cuando compramos. Revisar la señal de "
                "KalmanVolumeTracker: si vel_rvol ya era negativa al entrar, "
                "el sector estaba pasando de MARKUP a DISTRIBUCIÓN.",
            )

        # Derrota genérica
        return (
            "DERROTA_GENERAL",
            f"Trade perdedor sin patrón de error claro. "
            f"PnL: {pnl_pct:.1f}%, MFE: {mfe_pct:.1f}%, MAE: {mae_pct:.1f}%, "
            f"Edge Ratio: {edge_ratio:.1f}x.",
            "Analizar el SHAP agregado cuando haya suficientes trades "
            "para encontrar patrones sistémicos.",
        )

    def analyze_batch(self, trades: list[dict]) -> pd.DataFrame:
        """
        Ejecuta la autopsia sobre un lote de trades cerrados.

        Args:
            trades: Lista de dicts con claves trade_id, ticker,
                    entry_price, exit_price, initial_stop, price_series,
                    exit_reason, direction.

        Returns:
            DataFrame con métricas de todos los trades analizados.
        """
        results = []
        for t in trades:
            result = self.analyze(
                trade_id=t['trade_id'],
                ticker=t['ticker'],
                entry_price=t['entry_price'],
                exit_price=t['exit_price'],
                initial_stop=t.get('initial_stop', t['entry_price'] * 0.95),
                price_series=t.get('price_series', [t['entry_price'], t['exit_price']]),
                exit_reason=t.get('exit_reason', ''),
                direction=t.get('direction', 'LONG'),
            )
            results.append(result.to_dict())

        df = pd.DataFrame(results)

        if not df.empty:
            # Estadísticas agregadas de error
            error_counts = df['error_class'].value_counts()
            logger.info(f"📊 Autopsia de {len(df)} trades:")
            for cls, count in error_counts.items():
                pct = count / len(df) * 100
                logger.info(f"   {cls}: {count} ({pct:.0f}%)")

            # Promedios de eficiencia
            avg_eff = df['entry_efficiency'].mean()
            avg_edge = df['edge_ratio'].mean()
            logger.info(f"   Avg Entry Efficiency: {avg_eff:.2f}")
            logger.info(f"   Avg Edge Ratio: {avg_edge:.2f}")

        return df

    def get_systemic_weakness(self, autopsy_df: pd.DataFrame) -> dict:
        """
        Analiza el DataFrame de autopsias para encontrar debilidades
        sistémicas del trading system (Capa 2 - SHAP Agregado simplificado).

        Args:
            autopsy_df: DataFrame producido por analyze_batch().

        Returns:
            Dict con debilidades identificadas y recomendaciones.
        """
        if autopsy_df.empty or len(autopsy_df) < 5:
            return {"message": "Insuficientes trades para análisis sistémico (mínimo 5)."}

        losers = autopsy_df[~autopsy_df['was_winner']]
        if losers.empty:
            return {"message": "No hay trades perdedores para analizar."}

        error_dist = losers['error_class'].value_counts(normalize=True)
        dominant_error = error_dist.index[0]
        dominant_pct = error_dist.iloc[0] * 100

        # Métricas promedio de los perdedores
        avg_entry_eff = losers['entry_efficiency'].mean()
        avg_edge = losers['edge_ratio'].mean()
        avg_stop_eff = losers['stop_efficiency'].mean()

        weaknesses = []

        if dominant_pct > 40:
            weaknesses.append({
                "type": dominant_error,
                "prevalence_pct": round(dominant_pct, 1),
                "recommendation": losers[losers['error_class'] == dominant_error]['actionable_lesson'].iloc[0],
            })

        if avg_entry_eff < 0.25:
            weaknesses.append({
                "type": "SYSTEMIC_LATE_ENTRY",
                "prevalence_pct": round((losers['entry_efficiency'] < 0.30).mean() * 100, 1),
                "recommendation": "El sistema entra consistentemente tarde. "
                                  "Considerar adelantar el trigger o usar la señal Kalman ACCUMULATION.",
            })

        if avg_stop_eff > 1.3:
            weaknesses.append({
                "type": "SYSTEMIC_TIGHT_STOPS",
                "prevalence_pct": round((losers['stop_efficiency'] > 1.5).mean() * 100, 1),
                "recommendation": "Los stops están sistemáticamente demasiado ajustados para "
                                  "la volatilidad del mercado. Incrementar ATR multiplier 20-30%.",
            })

        return {
            "total_trades": len(autopsy_df),
            "total_losers": len(losers),
            "dominant_error": dominant_error,
            "dominant_pct": round(dominant_pct, 1),
            "avg_loser_entry_efficiency": round(avg_entry_eff, 3),
            "avg_loser_edge_ratio": round(avg_edge, 3),
            "avg_loser_stop_efficiency": round(avg_stop_eff, 3),
            "weaknesses": weaknesses,
        }
