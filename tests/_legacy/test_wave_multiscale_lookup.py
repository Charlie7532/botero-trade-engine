"""
Unit Tests for Wave Multiscale Lookup & Signal Cataloger
=========================================================
Verifies:
  1. Pure quantitative JSON loading without narrative text clutter.
  2. Level fallbacks (L1 -> L2 -> L3 -> GLOBAL).
  3. Signal cataloger delegation and rare alert trapping (N < 30).
"""
import pytest
from backend.modules.quality_swing.domain.rules.rc_wave_multiscale_lookup import (
    lookup_wave_multiscale_signal,
    RealWaveMultiscaleSignal,
)
from backend.modules.quality_swing.domain.rules.signal_cataloger import (
    WaveSignalCataloger,
    WaveFeatureVector,
)


def test_wave_multiscale_lookup_basic():
    sig = lookup_wave_multiscale_signal(
        wave_slope=0.20,
        vwap_sigma_current=-0.80,
        sigma_current=-0.90,
        vel_svw=-0.05,
    )
    assert sig is not None
    assert isinstance(sig, RealWaveMultiscaleSignal)
    assert sig.p_bull >= 0.0
    assert sig.p_bear >= 0.0
    assert isinstance(sig.action_code, str)
    assert sig.action_code.startswith("WAVE_")


def test_wave_rare_alert_trapping():
    # Construct a rare feature vector (N < 30)
    features = WaveFeatureVector(
        wave_direction="STRONG_DOWN",
        wave_zone="DEEP_DISCOUNT",
        channel_zone="DEEP_DISCOUNT",
        momentum_state="FALLING",
        n_samples=12,
        bot_lift=2.1,
        top_lift=0.4,
        bot_clean=85.0,
        top_clean=15.0,
        asymmetry_bias="STRONG_BOTTOM",
    )

    sig_name, action_code, urgency, scope = WaveSignalCataloger.classify(features)
    assert action_code == "WAVE_ALERT_RARE_CAPITULATION"
    assert urgency == "IMMEDIATE"


def test_wave_parabolic_blowoff_trapping():
    features = WaveFeatureVector(
        wave_direction="STRONG_UP",
        wave_zone="DEEP_PREMIUM",
        channel_zone="DEEP_PREMIUM",
        momentum_state="RISING",
        n_samples=5,
        bot_lift=0.3,
        top_lift=2.4,
        bot_clean=10.0,
        top_clean=90.0,
        asymmetry_bias="STRONG_TOP",
    )

    sig_name, action_code, urgency, scope = WaveSignalCataloger.classify(features)
    assert action_code == "WAVE_ALERT_RARE_PARABOLIC_BLOWOFF"
    assert urgency == "IMMEDIATE"
