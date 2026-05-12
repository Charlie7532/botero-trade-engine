import abc
from typing import Dict, Any

class MLDataPort(abc.ABC):
    """
    Port para almacenar vectores de características (X) y etiquetas (y)
    generados por el entorno forense y el OracleBacktester.
    """
    
    @abc.abstractmethod
    def save_ml_feature_and_label(
        self,
        feature_record: Dict[str, Any],
        label_record: Dict[str, Any]
    ) -> None:
        """
        Almacena un par (X, y) en el Data Lake.
        
        Args:
            feature_record: Diccionario con los datos para engine.ml_features.
                Debe contener 'id' (UUID), 'ticker', 'timeframe', 'signal_name', 
                'signal_time' y 'features' (dict).
            label_record: Diccionario con los datos para engine.ml_labels.
                Debe contener 'feature_id' (mismo UUID), 'label', 'return_pct',
                'bars_held', 'exit_time' y 'geometry_used' (dict).
        """
        pass

    @abc.abstractmethod
    def save_ml_batch(
        self,
        feature_records: list,
        label_records: list
    ) -> None:
        """
        Batch insert de pares (X, y) para reducir round-trips a Neon.
        """
        pass
