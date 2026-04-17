"""
TICKER QUALIFIER: Pre-Trade Fitness Test
==========================================
Antes de operar un ticker, el sistema ejecuta un mini Walk-Forward
para determinar si tenemos EDGE en ese instrumento específico.

Si el ticker no pasa el test, NO SE OPERA. Punto.

Incluye modelado realista de costos de ejecución:
- Bid-Ask Spread estimado (mínimo 1 centavo, adaptivo según volatilidad)
- Latency Drift: 0.5-2 segundos entre señal y fill
- Market Impact: función del volumen relativo de nuestra orden
"""
import logging
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score
from dataclasses import dataclass
from typing import Optional
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

import sys
sys.path.insert(0, '/root/botero-trade')

from backend.application.feature_engineering import QuantFeatureEngineer
from backend.application.sequence_modeling import (
    TripleBarrierLabeler, MetaLabeler, SampleWeighter, QuantSequenceDataset
)
from backend.application.lstm_model import QuantInstitutionalLSTM

logger = logging.getLogger(__name__)


@dataclass
class ExecutionDrift:
    """
    Modelo realista de costos de ejecución.
    
    Componentes del drift total:
    1. Bid-Ask Spread: Spread/2 por lado (entry + exit = spread completo)
    2. Latency Slippage: Precio se mueve mientras la orden viaja
    3. Market Impact: Nuestra orden mueve el precio (solo para posiciones grandes)
    """
    avg_spread_pct: float = 0.05    # 5 bps default (adaptivo)
    latency_drift_pct: float = 0.02  # 2 bps por latencia
    market_impact_pct: float = 0.01  # 1 bp para posiciones <$50K
    
    @property
    def total_cost_per_trade_pct(self) -> float:
        """Costo total por trade (ida + vuelta)."""
        return (self.avg_spread_pct + self.latency_drift_pct + self.market_impact_pct) * 2
    
    @classmethod
    def estimate_from_data(cls, df: pd.DataFrame, avg_price: float) -> 'ExecutionDrift':
        """
        Estima el drift desde datos reales.
        
        Bid-Ask Spread real por categoría (datos empíricos):
        - SPY, QQQ, IWM:   ~$0.01 spread = 0.002% (1-2 bps)
        - IBIT, XLK, XLF:  ~$0.02-0.05 = 0.01-0.03% (3-8 bps)
        - Stock individual: ~$0.03-0.15 = 0.02-0.10% (5-20 bps)
        - Low liquidity:    ~$0.10-0.50 = 0.10-0.30% (20-50 bps)
        
        Usamos: spread_pct = min_spread_dollars / avg_price
        Escala con liquidez: más volumen = spread más tight
        """
        if 'volume' not in df.columns or avg_price <= 0:
            return cls()
        
        avg_vol = df['volume'].mean()
        
        # Spread basado en penny increments reales
        # $0.01 mínimo por regulación SEC para stocks >$1
        if avg_vol > 20_000_000:       # Ultra líquido (SPY: 80M+ diario)
            spread_dollars = 0.01       # 1 centavo
        elif avg_vol > 5_000_000:      # Muy líquido
            spread_dollars = 0.02
        elif avg_vol > 1_000_000:      # Líquido (IBIT, XLK)
            spread_dollars = 0.03
        elif avg_vol > 100_000:        # Medium
            spread_dollars = 0.08
        else:                           # Bajo volumen
            spread_dollars = 0.25
        
        spread_pct = (spread_dollars / avg_price) * 100  # Como porcentaje
        
        # Latency slippage: ~1-2 centavos de movimiento en 0.5-1 segundos
        # Para activos volátiles (crypto ETFs), puede ser mayor
        atr_per_bar = (df['high'] - df['low']).mean()
        # Asumimos 1 segundo de latencia, y una barra de 1h = 3600 segundos
        # Movimiento por segundo ≈ ATR / sqrt(3600)
        move_per_second = atr_per_bar / (3600 ** 0.5)
        latency_dollars = move_per_second * 1.5  # 1.5 segundos de latencia
        latency_pct = (latency_dollars / avg_price) * 100
        latency_pct = max(0.001, min(latency_pct, 0.05))  # Cap en 5 bps
        
        return cls(
            avg_spread_pct=round(spread_pct, 4),
            latency_drift_pct=round(latency_pct, 4),
            market_impact_pct=0.005,  # 0.5 bps para posiciones <$50K
        )


@dataclass
class QualificationResult:
    """Resultado del fitness test de un ticker."""
    ticker: str
    timeframe: str
    qualified: bool
    grade: str              # A, B, C, D, F
    edge_score: float       # 0-100
    
    # Métricas de backtest
    lstm_wr: float
    xgb_wr: float
    baseline_wr: float
    ev_lstm: float
    ev_xgb: float
    n_trades: int
    n_bars: int
    
    # Costos
    drift: ExecutionDrift
    ev_after_costs: float
    
    # Calibración óptima
    optimal_model: str       # 'lstm', 'xgboost', 'ensemble'
    optimal_payoff: float
    optimal_seq_len: int
    
    # Montecarlo
    mc_median: float
    mc_p5: float
    mc_p95: float
    mc_pct_profitable: float
    
    reason: str


class TickerQualifier:
    """
    Motor de Calificación Pre-Trade.
    
    Para cada ticker/timeframe ejecuta:
    1. Descarga de datos
    2. Feature engineering
    3. Walk-Forward mini (2-3 folds)
    4. Estimación de drift
    5. Montecarlo con costos reales
    6. Calificación final (A-F)
    
    Solo los tickers con grado B o superior son operables.
    """
    
    # Grading thresholds
    GRADE_A = 70  # Edge excepcional
    GRADE_B = 55  # Edge operable
    GRADE_C = 40  # Marginal, no operar
    GRADE_D = 25  # Sin edge
    # Below D = F
    
    TIMEFRAME_MAP = {
        '1h': {'interval': '1h', 'period': '2y', 'tf_min': 60, 'bars_day': 7},
        '4h': {'interval': '1h', 'period': '2y', 'tf_min': 240, 'bars_day': 2},
        '75m': {'interval': '1h', 'period': '2y', 'tf_min': 75, 'bars_day': 5},
        '1d': {'interval': '1d', 'period': '10y', 'tf_min': 1440, 'bars_day': 1},
    }
    
    def __init__(self):
        self.results_cache = {}
    
    def qualify(
        self,
        ticker: str,
        timeframe: str = '1h',
        min_bars: int = 500,
    ) -> QualificationResult:
        """
        Ejecuta el fitness test completo para un ticker.
        """
        cache_key = f"{ticker}_{timeframe}"
        if cache_key in self.results_cache:
            logger.info(f"Cache hit: {cache_key}")
            return self.results_cache[cache_key]
        
        print(f"\n{'='*60}")
        print(f"  QUALIFICATION TEST: {ticker} @ {timeframe}")
        print(f"{'='*60}")
        
        # 1. Descargar datos
        tf_config = self.TIMEFRAME_MAP.get(timeframe, self.TIMEFRAME_MAP['1h'])
        df = self._download_data(ticker, tf_config)
        
        if df is None or len(df) < min_bars:
            result = QualificationResult(
                ticker=ticker, timeframe=timeframe, qualified=False,
                grade='F', edge_score=0, lstm_wr=0, xgb_wr=0,
                baseline_wr=0, ev_lstm=0, ev_xgb=0, n_trades=0,
                n_bars=len(df) if df is not None else 0,
                drift=ExecutionDrift(), ev_after_costs=0,
                optimal_model='none', optimal_payoff=0, optimal_seq_len=0,
                mc_median=0, mc_p5=0, mc_p95=0, mc_pct_profitable=0,
                reason=f"Datos insuficientes: {len(df) if df is not None else 0} < {min_bars}",
            )
            self.results_cache[cache_key] = result
            return result
        
        print(f"  → {len(df)} barras cargadas ({df.index[0]} → {df.index[-1]})")
        
        # 2. Estimar drift de ejecución
        avg_price = df['close'].mean()
        drift = ExecutionDrift.estimate_from_data(df, avg_price)
        print(f"  → Drift estimado: {drift.total_cost_per_trade_pct*100:.2f}% por trade")
        print(f"    Spread: {drift.avg_spread_pct*100:.3f}% | Latency: {drift.latency_drift_pct*100:.3f}% | Impact: {drift.market_impact_pct*100:.3f}%")
        
        # 3. Feature engineering
        tf_min = tf_config['tf_min']
        if timeframe == '4h':
            # Resamplear a 4h
            df = df.resample('4h').agg({
                'open': 'first', 'high': 'max', 'low': 'min',
                'close': 'last', 'volume': 'sum',
            }).dropna()
            print(f"  → Resampleado a 4h: {len(df)} barras")
        
        engineer = QuantFeatureEngineer(data=df, timeframe_minutes=tf_min)
        df = engineer.process_all_features(d_price=0.4, d_volume=0.6)
        feature_cols = engineer.get_feature_columns()
        print(f"  → {len(feature_cols)} features")
        
        # 4. Labels - testear múltiples payoff ratios
        best_payoff = 1.5
        best_ev = -999
        
        for payoff in [1.5, 2.0, 2.5]:
            max_bars_label = 10 if tf_min <= 60 else 15 if tf_min <= 240 else 20
            labeler = TripleBarrierLabeler(
                profit_mult=payoff, loss_mult=1.0, max_bars=max_bars_label
            )
            test_df = labeler.apply_barriers(df.copy(), close_col='close')
            test_df = MetaLabeler.generate_primary_signals(test_df, momentum_lookback=10)
            test_df = MetaLabeler.apply_metalabels(test_df)
            test_df = test_df[test_df['meta_target'].notna()]
            
            if len(test_df) > 0:
                wr_est = test_df['meta_target'].mean()
                ev_est = (wr_est * payoff) - (1 - wr_est)
                if ev_est > best_ev:
                    best_ev = ev_est
                    best_payoff = payoff
        
        print(f"  → Payoff óptimo: {best_payoff}:1 (EV cruda: {best_ev:+.3f})")
        
        # 5. Walk-Forward con payoff óptimo
        max_bars_label = 10 if tf_min <= 60 else 15 if tf_min <= 240 else 20
        labeler = TripleBarrierLabeler(
            profit_mult=best_payoff, loss_mult=1.0, max_bars=max_bars_label
        )
        df = labeler.apply_barriers(df, close_col='close')
        df = MetaLabeler.generate_primary_signals(df, momentum_lookback=10)
        df = MetaLabeler.apply_metalabels(df)
        weights = SampleWeighter.compute_sample_weights(df)
        df['sample_weight'] = weights
        df = df[df['meta_target'].notna()].copy()
        
        if len(df) < min_bars:
            result = QualificationResult(
                ticker=ticker, timeframe=timeframe, qualified=False,
                grade='F', edge_score=0, lstm_wr=0, xgb_wr=0,
                baseline_wr=0, ev_lstm=0, ev_xgb=0, n_trades=0,
                n_bars=len(df), drift=drift, ev_after_costs=0,
                optimal_model='none', optimal_payoff=best_payoff,
                optimal_seq_len=0, mc_median=0, mc_p5=0, mc_p95=0,
                mc_pct_profitable=0,
                reason=f"Señales insuficientes después de labeling: {len(df)}",
            )
            self.results_cache[cache_key] = result
            return result
        
        # Walk-Forward
        SEQ = 15 if tf_min <= 60 else 20 if tf_min <= 240 else 30
        TRAIN = int(len(df) * 0.6)
        TEST = int(len(df) * 0.25)
        PURGE = max(10, int(len(df) * 0.05))
        
        wf_results = self._walk_forward(
            df, feature_cols, SEQ, TRAIN, TEST, PURGE, best_payoff
        )
        
        if not wf_results:
            result = QualificationResult(
                ticker=ticker, timeframe=timeframe, qualified=False,
                grade='F', edge_score=0, lstm_wr=0, xgb_wr=0,
                baseline_wr=0, ev_lstm=0, ev_xgb=0, n_trades=0,
                n_bars=len(df), drift=drift, ev_after_costs=0,
                optimal_model='none', optimal_payoff=best_payoff,
                optimal_seq_len=SEQ, mc_median=0, mc_p5=0, mc_p95=0,
                mc_pct_profitable=0, reason="Walk-Forward falló",
            )
            self.results_cache[cache_key] = result
            return result
        
        # 6. Calcular métricas con costos
        rdf = pd.DataFrame(wf_results)
        lstm_wr = rdf['lstm'].mean()
        xgb_wr = rdf['gb'].mean()
        base_wr = rdf['base'].mean()
        
        ev_lstm_raw = (lstm_wr * best_payoff) - (1 - lstm_wr)
        ev_xgb_raw = (xgb_wr * best_payoff) - (1 - xgb_wr)
        
        # Deducir drift
        drift_cost = drift.total_cost_per_trade_pct
        ev_lstm_net = ev_lstm_raw - drift_cost
        ev_xgb_net = ev_xgb_raw - drift_cost
        
        # Elegir mejor modelo
        if ev_xgb_net > ev_lstm_net and ev_xgb_net > 0:
            best_model = 'xgboost'
            best_wr = xgb_wr
            best_ev_net = ev_xgb_net
        elif ev_lstm_net > 0:
            best_model = 'lstm'
            best_wr = lstm_wr
            best_ev_net = ev_lstm_net
        else:
            best_model = 'none'
            best_wr = max(lstm_wr, xgb_wr)
            best_ev_net = max(ev_lstm_net, ev_xgb_net)
        
        n_trades = int(rdf.get('n_trades', pd.Series([0])).sum())
        
        # 7. Edge Score (0-100)
        edge_components = []
        
        # WR component (0-40 pts)
        wr_above_base = (best_wr - base_wr) * 100
        edge_components.append(min(40, max(0, wr_above_base * 4)))
        
        # EV after costs (0-30 pts)
        if best_ev_net > 0:
            edge_components.append(min(30, best_ev_net * 50))
        else:
            edge_components.append(0)
        
        # Consistency: % folds positivos (0-20 pts)
        if best_model == 'xgboost':
            folds_pos = (rdf['ev_gb'] > 0).mean()
        else:
            folds_pos = (rdf['ev_lstm'] > 0).mean()
        edge_components.append(folds_pos * 20)
        
        # Trade count bonus (0-10 pts)
        edge_components.append(min(10, n_trades / 10))
        
        edge_score = sum(edge_components)
        
        # Grade
        if edge_score >= self.GRADE_A:
            grade = 'A'
        elif edge_score >= self.GRADE_B:
            grade = 'B'
        elif edge_score >= self.GRADE_C:
            grade = 'C'
        elif edge_score >= self.GRADE_D:
            grade = 'D'
        else:
            grade = 'F'
        
        qualified = grade in ('A', 'B')
        
        # 8. Montecarlo con costos
        mc = self._montecarlo(best_wr, best_payoff, drift_cost, n_trades)
        
        reason_parts = []
        if qualified:
            reason_parts.append(f"QUALIFIED ({grade}): Edge de {best_model} con EV neta +{best_ev_net:.4f}")
        else:
            if best_ev_net <= 0:
                reason_parts.append(f"REJECTED: EV neta {best_ev_net:.4f} (negativa después de costos)")
            else:
                reason_parts.append(f"MARGINAL ({grade}): Edge insuficiente ({edge_score:.0f}/100)")
        
        result = QualificationResult(
            ticker=ticker, timeframe=timeframe, qualified=qualified,
            grade=grade, edge_score=round(edge_score, 1),
            lstm_wr=round(lstm_wr, 4), xgb_wr=round(xgb_wr, 4),
            baseline_wr=round(base_wr, 4),
            ev_lstm=round(ev_lstm_net, 4), ev_xgb=round(ev_xgb_net, 4),
            n_trades=n_trades, n_bars=len(df), drift=drift,
            ev_after_costs=round(best_ev_net, 4),
            optimal_model=best_model, optimal_payoff=best_payoff,
            optimal_seq_len=SEQ,
            mc_median=mc['median'], mc_p5=mc['p5'], mc_p95=mc['p95'],
            mc_pct_profitable=mc['pct_profitable'],
            reason='; '.join(reason_parts),
        )
        
        self.results_cache[cache_key] = result
        self._print_report(result)
        return result
    
    def _download_data(self, ticker: str, tf_config: dict) -> Optional[pd.DataFrame]:
        """Descarga datos via yfinance."""
        try:
            dl = yf.download(
                ticker,
                period=tf_config['period'],
                interval=tf_config['interval'],
                progress=False,
            )
            if dl.empty:
                return None
            if isinstance(dl.columns, pd.MultiIndex):
                dl.columns = dl.columns.get_level_values(0)
            df = pd.DataFrame({
                'open': dl['Open'], 'high': dl['High'],
                'low': dl['Low'], 'close': dl['Close'],
                'volume': dl['Volume'],
            })
            df.index.name = 'datetime'
            df.dropna(inplace=True)
            return df
        except Exception as e:
            logger.error(f"Error descargando {ticker}: {e}")
            return None
    
    def _walk_forward(self, df, feature_cols, seq, train_size, test_size, purge, payoff):
        """Mini Walk-Forward (2-3 folds)."""
        total = len(df)
        n_folds = max(1, (total - train_size - purge) // test_size)
        n_folds = min(n_folds, 3)  # Max 3 folds para velocidad
        
        results = []
        for fold in range(n_folds):
            ts = fold * test_size
            te = ts + train_size
            vs = te + purge
            ve = min(vs + test_size, total)
            if ve <= vs or vs >= total:
                break
            
            df_train = df.iloc[ts:te].copy()
            df_test = df.iloc[vs:ve].copy()
            
            X_train = df_train[feature_cols].values.astype(np.float32)
            y_train = df_train['meta_target'].values.astype(np.float32)
            w_train = df_train['sample_weight'].values.astype(np.float32)
            X_test = df_test[feature_cols].values.astype(np.float32)
            y_test = df_test['meta_target'].values.astype(np.float32)
            
            majority = int(y_train.mean() >= 0.5)
            base_wr = accuracy_score(y_test, np.full(len(y_test), majority))
            
            # XGBoost
            try:
                gb = GradientBoostingClassifier(
                    n_estimators=80, max_depth=3, learning_rate=0.1,
                    subsample=0.8, random_state=42,
                )
                gb.fit(X_train, y_train.astype(int), sample_weight=w_train)
                gb_preds = gb.predict(X_test)
                gb_wr = accuracy_score(y_test, gb_preds)
                gb_trades = int(gb_preds.sum())
            except:
                gb_wr = base_wr
                gb_trades = 0
            
            # LSTM
            try:
                train_ds = QuantSequenceDataset(
                    df_train, seq, feature_cols, 'meta_target', 'sample_weight',
                )
                train_dl = DataLoader(train_ds, batch_size=32, shuffle=True)
                
                model = QuantInstitutionalLSTM(
                    input_dim=len(feature_cols), hidden_dim=48,
                    num_layers=2, dropout=0.3,
                )
                opt = torch.optim.Adam(model.parameters(), lr=1e-3)
                crit = nn.BCELoss(reduction='none')
                
                model.train()
                for ep in range(15):
                    for xb, yb, wb in train_dl:
                        opt.zero_grad()
                        loss = (crit(model(xb), yb) * wb).mean()
                        loss.backward()
                        opt.step()
                
                test_ds = QuantSequenceDataset(
                    df_test, seq, feature_cols, 'meta_target', 'sample_weight',
                )
                test_dl = DataLoader(test_ds, batch_size=32, shuffle=False)
                
                model.eval()
                preds, trues = [], []
                with torch.no_grad():
                    for xb, yb, _ in test_dl:
                        p = model(xb)
                        preds.extend((p.numpy() >= 0.5).astype(int))
                        trues.extend(yb.numpy())
                lstm_wr = accuracy_score(trues, preds)
                lstm_trades = int(sum(preds))
            except Exception as e:
                print(f"    LSTM error fold {fold+1}: {e}")
                lstm_wr = base_wr
                lstm_trades = 0
            
            ev = lambda wr: (wr * payoff) - (1 - wr)
            results.append({
                'fold': fold+1, 'base': base_wr, 'gb': gb_wr, 'lstm': lstm_wr,
                'ev_base': ev(base_wr), 'ev_gb': ev(gb_wr), 'ev_lstm': ev(lstm_wr),
                'n_trades': max(gb_trades, lstm_trades),
            })
            
            print(f"    Fold {fold+1}: Base={base_wr*100:.1f}% XGB={gb_wr*100:.1f}% LSTM={lstm_wr*100:.1f}%")
        
        return results
    
    def _montecarlo(self, wr, payoff, drift_cost, n_trades, sims=1000):
        """Montecarlo con drift incluido."""
        np.random.seed(42)
        results = []
        risk_pct = 0.015  # 1.5% por trade
        
        fwd_trades = max(200, n_trades * 3)
        
        for _ in range(sims):
            capital = 100_000
            for _ in range(fwd_trades):
                risk = capital * risk_pct
                drift = risk * drift_cost  # Costo por drift
                if np.random.random() < wr:
                    capital += risk * payoff - drift
                else:
                    capital -= risk + drift
            results.append(capital)
        
        results = np.array(results)
        return {
            'median': float(np.median(results)),
            'p5': float(np.percentile(results, 5)),
            'p95': float(np.percentile(results, 95)),
            'pct_profitable': float((results > 100_000).mean() * 100),
        }
    
    def _print_report(self, r: QualificationResult):
        """Imprime el reporte de calificación."""
        status = "✅ QUALIFIED" if r.qualified else "❌ REJECTED"
        
        print(f"\n  {'─'*50}")
        print(f"  {status}: {r.ticker} @ {r.timeframe} → Grade {r.grade} ({r.edge_score}/100)")
        print(f"  {'─'*50}")
        print(f"  Modelo óptimo: {r.optimal_model} (payoff {r.optimal_payoff}:1)")
        print(f"  LSTM WR:    {r.lstm_wr*100:.1f}%  (EV neta: {r.ev_lstm:+.4f})")
        print(f"  XGBoost WR: {r.xgb_wr*100:.1f}%  (EV neta: {r.ev_xgb:+.4f})")
        print(f"  Baseline:   {r.baseline_wr*100:.1f}%")
        print(f"  Drift total: {r.drift.total_cost_per_trade_pct*100:.3f}% por trade")
        print(f"  Trades: {r.n_trades} | Barras: {r.n_bars}")
        if r.mc_median > 0:
            print(f"  Montecarlo: Mediana ${r.mc_median:,.0f} | P5 ${r.mc_p5:,.0f} | {r.mc_pct_profitable:.0f}% rentable")
        print(f"  Razón: {r.reason}")
        print(f"  {'─'*50}")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    qualifier = TickerQualifier()
    
    # Test IBIT en 1h y 4h
    tickers_tests = [
        ('IBIT', '1h'),
        ('IBIT', '4h'),
        ('IBIT', '1d'),
        ('SPY', '1h'),
        ('SPY', '1d'),
    ]
    
    all_results = []
    for ticker, tf in tickers_tests:
        result = qualifier.qualify(ticker, tf)
        all_results.append(result)
    
    # Resumen comparativo
    print(f"\n{'='*70}")
    print(f"  RESUMEN: FITNESS TEST MULTI-TICKER")
    print(f"{'='*70}")
    print(f"\n  {'Ticker':<8} {'TF':>4} {'Grade':>6} {'Score':>6} {'Model':>8} {'WR':>6} {'EV Net':>8} {'Drift':>7} {'MC Med':>12} {'Status':>10}")
    print(f"  {'─'*8} {'─'*4} {'─'*6} {'─'*6} {'─'*8} {'─'*6} {'─'*8} {'─'*7} {'─'*12} {'─'*10}")
    
    for r in all_results:
        best_wr = max(r.lstm_wr, r.xgb_wr)
        status = "✅ GO" if r.qualified else "❌ NO"
        print(f"  {r.ticker:<8} {r.timeframe:>4} {r.grade:>6} {r.edge_score:>5.0f} {r.optimal_model:>8} {best_wr*100:>5.1f}% {r.ev_after_costs:>+7.4f} {r.drift.total_cost_per_trade_pct*100:>6.2f}% ${r.mc_median:>11,.0f} {status:>10}")
