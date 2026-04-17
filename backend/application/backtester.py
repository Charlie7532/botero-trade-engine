"""
WALK-FORWARD BACKTESTER: Motor de Validación Institucional
===========================================================
Implementa el estándar institucional para validar estrategias de trading
ANTES de arriesgar capital (ni siquiera papel).

Principio fundamental:
  "Un modelo que nunca ha visto datos futuros no puede hacer trampa."

Walk-Forward evita el Look-Ahead Bias dividiendo la historia en ventanas
deslizantes de entrenamiento/test. Cada ventana de test simula
"el futuro" porque el modelo nunca la ha visto.

Secuencia:
  ├── Train 1 ──┤ Test 1 │
  │    ├── Train 2 ──────┤ Test 2 │
  │    │    ├── Train 3 ──────────┤ Test 3 │
                                           ↑ HOY

Métricas de paso (gating):
  - Sharpe Ratio Walk-Forward promedio ≥ 0.8
  - Max Drawdown ≤ -20%
  - Win Rate ≥ 45%
  - Profit Factor ≥ 1.3

Si NO pasan, el sistema NO avanza a Shadow Mode.

Dependencias:
  - data/historical/market_context_5y.parquet  (descargado por download_historical.py)
  - backend/application/sequence_modeling.py    (TripleBarrierLabeler, MetaLabeler)
  - backend/application/feature_engineering.py  (QuantFeatureEngineer)
  - backend/application/trade_autopsy.py        (TradeAutopsy para post-mortem)
"""
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional

from backend.application.sequence_modeling import TripleBarrierLabeler
from backend.application.trade_autopsy import TradeAutopsy

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "historical"
MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "models"


@dataclass
class WindowResult:
    """Resultado de una ventana individual de Walk-Forward."""
    window_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str

    # Métricas de la ventana de TEST
    n_trades: int = 0
    n_winners: int = 0
    n_losers: int = 0
    win_rate: float = 0.0

    total_pnl_pct: float = 0.0
    avg_pnl_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float = 0.0
    calmar_ratio: float = 0.0       # Rendimiento anualizado / Max Drawdown

    # Distribución de errores (del TradeAutopsy)
    error_distribution: dict = field(default_factory=dict)
    avg_entry_efficiency: float = 0.0
    avg_edge_ratio: float = 0.0

    # Meta
    model_auc: float = 0.0         # AUC del modelo meta-labeler en esta ventana
    regime: str = ""                # Bull, Bear, Sideways (clasificación del período)


@dataclass
class BacktestReport:
    """Reporte consolidado del Walk-Forward completo."""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    total_windows: int = 0
    windows: list = field(default_factory=list)

    # Métricas agregadas (promedio de todas las ventanas)
    avg_sharpe: float = 0.0
    avg_win_rate: float = 0.0
    avg_profit_factor: float = 0.0
    worst_drawdown: float = 0.0
    total_return_pct: float = 0.0

    # Gating
    passes_sharpe: bool = False
    passes_drawdown: bool = False
    passes_win_rate: bool = False
    passes_profit_factor: bool = False
    approved_for_shadow: bool = False

    # Debilidades sistémicas
    systemic_weaknesses: list = field(default_factory=list)


class WalkForwardBacktester:
    """
    Motor Walk-Forward para validación de estrategias.

    Flujo:
    1. Carga datos históricos de Parquet
    2. Genera ventanas deslizantes (rolling windows)
    3. Para cada ventana:
       a. Aplica TripleBarrierLabeler en la ventana de TRAIN
       b. Genera features con QuantFeatureEngineer
       c. (Opcional) Entrena meta-labeler en la ventana de TRAIN
       d. Simula trades en la ventana de TEST con el modelo/reglas
       e. Ejecuta TradeAutopsy sobre cada trade simulado
       f. Calcula métricas (Sharpe, DD, Profit Factor)
    4. Agrega métricas y emite veredicto de gating
    """

    # Criterios para aprobar y pasar a Shadow Mode
    GATING_CRITERIA = {
        'min_sharpe': 0.8,
        'max_drawdown': -20.0,
        'min_win_rate': 45.0,
        'min_profit_factor': 1.3,
    }

    def __init__(
        self,
        train_months: int = 24,
        test_months: int = 6,
        step_months: int = 6,
        parquet_file: str = "market_context_5y.parquet",
    ):
        """
        Args:
            train_months: Meses de datos para entrenar en cada ventana.
            test_months:  Meses de datos de test (out-of-sample) en cada ventana.
            step_months:  Cuántos meses avanzar entre ventanas consecutivas.
            parquet_file: Nombre del archivo Parquet con datos históricos.
        """
        self.train_months = train_months
        self.test_months = test_months
        self.step_months = step_months
        self.parquet_path = DATA_DIR / parquet_file
        self.labeler = TripleBarrierLabeler(
            profit_mult=2.0, loss_mult=1.0, max_bars=30, vol_lookback=20
        )
        self.autopsy = TradeAutopsy()

    def load_data(self, ticker: str = None) -> pd.DataFrame:
        """
        Carga datos históricos del Parquet.

        Args:
            ticker: Si se especifica, filtra solo un ticker.
                    Si None, retorna todos los ETFs.

        Returns:
            DataFrame con columnas Date, Ticker, Open, High, Low, Close, Volume.
        """
        if not self.parquet_path.exists():
            raise FileNotFoundError(
                f"Parquet no encontrado: {self.parquet_path}. "
                f"Ejecuta primero: python scripts/download_historical.py"
            )

        df = pd.read_parquet(self.parquet_path)
        df['Date'] = pd.to_datetime(df['Date'])

        if ticker:
            df = df[df['Ticker'] == ticker].copy()
            if df.empty:
                raise ValueError(f"Ticker '{ticker}' no encontrado en el Parquet.")

        df = df.sort_values('Date').reset_index(drop=True)
        logger.info(
            f"Datos cargados: {len(df):,} filas | "
            f"Tickers: {df['Ticker'].nunique()} | "
            f"Rango: {df['Date'].min().date()} — {df['Date'].max().date()}"
        )
        return df

    def generate_windows(self, df: pd.DataFrame) -> list[dict]:
        """
        Genera las ventanas deslizantes de Train/Test.

        Args:
            df: DataFrame con columna Date.

        Returns:
            Lista de dicts con train_start, train_end, test_start, test_end.
        """
        dates = df['Date'].sort_values().unique()
        min_date = pd.Timestamp(dates.min())
        max_date = pd.Timestamp(dates.max())

        windows = []
        train_start = min_date
        window_id = 0

        while True:
            train_end = train_start + pd.DateOffset(months=self.train_months)
            test_start = train_end
            test_end = test_start + pd.DateOffset(months=self.test_months)

            if test_end > max_date:
                break

            windows.append({
                'window_id': window_id,
                'train_start': train_start,
                'train_end': train_end,
                'test_start': test_start,
                'test_end': test_end,
            })

            train_start += pd.DateOffset(months=self.step_months)
            window_id += 1

        logger.info(
            f"Generadas {len(windows)} ventanas Walk-Forward "
            f"(Train={self.train_months}m, Test={self.test_months}m, Step={self.step_months}m)"
        )
        return windows

    def calibrate_adaptive_params(
        self,
        train_data: pd.DataFrame,
    ) -> dict:
        """
        Calibra parámetros adaptativos usando la ventana de TRAIN.

        El motor aprende el comportamiento histórico del ticker:
        - Su volatilidad típica (para calibrar entry z-score y stops)
        - Su ATR promedio (para stops/targets dinámicos)
        - Su ratio de distribución de retornos (para entry threshold)
        - El régimen del período (para filtrar entradas en bear markets)

        Args:
            train_data: DataFrame con Date, Close, Volume de la ventana train.

        Returns:
            Dict con parámetros calibrados al ticker/período.
        """
        closes = train_data['Close'].values
        volumes = train_data['Volume'].values if 'Volume' in train_data else np.ones(len(closes))

        # ── Volatilidad histórica del ticker ──────────────────────
        returns = np.diff(closes) / closes[:-1]
        daily_vol = np.std(returns) if len(returns) > 1 else 0.01

        # EWMA volatility (más reactiva a cambios recientes)
        ewma_vol = float(pd.Series(returns).ewm(span=20).std().iloc[-1]) if len(returns) > 20 else daily_vol

        # ── ATR (Average True Range) ──────────────────────────────
        highs = train_data['High'].values if 'High' in train_data else closes * 1.005
        lows = train_data['Low'].values if 'Low' in train_data else closes * 0.995
        true_ranges = []
        for k in range(1, len(closes)):
            tr = max(
                highs[k] - lows[k],
                abs(highs[k] - closes[k-1]),
                abs(lows[k] - closes[k-1]),
            )
            true_ranges.append(tr)
        atr = np.mean(true_ranges[-20:]) if len(true_ranges) >= 20 else np.mean(true_ranges) if true_ranges else closes[-1] * 0.01
        atr_pct = atr / closes[-1] * 100  # ATR como % del precio

        # ── Entry threshold adaptativo (Z-Score) ──────────────────
        # En vez de un umbral fijo de 2%, usamos 1.5 desviaciones estándar
        # del PROPIO ticker. Un ticker volátil (TSLA, 3% std) necesita
        # un threshold más alto que uno estable (KO, 0.8% std).
        entry_z_multiplier = 1.5
        entry_threshold = daily_vol * entry_z_multiplier

        # ── Stop adaptativo (ATR-based) ───────────────────────────
        # Stop = 2.0 * ATR (se adapta a la volatilidad actual)
        stop_atr_mult = 2.0
        stop_pct = (atr_pct * stop_atr_mult) / 100

        # ── Target adaptativo (Risk:Reward basado en ATR) ─────────
        # Target = 3.0 * ATR (ratio 1:1.5 respecto al stop)
        target_atr_mult = 3.0
        target_pct = (atr_pct * target_atr_mult) / 100

        # ── Max bars adaptativo ───────────────────────────────────
        # En mercados más volátiles, los trades se resuelven más rápido.
        # Escalamos inversamente a la volatilidad.
        base_bars = 30
        vol_ratio = daily_vol / 0.01  # Normalizado a "volatilidad estándar" de 1%
        max_bars = max(10, min(50, int(base_bars / max(vol_ratio, 0.5))))

        # ── Régimen del periodo de entrenamiento ──────────────────
        train_return = (closes[-1] / closes[0] - 1) * 100
        if train_return < -15:
            regime = "BEAR"
        elif train_return > 15:
            regime = "BULL"
        else:
            regime = "SIDEWAYS"

        # ── Volumen: baseline para Kalman ─────────────────────────
        avg_volume = float(np.mean(volumes[-20:])) if len(volumes) >= 20 else float(np.mean(volumes))

        params = {
            'daily_vol': round(daily_vol, 5),
            'ewma_vol': round(ewma_vol, 5),
            'atr': round(atr, 3),
            'atr_pct': round(atr_pct, 3),
            'entry_threshold': round(entry_threshold, 5),
            'stop_pct': round(stop_pct, 5),
            'target_pct': round(target_pct, 5),
            'max_bars': max_bars,
            'train_regime': regime,
            'train_return_pct': round(train_return, 2),
            'avg_volume': round(avg_volume, 0),
            # Multiplicadores (para logging y ajuste manual)
            'entry_z_mult': entry_z_multiplier,
            'stop_atr_mult': stop_atr_mult,
            'target_atr_mult': target_atr_mult,
        }

        logger.info(
            f"   Params adaptativos: vol={daily_vol*100:.2f}%/día | "
            f"ATR={atr_pct:.2f}% | entry>{entry_threshold*100:.2f}% | "
            f"stop={stop_pct*100:.2f}% | target={target_pct*100:.2f}% | "
            f"max_bars={max_bars} | régimen={regime}"
        )
        return params

    def simulate_trades_in_window(
        self,
        ticker_data: pd.DataFrame,
        test_start: pd.Timestamp,
        test_end: pd.Timestamp,
        adaptive_params: dict = None,
        # Fallback estáticos (usados solo si adaptive_params es None)
        entry_threshold: float = 0.02,
        stop_pct: float = 0.05,
        target_pct: float = 0.10,
    ) -> list[dict]:
        """
        Simula trades durante una ventana de test con parámetros adaptativos.

        Filtros inteligentes:
        1. RÉGIMEN GATE: Si el training period fue BEAR, reducimos sizing
           y elevamos el threshold de entrada (más selectivo).
        2. MOMENTUM ADAPTATIVO: El threshold de entrada se calibra al
           z-score del retorno diario del ticker (no un % fijo).
        3. STOP/TARGET ATR: Los stops y targets escalan con la volatilidad
           actual del ticker, no un % fijo.
        4. VOLUMEN GATE: Si el volumen del día es menor al 60% del promedio,
           la señal se descarta (sin respaldo institucional).

        Args:
            ticker_data:     DataFrame con Date, Close, Volume para UN ticker.
            test_start:      Inicio de la ventana de test.
            test_end:        Fin de la ventana de test.
            adaptive_params: Parámetros calibrados por calibrate_adaptive_params().
            entry_threshold: Fallback estático si no hay params adaptativos.
            stop_pct:        Fallback estático.
            target_pct:      Fallback estático.

        Returns:
            Lista de trades simulados con datos para TradeAutopsy.
        """
        test_data = ticker_data[
            (ticker_data['Date'] >= test_start) &
            (ticker_data['Date'] < test_end)
        ].copy()

        if len(test_data) < 10:
            return []

        closes = test_data['Close'].values
        dates = test_data['Date'].values
        volumes = test_data['Volume'].values if 'Volume' in test_data else np.ones(len(closes))

        # ── Usar parámetros adaptativos si disponibles ────────────
        if adaptive_params:
            entry_threshold = adaptive_params['entry_threshold']
            stop_pct = adaptive_params['stop_pct']
            target_pct = adaptive_params['target_pct']
            max_bars = adaptive_params['max_bars']
            avg_volume = adaptive_params['avg_volume']
            regime = adaptive_params['train_regime']

            # RÉGIMEN GATE: En bear market, duplicamos el Z-score requerido
            if regime == "BEAR":
                entry_threshold *= 2.0
                logger.debug("   ⚠️ Régimen BEAR detectado: threshold duplicado")
        else:
            max_bars = 30
            avg_volume = np.mean(volumes) if len(volumes) > 0 else 1
            regime = "UNKNOWN"

        trades = []
        i = 1  # Empezamos en la segunda barra (necesitamos retorno)

        # Rolling volatility para z-score en tiempo real dentro del test
        rolling_window = min(20, len(closes) // 3)

        while i < len(closes) - 1:
            # ── Z-Score del retorno diario (adaptativo en tiempo real) ──
            daily_return = (closes[i] / closes[i-1]) - 1.0

            # Calcular volatilidad rolling del test period hasta ahora
            lookback_start = max(0, i - rolling_window)
            recent_returns = np.diff(closes[lookback_start:i+1]) / closes[lookback_start:i]
            if len(recent_returns) > 2:
                local_vol = np.std(recent_returns)
                # Actualizar threshold usando la volatilidad LOCAL (no solo la del train)
                effective_threshold = max(entry_threshold, local_vol * 1.5)
            else:
                effective_threshold = entry_threshold

            if daily_return < effective_threshold:
                i += 1
                continue

            # ── VOLUMEN GATE: Descartar si volumen < 60% del promedio ──
            if avg_volume > 0 and volumes[i] < avg_volume * 0.6:
                i += 1
                continue  # Sin respaldo institucional

            # ── Entrar en el trade ──
            entry_price = closes[i]
            entry_idx = i

            # Stop y target adaptativos al precio actual
            # (recalculados con ATR local si tenemos suficientes datos)
            if i >= 20:
                local_highs = test_data['High'].values[i-20:i] if 'High' in test_data else closes[i-20:i] * 1.005
                local_lows = test_data['Low'].values[i-20:i] if 'Low' in test_data else closes[i-20:i] * 0.995
                local_trs = []
                for k in range(1, len(local_highs)):
                    tr = max(
                        local_highs[k] - local_lows[k],
                        abs(local_highs[k] - closes[i-20+k-1]),
                        abs(local_lows[k] - closes[i-20+k-1]),
                    )
                    local_trs.append(tr)
                local_atr = np.mean(local_trs) if local_trs else entry_price * stop_pct
                local_stop_pct = (local_atr * 2.0) / entry_price
                local_target_pct = (local_atr * 3.0) / entry_price
            else:
                local_stop_pct = stop_pct
                local_target_pct = target_pct

            stop_price = entry_price * (1 - local_stop_pct)
            target_price = entry_price * (1 + local_target_pct)
            exit_price = entry_price
            exit_idx = i
            price_series = [entry_price]

            # ── Buscar salida con trailing logic ──
            highest_price = entry_price
            for j in range(i + 1, min(len(closes), i + max_bars + 1)):
                price_series.append(closes[j])
                highest_price = max(highest_price, closes[j])

                # Trailing stop: una vez que ganamos > 1 ATR,
                # ajustamos el stop al 50% del recorrido favorable
                if highest_price > entry_price * (1 + local_stop_pct):
                    trailing_stop = entry_price + (highest_price - entry_price) * 0.5
                    stop_price = max(stop_price, trailing_stop)

                if closes[j] <= stop_price:
                    exit_price = closes[j]
                    exit_idx = j
                    break
                if closes[j] >= target_price:
                    exit_price = closes[j]
                    exit_idx = j
                    break
                exit_price = closes[j]
                exit_idx = j

            pnl = (exit_price / entry_price - 1) * 100

            trades.append({
                'trade_id': f"BT-{len(trades)+1:04d}",
                'ticker': ticker_data['Ticker'].iloc[0] if 'Ticker' in ticker_data else 'UNK',
                'entry_price': round(entry_price, 2),
                'exit_price': round(exit_price, 2),
                'initial_stop': round(entry_price * (1 - local_stop_pct), 2),
                'price_series': [round(p, 2) for p in price_series],
                'exit_reason': 'STOP_HIT' if exit_price <= stop_price
                               else 'TAKE_PROFIT' if exit_price >= target_price
                               else 'TIMEOUT',
                'direction': 'LONG',
                'entry_date': str(dates[entry_idx]),
                'exit_date': str(dates[exit_idx]),
                'pnl_pct': round(pnl, 3),
                'bars_held': exit_idx - entry_idx,
                # Metadata adaptativa (para análisis posterior)
                'adaptive_params': {
                    'effective_threshold': round(effective_threshold * 100, 3),
                    'local_stop_pct': round(local_stop_pct * 100, 3),
                    'local_target_pct': round(local_target_pct * 100, 3),
                    'volume_ratio': round(volumes[entry_idx] / max(avg_volume, 1), 2),
                    'regime': regime,
                },
            })

            i = exit_idx + 1  # No re-entrar durante el mismo trade

        return trades

    def evaluate_window(
        self,
        window: dict,
        ticker_data: pd.DataFrame,
    ) -> WindowResult:
        """
        Evalúa una ventana completa: calibra, simula trades y produce métricas.

        Args:
            window: Dict con train_start/end, test_start/end, window_id.
            ticker_data: DataFrame con datos para un ticker.

        Returns:
            WindowResult con todas las métricas de la ventana.
        """
        w = window
        wid = w['window_id']

        # ── NUEVO: Calibrar parámetros adaptativos desde TRAIN data ──
        train_data = ticker_data[
            (ticker_data['Date'] >= w['train_start']) &
            (ticker_data['Date'] < w['train_end'])
        ]

        if len(train_data) < 30:
            return WindowResult(
                window_id=wid,
                train_start=str(w['train_start'].date()),
                train_end=str(w['train_end'].date()),
                test_start=str(w['test_start'].date()),
                test_end=str(w['test_end'].date()),
                regime="INSUFFICIENT_DATA",
            )

        adaptive_params = self.calibrate_adaptive_params(train_data)

        # Simular trades en la ventana de test CON parámetros adaptativos
        trades = self.simulate_trades_in_window(
            ticker_data, w['test_start'], w['test_end'],
            adaptive_params=adaptive_params,
        )

        if not trades:
            return WindowResult(
                window_id=wid,
                train_start=str(w['train_start'].date()),
                train_end=str(w['train_end'].date()),
                test_start=str(w['test_start'].date()),
                test_end=str(w['test_end'].date()),
                regime=self._classify_regime(ticker_data, w['test_start'], w['test_end']),
            )

        # ── Métricas base ──
        pnls = [t['pnl_pct'] for t in trades]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]

        n_trades = len(pnls)
        n_winners = len(winners)
        win_rate = n_winners / n_trades * 100 if n_trades > 0 else 0

        total_pnl = sum(pnls)
        avg_pnl = np.mean(pnls) if pnls else 0.0

        # Sharpe Ratio (anualizado, asumiendo ~252 trading days / avg bars per trade)
        if len(pnls) > 1 and np.std(pnls) > 0:
            avg_bars = np.mean([t['bars_held'] for t in trades])
            trades_per_year = 252 / max(avg_bars, 1)
            sharpe = (np.mean(pnls) / np.std(pnls)) * np.sqrt(trades_per_year)
        else:
            sharpe = 0.0

        # Max Drawdown (sobre la equity curve acumulada)
        equity = np.cumsum(pnls)
        running_max = np.maximum.accumulate(equity)
        drawdowns = equity - running_max
        max_dd = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

        # Profit Factor
        gross_profit = sum(winners) if winners else 0
        gross_loss = abs(sum(losers)) if losers else 0.001
        profit_factor = gross_profit / gross_loss

        # Calmar Ratio
        calmar = (total_pnl / abs(max_dd)) if abs(max_dd) > 0.01 else total_pnl * 10

        # ── TradeAutopsy ──
        autopsy_df = self.autopsy.analyze_batch(trades)
        error_dist = {}
        avg_entry_eff = 0.0
        avg_edge = 0.0

        if not autopsy_df.empty:
            error_dist = autopsy_df['error_class'].value_counts().to_dict()
            avg_entry_eff = autopsy_df['entry_efficiency'].mean()
            avg_edge = autopsy_df['edge_ratio'].mean()

        regime = self._classify_regime(ticker_data, w['test_start'], w['test_end'])

        return WindowResult(
            window_id=wid,
            train_start=str(w['train_start'].date()),
            train_end=str(w['train_end'].date()),
            test_start=str(w['test_start'].date()),
            test_end=str(w['test_end'].date()),
            n_trades=n_trades,
            n_winners=n_winners,
            n_losers=len(losers),
            win_rate=round(win_rate, 1),
            total_pnl_pct=round(total_pnl, 2),
            avg_pnl_pct=round(avg_pnl, 3),
            sharpe_ratio=round(sharpe, 3),
            max_drawdown_pct=round(max_dd, 2),
            profit_factor=round(profit_factor, 3),
            calmar_ratio=round(calmar, 3),
            error_distribution=error_dist,
            avg_entry_efficiency=round(avg_entry_eff, 3),
            avg_edge_ratio=round(avg_edge, 3),
            regime=regime,
        )

    def run(self, ticker: str = 'SPY') -> BacktestReport:
        """
        Ejecuta el Walk-Forward completo sobre un ticker.

        Args:
            ticker: El ticker a evaluar (default: SPY como benchmark).

        Returns:
            BacktestReport con el veredicto de gating.
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"WALK-FORWARD BACKTESTER — {ticker}")
        logger.info(f"{'='*60}")

        # 1. Cargar datos
        df = self.load_data(ticker)

        # 2. Generar ventanas
        windows = self.generate_windows(df)
        if not windows:
            logger.warning("No se pudieron generar ventanas Walk-Forward.")
            return BacktestReport()

        # 3. Evaluar cada ventana
        results = []
        for w in windows:
            logger.info(
                f"\n── Ventana {w['window_id']} ──"
                f"\n   Train: {w['train_start'].date()} → {w['train_end'].date()}"
                f"\n   Test:  {w['test_start'].date()} → {w['test_end'].date()}"
            )
            result = self.evaluate_window(w, df)
            results.append(result)
            logger.info(
                f"   Trades: {result.n_trades} | "
                f"WR: {result.win_rate:.0f}% | "
                f"Sharpe: {result.sharpe_ratio:.2f} | "
                f"PF: {result.profit_factor:.2f} | "
                f"MaxDD: {result.max_drawdown_pct:.1f}% | "
                f"Régimen: {result.regime}"
            )

        # 4. Agregación y Gating
        report = self._aggregate_results(results)

        # 5. Log veredicto
        verdict = "✅ APROBADO → Shadow Mode" if report.approved_for_shadow \
                  else "❌ NO APROBADO — requiere refinamiento"
        logger.info(f"\n{'='*60}")
        logger.info(f"VEREDICTO: {verdict}")
        logger.info(f"  Sharpe promedio: {report.avg_sharpe:.2f} (min: {self.GATING_CRITERIA['min_sharpe']})")
        logger.info(f"  Win Rate promedio: {report.avg_win_rate:.1f}% (min: {self.GATING_CRITERIA['min_win_rate']}%)")
        logger.info(f"  Profit Factor promedio: {report.avg_profit_factor:.2f} (min: {self.GATING_CRITERIA['min_profit_factor']})")
        logger.info(f"  Peor Drawdown: {report.worst_drawdown:.1f}% (max: {self.GATING_CRITERIA['max_drawdown']}%)")
        logger.info(f"{'='*60}\n")

        return report

    def _aggregate_results(self, results: list[WindowResult]) -> BacktestReport:
        """Agrega resultados de todas las ventanas en un reporte."""
        active = [r for r in results if r.n_trades > 0]

        if not active:
            return BacktestReport(total_windows=len(results))

        sharpes = [r.sharpe_ratio for r in active]
        win_rates = [r.win_rate for r in active]
        pfs = [r.profit_factor for r in active]
        dds = [r.max_drawdown_pct for r in active]

        avg_sharpe = float(np.mean(sharpes))
        avg_wr = float(np.mean(win_rates))
        avg_pf = float(np.mean(pfs))
        worst_dd = float(np.min(dds))
        total_ret = sum(r.total_pnl_pct for r in active)

        # Gating checks
        g = self.GATING_CRITERIA
        passes_sharpe = avg_sharpe >= g['min_sharpe']
        passes_dd = worst_dd >= g['max_drawdown']
        passes_wr = avg_wr >= g['min_win_rate']
        passes_pf = avg_pf >= g['min_profit_factor']
        approved = passes_sharpe and passes_dd and passes_wr and passes_pf

        # Debilidades sistémicas: agregar error_distributions
        all_errors = {}
        for r in active:
            for err, count in r.error_distribution.items():
                all_errors[err] = all_errors.get(err, 0) + count

        total_errs = sum(all_errors.values()) or 1
        weaknesses = [
            {"error": e, "count": c, "pct": round(c / total_errs * 100, 1)}
            for e, c in sorted(all_errors.items(), key=lambda x: -x[1])
            if c / total_errs > 0.25  # Solo reportar errores > 25%
        ]

        return BacktestReport(
            total_windows=len(results),
            windows=[asdict(r) for r in results],
            avg_sharpe=round(avg_sharpe, 3),
            avg_win_rate=round(avg_wr, 1),
            avg_profit_factor=round(avg_pf, 3),
            worst_drawdown=round(worst_dd, 2),
            total_return_pct=round(total_ret, 2),
            passes_sharpe=passes_sharpe,
            passes_drawdown=passes_dd,
            passes_win_rate=passes_wr,
            passes_profit_factor=passes_pf,
            approved_for_shadow=approved,
            systemic_weaknesses=weaknesses,
        )

    @staticmethod
    def _classify_regime(
        df: pd.DataFrame,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> str:
        """
        Clasifica el régimen del mercado durante un período.
        Usa el retorno total del período para una clasificación simple.
        """
        period = df[(df['Date'] >= start) & (df['Date'] < end)]
        if period.empty or len(period) < 2:
            return "UNKNOWN"

        closes = period['Close'].values
        total_return = (closes[-1] / closes[0] - 1) * 100

        if total_return > 10:
            return "BULL"
        elif total_return < -10:
            return "BEAR"
        else:
            return "SIDEWAYS"
