#!/usr/bin/env python3
"""
Generate EV Derived Table — Committee-approved signals from EV probability table
====================================================================================
Reads:  rc_ev_probability_table.json (from train_ev_table.py)
Writes: rc_ev_derived.json (replaces rc_combined_derived.json)

Signal classification based on Expected Value (not P(bull)):
  BLOCK       — EV < -2% (value trap)
  ACCUMULATE  — EV > +1% AND Ann Sharpe > 0.5
  BUY_DIP     — EV > +0.5% AND P(MIN) > 40% (dip with positive EV)
  TAKE_PROFIT — EV < -3% in CEILING (blow-off top)
  REDUCE      — EV < 0 in CEILING AND Ann Sharpe < 0
  MOMENTUM    — EV > +4% AND E[days] > 10 (strong trend, hold)
  WATCH       — |EV| < 0.5% (no edge)
  NO_EDGE     — default

Conviction based on Ann Sharpe (not just sample size):
  HIGH   — Ann Sharpe > 2.0 AND N > 1000
  MEDIUM — Ann Sharpe > 0.5 AND N > 300
  LOW    — else

Consistency: do all 3 zigzag levels agree on EV direction?
  ALIGNED_BULL — all 3 positive
  ALIGNED_BEAR — all 3 negative
  DIVERGENT   — mixed

Approved by: Committee (Dalio, Druckenmiller, PTJ/Eifert, Weinstein/Pring, LdP, Simons)
"""
import json
import math
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_PATH = ROOT / "backend/modules/quality_swing/domain/rules/rc_ev_probability_table.json"
OUT_PATH = ROOT / "backend/modules/quality_swing/domain/rules/rc_ev_derived.json"

ZONE_MAP = {"<<": "FLOOR", "<": "BELOW", "~": "NEUTRAL", ">": "ABOVE", ">>": "CEILING"}

# CEILING zone zz50_max baseline — same as generate_derived_table.py
_CEILING_ZZ50_MAX_BASELINE = 7.15


# ═══════════════════════════════════════════════════════════════
# Classification helpers
# ═══════════════════════════════════════════════════════════════

def extract_zone(state_key: str) -> str:
    """Extract zone from state key (last component)."""
    parts = state_key.split("|")
    return ZONE_MAP.get(parts[-1], "NEUTRAL")


def extract_regime(state_key: str) -> str:
    """Classify T×C momentum regime (same as generate_derived_table.py)."""
    parts = state_key.split("|")
    t, c = parts[0], parts[1]
    t_strong_pos = t in ["T+++", "T++"]
    t_strong_neg = t in ["T---", "T--"]
    c_strong_pos = c in ["C+++", "C++"]
    c_strong_neg = c in ["C---", "C--"]

    if not (t_strong_pos or t_strong_neg) or not (c_strong_pos or c_strong_neg):
        return "TRANSITION"
    if t_strong_pos and c_strong_pos:
        return "ALIGN_BULL"
    if t_strong_neg and c_strong_neg:
        return "ALIGN_BEAR"
    if t_strong_neg and c_strong_pos:
        return "DIV_UP"
    return "DIV_DOWN"


def classify_signal(ev: float, zone: str, ann_sharpe: float, p_min: float) -> str:
    """Assign signal based on EV. Priority order — first match wins.

    Based on committee-approved thresholds:
      Dalio: EV primary metric
      PTJ: Hard block on EV < -2%
      Druckenmiller: ACCUMULATE needs Sharpe confirmation
      Weinstein: CEILING zone gets preventive treatment
    """
    # 1. BLOCK — value trap (PTJ directive)
    if ev < -0.02:
        return "BLOCK"

    # 2. TAKE_PROFIT — blow-off top in CEILING
    if zone == "CEILING" and ev < -0.03:
        return "TAKE_PROFIT"

    # 3. REDUCE — CEILING with negative EV
    if zone == "CEILING" and ev < 0 and ann_sharpe < 0:
        return "REDUCE"

    # 4. ACCUMULATE — positive EV with Sharpe confirmation
    if ev > 0.01 and ann_sharpe > 0.5:
        return "ACCUMULATE"

    # 5. BUY_DIP — dip with modest positive EV
    if ev > 0.005 and p_min > 0.40:
        return "BUY_DIP"

    # 6. MOMENTUM — strong trend, hold
    if ev > 0.04 and ann_sharpe > 1.0:
        return "MOMENTUM"

    # 7. WATCH — no clear edge
    if abs(ev) < 0.005:
        return "WATCH"

    # 8. NO_EDGE — default
    return "NO_EDGE"


def classify_conviction(ann_sharpe: float, n: int) -> str:
    """Conviction based on Ann Sharpe and sample size."""
    if ann_sharpe > 2.0 and n > 1000:
        return "HIGH"
    if ann_sharpe > 0.5 and n > 300:
        return "MEDIUM"
    return "LOW"


def conviction_score(ann_sharpe: float, n: int) -> int:
    """Conviction score 0-100 based on Ann Sharpe × log(N)."""
    if n <= 1:
        return 0
    return min(100, round(math.log(n) * max(ann_sharpe, 0) / 3.0))


def compute_signal_confidence(
    signal: str,
    n: int,
    ev: float,
    ann_sharpe: float,
    std_return: float,
    e_days: float,
) -> int:
    """Signal confidence score (0-100).

    Combines:
      w_N          — sample size (same as original)
      w_edge       — EV strength (signal-specific)
      w_stability  — penalizes high volatility relative to EV
      w_horizon    — rewards states with clear time horizon
    """
    # w_N: sample size weight (same formula as original)
    w_N = 1.0 - math.exp(-n / 1000.0)

    # w_edge: EV-based edge strength
    if signal == "ACCUMULATE":
        w_edge = min(1.0, ev / 0.05)  # 5% EV = full confidence
    elif signal == "BUY_DIP":
        w_edge = min(1.0, ev / 0.02)  # 2% EV = full
    elif signal == "BLOCK":
        w_edge = min(1.0, abs(ev) / 0.04)  # 4% negative EV = full
    elif signal == "TAKE_PROFIT":
        w_edge = min(1.0, abs(ev) / 0.05)
    elif signal == "REDUCE":
        w_edge = min(1.0, abs(ev) / 0.03)
    elif signal == "MOMENTUM":
        w_edge = min(1.0, ev / 0.06)
    else:  # WATCH, NO_EDGE
        w_edge = 0.25

    # w_stability: penalize high volatility (low Sharpe)
    if ann_sharpe > 1.0:
        w_stability = 1.0
    elif ann_sharpe > 0.5:
        w_stability = 0.75
    elif ann_sharpe > 0:
        w_stability = 0.5
    else:
        w_stability = 0.25

    # w_horizon: clear time horizon (5-30 days = stable)
    if 5 <= e_days <= 30:
        w_horizon = 1.0
    elif e_days < 5:
        w_horizon = 0.7  # too short — noisy
    else:
        w_horizon = 0.8  # too long — uncertainty

    confidence = 100.0 * w_N * w_edge * w_stability * w_horizon
    return min(100, max(0, round(confidence)))


def classify_consistency(levels_data: dict) -> str:
    """Check if all 3 zigzag levels agree on EV direction."""
    evs = []
    for lvl in ["zz25", "zz50", "zz75"]:
        if lvl in levels_data:
            evs.append(levels_data[lvl]["ev"])

    if len(evs) < 2:
        return "INSUFFICIENT"

    positive = sum(1 for e in evs if e > 0)
    negative = sum(1 for e in evs if e < 0)

    if positive == len(evs):
        return "ALIGNED_BULL"
    if negative == len(evs):
        return "ALIGNED_BEAR"
    return "DIVERGENT"


def generate_reading(state_key: str, s: dict) -> str:
    """Generate English reading from EV metrics."""
    zone = extract_zone(state_key)
    regime = extract_regime(state_key)
    signal = s["identity"]["signal"]
    ev = s["levels"]["zz25"]["ev"]
    p_min = s["levels"]["zz25"]["p_min"]
    e_ret_min = s["levels"]["zz25"]["e_ret_min"]
    e_ret_max = s["levels"]["zz25"]["e_ret_max"]
    n = s["levels"]["zz25"]["n"]
    ann_sharpe = s["identity"]["ann_sharpe"]
    e_days = s["levels"]["zz25"]["e_days"]
    fatigue = s.get("fatigue", {}).get("fatigue_type", "N/A")
    consistency = s["identity"]["consistency"]

    parts = []
    parts.append(f"{zone} in {regime} regime.")
    parts.append(f"EV={ev:+.2f} (P(MIN)={p_min:.0%}, E[ret|MIN]={e_ret_min:+.1%}, E[ret|MAX]={e_ret_max:+.1%}).")
    parts.append(f"Ann Sharpe={ann_sharpe:+.2f}, horizon={e_days:.0f}d, N={n:,}.")
    parts.append(f"Consistency: {consistency}. Fatigue: {fatigue}.")
    parts.append(f"Signal: {signal}.")

    return " ".join(parts)


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    with open(RAW_PATH) as f:
        raw = json.load(f)

    states_raw = raw["states"]
    n_total = raw["n_total_observations"]
    n_tickers = raw["n_tickers"]

    states_out = {}

    for state_key, state_data in states_raw.items():
        levels = state_data["levels"]
        fatigue_data = state_data.get("fatigue", {"buckets": {}, "fatigue_type": "INSUFFICIENT_DATA"})

        # Primary level: zz25
        if "zz25" not in levels:
            continue
        primary = levels["zz25"]

        zone = extract_zone(state_key)
        regime = extract_regime(state_key)

        # Compute annualized Sharpe
        e_days = primary["e_days"]
        std_ret = primary["std_return"]
        sharpe = primary["sharpe"]
        swings_per_year = 252 / e_days if e_days > 0 else 0
        ann_sharpe = sharpe * math.sqrt(swings_per_year) if swings_per_year > 0 else 0

        # Classify signal
        ev = primary["ev"]
        p_min = primary["p_min"]
        signal = classify_signal(ev, zone, ann_sharpe, p_min)

        # Conviction
        n = primary["n"]
        conviction = classify_conviction(ann_sharpe, n)
        conv_score = conviction_score(ann_sharpe, n)

        # Signal confidence
        sig_confidence = compute_signal_confidence(
            signal=signal, n=n, ev=ev, ann_sharpe=ann_sharpe,
            std_return=std_ret, e_days=e_days,
        )

        # Consistency across zigzag levels
        consistency = classify_consistency(levels)

        # Hard block?
        hard_block = (ev < -0.02)
        block_reason = ""
        if hard_block:
            block_reason = (
                f"NEGATIVE_EV: EV={ev:+.2%}, P(MIN)={p_min:.0%} but "
                f"E[ret|MIN]={primary['e_ret_min']:+.1%}. Value trap."
            )

        # Assemble state
        state_obj = {
            "identity": {
                "zone": zone,
                "regime": regime,
                "signal": signal,
                "signal_confidence": sig_confidence,
                "conviction": conviction,
                "conviction_score": conv_score,
                "hard_block": hard_block,
                "block_reason": block_reason if hard_block else "",
                "consistency": consistency,
                "ann_sharpe": round(ann_sharpe, 2),
            },
            "levels": levels,
            "primary_ev": ev,
            "primary_horizon_days": e_days,
            "primary_p_min": p_min,
            "primary_e_ret_min": primary["e_ret_min"],
            "primary_e_ret_max": primary["e_ret_max"],
            "primary_n": n,
            "fatigue": fatigue_data,
        }

        state_obj["reading"] = generate_reading(state_key, state_obj)
        states_out[state_key] = state_obj

    # ── Assemble final JSON ──
    output = {
        "version": f"v1_ev_derived_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "source": "rc_ev_probability_table.json v1",
        "model_type": "forward_pivot_expected_value",
        "approved_by": "Committee: Dalio (CIO), Druckenmiller (Quality Swing), PTJ/Eifert (Speculative), Weinstein/Pring (Rotation), LdP (Quantitative), Simons (ML)",

        "context": {
            "what": "Pre-computed Expected Value lookup table for the Swing Gate (Quality Swing department).",
            "how": "Each cell describes the Expected Value of the next zigzag pivot when the 3 dimensions (T, C, sigma_vw) align in that configuration.",
            "dimensions": "T_slope (Tide, long-term) x C_slope (Current, medium-term) x sigma_vwap_wave (price position vs VWAP Wave)",
            "n_states": len(states_out),
            "n_observations": n_total,
            "n_tickers": n_tickers,
            "label_definition": "next zigzag pivot type (MIN/MAX) + swing_return formed AFTER current bar",
            "label_type": "forward (no look-ahead bias from zigzag stereotypes)",
            "ev_formula": "EV = P(MIN)*E[swing_return|MIN] + P(MAX)*E[swing_return|MAX]",
            "signal_basis": "EV + Ann Sharpe (not P(bull))",
            "zigzag_levels": raw.get("zigzag_levels", [0.025, 0.05, 0.075]),
        },

        "states": states_out,
    }

    with open(OUT_PATH, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # ── Summary ──
    sig_counts = Counter(s["identity"]["signal"] for s in states_out.values())
    conv_counts = Counter(s["identity"]["conviction"] for s in states_out.values())
    consistency_counts = Counter(s["identity"]["consistency"] for s in states_out.values())
    blocked = sum(1 for s in states_out.values() if s["identity"]["hard_block"])

    print(f"Generated {OUT_PATH}")
    print(f"   States: {len(states_out)}")
    print(f"   Signals: {dict(sig_counts.most_common())}")
    print(f"   Conviction: {dict(conv_counts.most_common())}")
    print(f"   Consistency: {dict(consistency_counts.most_common())}")
    print(f"   Hard blocked: {blocked}")


if __name__ == "__main__":
    main()
