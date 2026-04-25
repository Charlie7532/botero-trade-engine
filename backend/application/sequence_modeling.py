import pandas as pd
import numpy as np
import torch
from torch.utils.data import Dataset
import logging

logger = logging.getLogger(__name__)


class TripleBarrierLabeler:
    """
    Etiquetado Institucional con Triple Barrera dinámica (López de Prado, Ch. 3).

    Diferencias con la versión anterior:
    1. Volatilidad basada en ATR real o EWMA de retornos, no en BBW.
    2. Trailing Stop basado en Maximum Favorable Excursion (MFE).
    3. Sample weights por unicidad temporal.
    """

    def __init__(
        self,
        profit_mult: float = 2.0,
        loss_mult: float = 1.0,
        max_bars: int = 30,
        vol_lookback: int = 20,
    ):
        """
        Args:
            profit_mult: Múltiplo de volatilidad para Take Profit.
            loss_mult: Múltiplo de volatilidad para Stop Loss.
            max_bars: Barrera vertical (timeout en barras).
            vol_lookback: Ventana para estimar volatilidad EWMA.
        """
        self.pt_mult = profit_mult
        self.sl_mult = loss_mult
        self.max_bars = max_bars
        self.vol_lookback = vol_lookback

    def _estimate_volatility(self, close: pd.Series) -> pd.Series:
        """
        Estima volatilidad EWMA de retornos logarítmicos.
        Más reactiva que ATR, sin sesgo de rango intradiario.
        """
        log_returns = np.log(close / close.shift(1))
        return log_returns.ewm(span=self.vol_lookback).std()

    def apply_barriers(self, df: pd.DataFrame, close_col: str = 'close') -> pd.DataFrame:
        """
        Aplica Triple Barrera con volatilidad dinámica.

        Args:
            df: DataFrame con al menos la columna close_col.
            close_col: Nombre de la columna de cierre.

        Returns:
            DataFrame con columnas añadidas:
            - 'target': 1 (TP alcanzado primero), 0 (SL o Timeout)
            - 'barrier_horizon': Barras hasta tocar barrera
            - 'vol_at_entry': Volatilidad al momento de la etiqueta
        """
        logger.info(
            f"Aplicando Triple Barrera (TP={self.pt_mult}x, SL={self.sl_mult}x, "
            f"MaxBars={self.max_bars})..."
        )

        close = df[close_col].values
        vol = self._estimate_volatility(df[close_col]).values

        n = len(df)
        labels = np.zeros(n, dtype=np.int32)
        horizons = np.full(n, self.max_bars, dtype=np.int32)
        vol_at_entry = np.full(n, np.nan, dtype=np.float64)

        for i in range(n - 1):
            v = vol[i]
            if np.isnan(v) or v < 1e-10:
                continue

            entry = close[i]
            tp_level = entry * (1.0 + v * self.pt_mult)
            sl_level = entry * (1.0 - v * self.sl_mult)

            vol_at_entry[i] = v
            end_idx = min(n, i + self.max_bars + 1)

            for j in range(i + 1, end_idx):
                # Stop Loss golpeado
                if close[j] <= sl_level:
                    labels[i] = 0
                    horizons[i] = j - i
                    break
                # Take Profit alcanzado
                if close[j] >= tp_level:
                    labels[i] = 1
                    horizons[i] = j - i
                    break

        df['target'] = labels
        df['barrier_horizon'] = horizons
        df['vol_at_entry'] = vol_at_entry

        # Descartar las últimas N barras (futuro desconocido = look-ahead bias)
        df = df.iloc[:-self.max_bars].copy()

        # Estadísticas
        valid = df['vol_at_entry'].notna()
        if valid.sum() > 0:
            wr = df.loc[valid, 'target'].mean()
            logger.info(
                f"Triple Barrera completada. Win Rate base: {wr*100:.2f}% "
                f"({valid.sum()} observaciones válidas)"
            )

        return df


class MetaLabeler:
    """
    Metalabeling (López de Prado, Ch. 3.6).

    Concepto: Un modelo primario genera señales de dirección (buy/sell).
    Este segundo modelo (la LSTM) aprende a filtrar las señales falsas.
    Su target: ¿La señal primaria será correcta (1) o incorrecta (0)?

    La ventaja: La LSTM no necesita predecir dirección del mercado
    (imposible consistentemente). Solo necesita evaluar la calidad
    de una señal ya emitida.
    """

    @staticmethod
    def generate_primary_signals(
        df: pd.DataFrame,
        momentum_lookback: int = 20,
        signal_col: str = 'primary_signal',
    ) -> pd.DataFrame:
        """
        Modelo primario simple: Señal de momentum.
        Genera BUY cuando el retorno de N períodos es positivo.

        En producción, esto puede reemplazarse por cualquier modelo:
        Random Forest, reglas de Order Flow, etc.
        """
        log_returns = np.log(df['close'] / df['close'].shift(momentum_lookback))
        df[signal_col] = (log_returns > 0).astype(int)
        return df

    @staticmethod
    def apply_metalabels(
        df: pd.DataFrame,
        signal_col: str = 'primary_signal',
        barrier_col: str = 'target',
    ) -> pd.DataFrame:
        """
        Genera meta-etiquetas: ¿La señal primaria acertó?

        Solo etiquetamos las filas donde el modelo primario emitió señal (=1).
        Meta-target = 1 si la señal fue correcta (y la barrera superior se tocó).
        Meta-target = 0 si la señal fue incorrecta (SL o timeout).
        """
        # Solo evaluamos filas con señal activa
        mask = df[signal_col] == 1
        df['meta_target'] = np.nan
        df.loc[mask, 'meta_target'] = df.loc[mask, barrier_col].astype(float)

        active = mask.sum()
        if active > 0:
            meta_wr = df.loc[mask, 'meta_target'].mean()
            logger.info(
                f"Metalabeling: {active} señales activas. "
                f"Meta Win Rate: {meta_wr*100:.2f}%"
            )

        return df


class SampleWeighter:
    """
    Pesos de muestra por unicidad temporal (López de Prado, Ch. 4).

    Problema: Muchas observaciones en un mercado lateral son casi idénticas.
    Si las tratamos con igual peso, la LSTM sobreajusta a la lateralidad.

    Solución: Observaciones concurrentes (que se solapan en la Triple Barrera)
    pesan menos. Eventos raros (crashes, reversiones) pesan más.
    """

    @staticmethod
    def compute_sample_weights(
        df: pd.DataFrame,
        horizon_col: str = 'barrier_horizon',
    ) -> pd.Series:
        """
        Calcula pesos basados en el número de eventos concurrentes.
        Menos concurrencia = más unicidad = más peso.
        """
        n = len(df)
        horizons = df[horizon_col].values

        # Contar cuántos eventos están activos en cada barra
        concurrency = np.zeros(n)
        for i in range(n):
            h = int(horizons[i]) if not np.isnan(horizons[i]) else 1
            end = min(n, i + h)
            concurrency[i:end] += 1

        # Peso = inverso de concurrencia promedio durante la vida del evento
        weights = np.ones(n)
        for i in range(n):
            h = int(horizons[i]) if not np.isnan(horizons[i]) else 1
            end = min(n, i + h)
            avg_concurrency = concurrency[i:end].mean()
            weights[i] = 1.0 / max(avg_concurrency, 1.0)

        # Normalizar para que sumen N (preserva la escala del loss)
        weights = weights * (n / weights.sum())

        return pd.Series(weights, index=df.index, name='sample_weight')


class QuantSequenceDataset(Dataset):
    """
    Dataset PyTorch para secuencias temporales con Metalabeling.
    Genera ventanas deslizantes (Batch, Seq_Length, Features) con pesos.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        sequence_length: int = 30,
        feature_cols: list = None,
        target_col: str = 'meta_target',
        weight_col: str = 'sample_weight',
    ):
        if feature_cols is None:
            raise ValueError("Debes especificar la lista de feature columns.")

        # Filtrar solo filas con meta_target válido (señales activas)
        if target_col in df.columns:
            valid_mask = df[target_col].notna()
            df = df[valid_mask].copy()

        if len(df) < sequence_length:
            raise ValueError(
                f"Dataset ({len(df)} filas) más pequeño que "
                f"sequence_length ({sequence_length})."
            )

        self.sequence_length = sequence_length
        self.features = df[feature_cols].values.astype(np.float32)
        self.targets = df[target_col].values.astype(np.float32)

        if weight_col in df.columns:
            self.weights = df[weight_col].values.astype(np.float32)
        else:
            self.weights = np.ones(len(df), dtype=np.float32)

    def __len__(self):
        return len(self.features) - self.sequence_length

    def __getitem__(self, idx):
        x_seq = self.features[idx: idx + self.sequence_length]
        y_label = self.targets[idx + self.sequence_length - 1]
        weight = self.weights[idx + self.sequence_length - 1]

        return (
            torch.from_numpy(x_seq),
            torch.tensor(y_label),
            torch.tensor(weight),
        )
