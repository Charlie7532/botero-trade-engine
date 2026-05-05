from backend.modules.portfolio_management.domain.entities.expectations import ImpliedExpectations

class ExpectationsEngine:
    """
    Helmer Protocol: Reverse DCF Engine.
    Calculates the growth rate implied by the current market price and compares it
    to historical fundamental growth to find asymmetric setups.
    """

    @staticmethod
    def calculate_implied_growth(
        current_price: float,
        ttm_fcf_per_share: float,
        wacc: float,
        terminal_growth_rate: float = 0.02,
        years: int = 10
    ) -> float:
        """
        Reverse DCF: Solves for the implied growth rate that justifies current_price.
        Uses a simple binary search approach to find the implied growth rate.
        """
        if current_price <= 0 or ttm_fcf_per_share <= 0 or wacc <= 0:
            return 0.0

        low, high = -0.5, 1.0  # -50% to +100% growth limits
        tolerance = 0.01
        
        # Binary search for the implied growth rate
        for _ in range(50):
            mid_g = (low + high) / 2
            
            # Calculate DCF value with mid_g
            pv_fcf = 0.0
            fcf = ttm_fcf_per_share
            
            for i in range(1, years + 1):
                fcf *= (1 + mid_g)
                pv_fcf += fcf / ((1 + wacc) ** i)
                
            terminal_value = (fcf * (1 + terminal_growth_rate)) / (wacc - terminal_growth_rate) if wacc > terminal_growth_rate else 0
            pv_tv = terminal_value / ((1 + wacc) ** years)
            
            estimated_price = pv_fcf + pv_tv
            
            if abs(estimated_price - current_price) < tolerance:
                return mid_g
            elif estimated_price < current_price:
                low = mid_g
            else:
                high = mid_g
                
        return (low + high) / 2

    @staticmethod
    def assess_expectations(
        ticker: str,
        current_price: float,
        implied_growth: float,
        historical_growth: float
    ) -> ImpliedExpectations:
        """
        Compares implied vs historical growth to classify market expectations.
        """
        gap = historical_growth - implied_growth
        
        if implied_growth > historical_growth * 1.5 and implied_growth > 0.15:
            assessment = "PRICED_FOR_PERFECTION"
        elif implied_growth < historical_growth * 0.5 or implied_growth < 0.0:
            assessment = "PRICED_FOR_FAILURE"
        else:
            assessment = "FAIRLY_PRICED"
            
        return ImpliedExpectations(
            ticker=ticker,
            current_price=current_price,
            market_implied_growth_rate=implied_growth,
            historical_growth_rate=historical_growth,
            growth_gap=gap,
            assessment=assessment
        )
