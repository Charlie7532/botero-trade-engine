import numpy as np
import pandas as pd

class CatalystDetector:
    """
    Tier 3: Detector de sobrerreacciones y catalizadores.
    
    Usa Finviz MCP para screening y datos de precio para detectar
    caídas irracionales en activos con fundamentales sólidos.
    """

    @staticmethod
    def detect_overreaction(
        close_series: pd.Series,
        lookback: int = 20,
        threshold_std: float = 2.5,
    ) -> dict:
        """
        Detecta si un activo sufrió una caída superior a N desviaciones
        estándar en los últimos M períodos.
        
        Returns:
            Dict con is_overreaction, magnitude, y z_score.
        """
        if len(close_series) < lookback + 1:
            return {"is_overreaction": False, "magnitude": 0, "z_score": 0}

        returns = np.log(close_series / close_series.shift(1)).dropna()
        recent_return = returns.iloc[-1]
        mean_ret = returns.iloc[-lookback:].mean()
        std_ret = returns.iloc[-lookback:].std()

        if std_ret < 1e-10:
            return {"is_overreaction": False, "magnitude": 0, "z_score": 0}

        z_score = (recent_return - mean_ret) / std_ret

        return {
            "is_overreaction": z_score < -threshold_std,
            "magnitude": float(recent_return),
            "z_score": float(z_score),
        }
