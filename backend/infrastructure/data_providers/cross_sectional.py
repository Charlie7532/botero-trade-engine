import pandas as pd
import numpy as np
import logging
from pathlib import Path
from backend.infrastructure.data_providers.tradingview_parser import TradingViewParser
from backend.application.feature_engineering import QuantFeatureEngineer

logger = logging.getLogger(__name__)


class CrossSectionalLoader:
    """
    Cargador Institucional Transversal.
    Ingesta el universo de ETFs suministrados, los sincroniza en la misma línea de tiempo,
    resuelve los Features Cuánticos estacionarios, y genera un Tensor Múltiple para LSTMs.
    """

    def __init__(self, data_directory: str, benchmark_ticker: str = "SPX"):
        self.data_dir = Path(data_directory)
        self.benchmark_ticker = benchmark_ticker
        self.parser = TradingViewParser()
        self.universe_dfs = {}
        self.benchmark_df = None
        self.unified_tensor = None

    def load_universe(self, timeframe_filter: str = "75"):
        """
        Escanea recursivamente el directorio buscando ETFs que coincidan
        con la temporalidad elegida.
        """
        logger.info(f"Buscando universo de datos para la temporalidad: {timeframe_filter}m")
        all_csvs = list(self.data_dir.rglob("*.csv"))

        target_csvs = [f for f in all_csvs if f", {timeframe_filter}" in f.name]

        if not target_csvs:
            raise ValueError(f"No se encontraron archivos para temporalidad {timeframe_filter}")

        for path in target_csvs:
            # Deducir ticker desde la ruta (ej: /DATA/XLK/AMEX_XLK, 75.csv -> XLK)
            ticker = path.parent.name
            df = self.parser.parse_csv(path)

            if ticker == self.benchmark_ticker:
                self.benchmark_df = df
            else:
                self.universe_dfs[ticker] = df

        logger.info(
            f"Universo Cargado. Benchmark: {self.benchmark_ticker}. "
            f"Sectores: {list(self.universe_dfs.keys())}"
        )

    def _get_timeframe_minutes(self, timeframe_filter: str) -> int:
        """Convierte el filtro de temporalidad a minutos."""
        tf_map = {
            "3": 3, "15": 15, "75": 75, "375": 375,
            "1D": 1440, "1W": 10080,
        }
        return tf_map.get(timeframe_filter, 75)

    def build_feature_tensor(self, timeframe_filter: str = "75") -> pd.DataFrame:
        """
        Calcula los features estacionarios de cada sector y los apila
        en un único DataFrame wide.
        """
        if self.benchmark_df is None:
            raise ValueError("El Benchmark (SPX/SPY) no fue cargado correctamente.")

        tf_mins = self._get_timeframe_minutes(timeframe_filter)
        wide_dataframes = []

        for ticker, df in self.universe_dfs.items():
            logger.info(f"Extrayendo Features Estacionarios para: {ticker}")

            engineer = QuantFeatureEngineer(data=df, timeframe_minutes=tf_mins)
            feat_df = engineer.process_all_features(benchmark_df=self.benchmark_df)
            feat_df.replace([np.inf, -np.inf], 0.0, inplace=True)

            # Retener features + close (necesario para Triple Barrera downstream)
            feature_cols = engineer.get_feature_columns()
            core_cols = feature_cols + ['close']

            sub_df = feat_df[core_cols].copy()
            sub_df.columns = [f"{ticker}_{c}" for c in sub_df.columns]

            wide_dataframes.append(sub_df)

        # Fusionar todos los sectores horizontalmente
        self.unified_tensor = pd.concat(wide_dataframes, axis=1)

        # Forward fill preserva el último dato conocido para alineación
        self.unified_tensor.ffill(inplace=True)
        self.unified_tensor.dropna(inplace=True)

        logger.info(
            f"Tensor unificado: {self.unified_tensor.shape[0]} filas × "
            f"{self.unified_tensor.shape[1]} columnas"
        )
        return self.unified_tensor
