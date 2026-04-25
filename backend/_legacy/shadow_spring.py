"""
SHADOW SPRING SCANNER
=====================
Motor de señales en tiempo real basado en la estrategia
Mean-Reversion Spring validada en Walk-Forward.

Aprobados en backtest (post-costos, métricas honestas):
  XLE: Sharpe 1.59, WR 73%, +14.3%
  USO: Sharpe 1.08, WR 63%, +18.5%
  EFA: Sharpe 0.83, WR 67%, +9.4%

Señal de entrada (SPRING):
  1. Oversold: ret_5d < -2%
  2. Volume Quality > 1.0 (Amihud + Price Confirm + RVol)
  3. RVol > 1.2
  4. Kalman NOT in DISTRIBUTION/MARKDOWN

Señal de salida:
  1. MA20 reversion (primary target)
  2. Stop ATR × 2 (protection)
  3. Distribution exit (Kalman detects selling)
  4. Max bars timeout
"""
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from pymongo import ASCENDING, DESCENDING

from infrastructure.data_providers.volume_dynamics import (
    KalmanVolumeTracker,
)
from application.backtester import WalkForwardBacktester
from application.trade_journal import _get_mongo_db

logger = logging.getLogger(__name__)


@dataclass
class SpringSignal:
    """Señal generada por el scanner."""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    ticker: str = ""
    signal_type: str = ""  # ENTRY, EXIT, HOLD, NO_SIGNAL

    # Métricas de entrada
    price: float = 0.0
    ret_5d: float = 0.0
    rvol: float = 0.0
    volume_quality: float = 0.0
    wyckoff_state: str = ""
    kalman_velocity: float = 0.0
    rs_vs_spy: float = 0.0
    ma20: float = 0.0

    # Para exits
    exit_reason: str = ""
    stop_price: float = 0.0
    target_price: float = 0.0

    # Trade context
    entry_price: float = 0.0
    bars_held: int = 0
    unrealized_pnl_pct: float = 0.0

    # Metadata
    confidence: str = ""  # HIGH, MEDIUM, LOW
    notes: str = ""


@dataclass
class ShadowPosition:
    """Posición virtual en Shadow Mode (sin dinero real)."""
    ticker: str = ""
    entry_price: float = 0.0
    entry_date: str = ""
    stop_price: float = 0.0
    ma20_target: float = 0.0
    entry_rs: float = 0.0
    entry_rvol: float = 0.0
    entry_wyckoff: str = ""
    entry_volume_quality: float = 0.0
    bars_held: int = 0
    highest_price: float = 0.0
    status: str = "OPEN"  # OPEN, CLOSED
    exit_price: float = 0.0
    exit_date: str = ""
    exit_reason: str = ""
    pnl_pct: float = 0.0


class ShadowSpringScanner:
    """
    Scanner en tiempo real para la estrategia Mean-Reversion Spring.

    Funciona en modo "shadow" — genera señales y las registra,
    pero NO ejecuta trades reales. Permite comparar las señales
    con la ejecución del paper trading para validación.
    """

    # Tickers aprobados en Walk-Forward con edge real
    APPROVED_TICKERS = ['XLE', 'USO', 'EFA']

    # Parámetros de la estrategia (de backtest)
    OVERSOLD_THRESHOLD = -0.02     # ret_5d < -2%
    RVOL_THRESHOLD = 1.2           # Relative Volume > 1.2
    VOLUME_QUALITY_MIN = 1.0       # VQ Score mínimo
    MAX_BARS = 30                  # Timeout en días
    STOP_ATR_MULT = 2.0            # Stop = ATR × 2

    def __init__(self, tickers: list[str] = None):
        self.tickers = tickers or self.APPROVED_TICKERS
        self.kalman_trackers: dict[str, KalmanVolumeTracker] = {}
        self.positions: dict[str, ShadowPosition] = {}
        self.bt = WalkForwardBacktester()  # Para reusar volume_quality_score

        # Inicializar DB
        self._init_db()

        # Inicializar Kalman para cada ticker con warmup
        for ticker in self.tickers:
            self.kalman_trackers[ticker] = KalmanVolumeTracker(
                dt=1.0, process_noise=0.05, obs_noise=0.2,
            )

    def _init_db(self):
        """Inicializar colecciones MongoDB para Shadow Mode."""
        self._db = _get_mongo_db()
        self._signals_col = self._db["shadow_signals"]
        self._positions_col = self._db["shadow_positions"]

        # Índices para queries frecuentes
        self._signals_col.create_index(
            [("ticker", ASCENDING), ("timestamp", DESCENDING)]
        )
        self._positions_col.create_index(
            [("ticker", ASCENDING), ("status", ASCENDING)]
        )
        logger.info(f"Shadow DB MongoDB inicializada: {self._db.name}")

    def _save_signal(self, signal: SpringSignal):
        """Persiste una señal en MongoDB."""
        doc = asdict(signal)
        self._signals_col.insert_one(doc)

    def _save_position(self, pos: ShadowPosition):
        """Persiste o actualiza una posición en MongoDB (upsert)."""
        doc = asdict(pos)
        self._positions_col.update_one(
            {"ticker": pos.ticker, "status": "OPEN"},
            {"$set": doc},
            upsert=True,
        )

    def warmup_kalman(self, ticker: str, days: int = 60) -> dict:
        """
        Calienta el Kalman con datos históricos recientes.
        Debe ejecutarse UNA VEZ al inicio del scanner.
        """
        try:
            data = yf.download(ticker, period=f'{days}d', interval='1d', progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            if len(data) < 30:
                return {"status": "INSUFFICIENT_DATA", "bars": len(data)}

            volumes = data['Volume'].values
            closes = data['Close'].values

            kalman = self.kalman_trackers[ticker]
            for i in range(20, len(volumes)):
                avg_v = np.mean(volumes[max(0, i - 20):i])
                rvol = volumes[i] / max(avg_v, 1.0)
                chg = (closes[i] / closes[i - 1] - 1) * 100 if i > 0 else 0.0
                kalman.update(ticker, rvol, change_pct=chg)

            logger.info(f"Kalman warmup: {ticker} con {len(data)} barras")
            return {"status": "WARMED_UP", "bars": len(data)}

        except Exception as e:
            logger.error(f"Kalman warmup failed for {ticker}: {e}")
            return {"status": "ERROR", "error": str(e)}

    def scan_ticker(self, ticker: str) -> SpringSignal:
        """
        Evalúa un ticker para señal de Spring en TIEMPO REAL.

        Returns:
            SpringSignal con el tipo de señal y métricas.
        """
        signal = SpringSignal(ticker=ticker)

        try:
            # Descargar datos recientes
            data = yf.download(ticker, period='3mo', interval='1d', progress=False)
            spy_data = yf.download('SPY', period='3mo', interval='1d', progress=False)

            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            if isinstance(spy_data.columns, pd.MultiIndex):
                spy_data.columns = spy_data.columns.get_level_values(0)

            if len(data) < 25 or len(spy_data) < 25:
                signal.signal_type = "NO_SIGNAL"
                signal.notes = "Datos insuficientes"
                return signal

            # Últimas barras
            close = float(data['Close'].iloc[-1])
            prev_close = float(data['Close'].iloc[-2])
            high = float(data['High'].iloc[-1])
            low = float(data['Low'].iloc[-1])
            volume = float(data['Volume'].iloc[-1])
            avg_vol = float(data['Volume'].rolling(20).mean().iloc[-1])

            # Métricas
            signal.price = close
            signal.ma20 = float(data['Close'].rolling(20).mean().iloc[-1])

            # 1. RET 5D — ¿estamos oversold?
            close_5d_ago = float(data['Close'].iloc[-6]) if len(data) >= 6 else close
            ret_5d = close / close_5d_ago - 1
            signal.ret_5d = round(ret_5d * 100, 2)

            # 2. RVOL
            rvol = volume / max(avg_vol, 1.0)
            signal.rvol = round(rvol, 2)

            # 3. VOLUME QUALITY SCORE
            vq = self.bt.volume_quality_score(
                close=close, high=high, low=low,
                volume=volume, avg_volume=avg_vol,
                prev_close=prev_close,
            )
            signal.volume_quality = round(vq, 2)

            # 4. KALMAN
            kalman = self.kalman_trackers.get(ticker)
            if kalman is None:
                kalman = KalmanVolumeTracker(dt=1.0, process_noise=0.05, obs_noise=0.2)
                self.kalman_trackers[ticker] = kalman

            price_chg = (close / prev_close - 1) * 100
            kalman_result = kalman.update(ticker, rvol, change_pct=price_chg)
            signal.wyckoff_state = kalman_result['wyckoff_state']
            signal.kalman_velocity = round(kalman_result['velocity'], 4)

            # 5. RS vs SPY
            spy_close = float(spy_data['Close'].iloc[-1])
            spy_20d = float(spy_data['Close'].iloc[-21]) if len(spy_data) >= 21 else spy_close
            stock_20d = float(data['Close'].iloc[-21]) if len(data) >= 21 else close
            stock_ret = close / stock_20d - 1
            spy_ret = spy_close / spy_20d - 1
            signal.rs_vs_spy = round((1 + stock_ret) / (1 + spy_ret), 4) if spy_ret != -1 else 1.0

            # ── ¿Tenemos posición abierta? ──
            if ticker in self.positions and self.positions[ticker].status == "OPEN":
                return self._evaluate_exit(ticker, signal, data)

            # ── EVALUACIÓN DE ENTRADA ──
            # Condición 1: Oversold
            if ret_5d >= self.OVERSOLD_THRESHOLD:
                signal.signal_type = "NO_SIGNAL"
                signal.notes = f"No oversold (5d: {ret_5d*100:+.1f}% >= {self.OVERSOLD_THRESHOLD*100:.0f}%)"
                self._save_signal(signal)
                return signal

            # Condición 2: Volume surge
            if rvol < self.RVOL_THRESHOLD:
                signal.signal_type = "NO_SIGNAL"
                signal.notes = f"Volumen bajo (RVol: {rvol:.2f} < {self.RVOL_THRESHOLD})"
                self._save_signal(signal)
                return signal

            # Condición 3: Volume Quality (filtro HFT)
            if vq < self.VOLUME_QUALITY_MIN:
                signal.signal_type = "NO_SIGNAL"
                signal.notes = f"Volumen ficticio HFT (VQ: {vq:.1f} < {self.VOLUME_QUALITY_MIN})"
                self._save_signal(signal)
                return signal

            # Condición 4: No en distribution/markdown
            if signal.wyckoff_state in ('DISTRIBUTION', 'MARKDOWN'):
                signal.signal_type = "NO_SIGNAL"
                signal.notes = f"Kalman en {signal.wyckoff_state} — caída libre, no spring"
                self._save_signal(signal)
                return signal

            # ═══ SPRING CONFIRMADO ═══
            signal.signal_type = "ENTRY"

            # Calcular stop y target
            atr_vals = (data['High'] - data['Low']).rolling(20).mean()
            atr = float(atr_vals.iloc[-1]) if not atr_vals.empty else close * 0.02
            stop = close * (1 - (atr * self.STOP_ATR_MULT) / close)
            signal.stop_price = round(stop, 2)
            signal.target_price = round(signal.ma20, 2)

            # Confidence
            confidence_score = 0
            if ret_5d < -0.03:
                confidence_score += 1
            if vq >= 2.0:
                confidence_score += 1
            if rvol > 1.5:
                confidence_score += 1
            if signal.wyckoff_state == 'ACCUMULATION':
                confidence_score += 1
            signal.confidence = (
                "HIGH" if confidence_score >= 3
                else "MEDIUM" if confidence_score >= 2
                else "LOW"
            )

            signal.notes = (
                f"SPRING {signal.confidence}: "
                f"5d={ret_5d*100:.1f}% | "
                f"RVol={rvol:.2f} | "
                f"VQ={vq:.1f} | "
                f"Wyckoff={signal.wyckoff_state} | "
                f"Target=MA20@{signal.ma20:.2f} | "
                f"Stop={stop:.2f}"
            )

            # Crear posición shadow
            pos = ShadowPosition(
                ticker=ticker,
                entry_price=close,
                entry_date=datetime.now(UTC).isoformat(),
                stop_price=stop,
                ma20_target=signal.ma20,
                entry_rs=signal.rs_vs_spy,
                entry_rvol=rvol,
                entry_wyckoff=signal.wyckoff_state,
                entry_volume_quality=vq,
                highest_price=close,
            )
            self.positions[ticker] = pos
            self._save_position(pos)

            logger.info(f"🔵 SPRING ENTRY: {ticker} @ {close:.2f} | {signal.notes}")

        except Exception as e:
            signal.signal_type = "ERROR"
            signal.notes = str(e)
            logger.error(f"Error scanning {ticker}: {e}")

        self._save_signal(signal)
        return signal

    def _evaluate_exit(self, ticker: str, signal: SpringSignal, data: pd.DataFrame) -> SpringSignal:
        """Evalúa si una posición abierta debe cerrarse."""
        pos = self.positions[ticker]
        pos.bars_held += 1
        close = signal.price

        # Update highest
        pos.highest_price = max(pos.highest_price, close)
        pnl = (close / pos.entry_price - 1) * 100
        signal.entry_price = pos.entry_price
        signal.bars_held = pos.bars_held
        signal.unrealized_pnl_pct = round(pnl, 2)
        signal.stop_price = pos.stop_price
        signal.target_price = pos.ma20_target

        exit_reason = None

        # Exit 1: MA20 Reversion (target alcanzado)
        if close >= signal.ma20 and pos.bars_held >= 2:
            exit_reason = "MA20_REVERSION"

        # Exit 2: Stop hit
        elif close <= pos.stop_price:
            exit_reason = "STOP_HIT"

        # Exit 3: Distribution detected
        elif signal.wyckoff_state in ('DISTRIBUTION', 'MARKDOWN'):
            exit_reason = "DISTRIBUTION"

        # Exit 4: Timeout
        elif pos.bars_held >= self.MAX_BARS:
            exit_reason = "TIMEOUT"

        if exit_reason:
            signal.signal_type = "EXIT"
            signal.exit_reason = exit_reason

            # Aplicar costos
            cost = self.bt.ROUND_TRIP_COST_PCT
            net_pnl = pnl - cost

            pos.status = "CLOSED"
            pos.exit_price = close
            pos.exit_date = datetime.now(UTC).isoformat()
            pos.exit_reason = exit_reason
            pos.pnl_pct = round(net_pnl, 3)

            self._save_position(pos)
            del self.positions[ticker]

            emoji = "🟢" if net_pnl > 0 else "🔴"
            logger.info(
                f"{emoji} SPRING EXIT: {ticker} | {exit_reason} | "
                f"PnL: {net_pnl:+.2f}% | Bars: {pos.bars_held}d"
            )
            signal.notes = (
                f"EXIT {exit_reason}: PnL={net_pnl:+.2f}% after {pos.bars_held}d | "
                f"Entry={pos.entry_price:.2f} → Exit={close:.2f}"
            )
        else:
            signal.signal_type = "HOLD"
            signal.notes = (
                f"HOLDING: PnL={pnl:+.2f}% | Day {pos.bars_held}/{self.MAX_BARS} | "
                f"Stop={pos.stop_price:.2f} | Target MA20={signal.ma20:.2f}"
            )

        self._save_signal(signal)
        return signal

    def scan_all(self) -> list[SpringSignal]:
        """Escanea todos los tickers aprobados y retorna señales."""
        signals = []
        for ticker in self.tickers:
            signal = self.scan_ticker(ticker)
            signals.append(signal)
        return signals

    def warmup_all(self) -> dict:
        """Warmup de Kalman para todos los tickers."""
        results = {}
        for ticker in self.tickers:
            results[ticker] = self.warmup_kalman(ticker)
        return results

    def get_performance_summary(self) -> dict:
        """Resumen de performance de todas las señales shadow."""
        trades = list(self._positions_col.find(
            {"status": "CLOSED"}, {"_id": 0}
        ))

        if not trades:
            return {"total_trades": 0, "message": "No hay trades cerrados aún"}

        pnls = [t['pnl_pct'] for t in trades]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]

        return {
            "total_trades": len(trades),
            "winners": len(winners),
            "losers": len(losers),
            "win_rate": round(len(winners) / len(trades) * 100, 1),
            "avg_pnl": round(np.mean(pnls), 3),
            "total_return": round(sum(pnls), 2),
            "best_trade": round(max(pnls), 2) if pnls else 0,
            "worst_trade": round(min(pnls), 2) if pnls else 0,
            "avg_bars": round(np.mean([t['bars_held'] for t in trades]), 1),
            "by_ticker": {
                ticker: {
                    "trades": len([t for t in trades if t['ticker'] == ticker]),
                    "pnl": round(sum(t['pnl_pct'] for t in trades if t['ticker'] == ticker), 2),
                }
                for ticker in set(t['ticker'] for t in trades)
            },
        }

    def get_open_positions(self) -> list[dict]:
        """Retorna posiciones shadow abiertas."""
        return list(self._positions_col.find(
            {"status": "OPEN"}, {"_id": 0}
        ))
