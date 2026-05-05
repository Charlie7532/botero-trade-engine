import os
import logging
import httpx
from bs4 import BeautifulSoup
from google import genai

logger = logging.getLogger(__name__)

class SecNLPAnalyzer:
    """
    Lee documentos 10-K/10-Q y utiliza un LLM (Gemini) para extraer
    riesgos fundamentales (Concentración de clientes y Cadena de suministro).
    """
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY", "")
        self.client = genai.Client(api_key=api_key) if api_key else None
        
    def _fetch_and_clean_text(self, url: str) -> str:
        try:
            # SEC EDGAR guidelines require a valid User-Agent
            headers = {"User-Agent": "BoteroTrade Engine/1.0 (Contact: compliance@example.com)"}
            with httpx.Client(headers=headers, timeout=30.0) as client:
                response = client.get(url)
                response.raise_for_status()
                
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text(separator=' ', strip=True)
            return text
        except Exception as e:
            logger.error(f"Error fetching SEC document from {url}: {e}")
            return ""

    def analyze_risk_factors(self, sec_url: str, ticker: str) -> str:
        """
        Lee el documento oficial y extrae los riesgos exigidos por Munger/Hohn.
        """
        if not self.client:
            logger.warning("GEMINI_API_KEY no encontrada. Omitiendo NLP.")
            return "[SEC ANALYSIS UNAVAILABLE] GEMINI_API_KEY no configurada. Riesgos omitidos."
            
        logger.info(f"Extracting SEC document for {ticker} from {sec_url}...")
        raw_text = self._fetch_and_clean_text(sec_url)
        
        if not raw_text:
            return "[SEC ANALYSIS FAILED] No se pudo extraer el texto del documento."
            
        # SEC Filings can be massive. We take the first 100k chars where Item 1 and Item 1A usually reside.
        text_chunk = raw_text[:100000]
        
        prompt = f"""
Act as a strict institutional risk manager for the ticker {ticker}.
I am giving you the text of a recent SEC 10-K/10-Q filing.
Your task is to find and extract any evidence of:
1. Customer Concentration (e.g., 'Customer A accounts for 20% of revenue').
2. Supply Chain Risks or dependencies on single-source suppliers.

Return ONLY factual bullet points. If no explicitly dangerous concentration or supply chain risk is found, explicitly state: "No material customer concentration or supply chain risks identified in the parsed text."
Do NOT include generic financial disclaimers. Do NOT hallucinate.

Filing Text (truncated):
{text_chunk}
"""
        try:
            logger.info("Enviando prompt a Gemini para análisis de riesgos...")
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error during LLM analysis for {ticker}: {e}")
            return f"[SEC ANALYSIS ERROR] Fallo en la inferencia LLM: {str(e)}"
