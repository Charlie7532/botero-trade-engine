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
    resuelve los Features Quánticos, y genera un Tensor Múltiple para LSTMs/Transformers.
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
        Escanea recursivamente el directorio buscando ETFs que coincidan con la temporalidad elegida.
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
                
        logger.info(f"Universo Cargado. Benchmark: {self.benchmark_ticker}. Sectores: {list(self.universe_dfs.keys())}")

    def build_feature_tensor(self) -> pd.DataFrame:
        """
        Calcula las 'Features' relativas de cada sector frente al Benchmark y
        las apila en un único DataFrame (MultiIndex).
        """
        if self.benchmark_df is None:
            raise ValueError("El Benchmark (SPX/SPY) no fue cargado correctamente.")
            
        wide_dataframes = []
        
        for ticker, df in self.universe_dfs.items():
            logger.info(f"Extrayendo Features Secuenciales para: {ticker}")
            
            engineer = QuantFeatureEngineer(data=df, timeframe_minutes=75)
            feat_df = engineer.process_all_features(spy_df=self.benchmark_df)
            feat_df.replace([np.inf, -np.inf], 0.0, inplace=True)
            
            # Solo retener las variables cuánticas deseadas para no llenar la RAM con OHLC repetidos
            core_cols = ['CX_Distancia_VWAP', 'CX_Intensidad_Total', 'CX_Dominio_Neto', 'CX_Z_Score_Sector', 'CX_Aceleracion', 'quantum_volume', 'CX_BBW_Rotacion', 'close']
            
            # Sub-seleccionar y añadir el prefijo para no colapsar columnas
            sub_df = feat_df[core_cols].copy()
            sub_df.columns = [f"{ticker}_{c}" for c in sub_df.columns]
            
            wide_dataframes.append(sub_df)
            
        # Fusionar todos los sectores horizontalmente (Cruce Espacial)
        # pd.concat(axis=1) alinea matemáticamente por el Index (Fecha-Hora). Los huecos son normales.
        self.unified_tensor = pd.concat(wide_dataframes, axis=1)
        
        # Eliminar huecos de sincronizacion inicial y días donde un ETF no operó
        # Forward fill preserva el último precio/dato conocido para alinearlo en la gran matriz
        self.unified_tensor.ffill(inplace=True)
        self.unified_tensor.dropna(inplace=True)
        return self.unified_tensor
