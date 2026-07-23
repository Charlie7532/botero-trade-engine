"""
Departmental Wishlists Registry (Observation Universes)
=========================================================
Centralized registry of observation wishlists for each trading department.
Used by the Vault Daemon and Causal Investigation Engine to target news,
NOTAM aviation warnings, and targeted vector evaluations.

Clean Architecture: Shared Domain Constants layer. Pure Python dicts/lists.
"""
from typing import Dict, List, Any

# ── 1. INVESTMENT WISHLIST (Quality Core — Hohn & Munger Mode) ──
# Top tollkeeper moat businesses (20-30 mega/large-cap tickers).
# Evaluated for balance sheet integrity (Beneish M-score), Stage 1/2 basings, and Insider buying.
INVESTMENT_WISHLIST: List[str] = [
    "AAPL", "MSFT", "AMZN", "COST", "HD", "HON", "IBM", "JNJ",
    "JPM",  "MCD",  "MRK",  "PEP",  "PG", "WMT", "XOM", "LLY",
    "UNH",  "V",    "MA",   "GOOGL","META"
]

# ── 2. ROTATION WISHLIST (Sector Leaders — Weinstein & Pring Mode) ──
# Top 3-5 constituent leader stocks per sector ETF.
# When a sector enters Stage 2 or Recovery, the system picks the leader stock instead of just the ETF.
ROTATION_SECTOR_LEADERS: Dict[str, List[str]] = {
    "XLK":  ["NVDA", "MSFT", "AVGO", "AAPL"],
    "XLV":  ["LLY", "UNH", "ABBV", "JNJ", "MRK"],
    "XLF":  ["JPM", "V", "MA", "BAC"],
    "XLC":  ["META", "GOOGL", "NFLX"],
    "XLE":  ["XOM", "CVX", "COP"],
    "XLY":  ["AMZN", "TSLA", "HD", "MCD"],
    "XLI":  ["GE", "CAT", "HON", "UNP"],
    "XLP":  ["PG", "PEP", "COST", "WMT"],
    "XLU":  ["NEE", "DUK", "SO"],
    "XLRE": ["PLD", "AMT", "EQIX"],
    "XLB":  ["LIN", "APD", "ECL"],
}

# ── 3. QUALITY SWING WISHLIST (Tactical Dip — Druckenmiller Mode) ──
# Dynamic watchlist of Quality Core tickers currently in Stage 2/Pullback near regression floor (sigma <= -1.5).
# Evaluated for Risk Reversal Skew, Fear & Greed panic (FG <= 20), and volume re-absorption (vol_div > 15).
QUALITY_SWING_WISHLIST: List[str] = [
    "NVDA", "MSFT", "AAPL", "AMZN", "COST", "JPM", "LLY", "UNH", "PG", "XOM"
]

# ── 4. SPECULATIVE WISHLIST (Asymmetric 5:1 Catalyst — PTJ & Seykota Mode) ──
# High-beta, high short-interest (Float Shorted >= 15%), high option volume tickers.
# Evaluated for 5-minute PCR capitulation (CBOE_PCR_5M), sweeps >= 10, and Short Squeeze triggers.
SPECULATIVE_WISHLIST: List[str] = [
    "TSLA", "AMD", "PLTR", "MSTR", "COIN", "SMCI", "ARM", "NVDA", "QQQ"
]

# Consolidated All-Ticker Master Watchlist for Vault Daemon targeting
ALL_DEPARTMENTAL_TICKERS: List[str] = list(set(
    INVESTMENT_WISHLIST +
    QUALITY_SWING_WISHLIST +
    SPECULATIVE_WISHLIST +
    [ticker for leaders in ROTATION_SECTOR_LEADERS.values() for ticker in leaders]
))
