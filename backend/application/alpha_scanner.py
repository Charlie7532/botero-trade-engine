"""
ALPHA SCANNER: Motor de Búsqueda de Oportunidades
===================================================
Corre periódicamente (cada 4 horas) y genera una lista
ranqueada de candidatos usando TODAS nuestras fuentes.

Pipeline:
1. Finviz Screener → S&P500 con filtros base
2. Sector Flow → Solo sectores fuertes o en recuperación
3. Unusual Volume → Acumulación institucional
4. Finnhub → Filtro de earnings + insiders
5. Ticker Qualifier → Fitness test rápido
6. Alpha Score composite → Ranking final
"""
import logging
import sys
import os
import numpy as np
sys.path.insert(0, '/root/botero-trade')

logger = logging.getLogger(__name__)


class AlphaScanner:
    """
    Escanea el mercado buscando las mejores oportunidades.
    
    Integra:
    - Finviz (screener, sector breadth, unusual volume)
    - Finnhub (earnings, insiders)
    - Relative Strength vs SPY y sector
    - Sector Flow Engine (WITH_TIDE vs AGAINST_TIDE)
    """
    
    # Componentes del Alpha Score
    WEIGHTS = {
        'rs_vs_spy': 0.25,       # Relative Strength vs SPY
        'rs_vs_sector': 0.20,    # RS vs sector ETF
        'insider_score': 0.15,   # Finnhub insider signal
        'sector_health': 0.15,   # Breadth del sector
        'volume_signal': 0.10,   # Acumulación por volumen
        'qualifier': 0.15,       # Ticker Qualifier fitness test
    }
    
    def __init__(self):
        self._finnhub = None
        self._sector_flow = None
    
    def _get_finnhub(self):
        if self._finnhub is None:
            os.environ.setdefault('FINNHUB_API_KEY', '')
            from backend.infrastructure.data_providers.finnhub_intelligence import FinnhubIntelligence
            self._finnhub = FinnhubIntelligence()
        return self._finnhub
    
    def _get_sector_flow(self):
        if self._sector_flow is None:
            from backend.infrastructure.data_providers.sector_flow import SectorFlowEngine
            self._sector_flow = SectorFlowEngine()
        return self._sector_flow
    
    def scan(
        self,
        tickers: list[str] = None,
        max_results: int = 15,
        include_qualifier: bool = False,
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
                score = self._score_ticker(ticker, sector_report, include_qualifier)
                if score is not None:
                    candidates.append(score)
            except Exception as e:
                logger.debug(f"Error scoring {ticker}: {e}")
                continue
        
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
        
        # 3. Sector health
        sector_health_score = 50  # Default
        stock_info = yf.Ticker(ticker).info
        sector = stock_info.get('sector', 'Unknown')
        
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
                from backend.application.ticker_qualifier import TickerQualifier
                q = TickerQualifier()
                result = q.qualify(ticker, '1h', min_bars=200)
                qualifier_score = result.edge_score
                qualifier_grade = result.grade
            except Exception:
                pass
        
        # Alpha Score composite
        alpha_score = (
            rs_spy_score * self.WEIGHTS['rs_vs_spy']
            + 50 * self.WEIGHTS['rs_vs_sector']  # TODO: RS vs sector ETF
            + insider_score * self.WEIGHTS['insider_score']
            + sector_health_score * self.WEIGHTS['sector_health']
            + volume_score * self.WEIGHTS['volume_signal']
            + qualifier_score * self.WEIGHTS['qualifier']
        )
        
        return {
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
        }


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
