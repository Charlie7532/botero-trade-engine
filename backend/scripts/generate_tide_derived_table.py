#!/usr/bin/env python3
"""
Generate rc_tide_derived.json v2 — Self-documenting, committee-approved.

Reads: rc_tide_probability_table.json (v3, 180 L1 states)
Writes: rc_tide_derived.json (v2, nested structure, English docs)

Approved by: Dalio (CIO), Druckenmiller (Quality Swing), PTJ/Eifert (Speculative),
             Weinstein/Pring (Rotation) — 2026-06-25
"""
import json
import math
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_PATH = ROOT / "backend/modules/quality_swing/domain/rules/rc_tide_probability_table.json"
OUT_PATH = ROOT / "backend/modules/quality_swing/domain/rules/rc_tide_derived.json"

GLOBAL_P_BULL = 0.6078
ZONE_MAP = {"<<": "FLOOR", "<": "BELOW", "~": "NEUTRAL", ">": "ABOVE", ">>": "CEILING"}
ZONE_LABELS = {
    "<<": "FLOOR — Price far below VWAP Wave",
    "<":  "BELOW — Price moderately below VWAP Wave",
    "~":  "NEUTRAL — Price near VWAP Wave",
    ">":  "ABOVE — Price moderately above VWAP Wave",
    ">>": "CEILING — Price far above VWAP Wave",
}


# ═══════════════════════════════════════════════════════════════
# Classification helpers
# ═══════════════════════════════════════════════════════════════

def classify_regime(t: str, c: str) -> str:
    """Classify T×C momentum regime."""
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


# CEILING zone zz50_max baseline — states must exceed this for TAKE_PROFIT via zz50
_CEILING_ZZ50_MAX_BASELINE = 7.15


def classify_signal(
    zone: str,
    p_bull: float,
    zz25_min_pct: float,
    zz25_max_pct: float,
    asym_pp: float,
    momentum_purity: float,
    zz50_min_pct: float = 0.0,
    zz75_min_pct: float = 0.0,
    zz50_max_pct: float = 0.0,
) -> str:
    """Assign one of 9 Universal Taxonomy Action Codes. Priority order — first match wins.

    Remediated v4 rules (meta-audit 2026-06-29, Universal Taxonomy 2026-07-25):
      STK_ACCUMULATE_STRUCTURAL — Deep capitulation: deep 5%/7.5% bottom density.
      STK_BUY_DIP_TACTICAL      — Statistical dip: asymmetry OR bottom density, p_bull<46.
      STK_TRIM_TACTICAL         — Blow-off top: zz25_max > 15% OR zz50_max above CEILING baseline
      STK_HOLD_EXTENDED         — CEILING but low structural top risk and strong p_bull.
      STK_DISTRIBUTE_DECAY      — Remaining CEILING: structural risk, preventive trim.
      STK_ACCUMULATE_PASSIVE    — Clean ABOVE uptrend with high purity.
      STK_HOLD_STABLE           — Stable ABOVE uptrend or WATCH/NO_EDGE.
    """
    # 1. ACCUMULATE — deep capitulation (5% or 7.5% zigzag bottoms)
    if zone == "FLOOR" and p_bull < 38.0 and (zz75_min_pct > 8.0 or zz50_min_pct > 12.0):
        return "STK_ACCUMULATE_STRUCTURAL"
    # 2. BUY_DIP — asymmetry edge or elevated minor bottom density
    if zone in ["FLOOR", "BELOW"] and p_bull < 46.0 and (asym_pp > 15.0 or zz25_min_pct > 18.0):
        return "STK_BUY_DIP_TACTICAL"
    # 3. TAKE_PROFIT — blow-off top: zz25 absolute OR zz50 zone-relative
    if zone == "CEILING" and (
        zz25_max_pct > 15.0
        or zz50_max_pct > _CEILING_ZZ50_MAX_BASELINE
    ):
        return "STK_TRIM_TACTICAL"
    # 4. STRONG_TREND (CEILING) — strong bull with low top risk
    if zone == "CEILING" and p_bull > 78.0 and zz25_max_pct < 12.0:
        return "STK_HOLD_EXTENDED"
    # 5. REDUCE — remaining CEILING: preventive distribution
    if zone == "CEILING":
        return "STK_DISTRIBUTE_DECAY"
    # 6. MOMENTUM (ABOVE) — clean uptrend with high purity and low turn risk
    if zone == "ABOVE" and p_bull > 70.0 and momentum_purity > 70.0 and zz25_max_pct < 10.0:
        return "STK_ACCUMULATE_PASSIVE"
    # 7. BULL_TREND — stable uptrend above VWAP
    if zone == "ABOVE" and p_bull > 65.0 and zz25_max_pct < 10.0:
        return "STK_HOLD_STABLE"
    # 8. WATCH / NO_EDGE — FLOOR/BELOW or neutral zone
    return "STK_HOLD_STABLE"



def classify_conviction(abs_z: float, n: int) -> str:
    if abs_z >= 10.0 and n >= 3000:
        return "HIGH"
    if abs_z >= 4.0 and n >= 1000:
        return "MEDIUM"
    return "LOW"


def conviction_score(abs_z: float, n: int) -> int:
    if n <= 1:
        return 0
    return min(100, round(math.log(n) * abs_z / 10.0))


def compute_signal_confidence(
    signal: str,
    n: int,
    p_bull: float,
    zz25_min_pct: float,
    zz25_max_pct: float,
    zz50_min_pct: float,
    zz50_max_pct: float,
    zz75_min_pct: float,
    asym_pp: float,
    avg_hh_run: float,
    turn_density: float,
) -> int:
    """Signal confidence score (0-100).

    Combines four orthogonal weights:
      w_N          — sample size (saturates at N≈3000; 1k → 0.63, 3k → 0.95)
      w_edge       — predictive edge strength (signal-specific, based on zigzag lift)
      w_stability  — penalizes highly fragmented states (avg_run<1.5) or very
                     long runs (avg_run>8) that suggest signal has already played out
      w_repetition — penalizes clustered pivots (double bottoms/tops) that dilute
                     the first-occurrence probability

    Note on temporal concentration:
      In FLOOR runs of length ≥5, 52% of bottoms occur in the FINAL 20% of the run.
      Buying day 1 of a FLOOR state is statistically premature. This is encoded in
      w_stability (fragmented runs → lower confidence) and is communicated via
      the signal reading field.
    """
    # w_N: sample size weight — exponential saturation
    w_N = 1.0 - math.exp(-n / 1000.0)

    # w_edge: signal-specific predictive edge strength
    if signal in ("STK_ACCUMULATE_STRUCTURAL", "ACCUMULATE"):
        # Deep capitulation edge: 5%/7.5% bottom density drives the edge
        edge_raw = (zz75_min_pct / 8.0) * 0.6 + (zz50_min_pct / 12.0) * 0.4
        w_edge = min(1.0, edge_raw)
    elif signal in ("STK_BUY_DIP_TACTICAL", "BUY_DIP"):
        # Asymmetry edge: positive asym_pp means bottoms dominate tops
        edge_raw = max(0.0, asym_pp) / 30.0  # 30pp = large asymmetry
        w_edge = min(1.0, edge_raw)
    elif signal in ("STK_TRIM_TACTICAL", "TAKE_PROFIT"):
        # Top density edge — use the BETTER of zz25 and zz50 lift
        edge_25 = max(0.0, zz25_max_pct - 10.0) / 10.0
        edge_50 = max(0.0, zz50_max_pct - 5.0) / 5.0  # 5% baseline for zz50
        edge_raw = max(edge_25, edge_50)
        w_edge = min(1.0, edge_raw)
    elif signal in ("STK_ACCUMULATE_PASSIVE", "MOMENTUM", "STK_HOLD_EXTENDED", "STRONG_TREND"):
        # Distance of p_bull above the 60.78% market baseline
        edge_raw = max(0.0, p_bull - 60.78) / 30.0  # 30pp above → full confidence
        w_edge = min(1.0, edge_raw)
    elif signal in ("STK_HOLD_STABLE", "BULL_TREND"):
        edge_raw = max(0.0, p_bull - 60.78) / 30.0
        w_edge = min(1.0, edge_raw * 0.8)  # Slightly lower than MOMENTUM
    elif signal in ("STK_DISTRIBUTE_DECAY", "REDUCE"):
        # Top-over-bottom dominance
        edge_raw = max(0.0, -asym_pp) / 25.0
        w_edge = min(1.0, edge_raw)
    else:  # WATCH, NO_EDGE — informational, low edge
        w_edge = 0.25

    # w_stability: penalize extreme fragmentation or over-persistence
    if avg_hh_run < 1.5:
        w_stability = 0.5   # Highly fragmented — noisy pivots
    elif avg_hh_run > 8.0:
        w_stability = 0.75  # Very long runs — signal already exploited
    else:
        w_stability = 1.0

    # w_repetition: penalize clustered zigzag pivots (double bottoms/tops)
    # turn_density = (zz25_min + zz25_max) / n * 100  → >20% means very noisy
    if turn_density > 20.0:
        w_repetition = 0.70
    elif turn_density > 15.0:
        w_repetition = 0.85
    else:
        w_repetition = 1.0

    confidence = 100.0 * w_N * w_edge * w_stability * w_repetition
    return min(100, max(0, round(confidence)))


def classify_fragmentation(avg_run: float) -> str:
    if avg_run < 2.0:
        return "HIGH"
    if avg_run > 5.0:
        return "LOW"
    return "MEDIUM"


def classify_predictive_edge(t1_bot_delta: float, t1_top_delta: float):
    if t1_bot_delta > 2.0:
        return "LEADING_BOTTOM"
    if t1_top_delta > 2.0:
        return "LEADING_TOP"
    return None


def classify_rotation_flag(zone: str, lift_band: float):
    if zone == "FLOOR" and lift_band > 1.15:
        return "EARLY_ROTATION"
    if zone == "CEILING" and lift_band < 0.88:
        return "LATE_CYCLE_WARNING"
    return None


def safe_one_in(n: int, count: int):
    return round(n / count) if count > 0 else None


def safe_ratio(a: int, b: int):
    return round(a / b, 1) if b > 0 else None


# ═══════════════════════════════════════════════════════════════
# Reading template (English)
# ═══════════════════════════════════════════════════════════════

SIGNAL_DESCRIPTIONS = {
    "STK_ACCUMULATE_STRUCTURAL": "Extreme capitulation zone. Statistically validated structural accumulation opportunity.",
    "STK_BUY_DIP_TACTICAL": "Statistical dip with strong bottom asymmetry. Accumulate on confirmed support.",
    "STK_TRIM_TACTICAL": "Blow-off top risk imminent. Tactical profit-taking recommended.",
    "STK_HOLD_EXTENDED": "Ceiling zone but structurally strong trend with low top risk. Hold — do not trim aggressively.",
    "STK_DISTRIBUTE_DECAY": "Preventive distribution. Ceiling zone carries structural top risk.",
    "STK_ACCUMULATE_PASSIVE": "Genuine trend with clean momentum and low turn risk. Maintain exposure.",
    "STK_HOLD_STABLE": "Stable uptrend or neutral range above VWAP. Hold positions.",
    "ACCUMULATE": "Extreme capitulation zone. Statistically validated accumulation opportunity.",
    "BUY_DIP": "Statistical dip with strong bottom asymmetry. Accumulate on confirmed support.",
    "TAKE_PROFIT": "Blow-off top risk imminent. Aggressive profit-taking recommended.",
    "STRONG_TREND": "Ceiling zone but structurally strong trend with low top risk. Hold — do not trim aggressively.",
    "REDUCE": "Preventive distribution. Ceiling zone carries structural top risk.",
    "MOMENTUM": "Genuine trend with clean momentum and low turn risk. Maintain exposure.",
    "BULL_TREND": "Stable uptrend above VWAP. Hold positions, do not add aggressively.",
    "WATCH": "FLOOR/BELOW zone with no actionable edge yet.",
    "NO_EDGE": "Neutral zone with no discriminating feature.",
}



def generate_reading(s: dict) -> str:
    """Generate English reading from state metrics."""
    zone_name = s["identity"]["zone"]
    regime = s["identity"]["regime"]
    signal = s["identity"].get("signal", "")
    p = s["direction"]["p_bull"]

    odds = s["direction"]["odds"]
    lift_b = s["direction"]["lift_vs_band"]
    n = s["frequency"]["N"]
    pct_total = s["frequency"]["pct_of_total"]
    rank = s["frequency"]["rank"]
    hh = s["composition"]["hh_pct"]
    ll = s["composition"]["ll_pct"]
    mp = s["composition"]["momentum_purity"]

    t25_top = s["turn_risk"]["top_25"]
    t25_bot = s["turn_risk"]["bottom_25"]
    t75_top = s["turn_risk"]["top_75"]
    asym = s["turn_risk"]["asymmetry_pp"]

    hh_avg = s["runs"]["hh"]["avg_run"]
    hh_frag = s["runs"]["hh"]["fragmentation"]

    parts = []
    parts.append(f"{zone_name} in {regime} regime.")
    parts.append(f"{p:.1f}% bull ({odds:.1f}:1 odds), "
                 f"{(lift_b - 1) * 100:+.0f}% vs band.")
    parts.append(f"Composition: {hh:.0f}% HH (purity {mp:.0f}%), {ll:.0f}% LL.")

    freq_word = "most frequent" if rank <= 5 else "rare" if rank >= 160 else ""
    if freq_word:
        parts.append(f"State #{rank}/180 ({freq_word}): {pct_total:.1f}% of universe (N={n:,}).")
    else:
        parts.append(f"State #{rank}/180: {pct_total:.1f}% of universe (N={n:,}).")

    if zone_name == "CEILING":
        oin = t25_top["one_in_bars"]
        oin_str = f"1 in {oin}" if oin else "N/A"
        parts.append(f"TOP RISK: 2.5% top in {oin_str} bars (lift {t25_top['lift']:.2f}x).")
        if t75_top["count"] > 0:
            oin75 = t75_top["one_in_bars"]
            parts.append(f"7.5% blow-off top in 1 in {oin75} bars (lift {t75_top['lift']:.2f}x).")
        parts.append(f"Asymmetry {asym:+.1f}pp -> tops dominate.")
    elif zone_name == "FLOOR":
        oin = t25_bot["one_in_bars"]
        oin_str = f"1 in {oin}" if oin else "N/A"
        parts.append(f"BOTTOM DENSITY: 2.5% bottom in {oin_str} bars (lift {t25_bot['lift']:.2f}x).")
        parts.append(f"Asymmetry {asym:+.1f}pp -> bottoms dominate.")

    parts.append(f"HH runs avg {hh_avg:.1f} bars, fragmentation {hh_frag}.")

    return " ".join(parts)



# ═══════════════════════════════════════════════════════════════
# Main generation
# ═══════════════════════════════════════════════════════════════

def main():
    with open(RAW_PATH) as f:
        raw = json.load(f)

    cells = raw["cells"]
    n_total = raw["n_total_observations"]
    gzz = raw["global_zigzag_totals"]

    # ── Band baselines ──
    band_data = {}
    for band_label in ["<<", "<", "~", ">", ">>"]:
        cell = cells[f"L3_svw:{band_label}"]
        n = sum(cell[f"count_{s}"] for s in ["HH", "HL", "LH", "LL"])
        bull = cell["count_HH"] + cell["count_HL"]
        p_bull_band = bull / n * 100

        zz_rates = {}
        for lvl in ["25", "50", "75"]:
            for tp in ["min", "max"]:
                k = f"zz{lvl}_{tp}"
                ct = cell.get(k, 0)
                zz_rates[f"zz{lvl}_{tp}_rate"] = round(ct / n * 100, 2)
                zz_rates[f"zz{lvl}_{tp}_one_in"] = safe_one_in(n, ct)

        band_data[band_label] = {
            "label": ZONE_LABELS[band_label],
            "n": n,
            "pct_of_market": round(n / n_total * 100, 1),
            "p_bull": round(p_bull_band, 1),
            "zz_rates": zz_rates,
        }

    # ── Compute all state N for ranking ──
    all_ns = []
    for key in cells:
        if not key.startswith("L1_full:"):
            continue
        state = key.split(":")[1]
        cell = cells[key]
        n = sum(cell[f"count_{s}"] for s in ["HH", "HL", "LH", "LL"])
        all_ns.append((state, n))
    all_ns.sort(key=lambda x: -x[1])
    rank_map = {state: i + 1 for i, (state, _) in enumerate(all_ns)}

    # ── Build each state ──
    states_out = {}
    for key, cell in cells.items():
        if not key.startswith("L1_full:"):
            continue
        state = key.split(":")[1]
        parts = state.split("|")
        t, c, svw = parts[0], parts[1], parts[2]

        hh = cell["count_HH"]
        hl = cell["count_HL"]
        lh = cell["count_LH"]
        ll = cell["count_LL"]
        n = hh + hl + lh + ll
        bull = hh + hl
        bear = lh + ll

        p_bull = bull / n * 100
        p_bear = bear / n * 100
        odds = round(bull / bear, 2) if bear > 0 else None
        se = math.sqrt(GLOBAL_P_BULL * (1 - GLOBAL_P_BULL) / n)
        z = (bull / n - GLOBAL_P_BULL) / se
        abs_z = abs(z)

        zone = ZONE_MAP[svw]
        regime = classify_regime(t, c)
        lift_global = round(p_bull / 60.78, 3)
        lift_band = round(p_bull / band_data[svw]["p_bull"], 3) if band_data[svw]["p_bull"] > 0 else None

        mp = round(hh / (hh + hl) * 100, 1) if (hh + hl) > 0 else 0
        cp = round(ll / (lh + ll) * 100, 1) if (lh + ll) > 0 else 0

        # Zigzag turn risk
        turn_risk = {}
        for lvl in ["25", "50", "75"]:
            for tp, label in [("min", f"bottom_{lvl}"), ("max", f"top_{lvl}")]:
                k = f"zz{lvl}_{tp}"
                ct = cell.get(k, 0)
                rate = ct / n * 100
                global_rate = gzz[k] / n_total * 100 if gzz.get(k, 0) > 0 else 0.001
                lift = round(rate / global_rate, 2) if global_rate > 0 else 0
                share = round(ct / gzz[k] * 100, 1) if gzz.get(k, 0) > 0 else 0
                turn_risk[label] = {
                    "pct": round(rate, 1),
                    "one_in_bars": safe_one_in(n, ct),
                    "lift": lift,
                    "share_pct": share,
                    "count": ct,
                }

        tot_bot = sum(cell.get(f"zz{l}_min", 0) for l in ["25", "50", "75"])
        tot_top = sum(cell.get(f"zz{l}_max", 0) for l in ["25", "50", "75"])
        asym_pp = round((tot_bot - tot_top) / n * 100, 1)
        turn_dens = round((cell.get("zz25_min", 0) + cell.get("zz25_max", 0)) / n * 100, 1)

        turn_risk["asymmetry_pp"] = asym_pp
        turn_risk["turn_density"] = turn_dens

        # Runs
        hh_runs_n = cell.get("N_HH_runs", 0)
        ll_runs_n = cell.get("N_LL_runs", 0)
        hh_avg = round(hh / hh_runs_n, 1) if hh_runs_n > 0 else 0
        ll_avg = round(ll / ll_runs_n, 1) if ll_runs_n > 0 else 0

        runs = {
            "hh_ll_ratio": safe_ratio(hh, ll),
            "hh": {
                "n_runs": hh_runs_n,
                "max_run": cell.get("max_HH_run", 0),
                "avg_run": hh_avg,
                "fragmentation": classify_fragmentation(hh_avg),
            },
            "ll": {
                "n_runs": ll_runs_n,
                "max_run": cell.get("max_LL_run", 0),
                "avg_run": ll_avg,
                "fragmentation": classify_fragmentation(ll_avg),
            },
        }

        # Predictive
        t1_bot25 = cell.get("zz25_min_prev", 0)
        t1_top25 = cell.get("zz25_max_prev", 0)
        t1_bot_pct = round(t1_bot25 / n * 100, 1)
        t1_top_pct = round(t1_top25 / n * 100, 1)
        t1_bot_delta = round(t1_bot_pct - turn_risk["bottom_25"]["pct"], 1)
        t1_top_delta = round(t1_top_pct - turn_risk["top_25"]["pct"], 1)

        predictive = {
            "t1_bottom_25": {"pct": t1_bot_pct, "delta_pp": t1_bot_delta},
            "t1_top_25": {"pct": t1_top_pct, "delta_pp": t1_top_delta},
        }

        # Signal — extract multi-level zigzag rates for refined classification
        zz25_min_pct = turn_risk["bottom_25"]["pct"]
        zz25_max_pct = turn_risk["top_25"]["pct"]
        zz50_min_pct = turn_risk["bottom_50"]["pct"]
        zz75_min_pct = turn_risk["bottom_75"]["pct"]
        zz50_max_pct = turn_risk["top_50"]["pct"]
        signal = classify_signal(
            zone, p_bull, zz25_min_pct, zz25_max_pct, asym_pp, mp,
            zz50_min_pct=zz50_min_pct, zz75_min_pct=zz75_min_pct,
            zz50_max_pct=zz50_max_pct,
        )

        # Signal confidence
        sig_confidence = compute_signal_confidence(
            signal=signal, n=n, p_bull=p_bull,
            zz25_min_pct=zz25_min_pct, zz25_max_pct=zz25_max_pct,
            zz50_min_pct=zz50_min_pct, zz50_max_pct=zz50_max_pct,
            zz75_min_pct=zz75_min_pct,
            asym_pp=asym_pp, avg_hh_run=hh_avg, turn_density=turn_dens,
        )

        # New committee fields
        pred_edge = classify_predictive_edge(t1_bot_delta, t1_top_delta)
        rot_flag = classify_rotation_flag(zone, lift_band) if lift_band else None

        # Assemble state
        state_obj = {
            "identity": {
                "zone": zone,
                "regime": regime,
                "signal_confidence": sig_confidence,
                "conviction": classify_conviction(abs_z, n),
                "conviction_score": conviction_score(abs_z, n),
                "predictive_edge": pred_edge,
                "rotation_flag": rot_flag,
            },

            "frequency": {
                "N": n,
                "pct_of_total": round(n / n_total * 100, 2),
                "pct_of_band": round(n / band_data[svw]["n"] * 100, 2),
                "rank": rank_map[state],
            },
            "direction": {
                "p_bull": round(p_bull, 1),
                "p_bear": round(p_bear, 1),
                "odds": odds,
                "lift_vs_global": lift_global,
                "lift_vs_band": lift_band,
                "z_score": round(z, 1),
            },
            "composition": {
                "hh_pct": round(hh / n * 100, 1),
                "hl_pct": round(hl / n * 100, 1),
                "lh_pct": round(lh / n * 100, 1),
                "ll_pct": round(ll / n * 100, 1),
                "momentum_purity": mp,
                "capitulation_purity": cp,
            },
            "turn_risk": turn_risk,
            "runs": runs,
            "predictive": predictive,
        }

        state_obj["reading"] = generate_reading(state_obj)
        states_out[state] = state_obj

    # ── Build baselines ──
    baselines = {}
    for lvl, desc_bot, desc_top in [
        ("25", "2.5% zigzag bottoms (minor support)", "2.5% zigzag tops (minor resistance)"),
        ("50", "5.0% zigzag bottoms (significant corrections)", "5.0% zigzag tops (significant resistance)"),
        ("75", "7.5% zigzag bottoms (capitulations)", "7.5% zigzag tops (blow-off tops)"),
    ]:
        min_k = f"zz{lvl}_min"
        max_k = f"zz{lvl}_max"
        n_bot = gzz[min_k]
        n_top = gzz[max_k]
        baselines[f"bottom_{lvl}"] = {
            "total_pivots": n_bot,
            "rate_pct": round(n_bot / n_total * 100, 2),
            "one_in_bars": round(n_total / n_bot) if n_bot > 0 else None,
            "meaning": f"{n_bot:,} {desc_bot} across {n_total:,} bars. 1 in every {round(n_total / n_bot)} market bars is this type of pivot.",
        }
        baselines[f"top_{lvl}"] = {
            "total_pivots": n_top,
            "rate_pct": round(n_top / n_total * 100, 2),
            "one_in_bars": round(n_total / n_top) if n_top > 0 else None,
            "meaning": f"{n_top:,} {desc_top} across {n_total:,} bars. 1 in every {round(n_total / n_top)} market bars is this type of pivot.",
        }

    # ── Assemble final JSON ──
    output = {
        "version": f"v2_derived_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "source": "rc_tide_probability_table.json v3",
        "approved_by": "Committee: Dalio (CIO), Druckenmiller (Quality Swing), PTJ/Eifert (Speculative), Weinstein/Pring (Rotation)",

        "context": {
            "what": "Pre-computed probability lookup table for the Swing Gate (Quality Swing department).",
            "how": "Each cell describes the historical behavior of 538 tickers when the 3 dimensions (T, C, sigma_vw) align in that configuration.",
            "dimensions": "T_slope (Tide, long-term) x C_slope (Current, medium-term) x sigma_vwap_wave (price position vs VWAP Wave)",
            "n_states": 180,
            "n_observations": n_total,
            "n_tickers": raw["n_tickers"],
            "observation_unit": f"1 observation = 1 bar = 1 trading day of 1 ticker. N={n_total:,} = {raw['n_tickers']} tickers x ~{n_total // raw['n_tickers']:,} days avg each.",
            "stereotype_source": "Zigzag 2.5% classifies each bar as HH (Higher-High), HL (Higher-Low), LH (Lower-High), LL (Lower-Low)",
            "bull_definition": "Bull = HH + HL (next high or low is higher than previous)",
            "bear_definition": "Bear = LH + LL (next high or low is lower than previous)",
            "global_p_bull": 60.78,
            "global_p_bull_meaning": f"Across all {n_total:,} bars, 60.78% are bull. The market has structural bullish bias.",
        },

        "baselines": {
            "_what": "Baseline zigzag pivot rates across the entire market. These are the REFERENCE for all lifts and comparisons in each state.",
            "_rate_formula": "rate_pct = total_pivots_of_this_type / N_total_bars x 100",
            "_share_denominator": "share_pct in each state = count_in_state / total_pivots x 100",
            **baselines,
        },

        "band_baselines": {
            "_what": "Each sigma_vw band groups a range of price position vs VWAP Wave. Shows WHERE the market lives and HOW it behaves at each position.",
            "_meaning": "If lift_vs_band ~ 1.0, T and C add NO information beyond sigma_vw. If it diverges, T x C DOES discriminate within that band.",
            **band_data,
        },

        "states": states_out,
    }

    with open(OUT_PATH, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # ── Summary ──
    sig_counts = Counter(s["identity"].get("signal", "PURE_FEATURE_FACT") for s in states_out.values())
    conv_counts = Counter(s["identity"]["conviction"] for s in states_out.values())
    pred_counts = Counter(s["identity"]["predictive_edge"] for s in states_out.values() if s["identity"]["predictive_edge"])
    rot_counts = Counter(s["identity"]["rotation_flag"] for s in states_out.values() if s["identity"]["rotation_flag"])

    print(f"Generated {OUT_PATH}")
    print(f"   States: {len(states_out)}")
    print(f"   Signals: {dict(sig_counts.most_common())}")

    print(f"   Conviction: {dict(conv_counts.most_common())}")
    print(f"   Predictive Edge: {dict(pred_counts.most_common())}")
    print(f"   Rotation Flags: {dict(rot_counts.most_common())}")


if __name__ == "__main__":
    main()
