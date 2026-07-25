"""
Druckenmiller Causal Evidence Rules
====================================
Pure mathematical scoring for Stanley Druckenmiller's 5 Causal Vectors.
Supports Missing Vectors detection, Data Completeness reporting, Extreme Sentiment (FG, VIX, PCR),
and Volatility Fragility / Tail Risk (SKEW, VVIX).

Vector Weights:
  1. Options & Darkpool Flow (Unusual Whales): 0.25
  2. Macro & Credit Liquidity (FRED): 0.20
  3. Insiders & Guru Accumulation (Finnhub/GuruFocus): 0.20
  4. Volume Capitulation & Extreme Sentiment (S5/SV5, FG, VIX, PCR, SKEW, VVIX): 0.20
  5. Narrative & News Sentiment (FinBERT): 0.15

Counter-Veto threshold: composite causal_score >= 0.70.
"""
from typing import Optional, List, Dict, Any
from backend.modules.causal_investigation.domain.entities.druckenmiller_causal import (
    CausalEvidenceMatrix,
    CounterVetoResult,
)


def evaluate_druckenmiller_counter_veto(
    symbol: str,
    uw_flow_alerts: Optional[list] = None,
    uw_net_premium: float = 0.0,
    uw_sweep_count: int = 0,
    fred_macro_snapshot: Optional[dict] = None,
    insider_activity: Optional[dict] = None,
    s5_th: float = 50.0,
    s5_fi: float = 50.0,
    s5_tw: float = 50.0,
    sv5_tw: float = 50.0,
    vol_div: float = 0.0,
    fg_score: float = 50.0,
    vix_zscore: float = 0.0,
    vix_val: float = 18.0,
    cboe_pcr: float = 1.0,
    skew_val: float = 120.0,
    vvix_val: float = 85.0,
    news_sentiment_score: float = 0.0,
    override_threshold: float = 0.70,
) -> CounterVetoResult:
    """
    Evaluates Druckenmiller's 5-vector causal evidence matrix.
    Detects and reports missing data vectors.
    """
    missing_vectors: List[str] = []

    # ── Vector 1: Options & Darkpool Flow (0.0 to 1.0) ──
    if uw_flow_alerts is None and uw_sweep_count == 0 and uw_net_premium == 0.0:
        missing_vectors.append("OPTIONS_DARKPOOL_FLOW")
    flow_score = _score_options_flow(uw_sweep_count, uw_net_premium, uw_flow_alerts)

    # ── Vector 2: Macro & Credit Liquidity (0.0 to 1.0) ──
    if fred_macro_snapshot is None:
        missing_vectors.append("FRED_MACRO_LIQUIDITY")
    macro_score = _score_macro_liquidity(fred_macro_snapshot)

    # ── Vector 3: Insider & Guru Accumulation (0.0 to 1.0) ──
    if insider_activity is None:
        missing_vectors.append("CORPORATE_INSIDER_ACTIVITY")
    insider_score = _score_insider_activity(insider_activity)

    # ── Vector 4: Volume Capitulation / Re-Absorption / Extreme Sentiment & Skew ──
    volume_score = _score_volume_reabsorption(
        s5_th, s5_fi, s5_tw, sv5_tw, vol_div, fg_score, vix_zscore, cboe_pcr, skew_val, vvix_val
    )

    # ── Vector 5: Narrative & News Sentiment Velocity (0.0 to 1.0) ──
    if news_sentiment_score == 0.0:
        missing_vectors.append("NEWS_SENTIMENT_FINBERT")
    narrative_score = _score_narrative_momentum(news_sentiment_score)

    total_vectors = 5
    available_vectors = total_vectors - len(missing_vectors)
    data_completeness_pct = round((available_vectors / total_vectors) * 100.0, 1)

    # Composite Weighted Score
    causal_score = (
        0.25 * flow_score +
        0.20 * macro_score +
        0.20 * insider_score +
        0.20 * volume_score +
        0.15 * narrative_score
    )
    causal_score = round(max(0.0, min(1.0, causal_score)), 4)

    is_overridden = causal_score >= override_threshold

    if causal_score >= 0.85:
        conviction = "HIGH"
        sizing_factor = 1.25
    elif causal_score >= override_threshold:
        conviction = "MEDIUM"
        sizing_factor = 1.00
    elif causal_score >= 0.50:
        conviction = "LOW"
        sizing_factor = 0.75
    else:
        conviction = "NONE"
        sizing_factor = 0.50

    matrix = CausalEvidenceMatrix(
        options_darkpool_score=round(flow_score, 4),
        macro_liquidity_score=round(macro_score, 4),
        insider_accumulation_score=round(insider_score, 4),
        volume_reabsorption_score=round(volume_score, 4),
        narrative_momentum_score=round(narrative_score, 4),
        missing_vectors=missing_vectors,
        data_completeness_pct=data_completeness_pct,
        details={
            "s5_th": s5_th,
            "s5_fi": s5_fi,
            "s5_tw": s5_tw,
            "sv5_tw": sv5_tw,
            "uw_sweeps": uw_sweep_count,
            "uw_net_prem": uw_net_premium,
            "vol_div": vol_div,
            "fg_score": fg_score,
            "vix_zscore": vix_zscore,
            "vix_val": vix_val,
            "cboe_pcr": cboe_pcr,
            "skew_val": skew_val,
            "vvix_val": vvix_val,
            "news_sent": news_sentiment_score,
            "missing_count": len(missing_vectors),
        }
    )

    missing_str = f" | MISSING: {', '.join(missing_vectors)}" if missing_vectors else ""
    summary = (
        f"Druckenmiller Score={causal_score:.2f} ({conviction}) | "
        f"Completeness={data_completeness_pct:.0f}% | "
        f"Flow={flow_score:.2f}, Macro={macro_score:.2f}, "
        f"Insiders={insider_score:.2f}, Vol={volume_score:.2f}, News={narrative_score:.2f} | "
        f"Override={'YES' if is_overridden else 'NO'} (x{sizing_factor}){missing_str}"
    )

    return CounterVetoResult(
        symbol=symbol,
        is_overridden=is_overridden,
        causal_score=causal_score,
        conviction_level=conviction,
        sizing_factor=sizing_factor,
        evidence_matrix=matrix,
        missing_vectors=missing_vectors,
        data_completeness_pct=data_completeness_pct,
        summary=summary,
    )


def _score_options_flow(sweeps: int, net_prem: float, alerts: Optional[list]) -> float:
    score = 0.5
    if sweeps >= 10:
        score += 0.3
    elif sweeps >= 4:
        score += 0.15

    if net_prem > 1_000_000:
        score += 0.2
    elif net_prem > 250_000:
        score += 0.1
    elif net_prem < -500_000:
        score -= 0.2

    if alerts and len(alerts) > 5:
        score += 0.1

    return max(0.0, min(1.0, score))


def _score_macro_liquidity(fred_snap: Optional[dict]) -> float:
    if not fred_snap or not isinstance(fred_snap, dict):
        return 0.5

    score = 0.5
    macro_regime = fred_snap.get("macro_regime", "neutral")
    net_liq_trend = fred_snap.get("net_liquidity_trend", "stable")
    fed_stance = fred_snap.get("fed_stance", "neutral")

    if macro_regime == "risk_on":
        score += 0.2
    elif macro_regime == "risk_off" or macro_regime == "crisis":
        score -= 0.3

    if net_liq_trend == "easing":
        score += 0.15
    elif net_liq_trend == "tightening":
        score -= 0.15

    if fed_stance == "dovish":
        score += 0.15
    elif fed_stance == "hawkish":
        score -= 0.1

    # Blind Spot 1 Fix: Credit Market High Yield Spread (HY_OAS / BAMLH0A0HYM2)
    hy_oas = fred_snap.get("hy_oas", fred_snap.get("credit_spread", 3.5))
    if isinstance(hy_oas, (int, float)):
        if hy_oas >= 5.0:  # >500 bps = Corporate Credit Freeze
            score -= 0.25
        elif hy_oas >= 4.0: # >400 bps = Credit Stress
            score -= 0.10

    return max(0.0, min(1.0, score))


def _score_insider_activity(insider_act: Optional[dict]) -> float:
    if not insider_act or not isinstance(insider_act, dict):
        return 0.5

    sig = insider_act.get("signal", "neutral")
    if sig in ("strong_buy", "cluster_buy"):
        return 0.9
    elif sig == "buy":
        return 0.75
    elif sig == "neutral":
        return 0.5
    elif sig in ("caution", "sell"):
        return 0.25
    return 0.5


def _score_volume_reabsorption(
    th: float, fi: float, tw: float, sv5_tw: float, vol_div: float,
    fg_score: float = 50.0, vix_zscore: float = 0.0, cboe_pcr: float = 1.0,
    skew_val: float = 120.0, vvix_val: float = 85.0
) -> float:
    score = 0.5

    # V28 Weinstein Smart Veto vol_div threshold
    if vol_div > 15.0:
        score += 0.25
    elif vol_div > 10.0:
        score += 0.15

    # Bullish Volume Re-absorption anomaly (S5_TH >= 60, S5_FI <= 45, SV5_TW >= 60)
    if th >= 60.0 and fi <= 45.0 and sv5_tw >= 60.0:
        score += 0.20

    # Volume Capitulation Floor (S5_TH <= 25, SV5_TW >= 60)
    if th <= 25.0 and sv5_tw >= 60.0:
        score += 0.25

    # Contrarian Fear & Greed Layer (Extreme Fear <= 20 -> Capitulation Buy)
    if fg_score <= 20.0:
        score += 0.25
    elif fg_score <= 30.0:
        score += 0.15
    elif fg_score >= 80.0:
        score -= 0.20

    # Panic Volatility Spike (VIX Z-Score > 2.0 -> Panic Floor Capitulation)
    if vix_zscore > 2.0:
        score += 0.20
    elif vix_zscore < -1.5:
        score -= 0.15

    # CBOE Put/Call Ratio Extreme (> 1.25 -> Extreme Put Buying Capitulation)
    if cboe_pcr > 1.25:
        score += 0.15
    elif cboe_pcr < 0.65:
        score -= 0.10

    # CBOE Skew Index (> 140 -> High Tail Risk / Black Swan hedging)
    if skew_val > 140.0:
        score += 0.15
    elif skew_val < 115.0:
        score -= 0.10

    # VVIX Volatility of Volatility (VVIX > 120 -> Vol Fragility / Panic inflection)
    if vvix_val > 120.0:
        score += 0.15

    return max(0.0, min(1.0, score))


def _score_narrative_momentum(news_sentiment: float) -> float:
    # news_sentiment is normalized between -1.0 and +1.0
    # Map [-1.0, 1.0] -> [0.0, 1.0]
    scaled = (news_sentiment + 1.0) / 2.0
    return max(0.0, min(1.0, scaled))
