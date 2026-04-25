"""
ALPHA SCANNER: Motor de Búsqueda de Oportunidades — Strategy Synthesis V2
==========================================================================
Corre periódicamente (cada 4 horas) y genera una lista
ranqueada de candidatos usando TODAS nuestras fuentes.

Pipeline:
1. Finviz Screener → S&P500 con filtros base
2. Sector Flow → Solo sectores fuertes o en recuperación
3. Unusual Volume → Acumulación institucional
4. Finnhub → Filtro de earnings + insiders
5. Ticker Qualifier → Fitness test rápido
6. UW Institutional Flow → Sweep/VOI/Premium conviction (NEW V2)
7. Macro Gate → SPY flow as risk posture (NEW V2)
8. Alpha Score composite → Ranking final (ADAPTIVE WEIGHTS)
"""
import logging
import sys
import os
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


class AdaptiveWeightManager:
    """
    Manages component weights adaptively based on signal effectiveness.
    
    Instead of static weights, tracks each component's contribution
    to successful predictions using an exponential moving average.
    Components that consistently identify winners get more weight;
    those that don't get less.
    
    Principle: The system learns from experience while maintaining
    minimum/maximum bounds to prevent any single signal from dominating.
    """
    
    # Base weights — starting point before adaptation
    BASE_WEIGHTS = {
        'rs_vs_spy': 0.18,       # Relative Strength vs SPY
        'rs_vs_sector': 0.13,    # RS vs sector ETF
        'insider_score': 0.13,   # Insider conviction (GuruFocus + Finnhub)
        'sector_health': 0.12,   # Breadth del sector
        'volume_signal': 0.10,   # Acumulación por volumen
        'qualifier': 0.05,       # Ticker Qualifier fitness test (slow, optional)
        'guru_score': 0.09,      # Guru conviction
        'analyst_score': 0.05,   # Analyst consensus
        'uw_flow_score': 0.10,   # UW Institutional Flow (V2)
    }
    # Sum = 0.95 → leaves 0.05 buffer for adaptation
    
    # Bounds: no component goes below 3% or above 30%
    MIN_WEIGHT = 0.03
    MAX_WEIGHT = 0.30
    
    # EMA decay factor for tracking effectiveness
    EMA_ALPHA = 0.15  # 15% weight on new observation
    
    def __init__(self):
        self._weights = dict(self.BASE_WEIGHTS)
        self._effectiveness = {k: 0.5 for k in self.BASE_WEIGHTS}
        self._n_updates = 0
    
    @property
    def weights(self) -> dict:
        """Current adaptive weights, always normalized to sum=1.0."""
        total = sum(self._weights.values())
        if total <= 0:
            return dict(self.BASE_WEIGHTS)
        return {k: v / total for k, v in self._weights.items()}
    
    def update_effectiveness(self, component: str, was_correct: bool):
        """
        Update a component's effectiveness score after observing outcome.
        
        Called by the Orchestrator after a trade resolves:
        - was_correct=True: this component's score was above average AND the trade won
        - was_correct=False: this component's score was above average BUT the trade lost
        """
        if component not in self._effectiveness:
            return
        
        new_val = 1.0 if was_correct else 0.0
        self._effectiveness[component] = (
            self.EMA_ALPHA * new_val + 
            (1 - self.EMA_ALPHA) * self._effectiveness[component]
        )
        
        # Adapt weight: base_weight × (0.5 + effectiveness)
        # effectiveness 0.0 → weight × 0.5 (halved)
        # effectiveness 0.5 → weight × 1.0 (base)
        # effectiveness 1.0 → weight × 1.5 (50% boost)
        base = self.BASE_WEIGHTS.get(component, 0.05)
        adapted = base * (0.5 + self._effectiveness[component])
        self._weights[component] = max(self.MIN_WEIGHT, min(self.MAX_WEIGHT, adapted))
        
        self._n_updates += 1
        if self._n_updates % 10 == 0:
            logger.info(f"Adaptive weights after {self._n_updates} updates: {self.weights}")
    
    def get_effectiveness_report(self) -> dict:
        """Returns current effectiveness scores for monitoring."""
        return {
            'n_updates': self._n_updates,
            'effectiveness': dict(self._effectiveness),
            'current_weights': self.weights,
            'base_weights': dict(self.BASE_WEIGHTS),
        }


class AlphaScanner:
    """
    Escanea el mercado buscando las mejores oportunidades.
    Strategy Synthesis V2 — with Institutional Flow + Adaptive Weights.
    
    Integra:
    - Finviz (screener, sector breadth, unusual volume)
    - Finnhub (earnings, insiders)
    - Relative Strength vs SPY y sector
    - Sector Flow Engine (WITH_TIDE vs AGAINST_TIDE)
    - UW Institutional Flow (sweeps, VOI, premium) [NEW V2]
    - SPY Macro Gate (adaptive risk posture) [NEW V2]
    """
    
    # Static weights kept for backward compatibility
    WEIGHTS = AdaptiveWeightManager.BASE_WEIGHTS
    
    def __init__(self):
        self._finnhub = None
        self._sector_flow = None
        self._gurufocus = None
        self._finviz = None
        self._uw_intel = None
        self.weight_manager = AdaptiveWeightManager()
    
    def _get_finnhub(self):
        if self._finnhub is None:
            from backend.infrastructure.data_providers.finnhub_intelligence import FinnhubIntelligence
            self._finnhub = FinnhubIntelligence()
        return self._finnhub
    
    def _get_gurufocus(self):
        if self._gurufocus is None:
            from backend.infrastructure.data_providers.gurufocus_intelligence import GuruFocusIntelligence
            self._gurufocus = GuruFocusIntelligence()
        return self._gurufocus

    def _get_finviz(self):
        if self._finviz is None:
            from backend.infrastructure.data_providers.finviz_intelligence import FinvizIntelligence
            self._finviz = FinvizIntelligence()
        return self._finviz
    
    def _get_sector_flow(self):
        if self._sector_flow is None:
            from backend.infrastructure.data_providers.sector_flow import SectorFlowEngine
            self._sector_flow = SectorFlowEngine()
        return self._sector_flow
    
    def _get_uw_intel(self):
        if self._uw_intel is None:
            from backend.infrastructure.data_providers.uw_intelligence import UnusualWhalesIntelligence
            self._uw_intel = UnusualWhalesIntelligence()
        return self._uw_intel
    
    def scan(
        self,
        tickers: list[str] = None,
        max_results: int = 15,
        include_qualifier: bool = False,
        # ─── MCP-sourced data (pre-fetched by orchestrator) ───
        insider_mcp_data: dict = None,     # {ticker: {cluster, ceo, cfo}}
        guru_mcp_data: dict = None,        # {ticker: mcp_response}
        analyst_mcp_data: dict = None,     # {ticker: mcp_response}
        finviz_movers_data: dict = None,   # Finviz MCP volume_surge response
        # ─── UW Institutional Flow (Strategy Synthesis V2) ───
        uw_flow_data: dict = None,         # {ticker: FlowSignal}
        uw_macro_gate: 'MacroGate' = None, # SPY macro gate
        uw_sentiment: 'MarketSentiment' = None,  # Market-wide sentiment
    ) -> list[dict]:
        """
        Escanea una lista de tickers y los rankea por Alpha Score.
        
        Args:
            tickers: Lista de tickers a evaluar. Si None, usa Finviz screener.
            max_results: Máximo de candidatos a retornar.
            include_qualifier: Si True, ejecuta fitness test (LENTO).
        """
        if tickers is None:
            tickers = self._get_finviz_movers()
        
        if not tickers:
            logger.warning("No hay tickers para escanear")
            return []
        
        logger.info(f"Escaneando {len(tickers)} tickers...")
        
        # Obtener contexto sectorial
        try:
            sector_flow = self._get_sector_flow()
            sector_report = sector_flow.get_sector_health_report()
        except Exception as e:
            logger.error(f"Error sector flow: {e}")
            sector_report = {}
        
        candidates = []
        for ticker in tickers:
            try:
                score = self._score_ticker(
                    ticker, sector_report, include_qualifier,
                    uw_flow_data=uw_flow_data,
                    insider_mcp_data=insider_mcp_data,
                    guru_mcp_data=guru_mcp_data,
                    analyst_mcp_data=analyst_mcp_data,
                )
                if score is not None:
                    candidates.append(score)
            except Exception as e:
                logger.debug(f"Error scoring {ticker}: {e}")
                continue
        
        # ═══ MACRO GATE: Adaptive scaling of all scores ═══
        if uw_macro_gate:
            scale = uw_macro_gate.position_scale_factor
            for candidate in candidates:
                original = candidate['alpha_score']
                candidate['alpha_score'] = round(original * scale, 1)
                candidate['macro_gate'] = uw_macro_gate.signal
                candidate['macro_scale'] = scale
            
            if scale != 1.0:
                logger.info(
                    f"Macro Gate applied: {uw_macro_gate.signal} "
                    f"(scale={scale:.2f}, score={uw_macro_gate.composite_score:+d})"
                )
        
        # ═══ SENTIMENT CONTEXT ═══
        if uw_sentiment:
            for candidate in candidates:
                candidate['market_regime'] = uw_sentiment.regime
                candidate['market_sentiment'] = uw_sentiment.sentiment_score
        
        # Ordenar por Alpha Score
        candidates.sort(key=lambda x: -x.get('alpha_score', 0))
        
        return candidates[:max_results]
    
    def _get_finviz_movers(self) -> list[str]:
        """Obtiene los movers del día de Finviz."""
        try:
            from finvizfinance.screener.overview import Overview
            screener = Overview()
            screener.set_filter(
                filters_dict={
                    'Market Cap.': '+Large (over $10bln)',
                    'Average Volume': 'Over 500K',
                    'Relative Volume': 'Over 1.5',
                }
            )
            data = screener.screener_view()
            if data is not None and not data.empty:
                return data['Ticker'].tolist()[:30]
        except Exception as e:
            logger.error(f"Error Finviz screener: {e}")
        
        # Fallback: top tickers conocidos
        return ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA',
                'JPM', 'V', 'UNH', 'XOM', 'JNJ', 'PG', 'HD', 'IBIT']
    
    def _score_ticker(
        self,
        ticker: str,
        sector_report: dict,
        include_qualifier: bool,
        uw_flow_data: dict = None,
        insider_mcp_data: dict = None,
        guru_mcp_data: dict = None,
        analyst_mcp_data: dict = None,
    ) -> dict:
        """Calcula el Alpha Score composite para un ticker."""
        import yfinance as yf
        
        # 1. Descargar datos recientes
        data = yf.download(ticker, period='3mo', interval='1d', progress=False)
        spy = yf.download('SPY', period='3mo', interval='1d', progress=False)
        
        if data.empty or spy.empty or len(data) < 20:
            return None
        
        if isinstance(data.columns, __import__('pandas').MultiIndex):
            data.columns = data.columns.get_level_values(0)
        if isinstance(spy.columns, __import__('pandas').MultiIndex):
            spy.columns = spy.columns.get_level_values(0)
        
        # 2. RS vs SPY
        stock_ret_20d = float(data['Close'].iloc[-1] / data['Close'].iloc[-20] - 1)
        spy_ret_20d = float(spy['Close'].iloc[-1] / spy['Close'].iloc[-20] - 1)
        rs_spy = (1 + stock_ret_20d) / (1 + spy_ret_20d) if spy_ret_20d != -1 else 1.0
        
        # Normalizar RS a 0-100
        rs_spy_score = max(0, min(100, (rs_spy - 0.8) / 0.4 * 100))
        
        # 3. Sector health + RS vs Sector ETF
        sector_health_score = 50  # Default
        stock_info = yf.Ticker(ticker).info
        sector = stock_info.get('sector', 'Unknown')
        
        # RS vs Sector ETF (fix placeholder)
        SECTOR_ETFS = {
            'Technology': 'XLK', 'Healthcare': 'XLV', 'Financial Services': 'XLF',
            'Consumer Cyclical': 'XLY', 'Industrials': 'XLI', 'Energy': 'XLE',
            'Communication Services': 'XLC', 'Consumer Defensive': 'XLP',
            'Utilities': 'XLU', 'Real Estate': 'XLRE', 'Basic Materials': 'XLB',
        }
        rs_sector_score = 50  # Default neutral
        sector_etf = SECTOR_ETFS.get(sector)
        if sector_etf:
            try:
                etf_data = yf.download(sector_etf, period='3mo', interval='1d', progress=False)
                if not etf_data.empty and len(etf_data) >= 20:
                    if isinstance(etf_data.columns, __import__('pandas').MultiIndex):
                        etf_data.columns = etf_data.columns.get_level_values(0)
                    etf_ret_20d = float(etf_data['Close'].iloc[-1] / etf_data['Close'].iloc[-20] - 1)
                    rs_sector = (1 + stock_ret_20d) / (1 + etf_ret_20d) if etf_ret_20d != -1 else 1.0
                    rs_sector_score = max(0, min(100, (rs_sector - 0.8) / 0.4 * 100))
            except Exception:
                pass
        
        if sector_report:
            for s_name, s_data in sector_report.items():
                if isinstance(s_data, dict) and s_data.get('sector_name', '') == sector:
                    breadth = s_data.get('breadth_pct', 50)
                    sector_health_score = breadth
                    break
        
        # 4. Insider signal (Finnhub)
        insider_score = 50  # Neutral
        earnings_safe = True
        try:
            fh = self._get_finnhub()
            intel = fh.get_ticker_intelligence(ticker)
            insider_sig = intel.get('insiders', {}).get('signal', 'neutral')
            if insider_sig == 'strong_buy':
                insider_score = 90
            elif insider_sig == 'buy':
                insider_score = 70
            elif insider_sig == 'caution':
                insider_score = 20
            
            earnings_safe = intel.get('earnings', {}).get('safe_to_trade', True)
            if not earnings_safe:
                return None  # No incluir — riesgo binario
        except Exception:
            pass
        
        # 5. Volume signal
        avg_vol = float(data['Volume'].rolling(20).mean().iloc[-1])
        current_vol = float(data['Volume'].iloc[-1])
        rel_vol = current_vol / avg_vol if avg_vol > 0 else 1.0
        volume_score = max(0, min(100, (rel_vol - 0.5) / 2.5 * 100))
        
        # 6. Qualifier (optional, slow)
        qualifier_score = 50
        qualifier_grade = 'N/A'
        if include_qualifier:
            try:
                from backend.modules.portfolio_management.domain.use_cases.qualify_ticker import TickerQualifier
                q = TickerQualifier()
                result = q.qualify(ticker, '1h', min_bars=200)
                qualifier_score = result.edge_score
                qualifier_grade = result.grade
            except Exception:
                pass
        
        # 7. Guru / Analyst from MCP
        guru_score = 50
        analyst_score_val = 50
        if insider_mcp_data and ticker in insider_mcp_data:
            try:
                gf = self._get_gurufocus()
                idata = insider_mcp_data[ticker]
                insider_parsed = gf.parse_insider_conviction(
                    ticker,
                    cluster_data=idata.get("cluster"),
                    ceo_data=idata.get("ceo"),
                    cfo_data=idata.get("cfo"),
                )
                insider_score = max(insider_score, insider_parsed.conviction_score)
            except Exception:
                pass
        if guru_mcp_data and ticker in guru_mcp_data:
            try:
                gf = self._get_gurufocus()
                guru = gf.parse_guru_tracking(ticker, guru_mcp_data[ticker])
                guru_score = guru.net_buying_score
            except Exception:
                pass
        if analyst_mcp_data and ticker in analyst_mcp_data:
            try:
                gf = self._get_gurufocus()
                analyst = gf.parse_analyst_intelligence(ticker, analyst_mcp_data[ticker])
                analyst_map = {"strong_buy": 90, "buy": 70, "hold": 50, "sell": 30, "strong_sell": 10}
                analyst_score_val = analyst_map.get(analyst.consensus, 50)
            except Exception:
                pass

        # 8. UW Institutional Flow Score (Strategy Synthesis V2)
        uw_flow_score_val = 50  # Neutral default when no UW data
        uw_flow_detail = None
        if uw_flow_data and ticker in uw_flow_data:
            flow = uw_flow_data[ticker]
            uw_flow_score_val = flow.flow_score
            uw_flow_detail = {
                'sweeps': flow.n_sweeps,
                'calls': flow.n_calls,
                'puts': flow.n_puts,
                'voi': flow.avg_voi_ratio,
                'premium': flow.total_premium,
                'score': flow.flow_score,
            }

        # ═══ Alpha Score composite (ADAPTIVE WEIGHTS) ═══
        w = self.weight_manager.weights
        
        component_scores = {
            'rs_vs_spy': rs_spy_score,
            'rs_vs_sector': rs_sector_score,
            'insider_score': insider_score,
            'sector_health': sector_health_score,
            'volume_signal': volume_score,
            'qualifier': qualifier_score,
            'guru_score': guru_score,
            'analyst_score': analyst_score_val,
            'uw_flow_score': uw_flow_score_val,
        }
        
        alpha_score = sum(
            component_scores[k] * w.get(k, 0) 
            for k in component_scores
        )
        
        result = {
            'ticker': ticker,
            'alpha_score': round(alpha_score, 1),
            'sector': sector,
            'rs_vs_spy': round(rs_spy, 4),
            'rs_spy_score': round(rs_spy_score, 1),
            'insider_score': round(insider_score, 1),
            'sector_health': round(sector_health_score, 1),
            'volume_signal': round(volume_score, 1),
            'rel_volume': round(rel_vol, 2),
            'qualifier_grade': qualifier_grade,
            'qualifier_score': round(qualifier_score, 1),
            'stock_return_20d': round(stock_ret_20d * 100, 2),
            'spy_return_20d': round(spy_ret_20d * 100, 2),
            'outperformance': round((stock_ret_20d - spy_ret_20d) * 100, 2),
            'earnings_safe': earnings_safe,
            # V2: UW Flow
            'uw_flow_score': round(uw_flow_score_val, 1),
            'uw_flow_detail': uw_flow_detail,
        }
        
        return result


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    scanner = AlphaScanner()
    
    # Test con tickers específicos
    test_tickers = ['IBIT', 'AAPL', 'NVDA', 'ABT', 'SCHW', 'AMD', 'JPM', 'XOM', 'META', 'TSLA']
    
    print(f"\n{'='*80}")
    print(f"  ALPHA SCANNER: Ranking de Oportunidades")
    print(f"{'='*80}")
    
    results = scanner.scan(tickers=test_tickers, include_qualifier=False)
    
    print(f"\n  {'#':>3} {'Ticker':<8} {'Alpha':>6} {'RS/SPY':>7} {'Insider':>8} {'Sector':>7} {'Vol':>5} {'Ret20d':>7} {'vs SPY':>7} {'Sector':>12}")
    print(f"  {'─'*3} {'─'*8} {'─'*6} {'─'*7} {'─'*8} {'─'*7} {'─'*5} {'─'*7} {'─'*7} {'─'*12}")
    
    for i, r in enumerate(results, 1):
        print(f"  {i:>3} {r['ticker']:<8} {r['alpha_score']:>5.1f} {r['rs_vs_spy']:>6.3f} {r['insider_score']:>7.0f} {r['sector_health']:>6.0f} {r['rel_volume']:>4.1f}x {r['stock_return_20d']:>+6.1f}% {r['outperformance']:>+6.1f}% {r['sector']:<12}")
