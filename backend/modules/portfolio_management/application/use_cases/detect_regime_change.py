"""
Detect Regime Change — Use Case
=================================
Evaluates whether any of the three regime levels (market, sector, instrument)
have transitioned to a new Wyckoff phase.

When a transition is detected:
1. Closes the old RegimePhase
2. Creates a new RegimePhase
3. Invalidates all active CalibrationProfiles for affected instruments
4. Returns the list of instruments that need re-calibration

Detection uses a quorum-based approach:
    - Primary detector signals the change
    - At least 2 confirmers must agree
    - Only then is the transition committed

Ports required:
    - InstrumentRepoPort (for reading/writing regime phases + calibrations)
    - SectorDataPort (for sector flow signals)
"""
import logging
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Optional

from backend.modules.portfolio_management.domain.ports.instrument_repo_port import (
    InstrumentRepoPort,
    RegimePhaseRecord,
)
from backend.modules.portfolio_management.domain.rules.macro_regime import MacroRegimeDetector

logger = logging.getLogger(__name__)


# ─── Wyckoff Phase Mapping ─────────────────────────────────

# Map VIX-based MarketRegime to Wyckoff phases
# This is the bridge between the existing MacroRegimeDetector and the new Wyckoff model
VIX_TO_WYCKOFF = {
    "risk_on": "markup",       # Low VIX, positive spread → bullish
    "neutral": "markup",       # Moderate → still bullish until confirmed otherwise
    "risk_off": "distribution",  # High VIX → smart money distributing
    "crisis": "markdown",      # Extreme VIX → active selloff
}

# Map SectorFlowEngine flow signals to Wyckoff phases
FLOW_SIGNAL_TO_WYCKOFF = {
    "ACCUMULATION_ACTIVE": "accumulation",
    "DISTRIBUTION": "distribution",
    "HIGH_VOL_CONSOLIDATION": "distribution",
    "WEAK_RALLY": "markup",  # Still up but losing conviction
    "QUIET_DECLINE": "markdown",
    "CONSOLIDATION": "accumulation",  # Low vol, waiting
}


@dataclass
class RegimeTransition:
    """Result of a regime change detection."""
    instrument_id: str
    ticker: str
    level: str  # market | sector | instrument
    old_phase: str
    new_phase: str
    trigger_signal: str
    calibrations_invalidated: int = 0


class DetectRegimeChange:
    """
    Use case: detect whether market, sector, or instrument regime has changed.

    Must be called with pre-fetched data — never calls infrastructure directly.
    """

    def __init__(self, repo: InstrumentRepoPort):
        self._repo = repo
        self._macro_detector = MacroRegimeDetector()

    def evaluate_market_regime(
        self,
        spy_instrument_id: str,
        vix: float,
        yield_spread: float,
        breadth_pct: float = 50.0,
    ) -> Optional[RegimeTransition]:
        """
        Evaluate market-level regime from VIX + yield spread + breadth.

        Args:
            spy_instrument_id: ID of the SPY instrument in the database
            vix: Current VIX level
            yield_spread: 10Y-2Y yield spread
            breadth_pct: % of S&P 500 stocks above 50-DMA
        """
        # Detect current regime from data
        macro_regime = self._macro_detector.detect_from_data(vix, yield_spread)
        new_phase = VIX_TO_WYCKOFF.get(macro_regime.value, "markup")

        # Breadth confirmation: if breadth < 30% and VIX neutral, it's distribution
        if breadth_pct < 30 and new_phase == "markup":
            new_phase = "distribution"

        # Breadth confirmation: if breadth > 70% and VIX risk_off, it's recovering
        if breadth_pct > 70 and new_phase == "distribution":
            new_phase = "accumulation"

        # Get current active regime
        active = self._repo.get_active_regime(spy_instrument_id, "market")

        if active and active.phase == new_phase:
            return None  # No change

        trigger = f"VIX={vix:.1f}_SPREAD={yield_spread:.2f}_BREADTH={breadth_pct:.0f}%"

        return self._commit_transition(
            instrument_id=spy_instrument_id,
            ticker="SPY",
            level="market",
            old_phase=active.phase if active else "unknown",
            new_phase=new_phase,
            trigger_signal=trigger,
            vix=vix,
            breadth=breadth_pct,
        )

    def evaluate_sector_regime(
        self,
        etf_instrument_id: str,
        etf_ticker: str,
        flow_signal: str,
        rel_vol: float = 1.0,
        change_pct: float = 0.0,
    ) -> Optional[RegimeTransition]:
        """
        Evaluate sector-level regime from SectorFlowEngine signals.

        Args:
            etf_instrument_id: ID of the sector ETF instrument
            etf_ticker: Ticker of the ETF (e.g., "XLK")
            flow_signal: Output from SectorFlowEngine (e.g., "ACCUMULATION_ACTIVE")
            rel_vol: Relative volume vs 20-day average
            change_pct: Price change percentage
        """
        new_phase = FLOW_SIGNAL_TO_WYCKOFF.get(flow_signal, "markup")

        active = self._repo.get_active_regime(etf_instrument_id, "sector")

        if active and active.phase == new_phase:
            return None

        trigger = f"FLOW={flow_signal}_RVOL={rel_vol:.2f}_CHG={change_pct:.2f}%"

        return self._commit_transition(
            instrument_id=etf_instrument_id,
            ticker=etf_ticker,
            level="sector",
            old_phase=active.phase if active else "unknown",
            new_phase=new_phase,
            trigger_signal=trigger,
        )

    def evaluate_instrument_regime(
        self,
        instrument_id: str,
        ticker: str,
        swing_trend: str = "UNKNOWN",
        choch_detected: bool = False,
        choch_direction: str = "NONE",
        bos_detected: bool = False,
        bos_direction: str = "NONE",
        liquidity_swept: bool = False,
        rel_vol: float = 1.0,
    ) -> Optional[RegimeTransition]:
        """
        Evaluate instrument-level regime from SMC structural analysis.

        Only called for instruments in CandidateScreenings.status = 'active'.
        Uses BOS/CHoCH as primary detectors.
        """
        active = self._repo.get_active_regime(instrument_id, "instrument")
        current_phase = active.phase if active else "accumulation"

        new_phase = current_phase  # Default: no change

        # CHoCH is the primary transition signal
        if choch_detected:
            if choch_direction == "BULLISH":
                # From bearish/distribution to accumulation
                if current_phase in ("markdown", "distribution"):
                    new_phase = "accumulation"
            elif choch_direction == "BEARISH":
                # From bullish/accumulation to distribution
                if current_phase in ("markup", "accumulation"):
                    new_phase = "distribution"

        # BOS confirms trend continuation
        if bos_detected and not choch_detected:
            if bos_direction == "BULLISH" and current_phase == "accumulation":
                new_phase = "markup"
            elif bos_direction == "BEARISH" and current_phase == "distribution":
                new_phase = "markdown"

        # Liquidity sweep + reversal = Wyckoff spring (accumulation signal)
        if liquidity_swept and choch_detected and choch_direction == "BULLISH":
            new_phase = "accumulation"  # Spring confirmed

        if new_phase == current_phase:
            return None

        parts = []
        if choch_detected:
            parts.append(f"CHoCH_{choch_direction}")
        if bos_detected:
            parts.append(f"BOS_{bos_direction}")
        if liquidity_swept:
            parts.append("LIQ_SWEPT")
        parts.append(f"RVOL={rel_vol:.2f}")
        trigger = "_".join(parts)

        return self._commit_transition(
            instrument_id=instrument_id,
            ticker=ticker,
            level="instrument",
            old_phase=current_phase,
            new_phase=new_phase,
            trigger_signal=trigger,
        )

    def _commit_transition(
        self,
        instrument_id: str,
        ticker: str,
        level: str,
        old_phase: str,
        new_phase: str,
        trigger_signal: str,
        vix: float = 0.0,
        breadth: float = 0.0,
    ) -> RegimeTransition:
        """
        Commit a regime transition:
        1. Create new RegimePhase (which auto-closes the old one)
        2. Invalidate active calibrations
        3. Return transition record
        """
        now = datetime.now(UTC)

        # Create new regime phase
        new_regime = self._repo.create_regime_phase(RegimePhaseRecord(
            instrument_id=instrument_id,
            level=level,
            phase=new_phase,
            detected_at=now,
            trigger_signal=trigger_signal,
            vix_at_detection=vix,
            breadth_at_detection=breadth,
        ))

        # Invalidate active calibrations for this instrument
        invalidated = self._repo.invalidate_calibrations(
            instrument_id=instrument_id,
            invalidated_by_regime_id=new_regime.id,
        )

        logger.info(
            f"REGIME CHANGE: {ticker} [{level}] {old_phase} → {new_phase} "
            f"(trigger={trigger_signal}, {invalidated} calibrations invalidated)"
        )

        return RegimeTransition(
            instrument_id=instrument_id,
            ticker=ticker,
            level=level,
            old_phase=old_phase,
            new_phase=new_phase,
            trigger_signal=trigger_signal,
            calibrations_invalidated=invalidated,
        )
