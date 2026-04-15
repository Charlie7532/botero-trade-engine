import pandas as pd
import numpy as np

class QuantFeatureEngineer:
    """
    Traductor Vectorial de Algoritmos PineScript a Features Continuas de Machine Learning.
    Calcula: Reaper Core (VWAP, Dominio Neto), Q-Delta Kinetics y Sigma-11 Relative Strength.
    """
    
    def __init__(self, data: pd.DataFrame, timeframe_minutes: int):
        # Aseguramos que el Dataframe no sea modificado involuntariamente
        self.df = data.copy()
        
        # Necesario para calcular periodos variables (Ej. rolling 24hs VWAP)
        self.tf_mins = timeframe_minutes
        
    def _mad(self, series: pd.Series, window: int) -> pd.Series:
        """Median Absolute Deviation (MAD) puro, vectorizado."""
        rolling_median = series.rolling(window=window).median()
        abs_deviation = (series - rolling_median).abs()
        # Escala aproximada para asemejarse al standard deviation
        return abs_deviation.rolling(window=window).median() * 1.4826 

    def _safe_division(self, n: pd.Series, d: pd.Series) -> pd.Series:
        return np.where(d != 0, n / d, 0.0)

    def extract_topography_features(self) -> pd.DataFrame:
        """
        Extrae características Topográficas y VWAP Dinámico (Reaper Core).
        CX_Distancia_VWAP.
        """
        # Calcular barras equivalentes a 24 horas usando el Timeframe base
        rolling_bars_24h = max(1, int((24 * 60) / self.tf_mins))
        
        # hlc3 = (high + low + close) / 3
        hlc3 = (self.df['high'] + self.df['low'] + self.df['close']) / 3
        
        # Ponderación Institucional del Reloj Cuántico
        # Ajustamos el volumen basado en la 'Densidad de la Sesión'
        self._apply_quantum_clock()
        
        # VWAP vectorial usando Volumen Ajustado
        vol_price = hlc3 * self.df['quantum_volume']
        rolling_vol_price = vol_price.rolling(window=rolling_bars_24h).sum()
        rolling_volume = self.df['quantum_volume'].rolling(window=rolling_bars_24h).sum()
        
        self.df['session_vwap'] = self._safe_division(rolling_vol_price, rolling_volume)
        
        # Si el volumen es 0, caer hacia el close actual
        self.df['session_vwap'] = np.where(rolling_volume > 0, self.df['session_vwap'], self.df['close'])
        
        # Distancia porcentual al VWAP (CX_Distancia_VWAP)
        self.df['CX_Distancia_VWAP'] = self._safe_division(self.df['close'] - self.df['session_vwap'], self.df['session_vwap']) * 100
        
        return self.df

    def _apply_quantum_clock(self):
        """
        Calcula la franja transaccional de Hora Nueva York y pondera el Volumen.
        Replicación fiel de la función f_get_session_id() y 'density_weight'
        del Multi Frame Quantic V19 PineScript.
        """
        # Asegurar un DateTime Index en formato apropiado
        index_ny = self.df.index
        if index_ny.tz is not None:
             index_ny = index_ny.tz_convert('America/New_York')
             
        hm = index_ny.hour * 100 + index_ny.minute
        
        # Condicionales Vectorizadas para Mapeo de Sesión Oculta
        conditions = [
            (hm >= 400) & (hm < 930),   # 0 -> PRE
            (hm >= 930) & (hm < 1100),  # 1 -> OPEN
            (hm >= 1100) & (hm < 1530), # 2 -> CORE
            (hm >= 1530) & (hm < 1600), # 3 -> POWER
            (hm == 1600),               # 4 -> AUCTION
            (hm > 1600) & (hm < 2000)   # 5 -> AFTER
        ]
        
        density_choices = [0.15, 1.00, 1.00, 1.00, 0.20, 0.25]
        
        # 6 -> NIGHT -> default 0.05
        self.df['session_density'] = np.select(conditions, density_choices, default=0.05)
        
        # Creacion del 'Quantum Volume', que es el volumen real multiplicado
        # por la esperanza institucional de la sesión dictada.
        self.df['quantum_volume'] = self.df['volume'] * self.df['session_density']

    def extract_kinetics(self) -> pd.DataFrame:
        """
        Extracción de Order Flow Simulado Vectorial (Q-Delta V58 y Reaper Core).
        Calcula CX_Intensidad_Total y CX_Dominio_Neto decodificando las velas.
        Aplica los volúmenes del Reloj Cuántico en vez de volúmenes crudos.
        """
        df = self.df
        
        # Geometría pura de Velas
        range_t = np.maximum(df['high'] - df['low'], 1e-6) 
        body_s = (df['close'] - df['open']).abs()
        
        is_green = df['close'] > df['open']
        is_red = df['close'] < df['open']
        
        # Utilizamos el quantum_volume en lugar del volumen bruto comercial
        q_vol = df['quantum_volume']
        
        # Lógica Robusta de Descomposición Vectorial
        av = np.where(is_green, (body_s / range_t) * q_vol, 0)
        ac = ((df['high'] - df[['open', 'close']].max(axis=1)) / range_t) * q_vol
        rv = np.where(is_red, (body_s / range_t) * q_vol, 0)
        rc = ((df[['open', 'close']].min(axis=1) - df['low']) / range_t) * q_vol
        
        # Variables de Machine Learning Base (Raw)
        gross_bull_raw = (av * 0.30) + (ac * 0.45)
        gross_bear_raw = (rv * 0.30) + (rc * 0.45)
        
        df['CX_Intensidad_Total'] = gross_bull_raw + gross_bear_raw
        df['CX_Dominio_Neto'] = gross_bull_raw - gross_bear_raw  # Positivo = Bull Control, Negativo = Bear Control
        
        # Aceleración = Momento del Delta
        df['CX_Aceleracion'] = df['CX_Dominio_Neto'] - df['CX_Dominio_Neto'].shift(1)
        
        return df

    def extract_sigma11_rotation(self, spy_df: pd.DataFrame, z_length: int = 60) -> pd.DataFrame:
        """
        Integra la data relativa contra el Benchmark SPY (Motor Sigma-11).
        Alinea los datos por la capa de tiempo y extrae el Z-Score Relativo (Fuerza).
        """
        # Sincronizar temporalmente el sector local con SPY
        aligned_spy = spy_df.reindex(self.df.index, method='ffill')
        
        ratio = self.df['close'] / aligned_spy['close']
        
        # Calcular Z-Score del ratio
        mean_ratio = ratio.rolling(window=z_length).mean()
        std_ratio = ratio.rolling(window=z_length).std()
        
        self.df['relative_ratio'] = ratio
        self.df['CX_Z_Score_Sector'] = self._safe_division(ratio - mean_ratio, std_ratio)
        
        # BBW (Bollinger Band Width de la fuerza relativa)
        self.df['CX_BBW_Rotacion'] = self._safe_division((4 * std_ratio), mean_ratio) * 100
        
        return self.df

    def process_all_features(self, include_macro: bool = False, spy_df: pd.DataFrame = None) -> pd.DataFrame:
        """Pipeline Ejecutor: De Datos Crudos a Matriz de ML."""
        self.extract_topography_features()
        self.extract_kinetics()
        
        if spy_df is not None:
             self.extract_sigma11_rotation(spy_df)
             
        # Limpiar filas iníciales donde el rolling generó NaNs
        self.df.dropna(inplace=True)
        return self.df

