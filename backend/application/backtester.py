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

from application.sequence_modeling import TripleBarrierLabeler
from application.trade_autopsy import TradeAutopsy
from infrastructure.data_providers.volume_dynamics import (
    KalmanVolumeTracker, SectorRegimeDetector,
)

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
        'min_trades_total': 15,   # Mínimo de trades totales para significancia
    }

    # Costos de transacción realistas para ETFs
    TRANSACTION_COSTS = {
        'spread_pct': 0.03,      # Spread promedio para ETFs líquidos
        'slippage_pct': 0.05,    # Slippage en condiciones oversold (spread ensanchado)
        'commission_per_trade': 0.0,  # Comisiones $0 en brokers modernos
    }

    # Costo round-trip total = (spread + slippage) × 2 lados
    ROUND_TRIP_COST_PCT = (TRANSACTION_COSTS['spread_pct'] + TRANSACTION_COSTS['slippage_pct']) * 2

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
        self.kalman = KalmanVolumeTracker(
            dt=1.0, process_noise=0.05, obs_noise=0.2,
        )
        self._all_trades = []  # Aggregate all trades across windows

    @staticmethod
    def volume_quality_score(
        close: float,
        high: float,
        low: float,
        volume: float,
        avg_volume: float,
        prev_close: float,
    ) -> float:
        """
        Volume Quality Score (0.0 - 3.0) para filtrar volumen ficticio de HFT.

        Concepto: Los algoritmos HFT generan millones de transacciones en
        microsegundos con márgenes minúsculos. Esto infla el volumen reportado
        pero NO mueve el precio proporcionalmente. Un volumen "real" de
        institucionales MUEVE el precio.

        Métricas usadas:
        1. AMIHUD ILLIQUIDITY: |return| / dollar_volume
           - Si el volumen es alto pero el precio no se mueve → HFT noise
           - Si el volumen es alto Y el precio se mueve → real

        2. PRICE CONFIRMATION: Close relativo al rango High-Low
           - Si el close está cerca del Low → buyers activos (convicción)
           - Si el close está al medio del rango → sin convicción

        3. RELATIVE VOLUME: Vs promedio
           - Solo puntúa si el volumen es genuinamente elevado

        Returns:
            Score 0.0 (noise) a 3.0 (high-quality institutional volume)
        """
        score = 0.0
        price_range = high - low

        if price_range <= 0 or volume <= 0 or avg_volume <= 0:
            return 0.0

        # 1. Amihud: ¿el volumen MUEVE el precio?
        abs_return = abs(close - prev_close) / prev_close if prev_close > 0 else 0
        dollar_volume = volume * close
        amihud = abs_return / (dollar_volume / 1e9) if dollar_volume > 0 else 0

        # Amihud alto = el volumen sí mueve el precio = volumen real
        # Amihud bajo = mucho volumen pero precio no se mueve = HFT noise
        if amihud > 0.5:  # Umbral adaptativo basado en ETFs
            score += 1.0
        elif amihud > 0.1:
            score += 0.5

        # 2. Price Confirmation: ¿el close está cerca del extremo del rango?
        # Close cerca del Low en un dip = buyers defending (bueno para Spring)
        close_position = (close - low) / price_range  # 0 = close@low, 1 = close@high
        # En una vela de dip, queremos que el close NO esté en el mínimo
        # (señal de que buyers aparecieron al final)
        if close_position > 0.6:  # Close en el tercio superior del rango
            score += 1.0
        elif close_position > 0.3:
            score += 0.5

        # 3. Relative Volume genuinamente elevado
        rvol = volume / avg_volume
        if rvol > 2.0:
            score += 1.0
        elif rvol > 1.5:
            score += 0.5

        return score

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

    def simulate_trades_with_edge(
        self,
        ticker_data: pd.DataFrame,
        spy_data: pd.DataFrame,
        test_start: pd.Timestamp,
        test_end: pd.Timestamp,
        adaptive_params: dict,
        kalman: KalmanVolumeTracker,
    ) -> list[dict]:
        """
        Simula trades usando Mean-Reversion Spring con confirmación Kalman.

        Lógica empíricamente validada:
          ETFs mean-revertan por el mecanismo de creation/redemption.
          El "Spring" de Wyckoff es comprar la caída injusta con volumen.

        ENTRY (3 condiciones simultáneas — "Wyckoff Spring"):
          1. OVERSOLD:  Retorno de 5 días < -2% (precio cayó más de lo justo)
          2. VOLUME:    RVol > 1.2 (institucionales están comprando el dip)
          3. KALMAN:    wyckoff_state != DISTRIBUTION ni MARKDOWN
                        (no entramos en caída libre confirmada)

        EXIT (cualquiera de las 4 condiciones):
          1. MA20_REVERSION: Precio alcanza la MA20 (target natural de reversión)
          2. TRAILING ATR:   Trailing stop adaptativo a la volatilidad
          3. RS SAFETY:      RS decay < 0.85 (si pierde vs SPY, salimos)
          4. TIMEOUT:        max_bars (evitar capital atrapado)

        Args:
            ticker_data:     DataFrame con Date, OHLCV para UN ticker.
            spy_data:        DataFrame con Date, OHLCV para SPY.
            test_start:      Inicio de la ventana de test.
            test_end:        Fin de la ventana de test.
            adaptive_params: Parámetros calibrados del train period.
            kalman:          KalmanVolumeTracker ya calentado con train data.

        Returns:
            Lista de trades simulados con datos para TradeAutopsy.
        """
        test_ticker = ticker_data[
            (ticker_data['Date'] >= test_start) &
            (ticker_data['Date'] < test_end)
        ].copy().reset_index(drop=True)
        test_spy = spy_data[
            (spy_data['Date'] >= test_start) &
            (spy_data['Date'] < test_end)
        ].copy().reset_index(drop=True)

        if len(test_ticker) < 20 or len(test_spy) < 20:
            return []

        # Alinear por fecha
        test_ticker = test_ticker.set_index('Date')
        test_spy = test_spy.set_index('Date')
        common_dates = test_ticker.index.intersection(test_spy.index)
        test_ticker = test_ticker.loc[common_dates].reset_index()
        test_spy = test_spy.loc[common_dates].reset_index()

        if len(test_ticker) < 20:
            return []

        closes = test_ticker['Close'].values
        highs_arr = test_ticker['High'].values
        lows_arr = test_ticker['Low'].values
        spy_closes = test_spy['Close'].values
        volumes = test_ticker['Volume'].values
        dates = test_ticker['Date'].values
        ticker_name = ticker_data['Ticker'].iloc[0] if 'Ticker' in ticker_data else 'UNK'

        # Parámetros adaptativos
        stop_pct = adaptive_params['stop_pct']
        max_bars = adaptive_params['max_bars']
        avg_volume = adaptive_params['avg_volume']

        trades = []
        in_trade = False
        entry_price = 0.0
        entry_idx = 0
        entry_rs = 0.0
        stop_price = 0.0
        ma20_target = 0.0
        highest_price = 0.0
        price_series = []
        local_stop_pct = stop_pct
        entry_wyckoff = 'UNKNOWN'

        # Lookbacks
        rs_lookback = 20
        oversold_lookback = 5

        for i in range(rs_lookback, len(closes)):
            # ── Calcular señales del motor ──────────────────────────

            # 1. KALMAN: Alimentar con rvol + cambio de precio
            avg_vol_local = np.mean(volumes[max(0, i-20):i]) if i >= 20 else np.mean(volumes[:i+1])
            rvol = volumes[i] / max(avg_vol_local, 1.0)
            price_change_pct = (closes[i] / closes[i-1] - 1) * 100 if i > 0 else 0.0
            kalman_result = kalman.update(ticker_name, rvol, change_pct=price_change_pct)
            wyckoff_state = kalman_result['wyckoff_state']
            kalman_velocity = kalman_result['velocity']

            # 2. RS vs SPY (20 días)
            stock_ret = closes[i] / closes[i - rs_lookback] - 1
            spy_ret = spy_closes[i] / spy_closes[i - rs_lookback] - 1
            rs_vs_spy = (1 + stock_ret) / (1 + spy_ret) if spy_ret != -1 else 1.0

            # 3. MA20 (target natural de reversión)
            ma20 = np.mean(closes[max(0, i-20):i]) if i >= 20 else closes[i]

            # 4. Retorno de 5 días (oversold detection)
            ret_5d = (closes[i] / closes[i - oversold_lookback] - 1) if i >= oversold_lookback else 0.0

            # ── GESTIÓN DE POSICIÓN ABIERTA ────────────────────────
            if in_trade:
                price_series.append(closes[i])
                highest_price = max(highest_price, closes[i])
                bars_held = i - entry_idx

                rs_decay = rs_vs_spy / entry_rs if entry_rs > 0 else 1.0
                exit_reason = None

                # Exit 1: MA20 REVERSION — precio alcanzó la MA20 (target)
                if closes[i] >= ma20 and bars_held >= 2:
                    exit_reason = 'MA20_REVERSION'

                # Exit 2: RS SAFETY — perdimos ventaja vs SPY
                elif rs_decay < 0.85:
                    exit_reason = 'RS_DECAY'

                # Exit 3: DISTRIBUTION — Kalman confirma distribución
                elif wyckoff_state == 'DISTRIBUTION' and bars_held >= 3:
                    exit_reason = 'DISTRIBUTION'

                # Exit 4: TRAILING ATR STOP
                if highest_price > entry_price * (1 + local_stop_pct):
                    trailing = entry_price + (highest_price - entry_price) * 0.5
                    stop_price = max(stop_price, trailing)

                if closes[i] <= stop_price:
                    exit_reason = 'STOP_HIT'
                elif bars_held >= max_bars:
                    exit_reason = 'TIMEOUT'

                if exit_reason:
                    exit_price = closes[i]
                    pnl = (exit_price / entry_price - 1) * 100
                    trades.append({
                        'trade_id': f"BT-{len(trades)+1:04d}",
                        'ticker': ticker_name,
                        'entry_price': round(entry_price, 2),
                        'exit_price': round(exit_price, 2),
                        'initial_stop': round(entry_price * (1 - local_stop_pct), 2),
                        'price_series': [round(p, 2) for p in price_series],
                        'exit_reason': exit_reason,
                        'direction': 'LONG',
                        'entry_date': str(dates[entry_idx]),
                        'exit_date': str(dates[i]),
                        'pnl_pct': round(pnl, 3),
                        'bars_held': bars_held,
                        'adaptive_params': {
                            'entry_rs': round(entry_rs, 4),
                            'exit_rs': round(rs_vs_spy, 4),
                            'rs_decay': round(rs_decay, 4),
                            'ret_5d_at_entry': round(ret_5d * 100, 2),
                            'rvol_at_entry': round(rvol, 2),
                            'wyckoff_at_entry': entry_wyckoff,
                            'wyckoff_at_exit': wyckoff_state,
                            'kalman_velocity': round(kalman_velocity, 4),
                            'local_stop_pct': round(local_stop_pct * 100, 3),
                            'ma20_target': round(ma20, 2),
                        },
                    })
                    in_trade = False
                continue

            # ── SEÑAL DE ENTRADA: MEAN-REVERSION SPRING ───────────

            # Condición 1: OVERSOLD — retorno de 5 días < -2%
            if ret_5d >= -0.02:
                continue

            # Condición 2: VOLUME SURGE — RVol > 1.2 (institucionales activos)
            if rvol < 1.2:
                continue

            # Condición 2b: VOLUME QUALITY — filtrar ruido HFT
            #   Si el volumen es alto pero el precio no se mueve = HFT noise
            vol_quality = self.volume_quality_score(
                close=closes[i], high=highs_arr[i], low=lows_arr[i],
                volume=volumes[i], avg_volume=avg_vol_local,
                prev_close=closes[i-1],
            )
            if vol_quality < 1.0:  # Score mínimo = volumen tiene que mover precio
                continue

            # Condición 3: NOT IN FREEFALL — Kalman no debe confirmar
            # distribución activa ni markdown (caída libre)
            if wyckoff_state in ('DISTRIBUTION', 'MARKDOWN'):
                continue

            # ── SPRING CONFIRMADO → ENTRAR ────────────────────────
            entry_price = closes[i]
            entry_idx = i
            entry_rs = rs_vs_spy
            entry_wyckoff = wyckoff_state
            price_series = [entry_price]
            highest_price = entry_price
            ma20_target = ma20
            in_trade = True

            # ATR local para stop adaptativo
            if i >= 20:
                trs = []
                for k in range(1, 20):
                    tr = max(
                        highs_arr[i-20+k] - lows_arr[i-20+k],
                        abs(highs_arr[i-20+k] - closes[i-20+k-1]),
                        abs(lows_arr[i-20+k] - closes[i-20+k-1]),
                    )
                    trs.append(tr)
                local_atr = np.mean(trs) if trs else entry_price * stop_pct
                local_stop_pct = (local_atr * 2.0) / entry_price
            else:
                local_stop_pct = stop_pct

            stop_price = entry_price * (1 - local_stop_pct)

        # Cerrar trade abierto al final del período
        if in_trade and len(closes) > 0:
            exit_price = closes[-1]
            pnl = (exit_price / entry_price - 1) * 100
            rs_decay = rs_vs_spy / entry_rs if entry_rs > 0 else 1.0
            trades.append({
                'trade_id': f"BT-{len(trades)+1:04d}",
                'ticker': ticker_name,
                'entry_price': round(entry_price, 2),
                'exit_price': round(exit_price, 2),
                'initial_stop': round(entry_price * (1 - local_stop_pct), 2),
                'price_series': [round(p, 2) for p in price_series],
                'exit_reason': 'WINDOW_END',
                'direction': 'LONG',
                'entry_date': str(dates[entry_idx]),
                'exit_date': str(dates[-1]),
                'pnl_pct': round(pnl, 3),
                'bars_held': len(closes) - 1 - entry_idx,
                'adaptive_params': {
                    'entry_rs': round(entry_rs, 4),
                    'exit_rs': round(rs_vs_spy, 4),
                    'rs_decay': round(rs_decay, 4),
                    'ret_5d_at_entry': round(ret_5d * 100, 2),
                    'rvol_at_entry': round(rvol, 2),
                    'wyckoff_at_entry': entry_wyckoff,
                    'wyckoff_at_exit': wyckoff_state,
                    'kalman_velocity': round(kalman_velocity, 4),
                    'local_stop_pct': round(local_stop_pct * 100, 3),
                    'ma20_target': round(ma20, 2),
                },
            })

        # ── Deducir costos de transacción de TODOS los trades ──────
        cost = self.ROUND_TRIP_COST_PCT
        for t in trades:
            t['pnl_pct'] = round(t['pnl_pct'] - cost, 3)

        return trades

    def evaluate_window(
        self,
        window: dict,
        ticker_data: pd.DataFrame,
        spy_data: pd.DataFrame = None,
    ) -> WindowResult:
        """
        Evalúa una ventana completa: calibra Kalman, simula trades con
        señales reales (Accumulation + RS), y produce métricas.

        Args:
            window: Dict con train_start/end, test_start/end, window_id.
            ticker_data: DataFrame con datos para un ticker.
            spy_data: DataFrame con datos de SPY para RS calculation.

        Returns:
            WindowResult con todas las métricas de la ventana.
        """
        w = window
        wid = w['window_id']

        # ── Calibrar parámetros adaptativos desde TRAIN data ──
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

        # ── Calentar Kalman con datos de TRAIN (warm-up) ──
        ticker_name = ticker_data['Ticker'].iloc[0] if 'Ticker' in ticker_data else 'UNK'
        kalman = KalmanVolumeTracker(dt=1.0, process_noise=0.05, obs_noise=0.2)
        train_volumes = train_data['Volume'].values
        train_closes = train_data['Close'].values
        for vi in range(20, len(train_volumes)):
            avg_v = np.mean(train_volumes[max(0, vi-20):vi])
            rvol = train_volumes[vi] / max(avg_v, 1.0)
            chg = (train_closes[vi] / train_closes[vi-1] - 1) * 100 if vi > 0 else 0.0
            kalman.update(ticker_name, rvol, change_pct=chg)

        # ── Simular trades con señales REALES ──
        if spy_data is not None and not spy_data.empty:
            trades = self.simulate_trades_with_edge(
                ticker_data, spy_data,
                w['test_start'], w['test_end'],
                adaptive_params=adaptive_params,
                kalman=kalman,
            )
        else:
            # Fallback si no hay SPY data (autodeterminación)
            trades = self.simulate_trades_with_edge(
                ticker_data, ticker_data,
                w['test_start'], w['test_end'],
                adaptive_params=adaptive_params,
                kalman=kalman,
            )

        # Acumular trades para métricas agregadas
        self._all_trades.extend(trades)

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

        Usa señales reales del motor:
        - Kalman ACCUMULATION para entradas
        - RS vs SPY para confirmación y salidas
        - ATR trailing para protección

        Args:
            ticker: El ticker a evaluar (default: SPY como benchmark).

        Returns:
            BacktestReport con el veredicto de gating.
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"WALK-FORWARD BACKTESTER — {ticker}")
        logger.info(f"{'='*60}")

        # 1. Cargar datos del ticker + SPY (benchmark para RS)
        df = self.load_data(ticker)
        spy_df = None
        if ticker != 'SPY':
            try:
                spy_df = self.load_data('SPY')
            except Exception as e:
                logger.warning(f"No se pudo cargar SPY para RS: {e}")
        else:
            # SPY vs sí mismo → RS siempre ~1.0, las señales
            # dependerán más de Kalman + Volume
            spy_df = df.copy()

        # 2. Generar ventanas
        windows = self.generate_windows(df)
        if not windows:
            logger.warning("No se pudieron generar ventanas Walk-Forward.")
            return BacktestReport()

        # 3. Evaluar cada ventana con señales reales
        self._all_trades = []  # Reset para aggregate metrics
        results = []
        for w in windows:
            logger.info(
                f"\n── Ventana {w['window_id']} ──"
                f"\n   Train: {w['train_start'].date()} → {w['train_end'].date()}"
                f"\n   Test:  {w['test_start'].date()} → {w['test_end'].date()}"
            )
            result = self.evaluate_window(w, df, spy_data=spy_df)
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
        """
        Agrega resultados de todas las ventanas en un reporte HONESTO.

        CAMBIO CLAVE: Las métricas (Sharpe, PF) se calculan sobre TODOS
        los trades agregados, NO promediando métricas por ventana.
        Esto elimina la inflación por ventanas con N=1-3 trades.
        """
        active = [r for r in results if r.n_trades > 0]

        if not active:
            return BacktestReport(total_windows=len(results))

        # ── Recopilar TODOS los trades desde _all_trades ──
        all_pnls = [t['pnl_pct'] for t in self._all_trades]
        all_bars = [t['bars_held'] for t in self._all_trades]
        total_trades = len(all_pnls)

        if total_trades > 0:
            winners = [p for p in all_pnls if p > 0]
            losers = [p for p in all_pnls if p <= 0]

            # Sharpe agregado (sobre todos los trades)
            if len(all_pnls) > 1 and np.std(all_pnls) > 0:
                avg_bars = np.mean(all_bars) if all_bars else 5
                trades_per_year = 252 / max(avg_bars, 1)
                agg_sharpe = (np.mean(all_pnls) / np.std(all_pnls)) * np.sqrt(trades_per_year)
            else:
                agg_sharpe = 0.0

            # Win Rate agregado
            agg_wr = len(winners) / total_trades * 100

            # Profit Factor agregado (honesto)
            gross_profit = sum(winners) if winners else 0
            gross_loss = abs(sum(losers)) if losers else 0.001
            agg_pf = gross_profit / gross_loss

            # Max Drawdown sobre equity curve completa
            equity = np.cumsum(all_pnls)
            running_max = np.maximum.accumulate(equity)
            drawdowns = equity - running_max
            worst_dd = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

            total_ret = sum(all_pnls)
        else:
            agg_sharpe = 0.0
            agg_wr = 0.0
            agg_pf = 0.0
            worst_dd = 0.0
            total_ret = 0.0

        # Gating checks (con mínimo de trades)
        g = self.GATING_CRITERIA
        min_trades = g.get('min_trades_total', 15)
        enough_trades = total_trades >= min_trades
        passes_sharpe = bool(agg_sharpe >= g['min_sharpe'] and enough_trades)
        passes_dd = bool(worst_dd >= g['max_drawdown'])
        passes_wr = bool(agg_wr >= g['min_win_rate'] and enough_trades)
        passes_pf = bool(agg_pf >= g['min_profit_factor'] and enough_trades)
        approved = bool(passes_sharpe and passes_dd and passes_wr and passes_pf)

        # Debilidades sistémicas
        all_errors = {}
        for r in active:
            for err, count in r.error_distribution.items():
                all_errors[err] = all_errors.get(err, 0) + count

        total_errs = sum(all_errors.values()) or 1
        weaknesses = [
            {"error": e, "count": c, "pct": round(c / total_errs * 100, 1)}
            for e, c in sorted(all_errors.items(), key=lambda x: -x[1])
            if c / total_errs > 0.25
        ]

        return BacktestReport(
            total_windows=len(results),
            windows=[asdict(r) for r in results],
            avg_sharpe=round(float(agg_sharpe), 3),
            avg_win_rate=round(float(agg_wr), 1),
            avg_profit_factor=round(float(agg_pf), 3),
            worst_drawdown=round(float(worst_dd), 2),
            total_return_pct=round(float(total_ret), 2),
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
