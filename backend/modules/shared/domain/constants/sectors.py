"""
Canonical Sector & ETF Mapping — Single Source of Truth
=========================================================
Resolves naming inconsistencies across modules:
    Finviz uses "Consumer Cyclical" → canonical "Consumer Discretionary"
    Finviz uses "Financial"        → canonical "Financials"

All modules MUST use canonical names from this file.
"""

# ── Finviz → Canonical Name Mapping ─────────────────────────
FINVIZ_TO_CANONICAL = {
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Financial": "Financials",
    "Basic Materials": "Materials",
}


def canonicalize(sector_name: str) -> str:
    """Convert any sector name variant to canonical GICS name."""
    return FINVIZ_TO_CANONICAL.get(sector_name, sector_name)


# ── Consolidated ETF Universe ──────────────────────────────
# Union of all ETFs previously scattered across 3 modules.

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLV": "Healthcare",
    "XLF": "Financials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLE": "Energy",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
    "XLC": "Communication Services",
}

INTERNATIONAL_ETFS = {
    "EFA": "Developed ex-US",
    "EEM": "Emerging Markets",
    "FXI": "China",
    "MCHI": "China Broad",
    "EWJ": "Japan",
    "VGK": "Europe",
    "EWZ": "Brazil",
    "INDA": "India",
    "EWY": "South Korea",
    "EPP": "Asia Pacific ex-Japan",
}

ASSET_CLASS_ETFS = {
    "SPY": "US Equities",
    "TLT": "Long Treasuries",
    "GLD": "Gold",
    "USO": "Oil",
    "UUP": "US Dollar",
    "HYG": "High Yield Bonds",
    "LQD": "Investment Grade Bonds",
    "DBA": "Agriculture",
}

# Equal-weight proxies for breadth divergence calculation
# Uses Invesco S&P 500 Equal Weight sector ETFs where available
EQUAL_WEIGHT_PROXIES = {
    "SPY": "RSP",       # S&P 500 Equal Weight
    "XLK": "RSPT",      # S&P 500 EW Technology
    "XLV": "RSPH",      # S&P 500 EW Health Care
    "XLF": "RSPF",      # S&P 500 EW Financials
    "XLY": "RSPD",      # S&P 500 EW Consumer Discretionary
    "XLP": "RSPS",      # S&P 500 EW Consumer Staples
    "XLI": "RSPN",      # S&P 500 EW Industrials
    "XLE": "RSPG",      # S&P 500 EW Energy
    "XLU": "RSPU",      # S&P 500 EW Utilities
}

BENCHMARK = "SPY"

ALL_ETFS = {**SECTOR_ETFS, **INTERNATIONAL_ETFS, **ASSET_CLASS_ETFS}


# ── Sector Breadth Indicator Tickers ────────────────────────
# Naming: S5_{ETF}_{TH|FI|TW}
# S5 = S&P 500 component breadth
# TH = % above 200-DMA (structural)
# FI = % above 50-DMA (intermediate)
# TW = % above 20-DMA (tactical)

# ETF prefix extraction: XLK→XLK, XLRE→XLRE (no truncation)
SECTOR_BREADTH_TICKERS: dict[str, dict[str, str]] = {}
for _etf in SECTOR_ETFS:
    SECTOR_BREADTH_TICKERS[_etf] = {
        "structural": f"S5_{_etf}_TH",
        "intermediate": f"S5_{_etf}_FI",
        "tactical": f"S5_{_etf}_TW",
    }

# Flat list of all 33 sector breadth indicator tickers
ALL_SECTOR_BREADTH_TICKERS: list[str] = [
    t for d in SECTOR_BREADTH_TICKERS.values() for t in d.values()
]

# MA lengths for each timeframe
BREADTH_MA_LENGTHS = {
    "structural": 200,
    "intermediate": 50,
    "tactical": 20,
}

# Approximate sector cap-weights in SPY (as of mid-2025).
# Used to compute breadth contribution weighted by capitalisation.
# Source: S&P Dow Jones Indices fact sheet.
# TODO: refresh dynamically via GuruFocus MCP (get_etf_sector_weighting).
SECTOR_CAP_WEIGHTS: dict[str, float] = {
    "XLK":  0.32,   # Technology
    "XLF":  0.13,   # Financials
    "XLV":  0.12,   # Healthcare
    "XLY":  0.10,   # Consumer Discretionary
    "XLC":  0.09,   # Communication Services
    "XLI":  0.08,   # Industrials
    "XLP":  0.06,   # Consumer Staples
    "XLE":  0.04,   # Energy
    "XLU":  0.025,  # Utilities
    "XLRE": 0.023,  # Real Estate
    "XLB":  0.022,  # Materials
}
