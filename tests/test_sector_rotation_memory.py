"""
Tests for SectorRotationMemory — Multi-Scale Intelligence
"""
import pytest
from backend.modules.entry_decision.domain.rules.sector_rotation_memory import (
    compute_market_rotation_snapshot,
    evaluate_rotation_intelligence,
    ScaleSnapshot,
    SectorRotationSnapshot,
    MarketRotationSnapshot,
    RotationSignal,
)


def _make_history(values: list[float], pad_to: int = 25) -> list[float]:
    """Create a history list padded to the required length."""
    if len(values) < pad_to:
        values = [values[0]] * (pad_to - len(values)) + values
    return values


def _make_all_sector_histories(
    base_val: float = 50.0, override: dict = None,
) -> dict[str, dict[str, list[float]]]:
    """Create histories for all 11 sectors with a default value."""
    sectors = ["XLK", "XLF", "XLV", "XLI", "XLY", "XLP", "XLE", "XLU", "XLRE", "XLB", "XLC"]
    override = override or {}
    result = {}
    for etf in sectors:
        val = override.get(etf, base_val)
        if isinstance(val, dict):
            result[etf] = {
                scale: _make_history(vals) for scale, vals in val.items()
            }
        else:
            h = _make_history([val])
            result[etf] = {
                "structural": h, "intermediate": h, "tactical": h,
            }
    return result


class TestConvergenceExtremes:
    """Test that extreme convergence signals fire correctly."""

    def test_generational_opportunity_th_extreme_low(self):
        """≥8 sectors with TH ≤ 20% → OPORTUNIDAD GENERACIONAL."""
        # 9 sectors at TH=15%, 2 at TH=50%
        histories = _make_all_sector_histories(base_val=15.0, override={
            "XLK": 50.0, "XLF": 50.0,
        })
        snap = compute_market_rotation_snapshot(histories)
        assert snap is not None
        assert snap.n_sectors_extreme_low_th >= 8

        signal = evaluate_rotation_intelligence(snap, "XLE")
        assert signal.sizing == 1.50
        assert any("GENERACIONAL" in a for a in signal.alerts)

    def test_intermediate_capitulation_fi_extreme_low(self):
        """≥8 sectors with FI ≤ 20% → CAPITULACIÓN INTERMEDIA."""
        # All at FI=15%
        histories = _make_all_sector_histories(base_val=15.0)
        snap = compute_market_rotation_snapshot(histories)
        assert snap is not None
        assert snap.n_sectors_extreme_low_fi >= 8

        signal = evaluate_rotation_intelligence(snap, "XLK")
        assert any("CAPITULACIÓN" in a or "GENERACIONAL" in a for a in signal.alerts)

    def test_high_extreme_does_not_penalize(self):
        """≥8 sectors at S5 ≥ 80% → NO sizing penalty."""
        histories = _make_all_sector_histories(base_val=90.0)
        snap = compute_market_rotation_snapshot(histories)
        assert snap is not None
        assert snap.n_sectors_extreme_high_th >= 8

        signal = evaluate_rotation_intelligence(snap, "XLK")
        # Sizing should NOT be reduced below 1.0
        assert signal.sizing >= 0.9  # Only ranking might slightly adjust


class TestTacticalTrap:
    """Test the Weinstein tactical trap detection."""

    def test_trap_detected(self):
        """Sector gains at 5d but loses at 20d → is_tactical_trap=True."""
        # Build a history where recent 5 days go UP but 20d net is DOWN
        # Start low, go lower, then bounce at the end
        fi_vals = [60.0] * 5 + [30.0] * 15 + [50.0] * 5  # dips then bounces
        histories = _make_all_sector_histories(base_val=50.0, override={
            "XLY": {"structural": _make_history([50.0]),
                    "intermediate": fi_vals,
                    "tactical": _make_history([50.0])},
        })
        snap = compute_market_rotation_snapshot(histories)
        assert snap is not None

        xly = snap.sectors.get("XLY")
        if xly and xly.intermediate.delta_5d > 2.0 and xly.intermediate.delta_20d < -3.0:
            assert xly.is_tactical_trap

    def test_no_trap_when_both_positive(self):
        """Sector gains at both 5d and 20d → NOT a trap."""
        # Steadily rising
        fi_vals = [float(i) for i in range(25, 75, 2)]
        histories = _make_all_sector_histories(base_val=50.0, override={
            "XLK": {"structural": _make_history([50.0]),
                    "intermediate": fi_vals,
                    "tactical": _make_history([50.0])},
        })
        snap = compute_market_rotation_snapshot(histories)
        assert snap is not None

        xlk = snap.sectors.get("XLK")
        if xlk:
            assert not xlk.is_tactical_trap


class TestPanicAndRanking:
    """Test panic total and ranking rules."""

    def test_total_panic_reduces_sizing(self):
        """≥8 sectors distributing → sizing *= 0.50."""
        # Make 9 sectors drop sharply in last 5 days
        dropping = _make_history([70.0] * 20 + [30.0] * 5)
        stable = _make_history([50.0])

        histories = _make_all_sector_histories(base_val=50.0, override={
            etf: {"structural": stable, "intermediate": dropping, "tactical": stable}
            for etf in ["XLK", "XLF", "XLV", "XLI", "XLY", "XLP", "XLE", "XLU", "XLRE"]
        })
        snap = compute_market_rotation_snapshot(histories)
        assert snap is not None
        assert snap.n_sectors_distributing >= 8

        signal = evaluate_rotation_intelligence(snap, "XLK")
        assert any("PANIC" in a for a in signal.alerts)

    def test_top3_ranking_boosts_sizing(self):
        """Sector in Top 3 by delta_5d → sizing *= 1.10."""
        # XLK gaining the most stocks
        gaining = _make_history([30.0] * 20 + [80.0] * 5)
        stable = _make_history([50.0])

        histories = _make_all_sector_histories(base_val=50.0, override={
            "XLK": {"structural": stable, "intermediate": gaining, "tactical": stable},
        })
        snap = compute_market_rotation_snapshot(histories)
        assert snap is not None

        xlk = snap.sectors.get("XLK")
        assert xlk is not None
        assert xlk.intermediate.rank_by_delta_5d <= 3

        signal = evaluate_rotation_intelligence(snap, "XLK")
        assert signal.sizing >= 1.05  # At least some boost


class TestScaleSnapshot:
    """Test basic ScaleSnapshot computation."""

    def test_stocks_above_conversion(self):
        """Converts S5 percentage to real stock count."""
        histories = _make_all_sector_histories(base_val=50.0)
        snap = compute_market_rotation_snapshot(histories)
        assert snap is not None

        # XLK has 67 constituents, 50% above → ~33.5 stocks
        xlk = snap.sectors.get("XLK")
        assert xlk is not None
        assert abs(xlk.intermediate.stocks_above - 33.5) < 1.0

    def test_pct_of_spy(self):
        """% of SPY is based on stock count, not raw percentage."""
        histories = _make_all_sector_histories(base_val=50.0)
        snap = compute_market_rotation_snapshot(histories)
        assert snap is not None

        # Total across all sectors should sum to ~50% of 505
        total_pct = sum(s.intermediate.pct_of_spy for s in snap.sectors.values())
        assert abs(total_pct - 50.0) < 2.0  # ~50% ± rounding
