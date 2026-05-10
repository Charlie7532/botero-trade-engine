import logging
import os
from datetime import datetime, timedelta, UTC
from typing import Optional

logger = logging.getLogger(__name__)


class FinnhubIntelligence:
    """
    Integración con Finnhub para datos que NO están en yfinance ni Finviz:
    
    1. Earnings Calendar — No comprar antes de reportes (riesgo binario)
    2. Insider Transactions — Insiders comprando = señal de convicción
    3. Recommendation Trends — Consenso de analistas como contrarian
    4. Company News — Feed para FinBERT sentiment scoring
    
    FILOSOFÍA: Los insiders saben más que Wall Street.
    Si el CEO compra acciones con su propio dinero mientras
    el mercado castiga la acción, eso es la señal más fuerte
    que existe. Warren Buffett lo ha dicho repetidamente.
    """

    def __init__(self, api_key: str = None):
        self._api_key = api_key or os.getenv("FINNHUB_API_KEY", "")
        self._client = None
        self._available = False

        if self._api_key:
            try:
                import finnhub
                self._client = finnhub.Client(api_key=self._api_key)
                self._available = True
                logger.info("Finnhub Intelligence inicializado correctamente.")
            except ImportError:
                logger.warning(
                    "finnhub-python no instalado. "
                    "Ejecutar: pip install finnhub-python"
                )
        else:
            logger.warning("FINNHUB_API_KEY no configurada.")

    # ================================================================
    # EARNINGS CALENDAR — Riesgo Binario
    # ================================================================

    def get_upcoming_earnings(
        self, ticker: str, days_ahead: int = 14
    ) -> Optional[dict]:
        """
        Determina si una acción tiene earnings próximos.
        
        REGLA DE ORO: No abrir posiciones nuevas 5 días antes de earnings.
        Un reporte puede mover 10-20% en una dirección. Eso no es trading,
        es gambling. Un sistema institucional evita el riesgo binario.
        
        Returns:
            Dict con fecha de earnings, días restantes, y si es seguro operar.
        """
        if not self._available:
            return {"safe_to_trade": True, "reason": "finnhub_unavailable"}

        try:
            today = datetime.now()
            end = today + timedelta(days=days_ahead)

            earnings = self._client.earnings_calendar(
                _from=today.strftime("%Y-%m-%d"),
                to=end.strftime("%Y-%m-%d"),
                symbol=ticker,
            )

            events = earnings.get("earningsCalendar", [])
            if not events:
                return {
                    "ticker": ticker,
                    "has_upcoming_earnings": False,
                    "safe_to_trade": True,
                    "reason": "No earnings en próximos 14 días",
                }

            nearest = events[0]
            earnings_date = nearest.get("date", "")
            days_until = (
                datetime.strptime(earnings_date, "%Y-%m-%d") - today
            ).days

            # Regla: No operar 5 días antes de earnings
            safe = days_until > 5
            eps_estimate = nearest.get("epsEstimate")
            revenue_estimate = nearest.get("revenueEstimate")

            result = {
                "ticker": ticker,
                "has_upcoming_earnings": True,
                "earnings_date": earnings_date,
                "days_until": days_until,
                "safe_to_trade": safe,
                "eps_estimate": eps_estimate,
                "revenue_estimate": revenue_estimate,
                "reason": (
                    f"Earnings en {days_until} días ({earnings_date}). "
                    f"{'SEGURO' if safe else 'PELIGRO — Riesgo binario.'}"
                ),
            }

            if not safe:
                logger.warning(
                    f"⚠️  {ticker}: Earnings en {days_until} días ({earnings_date}). "
                    f"NO OPERAR — riesgo binario."
                )
            return result

        except Exception as e:
            logger.error(f"Error earnings calendar {ticker}: {e}")
            return {"ticker": ticker, "safe_to_trade": True, "error": str(e)}

    # ================================================================
    # INSIDER TRANSACTIONS — La Señal del CEO
    # ================================================================

    def get_insider_activity(self, ticker: str) -> dict:
        """
        Analiza las transacciones de insiders (directivos, board members).
        
        EVIDENCIA:
        - Insiders comprando después de una caída: Win Rate ~68% a 6 meses
        - Insiders vendiendo masivamente: señal de precaución (pero menos confiable,
          pueden vender por razones fiscales)
        - Cluster buying (3+ insiders comprando en la misma semana): 
          Win Rate ~75% a 12 meses (Lakonishok & Lee, 2001)
        
        Returns:
            Dict con resumen de actividad insider y señal.
        """
        if not self._available:
            return {"signal": "neutral", "reason": "finnhub_unavailable"}

        try:
            transactions = self._client.stock_insider_transactions(
                symbol=ticker,
            )
            data = transactions.get("data", [])

            if not data:
                return {
                    "ticker": ticker,
                    "total_transactions": 0,
                    "signal": "neutral",
                    "reason": "Sin data de insiders",
                }

            # Analizar últimos 90 días
            cutoff = datetime.now() - timedelta(days=90)
            recent = []
            for txn in data:
                txn_date_str = txn.get("transactionDate", "")
                if txn_date_str:
                    try:
                        txn_date = datetime.strptime(txn_date_str, "%Y-%m-%d")
                        if txn_date >= cutoff:
                            recent.append(txn)
                    except ValueError:
                        continue

            # Clasificar compras vs ventas
            purchases = [
                t for t in recent
                if t.get("transactionCode") in ("P", "A")  # P=Purchase, A=Award
            ]
            sales = [
                t for t in recent
                if t.get("transactionCode") == "S"  # S=Sale
            ]

            buy_value = sum(
                abs(t.get("share", 0) * t.get("transactionPrice", 0))
                for t in purchases
            )
            sell_value = sum(
                abs(t.get("share", 0) * t.get("transactionPrice", 0))
                for t in sales
            )

            # Clasificar señal
            if len(purchases) >= 3 and buy_value > sell_value * 2:
                signal = "strong_buy"
                reason = (
                    f"CLUSTER BUYING: {len(purchases)} compras "
                    f"(${buy_value:,.0f}) vs {len(sales)} ventas "
                    f"(${sell_value:,.0f}) en 90 días"
                )
            elif len(purchases) > len(sales) and buy_value > sell_value:
                signal = "buy"
                reason = (
                    f"Net buying: {len(purchases)} compras vs {len(sales)} ventas"
                )
            elif sell_value > buy_value * 3:
                signal = "caution"
                reason = (
                    f"Heavy selling: ${sell_value:,.0f} vendido vs "
                    f"${buy_value:,.0f} comprado"
                )
            else:
                signal = "neutral"
                reason = (
                    f"Mixed: {len(purchases)} compras, {len(sales)} ventas"
                )

            result = {
                "ticker": ticker,
                "period_days": 90,
                "total_transactions": len(recent),
                "purchases": len(purchases),
                "sales": len(sales),
                "buy_value": buy_value,
                "sell_value": sell_value,
                "signal": signal,
                "reason": reason,
                "unique_buyers": len(set(
                    t.get("name", "") for t in purchases
                )),
            }

            if signal in ("strong_buy", "buy"):
                logger.info(
                    f"🏛️  {ticker} INSIDER {signal.upper()}: {reason}"
                )
            elif signal == "caution":
                logger.warning(f"⚠️  {ticker} INSIDER CAUTION: {reason}")

            return result

        except Exception as e:
            logger.error(f"Error insider transactions {ticker}: {e}")
            return {"ticker": ticker, "signal": "neutral", "error": str(e)}

    # ================================================================
    # RECOMMENDATION TRENDS — Consenso como Contrarian
    # ================================================================

    def get_analyst_consensus(self, ticker: str) -> dict:
        """
        Obtiene el consenso de analistas.
        
        USO CONTRARIAN: Si TODOS dicen "Buy", probablemente el trade
        ya se hizo. Si la mayoría dice "Sell" en una acción que el sistema
        detecta como VALUE_OPPORTUNITY, eso REFUERZA la tesis contrarian.
        """
        if not self._available:
            return {"consensus": "unknown"}

        try:
            trends = self._client.recommendation_trends(symbol=ticker)
            if not trends:
                return {"ticker": ticker, "consensus": "unknown"}

            latest = trends[0]
            strong_buy = latest.get("strongBuy", 0)
            buy = latest.get("buy", 0)
            hold = latest.get("hold", 0)
            sell = latest.get("sell", 0)
            strong_sell = latest.get("strongSell", 0)
            total = strong_buy + buy + hold + sell + strong_sell

            if total == 0:
                return {"ticker": ticker, "consensus": "unknown"}

            bull_pct = (strong_buy + buy) / total * 100
            bear_pct = (sell + strong_sell) / total * 100

            if bull_pct > 80:
                consensus = "extreme_bullish"
                contrarian_note = "Demasiado optimismo. Cautela."
            elif bull_pct > 60:
                consensus = "bullish"
                contrarian_note = "Consenso positivo moderado."
            elif bear_pct > 60:
                consensus = "bearish"
                contrarian_note = "Contrarian: oportunidad si fundamentales sólidos."
            elif bear_pct > 80:
                consensus = "extreme_bearish"
                contrarian_note = "Contrarian extremo. Verificar catalizador."
            else:
                consensus = "mixed"
                contrarian_note = "Sin señal de consenso."

            return {
                "ticker": ticker,
                "period": latest.get("period", ""),
                "strong_buy": strong_buy,
                "buy": buy,
                "hold": hold,
                "sell": sell,
                "strong_sell": strong_sell,
                "bull_pct": round(bull_pct, 1),
                "bear_pct": round(bear_pct, 1),
                "consensus": consensus,
                "contrarian_note": contrarian_note,
            }

        except Exception as e:
            logger.error(f"Error analyst consensus {ticker}: {e}")
            return {"ticker": ticker, "consensus": "unknown", "error": str(e)}

    # ================================================================
    # COMPANY NEWS — Feed para FinBERT
    # ================================================================

    def get_recent_news(
        self, ticker: str, days_back: int = 7, max_headlines: int = 10
    ) -> list[dict]:
        """
        Obtiene titulares recientes para alimentar a FinBERT.
        No analiza sentimiento aquí — solo provee los datos.
        """
        if not self._available:
            return []

        try:
            today = datetime.now()
            start = today - timedelta(days=days_back)

            news = self._client.company_news(
                ticker,
                _from=start.strftime("%Y-%m-%d"),
                to=today.strftime("%Y-%m-%d"),
            )

            if not news:
                return []

            return [
                {
                    "headline": n.get("headline", ""),
                    "source": n.get("source", ""),
                    "datetime": n.get("datetime", 0),
                    "url": n.get("url", ""),
                    "category": n.get("category", ""),
                }
                for n in news[:max_headlines]
            ]

        except Exception as e:
            logger.error(f"Error news {ticker}: {e}")
            return []

    # ================================================================
    # UNIFIED INTELLIGENCE REPORT
    # ================================================================

    def get_ticker_intelligence(self, ticker: str) -> dict:
        """
        Reporte completo de inteligencia Finnhub para un ticker.
        Combina earnings, insiders, consenso, y news en un solo dict.
        """
        logger.info(f"Generando reporte de inteligencia para {ticker}...")

        report = {
            "ticker": ticker,
            "earnings": self.get_upcoming_earnings(ticker),
            "insiders": self.get_insider_activity(ticker),
            "consensus": self.get_analyst_consensus(ticker),
            "news_count": len(self.get_recent_news(ticker)),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Score final de convicción
        conviction = 50  # Neutral

        # Earnings risk
        if report["earnings"] and not report["earnings"].get("safe_to_trade", True):
            conviction -= 30  # Penalización severa

        # Insider signal
        insider_sig = report["insiders"].get("signal", "neutral")
        if insider_sig == "strong_buy":
            conviction += 25
        elif insider_sig == "buy":
            conviction += 15
        elif insider_sig == "caution":
            conviction -= 15

        # Contrarian consensus
        consensus = report["consensus"].get("consensus", "unknown")
        if consensus == "extreme_bearish":
            conviction += 10  # Contrarian boost
        elif consensus == "extreme_bullish":
            conviction -= 10  # Too crowded

        report["conviction_score"] = max(0, min(100, conviction))
        report["conviction_rating"] = (
            "high" if conviction >= 65
            else "moderate" if conviction >= 45
            else "low"
        )

        return report

    # ================================================================
    # SEC FILINGS — 8-K Material Events & Moat Surveillance
    # ================================================================

    def get_recent_filings(
        self,
        ticker: str,
        form: str = "8-K",
        days_back: int = 90,
        max_results: int = 10,
    ) -> list[dict]:
        """
        Retrieve recent SEC filings for a ticker.

        8-K filings are the critical material-event disclosures:
        - Executive departures / appointments
        - M&A, divestitures
        - Regulatory actions, lawsuits
        - Debt covenant violations
        - Revenue guidance changes

        These are the earliest signals of moat decay or corporate stress.
        """
        if not self._available:
            return []

        try:
            today = datetime.now()
            start = today - timedelta(days=days_back)

            filings = self._client.filings(
                symbol=ticker,
                form=form,
                _from=start.strftime("%Y-%m-%d"),
                to=today.strftime("%Y-%m-%d"),
            )

            if not filings:
                return []

            results = []
            for f in filings[:max_results]:
                results.append({
                    "ticker": ticker,
                    "form": f.get("form", ""),
                    "filed_date": str(f.get("filedDate", "")),
                    "accepted_date": str(f.get("acceptedDate", "")),
                    "access_number": f.get("accessNumber", ""),
                    "report_url": f.get("reportUrl", ""),
                    "filing_url": f.get("filingUrl", ""),
                })

            if results:
                logger.info(
                    f"📄 {ticker}: {len(results)} {form} filings "
                    f"in last {days_back} days"
                )
            return results

        except Exception as e:
            logger.error(f"Error fetching {form} filings for {ticker}: {e}")
            return []

    def get_moat_surveillance(self, ticker: str) -> dict:
        """
        Complete moat-surveillance report combining 8-K filings
        with LLM analysis (Gemini → Claude fallback).

        Returns a dict with filing count, analyzed events,
        and a moat_risk score (0=safe, 100=critical).
        """
        filings = self.get_recent_filings(ticker, form="8-K", days_back=90)

        report = {
            "ticker": ticker,
            "filings_8k_count": len(filings),
            "filings": filings,
            "moat_risk": 0,
            "analyzed": False,
            "analysis": None,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if not filings:
            report["analysis"] = "No 8-K filings in last 90 days."
            return report

        # High filing frequency is itself a risk signal
        if len(filings) >= 5:
            report["moat_risk"] = min(40, len(filings) * 8)
            logger.warning(
                f"⚠️ {ticker}: {len(filings)} 8-K filings in 90 days — "
                f"elevated corporate activity"
            )

        # Analyze the most recent filing via LLM if URL available
        latest = filings[0]
        url = latest.get("report_url", "")
        if url:
            try:
                from backend.modules.portfolio_management.infrastructure.sec_nlp_analyzer import (
                    SecNLPAnalyzer,
                )
                analyzer = SecNLPAnalyzer()
                analysis = analyzer.analyze_risk_factors(url, ticker, form_type="8-K")
                report["analyzed"] = True
                report["analysis"] = analysis

                # Detect keywords that indicate moat stress
                stress_keywords = [
                    "departure", "resignation", "terminated",
                    "lawsuit", "litigation", "regulatory",
                    "restatement", "impairment", "covenant",
                    "downgrade", "restructuring",
                ]
                lower_analysis = analysis.lower()
                hits = [kw for kw in stress_keywords if kw in lower_analysis]
                if hits:
                    report["moat_risk"] = min(100, report["moat_risk"] + len(hits) * 15)
                    report["stress_signals"] = hits
                    logger.warning(
                        f"🔴 {ticker} MOAT STRESS: {hits} detected in 8-K"
                    )
            except Exception as e:
                logger.error(f"8-K NLP analysis failed for {ticker}: {e}")
                report["analysis"] = f"[ANALYSIS ERROR] {e}"

        return report

