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
