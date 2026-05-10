import os
import logging
import httpx
from bs4 import BeautifulSoup
from google import genai
import anthropic

logger = logging.getLogger(__name__)

class SecNLPAnalyzer:
    """
    Lee documentos 10-K/10-Q y utiliza un LLM (Gemini) para extraer
    riesgos fundamentales (Concentración de clientes y Cadena de suministro).
    """
    def __init__(self):
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        
        self.gemini_client = genai.Client(api_key=gemini_key) if gemini_key else None
        self.anthropic_client = anthropic.Anthropic(api_key=anthropic_key) if anthropic_key else None
        
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

    def analyze_risk_factors(self, sec_url: str, ticker: str, form_type: str = "10-K/10-Q") -> str:
        """
        Lee el documento oficial y extrae los riesgos exigidos por Munger/Hohn.
        Aplica fallback a Claude si Gemini falla o no está disponible.
        """
        if not self.gemini_client and not self.anthropic_client:
            logger.warning("Ninguna API_KEY (Gemini/Anthropic) encontrada. Omitiendo NLP.")
            return "[SEC ANALYSIS UNAVAILABLE] No hay LLM configurado. Riesgos omitidos."
            
        logger.info(f"Extracting SEC {form_type} document for {ticker} from {sec_url}...")
        raw_text = self._fetch_and_clean_text(sec_url)
        
        if not raw_text:
            return "[SEC ANALYSIS FAILED] No se pudo extraer el texto del documento."
            
        # SEC Filings can be massive. We take the first 100k chars where Item 1 and Item 1A usually reside.
        text_chunk = raw_text[:100000]
        
        prompt = f"""
Act as a strict institutional risk manager for the ticker {ticker}.
I am giving you the text of a recent SEC {form_type} filing.
Your task is to find and extract any evidence of:
1. Customer Concentration (e.g., 'Customer A accounts for 20% of revenue').
2. Supply Chain Risks or dependencies on single-source suppliers.
3. Material Events or Moat Decay (especially for 8-K filings: executive departures, regulatory actions, catastrophic losses).

Return ONLY factual bullet points. If no explicitly dangerous concentration, supply chain risk, or material event is found, explicitly state: "No material risks or moat-decay events identified in the parsed text."
Do NOT include generic financial disclaimers. Do NOT hallucinate.

Filing Text (truncated):
{text_chunk}
"""
        # Try Gemini First
        error_gemini = None
        if self.gemini_client:
            try:
                logger.info(f"Enviando prompt a Gemini para análisis de riesgos de {ticker}...")
                response = self.gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                )
                return response.text.strip()
            except Exception as e:
                logger.warning(f"Gemini fallback activado. Error: {e}")
                error_gemini = e

        # Fallback to Claude (Anthropic)
        if self.anthropic_client:
            try:
                logger.info(f"Enviando prompt a Claude (Fallback) para análisis de riesgos de {ticker}...")
                response = self.anthropic_client.messages.create(
                    model="claude-3-5-haiku-latest",
                    max_tokens=1000,
                    messages=[{"role": "user", "content": prompt}]
                )
                # Claude SDK v0.100+ response extraction
                if response.content and len(response.content) > 0:
                    return response.content[0].text.strip()
            except Exception as e:
                logger.error(f"Error during Claude LLM analysis for {ticker}: {e}")
                return f"[SEC ANALYSIS ERROR] Fallo en inferencia (Gemini: {error_gemini}, Claude: {e})"
        
        return f"[SEC ANALYSIS ERROR] Fallo en la inferencia LLM primaria: {error_gemini}"
