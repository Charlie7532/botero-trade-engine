import pytest
from backend.modules.quality_swing.domain.rules.rc_tide_ev_lookup import RealEVSignal, lookup_real_ev
from backend.modules.quality_swing.domain.rules.rc_wave_ev_lookup import RealWaveEVSignal
from backend.modules.quality_swing.domain.rules.swing_entry_rules import is_accumulate_signal, is_trim_signal
from backend.modules.quality_swing.domain.rules.rc_tide_lookup import classify_tide_signal_from_features


def test_real_ev_signal_contract_fields():
    """Verify that RealEVSignal has fatigue_type and fatigue_delta_ev contract fields."""
    fields = RealEVSignal.__dataclass_fields__
    assert "fatigue_type" in fields, "RealEVSignal must have fatigue_type field"
    assert "fatigue_delta_ev" in fields, "RealEVSignal must have fatigue_delta_ev field"

    sig = RealEVSignal(
        state_key="T+++|C+++|<",
        level="zz50",
        fallback_level="L3",
        signal="ACCUMULATE",
        action_code="STK_ACCUMULATE_STRUCTURAL",
        p_bull=0.60,
        p_bear=0.40,
        ev=0.0150,
        sharpe=0.5,
        e_ret_min=-0.01,
        e_ret_max=0.03,
        e_days=10.0,
        rr_asymmetry=2.0,
        ev_per_day=0.0015,
        n_samples=100,
        is_rare_state=False,
    )
    assert sig.fatigue_type == "STABLE"
    assert sig.fatigue_delta_ev == 0.0


def test_bilateral_ev_signal_symmetry():
    """Verify bilateral symmetry between RealEVSignal (Tide) and RealWaveEVSignal (Wave)."""
    tide_fields = RealEVSignal.__dataclass_fields__
    wave_fields = RealWaveEVSignal.__dataclass_fields__

    for field in ["ev", "p_bull", "p_bear", "sharpe", "rr_asymmetry", "fatigue_type", "fatigue_delta_ev"]:
        assert field in tide_fields, f"Field {field} missing in RealEVSignal"
        assert field in wave_fields, f"Field {field} missing in RealWaveEVSignal"


def test_lookup_real_ev_contract():
    """Verify lookup_real_ev returns a signal with valid fatigue contract fields."""
    sig = lookup_real_ev(t_slope="T+++", c_slope="C+++", svw="<", level="zz50")
    assert sig is not None
    assert hasattr(sig, "fatigue_type")
    assert hasattr(sig, "fatigue_delta_ev")
    assert sig.fatigue_type == "STABLE"
    assert sig.fatigue_delta_ev == 0.0


def test_swing_gate_l280_alert_formatting():
    """Verify formatting of REAL_EV alert (swing_gate.py L280) never raises AttributeError."""
    sig = lookup_real_ev(t_slope="T+++", c_slope="C+++", svw="<", level="zz50")
    assert sig is not None

    alert_text = (
        f"REAL_EV[{sig.state_key}]({sig.fallback_level}): "
        f"P_bull={sig.p_bull:.1f}% "
        f"EV={sig.ev:+.4f} "
        f"Sharpe={sig.sharpe:.3f} "
        f"R:R={sig.rr_asymmetry:.2f} "
        f"fatigue={sig.fatigue_type} "
        f"unobserved={sig.is_unobserved_state}"
    )
    assert "fatigue=STABLE" in alert_text


def test_swing_gate_l653_trim_condition_no_crash():
    """Verify that L653 condition does not crash when ev > -0.0020."""
    sig = RealEVSignal(
        state_key="T+++|C+++|<",
        level="zz50",
        fallback_level="L3",
        signal="ACCUMULATE",
        action_code="STK_ACCUMULATE_STRUCTURAL",
        p_bull=0.60,
        p_bear=0.40,
        ev=0.0150,  # > -0.0020 -> would evaluate right-side fatigue_type
        sharpe=0.5,
        e_ret_min=-0.01,
        e_ret_max=0.03,
        e_days=10.0,
        rr_asymmetry=2.0,
        ev_per_day=0.0015,
        n_samples=100,
        is_rare_state=False,
    )
    condition = sig and (sig.ev <= -0.0020 or sig.fatigue_type == "FATIGUE_RISK")
    assert condition is False


def test_is_accumulate_signal_with_real_ev():
    """Verify is_accumulate_signal (swing_entry_rules.py L115, L212) evaluates cleanly."""
    sig = lookup_real_ev(t_slope="T++", c_slope="C~", svw=">", level="zz50")
    assert sig is not None

    should_accum, conviction, reason = is_accumulate_signal(
        sigma_pos=-1.0,
        fear=None,
        below_vwap=True,
        hookup=True,
        real_ev_signal=sig,
    )
    assert isinstance(should_accum, bool)
    assert isinstance(conviction, float)
    assert isinstance(reason, str)


def test_is_trim_signal_with_real_ev():
    """Verify is_trim_signal (swing_entry_rules.py L419, L489) evaluates cleanly."""
    sig = lookup_real_ev(t_slope="T-", c_slope="C+++", svw=">>", level="zz50")
    assert sig is not None

    should_trim, trim_pct, reason = is_trim_signal(
        sigma_pos=1.5,
        fear=None,
        real_ev_signal=sig,
    )
    assert isinstance(should_trim, bool)
    assert isinstance(trim_pct, float)
    assert isinstance(reason, str)


def test_rc_tide_lookup_fatigue_extraction():
    """Verify classify_tide_signal_from_features extracts fatigue without exception."""
    identity = {"zone": "ABOVE", "regime": "MOMENTUM", "conviction": "HIGH", "conviction_score": 0.8}
    direction = {"p_bull": 65.0, "odds": 1.5, "lift_vs_band": 1.2, "z_score": 1.1}
    turn_risk = {"asymmetry_pp": 10.0, "bottom_25": {"pct": 5.0}, "top_25": {"pct": 10.0}}
    composition = {"momentum_purity": 80.0, "capitulation_purity": 10.0}

    sig, ac, urg, sc, ev, sharpe, rr_asym, fatigue = classify_tide_signal_from_features(
        identity, direction, turn_risk, composition, state_key="T+++|C+++|<"
    )
    assert fatigue == "STABLE"
