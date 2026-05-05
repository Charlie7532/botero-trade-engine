"""
QUALITY QUALIFIER — Fundamental Walk-Forward
===============================================
Pre-trade fitness test para posiciones QUALITY.

Diferencias con el TickerQualifier genérico:
- Usa barras DIARIAS (no horarias)
- Horizonte de semanas/meses (max_bars=20-30 barras diarias)
- Features fundamentales prioritarias (ROIC trend, FCF margin change)
- Grado A obligatorio (tollkeeper o nada)
- Payoff ratio más alto (2.0-3.0x, posiciones pacientes)

Migrado y especializado desde qualify_ticker.py.
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
import warnings
warnings.filterwarnings('ignore')

from backend.modules.simulation.application.use_cases.engineer_features import QuantFeatureEngineer
from backend.modules.simulation.domain.rules.labeling import (
    TripleBarrierLabeler, MetaLabeler, SampleWeighter, QuantSequenceDataset
)
from backend.modules.simulation.infrastructure.lstm_model import QuantInstitutionalLSTM
from backend.modules.portfolio_management.application.use_cases.qualify_ticker import (
    ExecutionDrift, QualificationResult,
)

logger = logging.getLogger(__name__)


class QualityQualifier:
    """
    Calificador Pre-Trade para QUALITY.

    Hohn: "Only tollkeepers. Grade A or nothing."
    Druckenmiller: "When you have edge, size matters more than frequency."

    Usa barras diarias, horizonte largo, payoff ratios altos.
    Umbrales más estrictos: solo Grade A califica.
    """

    # QUALITY requires Grade A — we invest for months, not hours
    MIN_GRADE = 'A'
    GRADE_A = 70
    GRADE_B = 55
    GRADE_C = 40
    GRADE_D = 25

    # Daily timeframe config
    TIMEFRAME_CONFIG = {
        'interval': '1d',
        'period': '10y',
        'tf_min': 1440,
        'bars_day': 1,
    }

    # Quality uses higher payoff ratios (patient positions)
    PAYOFF_RANGE = [2.0, 2.5, 3.0]
    MAX_BARS_LABEL = 25  # 25 trading days (~5 weeks)
    SEQUENCE_LENGTH = 30  # 30 daily bars context

    def __init__(self, market_data=None):
        self.results_cache = {}
        self._market_data = market_data

    def qualify(
        self,
        ticker: str,
        min_bars: int = 500,
    ) -> QualificationResult:
        """
        Ejecuta fitness test QUALITY: barras diarias, horizonte largo.
        Solo Grade A califica.
        """
        cache_key = f"QUALITY_{ticker}_1d"
        if cache_key in self.results_cache:
            return self.results_cache[cache_key]

        logger.info(f"QUALITY QUALIFIER: {ticker} @ 1d")

        # 1. Download daily data
        df = self._download_data(ticker)
        if df is None or len(df) < min_bars:
            result = self._fail_result(ticker, "1d", len(df) if df is not None else 0, f"Datos insuficientes: {len(df) if df is not None else 0} < {min_bars}")
            self.results_cache[cache_key] = result
            return result

        # 2. Execution drift
        avg_price = df['close'].mean()
        drift = ExecutionDrift.estimate_from_data(df, avg_price)

        # 3. Feature engineering (daily timeframe)
        engineer = QuantFeatureEngineer(data=df, timeframe_minutes=self.TIMEFRAME_CONFIG['tf_min'])
        df = engineer.process_all_features(d_price=0.4, d_volume=0.6)
        feature_cols = engineer.get_feature_columns()

        # 4. Find optimal payoff (QUALITY: higher range)
        best_payoff = 2.0
        best_ev = -999
        for payoff in self.PAYOFF_RANGE:
            labeler = TripleBarrierLabeler(profit_mult=payoff, loss_mult=1.0, max_bars=self.MAX_BARS_LABEL)
            test_df = labeler.apply_barriers(df.copy(), close_col='close')
            test_df = MetaLabeler.generate_primary_signals(test_df, momentum_lookback=20)  # 20-day momentum for daily
            test_df = MetaLabeler.apply_metalabels(test_df)
            test_df = test_df[test_df['meta_target'].notna()]
            if len(test_df) > 0:
                wr_est = test_df['meta_target'].mean()
                ev_est = (wr_est * payoff) - (1 - wr_est)
                if ev_est > best_ev:
                    best_ev = ev_est
                    best_payoff = payoff

        # 5. Walk-Forward with optimal payoff
        labeler = TripleBarrierLabeler(profit_mult=best_payoff, loss_mult=1.0, max_bars=self.MAX_BARS_LABEL)
        df = labeler.apply_barriers(df, close_col='close')
        df = MetaLabeler.generate_primary_signals(df, momentum_lookback=20)
        df = MetaLabeler.apply_metalabels(df)
        weights = SampleWeighter.compute_sample_weights(df)
        df['sample_weight'] = weights
        df = df[df['meta_target'].notna()].copy()

        if len(df) < min_bars:
            result = self._fail_result(ticker, "1d", len(df), f"Señales insuficientes: {len(df)}")
            self.results_cache[cache_key] = result
            return result

        SEQ = self.SEQUENCE_LENGTH
        TRAIN = int(len(df) * 0.6)
        TEST = int(len(df) * 0.25)
        PURGE = max(15, int(len(df) * 0.05))  # Larger purge for daily

        wf_results = self._walk_forward(df, feature_cols, SEQ, TRAIN, TEST, PURGE, best_payoff)
        if not wf_results:
            result = self._fail_result(ticker, "1d", len(df), "Walk-Forward failed")
            self.results_cache[cache_key] = result
            return result

        # 6. Compute metrics with costs
        result = self._compute_result(ticker, "1d", df, wf_results, drift, best_payoff, SEQ)
        self.results_cache[cache_key] = result

        # QUALITY: Only Grade A passes
        if result.grade != 'A':
            result.qualified = False
            result.reason = f"QUALITY requires Grade A, got {result.grade} ({result.edge_score:.0f}/100)"

        return result

    def _download_data(self, ticker: str) -> Optional[pd.DataFrame]:
        try:
            if self._market_data is None:
                return None
            dl = self._market_data.fetch_prices(ticker)
            if dl is None or dl.empty:
                return None
            if isinstance(dl.columns, pd.MultiIndex):
                dl.columns = dl.columns.get_level_values(0)
            df = pd.DataFrame({'open': dl['Open'], 'high': dl['High'], 'low': dl['Low'], 'close': dl['Close'], 'volume': dl['Volume']})
            df.index.name = 'datetime'
            df.dropna(inplace=True)
            return df
        except Exception as e:
            logger.error(f"QualityQualifier download error {ticker}: {e}")
            return None

    def _walk_forward(self, df, feature_cols, seq, train_size, test_size, purge, payoff):
        total = len(df)
        n_folds = max(1, min(3, (total - train_size - purge) // test_size))
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
            try:
                gb = GradientBoostingClassifier(n_estimators=80, max_depth=3, learning_rate=0.1, subsample=0.8, random_state=42)
                gb.fit(X_train, y_train.astype(int), sample_weight=w_train)
                gb_preds = gb.predict(X_test)
                gb_wr = accuracy_score(y_test, gb_preds)
                gb_trades = int(gb_preds.sum())
            except Exception:
                gb_wr = base_wr
                gb_trades = 0
            try:
                train_ds = QuantSequenceDataset(df_train, seq, feature_cols, 'meta_target', 'sample_weight')
                train_dl = DataLoader(train_ds, batch_size=32, shuffle=True)
                model = QuantInstitutionalLSTM(input_dim=len(feature_cols), hidden_dim=48, num_layers=2, dropout=0.3)
                opt = torch.optim.Adam(model.parameters(), lr=1e-3)
                crit = nn.BCELoss(reduction='none')
                model.train()
                for ep in range(15):
                    for xb, yb, wb in train_dl:
                        opt.zero_grad()
                        loss = (crit(model(xb), yb) * wb).mean()
                        loss.backward()
                        opt.step()
                test_ds = QuantSequenceDataset(df_test, seq, feature_cols, 'meta_target', 'sample_weight')
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
            except Exception:
                lstm_wr = base_wr
                lstm_trades = 0
            ev = lambda wr: (wr * payoff) - (1 - wr)
            results.append({'fold': fold + 1, 'base': base_wr, 'gb': gb_wr, 'lstm': lstm_wr, 'ev_base': ev(base_wr), 'ev_gb': ev(gb_wr), 'ev_lstm': ev(lstm_wr), 'n_trades': max(gb_trades, lstm_trades)})
        return results

    def _compute_result(self, ticker, timeframe, df, wf_results, drift, best_payoff, seq):
        rdf = pd.DataFrame(wf_results)
        lstm_wr = rdf['lstm'].mean()
        xgb_wr = rdf['gb'].mean()
        base_wr = rdf['base'].mean()
        drift_cost = drift.total_cost_per_trade_pct
        ev_lstm_net = (lstm_wr * best_payoff) - (1 - lstm_wr) - drift_cost
        ev_xgb_net = (xgb_wr * best_payoff) - (1 - xgb_wr) - drift_cost
        if ev_xgb_net > ev_lstm_net and ev_xgb_net > 0:
            best_model, best_wr, best_ev_net = 'xgboost', xgb_wr, ev_xgb_net
        elif ev_lstm_net > 0:
            best_model, best_wr, best_ev_net = 'lstm', lstm_wr, ev_lstm_net
        else:
            best_model, best_wr, best_ev_net = 'none', max(lstm_wr, xgb_wr), max(ev_lstm_net, ev_xgb_net)
        n_trades = int(rdf.get('n_trades', pd.Series([0])).sum())
        # Edge score
        wr_above_base = (best_wr - base_wr) * 100
        edge_score = min(40, max(0, wr_above_base * 4))
        edge_score += min(30, best_ev_net * 50) if best_ev_net > 0 else 0
        folds_pos = (rdf['ev_gb' if best_model == 'xgboost' else 'ev_lstm'] > 0).mean()
        edge_score += folds_pos * 20
        edge_score += min(10, n_trades / 10)
        grade = 'A' if edge_score >= self.GRADE_A else 'B' if edge_score >= self.GRADE_B else 'C' if edge_score >= self.GRADE_C else 'D' if edge_score >= self.GRADE_D else 'F'
        mc = self._montecarlo(best_wr, best_payoff, drift_cost, n_trades)
        return QualificationResult(
            ticker=ticker, timeframe=timeframe, qualified=grade == 'A',
            grade=grade, edge_score=round(edge_score, 1),
            lstm_wr=round(lstm_wr, 4), xgb_wr=round(xgb_wr, 4), baseline_wr=round(base_wr, 4),
            ev_lstm=round(ev_lstm_net, 4), ev_xgb=round(ev_xgb_net, 4),
            n_trades=n_trades, n_bars=len(df), drift=drift,
            ev_after_costs=round(best_ev_net, 4), optimal_model=best_model,
            optimal_payoff=best_payoff, optimal_seq_len=seq,
            mc_median=mc['median'], mc_p5=mc['p5'], mc_p95=mc['p95'],
            mc_pct_profitable=mc['pct_profitable'],
            reason=f"QUALITY: {grade} ({edge_score:.0f}/100) via {best_model}",
        )

    def _montecarlo(self, wr, payoff, drift_cost, n_trades, sims=1000):
        np.random.seed(42)
        results = []
        risk_pct = 0.015
        fwd_trades = max(200, n_trades * 3)
        for _ in range(sims):
            capital = 100_000
            for _ in range(fwd_trades):
                risk = capital * risk_pct
                d = risk * drift_cost
                if np.random.random() < wr:
                    capital += risk * payoff - d
                else:
                    capital -= risk + d
            results.append(capital)
        results = np.array(results)
        return {'median': float(np.median(results)), 'p5': float(np.percentile(results, 5)), 'p95': float(np.percentile(results, 95)), 'pct_profitable': float((results > 100_000).mean() * 100)}

    def _fail_result(self, ticker, tf, n_bars, reason):
        return QualificationResult(ticker=ticker, timeframe=tf, qualified=False, grade='F', edge_score=0, lstm_wr=0, xgb_wr=0, baseline_wr=0, ev_lstm=0, ev_xgb=0, n_trades=0, n_bars=n_bars, drift=ExecutionDrift(), ev_after_costs=0, optimal_model='none', optimal_payoff=0, optimal_seq_len=0, mc_median=0, mc_p5=0, mc_p95=0, mc_pct_profitable=0, reason=reason)
