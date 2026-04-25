import logging
from backend.modules.portfolio_management.domain.entities.universe_candidate import MarketRegime

logger = logging.getLogger(__name__)

class MacroRegimeDetector:
    """
    Tier 0: Detecta el régimen macroeconómico.
    
    Pure domain rule — classifies macro regime from provided data.
    Data fetching is delegated to infrastructure adapters.
    
    Modes:
    1. detect_from_fred(): Receives pre-parsed FRED snapshot
    2. detect_from_data(): Receives raw VIX + yield spread values
    """

    def __init__(self):
        self.vix_level: float = 20.0
        self.yield_spread: float = 0.5
        self.regime: MarketRegime = MarketRegime.NEUTRAL
        self.macro_snapshot = None

    def detect_from_fred(self, macro_snapshot) -> MarketRegime:
        """
        Detecta régimen usando a pre-parsed FRED MacroSnapshot.
        
        The caller (infrastructure or orchestrator) is responsible for
        fetching and parsing the FRED data via FREDMacroAdapter.
        """
        self.macro_snapshot = macro_snapshot

        # Extract key values for compatibility with existing code
        if self.macro_snapshot.vix is not None:
            self.vix_level = self.macro_snapshot.vix
        if self.macro_snapshot.yield_spread is not None:
            self.yield_spread = self.macro_snapshot.yield_spread

        # Use FRED's composite regime classification
        regime_map = {
            "risk_on": MarketRegime.RISK_ON,
            "neutral": MarketRegime.NEUTRAL,
            "risk_off": MarketRegime.RISK_OFF,
            "crisis": MarketRegime.CRISIS,
        }
        self.regime = regime_map.get(self.macro_snapshot.macro_regime, MarketRegime.NEUTRAL)

        logger.info(
            f"Régimen FRED: {self.regime.value} "
            f"(score={self.macro_snapshot.regime_score:.0f}, "
            f"VIX={self.vix_level:.1f}, Spread={self.yield_spread:.2f}, "
            f"CPI={self.macro_snapshot.cpi_yoy}, FFR={self.macro_snapshot.fed_funds_rate})"
        )
        return self.regime

    def detect_from_data(self, vix: float, yield_spread: float) -> MarketRegime:
        """Detecta régimen desde datos proporcionados (para backtesting o live)."""
        self.vix_level = vix
        self.yield_spread = yield_spread
        self.regime = self._classify()
        return self.regime

    def _classify(self) -> MarketRegime:
        """Clasificación basada en umbrales institucionales estándar."""
        if self.vix_level > 35:
            return MarketRegime.CRISIS
        elif self.vix_level > 25:
            return MarketRegime.RISK_OFF
        elif self.vix_level < 18 and self.yield_spread > 0:
            return MarketRegime.RISK_ON
        else:
            return MarketRegime.NEUTRAL
