#!/usr/bin/env python3
"""
Generate Wave Derived Table — rc_wave_derived.json
====================================================
Reads:  rc_wave_probability_table.json (raw counts)
Writes: rc_wave_derived.json (decision-ready with signals, lifts, reversal quality)

Usage:
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
    backend/scripts/generate_wave_derived_table.py
"""
import json, math, logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

root_dir = Path(__file__).resolve().parent.parent.parent
RULES_DIR = root_dir / "backend/modules/quality_swing/domain/rules"
RAW_TABLE = RULES_DIR / "rc_wave_probability_table.json"
DERIVED_TABLE = RULES_DIR / "rc_wave_derived.json"

STEREO_KEYS = ["HH", "HL", "LH", "LL"]
ZZ_EVENTS_MIN = ["zz25_min", "zz50_min", "zz75_min"]
ZZ_EVENTS_MAX = ["zz25_max", "zz50_max", "zz75_max"]
ZZ_EVENTS = ZZ_EVENTS_MIN + ZZ_EVENTS_MAX

# Wave direction labels
WAVE_DIR = {
    "W+++": "STRONG_UP", "W++": "MODERATE_UP", "W+": "MILD_UP",
    "W-": "MILD_DOWN", "W--": "MODERATE_DOWN", "W---": "STRONG_DOWN",
}

# Zone labels from sigma
ZONE_LABELS = {
    "<<": "DEEP_DISCOUNT", "<": "DISCOUNT", "~": "FAIR_VALUE",
    ">": "PREMIUM", ">>": "EXTREME_PREMIUM",
}

VEL_LABELS = {"▼": "FALLING", "~": "NEUTRAL", "▲": "RISING"}


def parse_key(key: str):
    """Parse state key like 'L1:W---|σVc:<<|σc:<|vel:▼' into components."""
    # Strip level prefix
    if ":" in key and key.split(":")[0] in ("L1", "L2", "L3"):
        _, rest = key.split(":", 1)
    else:
        rest = key

    parts = rest.split("|")
    result = {}
    for p in parts:
        if p.startswith("W"):
            result["W"] = p
        elif p.startswith("σVc:"):
            result["σVc"] = p.split(":")[1]
        elif p.startswith("σc:"):
            result["σc"] = p.split(":")[1]
        elif p.startswith("vel:"):
            result["vel"] = p.split(":")[1]
    return result


def compute_reversal_quality(stereo_before: dict, stereo_after: dict, tp_type_is_min: bool) -> dict:
    """Compute reversal quality from stereo_before and stereo_after distributions.

    For MIN pivots: clean reversal = second letter changes L→H (xL → xH)
    For MAX pivots: clean reversal = first letter changes H→L (Hx → Lx)
    """
    total_before = sum(stereo_before.values())
    total_after = sum(stereo_after.values())

    if total_before == 0 or total_after == 0:
        return {
            "dominant_before": "??",
            "dominant_after": "??",
            "transition_tag": "??→??",
            "pct_clean": 0.0,
        }

    dominant_before = max(stereo_before, key=stereo_before.get)
    dominant_after = max(stereo_after, key=stereo_after.get)

    # Count clean reversals
    if tp_type_is_min:
        # Clean: second letter goes L→H
        clean_before = sum(v for k, v in stereo_before.items() if k[1] == "L")
        clean_after = sum(v for k, v in stereo_after.items() if k[1] == "H")
    else:
        # Clean: first letter goes H→L
        clean_before = sum(v for k, v in stereo_before.items() if k[0] == "H")
        clean_after = sum(v for k, v in stereo_after.items() if k[0] == "L")

    # pct_clean = average of "before had right setup" and "after shows reversal"
    pct_before = clean_before / total_before * 100 if total_before else 0
    pct_after = clean_after / total_after * 100 if total_after else 0
    pct_clean = (pct_before + pct_after) / 2

    return {
        "dominant_before": dominant_before,
        "dominant_after": dominant_after,
        "transition_tag": f"{dominant_before}→{dominant_after}",
        "pct_clean": round(pct_clean, 1),
    }


def classify_signal(bot_lift, top_lift, bot_clean, top_clean, bias, n):
    """Classify the Wave signal."""
    if n < 30:
        return "NO_EDGE"

    if bot_lift >= 1.5 and bot_clean >= 50.0 and bias in ("STRONG_BOTTOM", "MILD_BOTTOM"):
        return "APPROACHING_BOTTOM"
    if bot_lift >= 1.2 and bias == "STRONG_BOTTOM":
        return "WATCH_BOTTOM"
    if top_lift >= 1.5 and top_clean >= 50.0 and bias in ("STRONG_TOP", "MILD_TOP"):
        return "APPROACHING_TOP"
    if top_lift >= 1.2 and bias == "STRONG_TOP":
        return "WATCH_TOP"
    if bot_lift < 0.5 and top_lift < 0.5:
        return "CONTINUATION"
    return "NO_EDGE"


def classify_microstructure(wave_dir, signal, vel_state):
    """Classify microstructure type."""
    if signal == "APPROACHING_BOTTOM" and wave_dir in ("STRONG_DOWN", "MODERATE_DOWN"):
        return "EXHAUSTION_BOTTOM"
    if signal == "APPROACHING_TOP" and wave_dir in ("STRONG_UP", "MODERATE_UP"):
        return "EXHAUSTION_TOP"
    if signal in ("APPROACHING_BOTTOM", "WATCH_BOTTOM") and wave_dir in ("MILD_UP", "MODERATE_UP"):
        return "DIVERGENCE"
    if signal == "CONTINUATION":
        return "CONTINUATION"
    return "NEUTRAL"


def conviction_score(lift_best, n, pct_clean):
    """Compute conviction score 0-100."""
    if n < 30:
        return 0
    lift_score = min(lift_best / 2.0, 1.0) * 40
    n_score = min(math.log(max(n, 1)) / 8.0, 1.0) * 30
    quality_score = (pct_clean / 100.0) * 30
    return min(100, round(lift_score + n_score + quality_score))


def derive_state(key, cell, baselines, n_total_obs):
    """Derive decision-ready state from raw cell."""
    parsed = parse_key(key)
    n = cell["n_total"]
    sc = cell["stereo_counts"]

    # P(bull) from causal stereotypes
    p_bull = (sc.get("HH", 0) + sc.get("HL", 0)) / n * 100 if n else 50.0

    # Identity
    w_dir = WAVE_DIR.get(parsed.get("W", "W+"), "NEUTRAL")
    w_zone = ZONE_LABELS.get(parsed.get("σVc", "~"), "FAIR_VALUE")
    ch_zone = ZONE_LABELS.get(parsed.get("σc", "~"), "FAIR_VALUE")
    vel_state = VEL_LABELS.get(parsed.get("vel", "~"), "NEUTRAL")

    # ── Bottom prediction (T-1 pre) ──
    bottom_metrics = {}
    for ev in ZZ_EVENTS_MIN:
        pre = cell["pre"][ev]
        count = pre["count"]
        baseline = baselines.get(ev, {}).get("rate_pct", 10.0)
        p_local = count / n * 100 if n else 0
        lift = p_local / baseline if baseline > 0 else 0
        dominant = max(pre["stereo"], key=pre["stereo"].get) if count > 0 else "??"
        p_dom = pre["stereo"].get(dominant, 0) / count * 100 if count > 0 else 0

        bottom_metrics[ev] = {
            "p_local": round(p_local, 2),
            "lift": round(lift, 2),
            "one_in": round(n / count) if count > 0 else 0,
            "count": count,
            "p_global": round(count / baselines.get(ev, {}).get("total", 1) * 100, 2),
            "pre_dominant_stereo": dominant,
            "p_dominant": round(p_dom, 1),
        }

    # Composite bottom: use zz25_min (finest level, captures all bottoms)
    bot_25 = bottom_metrics.get("zz25_min", {})
    bot_lift_best = max(m["lift"] for m in bottom_metrics.values()) if bottom_metrics else 0

    # ── Top prediction (T-1 pre) ──
    top_metrics = {}
    for ev in ZZ_EVENTS_MAX:
        pre = cell["pre"][ev]
        count = pre["count"]
        baseline = baselines.get(ev, {}).get("rate_pct", 10.0)
        p_local = count / n * 100 if n else 0
        lift = p_local / baseline if baseline > 0 else 0
        dominant = max(pre["stereo"], key=pre["stereo"].get) if count > 0 else "??"
        p_dom = pre["stereo"].get(dominant, 0) / count * 100 if count > 0 else 0

        top_metrics[ev] = {
            "p_local": round(p_local, 2),
            "lift": round(lift, 2),
            "one_in": round(n / count) if count > 0 else 0,
            "count": count,
            "p_global": round(count / baselines.get(ev, {}).get("total", 1) * 100, 2),
            "pre_dominant_stereo": dominant,
            "p_dominant": round(p_dom, 1),
        }

    top_25 = top_metrics.get("zz25_max", {})
    top_lift_best = max(m["lift"] for m in top_metrics.values()) if top_metrics else 0

    # ── Reversal quality (T=0 at) ──
    at_min_25 = cell["at"]["zz25_min"]
    rev_bottom = compute_reversal_quality(
        at_min_25["stereo_before"], at_min_25["stereo_after"], tp_type_is_min=True
    )

    at_max_25 = cell["at"]["zz25_max"]
    rev_top = compute_reversal_quality(
        at_max_25["stereo_before"], at_max_25["stereo_after"], tp_type_is_min=False
    )

    # ── Asymmetry ──
    p_any_bottom = bot_25.get("p_local", 0)
    p_any_top = top_25.get("p_local", 0)
    ratio = p_any_bottom / p_any_top if p_any_top > 0 else (999 if p_any_bottom > 0 else 1)

    if ratio >= 5:
        bias = "STRONG_BOTTOM"
    elif ratio >= 2:
        bias = "MILD_BOTTOM"
    elif ratio <= 0.2:
        bias = "STRONG_TOP"
    elif ratio <= 0.5:
        bias = "MILD_TOP"
    else:
        bias = "NEUTRAL"

    # ── Signal classification ──
    signal = classify_signal(
        bot_lift_best, top_lift_best,
        rev_bottom["pct_clean"], rev_top["pct_clean"],
        bias, n
    )

    micro_type = classify_microstructure(w_dir, signal, vel_state)
    conv = conviction_score(
        bot_lift_best if "BOTTOM" in signal else top_lift_best,
        n,
        rev_bottom["pct_clean"] if "BOTTOM" in signal else rev_top["pct_clean"],
    )

    if conv >= 60:
        conviction_label = "HIGH"
    elif conv >= 35:
        conviction_label = "MEDIUM"
    else:
        conviction_label = "LOW"

    # ── Reading ──
    reading_parts = [
        f"{w_dir} wave, VWAP zone={w_zone}, channel zone={ch_zone}, momentum {vel_state}.",
        f"P_bull={p_bull:.1f}%.",
    ]
    if "BOTTOM" in signal:
        reading_parts.append(
            f"BOTTOM: p={p_any_bottom:.1f}% (lift {bot_lift_best:.2f}×), "
            f"reversal {rev_bottom['transition_tag']} ({rev_bottom['pct_clean']:.0f}% clean)."
        )
    if "TOP" in signal:
        reading_parts.append(
            f"TOP: p={p_any_top:.1f}% (lift {top_lift_best:.2f}×), "
            f"reversal {rev_top['transition_tag']} ({rev_top['pct_clean']:.0f}% clean)."
        )
    reading_parts.append(f"Signal: {signal}. Microstructure: {micro_type}.")
    reading = " ".join(reading_parts)

    return {
        "identity": {
            "wave_direction": w_dir,
            "wave_zone": w_zone,
            "channel_zone": ch_zone,
            "momentum_state": vel_state,
            "signal": signal,
            "conviction": conviction_label,
            "conviction_score": conv,
            "microstructure_type": micro_type,
        },
        "frequency": {
            "N": n,
            "pct_of_total": round(n / n_total_obs * 100, 2) if n_total_obs else 0,
            "p_bull": round(p_bull, 1),
        },
        "pivot_prediction": {
            "bottom": bottom_metrics,
            "top": top_metrics,
            "composite": {
                "p_any_bottom": round(p_any_bottom, 2),
                "p_any_top": round(p_any_top, 2),
                "lift_best_bottom": round(bot_lift_best, 2),
                "lift_best_top": round(top_lift_best, 2),
            },
            "asymmetry": {
                "bottom_vs_top_ratio": round(ratio, 2),
                "bias": bias,
            },
        },
        "reversal_quality": {
            "bottom": rev_bottom,
            "top": rev_top,
        },
        "reading": reading,
    }


def main():
    logger.info("=" * 90)
    logger.info("  GENERATE WAVE DERIVED TABLE — rc_wave_derived.json")
    logger.info("=" * 90)

    with open(RAW_TABLE) as f:
        raw = json.load(f)

    n_total_obs = raw["n_total_observations"]
    n_tickers = raw["n_tickers"]
    cells = raw["cells"]

    logger.info(f"  Raw table: {len(cells)} cells, {n_total_obs:,} observations, {n_tickers} tickers")

    # ── Compute baselines ──
    # Global pivot rates: total pivots / total observations
    baselines = {}
    for ev in ZZ_EVENTS:
        # Sum across all L1 cells
        total_pre = sum(
            c["pre"][ev]["count"]
            for c in cells.values()
            if c["level"] == "L1_full"
        )
        total_at = sum(
            c["at"][ev]["count"]
            for c in cells.values()
            if c["level"] == "L1_full"
        )
        # Use L1 total observations
        l1_total = sum(c["n_total"] for c in cells.values() if c["level"] == "L1_full")
        rate_pct = total_pre / l1_total * 100 if l1_total else 0
        baselines[ev] = {
            "rate_pct": round(rate_pct, 2),
            "total": total_pre,
            "total_at": total_at,
            "one_in": round(l1_total / total_pre) if total_pre else 0,
        }

    logger.info("\n  Baselines (T-1 pre rates):")
    for ev, bl in sorted(baselines.items()):
        logger.info(f"    {ev}: {bl['rate_pct']:.2f}% ({bl['total']:,} pivots, 1-in-{bl['one_in']})")

    # ── Derive states ──
    states = {}
    for key, cell in cells.items():
        states[key] = derive_state(key, cell, baselines, n_total_obs)

    # ── Pass 2: Hierarchical L1->L2->L3 linkage & Empirical Bayes Shrinkage ──
    for key, state in states.items():
        if key.startswith("L1:"):
            parsed = parse_key(key)
            w = parsed.get("W", "")
            svc = parsed.get("σVc", "")
            l2_key = f"L2:{w}|σVc:{svc}"
            l3_key = f"L3:σVc:{svc}"

            l2_state = states.get(l2_key)
            l3_state = states.get(l3_key) or states.get(f"L3:σVc:{svc}")

            if l2_state:
                l1_n = state["frequency"]["N"]
                l1_p_bot = state["pivot_prediction"]["composite"]["p_any_bottom"]
                l1_p_top = state["pivot_prediction"]["composite"]["p_any_top"]
                l2_p_bot = l2_state["pivot_prediction"]["composite"]["p_any_bottom"]
                l2_p_top = l2_state["pivot_prediction"]["composite"]["p_any_top"]

                # Empirical Bayes shrinkage (k=20)
                k_bayes = 20.0
                p_bot_bayes = (l1_n * l1_p_bot + k_bayes * l2_p_bot) / (l1_n + k_bayes) if l1_n > 0 else l2_p_bot
                bl_bot = baselines.get("zz25_min", {}).get("rate_pct", 10.34)
                lift_bot_bayes = p_bot_bayes / bl_bot if bl_bot > 0 else 1.0

                l2_lift_bot = l2_state["pivot_prediction"]["composite"]["lift_best_bottom"]
                lift_vs_l2 = l1_p_bot / l2_p_bot if l2_p_bot > 0 else 1.0

                state["hierarchy"] = {
                    "parent_l2_key": l2_key,
                    "parent_l3_key": l3_key,
                    "l2_lift_best_bottom": round(l2_lift_bot, 2),
                    "lift_vs_parent_l2": round(lift_vs_l2, 2),
                    "bayes_p_bottom": round(p_bot_bayes, 2),
                    "bayes_lift_bottom": round(lift_bot_bayes, 2),
                }

    # Compute Shannon Mutual Information I(State; Turn_zz25_min)
    import math
    def compute_mutual_info(level_prefix):
        sub_states = {k: v for k, v in states.items() if k.startswith(level_prefix)}
        total_n = sum(s["frequency"]["N"] for s in sub_states.values())
        if not total_n:
            return 0.0
        bl_bot = baselines.get("zz25_min", {}).get("rate_pct", 10.34) / 100.0
        mi = 0.0
        for s in sub_states.values():
            n_s = s["frequency"]["N"]
            if not n_s:
                continue
            p_s = n_s / total_n
            p_turn_given_s = s["pivot_prediction"]["composite"]["p_any_bottom"] / 100.0
            p_no_turn_given_s = 1.0 - p_turn_given_s

            # Term for (state, turn)
            if p_turn_given_s > 0 and bl_bot > 0:
                mi += p_s * p_turn_given_s * math.log2(p_turn_given_s / bl_bot)
            # Term for (state, no_turn)
            if p_no_turn_given_s > 0 and (1.0 - bl_bot) > 0:
                mi += p_s * p_no_turn_given_s * math.log2(p_no_turn_given_s / (1.0 - bl_bot))
        return round(mi, 4)

    mi_l1 = compute_mutual_info("L1_full:") or compute_mutual_info("L1:")
    mi_l2 = compute_mutual_info("L2_w_svc:") or compute_mutual_info("L2:")
    mi_l3 = compute_mutual_info("L3_w:") or compute_mutual_info("L3:")

    # Compute global p_bull
    l1_states = {k: v for k, v in states.items() if cells[k]["level"] == "L1_full"}
    if l1_states:
        weighted_p_bull = sum(
            v["frequency"]["p_bull"] * v["frequency"]["N"]
            for v in l1_states.values()
        ) / sum(v["frequency"]["N"] for v in l1_states.values())
    else:
        weighted_p_bull = 50.0

    # Rank by N
    ranked = sorted(states.items(), key=lambda x: -x[1]["frequency"]["N"])
    for rank, (key, state) in enumerate(ranked, 1):
        state["frequency"]["rank"] = rank

    # Signal distribution
    from collections import Counter
    sig_counts = Counter(s["identity"]["signal"] for s in states.values())

    derived = {
        "version": f"v1_wave_derived_{datetime.now().strftime('%Y-%m-%d')}",
        "source": f"{RAW_TABLE.name} {raw['version']}",
        "context": {
            "what": "Wave pivot-prediction table for Swing Gate — complementary to Combined.",
            "approach": "Each cell answers: how likely is a zigzag pivot given this wave microstructure? And what reversal quality?",
            "dimensions": "W(6) × σVc(5) × σc(5) × vel_σVw(3) = 450 states",
            "shannon_mutual_info": {
                "L1_full": mi_l1,
                "L2_w_svc": mi_l2,
                "L3_w": mi_l3,
                "note": "Bits of Mutual Information I(WaveState; NearBottom) per resolution level",
            },
            "complementarity": "Combined: T×C trend + σVw position → P(bull). Wave: W cycle + σVc/σc position + σVw momentum → P(pivot).",
            "n_states": len(states),
            "n_observations": n_total_obs,
            "n_tickers": n_tickers,
            "global_p_bull": round(weighted_p_bull, 2),
        },
        "baselines": baselines,
        "vel_thresholds": raw.get("vel_thresholds"),
        "signal_distribution": dict(sig_counts.most_common()),
        "states": states,
    }

    with open(DERIVED_TABLE, "w") as f:
        json.dump(derived, f, indent=2, default=str)
    size_kb = DERIVED_TABLE.stat().st_size / 1024
    logger.info(f"\n  Derived table written: {DERIVED_TABLE.name} ({size_kb:.0f} KB)")
    logger.info(f"  States: {len(states)}")
    logger.info(f"  Signals: {dict(sig_counts.most_common())}")
    logger.info(f"  Global P(bull): {weighted_p_bull:.1f}%")

    # Sample states
    logger.info("\n  Top 5 states by N:")
    for key, state in ranked[:5]:
        ident = state["identity"]
        freq = state["frequency"]
        pp = state["pivot_prediction"]
        logger.info(
            f"    {key}: N={freq['N']:,}, P_bull={freq['p_bull']:.1f}%, "
            f"signal={ident['signal']}, conv={ident['conviction_score']}, "
            f"p_bot={pp['composite']['p_any_bottom']:.1f}%, "
            f"p_top={pp['composite']['p_any_top']:.1f}%, "
            f"bias={pp['asymmetry']['bias']}"
        )

    logger.info("=" * 90)


if __name__ == "__main__":
    main()
