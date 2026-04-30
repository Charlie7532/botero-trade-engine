import logging
from datetime import datetime, UTC
from typing import Optional

from backend.modules.portfolio_management.domain.entities.daily_mandate import DailyMandate

logger = logging.getLogger(__name__)

class CIOOrchestrator:
    """
    Capital Allocator — Ray Dalio / Macro Synthesis.
    
    Determines the daily budget allocation between Quality and Speculative 
    departments based on macro regime, cause-and-effect mechanics, and flows.
    """
    
    def __init__(self, min_quality: float = 0.60, max_speculative: float = 0.40):
        self.min_quality = min_quality
        self.max_speculative = max_speculative
        # Hard default if no dynamic mandate is active
        self._current_mandate = DailyMandate(
            date=datetime.now(UTC).strftime("%Y-%m-%d"),
            quality_budget_pct=0.80,
            speculative_budget_pct=0.20,
            regime="NEUTRAL",
            reasoning="Default baseline."
        )
    
    def get_current_mandate(self) -> DailyMandate:
        """Returns the active mandate for the day."""
        return self._current_mandate
    
    def synthesize_mandate(
        self,
        vix: float,
        market_breadth: float,
        macro_news_sentiment: float,
        yield_curve_inverted: bool = False,
        sector_flows: Optional[dict[str, float]] = None,
        news_vetoes: Optional[list[str]] = None,
    ) -> DailyMandate:
        """
        Synthesize macro variables to generate a dynamic capital allocation mandate.
        This embodies the Ray Dalio "Economic Machine" cause-and-effect logic.

        Args:
            sector_flows: Sector momentum scores, e.g. {"Energy": 0.8, "Healthcare": -0.5}.
                          Positive = capital inflow, Negative = capital outflow.
            news_vetoes:  Sectors to veto entirely due to exogenous shocks,
                          e.g. ["Healthcare"] after a major patent expiry event.
        """
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        
        # Base Allocation
        q_alloc = 0.80
        s_alloc = 0.20
        regime = "NEUTRAL"
        reasoning = []
        vetoed_sectors = list(news_vetoes) if news_vetoes else []
        focus_sectors = []
        
        # 1. Extreme Risk-Off (Deleveraging / Liquidity Crisis)
        if vix >= 35 or (vix >= 25 and market_breadth < 30 and macro_news_sentiment < -0.5):
            regime = "RISK_OFF"
            q_alloc = 0.95
            s_alloc = 0.05
            reasoning.append(f"VIX is {vix:.1f} and breadth is {market_breadth:.0f}%. High volatility demands moat protection. Slashing speculative budget.")
            
        # 2. Bull Momentum (Liquidity Expansion)
        elif vix < 18 and market_breadth > 60 and macro_news_sentiment > 0.3:
            regime = "RISK_ON"
            q_alloc = 0.60
            s_alloc = 0.40
            reasoning.append(f"VIX is {vix:.1f} with {market_breadth:.0f}% breadth. Favorable liquidity regime. Maximizing speculative budget to {s_alloc*100:.0f}%.")
            
        # 3. Uncertain / Choppy (Yield Curve fears etc)
        elif yield_curve_inverted and vix > 20:
            regime = "UNCERTAIN"
            q_alloc = 0.85
            s_alloc = 0.15
            reasoning.append("Yield curve inverted with elevated VIX. Tilting towards quality defensives.")
            
        else:
            reasoning.append("Baseline regime. Maintaining standard 80/20 allocation.")

        # 4. Sector Rotation Intelligence (Cause → Effect)
        if sector_flows:
            for sector, flow_score in sector_flows.items():
                if flow_score >= 0.5:
                    focus_sectors.append(sector)
                elif flow_score <= -0.5 and sector not in vetoed_sectors:
                    vetoed_sectors.append(sector)
            if focus_sectors:
                reasoning.append(f"Capital rotating INTO: {', '.join(focus_sectors)}.")
            if vetoed_sectors:
                reasoning.append(f"Sectors VETOED (outflow/shock): {', '.join(vetoed_sectors)}.")

        # Clamp to hard limits
        q_alloc = max(self.min_quality, min(q_alloc, 1.0))
        s_alloc = min(self.max_speculative, max(s_alloc, 0.0))
        
        # Ensure they sum to 1.0
        s_alloc = min(s_alloc, round(1.0 - q_alloc, 2))
        q_alloc = round(1.0 - s_alloc, 2)
        
        self._current_mandate = DailyMandate(
            date=today,
            quality_budget_pct=q_alloc,
            speculative_budget_pct=s_alloc,
            regime=regime,
            vetoed_sectors=vetoed_sectors,
            focus_sectors=focus_sectors,
            reasoning=" ".join(reasoning)
        )
        
        logger.info(f"CIO Mandate Set: {regime} | Quality={q_alloc*100:.0f}% | Speculative={s_alloc*100:.0f}%")
        return self._current_mandate

