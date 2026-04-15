import pandas as pd
import numpy as np
import torch
from torch.utils.data import Dataset
import logging

logger = logging.getLogger(__name__)

class TripleBarrierLabeler:
    """
    Etiquetado Institucional de Riesgo-Beneficio (Marcos de López de Prado).
    Ignora la predicción de la próxima vela. Etiqueta según tres barreras futuras:
    1. Barrera Superior (Take Profit Volátil)
    2. Barrera Inferior (Stop Loss Dinámico)
    3. Barrera Vertical (Timeout temporal)
    """
    def __init__(self, profit_factor: float = 2.0, loss_factor: float = 1.0, max_bars: int = 30):
        self.pt_mult = profit_factor
        self.sl_mult = loss_factor
        self.max_bars = max_bars

    def apply_barriers(self, df: pd.DataFrame, target_ticker: str) -> pd.DataFrame:
        """
        Devuelve el dataframe con dos columnas nuevas:
        'target_SMC': 1 (Éxito Toro), 0 (Fallo, Stop-Loss o Timeout)
        'execution_horizon': Barras requeridas para tocar barrera.
        Evaluando el Ticker objetivo en la matriz cruzada conjunta.
        """
        logger.info(f"Computando Triple Barrera (Labeling Cuántico) sobre objetivo {target_ticker}...")
        
        close_col = f"{target_ticker}_close"
        vol_col = f"{target_ticker}_CX_BBW_Rotacion"
        
        if close_col not in df.columns or vol_col not in df.columns:
             raise ValueError(f"Las columnas necesarias para {target_ticker} no existen en el df cruzado.")
        
        # Volatilidad base
        base_vol = df[vol_col].replace(0, 0.001) / 100.0
        
        pt_levels = df[close_col] * (1 + (base_vol * self.pt_mult))
        sl_levels = df[close_col] * (1 - (base_vol * self.sl_mult))
        
        closes = df[close_col].values
        pts = pt_levels.values
        sls = sl_levels.values
        
        n = len(df)
        labels = np.zeros(n, dtype=int)
        horizons = np.zeros(n, dtype=int)
        
        # Vectorización sobre el horizonte temporal T+N
        for i in range(n):
            if i + 1 >= n:
                continue
                
            # Fin del universo para esta ventana
            end_idx = min(n, i + self.max_bars + 1)
            future_window = closes[i+1:end_idx]
            
            # Busqueda de eventos (Cruces)
            pt_hits = future_window >= pts[i]
            sl_hits = future_window <= sls[i]
            
            # Detectar el primer índice (argmax devuelve el primero si hay múltiples True)
            first_pt_idx = np.argmax(pt_hits) if np.any(pt_hits) else float('inf')
            first_sl_idx = np.argmax(sl_hits) if np.any(sl_hits) else float('inf')
            
            if first_pt_idx < first_sl_idx and first_pt_idx != float('inf'):
                # Ganaron los toros. Tocaron el Take Profit antes del Stop-Loss
                labels[i] = 1
                horizons[i] = first_pt_idx + 1
            elif first_sl_idx <= first_pt_idx and first_sl_idx != float('inf'):
                # Ganaron los osos / Trampa / ChoCh Fallido. Stop-Loss golpeado.
                labels[i] = 0
                horizons[i] = first_sl_idx + 1
            else:
                # Time-Out (Barrera Vertical)
                labels[i] = 0
                horizons[i] = self.max_bars
                
        df['target_SMC'] = labels
        df['execution_horizon'] = horizons
        
        # Descartar las últimas N barras porque el marco futuro es desconocido
        # Evita Look-Ahead Bias severo
        df = df.iloc[:-self.max_bars].copy()
        
        win_rate_teorico = df['target_SMC'].mean()
        logger.info(f"Targeting SMC generado. Base Probability asimétrica calculada: {win_rate_teorico*100:.2f}%")
        return df

class QuantSequenceDataset(Dataset):
    """
    Dataset Vectorial Institucional en Pytorch.
    Transforma el DataFrame transversal en secuencias de "Ventana Deslizante" (La Película).
    Dimensión generada: (Batch, Sequence_Length, Features).
    """
    def __init__(self, df: pd.DataFrame, sequence_length: int = 30, feature_cols: list = None, target_col: str = 'target_SMC'):
        if feature_cols is None:
            raise ValueError("Debes especificar la matriz de features Cuantamentales a utilizar.")
            
        self.sequence_length = sequence_length
        self.features = df[feature_cols].values
        self.targets = df[target_col].values
        
        # Validar consistencia
        if len(self.features) < sequence_length:
            raise ValueError("El Dataset es más pequeño que el Sequence Length deseado.")

    def __len__(self):
        # Descontamos el Sequence Length porque la primera secuencia útil empieza en la fila X
        return len(self.features) - self.sequence_length

    def __getitem__(self, idx):
        # Obtener la película (Ventana)
        # Ejemplo: desde la barra 0 hasta la 30
        x_seq = self.features[idx : idx + self.sequence_length]
        
        # La etiqueta y_target pertenece al evento de disparar AL CULMINAR la ventana
        # Es decir, la predicción basada en los últimos N bloques.
        y_label = self.targets[idx + self.sequence_length - 1]
        
        return torch.tensor(x_seq, dtype=torch.float32), torch.tensor(y_label, dtype=torch.float32)
