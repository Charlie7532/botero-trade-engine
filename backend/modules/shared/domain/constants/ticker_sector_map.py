"""
Ticker → Sector ETF Reverse Mapping
=====================================
Given a ticker, returns the GICS Sector ETF that most influences it.

This is a static lookup for the S&P 500 universe based on GICS classification.
Updated: 2026-05-07.  Source: S&P Dow Jones Indices.
"""

from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS

# Build reverse: "Technology" → "XLK", "Financials" → "XLF", etc.
_SECTOR_NAME_TO_ETF: dict[str, str] = {v: k for k, v in SECTOR_ETFS.items()}

# Common aliases from various data sources
_ALIASES: dict[str, str] = {
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Financial": "Financials",
    "Financial Services": "Financials",
    "Basic Materials": "Materials",
    "Communication": "Communication Services",
    "Info Technology": "Technology",
    "Information Technology": "Technology",
    "Health Care": "Healthcare",
}


def sector_etf_for(gics_sector: str) -> str | None:
    """
    Return the sector ETF ticker for a given GICS sector name.
    """
    canonical = _ALIASES.get(gics_sector, gics_sector)
    return _SECTOR_NAME_TO_ETF.get(canonical)


# ── Static S&P 500 Ticker → GICS Sector ETF Mapping ──────────────
# This avoids DB lookups during batch processing.
# Key = ticker, Value = sector ETF ticker

SP500_SECTOR_MAP: dict[str, str] = {
    # Technology (XLK)
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AVGO": "XLK", "CSCO": "XLK",
    "ADBE": "XLK", "CRM": "XLK", "ACN": "XLK", "ORCL": "XLK", "IBM": "XLK",
    "INTC": "XLK", "AMD": "XLK", "QCOM": "XLK", "TXN": "XLK", "INTU": "XLK",
    "AMAT": "XLK", "ADI": "XLK", "LRCX": "XLK", "MU": "XLK", "KLAC": "XLK",
    "SNPS": "XLK", "CDNS": "XLK", "MCHP": "XLK", "FTNT": "XLK", "MSI": "XLK",
    "PANW": "XLK", "ADSK": "XLK", "IT": "XLK", "APH": "XLK", "NXPI": "XLK",
    "ON": "XLK", "MPWR": "XLK", "KEYS": "XLK", "CDW": "XLK", "FSLR": "XLK",
    "GLW": "XLK", "TDY": "XLK", "ZBRA": "XLK", "TRMB": "XLK", "PTC": "XLK",
    "TYL": "XLK", "SMCI": "XLK", "ANET": "XLK", "GEN": "XLK", "EPAM": "XLK",
    "AKAM": "XLK", "JNPR": "XLK", "FFIV": "XLK", "SWKS": "XLK", "QRVO": "XLK",
    "TECH": "XLK", "HPE": "XLK", "HPQ": "XLK", "WDC": "XLK", "STX": "XLK",
    "NTAP": "XLK", "LITE": "XLK", "ENPH": "XLK",

    # Healthcare (XLV)
    "UNH": "XLV", "JNJ": "XLV", "LLY": "XLV", "ABBV": "XLV", "MRK": "XLV",
    "TMO": "XLV", "ABT": "XLV", "PFE": "XLV", "AMGN": "XLV", "DHR": "XLV",
    "BMY": "XLV", "ISRG": "XLV", "MDT": "XLV", "GILD": "XLV", "REGN": "XLV",
    "VRTX": "XLV", "SYK": "XLV", "BSX": "XLV", "ZTS": "XLV", "CI": "XLV",
    "ELV": "XLV", "BDX": "XLV", "HUM": "XLV", "MCK": "XLV", "IDXX": "XLV",
    "EW": "XLV", "A": "XLV", "IQV": "XLV", "COR": "XLV", "DXCM": "XLV",
    "MTD": "XLV", "BAX": "XLV", "GEHC": "XLV", "PODD": "XLV", "ALGN": "XLV",
    "HOLX": "XLV", "CNC": "XLV", "MOH": "XLV", "CAH": "XLV", "RMD": "XLV",
    "STE": "XLV", "COO": "XLV", "VTRS": "XLV", "BIIB": "XLV", "RVTY": "XLV",
    "SOLV": "XLV", "INCY": "XLV", "MRNA": "XLV",

    # Financials (XLF)
    "BRK-B": "XLF", "JPM": "XLF", "V": "XLF", "MA": "XLF", "BAC": "XLF",
    "WFC": "XLF", "GS": "XLF", "MS": "XLF", "BLK": "XLF", "SCHW": "XLF",
    "C": "XLF", "AXP": "XLF", "CB": "XLF", "PGR": "XLF", "MMC": "XLF",
    "AON": "XLF", "CME": "XLF", "ICE": "XLF", "USB": "XLF", "PNC": "XLF",
    "TFC": "XLF", "AIG": "XLF", "MET": "XLF", "PRU": "XLF", "ALL": "XLF",
    "AFL": "XLF", "TROW": "XLF", "AMP": "XLF", "RJF": "XLF", "BK": "XLF",
    "STT": "XLF", "FITB": "XLF", "HBAN": "XLF", "CINF": "XLF", "BRO": "XLF",
    "FDS": "XLF", "MSCI": "XLF", "NDAQ": "XLF", "CBOE": "XLF", "DFS": "XLF",
    "SYF": "XLF", "CFG": "XLF", "KEY": "XLF", "RF": "XLF", "NTRS": "XLF",
    "AIZ": "XLF", "IVZ": "XLF", "BEN": "XLF", "L": "XLF", "GL": "XLF",
    "WRB": "XLF", "RE": "XLF", "AJG": "XLF", "ACGL": "XLF", "BX": "XLF",
    "KKR": "XLF", "COF": "XLF", "FI": "XLF", "PYPL": "XLF",

    # Consumer Discretionary (XLY)
    "AMZN": "XLY", "TSLA": "XLY", "HD": "XLY", "MCD": "XLY", "NKE": "XLY",
    "LOW": "XLY", "SBUX": "XLY", "TJX": "XLY", "BKNG": "XLY", "MAR": "XLY",
    "ORLY": "XLY", "AZO": "XLY", "CMG": "XLY", "HLT": "XLY", "DHI": "XLY",
    "RCL": "XLY", "LEN": "XLY", "ROST": "XLY", "YUM": "XLY", "GRMN": "XLY",
    "DPZ": "XLY", "POOL": "XLY", "GPC": "XLY", "APTV": "XLY", "BBY": "XLY",
    "ULTA": "XLY", "EBAY": "XLY", "F": "XLY", "GM": "XLY", "PHM": "XLY",
    "CCL": "XLY", "WYNN": "XLY", "LVS": "XLY", "MGM": "XLY", "NVR": "XLY",
    "TPR": "XLY", "ABNB": "XLY", "DECK": "XLY", "CASY": "XLY", "BLDR": "XLY",
    "LULU": "XLY", "UAL": "XLY", "DAL": "XLY", "LUV": "XLY",

    # Consumer Staples (XLP)
    "PG": "XLP", "KO": "XLP", "PEP": "XLP", "COST": "XLP", "WMT": "XLP",
    "PM": "XLP", "MO": "XLP", "CL": "XLP", "MDLZ": "XLP", "STZ": "XLP",
    "GIS": "XLP", "SYY": "XLP", "ADM": "XLP", "HSY": "XLP", "KMB": "XLP",
    "KHC": "XLP", "K": "XLP", "MKC": "XLP", "CHD": "XLP", "SJM": "XLP",
    "TSN": "XLP", "HRL": "XLP", "CPB": "XLP", "CAG": "XLP", "BG": "XLP",
    "WBA": "XLP", "EL": "XLP", "KR": "XLP", "TGT": "XLP", "DG": "XLP",
    "DLTR": "XLP", "CLX": "XLP", "BF-B": "XLP", "TAP": "XLP", "MNST": "XLP",
    "KVUE": "XLP",

    # Industrials (XLI)
    "RTX": "XLI", "HON": "XLI", "UNP": "XLI", "UPS": "XLI", "CAT": "XLI",
    "BA": "XLI", "DE": "XLI", "GE": "XLI", "LMT": "XLI", "MMM": "XLI",
    "GD": "XLI", "NOC": "XLI", "WM": "XLI", "RSG": "XLI", "ETN": "XLI",
    "EMR": "XLI", "ITW": "XLI", "CSX": "XLI", "NSC": "XLI", "TT": "XLI",
    "CARR": "XLI", "ROK": "XLI", "IR": "XLI", "SWK": "XLI", "PH": "XLI",
    "PCAR": "XLI", "AME": "XLI", "GWW": "XLI", "CTAS": "XLI", "PAYX": "XLI",
    "FAST": "XLI", "OTIS": "XLI", "FTV": "XLI", "AOS": "XLI", "HWM": "XLI",
    "XYL": "XLI", "IEX": "XLI", "DOV": "XLI", "ROP": "XLI", "WAB": "XLI",
    "AXON": "XLI", "VRSK": "XLI", "PWR": "XLI", "J": "XLI", "LDOS": "XLI",
    "BR": "XLI", "ALLE": "XLI", "GNRC": "XLI", "DAY": "XLI", "TKO": "XLI",
    "HUBB": "XLI", "PNR": "XLI", "CHRW": "XLI", "JBHT": "XLI",

    # Energy (XLE)
    "XOM": "XLE", "CVX": "XLE", "COP": "XLE", "SLB": "XLE", "EOG": "XLE",
    "MPC": "XLE", "VLO": "XLE", "PSX": "XLE", "OXY": "XLE", "HAL": "XLE",
    "DVN": "XLE", "HES": "XLE", "FANG": "XLE", "BKR": "XLE", "CTRA": "XLE",
    "APA": "XLE", "MRO": "XLE", "EQT": "XLE", "CF": "XLE",

    # Utilities (XLU)
    "NEE": "XLU", "SO": "XLU", "DUK": "XLU", "D": "XLU", "AEP": "XLU",
    "SRE": "XLU", "EXC": "XLU", "XEL": "XLU", "ED": "XLU", "WEC": "XLU",
    "PEG": "XLU", "ES": "XLU", "AWK": "XLU", "AEE": "XLU", "CMS": "XLU",
    "DTE": "XLU", "FE": "XLU", "PPL": "XLU", "CEG": "XLU", "ETR": "XLU",
    "AES": "XLU", "LNT": "XLU", "EVRG": "XLU", "NI": "XLU", "ATO": "XLU",
    "NRG": "XLU", "PNW": "XLU", "VST": "XLU",

    # Real Estate (XLRE)
    "PLD": "XLRE", "AMT": "XLRE", "CCI": "XLRE", "EQIX": "XLRE", "PSA": "XLRE",
    "SPG": "XLRE", "O": "XLRE", "WELL": "XLRE", "DLR": "XLRE", "VICI": "XLRE",
    "ARE": "XLRE", "SBAC": "XLRE", "AVB": "XLRE", "EQR": "XLRE", "VTR": "XLRE",
    "MAA": "XLRE", "ESS": "XLRE", "INVH": "XLRE", "KIM": "XLRE", "REG": "XLRE",
    "UDR": "XLRE", "HST": "XLRE", "CPT": "XLRE", "BXP": "XLRE", "IRM": "XLRE",

    # Materials (XLB)
    "LIN": "XLB", "APD": "XLB", "SHW": "XLB", "ECL": "XLB", "FCX": "XLB",
    "NEM": "XLB", "NUE": "XLB", "DOW": "XLB", "DD": "XLB", "PPG": "XLB",
    "VMC": "XLB", "MLM": "XLB", "IP": "XLB", "PKG": "XLB", "AVY": "XLB",
    "BALL": "XLB", "CF": "XLB", "MOS": "XLB", "ALB": "XLB", "CE": "XLB",
    "AMCR": "XLB", "IFF": "XLB", "EMN": "XLB",

    # Communication Services (XLC)
    "GOOGL": "XLC", "GOOG": "XLC", "META": "XLC", "NFLX": "XLC", "DIS": "XLC",
    "CMCSA": "XLC", "VZ": "XLC", "T": "XLC", "TMUS": "XLC", "CHTR": "XLC",
    "EA": "XLC", "TTWO": "XLC", "WBD": "XLC", "PARA": "XLC", "OMC": "XLC",
    "IPG": "XLC", "LYV": "XLC", "MTCH": "XLC", "FOXA": "XLC", "FOX": "XLC",
    "TTD": "XLC", "PINS": "XLC", "SNAP": "XLC", "RBLX": "XLC", "ZM": "XLC",
}


def get_sector_etf(ticker: str) -> str | None:
    """
    Fast O(1) lookup: ticker → sector ETF.

    Uses the static SP500_SECTOR_MAP. No DB queries.
    Returns None for ETFs, indices, and unmapped tickers.
    """
    return SP500_SECTOR_MAP.get(ticker)
