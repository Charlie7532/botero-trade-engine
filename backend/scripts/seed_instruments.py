"""
Seed Instruments — Fetch metadata from Yahoo Finance and generate seed JSON.

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/seed_instruments.py

Generates: src/collections/Instruments/seed-data.json
This file is consumed by Payload's onInit hook to populate the instruments collection.
"""
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    logger.error("yfinance not installed. Run: pip install yfinance")
    sys.exit(1)


# ─── Base ETFs (25 instruments) ────────────────────────────────

SECTOR_ETFS = [
    {"ticker": "XLK", "name": "Technology Select Sector", "gicsSector": "information_technology", "cyclicalType": "cyclical", "universe": "domestic_sector"},
    {"ticker": "XLV", "name": "Health Care Select Sector", "gicsSector": "health_care", "cyclicalType": "defensive", "universe": "domestic_sector"},
    {"ticker": "XLF", "name": "Financial Select Sector", "gicsSector": "financials", "cyclicalType": "cyclical", "universe": "domestic_sector"},
    {"ticker": "XLY", "name": "Consumer Discretionary Select", "gicsSector": "consumer_discretionary", "cyclicalType": "cyclical", "universe": "domestic_sector"},
    {"ticker": "XLP", "name": "Consumer Staples Select", "gicsSector": "consumer_staples", "cyclicalType": "defensive", "universe": "domestic_sector"},
    {"ticker": "XLI", "name": "Industrial Select Sector", "gicsSector": "industrials", "cyclicalType": "cyclical", "universe": "domestic_sector"},
    {"ticker": "XLE", "name": "Energy Select Sector", "gicsSector": "energy", "cyclicalType": "cyclical", "universe": "domestic_sector"},
    {"ticker": "XLU", "name": "Utilities Select Sector", "gicsSector": "utilities", "cyclicalType": "defensive", "universe": "domestic_sector"},
    {"ticker": "XLRE", "name": "Real Estate Select Sector", "gicsSector": "real_estate", "cyclicalType": "cyclical", "universe": "domestic_sector"},
    {"ticker": "XLB", "name": "Materials Select Sector", "gicsSector": "materials", "cyclicalType": "cyclical", "universe": "domestic_sector"},
    {"ticker": "XLC", "name": "Communication Services Select", "gicsSector": "communication_services", "cyclicalType": "mixed", "universe": "domestic_sector"},
]

INTERNATIONAL_ETFS = [
    {"ticker": "EWZ", "name": "iShares MSCI Brazil", "universe": "international", "cyclicalType": "cyclical"},
    {"ticker": "EWJ", "name": "iShares MSCI Japan", "universe": "international", "cyclicalType": "mixed"},
    {"ticker": "FXI", "name": "iShares China Large-Cap", "universe": "international", "cyclicalType": "cyclical"},
    {"ticker": "EWG", "name": "iShares MSCI Germany", "universe": "international", "cyclicalType": "cyclical"},
    {"ticker": "EWU", "name": "iShares MSCI United Kingdom", "universe": "international", "cyclicalType": "mixed"},
    {"ticker": "EWY", "name": "iShares MSCI South Korea", "universe": "international", "cyclicalType": "cyclical"},
    {"ticker": "EWT", "name": "iShares MSCI Taiwan", "universe": "international", "cyclicalType": "cyclical"},
    {"ticker": "INDA", "name": "iShares MSCI India", "universe": "international", "cyclicalType": "cyclical"},
    {"ticker": "EEM", "name": "iShares MSCI Emerging Markets", "universe": "international", "cyclicalType": "cyclical"},
    {"ticker": "VEA", "name": "Vanguard FTSE Developed Markets", "universe": "international", "cyclicalType": "mixed"},
]

COMMODITY_ETFS = [
    {"ticker": "GLD", "name": "SPDR Gold Shares", "universe": "commodity", "cyclicalType": "defensive"},
    {"ticker": "SLV", "name": "iShares Silver Trust", "universe": "commodity", "cyclicalType": "cyclical"},
    {"ticker": "USO", "name": "United States Oil Fund", "universe": "commodity", "cyclicalType": "cyclical"},
]

INDEX_ETFS = [
    {"ticker": "SPY", "name": "SPDR S&P 500 ETF Trust", "universe": "sp500", "cyclicalType": "mixed"},
]

# GICS sector mapping for S&P 500 stocks (Yahoo Finance sector → our enum)
YAHOO_SECTOR_MAP = {
    "Technology": "information_technology",
    "Information Technology": "information_technology",
    "Healthcare": "health_care",
    "Health Care": "health_care",
    "Financial Services": "financials",
    "Financials": "financials",
    "Consumer Cyclical": "consumer_discretionary",
    "Consumer Discretionary": "consumer_discretionary",
    "Consumer Defensive": "consumer_staples",
    "Consumer Staples": "consumer_staples",
    "Industrials": "industrials",
    "Energy": "energy",
    "Utilities": "utilities",
    "Real Estate": "real_estate",
    "Basic Materials": "materials",
    "Materials": "materials",
    "Communication Services": "communication_services",
}

# Sector ETF mapping
SECTOR_TO_ETF = {
    "information_technology": "XLK",
    "health_care": "XLV",
    "financials": "XLF",
    "consumer_discretionary": "XLY",
    "consumer_staples": "XLP",
    "industrials": "XLI",
    "energy": "XLE",
    "utilities": "XLU",
    "real_estate": "XLRE",
    "materials": "XLB",
    "communication_services": "XLC",
}


def fetch_sp500_tickers() -> list[str]:
    """
    Fetch S&P 500 constituent tickers.
    Strategy: Wikipedia with proper headers → hardcoded top-50 fallback.
    """
    # Strategy 1: Wikipedia with browser headers
    try:
        import pandas as pd
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            storage_options={"User-Agent": "Mozilla/5.0"},
        )
        df = tables[0]
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        logger.info(f"Fetched {len(tickers)} S&P 500 tickers from Wikipedia")
        return tickers
    except Exception as e:
        logger.warning(f"Wikipedia fetch failed: {e}")

    # Strategy 2: Hardcoded top-50 S&P 500 by market cap (always available)
    logger.info("Using hardcoded top-50 S&P 500 tickers as fallback")
    return [
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK-B",
        "LLY", "AVGO", "JPM", "TSLA", "UNH", "XOM", "V", "MA", "PG",
        "COST", "JNJ", "HD", "MRK", "ABBV", "WMT", "NFLX", "CRM",
        "BAC", "CVX", "AMD", "KO", "PEP", "TMO", "LIN", "ORCL", "ACN",
        "MCD", "CSCO", "ADBE", "WFC", "ABT", "PM", "IBM", "GE", "CAT",
        "TXN", "NOW", "ISRG", "INTU", "QCOM", "AMGN", "VZ",
        "DIS", "AMAT", "BKNG", "MS", "SPGI", "NEE", "PFE", "HON",
        "LOW", "GS", "UNP", "RTX", "T", "BLK", "ELV", "SYK", "ADP",
        "SBUX", "TJX", "MDLZ", "SCHW", "DE", "PLD", "LRCX", "BMY",
        "MMC", "VRTX", "CB", "CL", "CI", "SO", "AMT", "FI", "MO",
        "BSX", "CME", "SLB", "EQIX", "DUK", "APD", "REGN", "ICE",
        "PGR", "EOG", "AON", "BDX", "ITW", "CSX", "WM", "EMR",
    ]


def enrich_with_yahoo(ticker: str) -> dict:
    """Fetch instrument metadata from Yahoo Finance."""
    try:
        info = yf.Ticker(ticker).info
        return {
            "name": info.get("longName") or info.get("shortName") or ticker,
            "marketCap": classify_market_cap(info.get("marketCap", 0)),
            "gicsSector": YAHOO_SECTOR_MAP.get(info.get("sector", ""), ""),
            "gicsIndustry": info.get("industry", ""),
        }
    except Exception as e:
        logger.warning(f"Yahoo enrichment failed for {ticker}: {e}")
        return {}


def classify_market_cap(mcap: int) -> str:
    """Classify market cap into tiers."""
    if mcap > 200_000_000_000:
        return "mega"
    elif mcap > 10_000_000_000:
        return "large"
    elif mcap > 2_000_000_000:
        return "mid"
    else:
        return "small"


def build_seed_data(include_sp500: bool = True) -> list[dict]:
    """Build the complete seed data list."""
    instruments = []

    # 1. Sector ETFs
    for etf in SECTOR_ETFS:
        record = {
            "ticker": etf["ticker"],
            "name": etf["name"],
            "instrumentType": "etf_sector",
            "gicsSector": etf.get("gicsSector", ""),
            "universe": etf["universe"],
            "cyclicalType": etf.get("cyclicalType", "mixed"),
            "isActive": True,
            "isInSP500": False,
        }
        # Enrich with Yahoo
        yahoo = enrich_with_yahoo(etf["ticker"])
        if yahoo.get("name"):
            record["name"] = yahoo["name"]
        instruments.append(record)
        logger.info(f"  ✅ {etf['ticker']} — {record['name']}")

    # 2. International ETFs
    for etf in INTERNATIONAL_ETFS:
        record = {
            "ticker": etf["ticker"],
            "name": etf["name"],
            "instrumentType": "etf_international",
            "universe": etf["universe"],
            "cyclicalType": etf.get("cyclicalType", "mixed"),
            "isActive": True,
            "isInSP500": False,
        }
        yahoo = enrich_with_yahoo(etf["ticker"])
        if yahoo.get("name"):
            record["name"] = yahoo["name"]
        instruments.append(record)
        logger.info(f"  ✅ {etf['ticker']} — {record['name']}")

    # 3. Commodity ETFs
    for etf in COMMODITY_ETFS:
        record = {
            "ticker": etf["ticker"],
            "name": etf["name"],
            "instrumentType": "etf_commodity",
            "universe": etf["universe"],
            "cyclicalType": etf.get("cyclicalType", "mixed"),
            "isActive": True,
            "isInSP500": False,
        }
        yahoo = enrich_with_yahoo(etf["ticker"])
        if yahoo.get("name"):
            record["name"] = yahoo["name"]
        instruments.append(record)
        logger.info(f"  ✅ {etf['ticker']} — {record['name']}")

    # 4. Index ETFs (SPY)
    for etf in INDEX_ETFS:
        record = {
            "ticker": etf["ticker"],
            "name": etf["name"],
            "instrumentType": "index",
            "universe": etf["universe"],
            "cyclicalType": etf.get("cyclicalType", "mixed"),
            "isActive": True,
            "isInSP500": False,
        }
        yahoo = enrich_with_yahoo(etf["ticker"])
        if yahoo.get("name"):
            record["name"] = yahoo["name"]
        instruments.append(record)
        logger.info(f"  ✅ {etf['ticker']} — {record['name']}")

    # 5. S&P 500 stocks
    if include_sp500:
        sp500_tickers = fetch_sp500_tickers()
        # Skip ETFs already added
        existing_tickers = {i["ticker"] for i in instruments}

        total = len(sp500_tickers)
        for idx, ticker in enumerate(sp500_tickers):
            if ticker in existing_tickers:
                continue

            yahoo = enrich_with_yahoo(ticker)
            gics = yahoo.get("gicsSector", "")
            sector_etf = SECTOR_TO_ETF.get(gics, "")

            record = {
                "ticker": ticker,
                "name": yahoo.get("name", ticker),
                "instrumentType": "stock",
                "gicsSector": gics,
                "gicsIndustry": yahoo.get("gicsIndustry", ""),
                "universe": "sp500",
                "cyclicalType": "cyclical" if gics in (
                    "information_technology", "consumer_discretionary",
                    "financials", "energy", "materials", "industrials",
                ) else "defensive" if gics in (
                    "health_care", "consumer_staples", "utilities",
                ) else "mixed",
                "marketCap": yahoo.get("marketCap", "large"),
                "isActive": True,
                "isInSP500": True,
                "sectorETFTicker": sector_etf,  # Resolved to FK later by Payload seed
            }
            instruments.append(record)

            if (idx + 1) % 50 == 0:
                logger.info(f"  📊 Progress: {idx + 1}/{total} S&P 500 stocks processed")

        logger.info(f"  ✅ {len(sp500_tickers)} S&P 500 stocks processed")

    logger.info(f"\n{'='*60}")
    logger.info(f"Total instruments: {len(instruments)}")
    logger.info(f"  ETFs (sector):        {sum(1 for i in instruments if i['instrumentType'] == 'etf_sector')}")
    logger.info(f"  ETFs (international): {sum(1 for i in instruments if i['instrumentType'] == 'etf_international')}")
    logger.info(f"  ETFs (commodity):     {sum(1 for i in instruments if i['instrumentType'] == 'etf_commodity')}")
    logger.info(f"  Index:                {sum(1 for i in instruments if i['instrumentType'] == 'index')}")
    logger.info(f"  Stocks:               {sum(1 for i in instruments if i['instrumentType'] == 'stock')}")

    return instruments


def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Seed instruments data from Yahoo Finance")
    parser.add_argument("--etfs-only", action="store_true", help="Only fetch 25 base ETFs (skip S&P 500)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path")
    args = parser.parse_args()

    logger.info("🌱 Seeding instruments from Yahoo Finance...")

    instruments = build_seed_data(include_sp500=not args.etfs_only)

    # Output path
    output_path = args.output or str(
        Path(__file__).resolve().parent.parent.parent / "src" / "collections" / "Instruments" / "seed-data.json"
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(instruments, f, indent=2, ensure_ascii=False)

    logger.info(f"💾 Seed data written to: {output_path}")
    logger.info(f"   {len(instruments)} instruments ready for Payload import")


if __name__ == "__main__":
    main()
