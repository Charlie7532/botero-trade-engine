"""
Moat Surveillance Loop
======================
Ejecuta la auditoría continua (Druckenmiller) sobre las posiciones abiertas de QUALITY.
No usa stops de precio. Si la empresa se deteriora fundamentalmente (márgenes/capex),
levanta la bandera de 'Thesis Death' para que el QualityExitEngine liquide la posición.

V12: Direct journal injection (no orchestrator dependency) + 4Q blacklist.
"""
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class SurveillanceLoop:
    def __init__(self, quality_journal, fundamental_data_port=None, sec_adapter=None, blacklist=None, thesis_repo=None):
        self.journal = quality_journal  # Direct QUALITY journal injection
        self.fundamental_data = fundamental_data_port
        self.sec_adapter = sec_adapter
        self.blacklist = blacklist  # InstrumentBlacklistPort
        self.thesis_repo = thesis_repo
        
    def _evaluate_moat_decay(self, financials: dict) -> tuple[bool, str]:
        """
        Druckenmiller & Hohn Strict Moat Math.
        Devuelve (True, "Razón") si el Moat ha muerto operativamente.
        """
        if not financials:
            return False, ""
            
        # 1. Pricing Power Alert (Munger/Hohn)
        margin_ttm = financials.get("operating_margin_ttm", 0.0)
        margin_5y = financials.get("operating_margin_5y_avg", 0.0)
        if margin_5y > 0:
            # 15% relative drop
            if margin_ttm < (margin_5y * 0.85):
                return True, f"Pricing Power Lost: Margin dropped 15%+ (TTM: {margin_ttm:.2f} vs 5Y: {margin_5y:.2f})"
            # 350bps absolute drop
            if (margin_5y - margin_ttm) > 0.035:
                return True, f"Pricing Power Lost: Margin absolute drop >350bps (TTM: {margin_ttm:.2f} vs 5Y: {margin_5y:.2f})"
                
        # 2. Capex Bloat Alert (Hohn)
        capex_ratio_ttm = financials.get("capex_revenue_ttm", 0.0)
        capex_ratio_5y = financials.get("capex_revenue_5y", 0.0)
        if capex_ratio_5y > 0 and capex_ratio_ttm > (capex_ratio_5y * 1.25):
            return True, f"Capex Bloat: Capital intensity +25% (TTM: {capex_ratio_ttm:.2f} vs 5Y: {capex_ratio_5y:.2f})"
            
        # 3. Value Decay Alert (Druckenmiller)
        roic_trend = financials.get("roic_last_3_quarters", [])
        wacc = financials.get("wacc", 0.0)
        if len(roic_trend) == 3 and wacc > 0:
            # ROIC falling for 3 quarters and dangerously close to WACC (10% premium)
            if roic_trend[0] > roic_trend[1] > roic_trend[2] and roic_trend[2] < (wacc * 1.1):
                return True, f"Value Decay: ROIC declining 3Q ({roic_trend}) approaching WACC ({wacc})"
                
        return False, ""

    def run_surveillance(self) -> List[Dict]:
        """
        Escanea todas las posiciones abiertas del QUALITY journal
        y audita sus fundamentales y SEC filings para detectar deterioro estructural.
        """
        logger.info("Iniciando Surveillance Loop (Druckenmiller)...")
        open_trades = self.journal.get_open_trades()
        surveillance_reports = []
        
        for trade in open_trades:
            ticker = trade["ticker"]
            logger.info(f"Auditing Moat for {ticker}...")
            
            thesis_death = False
            reason = ""
            
            # A. Mathematical Moat Test (GuruFocus)
            if self.fundamental_data:
                financials = self.fundamental_data.get_financial_summary(ticker)
                thesis_death, reason = self._evaluate_moat_decay(financials)

                # Helmer Protocol: Dynamic Checkpoints Evaluation
                if not thesis_death and self.thesis_repo:
                    from backend.modules.portfolio_management.application.use_cases.validate_thesis import validate_thesis
                    thesis = self.thesis_repo.get_active_thesis(ticker)
                    if thesis:
                        validated_thesis = validate_thesis(thesis, financials)
                        if validated_thesis.thesis_status == "INVALIDATED":
                            thesis_death = True
                            breached_cp = next((cp for cp in validated_thesis.checkpoints if cp.is_breached), None)
                            notes = breached_cp.evidence_notes if breached_cp else "Unknown Checkpoint Breached"
                            reason = f"FALSIFICATION PROTOCOL: {notes}"
                            self.thesis_repo.save_thesis(validated_thesis)
            
            # B. NLP SEC Risk Factors Test (Finnhub + Gemini)
            if not thesis_death and self.sec_adapter:
                logger.info(f"Checking SEC Filings for {ticker}...")
                # Fetch latest 10-K URL
                latest_10k = self.sec_adapter.get_latest_10k(ticker)
                if latest_10k and latest_10k.get("filingUrl"):
                    risk_factors = self.sec_adapter.extract_risk_factors(latest_10k["filingUrl"], ticker=ticker)
                    # The LLM outputs "No material customer concentration" if clean.
                    # If it detects risk, it will omit that phrase and list bullet points.
                    if "No material customer concentration" not in risk_factors and "[SEC ANALYSIS" not in risk_factors:
                        thesis_death = True
                        reason = f"SEC NLP Alert: Material structural risks detected in 10-K: {risk_factors[:100]}..."
            
            report = {
                "ticker": ticker,
                "thesis_death_flag": thesis_death,
                "surveillance_reason": reason
            }
            surveillance_reports.append(report)
            
            if thesis_death:
                logger.warning(f"🚨 THESIS DEATH DECLARADO PARA {ticker}: {reason}")
                # Update journal via update_trade (now exists in Port)
                self.journal.update_trade(trade["trade_id"], {
                    "thesis_death_flag": True,
                    "thesis_death_reason": reason,
                    "thesis_alive": False,
                })
                # 4Q Blacklist (Druckenmiller: dead moat = dead for 4 quarters)
                if self.blacklist:
                    self.blacklist.blacklist(ticker, "QUALITY", reason, quarters=4)
                    
        return surveillance_reports

