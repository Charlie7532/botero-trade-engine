import pandas as pd
import numpy as np
import vectorbt as vbt
import logging

from backend.infrastructure.data_providers.tradingview_parser import TradingViewParser
from backend.application.feature_engineering import QuantFeatureEngineer
from backend.application.ai_orchestrator import RegimeDetector, QuantSMC_MetaModel
from backend.domain.entities import Portfolio
from backend.application.risk_manager import RiskManager

logger = logging.getLogger(__name__)

class QuantBacktester:
    """
    Simulador OOS (Out of Sample) Institucional.
    Usa vectorbt para cruzar las predicciones del XGBoost con las comisiones
    del mundo real y el Kelly Sizing fraccional.
    """
    def __init__(self, initial_capital: float = 100_000.0, commission: float = 0.001):
        self.initial_capital = initial_capital
        self.commission = commission
        
        # Subsistemas
        self.parser = TradingViewParser(target_timezone="America/New_York")
        self.regime_detector = RegimeDetector(n_regimes=3)
        self.ml_model = QuantSMC_MetaModel()
        
        # El gestor de Riesgo y Portafolio nativo se delega enteramente a VectorBT
        # en la fase execute_simulation para simulación al milisegundo.
        
    def execute_simulation(self, benchmark_csv_path: str, asset_csv_path: str, train_ratio: float = 0.7):
        """Pipeline que emula todo el trayecto desde los CSV a los Resultados Financieros"""
        logger.info("1. Cargando Datos y Alineando Tiempo...")
        spy_df = self.parser.parse_csv(benchmark_csv_path)
        asset_df = self.parser.parse_csv(asset_csv_path)
        
        logger.info("2. Engineering Features Quantamentales...")
        engineer = QuantFeatureEngineer(data=asset_df, timeframe_minutes=75) # asumiendo 75m
        features_df = engineer.process_all_features(spy_df=spy_df)
        
        core_features = ['CX_Distancia_VWAP', 'CX_Intensidad_Total', 'CX_Dominio_Neto', 'CX_Z_Score_Sector', 'CX_Aceleracion']
        
        logger.info("3. Modelado de Regímenes y Entrenamiento...")
        features_df['HMM_Regime'] = self.regime_detector.fit_predict(features_df, ['CX_Distancia_VWAP', 'CX_Z_Score_Sector'])
        core_features.append('HMM_Regime')
        
        ml_dataset = self.ml_model.prepare_target(features_df.copy(), prediction_horizon=1)
        
        # Separar en In-Sample (IS/Train) y Out-of-Sample (OOS/Test)
        split_idx = int(len(ml_dataset) * train_ratio)
        train_df = ml_dataset.iloc[:split_idx]
        test_df = ml_dataset.iloc[split_idx:]
        
        # Entrenar solo con el pasado (Train)
        self.ml_model.train(train_df, features=core_features)
        
        # Predecir sobre el futuro (Test - Out of Sample)
        logger.info("4. Simulando Predicciones Out-of-Sample (El Futuro)...")
        # .predict_proba requiere un DF con los feature_cols
        X_test = test_df[self.ml_model.feature_names]
        probabilities = self.ml_model.predict_probability(X_test)
        
        # --- VECTORIZATION PARA VECTORBT ---
        # Definición estricta de señales: Entrar solo si XGBoost dicta > 55% de Probabilidad
        # Salir/Vender en la barra siguiente (Swing muy corto para la prueba de concepto)
        
        entries = probabilities > 0.55
        exits = np.roll(entries, shift=1) # Vendemos 1 vela después de comprar
        exits[0] = False
        
        entries_series = pd.Series(entries, index=test_df.index)
        exits_series = pd.Series(exits, index=test_df.index)
        
        logger.info("5. VectorBT Ledger Execution...")
        
        # Extraer el precio Close correspondiente a nuestro test OOS
        price_series = test_df['close']
        
        # Construir Portafolio Vectorizado de vbt
        vbt_portfolio = vbt.Portfolio.from_signals(
            close=price_series,
            entries=entries_series,
            exits=exits_series,
            init_cash=self.initial_capital,
            fees=self.commission,
            freq='75t', # 75 minutos
            direction='longonly',
            # Simular Kelly fraccional simple asignando 10% de la cuenta por trade
            size=0.10, 
            size_type='percent' 
        )
        
        return vbt_portfolio

