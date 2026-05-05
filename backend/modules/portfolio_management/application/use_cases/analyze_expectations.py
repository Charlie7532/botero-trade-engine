import logging
from backend.modules.portfolio_management.domain.entities.expectations import ImpliedExpectations
from backend.modules.portfolio_management.domain.rules.expectations_engine import ExpectationsEngine

logger = logging.getLogger(__name__)

class AnalyzeExpectations:
    """
    Helmer Protocol: Analyze Market Expectations Use Case.
    Coordinates fetching data and running the Expectations Engine.
    """
    def __init__(self, fundamental_data_port, market_data_port):
        self.fundamental_data = fundamental_data_port
        self.market_data = market_data_port

    def execute(self, ticker: str) -> ImpliedExpectations:
        try:
            # 1. Fetch current price via EntryMarketDataPort.fetch_prices()
            prices = self.market_data.fetch_prices(ticker, period="5d")
            if prices is not None and not prices.empty:
                close = prices['Close']
                if hasattr(close, 'columns'):
                    close = close.iloc[:, 0]
                current_price = float(close.iloc[-1])
            else:
                current_price = 0.0
            
            # 2. Fetch financial summary (for FCF/share and WACC)
            summary = self.fundamental_data.get_financial_summary(ticker)
            # In a real scenario, FCF/share is extracted from financials or key ratios.
            # Using a fallback for now.
            ttm_fcf_per_share = summary.get("fcf_per_share_ttm", summary.get("fcf_per_share", 0.0))
            
            # Use WACC parser
            wacc = self.fundamental_data.get_wacc(ticker)
            if wacc <= 0:
                wacc = summary.get("wacc", 0.08)  # Fallback to 8% if missing
            
            # 3. Fetch historical growth
            growth_profile = self.fundamental_data.get_growth_profile(ticker)
            # If growth_profile is a dict (as returned by some ports) or the Dataclass GrowthProfile
            if isinstance(growth_profile, dict):
                fcf_cagr_5y = growth_profile.get("fcf_cagr", {}).get("5y", 0.0)
                rev_cagr_5y = growth_profile.get("revenue_cagr", {}).get("5y", 0.0)
            else:
                fcf_cagr_5y = growth_profile.fcf_cagr.get("5y", 0.0)
                rev_cagr_5y = growth_profile.revenue_cagr.get("5y", 0.0)
                
            historical_growth = fcf_cagr_5y if fcf_cagr_5y > 0 else rev_cagr_5y
            
            if ttm_fcf_per_share <= 0:
                logger.warning(f"{ticker} has negative or missing FCF per share. Cannot run DCF.")
                return ImpliedExpectations(
                    ticker=ticker, current_price=current_price,
                    market_implied_growth_rate=0.0, historical_growth_rate=historical_growth,
                    growth_gap=0.0, assessment="PRICED_FOR_FAILURE", raw_data={"error": "Negative FCF"}
                )

            # 4. Calculate implied growth
            implied_growth = ExpectationsEngine.calculate_implied_growth(
                current_price=current_price,
                ttm_fcf_per_share=ttm_fcf_per_share,
                wacc=wacc
            )
            
            # 5. Assess expectations
            assessment = ExpectationsEngine.assess_expectations(
                ticker=ticker,
                current_price=current_price,
                implied_growth=implied_growth,
                historical_growth=historical_growth
            )
            
            return assessment
            
        except Exception as e:
            logger.error(f"Error analyzing expectations for {ticker}: {e}")
            return ImpliedExpectations(
                ticker=ticker, current_price=0.0, market_implied_growth_rate=0.0,
                historical_growth_rate=0.0, growth_gap=0.0, assessment="ERROR",
                raw_data={"error": str(e)}
            )
