"""
Meta-Signal Engine — Second-Order Constellation Patterns
============================================================
Detects emergent patterns from combinations of 8 head probabilities
and snapshot features. These are NOT individual indicators — they
are higher-order signals that only appear when specific heads align.

Implemented as deterministic rules (not ML) per LdP directive:
"Codify the hypothesis before training it."

Each meta-signal has:
  - Forensic evidence (tape analysis t-stat, p-value, lift)
  - Department scope (Quality, Speculative, or both)
  - Action type: DANGER (block), SQUEEZE (alert), CONFLUENCE (boost)

Clean Architecture: Domain rules layer. Pure functions, no IO.
"""
from dataclasses import dataclass
from typing import Optional

from backend.modules.shared.domain.entities.channel_snapshot import ChannelSnapshot
from backend.modules.shared.domain.ports.head_scorer_port import HeadScore


@dataclass
class MetaSignal:
    """A second-order signal detected from head constellation patterns."""
    name: str           # e.g., "DANGER_CONSTELLATION"
    level: str          # DANGER, SQUEEZE, CONFLUENCE
    action: str         # BLOCK, ALERT, BOOST
    description: str    # Human-readable explanation
    evidence: str       # Forensic reference (t-stat, lift, WR)
    department: str     # QUALITY, SPECULATIVE, BOTH


def detect_meta_signals(
    scores: dict[str, HeadScore],
    snap: ChannelSnapshot,
) -> list[MetaSignal]:
    """Detect constellation patterns from head probabilities + snapshot.

    Args:
        scores: dict of head_name -> HeadScore from HeadScorer.score_all()
        snap: Current ChannelSnapshot with sigma, RSI, regime, etc.

    Returns:
        List of detected MetaSignals (may be empty if no patterns match).
    """
    signals: list[MetaSignal] = []

    # Extract probabilities safely
    def _p(head: str) -> float:
        s = scores.get(head)
        return s.probability if s else 0.0

    p_long = _p('long_entry')
    p_short = _p('short_entry')
    p_exit = _p('swing_exit')
    p_cover = _p('short_cover')
    p_depth = _p('pullback_depth')
    p_reversal = _p('trend_reversal')
    p_bounce = _p('bounce_height')
    p_recovery = _p('trend_recovery')

    regime = snap.regime or "FLAT"
    rsi = snap.rsi_value or 50.0
    sigma = snap.sigma_tide or 0.0

    # ── M1: DANGER CONSTELLATION ──────────────────────────────────
    # Forensic: 43.9% crash rate, 2.8x lift. N=3,559.
    if p_short > 0.6 and p_long < 0.5:
        signals.append(MetaSignal(
            name="DANGER_CONSTELLATION",
            level="DANGER",
            action="BLOCK",
            description=(
                f"P(short)={p_short:.2f}>0.6 AND P(long)={p_long:.2f}<0.5 "
                f"→ 43.9% probability of DD>5% in 10 days"
            ),
            evidence="Tape 3E: lift=2.8x, N=3,559, danger_rate=43.9% vs base=15.6%",
            department="BOTH",
        ))

    # ── M2: SHORT SQUEEZE ─────────────────────────────────────────
    # Forensic: bounce_height in BEAR has edge +44.9%, WR=86.7%.
    if p_cover > 0.7 and p_bounce > 0.6 and regime == "BEAR":
        signals.append(MetaSignal(
            name="SHORT_SQUEEZE",
            level="SQUEEZE",
            action="ALERT",
            description=(
                f"P(cover)={p_cover:.2f}>0.7 AND P(bounce)={p_bounce:.2f}>0.6 "
                f"in BEAR regime → possible reversal/squeeze"
            ),
            evidence="Tape 3A: bounce BEAR WR=86.7%, edge=+44.9%, N=594",
            department="SPECULATIVE",
        ))

    # ── M3: LONG SQUEEZE ──────────────────────────────────────────
    # Forensic: pullback_depth in BULL has edge +47.2%, WR=74.8%.
    if p_exit > 0.6 and p_depth > 0.6 and regime == "BULL":
        signals.append(MetaSignal(
            name="LONG_SQUEEZE",
            level="SQUEEZE",
            action="ALERT",
            description=(
                f"P(exit)={p_exit:.2f}>0.6 AND P(depth)={p_depth:.2f}>0.6 "
                f"in BULL regime → possible correction/squeeze"
            ),
            evidence="Tape 3A: pullback BULL WR=74.8%, edge=+47.2%, N=361",
            department="QUALITY",
        ))

    # ── M4: FULL CONFLUENCE LONG ──────────────────────────────────
    # Forensic: long_entry WR=99.5% when triggered. RSI<40 adds oversold confirm.
    if p_long > 0.7 and p_recovery > 0.5 and rsi < 40:
        signals.append(MetaSignal(
            name="FULL_CONFLUENCE_LONG",
            level="CONFLUENCE",
            action="BOOST",
            description=(
                f"P(long)={p_long:.2f}>0.7 AND P(recovery)={p_recovery:.2f}>0.5 "
                f"AND RSI={rsi:.1f}<40 → full bullish alignment"
            ),
            evidence="Tape 3A: long_entry WR=99.5%, edge=+40.4%, N=365",
            department="QUALITY",
        ))

    # ── M5: FULL CONFLUENCE SHORT ─────────────────────────────────
    # Forensic: short_entry FLAT edge=+26.8%, BEAR edge=+18.7%.
    if p_short > 0.7 and p_reversal > 0.5 and rsi > 70:
        signals.append(MetaSignal(
            name="FULL_CONFLUENCE_SHORT",
            level="CONFLUENCE",
            action="BOOST",
            description=(
                f"P(short)={p_short:.2f}>0.7 AND P(reversal)={p_reversal:.2f}>0.5 "
                f"AND RSI={rsi:.1f}>70 → full bearish alignment"
            ),
            evidence="Tape 3A: short FLAT edge=+26.8%, short BEAR edge=+18.7%",
            department="SPECULATIVE",
        ))

    # ── M6: ZIGZAG BOTTOM CONFLUENCE ──────────────────────────────
    # Forensic Phase 2: zz_bottom DSR=13.89, edge=+41.3%, 89% ANTES del giro.
    # Fires when zigzag bottom detector + RSI oversold confirm a turning point.
    p_zz_bottom = _p('zz_bottom_detector')
    if p_zz_bottom > 0.65 and rsi < 40:
        signals.append(MetaSignal(
            name="ZIGZAG_BOTTOM_CONFLUENCE",
            level="CONFLUENCE",
            action="BOOST",
            description=(
                f"P(zz_bottom)={p_zz_bottom:.2f}>0.65 AND RSI={rsi:.1f}<40 "
                f"→ turning point detected (fires 3d BEFORE bottom)"
            ),
            evidence="Phase 2: DSR=13.89, edge=+41.3%, timing=-3.4d, WR=59% at 5d",
            department="QUALITY",
        ))

    # ── M7: ZIGZAG TOP WARNING ────────────────────────────────────
    # Forensic Phase 2: zz_top DSR=30.06, edge=+35.6%.
    # Fires when top detector signals ceiling — used as TRIM alert, not SHORT.
    p_zz_top = _p('zz_top_detector')
    if p_zz_top > 0.65 and sigma > 0.5:
        signals.append(MetaSignal(
            name="ZIGZAG_TOP_WARNING",
            level="SQUEEZE",
            action="ALERT",
            description=(
                f"P(zz_top)={p_zz_top:.2f}>0.65 AND σ_tide={sigma:.1f}>0.5 "
                f"→ ceiling approaching (reduce exposure, do NOT add)"
            ),
            evidence="Phase 2: DSR=30.06, edge=+35.6%, 69% fires before top",
            department="QUALITY",
        ))

    return signals
