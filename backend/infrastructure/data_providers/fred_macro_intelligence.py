"""
FRED Macro Intelligence Adapter
==================================
Bridges FRED MCP tools (12 capabilities) to the Botero Trade engine.

Transforms the MacroRegimeDetector from a 2-signal system (VIX + Yield)
into a 6+ signal institutional macro dashboard.

FRED Series Used:
- GDP:           Real GDP growth rate
- CPIAUCSL:      CPI (Consumer Price Index, YoY inflation)
- FEDFUNDS:      Federal Funds Rate
- UNRATE:        Unemployment Rate
- DGS10:         10-Year Treasury Constant Maturity Rate
- DGS2:          2-Year Treasury Constant Maturity Rate
- T10Y2Y:        10Y-2Y Treasury Spread (Yield Curve)
- VIXCLS:        CBOE VIX Index
- MORTGAGE30US:  30-Year Fixed Mortgage Rate
- UMCSENT:       University of Michigan Consumer Sentiment

MCP Tools Consumed:
- get_economic_indicators → broad macro snapshot
- get_economic_indicator  → individual series query
"""
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Well-known FRED series IDs
FRED_SERIES = {
    "gdp": "GDP",
    "cpi": "CPIAUCSL",
    "fed_funds": "FEDFUNDS",
    "unemployment": "UNRATE",
    "treasury_10y": "DGS10",
    "treasury_2y": "DGS2",
    "yield_spread": "T10Y2Y",
    "vix": "VIXCLS",
    "mortgage_30y": "MORTGAGE30US",
    "consumer_sentiment": "UMCSENT",
    "fed_balance_sheet": "WALCL",    # Total Assets of Federal Reserve
    "m2_money_supply": "WM2NS",      # M2 Money Stock
}


@dataclass
class MacroSnapshot:
    """Complete macro economic state from FRED."""
    # Growth
    gdp_growth: Optional[float] = None         # Real GDP growth %
    gdp_trend: str = "unknown"                 # expanding, contracting, stagnant

    # Inflation
    cpi_yoy: Optional[float] = None            # CPI Year-over-Year %
    inflation_regime: str = "unknown"          # low, moderate, high, hyperinflation

    # Monetary Policy
    fed_funds_rate: Optional[float] = None     # Current FFR %
    fed_stance: str = "unknown"                # dovish, neutral, hawkish

    # Labor
    unemployment_rate: Optional[float] = None  # Current unemployment %

    # Rates
    treasury_10y: Optional[float] = None       # 10Y yield
    treasury_2y: Optional[float] = None        # 2Y yield
    yield_spread: Optional[float] = None       # 10Y - 2Y (inversion signal)
    yield_curve_signal: str = "unknown"        # normal, flat, inverted

    # Volatility
    vix: Optional[float] = None
    vix_regime: str = "unknown"                # calm, elevated, panic, crisis

    # Consumer
    consumer_sentiment: Optional[float] = None
    mortgage_30y: Optional[float] = None

    # Liquidity
    fed_balance_sheet: Optional[float] = None    # Total FED assets (trillions)
    fed_balance_trend: str = "unknown"           # expanding, contracting, stable
    m2_money_supply: Optional[float] = None
    liquidity_regime: str = "unknown"            # abundant, tightening, drought

    # Composite
    macro_regime: str = "neutral"              # risk_on, neutral, risk_off, crisis
    regime_score: float = 50.0                 # 0-100 (0=crisis, 100=euphoria)

    raw_data: dict = field(default_factory=dict)


class FREDMacroIntelligence:
    """
    Adapter for FRED MCP tools.

    Receives pre-fetched MCP responses and produces structured
    MacroSnapshot for the MacroRegimeDetector.
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.FREDMacroIntelligence")

    def parse_macro_snapshot(
        self,
        indicators_data: dict = None,
        individual_series: dict = None,
    ) -> MacroSnapshot:
        """
        Parse MCP responses into comprehensive macro snapshot.

        Args:
            indicators_data: Response from get_economic_indicators
            individual_series: Dict of {series_name: value} from get_economic_indicator

        Returns:
            MacroSnapshot with classified regimes
        """
        snapshot = MacroSnapshot()

        try:
            data = {}
            if indicators_data and isinstance(indicators_data, dict):
                data.update(indicators_data)
            if individual_series and isinstance(individual_series, dict):
                data.update(individual_series)

            # Parse individual indicators
            snapshot.gdp_growth = self._safe_float(data.get("gdp_growth", data.get("GDP")))
            snapshot.cpi_yoy = self._safe_float(data.get("cpi_yoy", data.get("CPIAUCSL", data.get("cpi"))))
            snapshot.fed_funds_rate = self._safe_float(data.get("fed_funds_rate", data.get("FEDFUNDS", data.get("fed_funds"))))
            snapshot.unemployment_rate = self._safe_float(data.get("unemployment_rate", data.get("UNRATE", data.get("unemployment"))))
            snapshot.treasury_10y = self._safe_float(data.get("treasury_10y", data.get("DGS10")))
            snapshot.treasury_2y = self._safe_float(data.get("treasury_2y", data.get("DGS2")))
            snapshot.yield_spread = self._safe_float(data.get("yield_spread", data.get("T10Y2Y")))
            snapshot.vix = self._safe_float(data.get("vix", data.get("VIXCLS")))
            snapshot.consumer_sentiment = self._safe_float(data.get("consumer_sentiment", data.get("UMCSENT")))
            snapshot.mortgage_30y = self._safe_float(data.get("mortgage_30y", data.get("MORTGAGE30US")))
            snapshot.fed_balance_sheet = self._safe_float(data.get("fed_balance_sheet", data.get("WALCL")))
            snapshot.m2_money_supply = self._safe_float(data.get("m2_money_supply", data.get("WM2NS")))
            snapshot.raw_data = data

            # Calculate yield spread if we have both rates
            if snapshot.yield_spread is None and snapshot.treasury_10y and snapshot.treasury_2y:
                snapshot.yield_spread = snapshot.treasury_10y - snapshot.treasury_2y

            # Classify regimes
            self._classify_gdp(snapshot)
            self._classify_inflation(snapshot)
            self._classify_fed(snapshot)
            self._classify_yield_curve(snapshot)
            self._classify_vix(snapshot)
            self._classify_liquidity(snapshot)
            self._classify_macro_regime(snapshot)

            self.logger.info(
                f"Macro Snapshot: regime={snapshot.macro_regime} "
                f"(score={snapshot.regime_score:.0f}), "
                f"VIX={snapshot.vix}, FFR={snapshot.fed_funds_rate}, "
                f"CPI={snapshot.cpi_yoy}, Spread={snapshot.yield_spread}"
            )
            return snapshot

        except Exception as e:
            self.logger.error(f"Error parsing macro snapshot: {e}")
            return snapshot

    # ═══════════════════════════════════════════════════════════
    # REGIME CLASSIFIERS
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _classify_gdp(s: MacroSnapshot):
        if s.gdp_growth is None:
            return
        if s.gdp_growth > 2.5:
            s.gdp_trend = "expanding"
        elif s.gdp_growth > 0:
            s.gdp_trend = "stagnant"
        else:
            s.gdp_trend = "contracting"

    @staticmethod
    def _classify_inflation(s: MacroSnapshot):
        if s.cpi_yoy is None:
            return
        if s.cpi_yoy < 2.0:
            s.inflation_regime = "low"
        elif s.cpi_yoy < 4.0:
            s.inflation_regime = "moderate"
        elif s.cpi_yoy < 7.0:
            s.inflation_regime = "high"
        else:
            s.inflation_regime = "hyperinflation"

    @staticmethod
    def _classify_fed(s: MacroSnapshot):
        if s.fed_funds_rate is None:
            return
        if s.fed_funds_rate < 2.0:
            s.fed_stance = "dovish"
        elif s.fed_funds_rate < 4.0:
            s.fed_stance = "neutral"
        else:
            s.fed_stance = "hawkish"

    @staticmethod
    def _classify_yield_curve(s: MacroSnapshot):
        if s.yield_spread is None:
            return
        if s.yield_spread > 0.5:
            s.yield_curve_signal = "normal"
        elif s.yield_spread > -0.2:
            s.yield_curve_signal = "flat"
        else:
            s.yield_curve_signal = "inverted"

    @staticmethod
    def _classify_vix(s: MacroSnapshot):
        if s.vix is None:
            return
        if s.vix < 15:
            s.vix_regime = "calm"
        elif s.vix < 25:
            s.vix_regime = "elevated"
        elif s.vix < 35:
            s.vix_regime = "panic"
        else:
            s.vix_regime = "crisis"

    @staticmethod
    def _classify_liquidity(s: MacroSnapshot):
        """
        Clasifica el régimen de liquidez de la FED.
        
        Soporta 3 formatos de entrada:
        1. raw_data contiene "WALCL_series" (lista de valores históricos)
           → Calcula delta entre el último y el de hace ~4 semanas
        2. raw_data contiene "WALCL_prev" (valor previo explícito)
           → Calcula delta contra el valor actual
        3. Solo fed_balance_sheet disponible (sin histórico)
           → Usa heurística basada en el tamaño absoluto del balance
        """
        if s.fed_balance_sheet is None:
            return
        
        walcl_diff_pct = 0.0
        calculated = False
        
        # Método 1: Serie histórica completa (ideal)
        walcl_series = s.raw_data.get("WALCL_series")
        if walcl_series and isinstance(walcl_series, (list, tuple)) and len(walcl_series) >= 2:
            # El último vs hace 4 semanas (o el más antiguo disponible)
            lookback = min(4, len(walcl_series) - 1)
            current = float(walcl_series[-1])
            previous = float(walcl_series[-(lookback + 1)])
            if previous > 0:
                walcl_diff_pct = ((current - previous) / previous) * 100
                calculated = True
        
        # Método 2: Valor previo explícito
        if not calculated:
            walcl_prev = s.raw_data.get("WALCL_prev")
            if walcl_prev is not None:
                try:
                    prev = float(walcl_prev)
                    if prev > 0:
                        walcl_diff_pct = ((s.fed_balance_sheet - prev) / prev) * 100
                        calculated = True
                except (ValueError, TypeError):
                    pass
        
        # Método 3: Campo precalculado (compatibilidad)
        if not calculated:
            walcl_diff_pct = float(s.raw_data.get("WALCL_diff_pct", 0))
        
        # Clasificar régimen de liquidez
        if walcl_diff_pct > 0.5:
            s.liquidity_regime = "abundant"
            s.fed_balance_trend = "expanding"
        elif walcl_diff_pct < -0.5:
            s.liquidity_regime = "tightening"
            s.fed_balance_trend = "contracting"
        else:
            s.liquidity_regime = "neutral"
            s.fed_balance_trend = "stable"
        
        # Guardar la delta calculada para logging/debug
        s.raw_data["_walcl_diff_pct_calculated"] = round(walcl_diff_pct, 3)

    def _classify_macro_regime(self, s: MacroSnapshot):
        """
        Composite macro regime classification.

        Uses a scoring system based on all available indicators.
        0-100 scale: 0 = deep crisis, 100 = euphoria
        """
        scores = []

        # VIX score (inverted: low VIX = bullish)
        if s.vix is not None:
            vix_score = max(0, min(100, 100 - (s.vix - 12) * 3))
            scores.append(vix_score)

        # Yield curve score
        if s.yield_spread is not None:
            yc_score = max(0, min(100, 50 + s.yield_spread * 25))
            scores.append(yc_score)

        # GDP score
        if s.gdp_growth is not None:
            gdp_score = max(0, min(100, 50 + s.gdp_growth * 10))
            scores.append(gdp_score)

        # Inflation penalty (high inflation = bearish)
        if s.cpi_yoy is not None:
            infl_score = max(0, min(100, 100 - max(0, s.cpi_yoy - 2) * 15))
            scores.append(infl_score)

        # Unemployment (lower = better)
        if s.unemployment_rate is not None:
            unemp_score = max(0, min(100, 100 - (s.unemployment_rate - 3.5) * 10))
            scores.append(unemp_score)

        if scores:
            s.regime_score = sum(scores) / len(scores)
        else:
            s.regime_score = 50.0

        # Liquidity Modifier (Direct impact on final score)
        if s.liquidity_regime == "tightening":
            s.regime_score -= 15.0
        elif s.liquidity_regime == "abundant":
            s.regime_score += 10.0
            
        # Ensure bounds
        s.regime_score = max(0, min(100, s.regime_score))

        # Map score to regime
        if s.regime_score >= 70:
            s.macro_regime = "risk_on"
        elif s.regime_score >= 40:
            s.macro_regime = "neutral"
        elif s.regime_score >= 20:
            s.macro_regime = "risk_off"
        else:
            s.macro_regime = "crisis"

    # ═══════════════════════════════════════════════════════════
    # UTILITIES
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _safe_float(value, default=None) -> Optional[float]:
        """Safely convert value to float."""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
