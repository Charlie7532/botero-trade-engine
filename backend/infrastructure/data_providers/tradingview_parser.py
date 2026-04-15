import pandas as pd
import numpy as np
import logging
from pathlib import Path
from typing import Union, Optional

logger = logging.getLogger(__name__)

class TradingViewParser:
    """
    Motor Institucional de Ingesta Vectorizada para Archivos CSV de TradingView.
    Diseñado para cargar, limpiar y preparar millones de filas para VectorBT y Modelos de ML.
    """
    
    # Mapeo estándar de columnas comunes de exportación de TV a nombres estandarizados
    STANDARD_COLUMNS_MAP = {
        'time': 'datetime',
        'Time': 'datetime',
        'Date': 'datetime',
        'open': 'open',
        'Open': 'open',
        'high': 'high',
        'High': 'high',
        'low': 'low',
        'Low': 'low',
        'close': 'close',
        'Close': 'close',
        'Volume': 'volume',
        'vol': 'volume',
        'Volume MA': 'volume_ma',
    }

    def __init__(self, target_timezone: str = "America/New_York"):
        """
        Args:
            target_timezone: La zona horaria a la que se normalizarán todos los datos.
                             Crítico para los cálculos estacionales de la sesión (ej. Q-Delta).
        """
        self.target_timezone = target_timezone
        self.REQUIRED_COLS = ['open', 'high', 'low', 'close', 'volume']

    def parse_csv(self, file_path: Union[str, Path]) -> pd.DataFrame:
        """
        Lee un archivo CSV de TradingView y lo vectoriza en un DataFrame de Alta Performance.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"El archivo CSV no existe en la ruta: {path}")

        logger.info(f"Ingestando datos desde: {path.name}")
        
        try:
            # Lectura inicial detectando el formato de tiempo automáticamente
            df = pd.read_csv(path)
            
            # Renombrar columnas a formato estándar en minúsculas
            df.rename(columns=self.STANDARD_COLUMNS_MAP, inplace=True)
            
            # Verificar integridad de columnas
            missing_cols = [col for col in self.REQUIRED_COLS if col not in df.columns]
            if missing_cols:
                raise ValueError(f"El CSV carece de columnas obligatorias: {missing_cols}. Columnas encontradas: {df.columns.tolist()}")

            # Vectorización y Localización del Índice de Tiempo
            if 'datetime' in df.columns:
                # Comprobar si es un formato UNIX timestamp (Enteros grandes)
                if pd.api.types.is_numeric_dtype(df['datetime']):
                    df['datetime'] = pd.to_datetime(df['datetime'], unit='s')
                else:
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    
                # Manejo avanzado de Timezones
                if df['datetime'].dt.tz is None:
                    # Asumimos UTC por defecto si no tiene, luego pasamos al objetivo local
                    df['datetime'] = df['datetime'].dt.tz_localize('UTC').dt.tz_convert(self.target_timezone)
                else:
                    df['datetime'] = df['datetime'].dt.tz_convert(self.target_timezone)
                
                df.set_index('datetime', inplace=True)
            else:
                logger.warning("No se encontró columna 'time' explícita. El índice no estará en formato DatetimeTZ.")

            # Limpiar ruidos o NaNs provocados por paradas en la data de TV
            self._clean_data(df)

            # Optimización de Memoria para procesamiento masivo
            self._optimize_memory(df)
            
            logger.info(f"Ingesta exitosa: {len(df)} filas indexadas. Rango temporal: {df.index.min()} -> {df.index.max()}")
            return df

        except Exception as e:
            logger.error(f"Fallo críttico durante la ingesta del CSV: {e}")
            raise

    def _clean_data(self, df: pd.DataFrame):
        """
        Limpieza institucional: Remueve filas basura, imputa forward-fill en gaps microscópicos y
        se asegura de que no hay voluménes negativos.
        """
        # Eliminar filas donde el precio Close es nulo (Corrupción de datos)
        df.dropna(subset=['close'], inplace=True)
        
        # Llenar huecos de volumen con 0 en periodos sin liquidez (Extended Hours)
        if 'volume' in df.columns:
            df['volume'] = df['volume'].fillna(0.0)
            # Asegurar que no existan valores extraños
            df['volume'] = df['volume'].clip(lower=0.0)
            
        # Llenar huecos de precio usando ffill (El último precio cotizado sigue siendo válido)
        df.ffill(inplace=True)

    def _optimize_memory(self, df: pd.DataFrame):
        """
        Downcasting vectorizado para ahorrar hasta 50% de RAM, esencial para 
        modelos XGBoost y simulaciones VectorBT simultaneas.
        """
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], downcast='float')
