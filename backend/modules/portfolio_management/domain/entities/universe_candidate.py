from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, UTC

class MarketRegime(str, Enum):
    """Régimen macroeconómico detectado."""
    RISK_ON = "risk_on"          # VIX < 18, Yield positiva → Cíclicos
    NEUTRAL = "neutral"          # VIX 18-25 → Selectivo
    RISK_OFF = "risk_off"        # VIX > 25 → Defensivos o Cash
    CRISIS = "crisis"            # VIX > 35 → Solo reversión extrema


@dataclass
class UniverseCandidate:
    """Un activo que pasó los filtros y es elegible para la LSTM."""
    ticker: str
    regime: MarketRegime
    sector: str = ""
    relative_momentum: float = 0.0       # Momentum vs SPX
    vix_at_selection: float = 0.0
    guru_accumulation: bool = False       # True si Gurus están comprando
    dcf_discount_pct: float = 0.0         # Descuento vs valor intrínseco
    catalyst_active: bool = False         # Sobrerreacción detectada
    # ─── QGARP / GuruFocus Intelligence (NEW) ───
    qgarp_score: float = 0.0              # QGARP composite 0-100
    piotroski_f_score: int = 0            # Financial strength 0-9
    altman_z_score: float = 0.0           # Bankruptcy risk (>2.99 safe)
    guru_conviction_score: float = 0.0    # Guru net buying 0-100
    guru_count: int = 0                   # Number of gurus holding
    insider_conviction_score: float = 0.0 # Insider cluster buying 0-100
    insider_sentiment: str = "neutral"    # strong_buy, buy, neutral, sell
    risk_score_5d: float = 50.0           # 5D risk matrix 0-100 (higher=safer)
    analyst_consensus: str = "hold"       # strong_buy → strong_sell
    analyst_upside_pct: float = 0.0       # Price target upside %
    political_signal: str = "neutral"     # Congressional trades signal
    # ─── GURU VALUATION METRICS (GuruFocus real data) ───
    price_to_gf_value: float = 0.0        # Price / GF Value (<1 = undervalued)
    gf_value_discount_pct: float = 0.0    # Margin of Safety % (positive = cheap)
    ps_vs_historical: float = 0.0         # Current P/S / Historical Median P/S
    price_to_fcf: float = 0.0             # Price / Free Cash Flow
    fcf_margin: float = 0.0               # FCF Margin % (cash conversion quality)
    beneish_m_score: float = -3.0         # Beneish M-Score (> -1.78 = manipulation risk)
    # Opciones & Sentimiento
    max_pain: float = 0.0                 # Max Pain del ticker
    max_pain_distance_pct: float = 0.0    # Distancia precio→MaxPain en %
    put_call_ratio: float = 0.0           # Put/Call OI Ratio
    gex_positive: bool = True             # GEX neto positivo (vol suprimida)
    mm_bias: str = "NEUTRAL"              # BULLISH_PULL / BEARISH_PULL / NEUTRAL
    sentiment_score: float = 50.0         # Score sentimiento 0-100
    sentiment_rating: str = "neutral"     # extreme_fear → extreme_greed
    fear_greed_macro: float = 50.0        # CNN Fear & Greed
    sp500_breadth_pct: float = 50.0       # S5TH proxy
    score: float = 0.0                    # Score compuesto
    is_emerging_gem: bool = False         # True si viene de Guru Gems (fuera de S&P500)
    alpha_score: float = 0.0              # Alpha score posterior
    selected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
