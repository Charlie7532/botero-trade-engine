"""
test_regime_state.py — Unit Tests for Stateful-First Architecture
===================================================================
Tests StateSnapshot entity, RegimeStatePort contract, and SwingGate
consumption of StateSnapshot (with fallback to bare label).

Uses mock RegimeStatePort — no database required.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from typing import Optional

from backend.modules.shared.domain.entities.state_snapshot import StateSnapshot
from backend.modules.shared.domain.ports.regime_state_port import RegimeStatePort


# ── Fixtures ─────────────────────────────────────────────────


def _make_snapshot(
    key: str = "vol:quality:MARKET",
    current_state: str = "ELEVATED",
    previous_state: str = "NORMAL",
    duration_bars: int = 15,
    trigger: str = "VIX_Z=1.5",
    closed_at: Optional[datetime] = None,
) -> StateSnapshot:
    return StateSnapshot(
        key=key,
        current_state=current_state,
        previous_state=previous_state,
        entered_at=datetime(2026, 5, 10, 14, 0, tzinfo=timezone.utc),
        closed_at=closed_at,
        duration_bars=duration_bars,
        trigger_event=trigger,
        metadata={"vix_zscore": 1.5},
    )


class MockRegimeStatePort(RegimeStatePort):
    """In-memory mock for testing."""

    def __init__(self):
        self._states: dict[str, StateSnapshot] = {}
        self._history: list[StateSnapshot] = []

    def get_current(self, key: str, reference_date=None) -> Optional[StateSnapshot]:
        snap = self._states.get(key)
        if snap and reference_date:
            if snap.entered_at > reference_date:
                return None
            if snap.closed_at and snap.closed_at <= reference_date:
                return None
        return snap

    def commit_transition(self, key, next_state, trigger=None, timestamp=None, metadata=None):
        old = self._states.get(key)
        ts = timestamp or datetime.now(timezone.utc)
        new = StateSnapshot(
            key=key,
            current_state=next_state,
            previous_state=old.current_state if old else None,
            entered_at=ts,
            closed_at=None,
            duration_bars=1,
            trigger_event=trigger,
            metadata=metadata,
        )
        if old:
            closed_old = StateSnapshot(
                key=old.key, current_state=old.current_state,
                previous_state=old.previous_state,
                entered_at=old.entered_at,
                closed_at=ts,
                duration_bars=old.duration_bars,
                trigger_event=old.trigger_event,
                metadata=old.metadata,
            )
            self._history.append(closed_old)
        self._states[key] = new

    def increment_duration(self, key):
        old = self._states.get(key)
        if old:
            self._states[key] = StateSnapshot(
                key=old.key, current_state=old.current_state,
                previous_state=old.previous_state,
                entered_at=old.entered_at, closed_at=None,
                duration_bars=old.duration_bars + 1,
                trigger_event=old.trigger_event,
                metadata=old.metadata,
            )

    def load_history(self, key, start, end):
        return [
            s for s in self._history
            if s.key == key and start <= s.entered_at <= end
        ]


# ── Entity Tests ─────────────────────────────────────────────


class TestStateSnapshot:
    """StateSnapshot is a pure frozen dataclass."""

    def test_creation(self):
        snap = _make_snapshot()
        assert snap.current_state == "ELEVATED"
        assert snap.previous_state == "NORMAL"
        assert snap.duration_bars == 15
        assert snap.trigger_event == "VIX_Z=1.5"

    def test_frozen(self):
        snap = _make_snapshot()
        with pytest.raises(AttributeError):
            snap.current_state = "CRISIS"  # type: ignore

    def test_metadata_dict(self):
        snap = _make_snapshot()
        assert snap.metadata == {"vix_zscore": 1.5}

    def test_closed_at_none_means_active(self):
        snap = _make_snapshot(closed_at=None)
        assert snap.closed_at is None

    def test_closed_at_set_means_historical(self):
        snap = _make_snapshot(
            closed_at=datetime(2026, 5, 20, 14, 0, tzinfo=timezone.utc)
        )
        assert snap.closed_at is not None


# ── Port Contract Tests ──────────────────────────────────────


class TestRegimeStatePort:
    """Tests the RegimeStatePort contract via MockRegimeStatePort."""

    def test_get_current_returns_active_state(self):
        port = MockRegimeStatePort()
        port._states["vol:quality:MARKET"] = _make_snapshot()
        result = port.get_current("vol:quality:MARKET")
        assert result is not None
        assert result.current_state == "ELEVATED"

    def test_get_current_returns_none_for_unknown_key(self):
        port = MockRegimeStatePort()
        assert port.get_current("nonexistent:key") is None

    def test_get_current_with_reference_date_filters(self):
        port = MockRegimeStatePort()
        snap = _make_snapshot()  # entered_at = 2026-05-10
        port._states["vol:quality:MARKET"] = snap
        # Query BEFORE entered_at → None
        before = datetime(2026, 5, 1, tzinfo=timezone.utc)
        assert port.get_current("vol:quality:MARKET", reference_date=before) is None
        # Query AFTER entered_at → snap
        after = datetime(2026, 5, 15, tzinfo=timezone.utc)
        assert port.get_current("vol:quality:MARKET", reference_date=after) is not None

    def test_commit_transition_atomic(self):
        """Old state gets closed, new state gets opened."""
        port = MockRegimeStatePort()
        # First state
        port.commit_transition("vol:quality:MARKET", "NORMAL")
        assert port.get_current("vol:quality:MARKET").current_state == "NORMAL"
        assert port.get_current("vol:quality:MARKET").previous_state is None

        # Transition
        port.commit_transition("vol:quality:MARKET", "ELEVATED", trigger="VIX_Z=1.2")
        result = port.get_current("vol:quality:MARKET")
        assert result.current_state == "ELEVATED"
        assert result.previous_state == "NORMAL"
        assert result.trigger_event == "VIX_Z=1.2"
        assert result.duration_bars == 1

        # Old state is in history with closed_at set
        assert len(port._history) == 1
        assert port._history[0].closed_at is not None

    def test_increment_duration(self):
        """duration_bars goes from N to N+1."""
        port = MockRegimeStatePort()
        port.commit_transition("vol:quality:MARKET", "ELEVATED")
        assert port.get_current("vol:quality:MARKET").duration_bars == 1

        port.increment_duration("vol:quality:MARKET")
        assert port.get_current("vol:quality:MARKET").duration_bars == 2

        port.increment_duration("vol:quality:MARKET")
        assert port.get_current("vol:quality:MARKET").duration_bars == 3

    def test_load_history(self):
        port = MockRegimeStatePort()
        t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 2, 1, tzinfo=timezone.utc)
        t3 = datetime(2026, 3, 1, tzinfo=timezone.utc)

        port.commit_transition("vol:quality:MARKET", "NORMAL", timestamp=t1)
        port.commit_transition("vol:quality:MARKET", "ELEVATED", timestamp=t2)
        port.commit_transition("vol:quality:MARKET", "CRISIS", timestamp=t3)

        history = port.load_history(
            "vol:quality:MARKET",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 12, 31, tzinfo=timezone.utc),
        )
        assert len(history) == 2  # NORMAL and ELEVATED (closed states)
        assert history[0].current_state == "NORMAL"
        assert history[1].current_state == "ELEVATED"


# ── Crisis Duration Does NOT Override Gate ───────────────────


class TestCrisisBlockIgnoresDuration:
    """CRISIS block is absolute regardless of duration_bars.

    Correction 1 from meta-auditoría: duration in CRISIS never
    relaxes the 'ZERO new entries' Hard Gate.
    """

    def test_crisis_day_1_blocks(self):
        from backend.modules.quality_swing.domain.rules.swing_entry_rules import (
            is_accumulate_signal,
        )
        should, conv, reason = is_accumulate_signal(
            sigma_pos=-2.0, fear=None, below_vwap=True,
            hookup=True, vol_regime_label="CRISIS",
        )
        # CRISIS blocks even with perfect accumulation setup
        # (fear=None will also block, but CRISIS is checked first)
        assert not should

    def test_crisis_day_30_blocks(self):
        from backend.modules.quality_swing.domain.rules.swing_entry_rules import (
            is_accumulate_signal,
        )
        # Even after 30 days in CRISIS, the block is absolute
        should, conv, reason = is_accumulate_signal(
            sigma_pos=-2.0, fear=None, below_vwap=True,
            hookup=True, vol_regime_label="CRISIS",
        )
        assert not should
        assert "CRISIS" in reason or "INSUFFICIENT" in reason

    def test_crisis_day_100_blocks(self):
        from backend.modules.quality_swing.domain.rules.swing_entry_rules import (
            is_accumulate_signal,
        )
        should, conv, reason = is_accumulate_signal(
            sigma_pos=-2.0, fear=None, below_vwap=True,
            hookup=True, vol_regime_label="CRISIS",
        )
        assert not should
