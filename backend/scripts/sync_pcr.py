"""
CBOE PCR Sync Pipeline
======================
Automatically updates the CBOE_PCR in the Neon Vault from a TradingView CSV export.

Usage:
  1. Export the 'USI:PCC' chart from TradingView as CSV.
  2. Save it to `backend/data/imports/` (any filename ending in .csv).
  3. Run: python -m backend.scripts.sync_pcr

The script is idempotent: it will only append NEW bars that don't already exist
in the database, meaning you can drop overlapping CSVs without corrupting history.
"""
import os
import glob
import logging
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

IMPORT_DIR = "backend/data/imports"

def main():
    if not os.path.exists(IMPORT_DIR):
        os.makedirs(IMPORT_DIR)
        
    csv_files = glob.glob(f"{IMPORT_DIR}/*.csv")
    
    if not csv_files:
        logger.warning(f"⚠️ No CSV files found in {IMPORT_DIR}.")
        logger.info("Drop your TradingView export (USI_PCC) there and run again.")
        return
        
    # Take the most recently modified CSV
    latest_csv = max(csv_files, key=os.path.getmtime)
    logger.info(f"📂 Found CSV: {latest_csv}")
    
    try:
        df = pd.read_csv(latest_csv)
        if 'time' not in df.columns or 'close' not in df.columns:
            logger.error("❌ Invalid CSV format. Expected 'time' and 'close' columns.")
            return
            
        df['date'] = pd.to_datetime(df['time'], unit='s')
        df = df.set_index('date')
        df = df[['open', 'high', 'low', 'close']]
        df['volume'] = 0
        
    except Exception as e:
        logger.error(f"❌ Error reading CSV: {e}")
        return

    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()
    
    # Check what we already have
    existing_last = store.bars_last_date("CBOE_PCR", "1d")
    
    if existing_last:
        logger.info(f"📊 Current Vault state: CBOE_PCR updated up to {existing_last.date()}")
        # Filter to strictly new rows
        cutoff = pd.to_datetime(existing_last)
        df_new = df[df.index > cutoff]
    else:
        logger.info("📊 Current Vault state: No data found. Doing full initial import.")
        df_new = df
        
    if df_new.empty:
        logger.info("✅ Vault is already up to date. No new bars to insert.")
    else:
        logger.info(f"🚀 Inserting {len(df_new)} NEW bars...")
        store.save_bars("CBOE_PCR", "1d", df_new)
        logger.info(f"✅ Success! CBOE_PCR is now updated up to {df_new.index.max().date()}")
        
    store.close()
    
    # Auto-cleanup
    os.remove(latest_csv)
    logger.info(f"🧹 Cleaned up file: {latest_csv}")

if __name__ == "__main__":
    print("=" * 60)
    print("CBOE_PCR VAULT SYNC")
    print("=" * 60)
    main()
