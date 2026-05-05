import os
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class SecFilingsAdapter:
    """
    Adapter para consultar reportes de la SEC (10-K, 10-Q) vía Finnhub.
    Extrae la URL del documento oficial para análisis de NLP de riesgos
    (Customer Concentration, Supply Chain, Moat Decay).
    """
    
    def __init__(self):
        self._client = None
        self._available = False
        
    def _try_init(self):
        if self._client is not None:
            return
        try:
            import finnhub
            api_key = os.getenv("FINNHUB_API_KEY", "")
            if api_key:
                self._client = finnhub.Client(api_key=api_key)
                self._available = True
                logger.info("SecFilingsAdapter: conectado a Finnhub ✅")
        except (ImportError, Exception) as e:
            logger.warning(f"SecFilingsAdapter: no disponible ({e})")
            
    @property
    def is_available(self) -> bool:
        self._try_init()
        return self._available
        
    def get_latest_10k(self, symbol: str) -> Optional[Dict]:
        """Obtiene el último reporte anual (10-K)."""
        if not self.is_available:
            return None
            
        try:
            filings = self._client.filings(symbol=symbol)
            for f in filings:
                if f.get('form') in ['10-K', '10-K/A']:
                    return {
                        "symbol": symbol,
                        "form": f.get('form'),
                        "filedDate": f.get('filedDate'),
                        "reportUrl": f.get('reportUrl'),
                        "filingUrl": f.get('filingUrl')
                    }
            return None
        except Exception as e:
            logger.error(f"Error fetching 10-K para {symbol}: {e}")
            return None
            
    def get_latest_10q(self, symbol: str) -> Optional[Dict]:
        """Obtiene el último reporte trimestral (10-Q)."""
        if not self.is_available:
            return None
            
        try:
            filings = self._client.filings(symbol=symbol)
            for f in filings:
                if f.get('form') in ['10-Q', '10-Q/A']:
                    return {
                        "symbol": symbol,
                        "form": f.get('form'),
                        "filedDate": f.get('filedDate'),
                        "reportUrl": f.get('reportUrl'),
                        "filingUrl": f.get('filingUrl')
                    }
            return None
        except Exception as e:
            logger.error(f"Error fetching 10-Q para {symbol}: {e}")
            return None
            
    def extract_risk_factors(self, report_url: str, ticker: str = "UNKNOWN") -> str:
        """
        Extrae la sección 'Item 1A. Risk Factors' del documento XML/HTML usando NLP.
        """
        from backend.modules.portfolio_management.infrastructure.sec_nlp_analyzer import SecNLPAnalyzer
        analyzer = SecNLPAnalyzer()
        return analyzer.analyze_risk_factors(sec_url=report_url, ticker=ticker)
