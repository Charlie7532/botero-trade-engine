#!/usr/bin/env python3
"""
Migration Script: Clean and Standardize market.ticker_metadata
==============================================================
Applies the following audited fixes in an atomic PostgreSQL transaction:

1. ETFs with sector = 'ETF' (30 tickers):
   - 11 Sector ETFs (XLB..XLY) -> GICS Sectors (Materials..Consumer Discretionary)
   - 3 Broad Market ETFs (DIA, IWM, RSP) -> 'Broad Market'
   - 12 International ETFs (EEM, EFA, EWG..VGK) -> 'International'
   - 4 Commodity / Fixed Income ETFs (GLD, SLV, USO, IEF) -> 'Commodities' / 'Fixed Income'
   - market_cap_bucket set to 'MEGA' for major ETFs (SPY, QQQ, DIA, IWM), 'LARGE' for sector ETFs, 'None' for rest.

2. Stock Sector Normalization (Finviz -> GICS Canonical):
   - 'Consumer Cyclical' -> 'Consumer Discretionary' (56 tickers)
   - 'Consumer Defensive' -> 'Consumer Staples' (36 tickers)
   - 'Financial Services' -> 'Financials' (71 tickers)
   - 'Basic Materials' -> 'Materials' (20 tickers)

3. market_cap_bucket Casing Standardization:
   - 'large' -> 'LARGE'
   - 'mega' -> 'MEGA'
   - 'mid' -> 'MID'
   - 'small' -> 'SMALL'

4. Generic Indicators (PCCE, TRIN):
   - PCCE: sector = 'Options Flow' (industry = 'Options Sentiment' preserved)
   - TRIN: sector = 'Market Internals' (industry = 'Market Internals' preserved)

Usage:
  PYTHONPATH=. backend/.venv/bin/python scratch/migrate_ticker_metadata_classification.py [--commit]
"""
import sys
import argparse
import psycopg2
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

ETF_SECTOR_UPDATES = {
    # 11 Sector ETFs
    "XLK": ("Technology", "LARGE"),
    "XLV": ("Healthcare", "LARGE"),
    "XLF": ("Financials", "LARGE"),
    "XLY": ("Consumer Discretionary", "LARGE"),
    "XLP": ("Consumer Staples", "LARGE"),
    "XLI": ("Industrials", "LARGE"),
    "XLE": ("Energy", "LARGE"),
    "XLU": ("Utilities", "LARGE"),
    "XLRE": ("Real Estate", "LARGE"),
    "XLB": ("Materials", "LARGE"),
    "XLC": ("Communication Services", "LARGE"),

    # Broad Market / Indices
    "DIA": ("Broad Market", "MEGA"),
    "IWM": ("Broad Market", "MEGA"),
    "RSP": ("Broad Market", "LARGE"),

    # International
    "EEM": ("International", "LARGE"),
    "EFA": ("International", "LARGE"),
    "EWG": ("International", None),
    "EWJ": ("International", "LARGE"),
    "EWT": ("International", None),
    "EWU": ("International", None),
    "EWY": ("International", None),
    "EWZ": ("International", None),
    "FXI": ("International", None),
    "INDA": ("International", None),
    "VEA": ("International", "LARGE"),
    "VGK": ("International", None),

    # Commodities & Fixed Income
    "GLD": ("Commodities", "MEGA"),
    "SLV": ("Commodities", "LARGE"),
    "USO": ("Commodities", None),
    "IEF": ("Fixed Income", "LARGE"),
}

STOCK_SECTOR_CANONICAL = {
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Financial Services": "Financials",
    "Basic Materials": "Materials",
}

def run_migration(commit: bool = False):
    store = TimescaleDataStore()
    conn = store._conn()
    
    print("=" * 80)
    print(f"MIGRATION: market.ticker_metadata Standardization (Mode: {'COMMIT' if commit else 'DRY-RUN / ROLLBACK'})")
    print("=" * 80)

    try:
        with conn.cursor() as cur:
            # 1. Update 30 ETFs
            print("\n1. Updating 30 ETFs with sector = 'ETF'...")
            etf_count = 0
            for ticker, (sector, cap) in ETF_SECTOR_UPDATES.items():
                cur.execute("""
                    UPDATE market.ticker_metadata
                    SET sector = %s,
                        market_cap_bucket = %s,
                        updated_at = NOW()
                    WHERE ticker = %s AND sector = 'ETF'
                """, (sector, cap, ticker))
                if cur.rowcount > 0:
                    etf_count += cur.rowcount
                    print(f"  ✓ {ticker:<5} -> sector='{sector}', cap='{cap}'")
            print(f"  Total ETFs updated: {etf_count}")

            # 2. Canonicalize Stock Sectors
            print("\n2. Canonicalizing Stock Sectors (Finviz -> GICS)...")
            stock_count = 0
            for finviz_sec, gics_sec in STOCK_SECTOR_CANONICAL.items():
                cur.execute("""
                    UPDATE market.ticker_metadata
                    SET sector = %s,
                        updated_at = NOW()
                    WHERE sector = %s AND asset_type = 'STOCK'
                """, (gics_sec, finviz_sec))
                print(f"  ✓ '{finviz_sec}' -> '{gics_sec}': {cur.rowcount} stocks")
                stock_count += cur.rowcount
            print(f"  Total Stocks updated: {stock_count}")

            # 3. Standardize market_cap_bucket Casing
            print("\n3. Standardizing market_cap_bucket Casing...")
            cap_updates = [("large", "LARGE"), ("mega", "MEGA"), ("mid", "MID"), ("small", "SMALL")]
            cap_count = 0
            for old_cap, new_cap in cap_updates:
                cur.execute("""
                    UPDATE market.ticker_metadata
                    SET market_cap_bucket = %s,
                        updated_at = NOW()
                    WHERE market_cap_bucket = %s
                """, (new_cap, old_cap))
                print(f"  ✓ '{old_cap}' -> '{new_cap}': {cur.rowcount} rows")
                cap_count += cur.rowcount
            print(f"  Total Cap buckets normalized: {cap_count}")

            # 4. Indicators with generic sector = 'Indicator'
            print("\n4. Fixing generic sector on PCCE and TRIN...")
            cur.execute("""
                UPDATE market.ticker_metadata
                SET sector = 'Options Flow', updated_at = NOW()
                WHERE ticker = 'PCCE' AND sector = 'Indicator'
            """)
            print(f"  ✓ PCCE -> sector='Options Flow' ({cur.rowcount} rows)")
            cur.execute("""
                UPDATE market.ticker_metadata
                SET sector = 'Market Internals', updated_at = NOW()
                WHERE ticker = 'TRIN' AND sector = 'Indicator'
            """)
            print(f"  ✓ TRIN -> sector='Market Internals' ({cur.rowcount} rows)")

            # Post-check validation
            print("\n" + "-" * 80)
            print("POST-CHECK VALIDATION QUERY IN TRANSACTION:")
            print("-" * 80)
            cur.execute("""
                SELECT sector, COUNT(*) 
                FROM market.ticker_metadata 
                GROUP BY sector 
                ORDER BY COUNT(*) DESC
            """)
            for sec, cnt in cur.fetchall():
                print(f"  {sec:<25}: {cnt}")

            if commit:
                conn.commit()
                print("\n✅ TRANSACTION COMMITTED SUCCESSFULLY!")
            else:
                conn.rollback()
                print("\n🔄 DRY-RUN COMPLETE. TRANSACTION ROLLED BACK. No changes saved to DB.")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ ERROR OCCURRED: {e}. Transaction rolled back.")
        raise
    finally:
        store._put(conn)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="Commit changes to database")
    args = parser.parse_args()
    run_migration(commit=args.commit)
