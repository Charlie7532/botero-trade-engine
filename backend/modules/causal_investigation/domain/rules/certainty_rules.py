"""
Certainty & Credibility Scoring Rules — Pure Domain Rules
==========================================================
Computes overall AND department-calibrated Certainty Scores:
  - Overall Certainty Score (Global Market Weather)
  - Quality Certainty Score (Quality Gate — Munger/Hohn: Macro, Insiders, Stage, Beneish. Ignores intraday 5M option flow)
  - Swing Certainty Score (Quality Swing Gate — Druckenmiller: Vol div, Breadth, Fear & Greed, Risk Reversal. Ignores insiders)
  - Speculative Certainty Score (Speculative Gate — PTJ/Seykota: Intraday 5M PCR, Option sweeps, Short float. Heavy 5M penalty)

Clean Architecture: Pure Domain Rule — Zero I/O, zero external dependencies.
"""
from typing import List, Tuple, Dict, Any


def compute_certainty_score(
    missing_vectors: List[str],
    data_age_hours: float,
    vector_scores: List[float],
    notam_status: str = "FRESH",
) -> Tuple[float, str, str, Dict[str, Any]]:
    """
    Computes overall certainty and department-calibrated certainty scores.

    Returns:
      (overall_certainty_score, overall_certainty_grade, uncertainty_note, department_certainty_dict)
    """
    # ── 1. Overall Certainty Score ──
    base_score = 100.0
    notes = []

    vector_penalties = {
        "OPTIONS_DARKPOOL_FLOW": 15.0,
        "FRED_MACRO_LIQUIDITY": 12.0,
        "CORPORATE_INSIDER_ACTIVITY": 10.0,
        "NEWS_SENTIMENT_FINBERT": 8.0,
    }

    for vec in missing_vectors:
        pen = vector_penalties.get(vec, 10.0)
        base_score -= pen
        notes.append(f"Missing {vec} (-{pen:.0f}%)")

    # Data Age Decay
    if data_age_hours > 12.0:
        over_hours = data_age_hours - 12.0
        age_penalty = min(25.0, over_hours * 0.5)
        base_score -= age_penalty
        notes.append(f"Age {data_age_hours:.1f}h (-{age_penalty:.1f}%)")

    # Vector Directional Consensus Bonus
    if vector_scores and len(vector_scores) >= 3:
        bullish_count = sum(1 for s in vector_scores if s >= 0.65)
        bearish_count = sum(1 for s in vector_scores if s <= 0.35)
        if bullish_count >= 4 or bearish_count >= 4:
            base_score += 5.0
            notes.append("High Vector Consensus (+5%)")

    overall_certainty_score = round(max(0.0, min(100.0, base_score)), 1)
    overall_grade = _classify_grade(overall_certainty_score)

    # ── 2. Department-Calibrated Certainty Scores ──

    # Quality Gate (Munger/Hohn): Ignores OPTIONS_DARKPOOL_FLOW missingness
    q_score = 100.0
    for vec in missing_vectors:
        if vec == "OPTIONS_DARKPOOL_FLOW":
            continue  # Quality Core does NOT rely on intraday 5M option flow
        q_score -= vector_penalties.get(vec, 10.0)
    if data_age_hours > 24.0:  # Quality operates on daily/weekly horizon
        q_score -= min(15.0, (data_age_hours - 24.0) * 0.25)
    quality_certainty_score = round(max(0.0, min(100.0, q_score)), 1)
    quality_grade = _classify_grade(quality_certainty_score)

    # Swing Gate (Druckenmiller): Ignores CORPORATE_INSIDER_ACTIVITY missingness
    s_score = 100.0
    for vec in missing_vectors:
        if vec == "CORPORATE_INSIDER_ACTIVITY":
            continue
        s_score -= vector_penalties.get(vec, 10.0)
    if data_age_hours > 12.0:
        s_score -= min(20.0, (data_age_hours - 12.0) * 0.5)
    swing_certainty_score = round(max(0.0, min(100.0, s_score)), 1)
    swing_grade = _classify_grade(swing_certainty_score)

    # Speculative Gate (PTJ/Seykota): Heavy penalty (-30%) if OPTIONS_DARKPOOL_FLOW missing
    spec_score = 100.0
    for vec in missing_vectors:
        if vec == "OPTIONS_DARKPOOL_FLOW":
            spec_score -= 30.0  # Speculative requires flow!
        else:
            spec_score -= vector_penalties.get(vec, 8.0)
    if data_age_hours > 4.0:  # Speculative requires intraday freshness
        spec_score -= min(30.0, (data_age_hours - 4.0) * 1.5)
    speculative_certainty_score = round(max(0.0, min(100.0, spec_score)), 1)
    speculative_grade = _classify_grade(speculative_certainty_score)

    dept_certainty_dict = {
        "quality_certainty_score": quality_certainty_score,
        "quality_certainty_grade": quality_grade,
        "swing_certainty_score": swing_certainty_score,
        "swing_certainty_grade": swing_grade,
        "speculative_certainty_score": speculative_certainty_score,
        "speculative_certainty_grade": speculative_grade,
    }

    uncertainty_note = " | ".join(notes) if notes else "Full Vector Completeness (100% Data Freshness)"

    return overall_certainty_score, overall_grade, uncertainty_note, dept_certainty_dict


def _classify_grade(score: float) -> str:
    if score >= 85.0:
        return "HIGH_CERTAINTY"
    elif score >= 70.0:
        return "MODERATE_CERTAINTY"
    elif score >= 50.0:
        return "LOW_CERTAINTY"
    else:
        return "HIGH_UNCERTAINTY"
