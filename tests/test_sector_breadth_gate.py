"""
Unit Tests for Sector Breadth Gate — Pure Domain Rule
=======================================================
Tests the compute_sector_breadth_snapshot function with all empirical rules.
"""
import pytest
from backend.modules.entry_decision.domain.rules.sector_breadth_gate import (
    compute_sector_breadth_snapshot,
    SectorBreadthSnapshot,
    TIER_THRESHOLDS,
)


class TestSectorBreadthZone:
    """Test zone classification based on tier thresholds."""

    def test_cold_tier1_defensive(self):
        """Tier 1 (defensive): COLD when S5_FI < 20%."""
        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=15.0, s5_fi_market=50.0,
            etf_above_ma200=True, tier=1,
        )
        assert snap.s5_fi_zone == "COLD"
        assert snap.sizing_modifier == 1.15

    def test_cold_tier3_cyclical(self):
        """Tier 3 (cyclical): COLD when S5_FI < 25%."""
        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=22.0, s5_fi_market=50.0,
            etf_above_ma200=True, tier=3,
        )
        assert snap.s5_fi_zone == "COLD"
        assert snap.sizing_modifier == 1.15

    def test_not_cold_tier1_at_threshold(self):
        """Tier 1: exactly at threshold is NOT cold (uses strict <)."""
        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=20.0, s5_fi_market=50.0,
            etf_above_ma200=True, tier=1,
        )
        assert snap.s5_fi_zone == "NEUTRAL"

    def test_hot_tier2(self):
        """Tier 2: HOT when S5_FI > 70%."""
        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=75.0, s5_fi_market=50.0,
            etf_above_ma200=True, tier=2,
        )
        assert snap.s5_fi_zone == "HOT"
        assert snap.sizing_modifier == 1.0  # No penalty

    def test_neutral(self):
        """NEUTRAL zone: standard sizing."""
        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=45.0, s5_fi_market=50.0,
            etf_above_ma200=True, tier=2,
        )
        assert snap.s5_fi_zone == "NEUTRAL"
        assert snap.sizing_modifier == 1.0


class TestGoldenSignal:
    """Test COLD + IMPROVING → 1.25x boost."""

    def test_golden_signal(self):
        """COLD + IMPROVING relative direction → golden signal."""
        # Simulate history: sector was 10pp behind market, now only 3pp → improving
        s5_hist = [30.0, 30.5, 31.0, 31.5, 32.0, 32.5, 33.0, 33.5, 34.0, 15.0]
        mkt_hist = [45.0, 45.5, 46.0, 46.5, 47.0, 47.5, 48.0, 48.5, 49.0, 50.0]
        # rel at -10: 30-45=-15. rel at -1: 15-50=-35. RoC = -35-(-15) = -20. LOSING.
        # Wait, need to make it IMPROVING. Let me fix the history.
        # For IMPROVING: rel_now > rel_10d_ago + 3
        s5_hist = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0]
        mkt_hist = [50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0]
        # rel at [-10]: 10-50=-40. rel at [-1]: 19-50=-31. RoC = -31-(-40) = +9 > 3 → IMPROVING

        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=19.0, s5_fi_market=50.0,
            etf_above_ma200=True, tier=2,
            s5_fi_history=s5_hist, mkt_fi_history=mkt_hist,
        )
        assert snap.s5_fi_zone == "COLD"
        assert snap.relative_direction == "IMPROVING"
        assert snap.is_golden_signal is True
        assert snap.sizing_modifier == 1.25

    def test_cold_but_losing(self):
        """COLD but LOSING → 1.15x (not golden)."""
        s5_hist = [19.0, 18.0, 17.0, 16.0, 15.0, 14.0, 13.0, 12.0, 11.0, 10.0]
        mkt_hist = [50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0]
        # rel at [-10]: 19-50=-31. rel at [-1]: 10-50=-40. RoC = -40-(-31) = -9 < -3 → LOSING

        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=10.0, s5_fi_market=50.0,
            etf_above_ma200=True, tier=2,
            s5_fi_history=s5_hist, mkt_fi_history=mkt_hist,
        )
        assert snap.s5_fi_zone == "COLD"
        assert snap.relative_direction == "LOSING"
        assert snap.is_golden_signal is False
        assert snap.sizing_modifier == 1.15


class TestNeutralEtfBear:
    """Test NEUTRAL + ETF below MA200 → 1.15x boost."""

    def test_neutral_etf_bear_boost(self):
        """NEUTRAL + ETF < MA200 → sizing 1.15x (N=55, WR=87.3%)."""
        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=45.0, s5_fi_market=50.0,
            etf_above_ma200=False, tier=2,
        )
        assert snap.s5_fi_zone == "NEUTRAL"
        assert snap.etf_above_ma200 is False
        assert snap.sizing_modifier == 1.15

    def test_neutral_etf_bull_standard(self):
        """NEUTRAL + ETF > MA200 → standard 1.0x."""
        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=45.0, s5_fi_market=50.0,
            etf_above_ma200=True, tier=2,
        )
        assert snap.s5_fi_zone == "NEUTRAL"
        assert snap.sizing_modifier == 1.0


class TestHotAdvisory:
    """Test HOT = advisory only, no penalty."""

    def test_hot_no_penalty(self):
        """HOT zone → sizing stays at 1.0 (no penalty)."""
        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=80.0, s5_fi_market=60.0,
            etf_above_ma200=True, tier=2,
        )
        assert snap.s5_fi_zone == "HOT"
        assert snap.sizing_modifier == 1.0
        assert "advisory" in snap.context_label.lower()


class TestEdgeCases:
    """Test edge cases and defaults."""

    def test_no_history(self):
        """Without history, RoC defaults to 0 → STABLE direction."""
        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=15.0, s5_fi_market=50.0,
            etf_above_ma200=True, tier=2,
        )
        assert snap.relative_direction == "STABLE"
        assert snap.relative_roc_10d == 0.0

    def test_short_history(self):
        """With history < 10 bars, RoC defaults to 0."""
        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=15.0, s5_fi_market=50.0,
            etf_above_ma200=True, tier=2,
            s5_fi_history=[1.0, 2.0, 3.0],
            mkt_fi_history=[50.0, 50.0, 50.0],
        )
        assert snap.relative_roc_10d == 0.0

    def test_invalid_tier_defaults(self):
        """Invalid tier defaults to tier 2 thresholds."""
        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=15.0, s5_fi_market=50.0,
            etf_above_ma200=True, tier=99,
        )
        assert snap.s5_fi_zone == "COLD"  # 15 < 22 (tier 2 default)

    def test_snapshot_is_frozen(self):
        """SectorBreadthSnapshot is immutable (frozen dataclass)."""
        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=15.0, s5_fi_market=50.0,
            etf_above_ma200=True, tier=2,
        )
        with pytest.raises(AttributeError):
            snap.sizing_modifier = 2.0

    def test_relative_breadth(self):
        """Relative breadth = sector - market."""
        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=30.0, s5_fi_market=50.0,
            etf_above_ma200=True, tier=2,
        )
        assert snap.relative_breadth == pytest.approx(-20.0)

    def test_context_label_populated(self):
        """Context label is always non-empty."""
        snap = compute_sector_breadth_snapshot(
            s5_fi_sector=45.0, s5_fi_market=50.0,
            etf_above_ma200=True, tier=2,
        )
        assert len(snap.context_label) > 10
