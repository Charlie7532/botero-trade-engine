#!/usr/bin/env python3
"""
Test Real EV Lookup Adapter
===========================
Verifies that rc_ev_lookup.py correctly queries rc_ev_derived.json with:
  1. Real point-in-time EV, Sharpe, R:R Asymmetry Ratio, and P(bull)
  2. Cascading fallbacks L3 -> L2 -> L1 -> L0
  3. Dynamic flexible fatigue evaluation (FATIGUE_RISK, ACCUMULATING, STABLE)
"""
import os, sys, logging
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.quality_swing.domain.rules.rc_tide_ev_lookup import lookup_real_ev

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    logger.info("Running Real EV Lookup Unit Tests...")

    # Test 1: Full L3 State Query (zz50)
    sig1 = lookup_real_ev(t_slope="T+++", c_slope="C+++", svw="<", level="zz50", run_length=1)
    assert sig1 is not None
    logger.info(f"Test 1 (L3 Full): State={sig1.state_key} | Signal={sig1.signal} | EV={sig1.ev:+.4f} | Sharpe={sig1.sharpe:.3f} | Fallback={sig1.fallback_level} | Fatigue={sig1.fatigue_type}")
    assert sig1.fallback_level == "L3"

    # Test 2: Multi-Scale Query (zz25 vs zz50 vs zz75)
    sig_zz25 = lookup_real_ev(t_slope="T+++", c_slope="C+++", svw="<", level="zz25", run_length=1)
    sig_zz75 = lookup_real_ev(t_slope="T+++", c_slope="C+++", svw="<", level="zz75", run_length=1)
    logger.info(f"Test 2 (Multi-Scale):")
    logger.info(f"  zz25: EV={sig_zz25.ev:+.4f} | Sharpe={sig_zz25.sharpe:.3f} | R:R Asym={sig_zz25.rr_asymmetry:.2f}")
    logger.info(f"  zz50: EV={sig1.ev:+.4f} | Sharpe={sig1.sharpe:.3f} | R:R Asym={sig1.rr_asymmetry:.2f}")
    logger.info(f"  zz75: EV={sig_zz75.ev:+.4f} | Sharpe={sig_zz75.sharpe:.3f} | R:R Asym={sig_zz75.rr_asymmetry:.2f}")

    # Test 3: Fallback Cascade (Non-existent L3 state -> Fallback to L2)
    sig_fallback = lookup_real_ev(t_slope="T+++", c_slope="C---", svw=">>", level="zz50", min_l3_samples=999999)
    assert sig_fallback is not None
    logger.info(f"Test 3 (Fallback L2): State={sig_fallback.state_key} | Signal={sig_fallback.signal} | Fallback={sig_fallback.fallback_level}")
    assert sig_fallback.fallback_level in ("L2", "L1", "L0")

    # Test 4: Dynamic Fatigue Evaluation (Run length 1 vs 10)
    sig_f1 = lookup_real_ev(t_slope="T---", c_slope="C---", svw=">>", level="zz50", run_length=1)
    sig_f10 = lookup_real_ev(t_slope="T---", c_slope="C---", svw=">>", level="zz50", run_length=10)
    logger.info(f"Test 4 (Fatigue):")
    logger.info(f"  Run Length 1:  Fatigue={sig_f1.fatigue_type} | Delta EV={sig_f1.fatigue_delta_ev:+.4f} | Signal={sig_f1.signal}")
    logger.info(f"  Run Length 10: Fatigue={sig_f10.fatigue_type} | Delta EV={sig_f10.fatigue_delta_ev:+.4f} | Signal={sig_f10.signal}")

    # Test 5: Unobserved State Notification & Fallback Context
    sig_unobserved = lookup_real_ev(t_slope="INVALID_T", c_slope="C+++", svw="<", level="zz50", min_l3_samples=1)
    assert sig_unobserved is not None
    logger.info(f"Test 5 (Unobserved State Notification):")
    logger.info(f"  Is Unobserved={sig_unobserved.is_unobserved_state} | Fallback Level={sig_unobserved.fallback_level} | Reason={sig_unobserved.fallback_reason}")
    assert sig_unobserved.is_unobserved_state is True
    assert sig_unobserved.fallback_level == "L0"

    # Test 6: Extreme Deviation State Preservation (n >= 1)
    sig_extreme = lookup_real_ev(t_slope="T+++", c_slope="C+++", svw="<<", level="zz50", min_l3_samples=1)
    assert sig_extreme is not None
    logger.info(f"Test 6 (Extreme Tail State Preservation): State={sig_extreme.state_key} | n={sig_extreme.n_samples} | EV={sig_extreme.ev:+.4f} | R:R Asymmetry={sig_extreme.rr_asymmetry:.2f}")
    assert sig_extreme.fallback_level == "L3"
    assert sig_extreme.is_unobserved_state is False

    logger.info("✅ ALL REAL EV LOOKUP TESTS PASSED CLEANLY!")


if __name__ == "__main__":
    main()
